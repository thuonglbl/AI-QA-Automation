"""API tests for project listing, detail, and membership authorization routes."""

from collections.abc import Generator
from typing import cast

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.session import SessionManager
from ai_qa.api.projects import require_project_member_or_admin
from ai_qa.auth.service import ADMIN_ROLE, STANDARD_ROLE
from ai_qa.db.base import Base
from ai_qa.db.models import Project, ProjectMembership, User


@pytest.fixture
def project_client() -> Generator[TestClient]:
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


def _create_project(client: TestClient, name: str, creator: User | None = None) -> Project:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        project = Project(
            name=name,
            description=f"{name} description",
            created_by_user_id=creator.id if creator else None,
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        session.expunge(project)
        return project
    finally:
        session_gen.close()


def _add_membership(client: TestClient, project: Project, user: User, role: str = "member") -> None:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        session.add(ProjectMembership(project_id=project.id, user_id=user.id, role=role))
        session.commit()
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
    return session_manager.encode_session(session)


def _auth_headers(client: TestClient, user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client, user)}"}


def test_admin_lists_all_projects_with_membership_summary(project_client: TestClient) -> None:
    admin = _create_user(project_client, "admin@example.com", ADMIN_ROLE)
    member = _create_user(project_client, "member@example.com", STANDARD_ROLE)
    first = _create_project(project_client, "Alpha", admin)
    _create_project(project_client, "Beta", admin)
    _add_membership(project_client, first, member, "owner")

    response = project_client.get("/api/projects", headers=_auth_headers(project_client, admin))

    assert response.status_code == 200
    projects = response.json()
    assert [project["name"] for project in projects] == ["Alpha", "Beta"]
    assert projects[0]["membership_count"] == 1
    assert projects[0]["memberships"][0]["user_id"] == str(member.id)
    assert projects[0]["memberships"][0]["role"] == "owner"
    # AC1: project listing exposes timestamps for admin project management views.
    assert projects[0]["created_at"] is not None
    assert projects[0]["updated_at"] is not None
    assert all("created_at" in project and "updated_at" in project for project in projects)


def test_standard_user_lists_only_assigned_projects(project_client: TestClient) -> None:
    admin = _create_user(project_client, "admin@example.com", ADMIN_ROLE)
    member = _create_user(project_client, "member@example.com", STANDARD_ROLE)
    assigned = _create_project(project_client, "Assigned", admin)
    _create_project(project_client, "Hidden", admin)
    _add_membership(project_client, assigned, member, "member")

    response = project_client.get("/api/projects", headers=_auth_headers(project_client, member))

    assert response.status_code == 200
    projects = response.json()
    assert [project["name"] for project in projects] == ["Assigned"]
    assert projects[0]["current_user_role"] == "member"
    assert projects[0]["memberships"] == []


def test_project_detail_allows_admin_and_member_but_hides_non_member(
    project_client: TestClient,
) -> None:
    admin = _create_user(project_client, "admin@example.com", ADMIN_ROLE)
    member = _create_user(project_client, "member@example.com", STANDARD_ROLE)
    outsider = _create_user(project_client, "outsider@example.com", STANDARD_ROLE)
    project = _create_project(project_client, "Scoped", admin)
    _add_membership(project_client, project, member, "member")

    admin_response = project_client.get(
        f"/api/projects/{project.id}", headers=_auth_headers(project_client, admin)
    )
    member_response = project_client.get(
        f"/api/projects/{project.id}", headers=_auth_headers(project_client, member)
    )
    outsider_response = project_client.get(
        f"/api/projects/{project.id}", headers=_auth_headers(project_client, outsider)
    )

    assert admin_response.status_code == 200
    assert admin_response.json()["membership_count"] == 1
    assert member_response.status_code == 200
    assert member_response.json()["current_user_role"] == "member"
    assert outsider_response.status_code == 404
    assert outsider_response.json()["detail"] == "Resource not found"


def test_project_routes_reject_unauthenticated_and_stale_users(
    project_client: TestClient,
) -> None:
    user = _create_user(project_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(project_client, "Scoped")
    _add_membership(project_client, project, user)
    token = _token(project_client, user)

    session_gen = _session_from_override(project_client)
    session = next(session_gen)
    try:
        db_user = session.get(User, user.id)
        assert db_user is not None
        db_user.is_active = False
        session.commit()
    finally:
        session_gen.close()

    unauthenticated = project_client.get("/api/projects")
    stale = project_client.get("/api/projects", headers={"Authorization": f"Bearer {token}"})

    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["detail"] == "Not authenticated"
    assert stale.status_code == 401
    assert stale.json()["detail"] == "Not authenticated"


@pytest.mark.asyncio
async def test_membership_dependency_revalidates_project_access(
    project_client: TestClient,
) -> None:
    admin = _create_user(project_client, "admin@example.com", ADMIN_ROLE)
    member = _create_user(project_client, "member@example.com", STANDARD_ROLE)
    outsider = _create_user(project_client, "outsider@example.com", STANDARD_ROLE)
    project = _create_project(project_client, "Scoped", admin)
    _add_membership(project_client, project, member)
    request = Request({"type": "http", "method": "GET", "path": "/api/projects", "headers": []})

    session_gen = _session_from_override(project_client)
    session = next(session_gen)
    try:
        assert (await require_project_member_or_admin(project.id, admin, session)).id == project.id
        assert (await require_project_member_or_admin(project.id, member, session)).id == project.id
        with pytest.raises(HTTPException) as exc_info:
            await require_project_member_or_admin(project.id, outsider, session)
    finally:
        session_gen.close()

    assert request.scope["path"] == "/api/projects"
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Resource not found"


def test_openapi_documents_project_routes_and_schemas(project_client: TestClient) -> None:
    schema = project_client.get("/openapi.json").json()

    assert "/api/projects" in schema["paths"]
    assert "/api/projects/{project_id}" in schema["paths"]
    assert schema["paths"]["/api/projects"]["get"]["tags"] == ["projects"]
    assert "ProjectResponse" in schema["components"]["schemas"]
    assert "ProjectMembershipSummary" in schema["components"]["schemas"]
