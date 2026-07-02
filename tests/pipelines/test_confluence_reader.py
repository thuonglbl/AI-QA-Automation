"""Tests for ConfluenceReader pipeline stage.

Tests the ConfluenceReader class with mocked MCP client.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_qa.exceptions import MCPConnectionError, MCPToolError
from ai_qa.mcp.tools import ToolResult
from ai_qa.pipelines.confluence_reader import (
    ConfluenceReader,
    _extract_parent_and_ancestors,
    _resolve_page_url,
)


def test_resolve_page_url_no_double_append_when_base_is_full_page_url() -> None:
    """Bug fix: a base URL that is itself a full page URL must NOT get /pages/{id}
    appended again — derive the site root instead."""
    base = "https://confluence.svc.corp.ch/spaces/EXPERTGROUP/pages/1238866187/PTP+-+Personal+Travel+Plan"
    assert (
        _resolve_page_url(base, {}, "1238866187")
        == "https://confluence.svc.corp.ch/pages/1238866187"
    )


def test_resolve_page_url_prefers_server_links() -> None:
    base = "https://confluence.svc.corp.ch/spaces/X/pages/1/Whatever"
    # _links.webui (relative) joins onto the site root.
    assert _resolve_page_url(base, {"_links": {"webui": "/spaces/X/pages/9/Title"}}, "9") == (
        "https://confluence.svc.corp.ch/spaces/X/pages/9/Title"
    )
    # A top-level url is used verbatim.
    assert (
        _resolve_page_url(base, {"url": "https://c.example/pages/9"}, "9")
        == "https://c.example/pages/9"
    )


def test_resolve_page_url_site_root_base() -> None:
    assert (
        _resolve_page_url("https://confluence.svc.corp.ch", {}, "42")
        == "https://confluence.svc.corp.ch/pages/42"
    )


def test_extract_parent_and_ancestors_prefers_ancestors_chain() -> None:
    """The immediate parent is the LAST entry of the ancestors chain, and the chain itself is returned."""
    page = {"id": "5", "ancestors": [{"id": "1"}, {"id": "3"}]}
    assert _extract_parent_and_ancestors(page, "root") == ("3", ["1", "3"])


def test_extract_parent_and_ancestors_falls_back_to_parentid_then_parent_obj() -> None:
    assert _extract_parent_and_ancestors({"id": "5", "parentId": "9"}, "root") == ("9", ["9"])
    assert _extract_parent_and_ancestors({"id": "5", "parent": {"id": "7"}}, "root") == ("7", ["7"])


def test_extract_parent_and_ancestors_falls_back_to_root_when_unavailable() -> None:
    assert _extract_parent_and_ancestors({"id": "5"}, "root") == ("root", ["root"])
    assert _extract_parent_and_ancestors({"id": "5", "ancestors": []}, "root") == ("root", ["root"])
    # The root itself has no fallback.
    assert _extract_parent_and_ancestors({"id": "root"}, None) == (None, [])


@pytest.fixture
def mock_mcp_client() -> MagicMock:
    """Create a mock MCP client."""
    client = MagicMock()
    client.is_connected = True
    client.server_url = "http://localhost:3000/sse"
    client.call_tool = AsyncMock()
    return client


@pytest.fixture
def confluence_reader(mock_mcp_client: MagicMock) -> ConfluenceReader:
    """Create a ConfluenceReader with mocked MCP client."""
    return ConfluenceReader(
        mcp_client=mock_mcp_client,
        confluence_base_url="https://confluence.company.com",
    )


class TestConfluenceReaderReadPage:
    """Test suite for ConfluenceReader.read_page method."""

    async def test_read_page_success(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test successful page read."""
        # Setup mock response
        mock_mcp_client.call_tool.return_value = ToolResult.from_data(
            {
                "id": "123456",
                "title": "Test Page",
                "content": "<p>Page content</p>",
                "space": {"key": "TEST"},
                "author": {"displayName": "John Doe"},
                "version": {"number": 1},
                "labels": ["test", "documentation"],
            }
        )

        url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123456/Test+Page"
        result = await confluence_reader.read_page(url)

        assert result.success is True
        assert result.data is not None
        assert result.data.page_id == "123456"
        assert result.data.title == "Test Page"
        assert result.data.content == "<p>Page content</p>"
        assert result.data.space_key == "TEST"
        assert result.data.author == "John Doe"
        assert result.data.version == 1
        assert result.data.labels == ["test", "documentation"]
        assert result.confidence == 1.0
        assert len(result.errors) == 0

    async def test_read_page_invalid_url(self, confluence_reader: ConfluenceReader) -> None:
        """Test reading with invalid URL."""
        result = await confluence_reader.read_page("https://example.com/not-confluence")

        assert result.success is False
        assert result.data is None
        assert result.confidence == 0.0
        assert any("Invalid Confluence URL" in e for e in result.errors)

    async def test_read_page_no_page_id(self, confluence_reader: ConfluenceReader) -> None:
        """Test reading URL without extractable page ID."""
        result = await confluence_reader.read_page(
            "https://confluence.company.com/display/TEST/Page"
        )

        assert result.success is False
        assert result.data is None
        assert result.confidence == 0.0
        assert any("Could not extract page ID" in e for e in result.errors)

    async def test_read_page_not_connected(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test reading when MCP client is not connected."""
        mock_mcp_client.is_connected = False

        url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123456/Test+Page"
        result = await confluence_reader.read_page(url)

        assert result.success is False
        assert result.data is None
        assert result.confidence == 0.0
        assert any("MCP server not connected" in e for e in result.errors)

    async def test_read_page_mcp_connection_error(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test handling MCP connection error."""
        mock_mcp_client.call_tool.side_effect = MCPConnectionError("Connection refused")

        url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123456/Test+Page"
        result = await confluence_reader.read_page(url)

        assert result.success is False
        assert result.data is None
        assert result.confidence == 0.0
        assert any("MCP server unavailable" in e for e in result.errors)
        assert any("Connection refused" in e for e in result.errors)

    async def test_read_page_mcp_tool_error_not_found(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test handling MCP tool error with 'not found' message."""
        mock_mcp_client.call_tool.side_effect = MCPToolError("Tool returned: Page not found")

        url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123456/Test+Page"
        result = await confluence_reader.read_page(url)

        assert result.success is False
        assert result.data is None
        assert result.confidence == 0.0
        assert any("Page not found" in e for e in result.errors)

    async def test_read_page_mcp_tool_error_general(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test handling general MCP tool error."""
        mock_mcp_client.call_tool.side_effect = MCPToolError(
            "Tool execution failed", details="Timeout"
        )

        url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123456/Test+Page"
        result = await confluence_reader.read_page(url)

        assert result.success is False
        assert result.data is None
        assert result.confidence == 0.0
        assert any("MCP tool error" in e for e in result.errors)

    async def test_read_page_empty_content(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test reading page with empty content."""
        mock_mcp_client.call_tool.return_value = ToolResult.from_data(
            {
                "id": "123456",
                "title": "Empty Page",
                "content": "",
                "space": {"key": "TEST"},
            }
        )

        url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123456/Empty+Page"
        result = await confluence_reader.read_page(url)

        assert result.success is True
        assert result.data is not None
        assert result.data.content == ""
        assert any("Page has no content" in w for w in result.warnings)

    async def test_read_page_tool_error_response(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test handling tool result with error flag."""
        mock_mcp_client.call_tool.return_value = ToolResult.from_error("Page not accessible")

        url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123456/Test+Page"
        result = await confluence_reader.read_page(url)

        assert result.success is False
        assert result.data is None
        assert any("Failed to retrieve page" in e for e in result.errors)

    async def test_read_page_string_response(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test handling string response from MCP."""
        import json

        page_data = {
            "id": "123456",
            "title": "Test Page",
            "content": "<p>Content</p>",
            "space_key": "TEST",
        }
        mock_mcp_client.call_tool.return_value = ToolResult.from_data(json.dumps(page_data))

        url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123456/Test+Page"
        result = await confluence_reader.read_page(url)

        assert result.success is True
        assert result.data is not None
        assert result.data.title == "Test Page"

    async def test_read_page_by_id_success(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test successful page read by ID."""
        mock_mcp_client.call_tool.return_value = ToolResult.from_data(
            {
                "id": "123456",
                "title": "Test Page",
                "content": "<p>Page content</p>",
                "space": {"key": "TEST"},
                "author": {"displayName": "John Doe"},
                "version": {"number": 1},
                "labels": ["test", "documentation"],
            }
        )

        result = await confluence_reader.read_page_by_id("123456")

        assert result.success is True
        assert result.data is not None
        assert result.data.page_id == "123456"
        assert result.data.title == "Test Page"
        assert result.data.content == "<p>Page content</p>"
        assert result.confidence == 1.0

    async def test_read_page_by_id_tool_error(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test read_page_by_id tool error."""
        mock_mcp_client.call_tool.side_effect = MCPToolError("Page not found")

        result = await confluence_reader.read_page_by_id("123456")

        assert result.success is False
        assert result.data is None
        assert any("Page not found" in e for e in result.errors)

    async def test_read_page_by_id_connection_error(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test read_page_by_id connection error."""
        mock_mcp_client.call_tool.side_effect = MCPConnectionError("Connection refused")

        result = await confluence_reader.read_page_by_id("123456")

        assert result.success is False
        assert result.data is None
        assert any("Connection refused" in e for e in result.errors)

    async def test_read_page_by_id_not_connected(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test read_page_by_id when MCP client is not connected."""
        mock_mcp_client.is_connected = False

        result = await confluence_reader.read_page_by_id("123456")

        assert result.success is False
        assert result.data is None
        assert result.confidence == 0.0
        assert any("MCP server not connected" in e for e in result.errors)


class TestConfluenceReaderReadMultiple:
    """Test suite for ConfluenceReader.read_multiple_pages method."""

    async def test_read_multiple_pages_success(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test reading multiple pages successfully."""
        mock_mcp_client.call_tool.side_effect = [
            ToolResult.from_data(
                {
                    "id": "111",
                    "title": "Page 1",
                    "content": "Content 1",
                    "space": {"key": "TEST"},
                }
            ),
            ToolResult.from_data(
                {
                    "id": "222",
                    "title": "Page 2",
                    "content": "Content 2",
                    "space": {"key": "TEST"},
                }
            ),
        ]

        urls = [
            "https://company.atlassian.net/wiki/spaces/TEST/pages/111/Page1",
            "https://company.atlassian.net/wiki/spaces/TEST/pages/222/Page2",
        ]
        result = await confluence_reader.read_multiple_pages(urls)

        assert result.success is True
        assert result.data is not None
        assert len(result.data) == 2
        assert result.confidence == 1.0

    async def test_read_multiple_pages_partial_failure(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test reading multiple pages with partial failure."""
        mock_mcp_client.call_tool.side_effect = [
            ToolResult.from_data(
                {
                    "id": "111",
                    "title": "Page 1",
                    "content": "Content 1",
                    "space": {"key": "TEST"},
                }
            ),
            ToolResult.from_error("Page not found"),
        ]

        urls = [
            "https://company.atlassian.net/wiki/spaces/TEST/pages/111/Page1",
            "https://company.atlassian.net/wiki/spaces/TEST/pages/222/Page2",
        ]
        result = await confluence_reader.read_multiple_pages(urls)

        assert result.success is True  # Partial success counts as success
        assert result.data is not None
        assert len(result.data) == 1
        assert result.confidence == 0.5
        # Errors are converted to warnings on partial success
        assert len(result.errors) == 0
        assert len(result.warnings) > 0

    async def test_read_multiple_pages_all_fail(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test reading multiple pages all failing."""
        mock_mcp_client.call_tool.return_value = ToolResult.from_error("Page not found")

        urls = [
            "https://company.atlassian.net/wiki/spaces/TEST/pages/111/Page1",
            "https://company.atlassian.net/wiki/spaces/TEST/pages/222/Page2",
        ]
        result = await confluence_reader.read_multiple_pages(urls)

        assert result.success is False
        assert result.data is None
        assert len(result.errors) > 0
        assert result.confidence == 0.0

    async def test_read_multiple_pages_empty_list(
        self, confluence_reader: ConfluenceReader
    ) -> None:
        """Test reading with empty URL list."""
        result = await confluence_reader.read_multiple_pages([])

        assert result.success is True
        assert result.data == []
        assert any("No URLs provided" in w for w in result.warnings)

    async def test_read_multiple_pages_not_connected(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test reading multiple when not connected."""
        mock_mcp_client.is_connected = False

        urls = ["https://company.atlassian.net/wiki/spaces/TEST/pages/111/Page1"]
        result = await confluence_reader.read_multiple_pages(urls)

        assert result.success is False
        assert result.data is None
        assert any("MCP server not connected" in e for e in result.errors)


class TestConfluenceReaderEdgeCases:
    """Test suite for edge cases and error handling."""

    async def test_read_page_unexpected_exception(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test handling unexpected exceptions."""
        mock_mcp_client.call_tool.side_effect = Exception("Unexpected error")

        url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123456/Test+Page"
        result = await confluence_reader.read_page(url)

        assert result.success is False
        assert any("Unexpected error" in e for e in result.errors)

    async def test_read_page_various_url_formats(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test reading with various valid Confluence URL formats."""
        mock_mcp_client.call_tool.return_value = ToolResult.from_data(
            {
                "id": "123456",
                "title": "Test",
                "content": "Content",
                "space": {"key": "TEST"},
            }
        )

        # Cloud format
        url1 = "https://company.atlassian.net/wiki/spaces/TEST/pages/123456/Test"
        result1 = await confluence_reader.read_page(url1)
        assert result1.success is True

        # Server with pageId
        url2 = "https://confluence.company.com/pages/viewpage.action?pageId=123456"
        result2 = await confluence_reader.read_page(url2)
        assert result2.success is True


class TestConfluenceReaderParameterConsistency:
    """Tests for parameter naming: confluence_get_page expects 'pageId' (__SKIP_WORD_0_camcorpse__).

    The internal MCP server rejects snake_case 'page_id' ("Unknown parameter: page_id"),
    so the reader must send the __SKIP_WORD_0_camcorpse__ 'pageId' the server schema requires.
    """

    async def test_read_page_uses_pageid_camel_case(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """read_page() must call confluence_get_page with 'pageId' (__SKIP_WORD_0_camcorpse__)."""
        mock_mcp_client.call_tool.return_value = ToolResult.from_data(
            {
                "id": "123456",
                "title": "Test Page",
                "content": "<p>Content</p>",
                "space": {"key": "TEST"},
            }
        )

        url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123456/Test+Page"
        await confluence_reader.read_page(url)

        mock_mcp_client.call_tool.assert_called_once()
        call_args = mock_mcp_client.call_tool.call_args
        params = call_args.args[1]
        assert params == {
            "pageId": "123456",
            "format": "view",
            "userPrompt": "User initiated a story creation workflow from a Confluence page link.",
            "llmReasoning": "Need to extract the content of the provided Confluence page to fulfill the user's request.",
        }

    async def test_read_page_by_id_uses_pageid_camel_case(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """read_page_by_id() must also use 'pageId' (__SKIP_WORD_0_camcorpse__)."""
        mock_mcp_client.call_tool.return_value = ToolResult.from_data(
            {
                "id": "789",
                "title": "Another Page",
                "content": "<p>Content</p>",
                "space": {"key": "TEST"},
            }
        )

        await confluence_reader.read_page_by_id("789")

        mock_mcp_client.call_tool.assert_called_once()
        call_args = mock_mcp_client.call_tool.call_args
        params = call_args.args[1]
        assert params == {
            "pageId": "789",
            "format": "view",
            "userPrompt": "User initiated a story creation workflow from a Confluence page link.",
            "llmReasoning": "Need to extract the content of the provided Confluence page to fulfill the user's request.",
        }


class TestConfluenceReaderChildrenAndSearch:
    """Tests for child pages and finding parent pages."""

    async def test_get_children_by_id_success(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test getting child pages successfully."""

        def mock_call_tool(tool_name, params):
            if params["cql"] == "type=page AND parent=123":
                return ToolResult.from_data(
                    {
                        "results": [
                            {"id": "111", "title": "Child 1", "url": "url1"},
                            {"id": "222", "title": "Child 2"},
                        ]
                    }
                )
            return ToolResult.from_data({"results": []})

        mock_mcp_client.call_tool.side_effect = mock_call_tool
        result = await confluence_reader.get_children_by_id("123", "SPACE")
        assert result.success is True
        assert result.data is not None
        assert len(result.data) == 2
        assert result.data[0].page_id == "111"
        assert result.data[0].title == "Child 1"
        assert result.data[0].url == "url1"

    async def test_get_children_by_id_extracts_version(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Child version (Confluence revision) is surfaced on PageSummary for change detection."""

        def mock_call_tool(tool_name, params):
            if params["cql"] == "type=page AND parent=123":
                return ToolResult.from_data(
                    {
                        "results": [
                            {"id": "111", "title": "Child 1", "version": {"number": 7}},
                            {"id": "222", "title": "Child 2"},  # no version → None
                        ]
                    }
                )
            return ToolResult.from_data({"results": []})

        mock_mcp_client.call_tool.side_effect = mock_call_tool
        result = await confluence_reader.get_children_by_id("123", "SPACE")
        assert result.success is True
        assert result.data is not None
        assert result.data[0].version == 7
        assert result.data[1].version is None

    async def test_get_children_by_id_error(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test getting child pages with error."""
        mock_mcp_client.call_tool.return_value = ToolResult.from_error("Search failed")
        result = await confluence_reader.get_children_by_id("123")
        assert result.success is True
        assert result.data == []
        assert any("Search failed" in w for w in result.warnings)

    async def test_find_parent_pages_success(
        self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock
    ) -> None:
        """Test finding parent pages."""
        mock_mcp_client.call_tool.return_value = ToolResult.from_data(
            {
                "results": [
                    {"id": "111", "title": "Requirements"},
                ]
            }
        )
        result = await confluence_reader.find_parent_pages("SPACE")
        assert result.success is True
        assert result.data is not None
        assert len(result.data) == 1
        assert result.data[0].page_id == "111"
