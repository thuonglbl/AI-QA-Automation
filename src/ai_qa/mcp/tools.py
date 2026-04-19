"""Tool discovery, caching, and execution for MCP servers.

This module provides:
- Tool: Pydantic model representing an MCP tool
- ToolResult: Pydantic model for tool execution results
- ToolCache: Caching layer for discovered tools
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    """Parameter definition for an MCP tool."""

    name: str
    type: str
    description: str = ""
    required: bool = True
    default: Any | None = None


class Tool(BaseModel):
    """Represents an MCP tool discovered from the server.

    Attributes:
        name: Unique identifier for the tool
        description: Human-readable description
        parameters: List of parameter definitions
        returns: Expected return type description
    """

    name: str = Field(..., description="Tool unique identifier")
    description: str = Field(default="", description="Tool description")
    parameters: list[ToolParameter] = Field(default_factory=list)
    returns: str = Field(default="any", description="Return type description")

    def get_required_params(self) -> list[ToolParameter]:
        """Return only required parameters."""
        return [p for p in self.parameters if p.required]

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """Validate parameters against tool definition.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        required_names = {p.name for p in self.parameters if p.required}
        provided_names = set(params.keys())

        # Check missing required params
        missing = required_names - provided_names
        for name in missing:
            errors.append(f"Missing required parameter: {name}")

        # Check unknown params
        valid_names = {p.name for p in self.parameters}
        unknown = provided_names - valid_names
        for name in unknown:
            errors.append(f"Unknown parameter: {name}")

        return errors


class ToolResult(BaseModel):
    """Result from executing an MCP tool.

    Attributes:
        success: Whether the tool executed successfully
        data: Result data (if success=True)
        error: Error message (if success=False)
        metadata: Additional metadata from the tool execution
    """

    success: bool
    data: Any | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_error(cls, error: str, metadata: dict[str, Any] | None = None) -> ToolResult:
        """Create a failed result."""
        return cls(success=False, error=error, metadata=metadata or {})

    @classmethod
    def from_data(cls, data: Any, metadata: dict[str, Any] | None = None) -> ToolResult:
        """Create a successful result."""
        return cls(success=True, data=data, metadata=metadata or {})


@dataclass
class CachedTool:
    """Internal cache entry for a tool."""

    tool: Tool
    cached_at: float = field(default_factory=time.time)


class ToolCache:
    """Cache for discovered MCP tools.

    Provides TTL-based caching to avoid repeated tool discovery calls.
    """

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        """Initialize cache.

        Args:
            ttl_seconds: Time-to-live for cached entries (default 5 minutes)
        """
        self._ttl = ttl_seconds
        self._cache: dict[str, CachedTool] = {}

    def get(self, name: str) -> Tool | None:
        """Get tool from cache if not expired.

        Args:
            name: Tool name to look up

        Returns:
            Tool if cached and not expired, None otherwise
        """
        if name not in self._cache:
            return None

        cached = self._cache[name]
        if time.time() - cached.cached_at > self._ttl:
            del self._cache[name]
            return None

        return cached.tool

    def set(self, tool: Tool) -> None:
        """Cache a tool.

        Args:
            tool: Tool to cache
        """
        self._cache[tool.name] = CachedTool(tool=tool)

    def set_many(self, tools: list[Tool]) -> None:
        """Cache multiple tools."""
        for tool in tools:
            self.set(tool)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def list_cached(self) -> list[str]:
        """List names of all cached tools."""
        return list(self._cache.keys())

    def invalidate_expired(self) -> int:
        """Remove expired entries, return count of removed items."""
        now = time.time()
        expired = [
            name for name, cached in self._cache.items() if now - cached.cached_at > self._ttl
        ]
        for name in expired:
            del self._cache[name]
        return len(expired)
