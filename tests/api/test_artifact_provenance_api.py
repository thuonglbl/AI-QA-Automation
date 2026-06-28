"""API tests verifying provenance fields on artifact responses (Story 11.7)."""

from __future__ import annotations

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
from ai_qa.artifacts.service import ArtifactService
from ai_qa.artifacts.storage import LocalArtifactStorage
from ai_qa.auth.service import STANDARD_ROLE
from ai_qa.db.base import Base
from ai_qa.db.models import Artifact, ArtifactVersion, Project, ProjectMembership, User
from ai_qa.threads.models import AgentRun, Thread


class LocalStorageFake:
    """In-memory-backed LocalArtifactStorage fake for API tests."""

    def __init__(self, tmp_path: Path) -> None:
        self._storage = LocalArtifactStorage(root=tmp_path)

    def write(self, **kwargs: object) -> str:
        return self._storage.write(**kwargs)  # type: ignore[arg-type]

    def read(self, storage_path: str) -> bytes:
        return self._storage.read(storage_path)

    def delete(self, storage_path: str) -> None:
        self._storage.delete(storage_path)

    def delete_prefix(self, prefix: str) -> None:
        self._storage.delete_prefix(prefix)


@pytest.fixture
def prov_client(tmp_path: Path) -> Generator[TestClient]:
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
    storage = LocalStorageFake(tmp_path)

    def override_get_db_session() -> Generator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db_session_dependency] = override_get_db_session
    app.dependency_overrides[get_artifact_storage] = lambda: storage
    with TestClient(app) as client:
        # Attach session_factory for helper usage
        client.app.state.test_session_factory = session_factory  # type: ignore[attr-defined]
        yield client
    app.dependency_overrides.clear()
    engine.dispose()


def _session(client: TestClient) -> Session:
    return client.app.state.test_session_factory()  # type: ignore[attr-defined]


def _create_user_and_project(client: TestClient) -> tuple[User, Project]:
    session = _session(client)
    user = User(
        email="prov@example.com",
        display_name="prov",
        role=STANDARD_ROLE,
        is_active=True,
    )
    project = Project(name="ProvProject", created_by_user=user)
    session.add_all([user, project])
    session.commit()
    session.refresh(user)
    session.refresh(project)
    session.add(ProjectMembership(project_id=project.id, user_id=user.id, role="member"))
    session.commit()
    session.expunge_all()
    session.close()
    return user, project


def _seed_requirement(client: TestClient, project: Project, user: User, tmp_path: Path) -> Artifact:
    """Insert an approved requirement artifact with provenance directly via service."""
    session = _session(client)
    storage = LocalStorageFake(tmp_path)
    service = ArtifactService(session, storage)

    artifact = service.save_artifact(
        project_id=project.id,
        owner_user_id=user.id,
        kind="requirements",
        name="p1/requirement.md",
        content="# Approved Requirement",
        source_type="confluence",
        source_url="https://example.atlassian.net/wiki/spaces/TEST/pages/42",
        warnings=[{"category": "vague_language", "message": "m", "location": "P1", "impact": "i"}],
    )
    session.expunge(artifact)
    session.close()
    return artifact


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


def _auth(client: TestClient, user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client, user)}"}


def test_list_artifacts_includes_provenance_fields(prov_client: TestClient, tmp_path: Path) -> None:
    """7.1: GET /projects/{id}/artifacts?kind=requirements returns source_type/source_url/warnings."""
    user, project = _create_user_and_project(prov_client)
    _seed_requirement(prov_client, project, user, tmp_path)

    resp = prov_client.get(
        f"/api/projects/{project.id}/artifacts?kind=requirements",
        headers=_auth(prov_client, user),
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    item = items[0]
    assert item["source_type"] == "confluence"
    assert item["source_url"] == "https://example.atlassian.net/wiki/spaces/TEST/pages/42"
    assert isinstance(item["warnings"], list)
    assert len(item["warnings"]) == 1
    assert item["warnings"][0]["category"] == "vague_language"


def test_get_artifact_detail_includes_provenance_fields(
    prov_client: TestClient, tmp_path: Path
) -> None:
    """7.1: GET /projects/{id}/artifacts/{artifact_id} detail carries the 3 provenance fields."""
    user, project = _create_user_and_project(prov_client)
    artifact = _seed_requirement(prov_client, project, user, tmp_path)

    resp = prov_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact.id}",
        headers=_auth(prov_client, user),
    )
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["source_type"] == "confluence"
    assert detail["source_url"] == "https://example.atlassian.net/wiki/spaces/TEST/pages/42"
    assert detail["warnings"] is not None
    assert len(detail["warnings"]) == 1


def test_artifact_tree_includes_provenance_fields(prov_client: TestClient, tmp_path: Path) -> None:
    """7.1: GET /projects/{id}/artifacts/tree — requirements folder entry carries provenance."""
    user, project = _create_user_and_project(prov_client)
    _seed_requirement(prov_client, project, user, tmp_path)

    resp = prov_client.get(
        f"/api/projects/{project.id}/artifacts/tree",
        headers=_auth(prov_client, user),
    )
    assert resp.status_code == 200
    tree = resp.json()

    req_folder = next(f for f in tree["folders"] if f["name"] == "requirements")
    assert len(req_folder["entries"]) == 1
    entry = req_folder["entries"][0]
    assert entry["source_type"] == "confluence"
    assert entry["source_url"] == "https://example.atlassian.net/wiki/spaces/TEST/pages/42"
    assert isinstance(entry["warnings"], list)


def test_non_member_cannot_access_provenance(prov_client: TestClient, tmp_path: Path) -> None:
    """7.2: non-member receives 404 — provenance fields don't leak."""
    user, project = _create_user_and_project(prov_client)
    artifact = _seed_requirement(prov_client, project, user, tmp_path)

    session = _session(prov_client)
    intruder = User(
        email="intruder@example.com",
        display_name="intruder",
        role=STANDARD_ROLE,
        is_active=True,
    )
    session.add(intruder)
    session.commit()
    session.expunge(intruder)
    session.close()

    resp = prov_client.get(
        f"/api/projects/{project.id}/artifacts/{artifact.id}",
        headers=_auth(prov_client, intruder),
    )
    assert resp.status_code == 404


def test_artifact_provenance_fields_optional_on_draft(
    prov_client: TestClient, tmp_path: Path
) -> None:
    """7.2 back-compat: artifact created without provenance returns null fields — no schema break."""
    user, project = _create_user_and_project(prov_client)

    # Create via API (no provenance kwarg exposed in API)
    resp = prov_client.post(
        f"/api/projects/{project.id}/artifacts",
        headers=_auth(prov_client, user),
        json={"kind": "requirements", "name": "draft.md", "content": "# Draft"},
    )
    assert resp.status_code == 200
    artifact = resp.json()
    assert artifact["source_type"] is None
    assert artifact["source_url"] is None
    assert artifact["warnings"] is None
