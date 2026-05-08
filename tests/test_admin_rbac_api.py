"""API tests for admin RBAC routes."""

from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import get_current_active_user, require_admin
from ai_qa.api.auth.session import SessionManager
from ai_qa.auth.password import hash_password
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
        engine, tables=[User.__table__, Project.__table__, ProjectMembership.__table__]
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


def _session_from_override(client: TestClient) -> Generator[Session]:
    db_override = client.app.dependency_overrides[get_db_session_dependency]
    return db_override()


def _create_user(client: TestClient, email: str, role: str, *, active: bool = True) -> User:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        user = User(
            email=email,
            display_name=email.split("@")[0],
            password_hash=hash_password("super-secret"),
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
    session_manager = SessionManager(client.app.state.settings)
    session = session_manager.create_session(
        {
            "user_id": str(user.id),
            "email": user.email,
            "name": user.display_name,
            "role": user.role,
            "is_active": user.is_active,
        }
    )
    return session_manager.encode_session(session)


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
                "app": admin_client.app,
            }
        )
        request.state.user = SessionManager(admin_client.app.state.settings).decode_session(
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


def test_admin_can_list_users_without_password_hash(admin_client: TestClient) -> None:
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    _create_user(admin_client, "standard@example.com", STANDARD_ROLE)

    response = admin_client.get("/api/admin/users", headers=_auth_headers(admin_client, admin))

    assert response.status_code == 200
    users = response.json()
    assert [user["email"] for user in users] == ["admin@example.com", "standard@example.com"]
    assert all("password_hash" not in user for user in users)


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
        json={"name": "  Quality Workspace  ", "description": "  Core QA project  "},
    )
    denied = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, standard),
        json={"name": "Denied"},
    )
    blank = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={"name": "   "},
    )

    assert created.status_code == 200
    project = created.json()
    assert project["name"] == "Quality Workspace"
    assert project["description"] == "Core QA project"
    assert project["created_by_user_id"] == str(admin.id)
    assert "password_hash" not in project
    assert denied.status_code == 403
    assert blank.status_code == 422


def test_admin_assigns_membership_and_duplicate_updates_role(admin_client: TestClient) -> None:
    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)
    project_response = admin_client.post(
        "/api/admin/projects",
        headers=_auth_headers(admin_client, admin),
        json={"name": "Quality Workspace"},
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
        json={"name": "Quality Workspace"},
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
