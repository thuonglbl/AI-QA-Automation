"""API tests for thread endpoints."""

from collections.abc import Generator
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.session import SessionManager
from ai_qa.auth.password import hash_password
from ai_qa.auth.service import STANDARD_ROLE
from ai_qa.db.base import Base
from ai_qa.db.models import Project, ProjectMembership, User
from ai_qa.threads.models import AgentRun, Message, Thread


@pytest.fixture
def thread_client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=cast(
            list[Table],
            [
                User.__table__,
                Project.__table__,
                Thread.__table__,
                ProjectMembership.__table__,
                Message.__table__,
                AgentRun.__table__,
            ],
        ),
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
    return app.dependency_overrides[get_db_session_dependency]()


def _create_user(client: TestClient, email: str) -> User:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        user = User(
            email=email,
            display_name=email.split("@")[0],
            password_hash=hash_password("super-secret"),
            role=STANDARD_ROLE,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session_gen.close()


def _create_project(client: TestClient, name: str) -> Project:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        project = Project(
            name=name,
            description=f"{name} description",
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        session.expunge(project)
        return project
    finally:
        session_gen.close()


def _create_membership(client: TestClient, project_id: str, user_id: str) -> ProjectMembership:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        membership = ProjectMembership(
            project_id=UUID(project_id),
            user_id=UUID(user_id),
            role="member",
        )
        session.add(membership)
        session.commit()
        session.refresh(membership)
        session.expunge(membership)
        return membership
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


def test_create_thread(thread_client: TestClient) -> None:
    user = _create_user(thread_client, "user@example.com")

    response = thread_client.post(
        "/api/threads", json={"user_id": str(user.id)}, headers=_auth_headers(thread_client, user)
    )

    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == str(user.id)
    assert data["project_id"] is None
    assert "id" in data


def test_create_thread_unauthorized(thread_client: TestClient) -> None:
    user = _create_user(thread_client, "user@example.com")
    other_user_id = str(uuid4())

    response = thread_client.post(
        "/api/threads", json={"user_id": other_user_id}, headers=_auth_headers(thread_client, user)
    )

    assert response.status_code == 403


def test_bind_project(thread_client: TestClient) -> None:
    user = _create_user(thread_client, "user@example.com")
    project = _create_project(thread_client, "Project X")

    # Create thread first
    create_resp = thread_client.post(
        "/api/threads", json={"user_id": str(user.id)}, headers=_auth_headers(thread_client, user)
    )
    thread_id = create_resp.json()["id"]

    # Create project membership
    _create_membership(thread_client, str(project.id), str(user.id))

    # Bind project
    response = thread_client.post(
        f"/api/threads/{thread_id}/bind",
        params={"project_id": str(project.id)},
        headers=_auth_headers(thread_client, user),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == str(project.id)


def test_bind_project_unauthorized(thread_client: TestClient) -> None:
    user = _create_user(thread_client, "user@example.com")
    other_user = _create_user(thread_client, "other@example.com")
    project = _create_project(thread_client, "Project X")

    # Create thread as other_user
    create_resp = thread_client.post(
        "/api/threads",
        json={"user_id": str(other_user.id)},
        headers=_auth_headers(thread_client, other_user),
    )
    thread_id = create_resp.json()["id"]

    # Attempt to bind as user
    response = thread_client.post(
        f"/api/threads/{thread_id}/bind",
        params={"project_id": str(project.id)},
        headers=_auth_headers(thread_client, user),
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Story 7.6: Membership removal access enforcement
# ---------------------------------------------------------------------------

RESOURCE_NOT_FOUND_DETAIL = "Resource not found"

# Substrings that would indicate a thread/project/artifact/agent-run detail leak.
_LEAK_MARKERS = (
    "conversation_data",
    "agent_runs",
    "messages",
    "project_id",
    "user_id",
    "current_step",
    "title",
    "confluence",
)


def _create_admin(client: TestClient, email: str) -> User:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        user = User(
            email=email,
            display_name=email.split("@")[0],
            password_hash=hash_password("super-secret"),
            role="admin",
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session_gen.close()


def _remove_membership(client: TestClient, project_id: str, user_id: str) -> None:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        membership = (
            session.query(ProjectMembership)
            .filter(
                ProjectMembership.project_id == UUID(project_id),
                ProjectMembership.user_id == UUID(user_id),
            )
            .one()
        )
        session.delete(membership)
        session.commit()
    finally:
        session_gen.close()


def _create_bound_thread(client: TestClient, user: User, project: Project) -> str:
    """Create a project-bound thread for a current member and return its id."""
    _create_membership(client, str(project.id), str(user.id))
    create_resp = client.post(
        "/api/threads",
        json={"user_id": str(user.id), "project_id": str(project.id)},
        headers=_auth_headers(client, user),
    )
    assert create_resp.status_code == 201
    return create_resp.json()["id"]


def test_threads_list_hides_removed_project(thread_client: TestClient) -> None:
    """A removed member no longer sees the project-bound thread in /threads."""
    user = _create_user(thread_client, "member@example.com")
    project = _create_project(thread_client, "Project X")
    thread_id = _create_bound_thread(thread_client, user, project)

    # Visible while still a member.
    resp = thread_client.get("/api/threads", headers=_auth_headers(thread_client, user))
    assert resp.status_code == 200
    assert any(t["id"] == thread_id for t in resp.json())

    # Remove membership -> thread is hidden.
    _remove_membership(thread_client, str(project.id), str(user.id))
    resp = thread_client.get("/api/threads", headers=_auth_headers(thread_client, user))
    assert resp.status_code == 200
    assert all(t["id"] != thread_id for t in resp.json())


def test_removed_member_denied_on_all_thread_endpoints(thread_client: TestClient) -> None:
    """Every project-scoped thread endpoint returns a detail-free 404 after removal."""
    user = _create_user(thread_client, "member@example.com")
    project = _create_project(thread_client, "Project X")
    thread_id = _create_bound_thread(thread_client, user, project)
    headers = _auth_headers(thread_client, user)

    _remove_membership(thread_client, str(project.id), str(user.id))

    requests = [
        ("get", f"/api/threads/{thread_id}", None),
        ("get", f"/api/threads/{thread_id}/conversation", None),
        (
            "post",
            f"/api/threads/{thread_id}/conversation",
            {"conversation": {"messages": [], "current_step": 1, "status": "start"}},
        ),
        ("get", f"/api/threads/{thread_id}/messages", None),
        ("post", f"/api/threads/{thread_id}/messages", {"role": "user", "content": "hi"}),
        ("post", f"/api/threads/{thread_id}/runs", {"status": "running"}),
        (
            "patch",
            f"/api/threads/{thread_id}/runs/{uuid4()}",
            {"status": "completed"},
        ),
    ]

    for method, url, json_body in requests:
        kwargs: dict[str, object] = {"headers": headers}
        if json_body is not None:
            kwargs["json"] = json_body
        response = getattr(thread_client, method)(url, **kwargs)
        assert response.status_code == 404, f"{method} {url} expected 404"
        body = response.json()
        assert body == {"detail": RESOURCE_NOT_FOUND_DETAIL}, f"{method} {url} leaked: {body}"
        serialized = response.text.lower()
        for marker in _LEAK_MARKERS:
            assert marker not in serialized, f"{method} {url} leaked '{marker}'"


def test_still_member_owner_keeps_access(thread_client: TestClient) -> None:
    """The owner who is still a member can read the bound thread."""
    user = _create_user(thread_client, "member@example.com")
    project = _create_project(thread_client, "Project X")
    thread_id = _create_bound_thread(thread_client, user, project)

    response = thread_client.get(
        f"/api/threads/{thread_id}", headers=_auth_headers(thread_client, user)
    )
    assert response.status_code == 200
    assert response.json()["id"] == thread_id


def test_admin_keeps_access_without_membership(thread_client: TestClient) -> None:
    """A global admin can access their own project-bound thread without membership."""
    admin = _create_admin(thread_client, "admin@example.com")
    project = _create_project(thread_client, "Project X")

    # Admin creates a project-bound thread (admin bypasses membership at creation).
    create_resp = thread_client.post(
        "/api/threads",
        json={"user_id": str(admin.id), "project_id": str(project.id)},
        headers=_auth_headers(thread_client, admin),
    )
    assert create_resp.status_code == 201
    thread_id = create_resp.json()["id"]

    response = thread_client.get(
        f"/api/threads/{thread_id}", headers=_auth_headers(thread_client, admin)
    )
    assert response.status_code == 200
    assert response.json()["id"] == thread_id


def test_update_run_via_sibling_thread_is_denied_without_mutation(
    thread_client: TestClient,
) -> None:
    """A run can't be updated (or have its existence leaked) through another thread.

    The owner has two project-bound threads. Patching thread B's runs endpoint
    with a run that belongs to thread A must return a generic 404 and must NOT
    mutate the run (no write before the ownership check).
    """
    user = _create_user(thread_client, "member@example.com")
    project = _create_project(thread_client, "Project X")
    headers = _auth_headers(thread_client, user)

    # Two bound threads owned by the same still-member user.
    thread_a = _create_bound_thread(thread_client, user, project)
    create_b = thread_client.post(
        "/api/threads",
        json={"user_id": str(user.id), "project_id": str(project.id)},
        headers=headers,
    )
    assert create_b.status_code == 201
    thread_b = create_b.json()["id"]

    # Create a run on thread A.
    run_resp = thread_client.post(
        f"/api/threads/{thread_a}/runs", json={"status": "running"}, headers=headers
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]

    # Attempt to mutate A's run through thread B's URL -> generic 404, no leak.
    cross = thread_client.patch(
        f"/api/threads/{thread_b}/runs/{run_id}",
        json={"status": "completed"},
        headers=headers,
    )
    assert cross.status_code == 404
    assert cross.json() == {"detail": RESOURCE_NOT_FOUND_DETAIL}

    # The run on thread A is untouched (still "running").
    via_a = thread_client.patch(
        f"/api/threads/{thread_a}/runs/{run_id}",
        json={"summary": "noop"},
        headers=headers,
    )
    assert via_a.status_code == 200
    assert via_a.json()["status"] == "running"
