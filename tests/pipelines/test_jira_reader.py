"""Tests for JiraReader pipeline stage and related capability helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_qa.exceptions import MCPConnectionError, MCPToolError  # noqa: F401 (used in pytest.raises)
from ai_qa.mcp.tools import ToolResult
from ai_qa.pipelines.jira_reader import JiraReader

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_mcp_client() -> MagicMock:
    client = MagicMock()
    client.is_connected = True
    client.server_url = "http://localhost:3000/sse"
    client.settings = MagicMock()
    client.settings.mcp_tool_prefix = ""
    client.call_tool = AsyncMock()
    client.list_tools = AsyncMock()
    client.check_required_tools = AsyncMock()
    return client


@pytest.fixture
def jira_reader(mock_mcp_client: MagicMock) -> JiraReader:
    return JiraReader(
        mcp_client=mock_mcp_client,
        jira_base_url="https://jira.company.com",
    )


_REALISTIC_PAYLOAD = {
    "key": "PROJ-123",
    "fields": {
        "summary": "Login fails for SSO users",
        "description": "Steps to reproduce: ...",
        "acceptance_criteria": "Given SSO is configured, user can log in",
        "status": {"name": "In Progress"},
        "labels": ["auth", "sso"],
        "project": {"key": "PROJ"},
        "issuetype": {"name": "Story"},
        "reporter": {"displayName": "Alice Smith"},
        "assignee": {"displayName": "Bob Jones"},
    },
}


# ---------------------------------------------------------------------------
# _parse_issue_ref tests
# ---------------------------------------------------------------------------


class TestParseIssueRef:
    def test_plain_key(self) -> None:
        assert JiraReader._parse_issue_ref("PROJ-123") == "PROJ-123"

    def test_cloud_url(self) -> None:
        url = "https://company.atlassian.net/browse/PROJ-123"
        assert JiraReader._parse_issue_ref(url) == "PROJ-123"

    def test_datacenter_url(self) -> None:
        url = "https://jira.company.com/browse/PROJ-123"
        assert JiraReader._parse_issue_ref(url) == "PROJ-123"

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            JiraReader._parse_issue_ref("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            JiraReader._parse_issue_ref("   ")

    def test_garbage_input_raises(self) -> None:
        with pytest.raises(ValueError, match="No Jira issue key found"):
            JiraReader._parse_issue_ref("https://example.com/not-a-jira-url")

    def test_lowercase_key_succeeds(self) -> None:
        assert JiraReader._parse_issue_ref("proj-123") == "PROJ-123"


# ---------------------------------------------------------------------------
# read_issue happy path
# ---------------------------------------------------------------------------


class TestReadIssueHappyPath:
    @pytest.mark.asyncio
    async def test_returns_jira_issue(
        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
    ) -> None:
        mock_mcp_client.call_tool.return_value = ToolResult.from_data(_REALISTIC_PAYLOAD)

        result = await jira_reader.read_issue("PROJ-123")

        assert result.success is True
        assert result.data is not None
        issue = result.data
        assert issue.issue_key == "PROJ-123"
        assert issue.summary == "Login fails for SSO users"
        assert issue.description == "Steps to reproduce: ..."
        assert issue.acceptance_criteria == "Given SSO is configured, user can log in"
        assert issue.status == "In Progress"
        assert issue.labels == ["auth", "sso"]
        assert issue.project_key == "PROJ"
        assert issue.issue_type == "Story"
        assert issue.reporter == "Alice Smith"
        assert issue.assignee == "Bob Jones"
        assert "PROJ-123" in issue.url

    @pytest.mark.asyncio
    async def test_url_contains_browse(
        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
    ) -> None:
        mock_mcp_client.call_tool.return_value = ToolResult.from_data(_REALISTIC_PAYLOAD)
        result = await jira_reader.read_issue("PROJ-123")
        assert result.success is True
        assert result.data is not None
        assert "/browse/PROJ-123" in result.data.url

    @pytest.mark.asyncio
    async def test_accepts_browse_url(
        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
    ) -> None:
        mock_mcp_client.call_tool.return_value = ToolResult.from_data(_REALISTIC_PAYLOAD)
        result = await jira_reader.read_issue("https://jira.company.com/browse/PROJ-123")
        assert result.success is True
        assert result.data is not None
        assert result.data.issue_key == "PROJ-123"


# ---------------------------------------------------------------------------
# read_issue request payload contract (guards the MCP parameter name)
# ---------------------------------------------------------------------------


class TestReadIssueRequestPayload:
    """Pin the identifier key the live MCP ``jira_get_issue`` tool requires.

    Verified against the live MCP server (2026-06-17): the tool requires the
    camelCase ``issueKey`` parameter. Both snake_case ``issue_key`` and the
    Atlassian-style ``issueIdOrKey`` are rejected by the server
    ("Required: issueKey"). These tests fail loudly if anyone reintroduces a
    wrong key in the request payload.
    """

    @pytest.mark.asyncio
    async def test_call_tool_uses_camelcase_issue_key(
        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
    ) -> None:
        mock_mcp_client.call_tool.return_value = ToolResult.from_data(_REALISTIC_PAYLOAD)

        await jira_reader.read_issue("PROJ-123")

        mock_mcp_client.call_tool.assert_called_once()
        tool_name, payload = mock_mcp_client.call_tool.call_args.args
        assert tool_name == "jira_get_issue"
        # The correct camelCase key carries the parsed issue key value...
        assert payload["issueKey"] == "PROJ-123"
        # ...and the server-rejected variants must never be sent.
        assert "issue_key" not in payload
        assert "issueIdOrKey" not in payload

    @pytest.mark.asyncio
    async def test_call_tool_issue_key_is_parsed_from_url(
        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
    ) -> None:
        mock_mcp_client.call_tool.return_value = ToolResult.from_data(_REALISTIC_PAYLOAD)

        await jira_reader.read_issue("https://jira.company.com/browse/PROJ-123")

        _, payload = mock_mcp_client.call_tool.call_args.args
        assert payload["issueKey"] == "PROJ-123"
        assert "issue_key" not in payload
        assert "issueIdOrKey" not in payload

    @pytest.mark.asyncio
    async def test_call_tool_uses_prefixed_tool_name(self, mock_mcp_client: MagicMock) -> None:
        mock_mcp_client.settings.mcp_tool_prefix = "corp_"
        reader = JiraReader(mock_mcp_client, jira_base_url="https://jira.company.com")
        mock_mcp_client.call_tool.return_value = ToolResult.from_data(_REALISTIC_PAYLOAD)

        await reader.read_issue("PROJ-123")

        tool_name, payload = mock_mcp_client.call_tool.call_args.args
        assert tool_name == "corp_jira_get_issue"
        assert payload["issueKey"] == "PROJ-123"
        assert "issue_key" not in payload
        assert "issueIdOrKey" not in payload


# ---------------------------------------------------------------------------
# read_issue error paths
# ---------------------------------------------------------------------------


class TestReadIssueErrors:
    @pytest.mark.asyncio
    async def test_mcp_tool_error_returns_failure(
        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
    ) -> None:
        mock_mcp_client.call_tool.side_effect = MCPToolError("tool not found")
        result = await jira_reader.read_issue("PROJ-123")
        assert result.success is False
        assert result.data is None
        assert result.errors
        assert "tool not found" in result.errors[0]

    @pytest.mark.asyncio
    async def test_unsuccessful_tool_result_returns_failure(
        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
    ) -> None:
        mock_mcp_client.call_tool.return_value = ToolResult.from_error("issue not found")
        result = await jira_reader.read_issue("PROJ-123")
        assert result.success is False
        assert result.data is None
        assert result.errors

    @pytest.mark.asyncio
    async def test_invalid_issue_ref_returns_failure(
        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
    ) -> None:
        result = await jira_reader.read_issue("not-a-jira-key")
        assert result.success is False
        assert result.data is None
        mock_mcp_client.call_tool.assert_not_called()


# ---------------------------------------------------------------------------
# check_tool_availability tests
# ---------------------------------------------------------------------------


class TestCheckToolAvailability:
    @pytest.mark.asyncio
    async def test_returns_missing_tool(
        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
    ) -> None:
        mock_mcp_client.check_required_tools.return_value = ["jira_search_issues"]
        missing = await jira_reader.check_tool_availability()
        assert missing == ["jira_search_issues"]

    @pytest.mark.asyncio
    async def test_returns_empty_when_all_present(
        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
    ) -> None:
        mock_mcp_client.check_required_tools.return_value = []
        missing = await jira_reader.check_tool_availability()
        assert missing == []

    @pytest.mark.asyncio
    async def test_propagates_mcp_connection_error(
        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
    ) -> None:
        mock_mcp_client.check_required_tools.side_effect = MCPConnectionError("cannot reach server")
        with pytest.raises(MCPConnectionError):
            await jira_reader.check_tool_availability()

    @pytest.mark.asyncio
    async def test_passes_prefixed_names(self, mock_mcp_client: MagicMock) -> None:
        mock_mcp_client.settings.mcp_tool_prefix = "myprefix_"
        reader = JiraReader(mock_mcp_client, jira_base_url="https://jira.company.com")
        mock_mcp_client.check_required_tools.return_value = []
        await reader.check_tool_availability()
        called_with = mock_mcp_client.check_required_tools.call_args[0][0]
        assert all(name.startswith("myprefix_") for name in called_with)


# ---------------------------------------------------------------------------
# ConfluenceReader.check_tool_availability delegation
# ---------------------------------------------------------------------------


class TestConfluenceReaderCheckToolAvailability:
    @pytest.mark.asyncio
    async def test_delegates_to_check_required_tools(self, mock_mcp_client: MagicMock) -> None:
        from ai_qa.pipelines.confluence_reader import ConfluenceReader

        mock_mcp_client.check_required_tools.return_value = []
        reader = ConfluenceReader(mcp_client=mock_mcp_client)
        await reader.check_tool_availability()

        mock_mcp_client.check_required_tools.assert_called_once()
        called_tools: list[str] = mock_mcp_client.check_required_tools.call_args[0][0]
        assert len(called_tools) == len(ConfluenceReader.CONFLUENCE_TOOLS)

    @pytest.mark.asyncio
    async def test_returns_missing_confluence_tools(self, mock_mcp_client: MagicMock) -> None:
        from ai_qa.pipelines.confluence_reader import ConfluenceReader

        mock_mcp_client.check_required_tools.return_value = ["confluence_get_page"]
        reader = ConfluenceReader(mcp_client=mock_mcp_client)
        missing = await reader.check_tool_availability()
        assert missing == ["confluence_get_page"]
