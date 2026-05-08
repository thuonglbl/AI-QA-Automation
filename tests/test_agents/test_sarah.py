"""Tests for Sarah agent - Generate Playwright Scripts with Side-by-Side Review.

Tests follow TDD pattern:
- RED: Write failing tests first
- GREEN: Implement minimal code to pass tests
- REFACTOR: Improve code structure while keeping tests green
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

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


# -----------------------------------------------------------------------------
# Initialization Tests
# -----------------------------------------------------------------------------


class TestSarahAgentInit:
    """Test Sarah agent initialization."""

    def test_sarah_agent_initialization(self, sarah_agent: Any) -> None:
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
# Chrome Path Persistence Tests
# -----------------------------------------------------------------------------


class TestChromePathPersistence:
    """Test Chrome path loading and storage."""

    @pytest.mark.asyncio
    async def test_load_chrome_path_from_storage(self, tmp_path: Path) -> None:
        """Test Chrome path is loaded from persistent storage on init."""
        from ai_qa.agents.sarah import SarahAgent

        # Create chrome path file
        config_dir = tmp_path / "configuration"
        config_dir.mkdir(parents=True, exist_ok=True)
        chrome_path_data = {"chrome_path": "/usr/bin/chrome"}
        (config_dir / "chrome_path.json").write_text(json.dumps(chrome_path_data))

        agent = SarahAgent(workspace_dir=tmp_path)
        assert agent._chrome_path == "/usr/bin/chrome"

    @pytest.mark.asyncio
    async def test_store_chrome_path_saves_to_file(self, tmp_path: Path) -> None:
        """Test Chrome path is saved to persistent storage."""
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        await agent._store_chrome_path("/usr/bin/google-chrome")

        chrome_path_file = tmp_path / "configuration" / "chrome_path.json"
        assert chrome_path_file.exists()
        data = json.loads(chrome_path_file.read_text())
        assert data["chrome_path"] == "/usr/bin/google-chrome"

    def test_chrome_path_none_when_no_storage(self, tmp_path: Path) -> None:
        """Test Chrome path is None when no storage exists."""
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)
        assert agent._chrome_path is None


# -----------------------------------------------------------------------------
# Process Method Tests
# -----------------------------------------------------------------------------


class TestSarahAgentProcess:
    """Test Sarah agent process method."""

    @pytest.mark.asyncio
    async def test_process_loads_test_cases_from_workspace(
        self, tmp_path: Path, sample_test_cases: list[TestCase]
    ) -> None:
        """Test process loads test cases from workspace/testcases/."""
        from ai_qa.agents.sarah import SarahAgent

        # Create test cases directory with test case files
        testcases_dir = tmp_path / "testcases"
        testcases_dir.mkdir(parents=True, exist_ok=True)
        for tc in sample_test_cases:
            (testcases_dir / f"{tc.filename}.json").write_text(json.dumps(tc.model_dump()))

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_generator_class:
            mock_generator = AsyncMock()
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
            result = await agent.process({"chrome_path": "/usr/bin/chrome"})

            assert result.success is True
            assert len(agent._generated_scripts) == len(sample_test_cases)

    @pytest.mark.asyncio
    async def test_process_handles_empty_testcases_directory(self, tmp_path: Path) -> None:
        """Test process returns error for empty testcases directory."""
        from ai_qa.agents.sarah import SarahAgent

        # Create empty testcases directory
        testcases_dir = tmp_path / "testcases"
        testcases_dir.mkdir(parents=True, exist_ok=True)

        agent = SarahAgent(workspace_dir=tmp_path)
        result = await agent.process({"chrome_path": "/usr/bin/chrome"})

        assert result.success is False
        assert result.data is None
        assert any("No test case files found" in err for err in result.errors)

    @pytest.mark.asyncio
    async def test_process_sends_progress_updates(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mock_broadcast: AsyncMock
    ) -> None:
        """Test process sends progress updates for each script generation."""
        from ai_qa.agents.sarah import SarahAgent

        # Create test cases directory
        testcases_dir = tmp_path / "testcases"
        testcases_dir.mkdir(parents=True, exist_ok=True)
        for tc in sample_test_cases:
            (testcases_dir / f"{tc.filename}.json").write_text(json.dumps(tc.model_dump()))

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_generator_class:
            mock_generator = AsyncMock()
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
            await agent.process({"chrome_path": "/usr/bin/chrome"})

            # Check that progress messages were sent
            # Should have: initial message + progress for each test case
            progress_calls = [
                c for c in mock_broadcast.call_args_list if c[0][0].message_type == "info"
            ]
            assert len(progress_calls) >= len(sample_test_cases)

    @pytest.mark.asyncio
    async def test_process_stores_chrome_path_when_provided(
        self, tmp_path: Path, sample_test_cases: list[TestCase]
    ) -> None:
        """Test process stores Chrome path when provided in input."""
        from ai_qa.agents.sarah import SarahAgent

        # Create test cases directory
        testcases_dir = tmp_path / "testcases"
        testcases_dir.mkdir(parents=True, exist_ok=True)
        for tc in sample_test_cases:
            (testcases_dir / f"{tc.filename}.json").write_text(json.dumps(tc.model_dump()))

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_generator_class:
            mock_generator = AsyncMock()
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
            await agent.process({"chrome_path": "/usr/bin/google-chrome"})

            # Check Chrome path was stored
            chrome_path_file = tmp_path / "configuration" / "chrome_path.json"
            assert chrome_path_file.exists()
            data = json.loads(chrome_path_file.read_text())
            assert data["chrome_path"] == "/usr/bin/google-chrome"


# -----------------------------------------------------------------------------
# Handle Start Tests
# -----------------------------------------------------------------------------


class TestSarahAgentHandleStart:
    """Test Sarah agent handle_start method."""

    @pytest.mark.asyncio
    async def test_handle_start_requests_chrome_path_when_not_set(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        """Test handle_start requests Chrome path when not configured."""
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)

        await agent.handle_start({})

        # Should send state transition, greeting and Chrome path request
        assert mock_broadcast.call_count >= 2
        # Find greeting message (may not be first due to state transition)
        messages = [call[0][0].content for call in mock_broadcast.call_args_list]
        assert any("Sarah" in msg for msg in messages)
        assert any("Chrome" in msg for msg in messages)

    @pytest.mark.asyncio
    async def test_handle_start_uses_saved_chrome_path(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        """Test handle_start uses saved Chrome path when available."""
        from ai_qa.agents.sarah import SarahAgent

        # Create chrome path file
        config_dir = tmp_path / "configuration"
        config_dir.mkdir(parents=True, exist_ok=True)
        chrome_path_data = {"chrome_path": "/usr/bin/chrome"}
        (config_dir / "chrome_path.json").write_text(json.dumps(chrome_path_data))

        # Create test cases directory
        testcases_dir = tmp_path / "testcases"
        testcases_dir.mkdir(parents=True, exist_ok=True)

        agent = SarahAgent(workspace_dir=tmp_path)

        with patch("ai_qa.agents.sarah.ScriptGenerator") as mock_generator_class:
            mock_generator = AsyncMock()
            mock_generator.generate.return_value = StageResult(
                success=True,
                data=[],
                errors=[],
                warnings=["No test cases found"],
                confidence=1.0,
            )
            mock_generator_class.return_value = mock_generator

            await agent.handle_start({})

            # Should use saved Chrome path in greeting
            first_call = mock_broadcast.call_args_list[0][0][0]
            assert "saved Chrome path" in first_call.content


# -----------------------------------------------------------------------------
# Handle Approve Tests
# -----------------------------------------------------------------------------


class TestSarahAgentHandleApprove:
    """Test Sarah agent handle_approve method."""

    @pytest.mark.asyncio
    async def test_handle_approve_marks_script_approved_and_advances(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mock_broadcast: AsyncMock
    ) -> None:
        """Test handle_approve marks current script as approved and advances."""
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

        agent.state = AgentState.REVIEW_REQUEST
        agent._current_review_index = 0

        await agent.handle_approve()

        # Script should be marked approved
        assert agent._generated_scripts[0].approved is True
        # Should advance to next index
        assert agent._current_review_index == 1

    @pytest.mark.asyncio
    async def test_handle_approve_transitions_to_done_when_all_approved(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mock_broadcast: AsyncMock
    ) -> None:
        """Test handle_approve transitions to DONE when all scripts approved."""
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

        agent.state = AgentState.REVIEW_REQUEST
        agent._current_review_index = 0

        await agent.handle_approve()

        # Should transition to DONE
        assert agent.state == AgentState.DONE

    @pytest.mark.asyncio
    async def test_handle_approve_presents_next_script(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mock_broadcast: AsyncMock
    ) -> None:
        """Test handle_approve presents next script when more exist."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)

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

        await agent.handle_approve()

        # Should still be in REVIEW_REQUEST state
        assert agent.state == AgentState.REVIEW_REQUEST


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
            mock_generator = AsyncMock()
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
            mock_generator = AsyncMock()
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

    @pytest.mark.asyncio
    async def test_handle_skip_advances_without_approval(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mock_broadcast: AsyncMock
    ) -> None:
        """Test handle_skip advances without marking script approved."""
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

        agent.state = AgentState.REVIEW_REQUEST
        agent._current_review_index = 0

        await agent.handle_skip()

        # First script should NOT be approved
        assert agent._generated_scripts[0].approved is False
        # Should advance to next index
        assert agent._current_review_index == 1

    @pytest.mark.asyncio
    async def test_handle_skip_sends_skip_notification(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mock_broadcast: AsyncMock
    ) -> None:
        """Test handle_skip sends notification about skipped script."""
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

        assert review_state["has_scripts"] is True
        assert review_state["current_index"] == 1
        assert review_state["total_count"] == len(sample_test_cases)
        assert review_state["approved_count"] == 1
        assert review_state["current_script"] == sample_test_cases[1].title

    def test_get_review_state_when_no_scripts(self, tmp_path: Path) -> None:
        """Test get_review_state when no scripts generated."""
        from ai_qa.agents.sarah import SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)

        review_state = agent.get_review_state()

        assert review_state["has_scripts"] is False
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

    def test_format_review_content_when_no_scripts(self, tmp_path: Path) -> None:
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
    """Test Sarah agent review presentation."""

    @pytest.mark.asyncio
    async def test_present_current_script_sends_review_data(
        self, tmp_path: Path, sample_test_cases: list[TestCase], mock_broadcast: AsyncMock
    ) -> None:
        """Test _present_current_script_for_review sends review data for UI."""
        from ai_qa.agents.sarah import GeneratedScript, SarahAgent

        agent = SarahAgent(workspace_dir=tmp_path)

        # Create generated script
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

        # Check review request was sent with metadata
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
