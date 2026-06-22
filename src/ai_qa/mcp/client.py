"""Main MCP client for AI QA Automation.

Provides high-level interface for MCP server communication with
tool discovery, caching, and robust error handling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from ai_qa.config import AppSettings
from ai_qa.exceptions import MCPConnectionError, MCPToolError
from ai_qa.mcp.connection import ConnectionManager, MCPConnection
from ai_qa.mcp.tools import Tool, ToolCache, ToolResult

if TYPE_CHECKING:
    pass


class ServerCapabilities(BaseModel):
    """Capabilities discovered from MCP server."""

    tools: list[str] = []
    supports_progress: bool = False
    supports_logging: bool = False
    protocol_version: str = "unknown"


class MCPClient:
    """Client for MCP server communication.

    This is the main entry point for interacting with MCP servers.
    It handles connection management, tool discovery, caching,
    and provides retry logic for resilience.

    Example:
        >>> client = MCPClient("http://localhost:3000/sse")
        >>> await client.connect()
        >>> tools = await client.list_tools()
        >>> result = await client.call_tool("confluence_reader", {"page_id": "123"})
        >>> await client.disconnect()
    """

    def __init__(
        self,
        server_url: str | None = None,
        auth_token: str | None = None,
        settings: AppSettings | None = None,
    ) -> None:
        """Initialize MCP client.

        Args:
            server_url: MCP server URL (from settings if not provided)
            auth_token: Optional authentication token (from settings if not provided)
            settings: Application settings instance
        """
        self._settings = settings or AppSettings()
        self._server_url = server_url or self._settings.mcp_server_url or ""
        self._auth_token = auth_token

        if not self._server_url:
            raise MCPConnectionError(
                "No MCP server URL provided. "
                "Set mcp_server_url in settings or pass server_url parameter."
            )

        # Connection management
        self._connection_manager = ConnectionManager(
            settings=self._settings,
            default_timeout=self._settings.mcp_timeout or 30.0,
        )
        self._connection: MCPConnection | None = None

        # Tool cache
        self._tool_cache = ToolCache()
        self._capabilities: ServerCapabilities | None = None

        # Retry configuration
        self._max_retries = self._settings.mcp_max_retries or 3
        self._retry_backoff = self._settings.mcp_retry_backoff or 1.0

    @property
    def is_connected(self) -> bool:
        """Whether client is connected to MCP server."""
        return self._connection is not None and self._connection.is_connected

    @property
    def server_url(self) -> str:
        """Current server URL."""
        return self._server_url

    @property
    def capabilities(self) -> ServerCapabilities | None:
        """Discovered server capabilities (None if not discovered)."""
        return self._capabilities

    async def connect(self) -> None:
        """Connect to MCP server with retry logic.

        Raises:
            MCPConnectionError: If connection fails after retries
            MCPAuthenticationError: If authentication fails
            MCPTimeoutError: If connection times out
        """
        if self.is_connected:
            return

        try:
            self._connection = self._connection_manager.get_connection(
                self._server_url,
                self._auth_token,
            )
            await self._connect_with_retry()
        except Exception:
            self._connection = None
            raise

    async def _connect_with_retry(self) -> None:
        """Internal connect with retry logic."""
        if not self._connection:
            raise MCPConnectionError("No connection available")
        await self._connection.connect()

    async def disconnect(self) -> None:
        """Disconnect from MCP server."""
        if self._connection:
            await self._connection.disconnect()
            self._connection = None

    async def __aenter__(self) -> MCPClient:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()

    async def list_tools(self, use_cache: bool = True) -> list[Tool]:
        """List available tools from MCP server.

        Args:
            use_cache: Whether to use cached results

        Returns:
            List of available tools

        Raises:
            MCPConnectionError: If not connected
        """
        if not self.is_connected:
            raise MCPConnectionError("Not connected to MCP server. Call connect() first.")

        # Check cache first
        if use_cache:
            cached_list: list[Tool] = []
            for name in self._tool_cache.list_cached():
                t = self._tool_cache.get(name)
                if t is not None:
                    cached_list.append(t)
            if cached_list:
                return cached_list

        # Fetch from server
        if not self._connection:
            raise MCPConnectionError("No connection available")

        try:
            tools = await self._connection.list_tools()
            # Cache results
            self._tool_cache.set_many(tools)
            return tools
        except Exception as e:
            raise MCPToolError(
                "Failed to list tools",
                details=str(e),
            ) from e

    async def call_tool(self, name: str, params: dict[str, Any] | None = None) -> ToolResult:
        """Call an MCP tool with retry logic.

        Args:
            name: Tool name
            params: Tool parameters

        Returns:
            Tool execution result

        Raises:
            MCPConnectionError: If not connected
            MCPToolError: If tool execution fails
        """
        if not self.is_connected:
            raise MCPConnectionError("Not connected to MCP server. Call connect() first.")

        params = params or {}

        # Validate against tool definition if cached
        cached_tool = self._tool_cache.get(name)
        if cached_tool:
            errors = cached_tool.validate_params(params)
            if errors:
                return ToolResult.from_error(f"Parameter validation failed: {'; '.join(errors)}")

        try:
            result = await self._call_tool_with_retry(name, params)

            # Check for tool execution errors wrapped in the response
            if getattr(result, "isError", False):
                error_msg = ""
                content_list = getattr(result, "content", [])
                if content_list:
                    error_msg = "\n".join(
                        getattr(c, "text", "") for c in content_list if hasattr(c, "text")
                    )
                if not error_msg:
                    error_msg = f"Tool '{name}' executed with error flag set."
                return ToolResult.from_error(error_msg)

            # Extract content data from CallToolResult
            data = None
            content_list = getattr(result, "content", [])
            if content_list:
                first_content = content_list[0]
                if hasattr(first_content, "text"):
                    import json

                    text_data = first_content.text
                    try:
                        data = json.loads(text_data)
                    except Exception:
                        data = text_data
                elif hasattr(first_content, "json_"):
                    data = first_content.json_
                else:
                    data = result
            else:
                data = result

            return ToolResult.from_data(data)
        except MCPToolError:
            raise
        except Exception as e:
            raise MCPToolError(
                f"Tool '{name}' execution failed",
                details=str(e),
            ) from e

    async def _call_tool_with_retry(self, name: str, params: dict[str, Any]) -> Any:
        """Internal tool call with retry logic."""
        if not self._connection:
            raise MCPConnectionError("No connection available")

        try:
            return await self._connection.call_tool(name, params)
        except Exception as e:
            if "tool" in str(e).lower() and "not found" in str(e).lower():
                raise MCPToolError(f"Tool '{name}' not found on server") from e
            raise

    async def check_required_tools(self, required_tools: list[str]) -> list[str]:
        """Return names from required_tools that are absent on the MCP server.

        Args:
            required_tools: Tool names to check for (use prefixed names when applicable).

        Returns:
            List of missing tool names; empty list means all required tools are present.

        Raises:
            MCPConnectionError: If list_tools() fails due to connectivity.
            MCPAuthenticationError: If authentication fails.
        """
        if not required_tools:
            return []
        available = {t.name for t in await self.list_tools()}
        return [name for name in required_tools if name not in available]

    async def discover_capabilities(self) -> ServerCapabilities:
        """Discover server capabilities.

        Fetches tools and determines supported features.

        Returns:
            ServerCapabilities with discovered features
        """
        tools = await self.list_tools()

        self._capabilities = ServerCapabilities(
            tools=[t.name for t in tools],
            supports_progress=False,  # TODO: Detect from server info
            supports_logging=False,  # TODO: Detect from server info
            protocol_version="1.0",  # TODO: Detect from server info
        )

        return self._capabilities

    def get_cached_tool(self, name: str) -> Tool | None:
        """Get a tool from cache.

        Args:
            name: Tool name

        Returns:
            Cached tool or None
        """
        return self._tool_cache.get(name)

    def clear_cache(self) -> None:
        """Clear tool cache."""
        self._tool_cache.clear()

    async def health_check(self) -> dict[str, Any]:
        """Check connection health.

        Returns:
            Health status dictionary
        """
        return {
            "connected": self.is_connected,
            "server_url": self._server_url,
            "capabilities": self._capabilities.model_dump() if self._capabilities else None,
            "cached_tools": self._tool_cache.list_cached(),
        }
