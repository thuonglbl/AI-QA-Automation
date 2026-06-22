"""Unit tests for the BaseAgent lifecycle and AgentState enum.

``BaseAgent`` is abstract, so these tests drive it through a minimal concrete
subclass that implements ``process``.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from ai_qa.agents.base import AgentState, BaseAgent
from ai_qa.models import StageResult


class _StubAgent(BaseAgent):
    """Minimal concrete agent used to exercise the shared lifecycle."""

    def __init__(self, **overrides: Any) -> None:
        kwargs: dict[str, Any] = {
            "name": "Alice",
            "color": "#EC4899",
            "step_number": 1,
            "step_title": "Test Step",
        }
        kwargs.update(overrides)
        super().__init__(**kwargs)

    async def process(self, input_data: dict[str, Any], feedback: str | None = None) -> StageResult:
        return StageResult(success=True, data={"output": "ok"})


class TestBaseAgent:
    def test_cannot_instantiate_abstract_base_directly(self) -> None:
        # Assigning to a plain ``type`` hides the abstractness from the type
        # checker so we can assert the runtime guard without a type-ignore.
        base_cls: type = BaseAgent
        with pytest.raises(TypeError):
            base_cls(name="X", color="#000000", step_number=1, step_title="X")

    def test_initial_state_is_start(self) -> None:
        agent = _StubAgent()
        assert agent.state == AgentState.START

    def test_set_user_context_sets_email(self) -> None:
        agent = _StubAgent()
        agent.set_user_context("test@example.com")
        assert agent._user_email == "test@example.com"

    def test_set_project_context_sets_context(self) -> None:
        agent = _StubAgent()
        mock_context = MagicMock()
        mock_context.user_id = "user-1"
        mock_context.user_email = "ctx@example.com"
        mock_context.thread_id = None
        agent.set_project_context(mock_context)
        assert agent.project_context is mock_context

    def test_name_reflects_constructor_argument(self) -> None:
        assert _StubAgent(name="Bob").name == "Bob"

    def test_agent_state_transitions_are_assignable(self) -> None:
        agent = _StubAgent()
        assert agent.state == AgentState.START
        agent.state = AgentState.PROCESSING
        assert agent.state == AgentState.PROCESSING
        agent.state = AgentState.DONE
        assert agent.state == AgentState.DONE

    def test_custom_step_number(self) -> None:
        assert _StubAgent(step_number=3).step_number == 3
