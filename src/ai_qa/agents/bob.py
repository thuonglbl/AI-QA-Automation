import asyncio
import base64
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote

from markdownify import markdownify

from ai_qa.agents.base import AgentState, BaseAgent
from ai_qa.ai_connection.client import LLMClient
from ai_qa.config import AppSettings
from ai_qa.exceptions import PipelineError
from ai_qa.mcp.client import MCPClient
from ai_qa.models import StageResult
from ai_qa.pipelines.artifact_adapter import PipelineArtifactAdapter
from ai_qa.pipelines.confluence_reader import ConfluenceReader, ConfluenceURLParser
from ai_qa.pipelines.content_parser import ContentParser
from ai_qa.pipelines.jira_reader import JiraReader
from ai_qa.pipelines.models import ConfluencePage, JiraIssue, QualityIssue
from ai_qa.pipelines.requirement_formatter import RequirementFormatter
from ai_qa.secrets import SECRET_TYPE_MCP
from ai_qa.secrets.service import get_secret_status, get_user_secret, set_user_secret

logger = logging.getLogger(__name__)

_QUALITY_MIN_CONTENT_CHARS = 200

# Below this many chars of *parsed* content, a page is treated as having no
# extractable requirements: the LLM formatter is skipped entirely so it cannot
# FABRICATE a full spec from an empty source (a near-empty source gives the model
# nothing real to work from). Deliberately much lower than the advisory quality
# threshold above so it only fires on genuinely empty/trivial pages.
_MIN_EXTRACTABLE_CONTENT_CHARS = 30

_VAGUE_TERMS: tuple[str, ...] = (
    "etc.",
    "and so on",
    "tbd",
    "to be defined",
    "as appropriate",
    "as needed",
    "should work",
    "works properly",
    "works correctly",
    "somehow",
    "some kind of",
    "various",
    "as required",
)

_AMBIGUOUS_UI_TERMS: tuple[str, ...] = (
    "the button",
    "that button",
    "the link",
    "the field",
    "the relevant",
    "the appropriate",
    "the correct page",
    "the right page",
)

_EXPECTED_RESULT_MARKERS: tuple[str, ...] = (
    "expected",
    "then ",
    "## acceptance criteria",
    "acceptance criteria",
    "result",
)

_PRECONDITION_MARKERS: tuple[str, ...] = (
    "precondition",
    "given ",
    "## preconditions",
    "prerequisite",
    "setup",
)

_IMPACT_BY_CATEGORY: dict[str, str] = {
    "unsupported_content": (
        "Source content could not be fully parsed; generated tests may miss this detail."
    ),
    "missing_expected_results": (
        "Without expected results, Mary cannot derive assertions and generated tests may lack verification steps."
    ),
    "missing_preconditions": (
        "Without preconditions, test setup state is undefined and scripts may start from the wrong state."
    ),
    "vague_language": (
        "Vague wording forces the model to guess; generated steps may be inaccurate or unstable."
    ),
    "ambiguous_ui_reference": (
        "Unnamed UI elements force the model to guess selectors; Sarah's scripts may be brittle."
    ),
    "insufficient_content": ("Too little detail to generate meaningful test cases for this item."),
}

# Quality categories that BLOCK progression to test-case selection until the user
# clarifies (or explicitly skips) them. The remaining categories (vague_language,
# ambiguous_ui_reference, unsupported_content) are advisory: surfaced inside the
# clarification question but never gate the flow.
_BLOCKING_QUALITY_CATEGORIES: frozenset[str] = frozenset(
    {"missing_preconditions", "missing_expected_results", "insufficient_content"}
)

# Max clarification rounds per page before Bob auto-acknowledges any remaining
# issues and moves on, so a requirement that can never be fully clarified cannot
# trap the loop indefinitely.
_MAX_CLARIFY_ROUNDS = 3

# Hard upper bound (seconds) on each clarification-loop LLM call. These are small,
# fast prompts (one question / one short rewrite), so a call that runs this long is a
# stalled provider, not real work. Far below the LLMConfig per-request timeout (600s)
# used for the heavy extraction/formatting calls: here we want to FAIL FAST and let
# the loop fall back to a template (or report "couldn't update — skip/rephrase") so a
# slow provider can never hang the clarification step. asyncio.TimeoutError is a
# subclass of Exception, so the existing try/except fallbacks in each call site catch it.
_CLARIFY_LLM_TIMEOUT = 90.0

# Substring stamped on a page's warnings when the extraction pipeline deliberately
# emitted an honest "no content" stub instead of fabricating a requirement. Such
# pages are kept OUT of the clarification loop so the user is never prompted to
# fill in (and the LLM never fabricates) a requirement the pipeline refused to make.
_ANTI_HALLUCINATION_MARKER = "anti-hallucination guard"

# Sentinel the cross-page planner/composer returns for a file whose flagged gaps
# are actually answered elsewhere in the requirement set, or that is an intentional
# wrapper/index page — such files are dropped from the clarification queue.
_NO_CLARIFICATION_SENTINEL = "NO_CLARIFICATION_NEEDED"


class BobAgent(BaseAgent):
    """Bob Agent — Requirements Extraction.

    Extracts pages from Confluence, parses content, and manages
    paginated review of each extracted page.
    """

    def __init__(self, **kwargs: Any) -> None:
        if "name" not in kwargs:
            kwargs["name"] = "Bob"
            kwargs["color"] = "#2196F3"
            kwargs["step_number"] = 2
            kwargs["step_title"] = "Requirements Extraction"
        super().__init__(**kwargs)
        self.pages: list[Any] = []
        self.current_page_index = 0
        self.output_files_saved = 0
        self._space_key: str | None = None
        self._page_id: str | None = None
        self._jira_ref: str | None = None
        # Phases: "init" -> "confirm_parent" -> "clarify" -> "select_id" -> "done".
        # Per-page markdown review was removed: after confirm, all pages are
        # auto-saved; if any has blocking quality issues Bob runs an interactive
        # clarification loop, then the user selects ONE id (Confluence page / Jira ticket).
        self.phase = "init"
        self._has_quality_warnings: bool = False
        self._resolved_page_ids: set[str] = set()
        # The single id the user picks for Mary to generate test cases from.
        self._selected_id: str | None = None
        # Interactive clarification loop (point 5): per-run state for the
        # back-and-forth that resolves blocking quality issues before id selection.
        # _clarify_questions maps page_id -> the cross-page-aware question to ask.
        self._clarify_queue: list[str] = []
        self._clarify_rounds: dict[str, int] = {}
        self._clarify_questions: dict[str, str] = {}

    def _load_project(self) -> Any:
        """Load Project from DB using project context. Returns None if unavailable."""
        if not self.project_context or not self.project_context.artifact_service:
            return None
        db = self.project_context.artifact_service.db
        from ai_qa.db.models import Project

        return db.get(Project, self.project_context.project_id)

    def _check_preconditions(self) -> list[str]:
        """Return list of blocking recovery messages; empty list means all good.

        Checks (in order): project/thread context present, Alice provider config
        ready, MCP credential configured. Performs DB reads only — no MCP, no decryption.
        """
        ctx = self.project_context
        if not ctx or not ctx.project_id or not ctx.user_id or not ctx.thread_id:
            return ["Start Bob from inside an active project thread."]

        db = ctx.artifact_service.db if ctx.artifact_service else None
        if db is None:
            return ["The backend storage service is unavailable — contact support."]

        reasons: list[str] = []

        from ai_qa.threads.models import Thread

        thread = db.get(Thread, ctx.thread_id)
        bob_cfg = (thread.agent_configs or {}).get("bob") if thread else None
        bob_model = (
            (bob_cfg.get("model") or bob_cfg.get("model_name"))
            if isinstance(bob_cfg, dict)
            else None
        )
        if not thread or not thread.provider_name or not bob_model:
            reasons.append("Complete provider and model setup with Alice before starting Bob.")

        if not get_secret_status(db, ctx.user_id, SECRET_TYPE_MCP).configured:
            reasons.append("Add your MCP key in provider configuration, then retry.")

        return reasons

    def _validate_confluence_url(self, url: str, confluence_base_url: str | None) -> str | None:
        """Returns None when the URL is accepted; otherwise a correction string.

        Rules (in order): blank → required; invalid format → format hint; wrong host
        vs configured base → host-mismatch; no page-id or space-key → identifier hint.
        """
        from urllib.parse import urlparse

        url = url.strip()
        if not url:
            return "A Confluence page URL is required to start extraction."

        if not ConfluenceURLParser.is_valid_confluence_url(url):
            return (
                "The URL does not appear to be a valid Confluence page URL. "
                "Expected formats:\n"
                "  - https://company.atlassian.net/wiki/spaces/SPACE/pages/PAGE_ID\n"
                "  - https://confluence.company.com/display/SPACE/Page+Title\n"
                "  - https://confluence.company.com/pages/viewpage.action?pageId=PAGE_ID"
            )

        if isinstance(confluence_base_url, str) and confluence_base_url:
            c_base = (
                confluence_base_url
                if "://" in confluence_base_url
                else "https://" + confluence_base_url
            )
            s_url = url if "://" in url else "https://" + url
            configured_host = (urlparse(c_base).netloc or "").lower()
            submitted_host = (urlparse(s_url).netloc or "").lower()
            if configured_host and submitted_host != configured_host:
                return (
                    f"This URL is not part of the project's configured Confluence "
                    f"instance ({configured_host})."
                )

        page_id = ConfluenceURLParser.extract_page_id(url)
        space_key = ConfluenceURLParser.extract_space_key(url)
        if not page_id and not space_key:
            return (
                "Could not find a page ID or space key in the URL — "
                "point to a specific Confluence page."
            )

        return None

    def _validate_jira_ref(self, jira_ref: str | None, jira_base_url: str | None) -> str | None:
        """Returns None when Jira ref is valid or Jira is disabled; otherwise a correction.

        Jira is optional — a missing ref when Jira is enabled is accepted. Never blocks
        Confluence extraction.
        """
        import re
        from urllib.parse import urlparse

        if not jira_base_url:
            return None

        if not jira_ref or not jira_ref.strip():
            return None

        jira_ref = jira_ref.strip()

        if re.match(r"^[A-Z][A-Z0-9_]+-\d+$", jira_ref):
            return None

        if not re.search(r"\b[A-Za-z][A-Za-z0-9_]+-\d+\b", jira_ref):
            return "The Jira URL must contain a valid issue key (e.g. PROJ-123)."

        test_url = jira_ref if "://" in jira_ref else f"https://{jira_ref}"
        parsed = urlparse(test_url)

        if parsed.netloc:
            c_base = jira_base_url if "://" in jira_base_url else "https://" + jira_base_url
            configured_host = (urlparse(c_base).netloc or "").lower()
            submitted_host = (parsed.netloc or "").lower()
            if submitted_host == configured_host:
                return None
            return (
                f"The Jira URL does not match the project's configured Jira instance "
                f"({configured_host})."
            )

        return (
            "The Jira reference must be a ticket key (e.g. PROJ-123) or a URL from "
            "the project's configured Jira instance."
        )

    def _format_blocked_message(self, reasons: list[str]) -> str:
        """Format precondition failure reasons into a UX-DR12 blocking message."""
        bullets = "\n".join(f"  - {r}" for r in reasons)
        return (
            "**What happened:** Bob cannot start requirements extraction.\n\n"
            "**Why:** One or more required conditions are not met.\n\n"
            f"**What to do:**\n{bullets}"
        )

    def _format_jira_markdown(self, issue: JiraIssue) -> str:
        """Render a JiraIssue to clean Markdown for the review panel (AC2).

        Deterministic, synchronous, no side effects. Only non-empty fields are
        rendered so None values never leak into the output.
        """
        lines: list[str] = []

        lines.append(f"# [{issue.issue_key}] {issue.summary}")
        lines.append("")

        # Metadata line — each segment only when present
        meta_parts: list[str] = []
        if issue.status:
            meta_parts.append(f"**Status:** {issue.status}")
        if issue.issue_type:
            meta_parts.append(f"**Type:** {issue.issue_type}")
        if issue.labels:
            meta_parts.append(f"**Labels:** {', '.join(issue.labels)}")
        if meta_parts:
            lines.append(" · ".join(meta_parts))
            lines.append("")

        lines.append(f"**Source:** [{issue.issue_key}]({issue.url})")

        if issue.description:
            lines.append("")
            lines.append("## Description")
            lines.append("")
            lines.append(issue.description)

        if issue.acceptance_criteria:
            lines.append("")
            lines.append("## Acceptance Criteria")
            lines.append("")
            lines.append(issue.acceptance_criteria)

        return "\n".join(lines)

    def _detect_quality_issues(self, page: dict[str, Any]) -> list[QualityIssue]:
        """Deterministic, synchronous quality scan over a single page dict.

        Returns a list of QualityIssue instances (possibly empty). Never raises.
        """
        issues: list[QualityIssue] = []

        title = str(page.get("page_title") or page.get("page_id") or "this page")
        text = str(page.get("requirement_md") or page.get("parsed_markdown") or "")
        lowered = text.lower()

        for w in page.get("warnings") or []:
            issues.append(
                QualityIssue(
                    category="unsupported_content",
                    location=title,
                    message=str(w),
                    impact=_IMPACT_BY_CATEGORY["unsupported_content"],
                )
            )

        if len(text.strip()) < _QUALITY_MIN_CONTENT_CHARS:
            issues.append(
                QualityIssue(
                    category="insufficient_content",
                    location=title,
                    message=(
                        f"The extracted requirement for '{title}' is very short "
                        f"(fewer than {_QUALITY_MIN_CONTENT_CHARS} characters)."
                    ),
                    impact=_IMPACT_BY_CATEGORY["insufficient_content"],
                )
            )

        if not any(m in lowered for m in _EXPECTED_RESULT_MARKERS):
            issues.append(
                QualityIssue(
                    category="missing_expected_results",
                    location=title,
                    message="No expected results or acceptance criteria were found.",
                    impact=_IMPACT_BY_CATEGORY["missing_expected_results"],
                )
            )

        if not any(m in lowered for m in _PRECONDITION_MARKERS):
            issues.append(
                QualityIssue(
                    category="missing_preconditions",
                    location=title,
                    message="No preconditions or setup steps were found.",
                    impact=_IMPACT_BY_CATEGORY["missing_preconditions"],
                )
            )

        found_vague = sorted({t for t in _VAGUE_TERMS if t in lowered})
        if found_vague:
            issues.append(
                QualityIssue(
                    category="vague_language",
                    location=title,
                    message=f"Vague wording detected: {', '.join(found_vague)}.",
                    impact=_IMPACT_BY_CATEGORY["vague_language"],
                )
            )

        found_ui = sorted({t for t in _AMBIGUOUS_UI_TERMS if t in lowered})
        if found_ui:
            issues.append(
                QualityIssue(
                    category="ambiguous_ui_reference",
                    location=title,
                    message=f"Ambiguous UI references without a specific element name: {', '.join(found_ui)}.",
                    impact=_IMPACT_BY_CATEGORY["ambiguous_ui_reference"],
                )
            )

        return issues

    async def _run_quality_detection(self) -> bool:
        """Run quality detection over all assembled pages; surface a warning summary if any issues.

        Returns True if any page had quality issues.
        """
        has_issues = False
        page_summaries: list[str] = []

        for page in self.pages:
            issues = self._detect_quality_issues(page)
            page["quality_issues"] = [qi.model_dump(mode="json") for qi in issues]
            if issues:
                has_issues = True
                title = str(page.get("page_title") or page.get("page_id") or "this page")
                lines = [f"**{title}**"]
                for qi in issues:
                    lines.append(f"  - {qi.message} — {qi.impact}")
                page_summaries.append("\n".join(lines))

        if has_issues:
            summary_body = "\n\n".join(page_summaries)
            summary = f"⚠ Quality issues detected in the extracted requirements:\n\n{summary_body}"
            await self.send_message(
                content=summary,
                message_type="warning",
                metadata={"is_quality_warning": True},
            )

        return has_issues

    def _resolve_mcp_pat(self) -> str:
        """Resolve MCP PAT from the thread owner's encrypted secrets.

        Returns:
            The decrypted MCP PAT string.

        Raises:
            PipelineError: When project context, user ID, or secret is missing.
        """
        if not self.project_context or not self.project_context.user_id:
            raise PipelineError(
                "**What happened:** Cannot resolve MCP secret.\n\n"
                "**Why:** No project context or user ID is available for this agent run.\n\n"
                "**What to do:** Ensure the agent is started within an active thread with a "
                "valid user session."
            )
        if not self.project_context.artifact_service:
            raise PipelineError(
                "**What happened:** Cannot resolve MCP secret.\n\n"
                "**Why:** The artifact service is not available.\n\n"
                "**What to do:** Contact support — the backend configuration may be incomplete."
            )
        db = self.project_context.artifact_service.db
        try:
            mcp_pat = get_user_secret(db, self.project_context.user_id, SECRET_TYPE_MCP)
        except Exception as exc:
            logger.error("Failed to read MCP secret from DB: %s", exc, exc_info=True)
            raise PipelineError(
                "**What happened:** Failed to read MCP secret from the database.\n\n"
                f"**Why:** A database error occurred while retrieving the secret: {type(exc).__name__}.\n\n"
                "**What to do:** Try again. If the problem persists, contact support."
            ) from exc
        if not mcp_pat:
            raise PipelineError(
                "**What happened:** MCP PAT not configured.\n\n"
                "**Why:** The MCP personal access token is required for Confluence access but was "
                "not found in your encrypted secret store.\n\n"
                "**What to do:** Add your MCP key in the provider configuration and try again."
            )
        return mcp_pat

    async def _retrieve_jira_requirements(
        self,
        client: MCPClient,
        jira_base_url: str | None,
    ) -> list[str]:
        """Best-effort Jira retrieval — appends ticket to self.pages and returns warnings (AC1/AC2/AC3).

        Reuses the already-connected client; never creates a new MCPClient.
        On any failure, logs and returns a warning list without re-raising (AC3).
        """
        try:
            jira_ref = getattr(self, "_jira_ref", None)
            if not jira_ref:
                return []

            if not jira_base_url:
                return []

            reader = JiraReader(client, jira_base_url)
            missing = await reader.check_tool_availability()
            if missing:
                await self.send_message(
                    "⚠ Jira skipped — required tools are not available on the MCP server.",
                    "warning",
                )
                return ["Jira skipped: MCP Jira tools unavailable"]

            result = await reader.read_issue(jira_ref)
            if not result.success or result.data is None:
                err_msg = ", ".join(result.errors) if result.errors else "Unknown error"
                await self.send_message(
                    f"⚠ Could not retrieve the referenced Jira ticket: {err_msg} — continuing with Confluence only.",
                    "warning",
                )
                return [f"Jira ticket retrieval failed: {err_msg}"]

            issue: JiraIssue = result.data
            self.pages.append(
                {
                    "page_id": issue.issue_key,
                    "page_title": f"[{issue.issue_key}] {issue.summary}",
                    "source_url": issue.url,
                    "raw_html": "",
                    "requirement_md": self._format_jira_markdown(issue),
                    "source_type": "jira",
                    "warnings": [],
                }
            )
            await self.send_message(f"✓ Retrieved Jira ticket {issue.issue_key}", "info")
            return []

        except Exception as e:
            logger.error("Jira retrieval step failed: %s", e, exc_info=True)
            await self.send_message(
                "⚠ Jira step skipped due to an unexpected error — continuing with Confluence only.",
                "warning",
            )
            return ["Jira step skipped due to unexpected error"]

    async def handle_start(self, input_data: dict[str, Any]) -> None:
        """Override to parse multiple pages immediately."""
        # Persist MCP PAT submitted via Bob's form before the precondition check so
        # that _check_preconditions can see it as configured in the DB.
        mcp_pat_input = str(input_data.get("mcp_pat") or "").strip()
        if mcp_pat_input and self.project_context and self.project_context.artifact_service:
            db = self.project_context.artifact_service.db
            set_user_secret(db, self.project_context.user_id, SECRET_TYPE_MCP, mcp_pat_input)
            db.commit()

        # --- 11.2 intake gate — runs before any MCP/processing ---
        blockers = self._check_preconditions()
        if blockers:
            await self.send_message(self._format_blocked_message(blockers), message_type="error")
            return

        project = self._load_project()
        confluence_url = str(input_data.get("confluence_url") or "").strip()
        url_err = self._validate_confluence_url(
            confluence_url, project.confluence_base_url if project else None
        )
        if url_err:
            await self.send_message(url_err, message_type="error")
            return

        jira_err = self._validate_jira_ref(
            input_data.get("jira_url"), project.jira_base_url if project else None
        )
        if jira_err:
            await self.send_message(jira_err, message_type="error")
            return
        self._jira_ref = str(input_data.get("jira_url") or "").strip() or None

        # --- 11.1 Capability Check ---
        try:
            mcp_pat = self._resolve_mcp_pat()
            settings = AppSettings()
            client = MCPClient(auth_token=mcp_pat, settings=settings)
            await client.connect()
            try:
                reader_conf = ConfluenceReader(
                    client, confluence_base_url=project.confluence_base_url if project else None
                )
                if hasattr(reader_conf, "check_tool_availability"):
                    missing_conf = await reader_conf.check_tool_availability()
                    if missing_conf:
                        await self.send_message(
                            f"Missing Confluence tools on MCP server: {', '.join(missing_conf)}",
                            message_type="error",
                        )
                        return

                if self._jira_ref:
                    reader_jira = JiraReader(
                        client, jira_base_url=project.jira_base_url if project else None
                    )
                    if hasattr(reader_jira, "check_tool_availability"):
                        missing_jira = await reader_jira.check_tool_availability()
                        if missing_jira:
                            await self.send_message(
                                f"Missing Jira tools on MCP server: {', '.join(missing_jira)}",
                                message_type="error",
                            )
                            return
            finally:
                await client.disconnect()
        except Exception as e:
            logger.error("Failed to verify MCP tools: %s", e, exc_info=True)
            await self.send_message(
                f"Failed to verify MCP tools: {type(e).__name__}. Please check your connection and credentials.",
                message_type="error",
            )
            return

        # --- existing extraction flow (UNCHANGED) ---
        self.phase = "confirm_parent"
        await self.transition_to(AgentState.PROCESSING)

        # Start processing
        try:
            result = await self.process(input_data)
        except Exception as exc:
            logger.error("BobAgent handle_start error: %s", exc, exc_info=True)
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message([str(exc)]),
                message_type="error",
            )
            return

        if (
            result.success
            and isinstance(result.data, dict)
            and result.data.get("type") == "confirm_parent"
        ):
            self.phase = "confirm_parent"
            await self.transition_to(AgentState.REVIEW_REQUEST)
            suggested = result.data.get("suggested_page", "")
            await self.send_message(
                content=(
                    "I found the link below with all the requirements. To cover only part "
                    "of them, enter a parent page URL instead — all of its child pages are "
                    "processed. If your requirements are already extracted and unchanged, "
                    "leave it blank to skip straight to test cases."
                ),
                message_type="text",
                metadata={"is_confirm_parent": True, "suggested_page": suggested},
            )
            return

        if result.success and self.pages:
            self.phase = "review_markdown"
            self.current_page_index = 0
            self.output_files_saved = 0
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self.send_message(
                content="Please review the extracted requirements below.",
                message_type="text",
                metadata={
                    "is_review_ready": True,
                    "pages": self.pages,
                    "has_quality_warnings": self._has_quality_warnings,
                },
            )
        else:
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message(
                    result.errors if result.errors else ["No pages found or parsed."]
                ),
                message_type="error",
            )

    async def process(self, input_data: dict[str, Any], feedback: str | None = None) -> StageResult:
        """Process Confluence extraction."""
        if feedback:
            current_page = self.pages[self.current_page_index]
            await self.send_message(
                f"Re-processing '{current_page.get('page_title', 'this page')}' with feedback...",
                "info",
            )
            raw_html = current_page.get("raw_html") or ""
            if not raw_html:
                # "Where possible": no source HTML (e.g. a Jira item) — re-present
                # unchanged for manual edit rather than fabricating content.
                await self.send_message(
                    "This item has no source HTML to regenerate from. Please edit the "
                    "requirement directly and approve.",
                    "info",
                )
                return StageResult(
                    success=True, data=current_page, errors=[], warnings=[], confidence=1.0
                )
            try:
                config = self.get_llm_config()
                llm_client = LLMClient(config)
                formatter = RequirementFormatter(llm_client)
                page_model = ConfluencePage(
                    page_id=current_page["page_id"],
                    title=current_page.get("page_title", ""),
                    content=raw_html,
                    space_key=self._space_key or "",
                    url=current_page.get("source_url", ""),
                )
                new_md = await formatter.convert_page(page_model, feedback=feedback)
                current_page["requirement_md"] = new_md
            except Exception as exc:
                # Never crash the reject loop — re-present unchanged with a notice.
                logger.error("Bob reprocess failed: %s", exc, exc_info=True)
                await self.send_message(
                    "I couldn't automatically regenerate this page. Please edit it "
                    "directly and approve.",
                    "warning",
                )
            # Refresh quality issues if 11.5's scanner is available
            if hasattr(self, "_detect_quality_issues"):
                current_page["quality_issues"] = [
                    qi.model_dump(mode="json") for qi in self._detect_quality_issues(current_page)
                ]
            return StageResult(
                success=True, data=current_page, errors=[], warnings=[], confidence=1.0
            )

        confluence_url = input_data.get("confluence_url") or ""

        # Try to get confluence_url from project DB if not provided
        if not confluence_url and self.project_context and self.project_context.artifact_service:
            db = self.project_context.artifact_service.db
            from ai_qa.db.models import Project

            project = db.get(Project, self.project_context.project_id)
            if project and project.confluence_base_url:
                confluence_url = project.confluence_base_url

        logger.debug("BobAgent.process: confluence_url=%r", confluence_url)

        # Extract page_id from the URL (works for all Confluence formats including
        # /spaces/SPACE/pages/PAGE_ID/ which doesn't match the space-key regexes)
        parser = ConfluenceURLParser()
        page_id = parser.extract_page_id(confluence_url) if confluence_url else None
        logger.debug("BobAgent.process: page_id=%r", page_id)

        # Resolve MCP PAT from thread owner's encrypted secrets
        mcp_pat = self._resolve_mcp_pat()
        settings = AppSettings()

        await self.send_message(
            content="Connecting to MCP Server...",
            message_type="info",
            metadata={
                "type": "thinking_trace",
                "trace": {
                    "agent_name": "Bob",
                    "available_models": [],
                    "chain_of_thought": [
                        "Initializing MCP Client connection",
                        "Connect status: processing",
                        "Read Confluence page via MCP: pending",
                    ],
                },
            },
        )

        client = MCPClient(auth_token=mcp_pat, settings=settings)
        try:
            await client.connect()
        except Exception as e:
            logger.error("Failed to connect to MCP Server: %s", e, exc_info=True)
            # Update Bob's Thought with the failure
            await self.send_message(
                content="Connect status: FAIL",
                message_type="info",
                metadata={
                    "type": "thinking_trace",
                    "trace": {
                        "agent_name": "Bob",
                        "available_models": [],
                        "chain_of_thought": [f"Connect status: FAIL — {e}"],
                    },
                },
            )
            return StageResult(
                success=False,
                data=None,
                errors=[f"MCP Connection failed: {e}"],
                warnings=[],
                confidence=0.0,
            )

        await self.send_message(
            content="Connected to MCP Server.",
            message_type="info",
            metadata={
                "type": "thinking_trace",
                "trace": {
                    "agent_name": "Bob",
                    "available_models": [],
                    "chain_of_thought": [
                        "Connect status: OK",
                        "Read Confluence page via MCP: processing",
                    ],
                },
            },
        )

        try:
            # Determine suggested page — search for a requirement page first;
            # fall back to confluence_url so the user can always correct it.
            suggested = confluence_url

            if page_id:
                logger.debug("BobAgent.process: have page_id=%r, extracting from URL", page_id)
                space_key = parser.extract_space_key(confluence_url)
                self._space_key = space_key
                self._page_id = page_id
            else:
                space_key = parser.extract_space_key(confluence_url)
                logger.debug("BobAgent.process: fallback space_key=%r", space_key)
                if not space_key:
                    return StageResult(
                        success=False,
                        data=None,
                        errors=[
                            "Could not determine a Confluence page ID or space key from the "
                            f"URL: '{confluence_url}'. "
                            "Please ensure the project's Confluence Base URL points to a "
                            "specific page or includes the space key in the path."
                        ],
                        warnings=[],
                        confidence=0.0,
                    )

                self._space_key = space_key

            # --- Search for requirement page to suggest a smarter URL ---
            # Re-use the already-connected client; ConfluenceReader is lightweight.
            reader = ConfluenceReader(client, confluence_base_url=confluence_url)
            if space_key:
                logger.debug(
                    "BobAgent.process: searching requirement pages in space_key=%r", space_key
                )
                req_result = await reader.find_parent_pages(space_key)
                if req_result.success and req_result.data:
                    first: Any = req_result.data[0]
                    candidate_url = getattr(first, "url", "") if hasattr(first, "url") else ""
                    if candidate_url:
                        suggested = candidate_url
                        logger.debug(
                            "BobAgent.process: requirement page found, suggested=%r", suggested
                        )
            elif page_id:
                logger.debug(
                    "BobAgent.process: searching requirement pages under page_id=%r", page_id
                )
                req_result = await reader.find_requirement_page_by_parent_id(page_id)
                if req_result.success and req_result.data:
                    candidate_url = getattr(req_result.data, "url", "")
                    if candidate_url:
                        suggested = candidate_url
                        logger.debug(
                            "BobAgent.process: requirement child page found, suggested=%r",
                            suggested,
                        )

            await self.send_message(
                content="Found the requirements page.",
                message_type="info",
                metadata={
                    "type": "thinking_trace",
                    "trace": {
                        "agent_name": "Bob",
                        "available_models": [],
                        "chain_of_thought": [
                            "Connect status: OK",
                            "Read Confluence page via MCP: request_review",
                        ],
                    },
                },
            )

            return StageResult(
                success=True,
                data={"type": "confirm_parent", "suggested_page": suggested},
                errors=[],
                warnings=[],
                confidence=1.0,
            )
        finally:
            await client.disconnect()

    async def _extract_descendants(self, parent_title: str) -> StageResult:
        """Phase 2: Extract descendants using the confirmed parent page.

        If self._page_id is set, uses confluence_get_children directly (faster).
        Otherwise falls back to searching by title within the space.
        """
        # Resolve MCP PAT from thread owner's encrypted secrets
        mcp_pat = self._resolve_mcp_pat()

        settings = AppSettings()
        client = MCPClient(auth_token=mcp_pat, settings=settings)
        try:
            await client.connect()
        except Exception as e:
            logger.error("Failed to connect to MCP Server during extraction: %s", e, exc_info=True)
            return StageResult(
                success=False,
                data=None,
                errors=[f"MCP Connection failed: {str(e)}"],
                warnings=[],
                confidence=0.0,
            )

        try:
            confluence_base_url = None
            jira_base_url: str | None = None
            if self.project_context and self.project_context.artifact_service:
                db = self.project_context.artifact_service.db
                from ai_qa.db.models import Project

                project = db.get(Project, self.project_context.project_id)
                if project:
                    confluence_base_url = project.confluence_base_url
                    jira_base_url = project.jira_base_url

            reader = ConfluenceReader(client, confluence_base_url=confluence_base_url)

            await self.send_message(
                f"Extracting child pages for '{parent_title}'...",
                "info",
                metadata={
                    "type": "thinking_trace",
                    "trace": {
                        "agent_name": "Bob",
                        "available_models": [],
                        "chain_of_thought": [
                            "Connect status: OK",
                            f"Fetching children of '{parent_title}' via MCP: processing",
                        ],
                    },
                },
            )

            # Soft tool-availability guard — skip silently if Story 11.1 not yet merged
            if hasattr(reader, "check_tool_availability"):
                missing_tools: list[str] = await reader.check_tool_availability()
                if missing_tools:
                    await self.send_message(
                        "⚠ Some required Confluence tools are unavailable: "
                        f"{', '.join(missing_tools)}. "
                        "Descendant discovery may be limited — check your MCP server configuration.",
                        "warning",
                    )

            # Use page_id if available (direct children fetch), else search by title
            if self._page_id:
                logger.debug("_extract_descendants: using page_id=%r for children", self._page_id)
                desc_res = await reader.get_children_by_id(
                    self._page_id, space_key=self._space_key or ""
                )
            elif self._space_key:
                logger.debug(
                    "_extract_descendants: using space_key=%r + title for descendants",
                    self._space_key,
                )
                desc_res = await reader.get_descendants_by_title(self._space_key, parent_title)
            else:
                return StageResult(
                    success=False,
                    data=None,
                    errors=["No page_id or space_key available to fetch children."],
                    warnings=[],
                    confidence=0.0,
                )
            if not desc_res.success:
                return desc_res

            summaries = []
            from ai_qa.pipelines.models import PageSummary

            if self._page_id and parent_title:
                summaries.append(
                    PageSummary(page_id=self._page_id, title=parent_title, url=parent_title)
                )

            if desc_res.data:
                summaries.extend(desc_res.data)

            if not summaries:
                return StageResult(
                    success=False,
                    data=None,
                    errors=["No pages found to extract (parent or descendants)."],
                    warnings=[],
                    confidence=0.0,
                )

            # Map page id -> immediate parent id for tree rendering. The prepended
            # root page has parent_id=None; descendants carry it from the reader
            # (falling back to the root when their own parent can't be resolved).
            parent_map = {s.page_id: s.parent_id for s in summaries}

            if self.project_context is None:
                raise ValueError("BobAgent requires an active project context.")

            adapter = PipelineArtifactAdapter(self.project_context)

            # Phase 1: Extract Raw HTML
            raw_pages: list[ConfluencePage] = []
            for summary in summaries:
                if not summary.page_id:
                    continue
                await self.send_message(f"Extracting page '{summary.title}'...", "info")

                # Fetch directly by page ID instead of URL to avoid URL validation issues
                page_result = await reader.read_page_by_id(summary.page_id)
                if not page_result.success or not page_result.data:
                    error_details = (
                        ", ".join(page_result.errors) if page_result.errors else "Unknown error"
                    )
                    logger.error(
                        f"Failed to extract page '{summary.title}' (ID: {summary.page_id}): {error_details}"
                    )
                    await self.send_message(
                        f"⚠ Failed to extract: '{summary.title}' - {error_details}", "warning"
                    )
                    continue

                page: ConfluencePage = page_result.data
                adapter.save_raw_html(page.page_id, page.content)
                adapter._save_text(kind="raw_html", name=f"{page.page_id}.txt", content=page.url)
                await self.send_message(f"✓ Extracted '{summary.title}'", "info")
                raw_pages.append(page)

            # Setup LLM for Bob
            config = self.get_llm_config()
            llm_client = LLMClient(config)
            formatter = RequirementFormatter(llm_client)
            parser = ContentParser(adapter)

            # Image captioning fetches each in-page image's bytes through the MCP
            # attachment tools (which reach private Confluence across spaces — the
            # direct /download URL is SSO-gated and returns a login page). Maps an
            # <img src> "/download/(attachments|thumbnails)/{pageId}/{file}" to its
            # attachment id, then downloads the base64 bytes. Per-page list is cached.
            attach_cache: dict[str, dict[str, dict[str, str]]] = {}
            attach_re = re.compile(r"/download/(?:attachments|thumbnails)/(\d+)/([^/?#]+)")
            audit = {
                "userPrompt": "Start requirements extraction from Confluence for this project",
                "llmReasoning": (
                    "Fetching a page image attachment to caption it for the requirement document"
                ),
            }

            async def fetch_image_via_mcp(abs_url: str) -> tuple[bytes, str] | None:
                m = attach_re.search(abs_url)
                if not m:
                    return None
                owner_id, filename = m.group(1), unquote(m.group(2))
                if owner_id not in attach_cache:
                    listing: dict[str, dict[str, str]] = {}
                    try:
                        res = await client.call_tool(
                            reader._get_tool_name("confluence_list_attachments"),
                            {"pageId": owner_id, "limit": 100, **audit},
                        )
                        data = res.data
                        if isinstance(data, str):
                            data = json.loads(data)
                        atts = data.get("attachments", []) if isinstance(data, dict) else []
                        for a in atts if isinstance(atts, list) else []:
                            title = str(a.get("title") or "")
                            if title:
                                listing[title] = {
                                    "id": str(a.get("id") or ""),
                                    "mediaType": str(a.get("mediaType") or ""),
                                }
                    except Exception as exc:
                        logger.warning("MCP list_attachments failed (page %s): %s", owner_id, exc)
                    attach_cache[owner_id] = listing
                att = attach_cache[owner_id].get(filename)
                if not att or not att.get("id"):
                    return None
                try:
                    dl = await client.call_tool(
                        reader._get_tool_name("confluence_download_attachment"),
                        {"attachmentId": att["id"], **audit},
                    )
                    d = dl.data
                    if isinstance(d, str):
                        d = json.loads(d)
                    if not isinstance(d, dict):
                        return None
                    b64 = d.get("base64")
                    if not isinstance(b64, str) or not b64:
                        return None
                    mime = str(d.get("mediaType") or att.get("mediaType") or "image/png")
                    return base64.b64decode(b64), mime
                except Exception as exc:
                    logger.warning("MCP download_attachment failed (%s): %s", att.get("id"), exc)
                    return None

            # Phase 2: Parse + Convert to Requirement
            self.pages = []
            for page in raw_pages:
                await self.send_message(f"Parsing '{page.title}'...", "info")
                parsed_result = await parser.parse(page)
                parsed = parsed_result.data
                warnings = parsed_result.warnings or []
                clean_md = (
                    parsed.markdown if parsed else markdownify(page.content, heading_style="ATX")
                )

                # Anti-hallucination guard (bug fix): an empty/near-empty source gives
                # the LLM nothing to work from, and the fixed BMAD prompt would force it
                # to FABRICATE a full spec. Emit an honest stub and skip the formatter.
                # (If a page that genuinely HAS content lands here, that's a parser
                # fidelity gap — e.g. an unrecognized macro stripped to empty — to fix
                # separately; stubbing is still safer than hallucinating.)
                if len(clean_md.strip()) < _MIN_EXTRACTABLE_CONTENT_CHARS:
                    stub_md = (
                        f"# {page.title}\n\n"
                        f"**Source:** {page.url}\n\n"
                        "_No extractable requirements were found on this page "
                        "(the source is empty or has no substantive content). "
                        "No requirement story was generated to avoid fabricated content._\n"
                    )
                    adapter.save_requirement_page(page.page_id, stub_md)
                    await self.send_message(
                        f"⚠ '{page.title}' has no extractable content — skipped generation.",
                        "warning",
                    )
                    self.pages.append(
                        {
                            "page_id": page.page_id,
                            "page_title": page.title,
                            "parent_id": parent_map.get(page.page_id),
                            "source_url": page.url,
                            "raw_html": page.content,
                            "requirement_md": stub_md,
                            "parsed_markdown": clean_md,
                            "warnings": warnings
                            + [
                                "No extractable content on this page — "
                                "requirement generation skipped (anti-hallucination guard)"
                            ],
                        }
                    )
                    continue

                try:
                    requirement_md = await formatter.convert_markdown(
                        page, clean_md, image_fetcher=fetch_image_via_mcp
                    )
                    adapter.save_requirement_page(page.page_id, requirement_md)
                    await self.send_message(f"✓ Converted '{page.title}'", "info")
                    self.pages.append(
                        {
                            "page_id": page.page_id,
                            "page_title": page.title,
                            "parent_id": parent_map.get(page.page_id),
                            "source_url": page.url,
                            "raw_html": page.content,
                            "requirement_md": requirement_md,
                            "parsed_markdown": clean_md,
                            "warnings": warnings,
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to convert page {page.title}: {e}")
                    await self.send_message(f"⚠ Failed to convert: '{page.title}'", "warning")
                    self.pages.append(
                        {
                            "page_id": page.page_id,
                            "page_title": page.title,
                            "parent_id": parent_map.get(page.page_id),
                            "source_url": page.url,
                            "raw_html": page.content,
                            "requirement_md": "",
                            "parsed_markdown": clean_md,
                            "warnings": warnings
                            + [f"Conversion to requirement failed: {type(e).__name__}"],
                        }
                    )

            if not self.pages:
                return StageResult(
                    success=False,
                    data=None,
                    errors=["All pages failed to extract or convert"],
                    warnings=[],
                    confidence=0.0,
                )

            # --- 11.4: supplement Confluence with Jira (best-effort, never fatal) ---
            # jira_base_url was captured inside the `if project:` block above (Task 4.1)
            jira_warnings = await self._retrieve_jira_requirements(client, jira_base_url)

            # Point 2: emit the "Extract requirements from MCP: done" status block
            # FIRST — right after the per-page conversions and BEFORE the quality
            # summary — so the user sees extraction finished, then the findings.
            await self.send_message(
                content="Requirements extraction complete.",
                message_type="info",
                metadata={
                    "type": "thinking_trace",
                    "trace": {
                        "agent_name": "Bob",
                        "available_models": [],
                        "chain_of_thought": [
                            "Connect status: OK",
                            "Extract requirements from MCP: done",
                        ],
                    },
                },
            )

            # --- 11.5: advisory input-quality detection over all assembled pages ---
            # (Jira items are included because _retrieve_jira_requirements runs above.)
            self._has_quality_warnings = await self._run_quality_detection()

            return StageResult(
                success=True,
                data=self.pages,
                errors=[],
                warnings=jira_warnings,
                confidence=1.0,
            )

        except Exception as e:
            logger.error(f"Error in Bob _extract_descendants: {e}", exc_info=True)
            raise
        finally:
            await client.disconnect()

    def _auto_save_requirements(self) -> int:
        """Save every extracted page as an approved requirement artifact.

        Replaces the old per-page review+approve loop. `save_requirement` is
        idempotent (save-new-first then delete-superseded), so a retry never
        duplicates. Raises on failure so the caller can surface a UX-DR12 retry.
        Returns the number of pages saved.
        """
        if self.project_context is None:
            raise PipelineError("No active project context.")
        adapter = PipelineArtifactAdapter(self.project_context)
        saved = 0
        for page in self.pages:
            if not page.get("requirement_md"):
                continue  # skip pages whose LLM conversion failed
            source_type = str(page.get("source_type") or "confluence")
            source_url = str(page.get("source_url") or "")
            quality_issues = page.get("quality_issues") or []
            adapter.save_requirement(
                page_id=page["page_id"],
                markdown=page["requirement_md"],
                source_type=source_type,
                source_url=source_url,
                warnings=quality_issues,
                title=str(page.get("page_title") or "") or None,
                parent_source_id=page.get("parent_id"),
            )
            # D8: drop the pre-approval draft so Mary's loader sees only the approved copy.
            adapter.delete_draft_requirement(page["page_id"])
            saved_at = datetime.now(UTC).isoformat()
            adapter.save_metadata(
                f"{page['page_id']}/requirement.metadata.json",
                {
                    "source_url": source_url,
                    "extracted_at": saved_at,
                    "source_type": source_type,
                    "quality_warnings_acknowledged": bool(quality_issues),
                    "acknowledged_quality_issues": quality_issues,
                    "acknowledged_at": saved_at,
                    "artifact_kind": "requirements",
                },
            )
            self._resolved_page_ids.add(page["page_id"])
            saved += 1
        return saved

    async def _read_and_save_jira_ticket(
        self, adapter: PipelineArtifactAdapter, ticket_id: str
    ) -> bool:
        """Read one Jira ticket via MCP and save it as an approved requirement.

        Returns True on success; on failure sends a UX-DR12 message and returns
        False (the caller stays in select_id so the user can retry).
        """
        project = self._load_project()
        jira_base_url = project.jira_base_url if project else None
        try:
            mcp_pat = self._resolve_mcp_pat()
            settings = AppSettings()
            client = MCPClient(auth_token=mcp_pat, settings=settings)
            await client.connect()
            try:
                reader = JiraReader(client, jira_base_url=jira_base_url)
                result = await reader.read_issue(ticket_id)
            finally:
                await client.disconnect()
        except Exception as exc:
            logger.error("Bob failed to read Jira ticket %s: %s", ticket_id, exc, exc_info=True)
            await self.send_message(
                content=(
                    "**What happened:** Could not read the Jira ticket.\n\n"
                    f"**Why:** {type(exc).__name__} while contacting the MCP server.\n\n"
                    "**What to do:** Check the ticket id and your connection, then submit again."
                ),
                message_type="error",
            )
            return False

        if not result.success or result.data is None:
            await self.send_message(
                content=self._format_error_message(
                    result.errors if result.errors else [f"Jira ticket '{ticket_id}' not found."]
                ),
                message_type="error",
            )
            return False

        issue = result.data
        markdown = self._format_jira_markdown(issue)
        try:
            adapter.save_requirement(
                page_id=issue.issue_key,
                markdown=markdown,
                source_type="jira",
                source_url=issue.url,
                warnings=[],
                title=f"[{issue.issue_key}] {issue.summary}",
            )
            adapter.delete_draft_requirement(issue.issue_key)
        except Exception as exc:
            logger.error(
                "Bob failed to save Jira requirement %s: %s", ticket_id, exc, exc_info=True
            )
            await self.send_message(
                content=(
                    "**What happened:** Failed to save the Jira requirement.\n\n"
                    f"**Why:** {type(exc).__name__} while writing the artifact.\n\n"
                    "**What to do:** Please submit the ticket id again."
                ),
                message_type="error",
            )
            return False
        return True

    async def _handle_select_id(self, data: dict[str, Any] | None) -> None:
        """Resolve the user's single chosen id, persist it for Mary, then go DONE."""
        import re

        selected_id = str((data or {}).get("id") or "").strip()
        if not selected_id:
            await self.send_message("Please enter a Confluence page id or Jira ticket id.", "error")
            return
        if self.project_context is None:
            await self.send_message(
                content=self._format_error_message(
                    ["Cannot record the selection: no active project context."]
                ),
                message_type="error",
            )
            return
        adapter = PipelineArtifactAdapter(self.project_context)

        # A Confluence page already extracted (and auto-saved) is reused without re-read.
        already_saved = any(p["page_id"] == selected_id for p in self.pages)
        is_jira = bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]+-\d+", selected_id))

        if already_saved:
            page = next(p for p in self.pages if p["page_id"] == selected_id)
            source_type = str(page.get("source_type") or "confluence")
        elif is_jira:
            if not await self._read_and_save_jira_ticket(adapter, selected_id):
                return  # message already sent; stay in select_id for retry
            source_type = "jira"
        else:
            await self.send_message(
                content=(
                    "**What happened:** That id was not recognized.\n\n"
                    f"**Why:** '{selected_id}' is neither a Jira ticket id (e.g. PROJ-123) "
                    "nor one of the Confluence page ids just extracted.\n\n"
                    "**What to do:** Enter a Jira ticket id, or a Confluence page id from "
                    "the pages above."
                ),
                message_type="error",
            )
            return

        # Bob and Mary are separate agent instances — persist the choice as a
        # configuration artifact so Mary can read it on start.
        self._selected_id = selected_id
        try:
            adapter.save_metadata(
                "mary_selected_id.json",
                {"selected_id": selected_id, "source_type": source_type},
            )
        except Exception as exc:
            logger.error("Bob failed to persist selected id: %s", exc, exc_info=True)
            await self.send_message(
                content=(
                    "**What happened:** Failed to record your selection.\n\n"
                    f"**Why:** {type(exc).__name__} while saving the selection.\n\n"
                    "**What to do:** Please submit the id again."
                ),
                message_type="error",
            )
            return

        self.phase = "done"
        await self.transition_to(AgentState.DONE)
        await self.send_message(
            f"Selected '{selected_id}'. Handing off to Mary to generate test cases.",
            "success",
            metadata={"selected_id": selected_id},
        )

    # ------------------------------------------------------------------ #
    # Point 5: interactive requirement-clarification loop                #
    # ------------------------------------------------------------------ #

    def _blocking_issues_for(self, page: dict[str, Any]) -> list[dict[str, Any]]:
        """Stored quality issues for *page* whose category gates progression."""
        return [
            qi
            for qi in (page.get("quality_issues") or [])
            if qi.get("category") in _BLOCKING_QUALITY_CATEGORIES
        ]

    def _advisory_issues_for(self, page: dict[str, Any]) -> list[dict[str, Any]]:
        """Stored quality issues for *page* that are informational only."""
        return [
            qi
            for qi in (page.get("quality_issues") or [])
            if qi.get("category") not in _BLOCKING_QUALITY_CATEGORIES
        ]

    def _page_by_id(self, page_id: str) -> dict[str, Any] | None:
        return next((p for p in self.pages if p.get("page_id") == page_id), None)

    def _is_clarifiable(self, page: dict[str, Any]) -> bool:
        """Only pages with real generated content AND blocking issues enter the loop.

        Excludes failed conversions (empty ``requirement_md`` — never auto-saved) and
        anti-hallucination stubs, so the clarify loop can't resurrect or fabricate a
        requirement the extraction pipeline deliberately refused to generate.
        """
        if not str(page.get("requirement_md") or "").strip():
            return False
        if any(_ANTI_HALLUCINATION_MARKER in str(w) for w in (page.get("warnings") or [])):
            return False
        return bool(self._blocking_issues_for(page))

    def _corpus_digest(
        self,
        *,
        exclude_page_id: str | None = None,
        per_page_chars: int = 2000,
        total_chars: int = 16000,
    ) -> str:
        """A compact context block of EVERY extracted requirement (title + md).

        Used so the LLM judges a file against the WHOLE set — a gap in one file may
        be answered in a related file it references, and wrapper/index pages have
        their detail in their children. Bounded so the prompt stays reasonable.
        """
        parts: list[str] = []
        used = 0
        for p in self.pages:
            pid = str(p.get("page_id") or "")
            if exclude_page_id is not None and pid == exclude_page_id:
                continue
            md = str(p.get("requirement_md") or "").strip()
            if not md:
                continue
            title = str(p.get("page_title") or pid)
            chunk = f"=== {title} (id: {pid}) ===\n{md[:per_page_chars]}"
            if used + len(chunk) > total_chars:
                break
            parts.append(chunk)
            used += len(chunk)
        return "\n\n".join(parts)

    @staticmethod
    def _is_no_clarification(text: str) -> bool:
        """True when an LLM reply means 'this file needs no clarification'."""
        t = text.strip().upper()
        return _NO_CLARIFICATION_SENTINEL in t and len(t) <= len(_NO_CLARIFICATION_SENTINEL) + 12

    async def _begin_clarification_or_select(self) -> None:
        """Read the WHOLE requirement set, decide which files genuinely need
        clarification, then enter the loop — or skip straight to id selection."""
        candidates = [p for p in self.pages if self._is_clarifiable(p)]
        self._clarify_rounds = {}
        self._clarify_questions = {}
        if candidates:
            await self.send_message(
                "Reviewing all requirements together to decide what needs clarifying...",
                "info",
            )
            # Holistic cross-page pass: a gap answered in another file (or a wrapper
            # page) is dropped, and questions are specific rather than generic.
            self._clarify_questions = await self._plan_clarifications(candidates)
        self._clarify_queue = list(self._clarify_questions.keys())
        if not self._clarify_queue:
            await self._prompt_select_id()
            return
        self.phase = "clarify"
        await self.transition_to(AgentState.REVIEW_REQUEST)
        await self.send_message(
            content=(
                "Before generating test cases, let's clarify a few unclear points so the "
                "requirements are complete. I'll go through them one file at a time — "
                "answer in your own words, or skip a file you can't complete."
            ),
            message_type="text",
        )
        await self._ask_clarification(self._clarify_queue[0])

    async def _plan_clarifications(self, candidates: list[dict[str, Any]]) -> dict[str, str]:
        """One holistic LLM pass over the WHOLE set → {page_id: question}.

        Considers every file at once so a gap resolved by a referenced file, or an
        intentional wrapper page, is omitted. Falls back to per-file deterministic
        templates only if the LLM call/parse fails (never silently drops everything).
        """
        valid_ids = {str(p["page_id"]) for p in candidates}
        fallback = {
            str(p["page_id"]): self._template_clarify_question(
                str(p.get("page_title") or p["page_id"]),
                self._blocking_issues_for(p),
                self._advisory_issues_for(p),
            )
            for p in candidates
        }
        flagged = []
        for p in candidates:
            title = str(p.get("page_title") or p["page_id"])
            gaps = "; ".join(str(qi.get("message") or "") for qi in self._blocking_issues_for(p))
            flagged.append(f"- {title} (id: {p['page_id']}): {gaps}")
        try:
            from langchain_core.messages import HumanMessage

            config = self.get_llm_config()
            client = LLMClient(config)
            prompt = (
                "You are a QA analyst reviewing a SET of related software requirement "
                "files before test cases are written. Read the ENTIRE set FIRST. A detail "
                "missing from one file is often defined in another file it references, and "
                "some pages are intentional wrappers / index pages whose real detail lives "
                "in their child files. Do NOT ask about anything already answered elsewhere "
                "in the set, and do NOT ask a wrapper page to add its own requirements.\n\n"
                "ALL REQUIREMENT FILES:\n" + self._corpus_digest() + "\n\n"
                "Files flagged with potential gaps:\n" + "\n".join(flagged) + "\n\n"
                "For ONLY the files that, considering the whole set, STILL have a genuine "
                "unresolved gap, output one block per file in EXACTLY this format:\n"
                "@@FILE: <id>\n<one concise, specific question — a few short sub-questions "
                "max — about what is genuinely missing>\n@@END\n\n"
                "Omit files whose gaps are answered by another file or that are wrappers. "
                "Be specific to the real feature; never ask generic questions. If NOTHING "
                f"needs clarification, output exactly: {_NO_CLARIFICATION_SENTINEL}\n"
                "Output only the blocks (or the sentinel), nothing else."
            )
            resp = await asyncio.wait_for(
                client._chat_model.ainvoke([HumanMessage(content=prompt)]),
                timeout=_CLARIFY_LLM_TIMEOUT,
            )
            content = str(resp.content)
            parsed = self._parse_clarification_plan(content, valid_ids)
            if parsed:
                return parsed
            # No blocks: distinguish 'nothing to clarify' from an unparseable reply.
            if _NO_CLARIFICATION_SENTINEL in content.upper() or len(content.strip()) < 12:
                return {}
            return fallback
        except Exception as exc:
            logger.warning("Bob cross-page clarify planning failed (%s); using templates", exc)
            return fallback

    @staticmethod
    def _parse_clarification_plan(text: str, valid_ids: set[str]) -> dict[str, str]:
        """Parse ``@@FILE: <id>\\n<question>\\n@@END`` blocks → {id: question}."""
        plan: dict[str, str] = {}
        pattern = re.compile(r"@@FILE:\s*([^\n]+?)\s*\n(.*?)(?=@@FILE:|@@END|\Z)", re.DOTALL)
        for m in pattern.finditer(text):
            pid = m.group(1).strip()
            question = m.group(2).strip()
            if pid in valid_ids and question:
                plan[pid] = question
        return plan

    async def _ask_clarification(self, page_id: str) -> None:
        """Emit the (already cross-page-planned) clarification question for one page."""
        page = self._page_by_id(page_id)
        if page is None:
            await self._advance_clarification(page_id)
            return
        blocking = self._blocking_issues_for(page)
        advisory = self._advisory_issues_for(page)
        title = str(page.get("page_title") or page_id)
        question = self._clarify_questions.get(page_id) or self._template_clarify_question(
            title, blocking, advisory
        )
        await self.send_message(
            content=question,
            message_type="text",
            metadata={
                "type": "clarify_request",
                "page_id": page_id,
                "page_title": title,
                "source_url": str(page.get("source_url") or ""),
                "round": self._clarify_rounds.get(page_id, 0) + 1,
                "max_rounds": _MAX_CLARIFY_ROUNDS,
                "points": [
                    {
                        "category": str(qi.get("category") or ""),
                        "message": str(qi.get("message") or ""),
                        "blocking": qi.get("category") in _BLOCKING_QUALITY_CATEGORIES,
                    }
                    for qi in (blocking + advisory)
                ],
            },
        )

    @staticmethod
    def _template_clarify_question(
        title: str,
        blocking: list[dict[str, Any]],
        advisory: list[dict[str, Any]],
    ) -> str:
        """Deterministic fallback question used when the LLM call is unavailable."""
        lines = [f"**{title}** needs a bit more detail before I can hand it to Mary:"]
        lines += [f"- {qi.get('message')}" for qi in blocking]
        lines += [f"- (advisory) {qi.get('message')}" for qi in advisory]
        lines.append("")
        lines.append("Please describe the missing details, or Skip the points you can't provide.")
        return "\n".join(lines)

    async def _compose_clarify_question(self, page: dict[str, Any]) -> str:
        """Regenerate a single file's question (corpus-aware) for a follow-up round.

        Returns the sentinel when the whole-set context now resolves the gaps, so the
        caller can drop the file instead of re-asking. Falls back to a template on error.
        """
        blocking = self._blocking_issues_for(page)
        advisory = self._advisory_issues_for(page)
        title = str(page.get("page_title") or page.get("page_id") or "this requirement")
        fallback = self._template_clarify_question(title, blocking, advisory)
        blocking_lines = "\n".join(f"- {qi.get('message')}" for qi in blocking) or "(none)"
        advisory_lines = "\n".join(f"- {qi.get('message')}" for qi in advisory) or "(none)"
        current_md = str(page.get("requirement_md") or "")
        corpus = self._corpus_digest(exclude_page_id=str(page.get("page_id") or ""))
        try:
            from langchain_core.messages import HumanMessage

            config = self.get_llm_config()
            client = LLMClient(config)
            prompt = (
                "You are a QA analyst reviewing a SET of related requirement files. "
                "Consider the WHOLE set: a gap in this file may be answered in a related "
                "file, and some pages are intentional wrappers.\n\n"
                f"FILE TO CLARIFY: {title}\n{current_md[:4000]}\n\n"
                f"Flagged gaps (may be false positives if covered elsewhere):\n{blocking_lines}\n"
                f"Advisory:\n{advisory_lines}\n\n"
                f"RELATED FILES (context — never ask about anything answered here):\n{corpus}\n\n"
                "If the whole-set context resolves the gaps, or this is a wrapper page, reply "
                f"EXACTLY: {_NO_CLARIFICATION_SENTINEL}\n"
                "Otherwise ask ONE concise, specific question about what is genuinely missing "
                "for this file. Be specific to the real feature; do not ask generic questions. "
                "Output only the question text (or the sentinel)."
            )
            resp = await asyncio.wait_for(
                client._chat_model.ainvoke([HumanMessage(content=prompt)]),
                timeout=_CLARIFY_LLM_TIMEOUT,
            )
            return str(resp.content).strip() or fallback
        except Exception as exc:
            logger.warning("Bob clarify-question LLM call failed (%s); using template", exc)
            return fallback

    async def _handle_clarify_answer(self, data: dict[str, Any] | None) -> None:
        """Apply the user's clarification answer (or a file skip) for the current page,
        then either re-ask, advance, or finish."""
        payload = data or {}
        action = str(payload.get("action") or "clarify_answer")
        supplied_id = str(payload.get("page_id") or "")

        if not self._clarify_queue:
            # Nothing left to clarify (e.g. a late / duplicate submit) — move on.
            await self._prompt_select_id()
            return
        head = self._clarify_queue[0]

        if action == "skip_file":
            await self.send_message("Skipped — leaving this requirement as-is.", "info")
            await self._advance_clarification(head)
            return

        # A content answer must target the CURRENT head. A stale / duplicate answer
        # for an already-advanced page is never applied to a different requirement —
        # just re-ask the current head so the user answers the right file.
        if supplied_id and supplied_id != head:
            await self._ask_clarification(head)
            return

        answer = str(payload.get("answer") or "").strip()
        if not answer:
            await self.send_message("Please type an answer, or use Skip.", "error")
            return

        page = self._page_by_id(head)
        if page is None:
            await self._advance_clarification(head)
            return

        await self.send_message("Updating the requirement with your answer...", "info")
        # _apply_clarification rewrites the MD, RE-SCANS, and saves with the fresh
        # warnings, then commits the refreshed issues onto the page on success.
        applied = await self._apply_clarification(page, answer)
        self._clarify_rounds[head] = self._clarify_rounds.get(head, 0) + 1

        if not applied:
            await self.send_message(
                "I couldn't update the file automatically. You can skip this file or "
                "rephrase your answer.",
                "warning",
            )

        still_blocking = self._blocking_issues_for(page)
        if still_blocking and self._clarify_rounds[head] < _MAX_CLARIFY_ROUNDS:
            # Regenerate the question with whole-set context; the rewrite may now be
            # covered by sibling files, in which case drop the file instead of re-asking.
            new_q = await self._compose_clarify_question(page)
            if not self._is_no_clarification(new_q):
                self._clarify_questions[head] = new_q
                await self.send_message("Thanks. A couple of points still need detail:", "text")
                await self._ask_clarification(head)
                return

        if still_blocking:
            await self.send_message(
                "Thanks. I'll proceed with what we have for this file "
                "(remaining gaps noted for the test author).",
                "info",
            )
        else:
            await self.send_message("That requirement looks complete now. ✓", "success")
        await self._advance_clarification(head)

    async def _advance_clarification(self, page_id: str) -> None:
        """Drop *page_id* from the queue and ask the next page, or prompt for an id."""
        self._clarify_queue = [pid for pid in self._clarify_queue if pid != page_id]
        if self._clarify_queue:
            await self._ask_clarification(self._clarify_queue[0])
        else:
            await self._prompt_select_id()

    async def _apply_clarification(self, page: dict[str, Any], answer: str) -> bool:
        """Rewrite the page's requirement.md to incorporate the user's answer and
        persist it (idempotent overwrite). Returns True on a successful edit + save."""
        if self.project_context is None:
            return False
        current_md = str(page.get("requirement_md") or "")
        title = str(page.get("page_title") or page.get("page_id") or "")
        source_url = str(page.get("source_url") or "")
        corpus = self._corpus_digest(exclude_page_id=str(page.get("page_id") or ""))
        try:
            from langchain_core.messages import HumanMessage

            config = self.get_llm_config()
            client = LLMClient(config)
            prompt = (
                "You are editing a software requirement written in Markdown. Revise it to "
                "incorporate the author's clarification below. Integrate the new details "
                "into the appropriate sections (e.g. add or complete '## Preconditions' or "
                "'## Acceptance Criteria'); keep everything already correct; keep the "
                "existing title and the '**Source:**' line intact. You MAY rely on facts the "
                "author references from the related files below, but do NOT invent anything "
                "beyond those files and the clarification. Output ONLY the full revised "
                "Markdown — no code fences, no commentary.\n\n"
                f"Author's clarification:\n{answer}\n\n"
                f"Related files in the same set (for referenced facts):\n{corpus}\n\n"
                f"Current requirement:\n{current_md}"
            )
            resp = await asyncio.wait_for(
                client._chat_model.ainvoke([HumanMessage(content=prompt)]),
                timeout=_CLARIFY_LLM_TIMEOUT,
            )
            new_md = str(resp.content).strip()
        except Exception as exc:
            logger.error("Bob clarify-apply LLM call failed: %s", exc, exc_info=True)
            return False

        if not new_md:
            return False
        page["requirement_md"] = new_md
        # Re-scan the rewritten content BEFORE persisting so the saved artifact's
        # warnings reflect the NEW content, not the stale pre-edit issues (F7).
        fresh_issues = [qi.model_dump(mode="json") for qi in self._detect_quality_issues(page)]
        try:
            adapter = PipelineArtifactAdapter(self.project_context)
            adapter.save_requirement(
                page_id=str(page["page_id"]),
                markdown=new_md,
                source_type=str(page.get("source_type") or "confluence"),
                source_url=source_url,
                warnings=fresh_issues,
                title=title or None,
                parent_source_id=page.get("parent_id"),
            )
        except Exception as exc:
            # The in-memory MD is updated; persistence is retried on the next save.
            logger.error("Bob clarify-save failed: %s", exc, exc_info=True)
            return False
        # Commit the refreshed issues only after a successful save so in-memory
        # state matches what was persisted.
        page["quality_issues"] = fresh_issues
        return True

    def _load_saved_requirement_pages(
        self, adapter: PipelineArtifactAdapter
    ) -> list[dict[str, Any]]:
        """Minimal page dicts for the APPROVED requirements already saved in this project.

        Used by the "skip extraction" path so the user can still pick ONE existing
        requirement id for Mary: the id picker and ``_handle_select_id`` resolve against
        ``self.pages``. Drafts (``source_type`` is None) are excluded. Approved copies are
        named ``{page_id}/requirement.md`` — the id is the path's first segment.
        """
        pages: list[dict[str, Any]] = []
        for art in adapter.load_requirement_markdown():
            if art.source_type is None:
                continue
            page_id = art.name.split("/")[0] if "/" in art.name else art.name
            pages.append(
                {
                    "page_id": page_id,
                    "page_title": page_id,
                    "source_url": art.source_url or "",
                    "source_type": art.source_type or "confluence",
                    "requirement_md": art.content or "",
                }
            )
        return pages

    async def _prompt_select_id(self) -> None:
        """Ask the user to pick one Confluence page id or Jira ticket id for Mary.

        Shared exit for both the no-issues path and the end of the clarify loop.
        """
        self.phase = "select_id"
        await self.transition_to(AgentState.REVIEW_REQUEST)
        await self.send_message(
            content=(
                f"Saved {self.output_files_saved} requirements from Confluence. Please input "
                "1 Confluence page id or Jira ticket id to generate test cases."
            ),
            message_type="text",
            metadata={"is_select_id": True},
        )

    async def handle_approve(self, data: dict[str, Any] | None = None) -> None:
        """Override to handle parent confirmation and single-id selection."""
        if self.phase == "confirm_parent":
            # Skip path: the user left the link blank — their requirements are
            # already extracted (e.g. by a colleague) with no updates. Bypass
            # extraction entirely and hand off to Mary, which reads the existing
            # approved requirements from the project artifact store.
            if data and data.get("action") == "skip":
                # "Already extracted, unchanged" — don't re-read Confluence. But the
                # pipeline is per-requirement, so the user must still pick ONE saved
                # requirement for Mary to focus on. Load the saved approved requirements
                # into self.pages so the id picker + _handle_select_id can resolve them,
                # then prompt for the id. (The old behaviour jumped straight to DONE
                # without a selected id, so Mary fell back to ALL requirements at once —
                # an enormous prompt that stalled generation.)
                if self.project_context is None:
                    await self.transition_to(AgentState.ERROR)
                    await self.send_message(
                        content=self._format_error_message(
                            ["Cannot continue: no active project context."]
                        ),
                        message_type="error",
                    )
                    return
                adapter = PipelineArtifactAdapter(self.project_context)
                self.pages = self._load_saved_requirement_pages(adapter)
                if not self.pages:
                    # Nothing saved to choose from — hand off so Mary surfaces its own
                    # "no requirements" message rather than trapping the user here.
                    self.phase = "done"
                    await self.transition_to(AgentState.DONE)
                    await self.send_message(
                        "No previously saved requirements were found to skip to. Handing "
                        "off to Mary, which will report if there is nothing to generate "
                        "from.",
                        "warning",
                    )
                    return
                self.output_files_saved = len(self.pages)
                await self._prompt_select_id()
                return

            # Proceed to Phase 2: Extraction
            confirmed_page = data.get("confirmed_page_name") if data else None
            if not confirmed_page and data and data.get("suggested_page"):
                confirmed_page = data.get("suggested_page")

            if not confirmed_page:
                await self.send_message("No page title provided.", "error")
                return

            parser = ConfluenceURLParser()
            new_page_id = parser.extract_page_id(confirmed_page)
            if new_page_id:
                self._page_id = new_page_id

            new_space_key = parser.extract_space_key(confirmed_page)
            if new_space_key:
                self._space_key = new_space_key

            await self.transition_to(AgentState.PROCESSING)
            result = await self._extract_descendants(confirmed_page)

            if result.success and self.pages:
                if self.project_context is None:
                    await self.transition_to(AgentState.ERROR)
                    await self.send_message(
                        content=self._format_error_message(
                            ["Cannot save requirements: no active project context."]
                        ),
                        message_type="error",
                    )
                    return
                # Per-page review removed: auto-save every extracted page as an
                # approved requirement, then ask the user to pick ONE id.
                try:
                    saved = self._auto_save_requirements()
                except Exception as exc:
                    logger.error("Bob failed to auto-save requirements: %s", exc, exc_info=True)
                    await self.send_message(
                        content=(
                            "**What happened:** Failed to save extracted requirements to "
                            "the project artifact store.\n\n"
                            f"**Why:** {type(exc).__name__} while writing the artifacts.\n\n"
                            "**What to do:** Please approve again to retry — saving is "
                            "idempotent, so no duplicates are created."
                        ),
                        message_type="error",
                    )
                    return  # stay in confirm_parent; re-approve re-runs the save
                self.output_files_saved = saved
                # Point 5: if any requirement has blocking quality issues, run the
                # interactive clarification loop first; otherwise go straight to id
                # selection. Either path ends at the select-id prompt.
                await self._begin_clarification_or_select()
            else:
                await self.transition_to(AgentState.ERROR)
                await self.send_message(
                    content=self._format_error_message(
                        result.errors if result.errors else ["Failed to extract."]
                    ),
                    message_type="error",
                )
            return

        # Clarify Phase: the user answers (or skips) the open quality questions.
        if self.phase == "clarify":
            await self._handle_clarify_answer(data)
            return

        # Select-id Phase: the user picks ONE Confluence page id or Jira ticket id.
        if self.phase == "select_id":
            await self._handle_select_id(data)
            return

        # No active phase matched. This usually means the backend was restarted: the
        # frontend restores a mid-flow panel (clarify / select-id) from chat history, but
        # this agent's in-memory progress was reset to "init". Silently doing nothing left
        # the user clicking with no response — tell them how to recover instead.
        await self.send_message(
            content=(
                "**What happened:** This step is no longer in progress.\n\n"
                "**Why:** The server was restarted, so this step's in-memory progress was "
                "reset. Your chat history is restored, but the live session is not.\n\n"
                "**What to do:** Click **Start** to run this step again from the beginning. "
                "Requirements already saved in this project are kept."
            ),
            message_type="error",
        )

    async def handle_reject(self, feedback: str, data: dict[str, Any] | None = None) -> None:
        """Reprocess the rejected page with feedback, then re-present it for review."""
        # Target the rejected page (frontend sends data={"page_id": ...}); default to current.
        page_id = data.get("page_id") if data else None
        if page_id:
            idx = next((i for i, p in enumerate(self.pages) if p["page_id"] == page_id), None)
            if idx is not None:
                self.current_page_index = idx
            else:
                await self.send_message(f"Page '{page_id}' not found.", "error")
                return

        # AC3: acknowledge conversationally BEFORE retrying.
        await self.send_message(
            content=f'Understood — reprocessing this page with your feedback: "{feedback}"',
            message_type="text",
        )
        await self.transition_to(AgentState.PROCESSING)

        try:
            result = await self.process(input_data={}, feedback=feedback)
        except Exception as exc:
            logger.error("BobAgent error during reject: %s", exc, exc_info=True)
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message([str(exc)]), message_type="error"
            )
            return

        if result.success and result.data is not None:
            self.pages[self.current_page_index] = result.data
            self.phase = "review_markdown"
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self.send_message(
                content="I've updated this page based on your feedback. Please review it again.",
                message_type="text",
                metadata={
                    "is_review_ready": True,
                    "pages": self.pages,
                    "has_quality_warnings": getattr(self, "_has_quality_warnings", False),
                },
            )
        else:
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message(result.errors), message_type="error"
            )
