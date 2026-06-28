"""API tests for admin RBAC routes."""

from collections.abc import Generator
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import get_current_active_user, require_admin
from ai_qa.api.auth.session import SessionManager
from ai_qa.auth.service import ADMIN_ROLE, STANDARD_ROLE
from ai_qa.db.base import Base
from ai_qa.db.models import Project, ProjectMembership, User


@pytest.fixture
def admin_client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=cast(list[Table], [User.__table__, Project.__table__, ProjectMembership.__table__]),
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db_session() -> Generator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db_session_dependency] = override_get_db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    engine.dispose()


def _session_from_override(client: TestClient) -> Generator[Session]:
    app = cast(FastAPI, client.app)
    db_override = app.dependency_overrides[get_db_session_dependency]
    return cast(Generator[Session], db_override())


def _create_user(client: TestClient, email: str, role: str, *, active: bool = True) -> User:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        user = User(
            email=email,
            display_name=email.split("@")[0],
            role=role,
            is_active=active,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session_gen.close()


def _token(client: TestClient, user: User) -> str:
    app = cast(FastAPI, client.app)
    session_manager = SessionManager(app.state.settings)
    session = session_manager.create_session(
        {
            "user_id": str(user.id),
            "email": user.email,
            "name": user.display_name,
            "role": user.role,
            "is_active": user.is_active,
        }
    )
    return session_manager.encode_session(session)  # type: ignore[no-any-return]


def _auth_headers(client: TestClient, user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client, user)}"}


@pytest.mark.asyncio
async def test_require_admin_allows_active_admin_and_rejects_standard(
    admin_client: TestClient,
) -> None:
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)

    async def _current_user_for(user: User) -> User:
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/admin/users",
                "headers": [],
                "app": cast(FastAPI, admin_client.app),
            }
        )
        app = cast(FastAPI, admin_client.app)
        request.state.user = SessionManager(app.state.settings).decode_session(
            _token(admin_client, user)
        )
        session_gen = _session_from_override(admin_client)
        session = next(session_gen)
        try:
            return await get_current_active_user(request, session)
        finally:
            session_gen.close()

    current_admin = await _current_user_for(admin)
    assert (await require_admin(current_admin)).email == "admin@example.com"

    current_standard = await _current_user_for(standard)
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(current_standard)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Forbidden"


@pytest.mark.asyncio
async def test_current_user_rejects_malformed_request_state(admin_client: TestClient) -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/admin/users",
            "headers": [],
            "app": admin_client.app,
        }
    )
    request.state.user = SimpleNamespace(user_id="00000000-0000-0000-0000-000000000001")
    session_gen = _session_from_override(admin_client)
    session = next(session_gen)
    try:
        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(request, session)
    finally:
        session_gen.close()

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Not authenticated"


def test_admin_can_list_users_with_safe_project_memberships(admin_client: TestClient) -> None:
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)
    project_response = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Quality Workspace",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )
    project_id = project_response.json()["id"]
    admin_client.post(
        f"/api/admin/projects/{project_id}/memberships",
        headers=_auth_headers(admin_client, admin),
        json={"user_id": str(standard.id), "role": "owner"},
    )

    response = admin_client.get("/api/admin/users", headers=_auth_headers(admin_client, admin))

    assert response.status_code == 200
    users = response.json()
    assert [user["email"] for user in users] == ["admin@example.com", "standard@example.com"]
    standard_user = next(user for user in users if user["email"] == "standard@example.com")
    assert standard_user["project_memberships"] == [
        {
            "id": standard_user["project_memberships"][0]["id"],
            "project_id": project_id,
            "project_name": "Quality Workspace",
            "role": "owner",
            "created_at": standard_user["project_memberships"][0]["created_at"],
            "updated_at": standard_user["project_memberships"][0]["updated_at"],
        }
    ]
    assert "user_id" not in standard_user["project_memberships"][0]
    assert "ai_provider_config" not in standard_user["project_memberships"][0]


def test_standard_and_unauthenticated_users_cannot_list_admin_users(
    admin_client: TestClient,
) -> None:
    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)

    forbidden = admin_client.get("/api/admin/users", headers=_auth_headers(admin_client, standard))
    unauthenticated = admin_client.get("/api/admin/users")

    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "Forbidden"
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["detail"] == "Not authenticated"


def test_admin_can_create_project_and_standard_user_cannot(admin_client: TestClient) -> None:
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)

    created = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "  Quality Workspace  ",
            "description": "  Core QA project  ",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )
    denied = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, standard),
        json={
            "name": "Denied",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )
    blank = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={"name": "   ", "confluence_base_url": "https://mcp", "enabled_providers": ["claude"]},
    )

    assert created.status_code == 200
    project = created.json()
    assert project["name"] == "Quality Workspace"
    assert project["description"] == "Core QA project"
    assert project["created_by_user_id"] == str(admin.id)
    assert denied.status_code == 403
    assert blank.status_code == 422


def test_admin_create_project_no_longer_enforces_link_or_provider(
    admin_client: TestClient,
) -> None:
    """Admin now creates a bare project (name + description only).

    The at-least-one-link / at-least-one-provider invariants MOVED to the project_admin
    config endpoint (``PUT /project-admin/projects/{id}/config``, covered in
    test_project_admin_rbac.py). So at the admin endpoint these create cleanly now.
    """
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)

    # No links, no providers — previously 422, now allowed (a bare project).
    bare = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={"name": "Bare"},
    )
    # Blank links are normalized to None rather than rejected.
    blank_links = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={"name": "Blank Links", "confluence_base_url": "", "jira_base_url": ""},
    )

    assert bare.status_code == 200
    assert bare.json()["enabled_providers"] == []
    assert bare.json()["confluence_base_url"] is None
    assert blank_links.status_code == 200
    assert blank_links.json()["confluence_base_url"] is None
    assert blank_links.json()["jira_base_url"] is None


def test_admin_project_list_exposes_jira_url_and_enabled_providers(
    admin_client: TestClient,
) -> None:
    """Test that project list and detail endpoints expose jira_base_url and enabled_providers.

    Story 8.5: Admin Dashboard must display Jira link and provider icons.
    """
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)

    # Create projects with various configurations
    confluence_only = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Confluence Only",
            "confluence_base_url": "https://confluence.example.com",
            "enabled_providers": ["claude", "gemini"],
        },
    )
    assert confluence_only.status_code == 200
    jira_only = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Jira Only",
            "jira_base_url": "https://jira.example.com",
            "enabled_providers": ["openai"],
        },
    )
    assert jira_only.status_code == 200
    both_links = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Both Links",
            "confluence_base_url": "https://confluence.example.com",
            "jira_base_url": "https://jira.example.com",
            "enabled_providers": ["claude", "browser-use-cloud", "on-premises"],
        },
    )
    assert both_links.status_code == 200

    # List all projects (the project-list endpoint lives on the projects router,
    # not the admin router; admins receive every project).
    list_response = admin_client.get(
        "/api/projects",
        headers=_auth_headers(admin_client, admin),
    )
    assert list_response.status_code == 200
    projects = list_response.json()

    # Find each project by name and verify fields
    confluence_proj = next(p for p in projects if p["name"] == "Confluence Only")
    assert confluence_proj["confluence_base_url"] == "https://confluence.example.com"
    assert confluence_proj["jira_base_url"] is None
    assert sorted(confluence_proj["enabled_providers"]) == ["claude", "gemini"]

    jira_proj = next(p for p in projects if p["name"] == "Jira Only")
    assert jira_proj["confluence_base_url"] is None
    assert jira_proj["jira_base_url"] == "https://jira.example.com"
    assert jira_proj["enabled_providers"] == ["openai"]

    both_proj = next(p for p in projects if p["name"] == "Both Links")
    assert both_proj["confluence_base_url"] == "https://confluence.example.com"
    assert both_proj["jira_base_url"] == "https://jira.example.com"
    assert sorted(both_proj["enabled_providers"]) == ["browser-use-cloud", "claude", "on-premises"]


def test_admin_project_update_preserves_jira_url_and_enabled_providers(
    admin_client: TestClient,
) -> None:
    """Test that updating a project can modify jira_base_url and enabled_providers.

    Story 8.3: Admin must be able to update project with new configuration.
    """
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)

    # Create project with Confluence only
    create = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Original Project",
            "confluence_base_url": "https://confluence.example.com",
            "enabled_providers": ["claude"],
        },
    )
    assert create.status_code == 200
    project_id = create.json()["id"]

    # Update with Jira URL and additional providers
    update = admin_client.put(
        f"/api/admin/projects/{project_id}",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Updated Project",
            "confluence_base_url": "https://confluence.example.com",
            "jira_base_url": "https://jira.example.com",
            "enabled_providers": ["claude", "gemini", "openai"],
        },
    )
    assert update.status_code == 200
    assert update.json()["jira_base_url"] == "https://jira.example.com"
    assert sorted(update.json()["enabled_providers"]) == ["claude", "gemini", "openai"]

    # Update to remove Confluence (keep only Jira)
    update2 = admin_client.put(
        f"/api/admin/projects/{project_id}",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Updated Project",
            "confluence_base_url": None,
            "jira_base_url": "https://jira.example.com",
            "enabled_providers": ["gemini"],
        },
    )
    assert update2.status_code == 200
    assert update2.json()["confluence_base_url"] is None
    assert update2.json()["jira_base_url"] == "https://jira.example.com"
    assert update2.json()["enabled_providers"] == ["gemini"]


def test_admin_cannot_create_project_with_duplicate_name(admin_client: TestClient) -> None:
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)

    first = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Quality Workspace",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )
    duplicate = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "  Quality Workspace  ",
            "confluence_base_url": "https://other",
            "enabled_providers": ["claude"],
        },
    )

    assert first.status_code == 200
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Project name already exists"


def test_admin_cannot_rename_project_to_existing_name(admin_client: TestClient) -> None:
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    first = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Alpha",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )
    second = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Beta",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )
    second_id = second.json()["id"]

    # Renaming Beta -> Alpha collides with the first project.
    conflict = admin_client.put(
        f"/api/admin/projects/{second_id}",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Alpha",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )
    # Renaming Beta -> Beta (its own name) must remain allowed.
    same_name = admin_client.put(
        f"/api/admin/projects/{second_id}",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Beta",
            "confluence_base_url": "https://updated",
            "enabled_providers": ["claude"],
        },
    )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "Project name already exists"
    assert same_name.status_code == 200
    assert same_name.json()["confluence_base_url"] == "https://updated"


def test_admin_assigns_membership_and_duplicate_updates_role(admin_client: TestClient) -> None:
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)
    project_response = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Quality Workspace",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )
    project_id = project_response.json()["id"]

    first = admin_client.post(
        f"/api/admin/projects/{project_id}/memberships",
        headers=_auth_headers(admin_client, admin),
        json={"user_id": str(standard.id)},
    )
    duplicate = admin_client.post(
        f"/api/admin/projects/{project_id}/memberships",
        headers=_auth_headers(admin_client, admin),
        json={"user_id": str(standard.id), "role": "owner"},
    )
    invalid_role = admin_client.post(
        f"/api/admin/projects/{project_id}/memberships",
        headers=_auth_headers(admin_client, admin),
        json={"user_id": str(standard.id), "role": "   "},
    )

    assert first.status_code == 200
    assert first.json()["role"] == "member"
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == first.json()["id"]
    assert duplicate.json()["role"] == "owner"
    assert invalid_role.status_code == 422


def test_admin_membership_assignment_returns_safe_404_for_missing_resources(
    admin_client: TestClient,
) -> None:
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)

    response = admin_client.post(
        "/api/admin/projects/00000000-0000-0000-0000-000000000001/memberships",
        headers=_auth_headers(admin_client, admin),
        json={"user_id": str(standard.id)},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Resource not found"


def test_admin_cannot_assign_inactive_user_to_project(admin_client: TestClient) -> None:
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    inactive = _create_user(admin_client, "inactive@example.com", STANDARD_ROLE, active=False)
    project_response = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Quality Workspace",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )

    response = admin_client.post(
        f"/api/admin/projects/{project_response.json()['id']}/memberships",
        headers=_auth_headers(admin_client, admin),
        json={"user_id": str(inactive.id)},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Resource not found"


def test_inactive_user_with_old_token_cannot_pass_rbac(admin_client: TestClient) -> None:
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    token = _token(admin_client, admin)

    session_gen = _session_from_override(admin_client)
    session = next(session_gen)
    try:
        user = session.get(User, admin.id)
        assert user is not None
        user.is_active = False
        session.commit()
    finally:
        session_gen.close()

    response = admin_client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_admin_can_update_and_delete_project(admin_client: TestClient) -> None:
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    project_response = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Original Project",
            "description": "Original description",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )
    project_id = project_response.json()["id"]

    updated = admin_client.put(
        f"/api/admin/projects/{project_id}",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "  Updated Project  ",
            "description": "  Updated description  ",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )
    blank = admin_client.put(
        f"/api/admin/projects/{project_id}",
        headers=_auth_headers(admin_client, admin),
        json={"name": "   ", "confluence_base_url": "https://mcp", "enabled_providers": ["claude"]},
    )
    deleted = admin_client.delete(
        f"/api/admin/projects/{project_id}",
        headers=_auth_headers(admin_client, admin),
    )
    missing = admin_client.delete(
        f"/api/admin/projects/{project_id}",
        headers=_auth_headers(admin_client, admin),
    )

    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Project"
    assert updated.json()["description"] == "Updated description"
    assert blank.status_code == 422
    assert deleted.status_code == 204
    assert missing.status_code == 404


def test_standard_user_cannot_update_or_delete_project(admin_client: TestClient) -> None:
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)
    project_response = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Quality Workspace",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )
    project_id = project_response.json()["id"]

    updated = admin_client.put(
        f"/api/admin/projects/{project_id}",
        headers=_auth_headers(admin_client, standard),
        json={
            "name": "Denied",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )
    deleted = admin_client.delete(
        f"/api/admin/projects/{project_id}", headers=_auth_headers(admin_client, standard)
    )

    assert updated.status_code == 403
    assert deleted.status_code == 403


def test_admin_can_create_user_with_approved_role_without_leaking_credentials(
    admin_client: TestClient,
) -> None:
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)

    # A project_admin must be linked to an existing project at creation (Story 15.3).
    project = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={"name": "PAdmin Workspace"},
    )
    project_id = project.json()["id"]

    created = admin_client.post(
        "/api/admin/users",
        headers=_auth_headers(admin_client, admin),
        json={
            "email": "  new.padmin@example.com  ",
            "display_name": "  New PAdmin  ",
            "role": "project_admin",
            "project_id": project_id,
        },
    )
    # An admin may NOT mint another platform admin — role "admin" is not creatable.
    admin_rejected = admin_client.post(
        "/api/admin/users",
        headers=_auth_headers(admin_client, admin),
        json={
            "email": "another.admin@example.com",
            "display_name": "Another Admin",
            "role": ADMIN_ROLE,
        },
    )
    duplicate = admin_client.post(
        "/api/admin/users",
        headers=_auth_headers(admin_client, admin),
        json={
            "email": "new.padmin@example.com",
            "display_name": "Duplicate",
            "role": STANDARD_ROLE,
        },
    )

    invalid_role = admin_client.post(
        "/api/admin/users",
        headers=_auth_headers(admin_client, admin),
        json={
            "email": "bad.role@example.com",
            "display_name": "Bad Role",
            "role": "superadmin",
        },
    )

    assert created.status_code == 200
    user = created.json()
    assert user["email"] == "new.padmin@example.com"
    assert user["display_name"] == "New PAdmin"
    assert user["role"] == "project_admin"
    assert user["is_active"] is True
    assert any(
        m["role"] == "project_admin" and m["project_id"] == project_id
        for m in user["project_memberships"]
    )
    assert admin_rejected.status_code == 422  # admins cannot create another admin
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "User already exists"

    assert invalid_role.status_code == 422


def test_admin_can_remove_project_membership(admin_client: TestClient) -> None:
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)
    project_response = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Quality Workspace",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )
    project_id = project_response.json()["id"]
    assigned = admin_client.post(
        f"/api/admin/projects/{project_id}/memberships",
        headers=_auth_headers(admin_client, admin),
        json={"user_id": str(standard.id)},
    )

    removed = admin_client.delete(
        f"/api/admin/projects/{project_id}/memberships/{standard.id}",
        headers=_auth_headers(admin_client, admin),
    )
    missing = admin_client.delete(
        f"/api/admin/projects/{project_id}/memberships/{standard.id}",
        headers=_auth_headers(admin_client, admin),
    )

    assert assigned.status_code == 200
    assert removed.status_code == 204
    assert missing.status_code == 404


def test_admin_can_delete_user(admin_client: TestClient) -> None:
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    target = _create_user(admin_client, "target@example.com", STANDARD_ROLE)

    deleted = admin_client.delete(
        f"/api/admin/users/{target.id}",
        headers=_auth_headers(admin_client, admin),
    )
    missing = admin_client.delete(
        f"/api/admin/users/{target.id}",
        headers=_auth_headers(admin_client, admin),
    )

    assert deleted.status_code == 204
    assert missing.status_code == 404


def test_standard_user_cannot_create_or_delete_user(admin_client: TestClient) -> None:
    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)
    target = _create_user(admin_client, "target@example.com", STANDARD_ROLE)

    created = admin_client.post(
        "/api/admin/users",
        headers=_auth_headers(admin_client, standard),
        json={
            "email": "new@example.com",
            "display_name": "New User",
            "role": STANDARD_ROLE,
        },
    )
    deleted = admin_client.delete(
        f"/api/admin/users/{target.id}",
        headers=_auth_headers(admin_client, standard),
    )

    assert created.status_code == 403
    assert deleted.status_code == 403


def test_standard_and_unauthenticated_users_cannot_manage_memberships(
    admin_client: TestClient,
) -> None:
    """Membership assign/remove must reject non-admins (403) and anonymous (401).

    Story 8.1 AC4: the denial response body must expose no admin-only data —
    only a ``detail`` field — so a forbidden caller cannot enumerate users,
    projects, or memberships.
    """
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)
    project_response = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Quality Workspace",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )
    project_id = project_response.json()["id"]

    assign_forbidden = admin_client.post(
        f"/api/admin/projects/{project_id}/memberships",
        headers=_auth_headers(admin_client, standard),
        json={"user_id": str(standard.id)},
    )
    assign_unauthenticated = admin_client.post(
        f"/api/admin/projects/{project_id}/memberships",
        json={"user_id": str(standard.id)},
    )
    remove_forbidden = admin_client.delete(
        f"/api/admin/projects/{project_id}/memberships/{standard.id}",
        headers=_auth_headers(admin_client, standard),
    )
    remove_unauthenticated = admin_client.delete(
        f"/api/admin/projects/{project_id}/memberships/{standard.id}",
    )

    assert assign_forbidden.status_code == 403
    assert remove_forbidden.status_code == 403
    assert assign_unauthenticated.status_code == 401
    assert remove_unauthenticated.status_code == 401

    # AC4: denial bodies leak nothing beyond the status detail.
    assert assign_forbidden.json() == {"detail": "Forbidden"}
    assert remove_forbidden.json() == {"detail": "Forbidden"}
    assert assign_unauthenticated.json() == {"detail": "Not authenticated"}
    assert remove_unauthenticated.json() == {"detail": "Not authenticated"}


def test_assigned_member_sees_project_in_accessible_list(
    admin_client: TestClient,
) -> None:
    """Story 8.4 AC1 forward round-trip: admin assigns membership → member's GET /api/projects lists the project.

    Mirrors the inverse-direction guarantee in
    ``test_deleted_project_disappears_from_affected_member_project_list``: the
    membership row is the sole gate on standard-user project visibility, so the
    forward direction (assign → visible) must be just as binding as the inverse
    (delete → not visible).
    """
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    member = _create_user(admin_client, "member@example.com", STANDARD_ROLE)

    # Admin creates a project; the standard user has no memberships yet.
    project_response = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Round-Trip Project",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    project_name = project_response.json()["name"]

    # Before assignment: member's accessible-project list is empty.
    list_before = admin_client.get("/api/projects", headers=_auth_headers(admin_client, member))
    assert list_before.status_code == 200
    assert list_before.json() == []

    # Admin assigns the standard user to the project.
    assign = admin_client.post(
        f"/api/admin/projects/{project_id}/memberships",
        headers=_auth_headers(admin_client, admin),
        json={"user_id": str(member.id)},
    )
    assert assign.status_code == 200

    # After assignment: member's accessible-project list includes the project (matching id + name).
    list_after = admin_client.get("/api/projects", headers=_auth_headers(admin_client, member))
    assert list_after.status_code == 200
    member_projects = list_after.json()
    assert len(member_projects) == 1
    assert member_projects[0]["id"] == project_id
    assert member_projects[0]["name"] == project_name


def test_deleted_project_disappears_from_affected_member_project_list(
    admin_client: TestClient,
) -> None:
    """AC4 cross-user clause: after admin deletes a project, an assigned member no longer sees it."""
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    member = _create_user(admin_client, "member@example.com", STANDARD_ROLE)

    # Admin creates a project and assigns the member.
    project_response = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={
            "name": "Ephemeral Project",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    admin_client.post(
        f"/api/admin/projects/{project_id}/memberships",
        headers=_auth_headers(admin_client, admin),
        json={"user_id": str(member.id)},
    )

    # Member sees the project in their accessible list.
    member_list_before = admin_client.get(
        "/api/projects", headers=_auth_headers(admin_client, member)
    )
    assert member_list_before.status_code == 200
    assert any(p["id"] == project_id for p in member_list_before.json())

    # Admin deletes the project.
    deleted = admin_client.delete(
        f"/api/admin/projects/{project_id}",
        headers=_auth_headers(admin_client, admin),
    )
    assert deleted.status_code == 204

    # Member no longer sees the deleted project.
    member_list_after = admin_client.get(
        "/api/projects", headers=_auth_headers(admin_client, member)
    )
    assert member_list_after.status_code == 200
    assert not any(p["id"] == project_id for p in member_list_after.json())


def test_e2e_report_view_requires_admin(admin_client: TestClient) -> None:
    """The Playwright HTML report viewer must not be publicly readable.

    The report bundles traces, screenshots, videos, and captured request/response
    data from E2E runs against real DB projects. ``view_e2e_report`` is now gated by
    ``AdminDependency`` and the path is no longer whitelisted in
    ``AuthMiddleware.PUBLIC_PATHS``. This pins both enforcement layers:

    * ``.html`` paths are blocked at the auth middleware (not in its ``is_static``
      suffix list), so anonymous callers get 401.
    * ``.png`` report assets ARE waved through the middleware's ``is_static`` rule,
      so the endpoint-level ``AdminDependency`` is the sole guard — anonymous 401,
      non-admin 403.
    * An admin passes auth (proving the session/token path still works); the
      missing-file 404 confirms RBAC let the request reach the handler.
    """
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)

    # Anonymous: blocked at the middleware for the HTML entrypoint.
    anon_html = admin_client.get("/api/admin/tests/e2e/report/view/index.html")
    assert anon_html.status_code == 401
    assert anon_html.json() == {"detail": "Not authenticated"}

    # Anonymous: a static-suffixed asset bypasses the middleware but the endpoint
    # dependency still rejects it. This is the regression that the public whitelist hid.
    anon_asset = admin_client.get("/api/admin/tests/e2e/report/view/trace/screenshot.png")
    assert anon_asset.status_code == 401
    assert anon_asset.json() == {"detail": "Not authenticated"}

    # Authenticated non-admin: forbidden, and the body leaks nothing beyond the detail.
    standard_html = admin_client.get(
        "/api/admin/tests/e2e/report/view/index.html",
        headers=_auth_headers(admin_client, standard),
    )
    assert standard_html.status_code == 403
    assert standard_html.json() == {"detail": "Forbidden"}

    # Admin passes RBAC and reaches the handler: 200 if a report exists in this tree,
    # 404 if not. The point is that auth no longer blocks a legitimate admin — so the
    # status must be anything BUT 401/403.
    admin_html = admin_client.get(
        "/api/admin/tests/e2e/report/view/index.html",
        headers=_auth_headers(admin_client, admin),
    )
    assert admin_html.status_code not in (401, 403)


def test_anonymous_caller_cannot_create_project_and_response_is_secret_free(
    admin_client: TestClient,
) -> None:
    """AC5: unauthenticated create returns 401 with only a detail body, no project data leaked."""
    response = admin_client.post(
        "/api/admin/projects",
        json={
            "name": "Ghost Project",
            "confluence_base_url": "https://mcp",
            "enabled_providers": ["claude"],
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
