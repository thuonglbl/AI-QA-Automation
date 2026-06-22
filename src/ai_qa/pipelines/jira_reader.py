"""Jira Reader Pipeline Stage.

This module provides the JiraReader pipeline stage for retrieving
issue content from Jira via MCP server.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from ai_qa.exceptions import MCPError
from ai_qa.mcp.client import MCPClient
from ai_qa.models import StageResult
from ai_qa.pipelines.models import JiraIssue

_ISSUE_KEY_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_]+-\d+)\b")


class JiraReader:
    """Pipeline stage for reading Jira issues via MCP.

    Retrieves Jira issue content through the MCP server and returns
    structured JiraIssue data for downstream processing.

    Example:
        >>> reader = JiraReader(mcp_client, jira_base_url="https://jira.company.com")
        >>> result = await reader.read_issue("PROJ-123")
        >>> if result.success:
        ...     issue = result.data
        ...     print(issue.summary)
    """

    # Only require the tool the reader actually invokes. jira_search_issues and
    # jira_get_project were never called by any method, yet requiring them made
    # check_tool_availability falsely report tools missing (same class of bug as
    # CONFLUENCE_TOOLS over-requiring get_page_by_title/get_space).
    JIRA_TOOLS: list[str] = [
        "jira_get_issue",
    ]

    def __init__(
        self,
        mcp_client: MCPClient,
        jira_base_url: str | None = None,
        max_concurrent_requests: int = 10,
    ) -> None:
        """Initialize Jira reader.

        Args:
            mcp_client: Configured MCPClient instance
            jira_base_url: Base URL for the Jira instance
            max_concurrent_requests: Maximum concurrent requests

        Raises:
            ValueError: If mcp_client is None
        """
        if mcp_client is None:
            raise ValueError("MCP client is required")
        self._mcp_client = mcp_client
        self._jira_base_url = (jira_base_url or "").rstrip("/")
        settings = getattr(mcp_client, "settings", getattr(mcp_client, "_settings", None))
        self._tool_prefix = getattr(settings, "mcp_tool_prefix", "") if settings else ""
        self._max_concurrent_requests = max_concurrent_requests

    def _get_tool_name(self, base_name: str) -> str:
        """Get the full tool name including any configured prefix."""
        return f"{self._tool_prefix}{base_name}"

    @classmethod
    def _parse_issue_ref(cls, ref: str) -> str:
        """Extract Jira issue key from a URL or bare key string.

        Args:
            ref: Issue key (e.g. "PROJ-123") or Jira browse URL

        Returns:
            Extracted issue key

        Raises:
            ValueError: If ref is empty or contains no valid issue key
        """
        stripped = ref.strip()
        if not stripped:
            raise ValueError("Issue reference must not be empty")
        match = _ISSUE_KEY_RE.search(stripped)
        if not match:
            raise ValueError(f"No Jira issue key found in: {stripped!r}")
        return match.group(1).upper()

    def _map_issue_data(self, raw: Any, issue_key: str) -> JiraIssue:
        """Map raw MCP tool response to JiraIssue model.

        Handles both Jira Cloud (flat) and Data Center (fields-nested) response shapes.
        """
        if not isinstance(raw, dict):
            raw = {}
        # Data Center wraps everything under "fields"; Cloud may be flat
        fields: Any = raw.get("fields", raw)
        if not isinstance(fields, dict):
            fields = raw

        resolved_key: str = str(raw.get("key", "") or issue_key)

        def _get_str(d: Any, key: str) -> str | None:
            val = d.get(key) if isinstance(d, dict) else None
            return str(val) if val is not None else None

        def _get_name(d: Any, key: str) -> str | None:
            obj = d.get(key) if isinstance(d, dict) else None
            if isinstance(obj, dict):
                return str(obj.get("displayName") or obj.get("name") or "")
            return None

        def _get_nested_name(d: Any, key: str) -> str | None:
            obj = d.get(key) if isinstance(d, dict) else None
            if isinstance(obj, dict):
                return str(obj.get("name")) if obj.get("name") else None
            return None

        status_val = fields.get("status") if isinstance(fields, dict) else None
        status: str | None
        if isinstance(status_val, dict):
            status = str(status_val.get("name") or "")
        else:
            status = str(status_val) if status_val is not None else None

        project_val = fields.get("project") if isinstance(fields, dict) else None
        project_key: str
        if isinstance(project_val, dict):
            project_key = str(project_val.get("key") or "")
        elif project_val is not None:
            project_key = str(project_val)
        else:
            project_key = ""

        labels_val = fields.get("labels") if isinstance(fields, dict) else None
        labels: list[str] = list(labels_val) if isinstance(labels_val, (list, tuple)) else []

        url = f"{self._jira_base_url}/browse/{resolved_key}" if self._jira_base_url else ""

        return JiraIssue(
            issue_key=resolved_key,
            summary=str(fields.get("summary", "") if isinstance(fields, dict) else ""),
            description=_get_str(fields, "description"),
            acceptance_criteria=_get_str(fields, "acceptance_criteria"),
            status=status,
            labels=labels,
            project_key=project_key,
            url=url,
            retrieved_at=datetime.now(tz=UTC),
            issue_type=_get_nested_name(fields, "issuetype"),
            reporter=_get_name(fields, "reporter"),
            assignee=_get_name(fields, "assignee"),
        )

    async def read_issue(self, issue_ref: str) -> StageResult:
        """Read a single Jira issue.

        Args:
            issue_ref: Issue key (e.g. "PROJ-123") or Jira browse URL

        Returns:
            StageResult with JiraIssue data on success, or error details on failure.
            Never re-raises MCP errors — soft failures are returned as StageResult.
        """
        try:
            issue_key = self._parse_issue_ref(issue_ref)
        except ValueError as e:
            return StageResult(
                success=False,
                data=None,
                errors=[str(e)],
                warnings=[],
                confidence=0.0,
            )

        try:
            tool_result = await self._mcp_client.call_tool(
                self._get_tool_name("jira_get_issue"),
                {
                    # Verified against the live MCP server (2026-06-17): the
                    # jira_get_issue tool requires the camelCase "issueKey" param.
                    # Both snake_case "issue_key" and the Atlassian-style
                    # "issueIdOrKey" are rejected by the server ("Required: issueKey").
                    # Guarded by TestReadIssueRequestPayload in
                    # tests/pipelines/test_jira_reader.py.
                    "issueKey": issue_key,
                    "userPrompt": f"Extract issue {issue_key}",
                    "llmReasoning": "Retrieving Jira requirement for analysis.",
                },
            )
        except MCPError as e:
            return StageResult(
                success=False,
                data=None,
                errors=[str(e)],
                warnings=[],
                confidence=0.0,
            )

        if not tool_result.success:
            return StageResult(
                success=False,
                data=None,
                errors=[tool_result.error or "Failed to retrieve Jira issue"],
                warnings=[],
                confidence=0.0,
            )

        issue = self._map_issue_data(tool_result.data, issue_key)

        return StageResult(
            success=True,
            data=issue,
            errors=[],
            warnings=[],
            confidence=1.0,
        )

    async def check_tool_availability(self) -> list[str]:
        """Return names of required Jira tools absent from the MCP server.

        Returns:
            List of missing tool names; empty list means all tools are present.

        Raises:
            MCPConnectionError: If list_tools() cannot reach the MCP server.
            MCPAuthenticationError: If authentication with the MCP server fails.
        """
        prefixed = [self._get_tool_name(t) for t in self.JIRA_TOOLS]
        return await self._mcp_client.check_required_tools(prefixed)
