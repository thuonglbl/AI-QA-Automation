from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_qa.agents.base import AgentState
from ai_qa.agents.bob import BobAgent
from ai_qa.exceptions import PipelineError
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
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
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
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
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
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
        patch.object(bob_agent, "get_llm_config") as mock_llm_config,
    ):
        mock_llm_config.return_value = MagicMock()
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
        mock_reader.read_page_by_id.return_value = StageResult(
            success=False, data=None, errors=["mock failure"], warnings=[], confidence=0.0
        )
        mock_reader_class.return_value = mock_reader

        # Call extract_descendants — should fail gracefully with no pages
        await bob_agent._extract_descendants("Test Parent")

        # MCPClient should only be instantiated ONCE
        assert mock_mcp_client_class.call_count == 1


@pytest.mark.asyncio
async def test_bob_handle_start_confirm_parent(bob_agent: BobAgent) -> None:
    """Test handle_start when process returns confirm_parent."""
    with patch.object(bob_agent, "process") as mock_process:
        mock_process.return_value = StageResult(
            success=True, data={"type": "confirm_parent", "suggested_page": "url1"}
        )
        await bob_agent.handle_start({"space_key": "TEST"})
        assert bob_agent.phase == "confirm_parent"
        assert bob_agent.state == AgentState.REVIEW_REQUEST


@pytest.mark.asyncio
async def test_bob_handle_start_review_markdown(bob_agent: BobAgent) -> None:
    """Test handle_start when pages are successfully processed."""
    with patch.object(bob_agent, "process") as mock_process:
        mock_process.return_value = StageResult(success=True)
        bob_agent.pages = [{"title": "Page 1"}]
        await bob_agent.handle_start({"confluence_url": "test"})
        assert bob_agent.phase == "review_markdown"
        assert bob_agent.state == AgentState.REVIEW_REQUEST


@pytest.mark.asyncio
async def test_bob_handle_start_error(bob_agent: BobAgent) -> None:
    """Test handle_start when process raises an exception."""
    with patch.object(bob_agent, "process") as mock_process:
        mock_process.side_effect = Exception("Crash")
        await bob_agent.handle_start({"confluence_url": "test"})
        assert bob_agent.state == AgentState.ERROR


@pytest.mark.asyncio
async def test_bob_process_with_feedback(bob_agent: BobAgent) -> None:
    """Test process with feedback parameter."""
    bob_agent.pages = [
        {
            "title": "Page 1",
            "content": "Initial",
            "page_id": "1",
            "url": "url",
            "space_key": "SPACE",
        }
    ]
    bob_agent.current_page_index = 0
    result = await bob_agent.process({"confluence_url": "test"}, feedback="Fix this")
    assert result.success is True
    assert result.data == bob_agent.pages[0]


@pytest.mark.asyncio
async def test_bob_process_disconnects_mcp_on_completion(bob_agent: BobAgent) -> None:
    """AC3: process() must call disconnect() on the MCP client to release server session."""
    input_data = {
        "confluence_url": "https://company.atlassian.net/wiki/spaces/TEST/pages/111/Test",
    }

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp_client_class,
        patch("ai_qa.agents.bob.AppSettings"),
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
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
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
    ):
        mock_client = AsyncMock()
        mock_client.is_connected = True
        mock_mcp_client_class.return_value = mock_client

        mock_reader = AsyncMock()
        mock_reader.get_children_by_id.side_effect = Exception("Simulated error")
        mock_reader.read_page_by_id.return_value = StageResult(
            success=False, data=None, errors=["mock failure"], warnings=[], confidence=0.0
        )
        mock_reader_class.return_value = mock_reader

        with pytest.raises(Exception, match="Simulated error"):
            await bob_agent._extract_descendants("Test Parent")

        mock_client.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_bob_extract_descendants_disconnects_mcp_on_completion(bob_agent: BobAgent) -> None:
    """AC3: _extract_descendants() must call disconnect() when done, releasing the MCP session."""
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
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
        patch.object(bob_agent, "get_llm_config") as mock_llm_config,
    ):
        mock_llm_config.return_value = MagicMock()
        mock_client = AsyncMock()
        mock_client.is_connected = True
        mock_mcp_client_class.return_value = mock_client

        mock_reader = AsyncMock()
        mock_reader.get_children_by_id.return_value = StageResult(
            success=True, data=[], errors=[], warnings=[], confidence=1.0
        )
        mock_reader.read_page_by_id.return_value = StageResult(
            success=False, data=None, errors=["mock failure"], warnings=[], confidence=0.0
        )
        mock_reader_class.return_value = mock_reader

        await bob_agent._extract_descendants("Test Parent")

        # The MCP client MUST be disconnected via except/finally handler
        mock_client.disconnect.assert_called()


@pytest.mark.asyncio
async def test_bob_get_llm_config_raises_on_missing_api_key(
    bob_agent: BobAgent,
) -> None:
    """Patch 7: get_llm_config() raises PipelineError with UX-DR12 format when API key is missing."""
    # Ensure project_context exists so the production path is taken
    assert bob_agent.project_context is not None

    # Mock the secret service to return None (no secret stored)
    with (
        patch("ai_qa.secrets.service.get_user_secret", return_value=None),
        patch.dict("os.environ", {}, clear=True),
    ):
        with pytest.raises(PipelineError, match="API key not configured"):
            bob_agent.get_llm_config()


@pytest.mark.asyncio
async def test_bob_process_raises_on_missing_mcp_secret(
    bob_agent: BobAgent,
) -> None:
    """Patch 10: process() raises PipelineError when get_user_secret returns None."""
    input_data = {"confluence_url": "https://company.atlassian.net/wiki/spaces/TEST"}

    with patch("ai_qa.agents.bob.get_user_secret", return_value=None):
        with pytest.raises(PipelineError, match="MCP PAT not configured"):
            await bob_agent.process(input_data)


@pytest.mark.asyncio
async def test_bob_extract_descendants_raises_on_missing_mcp_secret(
    bob_agent: BobAgent,
) -> None:
    """Patch 10: _extract_descendants() raises PipelineError when get_user_secret returns None."""
    bob_agent._page_id = "12345"
    bob_agent._space_key = "TEST"

    with patch("ai_qa.agents.bob.get_user_secret", return_value=None):
        with pytest.raises(PipelineError, match="MCP PAT not configured"):
            await bob_agent._extract_descendants("Test Parent")


@pytest.mark.asyncio
async def test_bob_process_raises_on_empty_string_mcp_secret(
    bob_agent: BobAgent,
) -> None:
    """Patch 9: process() raises PipelineError when secret is empty string."""
    input_data = {"confluence_url": "https://company.atlassian.net/wiki/spaces/TEST"}

    with patch("ai_qa.agents.bob.get_user_secret", return_value=""):
        with pytest.raises(PipelineError, match="MCP PAT not configured"):
            await bob_agent.process(input_data)
