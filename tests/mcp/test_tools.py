"""Tests for MCP tools module."""

from ai_qa.mcp.tools import Tool, ToolCache, ToolParameter, ToolResult


class TestTool:
    """Test Tool class."""

    def test_tool_basic(self):
        """Create basic tool."""
        tool = Tool(name="test_tool", description="A test tool")

        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.parameters == []

    def test_tool_with_parameters(self):
        """Create tool with parameters."""
        params = [
            ToolParameter(name="url", type="string", description="Page URL", required=True),
            ToolParameter(name="limit", type="integer", description="Max results", required=False),
        ]
        tool = Tool(name="fetch", description="Fetch page", parameters=params)

        assert len(tool.parameters) == 2
        assert tool.parameters[0].name == "url"

    def test_get_required_params(self):
        """Filter required parameters."""
        params = [
            ToolParameter(name="required1", type="string", required=True),
            ToolParameter(name="optional1", type="string", required=False),
            ToolParameter(name="required2", type="string", required=True),
        ]
        tool = Tool(name="test", parameters=params)

        required = tool.get_required_params()
        assert len(required) == 2
        assert all(p.required for p in required)

    def test_validate_params_valid(self):
        """Validate valid parameters."""
        params = [
            ToolParameter(name="url", type="string", required=True),
            ToolParameter(name="limit", type="integer", required=False),
        ]
        tool = Tool(name="fetch", parameters=params)

        errors = tool.validate_params({"url": "http://example.com"})
        assert errors == []

    def test_validate_params_missing_required(self):
        """Detect missing required parameters."""
        params = [
            ToolParameter(name="url", type="string", required=True),
            ToolParameter(name="key", type="string", required=True),
        ]
        tool = Tool(name="fetch", parameters=params)

        errors = tool.validate_params({"url": "http://example.com"})
        assert len(errors) == 1
        assert "key" in errors[0]

    def test_validate_params_unknown(self):
        """Detect unknown parameters."""
        params = [ToolParameter(name="url", type="string", required=True)]
        tool = Tool(name="fetch", parameters=params)

        errors = tool.validate_params({"url": "http://example.com", "unknown": "value"})
        assert len(errors) == 1
        assert "unknown" in errors[0]


class TestToolResult:
    """Test ToolResult class."""

    def test_success_result(self):
        """Create successful result."""
        result = ToolResult.from_data({"content": "test"})

        assert result.success is True
        assert result.data == {"content": "test"}
        assert result.error is None

    def test_error_result(self):
        """Create error result."""
        result = ToolResult.from_error("Something failed")

        assert result.success is False
        assert result.error == "Something failed"
        assert result.data is None

    def test_result_with_metadata(self):
        """Result with metadata."""
        result = ToolResult.from_data(
            {"content": "test"},
            metadata={"source": "confluence", "page_id": "123"},
        )

        assert result.metadata["source"] == "confluence"


class TestToolCache:
    """Test ToolCache class."""

    def test_cache_hit(self):
        """Retrieve cached tool."""
        cache = ToolCache()
        tool = Tool(name="cached", description="Cached tool")

        cache.set(tool)
        retrieved = cache.get("cached")

        assert retrieved is not None
        assert retrieved.name == "cached"

    def test_cache_miss(self):
        """Handle cache miss."""
        cache = ToolCache()
        result = cache.get("nonexistent")
        assert result is None

    def test_cache_set_many(self):
        """Cache multiple tools."""
        cache = ToolCache()
        tools = [
            Tool(name="tool1", description="T1"),
            Tool(name="tool2", description="T2"),
            Tool(name="tool3", description="T3"),
        ]

        cache.set_many(tools)
        assert len(cache.list_cached()) == 3

    def test_cache_invalidate_expired(self):
        """Remove expired entries."""
        import time

        cache = ToolCache(ttl_seconds=0.01)
        cache.set(Tool(name="fresh", description="Fresh"))

        time.sleep(0.02)  # Wait for expiration

        removed = cache.invalidate_expired()
        assert removed == 1
        assert len(cache.list_cached()) == 0

    def test_cache_clear(self):
        """Clear all entries."""
        cache = ToolCache()
        cache.set(Tool(name="t1", description="T1"))
        cache.set(Tool(name="t2", description="T2"))

        cache.clear()
        assert cache.list_cached() == []


class TestToolParameter:
    """Test ToolParameter class."""

    def test_parameter_defaults(self):
        """Parameter with defaults."""
        param = ToolParameter(name="test", type="string")

        assert param.name == "test"
        assert param.type == "string"
        assert param.description == ""
        assert param.required is True
        assert param.default is None

    def test_parameter_with_description(self):
        """Parameter with description."""
        param = ToolParameter(
            name="url",
            type="string",
            description="The URL to fetch",
            required=True,
        )

        assert param.description == "The URL to fetch"
