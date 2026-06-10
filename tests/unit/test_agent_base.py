"""Unit tests for BaseAgent class."""

from unittest.mock import MagicMock

import pytest

from ai_qa.agents.base import AgentState, BaseAgent


class TestBaseAgent:
    @pytest.mark.asyncio
    async def test_initial_state_is_idle(self):
        agent = BaseAgent()
        assert agent.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_set_user_context_sets_email(self):
        agent = BaseAgent()
        agent.set_user_context("test@example.com")
        assert agent.user_email == "test@example.com"

    @pytest.mark.asyncio
    async def test_set_project_context_sets_context(self):
        agent = BaseAgent()
        mock_context = MagicMock()
        mock_context.user_id = "user-1"
        mock_context.project_id = "proj-1"
        agent.set_project_context(mock_context)
        assert agent.project_context == mock_context

    @pytest.mark.asyncio
    async def test_handle_start_without_override_raises(self):
        agent = BaseAgent()
        with pytest.raises(NotImplementedError):
            await agent.handle_start({})

    @pytest.mark.asyncio
    async def test_name_default_is_class_name(self):
        agent = BaseAgent()
        assert agent.name == "BaseAgent"

    def test_agent_state_transitions_valid(self):
        agent = BaseAgent()
        assert agent.state == AgentState.IDLE
        agent.state = AgentState.PROCESSING
        assert agent.state == AgentState.PROCESSING
        agent.state = AgentState.DONE
        assert agent.state == AgentState.DONE

    def test_custom_step_number(self):
        agent = BaseAgent(step_number=3)
        assert agent.step_number == 3
