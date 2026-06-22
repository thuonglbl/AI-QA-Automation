"""Tests for provenance columns on the artifact service (Story 11.7)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.artifacts.service import ArtifactService
from ai_qa.artifacts.storage import LocalArtifactStorage
from ai_qa.db.base import Base
from ai_qa.db.models import Artifact, ArtifactVersion, Project, User
from ai_qa.pipelines.artifact_adapter import PipelineArtifactAdapter
from ai_qa.pipelines.context import PipelineContext
from ai_qa.threads.models import AgentRun, Thread


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
                Thread.__table__,
                AgentRun.__table__,
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
    engine.dispose()


@pytest.fixture
def _seed(db_session: Session) -> tuple[Project, User]:
    user = User(
        email="member@example.com",
        display_name="member",
        password_hash="hash",
        role="standard",
        is_active=True,
    )
    project = Project(name="Scoped", created_by_user=user)
    db_session.add_all([user, project])
    db_session.commit()
    return project, user


def test_save_artifact_provenance_columns_round_trip(
    db_session: Session,
    _seed: tuple[Project, User],
    tmp_path: Path,
) -> None:
    """6.1: provenance columns persist and round-trip from DB; storage path under requirements/."""
    project, user = _seed
    service = ArtifactService(db_session, LocalArtifactStorage(root=tmp_path))

    artifact = service.save_artifact(
        project_id=project.id,
        owner_user_id=user.id,
        kind="requirements",
        name="p1/requirement.md",
        content="# Requirement",
        source_type="confluence",
        source_url="https://example.atlassian.net/wiki/spaces/TEST/pages/12345",
        warnings=[{"category": "vague_language", "message": "m", "location": "P1", "impact": "i"}],
    )

    db_session.expire(artifact)
    reloaded = db_session.get(Artifact, artifact.id)
    assert reloaded is not None
    assert reloaded.source_type == "confluence"
    assert reloaded.source_url == "https://example.atlassian.net/wiki/spaces/TEST/pages/12345"
    assert reloaded.warnings is not None
    assert len(reloaded.warnings) == 1
    assert reloaded.warnings[0]["category"] == "vague_language"
    assert reloaded.storage_path.startswith(f"projects/{project.id}/requirements/")


def test_save_artifact_provenance_defaults_to_none(
    db_session: Session,
    _seed: tuple[Project, User],
    tmp_path: Path,
) -> None:
    """6.1 back-compat: omitting provenance params leaves all three columns NULL."""
    project, user = _seed
    service = ArtifactService(db_session, LocalArtifactStorage(root=tmp_path))

    artifact = service.save_artifact(
        project_id=project.id,
        owner_user_id=user.id,
        kind="requirements",
        name="p1.md",
        content="# Draft",
    )

    db_session.expire(artifact)
    reloaded = db_session.get(Artifact, artifact.id)
    assert reloaded is not None
    assert reloaded.source_type is None
    assert reloaded.source_url is None
    assert reloaded.warnings is None


def test_ac2_query_reachability_no_workspace_path(
    db_session: Session,
    _seed: tuple[Project, User],
    tmp_path: Path,
) -> None:
    """6.5: approved requirement queryable via list_artifacts + read_current_content; no workspace path."""
    project, user = _seed

    thread = Thread(project_id=project.id, user_id=user.id)
    db_session.add(thread)
    db_session.flush()
    agent_run = AgentRun(thread_id=thread.id, status="running")
    db_session.add(agent_run)
    db_session.commit()

    storage = LocalArtifactStorage(root=tmp_path)
    service = ArtifactService(db_session, storage)
    adapter = PipelineArtifactAdapter(
        PipelineContext(
            project_id=project.id,
            user_id=user.id,
            user_email=user.email,
            artifact_service=service,
            agent_run_id=agent_run.id,
            thread_id=thread.id,
        )
    )

    adapter.save_requirement(
        page_id="p1",
        markdown="# Approved Requirement\n\nGiven setup, Then result expected.",
        source_type="confluence",
        source_url="https://example.atlassian.net/p1",
        warnings=[],
    )

    artifacts = service.list_artifacts(project_id=project.id, kind="requirements")
    approved = [a for a in artifacts if a.name == "p1/requirement.md"]
    assert len(approved) == 1
    a = approved[0]

    content = service.read_current_content(a)
    assert b"Approved Requirement" in content

    assert a.source_type == "confluence"
    assert a.source_url == "https://example.atlassian.net/p1"
    assert a.warnings == []
    assert "workspace" not in a.storage_path


def test_ac2_draft_vs_approved_discriminator(
    db_session: Session,
    _seed: tuple[Project, User],
    tmp_path: Path,
) -> None:
    """6.5: draft has NULL provenance; approved has provenance set — discriminator works."""
    project, user = _seed

    thread = Thread(project_id=project.id, user_id=user.id)
    db_session.add(thread)
    db_session.flush()
    agent_run = AgentRun(thread_id=thread.id, status="running")
    db_session.add(agent_run)
    db_session.commit()

    storage = LocalArtifactStorage(root=tmp_path)
    service = ArtifactService(db_session, storage)
    adapter = PipelineArtifactAdapter(
        PipelineContext(
            project_id=project.id,
            user_id=user.id,
            user_email=user.email,
            artifact_service=service,
            agent_run_id=agent_run.id,
            thread_id=thread.id,
        )
    )

    # Draft save (no provenance)
    adapter.save_requirement_page("p1", "# Draft")

    # Approved save (with provenance)
    adapter.save_requirement(
        page_id="p1",
        markdown="# Approved",
        source_type="confluence",
        source_url="https://example.atlassian.net/p1",
        warnings=[],
    )

    all_requirements = service.list_artifacts(project_id=project.id, kind="requirements")
    assert len(all_requirements) == 2

    drafts = [a for a in all_requirements if a.source_type is None]
    approved = [a for a in all_requirements if a.source_type is not None]
    assert len(drafts) == 1
    assert len(approved) == 1
    assert approved[0].name == "p1/requirement.md"
