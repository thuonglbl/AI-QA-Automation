You are an Acceptance Auditor. Review this diff against the spec and context docs. Check for: violations of acceptance criteria, deviations from spec intent, missing implementation of specified behavior, contradictions between spec constraints and actual code.

STORY SPEC:
## Acceptance Criteria
### AC1 — MCP client resolves the current user's encrypted MCP key at execution time
### AC2 — Client discovers available Confluence and Jira tools on connect
### AC3 — Retry logic covers MCP connection and transient failures

## Tasks Required:
- Task 1: JiraIssue model in models.py + export
- Task 2: JiraReader pipeline stage with JIRA_TOOLS, _parse_issue_ref(), read_issue(), check_tool_availability()
- Task 3: MCPClient.check_required_tools() + ConfluenceReader.check_tool_availability()
- Task 4: Unit tests (25 total)
- Task 5: Full gate (ruff, mypy, pytest, alembic)

## Key Spec Constraints:
- Do NOT rebuild MCPClient, ConfluenceReader, or secret resolution
- JiraReader follows same constructor shape as ConfluenceReader
- read_issue() must NOT re-raise MCP errors — returns StageResult(success=False)
- check_tool_availability() MAY raise MCPConnectionError/MCPAuthenticationError
- Never include raw exception messages or auth tokens in StageResult.error
- No new retry layer in JiraReader (MCPClient handles retry)
- JiraReader uses _get_tool_name() for prefix support
- Bob agent intake gate changes were described as part of story 11-2, but are included in the diff

Output findings as a Markdown list. Each finding: one-line title, which AC/constraint it violates, and evidence from the diff. If you find no violations, state that all ACs are satisfied with brief justification per AC.

Here is the diff to review:
```diff
﻿diff --git a/src/ai_qa/agents/bob.py b/src/ai_qa/agents/bob.py
index 3b55c23..c3cd2b7 100644
--- a/src/ai_qa/agents/bob.py
+++ b/src/ai_qa/agents/bob.py
@@ -13,7 +13,7 @@ from ai_qa.pipelines.confluence_reader import ConfluenceReader, ConfluenceURLPar
 from ai_qa.pipelines.models import ConfluencePage
 from ai_qa.pipelines.requirement_formatter import RequirementFormatter
 from ai_qa.secrets import SECRET_TYPE_MCP
-from ai_qa.secrets.service import get_user_secret
+from ai_qa.secrets.service import get_secret_status, get_user_secret
 
 logger = logging.getLogger(__name__)
 
@@ -37,8 +37,140 @@ class BobAgent(BaseAgent):
         self.output_files_saved = 0
         self._space_key: str | None = None
         self._page_id: str | None = None
+        self._jira_ref: str | None = None
         self.phase = "init"
 
+    def _load_project(self) -> Any:
+        """Load Project from DB using project context. Returns None if unavailable."""
+        if not self.project_context or not self.project_context.artifact_service:
+            return None
+        db = self.project_context.artifact_service.db
+        from ai_qa.db.models import Project
+
+        return db.get(Project, self.project_context.project_id)
+
+    def _check_preconditions(self) -> list[str]:
+        """Return list of blocking recovery messages; empty list means all good.
+
+        Checks (in order): project/thread context present, Alice provider config
+        ready, MCP credential configured. Performs DB reads only ΓÇö no MCP, no decryption.
+        """
+        ctx = self.project_context
+        if not ctx or not ctx.project_id or not ctx.user_id or not ctx.thread_id:
+            return ["Start Bob from inside an active project thread."]
+
+        db = ctx.artifact_service.db if ctx.artifact_service else None
+        if db is None:
+            return ["The backend storage service is unavailable ΓÇö contact support."]
+
+        reasons: list[str] = []
+
+        from ai_qa.threads.models import Thread
+
+        thread = db.get(Thread, ctx.thread_id)
+        bob_cfg = (thread.agent_configs or {}).get("bob") if thread else None
+        bob_model = (
+            (bob_cfg.get("model") or bob_cfg.get("model_name"))
+            if isinstance(bob_cfg, dict)
+            else None
+        )
+        if not thread or not thread.provider_name or not bob_model:
+            reasons.append(
+                "Complete provider and model setup with Alice before starting Bob."
+            )
+
+        if not get_secret_status(db, ctx.user_id, SECRET_TYPE_MCP).configured:
+            reasons.append("Add your MCP key in provider configuration, then retry.")
+
+        return reasons
+
+    @staticmethod
+    def _validate_confluence_url(url: str, confluence_base_url: str | None) -> str | None:
+        """Returns None when the URL is accepted; otherwise a correction string.
+
+        Rules (in order): blank ΓåÆ required; invalid format ΓåÆ format hint; wrong host
+        vs configured base ΓåÆ host-mismatch; no page-id or space-key ΓåÆ identifier hint.
+        """
+        from urllib.parse import urlparse
+
+        url = url.strip()
+        if not url:
+            return "A Confluence page URL is required to start extraction."
+
+        if not ConfluenceURLParser.is_valid_confluence_url(url):
+            return (
+                "The URL does not appear to be a valid Confluence page URL. "
+                "Expected formats:\n"
+                "  - https://company.atlassian.net/wiki/spaces/SPACE/pages/PAGE_ID\n"
+                "  - https://confluence.company.com/display/SPACE/Page+Title\n"
+                "  - https://confluence.company.com/pages/viewpage.action?pageId=PAGE_ID"
+            )
+
+        if isinstance(confluence_base_url, str) and confluence_base_url:
+            configured_host = (urlparse(confluence_base_url).netloc or "").lower()
+            submitted_host = (urlparse(url).netloc or "").lower()
+            if configured_host and submitted_host != configured_host:
+                return (
+                    f"This URL is not part of the project's configured Confluence "
+                    f"instance ({configured_host})."
+                )
+
+        page_id = ConfluenceURLParser.extract_page_id(url)
+        space_key = ConfluenceURLParser.extract_space_key(url)
+        if not page_id and not space_key:
+            return (
+                "Could not find a page ID or space key in the URL ΓÇö "
+                "point to a specific Confluence page."
+            )
+
+        return None
+
+    @staticmethod
+    def _validate_jira_ref(jira_ref: str | None, jira_base_url: str | None) -> str | None:
+        """Returns None when Jira ref is valid or Jira is disabled; otherwise a correction.
+
+        Jira is optional ΓÇö a missing ref when Jira is enabled is accepted. Never blocks
+        Confluence extraction.
+        """
+        import re
+        from urllib.parse import urlparse
+
+        if not jira_base_url:
+            return None
+
+        if not jira_ref or not jira_ref.strip():
+            return None
+
+        jira_ref = jira_ref.strip()
+
+        if re.match(r"^[A-Z][A-Z0-9_]+-\d+$", jira_ref):
+            return None
+
+        parsed = urlparse(jira_ref)
+        if parsed.scheme in ("http", "https") and parsed.netloc:
+            configured_host = (urlparse(jira_base_url).netloc or "").lower()
+            submitted_host = (parsed.netloc or "").lower()
+            if submitted_host == configured_host:
+                return None
+            return (
+                f"The Jira URL does not match the project's configured Jira instance "
+                f"({configured_host})."
+            )
+
+        return (
+            "The Jira reference must be a ticket key (e.g. PROJ-123) or a URL from "
+            "the project's configured Jira instance."
+        )
+
+    def _format_blocked_message(self, reasons: list[str]) -> str:
+        """Format precondition failure reasons into a UX-DR12 blocking message."""
+        bullets = "\n".join(f"  - {r}" for r in reasons)
+        return (
+            "**What happened:** Bob cannot start requirements extraction.\n\n"
+            "**Why:** One or more required conditions are not met.\n\n"
+            f"**What to do:**\n{bullets}"
+        )
+
     def _resolve_mcp_pat(self) -> str:
         """Resolve MCP PAT from the thread owner's encrypted secrets.
 
@@ -82,6 +214,30 @@ class BobAgent(BaseAgent):
 
     async def handle_start(self, input_data: dict[str, Any]) -> None:
         """Override to parse multiple pages immediately."""
+        # --- 11.2 intake gate ΓÇö runs before any MCP/processing ---
+        blockers = self._check_preconditions()
+        if blockers:
+            await self.send_message(self._format_blocked_message(blockers), message_type="error")
+            return
+
+        project = self._load_project()
+        confluence_url = (input_data.get("confluence_url") or "").strip()
+        url_err = self._validate_confluence_url(
+            confluence_url, project.confluence_base_url if project else None
+        )
+        if url_err:
+            await self.send_message(url_err, message_type="error")
+            return
+
+        jira_err = self._validate_jira_ref(
+            input_data.get("jira_url"), project.jira_base_url if project else None
+        )
+        if jira_err:
+            await self.send_message(jira_err, message_type="error")
+            return
+        self._jira_ref = (input_data.get("jira_url") or "").strip() or None
+
+        # --- existing extraction flow (UNCHANGED) ---
         self.phase = "confirm_parent"
         await self.transition_to(AgentState.PROCESSING)
 
diff --git a/src/ai_qa/mcp/client.py b/src/ai_qa/mcp/client.py
index ba075f9..52d0c75 100644
--- a/src/ai_qa/mcp/client.py
+++ b/src/ai_qa/mcp/client.py
@@ -260,6 +260,24 @@ class MCPClient:
                 raise MCPToolError(f"Tool '{name}' not found on server") from e
             raise
 
+    async def check_required_tools(self, required_tools: list[str]) -> list[str]:
+        """Return names from required_tools that are absent on the MCP server.
+
+        Args:
+            required_tools: Tool names to check for (use prefixed names when applicable).
+
+        Returns:
+            List of missing tool names; empty list means all required tools are present.
+
+        Raises:
+            MCPConnectionError: If list_tools() fails due to connectivity.
+            MCPAuthenticationError: If authentication fails.
+        """
+        if not required_tools:
+            return []
+        available = {t.name for t in await self.list_tools()}
+        return [name for name in required_tools if name not in available]
+
     async def discover_capabilities(self) -> ServerCapabilities:
         """Discover server capabilities.
 
diff --git a/src/ai_qa/pipelines/__init__.py b/src/ai_qa/pipelines/__init__.py
index 93c9b41..01cbe00 100644
--- a/src/ai_qa/pipelines/__init__.py
+++ b/src/ai_qa/pipelines/__init__.py
@@ -7,7 +7,13 @@ the AI QA workflow. Each stage follows the StageResult contract.
 from ai_qa.models import TestCase, TestCaseStep
 from ai_qa.pipelines.confluence_reader import ConfluenceReader
 from ai_qa.pipelines.content_parser import ContentParser
-from ai_qa.pipelines.models import ConfluencePage, OutputMetadata, PageSummary, ParsedContent
+from ai_qa.pipelines.models import (
+    ConfluencePage,
+    JiraIssue,
+    OutputMetadata,
+    PageSummary,
+    ParsedContent,
+)
 from ai_qa.pipelines.output_writer import OutputWriter
 from ai_qa.pipelines.test_case_extractor import TestCaseExtractor
 from ai_qa.pipelines.vision_locator import LocatorResult, SelectorInfo, VisionLocator
@@ -15,6 +21,7 @@ from ai_qa.pipelines.vision_locator import LocatorResult, SelectorInfo, VisionLo
 __all__ = [
     "ConfluenceReader",
     "ConfluencePage",
+    "JiraIssue",
     "PageSummary",
     "ContentParser",
     "ParsedContent",
diff --git a/src/ai_qa/pipelines/confluence_reader.py b/src/ai_qa/pipelines/confluence_reader.py
index 962cb18..d6a079a 100644
--- a/src/ai_qa/pipelines/confluence_reader.py
+++ b/src/ai_qa/pipelines/confluence_reader.py
@@ -280,6 +280,19 @@ class ConfluenceReader:
         """Get the full tool name including any configured prefix."""
         return f"{self._tool_prefix}{base_name}"
 
+    async def check_tool_availability(self) -> list[str]:
+        """Return names of required Confluence tools absent from the MCP server.
+
+        Returns:
+            List of missing tool names; empty list means all tools are present.
+
+        Raises:
+            MCPConnectionError: If list_tools() cannot reach the MCP server.
+            MCPAuthenticationError: If authentication with the MCP server fails.
+        """
+        prefixed = [self._get_tool_name(t) for t in self.CONFLUENCE_TOOLS]
+        return await self._mcp_client.check_required_tools(prefixed)
+
     async def read_page(self, page_url: str) -> StageResult:
         """Read a single Confluence page.
 
diff --git a/src/ai_qa/pipelines/jira_reader.py b/src/ai_qa/pipelines/jira_reader.py
new file mode 100644
index 0000000..d816f19
--- /dev/null
+++ b/src/ai_qa/pipelines/jira_reader.py
@@ -0,0 +1,229 @@
+"""Jira Reader Pipeline Stage.
+
+This module provides the JiraReader pipeline stage for retrieving
+issue content from Jira via MCP server.
+"""
+
+from __future__ import annotations
+
+import re
+from datetime import UTC, datetime
+from typing import Any
+
+from ai_qa.config import AppSettings
+from ai_qa.exceptions import MCPToolError
+from ai_qa.mcp.client import MCPClient
+from ai_qa.models import StageResult
+from ai_qa.pipelines.models import JiraIssue
+
+_ISSUE_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9_]+-\d+)\b")
+
+
+class JiraReader:
+    """Pipeline stage for reading Jira issues via MCP.
+
+    Retrieves Jira issue content through the MCP server and returns
+    structured JiraIssue data for downstream processing.
+
+    Example:
+        >>> reader = JiraReader(mcp_client, jira_base_url="https://jira.company.com")
+        >>> result = await reader.read_issue("PROJ-123")
+        >>> if result.success:
+        ...     issue = result.data
+        ...     print(issue.summary)
+    """
+
+    JIRA_TOOLS: list[str] = [
+        "jira_get_issue",
+        "jira_search_issues",
+        "jira_get_project",
+    ]
+
+    def __init__(
+        self,
+        mcp_client: MCPClient,
+        jira_base_url: str | None = None,
+        settings: AppSettings | None = None,
+    ) -> None:
+        """Initialize Jira reader.
+
+        Args:
+            mcp_client: Configured MCPClient instance
+            jira_base_url: Base URL for the Jira instance
+            settings: Optional AppSettings (uses mcp_tool_prefix if provided)
+
+        Raises:
+            ValueError: If mcp_client is None
+        """
+        if mcp_client is None:
+            raise ValueError("MCP client is required")
+        self._mcp_client = mcp_client
+        self._jira_base_url = (jira_base_url or "").rstrip("/")
+        _settings = settings or (
+            mcp_client._settings if hasattr(mcp_client, "_settings") else None
+        )
+        self._tool_prefix = (
+            getattr(_settings, "mcp_tool_prefix", "") if _settings is not None else ""
+        )
+
+    def _get_tool_name(self, base_name: str) -> str:
+        """Get the full tool name including any configured prefix."""
+        return f"{self._tool_prefix}{base_name}"
+
+    @classmethod
+    def _parse_issue_ref(cls, ref: str) -> str:
+        """Extract Jira issue key from a URL or bare key string.
+
+        Args:
+            ref: Issue key (e.g. "PROJ-123") or Jira browse URL
+
+        Returns:
+            Extracted issue key
+
+        Raises:
+            ValueError: If ref is empty or contains no valid issue key
+        """
+        stripped = ref.strip()
+        if not stripped:
+            raise ValueError("Issue reference must not be empty")
+        match = _ISSUE_KEY_RE.search(stripped)
+        if not match:
+            raise ValueError(f"No Jira issue key found in: {stripped!r}")
+        return match.group(1)
+
+    def _map_issue_data(self, raw: Any, issue_key: str) -> JiraIssue:
+        """Map raw MCP tool response to JiraIssue model.
+
+        Handles both Jira Cloud (flat) and Data Center (fields-nested) response shapes.
+        """
+        if not isinstance(raw, dict):
+            raw = {}
+        # Data Center wraps everything under "fields"; Cloud may be flat
+        fields: Any = raw.get("fields", raw)
+        if not isinstance(fields, dict):
+            fields = raw
+
+        resolved_key: str = str(raw.get("key", "") or issue_key)
+
+        def _get_str(d: Any, key: str) -> str | None:
+            val = d.get(key) if isinstance(d, dict) else None
+            return str(val) if val is not None else None
+
+        def _get_name(d: Any, key: str) -> str | None:
+            obj = d.get(key) if isinstance(d, dict) else None
+            if isinstance(obj, dict):
+                return str(obj.get("displayName") or obj.get("name") or "")
+            return None
+
+        def _get_nested_name(d: Any, key: str) -> str | None:
+            obj = d.get(key) if isinstance(d, dict) else None
+            if isinstance(obj, dict):
+                return str(obj.get("name") or "")
+            return None
+
+        status_val = fields.get("status") if isinstance(fields, dict) else None
+        status: str | None
+        if isinstance(status_val, dict):
+            status = str(status_val.get("name") or "")
+        else:
+            status = str(status_val) if status_val is not None else None
+
+        project_val = fields.get("project") if isinstance(fields, dict) else None
+        project_key: str
+        if isinstance(project_val, dict):
+            project_key = str(project_val.get("key") or "")
+        elif project_val is not None:
+            project_key = str(project_val)
+        else:
+            project_key = ""
+
+        labels_val = fields.get("labels") if isinstance(fields, dict) else None
+        labels: list[str] = list(labels_val) if isinstance(labels_val, list) else []
+
+        url = f"{self._jira_base_url}/browse/{resolved_key}" if self._jira_base_url else ""
+
+        return JiraIssue(
+            issue_key=resolved_key,
+            summary=str(fields.get("summary", "") if isinstance(fields, dict) else ""),
+            description=_get_str(fields, "description"),
+            acceptance_criteria=_get_str(fields, "acceptance_criteria"),
+            status=status,
+            labels=labels,
+            project_key=project_key,
+            url=url,
+            retrieved_at=datetime.now(tz=UTC),
+            issue_type=_get_nested_name(fields, "issuetype"),
+            reporter=_get_name(fields, "reporter"),
+            assignee=_get_name(fields, "assignee"),
+        )
+
+    async def read_issue(self, issue_ref: str) -> StageResult:
+        """Read a single Jira issue.
+
+        Args:
+            issue_ref: Issue key (e.g. "PROJ-123") or Jira browse URL
+
+        Returns:
+            StageResult with JiraIssue data on success, or error details on failure.
+            Never re-raises MCP errors ΓÇö soft failures are returned as StageResult.
+        """
+        try:
+            issue_key = self._parse_issue_ref(issue_ref)
+        except ValueError as e:
+            return StageResult(
+                success=False,
+                data=None,
+                errors=[str(e)],
+                warnings=[],
+                confidence=0.0,
+            )
+
+        try:
+            tool_result = await self._mcp_client.call_tool(
+                self._get_tool_name("jira_get_issue"),
+                {
+                    "issue_key": issue_key,
+                    "userPrompt": "User initiated a requirements extraction workflow from a Jira issue.",
+                    "llmReasoning": "Need to retrieve the Jira issue content to fulfill the user's request.",
+                },
+            )
+        except MCPToolError:
+            return StageResult(
+                success=False,
+                data=None,
+                errors=["Jira tool not available on the MCP server"],
+                warnings=[],
+                confidence=0.0,
+            )
+
+        if not tool_result.success:
+            return StageResult(
+                success=False,
+                data=None,
+                errors=[tool_result.error or "Failed to retrieve Jira issue"],
+                warnings=[],
+                confidence=0.0,
+            )
+
+        issue = self._map_issue_data(tool_result.data, issue_key)
+
+        return StageResult(
+            success=True,
+            data=issue,
+            errors=[],
+            warnings=[],
+            confidence=1.0,
+        )
+
+    async def check_tool_availability(self) -> list[str]:
+        """Return names of required Jira tools absent from the MCP server.
+
+        Returns:
+            List of missing tool names; empty list means all tools are present.
+
+        Raises:
+            MCPConnectionError: If list_tools() cannot reach the MCP server.
+            MCPAuthenticationError: If authentication with the MCP server fails.
+        """
+        prefixed = [self._get_tool_name(t) for t in self.JIRA_TOOLS]
+        return await self._mcp_client.check_required_tools(prefixed)
diff --git a/src/ai_qa/pipelines/models.py b/src/ai_qa/pipelines/models.py
index e30ce0a..461a7e0 100644
--- a/src/ai_qa/pipelines/models.py
+++ b/src/ai_qa/pipelines/models.py
@@ -54,6 +54,57 @@ class ConfluencePage(BaseModel):
         return self.model_dump(mode="json")
 
 
+class JiraIssue(BaseModel):
+    """Represents a retrieved Jira issue.
+
+    Attributes:
+        issue_key: Issue key (e.g. "PROJ-123")
+        summary: Issue summary/title
+        description: Issue description body
+        acceptance_criteria: Acceptance criteria text (from description or custom field)
+        status: Issue status name
+        labels: List of issue labels
+        project_key: Jira project key
+        url: Direct URL to the issue in Jira
+        retrieved_at: ISO 8601 timestamp when issue was retrieved
+        issue_type: Issue type name (e.g. "Story", "Bug")
+        reporter: Display name of reporter
+        assignee: Display name of assignee
+    """
+
+    issue_key: str = Field(description="Jira issue key (e.g. 'PROJ-123')")
+    summary: str = Field(description="Issue summary/title")
+    description: str | None = Field(default=None, description="Issue description body")
+    acceptance_criteria: str | None = Field(
+        default=None, description="Acceptance criteria text"
+    )
+    status: str | None = Field(default=None, description="Issue status name")
+    labels: list[str] = Field(default_factory=list, description="List of issue labels")
+    project_key: str = Field(description="Jira project key")
+    url: str = Field(description="Direct URL to the issue in Jira")
+    retrieved_at: datetime = Field(
+        default_factory=lambda: datetime.now(UTC),
+        description="ISO 8601 timestamp when issue was retrieved",
+    )
+    issue_type: str | None = Field(default=None, description="Issue type name")
+    reporter: str | None = Field(default=None, description="Display name of reporter")
+    assignee: str | None = Field(default=None, description="Display name of assignee")
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
 class ParsedContent(BaseModel):
     """Represents LLM-optimized content parsed from a Confluence page."""
 
diff --git a/tests/conftest.py b/tests/conftest.py
index bd3e5e8..2444b04 100644
--- a/tests/conftest.py
+++ b/tests/conftest.py
@@ -30,20 +30,31 @@ def mock_db() -> MagicMock:
     user = User(id="user-123", email="test@example.com")
 
     def mock_db_get(model, ident, **kwargs):
-        from ai_qa.db.models import User
+        from ai_qa.db.models import Project, User
         from ai_qa.threads.models import Thread
 
         if model is User:
             return user
         if model is Thread:
-            thread = Thread(id=ident, provider_name="claude", provider_base_url="")
+            thread = Thread(
+                id=ident,
+                provider_name="claude",
+                provider_base_url="",
+                agent_configs={"bob": {"model": "claude-sonnet"}},
+            )
             return thread
+        if model is Project:
+            proj = MagicMock()
+            proj.confluence_base_url = None
+            proj.jira_base_url = None
+            return proj
         return MagicMock()
 
     db.get.side_effect = mock_db_get
-    # A fresh user has no stored UserSecret rows; the secret accessor uses
-    # db.scalar(select(...)), so default it to None to mirror real behavior.
-    db.scalar.return_value = None
+    # Default scalar to a configured UserSecret mock so get_secret_status returns
+    # configured=True for the happy-path gate in BobAgent._check_preconditions.
+    # Individual tests that need configured=False can override db.scalar.return_value.
+    db.scalar.return_value = MagicMock(status="configured", updated_at=None)
     return db
 
 
diff --git a/tests/pipelines/test_jira_reader.py b/tests/pipelines/test_jira_reader.py
new file mode 100644
index 0000000..48c25c0
--- /dev/null
+++ b/tests/pipelines/test_jira_reader.py
@@ -0,0 +1,235 @@
+"""Tests for JiraReader pipeline stage and related capability helpers."""
+
+from unittest.mock import AsyncMock, MagicMock
+
+import pytest
+
+from ai_qa.exceptions import MCPConnectionError, MCPToolError  # noqa: F401 (used in pytest.raises)
+from ai_qa.mcp.tools import ToolResult
+from ai_qa.pipelines.jira_reader import JiraReader
+
+# ---------------------------------------------------------------------------
+# Fixtures
+# ---------------------------------------------------------------------------
+
+
+@pytest.fixture
+def mock_mcp_client() -> MagicMock:
+    client = MagicMock()
+    client.is_connected = True
+    client.server_url = "http://localhost:3000/sse"
+    client._settings = MagicMock()
+    client._settings.mcp_tool_prefix = ""
+    client.call_tool = AsyncMock()
+    client.list_tools = AsyncMock()
+    client.check_required_tools = AsyncMock()
+    return client
+
+
+@pytest.fixture
+def jira_reader(mock_mcp_client: MagicMock) -> JiraReader:
+    return JiraReader(
+        mcp_client=mock_mcp_client,
+        jira_base_url="https://jira.company.com",
+    )
+
+
+_REALISTIC_PAYLOAD = {
+    "key": "PROJ-123",
+    "fields": {
+        "summary": "Login fails for SSO users",
+        "description": "Steps to reproduce: ...",
+        "acceptance_criteria": "Given SSO is configured, user can log in",
+        "status": {"name": "In Progress"},
+        "labels": ["auth", "sso"],
+        "project": {"key": "PROJ"},
+        "issuetype": {"name": "Story"},
+        "reporter": {"displayName": "Alice Smith"},
+        "assignee": {"displayName": "Bob Jones"},
+    },
+}
+
+
+# ---------------------------------------------------------------------------
+# _parse_issue_ref tests
+# ---------------------------------------------------------------------------
+
+
+class TestParseIssueRef:
+    def test_plain_key(self) -> None:
+        assert JiraReader._parse_issue_ref("PROJ-123") == "PROJ-123"
+
+    def test_cloud_url(self) -> None:
+        url = "https://company.atlassian.net/browse/PROJ-123"
+        assert JiraReader._parse_issue_ref(url) == "PROJ-123"
+
+    def test_datacenter_url(self) -> None:
+        url = "https://jira.company.com/browse/PROJ-123"
+        assert JiraReader._parse_issue_ref(url) == "PROJ-123"
+
+    def test_empty_string_raises(self) -> None:
+        with pytest.raises(ValueError, match="must not be empty"):
+            JiraReader._parse_issue_ref("")
+
+    def test_whitespace_only_raises(self) -> None:
+        with pytest.raises(ValueError, match="must not be empty"):
+            JiraReader._parse_issue_ref("   ")
+
+    def test_garbage_input_raises(self) -> None:
+        with pytest.raises(ValueError, match="No Jira issue key found"):
+            JiraReader._parse_issue_ref("https://example.com/not-a-jira-url")
+
+    def test_lowercase_key_raises(self) -> None:
+        with pytest.raises(ValueError, match="No Jira issue key found"):
+            JiraReader._parse_issue_ref("proj-123")
+
+
+# ---------------------------------------------------------------------------
+# read_issue happy path
+# ---------------------------------------------------------------------------
+
+
+class TestReadIssueHappyPath:
+    async def test_returns_jira_issue(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client.call_tool.return_value = ToolResult.from_data(_REALISTIC_PAYLOAD)
+
+        result = await jira_reader.read_issue("PROJ-123")
+
+        assert result.success is True
+        assert result.data is not None
+        issue = result.data
+        assert issue.issue_key == "PROJ-123"
+        assert issue.summary == "Login fails for SSO users"
+        assert issue.description == "Steps to reproduce: ..."
+        assert issue.acceptance_criteria == "Given SSO is configured, user can log in"
+        assert issue.status == "In Progress"
+        assert issue.labels == ["auth", "sso"]
+        assert issue.project_key == "PROJ"
+        assert issue.issue_type == "Story"
+        assert issue.reporter == "Alice Smith"
+        assert issue.assignee == "Bob Jones"
+        assert "PROJ-123" in issue.url
+
+    async def test_url_contains_browse(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client.call_tool.return_value = ToolResult.from_data(_REALISTIC_PAYLOAD)
+        result = await jira_reader.read_issue("PROJ-123")
+        assert result.success is True
+        assert result.data is not None
+        assert "/browse/PROJ-123" in result.data.url
+
+    async def test_accepts_browse_url(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client.call_tool.return_value = ToolResult.from_data(_REALISTIC_PAYLOAD)
+        result = await jira_reader.read_issue("https://jira.company.com/browse/PROJ-123")
+        assert result.success is True
+        assert result.data is not None
+        assert result.data.issue_key == "PROJ-123"
+
+
+# ---------------------------------------------------------------------------
+# read_issue error paths
+# ---------------------------------------------------------------------------
+
+
+class TestReadIssueErrors:
+    async def test_mcp_tool_error_returns_failure(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client.call_tool.side_effect = MCPToolError("tool not found")
+        result = await jira_reader.read_issue("PROJ-123")
+        assert result.success is False
+        assert result.data is None
+        assert result.errors
+        assert "Jira tool not available" in result.errors[0]
+
+    async def test_unsuccessful_tool_result_returns_failure(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client.call_tool.return_value = ToolResult.from_error("issue not found")
+        result = await jira_reader.read_issue("PROJ-123")
+        assert result.success is False
+        assert result.data is None
+        assert result.errors
+
+    async def test_invalid_issue_ref_returns_failure(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        result = await jira_reader.read_issue("not-a-jira-key")
+        assert result.success is False
+        assert result.data is None
+        mock_mcp_client.call_tool.assert_not_called()
+
+
+# ---------------------------------------------------------------------------
+# check_tool_availability tests
+# ---------------------------------------------------------------------------
+
+
+class TestCheckToolAvailability:
+    async def test_returns_missing_tool(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client.check_required_tools.return_value = ["jira_search_issues"]
+        missing = await jira_reader.check_tool_availability()
+        assert missing == ["jira_search_issues"]
+
+    async def test_returns_empty_when_all_present(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client.check_required_tools.return_value = []
+        missing = await jira_reader.check_tool_availability()
+        assert missing == []
+
+    async def test_propagates_mcp_connection_error(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client.check_required_tools.side_effect = MCPConnectionError(
+            "cannot reach server"
+        )
+        with pytest.raises(MCPConnectionError):
+            await jira_reader.check_tool_availability()
+
+    async def test_passes_prefixed_names(
+        self, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client._settings.mcp_tool_prefix = "myprefix_"
+        reader = JiraReader(mock_mcp_client, jira_base_url="https://jira.company.com")
+        mock_mcp_client.check_required_tools.return_value = []
+        await reader.check_tool_availability()
+        called_with = mock_mcp_client.check_required_tools.call_args[0][0]
+        assert all(name.startswith("myprefix_") for name in called_with)
+
+
+# ---------------------------------------------------------------------------
+# ConfluenceReader.check_tool_availability delegation
+# ---------------------------------------------------------------------------
+
+
+class TestConfluenceReaderCheckToolAvailability:
+    async def test_delegates_to_check_required_tools(
+        self, mock_mcp_client: MagicMock
+    ) -> None:
+        from ai_qa.pipelines.confluence_reader import ConfluenceReader
+
+        mock_mcp_client.check_required_tools.return_value = []
+        reader = ConfluenceReader(mcp_client=mock_mcp_client)
+        await reader.check_tool_availability()
+
+        mock_mcp_client.check_required_tools.assert_called_once()
+        called_tools: list[str] = mock_mcp_client.check_required_tools.call_args[0][0]
+        assert len(called_tools) == len(ConfluenceReader.CONFLUENCE_TOOLS)
+
+    async def test_returns_missing_confluence_tools(
+        self, mock_mcp_client: MagicMock
+    ) -> None:
+        from ai_qa.pipelines.confluence_reader import ConfluenceReader
+
+        mock_mcp_client.check_required_tools.return_value = ["confluence_get_page"]
+        reader = ConfluenceReader(mcp_client=mock_mcp_client)
+        missing = await reader.check_tool_availability()
+        assert missing == ["confluence_get_page"]
diff --git a/tests/test_agents/test_bob.py b/tests/test_agents/test_bob.py
index 24d6d3b..13e7c4b 100644
--- a/tests/test_agents/test_bob.py
+++ b/tests/test_agents/test_bob.py
@@ -6,6 +6,7 @@ from ai_qa.agents.base import AgentState
 from ai_qa.agents.bob import BobAgent
 from ai_qa.exceptions import PipelineError
 from ai_qa.models import StageResult
+from ai_qa.secrets.service import SecretStatus
 
 
 @pytest.fixture
@@ -171,6 +172,9 @@ async def test_bob_extract_descendants_creates_single_mcp_client(bob_agent: BobA
         assert mock_mcp_client_class.call_count == 1
 
 
+_VALID_CONFLUENCE_URL = "https://company.atlassian.net/wiki/spaces/TEST/pages/12345/Title"
+
+
 @pytest.mark.asyncio
 async def test_bob_handle_start_confirm_parent(bob_agent: BobAgent) -> None:
     """Test handle_start when process returns confirm_parent."""
@@ -178,7 +182,7 @@ async def test_bob_handle_start_confirm_parent(bob_agent: BobAgent) -> None:
         mock_process.return_value = StageResult(
             success=True, data={"type": "confirm_parent", "suggested_page": "url1"}
         )
-        await bob_agent.handle_start({"space_key": "TEST"})
+        await bob_agent.handle_start({"confluence_url": _VALID_CONFLUENCE_URL})
         assert bob_agent.phase == "confirm_parent"
         assert bob_agent.state == AgentState.REVIEW_REQUEST
 
@@ -189,7 +193,7 @@ async def test_bob_handle_start_review_markdown(bob_agent: BobAgent) -> None:
     with patch.object(bob_agent, "process") as mock_process:
         mock_process.return_value = StageResult(success=True)
         bob_agent.pages = [{"title": "Page 1"}]
-        await bob_agent.handle_start({"confluence_url": "test"})
+        await bob_agent.handle_start({"confluence_url": _VALID_CONFLUENCE_URL})
         assert bob_agent.phase == "review_markdown"
         assert bob_agent.state == AgentState.REVIEW_REQUEST
 
@@ -199,7 +203,7 @@ async def test_bob_handle_start_error(bob_agent: BobAgent) -> None:
     """Test handle_start when process raises an exception."""
     with patch.object(bob_agent, "process") as mock_process:
         mock_process.side_effect = Exception("Crash")
-        await bob_agent.handle_start({"confluence_url": "test"})
+        await bob_agent.handle_start({"confluence_url": _VALID_CONFLUENCE_URL})
         assert bob_agent.state == AgentState.ERROR
 
 
@@ -372,3 +376,260 @@ async def test_bob_process_raises_on_empty_string_mcp_secret(
     with patch("ai_qa.agents.bob.get_user_secret", return_value=""):
         with pytest.raises(PipelineError, match="MCP PAT not configured"):
             await bob_agent.process(input_data)
+
+
+# ---------------------------------------------------------------------------
+# Story 11.2 ΓÇö Intake gate tests
+# ---------------------------------------------------------------------------
+
+_VALID_CONF_URL = "https://company.atlassian.net/wiki/spaces/TEST/pages/12345/Title"
+_CONFIGURED_MCP = SecretStatus(
+    secret_type="mcp",
+    configured=True,
+    status="configured",
+    last_updated=None,
+    validation_state="configured",
+)
+_UNCONFIGURED_MCP = SecretStatus(
+    secret_type="mcp",
+    configured=False,
+    status="missing",
+    last_updated=None,
+    validation_state="missing",
+)
+
+
+# --- AC3: precondition checks ---
+
+
+@pytest.mark.asyncio
+async def test_bob_gate_blocks_when_thread_context_missing(bob_agent: BobAgent) -> None:
+    """AC3: missing thread_id ΓåÆ blocking message sent, no MCP connection."""
+    bob_agent.project_context.thread_id = None  # type: ignore[attr-defined]
+
+    with (
+        patch("ai_qa.agents.bob.MCPClient") as mock_mcp,
+        patch.object(bob_agent, "send_message") as mock_send,
+    ):
+        await bob_agent.handle_start({"confluence_url": _VALID_CONF_URL})
+        mock_mcp.assert_not_called()
+        mock_send.assert_called_once()
+        _, kwargs = mock_send.call_args
+        assert kwargs.get("message_type") == "error"
+
+
+@pytest.mark.asyncio
+async def test_bob_gate_blocks_when_thread_missing_provider_name(
+    bob_agent: BobAgent,
+) -> None:
+    """AC3: thread with no provider_name ΓåÆ blocking message, no MCP."""
+    assert bob_agent.project_context is not None
+    assert bob_agent.project_context.artifact_service is not None
+    bob_agent.project_context.artifact_service.db.get.side_effect = None
+    # Thread has no provider_name
+    mock_thread = MagicMock()
+    mock_thread.provider_name = None
+    mock_thread.agent_configs = {"bob": {"model": "claude-sonnet"}}
+    bob_agent.project_context.artifact_service.db.get.return_value = mock_thread
+
+    with (
+        patch("ai_qa.agents.bob.MCPClient") as mock_mcp,
+        patch("ai_qa.agents.bob.get_secret_status", return_value=_CONFIGURED_MCP),
+        patch.object(bob_agent, "send_message") as mock_send,
+    ):
+        await bob_agent.handle_start({"confluence_url": _VALID_CONF_URL})
+        assert mock_mcp.call_count == 0
+        mock_send.assert_called_once()
+        _, kwargs = mock_send.call_args
+        assert kwargs.get("message_type") == "error"
+        assert "Alice" in mock_send.call_args[0][0]
+
+
+@pytest.mark.asyncio
+async def test_bob_gate_blocks_when_bob_model_missing(bob_agent: BobAgent) -> None:
+    """AC3: thread has provider_name but no bob model config ΓåÆ blocking message, no MCP."""
+    assert bob_agent.project_context is not None
+    assert bob_agent.project_context.artifact_service is not None
+    bob_agent.project_context.artifact_service.db.get.side_effect = None
+    mock_thread = MagicMock()
+    mock_thread.provider_name = "claude"
+    mock_thread.agent_configs = {}  # no "bob" entry
+    bob_agent.project_context.artifact_service.db.get.return_value = mock_thread
+
+    with (
+        patch("ai_qa.agents.bob.MCPClient") as mock_mcp,
+        patch("ai_qa.agents.bob.get_secret_status", return_value=_CONFIGURED_MCP),
+        patch.object(bob_agent, "send_message") as mock_send,
+    ):
+        await bob_agent.handle_start({"confluence_url": _VALID_CONF_URL})
+        assert mock_mcp.call_count == 0
+        mock_send.assert_called_once()
+        _, kwargs = mock_send.call_args
+        assert kwargs.get("message_type") == "error"
+
+
+@pytest.mark.asyncio
+async def test_bob_gate_blocks_when_mcp_not_configured(bob_agent: BobAgent) -> None:
+    """AC3: MCP credential not configured ΓåÆ blocking message, MCPClient never instantiated."""
+    with (
+        patch("ai_qa.agents.bob.MCPClient") as mock_mcp,
+        patch("ai_qa.agents.bob.get_secret_status", return_value=_UNCONFIGURED_MCP),
+        patch.object(bob_agent, "send_message") as mock_send,
+    ):
+        await bob_agent.handle_start({"confluence_url": _VALID_CONF_URL})
+        assert mock_mcp.call_count == 0
+        mock_send.assert_called_once()
+        _, kwargs = mock_send.call_args
+        assert kwargs.get("message_type") == "error"
+        assert "MCP key" in mock_send.call_args[0][0]
+
+
+# --- AC2: _validate_confluence_url unit tests ---
+
+
+def test_validate_confluence_url_empty_returns_required_message() -> None:
+    assert BobAgent._validate_confluence_url("", None) is not None
+    assert BobAgent._validate_confluence_url("   ", None) is not None
+    assert "required" in (BobAgent._validate_confluence_url("", None) or "")
+
+
+def test_validate_confluence_url_invalid_format_returns_hint() -> None:
+    result = BobAgent._validate_confluence_url("not-a-url", None)
+    assert result is not None
+    assert "Expected formats" in result
+
+
+def test_validate_confluence_url_wrong_host_vs_configured_base() -> None:
+    url = "https://evil.com/wiki/spaces/HACK/pages/111/Title"
+    base = "https://company.atlassian.net"
+    result = BobAgent._validate_confluence_url(url, base)
+    assert result is not None
+    assert "company.atlassian.net" in result
+
+
+def test_validate_confluence_url_valid_cloud_matching_host_returns_none() -> None:
+    url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123/Title"
+    base = "https://company.atlassian.net/wiki"
+    assert BobAgent._validate_confluence_url(url, base) is None
+
+
+def test_validate_confluence_url_valid_no_base_configured_returns_none() -> None:
+    url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123/Title"
+    assert BobAgent._validate_confluence_url(url, None) is None
+
+
+@pytest.mark.asyncio
+async def test_bob_gate_invalid_url_blocks_before_mcp(bob_agent: BobAgent) -> None:
+    """AC2: invalid confluence_url ΓåÆ correction sent, MCPClient not instantiated."""
+    with (
+        patch("ai_qa.agents.bob.MCPClient") as mock_mcp,
+        patch("ai_qa.agents.bob.get_secret_status", return_value=_CONFIGURED_MCP),
+        patch.object(bob_agent, "send_message") as mock_send,
+    ):
+        await bob_agent.handle_start({"confluence_url": "not-a-url"})
+        assert mock_mcp.call_count == 0
+        mock_send.assert_called_once()
+        _, kwargs = mock_send.call_args
+        assert kwargs.get("message_type") == "error"
+
+
+# --- AC1: _validate_jira_ref unit tests ---
+
+
+def test_validate_jira_ref_jira_disabled_ignores_any_input() -> None:
+    assert BobAgent._validate_jira_ref("PROJ-123", None) is None
+    assert BobAgent._validate_jira_ref("https://jira.company.com/x", None) is None
+    assert BobAgent._validate_jira_ref("garbage", None) is None
+
+
+def test_validate_jira_ref_jira_enabled_empty_ref_returns_none() -> None:
+    assert BobAgent._validate_jira_ref(None, "https://jira.company.com") is None
+    assert BobAgent._validate_jira_ref("", "https://jira.company.com") is None
+    assert BobAgent._validate_jira_ref("   ", "https://jira.company.com") is None
+
+
+def test_validate_jira_ref_valid_bare_key_returns_none() -> None:
+    assert BobAgent._validate_jira_ref("PROJ-123", "https://jira.company.com") is None
+    assert BobAgent._validate_jira_ref("AB-1", "https://jira.company.com") is None
+
+
+def test_validate_jira_ref_valid_same_host_url_returns_none() -> None:
+    assert (
+        BobAgent._validate_jira_ref(
+            "https://jira.company.com/browse/PROJ-1", "https://jira.company.com"
+        )
+        is None
+    )
+
+
+def test_validate_jira_ref_foreign_host_url_returns_correction() -> None:
+    result = BobAgent._validate_jira_ref(
+        "https://evil.atlassian.net/browse/PROJ-1", "https://jira.company.com"
+    )
+    assert result is not None
+    assert "jira.company.com" in result
+
+
+def test_validate_jira_ref_garbage_returns_correction() -> None:
+    result = BobAgent._validate_jira_ref("not-a-ticket", "https://jira.company.com")
+    assert result is not None
+
+
+@pytest.mark.asyncio
+async def test_bob_gate_stashes_valid_jira_ref(bob_agent: BobAgent) -> None:
+    """AC1: valid Jira ref is stashed on self._jira_ref after gate passes."""
+    assert bob_agent.project_context is not None
+    assert bob_agent.project_context.artifact_service is not None
+    bob_agent.project_context.artifact_service.db.get.side_effect = None
+    mock_project = MagicMock()
+    mock_project.confluence_base_url = None
+    mock_project.jira_base_url = "https://jira.company.com"
+    mock_thread = MagicMock()
+    mock_thread.provider_name = "claude"
+    mock_thread.agent_configs = {"bob": {"model": "claude-sonnet"}}
+
+    def side_effect(model: type, ident: object, **kw: object) -> object:
+        from ai_qa.db.models import Project
+        from ai_qa.threads.models import Thread
+
+        if model is Thread:
+            return mock_thread
+        if model is Project:
+            return mock_project
+        return MagicMock()
+
+    bob_agent.project_context.artifact_service.db.get.side_effect = side_effect
+
+    with (
+        patch("ai_qa.agents.bob.MCPClient") as mock_mcp,
+        patch("ai_qa.agents.bob.get_secret_status", return_value=_CONFIGURED_MCP),
+        patch.object(bob_agent, "process", new_callable=AsyncMock) as mock_proc,
+    ):
+        mock_mcp_instance = AsyncMock()
+        mock_mcp.return_value = mock_mcp_instance
+        mock_proc.return_value = StageResult(
+            success=True, data={"type": "confirm_parent", "suggested_page": "url1"}
+        )
+        await bob_agent.handle_start(
+            {
+                "confluence_url": _VALID_CONF_URL,
+                "jira_url": "PROJ-99",
+            }
+        )
+        assert bob_agent._jira_ref == "PROJ-99"
+
+
+@pytest.mark.asyncio
+async def test_bob_gate_happy_path_reaches_confirm_parent(bob_agent: BobAgent) -> None:
+    """Happy-path regression: valid start with all preconditions met reaches confirm_parent."""
+    with (
+        patch("ai_qa.agents.bob.get_secret_status", return_value=_CONFIGURED_MCP),
+        patch.object(bob_agent, "process", new_callable=AsyncMock) as mock_proc,
+    ):
+        mock_proc.return_value = StageResult(
+            success=True, data={"type": "confirm_parent", "suggested_page": "url1"}
+        )
+        await bob_agent.handle_start({"confluence_url": _VALID_CONF_URL})
+        assert bob_agent.phase == "confirm_parent"
+        assert bob_agent.state == AgentState.REVIEW_REQUEST
+        mock_proc.assert_called_once()
diff --git a/tests/unit/test_mcp_client_capabilities.py b/tests/unit/test_mcp_client_capabilities.py
new file mode 100644
index 0000000..e78ed8b
--- /dev/null
+++ b/tests/unit/test_mcp_client_capabilities.py
@@ -0,0 +1,63 @@
+"""Tests for MCPClient.check_required_tools capability checking."""
+
+from unittest.mock import AsyncMock, MagicMock, patch
+
+import pytest
+
+from ai_qa.exceptions import MCPConnectionError
+from ai_qa.mcp.client import MCPClient
+from ai_qa.mcp.tools import Tool
+
+
+def _make_tool(name: str) -> Tool:
+    return Tool(name=name, description="", parameters=[], returns="")
+
+
+@pytest.fixture
+def mock_mcp_client() -> MCPClient:
+    with patch("ai_qa.mcp.client.ConnectionManager"):
+        client = MCPClient(server_url="http://localhost:3000/sse")
+    client._connection = MagicMock()
+    client._connection.is_connected = True
+    return client
+
+
+class TestCheckRequiredTools:
+    async def test_empty_required_returns_empty(self, mock_mcp_client: MCPClient) -> None:
+        missing = await mock_mcp_client.check_required_tools([])
+        assert missing == []
+
+    async def test_all_present_returns_empty(self, mock_mcp_client: MCPClient) -> None:
+        mock_mcp_client.list_tools = AsyncMock(
+            return_value=[
+                _make_tool("tool_a"),
+                _make_tool("tool_b"),
+            ]
+        )
+        missing = await mock_mcp_client.check_required_tools(["tool_a", "tool_b"])
+        assert missing == []
+
+    async def test_missing_tool_returned(self, mock_mcp_client: MCPClient) -> None:
+        mock_mcp_client.list_tools = AsyncMock(
+            return_value=[_make_tool("tool_a")]
+        )
+        missing = await mock_mcp_client.check_required_tools(["tool_a", "tool_b"])
+        assert missing == ["tool_b"]
+
+    async def test_all_missing(self, mock_mcp_client: MCPClient) -> None:
+        mock_mcp_client.list_tools = AsyncMock(return_value=[])
+        missing = await mock_mcp_client.check_required_tools(["tool_a", "tool_b"])
+        assert set(missing) == {"tool_a", "tool_b"}
+
+    async def test_propagates_connection_error(self, mock_mcp_client: MCPClient) -> None:
+        mock_mcp_client.list_tools = AsyncMock(
+            side_effect=MCPConnectionError("cannot connect")
+        )
+        with pytest.raises(MCPConnectionError):
+            await mock_mcp_client.check_required_tools(["tool_a"])
+
+    async def test_does_not_bypass_cache(self, mock_mcp_client: MCPClient) -> None:
+        mock_mcp_client.list_tools = AsyncMock(return_value=[_make_tool("tool_a")])
+        await mock_mcp_client.check_required_tools(["tool_a"])
+        # list_tools is delegated with default args (uses_cache=True by default)
+        mock_mcp_client.list_tools.assert_called_once()

```
