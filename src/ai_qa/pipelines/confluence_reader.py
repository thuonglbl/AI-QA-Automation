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
from urllib.parse import parse_qs, urlparse

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
        "confluence_get_children",  # Get child pages
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
        self._confluence_base_url = confluence_base_url
        self._max_concurrent_requests = max_concurrent_requests
        self._url_parser = ConfluenceURLParser()

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
                "confluence_get_page",
                {"page_id": page_id},
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
            content = _safe_get(page_data, "content", "")
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

    async def list_pages_in_space(self, space_key: str) -> StageResult:
        """List all pages in a Confluence space.

        Args:
            space_key: Confluence space key (e.g., "TEST")

        Returns:
            StageResult with list of page summaries
        """
        if not space_key:
            return StageResult(
                success=False,
                data=None,
                errors=["Space key is required"],
                warnings=[],
                confidence=0.0,
            )

        # Validate space_key format to prevent CQL injection
        # Space keys should be alphanumeric with optional hyphens/underscores
        if not re.match(r"^[A-Z0-9_-]+$", space_key.upper()):
            return StageResult(
                success=False,
                data=None,
                errors=[
                    f"Invalid space key format: {space_key}",
                    "Space keys should contain only letters, numbers, hyphens, and underscores.",
                ],
                warnings=[],
                confidence=0.0,
            )

        if not self._mcp_client.is_connected:
            return StageResult(
                success=False,
                data=None,
                errors=_MCP_NOT_CONNECTED_ERROR,
                warnings=[],
                confidence=0.0,
            )

        try:
            # Try to get space info first
            space_result = await self._mcp_client.call_tool(
                "confluence_get_space",
                {"space_key": space_key},
            )

            if not space_result.success:
                return StageResult(
                    success=False,
                    data=None,
                    errors=[f"Space not found or inaccessible: {space_key}"],
                    warnings=[],
                    confidence=0.0,
                )

            # Search for all pages in space with pagination
            all_pages: list[dict[str, Any]] = []
            start = 0
            has_more = True

            while has_more:
                search_result = await self._mcp_client.call_tool(
                    "confluence_search",
                    {
                        "cql": f"space = {space_key} AND type = page",
                        "limit": DEFAULT_PAGE_LIMIT,
                        "start": start,
                    },
                )

                if not search_result.success:
                    return StageResult(
                        success=False,
                        data=None,
                        errors=[f"Failed to search pages in space: {search_result.error}"],
                        warnings=[],
                        confidence=0.0,
                    )

                # Parse results
                search_data = search_result.data
                if isinstance(search_data, str):
                    try:
                        search_data = json.loads(search_data)
                    except json.JSONDecodeError:
                        return StageResult(
                            success=False,
                            data=None,
                            errors=["Invalid search response format from MCP server"],
                            warnings=[],
                            confidence=0.0,
                        )

                pages = (
                    search_data.get("results", []) if isinstance(search_data, dict) else search_data
                )
                if not isinstance(pages, list):
                    pages = []

                all_pages.extend(pages)

                # Check if there are more results
                total_size = (
                    search_data.get("size", 0) if isinstance(search_data, dict) else len(pages)
                )
                has_more = len(pages) == DEFAULT_PAGE_LIMIT and len(all_pages) < total_size
                start += len(pages)

            # Build PageSummary list
            summaries = []
            warnings = []

            for page_data in all_pages:
                if not isinstance(page_data, dict):
                    continue

                page_id = str(page_data.get("id", ""))
                if not page_id:
                    # Skip pages without IDs - they can't be properly referenced
                    warnings.append("Skipping page without ID in search results")
                    continue

                # Build URL
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
                    last_modified=None,  # Not always available in search results
                )
                summaries.append(summary)

            return StageResult(
                success=True,
                data=summaries,
                errors=[],
                warnings=warnings if warnings else [],
                confidence=0.9 if summaries else 0.5,  # Lower confidence if no results
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
                errors=[f"Unexpected error listing pages: {str(e)}"],
                warnings=[],
                confidence=0.0,
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
