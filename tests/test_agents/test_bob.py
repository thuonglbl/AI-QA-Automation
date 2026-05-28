from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_qa.agents.base import AgentState
from ai_qa.agents.bob import BobAgent
from ai_qa.models import StageResult


@pytest.fixture
def bob_agent(mock_project_context: MagicMock) -> BobAgent:
    agent = BobAgent(
        name="Bob", color="#2196F3", step_number=3, step_title="Requirements Extraction"
    )
    agent.set_project_context(mock_project_context)
    return agent


@pytest.mark.asyncio
async def test_bob_initial_process(bob_agent: BobAgent) -> None:
    """Test initial processing creates a list of pages and transitions state appropriately."""
    input_data = {"confluence_url": "https://company.atlassian.net/wiki/spaces/TEST"}

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp_client_class,
        patch("ai_qa.agents.bob.ConfluenceURLParser") as mock_parser_class,
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
    ):
        mock_mcp_client = AsyncMock()
        mock_mcp_client_class.return_value = mock_mcp_client

        mock_parser = mock_parser_class.return_value
        mock_parser.extract_page_id.return_value = None
        mock_parser.extract_space_key.return_value = "TEST"

        mock_reader = AsyncMock()
        mock_reader.list_pages_in_space.return_value = StageResult(
            success=True,
            data=[AsyncMock(page_id="1", url="http://1")],
            errors=[],
            warnings=[],
            confidence=1.0,
        )
        mock_reader.read_multiple_pages.return_value = StageResult(
            success=True,
            data=[AsyncMock(page_id="1", content="hi")],
            errors=[],
            warnings=[],
            confidence=1.0,
        )
        mock_reader_class.return_value = mock_reader

        result = await bob_agent.process(input_data)

        assert result.success is True
        assert result.data is not None
        assert result.data["type"] == "confirm_parent"
        assert result.data["suggested_page"] == input_data["confluence_url"]


@pytest.mark.asyncio
async def test_bob_handle_approve_pagination(bob_agent: BobAgent) -> None:
    """Test custom handle_approve advances to next page or completes."""
    bob_agent.pages = [
        {"page_title": "1", "requirement_md": "1", "page_id": "1"},
        {"page_title": "2", "requirement_md": "2", "page_id": "2"},
    ]
    bob_agent.current_page_index = 0

    with (
        patch.object(bob_agent, "transition_to") as mock_transition,
        patch.object(bob_agent, "send_message"),
    ):
        await bob_agent.handle_approve()

        assert bob_agent.current_page_index == 1
        mock_transition.assert_not_called()

        await bob_agent.handle_approve()
        assert bob_agent.current_page_index == 2
        mock_transition.assert_called_with(AgentState.DONE)
