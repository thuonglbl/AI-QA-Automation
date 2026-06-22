"""Tests for MCPClient.check_required_tools capability checking."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_qa.exceptions import MCPConnectionError
from ai_qa.mcp.client import MCPClient
from ai_qa.mcp.tools import Tool


def _make_tool(name: str) -> Tool:
    return Tool(name=name, description="", parameters=[], returns="")


@pytest.fixture
def mock_mcp_client() -> MCPClient:
    with patch("ai_qa.mcp.client.ConnectionManager"):
        client = MCPClient(server_url="http://localhost:3000/sse")
    client._connection = MagicMock()
    client._connection.is_connected = True
    return client


class TestCheckRequiredTools:
    async def test_empty_required_returns_empty(self, mock_mcp_client: MCPClient) -> None:
        missing = await mock_mcp_client.check_required_tools([])
        assert missing == []

    async def test_all_present_returns_empty(self, mock_mcp_client: MCPClient) -> None:
        mock_mcp_client.list_tools = AsyncMock(
            return_value=[
                _make_tool("tool_a"),
                _make_tool("tool_b"),
            ]
        )
        missing = await mock_mcp_client.check_required_tools(["tool_a", "tool_b"])
        assert missing == []

    async def test_missing_tool_returned(self, mock_mcp_client: MCPClient) -> None:
        mock_mcp_client.list_tools = AsyncMock(return_value=[_make_tool("tool_a")])
        missing = await mock_mcp_client.check_required_tools(["tool_a", "tool_b"])
        assert missing == ["tool_b"]

    async def test_all_missing(self, mock_mcp_client: MCPClient) -> None:
        mock_mcp_client.list_tools = AsyncMock(return_value=[])
        missing = await mock_mcp_client.check_required_tools(["tool_a", "tool_b"])
        assert set(missing) == {"tool_a", "tool_b"}

    async def test_propagates_connection_error(self, mock_mcp_client: MCPClient) -> None:
        mock_mcp_client.list_tools = AsyncMock(side_effect=MCPConnectionError("cannot connect"))
        with pytest.raises(MCPConnectionError):
            await mock_mcp_client.check_required_tools(["tool_a"])

    async def test_does_not_bypass_cache(self, mock_mcp_client: MCPClient) -> None:
        mock_mcp_client.list_tools = AsyncMock(return_value=[_make_tool("tool_a")])
        await mock_mcp_client.check_required_tools(["tool_a"])
        # list_tools is delegated with default args (uses_cache=True by default)
        mock_mcp_client.list_tools.assert_called_once()
