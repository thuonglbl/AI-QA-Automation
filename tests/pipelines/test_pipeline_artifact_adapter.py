"""Tests for project-scoped pipeline artifact adapter."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock, patch

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


def test_pipeline_artifact_adapter_saves_and_loads_project_artifacts(tmp_path) -> None:
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


def test_adapter_save_text_schedules_broadcast_via_create_task(tmp_path) -> None:
    """Task 3.6 / AC1: _save_text calls loop.create_task with a broadcast coroutine.

    Patches asyncio.get_running_loop to return a MagicMock loop with a
    create_task spy.  Asserts that after save_requirement_page the spy was
    called once with a coroutine argument.
    """
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
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        user = User(
            email="agent@example.com",
            display_name="agent",
            password_hash="hash",
            role="standard",
            is_active=True,
        )
        project = Project(name="BroadcastTest", created_by_user=user)
        session.add_all([user, project])
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

        mock_loop = MagicMock()
        mock_loop.create_task = MagicMock()

        with patch("asyncio.get_running_loop", return_value=mock_loop):
            adapter.save_requirement_page("req/page-001.md", "# Requirement")

        mock_loop.create_task.assert_called_once()
        # The argument passed to create_task must be a coroutine
        task_arg = mock_loop.create_task.call_args.args[0]
        import inspect

        assert inspect.iscoroutine(task_arg), "create_task must receive a coroutine"
        # Close the coroutine to avoid ResourceWarning
        task_arg.close()
    finally:
        session.close()
    engine.dispose()


def test_adapter_schedule_change_event_silent_when_no_running_loop(tmp_path) -> None:
    """Task 3.6 / AC1: _schedule_change_event is silent (no raise) when no loop is running.

    Simulates unit-test context where get_running_loop raises RuntimeError.
    The adapter must not propagate the error.
    """
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
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        user = User(
            email="agent2@example.com",
            display_name="agent2",
            password_hash="hash",
            role="standard",
            is_active=True,
        )
        project = Project(name="NoLoopTest", created_by_user=user)
        session.add_all([user, project])
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

        # Simulate no running event loop (unit-test context)
        with patch("asyncio.get_running_loop", side_effect=RuntimeError("no running loop")):
            # Must not raise
            result = adapter.save_requirement_page("req/page-no-loop.md", "# Silent")

        # Artifact should still be persisted correctly
        assert result.project_id == project.id
    finally:
        session.close()
    engine.dispose()


def test_save_requirement_forwards_provenance_to_save_artifact(tmp_path) -> None:
    """6.2 (Story 11.7): save_requirement calls save_artifact with kind='requirements',
    name='{page_id}/requirement.md', and the provenance kwargs forwarded.
    """
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
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        user = User(
            email="prov@example.com",
            display_name="prov",
            password_hash="hash",
            role="standard",
            is_active=True,
        )
        project = Project(name="ProvTest", created_by_user=user)
        session.add_all([user, project])
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
                thread_id=thread.id,
            )
        )

        warnings_data = [
            {"category": "vague_language", "message": "m", "location": "l", "impact": "i"}
        ]

        with patch.object(service, "save_artifact", wraps=service.save_artifact) as mock_save:
            artifact = adapter.save_requirement(
                page_id="p1",
                markdown="# Approved md",
                source_type="jira",
                source_url="PROJ-1",
                warnings=warnings_data,
            )

        mock_save.assert_called_once()
        _, kwargs = mock_save.call_args
        assert kwargs["kind"] == "requirements"
        assert kwargs["name"] == "p1/requirement.md"
        assert kwargs["source_type"] == "jira"
        assert kwargs["source_url"] == "PROJ-1"
        assert kwargs["warnings"] == warnings_data
        assert artifact.kind == "requirements"
        assert artifact.source_type == "jira"
    finally:
        session.close()
    engine.dispose()


def test_to_pipeline_artifact_exposes_warnings_from_artifact(tmp_path) -> None:
    """12.3 Task 2: _to_pipeline_artifact populates DTO.warnings from artifact.warnings column."""
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
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        user = User(
            email="warn@example.com",
            display_name="warn",
            password_hash="hash",
            role="standard",
            is_active=True,
        )
        project = Project(name="WarnTest", created_by_user=user)
        session.add_all([user, project])
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
                thread_id=thread.id,
            )
        )

        warnings_data = [
            {
                "category": "vague_language",
                "message": "too vague",
                "location": "body",
                "impact": "medium",
            }
        ]
        adapter.save_requirement(
            page_id="warn-page",
            markdown="# Vague requirement",
            source_type="confluence",
            source_url="",
            warnings=warnings_data,
        )

        artifacts = adapter.load_requirement_markdown()
        approved = [a for a in artifacts if "requirement.md" in a.name]
        assert len(approved) == 1
        assert approved[0].warnings == warnings_data

        # Also verify: artifact without warnings returns None
        adapter.save_requirement_page("draft/page.md", "# Draft")
        all_artifacts = adapter.load_requirement_markdown()
        draft = [a for a in all_artifacts if a.name == "draft/page.md"]
        assert len(draft) == 1
        assert draft[0].warnings is None
    finally:
        session.close()
    engine.dispose()


def _make_test_db_session(tmp_path):
    """Shared SQLite-in-memory setup for 12.5 adapter tests."""
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
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()

    user = User(
        email="tc@example.com",
        display_name="tc-user",
        password_hash="hash",
        role="standard",
        is_active=True,
    )
    project = Project(name="TCProject", created_by_user=user)
    other_project = Project(name="OtherProject", created_by_user=user)
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
            thread_id=thread.id,
        )
    )
    other_adapter = PipelineArtifactAdapter(
        PipelineContext(
            project_id=other_project.id,
            user_id=user.id,
            user_email=user.email,
            artifact_service=service,
            agent_run_id=None,
        )
    )
    return session, engine, service, adapter, other_adapter, project


def test_save_test_case_idempotent_by_name(tmp_path) -> None:
    """save_test_case keeps exactly one artifact per name — same-name re-save supersedes prior (AC3 / D8).

    A retry after a partial batch failure must converge to exactly N test-case artifacts,
    never duplicating.
    """
    session, engine, service, adapter, _other_adapter, project = _make_test_db_session(tmp_path)
    try:
        adapter.save_test_case("tc-login.json", '{"title": "Login Test v1"}')
        adapter.save_test_case("tc-login.json", '{"title": "Login Test v2"}')

        all_tc = service.list_artifacts(project_id=project.id, kind="testcase")
        by_name = [a for a in all_tc if a.name == "tc-login.json"]
        assert len(by_name) == 1, "Re-save must supersede prior row — exactly one artifact per name"
        content = service.read_current_content(by_name[0]).decode("utf-8")
        assert "Login Test v2" in content, "Surviving artifact must be the latest version"
    finally:
        session.close()
    engine.dispose()


def test_save_metadata_idempotent_by_name(tmp_path) -> None:
    """C43: save_metadata keeps exactly one configuration artifact per name.

    A reject→regen→re-approve cycle re-saves the same ``{filename}.metadata.json`` side-car;
    without idempotency, duplicate configuration rows would accumulate and load_metadata
    could surface a stale copy. The same-name re-save must supersede the prior row and
    load_metadata must return the latest content.
    """
    session, engine, service, adapter, _other_adapter, project = _make_test_db_session(tmp_path)
    try:
        adapter.save_metadata("tc-login.metadata.json", {"confidence": 0.42, "version": 1})
        adapter.save_metadata("tc-login.metadata.json", {"confidence": 0.91, "version": 2})

        all_meta = service.list_artifacts(project_id=project.id, kind="configuration")
        by_name = [a for a in all_meta if a.name == "tc-login.metadata.json"]
        assert len(by_name) == 1, "Re-save must supersede prior side-car — exactly one per name"

        loaded = adapter.load_metadata("tc-login.metadata.json")
        assert loaded is not None
        assert loaded["confidence"] == 0.91, "load_metadata must return the latest row"
        assert loaded["version"] == 2

        # A differently-named side-car is kept separately (per-name idempotency only).
        adapter.save_metadata("tc-search.metadata.json", {"confidence": 0.5})
        all_meta = service.list_artifacts(project_id=project.id, kind="configuration")
        assert {a.name for a in all_meta} == {
            "tc-login.metadata.json",
            "tc-search.metadata.json",
        }
    finally:
        session.close()
    engine.dispose()


def test_save_test_case_ac2_query_reachability(tmp_path) -> None:
    """Saved test cases are reachable via project-scoped queries, no workspace path (AC2).

    Proves: load_test_cases() round-trips the content; storage_path is under
    projects/{project_id}/test_cases/; a different project's adapter returns [].
    Every kind='testcase' artifact is approved by construction (no draft exists),
    so no additional discriminator is needed — noted for Story 13.1.
    """
    from ai_qa.models import TestCase, TestCaseStep

    session, engine, service, adapter, other_adapter, project = _make_test_db_session(tmp_path)
    try:
        tc = TestCase(
            title="AC2 reachability test",
            steps=[TestCaseStep(number=1, action="Navigate", target="the login page")],
            confidence=0.8,
            confidence_level="high",
            approved_by="qa@example.com",
            approved_at="2026-06-16T10:00:00+00:00",
        )
        adapter.save_test_case("tc-ac2.json", tc.model_dump_json(indent=2))

        # load_test_cases() returns the artifact (project-scoped, no workspace path)
        test_cases = adapter.load_test_cases()
        assert len(test_cases) == 1
        assert test_cases[0].name == "tc-ac2.json"

        # Content round-trips correctly
        artifact_rows = service.list_artifacts(project_id=project.id, kind="testcase")
        assert len(artifact_rows) == 1
        artifact = artifact_rows[0]
        content = service.read_current_content(artifact).decode("utf-8")
        assert "AC2 reachability test" in content
        assert "qa@example.com" in content  # approved_by in model_dump_json

        # storage_path is under projects/{project_id}/test_cases/ — never workspace/
        assert artifact.storage_path.startswith(f"projects/{project.id}/test_cases/")
        assert "workspace" not in artifact.storage_path

        # Project isolation: a different project's adapter returns nothing
        assert other_adapter.load_test_cases() == []
    finally:
        session.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# Story 13.1: load_approved_test_cases tests
# ---------------------------------------------------------------------------


def test_load_approved_test_cases_returns_all_testcase_kind(tmp_path) -> None:
    """load_approved_test_cases returns approved (non-draft) testcase artifacts."""
    session, engine, service, adapter, _other_adapter, project = _make_test_db_session(tmp_path)
    try:
        adapter.save_test_case("tc-a.json", '{"title": "TC A"}')
        adapter.save_test_case("tc-b.json", '{"title": "TC B"}')

        results = adapter.load_approved_test_cases()
        assert len(results) == 2
        names = {r.name for r in results}
        assert names == {"tc-a.json", "tc-b.json"}
    finally:
        session.close()
    engine.dispose()


def test_loaders_exclude_streaming_drafts(tmp_path) -> None:
    """Streaming drafts (source_type='draft') are hidden from both loaders until approved."""
    session, engine, service, adapter, _other_adapter, project = _make_test_db_session(tmp_path)
    try:
        adapter.save_test_case("approved.json", '{"title": "Approved"}')
        adapter.save_test_case("draft.json", '{"title": "Draft"}', source_type="draft")

        approved_names = {r.name for r in adapter.load_approved_test_cases()}
        all_names = {r.name for r in adapter.load_test_cases()}
        assert approved_names == {"approved.json"}
        assert all_names == {"approved.json"}
        # The draft row does exist at the storage layer (visible in the folder), just
        # excluded from the loaders that feed Sarah.
        raw = {a.name for a in service.list_artifacts(project_id=project.id, kind="testcase")}
        assert raw == {"approved.json", "draft.json"}
    finally:
        session.close()
    engine.dispose()


def test_load_approved_test_cases_project_isolation(tmp_path) -> None:
    """load_approved_test_cases is project-scoped: different project returns []."""
    session, engine, service, adapter, other_adapter, _project = _make_test_db_session(tmp_path)
    try:
        adapter.save_test_case("tc-proj.json", '{"title": "Only in main project"}')

        assert other_adapter.load_approved_test_cases() == []
    finally:
        session.close()
    engine.dispose()


def test_load_approved_test_cases_thread_prioritization(tmp_path) -> None:
    """load_approved_test_cases lists current-thread artifacts first (stable sort)."""
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
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        user = User(
            email="thread@example.com",
            display_name="thread-user",
            password_hash="hash",
            role="standard",
            is_active=True,
        )
        project = Project(name="ThreadTest", created_by_user=user)
        session.add_all([user, project])
        session.commit()

        thread_a = Thread(project_id=project.id, user_id=user.id)
        thread_b = Thread(project_id=project.id, user_id=user.id)
        session.add_all([thread_a, thread_b])
        session.flush()
        run_a = AgentRun(thread_id=thread_a.id, status="running")
        run_b = AgentRun(thread_id=thread_b.id, status="running")
        session.add_all([run_a, run_b])
        session.commit()

        service = ArtifactService(session, LocalArtifactStorage(root=tmp_path))

        adapter_b = PipelineArtifactAdapter(
            PipelineContext(
                project_id=project.id,
                user_id=user.id,
                user_email=user.email,
                artifact_service=service,
                agent_run_id=run_b.id,
                thread_id=thread_b.id,
            )
        )
        adapter_b.save_test_case("tc-other-1.json", '{"title": "Other 1"}')
        adapter_b.save_test_case("tc-other-2.json", '{"title": "Other 2"}')

        adapter_a = PipelineArtifactAdapter(
            PipelineContext(
                project_id=project.id,
                user_id=user.id,
                user_email=user.email,
                artifact_service=service,
                agent_run_id=run_a.id,
                thread_id=thread_a.id,
            )
        )
        adapter_a.save_test_case("tc-current.json", '{"title": "Current thread"}')

        results = adapter_a.load_approved_test_cases()
        assert len(results) == 3
        assert results[0].name == "tc-current.json", "Current-thread artifact must be first"
        other_names = {r.name for r in results[1:]}
        assert other_names == {"tc-other-1.json", "tc-other-2.json"}
    finally:
        session.close()
    engine.dispose()


def test_pipeline_artifact_dto_carries_thread_id(tmp_path) -> None:
    """PipelineArtifact DTO exposes thread_id from Artifact.thread_id (13.1)."""
    session, engine, service, adapter, _other_adapter, _project = _make_test_db_session(tmp_path)
    try:
        adapter.save_test_case("tc-threadid.json", '{"title": "Thread ID check"}')
        results = adapter.load_approved_test_cases()
        assert len(results) == 1
        assert results[0].thread_id == adapter.context.thread_id
    finally:
        session.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# Story 13.8: save_script idempotent-by-name (AC1) + AC3 query reachability
# ---------------------------------------------------------------------------


def test_save_script_idempotent_by_name(tmp_path) -> None:
    """save_script keeps exactly one artifact per name — same-name re-save supersedes prior (AC1/D8).

    A reject→regenerate→re-approve of the same test case must converge to exactly one
    playwright_script artifact, never duplicating.
    """
    session, engine, service, adapter, _other_adapter, project = _make_test_db_session(tmp_path)
    try:
        adapter.save_script("test_login.py", "# version 1")
        adapter.save_script("test_login.py", "# version 2")

        all_scripts = service.list_artifacts(project_id=project.id, kind="playwright_script")
        by_name = [a for a in all_scripts if a.name == "test_login.py"]
        assert len(by_name) == 1, "Re-save must supersede prior row — exactly one artifact per name"
        content = service.read_current_content(by_name[0]).decode("utf-8")
        assert "# version 2" in content, "Surviving artifact must be the latest version"
    finally:
        session.close()
    engine.dispose()


def test_save_script_ac3_query_reachability(tmp_path) -> None:
    """Saved scripts are reachable via project-scoped artifact queries, no workspace path (AC3).

    Proves: load_scripts() round-trips the content; storage_path is under
    projects/{project_id}/test_scripts/; a different project's adapter returns [].
    Every kind='playwright_script' artifact is approved by construction (save_script
    runs only in the approve path — noted for Story 15.1 which will query it directly).
    """
    session, engine, service, adapter, other_adapter, project = _make_test_db_session(tmp_path)
    try:
        adapter.save_script("test_login.py", "# approved playwright script")

        # load_scripts() returns the artifact (project-scoped, no workspace path)
        scripts = adapter.load_scripts()
        assert len(scripts) == 1
        assert scripts[0].name == "test_login.py"
        assert "# approved playwright script" in scripts[0].content

        # storage_path is under projects/{project_id}/test_scripts/ — never workspace/
        artifact_rows = service.list_artifacts(project_id=project.id, kind="playwright_script")
        assert len(artifact_rows) == 1
        artifact = artifact_rows[0]
        assert artifact.storage_path.startswith(f"projects/{project.id}/test_scripts/")
        assert "workspace" not in artifact.storage_path

        # Content is readable through read_current_content
        content = service.read_current_content(artifact).decode("utf-8")
        assert "# approved playwright script" in content

        # Project isolation: a different project's adapter returns nothing
        assert other_adapter.load_scripts() == []
    finally:
        session.close()
    engine.dispose()


def test_save_script_different_names_kept_separately(tmp_path) -> None:
    """Two scripts with different names both persist — idempotency applies per-name only."""
    session, engine, service, adapter, _other_adapter, project = _make_test_db_session(tmp_path)
    try:
        adapter.save_script("test_login.py", "# login script")
        adapter.save_script("test_search.py", "# search script")

        all_scripts = service.list_artifacts(project_id=project.id, kind="playwright_script")
        assert len(all_scripts) == 2
        names = {a.name for a in all_scripts}
        assert names == {"test_login.py", "test_search.py"}
    finally:
        session.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# Story 14.1: load_approved_scripts (thread-prioritized, no discriminator)
# ---------------------------------------------------------------------------


def test_load_approved_scripts_returns_all_script_kind(tmp_path) -> None:
    """load_approved_scripts returns every playwright_script artifact (no discriminator)."""
    session, engine, service, adapter, _other_adapter, _project = _make_test_db_session(tmp_path)
    try:
        adapter.save_script("test_a.py", "# script a")
        adapter.save_script("test_b.py", "# script b")

        results = adapter.load_approved_scripts()
        assert len(results) == 2
        names = {r.name for r in results}
        assert names == {"test_a.py", "test_b.py"}
        assert all(r.kind == "playwright_script" for r in results)
    finally:
        session.close()
    engine.dispose()


def test_load_approved_scripts_project_isolation(tmp_path) -> None:
    """load_approved_scripts is project-scoped: a different project returns []."""
    session, engine, service, adapter, other_adapter, _project = _make_test_db_session(tmp_path)
    try:
        adapter.save_script("test_only_main.py", "# only in main project")
        assert other_adapter.load_approved_scripts() == []
    finally:
        session.close()
    engine.dispose()


def test_load_approved_scripts_thread_prioritization(tmp_path) -> None:
    """load_approved_scripts lists current-thread scripts first (stable sort)."""
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
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        user = User(
            email="scripts@example.com",
            display_name="scripts-user",
            password_hash="hash",
            role="standard",
            is_active=True,
        )
        project = Project(name="ScriptThreadTest", created_by_user=user)
        session.add_all([user, project])
        session.commit()

        thread_a = Thread(project_id=project.id, user_id=user.id)
        thread_b = Thread(project_id=project.id, user_id=user.id)
        session.add_all([thread_a, thread_b])
        session.flush()
        run_a = AgentRun(thread_id=thread_a.id, status="running")
        run_b = AgentRun(thread_id=thread_b.id, status="running")
        session.add_all([run_a, run_b])
        session.commit()

        service = ArtifactService(session, LocalArtifactStorage(root=tmp_path))

        adapter_b = PipelineArtifactAdapter(
            PipelineContext(
                project_id=project.id,
                user_id=user.id,
                user_email=user.email,
                artifact_service=service,
                agent_run_id=run_b.id,
                thread_id=thread_b.id,
            )
        )
        adapter_b.save_script("test_other_1.py", "# other 1")
        adapter_b.save_script("test_other_2.py", "# other 2")

        adapter_a = PipelineArtifactAdapter(
            PipelineContext(
                project_id=project.id,
                user_id=user.id,
                user_email=user.email,
                artifact_service=service,
                agent_run_id=run_a.id,
                thread_id=thread_a.id,
            )
        )
        adapter_a.save_script("test_current.py", "# current thread")

        results = adapter_a.load_approved_scripts()
        assert len(results) == 3
        assert results[0].name == "test_current.py", "Current-thread script must be first"
        other_names = {r.name for r in results[1:]}
        assert other_names == {"test_other_1.py", "test_other_2.py"}
    finally:
        session.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# Story 14.3: save_execution_output / persist_run_outputs
# ---------------------------------------------------------------------------


def _short_storage_adapter(adapter):
    """Adapter sharing the DB session but with a SHORT local storage root.

    The nested execution path ``runs/{run_id}/{file}`` + the per-artifact UUID + temp
    suffix can exceed the Windows 260-char MAX_PATH inside pytest's deep tmp dir. Using
    a short ``tempfile.mkdtemp`` root keeps the local backend under the limit. (Production
    uses S3/SeaweedFS, which has no such limit.)
    """
    import tempfile

    short_root = tempfile.mkdtemp(prefix="x")
    ctx = adapter.context
    short_service = ArtifactService(ctx.artifact_service.db, LocalArtifactStorage(root=short_root))
    short_ctx = PipelineContext(
        project_id=ctx.project_id,
        user_id=ctx.user_id,
        user_email=ctx.user_email,
        artifact_service=short_service,
        agent_run_id=ctx.agent_run_id,
        thread_id=ctx.thread_id,
    )
    return PipelineArtifactAdapter(short_ctx), short_root


def test_save_execution_output_writes_under_run_prefix(tmp_path) -> None:
    """Outputs are named '{prefix}/{run_id}/{file}' with the right kind; binary round-trips."""
    import shutil

    session, engine, _service, adapter, _other, _project = _make_test_db_session(tmp_path)
    exec_adapter, short_root = _short_storage_adapter(adapter)
    try:
        run_id = exec_adapter.context.agent_run_id
        assert run_id is not None

        report = exec_adapter.save_execution_output(
            run_id=run_id, file_name="report.md", content="# Report", kind="report"
        )
        assert report.name == f"runs/{run_id}/report.md"
        assert report.kind == "report"
        assert exec_adapter.service.read_current_content(report).decode("utf-8") == "# Report"

        png_bytes = b"\x89PNG\r\n\x1a\nFAKE"
        shot = exec_adapter.save_execution_output(
            run_id=run_id,
            file_name="test__chromium.png",
            content=png_bytes,
            kind="execution_screenshot",
        )
        assert shot.kind == "execution_screenshot"
        assert exec_adapter.service.read_current_content(shot) == png_bytes
    finally:
        session.close()
        shutil.rmtree(short_root, ignore_errors=True)
    engine.dispose()


def test_persist_run_outputs_uniqueness_and_overwrite(tmp_path) -> None:
    """Two run ids never collide; same run id + overwrite=False raises, overwrite=True allows."""
    import shutil

    import pytest as _pytest

    session, engine, _service, adapter, _other, project = _make_test_db_session(tmp_path)
    exec_adapter, short_root = _short_storage_adapter(adapter)
    try:
        run1 = exec_adapter.context.agent_run_id
        assert run1 is not None

        ids = exec_adapter.persist_run_outputs(
            run_id=run1,
            files=[("report.md", "# R", "report"), ("run.log", "log text", "log")],
        )
        assert len(ids) == 2

        # Same run id again with overwrite disabled → guard raises.
        with _pytest.raises(ValueError, match="already exist"):
            exec_adapter.persist_run_outputs(run_id=run1, files=[("report.md", "# R2", "report")])

        # overwrite=True allows re-persist.
        more = exec_adapter.persist_run_outputs(
            run_id=run1, files=[("extra.log", "x", "log")], overwrite=True
        )
        assert len(more) == 1

        # A second run id writes to a distinct folder (no collision).
        thread2 = Thread(project_id=project.id, user_id=exec_adapter.context.user_id)
        session.add(thread2)
        session.flush()
        run2 = AgentRun(thread_id=thread2.id, status="running")
        session.add(run2)
        session.commit()
        ids2 = exec_adapter.persist_run_outputs(
            run_id=run2.id, files=[("report.md", "# R", "report")]
        )
        assert len(ids2) == 1
    finally:
        session.close()
        shutil.rmtree(short_root, ignore_errors=True)
    engine.dispose()
