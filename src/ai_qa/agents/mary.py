"""Mary agent - Test Case Generation with Per-Item Review.

Mary generates test cases from requirements extracted by Bob and presents them
for per-item review. Users can approve or reject individual test cases with feedback.
"""

import asyncio
import logging
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage

from ai_qa.agents.base import AgentState, BaseAgent
from ai_qa.ai_connection.client import LLMClient
from ai_qa.config import AppSettings
from ai_qa.exceptions import PipelineError
from ai_qa.mcp.client import MCPClient
from ai_qa.models import StageResult, TestCase
from ai_qa.pipelines.artifact_adapter import PipelineArtifact, PipelineArtifactAdapter
from ai_qa.pipelines.jira_reader import JiraReader
from ai_qa.pipelines.models import JiraIssue
from ai_qa.pipelines.test_case_extractor import RequirementSource, TestCaseExtractor
from ai_qa.secrets import SECRET_TYPE_MCP
from ai_qa.secrets.service import get_user_secret

logger = logging.getLogger(__name__)

# A Jira ticket key looks like ``PROJ-123``; a Confluence page id is all digits.
_JIRA_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]+-\d+$")

# Sentinel the test-design clarification planner returns when the focus requirement
# (read together with the project overview) has no genuine gap worth asking about.
_NO_CLARIFICATION_SENTINEL = "NO_CLARIFICATION_NEEDED"

# Cap how many clarification questions Mary asks in one run so an unusually gap-heavy
# requirement cannot trap the user in an endless Q&A before any test case is written.
_MAX_CLARIFY_QUESTIONS = 5

# Hard upper bound (seconds) on the test-design clarification-planning LLM call. It is a
# small prompt, so a call running longer than this means a stalled provider, not real
# work. Far below the 600s per-request timeout used for heavy generation: here we want
# planning to FAIL FAST and fall back to "no clarifications → generate" rather than leave
# the step looking idle. asyncio.TimeoutError ⊂ Exception, so the caller's try/except
# (handle_start) catches it.
_CLARIFY_LLM_TIMEOUT = 90.0


class MaryAgent(BaseAgent):
    """Agent for generating and reviewing test cases.

    Mary generates test cases from requirements saved by Bob via the artifact service
    and presents them for per-item review. Users can approve or reject individual
    test cases with feedback.

    Lifecycle:
        START → PROCESSING → REVIEW_REQUEST → (Approve/Reject+feedback) → DONE
    """

    def __init__(
        self,
        name: str = "Mary",
        color: str = "green",
        step_number: int = 3,
        step_title: str = "Create Test Cases",
        workspace_dir: Path | None = None,
    ) -> None:
        """Initialize Mary agent.

        Args:
            name: Agent display name
            color: HEX colour string matching frontend
            step_number: Pipeline step index
            step_title: Human-readable label shown in UI
            workspace_dir: Override workspace root path (used in tests)
        """
        super().__init__(name, color, step_number, step_title, workspace_dir)

        # Mary-specific state
        self.test_cases: list[TestCase] = []
        self.current_review_index: int = 0
        self._reviewed_indices: set[int] = set()

        # Phase gates handle_approve: "clarify" runs the test-design clarification
        # loop (point 5); "review_testcases" is the per-item test-case review. Default
        # to review so the existing single-instance approval flow is unchanged.
        self.phase: str = "review_testcases"
        # Interactive test-design clarification loop state (persists across websocket
        # messages because the agent instance is cached per (user, project, step)).
        self._clarify_queue: list[str] = []
        self._clarifications: list[str] = []
        # Resolved at handle_start: the single id Bob handed off + its source kind, and
        # a compact overview of every other requirement, all fed into generation.
        self._selected_id: str | None = None
        self._selected_source_type: str | None = None
        self._overview_digest: str = ""

        # Initialize pipeline components. The LLM config is resolved here only as a
        # provisional placeholder — the real api_key lives in the user's encrypted
        # secret store, which is unreachable until set_project_context() attaches the
        # context. _ensure_llm_ready() refreshes it before any LLM call (see below).
        self.config = self.get_llm_config()

        self.extractor = TestCaseExtractor(
            llm_config=self.config,
        )

    def _ensure_llm_ready(self) -> None:
        """Resolve the LLM config against the attached project context and apply it.

        Building the extractor in ``__init__`` captured an empty api_key (the agent is
        constructed by ``agent_class()`` before ``set_project_context`` runs), which
        surfaced at call time as a raw provider auth error ("Could not resolve
        authentication method"). Resolving here — mirroring Bob, which builds its LLM
        lazily — uses the context-resolved key. Raises ``PipelineError`` (UX-DR12) when
        the key is genuinely missing; callers run inside try/except that surface it.
        """
        self.config = self.get_llm_config()
        # Assign the attribute directly (not via a setter call) so a mocked extractor
        # in unit tests records a plain attribute rather than an unawaited coroutine.
        self.extractor.llm_config = self.config

    def _check_preconditions(self) -> list[str]:
        """Return blocking messages (UX-DR12); empty list = all checks pass.

        Mirrors Sarah/Bob's gate but only the context checks Mary needs for input
        resolution — no MCP / Alice-provider gate (the LLM is only used at generation).
        """
        ctx = self.project_context
        if not ctx or not ctx.project_id or not ctx.user_id or not ctx.thread_id:
            return ["Start Mary from inside an active project thread."]
        if ctx.artifact_service is None:
            return ["The backend storage service is unavailable — contact support."]
        return []

    def _format_blocked_message(self, reasons: list[str]) -> str:
        """Format precondition failure reasons into a UX-DR12 blocking message."""
        bullets = "\n".join(f"  - {r}" for r in reasons)
        return (
            "**What happened:** Mary cannot start test case generation.\n\n"
            "**Why:** One or more required conditions are not met.\n\n"
            f"**What to do:**\n{bullets}"
        )

    def _format_no_requirements_message(self) -> str:
        """UX-DR12 message when no approved requirements are found (AC3)."""
        return (
            "**What happened:** Mary cannot generate test cases yet.\n\n"
            "**Why:** No approved requirements were found for this project.\n\n"
            "**What to do:** Run Bob to extract requirements from Confluence/Jira and "
            "approve at least one requirement, then start Mary again."
        )

    def _approved_requirement_artifacts(
        self, adapter: PipelineArtifactAdapter
    ) -> list[PipelineArtifact]:
        """Load requirement artifacts, keeping only APPROVED ones (AC1).

        Drafts are saved as ``{page_id}.md`` with ``source_type`` NULL; approved copies
        are ``{page_id}/requirement.md`` with ``source_type`` set. ``source_type IS NOT
        NULL`` is the authoritative draft-vs-approved discriminator.
        """
        return [a for a in adapter.load_requirement_markdown() if a.source_type is not None]

    async def handle_start(self, input_data: dict[str, Any]) -> None:
        """Read the requirement overview, resolve the focus source, clarify, generate.

        Flow (point 5 + the requested overview/Jira behaviour):
          1. Gate on at least one APPROVED requirement (AC3 — no LLM call otherwise).
          2. Read EVERY requirement markdown for an overview, then focus on the single
             id Bob handed off. A Confluence page id reuses Bob's saved copy; a Jira
             ticket id is fetched live from MCP and saved.
          3. Run a risk-based test-design pass and, only when there are genuine gaps,
             ask the author to clarify (one question at a time) before generating.
        """
        await self.send_message("I'll design test cases based on your approved requirements.")

        blockers = self._check_preconditions()
        if blockers:
            await self.send_message(self._format_blocked_message(blockers), message_type="error")
            return

        # AC3 precondition: at least one APPROVED requirement must exist before we
        # transition to PROCESSING or invoke the extractor.
        assert self.project_context is not None  # narrowed by _check_preconditions
        adapter = PipelineArtifactAdapter(self.project_context)
        if not self._approved_requirement_artifacts(adapter):
            await self.send_message(self._format_no_requirements_message(), message_type="error")
            return

        # Resolve the LLM config now that the context (and the user's encrypted secret
        # store) is attached; surface a clean UX-DR12 message if the key is missing.
        try:
            self._ensure_llm_ready()
        except Exception as exc:
            logger.error("Mary could not resolve the LLM config: %s", exc, exc_info=True)
            await self.transition_to(AgentState.ERROR)
            await self.send_message(self._format_error_message([str(exc)]), message_type="error")
            return

        # Reset per-run clarification state (the instance is reused across runs).
        self.phase = "review_testcases"
        self._clarify_queue = []
        self._clarifications = []

        # Resolve the single id Bob handed off + its source kind.
        selected_id, source_type = self._resolve_selection(adapter, input_data)
        is_jira = source_type == "jira" or bool(_JIRA_KEY_RE.match(selected_id))
        self._selected_source_type = "jira" if is_jira else source_type
        self._selected_id = selected_id or None

        # Jira focus → fetch the ticket live via MCP and persist it (Confluence pages
        # are already saved by Bob, so they are reused without a re-fetch).
        if is_jira and selected_id:
            await self.transition_to(AgentState.PROCESSING)
            if not await self._fetch_and_save_jira(adapter, selected_id):
                await self.transition_to(AgentState.ERROR)
                return
            selected_id = self._selected_id or selected_id

        # Surface progress before the (LLM-bound) requirement read + test-design review so
        # the step is never a silent, idle "Start" button while planning runs. Mirrors Bob;
        # the Jira branch above already transitioned to PROCESSING.
        if self.state != AgentState.PROCESSING:
            await self.transition_to(AgentState.PROCESSING)
        await self.send_message(
            "Reviewing the requirements to plan the test cases...", message_type="info"
        )

        # Read ALL requirements for the overview, then isolate the focus requirement.
        approved = self._approved_requirement_artifacts(adapter)
        focus = self._focus_artifacts(approved, selected_id)
        focus_names = {a.name for a in focus}
        self._overview_digest = self._build_overview_digest(
            [a for a in approved if a.name not in focus_names]
        )

        # Risk-based test-design clarification pass (only asks about genuine gaps).
        try:
            questions = await self._plan_test_clarifications(focus, self._overview_digest)
        except Exception as exc:
            logger.warning("Mary clarification planning failed (%s); skipping", exc)
            questions = []

        if questions:
            self.phase = "clarify"
            self._clarify_queue = questions[:_MAX_CLARIFY_QUESTIONS]
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self.send_message(
                "Before I write the test cases, let's clarify a few points so the cases "
                "are accurate and well-prioritized. Answer in your own words, or skip a "
                "question you can't answer.",
                message_type="text",
            )
            await self._ask_test_clarification(self._clarify_queue[0])
            return

        # No clarification needed → generate straight away.
        await self._generate_and_present(self._selection_input())

    def _selection_input(self) -> dict[str, Any]:
        """Pack the resolved focus id so process() narrows generation to it."""
        return {"selected_id": self._selected_id} if self._selected_id else {}

    async def _generate_and_present(self, input_data: dict[str, Any]) -> None:
        """Run generation then route to per-item review / DONE / ERROR.

        Shared exit for both the no-clarification path and the end of the clarify loop.
        """
        self.phase = "review_testcases"
        await self.transition_to(AgentState.PROCESSING)
        try:
            result = await self.process(input_data, feedback=None)
        except Exception as exc:
            logger.error("Mary agent raised error: %s", exc, exc_info=True)
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message([str(exc)]),
                message_type="error",
            )
            return

        if result.success:
            if self.test_cases:
                await self.transition_to(AgentState.REVIEW_REQUEST)
                await self._present_test_case_review()
            else:
                await self.transition_to(AgentState.DONE)
                warning = result.warnings[0] if result.warnings else "No test cases generated."
                await self.send_message(warning, message_type="warning")
        else:
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message(result.errors),
                message_type="error",
            )

    # ------------------------------------------------------------------ #
    # Requirement overview + focus resolution                            #
    # ------------------------------------------------------------------ #

    def _resolve_selection(
        self, adapter: PipelineArtifactAdapter, input_data: dict[str, Any] | None
    ) -> tuple[str, str | None]:
        """Resolve ``(selected_id, source_type)`` for the focus requirement.

        Prefers an id supplied directly in ``input_data``; otherwise falls back to the
        persisted ``mary_selected_id.json`` (which Bob stamps with the ``source_type``).
        """
        selected_id = str(input_data.get("selected_id") or "").strip() if input_data else ""
        if selected_id:
            return selected_id, None
        meta = adapter.load_metadata("mary_selected_id.json")
        if meta:
            selected_id = str(meta.get("selected_id") or "").strip()
            raw = meta.get("source_type")
            source_type = str(raw).strip() if raw else None
            return selected_id, source_type
        return "", None

    def _focus_artifacts(
        self, approved: list[PipelineArtifact], selected_id: str
    ) -> list[PipelineArtifact]:
        """Return the artifact(s) test cases are generated FOR.

        The selected id narrows to ``{selected_id}/requirement.md``; when it cannot be
        resolved, fall back to ALL approved requirements (never drafts).
        """
        if selected_id:
            target = [a for a in approved if a.name == f"{selected_id}/requirement.md"]
            if target:
                return target
        return approved

    def _build_overview_digest(
        self,
        artifacts: list[PipelineArtifact],
        *,
        per_req_chars: int = 400,
        total_chars: int = 4000,
    ) -> str:
        """Compact context block of the OTHER requirements (title + truncated body).

        Lets the generator judge the focus requirement against the whole project — a
        detail missing from it may be defined in a sibling it references. Kept SMALL on
        purpose: the focus requirement + the author's clarifications carry the detail,
        while this is just orientation. A slow on-premises model's generation latency
        scales with prompt size, so an oversized overview directly hurts responsiveness.
        """
        parts: list[str] = []
        used = 0
        for a in artifacts:
            content = (a.content or "").strip()
            if not content:
                continue
            chunk = f"=== {a.name} ===\n{content[:per_req_chars]}"
            if used + len(chunk) > total_chars:
                break
            parts.append(chunk)
            used += len(chunk)
        return "\n\n".join(parts)

    def _generation_context_block(self) -> str:
        """Assemble the extra prompt context: project overview + author clarifications.

        Reads the stored ``self._overview_digest`` (built in handle_start, excluding the
        focus) and ``self._clarifications`` so both first-pass generation and the reject
        regeneration share the same context.
        """
        blocks: list[str] = []
        app_roles = self._project_app_roles()
        if app_roles:
            blocks.append(
                "## Available roles (assign each test case's `role` to exactly one of these)\n"
                + ", ".join(app_roles)
            )
        if self._overview_digest.strip():
            blocks.append(
                "## Project Overview (other requirements in this project — context only, "
                "do not duplicate)\n" + self._overview_digest
            )
        if self._clarifications:
            blocks.append(
                "## Clarifications from the test author (authoritative — incorporate these)\n"
                + "\n\n".join(self._clarifications)
            )
        return "\n\n".join(blocks)

    # ------------------------------------------------------------------ #
    # Jira focus: fetch live via MCP (point: Jira id => Mary reads MCP)   #
    # ------------------------------------------------------------------ #

    def _load_project(self) -> Any:
        """Load the Project row from the DB; None when context/service unavailable."""
        if not self.project_context or not self.project_context.artifact_service:
            return None
        db = self.project_context.artifact_service.db
        from ai_qa.db.models import Project

        return db.get(Project, self.project_context.project_id)

    def _project_app_roles(self) -> list[str]:
        """Return the project's configured application roles (e.g. ["Admin", "User"]).

        These are the roles a test case may log in AS; they drive per-role
        sub-foldering and the clarify-loop role question. Empty list when the
        project has none configured or the project row is unavailable.
        """
        project = self._load_project()
        raw = getattr(project, "app_roles", None) if project is not None else None
        if not isinstance(raw, list):
            return []
        return [str(r).strip() for r in raw if str(r).strip()]

    def _resolve_mcp_pat(self) -> str:
        """Resolve the MCP PAT from the thread owner's encrypted secrets (UX-DR12)."""
        if (
            not self.project_context
            or not self.project_context.user_id
            or not self.project_context.artifact_service
        ):
            raise PipelineError(
                "**What happened:** Cannot resolve the MCP secret.\n\n"
                "**Why:** No active project context or storage service is available.\n\n"
                "**What to do:** Start Mary from inside an active project thread."
            )
        db = self.project_context.artifact_service.db
        mcp_pat = get_user_secret(db, self.project_context.user_id, SECRET_TYPE_MCP)
        if not mcp_pat:
            raise PipelineError(
                "**What happened:** MCP key not configured.\n\n"
                "**Why:** Reading a Jira ticket requires the MCP personal access token, "
                "but it was not found in your encrypted secret store.\n\n"
                "**What to do:** Add your MCP key in the provider configuration and try again."
            )
        return mcp_pat

    def _format_jira_markdown(self, issue: JiraIssue) -> str:
        """Render a JiraIssue to clean Markdown (only non-empty fields are emitted)."""
        lines: list[str] = [f"# [{issue.issue_key}] {issue.summary}", ""]
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
            lines += ["", "## Description", "", issue.description]
        if issue.acceptance_criteria:
            lines += ["", "## Acceptance Criteria", "", issue.acceptance_criteria]
        return "\n".join(lines)

    async def _fetch_and_save_jira(self, adapter: PipelineArtifactAdapter, ticket_id: str) -> bool:
        """Read one Jira ticket via MCP and save it as an approved requirement.

        Returns True on success; on failure sends a UX-DR12 message and returns False.
        """
        project = self._load_project()
        jira_base_url = project.jira_base_url if project else None
        await self.send_message(f"Reading Jira ticket {ticket_id} via MCP...", "info")
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
            logger.error("Mary failed to read Jira ticket %s: %s", ticket_id, exc, exc_info=True)
            await self.send_message(
                content=(
                    "**What happened:** Could not read the Jira ticket.\n\n"
                    f"**Why:** {type(exc).__name__} while contacting the MCP server.\n\n"
                    "**What to do:** Check the ticket id and your connection, then start again."
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

        issue: JiraIssue = result.data
        try:
            adapter.save_requirement(
                page_id=issue.issue_key,
                markdown=self._format_jira_markdown(issue),
                source_type="jira",
                source_url=issue.url,
                warnings=[],
                title=f"[{issue.issue_key}] {issue.summary}",
            )
            adapter.delete_draft_requirement(issue.issue_key)
        except Exception as exc:
            logger.error(
                "Mary failed to save Jira requirement %s: %s", ticket_id, exc, exc_info=True
            )
            await self.send_message(
                content=(
                    "**What happened:** Failed to save the Jira requirement.\n\n"
                    f"**Why:** {type(exc).__name__} while writing the artifact.\n\n"
                    "**What to do:** Please start again."
                ),
                message_type="error",
            )
            return False

        # Align the focus id with the saved artifact name segment ({issue_key}/...).
        self._selected_id = issue.issue_key
        await self.send_message(f"✓ Loaded Jira ticket {issue.issue_key}", "info")
        return True

    # ------------------------------------------------------------------ #
    # Risk-based test-design clarification loop (point 5)                #
    # ------------------------------------------------------------------ #

    async def _plan_test_clarifications(
        self, focus: list[PipelineArtifact], overview: str
    ) -> list[str]:
        """One LLM pass over the focus requirement → list of clarification questions.

        Uses the Master Test Architect / risk-based lens to surface only genuine gaps
        (ambiguous AC/expected results, undefined preconditions or test data, unclear
        risk/priority, ambiguous UI controls, missing NFR thresholds). Returns [] when
        nothing needs clarifying, or on any LLM/parse failure (the caller also guards).
        """
        if not focus:
            return []
        focus_md = "\n\n".join(f"=== {a.name} ===\n{(a.content or '')[:6000]}" for a in focus)
        app_roles = self._project_app_roles()
        role_hint = ""
        if app_roles:
            role_hint = (
                "This project defines these application roles a test logs in AS: "
                + ", ".join(app_roles)
                + ". If the focus requirement does not make clear which of these role(s) "
                "each scenario should be exercised as, ASK which role(s) apply (this is a "
                "genuine gap — different roles use different test accounts). Otherwise do "
                "not ask about roles.\n\n"
            )
        prompt = (
            "You are a Master Test Architect about to write browser-automation test "
            "cases for the FOCUS requirement(s) below, using risk-based test design. "
            "Read the focus requirement together with the project overview. List ONLY "
            "the points that are genuinely unclear or missing and that would materially "
            "lower the quality or correctness of the test cases — for example: ambiguous "
            "or missing acceptance criteria / expected results, undefined preconditions "
            "or test data, unclear risk or priority (what is most critical to test), "
            "ambiguous UI controls, or missing non-functional thresholds. Do NOT ask "
            "about anything already answered in the project overview, and do NOT ask "
            "generic questions.\n\n" + role_hint + "FOCUS REQUIREMENT(S):\n" + focus_md + "\n\n"
            "PROJECT OVERVIEW (context — never ask about anything answered here):\n"
            + (overview or "(none)")
            + "\n\n"
            f"Output one question per line starting with '- ', at most "
            f"{_MAX_CLARIFY_QUESTIONS} questions, each concise and specific to this "
            f"feature. Write the questions in {self._get_conversation_language()} language. If nothing genuinely needs clarification, output exactly: "
            f"{_NO_CLARIFICATION_SENTINEL}\nOutput only the questions (or the sentinel)."
        )
        client = LLMClient(self.config)
        resp = await asyncio.wait_for(
            client._chat_model.ainvoke([HumanMessage(content=prompt)]),
            timeout=_CLARIFY_LLM_TIMEOUT,
        )
        return self._parse_clarification_questions(str(resp.content))

    @staticmethod
    def _parse_clarification_questions(text: str) -> list[str]:
        """Parse one-question-per-line output → list; sentinel/blank → []."""
        if _NO_CLARIFICATION_SENTINEL in text.upper():
            return []
        questions: list[str] = []
        for raw_line in text.splitlines():
            cleaned = re.sub(r"^[-*\d.)\s]+", "", raw_line.strip()).strip()
            if len(cleaned) > 3:
                questions.append(cleaned)
        return questions[:_MAX_CLARIFY_QUESTIONS]

    async def _ask_test_clarification(self, question: str) -> None:
        """Emit one clarification question with a Mary-specific metadata envelope."""
        await self.send_message(
            content=question,
            message_type="text",
            metadata={
                "type": "test_clarify_request",
                "requirement_id": self._selected_id or "",
                "remaining": len(self._clarify_queue),
            },
        )

    async def _handle_test_clarify_answer(self, data: dict[str, Any] | None) -> None:
        """Apply the author's answer/skip for the current question, then advance."""
        payload = data or {}
        action = str(payload.get("action") or "clarify_answer")

        if not self._clarify_queue:
            await self._generate_and_present(self._selection_input())
            return

        question = self._clarify_queue[0]
        if action == "skip":
            await self.send_message("Skipped that question.", "info")
        else:
            answer = str(payload.get("answer") or "").strip()
            if not answer:
                await self.send_message("Please type an answer, or use Skip.", "error")
                return
            self._clarifications.append(f"Q: {question}\nA: {answer}")
            await self.send_message("Got it — noted for the test cases.", "info")

        self._clarify_queue = self._clarify_queue[1:]
        if self._clarify_queue:
            await self._ask_test_clarification(self._clarify_queue[0])
        else:
            await self.send_message(
                "Thanks. Generating the test cases now with your input.", "info"
            )
            await self._generate_and_present(self._selection_input())

    async def process(
        self,
        input_data: dict[str, Any],
        feedback: str | None = None,
    ) -> StageResult:
        """Generate test cases from requirements.

        Args:
            input_data: Carries ``selected_id`` (the single Confluence page id or
                Jira ticket id Bob handed off). Falls back to the persisted
                ``mary_selected_id.json`` configuration artifact.
            feedback: User rejection feedback for re-processing

        Returns:
            StageResult with generated test cases
        """
        try:
            if self.project_context is None:
                raise ValueError("MaryAgent requires an active project context.")

            # Resolve the LLM config against the attached context before any LLM call
            # (the extractor captured an empty key at construction time — see
            # _ensure_llm_ready). Safe to repeat when already resolved by handle_start.
            self._ensure_llm_ready()

            adapter = PipelineArtifactAdapter(self.project_context)

            # Resolve the single id Bob selected: input_data first, then the
            # persisted configuration artifact (authoritative, survives reloads).
            selected_id = str(input_data.get("selected_id") or "").strip() if input_data else ""
            if not selected_id:
                meta = adapter.load_metadata("mary_selected_id.json")
                if meta:
                    selected_id = str(meta.get("selected_id") or "").strip()

            # AC1: only APPROVED requirements feed generation. Drafts ({page_id}.md,
            # source_type NULL) are excluded BEFORE any selected_id narrowing so the
            # fallback-to-all path can never include a draft.
            approved_artifacts = self._approved_requirement_artifacts(adapter)
            requirement_artifacts = approved_artifacts

            # Scope generation to the chosen requirement when resolvable. (Feeding the
            # full Confluence set as additional context is a later Epic 12.2 concern.)
            if selected_id:
                target = [
                    a for a in approved_artifacts if a.name == f"{selected_id}/requirement.md"
                ]
                if target:
                    requirement_artifacts = target
                else:
                    # Fall back to all APPROVED requirements (never drafts).
                    requirement_artifacts = approved_artifacts
                    await self.send_message(
                        f"Selected id '{selected_id}' was not found among saved "
                        "requirements; generating from all requirements instead.",
                        message_type="warning",
                    )

            requirements_files = self._materialize_requirement_artifacts(requirement_artifacts)
            missing_warning = "No requirement artifacts found for this project"

            if not requirements_files:
                return StageResult(
                    success=True,
                    data=[],
                    errors=[],
                    warnings=[missing_warning],
                    confidence=1.0,
                )

            # Send progress updates
            await self.send_message(
                f"Found {len(requirements_files)} requirement(s) to process",
                message_type="info",
            )

            # Build per-artifact source attribution list (parallel to requirements_files)
            # Materialization preserves order: artifact[i] → requirements_files[i]
            sources = [
                RequirementSource(
                    id=str(artifact.id),
                    name=artifact.name,
                    url=artifact.source_url or "",
                    warnings=artifact.warnings,
                )
                for artifact in requirement_artifacts
            ]

            # Build the extra prompt context: a project overview of the OTHER
            # requirements (so generation sees cross-requirement context) plus any
            # clarification answers the author gave in the test-design loop. handle_start
            # normally fills the overview; populate it here too for direct entry.
            if not self._overview_digest:
                focus_names = {a.name for a in requirement_artifacts}
                self._overview_digest = self._build_overview_digest(
                    [a for a in approved_artifacts if a.name not in focus_names]
                )
            generation_context = self._generation_context_block()
            source_urls = [s.url or "" for s in sources]

            # Stream generation so each test case is SAVED to the Test Cases folder and
            # reported the moment it finishes — instead of one opaque multi-minute call.
            # On the slow on-prem model the first case lands in ~1 min, then a steady
            # trickle, each visible + persisted as it arrives.
            used_names: set[str] = self._get_existing_test_case_bases()
            streamed: list[TestCase] = []

            async def _on_streamed_case(tc: TestCase) -> None:
                streamed.append(tc)
                position = len(streamed)
                try:
                    # Persist as a DRAFT: visible in the Test Cases folder for live
                    # progress, but excluded from Sarah's loaders until the user approves
                    # (approval re-saves the same name without the draft marker).
                    self._persist_test_case(adapter, tc, position, used_names, source_type="draft")
                except Exception as exc:
                    logger.error("Failed to save streamed test case: %s", exc, exc_info=True)
                    await self.send_message(
                        f"⚠ Generated '{tc.title}' but couldn't save it yet — "
                        "it will be saved when you approve.",
                        message_type="warning",
                    )
                    return
                await self.send_message(
                    f"✓ Test case {position}: {tc.title} — saved to Test Cases.",
                    message_type="info",
                )

            result = await self.extractor.extract_streaming(
                requirements_files,
                source_urls,
                sources=sources,
                context=generation_context,
                on_case=_on_streamed_case,
            )

            if not result.success:
                return result

            # Store generated test cases (in requirement order = grouped by source)
            self.test_cases = result.data or []

            # Emit grouping summary so the user can see how cases map to requirements (AC3)
            if self.test_cases:
                groups: dict[str, int] = {}
                for tc in self.test_cases:
                    key = tc.source_requirement_name or "Unknown"
                    groups[key] = groups.get(key, 0) + 1
                group_summary = ", ".join(f"{name}: {count}" for name, count in groups.items())
                await self.send_message(
                    f"Generated {len(self.test_cases)} test case(s) across "
                    f"{len(requirement_artifacts)} requirement(s): {group_summary}",
                    message_type="info",
                )

                # AC2: warn about low-confidence cases that need explicit review
                low_count = sum(1 for tc in self.test_cases if tc.confidence_level == "low")
                if low_count > 0:
                    await self.send_message(
                        f"⚠ {low_count} of {len(self.test_cases)} test case(s) are low confidence "
                        "and need explicit review before proceeding to Sarah.",
                        message_type="warning",
                    )

            # Reset review index and decisions
            self.current_review_index = 0
            self._reviewed_indices = set()

            return StageResult(
                success=True,
                data=self.test_cases,
                errors=[],
                warnings=result.warnings,
                confidence=result.confidence,
            )

        except Exception as e:
            logger.error(f"Error in Mary agent process: {e}")
            return StageResult(
                success=False,
                data=None,
                errors=[f"Failed to generate test cases: {e}"],
                warnings=[],
                confidence=0.0,
            )

    def _resolve_index(self, data: dict[str, Any] | None) -> int:
        """Resolve a client-supplied ``test_case_index`` defensively (C31/C33).

        A non-numeric/None/list value (or an out-of-range index) falls back to
        ``current_review_index`` instead of raising, then the result is re-clamped
        into ``[0, len-1]``. Caller must guard the empty-list case separately.
        """
        index = self.current_review_index
        if data and "test_case_index" in data:
            raw = data["test_case_index"]
            if isinstance(raw, bool):
                raw = None
            if isinstance(raw, int):
                index = raw
            elif isinstance(raw, str):
                try:
                    index = int(raw.strip())
                except ValueError:
                    index = self.current_review_index
            else:
                index = self.current_review_index
        if not (0 <= index < len(self.test_cases)):
            index = self.current_review_index
        # Re-clamp: current_review_index may itself be out of range (e.g. == len).
        return min(max(index, 0), len(self.test_cases) - 1)

    async def handle_approve(self, data: dict[str, Any] | None = None) -> None:
        """Handle approval — routed by phase.

        During the test-design clarification loop (``phase == "clarify"``) an "approve"
        carries the author's answer (or a skip) for the current question. Otherwise it
        is a per-item test-case approval (the original behaviour), addressed by an
        optional ``test_case_index`` and defaulting to the current positional index.
        """
        if self.phase == "clarify":
            await self._handle_test_clarify_answer(data)
            return

        if not self.test_cases:
            return
        index = self._resolve_index(data)

        # Stamp approval metadata on the approved case (AC2)
        if self.project_context is not None:
            tc = self.test_cases[index]
            tc.approved_by = self.project_context.user_email or str(self.project_context.user_id)
            tc.approved_at = datetime.now(UTC).isoformat()

        # Record this index as explicitly reviewed (AC3 guard — authoritative for DONE)
        self._reviewed_indices.add(index)
        # Keep positional pointer in sync for back-compat and single-case flow
        self.current_review_index = index + 1

        # DONE only when every test case has been reviewed AND every low-confidence
        # case has an explicit decision. The low-confidence guard gates BEFORE
        # completion (C32 — it must stay reachable; the all-reviewed counter alone
        # cannot prove the low cases specifically were among the reviewed indices
        # because _reviewed_indices may carry stale/extra entries).
        skipped = self._unresolved_low_confidence_indices()
        all_reviewed = len(self._reviewed_indices) >= len(self.test_cases)
        if skipped:
            self.current_review_index = skipped[0]
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self._present_test_case_review()
            return
        if all_reviewed:
            saved_ok = await self._write_approved_test_cases()
            if not saved_ok:
                # AC3: do NOT mark approved/available; stay reviewable so re-approve retries.
                await self.send_message(
                    content=(
                        "**What happened:** Failed to save the approved test cases to the "
                        "project artifact store.\n\n"
                        "**Why:** An error occurred while writing the artifacts.\n\n"
                        "**What to do:** Please approve again to retry — saving is "
                        "idempotent, so no duplicates are created."
                    ),
                    message_type="error",
                )
                # Clamp the display index back into range (C34): current_review_index
                # was advanced to index+1 which may equal len, so the re-presented card
                # would otherwise render "No test case to review." with the list attached.
                self.current_review_index = min(
                    max(self.current_review_index, 0), len(self.test_cases) - 1
                )
                await self.transition_to(AgentState.REVIEW_REQUEST)
                await self._present_test_case_review()
                return

            await self.transition_to(AgentState.DONE)
            await self.send_message(
                f"{len(self.test_cases)} test cases saved to project artifacts",
                message_type="success",
            )
        else:
            # C36: point the card at the first still-unreviewed case so the user is
            # taken to remaining work; keep it in range.
            remaining = sorted(set(range(len(self.test_cases))) - self._reviewed_indices)
            if remaining:
                self.current_review_index = remaining[0]
            else:
                self.current_review_index = min(
                    max(self.current_review_index, 0), len(self.test_cases) - 1
                )
            # Re-present the full list so the client card stays in sync
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self._present_test_case_review()

    def _unresolved_low_confidence_indices(self) -> list[int]:
        """Return indices of low-confidence cases not yet in _reviewed_indices (AC3 guard)."""
        return [
            i
            for i, tc in enumerate(self.test_cases)
            if tc.confidence_level == "low" and i not in self._reviewed_indices
        ]

    async def handle_reject(self, feedback: str, data: dict[str, Any] | None = None) -> None:
        """Handle rejection of a test case with feedback.

        Accepts an optional ``test_case_index`` in data for client-driven navigation;
        defaults to the current positional index for back-compat.

        Args:
            feedback: User rejection feedback
            data: Optional payload; may carry ``test_case_index``.
        """
        if not self.test_cases:
            return
        index = self._resolve_index(data)

        # AC3 / C2: a reject ALWAYS invalidates the prior decision for this case,
        # regardless of whether regeneration later succeeds. Clear the reviewed flag
        # and any prior approval stamp up front so the rejected output can never be
        # carried into the approved set without a fresh, explicit re-approval.
        self._reviewed_indices.discard(index)
        rejected_tc = self.test_cases[index]
        rejected_tc.approved_by = None
        rejected_tc.approved_at = None
        self.current_review_index = index

        # Paraphrase feedback in acknowledgment (UX-DR12)
        await self.send_message(
            f"I'll revise the test case to address your feedback: '{feedback}'",
            message_type="text",
        )

        # Re-generate current test case with feedback
        await self.transition_to(AgentState.PROCESSING)

        # Re-generate the current test case using its source requirement for attribution
        try:
            if self.project_context is None:
                raise ValueError("MaryAgent requires an active project context.")

            # Resolve the LLM config against the attached context before regenerating.
            self._ensure_llm_ready()

            source_requirement_id = rejected_tc.source_requirement_id

            # C12+C13: scope regeneration to the single rejected requirement. Without an
            # identifiable source we must NOT overwrite this index with an unrelated case.
            if not source_requirement_id:
                await self.send_message(
                    self._format_error_message(
                        [
                            "This test case has no identifiable source requirement, so it "
                            "cannot be regenerated automatically."
                        ]
                    ),
                    message_type="error",
                )
                await self.transition_to(AgentState.REVIEW_REQUEST)
                await self._present_test_case_review()
                return

            requirement_artifacts = [
                a
                for a in PipelineArtifactAdapter(self.project_context).load_requirement_markdown()
                if str(a.id) == source_requirement_id
            ]

            requirements_files = self._materialize_requirement_artifacts(requirement_artifacts)

            regenerated_cases: list[TestCase] = []
            if requirements_files:
                # Build sources for re-generation, preserving source warnings for re-scoring
                sources = [
                    RequirementSource(
                        id=str(a.id),
                        name=a.name,
                        url=a.source_url or "",
                        warnings=a.warnings,
                    )
                    for a in requirement_artifacts
                ]
                source_urls = [s.url or "" for s in sources]
                # Regeneration reuses streaming for consistency; no on_case here — a
                # rejected case is refined in place and persisted on approval, not saved
                # incrementally.
                result = await self.extractor.extract_streaming(
                    requirements_files,
                    source_urls,
                    sources=sources,
                    context=self._generation_context_block(),
                )
                if result.success and result.data:
                    regenerated_cases = result.data

            if not regenerated_cases:
                # Failed/empty regeneration (C2): keep the case un-reviewed, surface a
                # UX-DR12 retry message, stay in REVIEW_REQUEST so the user can retry.
                await self.send_message(
                    self._format_error_message(
                        [
                            "I could not regenerate this test case from its source "
                            "requirement. Please reject again to retry, or adjust the "
                            "requirement in Bob."
                        ]
                    ),
                    message_type="error",
                )
                await self.transition_to(AgentState.REVIEW_REQUEST)
                await self._present_test_case_review()
                return

            for regenerated in regenerated_cases:
                # Stamp the source so the replacement group stays attributable + re-rejectable
                regenerated.source_requirement_id = source_requirement_id
                # Clear any approval stamp — AC3: rejected output is never approved.
                regenerated.approved_by = None
                regenerated.approved_at = None

            if len(regenerated_cases) == 1:
                # Single replacement maps 1:1 onto the rejected index.
                self.test_cases[index] = regenerated_cases[0]
            else:
                # Multiple cases for this source requirement → replace the WHOLE group.
                self._replace_source_group(source_requirement_id, regenerated_cases)

            # Re-present the full review list so the client card refreshes
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self._present_test_case_review()

        except Exception as e:
            logger.error(f"Error re-generating test case: {e}")
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                f"Failed to regenerate test case: {e}",
                message_type="error",
            )

    def _replace_source_group(
        self, source_requirement_id: str, replacements: list[TestCase]
    ) -> None:
        """Replace every test case for one source requirement with ``replacements`` (C13).

        Removes the old group in place, inserts the regenerated cases at the position of
        the first removed case (so grouping/contiguity is preserved), and rebuilds
        ``_reviewed_indices`` so reviewed flags survive the reindex for every other case
        while the regenerated group is left un-reviewed (fresh decision required).
        """
        old_reviewed_keep: set[int] = set()
        new_cases: list[TestCase] = []
        insert_at: int | None = None
        for old_index, tc in enumerate(self.test_cases):
            if tc.source_requirement_id == source_requirement_id:
                if insert_at is None:
                    insert_at = len(new_cases)
                continue
            # Carry forward the reviewed flag under the case's NEW index.
            if old_index in self._reviewed_indices:
                old_reviewed_keep.add(len(new_cases))
            new_cases.append(tc)

        if insert_at is None:
            insert_at = len(new_cases)
        # Shift kept reviewed indices that sit at/after the insertion point.
        shifted = {(i + len(replacements) if i >= insert_at else i) for i in old_reviewed_keep}
        new_cases[insert_at:insert_at] = replacements

        self.test_cases = new_cases
        self._reviewed_indices = shifted  # regenerated group intentionally absent
        self.current_review_index = min(insert_at, len(self.test_cases) - 1)

    def _format_review_content(self, result: StageResult) -> str:
        """Format test case for review display.

        Args:
            result: StageResult with test case data

        Returns:
            Formatted markdown string with test case structure
        """
        if not self.test_cases:
            return "No test case to review."

        # Clamp the display index into range (C34). current_review_index may be == len
        # (advanced past the last case) when the full list is still attached — render the
        # last case rather than "No test case to review."
        display_index = min(max(self.current_review_index, 0), len(self.test_cases) - 1)
        test_case = self.test_cases[display_index]
        total = len(self.test_cases)
        current = display_index + 1

        # Format test case with clear structure
        content = f"## Test Case {current} of {total}: {test_case.title}\n\n"

        # Confidence line (AC2 — causes shown to reviewer)
        if test_case.confidence_level is not None:
            level_emoji = {"high": "✅", "medium": "⚠", "low": "🔴"}.get(
                test_case.confidence_level, "?"
            )
            score_str = f"{test_case.confidence:.2f}" if test_case.confidence is not None else "?"
            content += f"**Confidence:** {level_emoji} {test_case.confidence_level.upper()} ({score_str})\n\n"
            if test_case.confidence_rationale:
                content += "**Why this score:**\n"
                for reason in test_case.confidence_rationale:
                    content += f"- {reason}\n"
                content += "\n"

        if test_case.objective:
            content += f"**Objective:** {test_case.objective}\n\n"

        if test_case.source_requirement_name:
            source_ref = test_case.source_requirement_name
            if test_case.source_url:
                source_ref += f" ({test_case.source_url})"
            content += f"**Source Requirement:** {source_ref}\n\n"

        if test_case.test_data:
            content += "**Test Data:**\n"
            for item in test_case.test_data:
                content += f"- {item}\n"
            content += "\n"

        if test_case.preconditions:
            content += "**Preconditions:**\n"
            for i, precond in enumerate(test_case.preconditions, start=1):
                content += f"{i}. {precond}\n"
            content += "\n"

        if test_case.steps:
            content += "**Steps:**\n"
            for step in test_case.steps:
                content += f"{step.number}. {step.action} (target: {step.target})"
                if step.data:
                    content += f" - Data: {step.data}"
                content += "\n"
            content += "\n"

        if test_case.expected_results:
            content += "**Expected Results:**\n"
            for i, expected_result in enumerate(test_case.expected_results, start=1):
                content += f"{i}. {expected_result}\n"
            content += "\n"

        if test_case.automation_hints:
            content += "**Automation Hints:**\n"
            for hint in test_case.automation_hints:
                content += f"- {hint}\n"
            content += "\n"

        if test_case.warnings:
            content += "**⚠ Warnings:**\n"
            for warning in test_case.warnings:
                content += f"- {warning}\n"
            content += "\n"

        return content

    def _review_case_payload(self, tc: TestCase) -> dict[str, Any]:
        """One review-panel entry: the test case AS MARKDOWN + review-only chrome.

        QA reviews the rendered Markdown document (the same body that is stored and fed to
        Sarah) — no structured-JSON test case is sent. Only review metadata that lives
        *outside* the test case itself (confidence band/score/rationale, the warnings that
        drove it, approval timestamp) rides alongside so the panel can show its badge and
        track resolved state.
        """
        return {
            "title": tc.title,
            "markdown": tc.to_markdown(),
            "confidence": tc.confidence,
            "confidence_level": tc.confidence_level,
            "confidence_rationale": tc.confidence_rationale,
            "warnings": tc.warnings,
            "approved_at": tc.approved_at,
        }

    async def _present_test_case_review(self) -> None:
        """Emit the full test-case list in one payload so the client can drive navigation.

        Metadata type ``test_case_review`` carries each case AS MARKDOWN; the frontend
        MaryReviewPanel renders the Markdown and owns Prev/Next + per-case approve/reject
        (index-addressed).
        """
        if not self.test_cases:
            return

        low_confidence_count = sum(1 for tc in self.test_cases if tc.confidence_level == "low")
        # C36: surface which indices are still unreviewed (set difference vs range(len))
        # so a re-presented payload tells the client exactly what work remains. Filtered
        # to in-range indices so stale/extra entries in _reviewed_indices cannot leak.
        in_range = set(range(len(self.test_cases)))
        reviewed_in_range = sorted(self._reviewed_indices & in_range)
        remaining_indices = sorted(in_range - self._reviewed_indices)
        # Carrier content is a short, non-empty line (the verbose per-case dump is gone):
        # the panel renders the Markdown, and the chat bubble for this carrier is hidden.
        active_index = min(max(self.current_review_index, 0), len(self.test_cases) - 1)
        content = f"Review test case {active_index + 1} of {len(self.test_cases)}."
        await self.send_message(
            content,
            message_type="text",
            metadata={
                "type": "test_case_review",
                "test_cases": [self._review_case_payload(tc) for tc in self.test_cases],
                "low_confidence_count": low_confidence_count,
                "reviewed_indices": reviewed_in_range,
                "remaining_indices": remaining_indices,
                "active_index": active_index,
            },
        )

    async def _present_current_test_case(self) -> None:
        """Back-compat wrapper — delegates to the full-list review payload."""
        await self._present_test_case_review()

    def _unique_artifact_base(self, tc: TestCase, position: int, used_names: set[str]) -> str:
        """Return a stable, batch-unique base filename for a test case (C5/C14).

        ``TestCase.filename`` is a kebab-case slug of the title; it is empty when the
        title has no alphanumerics, and two cases can share a slug. Guard the empty case
        (so the name is never just ``.md``) and append a stable discriminator —
        ``source_requirement_id`` when available, otherwise the 1-based batch position —
        when the slug is empty or already used in THIS batch.
        """
        base = tc.filename or f"test-case-{position}"
        if base in used_names:
            suffix = tc.source_requirement_id or str(position)
            base = f"{base}-{suffix}"
            # In the rare event the discriminated name still collides, fall back to
            # the unconditionally-unique batch position.
            while base in used_names:
                base = f"{base}-{position}"
        used_names.add(base)
        return base

    def _persist_test_case(
        self,
        adapter: PipelineArtifactAdapter,
        tc: TestCase,
        position: int,
        used_names: set[str],
        source_type: str | None = None,
    ) -> UUID:
        """Save one test case as LLM-friendly **Markdown** to the Test Cases folder.

        The Markdown body (``{base}.md``, via ``TestCase.to_markdown``) is the single
        persisted representation — what the Test Cases folder shows and what Sarah feeds,
        as natural language, to the script-generation LLM. No parallel JSON copy is kept;
        ``TestCase.from_markdown`` reconstructs the typed object on demand downstream.

        Idempotent-by-name via the adapter; used both for incremental save during
        streaming generation (``source_type="draft"`` — kept out of Sarah's input) and
        for the all-or-nothing batch save on approval (``source_type=None`` — the
        approved, Sarah-visible copy, which supersedes the same-named draft). Returns the
        saved artifact id.
        """
        base_name = self._unique_artifact_base(tc, position, used_names)
        artifact_name = f"{base_name}.md"
        artifact = adapter.save_test_case(
            artifact_name,
            tc.to_markdown(),
            source_type=source_type,
            source_url=tc.source_url,
            warnings=[{"message": w} for w in tc.warnings] if tc.warnings else None,
            # Persist the human-readable title so the Test Cases tree shows each case's
            # own name (e.g. "Verify attribution is recorded") instead of falling back to
            # the role-folder segment — which made every case under one role look identical.
            title=(tc.title or None),
        )
        return artifact.id

    async def _write_approved_test_cases(self) -> bool:
        """Persist all approved test cases. All-or-nothing within the batch (AC3).

        Returns True when every test case saved successfully. On any failure, best-effort
        deletes every artifact committed in this batch so no partial set is left available
        to Sarah, then returns False.
        """
        if self.project_context is None:
            raise ValueError("MaryAgent requires an active project context.")
        adapter = PipelineArtifactAdapter(self.project_context)
        saved_ids: list[UUID] = []
        used_names: set[str] = self._get_existing_test_case_bases()
        try:
            for position, tc in enumerate(self.test_cases, start=1):
                saved_ids.append(self._persist_test_case(adapter, tc, position, used_names))
            # Each approved copy (no draft marker) superseded its same-named streaming
            # draft; sweep any DRAFT test cases still left over (rejected-then-regenerated
            # with a new title, or an abandoned earlier stream) so none linger in the
            # folder or reach Sarah.
            self._delete_orphan_draft_test_cases()
            return True
        except Exception as exc:
            logger.error("Failed to save approved test cases: %s", exc, exc_info=True)
            # AC3: all-or-nothing — remove anything saved in THIS batch so no partial
            # set is left available to Sarah. delete is best-effort; save_test_case is
            # idempotent-by-name so a retry still converges if a rollback delete fails.
            artifact_service = self.project_context.artifact_service
            project_id = self.project_context.project_id
            if artifact_service is not None and project_id is not None:
                for artifact_id in saved_ids:
                    try:
                        artifact_service.delete_artifact(
                            project_id=project_id, artifact_id=artifact_id
                        )
                    except Exception:
                        logger.warning(
                            "Rollback delete failed for test case artifact %s", artifact_id
                        )
            return False

    def _delete_orphan_draft_test_cases(self) -> None:
        """Best-effort removal of leftover ``source_type="draft"`` test cases.

        Streaming saves each case as a draft; approval re-saves it (no draft marker),
        superseding the same-named draft. Any test-case artifact still marked ``draft``
        afterward is an orphan (rejected-then-regenerated under a new name, or an earlier
        abandoned stream). Never raises — cleanup failure must not fail the approval.
        """
        if self.project_context is None or self.project_context.artifact_service is None:
            return
        project_id = self.project_context.project_id
        if project_id is None:
            return
        service = self.project_context.artifact_service
        try:
            artifacts = list(service.list_artifacts(project_id=project_id, kind="testcase"))
        except Exception:
            return
        for art in artifacts:
            if getattr(art, "source_type", None) == "draft":
                try:
                    service.delete_artifact(project_id=project_id, artifact_id=art.id)
                except Exception:
                    logger.warning("Could not delete orphan draft test case %s", art.id)

    def _get_existing_test_case_bases(self) -> set[str]:
        """Return the set of existing test case base names for collision resolution."""
        bases: set[str] = set()
        if self.project_context is None or self.project_context.artifact_service is None:
            return bases
        project_id = self.project_context.project_id
        if project_id is None:
            return bases
        try:
            artifacts = list(
                self.project_context.artifact_service.list_artifacts(
                    project_id=project_id, kind="testcase"
                )
            )
            for art in artifacts:
                if art.name and art.name.endswith(".md"):
                    # Extract the base name, ignoring any legacy role folders
                    base = art.name.split("/")[-1][:-3]
                    bases.add(base)
        except Exception:
            logger.warning("Could not list existing test cases for collision resolution")
        return bases

    def _materialize_requirement_artifacts(
        self, requirement_artifacts: list[PipelineArtifact]
    ) -> list[Path]:
        """Create temporary markdown files for extractor compatibility."""
        temp_dir = Path(tempfile.mkdtemp(prefix="aiqa-requirements-"))
        materialized: list[Path] = []
        for index, artifact in enumerate(requirement_artifacts, start=1):
            path = temp_dir / f"requirement-{index:03d}.md"
            path.write_text(artifact.content, encoding="utf-8")
            materialized.append(path)
        return materialized
