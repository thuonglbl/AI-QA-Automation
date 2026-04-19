"""MCP-specific error classes.

These errors extend the base MCPError from ai_qa.exceptions and provide
MCP-specific context for better error handling and debugging.
"""

from ai_qa.exceptions import (
    MCPAuthenticationError,
    MCPConnectionError,
    MCPTimeoutError,
    MCPToolError,
)

__all__ = ["MCPConnectionError", "MCPAuthenticationError", "MCPToolError", "MCPTimeoutError"]
