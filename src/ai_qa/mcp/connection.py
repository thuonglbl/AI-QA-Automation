"""Connection management for MCP servers.

Provides connection pooling, lifecycle management, and retry logic
for MCP server connections.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

from ai_qa.config import AppSettings
from ai_qa.exceptions import MCPAuthenticationError, MCPConnectionError, MCPTimeoutError
from ai_qa.mcp.tools import Tool, ToolCache

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class ConnectionState:
    """Tracks the state of an MCP connection."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class MCPConnection:
    """Manages a single connection to an MCP server.

    Handles transport (stdio or HTTP/SSE), session lifecycle,
    and provides basic error handling.
    """

    def __init__(
        self,
        server_url: str,
        auth_token: str | None = None,
        timeout: float = 30.0,
        use_streamable_http: bool = True,
    ) -> None:
        """Initialize connection configuration.

        Args:
            server_url: MCP server URL (http://, https://, or stdio command)
            auth_token: Optional authentication token
            timeout: Connection timeout in seconds
            use_streamable_http: Whether to use Streamable HTTP transport
        """
        self.server_url = server_url
        self.auth_token = auth_token
        self.timeout = timeout
        self.use_streamable_http = use_streamable_http
        self._state = ConnectionState.DISCONNECTED
        self._session: ClientSession | None = None
        self._session_context: ClientSession | None = None
        self._transport_context: Any = None
        self._transport: Any = None
        self._http_client: Any = None

    @property
    def state(self) -> str:
        """Current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Whether connection is established."""
        return self._state == ConnectionState.CONNECTED and self._session is not None

    def _is_sse_url(self) -> bool:
        """Check if URL uses SSE transport."""
        return self.server_url.startswith(("http://", "https://"))

    async def connect(self) -> None:
        """Establish connection to MCP server.

        Raises:
            MCPConnectionError: If connection fails
            MCPAuthenticationError: If authentication fails
            MCPTimeoutError: If connection times out
        """
        if self._state == ConnectionState.CONNECTED:
            return

        self._state = ConnectionState.CONNECTING

        try:
            if self._is_sse_url():
                await self._connect_sse()
            else:
                await self._connect_stdio()

            self._state = ConnectionState.CONNECTED

        except TimeoutError as e:
            self._state = ConnectionState.ERROR
            raise MCPTimeoutError(
                f"Connection to MCP server timed out after {self.timeout}s",
                details=str(e),
            ) from e
        except Exception as e:
            self._state = ConnectionState.ERROR
            error_msg = str(e)

            # Handle Python 3.11+ ExceptionGroup which wraps the actual httpx errors
            if isinstance(e, BaseExceptionGroup):
                sub_msgs = []
                for exc in e.exceptions:
                    msg = str(exc)
                    if hasattr(exc, "response") and exc.response is not None:
                        try:
                            await exc.response.aread()
                            msg += f" - Response body: {exc.response.text}"
                        except Exception:
                            pass
                    sub_msgs.append(msg)
                error_msg = " | ".join(sub_msgs)

            if (
                "auth" in error_msg.lower()
                or "unauthorized" in error_msg.lower()
                or "401" in error_msg
            ):
                raise MCPAuthenticationError(
                    "Failed to authenticate with MCP server",
                    details=error_msg,
                ) from e
            raise MCPConnectionError(
                f"Failed to connect to MCP server at {self.server_url}",
                details=error_msg,
            ) from e

    async def _connect_sse(self) -> None:
        """Connect using SSE transport.

        If use_streamable_http is set, it will use the Streamable HTTP transport
        instead of the Legacy SSE transport.
        """

        if self.use_streamable_http:
            import httpx
            from mcp.client.streamable_http import streamable_http_client
            from mcp.shared._httpx_utils import create_mcp_http_client

            headers = {}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"

            # Create standard MCP client with appropriate timeouts
            timeout = httpx.Timeout(self.timeout, read=300.0)
            self._http_client = create_mcp_http_client(headers=headers, timeout=timeout)
            await self._http_client.__aenter__()

            self._transport_context = streamable_http_client(
                self.server_url, http_client=self._http_client
            )
            transport_tuple = await self._transport_context.__aenter__()
            if transport_tuple is None:
                raise MCPConnectionError("Failed to establish Streamable HTTP transport")
            read_stream, write_stream, _get_session_id = transport_tuple

            self._session_context = ClientSession(read_stream, write_stream)
            self._session = await self._session_context.__aenter__()
            await asyncio.wait_for(self._session.initialize(), timeout=self.timeout)
            return

        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        self._transport_context = sse_client(self.server_url, headers=headers)
        self._transport = await self._transport_context.__aenter__()
        if self._transport is None:
            raise MCPConnectionError("Failed to establish SSE transport")
        read_stream, write_stream = self._transport

        self._session_context = ClientSession(read_stream, write_stream)
        self._session = await self._session_context.__aenter__()
        await asyncio.wait_for(self._session.initialize(), timeout=self.timeout)

    async def _connect_stdio(self) -> None:
        """Connect using stdio transport."""
        # Parse command from URL-like string: "stdio:command arg1 arg2"
        command = self.server_url
        if command.startswith("stdio:"):
            command = command[6:]

        parts = command.split()
        if not parts:
            raise MCPConnectionError("Empty stdio command")

        from mcp import StdioServerParameters

        server_params = StdioServerParameters(command=parts[0], args=parts[1:])
        self._transport_context = stdio_client(server_params)
        self._transport = await self._transport_context.__aenter__()
        if self._transport is None:
            raise MCPConnectionError("Failed to establish stdio transport")
        read_stream, write_stream = self._transport

        self._session_context = ClientSession(read_stream, write_stream)
        self._session = await self._session_context.__aenter__()
        await asyncio.wait_for(self._session.initialize(), timeout=self.timeout)

    async def disconnect(self) -> None:
        """Close connection to MCP server."""
        if self._session_context:
            try:
                await self._session_context.__aexit__(None, None, None)
            except Exception:
                pass
            self._session_context = None
        self._session = None

        if self._transport_context:
            try:
                await self._transport_context.__aexit__(None, None, None)
            except Exception:
                pass
            self._transport_context = None
            self._transport = None

        if self._http_client:
            try:
                await self._http_client.__aexit__(None, None, None)
            except Exception:
                pass
            self._http_client = None

        self._state = ConnectionState.DISCONNECTED

    async def call_tool(self, name: str, params: dict[str, Any]) -> Any:
        """Call a tool on the MCP server.

        Args:
            name: Tool name
            params: Tool parameters

        Returns:
            Tool result as dictionary

        Raises:
            MCPConnectionError: If not connected or call fails
        """
        if not self.is_connected or not self._session:
            raise MCPConnectionError("Not connected to MCP server")

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(name, params),
                timeout=self.timeout,
            )
            return result
        except TimeoutError as e:
            raise MCPTimeoutError(
                f"Tool call '{name}' timed out after {self.timeout}s",
                details=str(e),
            ) from e
        except Exception as e:
            raise MCPConnectionError(
                f"Tool call '{name}' failed",
                details=str(e),
            ) from e

    async def list_tools(self) -> list[Tool]:
        """List available tools from MCP server.

        Returns:
            List of discovered tools
        """
        if not self.is_connected or not self._session:
            raise MCPConnectionError("Not connected to MCP server")

        try:
            response = await asyncio.wait_for(
                self._session.list_tools(),
                timeout=self.timeout,
            )

            tools: list[Tool] = []
            for tool_data in response.tools:
                # Convert MCP tool to our Tool model
                params = []
                if hasattr(tool_data, "parameters") and tool_data.parameters:
                    for name, param in tool_data.parameters.items():
                        params.append(
                            Tool.Parameter(  # type: ignore[attr-defined]
                                name=name,
                                type=param.get("type", "string"),
                                description=param.get("description", ""),
                                required=param.get("required", True),
                            )
                        )

                tools.append(
                    Tool(
                        name=tool_data.name,
                        description=getattr(tool_data, "description", ""),
                        parameters=params,
                    )
                )

            return tools
        except TimeoutError as e:
            raise MCPTimeoutError(
                f"List tools timed out after {self.timeout}s",
                details=str(e),
            ) from e
        except Exception as e:
            raise MCPConnectionError(
                "Failed to list tools",
                details=str(e),
            ) from e


class ConnectionManager:
    """Manages multiple MCP connections with pooling.

    Provides connection reuse, health checking, and automatic cleanup.
    """

    def __init__(
        self,
        settings: AppSettings | None = None,
        default_timeout: float = 30.0,
    ) -> None:
        """Initialize connection manager.

        Args:
            settings: Application settings for default connection
            default_timeout: Default timeout for connections
        """
        self._settings = settings
        self._default_timeout = default_timeout
        self._connections: dict[str, MCPConnection] = {}
        self._tool_cache = ToolCache()

    def get_connection(
        self,
        server_url: str | None = None,
        auth_token: str | None = None,
    ) -> MCPConnection:
        """Get or create a connection.

        Args:
            server_url: Server URL (uses settings if not provided)
            auth_token: Auth token (uses settings if not provided)

        Returns:
            MCPConnection instance
        """
        url = server_url or (self._settings.mcp_server_url if self._settings else None) or ""
        token = auth_token or (self._settings.mcp_server_key if self._settings else None)
        timeout = (
            self._settings.mcp_timeout
            if self._settings and self._settings.mcp_timeout
            else self._default_timeout
        )

        # Create connection key
        key = f"{url}:{token or 'noauth'}"

        if key not in self._connections:
            use_streamable_http = self._settings.mcp_use_streamable_http if self._settings else True
            self._connections[key] = MCPConnection(
                server_url=url,
                auth_token=token,
                timeout=timeout,
                use_streamable_http=use_streamable_http,
            )

        return self._connections[key]

    async def connect_all(self) -> None:
        """Connect all managed connections with retry logic."""
        for conn in self._connections.values():
            await self._connect_with_retry(conn)

    async def _connect_with_retry(self, conn: MCPConnection) -> None:
        """Connect with exponential backoff retry."""
        await conn.connect()

    async def disconnect_all(self) -> None:
        """Disconnect all managed connections."""
        for conn in self._connections.values():
            await conn.disconnect()
        self._connections.clear()

    @asynccontextmanager
    async def connection(
        self,
        server_url: str | None = None,
        auth_token: str | None = None,
    ) -> AsyncGenerator[MCPConnection, None]:
        """Context manager for temporary connections.

        Example:
            >>> async with manager.connection() as conn:
            ...     tools = await conn.list_tools()
        """
        conn = self.get_connection(server_url, auth_token)
        try:
            if not conn.is_connected:
                await self._connect_with_retry(conn)
            yield conn
        finally:
            # Don't disconnect pooled connections on exit
            pass

    def clear_cache(self) -> None:
        """Clear tool cache."""
        self._tool_cache.clear()
