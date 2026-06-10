"""Tests for project-scoped pipeline artifact adapter."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.artifacts.service import ArtifactService
from ai_qa.artifacts.storage import LocalArtifactStorage
from ai_qa.db.base import Base
from ai_qa.db.models import Artifact, ArtifactVersion, Project, User
from ai_qa.pipelines.artifact_adapter import PipelineArtifactAdapter
from ai_qa.pipelines.context import PipelineContext
from ai_qa.threads.models import AgentRun, Thread


def test_pipeline_artifact_adapter_saves_and_loads_project_artifacts(tmp_path) -> None:
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
            Thread.__table__,
            AgentRun.__table__,
            Artifact.__table__,
            ArtifactVersion.__table__,
        ],
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        user = User(
            email="member@example.com",
            display_name="member",
            password_hash="hash",
            role="standard",
            is_active=True,
        )
        project = Project(name="Scoped", created_by_user=user)
        other_project = Project(name="Other", created_by_user=user)
        session.add_all([user, project, other_project])
        session.commit()

        thread = Thread(project_id=project.id, user_id=user.id)
        session.add(thread)
        session.flush()
        run = AgentRun(thread_id=thread.id, status="running")
        session.add(run)
        session.commit()

        service = ArtifactService(session, LocalArtifactStorage(root=tmp_path))
        adapter = PipelineArtifactAdapter(
            PipelineContext(
                project_id=project.id,
                user_id=user.id,
                user_email=user.email,
                artifact_service=service,
                agent_run_id=run.id,
            )
        )

        requirement = adapter.save_requirement_page("requirements/page-001.md", "# Requirement")
        test_case = adapter.save_test_case("testcases/case-001.json", {"title": "Case 1"})
        script = adapter.save_script("testscripts/case-001.spec.ts", "test('ok', async () => {})")
        metadata = adapter.save_metadata("metadata/case-001.json", {"approved": True})

        requirements = adapter.load_requirement_markdown()
        test_cases = adapter.load_test_cases()
        scripts = adapter.load_scripts()

        assert requirement.project_id == project.id
        assert requirement.agent_run_id == run.id
        assert test_case.kind == "testcase"
        assert script.kind == "playwright_script"
        assert metadata.kind == "configuration"
        assert [item.content for item in requirements] == ["# Requirement"]
        assert '"title": "Case 1"' in test_cases[0].content
        assert scripts[0].content == "test('ok', async () => {})"

        other_service = ArtifactService(session, LocalArtifactStorage(root=tmp_path))
        other_adapter = PipelineArtifactAdapter(
            PipelineContext(
                project_id=other_project.id,
                user_id=user.id,
                user_email=user.email,
                artifact_service=other_service,
                agent_run_id=None,
            )
        )
        assert other_adapter.load_requirement_markdown() == []
    finally:
        session.close()
    engine.dispose()
