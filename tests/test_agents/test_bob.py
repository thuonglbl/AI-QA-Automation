from unittest.mock import AsyncMock, patch

import pytest

from ai_qa.agents.base import AgentState
from ai_qa.agents.bob import BobAgent
from ai_qa.models import StageResult


@pytest.fixture
def bob_agent() -> BobAgent:
    return BobAgent(
        name="Bob", color="#2196F3", step_number=3, step_title="Requirements Extraction"
    )


@pytest.mark.asyncio
async def test_bob_initial_process(bob_agent: BobAgent) -> None:
    """Test initial processing creates a list of pages and transitions state appropriately."""
    input_data = {"confluence_url": "https://company.atlassian.net/wiki/spaces/TEST"}

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp_client_class,
        patch("ai_qa.agents.bob.ConfluenceURLParser") as mock_parser_class,
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.ContentParser") as mock_content_parser_class,
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

        mock_content_parser = AsyncMock()
        mock_content_parser.parse_multiple.return_value = StageResult(
            success=True,
            data=[AsyncMock(page_id="1", markdown="parsed hi")],
            errors=[],
            warnings=[],
            confidence=1.0,
        )
        mock_content_parser_class.return_value = mock_content_parser

        result = await bob_agent.process(input_data)

        assert result.success is True
        assert len(bob_agent.pages) == 1
        assert bob_agent.current_page_index == 0


@pytest.mark.asyncio
async def test_bob_handle_approve_pagination(bob_agent: BobAgent) -> None:
    """Test custom handle_approve advances to next page or completes."""
    bob_agent.pages = [
        AsyncMock(page_title="1", markdown="1", source_url="1"),
        AsyncMock(page_title="2", markdown="2", source_url="2"),
    ]
    bob_agent.current_page_index = 0

    with (
        patch.object(bob_agent, "transition_to") as mock_transition,
        patch.object(bob_agent, "send_message"),
        patch("ai_qa.agents.bob.OutputWriter") as mock_writer_class,
    ):
        mock_writer = AsyncMock()
        mock_writer.write.return_value = StageResult(
            success=True, data={}, errors=[], warnings=[], confidence=1.0
        )
        mock_writer_class.return_value = mock_writer

        await bob_agent.handle_approve()

        assert bob_agent.current_page_index == 1
        mock_transition.assert_called_with(AgentState.REVIEW_REQUEST)

        await bob_agent.handle_approve()
        assert bob_agent.current_page_index == 2
        mock_transition.assert_called_with(AgentState.DONE)
