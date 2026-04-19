"""Tests for BaseAgent abstract class and AgentState enum.

Uses a minimal ConcreteAgent (defined in this file) to exercise the
abstract lifecycle methods without depending on any real agent implementation.

All WebSocket interactions are mocked so no real network connections are made.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from ai_qa.agents.base import (
    WORKSPACE_SUBFOLDERS,
    AgentState,
    BaseAgent,
)
from ai_qa.models import StageResult

# ---------------------------------------------------------------------------
# Concrete test double
# ---------------------------------------------------------------------------


class ConcreteAgent(BaseAgent):
    """Minimal concrete implementation used only inside this test file.

    The ``process`` method delegates to a configurable callable so each test
    can control whether it succeeds, fails, or raises ``PipelineError``.
    """

    def __init__(
        self,
        process_result: StageResult | None = None,
        workspace_dir: Path | None = None,
    ) -> None:
        self._process_result: StageResult = process_result or StageResult(
            success=True, data={"output": "default"}
        )
        super().__init__(
            name="Alice",
            color="#EC4899",
            step_number=1,
            step_title="AI Provider Configuration",
            workspace_dir=workspace_dir,
        )

    async def process(
        self,
        input_data: dict[str, Any],
        feedback: str | None = None,
    ) -> StageResult:
        return self._process_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_agent(
    process_result: StageResult | None = None,
    workspace_dir: Path | None = None,
) -> ConcreteAgent:
    """Create a ConcreteAgent with broadcast_message mocked at module level."""
    return ConcreteAgent(process_result=process_result, workspace_dir=workspace_dir)


# ---------------------------------------------------------------------------
# AgentState enum tests
# ---------------------------------------------------------------------------


class TestAgentStateEnum:
    """Verify AgentState values match the TypeScript AgentStatus union exactly."""

    def test_state_values_match_typescript_literals(self) -> None:
        """String values must match frontend TypeScript literal types exactly."""
        assert AgentState.START.value == "start"
        assert AgentState.PROCESSING.value == "processing"
        assert AgentState.REVIEW_REQUEST.value == "review_request"
        assert AgentState.DONE.value == "done"
        assert AgentState.COMPLETED.value == "completed"
        assert AgentState.ERROR.value == "error"

    def test_agent_state_is_str_subclass(self) -> None:
        """AgentState inherits from str for direct JSON serialisation."""
        assert isinstance(AgentState.START, str)
        assert AgentState.PROCESSING == "processing"

    def test_all_states_are_lowercase(self) -> None:
        """All state values must be lowercase (TypeScript convention)."""
        for state in AgentState:
            assert state.value == state.value.lower(), (
                f"State {state!r} value {state.value!r} is not lowercase"
            )


# ---------------------------------------------------------------------------
# BaseAgent initialisation tests
# ---------------------------------------------------------------------------


class TestBaseAgentInit:
    """Verify constructor sets identity properties and initial state."""

    def test_initial_state_is_start(self, tmp_path: Path) -> None:
        agent = make_agent(workspace_dir=tmp_path)
        assert agent.state is AgentState.START

    def test_identity_properties_set_correctly(self, tmp_path: Path) -> None:
        agent = make_agent(workspace_dir=tmp_path)
        assert agent.name == "Alice"
        assert agent.color == "#EC4899"
        assert agent.step_number == 1
        assert agent.step_title == "AI Provider Configuration"

    def test_agent_config_defaults_to_empty_dict_when_file_missing(self, tmp_path: Path) -> None:
        """No agents.json → _agent_config == {}."""
        agent = make_agent(workspace_dir=tmp_path)
        assert agent._agent_config == {}


# ---------------------------------------------------------------------------
# Workspace creation tests
# ---------------------------------------------------------------------------


class TestCreateWorkspace:
    """Verify workspace directory structure is created correctly."""

    def test_create_workspace_creates_all_subfolders(self, tmp_path: Path) -> None:
        """All 6 required subdirectories must be created under workspace_dir."""
        make_agent(workspace_dir=tmp_path)
        for folder in WORKSPACE_SUBFOLDERS:
            assert (tmp_path / folder).is_dir(), (
                f"Expected workspace subdirectory '{folder}' to exist"
            )

    def test_create_workspace_is_idempotent(self, tmp_path: Path) -> None:
        """Calling _create_workspace twice must not raise any error."""
        agent = make_agent(workspace_dir=tmp_path)
        agent._create_workspace()  # second call — must not raise
        for folder in WORKSPACE_SUBFOLDERS:
            assert (tmp_path / folder).is_dir()


# ---------------------------------------------------------------------------
# Agent config loading tests
# ---------------------------------------------------------------------------


class TestLoadAgentConfig:
    """Verify agents.json config loading behaviour."""

    def test_load_agent_config_from_file(self, tmp_path: Path) -> None:
        """Agent reads its section from agents.json when the file exists."""
        config_dir = tmp_path / "configuration"
        config_dir.mkdir(parents=True, exist_ok=True)
        agents_data = {
            "alice": {"model": "claude-sonnet-4-6", "prompt": "config_v1"},
            "bob": {"model": "claude-opus-4"},
        }
        (config_dir / "agents.json").write_text(json.dumps(agents_data))

        agent = make_agent(workspace_dir=tmp_path)
        assert agent._agent_config == {"model": "claude-sonnet-4-6", "prompt": "config_v1"}

    def test_load_agent_config_defaults_when_key_missing(self, tmp_path: Path) -> None:
        """Agent uses empty dict when its key is absent from agents.json."""
        config_dir = tmp_path / "configuration"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "agents.json").write_text(json.dumps({"bob": {"model": "x"}}))

        agent = make_agent(workspace_dir=tmp_path)
        assert agent._agent_config == {}

    def test_load_agent_config_handles_malformed_json(self, tmp_path: Path) -> None:
        """Malformed agents.json must not raise — agent falls back to defaults."""
        config_dir = tmp_path / "configuration"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "agents.json").write_text("this is not json }")

        # Should not raise
        agent = make_agent(workspace_dir=tmp_path)
        assert agent._agent_config == {}


# ---------------------------------------------------------------------------
# Lifecycle transition tests  (broadcast_message mocked)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_broadcast():
    """Patch broadcast_message with an AsyncMock for the entire test."""
    with patch("ai_qa.api.websocket.broadcast_message", new_callable=AsyncMock) as mock:
        yield mock


class TestHandleStart:
    """Tests for the happy-path agent start lifecycle."""

    @pytest.mark.asyncio
    async def test_handle_start_transitions_to_processing_then_review(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        """handle_start: START → PROCESSING → REVIEW_REQUEST on success."""
        agent = make_agent(
            process_result=StageResult(success=True, data={"x": 1}),
            workspace_dir=tmp_path,
        )
        await agent.handle_start({"url": "http://example.com"})

        assert agent.state is AgentState.REVIEW_REQUEST

    @pytest.mark.asyncio
    async def test_handle_start_transitions_to_error_on_failure(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        """handle_start: START → PROCESSING → ERROR when process returns failure."""
        agent = make_agent(
            process_result=StageResult(success=False, errors=["something broke"]),
            workspace_dir=tmp_path,
        )
        await agent.handle_start({})
        assert agent.state is AgentState.ERROR

    @pytest.mark.asyncio
    async def test_handle_start_broadcasts_state_transitions(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        """broadcast_message is called for each state transition."""
        agent = make_agent(
            process_result=StageResult(success=True),
            workspace_dir=tmp_path,
        )
        await agent.handle_start({})
        # Should have been called at least twice (PROCESSING + REVIEW_REQUEST + content msg)
        assert mock_broadcast.call_count >= 2

    @pytest.mark.asyncio
    async def test_handle_start_broadcasts_error_message_on_failure(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        """Error message broadcast uses 'error' message_type."""
        agent = make_agent(
            process_result=StageResult(success=False, errors=["boom"]),
            workspace_dir=tmp_path,
        )
        await agent.handle_start({})
        # Last broadcast call should include messageType="error"
        last_call_args = mock_broadcast.call_args
        sent_message = last_call_args[0][0]
        assert sent_message.message_type == "error"


class TestHandleReject:
    """Tests for the reject→re-process loop."""

    @pytest.mark.asyncio
    async def test_handle_reject_loops_back_to_processing(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        """handle_reject: any state → PROCESSING → REVIEW_REQUEST on success."""
        agent = make_agent(
            process_result=StageResult(success=True, data={"revised": True}),
            workspace_dir=tmp_path,
        )
        # Set agent to REVIEW_REQUEST as it would be after handle_start
        agent.state = AgentState.REVIEW_REQUEST
        await agent.handle_reject("Please add more detail")
        assert agent.state is AgentState.REVIEW_REQUEST

    @pytest.mark.asyncio
    async def test_handle_reject_acknowledges_feedback(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        """handle_reject sends an acknowledgement text message first."""
        agent = make_agent(
            process_result=StageResult(success=True),
            workspace_dir=tmp_path,
        )
        agent.state = AgentState.REVIEW_REQUEST
        await agent.handle_reject("More detail please")

        # First call should be the ack text message (sender=agent, type=text)
        first_call_message = mock_broadcast.call_args_list[0][0][0]
        assert first_call_message.sender == "agent"
        assert first_call_message.message_type == "text"
        assert "More detail please" in first_call_message.content

    @pytest.mark.asyncio
    async def test_handle_reject_transitions_to_error_on_failure(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        """handle_reject → ERROR when re-processing returns failure."""
        agent = make_agent(
            process_result=StageResult(success=False, errors=["cannot redo"]),
            workspace_dir=tmp_path,
        )
        agent.state = AgentState.REVIEW_REQUEST
        await agent.handle_reject("Some feedback")
        assert agent.state is AgentState.ERROR


class TestHandleApprove:
    """Tests for approval lifecycle."""

    @pytest.mark.asyncio
    async def test_handle_approve_transitions_to_done(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        """handle_approve: any state → DONE."""
        agent = make_agent(workspace_dir=tmp_path)
        agent.state = AgentState.REVIEW_REQUEST
        await agent.handle_approve()
        assert agent.state is AgentState.DONE

    @pytest.mark.asyncio
    async def test_handle_approve_broadcasts_success_message(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        """handle_approve broadcasts a 'success' message."""
        agent = make_agent(workspace_dir=tmp_path)
        agent.state = AgentState.REVIEW_REQUEST
        await agent.handle_approve()

        last_message = mock_broadcast.call_args_list[-1][0][0]
        assert last_message.message_type == "success"


# ---------------------------------------------------------------------------
# send_message tests
# ---------------------------------------------------------------------------


class TestSendMessage:
    """Verify AgentMessage construction and broadcast."""

    @pytest.mark.asyncio
    async def test_agent_sends_message_via_broadcast(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        """send_message calls broadcast_message with correct AgentMessage."""
        agent = make_agent(workspace_dir=tmp_path)
        await agent.send_message("Hello from Alice", message_type="info")

        mock_broadcast.assert_called_once()
        sent = mock_broadcast.call_args[0][0]
        assert sent.sender == "agent"
        assert sent.agent_name == "Alice"
        assert sent.content == "Hello from Alice"
        assert sent.message_type == "info"

    @pytest.mark.asyncio
    async def test_send_message_with_metadata(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        """Metadata dict is attached to the broadcasted AgentMessage."""
        agent = make_agent(workspace_dir=tmp_path)
        meta = {"key": "value"}
        await agent.send_message("data", metadata=meta)
        sent = mock_broadcast.call_args[0][0]
        assert sent.metadata == meta


# ---------------------------------------------------------------------------
# transition_to tests
# ---------------------------------------------------------------------------


class TestTransitionTo:
    """Verify state transitions broadcast system messages."""

    @pytest.mark.asyncio
    async def test_transition_to_updates_state(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        agent = make_agent(workspace_dir=tmp_path)
        await agent.transition_to(AgentState.PROCESSING)
        assert agent.state is AgentState.PROCESSING

    @pytest.mark.asyncio
    async def test_transition_to_broadcasts_system_message(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        agent = make_agent(workspace_dir=tmp_path)
        await agent.transition_to(AgentState.REVIEW_REQUEST)

        mock_broadcast.assert_called_once()
        msg = mock_broadcast.call_args[0][0]
        assert msg.sender == "system"
        assert msg.content == "review_request"
        assert msg.metadata == {"state": "review_request", "step": 1}


# ---------------------------------------------------------------------------
# PipelineError handling in lifecycle methods
# ---------------------------------------------------------------------------


class TestPipelineErrorHandling:
    """Verify PipelineError raised in process() is caught and converted to ERROR state."""

    @pytest.mark.asyncio
    async def test_pipeline_error_in_handle_start_transitions_to_error(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        """PipelineError raised in process() must transition to ERROR, not propagate."""
        from ai_qa.exceptions import PipelineError

        class FailingAgent(ConcreteAgent):
            async def process(
                self, input_data: dict[str, Any], feedback: str | None = None
            ) -> StageResult:
                raise PipelineError("Pipeline broke unexpectedly")

        agent = FailingAgent(workspace_dir=tmp_path)
        await agent.handle_start({})
        assert agent.state is AgentState.ERROR

    @pytest.mark.asyncio
    async def test_pipeline_error_in_handle_reject_transitions_to_error(
        self, tmp_path: Path, mock_broadcast: AsyncMock
    ) -> None:
        from ai_qa.exceptions import PipelineError

        class FailingAgent(ConcreteAgent):
            async def process(
                self, input_data: dict[str, Any], feedback: str | None = None
            ) -> StageResult:
                raise PipelineError("Cannot re-process")

        agent = FailingAgent(workspace_dir=tmp_path)
        agent.state = AgentState.REVIEW_REQUEST
        await agent.handle_reject("feedback")
        assert agent.state is AgentState.ERROR
