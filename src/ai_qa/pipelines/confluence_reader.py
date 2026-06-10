"""Confluence Reader Pipeline Stage.

This module provides the ConfluenceReader pipeline stage for retrieving
page content from Confluence via MCP server.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, unquote_plus, urlparse

from ai_qa.exceptions import MCPConnectionError, MCPToolError
from ai_qa.mcp.client import MCPClient
from ai_qa.models import StageResult
from ai_qa.pipelines.models import ConfluencePage, PageSummary

# Default constants
DEFAULT_PAGE_LIMIT = 100
DEFAULT_MAX_CONCURRENT_REQUESTS = 5

# Compiled regex patterns for URL parsing
_CLOUD_PAGE_ID_RE = re.compile(r"/wiki/spaces/[^/]+/pages/(\d+)")
_VIEWPAGE_ID_RE = re.compile(r"/pages/viewpage\.action.*pageId=(\d+)")
_NUMERIC_ID_RE = re.compile(r"/(\d+)(?:/|$)")
_CLOUD_SPACE_RE = re.compile(r"/wiki/spaces/([^/]+)")
_DISPLAY_SPACE_RE = re.compile(r"/display/([^/]+)")
_CONFLUENCE_URL_PATTERNS = [
    re.compile(r"/wiki/spaces/"),
    re.compile(r"/display/"),
    re.compile(r"/pages/viewpage"),
    re.compile(r"\.atlassian\.net"),
    re.compile(r"confluence[./]"),
]

# Error message constants
_MCP_NOT_CONNECTED_ERROR = [
    "MCP server not connected.",
    "Please ensure:",
    "  1. MCP server is running",
    "  2. Connection URL is correct",
    "  3. Network connectivity is available",
]
_MCP_UNAVAILABLE_ERROR_TEMPLATE = "MCP server unavailable at {}."
_MCP_UNAVAILABLE_CHECKS = [
    "Please check:",
    "  1) Server is running",
    "  2) URL is correct",
    "  3) Network connectivity",
]


def _safe_get(data: Any, key: str, default: Any = None) -> Any:
    """Safely get value from dict-like object."""
    if isinstance(data, dict):
        return data.get(key, default)
    return default


class ConfluenceURLParser:
    """Parse Confluence URLs to extract identifiers.

    Supports various Confluence URL formats:
    - Cloud: https://company.atlassian.net/wiki/spaces/SPACE/pages/PAGE_ID/Page+Title
    - Server/Data Center: https://confluence.company.com/display/SPACE/Page+Title
    - Server/Data Center with page ID: https://confluence.company.com/pages/viewpage.action?pageId=PAGE_ID
    """

    @staticmethod
    def extract_page_id(url: str) -> str | None:
        """Extract page ID from various Confluence URL formats.

        Args:
            url: Confluence page URL

        Returns:
            Page ID string or None if not found
        """
        if not url:
            return None

        parsed = urlparse(url)
        path = parsed.path

        # Cloud format: /wiki/spaces/SPACE/pages/PAGE_ID/Page+Title
        cloud_match = _CLOUD_PAGE_ID_RE.search(path)
        if cloud_match:
            return cloud_match.group(1)

        # Server format with pageId query param: ?pageId=PAGE_ID
        query_params = parse_qs(parsed.query)
        if "pageId" in query_params:
            # Handle multiple values - use first, warn if ambiguous
            page_ids = query_params["pageId"]
            if len(page_ids) > 1:
                # Multiple pageIds found - this is ambiguous
                # Return first but this should be handled by caller
                pass
            return page_ids[0]

        # Server format: /pages/viewpage.action?pageId=PAGE_ID
        viewpage_match = _VIEWPAGE_ID_RE.search(path + "?" + parsed.query)
        if viewpage_match:
            return viewpage_match.group(1)

        # Try to extract numeric ID from path as fallback
        numeric_match = _NUMERIC_ID_RE.search(path)
        if numeric_match:
            return numeric_match.group(1)

        return None

    @staticmethod
    def extract_space_key(url: str) -> str | None:
        """Extract space key from Confluence URL.

        Args:
            url: Confluence page URL

        Returns:
            Space key string or None if not found
        """
        if not url:
            return None

        parsed = urlparse(url)
        path = parsed.path

        # Cloud format: /wiki/spaces/SPACE_KEY/pages/...
        cloud_match = _CLOUD_SPACE_RE.search(path)
        if cloud_match:
            return cloud_match.group(1)

        # Server format: /display/SPACE_KEY/Page+Title
        display_match = _DISPLAY_SPACE_RE.search(path)
        if display_match:
            return display_match.group(1)

        # Space query param
        query_params = parse_qs(parsed.query)
        if "spaceKey" in query_params:
            return query_params["spaceKey"][0]

        return None

    @staticmethod
    def extract_page_title(url: str) -> str | None:
        """Extract page title from Confluence URL if present in path."""
        if not url:
            return None

        parsed = urlparse(url)
        path = parsed.path

        # Server format: /display/SPACE_KEY/Page+Title
        display_match = _DISPLAY_SPACE_RE.search(path)
        if display_match:
            parts = path.split(display_match.group(0))
            if len(parts) > 1 and parts[1]:
                title_part = parts[1].lstrip("/")
                if title_part:
                    return unquote_plus(title_part)

        return None

    @staticmethod
    def normalize_url(url: str) -> str:
        """Normalize various Confluence URL formats to standard form.

        Args:
            url: Confluence page URL

        Returns:
            Normalized URL string
        """
        if not url:
            return ""

        parsed = urlparse(url)

        # Remove trailing slashes and normalize path
        path = parsed.path.rstrip("/")

        # Reconstruct URL without fragment and with normalized path
        return f"{parsed.scheme}://{parsed.netloc}{path}"

    @staticmethod
    def is_valid_confluence_url(url: str) -> bool:
        """Check if URL appears to be a valid Confluence URL.

        Args:
            url: URL to validate

        Returns:
            True if URL looks like a Confluence URL
        """
        if not url:
            return False

        try:
            parsed = urlparse(url)
        except Exception:
            return False

        # Must have http or https scheme
        if parsed.scheme not in ("http", "https"):
            return False

        # Must have a hostname
        if not parsed.netloc:
            return False

        # Check for Confluence-specific patterns using compiled regex
        url_lower = url.lower()
        for pattern in _CONFLUENCE_URL_PATTERNS:
            if pattern.search(url_lower):
                return True

        # Check for pageId in query
        if "pageid=" in parsed.query.lower():
            return True

        return False


class ConfluenceReader:
    """Pipeline stage for reading Confluence content via MCP.

    This stage retrieves page content from Confluence using the MCP server
    and returns structured data for downstream processing.

    Example:
        >>> reader = ConfluenceReader(mcp_client)
        >>> result = await reader.read_page("https://confluence.company.com/x/ABC123")
        >>> if result.success:
        ...     page = result.data
        ...     print(page.title)
    """

    # Expected MCP tools for Confluence operations
    CONFLUENCE_TOOLS = [
        "confluence_get_page",  # Get single page by ID
        "confluence_get_page_by_title",  # Get page by title
        "confluence_search",  # Search pages
        "confluence_get_space",  # Get space details
    ]

    def __init__(
        self,
        mcp_client: MCPClient,
        confluence_base_url: str | None = None,
        max_concurrent_requests: int = DEFAULT_MAX_CONCURRENT_REQUESTS,
    ) -> None:
        """Initialize Confluence reader.

        Args:
            mcp_client: Configured MCPClient instance
            confluence_base_url: Optional base URL for Confluence instance
            max_concurrent_requests: Maximum number of concurrent requests for batch operations

        Raises:
            ValueError: If mcp_client is None
        """
        if mcp_client is None:
            raise ValueError("MCP client is required")
        self._mcp_client = mcp_client
        self._tool_prefix = (
            getattr(mcp_client._settings, "mcp_tool_prefix", "")
            if hasattr(mcp_client, "_settings")
            else ""
        )
        self._confluence_base_url = confluence_base_url
        self._max_concurrent_requests = max_concurrent_requests
        self._url_parser = ConfluenceURLParser()

    def _get_tool_name(self, base_name: str) -> str:
        """Get the full tool name including any configured prefix."""
        return f"{self._tool_prefix}{base_name}"

    async def read_page(self, page_url: str) -> StageResult:
        """Read a single Confluence page.

        Args:
            page_url: Full Confluence page URL

        Returns:
            StageResult with ConfluencePage data or error details
        """
        # Validate URL
        if not self._url_parser.is_valid_confluence_url(page_url):
            return StageResult(
                success=False,
                data=None,
                errors=[
                    f"Invalid Confluence URL: {page_url}",
                    "Expected formats:",
                    "  - https://company.atlassian.net/wiki/spaces/SPACE/pages/PAGE_ID",
                    "  - https://confluence.company.com/display/SPACE/Page+Title",
                    "  - https://confluence.company.com/pages/viewpage.action?pageId=PAGE_ID",
                ],
                warnings=[],
                confidence=0.0,
            )

        # Extract page ID
        page_id = self._url_parser.extract_page_id(page_url)
        if not page_id:
            return StageResult(
                success=False,
                data=None,
                errors=[
                    f"Could not extract page ID from URL: {page_url}",
                    "Please ensure the URL contains a page ID.",
                ],
                warnings=[],
                confidence=0.0,
            )

        # Check MCP connection
        if not self._mcp_client.is_connected:
            return StageResult(
                success=False,
                data=None,
                errors=_MCP_NOT_CONNECTED_ERROR,
                warnings=[],
                confidence=0.0,
            )

        try:
            # Call MCP tool to get page
            tool_result = await self._mcp_client.call_tool(
                self._get_tool_name("confluence_get_page"),
                {
                    "page_id": page_id,
                    "format": "view",
                    "userPrompt": "User initiated a story creation workflow from a Confluence page link.",
                    "llmReasoning": "Need to extract the content of the provided Confluence page to fulfill the user's request.",
                },
            )

            if not tool_result.success:
                return StageResult(
                    success=False,
                    data=None,
                    errors=[f"Failed to retrieve page: {tool_result.error}"],
                    warnings=[],
                    confidence=0.0,
                )

            # Parse response data
            page_data = tool_result.data
            if isinstance(page_data, str):
                try:
                    page_data = json.loads(page_data)
                except json.JSONDecodeError:
                    return StageResult(
                        success=False,
                        data=None,
                        errors=["Invalid response format from MCP server"],
                        warnings=[],
                        confidence=0.0,
                    )

            # Build ConfluencePage model
            space_key = self._url_parser.extract_space_key(page_url) or _safe_get(
                page_data, "space_key", ""
            )
            if not space_key:
                space_data = _safe_get(page_data, "space", {})
                space_key = (
                    _safe_get(space_data, "key", "UNKNOWN")
                    if isinstance(space_data, dict)
                    else "UNKNOWN"
                )

            warnings = []

            def _extract_html_content(p_data: Any) -> str:
                c = _safe_get(p_data, "content", "") or _safe_get(p_data, "body", "")
                if isinstance(c, dict):
                    if "view" in c and isinstance(c["view"], dict) and c["view"].get("value"):
                        return str(c["view"]["value"])
                    if (
                        "storage" in c
                        and isinstance(c["storage"], dict)
                        and c["storage"].get("value")
                    ):
                        return str(c["storage"]["value"])
                    if (
                        "export_view" in c
                        and isinstance(c["export_view"], dict)
                        and c["export_view"].get("value")
                    ):
                        return str(c["export_view"]["value"])
                    if (
                        "anonymous_export_view" in c
                        and isinstance(c["anonymous_export_view"], dict)
                        and c["anonymous_export_view"].get("value")
                    ):
                        return str(c["anonymous_export_view"]["value"])
                    for _, v in c.items():
                        if isinstance(v, dict) and v.get("value"):
                            return str(v["value"])
                    return str(c)
                return str(c) if c else ""

            content = _extract_html_content(page_data)
            if not content:
                warnings.append("Page has no content")

            page = ConfluencePage(
                page_id=page_id,
                title=_safe_get(page_data, "title", "Untitled"),
                content=content,
                space_key=space_key,
                url=self._url_parser.normalize_url(page_url),
                retrieved_at=datetime.now(UTC),
                author=_safe_get(_safe_get(page_data, "author", {}), "displayName")
                if isinstance(_safe_get(page_data, "author"), dict)
                else _safe_get(page_data, "author"),
                version=_safe_get(_safe_get(page_data, "version", {}), "number")
                if isinstance(_safe_get(page_data, "version"), dict)
                else _safe_get(page_data, "version_number"),
                labels=_safe_get(page_data, "labels", []),
            )

            return StageResult(
                success=True,
                data=page,
                errors=[],
                warnings=warnings,
                confidence=1.0,
            )

        except MCPConnectionError as e:
            return StageResult(
                success=False,
                data=None,
                errors=[
                    _MCP_UNAVAILABLE_ERROR_TEMPLATE.format(self._mcp_client.server_url),
                    f"Details: {e.message}",
                ]
                + _MCP_UNAVAILABLE_CHECKS,
                warnings=[],
                confidence=0.0,
            )
        except MCPToolError as e:
            error_msg = str(e).lower()
            if "not found" in error_msg:
                return StageResult(
                    success=False,
                    data=None,
                    errors=[
                        f"Page not found (ID: {page_id})",
                        "The page may have been deleted or you may not have permission to view it.",
                    ],
                    warnings=[],
                    confidence=0.0,
                )
            return StageResult(
                success=False,
                data=None,
                errors=[f"MCP tool error: {e.message}"],
                warnings=[],
                confidence=0.0,
            )
        except Exception as e:
            return StageResult(
                success=False,
                data=None,
                errors=[f"Unexpected error reading page: {str(e)}"],
                warnings=[],
                confidence=0.0,
            )

    async def read_page_by_id(self, page_id: str) -> StageResult:
        """Read a single Confluence page directly by its numeric page ID.

        This is the preferred method when a page_id is available from the URL,
        because it works with any Confluence URL format regardless of path structure.

        Args:
            page_id: Numeric Confluence page ID (e.g. "1238866187")

        Returns:
            StageResult with ConfluencePage data or error details
        """
        if not self._mcp_client.is_connected:
            return StageResult(
                success=False,
                data=None,
                errors=_MCP_NOT_CONNECTED_ERROR,
                warnings=[],
                confidence=0.0,
            )

        try:
            tool_result = await self._mcp_client.call_tool(
                self._get_tool_name("confluence_get_page"),
                {
                    "page_id": page_id,
                    "format": "view",
                    "userPrompt": "User initiated a story creation workflow from a Confluence page link.",
                    "llmReasoning": "Need to extract the content of the provided Confluence page to fulfill the user's request.",
                },
            )

            if not tool_result.success:
                return StageResult(
                    success=False,
                    data=None,
                    errors=[f"Failed to retrieve page {page_id}: {tool_result.error}"],
                    warnings=[],
                    confidence=0.0,
                )

            page_data = tool_result.data
            if isinstance(page_data, str):
                try:
                    page_data = json.loads(page_data)
                except json.JSONDecodeError:
                    return StageResult(
                        success=False,
                        data=None,
                        errors=["Invalid response format from MCP server"],
                        warnings=[],
                        confidence=0.0,
                    )

            # Extract space_key from MCP response fields
            space_key = _safe_get(page_data, "space_key", "")
            if not space_key:
                space_data = _safe_get(page_data, "space", {})
                space_key = (
                    _safe_get(space_data, "key", "UNKNOWN")
                    if isinstance(space_data, dict)
                    else "UNKNOWN"
                )

            warnings: list[str] = []

            def _extract_html_content(p_data: Any) -> str:
                c = _safe_get(p_data, "content", "") or _safe_get(p_data, "body", "")
                if isinstance(c, dict):
                    if "view" in c and isinstance(c["view"], dict) and c["view"].get("value"):
                        return str(c["view"]["value"])
                    if (
                        "storage" in c
                        and isinstance(c["storage"], dict)
                        and c["storage"].get("value")
                    ):
                        return str(c["storage"]["value"])
                    if (
                        "export_view" in c
                        and isinstance(c["export_view"], dict)
                        and c["export_view"].get("value")
                    ):
                        return str(c["export_view"]["value"])
                    if (
                        "anonymous_export_view" in c
                        and isinstance(c["anonymous_export_view"], dict)
                        and c["anonymous_export_view"].get("value")
                    ):
                        return str(c["anonymous_export_view"]["value"])
                    for _, v in c.items():
                        if isinstance(v, dict) and v.get("value"):
                            return str(v["value"])
                    return str(c)
                return str(c) if c else ""

            content = _extract_html_content(page_data)
            if not content:
                warnings.append("Page has no content")

            page = ConfluencePage(
                page_id=page_id,
                title=_safe_get(page_data, "title", "Untitled"),
                content=content,
                space_key=space_key,
                url=_safe_get(page_data, "url", "")
                or (
                    f"{self._confluence_base_url}/pages/{page_id}"
                    if self._confluence_base_url
                    else ""
                ),
                retrieved_at=datetime.now(UTC),
                author=_safe_get(_safe_get(page_data, "author", {}), "displayName")
                if isinstance(_safe_get(page_data, "author"), dict)
                else _safe_get(page_data, "author"),
                version=_safe_get(_safe_get(page_data, "version", {}), "number")
                if isinstance(_safe_get(page_data, "version"), dict)
                else _safe_get(page_data, "version_number"),
                labels=_safe_get(page_data, "labels", []),
            )

            return StageResult(
                success=True,
                data=page,
                errors=[],
                warnings=warnings,
                confidence=1.0,
            )

        except MCPConnectionError as e:
            return StageResult(
                success=False,
                data=None,
                errors=[
                    _MCP_UNAVAILABLE_ERROR_TEMPLATE.format(self._mcp_client.server_url),
                    f"Details: {e.message}",
                ]
                + _MCP_UNAVAILABLE_CHECKS,
                warnings=[],
                confidence=0.0,
            )
        except Exception as e:
            return StageResult(
                success=False,
                data=None,
                errors=[f"Unexpected error reading page {page_id}: {str(e)}"],
                warnings=[],
                confidence=0.0,
            )

    async def get_children_by_id(self, page_id: str, space_key: str = "") -> StageResult:
        """Get all child pages of a Confluence page by its page_id via MCP using confluence_search.

        Returns a StageResult whose .data is a list of PageSummary objects.

        Args:
            page_id: Numeric Confluence page ID
            space_key: Optional space key to constrain the search

        Returns:
            StageResult with list[PageSummary] or error
        """
        if not self._mcp_client.is_connected:
            return StageResult(
                success=False,
                data=None,
                errors=_MCP_NOT_CONNECTED_ERROR,
                warnings=[],
                confidence=0.0,
            )

        try:
            # Construct CQL query
            cql = f"type=page AND (parent={page_id} OR ancestor={page_id})"
            if space_key:
                cql = f"space='{space_key}' AND " + cql

            tool_result = await self._mcp_client.call_tool(
                self._get_tool_name("confluence_search"),
                {
                    "cql": cql,
                    "limit": 50,
                    "userPrompt": "User initiated a story creation workflow that requires reading all children pages of a Confluence page.",
                    "llmReasoning": "Need to search for child pages to recursively process all documentation linked to the parent page.",
                },
            )

            if not tool_result.success:
                return StageResult(
                    success=False,
                    data=None,
                    errors=[
                        f"Failed to search for children of page {page_id}: {tool_result.error}"
                    ],
                    warnings=[],
                    confidence=0.0,
                )

            children_data = tool_result.data
            if isinstance(children_data, str):
                try:
                    children_data = json.loads(children_data)
                except json.JSONDecodeError:
                    return StageResult(
                        success=False,
                        data=None,
                        errors=["Invalid JSON from MCP server"],
                        warnings=[],
                        confidence=0.0,
                    )

            if isinstance(children_data, dict) and "results" in children_data:
                results_list = children_data["results"]
            else:
                results_list = children_data if isinstance(children_data, list) else []

            summaries = []
            for child in results_list:
                if not isinstance(child, dict):
                    continue
                child_id = str(child.get("id", child.get("page_id", "")))
                title = child.get("title", "Untitled")
                url = child.get("url", "") or (
                    f"{self._confluence_base_url}/pages/{child_id}"
                    if self._confluence_base_url and child_id
                    else ""
                )
                summaries.append(PageSummary(page_id=child_id, title=title, url=url))

            return StageResult(
                success=True,
                data=summaries,
                errors=[],
                warnings=[],
                confidence=1.0,
            )

        except MCPConnectionError as e:
            return StageResult(
                success=False,
                data=None,
                errors=[
                    _MCP_UNAVAILABLE_ERROR_TEMPLATE.format(self._mcp_client.server_url),
                    f"Details: {e.message}",
                ]
                + _MCP_UNAVAILABLE_CHECKS,
                warnings=[],
                confidence=0.0,
            )
        except Exception as e:
            return StageResult(
                success=False,
                data=None,
                errors=[f"Unexpected error getting children of page {page_id}: {str(e)}"],
                warnings=[],
                confidence=0.0,
            )

    # Keywords used to identify requirement pages (case-insensitive fuzzy match)
    _REQUIREMENT_KEYWORDS: tuple[str, ...] = (
        "requirement",
        "requirements",
        " fr ",
        "functional requirement",
        "spec",
        "specification",
    )

    @classmethod
    def _is_requirement_title(cls, title: str) -> bool:
        """Return True if *title* looks like a requirements page."""
        lower = title.lower()
        # Exact word-boundary check for short abbreviation "FR"
        if re.search(r"\bfr\b", lower):
            return True
        return any(kw in lower for kw in cls._REQUIREMENT_KEYWORDS)

    async def find_parent_pages(self, space_key: str) -> StageResult:
        """Find candidate requirement parent pages in *space_key* by title similarity.

        Searches via CQL for pages whose title contains requirement-related
        keywords and returns a list of :class:`PageSummary` objects (each with
        a populated ``url`` field) so that callers can present an actionable
        Confluence URL to the user.

        Previously this method returned plain title strings; it now returns
        ``PageSummary`` objects to avoid a second round-trip to resolve URLs.
        """
        if not self._mcp_client.is_connected:
            return StageResult(
                success=False,
                data=None,
                errors=_MCP_NOT_CONNECTED_ERROR,
                warnings=[],
                confidence=0.0,
            )

        # Build CQL covering the most common requirement-page title patterns.
        cql = (
            f"space = {space_key} AND type = page AND ("
            'title ~ "requirement" OR title ~ "requirements" OR title ~ "FR" '
            'OR title ~ "functional requirement" OR title ~ "spec")'
        )
        search_result = await self._mcp_client.call_tool(
            self._get_tool_name("confluence_search"),
            {
                "cql": cql,
                "limit": 10,
                "userPrompt": "Find the requirements page in the Confluence space.",
                "llmReasoning": "Searching for pages with requirement-related titles to suggest the best URL to the user.",
            },
        )

        if not search_result.success:
            return StageResult(
                success=False,
                data=None,
                errors=[search_result.error or "Unknown error"],
                warnings=[],
                confidence=0.0,
            )

        search_data = search_result.data
        if isinstance(search_data, str):
            try:
                search_data = json.loads(search_data)
            except json.JSONDecodeError:
                return StageResult(
                    success=False,
                    data=None,
                    errors=["Invalid JSON from MCP"],
                    warnings=[],
                    confidence=0.0,
                )

        results = search_data.get("results", []) if isinstance(search_data, dict) else search_data
        if not isinstance(results, list):
            results = []

        summaries: list[PageSummary] = []
        for page_data in results:
            if not isinstance(page_data, dict):
                continue
            title = page_data.get("title", "")
            if not title:
                continue
            # Only include pages whose title actually matches our keywords
            # (CQL `~` is substring so already filtered, but double-check)
            if not self._is_requirement_title(title):
                continue
            page_id = str(page_data.get("id", page_data.get("page_id", "")))
            # Prefer webui link embedded in response; fall back to constructing from base URL
            webui = ""
            links = page_data.get("_links", {})
            if isinstance(links, dict):
                webui = links.get("webui", "")
            if webui and self._confluence_base_url:
                url = f"{self._confluence_base_url}{webui}"
            elif page_data.get("url"):
                url = page_data["url"]
            elif self._confluence_base_url and page_id:
                url = f"{self._confluence_base_url}/pages/{page_id}"
            else:
                url = ""
            summaries.append(PageSummary(page_id=page_id, title=title, url=url))

        return StageResult(
            success=True,
            data=summaries,
            errors=[],
            warnings=[],
            confidence=1.0,
        )

    async def find_requirement_page_by_parent_id(self, parent_page_id: str) -> StageResult:
        """Search descendants of *parent_page_id* for a requirements page.

        Used as a fallback when no space key is available but we have a
        specific ``page_id`` from the Confluence base URL.  Returns a
        :class:`StageResult` whose ``data`` is the first matching
        :class:`PageSummary` (or ``None`` if nothing is found).
        """
        if not self._mcp_client.is_connected:
            return StageResult(
                success=False,
                data=None,
                errors=_MCP_NOT_CONNECTED_ERROR,
                warnings=[],
                confidence=0.0,
            )

        cql = (
            f"type = page AND ancestor IN ({parent_page_id}) AND ("
            'title ~ "requirement" OR title ~ "requirements" OR title ~ "FR" '
            'OR title ~ "functional requirement" OR title ~ "spec")'
        )
        search_result = await self._mcp_client.call_tool(
            self._get_tool_name("confluence_search"),
            {
                "cql": cql,
                "limit": 10,
                "userPrompt": "Find the requirements page under the given parent.",
                "llmReasoning": "Searching for requirement-related child pages to suggest to the user.",
            },
        )

        if not search_result.success:
            return StageResult(
                success=True,
                data=None,
                errors=[],
                warnings=[
                    search_result.error or "Requirement search failed; using base URL instead."
                ],
                confidence=0.0,
            )

        search_data = search_result.data
        if isinstance(search_data, str):
            try:
                search_data = json.loads(search_data)
            except json.JSONDecodeError:
                return StageResult(success=True, data=None, errors=[], warnings=[], confidence=0.0)

        results = search_data.get("results", []) if isinstance(search_data, dict) else search_data
        if not isinstance(results, list):
            results = []

        for page_data in results:
            if not isinstance(page_data, dict):
                continue
            title = page_data.get("title", "")
            if not self._is_requirement_title(title):
                continue
            page_id = str(page_data.get("id", page_data.get("page_id", "")))
            webui = ""
            links = page_data.get("_links", {})
            if isinstance(links, dict):
                webui = links.get("webui", "")
            if webui and self._confluence_base_url:
                url = f"{self._confluence_base_url}{webui}"
            elif page_data.get("url"):
                url = page_data["url"]
            elif self._confluence_base_url and page_id:
                url = f"{self._confluence_base_url}/pages/{page_id}"
            else:
                url = ""
            summary = PageSummary(page_id=page_id, title=title, url=url)
            return StageResult(success=True, data=summary, errors=[], warnings=[], confidence=1.0)

        return StageResult(success=True, data=None, errors=[], warnings=[], confidence=0.0)

    async def get_descendants_by_title(self, space_key: str, parent_title: str) -> StageResult:
        """Find the page by title and then retrieve all its descendants."""
        if not self._mcp_client.is_connected:
            return StageResult(
                success=False,
                data=None,
                errors=_MCP_NOT_CONNECTED_ERROR,
                warnings=[],
                confidence=0.0,
            )

        # 1. Search for the parent page by title exactly
        # CQL: space = SPACE AND type = page AND title = "parent_title"
        # We escape the title to be safe
        safe_title = parent_title.replace('"', '\\"')
        search_result = await self._mcp_client.call_tool(
            self._get_tool_name("confluence_search"),
            {
                "cql": f'space = {space_key} AND type = page AND title = "{safe_title}"',
                "limit": 10,
            },
        )
        if not search_result.success:
            return StageResult(
                success=False,
                data=None,
                errors=[search_result.error or "Unknown error"],
                warnings=[],
                confidence=0.0,
            )

        search_data = search_result.data
        if isinstance(search_data, str):
            search_data = json.loads(search_data)

        pages = search_data.get("results", []) if isinstance(search_data, dict) else search_data
        if not pages or not isinstance(pages, list):
            return StageResult(
                success=False,
                data=None,
                errors=[f"Could not find a page with title '{parent_title}'"],
                warnings=[],
                confidence=0.0,
            )

        parent_page = pages[0]
        parent_id = str(parent_page.get("id", ""))

        if not parent_id:
            return StageResult(
                success=False,
                data=None,
                errors=["Parent page has no ID"],
                warnings=[],
                confidence=0.0,
            )

        # 2. Search for descendants
        target_pages_dict = {parent_id: parent_page}
        desc_start = 0
        desc_has_more = True
        warnings = []

        while desc_has_more:
            desc_search = await self._mcp_client.call_tool(
                self._get_tool_name("confluence_search"),
                {
                    "cql": f"space = {space_key} AND type = page AND ancestor IN ({parent_id})",
                    "limit": DEFAULT_PAGE_LIMIT,
                    "start": desc_start,
                },
            )

            if not desc_search.success:
                warnings.append(f"Failed to fetch descendants: {desc_search.error}")
                break

            desc_data = desc_search.data
            if isinstance(desc_data, str):
                try:
                    desc_data = json.loads(desc_data)
                except json.JSONDecodeError:
                    warnings.append("Invalid descendant search response format")
                    break

            desc_pages = desc_data.get("results", []) if isinstance(desc_data, dict) else desc_data
            if not isinstance(desc_pages, list):
                desc_pages = []

            for p_data in desc_pages:
                if not isinstance(p_data, dict):
                    continue
                p_id = str(p_data.get("id", ""))
                if p_id:
                    target_pages_dict[p_id] = p_data

            desc_has_more = len(desc_pages) == DEFAULT_PAGE_LIMIT
            desc_start += len(desc_pages)

        # 3. Build PageSummary list
        summaries = []
        for page_id, page_data in target_pages_dict.items():
            page_url = (
                page_data.get("_links", {}).get("webui", "")
                if isinstance(page_data.get("_links"), dict)
                else ""
            )
            if page_url and self._confluence_base_url:
                page_url = f"{self._confluence_base_url}{page_url}"

            summary = PageSummary(
                page_id=page_id,
                title=page_data.get("title", "Untitled"),
                url=page_url,
                last_modified=None,
            )
            summaries.append(summary)

        return StageResult(
            success=True,
            data=summaries,
            errors=[],
            warnings=warnings if warnings else [],
            confidence=0.9 if summaries else 0.5,
        )

    async def read_multiple_pages(self, page_urls: list[str]) -> StageResult:
        """Read multiple pages with progress tracking.

        Args:
            page_urls: List of Confluence page URLs

        Returns:
            StageResult with list of ConfluencePage objects
        """
        if not page_urls:
            return StageResult(
                success=True,
                data=[],
                errors=[],
                warnings=["No URLs provided"],
                confidence=1.0,
            )

        if not self._mcp_client.is_connected:
            return StageResult(
                success=False,
                data=None,
                errors=_MCP_NOT_CONNECTED_ERROR,
                warnings=[],
                confidence=0.0,
            )

        # Use semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(self._max_concurrent_requests)

        async def _read_with_limit(url: str) -> StageResult:
            async with semaphore:
                return await self.read_page(url)

        # Gather all results with concurrency limiting
        results = await asyncio.gather(
            *[_read_with_limit(url) for url in page_urls], return_exceptions=True
        )

        pages = []
        errors = []
        warnings = []

        for url, result in zip(page_urls, results, strict=False):
            if isinstance(result, BaseException):
                errors.append(f"Exception reading {url}: {str(result)}")
                continue

            # At this point result is StageResult
            if result.success and result.data is not None:
                pages.append(result.data)
            else:
                errors.extend(result.errors)

            if result.warnings:
                warnings.extend([f"[{url}] {w}" for w in result.warnings])

        # Determine overall success - partial success counts as success with warnings
        success = len(pages) > 0
        confidence = len(pages) / len(page_urls) if page_urls else 0.0

        # Convert errors to warnings if we have partial success (per StageResult contract)
        if success and errors:
            warnings.extend([f"Error reading some pages: {e}" for e in errors])
            errors = []

        return StageResult(
            success=success,
            data=pages if pages else None,
            errors=errors if errors else [],
            warnings=warnings if warnings else [],
            confidence=confidence,
        )
