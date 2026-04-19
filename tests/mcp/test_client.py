"""Tests for MCPClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_qa.exceptions import MCPConnectionError, MCPToolError
from ai_qa.mcp import MCPClient, Tool


class TestMCPClientInit:
    """Test client initialization."""

    def test_init_with_url(self):
        """Initialize with explicit URL."""
        client = MCPClient(server_url="http://localhost:3000/sse")
        assert client.server_url == "http://localhost:3000/sse"
        assert not client.is_connected

    def test_init_requires_url(self):
        """Require server URL."""
        from ai_qa.config import AppSettings

        settings = AppSettings(mcp_server_url="")
        with pytest.raises(MCPConnectionError, match="No MCP server URL"):
            MCPClient(server_url="", settings=settings)

    def test_init_with_settings(self):
        """Initialize with settings."""
        from ai_qa.config import AppSettings

        settings = AppSettings(mcp_server_url="http://server:3000")
        client = MCPClient(settings=settings)
        assert client.server_url == "http://server:3000"


class TestMCPClientConnect:
    """Test connection functionality."""

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Successful connection."""
        client = MCPClient(server_url="http://localhost:3000/sse")

        with patch.object(client._connection_manager, "get_connection") as mock_get:
            mock_conn = AsyncMock()
            mock_conn.is_connected = True
            mock_get.return_value = mock_conn

            await client.connect()
            assert client.is_connected

    @pytest.mark.asyncio
    async def test_connect_already_connected(self):
        """No-op if already connected."""
        client = MCPClient(server_url="http://localhost:3000/sse")

        with patch.object(client._connection_manager, "get_connection") as mock_get:
            mock_conn = AsyncMock()
            mock_conn.is_connected = True
            mock_get.return_value = mock_conn

            await client.connect()
            await client.connect()  # Second call should be no-op
            assert client.is_connected
            mock_conn.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Disconnect from server."""
        client = MCPClient(server_url="http://localhost:3000/sse")

        with patch.object(client._connection_manager, "get_connection") as mock_get:
            mock_conn = AsyncMock()
            mock_conn.is_connected = True
            mock_get.return_value = mock_conn

            await client.connect()
            await client.disconnect()
            assert not client.is_connected


class TestMCPClientTools:
    """Test tool operations."""

    @pytest.fixture
    async def connected_client(self):
        """Create a connected client for testing."""
        client = MCPClient(server_url="http://localhost:3000/sse")

        with patch.object(client._connection_manager, "get_connection") as mock_get:
            mock_conn = AsyncMock()
            mock_conn.is_connected = True
            mock_get.return_value = mock_conn

            await client.connect()
            yield client

    @pytest.mark.asyncio
    async def test_list_tools_not_connected(self):
        """Raise error if not connected."""
        client = MCPClient(server_url="http://localhost:3000/sse")

        with pytest.raises(MCPConnectionError, match="Not connected"):
            await client.list_tools()

    @pytest.mark.asyncio
    async def test_call_tool_not_connected(self):
        """Raise error if not connected."""
        client = MCPClient(server_url="http://localhost:3000/sse")

        with pytest.raises(MCPConnectionError, match="Not connected"):
            await client.call_tool("test_tool")

    @pytest.mark.asyncio
    async def test_call_tool_success(self):
        """Successful tool call."""
        client = MCPClient(server_url="http://localhost:3000/sse")

        with patch.object(client._connection_manager, "get_connection") as mock_get:
            mock_conn = AsyncMock()
            mock_conn.is_connected = True
            mock_conn.call_tool.return_value = {"result": "success"}
            mock_get.return_value = mock_conn

            await client.connect()
            result = await client.call_tool("test_tool", {"param": "value"})

            assert result.success
            assert result.data == {"result": "success"}

    @pytest.mark.asyncio
    async def test_call_tool_failure(self):
        """Tool execution failure."""
        client = MCPClient(server_url="http://localhost:3000/sse")

        with patch.object(client._connection_manager, "get_connection") as mock_get:
            mock_conn = AsyncMock()
            mock_conn.is_connected = True
            mock_conn.call_tool.side_effect = Exception("Tool error")
            mock_get.return_value = mock_conn

            await client.connect()

            with pytest.raises(MCPToolError, match="execution failed"):
                await client.call_tool("test_tool")

    @pytest.mark.asyncio
    async def test_discover_capabilities(self):
        """Discover server capabilities."""
        client = MCPClient(server_url="http://localhost:3000/sse")

        with patch.object(client._connection_manager, "get_connection") as mock_get:
            mock_conn = AsyncMock()
            mock_conn.is_connected = True
            mock_conn.list_tools.return_value = [
                Tool(name="tool1", description="Tool 1"),
                Tool(name="tool2", description="Tool 2"),
            ]
            mock_get.return_value = mock_conn

            await client.connect()
            caps = await client.discover_capabilities()

            assert "tool1" in caps.tools
            assert "tool2" in caps.tools
            assert caps.protocol_version == "1.0"


class TestMCPClientCache:
    """Test caching functionality."""

    @pytest.mark.asyncio
    async def test_tool_caching(self):
        """Tools are cached after first fetch."""
        client = MCPClient(server_url="http://localhost:3000/sse")

        with patch.object(client._connection_manager, "get_connection") as mock_get:
            mock_conn = AsyncMock()
            mock_conn.is_connected = True
            mock_conn.list_tools.return_value = [
                Tool(name="cached_tool", description="Cached"),
            ]
            mock_get.return_value = mock_conn

            await client.connect()

            # First call - should fetch
            tools1 = await client.list_tools()
            assert len(tools1) == 1
            assert mock_conn.list_tools.call_count == 1

            # Check cache
            cached = client.get_cached_tool("cached_tool")
            assert cached is not None
            assert cached.name == "cached_tool"

    @pytest.mark.asyncio
    async def test_clear_cache(self):
        """Clear tool cache."""
        client = MCPClient(server_url="http://localhost:3000/sse")

        with patch.object(client._connection_manager, "get_connection") as mock_get:
            mock_conn = AsyncMock()
            mock_conn.is_connected = True
            mock_conn.list_tools.return_value = [
                Tool(name="tool1", description="Tool 1"),
            ]
            mock_get.return_value = mock_conn

            await client.connect()
            await client.list_tools()

            assert len(client._tool_cache.list_cached()) > 0

            client.clear_cache()
            assert len(client._tool_cache.list_cached()) == 0


class TestMCPClientContextManager:
    """Test async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Use as async context manager."""
        with patch("ai_qa.mcp.client.ConnectionManager") as mock_mgr_class:
            mock_mgr = MagicMock()
            mock_conn = AsyncMock()
            # Simulate connection becoming connected after connect() is called
            mock_conn.is_connected = True
            mock_mgr.get_connection.return_value = mock_conn
            mock_mgr_class.return_value = mock_mgr

            async with MCPClient(server_url="http://localhost:3000/sse") as client:
                assert client.is_connected

            # Should disconnect on exit
            mock_conn.disconnect.assert_called_once()
