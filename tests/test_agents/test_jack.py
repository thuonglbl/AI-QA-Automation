"""Tests for Jack agent - Test Execution input-selection gate (Story 14.1).

Mirrors the Sarah input-selection test scaffold:
- patch ``ai_qa.agents.jack.PipelineArtifactAdapter`` at the class boundary
- use ``mock_project_context`` (conftest) + ``mock_broadcast``
- drive AC2/AC3 via ``mock_adapter.load_approved_scripts.return_value``
"""

from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.agents.base import AgentState
from ai_qa.agents.jack import JackAgent, _merge_run_results
from ai_qa.artifacts.service import ArtifactService
from ai_qa.artifacts.storage import LocalArtifactStorage
from ai_qa.db.base import Base
from ai_qa.db.models import Artifact, ArtifactVersion, Project, TestExecutionResult, User
from ai_qa.pipelines.artifact_adapter import PipelineArtifact
from ai_qa.pipelines.context import PipelineContext
from ai_qa.pipelines.script_runner import ProducedFile, RunResult, RunSummary, TestResult
from ai_qa.threads.models import AgentRun, Thread


@pytest.fixture
def mock_broadcast():
    """Patch broadcast_message with an AsyncMock for the entire test."""
    with patch("ai_qa.api.websocket.broadcast_message", new_callable=AsyncMock) as mock:
        yield mock


def _make_script(name: str, thread_id, content: str = "def test_x():\n    pass") -> MagicMock:
    art = MagicMock(spec=PipelineArtifact)
    art.id = uuid4()
    art.name = name
    art.kind = "playwright_script"
    art.thread_id = thread_id
    art.content = content
    return art


class TestJackAgentInit:
    """Jack constructs with all-default args and no LLM."""

    def test_init_defaults(self, tmp_path: Path) -> None:
        agent = JackAgent(workspace_dir=tmp_path)
        assert agent.name == "Jack"
        assert agent.step_number == 5
        assert agent.color == "#F97316"
        assert agent.phase == "input_selection"
        assert agent.candidate_scripts == []
        assert agent.confirmed_scripts == []

    def test_check_preconditions_blocks_without_context(self, tmp_path: Path) -> None:
        agent = JackAgent(workspace_dir=tmp_path)
        agent.project_context = None
        blockers = agent._check_preconditions()
        assert blockers
        assert "active project thread" in blockers[0]

    def test_check_preconditions_blocks_without_artifact_service(self, tmp_path: Path) -> None:
        agent = JackAgent(workspace_dir=tmp_path)
        ctx = MagicMock()
        ctx.project_id = uuid4()
        ctx.user_id = "user-1"
        ctx.thread_id = uuid4()
        ctx.artifact_service = None
        agent.project_context = ctx
        blockers = agent._check_preconditions()
        assert blockers
        assert "storage service" in blockers[0]


class TestJackAgentHandleStart:
    """handle_start input-selection gate (AC1/AC2/AC3)."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch("ai_qa.agents.jack.PipelineArtifactAdapter") as mock_adapter_class:
            self.mock_adapter = MagicMock()
            self.mock_adapter.load_metadata.return_value = None
            mock_adapter_class.return_value = self.mock_adapter
            yield mock_adapter_class

    @pytest.mark.asyncio
    async def test_handle_start_blocks_when_no_approved_scripts(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """AC3: no approved scripts → error message, stays START, no REVIEW_REQUEST."""
        self.mock_adapter.load_approved_scripts.return_value = []

        agent = JackAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        await agent.handle_start({})

        assert agent.state == AgentState.START
        messages = [call[0][0].content for call in mock_broadcast.call_args_list]
        assert any("approved test scripts" in m.lower() or "Sarah" in m for m in messages)
        # No script_selection payload was emitted.
        assert not any(
            call[0][0].metadata and call[0][0].metadata.get("type") == "script_selection"
            for call in mock_broadcast.call_args_list
        )

    @pytest.mark.asyncio
    async def test_handle_start_presents_selection_when_scripts_available(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """AC2: approved scripts → script_selection payload + REVIEW_REQUEST."""
        current = _make_script("test_current.py", mock_project_context.thread_id)
        other = _make_script("test_other.py", uuid4())
        self.mock_adapter.load_approved_scripts.return_value = [current, other]

        agent = JackAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        await agent.handle_start({})

        assert agent.state == AgentState.REVIEW_REQUEST
        selection_calls = [
            call[0][0]
            for call in mock_broadcast.call_args_list
            if call[0][0].metadata and call[0][0].metadata.get("type") == "script_selection"
        ]
        assert len(selection_calls) == 1
        entries = selection_calls[0].metadata["scripts"]
        assert len(entries) == 2
        # First entry is the current-thread script: pre-selected + badge.
        assert entries[0]["name"] == "test_current.py"
        assert entries[0]["from_current_thread"] is True
        assert entries[0]["default_selected"] is True
        assert entries[0]["title"] == "test_current"
        assert "def test_x" in entries[0]["preview"]
        # Other-thread script: not pre-selected (since some are from this thread).
        assert entries[1]["from_current_thread"] is False
        assert entries[1]["default_selected"] is False

    @pytest.mark.asyncio
    async def test_handle_start_preselects_all_when_none_from_thread(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """When no script is from the current thread, all are pre-selected."""
        a = _make_script("test_a.py", uuid4())
        b = _make_script("test_b.py", uuid4())
        self.mock_adapter.load_approved_scripts.return_value = [a, b]

        agent = JackAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        await agent.handle_start({})

        selection_calls = [
            call[0][0]
            for call in mock_broadcast.call_args_list
            if call[0][0].metadata and call[0][0].metadata.get("type") == "script_selection"
        ]
        entries = selection_calls[0].metadata["scripts"]
        assert all(e["default_selected"] is True for e in entries)
        assert all(e["from_current_thread"] is False for e in entries)

    @pytest.mark.asyncio
    async def test_selection_payload_carries_roles_and_sessions(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """14.4: the script_selection payload includes app_roles + captured sessions."""
        a = _make_script("test_a.py", None)
        self.mock_adapter.load_approved_scripts.return_value = [a]

        agent = JackAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        await agent.handle_start({})

        selection = next(
            c[0][0].metadata
            for c in mock_broadcast.call_args_list
            if c[0][0].metadata and c[0][0].metadata.get("type") == "script_selection"
        )
        assert "app_roles" in selection
        assert "sessions" in selection
        assert "environments" in selection


def _canned_run_result() -> RunResult:
    """A RunResult with one pass + one failure (for agent persistence tests)."""
    results = [
        TestResult(test_name="test_login", browser="chromium", status="passed", duration_ms=120),
        TestResult(
            test_name="test_search",
            browser="chromium",
            status="failed",
            duration_ms=300,
            error_message="AssertionError",
            stack_trace="expect(...).to_be_visible failed",
            failure_classification="assertion",
        ),
    ]
    summary = RunSummary(
        total=2,
        passed=1,
        failed=1,
        errors=0,
        skipped=0,
        duration_ms=420,
        browsers=["chromium"],
        base_url_host="app.example.com",
        run_policy="continue",
        started_at="2026-06-21T00:00:00+00:00",
        completed_at="2026-06-21T00:00:01+00:00",
    )
    return RunResult(results=results, summary=summary, produced_files=[])


_CONFIRM_BASE = {
    "action": "confirm_inputs",
    "target_url": "https://app.example.com",
    "environment": "Production",
    "role": "Admin",
    "browsers": ["chromium"],
}


class TestJackAgentConfirmInputs:
    """handle_approve → _confirm_inputs → _begin_execution (14.2 runner, 14.4 auth)."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with (
            patch("ai_qa.agents.jack.PipelineArtifactAdapter") as mock_adapter_class,
            patch(
                "ai_qa.agents.jack.resolve_storage_state", return_value={"cookies": []}
            ) as mock_session,
        ):
            self.mock_adapter = MagicMock()
            self.mock_adapter.load_metadata.return_value = None
            mock_adapter_class.return_value = self.mock_adapter
            self.mock_session = mock_session
            yield mock_adapter_class

    @pytest.mark.asyncio
    async def test_confirm_with_url_runs_persists_and_reviews(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """confirm + URL + session → runs the runner, persists rows, lands REVIEW_REQUEST."""
        a = _make_script("test_a.py", None)
        b = _make_script("test_b.py", None)
        self.mock_adapter.load_approved_scripts.return_value = [a, b]
        db = mock_project_context.artifact_service.db

        agent = JackAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        await agent.handle_start({})

        with patch("ai_qa.agents.jack.run_scripts", return_value=_canned_run_result()) as runner:
            await agent.handle_approve(
                {**_CONFIRM_BASE, "selected_artifact_ids": [str(a.id), str(b.id)]}
            )

        runner.assert_called_once()
        assert runner.call_args.kwargs["base_url"] == "https://app.example.com"
        # AC3 (14.4): the resolved session blob is passed to the runner.
        assert runner.call_args.kwargs["storage_state"] == {"cookies": []}
        self.mock_session.assert_called_once()
        assert self.mock_session.call_args.kwargs["environment"] == "Production"
        assert self.mock_session.call_args.kwargs["role"] == "Admin"
        assert agent.state == AgentState.REVIEW_REQUEST
        # The live credential is cleared after the run (secret containment).
        assert agent._storage_state is None
        # Persisted one row per test result (2) + AgentRun summary committed.
        added = [c.args[0] for c in db.add.call_args_list]
        assert len(added) == 2
        assert all(isinstance(row, TestExecutionResult) for row in added)
        assert db.commit.called
        summaries = [
            c[0][0]
            for c in mock_broadcast.call_args_list
            if c[0][0].metadata and c[0][0].metadata.get("type") == "execution_summary"
        ]
        assert len(summaries) == 1
        assert summaries[0].metadata["total"] == 2
        assert summaries[0].metadata["browsers"] == ["chromium"]

    @pytest.mark.asyncio
    async def test_confirm_composes_and_persists_report(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """14.5: after a run, Jack composes + persists report.md + report.json and links it."""
        a = _make_script("test_a.py", None)
        self.mock_adapter.load_approved_scripts.return_value = [a]

        agent = JackAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        await agent.handle_start({})

        with patch("ai_qa.agents.jack.run_scripts", return_value=_canned_run_result()):
            await agent.handle_approve({**_CONFIRM_BASE, "selected_artifact_ids": [str(a.id)]})

        kinds = [
            c.kwargs.get("kind") for c in self.mock_adapter.save_execution_output.call_args_list
        ]
        assert "report" in kinds  # visible report.md
        assert "configuration" in kinds  # hidden report.json companion
        names = [
            c.kwargs.get("file_name")
            for c in self.mock_adapter.save_execution_output.call_args_list
        ]
        assert "report.md" in names
        assert "report.json" in names
        summary = next(
            c[0][0].metadata
            for c in mock_broadcast.call_args_list
            if c[0][0].metadata and c[0][0].metadata.get("type") == "execution_summary"
        )
        assert summary["report_artifact_id"] is not None

    @pytest.mark.asyncio
    async def test_confirm_no_session_hard_blocks(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """14.4 AC3: no captured session for (env, role) → hard-block, runner NOT called."""
        a = _make_script("test_a.py", None)
        self.mock_adapter.load_approved_scripts.return_value = [a]
        self.mock_session.return_value = None  # no session captured

        agent = JackAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        await agent.handle_start({})

        with patch("ai_qa.agents.jack.run_scripts") as runner:
            await agent.handle_approve({**_CONFIRM_BASE, "selected_artifact_ids": [str(a.id)]})

        runner.assert_not_called()
        assert agent.state != AgentState.PROCESSING
        assert agent.confirmed_scripts == []
        messages = [c[0][0].content for c in mock_broadcast.call_args_list]
        assert any("captured session" in m for m in messages)

    @pytest.mark.asyncio
    async def test_confirm_without_url_blocks_no_subprocess(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """AC1: no target URL → UX-DR12 block, runner NOT called, stays in gate."""
        a = _make_script("test_a.py", None)
        self.mock_adapter.load_approved_scripts.return_value = [a]

        agent = JackAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        await agent.handle_start({})

        with patch("ai_qa.agents.jack.run_scripts") as runner:
            await agent.handle_approve(
                {"action": "confirm_inputs", "selected_artifact_ids": [str(a.id)]}
            )

        runner.assert_not_called()
        assert agent.state != AgentState.PROCESSING
        messages = [c[0][0].content for c in mock_broadcast.call_args_list]
        assert any("target environment URL" in m for m in messages)

    @pytest.mark.asyncio
    async def test_confirm_empty_selection_warns_and_re_presents(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """An empty (but explicit) selection is rejected — warn + re-present, no run."""
        a = _make_script("test_a.py", None)
        self.mock_adapter.load_approved_scripts.return_value = [a]

        agent = JackAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        await agent.handle_start({})
        mock_broadcast.reset_mock()

        with patch("ai_qa.agents.jack.run_scripts") as runner:
            await agent.handle_approve(
                {
                    "action": "confirm_inputs",
                    "selected_artifact_ids": ["does-not-exist"],
                    "target_url": "https://app.example.com",
                }
            )

        runner.assert_not_called()
        assert agent.confirmed_scripts == []
        messages = [c[0][0].content for c in mock_broadcast.call_args_list]
        assert any("at least one script" in m for m in messages)

    @pytest.mark.asyncio
    async def test_confirm_empty_selection_selects_all_candidates(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """Omitting selected_artifact_ids runs ALL candidate scripts (the select-all default)."""
        a = _make_script("test_a.py", None)
        b = _make_script("test_b.py", None)
        self.mock_adapter.load_approved_scripts.return_value = [a, b]

        agent = JackAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        await agent.handle_start({})

        with patch("ai_qa.agents.jack.run_scripts", return_value=_canned_run_result()) as runner:
            # No selected_artifact_ids key at all → falls back to every candidate.
            await agent.handle_approve({**_CONFIRM_BASE})

        runner.assert_called_once()
        assert {s.name for s in agent.confirmed_scripts} == {"test_a.py", "test_b.py"}

    @pytest.mark.asyncio
    async def test_reject_resets_state_and_re_presents_without_running(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """Reject re-presents the selection gate; it must NOT re-run scripts (unauthenticated)."""
        a = _make_script("test_a.py", None)
        self.mock_adapter.load_approved_scripts.return_value = [a]

        agent = JackAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        await agent.handle_start({})
        with patch("ai_qa.agents.jack.run_scripts", return_value=_canned_run_result()):
            await agent.handle_approve({**_CONFIRM_BASE, "selected_artifact_ids": [str(a.id)]})

        with patch("ai_qa.agents.jack.run_scripts") as runner:
            await agent.handle_reject("redo it", {})

        runner.assert_not_called()
        assert agent.confirmed_scripts == []
        assert agent._target_url is None
        assert agent.state == AgentState.REVIEW_REQUEST

    @pytest.mark.asyncio
    async def test_confirm_persists_produced_outputs_via_adapter(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """14.3: runner-produced files are persisted through the adapter (capture toggles on)."""
        a = _make_script("test_a.py", None)
        self.mock_adapter.load_approved_scripts.return_value = [a]

        canned = _canned_run_result()
        canned.produced_files = [
            ProducedFile(name="run.log", content=b"log text", kind="log"),
            ProducedFile(name="test__chromium.png", content=b"PNG", kind="execution_screenshot"),
        ]

        agent = JackAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        await agent.handle_start({})

        with patch("ai_qa.agents.jack.run_scripts", return_value=canned):
            await agent.handle_approve({**_CONFIRM_BASE, "selected_artifact_ids": [str(a.id)]})

        self.mock_adapter.persist_run_outputs.assert_called_once()
        kwargs = self.mock_adapter.persist_run_outputs.call_args.kwargs
        kinds = {kind for (_n, _c, kind) in kwargs["files"]}
        assert kinds == {"log", "execution_screenshot"}


class TestMergeRunResults:
    """_merge_run_results: combine per-role-group RunResults into one."""

    @staticmethod
    def _group(role: str, browser: str, status: str, started: str, completed: str) -> RunResult:
        return RunResult(
            results=[TestResult(test_name=f"t_{role}", browser=browser, status=status, role=role)],
            summary=RunSummary(
                total=1,
                passed=1 if status == "passed" else 0,
                failed=1 if status == "failed" else 0,
                errors=0,
                skipped=0,
                duration_ms=10,
                browsers=[browser],
                base_url_host="app.example.com",
                run_policy="continue",
                started_at=started,
                completed_at=completed,
            ),
            produced_files=[ProducedFile(name=f"{role}__run.log", content=b"x", kind="log")],
        )

    def test_single_group_passes_through(self) -> None:
        g = self._group("Admin", "chromium", "passed", "t0", "t1")
        assert _merge_run_results([g]) is g

    def test_multi_group_sums_and_unions(self) -> None:
        g1 = self._group(
            "Admin", "chromium", "passed", "2026-06-21T00:00:00+00:00", "2026-06-21T00:00:01+00:00"
        )
        g2 = self._group(
            "User", "firefox", "failed", "2026-06-21T00:00:02+00:00", "2026-06-21T00:00:05+00:00"
        )
        merged = _merge_run_results([g1, g2])
        assert merged.summary.total == 2
        assert merged.summary.passed == 1
        assert merged.summary.failed == 1
        assert merged.summary.browsers == ["chromium", "firefox"]
        assert merged.summary.started_at == "2026-06-21T00:00:00+00:00"
        assert merged.summary.completed_at == "2026-06-21T00:00:05+00:00"
        assert [r.role for r in merged.results] == ["Admin", "User"]
        assert len(merged.produced_files) == 2


class TestJackRoleGroupedRuns:
    """Slice 6: scripts run grouped by their role, each under that role's captured session."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with (
            patch("ai_qa.agents.jack.PipelineArtifactAdapter") as mock_adapter_class,
            patch("ai_qa.agents.jack.resolve_storage_state") as mock_session,
        ):
            self.mock_adapter = MagicMock()
            mock_adapter_class.return_value = self.mock_adapter
            self.mock_session = mock_session
            yield mock_adapter_class

    @staticmethod
    def _meta_for(name: str):
        """Side-car role keyed by the script's <role>/ folder prefix (Slice 5 layout)."""
        if name.startswith("Admin/"):
            return {"role": "Admin"}
        if name.startswith("User/"):
            return {"role": "User"}
        return None

    @staticmethod
    def _group_run_result(scripts) -> RunResult:
        """A fresh RunResult with one passed test per script in the group."""
        results = [
            TestResult(
                test_name=s.name,
                browser="chromium",
                status="passed",
                duration_ms=10,
                source_artifact_id=s.source_artifact_id,
            )
            for s in scripts
        ]
        return RunResult(
            results=results,
            summary=RunSummary(
                total=len(results),
                passed=len(results),
                failed=0,
                errors=0,
                skipped=0,
                duration_ms=10,
                browsers=["chromium"],
                base_url_host="app.example.com",
                run_policy="continue",
                started_at="2026-06-21T00:00:00+00:00",
                completed_at="2026-06-21T00:00:01+00:00",
            ),
            produced_files=[],
        )

    @pytest.mark.asyncio
    async def test_runs_each_role_with_its_own_session(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        a = _make_script("Admin/test_a.py", None)
        b = _make_script("User/test_b.py", None)
        self.mock_adapter.load_approved_scripts.return_value = [a, b]
        self.mock_adapter.load_metadata.side_effect = self._meta_for
        # Each role has its own captured session blob (tagged so we can verify routing).
        self.mock_session.side_effect = lambda *a, **kw: {"cookies": [], "role": kw["role"]}
        db = mock_project_context.artifact_service.db

        agent = JackAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        await agent.handle_start({})

        runner_calls: list[dict] = []

        def _runner(**kw):
            runner_calls.append(kw)
            return self._group_run_result(kw["scripts"])

        with patch("ai_qa.agents.jack.run_scripts", side_effect=_runner):
            await agent.handle_approve(
                {**_CONFIRM_BASE, "selected_artifact_ids": [str(a.id), str(b.id)]}
            )

        # One run_scripts invocation per role group, each with ONLY its role's scripts + session.
        assert len(runner_calls) == 2
        routed = {c["storage_state"]["role"]: [s.name for s in c["scripts"]] for c in runner_calls}
        assert routed == {"Admin": ["Admin/test_a.py"], "User": ["User/test_b.py"]}
        assert {c.kwargs["role"] for c in self.mock_session.call_args_list} == {"Admin", "User"}

        # Persisted rows carry the per-script role.
        added = [c.args[0] for c in db.add.call_args_list]
        assert {row.role for row in added} == {"Admin", "User"}

        summary = next(
            c[0][0].metadata
            for c in mock_broadcast.call_args_list
            if c[0][0].metadata and c[0][0].metadata.get("type") == "execution_summary"
        )
        assert sorted(summary["roles"]) == ["Admin", "User"]
        assert summary["total"] == 2
        # Live credentials cleared after the run (secret containment).
        assert agent._role_sessions == {}
        assert agent._run_plan == []

    @pytest.mark.asyncio
    async def test_blocks_when_one_role_has_no_session(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        a = _make_script("Admin/test_a.py", None)
        b = _make_script("User/test_b.py", None)
        self.mock_adapter.load_approved_scripts.return_value = [a, b]
        self.mock_adapter.load_metadata.side_effect = self._meta_for
        # Admin has a session; User does not → the whole run must be blocked.
        self.mock_session.side_effect = lambda *a, **kw: (
            {"cookies": []} if kw["role"] == "Admin" else None
        )

        agent = JackAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        await agent.handle_start({})

        with patch("ai_qa.agents.jack.run_scripts") as runner:
            await agent.handle_approve(
                {**_CONFIRM_BASE, "selected_artifact_ids": [str(a.id), str(b.id)]}
            )

        runner.assert_not_called()
        assert agent.state != AgentState.PROCESSING
        assert agent.confirmed_scripts == []
        messages = [c[0][0].content for c in mock_broadcast.call_args_list]
        # The block names the missing role (User), not the one that has a session.
        assert any("captured session" in m and "User" in m for m in messages)

    @pytest.mark.asyncio
    async def test_roleless_scripts_stay_single_group(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """Back-compat: scripts with no side-car role → one group under the UI-selected role."""
        a = _make_script("test_a.py", None)
        b = _make_script("test_b.py", None)
        self.mock_adapter.load_approved_scripts.return_value = [a, b]
        self.mock_adapter.load_metadata.return_value = None  # no role on the side-car
        self.mock_session.return_value = {"cookies": []}

        agent = JackAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        await agent.handle_start({})

        with patch("ai_qa.agents.jack.run_scripts", side_effect=self._runner_capture()) as _runner:
            await agent.handle_approve(
                {**_CONFIRM_BASE, "selected_artifact_ids": [str(a.id), str(b.id)]}
            )

        # Exactly ONE run group (both scripts) and ONE session resolution (the UI role).
        assert _runner.call_count == 1
        assert self.mock_session.call_count == 1
        assert self.mock_session.call_args.kwargs["role"] == "Admin"

    def _runner_capture(self):
        def _runner(**kw):
            return self._group_run_result(kw["scripts"])

        return _runner


class TestJackAttachmentMatching:
    """Slice 6: report attachments match within a result's own role group (no cross-link)."""

    def test_match_attachment_prefers_role_group(self) -> None:
        admin_shot, user_shot = uuid4(), uuid4()
        records = [
            ("Admin__test_login_chromium.png", "execution_screenshot", admin_shot),
            ("User__test_login_chromium.png", "execution_screenshot", user_shot),
        ]
        # Same test name under two roles → each result links its OWN role's screenshot.
        assert JackAgent._match_attachment(
            records, "execution_screenshot", "test_login", "chromium", "Admin__"
        ) == str(admin_shot)
        assert JackAgent._match_attachment(
            records, "execution_screenshot", "test_login", "chromium", "User__"
        ) == str(user_shot)
        # No prefix (single-role / back-compat) → first match.
        assert JackAgent._match_attachment(
            records, "execution_screenshot", "test_login", "chromium"
        ) == str(admin_shot)

    def test_match_run_log_is_role_aware(self) -> None:
        admin_log, user_log = uuid4(), uuid4()
        records = [("Admin__run.log", "log", admin_log), ("User__run.log", "log", user_log)]
        assert JackAgent._match_run_log(records, "Admin__") == str(admin_log)
        assert JackAgent._match_run_log(records, "User__") == str(user_log)
        # Single-group run.log (no prefix) still resolves.
        single = uuid4()
        assert JackAgent._match_run_log([("run.log", "log", single)], "") == str(single)


class TestJackPersistenceRealDB:
    """_persist_results writes real TestExecutionResult rows + AgentRun summary."""

    def test_persist_results_creates_rows_and_summary(self, tmp_path: Path) -> None:
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
                    TestExecutionResult.__table__,
                ],
            ),
        )
        session = sessionmaker(bind=engine, expire_on_commit=False)()
        try:
            user = User(
                email="jack@example.com",
                display_name="jack-user",
                password_hash="hash",
                role="standard",
                is_active=True,
            )
            project = Project(name="JackProject", created_by_user=user)
            session.add_all([user, project])
            session.commit()
            thread = Thread(project_id=project.id, user_id=user.id)
            session.add(thread)
            session.flush()
            run = AgentRun(thread_id=thread.id, status="running")
            session.add(run)
            session.commit()

            service = ArtifactService(session, LocalArtifactStorage(root=tmp_path))
            ctx = PipelineContext(
                project_id=project.id,
                user_id=user.id,
                user_email=user.email,
                artifact_service=service,
                agent_run_id=run.id,
                thread_id=thread.id,
            )
            agent = JackAgent(workspace_dir=tmp_path)
            agent.project_context = ctx

            # source_artifact_id=None avoids needing a real artifact row for the FK.
            results = [
                TestResult("test_login", "chromium", "passed", duration_ms=100, role="Admin"),
                TestResult(
                    "test_search",
                    "chromium",
                    "failed",
                    duration_ms=200,
                    error_message="AssertionError",
                    failure_classification="assertion",
                    role="Admin",
                ),
            ]
            summary = RunSummary(
                total=2,
                passed=1,
                failed=1,
                errors=0,
                skipped=0,
                duration_ms=300,
                browsers=["chromium"],
                base_url_host="app.example.com",
                run_policy="continue",
                started_at="2026-06-21T00:00:00+00:00",
                completed_at="2026-06-21T00:00:01+00:00",
            )
            agent._persist_results(RunResult(results=results, summary=summary))

            rows = session.query(TestExecutionResult).all()
            assert len(rows) == 2
            assert {r.status for r in rows} == {"passed", "failed"}
            assert all(r.role == "Admin" for r in rows)  # Slice 6: per-result role persisted
            assert all(r.agent_run_id == run.id for r in rows)
            assert all(r.project_id == project.id for r in rows)
            refreshed = session.get(AgentRun, run.id)
            assert refreshed is not None
            assert refreshed.status == "completed"
            assert refreshed.execution_metadata is not None
            assert refreshed.execution_metadata["passed"] == 1
            assert refreshed.execution_metadata["base_url_host"] == "app.example.com"
        finally:
            session.close()
        engine.dispose()
