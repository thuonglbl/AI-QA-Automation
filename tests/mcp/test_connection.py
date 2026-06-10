"""Tests for MCP connection management."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_qa.config import AppSettings
from ai_qa.exceptions import MCPConnectionError, MCPTimeoutError
from ai_qa.mcp.connection import ConnectionManager, ConnectionState, MCPConnection
from ai_qa.mcp.tools import Tool


class TestMCPConnection:
    """Test MCPConnection class."""

    def test_init_sse_url(self):
        """Initialize with SSE URL."""
        conn = MCPConnection("http://localhost:3000/sse")
        assert conn.server_url == "http://localhost:3000/sse"
        assert conn.state == ConnectionState.DISCONNECTED
        assert not conn.is_connected

    def test_init_stdio_url(self):
        """Initialize with stdio command."""
        conn = MCPConnection("stdio:python -m mcp.server")
        assert conn.server_url == "stdio:python -m mcp.server"

    @pytest.mark.asyncio
    async def test_connect_not_connected(self):
        """Connect if not already connected."""
        conn = MCPConnection("http://localhost:3000/sse", use_streamable_http=False)

        with patch("ai_qa.mcp.connection.sse_client") as mock_sse:
            mock_ctx = AsyncMock()
            mock_transport = (AsyncMock(), AsyncMock())
            mock_ctx.__aenter__.return_value = mock_transport
            mock_sse.return_value = mock_ctx

            with patch("ai_qa.mcp.connection.ClientSession") as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value.__aenter__.return_value = mock_session

                await conn.connect()
                assert conn.is_connected

    @pytest.mark.asyncio
    async def test_connect_already_connected(self):
        """No-op if already connected."""
        conn = MCPConnection("http://localhost:3000/sse", use_streamable_http=False)

        with patch("ai_qa.mcp.connection.sse_client") as mock_sse:
            mock_ctx = AsyncMock()
            mock_transport = (AsyncMock(), AsyncMock())
            mock_ctx.__aenter__.return_value = mock_transport
            mock_sse.return_value = mock_ctx

            with patch("ai_qa.mcp.connection.ClientSession") as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value.__aenter__.return_value = mock_session

                await conn.connect()
                await conn.connect()  # Second call
                assert conn.is_connected
                mock_session.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Disconnect from server."""
        conn = MCPConnection("http://localhost:3000/sse", use_streamable_http=False)

        with patch("ai_qa.mcp.connection.sse_client") as mock_sse:
            mock_ctx = AsyncMock()
            mock_transport = (AsyncMock(), AsyncMock())
            mock_ctx.__aenter__.return_value = mock_transport
            mock_sse.return_value = mock_ctx

            with patch("ai_qa.mcp.connection.ClientSession") as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value.__aenter__.return_value = mock_session

                await conn.connect()
                await conn.disconnect()
                assert not conn.is_connected
                assert conn.state == ConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_call_tool_not_connected(self):
        """Raise error if not connected."""
        conn = MCPConnection("http://localhost:3000/sse")

        with pytest.raises(MCPConnectionError, match="Not connected"):
            await conn.call_tool("test", {})

    @pytest.mark.asyncio
    async def test_list_tools_not_connected(self):
        """Raise error if not connected."""
        conn = MCPConnection("http://localhost:3000/sse")

        with pytest.raises(MCPConnectionError, match="Not connected"):
            await conn.list_tools()


class TestConnectionManager:
    """Test ConnectionManager class."""

    def test_init_with_settings(self):
        """Initialize with settings."""
        settings = AppSettings(
            mcp_server_url="http://server:3000",
            mcp_timeout=60,
        )
        mgr = ConnectionManager(settings=settings)
        assert mgr._settings == settings

    def test_get_connection_creates_new(self):
        """Create new connection if not exists."""
        settings = AppSettings(mcp_server_url="http://server:3000")
        mgr = ConnectionManager(settings=settings)

        conn = mgr.get_connection()
        assert conn.server_url == "http://server:3000"
        # auth_token could be empty string or None depending on env
        assert not conn.auth_token

    def test_get_connection_reuses_existing(self):
        """Reuse existing connection."""
        settings = AppSettings(mcp_server_url="http://server:3000")
        mgr = ConnectionManager(settings=settings)

        conn1 = mgr.get_connection()
        conn2 = mgr.get_connection()
        assert conn1 is conn2

    def test_get_connection_with_explicit_params(self):
        """Use explicit URL and token."""
        mgr = ConnectionManager()
        conn = mgr.get_connection("http://other:3000", "token123")

        assert conn.server_url == "http://other:3000"

    @pytest.mark.asyncio
    async def test_connect_all(self):
        """Connect all managed connections."""
        mgr = ConnectionManager()

        with patch.object(MCPConnection, "connect", new_callable=AsyncMock):
            mgr.get_connection("http://server1:3000")
            mgr.get_connection("http://server2:3000")

            await mgr.connect_all()

    @pytest.mark.asyncio
    async def test_disconnect_all(self):
        """Disconnect all connections."""
        mgr = ConnectionManager()

        with patch.object(MCPConnection, "disconnect", new_callable=AsyncMock):
            mgr.get_connection("http://server1:3000")
            mgr.get_connection("http://server2:3000")

            await mgr.disconnect_all()
            assert len(mgr._connections) == 0

    @pytest.mark.asyncio
    async def test_connection_context_manager(self):
        """Context manager for temporary connections."""
        mgr = ConnectionManager()

        with patch.object(MCPConnection, "connect", new_callable=AsyncMock):
            async with mgr.connection("http://temp:3000") as conn:
                assert conn.server_url == "http://temp:3000"


class TestRetryLogic:
    """Test retry configuration."""

    def test_retry_settings_from_config(self):
        """Retry settings loaded from settings."""
        settings = AppSettings(
            mcp_max_retries=5,
            mcp_retry_backoff=2.0,
        )

        client = MagicMock()
        client._settings = settings

        assert settings.mcp_max_retries == 5
        assert settings.mcp_retry_backoff == 2.0


class TestToolCache:
    """Test ToolCache functionality."""

    def test_cache_set_and_get(self):
        """Set and retrieve from cache."""
        from ai_qa.mcp.tools import ToolCache

        cache = ToolCache()
        tool = Tool(name="test_tool", description="Test")

        cache.set(tool)
        retrieved = cache.get("test_tool")

        assert retrieved is not None
        assert retrieved.name == "test_tool"

    def test_cache_miss(self):
        """Return None for cache miss."""
        from ai_qa.mcp.tools import ToolCache

        cache = ToolCache()
        result = cache.get("nonexistent")
        assert result is None

    def test_cache_ttl_expiration(self):
        """Expired entries return None."""
        from ai_qa.mcp.tools import ToolCache

        cache = ToolCache(ttl_seconds=0.001)  # Very short TTL
        tool = Tool(name="expiring", description="Test")

        cache.set(tool)
        import time

        time.sleep(0.002)  # Wait for expiration

        result = cache.get("expiring")
        assert result is None

    def test_cache_clear(self):
        """Clear all cached entries."""
        from ai_qa.mcp.tools import ToolCache

        cache = ToolCache()
        cache.set(Tool(name="tool1", description="T1"))
        cache.set(Tool(name="tool2", description="T2"))

        cache.clear()
        assert cache.get("tool1") is None
        assert cache.get("tool2") is None
        assert len(cache.list_cached()) == 0

    def test_cache_set_many(self):
        """Cache multiple tools at once."""
        from ai_qa.mcp.tools import ToolCache

        cache = ToolCache()
        tools = [
            Tool(name="tool1", description="T1"),
            Tool(name="tool2", description="T2"),
        ]

        cache.set_many(tools)
        assert len(cache.list_cached()) == 2


@pytest.mark.asyncio
async def test_connect_sse_timeout():
    conn = MCPConnection("http://localhost:3000/sse", timeout=0.001)
    with pytest.raises(MCPTimeoutError):
        await conn.connect()


@pytest.mark.asyncio
async def test_call_tool_timeout():
    conn = MCPConnection("http://localhost:3000/sse", timeout=0.001)
    conn._state = ConnectionState.CONNECTED
    conn._session = AsyncMock()
    conn._session.call_tool.side_effect = TimeoutError()
    with pytest.raises(MCPTimeoutError):
        await conn.call_tool("test", {})


@pytest.mark.asyncio
async def test_list_tools_timeout():
    conn = MCPConnection("http://localhost:3000/sse", timeout=0.001)
    conn._state = ConnectionState.CONNECTED
    conn._session = AsyncMock()
    conn._session.list_tools.side_effect = TimeoutError()
    with pytest.raises(MCPTimeoutError):
        await conn.list_tools()


@pytest.mark.asyncio
async def test_connect_stdio_success():
    conn = MCPConnection("stdio:python test.py")
    with patch("ai_qa.mcp.connection.stdio_client") as mock_stdio:
        mock_ctx = AsyncMock()
        mock_transport = (AsyncMock(), AsyncMock())
        mock_ctx.__aenter__.return_value = mock_transport
        mock_stdio.return_value = mock_ctx
        with patch("ai_qa.mcp.connection.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session
            await conn.connect()
            assert conn.is_connected
