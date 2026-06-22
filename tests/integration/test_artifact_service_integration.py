"""Integration tests for AC3: thread_id propagation and no-bypass import guard.

Story 10-5 acceptance criteria:
  AC3-a: Artifacts saved via PipelineArtifactAdapter carry the thread_id from
          PipelineContext — no artifact should land in a second project's query.
  AC3-b: OutputWriter must not be importable from any production path — it was
          deleted as part of this story so any lingering reference is a bug.
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import Table, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.artifacts.service import ArtifactService
from ai_qa.artifacts.storage import LocalArtifactStorage
from ai_qa.db.base import Base
from ai_qa.db.models import Artifact, ArtifactVersion, Project, User
from ai_qa.pipelines.artifact_adapter import PipelineArtifactAdapter
from ai_qa.pipelines.context import PipelineContext
from ai_qa.threads.models import AgentRun, Thread

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _build_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=cast(
            "list[Table]",
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
    return engine


# ---------------------------------------------------------------------------
# AC3-a: cross-project read leak-canary
# ---------------------------------------------------------------------------


def test_cross_project_read_isolation_canary(tmp_path) -> None:
    """[AC3] Artifact written in project-A is invisible to project-B adapter.

    This is the leak-canary: if PipelineArtifactAdapter's load_* methods ever
    return data from a foreign project, a real privacy/isolation regression has
    been introduced and this test will fail loudly.
    """
    engine = _build_engine()
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        user = User(
            email="tester@example.com",
            display_name="tester",
            password_hash="hash",
            role="standard",
            is_active=True,
        )
        project_a = Project(name="ProjectA", created_by_user=user)
        project_b = Project(name="ProjectB", created_by_user=user)
        session.add_all([user, project_a, project_b])
        session.commit()

        thread_a = Thread(project_id=project_a.id, user_id=user.id)
        thread_b = Thread(project_id=project_b.id, user_id=user.id)
        session.add_all([thread_a, thread_b])
        session.flush()
        run_a = AgentRun(thread_id=thread_a.id, status="running")
        run_b = AgentRun(thread_id=thread_b.id, status="running")
        session.add_all([run_a, run_b])
        session.commit()

        storage = LocalArtifactStorage(root=tmp_path)
        service = ArtifactService(session, storage)

        ctx_a = PipelineContext(
            project_id=project_a.id,
            user_id=user.id,
            user_email=user.email,
            artifact_service=service,
            agent_run_id=run_a.id,
            thread_id=thread_a.id,
        )
        ctx_b = PipelineContext(
            project_id=project_b.id,
            user_id=user.id,
            user_email=user.email,
            artifact_service=service,
            agent_run_id=run_b.id,
            thread_id=thread_b.id,
        )

        adapter_a = PipelineArtifactAdapter(ctx_a)
        adapter_b = PipelineArtifactAdapter(ctx_b)

        # Write a requirement into project-A only
        saved = adapter_a.save_requirement_page("requirements/page-001.md", "# Project A secret")
        # Verify thread_id forwarding (AC1)
        assert saved.thread_id == thread_a.id, "thread_id not forwarded — AC1 regression"
        assert saved.project_id == project_a.id

        # project-B adapter must not see project-A's artifacts
        b_requirements = adapter_b.load_requirement_markdown()
        assert b_requirements == [], (
            "Cross-project read leak detected: project-B can see project-A artifacts"
        )

        # project-A adapter CAN see its own artifacts
        a_requirements = adapter_a.load_requirement_markdown()
        assert len(a_requirements) == 1
        assert a_requirements[0].content == "# Project A secret"

    finally:
        session.close()
    engine.dispose()


def test_thread_id_stamped_on_all_adapter_save_methods(tmp_path) -> None:
    """[AC1] Every adapter save method forwards thread_id to ArtifactService.

    Validates that requirements, test-cases, scripts, metadata, and image
    artifacts all carry the thread_id from PipelineContext.
    """
    engine = _build_engine()
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        user = User(
            email="tester@example.com",
            display_name="tester",
            password_hash="hash",
            role="standard",
            is_active=True,
        )
        project = Project(name="ThreadTest", created_by_user=user)
        session.add_all([user, project])
        session.commit()

        thread = Thread(project_id=project.id, user_id=user.id)
        session.add(thread)
        session.flush()
        run = AgentRun(thread_id=thread.id, status="running")
        session.add(run)
        session.commit()

        storage = LocalArtifactStorage(root=tmp_path)
        service = ArtifactService(session, storage)

        ctx = PipelineContext(
            project_id=project.id,
            user_id=user.id,
            user_email=user.email,
            artifact_service=service,
            agent_run_id=run.id,
            thread_id=thread.id,
        )
        adapter = PipelineArtifactAdapter(ctx)

        req = adapter.save_requirement_page("req.md", "# Req")
        tc = adapter.save_test_case("tc.json", '{"title": "T1"}')
        script = adapter.save_script("script.spec.ts", "test('x', () => {})")
        meta = adapter.save_metadata("meta.json", {"ok": True})

        for artifact in (req, tc, script, meta):
            assert artifact.thread_id == thread.id, (
                f"artifact kind={artifact.kind!r} missing thread_id"
            )
    finally:
        session.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# AC3-b: no-bypass import guard — OutputWriter must not be importable
# ---------------------------------------------------------------------------


def test_output_writer_is_not_importable() -> None:
    """[AC2] OutputWriter class must not exist in any importable production module.

    If this test fails it means output_writer.py was re-introduced or OutputWriter
    was re-exported somewhere — both of which are regressions.
    """
    import importlib
    import importlib.util

    # The file was deleted; the module must not be findable
    spec = importlib.util.find_spec("ai_qa.pipelines.output_writer")
    assert spec is None, (
        "ai_qa.pipelines.output_writer still exists on the module path — "
        "OutputWriter deletion is incomplete"
    )


def test_output_writer_not_in_pipelines_namespace() -> None:
    """[AC2] OutputWriter must not appear in the pipelines package __all__."""
    import ai_qa.pipelines as pipelines_pkg

    assert not hasattr(pipelines_pkg, "OutputWriter"), (
        "OutputWriter is still exported from ai_qa.pipelines — remove from __all__"
    )
    assert "OutputWriter" not in getattr(pipelines_pkg, "__all__", []), (
        "OutputWriter is still in ai_qa.pipelines.__all__"
    )
