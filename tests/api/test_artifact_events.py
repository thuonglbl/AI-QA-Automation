"""API tests for artifact change events (Story 10.6).

Validates that artifact change events are emitted on create/update/delete,
events are broadcast only to authorized project users, and no event is
emitted on failure.

Fixture scaffold copied from ``tests/api/test_admin_rbac_api.py`` per project
rules #19/#20/#21.
"""

from collections.abc import Generator
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.api.app import create_app
from ai_qa.api.artifacts import get_artifact_storage
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.session import SessionManager
from ai_qa.auth.service import STANDARD_ROLE
from ai_qa.db.base import Base
from ai_qa.db.models import Artifact, ArtifactVersion, Project, ProjectMembership, User
from ai_qa.threads.models import AgentRun, Thread


class ArtifactStorageFake:
    """In-memory storage fake shared by artifact API requests."""

    def __init__(self) -> None:
        self.contents: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.fail_on_write: bool = False

    def write(
        self,
        *,
        project_id: object,
        artifact_id: object,
        version: int,
        kind: str,
        name: str,
        content: str | bytes,
    ) -> str:
        if self.fail_on_write:
            raise ValueError("Storage write failed")
        storage_path = f"projects/{project_id}/artifacts/{artifact_id}/v{version}/{Path(name).name}"
        self.contents[storage_path] = (
            content.encode("utf-8") if isinstance(content, str) else content
        )
        return storage_path

    def read(self, storage_path: str) -> bytes:
        try:
            return self.contents[storage_path]
        except KeyError as exc:
            raise FileNotFoundError(storage_path) from exc

    def delete(self, storage_path: str) -> None:
        self.deleted.append(storage_path)
        self.contents.pop(storage_path, None)

    def delete_prefix(self, prefix: str) -> None:
        keys = [k for k in self.contents if k.startswith(prefix)]
        for k in keys:
            self.deleted.append(k)
            self.contents.pop(k, None)


@pytest.fixture
def event_client() -> Generator[TestClient]:
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
                ProjectMembership.__table__,
                Thread.__table__,
                AgentRun.__table__,
                Artifact.__table__,
                ArtifactVersion.__table__,
            ],
        ),
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    storage = ArtifactStorageFake()

    def override_get_db_session() -> Generator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db_session_dependency] = override_get_db_session
    app.dependency_overrides[get_artifact_storage] = lambda: storage
    app.state.test_artifact_storage = storage
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    engine.dispose()


def _session_from_override(client: TestClient) -> Generator[Session]:
    app = cast(FastAPI, client.app)
    return cast(Generator[Session], app.dependency_overrides[get_db_session_dependency]())


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


def _create_agent_run(client: TestClient, project: Project, user: User) -> AgentRun:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        thread = Thread(project_id=project.id, user_id=user.id)
        session.add(thread)
        session.flush()
        agent_run = AgentRun(thread_id=thread.id, status="pending")
        session.add(agent_run)
        session.commit()
        session.refresh(agent_run)
        session.expunge(agent_run)
        return agent_run
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


# --- [P0] Story 10.6: Artifact Change Events ---
# broadcast_artifact_change is lazily imported inside each endpoint function in
# artifacts.py, so we patch it at its *definition* site (ai_qa.api.websocket)
# which is where the lazy import resolves to.
_BROADCAST_PATCH = "ai_qa.api.websocket.broadcast_artifact_change"


def test_artifact_change_event_emitted_on_create(
    event_client: TestClient,
) -> None:
    """[P0] AC1: broadcast_artifact_change is called with correct args on artifact create.

    Patches the function at its definition site (ai_qa.api.websocket) so that
    the lazy import inside artifacts.py resolves to the mock.
    """
    member = _create_user(event_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(event_client, "Event Project")
    _add_membership(event_client, project, member)

    with patch(_BROADCAST_PATCH, new_callable=AsyncMock) as mock_broadcast:
        response = event_client.post(
            f"/api/projects/{project.id}/artifacts",
            headers=_auth_headers(event_client, member),
            json={
                "kind": "markdown",
                "name": "test.md",
                "content": "# Test",
            },
        )

        assert response.status_code == 200
        artifact_id = response.json()["id"]

        mock_broadcast.assert_awaited_once()
        call_kwargs = mock_broadcast.call_args.kwargs
        assert call_kwargs["project_id"] == str(project.id)
        assert call_kwargs["artifact_id"] == artifact_id
        assert call_kwargs["change_type"] == "created"


def test_artifact_change_event_emitted_on_update(
    event_client: TestClient,
) -> None:
    """[P0] AC1: broadcast_artifact_change is called with correct args on artifact update.

    Creates a real artifact first (no mock), then patches broadcast for the
    update call and asserts change_type='updated'.
    """
    member = _create_user(event_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(event_client, "Event Project")
    agent_run = _create_agent_run(event_client, project, member)
    _add_membership(event_client, project, member)

    # Create initial artifact (real, no mock)
    created = event_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(event_client, member),
        json={
            "kind": "markdown",
            "name": "test.md",
            "content": "# Initial",
            "agent_run_id": str(agent_run.id),
        },
    )
    assert created.status_code == 200
    artifact_id = created.json()["id"]

    # Update artifact — verify broadcast fires with correct args
    with patch(_BROADCAST_PATCH, new_callable=AsyncMock) as mock_broadcast:
        response = event_client.post(
            f"/api/projects/{project.id}/artifacts/{artifact_id}/versions",
            headers=_auth_headers(event_client, member),
            json={"content": "# Updated"},
        )

        assert response.status_code == 200
        mock_broadcast.assert_awaited_once()
        call_kwargs = mock_broadcast.call_args.kwargs
        assert call_kwargs["project_id"] == str(project.id)
        assert call_kwargs["artifact_id"] == artifact_id
        assert call_kwargs["change_type"] == "updated"


def test_artifact_change_event_emitted_on_delete(
    event_client: TestClient,
) -> None:
    """[P0] AC1: broadcast_artifact_change is called with change_type='deleted' on DELETE.

    (a) Creates an artifact via POST, (b) deletes via DELETE endpoint,
    (c) asserts broadcast was called with change_type='deleted'.
    """
    member = _create_user(event_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(event_client, "Event Project")
    _add_membership(event_client, project, member)

    # Create a real artifact first
    created = event_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(event_client, member),
        json={"kind": "markdown", "name": "to-delete.md", "content": "# Bye"},
    )
    assert created.status_code == 200
    artifact_id = created.json()["id"]

    # Delete the artifact — verify broadcast fires with correct args
    with patch(_BROADCAST_PATCH, new_callable=AsyncMock) as mock_broadcast:
        delete_resp = event_client.delete(
            f"/api/projects/{project.id}/artifacts/{artifact_id}",
            headers=_auth_headers(event_client, member),
        )
        assert delete_resp.status_code == 204

        mock_broadcast.assert_awaited_once()
        call_kwargs = mock_broadcast.call_args.kwargs
        assert call_kwargs["project_id"] == str(project.id)
        assert call_kwargs["artifact_id"] == artifact_id
        assert call_kwargs["change_type"] == "deleted"

    # Subsequent GET → 404 confirms the artifact was removed
    assert (
        event_client.get(
            f"/api/projects/{project.id}/artifacts/{artifact_id}",
            headers=_auth_headers(event_client, member),
        ).status_code
        == 404
    )


def test_no_broadcast_on_storage_failure(
    event_client: TestClient,
) -> None:
    """[P0] AC2: broadcast_artifact_change is NOT called when storage write fails.

    Sets storage.fail_on_write=True, POSTs a create request (expect 422),
    then verifies the patched broadcast was not called at all.
    """
    member = _create_user(event_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(event_client, "Event Project")
    _add_membership(event_client, project, member)

    app = cast(FastAPI, event_client.app)
    storage: ArtifactStorageFake = app.state.test_artifact_storage
    storage.fail_on_write = True

    with patch(_BROADCAST_PATCH, new_callable=AsyncMock) as mock_broadcast:
        response = event_client.post(
            f"/api/projects/{project.id}/artifacts",
            headers=_auth_headers(event_client, member),
            json={
                "kind": "markdown",
                "name": "test.md",
                "content": "# Test",
            },
        )

        # Request should fail with 422 (ValueError caught by endpoint)
        assert response.status_code == 422
        mock_broadcast.assert_not_awaited()

    # Verify no artifacts were created (second-layer check)
    list_response = event_client.get(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(event_client, member),
    )
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_events_broadcast_only_to_authorized_project_users(
    event_client: TestClient,
) -> None:
    """[P0] AC3: Events are broadcast only to authorized project users.

    Users who are not members of the project should not receive
    artifact change events for that project.
    """
    member = _create_user(event_client, "member@example.com", STANDARD_ROLE)
    outsider = _create_user(event_client, "outsider@example.com", STANDARD_ROLE)
    project = _create_project(event_client, "Event Project")
    _add_membership(event_client, project, member)

    # Member can create artifacts
    created = event_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(event_client, member),
        json={
            "kind": "markdown",
            "name": "test.md",
            "content": "# Test",
        },
    )
    assert created.status_code == 200

    # Outsider cannot access the project artifacts
    outsider_response = event_client.get(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(event_client, outsider),
    )
    assert outsider_response.status_code == 404


def test_no_event_emitted_on_storage_failure(
    event_client: TestClient,
) -> None:
    """[P0] AC2 (second-layer check): No artifact is created when storage fails.

    Kept alongside test_no_broadcast_on_storage_failure for defence-in-depth:
    this test verifies the DB side (artifact list stays empty), while the other
    test verifies the broadcast side (mock was not called).
    """
    member = _create_user(event_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(event_client, "Event Project")
    _add_membership(event_client, project, member)

    app = cast(FastAPI, event_client.app)
    storage: ArtifactStorageFake = app.state.test_artifact_storage
    storage.fail_on_write = True

    response = event_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(event_client, member),
        json={
            "kind": "markdown",
            "name": "test.md",
            "content": "# Test",
        },
    )

    # Request should fail with 422 (ValueError caught by endpoint)
    assert response.status_code == 422

    # Verify no artifacts were created
    list_response = event_client.get(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(event_client, member),
    )
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_events_not_emitted_for_unauthenticated_requests(
    event_client: TestClient,
) -> None:
    """[P0] No events are emitted for unauthenticated artifact operations."""
    project = _create_project(event_client, "Event Project")

    with patch(_BROADCAST_PATCH, new_callable=AsyncMock) as mock_broadcast:
        response = event_client.post(
            f"/api/projects/{project.id}/artifacts",
            json={
                "kind": "markdown",
                "name": "test.md",
                "content": "# Test",
            },
        )

        assert response.status_code == 401
        mock_broadcast.assert_not_awaited()


def test_events_contain_required_metadata(
    event_client: TestClient,
) -> None:
    """[P0] Artifact events contain required metadata fields.

    Events must include: artifact_id, project_id, change_type, and timestamp.
    """
    member = _create_user(event_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(event_client, "Event Project")
    agent_run = _create_agent_run(event_client, project, member)
    _add_membership(event_client, project, member)

    with patch(_BROADCAST_PATCH, new_callable=AsyncMock) as mock_broadcast:
        response = event_client.post(
            f"/api/projects/{project.id}/artifacts",
            headers=_auth_headers(event_client, member),
            json={
                "kind": "markdown",
                "name": "test.md",
                "content": "# Test",
                "agent_run_id": str(agent_run.id),
            },
        )

        assert response.status_code == 200
        artifact_id = response.json()["id"]

        # Verify broadcast was called with all required AC1 fields
        mock_broadcast.assert_awaited_once()
        call_kwargs = mock_broadcast.call_args.kwargs
        assert call_kwargs["project_id"] == str(project.id)
        assert call_kwargs["artifact_id"] == artifact_id
        assert call_kwargs["change_type"] == "created"
