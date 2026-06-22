"""API tests for project-scoped artifact routes."""

import re
from base64 import b64encode
from collections.abc import Generator
from pathlib import Path
from typing import cast

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
from ai_qa.auth.password import hash_password
from ai_qa.auth.service import ADMIN_ROLE, STANDARD_ROLE
from ai_qa.db.base import Base
from ai_qa.db.models import Artifact, ArtifactVersion, Project, ProjectMembership, User
from ai_qa.threads.models import AgentRun, Thread


class ArtifactStorageFake:
    """In-memory storage fake shared by artifact API requests."""

    def __init__(self) -> None:
        self.contents: dict[str, bytes] = {}
        self.deleted: list[str] = []

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
def artifact_client() -> Generator[TestClient]:
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


def test_member_creates_lists_reads_and_versions_text_artifact(artifact_client: TestClient) -> None:
    member = _create_user(artifact_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(artifact_client, "Scoped")
    agent_run = _create_agent_run(artifact_client, project, member)
    _add_membership(artifact_client, project, member)

    created = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(artifact_client, member),
        json={
            "kind": "markdown",
            "name": "requirements.md",
            "content": "# Requirements",
            "agent_run_id": str(agent_run.id),
        },
    )

    assert created.status_code == 200
    artifact = created.json()
    assert artifact["project_id"] == str(project.id)
    assert artifact["agent_run_id"] == str(agent_run.id)
    assert artifact["current_version"] == 1
    assert "storage_path" not in artifact
    assert "password_hash" not in str(artifact)

    listed = artifact_client.get(
        f"/api/projects/{project.id}/artifacts?kind=markdown",
        headers=_auth_headers(artifact_client, member),
    )
    detail = artifact_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact['id']}",
        headers=_auth_headers(artifact_client, member),
    )
    content = artifact_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact['id']}/content",
        headers=_auth_headers(artifact_client, member),
    )
    versioned = artifact_client.post(
        f"/api/projects/{project.id}/artifacts/{artifact['id']}/versions",
        headers=_auth_headers(artifact_client, member),
        json={"content": "# Updated"},
    )

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [artifact["id"]]
    assert detail.status_code == 200
    assert [version["version"] for version in detail.json()["versions"]] == [1]
    assert content.status_code == 200
    assert content.json()["content"] == "# Requirements"
    assert content.json()["content_encoding"] == "text"
    assert versioned.status_code == 200
    assert versioned.json()["current_version"] == 2
    assert "storage_path" not in versioned.json()
    assert all("storage_path" not in version for version in detail.json()["versions"])


def test_artifact_api_supports_base64_binary_content(artifact_client: TestClient) -> None:
    member = _create_user(artifact_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(artifact_client, "Scoped")
    _add_membership(artifact_client, project, member)
    binary_content = b"\xff\x00\x01"

    created = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(artifact_client, member),
        json={
            "kind": "screenshot",
            "name": "screen.png",
            "content": b64encode(binary_content).decode("ascii"),
            "content_encoding": "base64",
        },
    )
    content = artifact_client.get(
        f"/api/projects/{project.id}/artifacts/{created.json()['id']}/content",
        headers=_auth_headers(artifact_client, member),
    )

    assert created.status_code == 200
    assert content.status_code == 200
    assert content.json()["content_encoding"] == "base64"
    assert content.json()["content"] == b64encode(binary_content).decode("ascii")


def test_artifact_api_enforces_project_membership_and_allows_admin(
    artifact_client: TestClient,
) -> None:
    admin = _create_user(artifact_client, "admin@example.com", ADMIN_ROLE)
    member = _create_user(artifact_client, "member@example.com", STANDARD_ROLE)
    outsider = _create_user(artifact_client, "outsider@example.com", STANDARD_ROLE)
    project = _create_project(artifact_client, "Scoped", admin)
    _add_membership(artifact_client, project, member)

    created = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(artifact_client, member),
        json={"kind": "report", "name": "report.md", "content": "report"},
    )
    artifact_id = created.json()["id"]

    outsider_response = artifact_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}",
        headers=_auth_headers(artifact_client, outsider),
    )
    admin_response = artifact_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}",
        headers=_auth_headers(artifact_client, admin),
    )
    unauthenticated = artifact_client.get(f"/api/projects/{project.id}/artifacts")

    assert outsider_response.status_code == 404
    assert outsider_response.json()["detail"] == "Resource not found"
    assert admin_response.status_code == 200
    assert unauthenticated.status_code == 401


def test_artifact_api_rejects_invalid_kind_missing_artifact_and_wrong_agent_project(
    artifact_client: TestClient,
) -> None:
    member = _create_user(artifact_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(artifact_client, "Scoped")
    other_project = _create_project(artifact_client, "Other")
    wrong_agent = _create_agent_run(artifact_client, other_project, member)
    _add_membership(artifact_client, project, member)

    invalid_kind = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(artifact_client, member),
        json={"kind": "unknown", "name": "x.md", "content": "x"},
    )
    missing_artifact = artifact_client.get(
        f"/api/projects/{project.id}/artifacts/00000000-0000-0000-0000-000000000001",
        headers=_auth_headers(artifact_client, member),
    )
    wrong_agent_response = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(artifact_client, member),
        json={
            "kind": "markdown",
            "name": "bad.md",
            "content": "bad",
            "agent_run_id": str(wrong_agent.id),
        },
    )

    assert invalid_kind.status_code == 422
    assert missing_artifact.status_code == 404
    assert wrong_agent_response.status_code == 422


def test_stale_user_and_openapi_artifact_schema_behavior(artifact_client: TestClient) -> None:
    user = _create_user(artifact_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(artifact_client, "Scoped")
    _add_membership(artifact_client, project, user)
    token = _token(artifact_client, user)

    session_gen = _session_from_override(artifact_client)
    session = next(session_gen)
    try:
        db_user = session.get(User, user.id)
        assert db_user is not None
        db_user.is_active = False
        session.commit()
    finally:
        session_gen.close()

    stale = artifact_client.get(
        f"/api/projects/{project.id}/artifacts", headers={"Authorization": f"Bearer {token}"}
    )
    schema = artifact_client.get("/openapi.json").json()

    assert stale.status_code == 401
    assert stale.json()["detail"] == "Not authenticated"
    assert "/api/projects/{project_id}/artifacts" in schema["paths"]
    assert "ArtifactResponse" in schema["components"]["schemas"]
    assert "ArtifactCreateRequest" in schema["components"]["schemas"]


def test_artifact_api_returns_controlled_response_for_missing_content(
    artifact_client: TestClient,
) -> None:
    member = _create_user(artifact_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(artifact_client, "Scoped")
    _add_membership(artifact_client, project, member)
    created = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(artifact_client, member),
        json={"kind": "markdown", "name": "missing.md", "content": "content"},
    )
    artifact_id = created.json()["id"]
    app = cast(FastAPI, artifact_client.app)
    storage: ArtifactStorageFake = app.state.test_artifact_storage
    storage.contents.clear()

    content = artifact_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}/content",
        headers=_auth_headers(artifact_client, member),
    )

    assert content.status_code == 404
    assert content.json()["detail"] == "Resource not found"


def test_artifact_api_rejects_oversized_content(artifact_client: TestClient) -> None:
    member = _create_user(artifact_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(artifact_client, "Scoped")
    _add_membership(artifact_client, project, member)
    oversized = "x" * 1_000_001

    created = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(artifact_client, member),
        json={"kind": "markdown", "name": "too-large.md", "content": oversized},
    )

    assert created.status_code == 422


# --- AC1/AC3: Cross-member Artifact Edit and Delete (Task 1.2 / 1.6) ---


def test_cross_member_artifact_edit_and_delete_removes_consistently(
    artifact_client: TestClient,
) -> None:
    """AC1/AC3: A project member can edit and delete an artifact created by another member.

    Proves:
    1. Authorization is by project membership, not creator ownership.
    2. Editing appends a version and updates 'updated_by_user_id'.
    3. Deleting returns 204, removes from GET routes, and cleans storage.
    """
    member_a = _create_user(artifact_client, "memberA@example.com", STANDARD_ROLE)
    member_b = _create_user(artifact_client, "memberB@example.com", STANDARD_ROLE)
    project = _create_project(artifact_client, "Shared")
    _add_membership(artifact_client, project, member_a)
    _add_membership(artifact_client, project, member_b)

    # 1. Member A creates an artifact
    created = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(artifact_client, member_a),
        json={"kind": "markdown", "name": "shared.md", "content": "# V1"},
    )
    assert created.status_code == 200
    artifact_id = created.json()["id"]

    app = cast(FastAPI, artifact_client.app)
    storage: ArtifactStorageFake = app.state.test_artifact_storage

    # 2. Member B edits the artifact
    edited = artifact_client.post(
        f"/api/projects/{project.id}/artifacts/{artifact_id}/versions",
        headers=_auth_headers(artifact_client, member_b),
        json={"content": "# V2"},
    )
    assert edited.status_code == 200
    assert edited.json()["current_version"] == 2

    # Check detail metadata
    detail = artifact_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}",
        headers=_auth_headers(artifact_client, member_b),
    )
    assert detail.status_code == 200
    assert detail.json()["updated_by_user_id"] == str(member_b.id)
    assert len(detail.json()["versions"]) == 2

    storage_paths_before = list(storage.contents.keys())
    assert len(storage_paths_before) == 2  # V1 and V2

    # 3. Member B deletes the artifact
    deleted = artifact_client.delete(
        f"/api/projects/{project.id}/artifacts/{artifact_id}",
        headers=_auth_headers(artifact_client, member_b),
    )
    assert deleted.status_code == 204

    # 4. Assert subsequent GET -> 404
    missing_detail = artifact_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}",
        headers=_auth_headers(artifact_client, member_a),
    )
    assert missing_detail.status_code == 404

    missing_content = artifact_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}/content",
        headers=_auth_headers(artifact_client, member_a),
    )
    assert missing_content.status_code == 404

    # 5. Assert storage cleanup
    assert len(storage.contents) == 0
    for path in storage_paths_before:
        assert path in storage.deleted


# ---------------------------------------------------------------------------
# AC3 Leak-canary tests — Task 3.1, 3.2, 3.3
# ---------------------------------------------------------------------------

_SENSITIVE_FIELDS = {"storage_path", "s3_key", "object_key", "bucket"}
# A leaked storage key/path value looks like "projects/<uuid>/<folder>/...".
_STORAGE_KEY_VALUE = re.compile(r"projects/[0-9a-fA-F-]{8,}/")


def _no_storage_leak(body: object) -> bool:
    """Return True if the body leaks neither a sensitive field *name* nor a
    storage-key *value* (e.g. ``projects/<uuid>/test_cases/...``).

    The field-name scan alone is insufficient: a leaked path value contains none
    of the sensitive field names, so it would pass. The value regex closes that.
    """
    body_str = str(body)
    if any(field in body_str.lower() for field in _SENSITIVE_FIELDS):
        return False
    return _STORAGE_KEY_VALUE.search(body_str) is None


def test_ac3_non_member_gets_404_on_all_artifact_routes_with_no_metadata_leak(
    artifact_client: TestClient,
) -> None:
    """AC3 leak-canary: non-member gets 404 on every route; no storage_path or key leaked."""
    owner = _create_user(artifact_client, "owner@example.com", STANDARD_ROLE)
    non_member = _create_user(artifact_client, "nonmember@example.com", STANDARD_ROLE)
    project = _create_project(artifact_client, "Owned")
    _add_membership(artifact_client, project, owner)

    # Create a real artifact as the owner
    created = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(artifact_client, owner),
        json={"kind": "markdown", "name": "secret.md", "content": "secret content"},
    )
    assert created.status_code == 200
    artifact_id = created.json()["id"]

    non_headers = _auth_headers(artifact_client, non_member)

    # list
    r = artifact_client.get(f"/api/projects/{project.id}/artifacts", headers=non_headers)
    assert r.status_code == 404
    assert _no_storage_leak(r.json()), f"storage leak in list: {r.json()}"

    # create
    r = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=non_headers,
        json={"kind": "markdown", "name": "x.md", "content": "x"},
    )
    assert r.status_code == 404
    assert _no_storage_leak(r.json())

    # get
    r = artifact_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}", headers=non_headers
    )
    assert r.status_code == 404
    assert _no_storage_leak(r.json())

    # content
    r = artifact_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}/content", headers=non_headers
    )
    assert r.status_code == 404
    assert _no_storage_leak(r.json())

    # delete
    r = artifact_client.delete(
        f"/api/projects/{project.id}/artifacts/{artifact_id}", headers=non_headers
    )
    assert r.status_code == 404
    assert _no_storage_leak(r.json())

    # versions
    r = artifact_client.post(
        f"/api/projects/{project.id}/artifacts/{artifact_id}/versions",
        headers=non_headers,
        json={"content": "v2"},
    )
    assert r.status_code == 404
    assert _no_storage_leak(r.json())


def test_ac3_cross_project_member_gets_404_with_no_metadata_leak(
    artifact_client: TestClient,
) -> None:
    """AC3: member of project B gets 404 for project A's artifacts; no storage_path leaked."""
    owner = _create_user(artifact_client, "ownerA@example.com", STANDARD_ROLE)
    other_member = _create_user(artifact_client, "memberB@example.com", STANDARD_ROLE)
    project_a = _create_project(artifact_client, "ProjectA")
    project_b = _create_project(artifact_client, "ProjectB")
    _add_membership(artifact_client, project_a, owner)
    _add_membership(artifact_client, project_b, other_member)

    created = artifact_client.post(
        f"/api/projects/{project_a.id}/artifacts",
        headers=_auth_headers(artifact_client, owner),
        json={"kind": "markdown", "name": "private.md", "content": "private"},
    )
    assert created.status_code == 200
    artifact_id = created.json()["id"]

    other_headers = _auth_headers(artifact_client, other_member)
    for method, path, kwargs in [
        ("get", f"/api/projects/{project_a.id}/artifacts", {}),
        ("get", f"/api/projects/{project_a.id}/artifacts/{artifact_id}", {}),
        ("get", f"/api/projects/{project_a.id}/artifacts/{artifact_id}/content", {}),
        ("delete", f"/api/projects/{project_a.id}/artifacts/{artifact_id}", {}),
        (
            "post",
            f"/api/projects/{project_a.id}/artifacts/{artifact_id}/versions",
            {"json": {"content": "v2"}},
        ),
    ]:
        r = getattr(artifact_client, method)(path, headers=other_headers, **kwargs)
        assert r.status_code == 404, f"{method} {path} returned {r.status_code}"
        assert r.json().get("detail") == "Resource not found"
        assert _no_storage_leak(r.json()), f"storage leak on {method} {path}: {r.json()}"


def test_ac3_artifact_response_does_not_include_storage_path(
    artifact_client: TestClient,
) -> None:
    """ArtifactResponse must never include storage_path in any route response."""
    member = _create_user(artifact_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(artifact_client, "Scoped")
    _add_membership(artifact_client, project, member)
    headers = _auth_headers(artifact_client, member)

    created = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=headers,
        json={"kind": "testcase", "name": "cases.json", "content": "{}"},
    )
    assert created.status_code == 200
    artifact_id = created.json()["id"]

    # list, get (detail), version
    for r in [
        artifact_client.get(f"/api/projects/{project.id}/artifacts", headers=headers),
        artifact_client.get(f"/api/projects/{project.id}/artifacts/{artifact_id}", headers=headers),
        artifact_client.post(
            f"/api/projects/{project.id}/artifacts/{artifact_id}/versions",
            headers=headers,
            json={"content": "v2"},
        ),
    ]:
        assert r.status_code == 200
        assert _no_storage_leak(r.json()), f"storage leak in {r.url}: {r.json()}"


def test_ac2_non_creator_member_can_read_artifact_and_creator_fields_visible(
    artifact_client: TestClient,
) -> None:
    """AC2 positive test (Story 10-3 Task 1.2): Project member B (not the creator)
    successfully GETs and reads /content of an artifact created by member A
    in the same project.  creator/updater metadata is visible in the detail response.
    Access is granted by project membership, not creator ownership.
    """
    member_a = _create_user(artifact_client, "creator@example.com", STANDARD_ROLE)
    member_b = _create_user(artifact_client, "reader@example.com", STANDARD_ROLE)
    project = _create_project(artifact_client, "Shared")
    _add_membership(artifact_client, project, member_a)
    _add_membership(artifact_client, project, member_b)

    # Member A creates the artifact
    created = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(artifact_client, member_a),
        json={"kind": "requirements", "name": "spec.md", "content": "# Spec"},
    )
    assert created.status_code == 200
    artifact_id = created.json()["id"]

    # AC2: Member B (not the creator) can GET artifact detail
    detail = artifact_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}",
        headers=_auth_headers(artifact_client, member_b),
    )
    assert detail.status_code == 200, f"Member B denied access to detail: {detail.json()}"
    detail_body = detail.json()

    # Creator/updater metadata is visible in the response (not a UUID → confirms field exposure)
    assert detail_body["created_by_user_id"] == str(member_a.id), (
        "created_by_user_id must be member A's ID"
    )
    assert detail_body["updated_by_user_id"] == str(member_a.id), (
        "updated_by_user_id must be member A's ID on creation"
    )

    # AC2: Member B can also read the content
    content = artifact_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}/content",
        headers=_auth_headers(artifact_client, member_b),
    )
    assert content.status_code == 200, f"Member B denied access to content: {content.json()}"
    assert content.json()["content"] == "# Spec"
    assert content.json()["content_encoding"] == "text"

    # Confirm no storage path leaked in any response
    assert _no_storage_leak(detail_body), f"Storage path leaked in detail: {detail_body}"
    assert _no_storage_leak(content.json()), f"Storage path leaked in content: {content.json()}"


def test_ac3_new_ownership_fields_present_and_thread_id_none_by_default(
    artifact_client: TestClient,
) -> None:
    """ArtifactResponse includes created_by_user_id, updated_by_user_id, thread_id fields."""
    member = _create_user(artifact_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(artifact_client, "Scoped")
    _add_membership(artifact_client, project, member)
    headers = _auth_headers(artifact_client, member)

    created = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=headers,
        json={"kind": "markdown", "name": "owned.md", "content": "content"},
    )
    assert created.status_code == 200
    body = created.json()

    assert "created_by_user_id" in body
    assert body["created_by_user_id"] == str(member.id)
    assert "updated_by_user_id" in body
    assert body["updated_by_user_id"] == str(member.id)
    assert "thread_id" in body
    assert body["thread_id"] is None

    versioned = artifact_client.post(
        f"/api/projects/{project.id}/artifacts/{body['id']}/versions",
        headers=headers,
        json={"content": "v2"},
    )
    assert versioned.status_code == 200
    v_body = versioned.json()
    assert v_body["updated_by_user_id"] == str(member.id)


def test_execution_report_artifacts_are_membership_gated(artifact_client: TestClient) -> None:
    """Story 14.5 AC3: the execution report (report.md + report.json) is a project-scoped,
    membership-gated artifact — a member reads both; a non-member gets 404."""
    member = _create_user(artifact_client, "rep-member@example.com", STANDARD_ROLE)
    outsider = _create_user(artifact_client, "rep-outsider@example.com", STANDARD_ROLE)
    project = _create_project(artifact_client, "ReportScoped", member)
    _add_membership(artifact_client, project, member)
    headers = _auth_headers(artifact_client, member)

    report = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=headers,
        json={"kind": "report", "name": "runs/r1/report.md", "content": "# Execution Report"},
    )
    report_json = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=headers,
        json={"kind": "configuration", "name": "runs/r1/report.json", "content": "{}"},
    )
    assert report.status_code == 200
    assert report_json.status_code == 200
    report_id = report.json()["id"]

    # Member reads the report content.
    member_content = artifact_client.get(
        f"/api/projects/{project.id}/artifacts/{report_id}/content", headers=headers
    )
    assert member_content.status_code == 200

    # Non-member is denied (404, no leak).
    outsider_meta = artifact_client.get(
        f"/api/projects/{project.id}/artifacts/{report_id}",
        headers=_auth_headers(artifact_client, outsider),
    )
    assert outsider_meta.status_code == 404
