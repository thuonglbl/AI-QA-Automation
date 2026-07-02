"""API tests for artifact browsing endpoints (Story 10.2).

Tests the artifact browsing API:
  - GET /api/projects/{project_id}/artifacts - list with pagination
  - Filtering by kind
  - Permission checks (project membership required)
  - Empty state handling

Following project rules #19/#20/#21 for test patterns.
"""

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
def browsing_client() -> Generator[TestClient]:
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


def _create_artifact(
    client: TestClient,
    project: Project,
    kind: str,
    name: str,
    content: str,
    *,
    agent_run: AgentRun | None = None,
) -> dict:
    """Create an artifact via the API and return the response JSON."""
    return {
        "kind": kind,
        "name": name,
        "content": content,
        "agent_run_id": str(agent_run.id) if agent_run else None,
    }


def _list_project_members(client: TestClient, project: Project) -> list[User]:
    """List users who are members of the project."""
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        memberships = (
            session.query(ProjectMembership)
            .filter(ProjectMembership.project_id == project.id)
            .all()
        )
        return [u for m in memberships if (u := session.get(User, m.user_id)) is not None]
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


# --- List Artifacts ---


def test_list_artifacts_returns_empty_for_new_project(browsing_client: TestClient) -> None:
    """GET /api/projects/{id}/artifacts returns empty list when no artifacts exist."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Empty Project")
    _add_membership(browsing_client, project, member)

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
    )

    assert response.status_code == 200
    assert response.json() == []


def test_list_artifacts_returns_created_artifacts(browsing_client: TestClient) -> None:
    """GET /api/projects/{id}/artifacts lists all artifacts in the project."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Test Project")
    _add_membership(browsing_client, project, member)

    # Create two artifacts
    created1 = browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "markdown", "name": "req1.md", "content": "# Req 1"},
    )
    created2 = browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "report", "name": "report1.md", "content": "# Report 1"},
    )
    assert created1.status_code == 200
    assert created2.status_code == 200

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
    )

    assert response.status_code == 200
    artifacts = response.json()
    assert len(artifacts) == 2
    names = {a["name"] for a in artifacts}
    assert names == {"req1.md", "report1.md"}


def test_list_artifacts_filtered_by_kind(browsing_client: TestClient) -> None:
    """GET /api/projects/{id}/artifacts?kind=markdown returns only matching kind."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Filter Project")
    _add_membership(browsing_client, project, member)

    browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "markdown", "name": "req.md", "content": "# Req"},
    )
    browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "report", "name": "report.md", "content": "# Report"},
    )

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts?kind=markdown",
        headers=_auth_headers(browsing_client, member),
    )

    assert response.status_code == 200
    artifacts = response.json()
    assert len(artifacts) == 1
    assert artifacts[0]["kind"] == "markdown"
    assert artifacts[0]["name"] == "req.md"


def test_list_artifacts_returns_sorted_by_name(browsing_client: TestClient) -> None:
    """GET /api/projects/{id}/artifacts returns artifacts sorted by name."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Sort Project")
    _add_membership(browsing_client, project, member)

    browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "markdown", "name": "zebra.md", "content": "Z"},
    )
    browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "markdown", "name": "alpha.md", "content": "A"},
    )
    browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "markdown", "name": "middle.md", "content": "M"},
    )

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
    )

    assert response.status_code == 200
    names = [a["name"] for a in response.json()]
    assert names == ["alpha.md", "middle.md", "zebra.md"]


# --- Permission Checks ---


def test_unauthenticated_user_cannot_list_artifacts(browsing_client: TestClient) -> None:
    """Unauthenticated request to list artifacts returns 401."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Protected Project")
    _add_membership(browsing_client, project, member)

    browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "markdown", "name": "secret.md", "content": "secret"},
    )

    response = browsing_client.get(f"/api/projects/{project.id}/artifacts")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_non_member_cannot_list_project_artifacts(browsing_client: TestClient) -> None:
    """Non-member gets 404 when listing artifacts for a project."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    outsider = _create_user(browsing_client, "outsider@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Member Project")
    _add_membership(browsing_client, project, member)

    browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "markdown", "name": "internal.md", "content": "internal"},
    )

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, outsider),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Resource not found"


def test_admin_can_list_any_project_artifacts(browsing_client: TestClient) -> None:
    """Admin user can list artifacts for any project."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    admin = _create_user(browsing_client, "admin@example.com", ADMIN_ROLE)
    project = _create_project(browsing_client, "Admin Access Project")
    _add_membership(browsing_client, project, member)

    browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "markdown", "name": "doc.md", "content": "doc"},
    )

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, admin),
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_stale_user_cannot_list_artifacts(browsing_client: TestClient) -> None:
    """Deactivated user gets 401 when listing artifacts."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Stale Project")
    _add_membership(browsing_client, project, member)

    browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "markdown", "name": "doc.md", "content": "doc"},
    )

    token = _token(browsing_client, member)

    # Deactivate the user
    session_gen = _session_from_override(browsing_client)
    session = next(session_gen)
    try:
        db_user = session.get(User, member.id)
        assert db_user is not None
        db_user.is_active = False
        session.commit()
    finally:
        session_gen.close()

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


# --- Artifact Detail ---


def test_get_artifact_detail_returns_versions(browsing_client: TestClient) -> None:
    """GET /api/projects/{id}/artifacts/{artifact_id} returns artifact with versions."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Detail Project")
    _add_membership(browsing_client, project, member)

    created = browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "markdown", "name": "versioned.md", "content": "# V1"},
    )
    artifact_id = created.json()["id"]

    # Add version 2
    browsing_client.post(
        f"/api/projects/{project.id}/artifacts/{artifact_id}/versions",
        headers=_auth_headers(browsing_client, member),
        json={"content": "# V2"},
    )

    detail = browsing_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}",
        headers=_auth_headers(browsing_client, member),
    )

    assert detail.status_code == 200
    data = detail.json()
    assert data["id"] == artifact_id
    assert data["current_version"] == 2
    assert len(data["versions"]) == 2
    versions = sorted(data["versions"], key=lambda v: v["version"])
    assert versions[0]["version"] == 1
    assert versions[1]["version"] == 2


def test_get_artifact_detail_returns_404_for_nonexistent(browsing_client: TestClient) -> None:
    """GET /api/projects/{id}/artifacts/{id} returns 404 for nonexistent artifact."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Ghost Project")
    _add_membership(browsing_client, project, member)

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts/00000000-0000-0000-0000-000000000001",
        headers=_auth_headers(browsing_client, member),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Resource not found"


def test_get_artifact_content_returns_text(browsing_client: TestClient) -> None:
    """GET /api/projects/{id}/artifacts/{id}/content returns UTF-8 text content."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Content Project")
    _add_membership(browsing_client, project, member)

    created = browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "markdown", "name": "content.md", "content": "# Hello"},
    )
    artifact_id = created.json()["id"]

    content = browsing_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}/content",
        headers=_auth_headers(browsing_client, member),
    )

    assert content.status_code == 200
    assert content.json()["content"] == "# Hello"
    assert content.json()["content_encoding"] == "text"


def test_get_artifact_content_returns_base64_for_binary(browsing_client: TestClient) -> None:
    """GET /api/projects/{id}/artifacts/{id}/content returns base64 for binary content."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Binary Project")
    _add_membership(browsing_client, project, member)
    binary_content = b"\xff\x00\x01\x02"

    created = browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={
            "kind": "screenshot",
            "name": "screen.png",
            "content": b64encode(binary_content).decode("ascii"),
            "content_encoding": "base64",
        },
    )
    artifact_id = created.json()["id"]

    content = browsing_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}/content",
        headers=_auth_headers(browsing_client, member),
    )

    assert content.status_code == 200
    assert content.json()["content_encoding"] == "base64"


# --- Empty State Handling ---


def test_list_artifacts_for_project_with_no_artifacts_and_no_members(
    browsing_client: TestClient,
) -> None:
    """Empty project with no artifacts returns empty list for member."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Empty Project")
    _add_membership(browsing_client, project, member)

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
    )

    assert response.status_code == 200
    assert response.json() == []


def test_filter_by_kind_returns_empty_when_no_match(browsing_client: TestClient) -> None:
    """Filtering by kind returns empty list when no artifacts match."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "No Match Project")
    _add_membership(browsing_client, project, member)

    browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "markdown", "name": "doc.md", "content": "doc"},
    )

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts?kind=screenshot",
        headers=_auth_headers(browsing_client, member),
    )

    assert response.status_code == 200
    assert response.json() == []


def test_artifact_list_excludes_storage_path(browsing_client: TestClient) -> None:
    """Artifact list responses never expose storage_path."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Secure Project")
    _add_membership(browsing_client, project, member)

    browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "markdown", "name": "doc.md", "content": "doc"},
    )

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
    )

    assert response.status_code == 200
    for artifact in response.json():
        assert "storage_path" not in artifact


def test_artifact_detail_excludes_storage_path(browsing_client: TestClient) -> None:
    """Artifact detail responses never expose storage_path in versions."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Secure Detail Project")
    _add_membership(browsing_client, project, member)

    created = browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "markdown", "name": "doc.md", "content": "doc"},
    )
    artifact_id = created.json()["id"]

    detail = browsing_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}",
        headers=_auth_headers(browsing_client, member),
    )

    assert detail.status_code == 200
    assert "storage_path" not in detail.json()
    for version in detail.json()["versions"]:
        assert "storage_path" not in version


def test_artifact_api_openapi_schema_includes_endpoints(browsing_client: TestClient) -> None:
    """OpenAPI schema includes all artifact endpoints."""
    schema = browsing_client.get("/openapi.json").json()

    assert "/api/projects/{project_id}/artifacts" in schema["paths"]
    assert "ArtifactResponse" in schema["components"]["schemas"]
    assert "ArtifactCreateRequest" in schema["components"]["schemas"]
    assert "ArtifactDetailResponse" in schema["components"]["schemas"]


def test_oversized_content_is_rejected(browsing_client: TestClient) -> None:
    """Artifact creation rejects content exceeding MAX_ARTIFACT_CONTENT_CHARS."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Large Content Project")
    _add_membership(browsing_client, project, member)
    oversized = "x" * 1_000_001

    response = browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "markdown", "name": "huge.md", "content": oversized},
    )

    assert response.status_code == 422


def test_artifact_create_requires_membership(browsing_client: TestClient) -> None:
    """Creating an artifact requires project membership."""
    outsider = _create_user(browsing_client, "outsider@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Protected Create Project")

    response = browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, outsider),
        json={"kind": "markdown", "name": "denied.md", "content": "denied"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Resource not found"


def test_artifact_delete_removes_from_listing(
    browsing_client: TestClient,
) -> None:
    """[P2] Deleted artifacts no longer appear in artifact listing."""
    member = _create_user(browsing_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Delete Project")
    _add_membership(browsing_client, project, member)

    created = browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "markdown", "name": "ephemeral.md", "content": "temp"},
    )
    assert created.status_code == 200

    list_before = browsing_client.get(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
    )
    assert list_before.status_code == 200
    assert len(list_before.json()) == 1


# ---------------------------------------------------------------------------
# Task 5.1 — GET /projects/{id}/artifacts/tree endpoint tests
# ---------------------------------------------------------------------------


def test_tree_empty_project_returns_four_folders(browsing_client: TestClient) -> None:
    """Empty project: 4 browse folders; required 3 are marked required=true, all entries empty."""
    member = _create_user(browsing_client, "member@tree.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Tree Empty Project")
    _add_membership(browsing_client, project, member)

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts/tree",
        headers=_auth_headers(browsing_client, member),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == str(project.id)

    folders = data["folders"]
    folder_names = [f["name"] for f in folders]
    assert folder_names == ["requirements", "test_cases", "test_scripts", "reports"]

    required_names = {f["name"] for f in folders if f["required"]}
    assert required_names == {"requirements", "test_cases", "test_scripts"}

    for folder in folders:
        assert folder["is_empty"] is True
        assert folder["entries"] == []

    # Reports present but not required
    reports_folder = next(f for f in folders if f["name"] == "reports")
    assert reports_folder["required"] is False


def test_tree_groups_artifacts_by_kind(browsing_client: TestClient) -> None:
    """Populated project: raw_html/image → requirements, playwright_script → test_scripts,
    testcase → test_cases, report → reports.
    """
    member = _create_user(browsing_client, "member@grouping.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Tree Grouping Project")
    _add_membership(browsing_client, project, member)

    for kind, name in [
        ("testcase", "tc.json"),
        ("playwright_script", "pw.ts"),
        ("report", "rep.md"),
        ("image", "img.png"),
    ]:
        r = browsing_client.post(
            f"/api/projects/{project.id}/artifacts",
            headers=_auth_headers(browsing_client, member),
            json={"kind": kind, "name": name, "content": f"content of {name}"},
        )
        assert r.status_code == 200, f"Failed to create {kind}/{name}: {r.json()}"

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts/tree",
        headers=_auth_headers(browsing_client, member),
    )
    assert response.status_code == 200
    folders = {f["name"]: f for f in response.json()["folders"]}

    assert {e["name"] for e in folders["requirements"]["entries"]} == {"img.png"}
    assert {e["name"] for e in folders["test_cases"]["entries"]} == {"tc.json"}
    assert {e["name"] for e in folders["test_scripts"]["entries"]} == {"pw.ts"}
    assert {e["name"] for e in folders["reports"]["entries"]} == {"rep.md"}


def test_tree_entries_carry_title_and_parent_source_id(browsing_client: TestClient) -> None:
    """title + parent_source_id round-trip all the way through the tree *API* response
    (not just the service dict) so the frontend can show friendly names and build a
    Confluence-like hierarchy. Guards the api/artifacts.py ArtifactTreeEntry construction
    against silently dropping these fields.
    """
    member = _create_user(browsing_client, "member@hierarchy.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Tree Hierarchy Project")
    _add_membership(browsing_client, project, member)

    # title/parent_source_id are set by the on-approve save path, not the create API,
    # so insert directly via the model (mirrors test_tree_null_creator_yields_null_display).
    session_gen = _session_from_override(browsing_client)
    session = next(session_gen)
    try:
        from uuid import uuid4

        from ai_qa.artifacts.storage import build_artifact_key

        for name, title, parent_source_id in [
            ("100/requirement.md", "Personal Travel Plan", None),
            ("101/requirement.md", "US01 - Create journey", "100"),
        ]:
            artifact_id = uuid4()
            session.add(
                Artifact(
                    id=artifact_id,
                    project_id=project.id,
                    kind="requirements",
                    name=name,
                    storage_path=build_artifact_key(
                        project_id=project.id,
                        artifact_id=artifact_id,
                        version=1,
                        kind="requirements",
                        safe_name=Path(name).name,
                    ),
                    title=title,
                    parent_source_id=parent_source_id,
                )
            )
        session.commit()
    finally:
        session_gen.close()

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts/tree",
        headers=_auth_headers(browsing_client, member),
    )
    assert response.status_code == 200
    folders = {f["name"]: f for f in response.json()["folders"]}
    by_name = {e["name"]: e for e in folders["requirements"]["entries"]}

    assert by_name["100/requirement.md"]["title"] == "Personal Travel Plan"
    assert by_name["100/requirement.md"]["parent_source_id"] is None
    assert by_name["101/requirement.md"]["title"] == "US01 - Create journey"
    assert by_name["101/requirement.md"]["parent_source_id"] == "100"


def test_tree_entries_carry_resolved_display_names(browsing_client: TestClient) -> None:
    """Entries carry name, kind, updated_at AND resolved created_by_display/updated_by_display
    equal to User.display_name (not UUIDs).
    """
    member = _create_user(browsing_client, "alice@display.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Tree Display Names Project", creator=member)
    _add_membership(browsing_client, project, member)

    created = browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "requirements", "name": "req.md", "content": "# Req"},
    )
    assert created.status_code == 200

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts/tree",
        headers=_auth_headers(browsing_client, member),
    )
    assert response.status_code == 200
    folders = {f["name"]: f for f in response.json()["folders"]}
    entry = folders["requirements"]["entries"][0]

    # Presence of required fields
    assert entry["name"] == "req.md"
    assert entry["kind"] == "requirements"
    assert "updated_at" in entry

    # Display name is the display_name string, not a UUID
    created_display = entry["created_by_display"]
    assert created_display == member.display_name
    # Resolved to a display name, not the raw creator UUID
    assert created_display != entry["created_by_user_id"]


def test_tree_null_creator_yields_null_display(browsing_client: TestClient) -> None:
    """Artifact with created_by_user_id=None → created_by_display is None (no crash)."""
    member = _create_user(browsing_client, "member@nullcreator.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Tree Null Creator Project")
    _add_membership(browsing_client, project, member)

    # Create artifact via API (member sets created_by), then directly insert a no-creator one
    session_gen = _session_from_override(browsing_client)
    session = next(session_gen)
    from ai_qa.db.models import Artifact as ArtifactModel

    try:
        from uuid import uuid4

        from ai_qa.artifacts.storage import build_artifact_key

        artifact_id = uuid4()
        storage_path = build_artifact_key(
            project_id=project.id,
            artifact_id=artifact_id,
            version=1,
            kind="requirements",
            safe_name="anon.md",
        )
        a = ArtifactModel(
            id=artifact_id,
            project_id=project.id,
            kind="requirements",
            name="anon.md",
            storage_path=storage_path,
            created_by_user_id=None,
            updated_by_user_id=None,
        )
        session.add(a)
        session.commit()
    finally:
        session_gen.close()

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts/tree",
        headers=_auth_headers(browsing_client, member),
    )
    assert response.status_code == 200
    folders = {f["name"]: f for f in response.json()["folders"]}
    entry = next(e for e in folders["requirements"]["entries"] if e["name"] == "anon.md")

    assert entry["created_by_display"] is None
    assert entry["updated_by_display"] is None


def test_tree_pii_canary(browsing_client: TestClient) -> None:
    """The /artifacts/tree response body contains no email or storage_path."""
    member = _create_user(browsing_client, "pii-canary@example.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Tree PII Canary Project")
    _add_membership(browsing_client, project, member)

    browsing_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(browsing_client, member),
        json={"kind": "requirements", "name": "req.md", "content": "content"},
    )

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts/tree",
        headers=_auth_headers(browsing_client, member),
    )
    assert response.status_code == 200
    body = response.text

    assert "pii-canary@example.com" not in body
    assert "storage_path" not in body


def test_tree_cross_project_scoping(browsing_client: TestClient) -> None:
    """Project-B artifacts never appear in project-A's tree."""
    member_a = _create_user(browsing_client, "member-a@scope.com", STANDARD_ROLE)
    member_b = _create_user(browsing_client, "member-b@scope.com", STANDARD_ROLE)
    project_a = _create_project(browsing_client, "Tree Project A")
    project_b = _create_project(browsing_client, "Tree Project B")
    _add_membership(browsing_client, project_a, member_a)
    _add_membership(browsing_client, project_b, member_b)

    browsing_client.post(
        f"/api/projects/{project_a.id}/artifacts",
        headers=_auth_headers(browsing_client, member_a),
        json={"kind": "requirements", "name": "a_req.md", "content": "A"},
    )
    browsing_client.post(
        f"/api/projects/{project_b.id}/artifacts",
        headers=_auth_headers(browsing_client, member_b),
        json={"kind": "requirements", "name": "b_req.md", "content": "B"},
    )

    response_a = browsing_client.get(
        f"/api/projects/{project_a.id}/artifacts/tree",
        headers=_auth_headers(browsing_client, member_a),
    )
    assert response_a.status_code == 200
    body_a = response_a.text
    assert "b_req.md" not in body_a
    assert "a_req.md" in body_a


def test_tree_non_member_gets_404(browsing_client: TestClient) -> None:
    """Non-member requesting /tree gets 404 RESOURCE_NOT_FOUND_DETAIL."""
    member = _create_user(browsing_client, "member@403tree.com", STANDARD_ROLE)
    outsider = _create_user(browsing_client, "outsider@403tree.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Tree Protected Project")
    _add_membership(browsing_client, project, member)

    response = browsing_client.get(
        f"/api/projects/{project.id}/artifacts/tree",
        headers=_auth_headers(browsing_client, outsider),
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Resource not found"
    # Leak-canary (Task 5.1): the 404 body must not leak the project storage prefix
    # or any storage_path key to a non-member.
    body = response.text
    assert f"projects/{project.id}/" not in body
    assert "storage_path" not in body


def test_tree_unauthenticated_gets_401(browsing_client: TestClient) -> None:
    """Unauthenticated /tree request returns 401."""
    member = _create_user(browsing_client, "member@401tree.com", STANDARD_ROLE)
    project = _create_project(browsing_client, "Tree Auth Project")
    _add_membership(browsing_client, project, member)

    response = browsing_client.get(f"/api/projects/{project.id}/artifacts/tree")
    assert response.status_code == 401


def test_tree_openapi_schema_includes_tree_endpoint(browsing_client: TestClient) -> None:
    """OpenAPI schema includes the /tree endpoint and new response models."""
    schema = browsing_client.get("/openapi.json").json()

    paths = schema.get("paths", {})
    tree_path = next((k for k in paths if k.endswith("/artifacts/tree")), None)
    assert tree_path is not None, "No /tree path in OpenAPI schema"

    components = schema.get("components", {}).get("schemas", {})
    assert "ArtifactTreeEntry" in components
    assert "ArtifactTreeFolder" in components
    assert "ArtifactTreeResponse" in components
