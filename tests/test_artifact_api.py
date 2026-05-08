"""API tests for project-scoped artifact routes."""

from base64 import b64encode
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.api.app import create_app
from ai_qa.api.artifacts import get_artifact_storage
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.session import SessionManager
from ai_qa.auth.password import hash_password
from ai_qa.auth.service import ADMIN_ROLE, STANDARD_ROLE
from ai_qa.db.base import Base
from ai_qa.db.models import Artifact, ArtifactVersion, PipelineRun, Project, ProjectMembership, User


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


@pytest.fixture
def artifact_client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Project.__table__,
            ProjectMembership.__table__,
            PipelineRun.__table__,
            Artifact.__table__,
            ArtifactVersion.__table__,
        ],
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


def _session_from_override(client: TestClient) -> Generator[Session]:
    return client.app.dependency_overrides[get_db_session_dependency]()


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


def _create_pipeline_run(client: TestClient, project: Project) -> PipelineRun:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        pipeline_run = PipelineRun(project_id=project.id, status="pending")
        session.add(pipeline_run)
        session.commit()
        session.refresh(pipeline_run)
        session.expunge(pipeline_run)
        return pipeline_run
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


def test_member_creates_lists_reads_and_versions_text_artifact(artifact_client: TestClient) -> None:
    member = _create_user(artifact_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(artifact_client, "Scoped")
    pipeline_run = _create_pipeline_run(artifact_client, project)
    _add_membership(artifact_client, project, member)

    created = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(artifact_client, member),
        json={
            "kind": "markdown",
            "name": "requirements.md",
            "content": "# Requirements",
            "pipeline_run_id": str(pipeline_run.id),
        },
    )

    assert created.status_code == 200
    artifact = created.json()
    assert artifact["project_id"] == str(project.id)
    assert artifact["pipeline_run_id"] == str(pipeline_run.id)
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


def test_artifact_api_rejects_invalid_kind_missing_artifact_and_wrong_pipeline_project(
    artifact_client: TestClient,
) -> None:
    member = _create_user(artifact_client, "member@example.com", STANDARD_ROLE)
    project = _create_project(artifact_client, "Scoped")
    other_project = _create_project(artifact_client, "Other")
    wrong_pipeline = _create_pipeline_run(artifact_client, other_project)
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
    wrong_pipeline_response = artifact_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth_headers(artifact_client, member),
        json={
            "kind": "markdown",
            "name": "bad.md",
            "content": "bad",
            "pipeline_run_id": str(wrong_pipeline.id),
        },
    )

    assert invalid_kind.status_code == 422
    assert missing_artifact.status_code == 404
    assert wrong_pipeline_response.status_code == 422


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
    storage: ArtifactStorageFake = artifact_client.app.state.test_artifact_storage
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
