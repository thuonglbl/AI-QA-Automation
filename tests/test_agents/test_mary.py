"""Tests for Mary agent - Test Case Generation with Per-Item Review.

Tests follow TDD pattern:
- RED: Write failing tests first
- GREEN: Implement minimal code to pass tests
- REFACTOR: Improve code structure while keeping tests green
"""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ai_qa.agents.base import AgentState
from ai_qa.ai_connection.config import LLMConfig
from ai_qa.models import StageResult, TestCase, TestCaseStep
from ai_qa.pipelines.artifact_adapter import PipelineArtifact


@pytest.fixture
def mary_agent(tmp_path: Path, mock_project_context) -> Any:
    """Create Mary agent instance with test workspace."""
    # Import here to avoid import error if file doesn't exist yet
    from ai_qa.agents.mary import MaryAgent

    agent = MaryAgent()
    agent.set_project_context(mock_project_context)
    # Mary resolves its LLM config lazily at process/clarify time (the real api_key
    # lives in the user's encrypted secret store, unreachable in unit tests). Stub it
    # so _ensure_llm_ready() doesn't reach into the mock DB and so the extractor mocks
    # injected by individual tests are exercised instead of a real LLM call.
    agent.get_llm_config = MagicMock(  # type: ignore[method-assign]
        return_value=LLMConfig(provider="claude", model_name="claude-test", api_key="test-key")
    )
    return agent


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
            title="Login with invalid credentials",
            preconditions=["User is on login page"],
            steps=[
                TestCaseStep(
                    number=1, action="Enter username", target="#username", data="testuser"
                ),
                TestCaseStep(
                    number=2, action="Enter password", target="#password", data="wrongpass"
                ),
                TestCaseStep(number=3, action="Click login button", target="#login-btn"),
            ],
            expected_results=["Error message displayed"],
            automation_hints=["Wait for error message"],
        ),
    ]


class TestMaryAgentInit:
    """Test Mary agent initialization."""

    def test_mary_agent_initialization(self, mary_agent: Any) -> None:
        """Test Mary agent has correct identity properties."""
        assert mary_agent.name == "Mary"
        assert mary_agent.color == "green"
        assert mary_agent.step_number == 3
        assert mary_agent.step_title == "Create Test Cases"
        assert mary_agent.state == AgentState.START

    def test_mary_agent_has_test_cases_list(self, mary_agent: Any) -> None:
        """Test Mary agent initializes with empty test cases list."""
        assert hasattr(mary_agent, "test_cases")
        assert mary_agent.test_cases == []

    def test_mary_agent_has_current_review_index(self, mary_agent: Any) -> None:
        """Test Mary agent initializes with current review index at 0."""
        assert hasattr(mary_agent, "current_review_index")
        assert mary_agent.current_review_index == 0


class TestMaryAgentProcess:
    """Test Mary agent process method."""

    @pytest.mark.asyncio
    async def test_process_reads_requirements_from_workspace(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """Test process reads requirements from workspace/requirements/."""
        # Create sample requirements file
        requirements_dir = tmp_path / "requirements"
        requirements_dir.mkdir(parents=True, exist_ok=True)
        (requirements_dir / "test-req.md").write_text(
            "# Sample requirements\n\nUser should be able to login"
        )

        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True,
                data=sample_test_cases,
                errors=[],
                warnings=[],
                confidence=0.9,
            )
            mary_agent.extractor = mock_extractor

            mock_adapter = MagicMock()
            mock_artifact = MagicMock()
            mock_artifact.filename = "test-req.md"
            mock_artifact.content = "content"
            mock_adapter.load_requirement_markdown.return_value = [mock_artifact]
            mock_adapter_class.return_value = mock_adapter

            result = await mary_agent.process({})

            assert result.success is True
            assert result.data == sample_test_cases
            assert mary_agent.test_cases == sample_test_cases

    @pytest.mark.asyncio
    async def test_process_sends_progress_updates(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """Test process sends progress updates for each test case."""
        # Create sample requirements file
        requirements_dir = tmp_path / "requirements"
        requirements_dir.mkdir(parents=True, exist_ok=True)
        (requirements_dir / "test-req.md").write_text("# Sample requirements")

        with (
            patch("ai_qa.api.websocket.broadcast_message") as mock_broadcast,
            patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class,
        ):
            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True,
                data=sample_test_cases,
                errors=[],
                warnings=[],
                confidence=0.9,
            )
            mary_agent.extractor = mock_extractor

            mock_adapter = MagicMock()
            mock_artifact = MagicMock()
            mock_artifact.filename = "test-req.md"
            mock_artifact.content = "content"
            mock_adapter.load_requirement_markdown.return_value = [mock_artifact]
            mock_adapter_class.return_value = mock_adapter

            await mary_agent.process({})

            # Check that progress messages were sent
            # Should send: initial message + progress for each test case
            assert mock_broadcast.call_count >= len(sample_test_cases) + 1

    @pytest.mark.asyncio
    async def test_process_handles_empty_requirements(
        self, tmp_path: Path, mary_agent: Any
    ) -> None:
        """Test process handles empty requirements directory gracefully."""
        # Create empty requirements directory
        requirements_dir = tmp_path / "requirements"
        requirements_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch("ai_qa.agents.mary.TestCaseExtractor") as mock_extractor_class,
            patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class,
        ):
            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True,
                data=[],
                errors=[],
                warnings=["No requirements found"],
                confidence=1.0,
            )
            mock_extractor_class.return_value = mock_extractor

            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = []
            mock_adapter_class.return_value = mock_adapter

            result = await mary_agent.process({})

            assert result.success is True
            assert result.data == []

    @pytest.mark.asyncio
    async def test_process_handles_extractor_failure(self, tmp_path: Path, mary_agent: Any) -> None:
        """Test process handles TestCaseExtractor failure gracefully."""
        # Create sample requirements file
        requirements_dir = tmp_path / "requirements"
        requirements_dir.mkdir(parents=True, exist_ok=True)
        (requirements_dir / "test-req.md").write_text("# Sample requirements")

        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=False,
                data=None,
                errors=["LLM call failed"],
                warnings=[],
                confidence=0.0,
            )
            mary_agent.extractor = mock_extractor

            mock_adapter = MagicMock()
            mock_artifact = MagicMock()
            mock_artifact.filename = "test-req.md"
            mock_artifact.content = "content"
            mock_adapter.load_requirement_markdown.return_value = [mock_artifact]
            mock_adapter_class.return_value = mock_adapter

            result = await mary_agent.process({})

            assert result.success is False
            assert "LLM call failed" in result.errors


class TestMaryAgentHandleApprove:
    """Test Mary agent handle_approve method."""

    @pytest.mark.asyncio
    async def test_handle_approve_marks_current_test_case_approved(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """Test handle_approve marks current test case as approved."""
        mary_agent.test_cases = sample_test_cases
        mary_agent.current_review_index = 0

        with (
            patch.object(mary_agent, "transition_to"),
            patch.object(mary_agent, "send_message"),
        ):
            await mary_agent.handle_approve()

            # Should advance to next test case
            assert mary_agent.current_review_index == 1

    @pytest.mark.asyncio
    async def test_handle_approve_transitions_to_done_when_all_approved(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """Test handle_approve transitions to DONE when all test cases approved."""
        mary_agent.test_cases = sample_test_cases
        # Pre-populate prior approvals so only the last case remains
        prior_indices = set(range(len(sample_test_cases) - 1))
        mary_agent._reviewed_indices = prior_indices
        mary_agent.current_review_index = len(sample_test_cases) - 1  # last case

        with (
            patch.object(mary_agent, "transition_to") as mock_transition,
            patch.object(mary_agent, "send_message"),
            patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class,
        ):
            mock_adapter = MagicMock()
            mock_adapter_class.return_value = mock_adapter

            await mary_agent.handle_approve()

            # Should transition to DONE
            mock_transition.assert_called_with(AgentState.DONE)

    @pytest.mark.asyncio
    async def test_handle_approve_writes_approved_test_cases(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """Test handle_approve writes approved test cases to workspace."""
        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            mock_adapter = MagicMock()
            mock_adapter_class.return_value = mock_adapter

            mary_agent.test_cases = sample_test_cases
            # Pre-populate prior approvals so only the last case remains
            prior_indices = set(range(len(sample_test_cases) - 1))
            mary_agent._reviewed_indices = prior_indices
            mary_agent.current_review_index = len(sample_test_cases) - 1

            with (
                patch.object(mary_agent, "transition_to"),
                patch.object(mary_agent, "send_message"),
            ):
                await mary_agent.handle_approve()

                # Should write all test cases
                assert mock_adapter.save_test_case.call_count == len(sample_test_cases)


class TestMaryAgentHandleReject:
    """Test Mary agent handle_reject method."""

    @pytest.mark.asyncio
    async def test_handle_reject_acknowledges_feedback(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """Test handle_reject sends acknowledgment message paraphrasing feedback."""
        feedback = "The precondition is missing"

        # A reject only happens during review, so a case must be present (C31 guard).
        mary_agent.test_cases = sample_test_cases
        mary_agent.current_review_index = 0

        with (
            patch.object(mary_agent, "transition_to"),
            patch.object(mary_agent, "send_message") as mock_send,
            patch("ai_qa.agents.mary.TestCaseExtractor") as mock_extractor_class,
            patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class,
        ):
            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True,
                data=[],
                errors=[],
                warnings=[],
                confidence=0.9,
            )
            mock_extractor_class.return_value = mock_extractor

            mock_adapter = MagicMock()
            mock_artifact = MagicMock()
            mock_artifact.filename = "test-req.md"
            mock_artifact.content = "content"
            mock_adapter.load_requirement_markdown.return_value = [mock_artifact]
            mock_adapter_class.return_value = mock_adapter

            await mary_agent.handle_reject(feedback)

            # Check acknowledgment was sent (the paraphrase is sent before any source check)
            assert mock_send.call_count >= 1
            acknowledgment_call = mock_send.call_args_list[0]
            assert "precondition" in acknowledgment_call[0][0].lower()

    @pytest.mark.asyncio
    async def test_handle_reject_regenerates_current_test_case(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """Test handle_reject re-generates the current test case with feedback (C12).

        Regeneration is scoped to the rejected case's source requirement, so the case
        must carry a ``source_requirement_id`` that matches a loaded artifact.
        """
        import uuid

        req_id = uuid.uuid4()
        sample_test_cases[0].source_requirement_id = str(req_id)

        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            mock_extractor = AsyncMock()
            regenerated_case = TestCase(
                title="Login with valid credentials (updated)",
                preconditions=["User is on login page", "User has valid credentials"],
                steps=sample_test_cases[0].steps,
                expected_results=sample_test_cases[0].expected_results,
                automation_hints=sample_test_cases[0].automation_hints,
            )
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True,
                data=[regenerated_case],
                errors=[],
                warnings=[],
                confidence=0.9,
            )
            mary_agent.extractor = mock_extractor

            mock_adapter = MagicMock()
            mock_artifact = MagicMock()
            mock_artifact.id = req_id
            mock_artifact.name = "login/requirement.md"
            mock_artifact.source_url = ""
            mock_artifact.warnings = None
            mock_artifact.content = "content"
            mock_adapter.load_requirement_markdown.return_value = [mock_artifact]
            mock_adapter_class.return_value = mock_adapter

            mary_agent.test_cases = sample_test_cases
            mary_agent.current_review_index = 0

            with (
                patch.object(mary_agent, "transition_to"),
                patch.object(mary_agent, "send_message"),
            ):
                await mary_agent.handle_reject("Add precondition about valid credentials")

                # Should replace current test case (single case → 1:1 index replacement)
                assert mary_agent.test_cases[0].title == "Login with valid credentials (updated)"
                # Regeneration carries the source forward so the case stays re-rejectable
                assert mary_agent.test_cases[0].source_requirement_id == str(req_id)

    @pytest.mark.asyncio
    async def test_handle_reject_without_source_does_not_overwrite(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """C13: a rejected case with no source requirement is NOT overwritten.

        Without an identifiable source we must not blindly take result.data[0] (an
        unrelated case); instead surface an error and re-present unchanged.
        """
        original_title = sample_test_cases[0].title
        mary_agent.test_cases = sample_test_cases
        mary_agent.current_review_index = 0
        mary_agent._reviewed_indices = {0}

        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True,
                data=[TestCase(title="Unrelated case", steps=sample_test_cases[1].steps)],
                errors=[],
                warnings=[],
                confidence=0.9,
            )
            mary_agent.extractor = mock_extractor
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = []
            mock_adapter_class.return_value = mock_adapter

            messages: list[dict[str, Any]] = []

            async def track_message(content: str = "", **kwargs: Any) -> None:
                messages.append({"content": content, "type": kwargs.get("message_type")})

            with (
                patch.object(mary_agent, "transition_to"),
                patch.object(mary_agent, "send_message", side_effect=track_message),
            ):
                await mary_agent.handle_reject("Make it better")

        # Case is unchanged (not overwritten with the unrelated case)
        assert mary_agent.test_cases[0].title == original_title
        # extractor must NOT have run (no source → bail before extraction)
        mock_extractor.extract_streaming.assert_not_called()
        # Reject still invalidated the prior decision (C2)
        assert 0 not in mary_agent._reviewed_indices
        # An error was surfaced
        assert any(m["type"] == "error" for m in messages)

    @pytest.mark.asyncio
    async def test_handle_reject_replaces_whole_group_when_multiple(self, mary_agent: Any) -> None:
        """C13: regeneration yielding multiple cases for one source replaces the WHOLE group."""
        import uuid

        req_a = str(uuid.uuid4())
        req_b = str(uuid.uuid4())
        # Two cases from req_a (a group), one from req_b
        tc_a1 = TestCase(
            title="A1",
            source_requirement_id=req_a,
            steps=[TestCaseStep(number=1, action="x", target="t")],
        )
        tc_a2 = TestCase(
            title="A2",
            source_requirement_id=req_a,
            steps=[TestCaseStep(number=1, action="x", target="t")],
        )
        tc_b1 = TestCase(
            title="B1",
            source_requirement_id=req_b,
            steps=[TestCaseStep(number=1, action="x", target="t")],
        )
        mary_agent.test_cases = [tc_a1, tc_a2, tc_b1]
        mary_agent.current_review_index = 0
        mary_agent._reviewed_indices = {2}  # req_b case already reviewed

        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True,
                data=[
                    TestCase(
                        title="A1-new", steps=[TestCaseStep(number=1, action="x", target="t")]
                    ),
                    TestCase(
                        title="A2-new", steps=[TestCaseStep(number=1, action="x", target="t")]
                    ),
                    TestCase(
                        title="A3-new", steps=[TestCaseStep(number=1, action="x", target="t")]
                    ),
                ],
                errors=[],
                warnings=[],
                confidence=0.9,
            )
            mary_agent.extractor = mock_extractor
            mock_artifact = MagicMock()
            mock_artifact.id = req_a
            mock_artifact.name = "a/requirement.md"
            mock_artifact.source_url = ""
            mock_artifact.warnings = None
            mock_artifact.content = "content"
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [mock_artifact]
            mock_adapter_class.return_value = mock_adapter

            with (
                patch.object(mary_agent, "transition_to"),
                patch.object(mary_agent, "send_message"),
            ):
                await mary_agent.handle_reject("Regenerate group", {"test_case_index": 0})

        titles = [tc.title for tc in mary_agent.test_cases]
        # Old req_a group (A1, A2) replaced by the 3 regenerated, contiguous, in place
        assert titles == ["A1-new", "A2-new", "A3-new", "B1"]
        # The req_b case (now at index 3) keeps its reviewed flag after the reindex
        assert 3 in mary_agent._reviewed_indices
        # The regenerated group is left un-reviewed (fresh decision required)
        assert {0, 1, 2}.isdisjoint(mary_agent._reviewed_indices)
        # Regenerated cases carry the source id forward
        assert all(mary_agent.test_cases[i].source_requirement_id == req_a for i in range(3))


class TestMaryAgentFormatReviewContent:
    """Test Mary agent review content formatting."""

    def test_format_review_content_includes_test_case_structure(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """Test review content includes test case title, preconditions, steps, expected results."""
        mary_agent.test_cases = sample_test_cases
        mary_agent.current_review_index = 0

        result = StageResult(success=True, data=sample_test_cases, errors=[], warnings=[])

        content = mary_agent._format_review_content(result)

        assert "Login with valid credentials" in content
        assert "preconditions" in content.lower()
        assert "steps" in content.lower()
        assert "expected" in content.lower()

    def test_format_review_content_includes_navigation_info(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """Test review content includes current position and total count."""
        mary_agent.test_cases = sample_test_cases
        mary_agent.current_review_index = 0

        result = StageResult(success=True, data=sample_test_cases, errors=[], warnings=[])

        content = mary_agent._format_review_content(result)

        assert "1 of 2" in content or "1/2" in content


class TestMaryHandleStartGate:
    """Tests for the handle_start precondition gate + approved-only filter (C30/C35)."""

    @pytest.mark.asyncio
    async def test_handle_start_blocks_when_no_approved_requirements(self, mary_agent: Any) -> None:
        """C35 / AC3: no approved requirements → UX-DR12 message, NO PROCESSING, no LLM call."""
        transitions: list[AgentState] = []
        messages: list[dict[str, Any]] = []

        async def track_transition(state: AgentState) -> None:
            transitions.append(state)

        async def track_message(content: str = "", **kwargs: Any) -> None:
            messages.append({"content": content, "type": kwargs.get("message_type")})

        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            # Only a DRAFT (source_type is None) exists → not approved
            draft = MagicMock()
            draft.source_type = None
            draft.name = "page-1.md"
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [draft]
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mary_agent.extractor = mock_extractor

            with (
                patch.object(mary_agent, "transition_to", side_effect=track_transition),
                patch.object(mary_agent, "send_message", side_effect=track_message),
            ):
                await mary_agent.handle_start({})

        # No PROCESSING transition (no generation begun)
        assert AgentState.PROCESSING not in transitions
        # extractor never invoked (no LLM call)
        mock_extractor.extract_streaming.assert_not_called()
        # A UX-DR12 error explaining Bob extraction + approval is required
        error_msgs = [m for m in messages if m["type"] == "error"]
        assert len(error_msgs) >= 1
        assert "approve" in error_msgs[0]["content"].lower()
        assert "bob" in error_msgs[0]["content"].lower()

    @pytest.mark.asyncio
    async def test_handle_start_proceeds_when_approved_present(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """C35: at least one approved requirement → PROCESSING + generation proceeds."""
        transitions: list[AgentState] = []

        async def track_transition(state: AgentState) -> None:
            transitions.append(state)

        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            approved = MagicMock()
            approved.source_type = "confluence"
            approved.id = "req-1"
            approved.name = "page-1/requirement.md"
            approved.source_url = ""
            approved.warnings = None
            approved.content = "# Requirements"
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [approved]
            mock_adapter.load_metadata.return_value = None
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True, data=sample_test_cases, errors=[], warnings=[], confidence=0.9
            )
            mary_agent.extractor = mock_extractor

            with (
                patch.object(mary_agent, "transition_to", side_effect=track_transition),
                patch.object(mary_agent, "send_message"),
                patch.object(mary_agent, "_present_test_case_review"),
                # No genuine gaps → skip the clarification loop and generate directly.
                patch.object(mary_agent, "_plan_test_clarifications", return_value=[]),
            ):
                await mary_agent.handle_start({})

        assert AgentState.PROCESSING in transitions
        mock_extractor.extract_streaming.assert_called_once()


class TestMaryProcessApprovedFilter:
    """Tests for the approved-only filter + selected_id branch in process (C19/C30)."""

    @pytest.mark.asyncio
    async def test_process_excludes_draft_requirements(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """C30: drafts (source_type IS NULL) are excluded; only approved feed generation."""
        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            draft = MagicMock()
            draft.source_type = None
            draft.id = "draft-1"
            draft.name = "p1.md"
            draft.source_url = ""
            draft.warnings = None
            draft.content = "# Draft"
            approved = MagicMock()
            approved.source_type = "confluence"
            approved.id = "appr-1"
            approved.name = "p1/requirement.md"
            approved.source_url = ""
            approved.warnings = None
            approved.content = "# Approved"
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [draft, approved]
            mock_adapter.load_metadata.return_value = None
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True, data=sample_test_cases, errors=[], warnings=[], confidence=0.9
            )
            mary_agent.extractor = mock_extractor

            await mary_agent.process({})

        # Exactly one approved source must reach the extractor (draft excluded)
        call = mock_extractor.extract_streaming.call_args
        sources_arg = call.kwargs.get("sources") or (call.args[2] if len(call.args) > 2 else None)
        assert sources_arg is not None
        assert len(sources_arg) == 1
        assert sources_arg[0].id == "appr-1"

    @pytest.mark.asyncio
    async def test_process_selected_id_filters_to_target(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """C19: input_data selected_id narrows generation to {selected_id}/requirement.md."""
        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            a1 = MagicMock()
            a1.source_type = "confluence"
            a1.id = "a1"
            a1.name = "page-1/requirement.md"
            a1.source_url = ""
            a1.warnings = None
            a1.content = "# A1"
            a2 = MagicMock()
            a2.source_type = "confluence"
            a2.id = "a2"
            a2.name = "page-2/requirement.md"
            a2.source_url = ""
            a2.warnings = None
            a2.content = "# A2"
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [a1, a2]
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True, data=sample_test_cases, errors=[], warnings=[], confidence=0.9
            )
            mary_agent.extractor = mock_extractor

            await mary_agent.process({"selected_id": "page-2"})

        # load_metadata must NOT be consulted when input_data supplies selected_id
        mock_adapter.load_metadata.assert_not_called()
        call = mock_extractor.extract_streaming.call_args
        sources_arg = call.kwargs.get("sources") or (call.args[2] if len(call.args) > 2 else None)
        assert sources_arg is not None
        assert len(sources_arg) == 1
        assert sources_arg[0].id == "a2"

    @pytest.mark.asyncio
    async def test_process_falls_back_to_metadata_selected_id(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """C19: when input_data has no selected_id, fall back to mary_selected_id.json."""
        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            a1 = MagicMock()
            a1.source_type = "confluence"
            a1.id = "a1"
            a1.name = "page-1/requirement.md"
            a1.source_url = ""
            a1.warnings = None
            a1.content = "# A1"
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [a1]
            mock_adapter.load_metadata.return_value = {"selected_id": "page-1"}
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True, data=sample_test_cases, errors=[], warnings=[], confidence=0.9
            )
            mary_agent.extractor = mock_extractor

            await mary_agent.process({})

        mock_adapter.load_metadata.assert_called_once_with("mary_selected_id.json")
        call = mock_extractor.extract_streaming.call_args
        sources_arg = call.kwargs.get("sources") or (call.args[2] if len(call.args) > 2 else None)
        assert sources_arg is not None
        assert len(sources_arg) == 1
        assert sources_arg[0].id == "a1"

    @pytest.mark.asyncio
    async def test_process_selected_id_not_found_warns_and_falls_back_to_approved(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """C19/C30: unknown selected_id → warning + fall back to ALL approved (never drafts)."""
        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            draft = MagicMock()
            draft.source_type = None
            draft.id = "draft-1"
            draft.name = "p1.md"
            draft.source_url = ""
            draft.warnings = None
            draft.content = "# Draft"
            approved = MagicMock()
            approved.source_type = "confluence"
            approved.id = "appr-1"
            approved.name = "page-1/requirement.md"
            approved.source_url = ""
            approved.warnings = None
            approved.content = "# Approved"
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [draft, approved]
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True, data=sample_test_cases, errors=[], warnings=[], confidence=0.9
            )
            mary_agent.extractor = mock_extractor

            messages: list[dict[str, Any]] = []

            async def track_message(content: str = "", **kwargs: Any) -> None:
                messages.append({"content": content, "type": kwargs.get("message_type")})

            with patch.object(mary_agent, "send_message", side_effect=track_message):
                await mary_agent.process({"selected_id": "nonexistent"})

        # A warning was sent about the unknown id
        assert any(m["type"] == "warning" and "nonexistent" in m["content"] for m in messages)
        # Fallback uses ALL approved (draft still excluded → exactly the one approved)
        call = mock_extractor.extract_streaming.call_args
        sources_arg = call.kwargs.get("sources") or (call.args[2] if len(call.args) > 2 else None)
        assert sources_arg is not None
        assert len(sources_arg) == 1
        assert sources_arg[0].id == "appr-1"


class TestMaryProcessSourceAttribution:
    """Tests for per-requirement generation and source attribution (AC1/AC3)."""

    @pytest.mark.asyncio
    async def test_process_stamps_source_requirement_id_on_test_cases(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """process() stamps each test case with source_requirement_id from the artifact."""
        import uuid

        req_id = uuid.uuid4()
        source_stamped = [
            TestCase(
                title=tc.title,
                steps=tc.steps,
                source_requirement_id=str(req_id),
                source_requirement_name="my-page/requirement.md",
            )
            for tc in sample_test_cases
        ]

        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            mock_artifact = MagicMock()
            mock_artifact.id = req_id
            mock_artifact.name = "my-page/requirement.md"
            mock_artifact.source_url = "https://confluence.example.com/page/42"
            mock_artifact.content = "# Requirements"
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [mock_artifact]
            mock_adapter.load_metadata.return_value = None
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True,
                data=source_stamped,
                errors=[],
                warnings=[],
                confidence=0.9,
            )
            mary_agent.extractor = mock_extractor

            result = await mary_agent.process({})

        assert result.success is True
        for tc in result.data or []:
            assert tc.source_requirement_id == str(req_id)

    @pytest.mark.asyncio
    async def test_process_emits_grouping_summary_message(self, mary_agent: Any) -> None:
        """process() emits a grouping summary naming each source + its count (C50)."""
        import uuid

        req_id = uuid.uuid4()
        # Two cases grouped under the same named source requirement
        grouped = [
            TestCase(
                title="Case A",
                steps=[TestCaseStep(number=1, action="A", target="t")],
                source_requirement_name="login/requirement.md",
            ),
            TestCase(
                title="Case B",
                steps=[TestCaseStep(number=1, action="B", target="t")],
                source_requirement_name="login/requirement.md",
            ),
        ]
        with (
            patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class,
            patch("ai_qa.api.websocket.broadcast_message") as mock_broadcast,
        ):
            mock_artifact = MagicMock()
            mock_artifact.id = req_id
            mock_artifact.name = "login/requirement.md"
            mock_artifact.source_type = "confluence"
            mock_artifact.source_url = ""
            mock_artifact.warnings = None
            mock_artifact.content = "# Requirements"
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [mock_artifact]
            mock_adapter.load_metadata.return_value = None
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True,
                data=grouped,
                errors=[],
                warnings=[],
                confidence=0.9,
            )
            mary_agent.extractor = mock_extractor

            await mary_agent.process({})

        all_content = " ".join(str(call) for call in mock_broadcast.call_args_list)
        # Tightened (C50): specific substrings, not just "requirement" OR "generated"
        assert "Generated 2 test case(s) across 1 requirement(s)" in all_content
        assert "login/requirement.md: 2" in all_content

    @pytest.mark.asyncio
    async def test_process_two_requirement_grouping_contiguous(self, mary_agent: Any) -> None:
        """C21: two requirements → cases stay grouped/contiguous by source in the summary."""
        import uuid

        id_a = uuid.uuid4()
        id_b = uuid.uuid4()
        # Generated order preserves requirement order: A's cases then B's case
        generated = [
            TestCase(
                title="A1",
                steps=[TestCaseStep(number=1, action="x", target="t")],
                source_requirement_name="alpha/requirement.md",
            ),
            TestCase(
                title="A2",
                steps=[TestCaseStep(number=1, action="x", target="t")],
                source_requirement_name="alpha/requirement.md",
            ),
            TestCase(
                title="B1",
                steps=[TestCaseStep(number=1, action="x", target="t")],
                source_requirement_name="beta/requirement.md",
            ),
        ]
        with (
            patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class,
            patch("ai_qa.api.websocket.broadcast_message") as mock_broadcast,
        ):
            art_a = MagicMock()
            art_a.id = id_a
            art_a.name = "alpha/requirement.md"
            art_a.source_type = "confluence"
            art_a.source_url = ""
            art_a.warnings = None
            art_a.content = "# Alpha"
            art_b = MagicMock()
            art_b.id = id_b
            art_b.name = "beta/requirement.md"
            art_b.source_type = "confluence"
            art_b.source_url = ""
            art_b.warnings = None
            art_b.content = "# Beta"
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [art_a, art_b]
            mock_adapter.load_metadata.return_value = None
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True, data=generated, errors=[], warnings=[], confidence=0.9
            )
            mary_agent.extractor = mock_extractor

            await mary_agent.process({})

        # Both approved requirements feed generation, in order
        call = mock_extractor.extract_streaming.call_args
        sources_arg = call.kwargs.get("sources") or (call.args[2] if len(call.args) > 2 else None)
        assert sources_arg is not None
        assert [s.id for s in sources_arg] == [str(id_a), str(id_b)]
        # Cases remain stored grouped/contiguous by source (requirement order preserved)
        assert [tc.source_requirement_name for tc in mary_agent.test_cases] == [
            "alpha/requirement.md",
            "alpha/requirement.md",
            "beta/requirement.md",
        ]
        # Summary names both groups with their counts (C50)
        all_content = " ".join(str(c) for c in mock_broadcast.call_args_list)
        assert "Generated 3 test case(s) across 2 requirement(s)" in all_content
        assert "alpha/requirement.md: 2" in all_content
        assert "beta/requirement.md: 1" in all_content

    @pytest.mark.asyncio
    async def test_process_passes_sources_to_extractor(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """process() passes RequirementSource list to extract_streaming so stamping works."""
        import uuid

        from ai_qa.pipelines.test_case_extractor import RequirementSource

        req_id = uuid.uuid4()
        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            mock_artifact = MagicMock()
            mock_artifact.id = req_id
            mock_artifact.name = "feat/requirement.md"
            mock_artifact.source_url = "https://conf.example.com/page/99"
            mock_artifact.content = "# Feature requirements"
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [mock_artifact]
            mock_adapter.load_metadata.return_value = None
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True,
                data=sample_test_cases,
                errors=[],
                warnings=[],
                confidence=0.9,
            )
            mary_agent.extractor = mock_extractor

            await mary_agent.process({})

        # extract_streaming must have been called with sources=
        call_kwargs = mock_extractor.extract_streaming.call_args
        assert call_kwargs is not None
        sources_arg = call_kwargs.kwargs.get("sources") or (
            call_kwargs.args[2] if len(call_kwargs.args) > 2 else None
        )
        assert sources_arg is not None, "extract_streaming must be called with sources"
        assert len(sources_arg) == 1
        assert isinstance(sources_arg[0], RequirementSource)
        assert sources_arg[0].id == str(req_id)
        assert sources_arg[0].url == "https://conf.example.com/page/99"


class TestMaryFormatReviewNewFields:
    """Tests for enriched _format_review_content showing AC1 new fields."""

    def test_format_review_shows_objective(self, mary_agent: Any) -> None:
        """Review content shows Objective when present."""
        tc = TestCase(
            title="Login Test",
            objective="Verify user can log in with valid credentials",
            steps=[TestCaseStep(number=1, action="Navigate", target="the login page")],
            expected_results=["Dashboard is shown"],
        )
        mary_agent.test_cases = [tc]
        mary_agent.current_review_index = 0

        result = StageResult(success=True, data=[tc], errors=[], warnings=[])
        content = mary_agent._format_review_content(result)

        assert "objective" in content.lower() or "Verify user can log in" in content

    def test_format_review_shows_source_requirement(self, mary_agent: Any) -> None:
        """Review content shows source requirement name/url when present."""
        tc = TestCase(
            title="Search Test",
            source_requirement_name="search/requirement.md",
            source_url="https://confluence.example.com/page/100",
            steps=[TestCaseStep(number=1, action="Enter query", target="the search input field")],
            expected_results=["Results shown"],
        )
        mary_agent.test_cases = [tc]
        mary_agent.current_review_index = 0

        result = StageResult(success=True, data=[tc], errors=[], warnings=[])
        content = mary_agent._format_review_content(result)

        assert "search/requirement.md" in content or "source" in content.lower()

    def test_format_review_shows_test_data(self, mary_agent: Any) -> None:
        """Review content shows test data list when present."""
        tc = TestCase(
            title="Login Test",
            test_data=["user@example.com", "Password123!"],
            steps=[TestCaseStep(number=1, action="Enter email", target="the email input field")],
            expected_results=["Logged in"],
        )
        mary_agent.test_cases = [tc]
        mary_agent.current_review_index = 0

        result = StageResult(success=True, data=[tc], errors=[], warnings=[])
        content = mary_agent._format_review_content(result)

        assert "user@example.com" in content or "test data" in content.lower()

    def test_format_review_shows_warnings_section(self, mary_agent: Any) -> None:
        """Review content shows ⚠ Warnings section when warnings are present."""
        tc = TestCase(
            title="Form Submit Test",
            warnings=["Ambiguous UI target in step 3: 'submit the form'"],
            steps=[TestCaseStep(number=1, action="Submit", target="the submit button")],
            expected_results=["Form submitted"],
        )
        mary_agent.test_cases = [tc]
        mary_agent.current_review_index = 0

        result = StageResult(success=True, data=[tc], errors=[], warnings=[])
        content = mary_agent._format_review_content(result)

        assert "⚠" in content or "warning" in content.lower()
        assert "Ambiguous UI target" in content


class TestMaryConfidenceScoring:
    """Tests for 12.3 confidence surface in review content and AC3 guard."""

    def test_format_review_shows_confidence_line(self, mary_agent: Any) -> None:
        """Review content shows Confidence line when confidence fields are set."""
        tc = TestCase(
            title="Scored Test",
            objective="Check something",
            steps=[TestCaseStep(number=1, action="Click", target="the button")],
            expected_results=["Done"],
            confidence=0.85,
            confidence_level="high",
            confidence_rationale=[
                "All structural fields present; no source or generation warnings"
            ],
        )
        mary_agent.test_cases = [tc]
        mary_agent.current_review_index = 0

        result = StageResult(success=True, data=[tc], errors=[], warnings=[])
        content = mary_agent._format_review_content(result)

        assert "confidence" in content.lower()
        assert "high" in content.lower() or "HIGH" in content
        assert "0.85" in content

    def test_format_review_shows_low_confidence_rationale(self, mary_agent: Any) -> None:
        """Review content shows 'Why this score' bullet list for a low-confidence case."""
        tc = TestCase(
            title="Low Case",
            confidence=0.3,
            confidence_level="low",
            confidence_rationale=[
                "Flagged LOW because unresolved warnings exist; the 0.85 score reflects structure only.",
                "Source requirement issue (vague_language): requirement is ambiguous",
            ],
            steps=[TestCaseStep(number=1, action="Do it", target="the thing")],
            expected_results=["Done"],
        )
        mary_agent.test_cases = [tc]
        mary_agent.current_review_index = 0

        result = StageResult(success=True, data=[tc], errors=[], warnings=[])
        content = mary_agent._format_review_content(result)

        assert (
            "why this score" in content.lower()
            or "confidence_rationale" in content.lower()
            or "Flagged LOW" in content
        )
        assert "vague_language" in content

    @pytest.mark.asyncio
    async def test_process_emits_warning_when_low_confidence_cases_exist(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """process() emits a warning message when k>0 low-confidence cases are generated."""
        import uuid

        low_tc = TestCase(
            title="Low Confidence Case",
            confidence_level="low",
            steps=[TestCaseStep(number=1, action="Do it", target="the thing")],
        )

        req_id = uuid.uuid4()
        with (
            patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class,
            patch("ai_qa.api.websocket.broadcast_message") as mock_broadcast,
        ):
            mock_artifact = MagicMock()
            mock_artifact.id = req_id
            mock_artifact.name = "page/requirement.md"
            mock_artifact.source_url = ""
            mock_artifact.content = "# Requirements"
            mock_artifact.warnings = None
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [mock_artifact]
            mock_adapter.load_metadata.return_value = None
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True,
                data=[low_tc],
                errors=[],
                warnings=[],
                confidence=0.3,
            )
            mary_agent.extractor = mock_extractor

            await mary_agent.process({})

        # Tightened (C50): assert the specific broadcast substrings, not just "⚠".
        all_content = " ".join(str(call) for call in mock_broadcast.call_args_list)
        assert "1 of 1 test case(s) are low confidence" in all_content
        assert "explicit review before proceeding to Sarah" in all_content

    @pytest.mark.asyncio
    async def test_process_no_warning_when_no_low_confidence_cases(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """process() omits the low-confidence warning when k==0."""
        import uuid

        high_tc = TestCase(
            title="High Confidence Case",
            confidence_level="high",
            steps=[TestCaseStep(number=1, action="Do it", target="the thing")],
        )

        req_id = uuid.uuid4()
        with (
            patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class,
            patch("ai_qa.api.websocket.broadcast_message") as mock_broadcast,
        ):
            mock_artifact = MagicMock()
            mock_artifact.id = req_id
            mock_artifact.name = "page/requirement.md"
            mock_artifact.source_url = ""
            mock_artifact.content = "# Requirements"
            mock_artifact.warnings = None
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [mock_artifact]
            mock_adapter.load_metadata.return_value = None
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True,
                data=[high_tc],
                errors=[],
                warnings=[],
                confidence=0.85,
            )
            mary_agent.extractor = mock_extractor

            await mary_agent.process({})

        # No warning about low confidence should appear
        # The "low confidence" warning message should NOT be among the broadcast calls
        warning_calls = [
            call for call in mock_broadcast.call_args_list if "low confidence" in str(call).lower()
        ]
        assert len(warning_calls) == 0

    @pytest.mark.asyncio
    async def test_handle_approve_records_reviewed_indices(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """handle_approve records the reviewed index in _reviewed_indices before advancing."""
        mary_agent.test_cases = sample_test_cases
        mary_agent.current_review_index = 0
        mary_agent._reviewed_indices = set()

        with (
            patch.object(mary_agent, "transition_to"),
            patch.object(mary_agent, "send_message"),
            patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class,
        ):
            mock_adapter = MagicMock()
            mock_adapter_class.return_value = mock_adapter

            await mary_agent.handle_approve()

        assert 0 in mary_agent._reviewed_indices

    @pytest.mark.asyncio
    async def test_ac3_guard_redirects_unreviewed_low_confidence(self, mary_agent: Any) -> None:
        """AC3 guard: if a low-confidence case is not in _reviewed_indices when the
        set has enough entries to satisfy the DONE gate, the DONE transition is blocked
        and that case is re-presented.

        This simulates a bulk-approve path that bypasses individual handle_approve calls.
        """
        low_tc = TestCase(
            title="Low Confidence",
            confidence_level="low",
            steps=[TestCaseStep(number=1, action="Do it", target="the thing")],
            expected_results=["Done"],
        )
        normal_tc = TestCase(
            title="Normal",
            confidence_level="high",
            steps=[TestCaseStep(number=1, action="Do it", target="the thing")],
            expected_results=["Done"],
        )

        # Two test cases: index 0 (low, unreviewed), index 1 (normal)
        mary_agent.test_cases = [low_tc, normal_tc]
        # Simulate: index 1 was reviewed but index 0 (low-confidence) was skipped.
        # Directly set _reviewed_indices with enough entries to pass the DONE gate but
        # missing the low-confidence index — this is the belt-and-suspenders scenario.
        mary_agent._reviewed_indices = {1, 99}  # len=2 >= 2, but index 0 missing
        mary_agent.current_review_index = 1

        transitions_called = []
        presentations = []

        async def mock_transition(state: AgentState) -> None:
            transitions_called.append(state)

        async def mock_present() -> None:
            presentations.append(True)

        with (
            patch.object(mary_agent, "transition_to", side_effect=mock_transition),
            patch.object(mary_agent, "send_message"),
            patch.object(mary_agent, "_present_test_case_review", side_effect=mock_present),
            patch("ai_qa.agents.mary.PipelineArtifactAdapter"),
        ):
            # Approve index 1 — this adds index 1 again (no-op) and triggers the DONE check
            await mary_agent.handle_approve({"test_case_index": 1})

        # Must NOT have reached DONE — the guard should have blocked and re-presented
        assert AgentState.DONE not in transitions_called, (
            "DONE must not be reached while low-confidence case is unreviewed"
        )
        # Current index must have been reset to the unreviewed low-confidence case
        assert mary_agent.current_review_index == 0
        # _present_test_case_review must have been called
        assert len(presentations) > 0

    @pytest.mark.asyncio
    async def test_ac3_guard_allows_done_after_all_reviewed(self, mary_agent: Any) -> None:
        """AC3 guard allows DONE when all low-confidence cases are in _reviewed_indices."""
        low_tc = TestCase(
            title="Low Confidence",
            confidence_level="low",
            steps=[TestCaseStep(number=1, action="Do it", target="the thing")],
            expected_results=["Done"],
        )
        mary_agent.test_cases = [low_tc]
        mary_agent.current_review_index = 0
        mary_agent._reviewed_indices = set()

        transitions_called = []

        async def mock_transition(state: AgentState) -> None:
            transitions_called.append(state)

        with (
            patch.object(mary_agent, "transition_to", side_effect=mock_transition),
            patch.object(mary_agent, "send_message"),
            patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class,
        ):
            mock_adapter_class.return_value = MagicMock()
            await mary_agent.handle_approve()

        assert AgentState.DONE in transitions_called

    @pytest.mark.asyncio
    async def test_process_passes_artifact_warnings_to_requirement_source(
        self, mary_agent: Any
    ) -> None:
        """process() feeds artifact.warnings into RequirementSource so _assess_confidence sees them."""
        import uuid

        from ai_qa.pipelines.test_case_extractor import RequirementSource

        req_id = uuid.uuid4()
        bob_warnings = [
            {
                "category": "vague_language",
                "message": "vague",
                "location": "body",
                "impact": "medium",
            }
        ]

        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            mock_artifact = MagicMock()
            mock_artifact.id = req_id
            mock_artifact.name = "feat/requirement.md"
            mock_artifact.source_url = ""
            mock_artifact.content = "# Feature"
            mock_artifact.warnings = bob_warnings
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [mock_artifact]
            mock_adapter.load_metadata.return_value = None
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True,
                data=[TestCase(title="T1", steps=[TestCaseStep(number=1, action="A", target="t")])],
                errors=[],
                warnings=[],
                confidence=0.5,
            )
            mary_agent.extractor = mock_extractor

            await mary_agent.process({})

        call_kwargs = mock_extractor.extract_streaming.call_args
        sources_arg = call_kwargs.kwargs.get("sources") or (
            call_kwargs.args[2] if len(call_kwargs.args) > 2 else None
        )
        assert sources_arg is not None
        assert isinstance(sources_arg[0], RequirementSource)
        assert sources_arg[0].warnings == bob_warnings


class TestMaryApprovalMetadata:
    """Tests for 12.4 approval metadata and full-list review payload."""

    def test_test_case_approved_by_and_approved_at_defaults(self) -> None:
        """TestCase has approved_by/approved_at defaulting to None (back-compat)."""
        tc = TestCase(
            title="Back-compat case",
            steps=[TestCaseStep(number=1, action="Do it", target="the thing")],
        )
        assert tc.approved_by is None
        assert tc.approved_at is None

    def test_test_case_round_trips_approval_fields(self) -> None:
        """TestCase with approved_by/approved_at round-trips through model_dump/model_dump_json."""
        tc = TestCase(
            title="Approved case",
            steps=[TestCaseStep(number=1, action="Do it", target="the thing")],
            approved_by="test@example.com",
            approved_at="2026-06-16T10:00:00+00:00",
        )
        dumped = tc.model_dump()
        assert dumped["approved_by"] == "test@example.com"
        assert dumped["approved_at"] == "2026-06-16T10:00:00+00:00"

        json_str = tc.model_dump_json()
        assert "test@example.com" in json_str
        assert "2026-06-16T10:00:00" in json_str

    @pytest.mark.asyncio
    async def test_handle_approve_stamps_approval_on_test_case(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """handle_approve stamps approved_by/approved_at on the approved case (AC2)."""
        mary_agent.test_cases = sample_test_cases
        mary_agent._reviewed_indices = set()
        mary_agent.current_review_index = 0

        with (
            patch.object(mary_agent, "transition_to"),
            patch.object(mary_agent, "send_message"),
            patch("ai_qa.agents.mary.PipelineArtifactAdapter"),
        ):
            await mary_agent.handle_approve({"test_case_index": 0})

        tc = sample_test_cases[0]
        assert tc.approved_by == "test@example.com"
        assert tc.approved_at is not None

    @pytest.mark.asyncio
    async def test_handle_approve_index_addressable_stamps_correct_case(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """handle_approve with test_case_index=1 stamps only index 1, not index 0."""
        mary_agent.test_cases = sample_test_cases
        mary_agent._reviewed_indices = {0}  # index 0 already reviewed
        mary_agent.current_review_index = 1

        with (
            patch.object(mary_agent, "transition_to"),
            patch.object(mary_agent, "send_message"),
            patch("ai_qa.agents.mary.PipelineArtifactAdapter"),
        ):
            await mary_agent.handle_approve({"test_case_index": 1})

        assert sample_test_cases[1].approved_by == "test@example.com"
        assert sample_test_cases[0].approved_by is None

    @pytest.mark.asyncio
    async def test_handle_reject_clears_approval_stamp(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """handle_reject clears approved_by/approved_at on the regenerated case (AC3)."""
        import uuid

        # Pre-stamp the first case as approved
        req_id = uuid.uuid4()
        sample_test_cases[0].approved_by = "test@example.com"
        sample_test_cases[0].approved_at = "2026-06-16T10:00:00+00:00"
        sample_test_cases[0].source_requirement_id = str(req_id)

        mary_agent.test_cases = sample_test_cases
        mary_agent._reviewed_indices = {0}
        mary_agent.current_review_index = 0

        regenerated = TestCase(
            title="Regenerated case",
            steps=[TestCaseStep(number=1, action="New action", target="new target")],
        )

        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True,
                data=[regenerated],
                errors=[],
                warnings=[],
                confidence=0.7,
            )
            mary_agent.extractor = mock_extractor
            mock_artifact = MagicMock()
            mock_artifact.id = req_id
            mock_artifact.name = "page/requirement.md"
            mock_artifact.source_url = ""
            mock_artifact.content = "# Requirements"
            mock_artifact.warnings = None
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [mock_artifact]
            mock_adapter_class.return_value = mock_adapter

            with (
                patch.object(mary_agent, "transition_to"),
                patch.object(mary_agent, "send_message"),
            ):
                await mary_agent.handle_reject("Needs more detail", {"test_case_index": 0})

        # The regenerated case at index 0 must not carry the prior approval stamp
        assert mary_agent.test_cases[0].approved_by is None
        assert mary_agent.test_cases[0].approved_at is None
        # Reviewed status for index 0 must have been cleared
        assert 0 not in mary_agent._reviewed_indices

    @pytest.mark.asyncio
    async def test_present_test_case_review_emits_full_list_payload(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """_present_test_case_review emits metadata.type='test_case_review' with full list."""
        mary_agent.test_cases = sample_test_cases

        sent_messages: list[dict] = []

        async def capture_send(content: str, **kwargs: Any) -> None:
            sent_messages.append({"content": content, "kwargs": kwargs})

        with patch.object(mary_agent, "send_message", side_effect=capture_send):
            await mary_agent._present_test_case_review()

        assert len(sent_messages) == 1
        meta = sent_messages[0]["kwargs"].get("metadata", {})
        assert meta.get("type") == "test_case_review"
        test_cases_payload = meta.get("test_cases", [])
        assert len(test_cases_payload) == len(sample_test_cases)
        assert test_cases_payload[0]["title"] == sample_test_cases[0].title
        # QA reviews Markdown, not a structured-JSON test case: the payload carries the
        # rendered Markdown document and review-only chrome, never the structured fields.
        assert test_cases_payload[0]["markdown"].startswith("# ")
        assert "steps" not in test_cases_payload[0]
        assert "preconditions" not in test_cases_payload[0]
        assert "low_confidence_count" in meta

    @pytest.mark.asyncio
    async def test_handle_approve_back_compat_no_index(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """handle_approve({}) with no test_case_index still advances positionally."""
        mary_agent.test_cases = sample_test_cases
        mary_agent._reviewed_indices = set()
        mary_agent.current_review_index = 0

        with (
            patch.object(mary_agent, "transition_to"),
            patch.object(mary_agent, "send_message"),
            patch("ai_qa.agents.mary.PipelineArtifactAdapter"),
        ):
            await mary_agent.handle_approve({})

        assert 0 in mary_agent._reviewed_indices
        assert mary_agent.current_review_index == 1

    @pytest.mark.asyncio
    async def test_handle_approve_reaches_done_via_index_addressable(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """Approving out-of-order (last first, then first) reaches DONE after all reviewed."""
        mary_agent.test_cases = sample_test_cases
        mary_agent._reviewed_indices = set()
        mary_agent.current_review_index = 0

        transitions: list[AgentState] = []

        async def track_transition(state: AgentState) -> None:
            transitions.append(state)

        with (
            patch.object(mary_agent, "transition_to", side_effect=track_transition),
            patch.object(mary_agent, "send_message"),
            patch("ai_qa.agents.mary.PipelineArtifactAdapter"),
        ):
            # Approve index 1 first (out of order)
            await mary_agent.handle_approve({"test_case_index": 1})
            # Now approve index 0 — this completes all reviews
            await mary_agent.handle_approve({"test_case_index": 0})

        assert AgentState.DONE in transitions


class TestMaryRoleAwareness:
    """Role plumbing: project app_roles surface in generation context + clarify prompt."""

    def test_project_app_roles_reads_and_cleans(self, mary_agent: Any) -> None:
        with patch.object(
            mary_agent, "_load_project", return_value=MagicMock(app_roles=[" Admin ", "User", " "])
        ):
            assert mary_agent._project_app_roles() == ["Admin", "User"]

    def test_project_app_roles_empty_when_unset(self, mary_agent: Any) -> None:
        with patch.object(mary_agent, "_load_project", return_value=MagicMock(app_roles=None)):
            assert mary_agent._project_app_roles() == []

    def test_generation_context_lists_available_roles(self, mary_agent: Any) -> None:
        mary_agent._overview_digest = ""
        mary_agent._clarifications = []
        with patch.object(mary_agent, "_project_app_roles", return_value=["Admin", "User"]):
            block = mary_agent._generation_context_block()
        assert "Available roles" in block
        assert "Admin, User" in block

    @pytest.mark.asyncio
    async def test_clarify_prompt_asks_for_role_when_app_roles_exist(self, mary_agent: Any) -> None:
        """The clarify pass instructs the LLM to ask which role(s) apply."""
        captured: dict[str, Any] = {}

        class _FakeChatModel:
            async def ainvoke(self, messages: Any) -> Any:
                captured["prompt"] = messages[0].content
                return MagicMock(content="NO_CLARIFICATION_NEEDED")

        with (
            patch.object(mary_agent, "_project_app_roles", return_value=["Admin", "User"]),
            patch("ai_qa.agents.mary.LLMClient") as mock_client_class,
        ):
            mock_client_class.return_value._chat_model = _FakeChatModel()
            focus = [
                PipelineArtifact(
                    id=uuid4(),
                    name="req.md",
                    kind="requirements",
                    content="Some requirement",
                    version=1,
                )
            ]
            await mary_agent._plan_test_clarifications(focus, "overview")

        assert "Admin, User" in captured["prompt"]
        assert "which role" in captured["prompt"].lower()

    @pytest.mark.asyncio
    async def test_plan_test_clarifications_bounded_by_timeout(self, mary_agent: Any) -> None:
        """A stalled provider must not hang test-design planning: the LLM call is bounded
        by _CLARIFY_LLM_TIMEOUT and raises fast (handle_start then falls back to generating
        without clarifications) instead of leaving Mary stuck while planning."""
        import asyncio
        import time

        class _SlowChatModel:
            async def ainvoke(self, messages: Any) -> Any:
                await asyncio.sleep(30)  # far longer than the patched timeout
                return MagicMock(content="never reached")

        focus = [
            PipelineArtifact(
                id=uuid4(),
                name="req.md",
                kind="requirements",
                content="Some requirement",
                version=1,
            )
        ]
        start = time.monotonic()
        with (
            patch("ai_qa.agents.mary._CLARIFY_LLM_TIMEOUT", 0.05),
            patch("ai_qa.agents.mary.LLMClient") as mock_client_class,
        ):
            mock_client_class.return_value._chat_model = _SlowChatModel()
            with pytest.raises(asyncio.TimeoutError):
                await mary_agent._plan_test_clarifications(focus, "overview")
        # Bounded by wait_for, not the 30s sleep — proves the timeout actually fired.
        assert time.monotonic() - start < 5.0


class TestTestCaseMarkdownRoundTrip:
    """TestCase.to_markdown / from_markdown round-trip (the single persisted form)."""

    def test_round_trip_preserves_core_fields(self) -> None:
        tc = TestCase(
            title="Search by Country using contains matching",
            role="Admin",
            objective="Verify partial Country match returns the right journeys",
            preconditions=["User is authenticated", "Journeys exist with various Country values"],
            test_data=["Fran"],
            steps=[
                TestCaseStep(number=1, action="Navigate to the app", target="the app URL"),
                TestCaseStep(
                    number=2, action="Enter a partial country", target="Country field", data="Fran"
                ),
            ],
            expected_results=["Only journeys whose Country contains 'Fran' are shown"],
            automation_hints=["Wait for the grid to settle"],
            tags=["smoke", "search"],
            source_requirement_name="1249976517/requirement.md",
            source_url="https://confluence.example.com/page/42",
            warnings=["Ambiguous UI target in step 2"],
        )

        restored = TestCase.from_markdown(tc.to_markdown())

        assert restored.title == tc.title
        assert restored.role == tc.role
        assert restored.objective == tc.objective
        assert restored.preconditions == tc.preconditions
        assert restored.test_data == tc.test_data
        assert [(s.number, s.action, s.target, s.data) for s in restored.steps] == [
            (s.number, s.action, s.target, s.data) for s in tc.steps
        ]
        assert restored.expected_results == tc.expected_results
        assert restored.automation_hints == tc.automation_hints
        assert restored.tags == tc.tags
        assert restored.source_requirement_name == tc.source_requirement_name
        assert restored.source_url == tc.source_url
        assert restored.warnings == tc.warnings

    def test_from_markdown_minimal(self) -> None:
        """A title-only Markdown body still yields a valid TestCase."""
        restored = TestCase.from_markdown("# Just a title\n")
        assert restored.title == "Just a title"
        assert restored.steps == []


class TestMaryArtifactSave125:
    """Story 12.5: AC3 batch rollback + Markdown-only success-path regression."""

    @pytest.mark.asyncio
    async def test_test_case_saved_as_markdown_only(self, mary_agent: Any) -> None:
        """Test cases persist as LLM-friendly Markdown (.md) ONLY — no parallel JSON.

        The artifact body is Markdown carrying the real source/steps/expected (the whole
        pipeline is natural-language); the source_url + warnings ride on the artifact row;
        and NO ``.metadata.json`` sidecar is written (that JSON copy was redundant).
        """
        tc = TestCase(
            title="Search by Country",
            objective="Verify partial Country match",
            preconditions=["User is authenticated"],
            steps=[TestCaseStep(number=1, action="Enter Fran", target="the Country field")],
            expected_results=["Only journeys whose Country contains 'Fran' are shown"],
            source_requirement_name="1249976517/requirement.md",
            source_url="https://confluence.example.com/page/42",
            warnings=["Ambiguous selector in step 1"],
        )
        mary_agent.test_cases = [tc]

        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            mock_adapter = MagicMock()
            mock_adapter_class.return_value = mock_adapter
            result = await mary_agent._write_approved_test_cases()

        assert result is True
        # Body is Markdown saved under a .md name (not a JSON dump).
        tc_call = mock_adapter.save_test_case.call_args
        saved_name = tc_call.args[0]
        saved_body = tc_call.args[1]
        assert saved_name.endswith(".md")
        assert saved_body.startswith("# Search by Country")
        assert "## Steps" in saved_body
        assert "## Expected Results" in saved_body
        assert "Only journeys whose Country contains 'Fran' are shown" in saved_body
        assert "{" not in saved_body.splitlines()[0]  # not a JSON dump

        # Provenance rides on the artifact row, not a JSON body.
        assert tc_call.kwargs.get("source_url") == "https://confluence.example.com/page/42"
        assert tc_call.kwargs.get("warnings") == [{"message": "Ambiguous selector in step 1"}]
        # The human-readable title is persisted so the Test Cases tree labels each case by
        # its own name instead of the shared role folder.
        assert tc_call.kwargs.get("title") == "Search by Country"

        # No redundant JSON sidecar is written anymore.
        assert mock_adapter.save_metadata.call_count == 0

    @pytest.mark.asyncio
    async def test_role_test_case_saved_flat_with_role_in_body(self, mary_agent: Any) -> None:
        """A test case with a role lands at the flat root; body carries the role.

        Per-role sub-foldering is removed (saved as <case>.md) but the role still
        round-trips in the Markdown body via the ``## Role`` section.
        """
        tc = TestCase(
            title="Admin deletes a user",
            role="Admin User",
            steps=[TestCaseStep(number=1, action="Click delete", target="the Delete button")],
            expected_results=["The user is removed"],
        )
        mary_agent.test_cases = [tc]

        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            mock_adapter = MagicMock()
            mock_adapter_class.return_value = mock_adapter
            result = await mary_agent._write_approved_test_cases()

        assert result is True
        tc_call = mock_adapter.save_test_case.call_args
        saved_name = tc_call.args[0]
        saved_body = tc_call.args[1]
        assert "/" not in saved_name  # flat at root
        assert saved_name.endswith(".md")
        assert "## Role" in saved_body
        assert "Admin User" in saved_body

    @pytest.mark.asyncio
    async def test_cross_role_same_base_uniqueness(self, mary_agent: Any) -> None:
        """Cross-role same-base cases disambiguate across the whole flat folder."""
        # Two roles have a test case that normalizes to the same base name
        tc1 = TestCase(
            title="Login", role="Admin", steps=[TestCaseStep(number=1, action="X", target="Y")]
        )
        tc2 = TestCase(
            title="Login", role="User", steps=[TestCaseStep(number=1, action="X", target="Y")]
        )
        mary_agent.test_cases = [tc1, tc2]

        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            mock_adapter = MagicMock()
            mock_adapter_class.return_value = mock_adapter
            result = await mary_agent._write_approved_test_cases()

        assert result is True
        calls = mock_adapter.save_test_case.call_args_list
        assert len(calls) == 2
        name1 = calls[0].args[0]
        name2 = calls[1].args[0]
        assert name1 == "login.md"
        # Since source_requirement_id is None, it falls back to position
        assert name2 == "login-2.md"

    @pytest.mark.asyncio
    async def test_save_failure_no_done_error_message_rollback(self, mary_agent: Any) -> None:
        """AC3: save failure → no DONE, UX-DR12 error, batch rollback, stays reviewable.

        Second of three save_test_case calls raises.  The first saved artifact id
        must be passed to delete_artifact (rollback), DONE must not be reached, and
        a REVIEW_REQUEST re-presentation must follow the error message.
        """
        tc1 = TestCase(title="TC 1", steps=[TestCaseStep(number=1, action="Click", target="b")])
        tc2 = TestCase(title="TC 2", steps=[TestCaseStep(number=1, action="Click", target="b")])
        tc3 = TestCase(title="TC 3", steps=[TestCaseStep(number=1, action="Click", target="b")])
        mary_agent.test_cases = [tc1, tc2, tc3]
        mary_agent._reviewed_indices = {0, 1}
        mary_agent.current_review_index = 2

        transitions_called: list[AgentState] = []
        messages_sent: list[dict[str, Any]] = []

        async def track_transition(state: AgentState) -> None:
            transitions_called.append(state)

        async def track_message(content: str = "", **kwargs: Any) -> None:
            messages_sent.append({"content": content, "type": kwargs.get("message_type")})

        first_artifact = MagicMock()
        first_artifact.id = "artifact-id-1"

        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            mock_adapter = MagicMock()
            mock_adapter.save_test_case.side_effect = [
                first_artifact,
                RuntimeError("storage unavailable"),
            ]
            mock_adapter_class.return_value = mock_adapter

            with (
                patch.object(mary_agent, "transition_to", side_effect=track_transition),
                patch.object(mary_agent, "send_message", side_effect=track_message),
            ):
                await mary_agent.handle_approve({"test_case_index": 2})

        # Must NOT have reached DONE
        assert AgentState.DONE not in transitions_called
        # Must have re-entered REVIEW_REQUEST (stays reviewable)
        assert AgentState.REVIEW_REQUEST in transitions_called
        # Error message was sent
        error_msgs = [m for m in messages_sent if m["type"] == "error"]
        assert len(error_msgs) >= 1
        # No success message
        success_msgs = [m for m in messages_sent if m["type"] == "success"]
        assert len(success_msgs) == 0
        # Batch rollback: delete_artifact called for the first committed artifact
        delete_fn = mary_agent.project_context.artifact_service.delete_artifact
        delete_fn.assert_called_once()
        rollback_kwargs = delete_fn.call_args.kwargs
        assert rollback_kwargs.get("artifact_id") == "artifact-id-1"

    @pytest.mark.asyncio
    async def test_save_success_transitions_done_and_sends_success_message(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """Regression: success path still transitions to DONE and sends the success message."""
        mary_agent.test_cases = sample_test_cases
        prior_indices = set(range(len(sample_test_cases) - 1))
        mary_agent._reviewed_indices = prior_indices
        mary_agent.current_review_index = len(sample_test_cases) - 1

        transitions: list[AgentState] = []
        messages: list[dict[str, Any]] = []

        async def track_transition(state: AgentState) -> None:
            transitions.append(state)

        async def track_message(content: str = "", **kwargs: Any) -> None:
            messages.append({"content": content, "type": kwargs.get("message_type")})

        with (
            patch.object(mary_agent, "transition_to", side_effect=track_transition),
            patch.object(mary_agent, "send_message", side_effect=track_message),
            patch("ai_qa.agents.mary.PipelineArtifactAdapter"),
        ):
            await mary_agent.handle_approve()

        assert AgentState.DONE in transitions
        success_msgs = [m for m in messages if m["type"] == "success"]
        assert len(success_msgs) >= 1
        assert "saved" in success_msgs[0]["content"].lower()


class TestMaryIndexDefenseAndRepresent:
    """Defensive index parsing + re-present clamping/remaining indices (C31/C33/C34/C36)."""

    @pytest.mark.asyncio
    async def test_handle_approve_non_numeric_index_falls_back(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """C33: a non-numeric test_case_index falls back to current_review_index, not raise."""
        mary_agent.test_cases = sample_test_cases
        mary_agent._reviewed_indices = set()
        mary_agent.current_review_index = 1

        with (
            patch.object(mary_agent, "transition_to"),
            patch.object(mary_agent, "send_message"),
            patch("ai_qa.agents.mary.PipelineArtifactAdapter"),
        ):
            # "abc", None, and a list must all degrade gracefully to current_review_index (1)
            for bad in ("abc", None, [0, 1]):
                mary_agent._reviewed_indices = set()
                mary_agent.current_review_index = 1
                await mary_agent.handle_approve({"test_case_index": bad})
                assert 1 in mary_agent._reviewed_indices

    @pytest.mark.asyncio
    async def test_handle_approve_out_of_range_index_reclamps(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """C31: an out-of-range index re-clamps into range (no IndexError)."""
        mary_agent.test_cases = sample_test_cases  # len 2
        mary_agent._reviewed_indices = set()
        mary_agent.current_review_index = 99  # itself out of range

        with (
            patch.object(mary_agent, "transition_to"),
            patch.object(mary_agent, "send_message"),
            patch("ai_qa.agents.mary.PipelineArtifactAdapter"),
        ):
            await mary_agent.handle_approve({"test_case_index": 50})

        # Re-clamped to the last valid index (1)
        assert 1 in mary_agent._reviewed_indices

    @pytest.mark.asyncio
    async def test_handle_approve_empty_list_returns_early(self, mary_agent: Any) -> None:
        """C31: approving with no test cases returns early (no transition, no crash)."""
        mary_agent.test_cases = []
        transitions: list[AgentState] = []

        async def track(state: AgentState) -> None:
            transitions.append(state)

        with (
            patch.object(mary_agent, "transition_to", side_effect=track),
            patch.object(mary_agent, "send_message"),
            patch("ai_qa.agents.mary.PipelineArtifactAdapter"),
        ):
            await mary_agent.handle_approve({"test_case_index": 0})

        assert transitions == []

    @pytest.mark.asyncio
    async def test_represent_includes_remaining_indices(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """C36: after a partial approval the re-presented payload lists remaining indices."""
        mary_agent.test_cases = sample_test_cases  # len 2
        mary_agent._reviewed_indices = set()
        mary_agent.current_review_index = 0

        captured: list[dict[str, Any]] = []

        async def capture_send(content: str = "", **kwargs: Any) -> None:
            captured.append(kwargs.get("metadata") or {})

        with (
            patch.object(mary_agent, "transition_to"),
            patch.object(mary_agent, "send_message", side_effect=capture_send),
            patch("ai_qa.agents.mary.PipelineArtifactAdapter"),
        ):
            await mary_agent.handle_approve({"test_case_index": 0})

        review_meta = [m for m in captured if m.get("type") == "test_case_review"]
        assert review_meta, "Expected a test_case_review payload on partial approval"
        meta = review_meta[-1]
        assert meta["remaining_indices"] == [1]
        assert meta["reviewed_indices"] == [0]
        # active_index points at the first remaining case and is in range
        assert meta["active_index"] == 1

    def test_format_review_content_clamps_overflow_index(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """C34: current_review_index == len renders the last case, not 'No test case'."""
        mary_agent.test_cases = sample_test_cases  # len 2
        mary_agent.current_review_index = 2  # == len (advanced past the last case)

        result = StageResult(success=True, data=sample_test_cases, errors=[], warnings=[])
        content = mary_agent._format_review_content(result)

        assert "No test case to review." not in content
        # Renders the last case (2 of 2)
        assert "2 of 2" in content


def _approved_artifact(
    *, name: str = "page-1/requirement.md", content: str = "# Requirements", art_id: str = "a1"
) -> MagicMock:
    """Build a MagicMock APPROVED requirement artifact (source_type set)."""
    art = MagicMock()
    art.source_type = "confluence"
    art.id = art_id
    art.name = name
    art.source_url = ""
    art.warnings = None
    art.content = content
    return art


class TestMaryLazyLLMConfig:
    """The auth-bug fix: the LLM config is resolved lazily and applied to the extractor."""

    @pytest.mark.asyncio
    async def test_process_refreshes_extractor_llm_config(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """process() resolves the config at call time and applies it to the extractor.

        Regression guard for the __init__-time empty-api_key config that surfaced as a
        raw provider auth error.
        """
        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [_approved_artifact()]
            mock_adapter.load_metadata.return_value = None
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True, data=sample_test_cases, errors=[], warnings=[], confidence=0.9
            )
            mary_agent.extractor = mock_extractor

            await mary_agent.process({})

        # The context-resolved config (with a real api_key) is applied to the extractor.
        assert mary_agent.config.api_key == "test-key"
        assert mary_agent.extractor.llm_config == mary_agent.config


class TestMaryClarifyLoop:
    """The risk-based test-design clarification loop (point 5)."""

    @pytest.mark.asyncio
    async def test_handle_start_enters_clarify_when_gaps(self, mary_agent: Any) -> None:
        """When the planner finds genuine gaps, Mary enters the clarify phase and asks."""
        messages: list[dict[str, Any]] = []

        async def track_send(content: str = "", **kwargs: Any) -> None:
            messages.append({"content": content, "metadata": kwargs.get("metadata")})

        with (
            patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class,
            patch.object(mary_agent, "transition_to"),
            patch.object(mary_agent, "send_message", side_effect=track_send),
            patch.object(
                mary_agent,
                "_plan_test_clarifications",
                return_value=["What is the expected error message on invalid input?"],
            ),
        ):
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [_approved_artifact()]
            mock_adapter.load_metadata.return_value = None
            mock_adapter_class.return_value = mock_adapter

            await mary_agent.handle_start({})

        assert mary_agent.phase == "clarify"
        assert mary_agent._clarify_queue == ["What is the expected error message on invalid input?"]
        assert any((m["metadata"] or {}).get("type") == "test_clarify_request" for m in messages)

    @pytest.mark.asyncio
    async def test_clarify_answer_accumulates_then_generates(self, mary_agent: Any) -> None:
        """An answer is recorded as Q/A context; an empty queue triggers generation."""
        mary_agent.phase = "clarify"
        mary_agent._clarify_queue = ["What is the row limit?"]
        mary_agent._clarifications = []

        with (
            patch.object(mary_agent, "send_message"),
            patch.object(mary_agent, "_generate_and_present") as mock_gen,
        ):
            await mary_agent.handle_approve(
                {"action": "clarify_answer", "answer": "100 rows per page"}
            )

        assert mary_agent._clarifications == ["Q: What is the row limit?\nA: 100 rows per page"]
        assert mary_agent._clarify_queue == []
        mock_gen.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clarify_skip_records_nothing_and_advances(self, mary_agent: Any) -> None:
        """Skipping a question records no answer and asks the next one."""
        mary_agent.phase = "clarify"
        mary_agent._clarify_queue = ["Q1?", "Q2?"]
        mary_agent._clarifications = []

        with (
            patch.object(mary_agent, "send_message"),
            patch.object(mary_agent, "_ask_test_clarification") as mock_ask,
        ):
            await mary_agent.handle_approve({"action": "skip"})

        assert mary_agent._clarifications == []
        assert mary_agent._clarify_queue == ["Q2?"]
        mock_ask.assert_awaited_once_with("Q2?")

    def test_parse_clarification_questions_sentinel(self, mary_agent: Any) -> None:
        """The sentinel means 'no clarification needed' → empty list."""
        from ai_qa.agents.mary import _NO_CLARIFICATION_SENTINEL

        assert mary_agent._parse_clarification_questions(_NO_CLARIFICATION_SENTINEL) == []

    def test_parse_clarification_questions_lines(self, mary_agent: Any) -> None:
        """Bullet/numbered lines are cleaned into plain question strings."""
        text = "- What is the expected error?\n2) What is the max length allowed?\n"
        assert mary_agent._parse_clarification_questions(text) == [
            "What is the expected error?",
            "What is the max length allowed?",
        ]

    def test_parse_clarification_questions_capped(self, mary_agent: Any) -> None:
        """No more than _MAX_CLARIFY_QUESTIONS are returned."""
        from ai_qa.agents.mary import _MAX_CLARIFY_QUESTIONS

        text = "\n".join(f"- Question number {i} about the feature" for i in range(10))
        assert len(mary_agent._parse_clarification_questions(text)) == _MAX_CLARIFY_QUESTIONS


class TestMaryFocusSourceResolution:
    """Confluence id reuses Bob's saved copy; Jira id is fetched live via MCP."""

    @pytest.mark.asyncio
    async def test_jira_selected_id_fetches_via_mcp(self, mary_agent: Any) -> None:
        """A Jira ticket id routes through the MCP fetch path before generation."""
        with (
            patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class,
            patch.object(mary_agent, "transition_to"),
            patch.object(mary_agent, "send_message"),
            patch.object(mary_agent, "_fetch_and_save_jira", return_value=True) as mock_fetch,
            patch.object(mary_agent, "_plan_test_clarifications", return_value=[]),
            patch.object(mary_agent, "_generate_and_present"),
        ):
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [
                _approved_artifact(name="PROJ-1/requirement.md", art_id="j1")
            ]
            mock_adapter.load_metadata.return_value = {
                "selected_id": "PROJ-1",
                "source_type": "jira",
            }
            mock_adapter_class.return_value = mock_adapter

            await mary_agent.handle_start({})

        mock_fetch.assert_awaited_once()
        await_args = mock_fetch.await_args
        assert await_args is not None  # narrow Optional[_Call] before .args (Pyrefly)
        assert await_args.args[1] == "PROJ-1"

    @pytest.mark.asyncio
    async def test_confluence_numeric_id_does_not_call_mcp(self, mary_agent: Any) -> None:
        """A numeric Confluence page id reuses the saved artifact (no MCP fetch)."""
        with (
            patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class,
            patch.object(mary_agent, "transition_to"),
            patch.object(mary_agent, "send_message"),
            patch.object(mary_agent, "_fetch_and_save_jira") as mock_fetch,
            patch.object(mary_agent, "_plan_test_clarifications", return_value=[]),
            patch.object(mary_agent, "_generate_and_present"),
        ):
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [
                _approved_artifact(name="1249976517/requirement.md", art_id="c1")
            ]
            mock_adapter.load_metadata.return_value = {
                "selected_id": "1249976517",
                "source_type": "confluence",
            }
            mock_adapter_class.return_value = mock_adapter

            await mary_agent.handle_start({})

        mock_fetch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fetch_and_save_jira_persists_requirement(self, mary_agent: Any) -> None:
        """_fetch_and_save_jira reads the ticket via MCP and saves it as a requirement."""
        from ai_qa.pipelines.models import JiraIssue

        issue = JiraIssue(
            issue_key="PROJ-7",
            summary="Login flow",
            description="Users can log in",
            project_key="PROJ",
            url="https://jira.example.com/PROJ-7",
            status="Open",
            issue_type="Story",
        )
        mock_adapter = MagicMock()

        with (
            patch.object(mary_agent, "_resolve_mcp_pat", return_value="pat"),
            patch.object(
                mary_agent, "_load_project", return_value=MagicMock(jira_base_url="https://jira")
            ),
            patch("ai_qa.agents.mary.AppSettings"),
            patch("ai_qa.agents.mary.MCPClient") as mock_mcp_cls,
            patch("ai_qa.agents.mary.JiraReader") as mock_reader_cls,
            patch.object(mary_agent, "send_message"),
        ):
            mock_mcp_cls.return_value = AsyncMock()
            mock_reader = MagicMock()
            mock_reader.read_issue = AsyncMock(
                return_value=StageResult(
                    success=True, data=issue, errors=[], warnings=[], confidence=1.0
                )
            )
            mock_reader_cls.return_value = mock_reader

            ok = await mary_agent._fetch_and_save_jira(mock_adapter, "PROJ-7")

        assert ok is True
        mock_adapter.save_requirement.assert_called_once()
        save_call = mock_adapter.save_requirement.call_args
        assert save_call is not None  # narrow Optional[_Call] before .kwargs (Pyrefly)
        assert save_call.kwargs["page_id"] == "PROJ-7"
        assert save_call.kwargs["source_type"] == "jira"
        assert mary_agent._selected_id == "PROJ-7"


class TestMaryOverviewContext:
    """Mary reads ALL requirements for an overview and feeds it into generation."""

    @pytest.mark.asyncio
    async def test_process_passes_overview_context_excluding_focus(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """The focus requirement is excluded from the overview; siblings are included."""
        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            a1 = _approved_artifact(
                name="page-1/requirement.md", art_id="a1", content="# A1 focus body"
            )
            a2 = _approved_artifact(
                name="page-2/requirement.md", art_id="a2", content="# A2 sibling body"
            )
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [a1, a2]
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True, data=sample_test_cases, errors=[], warnings=[], confidence=0.9
            )
            mary_agent.extractor = mock_extractor

            await mary_agent.process({"selected_id": "page-1"})

        call = mock_extractor.extract_streaming.call_args
        assert call is not None  # narrow Optional[_Call] before .kwargs (Pyrefly)
        context = call.kwargs.get("context")
        assert context is not None
        assert "Project Overview" in context
        assert "page-2/requirement.md" in context  # sibling overview present
        assert "page-1/requirement.md" not in context  # focus excluded from overview

    @pytest.mark.asyncio
    async def test_process_includes_clarifications_in_context(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """Accumulated clarification answers are injected into the generation context."""
        mary_agent._clarifications = ["Q: What is the limit?\nA: 100 items per page"]

        with patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class:
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [_approved_artifact()]
            mock_adapter.load_metadata.return_value = None
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming.return_value = StageResult(
                success=True, data=sample_test_cases, errors=[], warnings=[], confidence=0.9
            )
            mary_agent.extractor = mock_extractor

            await mary_agent.process({})

        call = mock_extractor.extract_streaming.call_args
        assert call is not None  # narrow Optional[_Call] before .kwargs (Pyrefly)
        context = call.kwargs.get("context")
        assert context is not None
        assert "Clarifications from the test author" in context
        assert "100 items per page" in context


class TestMaryIncrementalGeneration:
    """Streaming generation saves + reports each test case as it lands (incremental)."""

    @pytest.mark.asyncio
    async def test_process_saves_and_reports_each_streamed_case(
        self, sample_test_cases: list[TestCase], mary_agent: Any
    ) -> None:
        """Each case streamed via on_case is persisted immediately + a progress line sent."""
        messages: list[str] = []

        async def track_send(content: str = "", **kwargs: Any) -> None:
            messages.append(content)

        async def fake_stream(
            requirements_paths: Any,
            source_urls: Any = None,
            sources: Any = None,
            context: str = "",
            on_case: Any = None,
        ) -> StageResult:
            for tc in sample_test_cases:
                if on_case is not None:
                    await on_case(tc)
            return StageResult(
                success=True, data=sample_test_cases, errors=[], warnings=[], confidence=0.9
            )

        with (
            patch("ai_qa.agents.mary.PipelineArtifactAdapter") as mock_adapter_class,
            patch.object(mary_agent, "send_message", side_effect=track_send),
        ):
            mock_adapter = MagicMock()
            mock_adapter.load_requirement_markdown.return_value = [_approved_artifact()]
            mock_adapter.load_metadata.return_value = None
            mock_adapter.save_test_case.return_value = MagicMock(id="art-1")
            mock_adapter_class.return_value = mock_adapter

            mock_extractor = AsyncMock()
            mock_extractor.extract_streaming = AsyncMock(side_effect=fake_stream)
            mary_agent.extractor = mock_extractor

            await mary_agent.process({})

        # Each streamed case was persisted to the Test Cases folder the moment it arrived.
        assert mock_adapter.save_test_case.call_count == len(sample_test_cases)
        # Persisted as Markdown only — no redundant JSON sidecar per streamed case.
        assert mock_adapter.save_metadata.call_count == 0
        # ...and as a DRAFT, so it stays out of Sarah's input until the user approves.
        assert all(
            c.kwargs.get("source_type") == "draft"
            for c in mock_adapter.save_test_case.call_args_list
        )
        # And each was reported with a per-case progress line.
        saved_lines = [m for m in messages if "saved to Test Cases" in m]
        assert len(saved_lines) == len(sample_test_cases)
        # The authoritative final list is still stored for review.
        assert mary_agent.test_cases == sample_test_cases
