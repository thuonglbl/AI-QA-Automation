"""MCP (Model Context Protocol) client module for AI QA Automation.

This module provides a client for connecting to MCP servers to access
tools like Confluence readers, Jira integrations, and other enterprise
resources while keeping all data on-premises.

Example:
    >>> from ai_qa.mcp import MCPClient
    >>> client = MCPClient("http://localhost:3000/sse")
    >>> await client.connect()
    >>> tools = await client.list_tools()
    >>> result = await client.call_tool("confluence_reader", {"page_id": "12345"})
    >>> await client.disconnect()
"""

from ai_qa.mcp.client import MCPClient
from ai_qa.mcp.connection import ConnectionManager
from ai_qa.mcp.errors import (
    MCPAuthenticationError,
    MCPConnectionError,
    MCPTimeoutError,
    MCPToolError,
)
from ai_qa.mcp.tools import Tool, ToolCache, ToolResult

__all__ = [
    "MCPClient",
    "ConnectionManager",
    "Tool",
    "ToolResult",
    "ToolCache",
    "MCPConnectionError",
    "MCPAuthenticationError",
    "MCPToolError",
    "MCPTimeoutError",
]
