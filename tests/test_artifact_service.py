"""Tests for project-scoped artifact storage and service behavior."""

from collections.abc import Generator
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import Table, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.artifacts.service import ArtifactService
from ai_qa.artifacts.storage import LocalArtifactStorage, sanitize_artifact_name
from ai_qa.db.base import Base
from ai_qa.db.models import Artifact, ArtifactVersion, PipelineRun, Project, User


@pytest.fixture
def db_session() -> Generator[Session]:
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
                PipelineRun.__table__,
                Artifact.__table__,
                ArtifactVersion.__table__,
            ],
        ),
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def _create_project(session: Session) -> Project:
    project = Project(name="Scoped", description="Project scoped artifacts")
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def test_local_storage_sanitizes_paths_and_round_trips_content(tmp_path: Path) -> None:
    storage = LocalArtifactStorage(tmp_path)
    project_id = uuid4()
    artifact_id = uuid4()

    storage_path = storage.write(
        project_id=project_id,
        artifact_id=artifact_id,
        version=1,
        kind="markdown",
        name="..\\secret folder/unsafe script.md",
        content="hello artifact",
    )

    assert ".." not in Path(storage_path).parts
    assert storage_path.endswith("unsafe-script.md")
    assert storage.read(storage_path) == b"hello artifact"


def test_local_storage_rejects_traversal_reads(tmp_path: Path) -> None:
    storage = LocalArtifactStorage(tmp_path)

    with pytest.raises(ValueError, match="Invalid artifact storage path"):
        storage.read("../secret.txt")

    with pytest.raises(ValueError, match="Invalid artifact storage path"):
        storage.read(str((tmp_path / "absolute.txt").resolve()))


def test_sanitize_artifact_name_handles_blank_and_windows_separators() -> None:
    assert (
        sanitize_artifact_name("..\\folder\\Playwright Script!.ts")
        == "folder/Playwright-Script-.ts"
    )
    assert sanitize_artifact_name("../") == "artifact"


def test_artifact_service_persists_metadata_initial_version_and_hash(
    db_session: Session, tmp_path: Path
) -> None:
    project = _create_project(db_session)
    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))

    artifact = service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="markdown",
        name="requirements.md",
        content="# Requirements",
    )

    assert artifact.project_id == project.id
    assert artifact.kind == "markdown"
    assert artifact.current_version == 1
    assert artifact.storage_path.endswith("requirements.md")
    assert service.read_current_content(artifact) == b"# Requirements"

    versions = db_session.execute(select(ArtifactVersion)).scalars().all()
    assert len(versions) == 1
    assert versions[0].version == 1
    assert len(versions[0].content_hash) == 64
    assert versions[0].storage_path == artifact.storage_path


def test_artifact_service_appends_versions_without_mutating_history(
    db_session: Session, tmp_path: Path
) -> None:
    project = _create_project(db_session)
    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))
    artifact = service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="mermaid",
        name="flow.mmd",
        content="graph TD; A-->B;",
    )
    first_storage_path = artifact.storage_path
    first_hash = artifact.versions[0].content_hash

    updated = service.create_version(
        project_id=project.id,
        artifact_id=artifact.id,
        created_by_user_id=None,
        content="graph TD; A-->C;",
    )

    assert updated is not None
    assert updated.current_version == 2
    assert updated.storage_path != first_storage_path
    assert service.read_current_content(updated) == b"graph TD; A-->C;"
    assert service.storage.read(first_storage_path) == b"graph TD; A-->B;"

    versions = sorted(updated.versions, key=lambda version: version.version)
    assert [version.version for version in versions] == [1, 2]
    assert versions[0].storage_path == first_storage_path
    assert versions[0].content_hash == first_hash
    assert versions[1].content_hash != first_hash


def test_artifact_service_filters_kind_and_validates_pipeline_project(
    db_session: Session, tmp_path: Path
) -> None:
    project = _create_project(db_session)
    other_project = Project(name="Other")
    db_session.add(other_project)
    db_session.commit()
    pipeline_run = PipelineRun(project_id=other_project.id, status="pending")
    db_session.add(pipeline_run)
    db_session.commit()
    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))

    service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="markdown",
        name="one.md",
        content="one",
    )
    service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="report",
        name="report.md",
        content="report",
    )

    assert [artifact.name for artifact in service.list_artifacts(project_id=project.id)] == [
        "one.md",
        "report.md",
    ]
    assert [
        artifact.name for artifact in service.list_artifacts(project_id=project.id, kind="report")
    ] == ["report.md"]
    with pytest.raises(ValueError, match="Pipeline run does not belong to project"):
        service.save_artifact(
            project_id=project.id,
            owner_user_id=None,
            kind="markdown",
            name="bad.md",
            content="bad",
            pipeline_run_id=pipeline_run.id,
        )


class RecordingStorage:
    """Storage fake that records writes and deletes for rollback cleanup tests."""

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
        storage_path = f"projects/{project_id}/artifacts/{artifact_id}/v{version}/{name}"
        self.contents[storage_path] = (
            content.encode("utf-8") if isinstance(content, str) else content
        )
        return storage_path

    def read(self, storage_path: str) -> bytes:
        return self.contents[storage_path]

    def delete(self, storage_path: str) -> None:
        self.deleted.append(storage_path)
        self.contents.pop(storage_path, None)


def test_artifact_service_cleans_file_when_commit_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _create_project(db_session)
    storage = RecordingStorage()
    service = ArtifactService(db_session, storage)

    def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="commit failed"):
        service.save_artifact(
            project_id=project.id,
            owner_user_id=None,
            kind="markdown",
            name="cleanup.md",
            content="cleanup",
        )

    assert len(storage.deleted) == 1
    assert storage.contents == {}


def test_artifact_service_cleans_version_file_when_commit_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _create_project(db_session)
    storage = RecordingStorage()
    service = ArtifactService(db_session, storage)
    artifact = service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="markdown",
        name="version-cleanup.md",
        content="v1",
    )
    first_storage_path = artifact.storage_path

    def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="commit failed"):
        service.create_version(
            project_id=project.id,
            artifact_id=artifact.id,
            created_by_user_id=None,
            content="v2",
        )

    assert len(storage.deleted) == 1
    assert first_storage_path in storage.contents
    assert all("/v2/" not in path for path in storage.contents)


def test_artifact_service_create_version_is_project_scoped(
    db_session: Session, tmp_path: Path
) -> None:
    project = _create_project(db_session)
    other_project = Project(name="Other")
    db_session.add(other_project)
    db_session.commit()
    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))
    artifact = service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="markdown",
        name="scoped.md",
        content="v1",
    )

    updated = service.create_version(
        project_id=other_project.id,
        artifact_id=artifact.id,
        created_by_user_id=None,
        content="v2",
    )

    assert updated is None
