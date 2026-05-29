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
async def test_bob_initial_process_with_requirement_page(bob_agent: BobAgent) -> None:
    """Test process() uses the requirement page URL if found via find_parent_pages."""
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
        mock_reader.find_parent_pages.return_value = StageResult(
            success=True,
            data=[
                MagicMock(
                    url="https://company.atlassian.net/wiki/spaces/TEST/pages/123/Requirements"
                )
            ],
            errors=[],
            warnings=[],
            confidence=1.0,
        )
        mock_reader_class.return_value = mock_reader

        result = await bob_agent.process(input_data)

        assert result.success is True
        assert result.data is not None
        assert result.data["type"] == "confirm_parent"
        # Verify it used the suggested requirement page URL instead of the base URL
        assert (
            result.data["suggested_page"]
            == "https://company.atlassian.net/wiki/spaces/TEST/pages/123/Requirements"
        )


@pytest.mark.asyncio
async def test_bob_initial_process_fallback_to_confluence_url(bob_agent: BobAgent) -> None:
    """Test process() falls back to the original URL if no requirement page is found."""
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
        # Simulate no requirement page found
        mock_reader.find_parent_pages.return_value = StageResult(
            success=True,
            data=[],
            errors=[],
            warnings=[],
            confidence=0.0,
        )
        mock_reader_class.return_value = mock_reader

        result = await bob_agent.process(input_data)

        assert result.success is True
        assert result.data is not None
        assert result.data["type"] == "confirm_parent"
        # Verify it fell back to the original input URL
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


@pytest.mark.asyncio
async def test_bob_extract_descendants_creates_single_mcp_client(bob_agent: BobAgent) -> None:
    """AC2: _extract_descendants must create only ONE MCPClient (not open a new connection)."""
    bob_agent._mcp_pat = "test-pat"
    bob_agent._page_id = "12345"
    bob_agent._space_key = "TEST"

    # Configure project mock to return a Project-like object with confluence_base_url
    mock_project = MagicMock()
    mock_project.confluence_base_url = "https://confluence.company.com"
    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.return_value = mock_project

    mock_client = AsyncMock()
    mock_client.is_connected = True

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp_client_class,
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.AppSettings"),
        patch("ai_qa.agents.bob.LLMClient"),
        patch("ai_qa.agents.bob.RequirementFormatter"),
    ):
        mock_mcp_client_class.return_value = mock_client

        # Return empty list for children so it exits gracefully with "no pages" error
        mock_reader = AsyncMock()
        mock_reader.get_children_by_id.return_value = StageResult(
            success=True,
            data=[],
            errors=[],
            warnings=[],
            confidence=1.0,
        )
        mock_reader_class.return_value = mock_reader

        # Call extract_descendants — should fail gracefully with no pages
        await bob_agent._extract_descendants("Test Parent")

        # MCPClient should only be instantiated ONCE (a single connection for extraction)
        assert mock_mcp_client_class.call_count == 1, (
            f"MCPClient was instantiated {mock_mcp_client_class.call_count} times, expected 1"
        )


@pytest.mark.asyncio
async def test_bob_process_disconnects_mcp_on_completion(bob_agent: BobAgent) -> None:
    """AC3: process() must call disconnect() on the MCP client to release server session."""
    input_data = {
        "confluence_url": "https://company.atlassian.net/wiki/spaces/TEST/pages/111/Test",
        "mcp_pat": "test-pat",
    }

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp_client_class,
        patch("ai_qa.agents.bob.AppSettings"),
    ):
        mock_client = AsyncMock()
        mock_client.is_connected = True
        mock_mcp_client_class.return_value = mock_client

        await bob_agent.process(input_data)

        # disconnect must be called to release MCP session
        mock_client.disconnect.assert_called()


@pytest.mark.asyncio
async def test_bob_extract_descendants_disconnects_mcp_on_exception(bob_agent: BobAgent) -> None:
    """AC3: _extract_descendants() must call disconnect() even if an exception occurs."""
    bob_agent._mcp_pat = "test-pat"
    bob_agent._page_id = "12345"

    mock_project = MagicMock()
    mock_project.confluence_base_url = "https://confluence.company.com"
    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.return_value = mock_project

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp_client_class,
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.AppSettings"),
        patch("ai_qa.agents.bob.LLMClient"),
        patch("ai_qa.agents.bob.RequirementFormatter"),
    ):
        mock_client = AsyncMock()
        mock_client.is_connected = True
        mock_mcp_client_class.return_value = mock_client

        mock_reader = AsyncMock()
        mock_reader.get_children_by_id.side_effect = Exception("Simulated error")
        mock_reader_class.return_value = mock_reader

        with pytest.raises(Exception, match="Simulated error"):
            await bob_agent._extract_descendants("Test Parent")

        mock_client.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_bob_extract_descendants_disconnects_mcp_on_completion(bob_agent: BobAgent) -> None:
    """AC3: _extract_descendants() must call disconnect() when done, releasing the MCP session."""
    bob_agent._mcp_pat = "test-pat"
    bob_agent._page_id = "12345"

    # Configure project mock to return a Project-like object with confluence_base_url
    mock_project = MagicMock()
    mock_project.confluence_base_url = "https://confluence.company.com"
    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.return_value = mock_project

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp_client_class,
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.AppSettings"),
        patch("ai_qa.agents.bob.LLMClient"),
        patch("ai_qa.agents.bob.RequirementFormatter"),
    ):
        mock_client = AsyncMock()
        mock_client.is_connected = True
        mock_mcp_client_class.return_value = mock_client

        mock_reader = AsyncMock()
        mock_reader.get_children_by_id.return_value = StageResult(
            success=True, data=[], errors=[], warnings=[], confidence=1.0
        )
        mock_reader_class.return_value = mock_reader

        await bob_agent._extract_descendants("Test Parent")

        # The MCP client MUST be disconnected proactively (via finally block)
        mock_client.disconnect.assert_called()
