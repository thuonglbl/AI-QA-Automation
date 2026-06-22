"""Jack agent - Test execution & reporting (step 5).

Story 14.1 built the **input-selection gate** (load approved scripts, thread-prioritised,
confirm-before-execute). Story 14.2 fills the execution tail: after the user confirms the
script set + a target environment URL, Jack runs the scripts in a controlled subprocess
(``script_runner.run_scripts`` via ``asyncio.to_thread``), persists per-test
``TestExecutionResult`` rows + a run summary on ``AgentRun.execution_metadata``, and lands
in REVIEW_REQUEST with an ``execution_summary`` message.

Lifecycle::

    handle_start
      → reset per-run state
      → _check_preconditions()        (project context)                 [AC3 gate #0]
      → load_approved_scripts()       (project-scoped, thread-first)     [14.1 AC1/AC2]
          → [] → AC3 block message, stay START                          [14.1 AC3]
          → present script_selection (REVIEW_REQUEST)                    [14.1 AC2]

    handle_approve (phase dispatch)
      → phase == "input_selection" → _confirm_inputs(data)
            → confirmed_scripts = selected subset                       [14.1]
            → target_url resolved (env pick / URL); none → BLOCK        [14.2 AC1]
            → phase = "execution" → _begin_execution()
                  PROCESSING → process() runs the runner subprocess     [14.2 AC1/AC2]
                  persist TestExecutionResult rows + run summary        [14.2 AC3]
                  REVIEW_REQUEST + execution_summary message
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any
from uuid import UUID

from ai_qa.agents.base import AgentState, BaseAgent
from ai_qa.artifacts.storage import role_to_folder
from ai_qa.config import AppSettings
from ai_qa.db.models import TestExecutionResult
from ai_qa.models import StageResult
from ai_qa.pipelines.artifact_adapter import PipelineArtifact, PipelineArtifactAdapter
from ai_qa.pipelines.execution_report import attachment_key, compose_execution_report
from ai_qa.pipelines.script_runner import (
    BrowserSpec,
    ProducedFile,
    RunResult,
    RunSummary,
    ScriptToRun,
    TestResult,
    browser_spec_from_label,
    run_scripts,
)
from ai_qa.sessions.service import list_session_status, resolve_storage_state
from ai_qa.threads.models import AgentRun

logger = logging.getLogger(__name__)

# Number of leading script lines surfaced as the panel preview.
_PREVIEW_LINES = 20


def _merge_run_results(groups: list[RunResult]) -> RunResult:
    """Merge per-role-group :class:`RunResult`\\ s into one (Slice 6).

    Each group ran its own role's scripts under that role's session; this concatenates the
    per-test results + produced files and sums the run-level summary so the persistence /
    report / summary-message path stays single-``RunResult``. A single group passes through
    unchanged (the common single-session path).
    """
    if len(groups) == 1:
        return groups[0]

    all_results: list[TestResult] = []
    produced: list[ProducedFile] = []
    browsers: list[str] = []
    unavailable: list[dict[str, str]] = []
    for rr in groups:
        all_results.extend(rr.results)
        produced.extend(rr.produced_files)
        for b in rr.summary.browsers:
            if b not in browsers:
                browsers.append(b)
        for u in rr.summary.unavailable_browsers:
            if u not in unavailable:
                unavailable.append(u)

    first = groups[0].summary
    summary = RunSummary(
        total=sum(g.summary.total for g in groups),
        passed=sum(g.summary.passed for g in groups),
        failed=sum(g.summary.failed for g in groups),
        errors=sum(g.summary.errors for g in groups),
        skipped=sum(g.summary.skipped for g in groups),
        duration_ms=sum(g.summary.duration_ms for g in groups),
        browsers=browsers,
        base_url_host=first.base_url_host,
        run_policy=first.run_policy,
        started_at=min(g.summary.started_at for g in groups),
        completed_at=max(g.summary.completed_at for g in groups),
        unavailable_browsers=unavailable,
    )
    return RunResult(
        results=all_results,
        summary=summary,
        produced_files=produced,
        stdout_tail=groups[0].stdout_tail,
        stderr_tail=groups[0].stderr_tail,
    )


class JackAgent(BaseAgent):
    """Jack - Execute approved Playwright scripts and report results.

    Input selection (14.1) needs no LLM. Execution (14.2) runs pre-generated pytest +
    pytest-playwright scripts in an isolated subprocess; results persist as structured
    rows. Browser is ``chromium`` in 14.2 (multi-browser is Story 14.4).
    """

    def __init__(
        self,
        name: str = "Jack",
        color: str = "#F97316",  # Orange — matches frontend AGENTS.Jack.color
        step_number: int = 5,
        step_title: str = "Run Tests",
        workspace_dir: Path | None = None,
    ) -> None:
        """Initialize Jack agent.

        All-default args so ``_clone_agent_for_workspace``'s no-arg ``agent_class()``
        construction works (mirrors Sarah). No LLM/generator — state fields only.
        """
        super().__init__(name, color, step_number, step_title, workspace_dir)

        # Input-selection gate state (14.1)
        self.phase: str = "input_selection"
        self.candidate_scripts: list[PipelineArtifact] = []
        self.confirmed_scripts: list[PipelineArtifact] = []
        # Execution context (14.2/14.4): resolved target URL + env/role + browser matrix.
        self._target_url: str | None = None
        self._environment: str = ""
        self._role: str = ""
        self._browser_labels: list[str] = ["chromium"]
        # Captured-session storageState (live credential) — held only between confirm and
        # the run, then cleared. Never persisted/logged/messaged.
        self._storage_state: dict[str, Any] | None = None
        # Role-grouped run plan (Slice 6): scripts grouped by the role they run AS, plus the
        # captured session resolved per role. Different roles = different accounts, so each
        # group runs in its own session and cannot co-run. Both are live credentials held
        # only between confirm and the run, then cleared.
        self._run_plan: list[tuple[str, list[PipelineArtifact]]] = []
        self._role_sessions: dict[str, dict[str, Any]] = {}

    # -------------------------------------------------------------------------
    # BaseAgent interface
    # -------------------------------------------------------------------------

    async def process(
        self,
        input_data: dict[str, Any],
        feedback: str | None = None,
    ) -> StageResult:
        """Run the confirmed scripts in a controlled subprocess (14.2).

        Returns a :class:`StageResult` whose ``data`` is the structured
        :class:`~ai_qa.pipelines.script_runner.RunResult`. Called by
        ``_begin_execution`` (the happy path); off-path callers get the same result.
        """
        base_url = self._target_url or (input_data.get("target_url") if input_data else None)
        if not self.confirmed_scripts:
            return StageResult(success=False, errors=["No scripts confirmed for execution."])
        if not base_url:
            return StageResult(success=False, errors=["No target environment URL provided."])

        settings = AppSettings()
        labels = self._browser_labels or ["chromium"]
        browsers: list[BrowserSpec] = [browser_spec_from_label(label) for label in labels]
        server_mode = os.getenv("E2E_SERVER_MODE") == "1"

        # Role-grouped run plan (Slice 6): one run_scripts invocation per role, each with
        # THAT role's captured session (different roles = different accounts, can't co-run).
        # Off-path/direct callers (no plan) degrade to a single group from confirmed_scripts
        # + self._storage_state — byte-identical to the pre-Slice-6 single-session run.
        plan: list[tuple[str, list[PipelineArtifact]]] = self._run_plan or [
            (self._role, list(self.confirmed_scripts))
        ]
        sessions: dict[str, dict[str, Any] | None] = (
            dict(self._role_sessions) if self._role_sessions else {self._role: self._storage_state}
        )
        multi = len(plan) > 1

        group_results: list[RunResult] = []
        try:
            for role, arts in plan:
                # Defense in depth (AC3): never launch a browser run for a role that has no
                # captured session — that would produce misleading login failures. The approve
                # path already hard-blocks this in _confirm_inputs; this also guards any
                # off-path caller (e.g. a crafted reject) from running unauthenticated.
                if sessions.get(role) is None:
                    return StageResult(
                        success=False,
                        errors=[
                            "Refusing to run: no captured session for "
                            f"role '{role or '(default)'}'. Capture a session and retry."
                        ],
                    )
                scripts = [
                    ScriptToRun(name=a.name, content=a.content, source_artifact_id=a.id)
                    for a in arts
                ]
                run_result = await asyncio.to_thread(
                    run_scripts,
                    scripts=scripts,
                    base_url=base_url,
                    browsers=browsers,
                    storage_state=sessions.get(role),
                    run_policy=settings.run_policy,
                    wall_clock_timeout=settings.execution_wall_clock_timeout,
                    execution_timeout=settings.execution_timeout,
                    headed=not server_mode,
                    capture_screenshots=settings.execution_capture_screenshots,
                    capture_traces=settings.execution_capture_traces,
                    server_mode=server_mode,
                )
                # Stamp the role each result ran AS, and namespace produced files per role so
                # two role groups never collide on a shared name (e.g. run.log / screenshots).
                for tr in run_result.results:
                    tr.role = role or None
                if multi:
                    folder = role_to_folder(role) or "role"
                    for pf in run_result.produced_files:
                        pf.name = f"{folder}__{pf.name}"
                group_results.append(run_result)
        finally:
            # Drop this frame's reference to the live session blobs immediately — they must
            # not linger on the stack (e.g. captured by a logged traceback) past the run.
            sessions.clear()

        return StageResult(success=True, data=_merge_run_results(group_results))

    # -------------------------------------------------------------------------
    # Precondition gate (AC3)
    # -------------------------------------------------------------------------

    def _check_preconditions(self) -> list[str]:
        """Return blocking messages (UX-DR12); empty list = all checks pass."""
        ctx = self.project_context
        if not ctx or not ctx.project_id or not ctx.user_id or not ctx.thread_id:
            return ["Start Jack from inside an active project thread."]
        if ctx.artifact_service is None:
            return ["The backend storage service is unavailable — contact support."]
        return []

    def _format_no_scripts_message(self) -> str:
        """UX-DR12 message when no approved scripts are found (14.1 AC3)."""
        return (
            "**What happened:** Jack cannot run tests yet.\n\n"
            "**Why:** No approved test scripts were found for this project.\n\n"
            "**What to do:** Run Sarah to generate Playwright scripts from approved test "
            "cases and approve at least one script, then start Jack again."
        )

    def _format_no_url_message(self) -> str:
        """UX-DR12 message when no target environment URL is available (14.2 AC1)."""
        return (
            "**What happened:** Jack needs a target environment URL to run scripts.\n\n"
            "**Why:** No environment was selected and no URL was provided.\n\n"
            "**What to do:** Configure a project environment (admin dashboard) or enter the "
            "application URL, then confirm again."
        )

    def _format_missing_sessions_message(self, environment: str, roles: list[str]) -> str:
        """UX-DR12 message when one or more involved roles have no captured session.

        Slice 6: the selected scripts can span several roles (each runs as its own account),
        so EVERY involved role needs a captured session for the chosen environment. Lists
        each missing (environment / role) so the tester knows exactly what to capture.
        """
        env_label = environment or "(no environment)"
        pairs = "\n".join(f"  - {env_label} / {r or '(no role)'}" for r in roles)
        return (
            "**What happened:** Jack cannot run: the selected scripts include role(s) with no "
            "captured session.\n\n"
            "**Why:** Each role runs as its own account, so every involved role needs a valid "
            "captured session for the selected environment — running without one would produce "
            "misleading login failures.\n\n"
            "**What to do:** Capture a session for each of these in the Sessions panel, then run "
            f"again:\n{pairs}"
        )

    # -------------------------------------------------------------------------
    # Input-selection helpers (AC2)
    # -------------------------------------------------------------------------

    @staticmethod
    def _script_title(name: str) -> str:
        """Strip a single trailing ``.py`` extension for a friendly title."""
        return name[:-3] if name.endswith(".py") else name

    @staticmethod
    def _script_preview(content: str) -> str:
        """First ``_PREVIEW_LINES`` lines of the raw ``.py`` content."""
        lines = content.splitlines()
        return "\n".join(lines[:_PREVIEW_LINES])

    def _project_environments(self) -> list[dict[str, str]]:
        """Return the project's configured target environments (``[{name, url}]``).

        Project-wide and admin-managed (``Project.environments``). Returns ``[]`` when
        the project has none, so the panel falls back to a free-text URL. Mirrors Sarah.
        """
        if (
            self.project_context is None
            or self.project_context.artifact_service is None
            or self.project_context.project_id is None
        ):
            return []
        from ai_qa.db.models import Project

        db = self.project_context.artifact_service.db
        project = db.get(Project, self.project_context.project_id)
        raw = getattr(project, "environments", None)
        if not isinstance(raw, list):
            return []
        return [
            {"name": str(entry["name"]), "url": str(entry["url"])}
            for entry in raw
            if isinstance(entry, dict) and entry.get("name") and entry.get("url")
        ]

    def _project_app_roles(self) -> list[str]:
        """Return the project's configured application roles (``Project.app_roles``)."""
        if (
            self.project_context is None
            or self.project_context.artifact_service is None
            or self.project_context.project_id is None
        ):
            return []
        from ai_qa.db.models import Project

        db = self.project_context.artifact_service.db
        project = db.get(Project, self.project_context.project_id)
        raw = getattr(project, "app_roles", None)
        return [str(r) for r in raw] if isinstance(raw, list) else []

    def _captured_sessions(self) -> list[dict[str, str]]:
        """Non-secret list of captured (environment, role) slots for the current user.

        Lets the panel disable Run + hint when the selected slot has no session. Never
        returns any session value — only the (env, role) keys (14.4 AC3 containment).
        """
        ctx = self.project_context
        if (
            ctx is None
            or ctx.artifact_service is None
            or ctx.project_id is None
            or ctx.user_id is None
        ):
            return []
        try:
            statuses = list_session_status(
                ctx.artifact_service.db, user_id=ctx.user_id, project_id=ctx.project_id
            )
        except Exception as exc:  # noqa: BLE001 — status is best-effort UX hinting
            logger.debug("Could not list session status: %s", exc)
            return []
        return [{"environment": s.environment, "role": s.role} for s in statuses]

    async def _present_script_selection(self) -> None:
        """Emit the ``script_selection`` payload to the frontend (14.1 AC2 + 14.2 env)."""
        if self.project_context is None:
            return
        ctx = self.project_context
        adapter = PipelineArtifactAdapter(ctx)
        entries: list[dict[str, Any]] = []
        any_from_thread = any(
            a.thread_id is not None and a.thread_id == ctx.thread_id for a in self.candidate_scripts
        )
        for art in self.candidate_scripts:
            from_thread = art.thread_id is not None and art.thread_id == ctx.thread_id
            # Default-select: current-thread entries always; others only when none from thread
            default_selected = from_thread or not any_from_thread
            source_title, confidence, role = self._sidecar_enrichment(adapter, art.name)
            entries.append(
                {
                    "artifact_id": str(art.id),
                    "name": art.name,
                    "title": self._script_title(art.name),
                    "from_current_thread": from_thread,
                    "default_selected": default_selected,
                    "preview": self._script_preview(art.content),
                    "source_test_case_title": source_title,
                    "confidence": confidence,
                    # Role the script runs AS (Slice 6) — lets the panel show + group by role
                    # and validate a captured session per involved role.
                    "role": role,
                }
            )
        await self.send_message(
            content="Please select which approved scripts to run.",
            message_type="text",
            metadata={
                "type": "script_selection",
                "is_input_selection": True,
                "scripts": entries,
                "environments": self._project_environments(),
                "app_roles": self._project_app_roles(),
                "sessions": self._captured_sessions(),
            },
        )

    def _sidecar_enrichment(
        self, adapter: PipelineArtifactAdapter, name: str
    ) -> tuple[str | None, float | None, str | None]:
        """Best-effort ``(test_case_title, confidence, role)`` from the 13.8 / Slice-5 side-car."""
        source_title: str | None = None
        confidence: float | None = None
        role: str | None = None
        try:
            stem = self._script_title(name)
            meta = adapter.load_metadata(f"{stem}.metadata.json")
            if meta:
                raw_title = meta.get("test_case_title")
                source_title = raw_title if isinstance(raw_title, str) else None
                raw_conf = meta.get("confidence")
                if isinstance(raw_conf, int | float):
                    confidence = float(raw_conf)
                raw_role = meta.get("role")
                role = raw_role if isinstance(raw_role, str) and raw_role.strip() else None
        except Exception as exc:  # noqa: BLE001 — side-car is best-effort only
            logger.debug("Side-car metadata lookup failed for %s: %s", name, exc)
        return source_title, confidence, role

    @staticmethod
    def _effective_role(script_role: str | None, ui_role: str) -> str:
        """The role a script runs AS: its own (from Sarah) when set, else the UI fallback.

        Role-bearing scripts (Slice 5 stamped ``role`` on the side-car) group by their own
        role; role-less scripts fall back to the single role the user picked — so a project
        without per-script roles behaves exactly as before (one group, one session).
        """
        return script_role if (script_role and script_role.strip()) else ui_role

    def _artifact_role(self, adapter: PipelineArtifactAdapter, name: str) -> str | None:
        """The role stamped on a script's side-car (Slice 5), or None."""
        return self._sidecar_enrichment(adapter, name)[2]

    async def _confirm_inputs(self, data: dict[str, Any] | None) -> None:
        """Handle user confirmation of input selection (phase == input_selection)."""
        selected_ids: list[str] = []
        target_url = ""
        environment = ""
        role = ""
        browser_labels: list[str] = []
        if data:
            raw = data.get("selected_artifact_ids")
            if isinstance(raw, list):
                selected_ids = [str(x) for x in raw]
            raw_url = data.get("target_url")
            if isinstance(raw_url, str):
                target_url = raw_url.strip()
            raw_env = data.get("environment")
            if isinstance(raw_env, str):
                environment = raw_env.strip()
            raw_role = data.get("role")
            if isinstance(raw_role, str):
                role = raw_role.strip()
            raw_browsers = data.get("browsers")
            if isinstance(raw_browsers, list):
                browser_labels = [str(b) for b in raw_browsers if b]

        selected_set = set(selected_ids)
        filtered = (
            [a for a in self.candidate_scripts if str(a.id) in selected_set]
            if selected_set
            else list(self.candidate_scripts)
        )

        if not filtered:
            await self.send_message(
                "Please select at least one script before confirming.",
                message_type="warning",
            )
            await self._present_script_selection()
            return

        # AC1 (14.2): a target URL is required to run at all — block if missing.
        if not target_url:
            await self.send_message(
                content=self._format_no_url_message(),
                message_type="error",
            )
            return  # Stay REVIEW_REQUEST — re-submittable with a URL.

        if self.project_context is None:
            return

        # Slice 6: group the selected scripts by the role they run AS (Sarah stamped each
        # script's role on its side-car). Role-less scripts fall back to the single role the
        # user picked, so a project without per-script roles stays one group / one session.
        adapter = PipelineArtifactAdapter(self.project_context)
        groups: dict[str, list[PipelineArtifact]] = {}
        for art in filtered:
            eff = self._effective_role(self._artifact_role(adapter, art.name), role)
            groups.setdefault(eff, []).append(art)

        # AC3 (14.4): the app under test is authenticated — EVERY involved role needs a
        # captured session for the selected environment. Hard-block listing any that are
        # missing (no unauthenticated fallback). resolve_storage_state is the only blob reader.
        sessions: dict[str, dict[str, Any]] = {}
        missing: list[str] = []
        for grp_role in groups:
            blob = self._resolve_session(environment, grp_role)
            if blob is None:
                missing.append(grp_role)
            else:
                sessions[grp_role] = blob
        if missing:
            await self.send_message(
                content=self._format_missing_sessions_message(environment, missing),
                message_type="error",
            )
            return  # Stay REVIEW_REQUEST — no subprocess, no browser.

        self.confirmed_scripts = filtered
        self._target_url = target_url
        self._environment = environment
        self._role = role
        self._browser_labels = browser_labels or ["chromium"]
        self._run_plan = list(groups.items())
        self._role_sessions = sessions
        self._storage_state = None
        self.phase = "execution"
        await self._begin_execution()

    def _resolve_session(self, environment: str, role: str) -> dict[str, Any] | None:
        """Return the captured storageState for (env, role) or None. Never logs the blob."""
        ctx = self.project_context
        if (
            ctx is None
            or ctx.artifact_service is None
            or ctx.project_id is None
            or ctx.user_id is None
        ):
            return None
        if not environment or not role:
            return None
        return resolve_storage_state(
            ctx.artifact_service.db,
            user_id=ctx.user_id,
            project_id=ctx.project_id,
            environment=environment,
            role=role,
        )

    async def _begin_execution(self) -> None:
        """Run the confirmed scripts, persist results, and land in REVIEW_REQUEST (14.2/14.4)."""
        await self.transition_to(AgentState.PROCESSING)
        try:
            try:
                result = await self.process({}, feedback=None)
            except Exception as exc:  # noqa: BLE001 — surface any runner failure to the user
                logger.error("Jack execution failed: %s", exc, exc_info=True)
                await self.transition_to(AgentState.ERROR)
                await self.send_message(
                    content=self._format_error_message([str(exc)]),
                    message_type="error",
                )
                return
        finally:
            # Clear live credentials as soon as the run is done (secret containment).
            self._storage_state = None
            self._role_sessions = {}
            self._run_plan = []

        if not result.success or not isinstance(result.data, RunResult):
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message(result.errors),
                message_type="error",
            )
            return

        run_result = result.data
        self._persist_results(run_result)
        records = self._persist_outputs(run_result)
        report_artifact_id = self._persist_report(run_result, records)

        summary = run_result.summary
        await self.transition_to(AgentState.REVIEW_REQUEST)
        browsers_label = ", ".join(summary.browsers) or "no browser"
        unavailable_note = (
            f" ({len(summary.unavailable_browsers)} browser(s) unavailable)"
            if summary.unavailable_browsers
            else ""
        )
        await self.send_message(
            content=(
                f"Executed {summary.total} result(s) on {browsers_label}: "
                f"{summary.passed} passed, {summary.failed} failed, "
                f"{summary.errors} error(s) in {summary.duration_ms / 1000:.1f}s{unavailable_note}."
            ),
            message_type="success",
            metadata={
                "type": "execution_summary",
                "run_id": str(ctx.agent_run_id) if (ctx := self.project_context) else None,
                "total": summary.total,
                "passed": summary.passed,
                "failed": summary.failed,
                "errors": summary.errors,
                "skipped": summary.skipped,
                "duration_ms": summary.duration_ms,
                "browsers": summary.browsers,
                "roles": sorted({r.role for r in run_result.results if r.role}),
                "unavailable_browsers": summary.unavailable_browsers,
                "report_artifact_id": report_artifact_id,
            },
        )

    def _persist_results(self, run_result: RunResult) -> None:
        """Persist per-test rows + the run summary (14.2 AC3). Sync DB path."""
        ctx = self.project_context
        if ctx is None or ctx.artifact_service is None or ctx.agent_run_id is None:
            logger.warning("Jack: no agent_run/context — skipping result persistence.")
            return
        db = ctx.artifact_service.db
        adapter = PipelineArtifactAdapter(ctx)
        name_by_id = {a.id: a.name for a in self.confirmed_scripts}

        for tr in run_result.results:
            test_case_id = self._resolve_test_case_id(
                adapter, name_by_id.get(tr.source_artifact_id) if tr.source_artifact_id else None
            )
            db.add(
                TestExecutionResult(
                    agent_run_id=ctx.agent_run_id,
                    project_id=ctx.project_id,
                    thread_id=ctx.thread_id,
                    source_script_artifact_id=tr.source_artifact_id,
                    source_test_case_artifact_id=test_case_id,
                    test_name=tr.test_name,
                    browser=tr.browser,
                    role=tr.role,
                    status=tr.status,
                    failure_classification=tr.failure_classification,
                    error_message=tr.error_message,
                    stack_trace=tr.stack_trace,
                    duration_ms=tr.duration_ms,
                )
            )

        summary = run_result.summary
        run = db.get(AgentRun, ctx.agent_run_id)
        if run is not None:
            run.execution_metadata = {
                "started_at": summary.started_at,
                "completed_at": summary.completed_at,
                "duration_ms": summary.duration_ms,
                "total": summary.total,
                "passed": summary.passed,
                "failed": summary.failed,
                "errors": summary.errors,
                "skipped": summary.skipped,
                "browsers": summary.browsers,
                "roles": sorted({r.role for r in run_result.results if r.role}),
                "unavailable_browsers": summary.unavailable_browsers,
                "base_url_host": summary.base_url_host,
                "run_policy": summary.run_policy,
            }
            run.status = "completed"
            run.summary = (
                f"{summary.passed}/{summary.total} passed, {summary.failed} failed, "
                f"{summary.errors} error(s)"
            )
        db.commit()

    def _persist_outputs(self, run_result: RunResult) -> list[tuple[str, str, UUID]]:
        """Persist runner-produced files; return ``(name, kind, artifact_id)`` records (14.3).

        Honors the per-kind capture toggles. The logical path is ``{prefix}/{run_id}/…``
        (unique per run — AC3). A misconfigured prefix raises in the adapter (AC2 runtime
        guard); we surface it as a UX-DR12 warning rather than crashing the run (results
        are already persisted; produced files remain in memory, not lost on disk).
        """
        ctx = self.project_context
        if ctx is None or ctx.artifact_service is None or ctx.agent_run_id is None:
            return []
        settings = AppSettings()
        keep_by_kind = {
            "log": settings.execution_capture_logs,
            "execution_screenshot": settings.execution_capture_screenshots,
            "trace": settings.execution_capture_traces,
        }
        kept = [pf for pf in run_result.produced_files if keep_by_kind.get(pf.kind, True)]
        if not kept:
            return []
        files: list[tuple[str, str | bytes, str]] = [(pf.name, pf.content, pf.kind) for pf in kept]
        adapter = PipelineArtifactAdapter(ctx)
        try:
            ids = adapter.persist_run_outputs(
                run_id=ctx.agent_run_id,
                files=files,
                prefix=settings.execution_output_prefix,
                overwrite=settings.execution_overwrite_reports,
            )
        except ValueError as exc:
            logger.warning("Jack: could not persist execution outputs: %s", exc)
            self._schedule_warning(
                "**What happened:** Execution ran, but its output files could not be saved.\n\n"
                f"**Why:** {exc}\n\n"
                "**What to do:** Check the execution output configuration "
                "(EXECUTION_OUTPUT_PREFIX) and try again."
            )
            return []
        return [(pf.name, pf.kind, art_id) for pf, art_id in zip(kept, ids, strict=False)]

    def _persist_report(
        self, run_result: RunResult, records: list[tuple[str, str, UUID]]
    ) -> str | None:
        """Compose + persist the execution report (Story 14.5); return its artifact id.

        Saves a visible ``report.md`` (``kind="report"``) and a hidden ``report.json``
        (``kind="configuration"``) holding the attachment link map for the 14.6 drilldown.
        Tolerant: a persistence/config error degrades to ``None`` (no report) without
        crashing — results are already persisted.
        """
        ctx = self.project_context
        if ctx is None or ctx.artifact_service is None or ctx.agent_run_id is None:
            return None
        settings = AppSettings()
        adapter = PipelineArtifactAdapter(ctx)
        link_map, result_dicts = self._build_report_inputs(adapter, run_result, records)
        summary = run_result.summary
        summary_dict = {
            "total": summary.total,
            "passed": summary.passed,
            "failed": summary.failed,
            "errors": summary.errors,
            "skipped": summary.skipped,
            "duration_ms": summary.duration_ms,
            "browsers": summary.browsers,
            "unavailable_browsers": summary.unavailable_browsers,
            "base_url_host": summary.base_url_host,
            "started_at": summary.started_at,
            "completed_at": summary.completed_at,
        }
        markdown, structured = compose_execution_report(
            summary=summary_dict,
            results=result_dicts,
            attachments=link_map,
            run_id=ctx.agent_run_id,
        )
        try:
            report = adapter.save_execution_output(
                run_id=ctx.agent_run_id,
                file_name="report.md",
                content=markdown,
                kind="report",
                prefix=settings.execution_output_prefix,
            )
            adapter.save_execution_output(
                run_id=ctx.agent_run_id,
                file_name="report.json",
                content=json.dumps(structured, indent=2, default=str),
                kind="configuration",
                prefix=settings.execution_output_prefix,
            )
        except ValueError as exc:
            logger.warning("Jack: could not persist execution report: %s", exc)
            return None
        # Story 14.6: render this report in the review UX (opened via report_artifact_id).
        return str(report.id)

    def _build_report_inputs(
        self,
        adapter: PipelineArtifactAdapter,
        run_result: RunResult,
        records: list[tuple[str, str, UUID]],
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        """Build the per-(test, browser) attachment link map + result dicts for the composer."""
        name_by_id = {a.id: a.name for a in self.confirmed_scripts}
        link_map: dict[str, dict[str, Any]] = {}
        result_dicts: list[dict[str, Any]] = []
        for r in run_result.results:
            # In a multi-role run, produced files are namespaced ``<role_folder>__<name>``
            # (Slice 6). Match within the result's OWN role group so a same-named test under
            # a different role can't steal its screenshot / trace / log.
            prefix = f"{role_to_folder(r.role)}__" if r.role else ""
            shot = self._match_attachment(
                records, "execution_screenshot", r.test_name, r.browser, prefix
            )
            trace = self._match_attachment(records, "trace", r.test_name, r.browser, prefix)
            # Role-aware key (Slice 6): must stay byte-identical with execution_report's
            # attachment_key and the frontend lookup in JackExecutionReport.tsx.
            link_map[attachment_key(r.test_name, r.browser, r.role)] = {
                "screenshot_id": shot,
                "trace_id": trace,
                "log_id": self._match_run_log(records, prefix),
            }
            tc_id = self._resolve_test_case_id(
                adapter,
                name_by_id.get(r.source_artifact_id) if r.source_artifact_id else None,
            )
            result_dicts.append(
                {
                    "test_name": r.test_name,
                    "browser": r.browser,
                    "role": r.role,
                    "status": r.status,
                    "duration_ms": r.duration_ms,
                    "failure_classification": r.failure_classification,
                    "error_message": r.error_message,
                    "stack_trace": r.stack_trace,
                    "source_script_artifact_id": (
                        str(r.source_artifact_id) if r.source_artifact_id else None
                    ),
                    "source_test_case_artifact_id": str(tc_id) if tc_id else None,
                }
            )
        return link_map, result_dicts

    @staticmethod
    def _match_attachment(
        records: list[tuple[str, str, UUID]],
        kind: str,
        test_name: str,
        browser: str,
        prefix: str = "",
    ) -> str | None:
        """Best-effort match of a produced attachment to a (test, browser) result by name.

        ``prefix`` is the result's role-folder namespace (``<role>__``) in a multi-role run;
        a file from the same role group is preferred so colliding test names across roles do
        not cross-link.
        """
        candidates = [
            (name, rid)
            for (name, rec_kind, rid) in records
            if rec_kind == kind and test_name in name and browser in name
        ]
        if not candidates:
            return None
        if prefix:
            for name, rid in candidates:
                if name.startswith(prefix):
                    return str(rid)
        return str(candidates[0][1])

    @staticmethod
    def _match_run_log(records: list[tuple[str, str, UUID]], prefix: str = "") -> str | None:
        """The run-log id for a result, role-aware (``<role>__run.log`` in multi-role runs)."""
        logs = [
            (name, rid)
            for (name, kind, rid) in records
            if kind == "log" and name.endswith("run.log")
        ]
        if not logs:
            return None
        if prefix:
            for name, rid in logs:
                if name.startswith(prefix):
                    return str(rid)
        return str(logs[0][1])

    def _schedule_warning(self, content: str) -> None:
        """Fire-and-forget a warning broadcast from sync code (best-effort)."""
        import asyncio as _asyncio

        try:
            loop = _asyncio.get_running_loop()
            loop.create_task(self.send_message(content, message_type="warning"))
        except RuntimeError:
            pass

    def _resolve_test_case_id(
        self, adapter: PipelineArtifactAdapter, script_name: str | None
    ) -> UUID | None:
        """Best-effort source test-case artifact id from the 13.8 side-car."""
        if not script_name:
            return None
        try:
            stem = self._script_title(script_name)
            meta = adapter.load_metadata(f"{stem}.metadata.json")
            if not meta:
                return None
            raw = meta.get("source_test_case_id")
            return UUID(str(raw)) if raw else None
        except (ValueError, TypeError, AttributeError) as exc:
            logger.debug("Could not resolve source test case id for %s: %s", script_name, exc)
            return None

    # -------------------------------------------------------------------------
    # Lifecycle entry points
    # -------------------------------------------------------------------------

    async def handle_start(self, input_data: dict[str, Any]) -> None:
        """Override handle_start to insert the input-selection gate (14.1).

        Flow: preconditions → load approved scripts → AC3 block if empty →
        present script_selection (REVIEW_REQUEST). After the user confirms,
        handle_approve dispatches to _confirm_inputs → _begin_execution.
        """
        # Fresh run: reset all per-run state so a re-start never inherits stale state.
        self.phase = "input_selection"
        self.confirmed_scripts = []
        self.candidate_scripts = []
        self._target_url = None
        self._environment = ""
        self._role = ""
        self._browser_labels = ["chromium"]
        self._storage_state = None
        self._run_plan = []
        self._role_sessions = {}

        # --- Precondition gate (AC3 gate #0) ---
        blockers = self._check_preconditions()
        for msg in blockers:
            await self.send_message(
                content=self._format_error_message([msg]),
                message_type="error",
            )
        if blockers:
            return  # Stay START — re-submittable

        # --- Load approved scripts (AC1) ---
        if self.project_context is None:
            return
        candidates = PipelineArtifactAdapter(self.project_context).load_approved_scripts()

        # --- AC3 block: no approved scripts ---
        if not candidates:
            await self.send_message(
                content=self._format_no_scripts_message(),
                message_type="error",
            )
            return  # Stay START — no PROCESSING, no execution

        # --- Present input-selection panel (AC2) ---
        self.candidate_scripts = candidates
        await self.transition_to(AgentState.REVIEW_REQUEST)
        await self._present_script_selection()

    async def handle_approve(self, data: dict[str, Any] | None = None) -> None:
        """Handle approve — phase-dispatched.

        * ``phase == "input_selection"``: user confirmed the script selection set.
        * any other phase: no-op (14.6 may add an execution-review branch).
        """
        if self.phase == "input_selection":
            await self._confirm_inputs(data)
            return
        # No other phase exists in 14.2.

    async def handle_reject(self, feedback: str, data: dict[str, Any] | None = None) -> None:
        """Reject returns to the input-selection gate — never re-runs with stale state.

        Without this override, ``BaseAgent.handle_reject`` would call ``process()`` directly.
        After a completed run the agent still holds ``confirmed_scripts``/``_target_url`` but
        has cleared the captured sessions, so that path would launch an UNauthenticated run
        and bypass the AC3 session hard-block. Instead we reset the per-run state and
        re-present the selection panel.
        """
        await self.send_message(
            content=(
                f'Understood — let\'s adjust the selection. Feedback: "{feedback}"'
                if feedback
                else "Understood — let's adjust the selection."
            ),
            message_type="text",
        )
        # Reset execution-bound state so a later approve can't inherit stale inputs.
        self.phase = "input_selection"
        self.confirmed_scripts = []
        self._target_url = None
        self._environment = ""
        self._role = ""
        self._browser_labels = ["chromium"]
        self._storage_state = None
        self._run_plan = []
        self._role_sessions = {}

        if self.project_context is not None and not self.candidate_scripts:
            self.candidate_scripts = PipelineArtifactAdapter(
                self.project_context
            ).load_approved_scripts()

        await self.transition_to(AgentState.REVIEW_REQUEST)
        if self.candidate_scripts:
            await self._present_script_selection()
        else:
            await self.send_message(
                content=self._format_no_scripts_message(),
                message_type="error",
            )
