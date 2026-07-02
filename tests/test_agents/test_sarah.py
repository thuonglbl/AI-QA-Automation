"""Tests for Sarah agent - Generate Playwright Scripts with Side-by-Side Review.

Tests follow TDD pattern:
- RED: Write failing tests first
- GREEN: Implement minimal code to pass tests
- REFACTOR: Improve code structure while keeping tests green
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_qa.agents.base import AgentState
from ai_qa.models import StageResult, TestCase, TestCaseStep


@pytest.fixture
def sarah_agent(tmp_path: Path) -> Any:
    """Create Sarah agent instance with test workspace."""
    from ai_qa.agents.sarah import SarahAgent

    return SarahAgent(workspace_dir=tmp_path)


@pytest.fixture
def sample_test_cases() -> list[TestCase]:
    """Sample test cases for testing."""
    return [
        TestCase(
            title="Login with valid credentials",
            preconditions=["User is on login page"],
            steps=[
                TestCaseStep(
                    number=1, action="Enter username", target="#username", data="testuser"
                ),
                TestCaseStep(
                    number=2, action="Enter password", target="#password", data="testpass"
                ),
                TestCaseStep(number=3, action="Click login button", target="#login-btn"),
            ],
            expected_results=["User is redirected to dashboard"],
            automation_hints=["Use CSS selectors"],
        ),
        TestCase(
            title="Search functionality",
            preconditions=["User is logged in"],
            steps=[
                TestCaseStep(number=1, action="Click search box", target="#search"),
                TestCaseStep(number=2, action="Type query", target="#search", data="test"),
                TestCaseStep(number=3, action="Press Enter", target="#search"),
            ],
            expected_results=["Search results displayed"],
            automation_hints=["Wait for results"],
        ),
    ]


@pytest.fixture
def mock_broadcast():
    """Patch broadcast_message with an AsyncMock for the entire test."""
    with patch("ai_qa.api.websocket.broadcast_message", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture(autouse=True)
def _stub_sarah_llm_config():
    """Stop the lazy LLM-config resolve from reaching the mock DB in unit tests.

    Story 16-12 (the auth-bug fix) makes Sarah resolve its LLM config lazily via
    ``_ensure_llm_ready()`` / ``_build_explore_llm()`` instead of trusting the empty-key
    config captured at ``__init__``. The real api_key lives in the user's encrypted
    secret store, unreachable in unit tests; against the ``mock_project_context`` MagicMock
    DB ``get_llm_config`` would build an ``LLMConfig`` from a MagicMock secret and raise a
    ``ValidationError``. Stub it to return the SAME empty-key placeholder ``__init__``
    produces today (provider=claude, default model, api_key="") so the lazy resolve never
    raises and ``_build_explore_llm`` still returns ``None`` (empty key) — behaviour-
    preserving. Tests that need a resolved key (or a forced auth failure) override
    ``agent.get_llm_config`` on the instance, which shadows this class-level stub.
    """
    from ai_qa.agents.sarah import SarahAgent
    from ai_qa.ai_connection.config import LLMConfig

    placeholder = LLMConfig(provider="claude", model_name="claude-3-5-sonnet-20241022", api_key="")
    with patch.object(SarahAgent, "get_llm_config", return_value=placeholder):
        yield


# -----------------------------------------------------------------------------
# Initialization Tests
# -----------------------------------------------------------------------------


class TestSarahAgentInit:
    """Test Sarah agent initialization."""

    def test_sarah_agent_initialization(self, sarah_agent: Any, mock_project_context) -> None:
        """Test Sarah agent has correct identity properties."""
        assert sarah_agent.name == "Sarah"
        assert sarah_agent.color == "#8B5CF6"  # Purple
        assert sarah_agent.step_number == 4
        assert sarah_agent.step_title == "Generate Scripts"
        assert sarah_agent.state == AgentState.START

    def test_sarah_agent_has_empty_scripts_list(self, sarah_agent: Any) -> None:
        """Test Sarah agent initializes with empty scripts list."""
        assert hasattr(sarah_agent, "_generated_scripts")
        assert sarah_agent._generated_scripts == []

    def test_sarah_agent_has_review_index_at_zero(self, sarah_agent: Any) -> None:
        """Test Sarah agent initializes with review index at 0."""
        assert hasattr(sarah_agent, "_current_review_index")
        assert sarah_agent._current_review_index == 0

    def test_sarah_agent_has_chrome_path_storage(self, sarah_agent: Any) -> None:
        """Test Sarah agent has Chrome path storage."""
        assert hasattr(sarah_agent, "_chrome_path")


# -----------------------------------------------------------------------------
# Chrome Path (transient, per-run) Tests
# -----------------------------------------------------------------------------


class TestChromePathTransient:
    """The Chrome path is a transient per-run launch hint (no longer persisted)."""

    @pytest.mark.asyncio
    async def test_chrome_path_set_from_input_without_persistence(
        self, mock_project_context
    ) -> None:
        """A submitted Chrome path is kept transiently and never written to an artifact."""
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent()
        agent.project_context = mock_project_context
        assert not hasattr(agent, "_store_chrome_path")
        assert not hasattr(agent, "_load_chrome_path")


class TestSarahProjectEnvironments:
    """Sarah surfaces the project's configured environments for the inputs request."""

    def test_project_environments_reads_and_filters(self, mock_project_context) -> None:
        from types import SimpleNamespace

        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent()
        agent.project_context = mock_project_context
        mock_project_context.artifact_service.db.get.return_value = SimpleNamespace(
            environments=[
                {"name": "Test 1", "url": "https://t1.app"},
                {"name": "bad"},  # missing url → dropped
                {"url": "https://nope.app"},  # missing name → dropped
            ],
        )
        assert agent._project_environments() == [
            {"name": "Test 1", "url": "https://t1.app", "login_type": "standard"}
        ]

    def test_project_environments_empty_when_none(self, mock_project_context) -> None:
        """A project with no environments column (mock returns no list) yields []."""
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent()
        agent.project_context = mock_project_context
        # db.get returns a MagicMock whose .environments is not a list → guarded to [].
        assert agent._project_environments() == []


# -----------------------------------------------------------------------------
# Tier-1 server-side explore — captured-session resolution
# -----------------------------------------------------------------------------


class TestSarahResolveExploreModel:
    """Sarah drives the browser-use explore with the project's VISION model (Bob's pick),
    while code generation keeps its own (coding) model."""

    def _agent(self, mock_project_context) -> Any:
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent()
        agent.project_context = mock_project_context
        return agent

    def _set_bob_model(self, mock_project_context, model: str | None) -> None:
        from types import SimpleNamespace

        agent_configs = {"bob": {"model": model}} if model else {}
        db = mock_project_context.artifact_service.db
        # The shared fixture wires db.get via side_effect (returns a fixed Thread);
        # clear it so this test's return_value (with the bob model we want) takes effect.
        db.get.side_effect = None
        db.get.return_value = SimpleNamespace(agent_configs=agent_configs)

    def test_uses_bobs_vision_model_with_vision_on(self, mock_project_context) -> None:
        agent = self._agent(mock_project_context)
        self._set_bob_model(mock_project_context, "inference-qwen3-vl-235b")
        model, use_vision = agent._resolve_explore_model("glm-5.1")
        assert model == "inference-qwen3-vl-235b"
        assert use_vision is True

    def test_falls_back_to_codegen_dom_only_when_no_vision_model(
        self, mock_project_context
    ) -> None:
        # Degraded pool: even Bob got a text-only model → run DOM-only, never send images.
        agent = self._agent(mock_project_context)
        self._set_bob_model(mock_project_context, "glm-5.1")
        model, use_vision = agent._resolve_explore_model("glm-5.1")
        assert model == "glm-5.1"
        assert use_vision is False

    def test_honours_codegen_model_when_it_is_itself_vision(self, mock_project_context) -> None:
        agent = self._agent(mock_project_context)
        self._set_bob_model(mock_project_context, None)  # no Bob config to borrow
        model, use_vision = agent._resolve_explore_model("pixtral-large")
        assert model == "pixtral-large"
        assert use_vision is True

    def _set_agent_configs(self, mock_project_context, configs: dict[str, dict]) -> None:
        from types import SimpleNamespace

        db = mock_project_context.artifact_service.db
        db.get.side_effect = None
        db.get.return_value = SimpleNamespace(agent_configs=configs)

    def test_explicit_sarah_explore_slot_takes_precedence_over_bob(
        self, mock_project_context
    ) -> None:
        # Alice now assigns Sarah a dedicated explore model; it wins over Bob's pick.
        agent = self._agent(mock_project_context)
        self._set_agent_configs(
            mock_project_context,
            {
                "bob": {"model": "inference-qwen3-vl-235b"},
                "sarah_explore": {"model": "inference-glm-5.1v-754b"},
            },
        )
        model, use_vision = agent._resolve_explore_model("glm-5.1")
        assert model == "inference-glm-5.1v-754b"
        assert use_vision is True

    def test_explicit_sarah_explore_override_to_text_model_runs_dom_only(
        self, mock_project_context
    ) -> None:
        # A user override of the explore slot is honoured even if it's text-only — but vision
        # is turned OFF (DOM-only) so browser-use never sends images a blind model can't read.
        agent = self._agent(mock_project_context)
        self._set_agent_configs(
            mock_project_context, {"sarah_explore": {"model": "inference-deepseek-v32"}}
        )
        model, use_vision = agent._resolve_explore_model("glm-5.1")
        assert model == "inference-deepseek-v32"
        assert use_vision is False


class TestSarahResolveRoleSessions:
    """Sarah resolves the user's captured sessions per involved role for server-side explore."""

    def _agent_with_env(
        self,
        mock_project_context,
        target_url: str = "https://t1.app",
        environment: str | None = "Test 1",
    ) -> Any:
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent()
        agent.project_context = mock_project_context
        # The environment NAME is the authoritative session-resolve key — submitted from the
        # inputs form alongside the target URL (no URL→name matching anymore).
        agent._target_url = target_url
        agent._environment = environment
        return agent

    @pytest.mark.asyncio
    async def test_resolves_per_role_and_builds_blob_map(self, mock_project_context) -> None:
        agent = self._agent_with_env(mock_project_context)
        agent._test_cases = [
            TestCase(title="Admin flow", role="Admin"),
            TestCase(title="User flow", role="User"),
            TestCase(title="Another admin flow", role="Admin"),  # duplicate role
        ]
        admin_blob = {"cookies": [{"name": "sid", "value": "admin"}]}

        async def fake_resolve(
            db,
            *,
            user_id,
            project_id,
            environment,
            role,
            chrome_path,
            llm,
            timeout,
            raise_on_failure=False,
        ):
            assert environment == "Test 1"  # the submitted env NAME, used directly
            return admin_blob if role == "Admin" else None  # User has no captured session

        with patch(
            "ai_qa.sessions.auto_login.resolve_or_generate_storage_state",
            new_callable=AsyncMock,
            side_effect=fake_resolve,
        ) as mock_resolve:
            result = await agent._resolve_role_sessions()

        # Called once per DISTINCT involved role.
        assert {c.kwargs["role"] for c in mock_resolve.call_args_list} == {"Admin", "User"}
        # Roles with no session are skipped.
        assert result == {"Admin": admin_blob}

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_environment_submitted(self, mock_project_context) -> None:
        """No env NAME (e.g. free-text URL path) → no session resolve, falls back to LLM-only."""
        agent = self._agent_with_env(mock_project_context, environment=None)
        agent._test_cases = [TestCase(title="Admin flow", role="Admin")]
        with patch(
            "ai_qa.sessions.auto_login.resolve_or_generate_storage_state", new_callable=AsyncMock
        ) as mock_resolve:
            result = await agent._resolve_role_sessions()
        assert result == {}
        mock_resolve.assert_not_called()  # no environment -> never query the session store

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_roles(self, mock_project_context) -> None:
        agent = self._agent_with_env(mock_project_context)
        agent._test_cases = [TestCase(title="Roleless")]  # role is None
        with patch(
            "ai_qa.sessions.auto_login.resolve_or_generate_storage_state", new_callable=AsyncMock
        ) as mock_resolve:
            result = await agent._resolve_role_sessions()
        assert result == {}
        mock_resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_empty_without_target_url(self, mock_project_context) -> None:
        agent = self._agent_with_env(mock_project_context, target_url="")
        agent._test_cases = [TestCase(title="Admin flow", role="Admin")]
        with patch(
            "ai_qa.sessions.auto_login.resolve_or_generate_storage_state", new_callable=AsyncMock
        ) as mock_resolve:
            result = await agent._resolve_role_sessions()
        assert result == {}
        mock_resolve.assert_not_called()

    async def test_generate_scripts_passes_role_sessions_to_generator(
        self, mock_project_context
    ) -> None:
        """_generate_scripts wires the resolved role_sessions into the ScriptGenerator."""
        agent = self._agent_with_env(mock_project_context)
        agent._test_cases = [TestCase(title="Admin flow", role="Admin")]
        agent._test_case_source_ids = [None]
        admin_blob = {"cookies": []}

        with (
            patch("ai_qa.agents.sarah.ScriptGenerator") as mock_generator_class,
            patch(
                "ai_qa.sessions.auto_login.resolve_or_generate_storage_state",
                new_callable=AsyncMock,
                return_value=admin_blob,
            ),
            patch.object(agent, "_build_explore_llm", return_value=object()),
            patch.object(agent, "send_message", new=AsyncMock()),
        ):
            mock_generator = MagicMock()
            mock_generator.generate = AsyncMock(
                return_value=StageResult(success=True, data=[], warnings=[], confidence=1.0)
            )
            mock_generator._generate_script_header = MagicMock(return_value="# header")
            mock_generator._generate_filename = MagicMock(return_value="test_x.py")
            mock_generator_class.return_value = mock_generator

            await agent._generate_scripts()

        _, kwargs = mock_generator_class.call_args
        assert kwargs["role_sessions"] == {"Admin": admin_blob}


# -----------------------------------------------------------------------------
# Process Method Tests
# -----------------------------------------------------------------------------


class TestSarahAgentProcess:
    """Test Sarah agent process method."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch("ai_qa.agents.sarah.PipelineArtifactAdapter") as mock_adapter_class:
            self.mock_adapter = MagicMock()
            mock_adapter_class.return_value = self.mock_adapter
            yield mock_adapter_class

    @pytest.mark.asyncio
    async def test_process_loads_test_cases_from_project_artifacts(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mock_project_context
    ) -> None:
        """Test process loads test cases from project artifacts."""
        from ai_qa.agents.sarah import SarahAgent

        # Mock adapter to return test cases
        mock_artifact = MagicMock()
        mock_artifact.content = json.dumps([tc.model_dump() for tc in sample_test_cases]).encode(
            "utf-8"
        )
        self.mock_adapter.load_test_cases.return_value = [mock_artifact]

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_generator_class:
            mock_generator = MagicMock()
            mock_generator.generate = AsyncMock()
            mock_generator._generate_script_header.return_value = "# Header"
            mock_generator._generate_filename.return_value = "file.py"
            mock_generator.generate.return_value = StageResult(
                success=True,
                data=[
                    {
                        "file_path": str(tmp_path / "testscripts" / "test_login.py"),
                        "test_case_title": tc.title,
                        "confidence": 0.85,
                    }
                    for tc in sample_test_cases
                ],
                errors=[],
                warnings=[],
                confidence=0.85,
            )
            mock_generator_class.return_value = mock_generator

            agent = SarahAgent(workspace_dir=tmp_path)
            agent.project_context = mock_project_context
            result = await agent.process({"chrome_path": "/usr/bin/chrome"})

            assert result.success
            assert len(agent._generated_scripts) == len(sample_test_cases)

    @pytest.mark.asyncio
    async def test_process_reconstructs_test_case_from_markdown(
        self, tmp_path: Path, mock_project_context
    ) -> None:
        """Markdown test-case artifacts reconstruct the typed TestCase via from_markdown.

        Mary saves test cases as natural-language Markdown (.md) — no JSON copy. When the
        artifact body is not parseable JSON, Sarah rebuilds the TestCase by parsing the
        Markdown so the review panel / heuristics keep working.
        """
        from ai_qa.agents.sarah import SarahAgent

        structured = TestCase(
            title="Search by Country",
            objective="Verify partial Country match",
            steps=[TestCaseStep(number=1, action="Enter Fran", target="the Country field")],
            expected_results=["Only matching journeys shown"],
        )
        md_artifact = MagicMock()
        md_artifact.name = "search-by-country.md"
        # Real Markdown body produced by Mary (round-trips via from_markdown).
        md_artifact.content = structured.to_markdown()
        self.mock_adapter.load_test_cases.return_value = [md_artifact]

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_generator_class:
            mock_generator = MagicMock()
            mock_generator.generate = AsyncMock()
            mock_generator._generate_script_header.return_value = "# Header"
            mock_generator._generate_filename.return_value = "file.py"
            mock_generator.generate.return_value = StageResult(
                success=True,
                data=[{"script_content": "code", "confidence": 0.9, "warnings": []}],
                errors=[],
                warnings=[],
                confidence=0.9,
            )
            mock_generator_class.return_value = mock_generator

            agent = SarahAgent(workspace_dir=tmp_path)
            agent.project_context = mock_project_context
            result = await agent.process({"chrome_path": "/usr/bin/chrome"})

        assert result.success
        assert len(agent._test_cases) == 1
        assert agent._test_cases[0].title == "Search by Country"
        assert agent._test_cases[0].steps[0].action == "Enter Fran"

    @pytest.mark.asyncio
    async def test_process_handles_empty_testcases_directory(
        self, tmp_path: Path, mock_project_context
    ) -> None:
        """Test process returns error for empty test cases from artifacts."""
        from ai_qa.agents.sarah import SarahAgent

        # Mock adapter to return empty list
        self.mock_adapter.load_test_cases.return_value = []

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        result = await agent.process({"chrome_path": "/usr/bin/chrome"})

        assert not result.success
        assert result.data is None
        assert any("No test case artifacts found" in err for err in result.errors)

    @pytest.mark.asyncio
    async def test_process_sends_progress_updates(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """Test process sends progress updates for each script generation."""
        from ai_qa.agents.sarah import SarahAgent

        mock_artifact = MagicMock()
        mock_artifact.content = json.dumps([tc.model_dump() for tc in sample_test_cases]).encode(
            "utf-8"
        )
        self.mock_adapter.load_test_cases.return_value = [mock_artifact]

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_generator_class:
            mock_generator = MagicMock()
            mock_generator.generate = AsyncMock()
            mock_generator._generate_script_header.return_value = "# Header"
            mock_generator._generate_filename.return_value = "file.py"
            mock_generator.generate.return_value = StageResult(
                success=True,
                data=[
                    {
                        "file_path": str(tmp_path / "testscripts" / "test_login.py"),
                        "test_case_title": tc.title,
                        "confidence": 0.85,
                    }
                    for tc in sample_test_cases
                ],
                errors=[],
                warnings=[],
                confidence=0.85,
            )
            mock_generator_class.return_value = mock_generator

            agent = SarahAgent(workspace_dir=tmp_path)
            agent.project_context = mock_project_context
            await agent.process({"chrome_path": "/usr/bin/chrome"})

            # Check that progress messages were sent
            # Should have: initial message + progress for each test case
            progress_calls = [
                c for c in mock_broadcast.call_args_list if c[0][0].message_type == "info"
            ]
            assert len(progress_calls) >= len(sample_test_cases)


# -----------------------------------------------------------------------------
# Handle Start Tests
# -----------------------------------------------------------------------------


class TestSarahAgentHandleStart:
    """Test Sarah agent handle_start method."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch("ai_qa.agents.sarah.PipelineArtifactAdapter") as mock_adapter_class:
            self.mock_adapter = MagicMock()
            mock_adapter_class.return_value = self.mock_adapter
            yield mock_adapter_class

    @pytest.mark.asyncio
    async def test_handle_start_blocks_when_no_approved_test_cases(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """AC3: handle_start sends error and stays START when no approved test cases exist."""
        from ai_qa.agents.sarah import AgentState as SarahState
        from ai_qa.agents.sarah import SarahAgent

        self.mock_adapter.service.list_artifacts.return_value = []
        self.mock_adapter.load_approved_test_cases.return_value = []

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        await agent.handle_start({})

        # AC3: must stay START (no PROCESSING, no REVIEW_REQUEST)
        assert agent.state == SarahState.START
        messages = [call[0][0].content for call in mock_broadcast.call_args_list]
        # Must send the "no approved test cases" message
        assert any("approved test cases" in msg.lower() or "Mary" in msg for msg in messages)
        # Must NOT ask for Chrome path
        assert not any("Chrome" in msg for msg in messages)

    @pytest.mark.asyncio
    async def test_handle_start_presents_selection_panel_when_test_cases_available(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """AC2: handle_start presents test_case_selection payload when approved test cases exist."""
        from uuid import uuid4

        from ai_qa.agents.sarah import AgentState as SarahState
        from ai_qa.agents.sarah import SarahAgent
        from ai_qa.pipelines.artifact_adapter import PipelineArtifact

        self.mock_adapter.service.list_artifacts.return_value = []
        mock_tc = MagicMock(spec=PipelineArtifact)
        mock_tc.id = uuid4()
        mock_tc.name = "tc-login.json"
        mock_tc.thread_id = None
        mock_tc.content = json.dumps({"title": "Login test"})
        self.mock_adapter.load_approved_test_cases.return_value = [mock_tc]

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        await agent.handle_start({})

        # Must transition to REVIEW_REQUEST (selection panel)
        assert agent.state == SarahState.REVIEW_REQUEST
        # Must emit test_case_selection metadata
        metadata_calls = [
            call[0][0]
            for call in mock_broadcast.call_args_list
            if call[0][0].metadata and call[0][0].metadata.get("type") == "test_case_selection"
        ]
        assert len(metadata_calls) >= 1
        # ScriptGenerator must NOT have been constructed
        assert agent._generated_scripts == []


# -----------------------------------------------------------------------------
# Handle Approve Tests
# -----------------------------------------------------------------------------


class TestSarahAgentHandleApprove:
    """Test Sarah agent handle_approve method."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch("ai_qa.agents.sarah.PipelineArtifactAdapter") as mock_adapter_class:
            self.mock_adapter = MagicMock()
            mock_adapter_class.return_value = self.mock_adapter
            yield mock_adapter_class

    @pytest.mark.asyncio
    async def test_handle_approve_marks_script_approved_and_advances(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """Test handle_approve marks current script as approved and advances."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        # Create generated scripts
        for tc in sample_test_cases:
            script = GeneratedScript(
                test_case=tc,
                script_content="# Test script",
                file_path=str(tmp_path / "testscripts" / f"{tc.filename}.py"),
                confidence=0.85,
                approved=False,
            )
            agent._generated_scripts.append(script)

        agent.state = AgentState.REVIEW_REQUEST
        agent._current_review_index = 0
        agent.phase = "script_review"  # skip input-selection dispatch

        await agent.handle_approve()

        # Script should be marked approved
        assert agent._generated_scripts[0].approved
        # Index 0 should be in the reviewed set (13.5: _reviewed_indices tracks, not linear counter)
        assert 0 in agent._reviewed_indices

    @pytest.mark.asyncio
    async def test_handle_approve_transitions_to_done_when_all_approved(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """Test handle_approve transitions to DONE when all scripts approved."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        # Create single generated script
        script = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# Test script",
            file_path=str(tmp_path / "testscripts" / f"{sample_test_cases[0].filename}.py"),
            confidence=0.85,
            approved=False,
        )
        agent._generated_scripts.append(script)

        agent.state = AgentState.REVIEW_REQUEST
        agent._current_review_index = 0
        agent.phase = "script_review"  # skip input-selection dispatch

        await agent.handle_approve()

        # Should transition to DONE
        assert agent.state == AgentState.DONE

    @pytest.mark.asyncio
    async def test_handle_approve_presents_next_script(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """Test handle_approve presents next script when more exist."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        # Create multiple generated scripts
        for tc in sample_test_cases:
            script = GeneratedScript(
                test_case=tc,
                script_content="# Test script",
                file_path=str(tmp_path / "testscripts" / f"{tc.filename}.py"),
                confidence=0.85,
                approved=False,
            )
            agent._generated_scripts.append(script)

        agent.state = AgentState.REVIEW_REQUEST
        agent._current_review_index = 0
        agent.phase = "script_review"  # skip input-selection dispatch

        await agent.handle_approve()

        # Should still be in REVIEW_REQUEST state
        assert agent.state == AgentState.REVIEW_REQUEST


# -----------------------------------------------------------------------------
# Handle Approve â€” 13.6 edit + validate tests
# -----------------------------------------------------------------------------


class TestSarahHandleApproveEditValidate:
    """Test 13.6 edit-and-validate paths in handle_approve."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch("ai_qa.agents.sarah.PipelineArtifactAdapter") as mock_adapter_class:
            self.mock_adapter = MagicMock()
            mock_adapter_class.return_value = self.mock_adapter
            yield mock_adapter_class

    def _make_agent(self, tmp_path: Path, tc: TestCase) -> Any:
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = MagicMock()
        agent.phase = "script_review"
        script = GeneratedScript(
            test_case=tc,
            script_content="# original content",
            file_path=str(tmp_path / "testscripts" / f"{tc.filename}.py"),
            confidence=0.85,
            approved=False,
        )
        agent._generated_scripts.append(script)
        agent._current_review_index = 0
        from ai_qa.agents.base import AgentState

        agent.state = AgentState.REVIEW_REQUEST
        return agent

    @pytest.mark.asyncio
    async def test_edited_valid_approve_saves_edited_content(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """AC3: edited + valid approve â†’ save_script called with the EDITED content."""
        agent = self._make_agent(tmp_path, sample_test_cases[0])
        agent.project_context = mock_project_context

        edited = (
            "import asyncio\n"
            "from playwright.async_api import async_playwright\n\n"
            "async def test_login():\n"
            "    async with async_playwright() as pw:\n"
            "        browser = await pw.chromium.launch()\n"
            "        page = await browser.new_page()\n"
            "        await page.goto('https://example.com')\n"
            "        await browser.close()\n"
        )

        await agent.handle_approve(
            {"action": "approved", "script_index": 0, "script_content": edited}
        )

        # save_script called with the EDITED content, not the original
        self.mock_adapter.save_script.assert_called_once()
        saved_content = self.mock_adapter.save_script.call_args[0][1]
        assert saved_content == edited
        assert agent._generated_scripts[0].approved
        assert 0 in agent._reviewed_indices

    @pytest.mark.asyncio
    async def test_edited_invalid_approve_does_not_save(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """AC2: invalid edited content â†’ save_script NOT called; stays REVIEW_REQUEST."""
        from ai_qa.agents.base import AgentState

        agent = self._make_agent(tmp_path, sample_test_cases[0])
        agent.project_context = mock_project_context

        # Syntax error in the edited content
        bad_edit = "def broken(\n    pass\n"

        await agent.handle_approve(
            {"action": "approved", "script_index": 0, "script_content": bad_edit}
        )

        # save_script must NOT be called on a validation failure
        self.mock_adapter.save_script.assert_not_called()
        # script must NOT be marked approved
        assert not agent._generated_scripts[0].approved
        assert 0 not in agent._reviewed_indices
        # agent stays in REVIEW_REQUEST (not DONE)
        assert agent.state == AgentState.REVIEW_REQUEST

    @pytest.mark.asyncio
    async def test_edited_invalid_approve_emits_script_validation_error(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """AC2: invalid edited content â†’ script_validation_error metadata message sent."""
        agent = self._make_agent(tmp_path, sample_test_cases[0])
        agent.project_context = mock_project_context

        bad_edit = "def broken(\n    pass\n"
        await agent.handle_approve(
            {"action": "approved", "script_index": 0, "script_content": bad_edit}
        )

        # Collect all broadcast calls to find the validation error message
        calls = mock_broadcast.call_args_list
        metadata_types = [
            call[1].get("metadata", {}).get("type")
            or (call[0][0].metadata.get("type") if hasattr(call[0][0], "metadata") else None)
            for call in calls
        ]
        # At least one message must be script_validation_error
        error_calls = [
            call
            for call in calls
            if (call[0][0].metadata or {}).get("type") == "script_validation_error"
        ]
        assert len(error_calls) >= 1, (
            f"Expected a script_validation_error message; got metadata types: {metadata_types}"
        )
        payload = error_calls[0][0][0].metadata
        assert payload["script_index"] == 0
        assert len(payload["errors"]) >= 1

    @pytest.mark.asyncio
    async def test_no_script_content_saves_original(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """Back-compat (13.5): no script_content in data â†’ saves the ORIGINAL content."""
        agent = self._make_agent(tmp_path, sample_test_cases[0])
        agent.project_context = mock_project_context

        await agent.handle_approve({"action": "approved", "script_index": 0})

        self.mock_adapter.save_script.assert_called_once()
        saved_content = self.mock_adapter.save_script.call_args[0][1]
        assert saved_content == "# original content"

    @pytest.mark.asyncio
    async def test_unsafe_pattern_in_edited_content_blocks_approve(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """AC2: unsafe pattern in edit â†’ blocked; save_script NOT called."""
        agent = self._make_agent(tmp_path, sample_test_cases[0])
        agent.project_context = mock_project_context

        unsafe_edit = "import subprocess\nsubprocess.run(['ls'])\n"

        await agent.handle_approve(
            {"action": "approved", "script_index": 0, "script_content": unsafe_edit}
        )

        self.mock_adapter.save_script.assert_not_called()
        assert not agent._generated_scripts[0].approved


# -----------------------------------------------------------------------------
# Handle Reject Tests
# -----------------------------------------------------------------------------


class TestSarahAgentHandleReject:
    """Test Sarah agent handle_reject method."""

    @pytest.mark.asyncio
    async def test_handle_reject_acknowledges_feedback(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mock_broadcast: AsyncMock
    ) -> None:
        """Test handle_reject sends acknowledgment message."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)

        # Create generated script
        script = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# Test script",
            file_path=str(tmp_path / "testscripts" / f"{sample_test_cases[0].filename}.py"),
            confidence=0.85,
            approved=False,
        )
        agent._generated_scripts.append(script)
        agent.state = AgentState.REVIEW_REQUEST
        agent._current_review_index = 0

        feedback = "Add more assertions"

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_generator_class:
            mock_generator = MagicMock()
            mock_generator.generate = AsyncMock()
            mock_generator._generate_script_header.return_value = "# Header"
            mock_generator._generate_filename.return_value = "file.py"
            mock_generator.generate.return_value = StageResult(
                success=True,
                data=[
                    {
                        "file_path": str(tmp_path / "testscripts" / "test_login.py"),
                        "test_case_title": sample_test_cases[0].title,
                        "confidence": 0.85,
                    }
                ],
                errors=[],
                warnings=[],
                confidence=0.85,
            )
            mock_generator_class.return_value = mock_generator

            await agent.handle_reject(feedback)

            # Check acknowledgment was sent
            first_call = mock_broadcast.call_args_list[0][0][0]
            assert "feedback" in first_call.content.lower()

    @pytest.mark.asyncio
    async def test_handle_reject_regenerates_script(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mock_broadcast: AsyncMock
    ) -> None:
        """Test handle_reject regenerates the current script with feedback."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)

        # Create generated script
        script = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# Original script",
            file_path=str(tmp_path / "testscripts" / f"{sample_test_cases[0].filename}.py"),
            confidence=0.85,
            approved=False,
        )
        agent._generated_scripts.append(script)
        agent.state = AgentState.REVIEW_REQUEST
        agent._current_review_index = 0

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_generator_class:
            mock_generator = MagicMock()
            mock_generator.generate = AsyncMock()
            mock_generator._generate_script_header.return_value = "# Header"
            mock_generator._generate_filename.return_value = "file.py"
            mock_generator.generate.return_value = StageResult(
                success=True,
                data=[
                    {
                        "file_path": str(tmp_path / "testscripts" / "test_login.py"),
                        "test_case_title": sample_test_cases[0].title,
                        "confidence": 0.9,
                    }
                ],
                errors=[],
                warnings=[],
                confidence=0.9,
            )
            mock_generator_class.return_value = mock_generator

            await agent.handle_reject("Add more assertions")

            # ScriptGenerator should have been called
            mock_generator.generate.assert_called_once()


# -----------------------------------------------------------------------------
# Handle Skip Tests
# -----------------------------------------------------------------------------


class TestSarahAgentHandleSkip:
    """Test Sarah agent handle_skip method."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch("ai_qa.agents.sarah.PipelineArtifactAdapter") as mock_adapter_class:
            self.mock_adapter = MagicMock()
            mock_adapter_class.return_value = self.mock_adapter
            yield mock_adapter_class

    @pytest.mark.asyncio
    async def test_handle_skip_advances_without_approval(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """Test handle_skip advances without marking script approved."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        # Create generated scripts
        for tc in sample_test_cases:
            script = GeneratedScript(
                test_case=tc,
                script_content="# Test script",
                file_path=str(tmp_path / "testscripts" / f"{tc.filename}.py"),
                confidence=0.85,
                approved=False,
            )
            agent._generated_scripts.append(script)

        agent.state = AgentState.REVIEW_REQUEST
        agent._current_review_index = 0

        await agent.handle_skip()

        # First script should NOT be approved
        assert not agent._generated_scripts[0].approved
        # Index 0 should be in the reviewed set (13.5: _reviewed_indices, not linear counter)
        assert 0 in agent._reviewed_indices

    @pytest.mark.asyncio
    async def test_handle_skip_sends_skip_notification(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """Test handle_skip sends notification about skipped script."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        # Create generated script
        script = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# Test script",
            file_path=str(tmp_path / "testscripts" / f"{sample_test_cases[0].filename}.py"),
            confidence=0.85,
            approved=False,
        )
        agent._generated_scripts.append(script)
        agent.state = AgentState.REVIEW_REQUEST
        agent._current_review_index = 0

        await agent.handle_skip()

        # Check skip notification was sent
        skip_call = [c for c in mock_broadcast.call_args_list if "skipped" in c[0][0].content]
        assert len(skip_call) > 0


# -----------------------------------------------------------------------------
# Handle Navigate Tests
# -----------------------------------------------------------------------------


class TestSarahAgentHandleNavigate:
    """Test Sarah agent handle_navigate method."""

    @pytest.mark.asyncio
    async def test_handle_navigate_next_advances_index(
        self, tmp_path: Path, sample_test_cases: list[TestCase]
    ) -> None:
        """Test handle_navigate next advances to next script."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)

        # Create generated scripts
        for tc in sample_test_cases:
            script = GeneratedScript(
                test_case=tc,
                script_content="# Test script",
                file_path=str(tmp_path / "testscripts" / f"{tc.filename}.py"),
                confidence=0.85,
                approved=False,
            )
            agent._generated_scripts.append(script)

        agent._current_review_index = 0

        with patch.object(agent, "_present_current_script_for_review"):
            await agent.handle_navigate("next")

        assert agent._current_review_index == 1

    @pytest.mark.asyncio
    async def test_handle_navigate_previous_goes_back(
        self, tmp_path: Path, sample_test_cases: list[TestCase]
    ) -> None:
        """Test handle_navigate previous goes to previous script."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)

        # Create generated scripts
        for tc in sample_test_cases:
            script = GeneratedScript(
                test_case=tc,
                script_content="# Test script",
                file_path=str(tmp_path / "testscripts" / f"{tc.filename}.py"),
                confidence=0.85,
                approved=False,
            )
            agent._generated_scripts.append(script)

        agent._current_review_index = 1

        with patch.object(agent, "_present_current_script_for_review"):
            await agent.handle_navigate("previous")

        assert agent._current_review_index == 0

    @pytest.mark.asyncio
    async def test_handle_navigate_respects_bounds(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mock_broadcast: AsyncMock
    ) -> None:
        """Test handle_navigate respects bounds of scripts list."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)

        # Create single generated script
        script = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# Test script",
            file_path=str(tmp_path / "testscripts" / f"{sample_test_cases[0].filename}.py"),
            confidence=0.85,
            approved=False,
        )
        agent._generated_scripts.append(script)

        agent._current_review_index = 0

        # Try to go previous at first script
        await agent.handle_navigate("previous")

        # Should stay at 0 and send warning
        assert agent._current_review_index == 0
        warning_calls = [
            c for c in mock_broadcast.call_args_list if c[0][0].message_type == "warning"
        ]
        assert len(warning_calls) > 0


# -----------------------------------------------------------------------------
# Review State Tests
# -----------------------------------------------------------------------------


class TestSarahAgentReviewState:
    """Test Sarah agent review state methods."""

    def test_get_review_state_returns_correct_info(
        self, tmp_path: Path, sample_test_cases: list[TestCase]
    ) -> None:
        """Test get_review_state returns correct review state info."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)

        # Create generated scripts
        for i, tc in enumerate(sample_test_cases):
            script = GeneratedScript(
                test_case=tc,
                script_content="# Test script",
                file_path=str(tmp_path / "testscripts" / f"{tc.filename}.py"),
                confidence=0.85,
                approved=(i == 0),  # First one approved
            )
            agent._generated_scripts.append(script)

        agent._current_review_index = 1

        review_state = agent.get_review_state()

        assert review_state["has_scripts"]
        assert review_state["current_index"] == 1
        assert review_state["total_count"] == len(sample_test_cases)
        assert review_state["approved_count"] == 1
        assert review_state["current_script"] == sample_test_cases[1].title

    def test_get_review_state_when_no_scripts(self, tmp_path: Path, mock_project_context) -> None:
        """Test get_review_state when no scripts generated."""
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)

        review_state = agent.get_review_state()

        assert not review_state["has_scripts"]
        assert review_state["current_index"] == 0
        assert review_state["total_count"] == 0


# -----------------------------------------------------------------------------
# Format Review Content Tests
# -----------------------------------------------------------------------------


class TestSarahAgentFormatReviewContent:
    """Test Sarah agent review content formatting."""

    def test_format_review_content_includes_script_info(
        self, tmp_path: Path, sample_test_cases: list[TestCase]
    ) -> None:
        """Test review content includes script and test case info."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)

        # Create generated script
        script = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# Playwright script",
            file_path=str(tmp_path / "testscripts" / f"{sample_test_cases[0].filename}.py"),
            confidence=0.85,
            approved=False,
        )
        agent._generated_scripts.append(script)
        agent._current_review_index = 0

        result = StageResult(success=True, data=[script], errors=[], warnings=[])
        content = agent._format_review_content(result)

        assert sample_test_cases[0].title in content
        assert "1 of 1" in content or "Script 1" in content

    def test_format_review_content_when_no_scripts(
        self, tmp_path: Path, mock_project_context
    ) -> None:
        """Test review content when no scripts to review."""
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)

        result = StageResult(success=True, data=[], errors=[], warnings=[])
        content = agent._format_review_content(result)

        assert "No scripts" in content


# -----------------------------------------------------------------------------
# Review Presentation Tests
# -----------------------------------------------------------------------------


class TestSarahAgentPresentForReview:
    """Test Sarah agent review presentation â€” legacy single-script + new present-all (13.5)."""

    @pytest.mark.asyncio
    async def test_present_current_script_sends_review_data(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mock_broadcast: AsyncMock
    ) -> None:
        """Back-compat: _present_current_script_for_review still works (kept for tests)."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)

        script = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="import pytest\n# Test code",
            file_path=str(tmp_path / "testscripts" / f"{sample_test_cases[0].filename}.py"),
            confidence=0.85,
            approved=False,
        )
        agent._generated_scripts.append(script)
        agent._current_review_index = 0

        await agent._present_current_script_for_review()

        review_calls = [
            c
            for c in mock_broadcast.call_args_list
            if c[0][0].metadata and c[0][0].metadata.get("type") == "review_request"
        ]
        assert len(review_calls) > 0

        review_data = review_calls[0][0][0].metadata.get("review_data", {})
        assert review_data["current_index"] == 1
        assert review_data["total_count"] == 1
        assert review_data["script_language"] == "python"

    @pytest.mark.asyncio
    async def test_present_script_review_emits_present_all_payload(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mock_broadcast: AsyncMock
    ) -> None:
        """_present_script_review sends ONE script_review message with the full scripts list."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        for tc in sample_test_cases:
            agent._generated_scripts.append(
                GeneratedScript(
                    test_case=tc,
                    script_content=f"# script for {tc.title}",
                    file_path=str(tmp_path / f"{tc.filename}.py"),
                    confidence=0.75,
                    warnings=["# TODO: verify selector"],
                )
            )
        agent._current_review_index = 0

        await agent._present_script_review()

        # Must be exactly ONE message with type=="script_review"
        review_calls = [
            c
            for c in mock_broadcast.call_args_list
            if c[0][0].metadata and c[0][0].metadata.get("type") == "script_review"
        ]
        assert len(review_calls) == 1

        meta = review_calls[0][0][0].metadata
        assert meta["total_count"] == len(sample_test_cases)
        assert meta["current_index"] == 0
        scripts = meta["scripts"]
        assert len(scripts) == len(sample_test_cases)

        # Verify per-script entry shape
        entry = scripts[0]
        assert entry["index"] == 0
        assert entry["script_language"] == "python"
        assert "test_case" in entry
        assert "script_content" in entry
        assert "confidence" in entry
        assert "warnings" in entry
        assert entry["status"] == "pending"
        assert not entry["approved"]

    @pytest.mark.asyncio
    async def test_present_script_review_warnings_channel(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mock_broadcast: AsyncMock
    ) -> None:
        """Warnings from GeneratedScript.warnings appear verbatim in the payload (AC3)."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        expected_warnings = ["Brittle selector (Step 2): use data-testid", "SSO setup required"]
        agent._generated_scripts.append(
            GeneratedScript(
                test_case=sample_test_cases[0],
                script_content="# script",
                file_path="file.py",
                confidence=0.5,
                warnings=expected_warnings,
            )
        )

        await agent._present_script_review()

        review_calls = [
            c
            for c in mock_broadcast.call_args_list
            if c[0][0].metadata and c[0][0].metadata.get("type") == "script_review"
        ]
        assert len(review_calls) == 1
        entry = review_calls[0][0][0].metadata["scripts"][0]
        assert entry["warnings"] == expected_warnings


# -----------------------------------------------------------------------------
# Story 13.5: Index-addressable approve / skip / reject + _reviewed_indices DONE gate
# -----------------------------------------------------------------------------


class TestSarahAgentScriptReview135:
    """Tests for 13.5 index-addressable approve/skip/reject + reviewed-set DONE gate."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch("ai_qa.agents.sarah.PipelineArtifactAdapter") as mock_adapter_class:
            self.mock_adapter = MagicMock()
            mock_adapter_class.return_value = self.mock_adapter
            yield mock_adapter_class

    def _make_agent(
        self, tmp_path: Path, mock_project_context, count: int, sample_test_cases: list[TestCase]
    ):
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"
        for i in range(count):
            tc = sample_test_cases[i % len(sample_test_cases)]
            agent._generated_scripts.append(
                GeneratedScript(
                    test_case=tc,
                    script_content=f"# script {i}",
                    file_path=f"script_{i}.py",
                    confidence=0.8,
                )
            )
        agent.state = AgentState.REVIEW_REQUEST
        return agent

    @pytest.mark.asyncio
    async def test_approve_by_index_marks_correct_script(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """handle_approve({script_index:1}) marks script[1] approved, not script[0]."""
        agent = self._make_agent(tmp_path, mock_project_context, 2, sample_test_cases)

        await agent.handle_approve({"action": "approved", "script_index": 1})

        assert agent._generated_scripts[1].approved
        assert not agent._generated_scripts[0].approved
        assert 1 in agent._reviewed_indices
        assert 0 not in agent._reviewed_indices

    @pytest.mark.asyncio
    async def test_approve_done_only_when_all_reviewed(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """DONE fires only after every index is in _reviewed_indices."""
        agent = self._make_agent(tmp_path, mock_project_context, 2, sample_test_cases)

        # Approve first â†’ still REVIEW_REQUEST
        await agent.handle_approve({"action": "approved", "script_index": 0})
        assert agent.state == AgentState.REVIEW_REQUEST

        # Approve second â†’ DONE
        await agent.handle_approve({"action": "approved", "script_index": 1})
        assert agent.state == AgentState.DONE

    @pytest.mark.asyncio
    async def test_approve_backcompat_no_index_uses_current(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """handle_approve({}) with no script_index defaults to _current_review_index."""
        agent = self._make_agent(tmp_path, mock_project_context, 1, sample_test_cases)
        agent._current_review_index = 0

        await agent.handle_approve({})

        assert agent._generated_scripts[0].approved
        assert agent.state == AgentState.DONE

    @pytest.mark.asyncio
    async def test_skip_by_index_does_not_approve(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """Skip via approve data action="skip" records in _reviewed_indices without approving."""
        agent = self._make_agent(tmp_path, mock_project_context, 2, sample_test_cases)

        await agent.handle_approve({"action": "skip", "script_index": 0})

        assert not agent._generated_scripts[0].approved
        assert 0 in agent._reviewed_indices
        assert agent.state == AgentState.REVIEW_REQUEST

    @pytest.mark.asyncio
    async def test_skip_done_when_all_reviewed(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """DONE fires after all skipped (no approvals needed for the gate)."""
        agent = self._make_agent(tmp_path, mock_project_context, 2, sample_test_cases)

        await agent.handle_approve({"action": "skip", "script_index": 0})
        assert agent.state == AgentState.REVIEW_REQUEST

        await agent.handle_approve({"action": "skip", "script_index": 1})
        assert agent.state == AgentState.DONE

    @pytest.mark.asyncio
    async def test_reject_by_index_clears_reviewed_state(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """handle_reject with script_index=1 sets _current_review_index=1 and clears reviewed/approved."""

        agent = self._make_agent(tmp_path, mock_project_context, 2, sample_test_cases)
        # Pre-approve script 1
        agent._generated_scripts[1].approved = True
        agent._reviewed_indices.add(1)

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_gen_class:
            mock_gen = MagicMock()
            mock_gen.generate = AsyncMock()
            mock_gen._generate_script_header.return_value = "# h"
            mock_gen._generate_filename.return_value = "f.py"
            mock_gen.generate.return_value = StageResult(
                success=True,
                data=[{"script_content": "# new", "confidence": 0.9}],
                errors=[],
                warnings=[],
            )
            mock_gen_class.return_value = mock_gen

            await agent.handle_reject("fix this", {"script_index": 1})

        assert agent._current_review_index == 1
        assert 1 not in agent._reviewed_indices
        assert not agent._generated_scripts[1].approved

    @pytest.mark.asyncio
    async def test_present_script_review_reemitted_after_approve(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """After approving script 0 of 2, _present_script_review is re-emitted."""
        agent = self._make_agent(tmp_path, mock_project_context, 2, sample_test_cases)

        await agent.handle_approve({"action": "approved", "script_index": 0})

        script_review_calls = [
            c
            for c in mock_broadcast.call_args_list
            if c[0][0].metadata and c[0][0].metadata.get("type") == "script_review"
        ]
        assert len(script_review_calls) >= 1
        # The re-emit must show index 0 as "approved" in the scripts list
        latest_scripts = script_review_calls[-1][0][0].metadata["scripts"]
        assert latest_scripts[0]["status"] == "approved"


# -----------------------------------------------------------------------------
# Story 13.1: Input Selection Gate Tests
# -----------------------------------------------------------------------------


class TestSarahAgentInputSelection:
    """Tests for the 13.1 input-selection gate (AC1-AC3)."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch("ai_qa.agents.sarah.PipelineArtifactAdapter") as mock_adapter_class:
            self.mock_adapter = MagicMock()
            mock_adapter_class.return_value = self.mock_adapter
            self.mock_adapter.service.list_artifacts.return_value = []
            yield mock_adapter_class

    def _make_artifact(self, title: str, *, from_current: bool = True):
        from uuid import uuid4

        from ai_qa.pipelines.artifact_adapter import PipelineArtifact

        art = MagicMock(spec=PipelineArtifact)
        art.id = uuid4()
        art.name = f"tc-{title.lower().replace(' ', '-')}.json"
        art.content = json.dumps({"title": title})
        if from_current:
            art.thread_id = uuid4()
        else:
            art.thread_id = None
        return art

    # -------------------------------------------------------------------------
    # AC3: no approved test cases â†’ block
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_ac3_stays_start_when_no_approved_test_cases(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """AC3: stays START, sends error, no chrome-path request when no TCs."""
        from ai_qa.agents.sarah import SarahAgent

        self.mock_adapter.load_approved_test_cases.return_value = []
        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        await agent.handle_start({})

        assert agent.state == AgentState.START
        messages = [c[0][0].content for c in mock_broadcast.call_args_list]
        # Must mention test cases or Mary
        assert any("test cases" in m.lower() or "Mary" in m for m in messages)
        # Must NOT request Chrome path
        assert not any("Chrome" in m or "chrome" in m for m in messages)

    @pytest.mark.asyncio
    async def test_ac3_script_generator_never_called_when_no_test_cases(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """AC3: ScriptGenerator is never constructed when no approved TCs."""
        from ai_qa.agents.sarah import SarahAgent

        self.mock_adapter.load_approved_test_cases.return_value = []
        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_gen_cls:
            await agent.handle_start({})
            mock_gen_cls.assert_not_called()

    # -------------------------------------------------------------------------
    # AC2: selection panel presented
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_ac2_presents_selection_panel_and_transitions_to_review_request(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """AC2: emits test_case_selection metadata; transitions to REVIEW_REQUEST."""
        from ai_qa.agents.sarah import SarahAgent

        arts = [self._make_artifact("Login"), self._make_artifact("Search")]
        self.mock_adapter.load_approved_test_cases.return_value = arts
        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        await agent.handle_start({})

        assert agent.state == AgentState.REVIEW_REQUEST
        selection_msgs = [
            c[0][0]
            for c in mock_broadcast.call_args_list
            if c[0][0].metadata and c[0][0].metadata.get("type") == "test_case_selection"
        ]
        assert len(selection_msgs) == 1
        entries = selection_msgs[0].metadata["test_cases"]
        assert len(entries) == 2
        titles = {e["title"] for e in entries}
        assert titles == {"Login", "Search"}
        # Generation must NOT have started
        assert agent._generated_scripts == []

    @pytest.mark.asyncio
    async def test_ac2_thread_first_ordering_reflected_in_payload(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """AC2: current-thread artifact appears before other-thread in payload."""
        from ai_qa.agents.sarah import SarahAgent

        other_art = self._make_artifact("Other", from_current=False)
        current_art = self._make_artifact("Current", from_current=True)
        # load_approved_test_cases already returns them thread-first; test confirms payload order
        self.mock_adapter.load_approved_test_cases.return_value = [current_art, other_art]
        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        # Make context.thread_id match current_art.thread_id so from_current_thread=True
        mock_project_context.thread_id = current_art.thread_id

        await agent.handle_start({})

        selection_msgs = [
            c[0][0]
            for c in mock_broadcast.call_args_list
            if c[0][0].metadata and c[0][0].metadata.get("type") == "test_case_selection"
        ]
        entries = selection_msgs[0].metadata["test_cases"]
        assert entries[0]["title"] == "Current"
        assert entries[0]["from_current_thread"]
        assert not entries[1]["from_current_thread"]

    # -------------------------------------------------------------------------
    # AC2: confirm_inputs
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_ac2_confirm_inputs_stores_selected_subset(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """AC2: handle_approve confirm_inputs stores confirmed_test_cases."""
        from ai_qa.agents.sarah import SarahAgent

        art_a = self._make_artifact("Login")
        art_b = self._make_artifact("Search")
        self.mock_adapter.load_approved_test_cases.return_value = [art_a, art_b]
        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        await agent.handle_start({})  # sets candidate_test_cases

        await agent.handle_approve(
            data={
                "action": "confirm_inputs",
                "selected_artifact_ids": [str(art_a.id)],
            }
        )

        assert len(agent.confirmed_test_cases) == 1
        assert agent.confirmed_test_cases[0].title == "Login"
        assert agent.phase == "script_review"

    @pytest.mark.asyncio
    async def test_ac2_confirm_inputs_then_chrome_path_requested_when_not_set(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """After confirm with no Chrome path saved, sarah_inputs_request is emitted."""
        from ai_qa.agents.sarah import SarahAgent

        art = self._make_artifact("Login")
        self.mock_adapter.load_approved_test_cases.return_value = [art]
        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent._chrome_path = None

        await agent.handle_start({})
        mock_broadcast.reset_mock()  # clear selection-panel calls

        await agent.handle_approve(
            data={
                "action": "confirm_inputs",
                "selected_artifact_ids": [str(art.id)],
            }
        )

        assert agent.state == AgentState.START
        chrome_meta_calls = [
            c[0][0]
            for c in mock_broadcast.call_args_list
            if c[0][0].metadata and c[0][0].metadata.get("type") == "sarah_inputs_request"
        ]
        assert len(chrome_meta_calls) >= 1

    # -------------------------------------------------------------------------
    # Re-entry guard
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_reentry_when_awaiting_inputs_skips_selection(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """C4: when _awaiting_inputs is set, the selection gate is bypassed on re-start.

        The re-entry guard keys off the dedicated _awaiting_inputs flag, NOT
        confirmed_test_cases (which is no longer overloaded as the re-entry signal).
        """
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.confirmed_test_cases = [
            TestCase(title="Login", preconditions=[], steps=[], expected_results=[])
        ]
        agent.phase = "script_review"
        agent._chrome_path = None
        agent._awaiting_inputs = True  # dedicated re-entry flag (C4)

        await agent.handle_start({"chrome_path": "/usr/bin/chrome"})

        # No test_case_selection payload should be emitted
        selection_calls = [
            c
            for c in mock_broadcast.call_args_list
            if c[0][0].metadata and c[0][0].metadata.get("type") == "test_case_selection"
        ]
        assert len(selection_calls) == 0

    @pytest.mark.asyncio
    async def test_inputs_request_asks_for_target_url(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """The inputs request always asks for the application URL (needs_url=True)."""
        from ai_qa.agents.sarah import SarahAgent

        art = self._make_artifact("Login")
        self.mock_adapter.load_approved_test_cases.return_value = [art]
        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent._chrome_path = None

        await agent.handle_start({})
        await agent.handle_approve(
            data={"action": "confirm_inputs", "selected_artifact_ids": [str(art.id)]}
        )

        requests = [
            c[0][0].metadata
            for c in mock_broadcast.call_args_list
            if c[0][0].metadata and c[0][0].metadata.get("type") == "sarah_inputs_request"
        ]
        assert requests, "expected a sarah_inputs_request"
        assert requests[-1]["needs_url"] is True
        # No browser-source fields anymore — the server-side captured session is the auth.
        assert "needs_chrome" not in requests[-1]
        assert "environments" in requests[-1]

    @pytest.mark.asyncio
    async def test_reentry_stores_target_url_and_chrome_then_proceeds(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """Re-entry captures target_url + chrome_path and proceeds (no re-request)."""
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.confirmed_test_cases = [
            TestCase(title="Login", preconditions=[], steps=[], expected_results=[])
        ]
        agent.phase = "script_review"
        agent._chrome_path = None
        agent._target_url = None
        agent._awaiting_inputs = True

        ok = StageResult(success=True, data=[], errors=[], warnings=[], confidence=1.0)
        with (
            patch.object(agent, "process", new=AsyncMock(return_value=ok)),
            patch.object(agent, "_present_script_review", new=AsyncMock()),
        ):
            await agent.handle_start(
                {"target_url": "https://app.test", "chrome_path": "/usr/bin/chrome"}
            )

        assert agent._target_url == "https://app.test"
        assert agent._chrome_path == "/usr/bin/chrome"
        # Inputs satisfied -> it must NOT re-emit an inputs request.
        reqs = [
            c
            for c in mock_broadcast.call_args_list
            if c[0][0].metadata and c[0][0].metadata.get("type") == "sarah_inputs_request"
        ]
        assert len(reqs) == 0

    @pytest.mark.asyncio
    async def test_reentry_with_env_only_proceeds_without_browser_source(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """Tier-1: a re-start with only {target_url, environment} (no Chrome/CDP) proceeds to
        generation. The server-side captured session is the browser auth, so a local browser
        source is no longer required (the gate previously looped forever here)."""
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.confirmed_test_cases = [
            TestCase(title="Login", preconditions=[], steps=[], expected_results=[])
        ]
        agent.phase = "script_review"
        agent._chrome_path = None
        agent._cdp_url = None
        agent._target_url = None
        agent._awaiting_inputs = True

        ok = StageResult(success=True, data=[], errors=[], warnings=[], confidence=1.0)
        with (
            patch.object(agent, "process", new=AsyncMock(return_value=ok)),
            patch.object(agent, "_present_script_review", new=AsyncMock()),
        ):
            await agent.handle_start({"target_url": "https://app.test", "environment": "Test 1"})

        assert agent._target_url == "https://app.test"
        assert agent._environment == "Test 1"
        # No browser source submitted, yet it must NOT loop back to an inputs request.
        reqs = [
            c
            for c in mock_broadcast.call_args_list
            if c[0][0].metadata and c[0][0].metadata.get("type") == "sarah_inputs_request"
        ]
        assert len(reqs) == 0

    # -------------------------------------------------------------------------
    # Regression: existing script-review approve tests unaffected by phase guard
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_handle_approve_in_script_review_phase_not_dispatched_to_confirm(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """When phase==script_review, handle_approve falls through to script-review logic."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent
        from ai_qa.models import TestCase, TestCaseStep

        tc = TestCase(
            title="Reg test",
            preconditions=[],
            steps=[TestCaseStep(number=1, action="click", target="#btn")],
            expected_results=["ok"],
        )
        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"

        script = GeneratedScript(
            test_case=tc,
            script_content="# script",
            file_path=str(tmp_path / "s.py"),
            confidence=0.9,
            approved=False,
        )
        agent._generated_scripts.append(script)
        agent._current_review_index = 0

        await agent.handle_approve(data=None)

        # Must have marked script approved (script-review logic ran)
        assert agent._generated_scripts[0].approved
        # Must NOT have called load_approved_test_cases (confirm_inputs path)
        self.mock_adapter.load_approved_test_cases.assert_not_called()


# ---------------------------------------------------------------------------
# Story 13.2 â€” GeneratedScript.warnings field (Task 1)
# ---------------------------------------------------------------------------


class TestGeneratedScriptWarningsField:
    """Test that GeneratedScript model carries a warnings field (AC3)."""

    def test_generated_script_has_warnings_field(self, tmp_path: Path) -> None:
        """GeneratedScript initializes with empty warnings by default."""
        from ai_qa.agents.sarah import GeneratedScript

        tc = TestCase(
            title="T",
            preconditions=[],
            steps=[],
            expected_results=[],
        )
        script = GeneratedScript(
            test_case=tc,
            script_content="pass",
            file_path="test_t.py",
            confidence=0.8,
        )
        assert hasattr(script, "warnings")
        assert script.warnings == []

    def test_generated_script_accepts_warnings_list(self, tmp_path: Path) -> None:
        """GeneratedScript stores provided warnings."""
        from ai_qa.agents.sarah import GeneratedScript

        tc = TestCase(title="T", preconditions=[], steps=[], expected_results=[])
        script = GeneratedScript(
            test_case=tc,
            script_content="pass",
            file_path="test_t.py",
            confidence=0.5,
            warnings=["TODO: missing URL", "REVIEW: ambiguous result"],
        )
        assert len(script.warnings) == 2
        assert "TODO: missing URL" in script.warnings

    def test_failed_placeholder_constructs_with_empty_warnings(self, tmp_path: Path) -> None:
        """The failed-generation placeholder still constructs correctly with warnings default."""
        from ai_qa.agents.sarah import GeneratedScript

        tc = TestCase(title="Fail", preconditions=[], steps=[], expected_results=[])
        placeholder = GeneratedScript(
            test_case=tc,
            script_content="# Generation failed: timeout",
            file_path="",
            confidence=0.0,
            approved=False,
            error_message="timeout",
        )
        assert placeholder.warnings == []


# ---------------------------------------------------------------------------
# Story 13.2 â€” Warnings flow through _generate_scripts and review_data (Task 3)
# ---------------------------------------------------------------------------


class TestSarahWarningsFlow:
    """Test that TODO/REVIEW markers flow from generator to GeneratedScript and review_data."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch("ai_qa.agents.sarah.PipelineArtifactAdapter") as mock_adapter_class:
            self.mock_adapter = MagicMock()
            mock_adapter_class.return_value = self.mock_adapter
            yield mock_adapter_class

    @pytest.mark.asyncio
    async def test_warnings_from_generator_land_on_generated_script(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """When generator returns warnings, GeneratedScript.warnings is populated."""
        from ai_qa.agents.sarah import SarahAgent

        tc = TestCase(title="Login", preconditions=[], steps=[], expected_results=[])

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_gen_class:
            mock_gen = MagicMock()
            mock_gen_class.return_value = mock_gen
            mock_gen._generate_script_header.return_value = "# header\n"
            mock_gen._generate_filename.return_value = "test_login.py"
            mock_gen.generate = AsyncMock(
                return_value=StageResult(
                    success=True,
                    data=[
                        {
                            "script_content": "def test_login(page):\n    # TODO: missing URL\n    pass\n",
                            "test_case_title": "Login",
                            "confidence": 0.6,
                            "warnings": ["TODO: missing URL"],
                        }
                    ],
                    errors=[],
                    warnings=["TODO: missing URL"],
                    confidence=0.6,
                )
            )

            agent = SarahAgent(workspace_dir=tmp_path)
            agent.project_context = mock_project_context
            agent._test_cases = [tc]

            await agent._generate_scripts()

        assert len(agent._generated_scripts) == 1
        assert agent._generated_scripts[0].warnings == ["TODO: missing URL"]

    @pytest.mark.asyncio
    async def test_warnings_appear_in_review_data(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """GeneratedScript.warnings are included in the review_data sent to the frontend."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        tc = TestCase(title="Review test", preconditions=[], steps=[], expected_results=[])
        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"

        script = GeneratedScript(
            test_case=tc,
            script_content="def test_review(page):\n    # TODO: selector unknown\n    pass\n",
            file_path="test_review_test.py",
            confidence=0.5,
            warnings=["TODO: selector unknown"],
        )
        agent._generated_scripts = [script]
        agent._current_review_index = 0

        await agent._present_current_script_for_review()

        calls = mock_broadcast.call_args_list
        assert len(calls) >= 1
        # The last broadcast carries review_data
        last_msg = calls[-1][0][0]
        assert last_msg.metadata is not None
        review_data = last_msg.metadata.get("review_data", {})
        assert "warnings" in review_data
        assert review_data["warnings"] == ["TODO: selector unknown"]

    @pytest.mark.asyncio
    async def test_regenerated_script_retains_markers(
        self, tmp_path: Path, mock_broadcast: AsyncMock, mock_project_context
    ) -> None:
        """Regenerated script warnings (from new markers) are stored on GeneratedScript."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        tc = TestCase(title="Regen", preconditions=[], steps=[], expected_results=[])
        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent._test_cases = [tc]

        # Seed an existing script with no warnings
        agent._generated_scripts = [
            GeneratedScript(
                test_case=tc,
                script_content="def test_regen(page): pass",
                file_path="test_regen.py",
                confidence=0.8,
                warnings=[],
            )
        ]
        agent._current_review_index = 0

        regen_warnings = ["REVIEW: expected outcome is ambiguous"]

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_gen_class:
            mock_gen = MagicMock()
            mock_gen_class.return_value = mock_gen
            mock_gen._generate_script_header.return_value = "# header\n"
            mock_gen._generate_filename.return_value = "test_regen.py"
            mock_gen.generate = AsyncMock(
                return_value=StageResult(
                    success=True,
                    data=[
                        {
                            "script_content": "def test_regen(page):\n    # REVIEW: expected outcome is ambiguous\n    pass\n",
                            "test_case_title": "Regen",
                            "confidence": 0.6,
                            "warnings": regen_warnings,
                        }
                    ],
                    errors=[],
                    warnings=regen_warnings,
                    confidence=0.6,
                )
            )

            await agent._regenerate_current_script("some feedback")

        assert agent._generated_scripts[0].warnings == regen_warnings


# ---------------------------------------------------------------------------
# Story 13.3 â€” GeneratedScript.warnings population via _generate_scripts
# ---------------------------------------------------------------------------


class TestStory133SarahWarningFlow:
    """13.3: GeneratedScript.warnings receives brittle/gap warnings from ScriptGenerator."""

    @pytest.mark.asyncio
    async def test_generate_scripts_populates_generated_script_warnings(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """Warnings from ScriptGenerator.generate flow into GeneratedScript.warnings."""
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent._test_cases = [sample_test_cases[0]]

        detected_warnings = [
            'Brittle selector (Step 1): .locator("xpath=//button") â€” prefer get_by_test_id/...',
            "Assertion gap: only 0 of 1 expected result(s) mapped to expect() assertions â€” review for missing/ambiguous assertions",
        ]

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_gen_class:
            mock_gen = MagicMock()
            mock_gen_class.return_value = mock_gen
            mock_gen._generate_script_header.return_value = "# header\n"
            mock_gen._generate_filename.return_value = "test_login.py"
            mock_gen.generate = AsyncMock(
                return_value=StageResult(
                    success=True,
                    data=[
                        {
                            "script_content": "def test_login(page): pass",
                            "test_case_title": sample_test_cases[0].title,
                            "confidence": 0.5,
                            "warnings": detected_warnings,
                        }
                    ],
                    errors=[],
                    warnings=detected_warnings,
                    confidence=0.5,
                )
            )

            await agent._generate_scripts()

        assert len(agent._generated_scripts) == 1
        gs = agent._generated_scripts[0]
        assert any("Brittle selector" in w for w in gs.warnings)
        assert any("Assertion gap" in w for w in gs.warnings)

    @pytest.mark.asyncio
    async def test_present_script_puts_warnings_in_review_data(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """_present_current_script_for_review puts GeneratedScript.warnings in review_data."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        script_warnings = [
            "Brittle selector (Step 2): .locator('.btn') â€” prefer get_by_test_id/...",
            "Assertion gap: only 1 of 2 expected result(s) mapped to expect() â€” review",
        ]
        gs = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="def test_login(page): pass",
            file_path="test_login.py",
            confidence=0.7,
            warnings=script_warnings,
        )
        agent._generated_scripts.append(gs)
        agent._current_review_index = 0
        agent.state = AgentState.REVIEW_REQUEST
        agent.phase = "script_review"

        await agent._present_current_script_for_review()

        assert mock_broadcast.called
        review_calls = [
            call
            for call in mock_broadcast.call_args_list
            if call[0][0].metadata and call[0][0].metadata.get("type") == "review_request"
        ]
        assert len(review_calls) >= 1
        review_data = review_calls[-1][0][0].metadata["review_data"]
        assert review_data["warnings"] == script_warnings


# ---------------------------------------------------------------------------
# Story 13.4 â€” GeneratedScript.warnings population via _generate_scripts
# ---------------------------------------------------------------------------


class TestStory134SarahWarningFlow:
    """13.4: SSO/credential warnings from ScriptGenerator flow into GeneratedScript.warnings."""

    @pytest.mark.asyncio
    async def test_generate_scripts_populates_sso_credential_warnings(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """Credential and SSO-setup warnings from 13.4 detectors flow into GeneratedScript.warnings."""
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent._test_cases = [sample_test_cases[0]]

        sso_warnings = [
            "Credential/secret literal (Step 1): .fill('<redacted>') â€” never hardcode credentials; reuse the authenticated SSO session",
            "SSO/session setup required: this test targets an authenticated area â€” run it against a pre-authenticated browser context (existing SSO session); no login automation or credentials are included",
        ]

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_gen_class:
            mock_gen = MagicMock()
            mock_gen_class.return_value = mock_gen
            mock_gen._generate_script_header.return_value = "# header\n"
            mock_gen._generate_filename.return_value = "test_login.py"
            mock_gen.generate = AsyncMock(
                return_value=StageResult(
                    success=True,
                    data=[
                        {
                            "script_content": "def test_login(page): pass",
                            "test_case_title": sample_test_cases[0].title,
                            "confidence": 0.6,
                            "warnings": sso_warnings,
                        }
                    ],
                    errors=[],
                    warnings=sso_warnings,
                    confidence=0.6,
                )
            )

            await agent._generate_scripts()

        assert len(agent._generated_scripts) == 1
        gs = agent._generated_scripts[0]
        assert any("Credential/secret literal" in w for w in gs.warnings)
        assert any("SSO/session setup required" in w for w in gs.warnings)

    @pytest.mark.asyncio
    async def test_sso_warnings_in_review_data(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """_present_current_script_for_review includes SSO/credential warnings in review_data."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        sso_warnings = [
            "Credential/secret literal (Step 1): .fill('<redacted>') â€” never hardcode credentials; reuse the authenticated SSO session",
            "SSO/session setup required: this test targets an authenticated area",
        ]
        gs = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="def test_login(page): pass",
            file_path="test_login.py",
            confidence=0.6,
            warnings=sso_warnings,
        )
        agent._generated_scripts.append(gs)
        agent._current_review_index = 0
        agent.state = AgentState.REVIEW_REQUEST
        agent.phase = "script_review"

        await agent._present_current_script_for_review()

        review_calls = [
            call
            for call in mock_broadcast.call_args_list
            if call[0][0].metadata and call[0][0].metadata.get("type") == "review_request"
        ]
        assert len(review_calls) >= 1
        review_data = review_calls[-1][0][0].metadata["review_data"]
        assert any("Credential/secret literal" in w for w in review_data["warnings"])
        assert any("SSO/session setup required" in w for w in review_data["warnings"])


# ---------------------------------------------------------------------------
# Story 13.4 â€” AC3 Leak-Canary: sentinel never reaches saved script or review_data
# ---------------------------------------------------------------------------


class TestStory134LeakCanary:
    """AC3: TestCase step credential data must never appear in the saved script or review_data warnings."""

    @pytest.mark.asyncio
    async def test_sentinel_absent_from_script_content_and_warnings(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """Sentinel in TestCase.step.data must not appear in GeneratedScript.script_content or warnings."""
        from ai_qa.agents.sarah import SarahAgent

        # TestCase with a step that carries a sentinel credential value
        sentinel = "S3CRET-SENTINEL"
        auth_test_case = TestCase(
            title="Login with credentials",
            preconditions=["User has a valid account"],
            steps=[
                TestCaseStep(
                    number=1,
                    action="Enter username",
                    target="username field",
                    data="testuser",
                ),
                TestCaseStep(
                    number=2,
                    action="Enter password",
                    target="password field",
                    data=sentinel,
                ),
                TestCaseStep(number=3, action="Click login button", target="login button"),
            ],
            expected_results=["User is logged in"],
        )

        # Mocked LLM follows the prompt: no credentials, uses SSO session assumption
        clean_script_content = (
            "def test_login_with_credentials(page):\n"
            "    # REVIEW: SSO/session setup required before execution\n"
            '    page.goto("https://app.example.com")\n'
            "    # Step 1: skipped â€” test assumes pre-authenticated SSO session\n"
            "    # Step 2: skipped â€” test assumes pre-authenticated SSO session\n"
            "    # Step 3: skip login step\n"
            '    expect(page).to_have_url("/dashboard")\n'
        )

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent._test_cases = [auth_test_case]

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_gen_class:
            mock_gen = MagicMock()
            mock_gen_class.return_value = mock_gen
            mock_gen._generate_script_header.return_value = "# Generated header\n"
            mock_gen._generate_filename.return_value = "test_login_with_credentials.py"
            # LLM mock returns clean script (no sentinel)
            mock_gen.generate = AsyncMock(
                return_value=StageResult(
                    success=True,
                    data=[
                        {
                            "script_content": clean_script_content,
                            "test_case_title": auth_test_case.title,
                            "confidence": 0.75,
                            # Warnings are category-prefixed, redacted â€” no sentinel
                            "warnings": [
                                "REVIEW: SSO/session setup required before execution",
                                "SSO/session setup required: this test targets an authenticated area â€” "
                                "run it against a pre-authenticated browser context (existing SSO session); "
                                "no login automation or credentials are included",
                            ],
                        }
                    ],
                    errors=[],
                    warnings=[],
                    confidence=0.75,
                )
            )

            await agent._generate_scripts()

        assert len(agent._generated_scripts) == 1
        gs = agent._generated_scripts[0]

        # AC3: sentinel must NOT appear in the script content
        assert sentinel not in gs.script_content, (
            f"Sentinel '{sentinel}' leaked into GeneratedScript.script_content"
        )

        # AC3: sentinel must NOT appear in any warning string
        for w in gs.warnings:
            assert sentinel not in w, f"Sentinel '{sentinel}' leaked into warning: {w}"

    @pytest.mark.asyncio
    async def test_sentinel_absent_from_save_script_payload(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context,
    ) -> None:
        """Sentinel in TestCase.step.data must not appear in the save_script payload on approve."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        sentinel = "S3CRET-SENTINEL"
        auth_test_case = TestCase(
            title="Login flow",
            steps=[
                TestCaseStep(
                    number=1,
                    action="Enter password",
                    target="password field",
                    data=sentinel,
                )
            ],
        )
        # Clean script content â€” the LLM follows the session-reuse prompt
        clean_script = (
            "def test_login_flow(page):\n"
            "    # REVIEW: SSO/session setup required before execution\n"
            '    page.goto("https://app.example.com")\n'
        )

        with patch("ai_qa.agents.sarah.PipelineArtifactAdapter") as mock_adapter_class:
            mock_adapter = MagicMock()
            mock_adapter_class.return_value = mock_adapter

            agent = SarahAgent(workspace_dir=tmp_path)
            agent.project_context = mock_project_context

            gs = GeneratedScript(
                test_case=auth_test_case,
                script_content=clean_script,
                file_path="test_login_flow.py",
                confidence=0.75,
                warnings=["SSO/session setup required: this test targets an authenticated area"],
            )
            agent._generated_scripts.append(gs)
            agent._current_review_index = 0
            agent.state = AgentState.REVIEW_REQUEST
            agent.phase = "script_review"

            await agent.handle_approve()

            # Verify save_script was called
            assert mock_adapter.save_script.called
            save_args = mock_adapter.save_script.call_args
            saved_content: str = save_args[0][1]  # second positional arg = script content

            # AC3: sentinel must NOT appear in the saved content
            assert sentinel not in saved_content, (
                f"Sentinel '{sentinel}' leaked into save_script payload"
            )


# -----------------------------------------------------------------------------
# 13.7 â€” Approval metadata, reject-clear, feedback-into-regeneration, eligibility
# -----------------------------------------------------------------------------


class TestSarahApprovalMetadata:
    """Story 13.7: approve stamps approved_by/approved_at; reject clears them.

    Tests use the mock_project_context fixture (from conftest.py) which has
    .user_email = "test@example.com" and .user_id = UUID(...).
    """

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch("ai_qa.agents.sarah.PipelineArtifactAdapter") as mock_adapter_class:
            self.mock_adapter = MagicMock()
            mock_adapter_class.return_value = self.mock_adapter
            yield mock_adapter_class

    def _make_agent(self, tmp_path: Path, tc: TestCase, mock_project_context: Any) -> Any:
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"
        script = GeneratedScript(
            test_case=tc,
            script_content="# test script",
            file_path=str(tmp_path / "testscripts" / f"{tc.filename}.py"),
            confidence=0.85,
        )
        agent._generated_scripts.append(script)
        agent._current_review_index = 0
        agent.state = AgentState.REVIEW_REQUEST
        return agent

    @pytest.mark.asyncio
    async def test_approve_stamps_approved_by_and_approved_at(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """AC1: approve sets approved_by=user_email and approved_at to an ISO string."""
        agent = self._make_agent(tmp_path, sample_test_cases[0], mock_project_context)
        before = datetime.now(UTC)
        await agent.handle_approve({"action": "approved", "script_index": 0})
        after = datetime.now(UTC)

        script = agent._generated_scripts[0]
        assert script.approved
        assert script.approved_by == mock_project_context.user_email
        assert script.approved_at is not None
        # Ensure approved_at is a parseable ISO-8601 string within the test window
        ts = datetime.fromisoformat(script.approved_at)
        assert before <= ts <= after

    @pytest.mark.asyncio
    async def test_approve_stamps_user_id_fallback_when_email_empty(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """AC1: when user_email is empty, approved_by falls back to str(user_id)."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        ctx = MagicMock()
        ctx.user_email = ""
        ctx.user_id = mock_project_context.user_id
        ctx.project_id = mock_project_context.project_id

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = ctx
        agent.phase = "script_review"
        gs = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# test",
            file_path="test.py",
            confidence=0.9,
        )
        agent._generated_scripts.append(gs)
        agent.state = AgentState.REVIEW_REQUEST

        await agent.handle_approve({"action": "approved", "script_index": 0})

        assert agent._generated_scripts[0].approved_by == str(mock_project_context.user_id)

    @pytest.mark.asyncio
    async def test_approve_stamp_lands_after_edited_path(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """AC1: edited+valid approve also stamps approved_by/approved_at."""
        agent = self._make_agent(tmp_path, sample_test_cases[0], mock_project_context)

        edited = (
            "import asyncio\n"
            "from playwright.async_api import async_playwright\n\n"
            "async def test_login():\n"
            "    async with async_playwright() as pw:\n"
            "        browser = await pw.chromium.launch()\n"
            "        page = await browser.new_page()\n"
            "        await page.goto('https://example.com')\n"
            "        await browser.close()\n"
        )
        await agent.handle_approve(
            {"action": "approved", "script_index": 0, "script_content": edited}
        )

        script = agent._generated_scripts[0]
        assert script.approved
        assert script.approved_by == mock_project_context.user_email
        assert script.approved_at is not None

    @pytest.mark.asyncio
    async def test_invalid_edit_does_not_stamp(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """13.6 preserved: validation failure â†’ no stamp, approved stays False."""
        agent = self._make_agent(tmp_path, sample_test_cases[0], mock_project_context)

        bad_edit = "def broken(\n    pass\n"
        await agent.handle_approve(
            {"action": "approved", "script_index": 0, "script_content": bad_edit}
        )

        script = agent._generated_scripts[0]
        assert not script.approved
        assert script.approved_by is None
        assert script.approved_at is None

    @pytest.mark.asyncio
    async def test_reject_clears_approved_by_and_approved_at(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """AC2/AC3: reject clears approved/approved_by/approved_at."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"

        # Pre-approve the script
        gs = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# test",
            file_path="test.py",
            confidence=0.9,
            approved=True,
            approved_by="qa@corp.vn",
            approved_at="2026-06-13T10:00:00+00:00",
        )
        agent._generated_scripts.append(gs)
        agent._current_review_index = 0
        agent._reviewed_indices.add(0)
        agent.state = AgentState.REVIEW_REQUEST

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_gen_class:
            mock_gen = MagicMock()
            mock_gen.generate = AsyncMock(
                return_value=StageResult(
                    success=True,
                    data=[
                        {
                            "script_content": "# regenerated",
                            "test_case_title": sample_test_cases[0].title,
                            "confidence": 0.8,
                            "warnings": [],
                        }
                    ],
                    errors=[],
                    warnings=[],
                    confidence=0.8,
                )
            )
            mock_gen._generate_script_header.return_value = ""
            mock_gen._generate_filename.return_value = "regen.py"
            mock_gen_class.return_value = mock_gen

            await agent.handle_reject("fix the selector", {"script_index": 0})

        # After reject, the NEW GeneratedScript at index 0 has no approval stamp
        new_script = agent._generated_scripts[0]
        assert not new_script.approved
        assert new_script.approved_by is None
        assert new_script.approved_at is None
        # Index must be removed from reviewed set
        assert 0 not in agent._reviewed_indices

    @pytest.mark.asyncio
    async def test_reject_feeds_feedback_to_script_generator(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """AC2: rejection feedback is passed to ScriptGenerator.generate as the feedback kwarg."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"
        gs = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# test",
            file_path="test.py",
            confidence=0.9,
        )
        agent._generated_scripts.append(gs)
        agent._current_review_index = 0
        agent.state = AgentState.REVIEW_REQUEST

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_gen_class:
            mock_gen = MagicMock()
            mock_gen.generate = AsyncMock(
                return_value=StageResult(
                    success=True,
                    data=[
                        {
                            "script_content": "# regen",
                            "test_case_title": sample_test_cases[0].title,
                            "confidence": 0.8,
                            "warnings": [],
                        }
                    ],
                    errors=[],
                    warnings=[],
                    confidence=0.8,
                )
            )
            mock_gen._generate_script_header.return_value = ""
            mock_gen._generate_filename.return_value = "regen.py"
            mock_gen_class.return_value = mock_gen

            await agent.handle_reject("fix the selector", {"script_index": 0})

        # ScriptGenerator.generate must have been called with feedback="fix the selector"
        mock_gen.generate.assert_called_once()
        call_kwargs = mock_gen.generate.call_args.kwargs
        assert call_kwargs.get("feedback") == "fix the selector"

    @pytest.mark.asyncio
    async def test_skip_does_not_save_and_stays_unapproved(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """AC3: skipped script â†’ save_script NOT called; approved stays False (structural)."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"

        for tc in sample_test_cases:
            gs = GeneratedScript(
                test_case=tc,
                script_content="# test",
                file_path=f"{tc.filename}.py",
                confidence=0.9,
            )
            agent._generated_scripts.append(gs)
        agent._current_review_index = 0
        agent.state = AgentState.REVIEW_REQUEST

        await agent.handle_approve({"action": "skip", "script_index": 0})

        self.mock_adapter.save_script.assert_not_called()
        assert not agent._generated_scripts[0].approved

    @pytest.mark.asyncio
    async def test_payload_carries_approved_by_and_approved_at_after_approve(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """AC1: after approve the re-emitted script_review payload has approved_by/approved_at."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"

        # Two scripts: approve index 0, then index 1 will trigger the re-present
        for tc in sample_test_cases:
            gs = GeneratedScript(
                test_case=tc,
                script_content="# test",
                file_path=f"{tc.filename}.py",
                confidence=0.9,
            )
            agent._generated_scripts.append(gs)
        agent._current_review_index = 0
        agent.state = AgentState.REVIEW_REQUEST

        await agent.handle_approve({"action": "approved", "script_index": 0})

        # Find the script_review payload in the broadcast calls
        review_calls = [
            call[0][0]
            for call in mock_broadcast.call_args_list
            if (call[0][0].metadata or {}).get("type") == "script_review"
        ]
        assert review_calls, "Expected a script_review payload to be emitted"
        scripts = review_calls[-1].metadata["scripts"]
        approved_entry = next((s for s in scripts if s["index"] == 0), None)
        assert approved_entry is not None
        assert approved_entry["approved_by"] == mock_project_context.user_email
        assert approved_entry["approved_at"] is not None


# =============================================================================
# Story 13.8 â€” Test Script Artifact Save
# =============================================================================


class TestSarahArtifactSave138:
    """Story 13.8: approved-only side-car, real metadata, .py fallback, idempotency."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch("ai_qa.agents.sarah.PipelineArtifactAdapter") as mock_adapter_class:
            self.mock_adapter = MagicMock()
            mock_adapter_class.return_value = self.mock_adapter
            yield mock_adapter_class

    def _make_agent_with_scripts(
        self,
        tmp_path: Path,
        mock_project_context: Any,
        *,
        approved_count: int = 1,
        skipped_count: int = 0,
        failed_count: int = 0,
        source_tc_id: str | None = "artifact-uuid-1234",
    ) -> Any:
        """Build a SarahAgent with a seeded _generated_scripts list for DONE-path tests."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent
        from ai_qa.models import TestCase, TestCaseStep

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"
        agent.state = AgentState.REVIEW_REQUEST

        def _tc(title: str) -> TestCase:
            return TestCase(
                title=title,
                steps=[TestCaseStep(number=1, action="click", target="#btn")],
            )

        for i in range(approved_count):
            gs = GeneratedScript(
                test_case=_tc(f"Approved {i}"),
                script_content=f"# approved script {i}",
                file_path=f"test_approved_{i}.py",
                confidence=0.85,
                approved=True,
                approved_by="qa@example.com",
                approved_at="2026-06-17T10:00:00+00:00",
                source_test_case_id=source_tc_id,
                validation_status="validated",
            )
            agent._generated_scripts.append(gs)
            agent._reviewed_indices.add(i)

        offset = approved_count
        for j in range(skipped_count):
            gs = GeneratedScript(
                test_case=_tc(f"Skipped {j}"),
                script_content=f"# skipped script {j}",
                file_path=f"test_skipped_{j}.py",
                confidence=0.5,
                approved=False,
                source_test_case_id=source_tc_id,
            )
            agent._generated_scripts.append(gs)
            agent._reviewed_indices.add(offset + j)

        offset += skipped_count
        for k in range(failed_count):
            gs = GeneratedScript(
                test_case=_tc(f"Failed {k}"),
                script_content="# Generation failed",
                file_path="",
                confidence=0.0,
                approved=False,
                error_message="timeout",
            )
            agent._generated_scripts.append(gs)
            # failed placeholders are NOT in _reviewed_indices (they were never reviewed)

        return agent

    # -------------------------------------------------------------------------
    # AC1: approved-only side-car
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_write_metadata_called_only_for_approved_scripts(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """_write_approved_scripts_metadata calls save_metadata ONLY for approved scripts."""
        agent = self._make_agent_with_scripts(
            tmp_path,
            mock_project_context,
            approved_count=2,
            skipped_count=1,
            failed_count=1,
        )
        await agent._write_approved_scripts_metadata()

        assert self.mock_adapter.save_metadata.call_count == 2, (
            "save_metadata must be called exactly for each approved script (not skipped/failed)"
        )

    @pytest.mark.asyncio
    async def test_write_metadata_not_called_when_all_skipped(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """When all scripts are skipped, save_metadata is never called."""
        agent = self._make_agent_with_scripts(
            tmp_path,
            mock_project_context,
            approved_count=0,
            skipped_count=2,
        )
        await agent._write_approved_scripts_metadata()

        self.mock_adapter.save_metadata.assert_not_called()

    # -------------------------------------------------------------------------
    # AC2: real metadata fields
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_write_metadata_carries_real_provenance_fields(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """Side-car metadata carries real source_test_case_id, logical_path, approved_by/at, etc."""
        agent = self._make_agent_with_scripts(
            tmp_path,
            mock_project_context,
            approved_count=1,
            source_tc_id="test-case-artifact-uuid",
        )
        await agent._write_approved_scripts_metadata()

        self.mock_adapter.save_metadata.assert_called_once()
        _, kwargs = self.mock_adapter.save_metadata.call_args
        # Positional call: (name, metadata_dict)
        call_args = self.mock_adapter.save_metadata.call_args[0]
        metadata = call_args[1]

        assert metadata["source_test_case_id"] == "test-case-artifact-uuid"
        assert metadata["logical_path"] == "test_approved_0.py"
        assert metadata["approved_by"] == "qa@example.com"
        assert metadata["approved_at"] == "2026-06-17T10:00:00+00:00"
        assert metadata["validation_status"] == "validated"
        assert metadata["confidence"] == 0.85
        assert "test_case_title" in metadata
        # Must NOT carry the old bogus source_url == filename pattern
        assert "source_url" not in metadata or metadata.get("source_url") != "test_approved_0.py"

    @pytest.mark.asyncio
    async def test_write_metadata_name_uses_test_case_filename(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """Side-car is saved as {test_case.filename}.metadata.json."""
        agent = self._make_agent_with_scripts(
            tmp_path,
            mock_project_context,
            approved_count=1,
        )
        await agent._write_approved_scripts_metadata()

        call_name = self.mock_adapter.save_metadata.call_args[0][0]
        assert call_name.endswith(".metadata.json")

    # -------------------------------------------------------------------------
    # AC1: .py fallback filename
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_approve_saves_with_py_filename_from_file_path(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
        sample_test_cases: list[TestCase],
    ) -> None:
        """When file_path is set, save_script uses the .py name from file_path."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"

        gs = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# test script",
            file_path="test_login_with_valid_credentials.py",
            confidence=0.85,
        )
        agent._generated_scripts.append(gs)
        agent._current_review_index = 0
        agent.state = AgentState.REVIEW_REQUEST

        await agent.handle_approve({"action": "approved", "script_index": 0})

        self.mock_adapter.save_script.assert_called_once()
        saved_name = self.mock_adapter.save_script.call_args[0][0]
        assert saved_name == "test_login_with_valid_credentials.py"

    @pytest.mark.asyncio
    async def test_approve_py_fallback_when_file_path_empty(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
        sample_test_cases: list[TestCase],
    ) -> None:
        """AC1: when file_path is empty, fallback name is {test_case.filename}.py (NOT .spec.ts)."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"

        gs = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# test script",
            file_path="",  # force the fallback branch
            confidence=0.85,
        )
        agent._generated_scripts.append(gs)
        agent._current_review_index = 0
        agent.state = AgentState.REVIEW_REQUEST

        await agent.handle_approve({"action": "approved", "script_index": 0})

        self.mock_adapter.save_script.assert_called_once()
        saved_name = self.mock_adapter.save_script.call_args[0][0]
        expected = f"{sample_test_cases[0].filename}.py"
        assert saved_name == expected, (
            f"Expected fallback name '{expected}' (Python .py), got '{saved_name}' â€” "
            "must NOT be .spec.ts"
        )
        assert not saved_name.endswith(".spec.ts"), "Fallback must NOT produce a .spec.ts name"

    # -------------------------------------------------------------------------
    # AC3: skip does NOT call save_script
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_skip_does_not_call_save_script(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
        sample_test_cases: list[TestCase],
    ) -> None:
        """AC3 structural: skipped scripts are never persisted (save_script not called on skip)."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"

        # Two scripts: skip first, then skip second to trigger DONE
        for tc in sample_test_cases:
            agent._generated_scripts.append(
                GeneratedScript(
                    test_case=tc,
                    script_content="# skip me",
                    file_path=f"{tc.filename}.py",
                    confidence=0.5,
                )
            )
        agent._current_review_index = 0
        agent.state = AgentState.REVIEW_REQUEST

        await agent.handle_approve({"action": "skip", "script_index": 0})
        await agent.handle_approve({"action": "skip", "script_index": 1})

        self.mock_adapter.save_script.assert_not_called()

    # -------------------------------------------------------------------------
    # AC2: source_test_case_id wired through _generate_scripts
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_generate_scripts_carries_source_test_case_id(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """source_test_case_id is threaded from _test_case_source_ids onto GeneratedScript."""
        from ai_qa.agents.sarah import SarahAgent
        from ai_qa.models import TestCase, TestCaseStep

        tc = TestCase(
            title="Source ID test",
            steps=[TestCaseStep(number=1, action="click", target="#btn")],
        )
        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent._test_cases = [tc]
        agent._test_case_source_ids = ["artifact-id-5678"]

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_gen_class:
            mock_gen = MagicMock()
            mock_gen_class.return_value = mock_gen
            mock_gen._generate_script_header.return_value = "# header\n"
            mock_gen._generate_filename.return_value = "test_source_id_test.py"
            mock_gen.generate = AsyncMock(
                return_value=StageResult(
                    success=True,
                    data=[{"script_content": "def test_src(page): pass", "confidence": 0.8}],
                    errors=[],
                    warnings=[],
                    confidence=0.8,
                )
            )

            await agent._generate_scripts()

        assert len(agent._generated_scripts) == 1
        assert agent._generated_scripts[0].source_test_case_id == "artifact-id-5678"

    @pytest.mark.asyncio
    async def test_generate_scripts_source_id_none_when_ids_list_empty(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """When _test_case_source_ids is empty (fallback path), source_test_case_id is None."""
        from ai_qa.agents.sarah import SarahAgent
        from ai_qa.models import TestCase, TestCaseStep

        tc = TestCase(
            title="Fallback path test",
            steps=[TestCaseStep(number=1, action="click", target="#btn")],
        )
        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent._test_cases = [tc]
        agent._test_case_source_ids = []  # fallback: no IDs available

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_gen_class:
            mock_gen = MagicMock()
            mock_gen_class.return_value = mock_gen
            mock_gen._generate_script_header.return_value = "# header\n"
            mock_gen._generate_filename.return_value = "test_fallback_path_test.py"
            mock_gen.generate = AsyncMock(
                return_value=StageResult(
                    success=True,
                    data=[{"script_content": "def test_fb(page): pass", "confidence": 0.7}],
                    errors=[],
                    warnings=[],
                    confidence=0.7,
                )
            )

            await agent._generate_scripts()

        assert len(agent._generated_scripts) == 1
        assert agent._generated_scripts[0].source_test_case_id is None

    # -------------------------------------------------------------------------
    # AC2: validation_status stamped on validated-edit path
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_approve_validated_edit_stamps_validation_status(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
        sample_test_cases: list[TestCase],
    ) -> None:
        """When edited content passes validation, validation_status='validated' on GeneratedScript."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"

        gs = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# original",
            file_path="test_x.py",
            confidence=0.8,
        )
        agent._generated_scripts.append(gs)
        agent._current_review_index = 0
        agent.state = AgentState.REVIEW_REQUEST

        valid_edit = (
            "from playwright.async_api import async_playwright\n\n"
            "async def test_x():\n"
            "    async with async_playwright() as pw:\n"
            "        browser = await pw.chromium.launch()\n"
            "        page = await browser.new_page()\n"
            "        await page.goto('https://example.com')\n"
            "        await browser.close()\n"
        )
        await agent.handle_approve(
            {"action": "approved", "script_index": 0, "script_content": valid_edit}
        )

        assert agent._generated_scripts[0].validation_status == "validated"

    @pytest.mark.asyncio
    async def test_approve_no_edit_leaves_validation_status_none(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
        sample_test_cases: list[TestCase],
    ) -> None:
        """When no edit is provided, validation_status stays None (original content path)."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"

        gs = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# original",
            file_path="test_y.py",
            confidence=0.8,
        )
        agent._generated_scripts.append(gs)
        agent._current_review_index = 0
        agent.state = AgentState.REVIEW_REQUEST

        await agent.handle_approve({"action": "approved", "script_index": 0})

        assert agent._generated_scripts[0].validation_status is None


# =============================================================================
# Review-fix hardening (C3, C4, C15/C16, C17/C18, C20, C37/C38, C39)
# =============================================================================


class TestSarahReviewFixHardening:
    """Tests for the 13.7/13.8 review-fix patches layered onto sarah.py."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch("ai_qa.agents.sarah.PipelineArtifactAdapter") as mock_adapter_class:
            self.mock_adapter = MagicMock()
            mock_adapter_class.return_value = self.mock_adapter
            self.mock_adapter.service.list_artifacts.return_value = []
            yield mock_adapter_class

    def _agent_in_review(self, tmp_path: Path, mock_project_context: Any) -> Any:
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"
        agent.state = AgentState.REVIEW_REQUEST
        return agent

    # -------------------------------------------------------------------------
    # C3: failed-generation placeholder is not approvable
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_c3_placeholder_not_approvable(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """C3: approving a script with error_message set is rejected â€” no save, no advance."""
        from ai_qa.agents.sarah import GeneratedScript

        agent = self._agent_in_review(tmp_path, mock_project_context)
        placeholder = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# Generation failed: timeout",
            file_path="",
            confidence=0.0,
            approved=False,
            error_message="timeout",
        )
        agent._generated_scripts.append(placeholder)
        agent._current_review_index = 0

        await agent.handle_approve({"action": "approved", "script_index": 0})

        # Not approved, not saved, not in reviewed set, stays REVIEW_REQUEST
        assert not agent._generated_scripts[0].approved
        self.mock_adapter.save_script.assert_not_called()
        assert 0 not in agent._reviewed_indices
        assert agent.state == AgentState.REVIEW_REQUEST

    # -------------------------------------------------------------------------
    # C4: per-run state reset on a fresh handle_start
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_c4_fresh_start_resets_per_run_state(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """C4: a fresh handle_start (not chrome-path re-entry) clears stale run state."""
        from uuid import uuid4

        from ai_qa.agents.sarah import GeneratedScript, SarahAgent
        from ai_qa.pipelines.artifact_adapter import PipelineArtifact

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context

        # Seed stale state from a "previous run"
        agent.phase = "script_review"
        agent.confirmed_test_cases = [sample_test_cases[0]]
        agent.candidate_test_cases = [MagicMock()]
        agent._generated_scripts = [
            GeneratedScript(
                test_case=sample_test_cases[0],
                script_content="# stale",
                file_path="stale.py",
                confidence=0.5,
            )
        ]
        agent._reviewed_indices = {0}
        agent._test_case_source_ids = ["stale-id"]
        agent._current_review_index = 3
        agent._awaiting_inputs = False  # NOT a chrome-path re-entry

        # New approved test case available for the fresh run
        art = MagicMock(spec=PipelineArtifact)
        art.id = uuid4()
        art.name = "tc-new.json"
        art.thread_id = None
        art.content = json.dumps({"title": "New"})
        self.mock_adapter.load_approved_test_cases.return_value = [art]

        await agent.handle_start({})

        # All per-run state reset before the selection gate ran
        assert agent.phase == "input_selection"
        assert agent.confirmed_test_cases == []
        assert agent._generated_scripts == []
        assert agent._reviewed_indices == set()
        assert agent._test_case_source_ids == []
        assert agent._current_review_index == 0

    @pytest.mark.asyncio
    async def test_c4_begin_generation_sets_awaiting_flag_when_no_chrome_path(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """C4: _begin_generation sets _awaiting_inputs when Chrome path is missing."""
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent._chrome_path = None

        await agent._begin_generation()

        assert agent._awaiting_inputs

    # -------------------------------------------------------------------------
    # C15/C16: reject â†’ regen â†’ approve preserves source_test_case_id
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_c15_regen_success_preserves_source_test_case_id(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """C15: a successful regeneration carries source_test_case_id onto the replacement."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"
        agent.state = AgentState.REVIEW_REQUEST
        gs = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# original",
            file_path="test_login.py",
            confidence=0.9,
            source_test_case_id="tc-artifact-9999",
        )
        agent._generated_scripts.append(gs)
        agent._current_review_index = 0

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_gen_class:
            mock_gen = MagicMock()
            mock_gen.generate = AsyncMock(
                return_value=StageResult(
                    success=True,
                    data=[{"script_content": "# regenerated", "confidence": 0.8}],
                    errors=[],
                    warnings=[],
                    confidence=0.8,
                )
            )
            mock_gen._generate_script_header.return_value = ""
            mock_gen._generate_filename.return_value = "test_login.py"
            mock_gen_class.return_value = mock_gen

            await agent.handle_reject("fix the selector", {"script_index": 0})

        # The replacement (new object) preserved the source id
        assert agent._generated_scripts[0].source_test_case_id == "tc-artifact-9999"
        # And then approving stamps it through to the saved metadata path
        await agent.handle_approve({"action": "approved", "script_index": 0})
        assert agent._generated_scripts[0].approved
        assert agent._generated_scripts[0].source_test_case_id == "tc-artifact-9999"

    @pytest.mark.asyncio
    async def test_c16_regen_failure_placeholder_carries_source_id(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """C16: a failed regeneration leaves a placeholder carrying source_test_case_id."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"
        agent.state = AgentState.REVIEW_REQUEST
        gs = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# original",
            file_path="test_login.py",
            confidence=0.9,
            source_test_case_id="tc-artifact-1111",
        )
        agent._generated_scripts.append(gs)
        agent._current_review_index = 0

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_gen_class:
            mock_gen = MagicMock()
            mock_gen.generate = AsyncMock(
                return_value=StageResult(
                    success=False,
                    data=None,
                    errors=["LLM unavailable"],
                    warnings=[],
                    confidence=0.0,
                )
            )
            mock_gen._generate_script_header.return_value = ""
            mock_gen._generate_filename.return_value = "test_login.py"
            mock_gen_class.return_value = mock_gen

            await agent._regenerate_current_script("fix the selector")

        placeholder = agent._generated_scripts[0]
        assert placeholder.error_message is not None
        assert placeholder.source_test_case_id == "tc-artifact-1111"
        assert not placeholder.approved

    # -------------------------------------------------------------------------
    # C17/C18: distinct titles colliding on filename â†’ distinct artifacts + 1:1 sidecar
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_c17_colliding_filenames_produce_distinct_artifacts(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """C17: two scripts with the same base .py name save under distinct artifact names."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent
        from ai_qa.models import TestCase, TestCaseStep

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"
        agent.state = AgentState.REVIEW_REQUEST

        def _tc(title: str) -> TestCase:
            return TestCase(title=title, steps=[TestCaseStep(number=1, action="x", target="#b")])

        # Both scripts deliberately share the same file_path â†’ colliding base names
        for i, src in enumerate(("tc-aaa", "tc-bbb")):
            agent._generated_scripts.append(
                GeneratedScript(
                    test_case=_tc(f"Case {i}"),
                    script_content=f"# script {i}",
                    file_path="test_dupe.py",
                    confidence=0.8,
                    source_test_case_id=src,
                )
            )
        agent._current_review_index = 0

        await agent.handle_approve({"action": "approved", "script_index": 0})
        await agent.handle_approve({"action": "approved", "script_index": 1})

        saved_names = [c[0][0] for c in self.mock_adapter.save_script.call_args_list]
        assert len(saved_names) == 2
        # The two saved artifact names must be distinct
        assert len(set(saved_names)) == 2, f"Expected distinct names, got {saved_names}"
        # The recorded saved_file_name matches what was passed to save_script
        assert agent._generated_scripts[0].saved_file_name == saved_names[0]
        assert agent._generated_scripts[1].saved_file_name == saved_names[1]

    @pytest.mark.asyncio
    async def test_c18_sidecar_name_derived_from_saved_py_stem(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """C18: the sidecar name shares the stem of the saved .py (handles C17 suffix)."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent
        from ai_qa.models import TestCase, TestCaseStep

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"
        agent.state = AgentState.REVIEW_REQUEST

        tc = TestCase(title="Case", steps=[TestCaseStep(number=1, action="x", target="#b")])
        gs = GeneratedScript(
            test_case=tc,
            script_content="# script",
            file_path="test_unique.py",
            confidence=0.8,
            approved=True,
            approved_by="qa@example.com",
            approved_at="2026-06-17T10:00:00+00:00",
            saved_file_name="test_unique__tc-xyz.py",
        )
        agent._generated_scripts.append(gs)

        await agent._write_approved_scripts_metadata()

        self.mock_adapter.save_metadata.assert_called_once()
        sidecar_name = self.mock_adapter.save_metadata.call_args[0][0]
        assert sidecar_name == "test_unique__tc-xyz.metadata.json"

    # -------------------------------------------------------------------------
    # C20: invalid edit â†’ NO script_review message broadcast
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_c20_invalid_edit_does_not_broadcast_script_review(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """C20: a validation failure must NOT re-emit a script_review payload (would clobber edits)."""
        from ai_qa.agents.sarah import GeneratedScript

        agent = self._agent_in_review(tmp_path, mock_project_context)
        gs = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# original",
            file_path="test_x.py",
            confidence=0.85,
        )
        agent._generated_scripts.append(gs)
        agent._current_review_index = 0

        bad_edit = "def broken(\n    pass\n"
        await agent.handle_approve(
            {"action": "approved", "script_index": 0, "script_content": bad_edit}
        )

        script_review_calls = [
            c
            for c in mock_broadcast.call_args_list
            if (c[0][0].metadata or {}).get("type") == "script_review"
        ]
        assert len(script_review_calls) == 0

    # -------------------------------------------------------------------------
    # C37/C38: malformed index degrades to out-of-range warning (no raise)
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_c37_malformed_index_in_approve_degrades_to_warning(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """C37: a non-int script_index on approve â†’ out-of-range warning, no exception."""
        from ai_qa.agents.sarah import GeneratedScript

        agent = self._agent_in_review(tmp_path, mock_project_context)
        agent._generated_scripts.append(
            GeneratedScript(
                test_case=sample_test_cases[0],
                script_content="# s",
                file_path="test_x.py",
                confidence=0.8,
            )
        )
        agent._current_review_index = 0

        await agent.handle_approve({"action": "approved", "script_index": "not-a-number"})

        self.mock_adapter.save_script.assert_not_called()
        warnings = [c for c in mock_broadcast.call_args_list if c[0][0].message_type == "warning"]
        assert len(warnings) >= 1

    @pytest.mark.asyncio
    async def test_c38_malformed_index_in_reject_and_skip_degrade(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """C38: a non-int script_index on reject/skip â†’ warning, no exception."""
        from ai_qa.agents.sarah import GeneratedScript

        agent = self._agent_in_review(tmp_path, mock_project_context)
        agent._generated_scripts.append(
            GeneratedScript(
                test_case=sample_test_cases[0],
                script_content="# s",
                file_path="test_x.py",
                confidence=0.8,
            )
        )
        agent._current_review_index = 0

        # reject with malformed index â€” must not raise
        await agent.handle_reject("fix", {"script_index": {"bad": "type"}})
        # skip with malformed index â€” must not raise
        await agent.handle_approve({"action": "skip", "script_index": [1, 2]})

        # No regeneration / no DONE; warnings emitted for both
        warnings = [c for c in mock_broadcast.call_args_list if c[0][0].message_type == "warning"]
        assert len(warnings) >= 2

    # -------------------------------------------------------------------------
    # C39: final-approval caption re-emitted before DONE
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_c39_final_approval_reemits_script_review_before_done(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """C39: approving the last script re-emits script_review (with the stamp) before DONE."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.phase = "script_review"
        agent.state = AgentState.REVIEW_REQUEST

        gs = GeneratedScript(
            test_case=sample_test_cases[0],
            script_content="# only script",
            file_path="test_only.py",
            confidence=0.9,
        )
        agent._generated_scripts.append(gs)
        agent._current_review_index = 0

        await agent.handle_approve({"action": "approved", "script_index": 0})

        # DONE reached
        assert agent.state == AgentState.DONE
        # A script_review payload was emitted whose approved entry carries the stamp
        review_calls = [
            c[0][0]
            for c in mock_broadcast.call_args_list
            if (c[0][0].metadata or {}).get("type") == "script_review"
        ]
        assert len(review_calls) >= 1
        scripts = review_calls[-1].metadata["scripts"]
        approved_entry = next(s for s in scripts if s["index"] == 0)
        assert approved_entry["status"] == "approved"
        assert approved_entry["approved_by"] == mock_project_context.user_email
        assert approved_entry["approved_at"] is not None


class TestSarahRolePropagation:
    """Slice 5: role-bearing scripts land under a ``<role>/`` sub-folder + carry role metadata."""

    @staticmethod
    def _script(*, role: str | None, file_path: str, sid: str | None = None) -> Any:
        from ai_qa.agents.sarah import GeneratedScript

        tc = TestCase(
            title="Login",
            role=role,
            steps=[TestCaseStep(number=1, action="Click", target="the Login button")],
        )
        return GeneratedScript(
            test_case=tc,
            script_content="# script",
            file_path=file_path,
            confidence=0.9,
            approved=True,
            source_test_case_id=sid,
        )

    def _agent(self, tmp_path: Path, scripts: list[Any]) -> Any:
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent._generated_scripts = scripts
        return agent

    def test_role_script_saved_flat(self, tmp_path: Path) -> None:
        scripts = [self._script(role="Admin", file_path="test_login.py")]
        agent = self._agent(tmp_path, scripts)
        assert agent._unique_script_name(scripts[0], 0) == "test_login.py"

    def test_same_base_different_roles_collide_with_suffix(self, tmp_path: Path) -> None:
        scripts = [
            self._script(role="Admin", file_path="test_login.py", sid="a1"),
            self._script(role="User", file_path="test_login.py", sid="u1"),
        ]
        agent = self._agent(tmp_path, scripts)
        # Without role folders separating them, they collide at the flat root.
        # Both are suffixed because they collide with each other.
        assert agent._unique_script_name(scripts[0], 0) == "test_login__a1.py"
        assert agent._unique_script_name(scripts[1], 1) == "test_login__u1.py"

    def test_same_base_same_role_collides_with_suffix(self, tmp_path: Path) -> None:
        scripts = [
            self._script(role="Admin", file_path="test_login.py", sid="a1"),
            self._script(role="Admin", file_path="test_login.py", sid="a2"),
        ]
        agent = self._agent(tmp_path, scripts)
        assert agent._unique_script_name(scripts[1], 1) == "test_login__a2.py"

    @pytest.mark.asyncio
    async def test_sidecar_flat_name_preserves_role_field(
        self, tmp_path: Path, mock_project_context
    ) -> None:
        script = self._script(role="Admin", file_path="test_login.py", sid="a1")
        script.saved_file_name = "test_login.py"  # as handle_approve would set it
        script.approved_by = "qa@example.com"
        script.approved_at = "2026-06-21T00:00:00Z"
        agent = self._agent(tmp_path, [script])
        agent.project_context = mock_project_context

        with patch("ai_qa.agents.sarah.PipelineArtifactAdapter") as mock_adapter_class:
            mock_adapter = MagicMock()
            mock_adapter_class.return_value = mock_adapter
            await agent._write_approved_scripts_metadata()

        call = mock_adapter.save_metadata.call_args
        sidecar_name = call.args[0]
        payload = call.args[1]
        # Sidecar is flat, but metadata role remains intact.
        assert sidecar_name == "test_login.metadata.json"
        assert payload["role"] == "Admin"
        assert payload["source_test_case_id"] == "a1"


# -----------------------------------------------------------------------------
# Story 16.12: lazy LLM-config resolution (auth-bug fix) + graceful degradation
# -----------------------------------------------------------------------------


class TestSarahLazyLLMConfigAuthFix:
    """16.12: the deterministic script generator must use the CONTEXT-RESOLVED key.

    Sarah captured an empty-key ``LLMConfig`` at ``__init__`` (before the project context,
    and thus the per-user encrypted secret, was attached). That stale config surfaced at
    generation time as the raw provider auth error "Could not resolve authentication
    method", aborting the whole batch with an empty Scripts folder. ``_ensure_llm_ready()``
    re-resolves the config against the attached context before every generation path; a
    per-test-case failure now degrades to a skip-only placeholder instead of aborting.
    """

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        with patch("ai_qa.agents.sarah.PipelineArtifactAdapter") as mock_adapter_class:
            self.mock_adapter = MagicMock()
            mock_adapter_class.return_value = self.mock_adapter
            self.mock_adapter.service.list_artifacts.return_value = []
            yield mock_adapter_class

    def test_init_captures_empty_key_placeholder(
        self, tmp_path: Path, mock_project_context: Any
    ) -> None:
        """The __init__ config is an empty-key placeholder (the bug source we re-resolve).

        Note: the autouse ``_stub_sarah_llm_config`` patches ``get_llm_config`` at class
        level, so ``__init__``'s call returns the stub placeholder.  The first assert
        documents the expected placeholder state; the second assert verifies the fix —
        that ``_ensure_llm_ready()`` actually changes the config to the context-resolved
        key when called with a real credential.
        """
        from ai_qa.agents.sarah import SarahAgent
        from ai_qa.ai_connection.config import LLMConfig

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        # The placeholder resolved before the context was attached carries no api_key.
        assert agent.config.api_key == ""

        # After attaching context, _ensure_llm_ready must update self.config to the
        # resolved key — this is the actual fix (mirrors Mary's pattern).
        agent.get_llm_config = MagicMock(  # type: ignore[method-assign]
            return_value=LLMConfig(
                provider="claude", model_name="claude-test", api_key="resolved-key"
            )
        )
        agent._ensure_llm_ready()
        assert agent.config.api_key == "resolved-key"

    @pytest.mark.asyncio
    async def test_begin_generation_uses_context_resolved_key(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """AC1/AC4: the ScriptGenerator is built with the context-resolved key, not the
        empty-key __init__ placeholder."""
        from ai_qa.agents.sarah import SarahAgent
        from ai_qa.ai_connection.config import LLMConfig

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        # Bug source: __init__ placeholder has no key.
        assert agent.config.api_key == ""
        # The context now resolves a real per-user key.
        agent.get_llm_config = MagicMock(  # type: ignore[method-assign]
            return_value=LLMConfig(provider="claude", model_name="claude-test", api_key="test-key")
        )
        agent.phase = "script_review"
        agent.confirmed_test_cases = [sample_test_cases[0]]
        agent._test_case_source_ids = [None]
        # Both inputs present so _begin_generation proceeds straight to generation.
        agent._target_url = "https://app.example.com"
        agent._chrome_path = "/usr/bin/chrome"

        with (
            patch("ai_qa.agents.sarah.ScriptGenerator") as mock_gen_class,
            patch("ai_qa.browser.llm_factory.build_browser_use_llm", return_value=MagicMock()),
        ):
            mock_gen = MagicMock()
            mock_gen.generate = AsyncMock(
                return_value=StageResult(
                    success=True,
                    data=[{"script_content": "# code", "confidence": 0.9, "warnings": []}],
                    errors=[],
                    warnings=[],
                    confidence=0.9,
                )
            )
            mock_gen._generate_script_header.return_value = "# h"
            mock_gen._generate_filename.return_value = "f.py"
            mock_gen_class.return_value = mock_gen

            await agent._begin_generation()

        # self.config was refreshed from the empty placeholder to the resolved key.
        assert agent.config.api_key == "test-key"
        # And the deterministic ScriptGenerator was constructed with that resolved config.
        construct = mock_gen_class.call_args
        assert construct is not None
        assert construct.kwargs["llm_config"].api_key == "test-key"

    @pytest.mark.asyncio
    async def test_handle_start_errors_cleanly_on_genuinely_missing_key(
        self,
        tmp_path: Path,
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """AC5/Task 1: a genuinely missing key fails fast with a UX-DR12 message (ERROR),
        not a raw provider auth error mid-generation."""
        from ai_qa.agents.sarah import SarahAgent
        from ai_qa.exceptions import PipelineError

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        # An approved candidate exists, so handle_start reaches the config resolve.
        self.mock_adapter.load_approved_test_cases.return_value = [MagicMock()]
        # The context cannot resolve a key → get_llm_config raises the UX-DR12 PipelineError.
        agent.get_llm_config = MagicMock(  # type: ignore[method-assign]
            side_effect=PipelineError(
                "**What happened:** Claude API key not configured.\n\n"
                "**Why:** The secret is required but was not found.\n\n"
                "**What to do:** Add your Claude API key and try again."
            )
        )

        await agent.handle_start({})

        assert agent.state == AgentState.ERROR
        # The selection panel must NOT have been presented (we failed before it).
        selection_calls = [
            c
            for c in mock_broadcast.call_args_list
            if c[0][0].metadata and c[0][0].metadata.get("type") == "test_case_selection"
        ]
        assert selection_calls == []
        # An actionable UX-DR12 error was surfaced.
        error_messages = [
            c[0][0].content
            for c in mock_broadcast.call_args_list
            if c[0][0].message_type == "error"
        ]
        assert any("API key" in m for m in error_messages)

    def test_build_explore_llm_returns_none_when_no_key(
        self, tmp_path: Path, mock_project_context: Any
    ) -> None:
        """AC2/AC3: with no usable driving credential, exploration is skipped (None) so
        generation can fall back to vision / LLM-only."""
        from ai_qa.agents.sarah import SarahAgent
        from ai_qa.ai_connection.config import LLMConfig

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent.get_llm_config = MagicMock(  # type: ignore[method-assign]
            return_value=LLMConfig(provider="claude", model_name="claude-test", api_key="")
        )
        assert agent._build_explore_llm() is None

    @pytest.mark.asyncio
    async def test_failed_generation_degrades_to_placeholder_not_empty_folder(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """AC3/AC4: when generation returns success=False for every test case, the batch
        still yields a skip-only placeholder per test case (never an empty-folder ERROR)."""
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        agent._test_cases = sample_test_cases
        agent._test_case_source_ids = [None] * len(sample_test_cases)

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_gen_class:
            mock_gen = MagicMock()
            # Every per-test-case generation fails (the auth-failure symptom).
            mock_gen.generate = AsyncMock(
                return_value=StageResult(
                    success=False,
                    data=None,
                    errors=["LLM Authentication failed: Could not resolve authentication method"],
                    warnings=[],
                    confidence=0.0,
                )
            )
            mock_gen._generate_script_header.return_value = "# h"
            mock_gen._generate_filename.return_value = "f.py"
            mock_gen_class.return_value = mock_gen

            result = await agent._generate_scripts()

        # Non-empty (placeholders) → the run does NOT collapse to an empty-folder ERROR.
        assert result.success
        assert len(agent._generated_scripts) == len(sample_test_cases)
        # Each placeholder is skip-only: error_message set, never approved.
        assert all(s.error_message is not None for s in agent._generated_scripts)
        assert all(not s.approved for s in agent._generated_scripts)

    @pytest.mark.asyncio
    async def test_auth_failure_surfacing_is_secret_safe(
        self,
        tmp_path: Path,
        sample_test_cases: list[TestCase],
        mock_broadcast: AsyncMock,
        mock_project_context: Any,
    ) -> None:
        """AC5 leak-canary: when generation fails on auth, neither the surfaced messages
        nor any broadcast metadata expose the resolved key or auth header names."""
        from ai_qa.agents.sarah import SarahAgent
        from ai_qa.ai_connection.config import LLMConfig

        sentinel = "sk-ant-LEAKCANARY-DO-NOT-SURFACE"
        agent = SarahAgent(workspace_dir=tmp_path)
        agent.project_context = mock_project_context
        # The context resolves a (sentinel) key — it must never reach any output channel.
        agent.get_llm_config = MagicMock(  # type: ignore[method-assign]
            return_value=LLMConfig(provider="claude", model_name="claude-test", api_key=sentinel)
        )
        agent.phase = "script_review"
        agent.confirmed_test_cases = [sample_test_cases[0]]
        agent._test_case_source_ids = [None]
        agent._target_url = "https://app.example.com"
        agent._chrome_path = "/usr/bin/chrome"

        with (
            patch("ai_qa.agents.sarah.ScriptGenerator") as mock_gen_class,
            patch("ai_qa.browser.llm_factory.build_browser_use_llm", return_value=MagicMock()),
        ):
            mock_gen = MagicMock()
            mock_gen.generate = AsyncMock(
                return_value=StageResult(
                    success=False,
                    data=None,
                    errors=[
                        'LLM Authentication failed: "Could not resolve authentication '
                        'method. Expected either api_key or auth_token to be set."'
                    ],
                    warnings=[],
                    confidence=0.0,
                )
            )
            mock_gen._generate_script_header.return_value = "# h"
            mock_gen._generate_filename.return_value = "f.py"
            mock_gen_class.return_value = mock_gen

            await agent._begin_generation()

        # Collect every surfaced channel: message content + serialized metadata.
        blob_parts: list[str] = []
        for call in mock_broadcast.call_args_list:
            msg = call[0][0]
            blob_parts.append(str(msg.content))
            if msg.metadata:
                blob_parts.append(json.dumps(msg.metadata, default=str))
        blob = "\n".join(blob_parts)

        assert sentinel not in blob
        assert "sk-ant-" not in blob
        assert "Authorization" not in blob
        assert "X-Api-Key" not in blob
        # Also check the GeneratedScript.error_message field: it is stored in memory and
        # surfaced in the _present_script_review payload to the frontend, so it must not
        # contain the resolved key either.
        for s in agent._generated_scripts:
            assert sentinel not in (s.error_message or "")
