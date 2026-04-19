"""Tests for Mary agent - Test Case Generation with Per-Item Review.

Tests follow TDD pattern:
- RED: Write failing tests first
- GREEN: Implement minimal code to pass tests
- REFACTOR: Improve code structure while keeping tests green
"""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from ai_qa.agents.base import AgentState
from ai_qa.models import StageResult, TestCase, TestCaseStep


@pytest.fixture
def mary_agent(tmp_path: Path) -> Any:
    """Create Mary agent instance with test workspace."""
    # Import here to avoid import error if file doesn't exist yet
    from ai_qa.agents.mary import MaryAgent

    return MaryAgent(workspace_dir=tmp_path)


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
        self, tmp_path: Path, sample_test_cases: list[TestCase]
    ) -> None:
        """Test process reads requirements from workspace/requirements/."""
        # Create sample requirements file
        requirements_dir = tmp_path / "requirements"
        requirements_dir.mkdir(parents=True, exist_ok=True)
        (requirements_dir / "test-req.md").write_text(
            "# Sample requirements\n\nUser should be able to login"
        )

        with patch("ai_qa.agents.mary.TestCaseExtractor") as mock_extractor_class:
            mock_extractor = AsyncMock()
            mock_extractor.extract_batch.return_value = StageResult(
                success=True,
                data=sample_test_cases,
                errors=[],
                warnings=[],
                confidence=0.9,
            )
            mock_extractor_class.return_value = mock_extractor

            # Create agent inside patch context
            from ai_qa.agents.mary import MaryAgent

            mary_agent = MaryAgent(workspace_dir=tmp_path)

            result = await mary_agent.process({})

            assert result.success is True
            assert result.data == sample_test_cases
            assert mary_agent.test_cases == sample_test_cases

    @pytest.mark.asyncio
    async def test_process_sends_progress_updates(
        self, tmp_path: Path, sample_test_cases: list[TestCase]
    ) -> None:
        """Test process sends progress updates for each test case."""
        # Create sample requirements file
        requirements_dir = tmp_path / "requirements"
        requirements_dir.mkdir(parents=True, exist_ok=True)
        (requirements_dir / "test-req.md").write_text("# Sample requirements")

        with (
            patch("ai_qa.agents.mary.TestCaseExtractor") as mock_extractor_class,
            patch("ai_qa.api.websocket.broadcast_message") as mock_broadcast,
        ):
            mock_extractor = AsyncMock()
            mock_extractor.extract_batch.return_value = StageResult(
                success=True,
                data=sample_test_cases,
                errors=[],
                warnings=[],
                confidence=0.9,
            )
            mock_extractor_class.return_value = mock_extractor

            # Create agent inside patch context
            from ai_qa.agents.mary import MaryAgent

            mary_agent = MaryAgent(workspace_dir=tmp_path)

            await mary_agent.process({})

            # Check that progress messages were sent
            # Should send: initial message + progress for each test case
            assert mock_broadcast.call_count >= len(sample_test_cases) + 1

    @pytest.mark.asyncio
    async def test_process_handles_empty_requirements(self, tmp_path: Path) -> None:
        """Test process handles empty requirements directory gracefully."""
        # Create empty requirements directory
        requirements_dir = tmp_path / "requirements"
        requirements_dir.mkdir(parents=True, exist_ok=True)

        with patch("ai_qa.agents.mary.TestCaseExtractor") as mock_extractor_class:
            mock_extractor = AsyncMock()
            mock_extractor.extract_batch.return_value = StageResult(
                success=True,
                data=[],
                errors=[],
                warnings=["No requirements found"],
                confidence=1.0,
            )
            mock_extractor_class.return_value = mock_extractor

            # Create agent inside patch context
            from ai_qa.agents.mary import MaryAgent

            mary_agent = MaryAgent(workspace_dir=tmp_path)

            result = await mary_agent.process({})

            assert result.success is True
            assert result.data == []

    @pytest.mark.asyncio
    async def test_process_handles_extractor_failure(self, tmp_path: Path) -> None:
        """Test process handles TestCaseExtractor failure gracefully."""
        # Create sample requirements file
        requirements_dir = tmp_path / "requirements"
        requirements_dir.mkdir(parents=True, exist_ok=True)
        (requirements_dir / "test-req.md").write_text("# Sample requirements")

        with patch("ai_qa.agents.mary.TestCaseExtractor") as mock_extractor_class:
            mock_extractor = AsyncMock()
            mock_extractor.extract_batch.return_value = StageResult(
                success=False,
                data=None,
                errors=["LLM call failed"],
                warnings=[],
                confidence=0.0,
            )
            mock_extractor_class.return_value = mock_extractor

            # Create agent inside patch context
            from ai_qa.agents.mary import MaryAgent

            mary_agent = MaryAgent(workspace_dir=tmp_path)

            result = await mary_agent.process({})

            assert result.success is False
            assert "LLM call failed" in result.errors


class TestMaryAgentHandleApprove:
    """Test Mary agent handle_approve method."""

    @pytest.mark.asyncio
    async def test_handle_approve_marks_current_test_case_approved(
        self, tmp_path: Path, sample_test_cases: list[TestCase]
    ) -> None:
        """Test handle_approve marks current test case as approved."""
        from ai_qa.agents.mary import MaryAgent

        mary_agent = MaryAgent(workspace_dir=tmp_path)
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
        self, tmp_path: Path, sample_test_cases: list[TestCase]
    ) -> None:
        """Test handle_approve transitions to DONE when all test cases approved."""
        from ai_qa.agents.mary import MaryAgent

        mary_agent = MaryAgent(workspace_dir=tmp_path)
        mary_agent.test_cases = sample_test_cases
        mary_agent.current_review_index = len(sample_test_cases) - 1  # Last test case

        with (
            patch.object(mary_agent, "transition_to") as mock_transition,
            patch.object(mary_agent, "send_message"),
            patch("ai_qa.agents.mary.OutputWriter") as mock_writer_class,
        ):
            mock_writer = AsyncMock()
            mock_writer.write.return_value = StageResult(
                success=True, data={}, errors=[], warnings=[], confidence=1.0
            )
            mock_writer_class.return_value = mock_writer

            await mary_agent.handle_approve()

            # Should transition to DONE
            mock_transition.assert_called_with(AgentState.DONE)

    @pytest.mark.asyncio
    async def test_handle_approve_writes_approved_test_cases(
        self, tmp_path: Path, sample_test_cases: list[TestCase]
    ) -> None:
        """Test handle_approve writes approved test cases to workspace."""
        with patch("ai_qa.agents.mary.OutputWriter") as mock_writer_class:
            mock_writer = AsyncMock()
            mock_writer.write.return_value = StageResult(
                success=True, data={}, errors=[], warnings=[], confidence=1.0
            )
            mock_writer_class.return_value = mock_writer

            # Create agent inside patch context
            from ai_qa.agents.mary import MaryAgent

            mary_agent = MaryAgent(workspace_dir=tmp_path)
            mary_agent.test_cases = sample_test_cases
            mary_agent.current_review_index = len(sample_test_cases) - 1  # Last test case

            with (
                patch.object(mary_agent, "transition_to"),
                patch.object(mary_agent, "send_message"),
            ):
                await mary_agent.handle_approve()

                # Should write all test cases
                assert mock_writer.write.call_count == len(sample_test_cases)


class TestMaryAgentHandleReject:
    """Test Mary agent handle_reject method."""

    @pytest.mark.asyncio
    async def test_handle_reject_acknowledges_feedback(self, tmp_path: Path) -> None:
        """Test handle_reject sends acknowledgment message paraphrasing feedback."""
        from ai_qa.agents.mary import MaryAgent

        mary_agent = MaryAgent(workspace_dir=tmp_path)
        feedback = "The precondition is missing"

        with (
            patch.object(mary_agent, "transition_to"),
            patch.object(mary_agent, "send_message") as mock_send,
            patch("ai_qa.agents.mary.TestCaseExtractor") as mock_extractor_class,
        ):
            mock_extractor = AsyncMock()
            mock_extractor.extract_batch.return_value = StageResult(
                success=True,
                data=[],
                errors=[],
                warnings=[],
                confidence=0.9,
            )
            mock_extractor_class.return_value = mock_extractor

            await mary_agent.handle_reject(feedback)

            # Check acknowledgment was sent
            assert mock_send.call_count >= 1
            acknowledgment_call = mock_send.call_args_list[0]
            assert "precondition" in acknowledgment_call[0][0].lower()

    @pytest.mark.asyncio
    async def test_handle_reject_regenerates_current_test_case(
        self, tmp_path: Path, sample_test_cases: list[TestCase]
    ) -> None:
        """Test handle_reject re-generates the current test case with feedback."""
        # Create requirements file so handle_reject executes replacement logic
        requirements_dir = tmp_path / "requirements"
        requirements_dir.mkdir(parents=True, exist_ok=True)
        (requirements_dir / "test-req.md").write_text("# Sample requirements")

        with patch("ai_qa.agents.mary.TestCaseExtractor") as mock_extractor_class:
            mock_extractor = AsyncMock()
            regenerated_case = TestCase(
                title="Login with valid credentials (updated)",
                preconditions=["User is on login page", "User has valid credentials"],
                steps=sample_test_cases[0].steps,
                expected_results=sample_test_cases[0].expected_results,
                automation_hints=sample_test_cases[0].automation_hints,
            )
            mock_extractor.extract_batch.return_value = StageResult(
                success=True,
                data=[regenerated_case],
                errors=[],
                warnings=[],
                confidence=0.9,
            )
            mock_extractor_class.return_value = mock_extractor

            # Create agent inside patch context
            from ai_qa.agents.mary import MaryAgent

            mary_agent = MaryAgent(workspace_dir=tmp_path)
            mary_agent.test_cases = sample_test_cases
            mary_agent.current_review_index = 0

            with (
                patch.object(mary_agent, "transition_to"),
                patch.object(mary_agent, "send_message"),
            ):
                await mary_agent.handle_reject("Add precondition about valid credentials")

                # Should replace current test case
                assert mary_agent.test_cases[0].title == "Login with valid credentials (updated)"


class TestMaryAgentFormatReviewContent:
    """Test Mary agent review content formatting."""

    def test_format_review_content_includes_test_case_structure(
        self, tmp_path: Path, sample_test_cases: list[TestCase]
    ) -> None:
        """Test review content includes test case title, preconditions, steps, expected results."""
        from ai_qa.agents.mary import MaryAgent

        mary_agent = MaryAgent(workspace_dir=tmp_path)
        mary_agent.test_cases = sample_test_cases
        mary_agent.current_review_index = 0

        result = StageResult(success=True, data=sample_test_cases, errors=[], warnings=[])

        content = mary_agent._format_review_content(result)

        assert "Login with valid credentials" in content
        assert "preconditions" in content.lower()
        assert "steps" in content.lower()
        assert "expected" in content.lower()

    def test_format_review_content_includes_navigation_info(
        self, tmp_path: Path, sample_test_cases: list[TestCase]
    ) -> None:
        """Test review content includes current position and total count."""
        from ai_qa.agents.mary import MaryAgent

        mary_agent = MaryAgent(workspace_dir=tmp_path)
        mary_agent.test_cases = sample_test_cases
        mary_agent.current_review_index = 0

        result = StageResult(success=True, data=sample_test_cases, errors=[], warnings=[])

        content = mary_agent._format_review_content(result)

        assert "1 of 2" in content or "1/2" in content
