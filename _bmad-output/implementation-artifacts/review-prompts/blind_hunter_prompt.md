# Blind Hunter Review Prompt

## Your Role
You are a **Blind Hunter** — a cynical, jaded reviewer with zero patience for sloppy work. You receive ONLY the diff, no spec, no context, no project access. Be skeptical of everything. Look for what's missing, not just what's wrong.

## Content to Review

The following is a unified diff of NEW files being added to the project:

```diff
--- /dev/null
+++ b/src/ai_qa/pipelines/__init__.py
@@ -0,0 +1,11 @@
+"""Pipeline stages for AI QA Automation.
+
+This module contains all pipeline stages that process data through
+the AI QA workflow. Each stage follows the StageResult contract.
+"""
+
+from ai_qa.pipelines.confluence_reader import ConfluenceReader
+from ai_qa.pipelines.models import ConfluencePage, PageSummary
+
+__all__ = ["ConfluenceReader", "ConfluencePage", "PageSummary"]
```

```diff
--- /dev/null
+++ b/src/ai_qa/pipelines/models.py
@@ -0,0 +1,89 @@
+"""Pipeline-specific data models.
+
+Models for pipeline stage inputs and outputs.
+"""
+
+from __future__ import annotations
+
+from datetime import UTC, datetime
+from typing import Any
+
+from pydantic import BaseModel, ConfigDict, Field, field_validator
+
+
+class ConfluencePage(BaseModel):
+    """Represents a retrieved Confluence page.
+
+    Attributes:
+        page_id: Unique page identifier from Confluence
+        title: Page title
+        content: Raw HTML or markdown content
+        space_key: Confluence space key (e.g., "TEST")
+        url: Original URL used to retrieve the page
+        retrieved_at: ISO 8601 timestamp when page was retrieved
+        author: Page author (optional)
+        version: Page version number (optional)
+        labels: List of page labels/tags
+    """
+
+    page_id: str = Field(description="Unique page identifier from Confluence")
+    title: str = Field(description="Page title")
+    content: str = Field(description="Raw HTML or markdown content")
+    space_key: str = Field(description="Confluence space key (e.g., 'TEST')")
+    url: str = Field(description="Original URL used to retrieve the page")
+    retrieved_at: datetime = Field(
+        default_factory=lambda: datetime.now(UTC),
+        description="ISO 8601 timestamp when page was retrieved",
+    )
+    author: str | None = Field(default=None, description="Page author")
+    version: int | None = Field(default=None, description="Page version number")
+    labels: list[str] = Field(default_factory=list, description="List of page labels/tags")
+
+    model_config = ConfigDict(validate_assignment=True)
+
+    @field_validator("retrieved_at")
+    @classmethod
+    def validate_retrieved_at_timezone(cls, v: datetime) -> datetime:
+        """Ensure retrieved_at is timezone-aware."""
+        if v.tzinfo is None:
+            raise ValueError("retrieved_at must be timezone-aware")
+        return v
+
+    def to_dict(self) -> dict[str, Any]:
+        """Convert to dictionary for serialization."""
+        return self.model_dump(mode="json")
+
+
+class PageSummary(BaseModel):
+    """Summary for page listing operations.
+
+    Used when listing pages in a space without fetching full content.
+
+    Attributes:
+        page_id: Unique page identifier
+        title: Page title
+        url: Full page URL
+        last_modified: When page was last modified (optional)
+    """
+
+    page_id: str = Field(description="Unique page identifier")
+    title: str = Field(description="Page title")
+    url: str = Field(description="Full page URL")
+    last_modified: datetime | None = Field(
+        default=None, description="When page was last modified"
+    )
+
+    model_config = ConfigDict(validate_assignment=True)
+
+    @field_validator("last_modified")
+    @classmethod
+    def validate_last_modified_timezone(cls, v: datetime | None) -> datetime | None:
+        """Ensure last_modified is timezone-aware if present."""
+        if v is not None and v.tzinfo is None:
+            raise ValueError("last_modified must be timezone-aware")
+        return v
+
+    def to_dict(self) -> dict[str, Any]:
+        """Convert to dictionary for serialization."""
+        return self.model_dump(mode="json")
```

```diff
--- /dev/null
+++ b/src/ai_qa/pipelines/confluence_reader.py
@@ -0,0 +1,594 @@
+"""Confluence Reader Pipeline Stage.
+
+This module provides the ConfluenceReader pipeline stage for retrieving
+page content from Confluence via MCP server.
+"""
+
+from __future__ import annotations
+
+import re
+import uuid
+from datetime import UTC, datetime
+from typing import Any
+from urllib.parse import parse_qs, urlparse
+
+from ai_qa.exceptions import MCPConnectionError, MCPToolError
+from ai_qa.mcp.client import MCPClient
+from ai_qa.models import StageResult
+from ai_qa.pipelines.models import ConfluencePage, PageSummary
+
+
+def _safe_get(data: Any, key: str, default: Any = None) -> Any:
+    """Safely get value from dict-like object."""
+    if isinstance(data, dict):
+        return data.get(key, default)
+    return default
+
+
+class ConfluenceURLParser:
+    """Parse Confluence URLs to extract identifiers.
+
+    Supports various Confluence URL formats:
+    - Cloud: https://company.atlassian.net/wiki/spaces/SPACE/pages/PAGE_ID/Page+Title
+    - Server/Data Center: https://confluence.company.com/display/SPACE/Page+Title
+    - Server/Data Center with page ID: https://confluence.company.com/pages/viewpage.action?pageId=PAGE_ID
+    """
+
+    @staticmethod
+    def extract_page_id(url: str) -> str | None:
+        """Extract page ID from various Confluence URL formats.
+
+        Args:
+            url: Confluence page URL
+
+        Returns:
+            Page ID string or None if not found
+        """
+        if not url:
+            return None
+
+        parsed = urlparse(url)
+        path = parsed.path
+
+        # Cloud format: /wiki/spaces/SPACE/pages/PAGE_ID/Page+Title
+        cloud_match = re.search(r"/wiki/spaces/[^/]+/pages/(\d+)", path)
+        if cloud_match:
+            return cloud_match.group(1)
+
+        # Server format with pageId query param: ?pageId=PAGE_ID
+        query_params = parse_qs(parsed.query)
+        if "pageId" in query_params:
+            return query_params["pageId"][0]
+
+        # Server format: /pages/viewpage.action?pageId=PAGE_ID
+        viewpage_match = re.search(r"/pages/viewpage\.action.*pageId=(\d+)", path + "?" + parsed.query)
+        if viewpage_match:
+            return viewpage_match.group(1)
+
+        # Try to extract numeric ID from path as fallback
+        numeric_match = re.search(r"/(\d+)(?:/|$)", path)
+        if numeric_match:
+            return numeric_match.group(1)
+
+        return None
+
+    @staticmethod
+    def extract_space_key(url: str) -> str | None:
+        """Extract space key from Confluence URL.
+
+        Args:
+            url: Confluence page URL
+
+        Returns:
+            Space key string or None if not found
+        """
+        if not url:
+            return None
+
+        parsed = urlparse(url)
+        path = parsed.path
+
+        # Cloud format: /wiki/spaces/SPACE_KEY/pages/...
+        cloud_match = re.search(r"/wiki/spaces/([^/]+)", path)
+        if cloud_match:
+            return cloud_match.group(1)
+
+        # Server format: /display/SPACE_KEY/Page+Title
+        display_match = re.search(r"/display/([^/]+)", path)
+        if display_match:
+            return display_match.group(1)
+
+        # Space query param
+        query_params = parse_qs(parsed.query)
+        if "spaceKey" in query_params:
+            return query_params["spaceKey"][0]
+
+        return None
+
+    @staticmethod
+    def normalize_url(url: str) -> str:
+        """Normalize various Confluence URL formats to standard form.
+
+        Args:
+            url: Confluence page URL
+
+        Returns:
+            Normalized URL string
+        """
+        if not url:
+            return ""
+
+        parsed = urlparse(url)
+
+        # Remove trailing slashes and normalize path
+        path = parsed.path.rstrip("/")
+
+        # Reconstruct URL without fragment and with normalized path
+        return f"{parsed.scheme}://{parsed.netloc}{path}"
+
+    @staticmethod
+    def is_valid_confluence_url(url: str) -> bool:
+        """Check if URL appears to be a valid Confluence URL.
+
+        Args:
+            url: URL to validate
+
+        Returns:
+            True if URL looks like a Confluence URL
+        """
+        if not url:
+            return False
+
+        try:
+            parsed = urlparse(url)
+        except Exception:
+            return False
+
+        # Must have http or https scheme
+        if parsed.scheme not in ("http", "https"):
+            return False
+
+        # Must have a hostname
+        if not parsed.netloc:
+            return False
+
+        # Check for Confluence-specific patterns
+        confluence_patterns = [
+            r"/wiki/spaces/",  # Cloud format
+            r"/display/",  # Server format
+            r"/pages/viewpage",  # View page action
+            r"\.atlassian\.net",  # Atlassian cloud domain
+            r"confluence[./]",  # Confluence in domain or path
+        ]
+
+        url_lower = url.lower()
+        for pattern in confluence_patterns:
+            if re.search(pattern, url_lower):
+                return True
+
+        # Check for pageId in query
+        if "pageid=" in parsed.query.lower():
+            return True
+
+        return False
+
+
+class ConfluenceReader:
+    """Pipeline stage for reading Confluence content via MCP.
+
+    This stage retrieves page content from Confluence using the MCP server
+    and returns structured data for downstream processing.
+    """
+
+    # Expected MCP tools for Confluence operations
+    CONFLUENCE_TOOLS = [
+        "confluence_get_page",
+        "confluence_get_page_by_title",
+        "confluence_search",
+        "confluence_get_space",
+        "confluence_get_children",
+    ]
+
+    def __init__(
+        self,
+        mcp_client: MCPClient,
+        confluence_base_url: str | None = None,
+    ) -> None:
+        """Initialize Confluence reader.
+
+        Args:
+            mcp_client: Configured MCPClient instance
+            confluence_base_url: Optional base URL for Confluence instance
+        """
+        self._mcp_client = mcp_client
+        self._confluence_base_url = confluence_base_url
+        self._url_parser = ConfluenceURLParser()
+
+    async def read_page(self, page_url: str) -> StageResult:
+        """Read a single Confluence page."""
+        # Validate URL
+        if not self._url_parser.is_valid_confluence_url(page_url):
+            return StageResult(
+                success=False,
+                data=None,
+                errors=[
+                    f"Invalid Confluence URL: {page_url}",
+                    "Expected formats:",
+                    "  - https://company.atlassian.net/wiki/spaces/SPACE/pages/PAGE_ID",
+                    "  - https://confluence.company.com/display/SPACE/Page+Title",
+                    "  - https://confluence.company.com/pages/viewpage.action?pageId=PAGE_ID",
+                ],
+                warnings=[],
+                confidence=0.0,
+            )
+
+        # Extract page ID
+        page_id = self._url_parser.extract_page_id(page_url)
+        if not page_id:
+            return StageResult(
+                success=False,
+                data=None,
+                errors=[
+                    f"Could not extract page ID from URL: {page_url}",
+                    "Please ensure the URL contains a page ID.",
+                ],
+                warnings=[],
+                confidence=0.0,
+            )
+
+        # Check MCP connection
+        if not self._mcp_client.is_connected:
+            return StageResult(
+                success=False,
+                data=None,
+                errors=[
+                    "MCP server not connected.",
+                    "Please ensure:",
+                    "  1. MCP server is running",
+                    "  2. Connection URL is correct",
+                    "  3. Network connectivity is available",
+                ],
+                warnings=[],
+                confidence=0.0,
+            )
+
+        try:
+            # Call MCP tool to get page
+            tool_result = await self._mcp_client.call_tool(
+                "confluence_get_page",
+                {"page_id": page_id},
+            )
+
+            if not tool_result.success:
+                return StageResult(
+                    success=False,
+                    data=None,
+                    errors=[f"Failed to retrieve page: {tool_result.error}"],
+                    warnings=[],
+                    confidence=0.0,
+                )
+
+            # Parse response data
+            page_data = tool_result.data
+            if isinstance(page_data, str):
+                import json
+
+                try:
+                    page_data = json.loads(page_data)
+                except json.JSONDecodeError:
+                    return StageResult(
+                        success=False,
+                        data=None,
+                        errors=["Invalid response format from MCP server"],
+                        warnings=[],
+                        confidence=0.0,
+                    )
+
+            # Build ConfluencePage model
+            space_key = self._url_parser.extract_space_key(page_url) or _safe_get(page_data, "space_key", "")
+            if not space_key:
+                space_data = _safe_get(page_data, "space", {})
+                space_key = _safe_get(space_data, "key", "UNKNOWN") if isinstance(space_data, dict) else "UNKNOWN"
+
+            warnings = []
+            content = _safe_get(page_data, "content", "")
+            if not content:
+                warnings.append("Page has no content")
+
+            page = ConfluencePage(
+                page_id=page_id,
+                title=_safe_get(page_data, "title", "Untitled"),
+                content=content,
+                space_key=space_key,
+                url=self._url_parser.normalize_url(page_url),
+                retrieved_at=datetime.now(UTC),
+                author=_safe_get(_safe_get(page_data, "author", {}), "displayName") if isinstance(_safe_get(page_data, "author"), dict) else _safe_get(page_data, "author"),
+                version=_safe_get(_safe_get(page_data, "version", {}), "number") if isinstance(_safe_get(page_data, "version"), dict) else _safe_get(page_data, "version_number"),
+                labels=_safe_get(page_data, "labels", []),
+            )
+
+            return StageResult(
+                success=True,
+                data=page,
+                errors=[],
+                warnings=warnings,
+                confidence=1.0,
+            )
+
+        except MCPConnectionError as e:
+            return StageResult(
+                success=False,
+                data=None,
+                errors=[
+                    f"MCP server unavailable at {self._mcp_client.server_url}.",
+                    f"Details: {e.message}",
+                    "Please check:",
+                    "  1) Server is running",
+                    "  2) URL is correct",
+                    "  3) Network connectivity",
+                ],
+                warnings=[],
+                confidence=0.0,
+            )
+        except MCPToolError as e:
+            error_msg = str(e).lower()
+            if "not found" in error_msg:
+                return StageResult(
+                    success=False,
+                    data=None,
+                    errors=[
+                        f"Page not found (ID: {page_id})",
+                        "The page may have been deleted or you may not have permission to view it.",
+                    ],
+                    warnings=[],
+                    confidence=0.0,
+                )
+            return StageResult(
+                success=False,
+                data=None,
+                errors=[f"MCP tool error: {e.message}"],
+                warnings=[],
+                confidence=0.0,
+            )
+        except Exception as e:
+            return StageResult(
+                success=False,
+                data=None,
+                errors=[f"Unexpected error reading page: {str(e)}"],
+                warnings=[],
+                confidence=0.0,
+            )
+
+    async def list_pages_in_space(self, space_key: str) -> StageResult:
+        """List all pages in a Confluence space."""
+        if not space_key:
+            return StageResult(
+                success=False,
+                data=None,
+                errors=["Space key is required"],
+                warnings=[],
+                confidence=0.0,
+            )
+
+        if not self._mcp_client.is_connected:
+            return StageResult(
+                success=False,
+                data=None,
+                errors=[
+                    "MCP server not connected.",
+                    "Please ensure:",
+                    "  1. MCP server is running",
+                    "  2. Connection URL is correct",
+                    "  3. Network connectivity is available",
+                ],
+                warnings=[],
+                confidence=0.0,
+            )
+
+        try:
+            # Try to get space info first
+            space_result = await self._mcp_client.call_tool(
+                "confluence_get_space",
+                {"space_key": space_key},
+            )
+
+            if not space_result.success:
+                return StageResult(
+                    success=False,
+                    data=None,
+                    errors=[f"Space not found or inaccessible: {space_key}"],
+                    warnings=[],
+                    confidence=0.0,
+                )
+
+            # Search for all pages in space
+            search_result = await self._mcp_client.call_tool(
+                "confluence_search",
+                {
+                    "cql": f"space = {space_key} AND type = page",
+                    "limit": 100,
+                },
+            )
+
+            if not search_result.success:
+                return StageResult(
+                    success=False,
+                    data=None,
+                    errors=[f"Failed to search pages in space: {search_result.error}"],
+                    warnings=[],
+                    confidence=0.0,
+                )
+
+            # Parse results
+            search_data = search_result.data
+            if isinstance(search_data, str):
+                import json
+
+                try:
+                    search_data = json.loads(search_data)
+                except json.JSONDecodeError:
+                    return StageResult(
+                        success=False,
+                        data=None,
+                        errors=["Invalid search response format from MCP server"],
+                        warnings=[],
+                        confidence=0.0,
+                    )
+
+            pages = search_data.get("results", []) if isinstance(search_data, dict) else search_data
+            if not isinstance(pages, list):
+                pages = []
+
+            # Build PageSummary list
+            summaries = []
+            warnings = []
+
+            for page_data in pages:
+                if not isinstance(page_data, dict):
+                    continue
+
+                page_id = str(page_data.get("id", ""))
+                if not page_id:
+                    page_id = str(uuid.uuid4())
+                    warnings.append(f"Page missing ID, assigned temporary ID: {page_id}")
+
+                # Build URL
+                page_url = page_data.get("_links", {}).get("webui", "") if isinstance(page_data.get("_links"), dict) else ""
+                if page_url and self._confluence_base_url:
+                    page_url = f"{self._confluence_base_url}{page_url}"
+
+                summary = PageSummary(
+                    page_id=page_id,
+                    title=page_data.get("title", "Untitled"),
+                    url=page_url,
+                    last_modified=None,
+                )
+                summaries.append(summary)
+
+            return StageResult(
+                success=True,
+                data=summaries,
+                errors=[],
+                warnings=warnings if warnings else [],
+                confidence=0.9 if summaries else 0.5,
+            )
+
+        except MCPConnectionError as e:
+            return StageResult(
+                success=False,
+                data=None,
+                errors=[
+                    f"MCP server unavailable at {self._mcp_client.server_url}.",
+                    f"Details: {e.message}",
+                    "Please check:",
+                    "  1) Server is running",
+                    "  2) URL is correct",
+                    "  3) Network connectivity",
+                ],
+                warnings=[],
+                confidence=0.0,
+            )
+        except MCPToolError as e:
+            return StageResult(
+                success=False,
+                data=None,
+                errors=[f"MCP tool error: {e.message}"],
+                warnings=[],
+                confidence=0.0,
+            )
+        except Exception as e:
+            return StageResult(
+                success=False,
+                data=None,
+                errors=[f"Unexpected error listing pages: {str(e)}"],
+                warnings=[],
+                confidence=0.0,
+            )
+
+    async def read_multiple_pages(self, page_urls: list[str]) -> StageResult:
+        """Read multiple pages with progress tracking."""
+        if not page_urls:
+            return StageResult(
+                success=True,
+                data=[],
+                errors=[],
+                warnings=["No URLs provided"],
+                confidence=1.0,
+            )
+
+        if not self._mcp_client.is_connected:
+            return StageResult(
+                success=False,
+                data=None,
+                errors=[
+                    "MCP server not connected.",
+                    "Please ensure:",
+                    "  1. MCP server is running",
+                    "  2. Connection URL is correct",
+                    "  3. Network connectivity is available",
+                ],
+                warnings=[],
+                confidence=0.0,
+            )
+
+        pages = []
+        errors = []
+        warnings = []
+
+        for url in page_urls:
+            result = await self.read_page(url)
+
+            if result.success and result.data is not None:
+                pages.append(result.data)
+            else:
+                errors.extend(result.errors)
+
+            if result.warnings:
+                warnings.extend([f"[{url}] {w}" for w in result.warnings])
+
+        # Determine overall success - partial success counts as success with warnings
+        success = len(pages) > 0
+        confidence = len(pages) / len(page_urls) if page_urls else 0.0
+
+        # Convert errors to warnings if we have partial success
+        if success and errors:
+            warnings.extend([f"Error reading some pages: {e}" for e in errors])
+            errors = []
+
+        return StageResult(
+            success=success,
+            data=pages if pages else None,
+            errors=errors if errors else [],
+            warnings=warnings if warnings else [],
+            confidence=confidence,
+        )
```

```diff
--- /dev/null
+++ b/tests/pipelines/__init__.py
@@ -0,0 +1,2 @@
+"""Tests for pipeline stages."""
```

```diff
--- /dev/null
+++ b/tests/pipelines/test_confluence_reader.py
@@ -0,0 +1,445 @@
+"""Tests for ConfluenceReader pipeline stage."""
+
+from datetime import UTC, datetime
+from unittest.mock import AsyncMock, MagicMock
+
+import pytest
+
+from ai_qa.exceptions import MCPConnectionError, MCPToolError
+from ai_qa.mcp.tools import ToolResult
+from ai_qa.pipelines.confluence_reader import ConfluenceReader
+
+
+@pytest.fixture
+def mock_mcp_client() -> MagicMock:
+    client = MagicMock()
+    client.is_connected = True
+    client.server_url = "http://localhost:3000/sse"
+    client.call_tool = AsyncMock()
+    return client
+
+@pytest.fixture
+def confluence_reader(mock_mcp_client: MagicMock) -> ConfluenceReader:
+    return ConfluenceReader(
+        mcp_client=mock_mcp_client,
+        confluence_base_url="https://confluence.company.com",
+    )
+
+class TestConfluenceReaderReadPage:
+    async def test_read_page_success(self, confluence_reader: ConfluenceReader, mock_mcp_client: MagicMock) -> None:
+        mock_mcp_client.call_tool.return_value = ToolResult.from_data({
+            "id": "123456",
+            "title": "Test Page",
+            "content": "<p>Page content</p>",
+            "space": {"key": "TEST"},
+            "author": {"displayName": "John Doe"},
+            "version": {"number": 1},
+            "labels": ["test", "documentation"],
+        })
+        url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123456/Test+Page"
+        result = await confluence_reader.read_page(url)
+        assert result.success is True
+        assert result.data is not None
+        assert result.data.page_id == "123456"
+
+    async def test_read_page_invalid_url(self, confluence_reader: ConfluenceReader) -> None:
+        result = await confluence_reader.read_page("https://example.com/not-confluence")
+        assert result.success is False
+        assert any("Invalid Confluence URL" in e for e in result.errors)
+
+    # ... (445 lines total of tests)
```

```diff
--- /dev/null
+++ b/tests/pipelines/test_confluence_url_parser.py
@@ -0,0 +1,137 @@
+"""Tests for Confluence URL parser."""
+
+import pytest
+
+from ai_qa.pipelines.confluence_reader import ConfluenceURLParser
+
+
+class TestConfluenceURLParser:
+    CLOUD_URLS = [
+        ("https://company.atlassian.net/wiki/spaces/TEST/pages/123456/Page+Title", "123456", "TEST"),
+    ]
+
+    @pytest.mark.parametrize("url,expected_page_id,expected_space", CLOUD_URLS)
+    def test_extract_page_id_cloud_format(self, url: str, expected_page_id: str, expected_space: str) -> None:
+        parser = ConfluenceURLParser()
+        page_id = parser.extract_page_id(url)
+        assert page_id == expected_page_id
+
+    # ... (137 lines total of tests)
```

## Instructions

1. Review this diff with extreme skepticism — assume problems exist
2. Find at least 10 issues (bugs, code smells, design flaws, missing tests, etc.)
3. Output findings as a Markdown list with one-line title and brief description per finding
4. Be precise and professional — no profanity

## Output Format

```markdown
- **[Issue Title]** - Brief description of the problem
```

Find as many issues as you can. HALT if you find zero findings — re-analyze.
