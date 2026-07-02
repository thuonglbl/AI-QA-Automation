"""Sarah agent - Generate Playwright scripts with side-by-side review.

Sarah orchestrates script generation using ScriptGenerator with VisionLocator
integration, then presents scripts for side-by-side review where users can
approve, reject with feedback, or skip individual scripts.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai_qa.agents.base import AgentState, BaseAgent
from ai_qa.browser.agent import BrowserAgent
from ai_qa.config import AppSettings
from ai_qa.exceptions import BrowserError, ConfigError
from ai_qa.models import StageResult, TestCase, bound_stage_messages
from ai_qa.pipelines.artifact_adapter import PipelineArtifact, PipelineArtifactAdapter
from ai_qa.pipelines.script_generator import ScriptGenerator
from ai_qa.pipelines.script_validator import ScriptValidationError, validate_script
from ai_qa.pipelines.vision_locator import VisionLocator

logger = logging.getLogger(__name__)


class GeneratedScript(BaseModel):
    """Represents a generated script with metadata for review.

    approved_by/approved_at are stamped on the in-memory model when approved (AC1 — 13.7).
    Their durable artifact-metadata persistence is Story 13.8.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    test_case: TestCase
    script_content: str
    file_path: str
    confidence: float
    approved: bool = False
    error_message: str | None = None  # For failed script generation placeholder
    warnings: list[str] = Field(default_factory=list)
    # AC1 (13.7): approval metadata — who approved and when.
    # Durable artifact-sidecar persistence is 13.8.
    approved_by: str | None = None
    approved_at: str | None = None
    # AC2 (13.8): provenance for the durable side-car.
    source_test_case_id: str | None = None  # artifact UUID of the source test case
    validation_status: str | None = None  # "validated" when edited content passed 13.6 gate
    # C17/C18: the unique artifact name the approved .py was saved under. Set in
    # handle_approve; the sidecar (C18) derives its name from this stem so script+sidecar
    # stay 1:1 even when two test cases normalise to the same base filename.
    saved_file_name: str | None = None


class SarahAgent(BaseAgent):
    """Sarah - Generate Playwright scripts with side-by-side review.

    Orchestrates script generation using:
    - ScriptGenerator for LLM-based script creation
    - VisionLocator for accurate selector identification
    - PipelineArtifactAdapter for file management
    - WebSocket for real-time review UI

    Lifecycle:
        START → PROCESSING → REVIEW_REQUEST → (Approve/Reject/Skip) → DONE
    """

    def __init__(
        self,
        name: str = "Sarah",
        color: str = "#8B5CF6",  # Purple per UX-DR19
        step_number: int = 4,
        step_title: str = "Generate Scripts",
        workspace_dir: Path | None = None,
    ) -> None:
        """Initialize Sarah agent.

        Args:
            name: Agent display name
            color: HEX colour string matching frontend (purple for Sarah)
            step_number: Pipeline step index (4 for Sarah)
            step_title: Human-readable label shown in UI
            workspace_dir: Override workspace root path (used in tests)
        """
        super().__init__(name, color, step_number, step_title, workspace_dir)

        # Sarah-specific state
        self._generated_scripts: list[GeneratedScript] = []
        self._current_review_index: int = 0
        self._test_cases: list[TestCase] = []
        self._chrome_path: str | None = None
        self._target_url: str | None = None
        # The project environment NAME the user picked for this run. Sessions are keyed by
        # environment name, so this is the AUTHORITATIVE key for resolving the captured
        # session (no URL→name guesswork). Run-specific; reset each fresh run. May be empty
        # when the project has no configured environments (free-text URL) → no session.
        self._environment: str | None = None
        # CDP URL of a running Chrome to connect to (reuses its live SSO session).
        # Run-specific (like target_url); reset each fresh run.
        self._cdp_url: str | None = None
        self._start_input_data: dict[str, Any] = {}  # Store input_data for context preservation

        # Reviewed-set DONE gate (13.5): tracks indices reviewed (approved OR skipped)
        self._reviewed_indices: set[int] = set()

        # Input-selection gate state (13.1)
        self.phase: str = "input_selection"
        self.candidate_test_cases: list[PipelineArtifact] = []
        self.confirmed_test_cases: list[TestCase] = []
        # Dedicated chrome-path re-entry flag (do NOT overload confirmed_test_cases):
        # set when _begin_generation requested a Chrome path and is awaiting re-start.
        self._awaiting_inputs: bool = False
        # AC2 (13.8): source test case artifact IDs, parallel to confirmed_test_cases / _test_cases.
        # Set in _confirm_inputs; fallback path initialises with [None] * len(_test_cases).
        self._test_case_source_ids: list[str | None] = []

        # Initialize pipeline components. The LLM config is resolved here only as a
        # provisional placeholder — the real api_key lives in the user's encrypted
        # secret store, which is unreachable until set_project_context() attaches the
        # context (so this returns an empty-key config and does NOT raise). Sarah builds
        # its ScriptGenerator fresh per generation call, so _ensure_llm_ready() refreshes
        # self.config against the context before each construction (see below).
        self.config = self.get_llm_config()

        self.app_settings = AppSettings()

        self._script_generator: ScriptGenerator | None = None
        self._vision_locator: VisionLocator | None = None
        self._browser_agent: BrowserAgent | None = None
        # Whether the browser-use explore may use screenshots — set by _build_explore_llm
        # from the EXPLORE model's vision capability (never send images to a text-only model).
        self._explore_use_vision: bool = False

    def _ensure_llm_ready(self) -> None:
        """Re-resolve the LLM config against the attached project context.

        ``__init__`` captured a provisional config with an EMPTY ``api_key`` — the agent
        is constructed by ``agent_class()`` before ``set_project_context`` runs, so the
        per-user encrypted secret is unreachable and ``get_llm_config`` returns a
        placeholder (it does not raise, because there is no context/user yet). Left
        stale, that empty key surfaces at generation time as a raw provider auth error
        ("Could not resolve authentication method"). Resolving here — before every
        ``ScriptGenerator(llm_config=self.config, …)`` construction — uses the
        context-resolved per-user secret. ``get_llm_config`` raises ``PipelineError``
        (UX-DR12) when the key is genuinely missing; callers run inside try/except that
        surface it.

        Unlike Mary, Sarah builds its ``ScriptGenerator`` fresh per generation call (it
        is not stored long-term), so there is no cached collaborator to re-apply the
        config to — keeping ``self.config`` fresh before each construction is enough.
        ``_build_explore_llm`` resolves the credential on its own and is intentionally
        left to do so (Task 2).
        """
        self.config = self.get_llm_config()

    # -------------------------------------------------------------------------
    # BaseAgent Interface
    # -------------------------------------------------------------------------

    async def process(
        self,
        input_data: dict[str, Any],
        feedback: str | None = None,
    ) -> StageResult:
        """Generate Playwright scripts from test cases.

        Args:
            input_data: User input containing chrome_path and target_url
            feedback: User rejection feedback for re-processing current script

        Returns:
            StageResult with generated scripts for review
        """
        try:
            # Handle feedback/reject case - regenerate current script
            if feedback and self._current_review_index < len(self._generated_scripts):
                return await self._regenerate_current_script(feedback)

            # Extract Chrome path, target URL, and optional CDP URL from input. The Chrome
            # path is a transient, per-run launch hint (no longer persisted) — a server-side
            # browser is planned (Phase C); until then the user supplies it each run.
            chrome_path = input_data.get("chrome_path", self._chrome_path)
            target_url = input_data.get("target_url", "")
            cdp_url = (input_data.get("cdp_url") or self._cdp_url or "").strip()
            # The environment NAME picked by the user — the authoritative session-resolve key.
            environment = (input_data.get("environment") or self._environment or "").strip()

            if chrome_path:
                self._chrome_path = chrome_path

            self._target_url = target_url
            self._cdp_url = cdp_url or None
            self._environment = environment or None

            # Use the user-confirmed test cases when the selection gate has run;
            # otherwise fall back to the full artifact load (back-compat / regeneration).
            if self.confirmed_test_cases:
                self._test_cases = self.confirmed_test_cases
                # _test_case_source_ids was set by _confirm_inputs; keep it as-is
            else:
                test_cases_result = await self._load_test_cases()
                if not test_cases_result.success:
                    return test_cases_result
                self._test_cases = test_cases_result.data or []
                # Fallback path: artifact IDs not available; use None for all
                self._test_case_source_ids = [None] * len(self._test_cases)

            if not self._test_cases:
                return StageResult(
                    success=True,
                    data=[],
                    errors=[],
                    warnings=["No test cases found for this project."],
                    confidence=1.0,
                )

            # Initialize browser and vision components if target URL provided
            if target_url:
                await self._initialize_vision_components(chrome_path, target_url)

            # Generate scripts for all test cases
            return await self._generate_scripts()

        except Exception as e:
            logger.error(f"Error in Sarah agent process: {e}")
            return StageResult(
                success=False,
                data=None,
                errors=[f"Failed to generate scripts: {e}"],
                warnings=[],
                confidence=0.0,
            )

    @staticmethod
    def _testcase_base(name: str) -> str:
        """Strip a single trailing ``.md``/``.json`` extension to get the base name."""
        for ext in (".md", ".json"):
            if name.endswith(ext):
                return name[: -len(ext)]
        return name

    def _testcases_from_artifact(self, artifact: PipelineArtifact) -> list[TestCase]:
        """Reconstruct typed ``TestCase`` objects from a test-case artifact.

        Mary stores each test case as natural-language **Markdown** (``{base}.md``) — the
        same form Sarah feeds to the script-generation LLM. ``TestCase.from_markdown``
        rebuilds the structured object the review panel / heuristics read. Legacy
        artifacts stored the JSON object as the body, so try JSON first (back-compat),
        then parse Markdown. Returns ``[]`` only for genuinely empty content.
        """
        try:
            data = json.loads(artifact.content)
        except json.JSONDecodeError, ValueError:
            data = None
        if data is not None:
            try:
                if isinstance(data, list):
                    return [TestCase(**item) for item in data]
                return [TestCase(**data)]
            except TypeError, ValueError:
                return []
        if artifact.content and artifact.content.strip():
            return [TestCase.from_markdown(artifact.content)]
        return []

    async def _load_test_cases(self) -> StageResult:
        """Load test cases from project artifacts via the artifact service."""
        if self.project_context is None:
            raise ValueError("SarahAgent requires an active project context.")
        adapter = PipelineArtifactAdapter(self.project_context)
        test_case_artifacts = adapter.load_test_cases()
        if not test_case_artifacts:
            return StageResult(
                success=False,
                data=None,
                errors=["No test case artifacts found for this project"],
                warnings=[],
                confidence=0.0,
            )

        test_cases: list[TestCase] = []
        errors: list[str] = []
        for artifact in test_case_artifacts:
            parsed = self._testcases_from_artifact(artifact)
            if parsed:
                test_cases.extend(parsed)
            else:
                errors.append(f"Failed to parse {artifact.name}")

        return StageResult(
            success=len(test_cases) > 0,
            data=test_cases,
            errors=errors if errors else [],
            warnings=[f"Loaded {len(test_cases)} test case artifact(s)"] if test_cases else [],
            confidence=1.0 if test_cases else 0.0,
        )

    async def _initialize_vision_components(self, chrome_path: str | None, target_url: str) -> None:
        """Initialize browser agent and vision locator.

        Args:
            chrome_path: Path to Chrome executable
            target_url: Target application URL
        """
        try:
            # Initialize browser agent if Chrome path provided
            if chrome_path:
                # Browser agent is initialized directly in constructor
                self._browser_agent = BrowserAgent(
                    chrome_path=chrome_path,
                    timeout=30,
                )

                # Initialize vision locator
                self._vision_locator = VisionLocator(
                    browser_agent=self._browser_agent,
                    config=self.app_settings,
                )
                logger.info("Vision components initialized for %s", target_url)
        except (OSError, RuntimeError) as e:
            logger.warning("Failed to initialize vision components: %s", e)
            await self.send_message(
                f"Vision analysis unavailable: {e}. Continuing with LLM-only generation.",
                message_type="warning",
            )

    def _thread_agent_model(self, agent_name: str) -> str:
        """Return the model id another agent is configured with on this thread (or "").

        Used to borrow the project's VISION model (Bob's pick) to drive Sarah's explore.
        """
        ctx = self.project_context
        if ctx is None or ctx.artifact_service is None or ctx.thread_id is None:
            return ""
        from ai_qa.threads.models import Thread

        thread = ctx.artifact_service.db.get(Thread, ctx.thread_id)
        if thread is None or not thread.agent_configs:
            return ""
        raw = thread.agent_configs.get(agent_name)
        if isinstance(raw, dict):
            model = raw.get("model") or raw.get("model_name")
            return str(model) if model else ""
        return raw if isinstance(raw, str) else ""

    def _resolve_explore_model(self, codegen_model: str) -> tuple[str, bool]:
        """Pick the model that DRIVES the browser-use explore + whether to use vision.

        The explore (a browser-use agent navigating the REAL app to capture REAL selectors)
        works far better with a VISION model, while Sarah's own model is chosen for code
        generation. Alice assigns Sarah a dedicated, user-overridable explore model
        (``sarah_explore`` in the config); prefer it. Older threads have no such slot, so fall
        back to the project's vision model (Bob's pick), then to the codegen model.

        Returns ``(model_id, use_vision)``. ``use_vision`` is True only when the chosen explore
        model is actually vision-capable — browser-use sends screenshots a text-only model
        cannot read (it only auto-disables vision for DeepSeek/some xAI), so a non-vision model
        runs DOM-only instead of failing the explore and guessing selectors.
        """
        from ai_qa.agents.alice import _has_vision_signal

        # 1) Explicit per-Sarah explore assignment (Alice's pick, user-overridable in review).
        explore_override = self._thread_agent_model("sarah_explore")
        if explore_override:
            return explore_override, _has_vision_signal({"id": explore_override})
        # 2) No explore slot (older thread) → borrow the project vision model (Bob's pick).
        bob_vision = self._thread_agent_model("bob")
        if bob_vision and _has_vision_signal({"id": bob_vision}):
            return bob_vision, True
        # 3) Last resort: Sarah's own model (rarely vision-capable).
        if codegen_model and _has_vision_signal({"id": codegen_model}):
            return codegen_model, True
        return codegen_model, False

    def _build_explore_llm(self) -> Any:
        """Build a browser-use LLM from the thread's configured provider to DRIVE
        the live exploration (real app → verified trace → deterministic Playwright).

        Reuses the SAME provider/credential the rest of the pipeline resolves, but drives
        the explore with the project's VISION model (Bob's pick) instead of Sarah's coding
        model so browser-use can actually SEE the page and capture real selectors. Sets
        ``self._explore_use_vision`` from that model's capability. Returns ``None`` when no
        usable credential is available — generation then falls back to vision / LLM-only.
        """
        try:
            cfg = self.get_llm_config()
        except Exception as exc:  # noqa: BLE001 — no credential → no exploration
            logger.info("No provider credential for browser-use exploration: %s", exc)
            return None
        if not getattr(cfg, "api_key", ""):
            return None
        explore_model, use_vision = self._resolve_explore_model(cfg.model_name)
        self._explore_use_vision = use_vision
        try:
            from ai_qa.browser.llm_factory import build_browser_use_llm

            llm = build_browser_use_llm(
                cfg.provider,
                api_key=cfg.api_key,
                model=explore_model,
                base_url=getattr(cfg, "base_url", "") or "",
                temperature=getattr(cfg, "temperature", 0.0) or 0.0,
            )
            logger.info(
                "Sarah explore: driving browser-use with model %s (use_vision=%s); "
                "code generation uses %s",
                explore_model,
                use_vision,
                cfg.model_name,
            )
            return llm
        except Exception as exc:  # noqa: BLE001 — unknown provider / build error
            logger.warning("Could not build browser-use LLM for exploration: %s", exc)
            return None

    async def _resolve_role_sessions(self) -> dict[str, dict[str, Any]]:
        """Resolve the user's test accounts for the roles in this run (Tier-1 explore).

        Builds a ``{role: storageState}`` map so the SERVER-SIDE browser-use explore can
        authenticate with the user's test accounts — no local Chrome required. Keyed by
        ``(user_id, project_id, environment, role)``; the environment is the NAME the user
        picked in the inputs form (``self._environment``), submitted alongside the target URL
        from the SAME env object — so it is the authoritative key (no URL→name guesswork).
        Roles with no test account are skipped. Returns ``{}`` (explore falls back to
        vision / LLM-only) when the context is incomplete, no environment was submitted, or
        nothing is configured. The decrypted ``storageState`` blob is a live credential — it is
        never logged.
        """
        ctx = self.project_context
        environment = self._environment
        if (
            ctx is None
            or ctx.artifact_service is None
            or ctx.project_id is None
            or ctx.user_id is None
            or not self._target_url
            or not environment
        ):
            return {}

        # Distinct roles across the test cases being generated (None role = no session).
        roles = {tc.role for tc in self._test_cases if getattr(tc, "role", None)}
        if not roles:
            return {}

        from ai_qa.sessions import auto_login

        db = ctx.artifact_service.db
        role_sessions: dict[str, dict[str, Any]] = {}
        for role in roles:
            assert role is not None  # narrowed by the comprehension filter above
            try:
                blob = await auto_login.resolve_or_generate_storage_state(
                    db,
                    user_id=ctx.user_id,
                    project_id=ctx.project_id,
                    environment=environment,
                    role=role,
                    chrome_path=self._chrome_path or "",
                    # Pass the explore LLM to browser-use for login form navigation
                    llm=self._build_explore_llm(),
                    timeout=60,
                    raise_on_failure=True,
                )
            except ConfigError as exc:
                logger.info("Could not resolve captured session for role '%s': %s", role, exc)
                continue
            except BrowserError as exc:
                logger.warning("Browser login failed for role '%s': %s", role, exc)
                continue
            except Exception as exc:  # noqa: BLE001 — never let session lookup break generation
                logger.warning(
                    "Unexpected error resolving session for role '%s' (%s)",
                    role,
                    type(exc).__name__,
                )
                continue
            if blob is not None:
                role_sessions[role] = blob
        return role_sessions

    async def _generate_scripts(self) -> StageResult:
        """Generate Playwright scripts for all test cases.

        Returns:
            StageResult with generated scripts
        """
        self._generated_scripts = []
        errors: list[str] = []
        warnings: list[str] = []

        # Initialize script generator with vision locator if available, and — when a
        # driving LLM + a browser source are available — the browser-use exploration path
        # (real app → verified trace → deterministic Playwright). The browser source is a
        # local Chrome (chrome_path/cdp_url) OR, on the server (UAT container), the user's
        # captured sessions per role (role_sessions) injected into a managed Chromium.
        # Exploration is gated inside ScriptGenerator and falls back to vision/LLM-only
        # on any failure.
        # Build the explore LLM first — it resolves the vision model + sets
        # self._explore_use_vision, which the generator passes to the explore call.
        explore_llm = self._build_explore_llm()
        script_generator = ScriptGenerator(
            output_base_dir=Path("/dev/null"),  # output_base_dir no longer used for writing
            llm_config=self.config,
            config=self.app_settings,
            vision_locator=self._vision_locator,
            explore_llm=explore_llm,
            explore_use_vision=self._explore_use_vision,
            chrome_path=self._chrome_path or "",
            cdp_url=self._cdp_url or "",
            role_sessions=await self._resolve_role_sessions(),
        )

        total = len(self._test_cases)

        for idx, test_case in enumerate(self._test_cases):
            i = idx + 1  # 1-based for display
            # Look up source artifact ID from parallel list (AC2 / 13.8)
            source_tc_id: str | None = (
                self._test_case_source_ids[idx] if idx < len(self._test_case_source_ids) else None
            )

            # Send progress update
            await self.send_message(
                f"Generating script {i} of {total}...",
                message_type="info",
                metadata={
                    "current": i,
                    "total": total,
                    "test_case_title": test_case.title,
                },
            )

            try:
                # Generate script for this test case
                result = await script_generator.generate(
                    test_cases=[test_case],
                    target_url=self._target_url,
                )

                if result.success and result.data:
                    script_data = result.data[0]
                    # Prepend header here since generator doesn't do it anymore
                    header = script_generator._generate_script_header(test_case)
                    full_script_content = header + "\n\n" + script_data.get("script_content", "")

                    # Generate filename for artifact
                    filename = script_generator._generate_filename(test_case.title)

                    # Coerce warnings to list[str] before assigning (dict value is Any)
                    raw_warnings = script_data.get("warnings", [])
                    script_warnings: list[str] = (
                        [str(w) for w in raw_warnings] if raw_warnings else []
                    )

                    generated_script = GeneratedScript(
                        test_case=test_case,
                        script_content=full_script_content,
                        file_path=filename,
                        confidence=script_data.get("confidence", 0.5),
                        warnings=script_warnings,
                        source_test_case_id=source_tc_id,
                    )
                    self._generated_scripts.append(generated_script)

                    if result.warnings:
                        warnings.extend(result.warnings)
                else:
                    error_msg = f"Failed to generate script for '{test_case.title}'"
                    if result.errors:
                        error_msg += f": {result.errors[0]}"
                    # Recorded as a WARNING, not an error: appending a placeholder below
                    # makes _generated_scripts non-empty, so this stage is a *degraded
                    # success* (success=True) and StageResult forbids a non-empty errors
                    # list then. The per-item failure detail lives on the placeholder.
                    warnings.append(error_msg)
                    # AC3/AC4: append a skip-only failure placeholder (mirrors the
                    # ``except`` branch below) so a single failed test case never
                    # silently drops and the batch never collapses to an empty Scripts
                    # folder. error_message makes it skip-only — never approvable (the
                    # C3 gate at handle_approve enforces this).
                    self._generated_scripts.append(
                        GeneratedScript(
                            test_case=test_case,
                            script_content=f"# Generation failed: {error_msg}",
                            file_path="",
                            confidence=0.0,
                            approved=False,
                            error_message=error_msg,
                            source_test_case_id=source_tc_id,
                        )
                    )

            except Exception as e:
                logger.error(f"Error generating script for '{test_case.title}': {e}")
                # WARNING (not error) for the same reason as the else branch above: the
                # placeholder makes this a degraded success, and StageResult requires the
                # errors list be empty when success=True.
                warnings.append(f"Exception for '{test_case.title}': {e}")
                # Add placeholder for failed script so index mapping is preserved
                failed_placeholder = GeneratedScript(
                    test_case=test_case,
                    script_content=f"# Generation failed: {e}",
                    file_path="",
                    confidence=0.0,
                    approved=False,
                    error_message=str(e),
                    source_test_case_id=source_tc_id,
                )
                self._generated_scripts.append(failed_placeholder)

        # Reset review state
        self._current_review_index = 0
        self._reviewed_indices = set()

        success = len(self._generated_scripts) > 0
        confidence = (
            sum(s.confidence for s in self._generated_scripts) / len(self._generated_scripts)
            if self._generated_scripts
            else 0.0
        )

        return StageResult(
            success=success,
            data=self._generated_scripts,
            errors=bound_stage_messages(errors, kind="errors"),
            warnings=bound_stage_messages(warnings),
            confidence=confidence,
        )

    def _read_script_content(self, file_path: str) -> str:
        # Not needed anymore
        return ""

    async def _regenerate_current_script(self, feedback: str) -> StageResult:
        """Regenerate the current script with user feedback.

        Args:
            feedback: User feedback for regeneration

        Returns:
            StageResult with regenerated script
        """
        if self._current_review_index >= len(self._generated_scripts):
            return StageResult(
                success=False,
                data=None,
                errors=["No script to regenerate"],
                warnings=[],
                confidence=0.0,
            )

        current_script = self._generated_scripts[self._current_review_index]
        test_case = current_script.test_case
        # Carry the source test case artifact ID forward onto the replacement (AC2/13.8):
        # read it BEFORE the GeneratedScript at this index is overwritten.
        source_tc_id = current_script.source_test_case_id

        await self.send_message(
            f"Regenerating script for '{test_case.title}' with feedback...",
            message_type="info",
        )

        # Refresh the LLM config against the attached context so the regeneration uses
        # the context-resolved per-user key, not the empty-key placeholder captured at
        # __init__. Called within process()'s try/except (and the direct-call test
        # path), so a genuinely missing key surfaces as a failure StageResult.
        self._ensure_llm_ready()

        # For now, re-generate using the same process but with feedback context
        # In a more sophisticated implementation, we'd incorporate feedback into the prompt
        script_generator = ScriptGenerator(
            output_base_dir=Path("/dev/null"),
            llm_config=self.config,
            config=self.app_settings,
            vision_locator=self._vision_locator,
        )

        try:
            result = await script_generator.generate(
                test_cases=[test_case],
                target_url=self._target_url,
                feedback=feedback,  # AC2 (13.7): inject reviewer feedback into the prompt
            )

            if result.success and result.data:
                script_data = result.data[0]
                header = script_generator._generate_script_header(test_case)
                full_script_content = header + "\n\n" + script_data.get("script_content", "")
                filename = script_generator._generate_filename(test_case.title)

                # Coerce warnings to list[str] (dict value is Any)
                raw_regen_warnings = script_data.get("warnings", [])
                regen_warnings: list[str] = (
                    [str(w) for w in raw_regen_warnings] if raw_regen_warnings else []
                )

                # Replace current script (carry source_test_case_id forward — AC2/13.8)
                self._generated_scripts[self._current_review_index] = GeneratedScript(
                    test_case=test_case,
                    script_content=full_script_content,
                    file_path=filename,
                    confidence=script_data.get("confidence", 0.5),
                    warnings=regen_warnings,
                    source_test_case_id=source_tc_id,
                )

                return StageResult(
                    success=True,
                    data=self._generated_scripts,
                    errors=[],
                    warnings=result.warnings if result.warnings else [],
                    confidence=result.confidence,
                )
            else:
                regen_errors = result.errors if result.errors else ["Regeneration failed"]
                # Replace with a failure placeholder so the stale (possibly previously
                # approved) content does not linger; carry source_test_case_id forward
                # and stamp error_message so it is skip-only, never approvable (C3).
                self._generated_scripts[self._current_review_index] = GeneratedScript(
                    test_case=test_case,
                    script_content=f"# Generation failed: {regen_errors[0]}",
                    file_path="",
                    confidence=0.0,
                    approved=False,
                    error_message=regen_errors[0],
                    source_test_case_id=source_tc_id,
                )
                return StageResult(
                    success=False,
                    data=None,
                    errors=regen_errors,
                    warnings=result.warnings if result.warnings else [],
                    confidence=0.0,
                )

        except Exception as e:
            logger.error(f"Error regenerating script: {e}")
            # Replace with a failure placeholder carrying source_test_case_id (C16)
            # and error_message so the failed regen is never approvable (C3).
            self._generated_scripts[self._current_review_index] = GeneratedScript(
                test_case=test_case,
                script_content=f"# Generation failed: {e}",
                file_path="",
                confidence=0.0,
                approved=False,
                error_message=str(e),
                source_test_case_id=source_tc_id,
            )
            return StageResult(
                success=False,
                data=None,
                errors=[f"Regeneration error: {e}"],
                warnings=[],
                confidence=0.0,
            )

    # -------------------------------------------------------------------------
    # Precondition gate (AC3)
    # -------------------------------------------------------------------------

    def _check_preconditions(self) -> list[str]:
        """Return blocking messages (UX-DR12); empty list = all checks pass."""
        ctx = self.project_context
        if not ctx or not ctx.project_id or not ctx.user_id or not ctx.thread_id:
            return ["Start Sarah from inside an active project thread."]
        if ctx.artifact_service is None:
            return ["The backend storage service is unavailable — contact support."]
        return []

    def _format_no_test_cases_message(self) -> str:
        """UX-DR12 message when no approved test cases are found (AC3)."""
        return (
            "**What happened:** Sarah cannot generate scripts yet.\n\n"
            "**Why:** No approved test cases were found for this project.\n\n"
            "**What to do:** Run Mary to generate test cases from approved requirements "
            "and approve at least one test case, then start Sarah again."
        )

    # -------------------------------------------------------------------------
    # Input-selection helpers (AC2)
    # -------------------------------------------------------------------------

    async def _present_test_case_selection(self) -> None:
        """Emit the test_case_selection payload to the frontend (AC2)."""
        if self.project_context is None:
            return
        ctx = self.project_context
        entries = []
        any_from_thread = any(
            a.thread_id is not None and a.thread_id == ctx.thread_id
            for a in self.candidate_test_cases
        )
        for art in self.candidate_test_cases:
            from_thread = art.thread_id is not None and art.thread_id == ctx.thread_id
            # Default-select: current-thread entries always; others only when none from thread
            default_selected = from_thread or not any_from_thread
            parsed = self._testcases_from_artifact(art)
            tc = parsed[0] if parsed else TestCase(title=self._testcase_base(art.name))
            entries.append(
                {
                    "artifact_id": str(art.id),
                    "name": art.name,
                    "title": tc.title,
                    "source_requirement_name": getattr(tc, "source_requirement_name", None),
                    "source_url": getattr(tc, "source_url", None),
                    "confidence_level": getattr(tc, "confidence_level", None),
                    "from_current_thread": from_thread,
                    "default_selected": default_selected,
                    "preview": tc.objective or tc.title,
                }
            )
        await self.send_message(
            content="Please select which test cases to use for script generation.",
            message_type="text",
            metadata={
                "type": "test_case_selection",
                "is_input_selection": True,
                "test_cases": entries,
            },
        )

    async def _confirm_inputs(self, data: dict[str, Any] | None) -> None:
        """Handle user confirmation of input selection (phase == input_selection)."""
        selected_ids: list[str] = []
        if data:
            raw = data.get("selected_artifact_ids")
            if isinstance(raw, list):
                selected_ids = [str(x) for x in raw]

        # Filter candidates to the selected set; fall back to all when nothing given
        selected_set = set(selected_ids)
        filtered = (
            [a for a in self.candidate_test_cases if str(a.id) in selected_set]
            if selected_set
            else list(self.candidate_test_cases)
        )

        if not filtered:
            # Re-present selection with corrective message
            await self.send_message(
                "Please select at least one test case before confirming.",
                message_type="warning",
            )
            await self._present_test_case_selection()
            return

        # Parse confirmed artifacts into TestCase objects + capture source artifact IDs (AC2/13.8).
        confirmed: list[TestCase] = []
        source_ids: list[str | None] = []
        for art in filtered:
            parsed = self._testcases_from_artifact(art)
            if not parsed:
                logger.warning("Could not parse test case artifact %s", art.name)
                continue
            for item in parsed:
                confirmed.append(item)
                source_ids.append(str(art.id))

        if not confirmed:
            await self.send_message(
                "No valid test cases could be parsed from the selection. Please try again.",
                message_type="warning",
            )
            await self._present_test_case_selection()
            return

        self.confirmed_test_cases = confirmed
        self._test_case_source_ids = source_ids  # AC2 (13.8): parallel artifact-ID list
        self.phase = "script_review"
        await self._begin_generation()

    def _project_environments(self) -> list[dict[str, str]]:
        """Return the project's configured target environments (``[{name, url}]``).

        Project-wide and admin-managed (see ``Project.environments``). Returns ``[]`` when
        the project has none, so Sarah falls back to a free-text URL. Only well-formed
        ``{name, url}`` entries are surfaced.
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
            {
                "name": str(entry["name"]),
                "url": str(entry["url"]),
                "login_type": str(entry.get("login_type", "standard")),
            }
            for entry in raw
            if isinstance(entry, dict) and entry.get("name") and entry.get("url")
        ]

    async def _begin_generation(self) -> None:
        """Inputs check (target URL via the chosen environment) → PROCESSING → generate → REVIEW.

        Sarah drives the real app with browser-use SERVER-SIDE, authenticated by the user's
        captured session (resolved per role for the chosen environment) — no local Chrome/CDP
        is required. Only the target application URL (from the selected environment) is needed;
        when it is missing, emit a single ``sarah_inputs_request`` and await a re-start. The
        browser source is then resolved server-side; exploration falls back to vision/LLM-only
        when no captured session (or browser) is available.
        """
        needs_url = not self._target_url
        if needs_url:
            # Await the inputs so the next handle_start re-entry skips the selection
            # gate (keying off this flag, not confirmed_test_cases).
            self._awaiting_inputs = True
            await self.send_message(
                "Hi! I'm Sarah. I'll generate Playwright test scripts from your approved "
                "test cases. First, tell me which application environment to test.",
                message_type="text",
            )
            await self.send_message(
                "Please choose the target environment (or enter the application URL):",
                message_type="info",
                metadata={
                    "type": "sarah_inputs_request",
                    "needs_url": needs_url,
                    # Project-wide target environments: the user PICKS one (its URL becomes
                    # the target; its name is the captured-session key). Sarah authenticates
                    # server-side with the captured session — no local browser needed.
                    "environments": self._project_environments(),
                    "roles": sorted(
                        list({tc.role for tc in self._test_cases if getattr(tc, "role", None)})
                    ),
                },
            )
            await self.transition_to(AgentState.START)
            return

        # Target available — clear the re-entry flag.
        self._awaiting_inputs = False

        # Re-resolve the LLM config against the attached context before generation
        # (defensive + idempotent): the awaiting-inputs re-entry path reaches here
        # WITHOUT going through handle_start's resolve, so this is the first/only resolve
        # on that path. Surface a UX-DR12 message on a genuinely missing key.
        try:
            self._ensure_llm_ready()
        except Exception as exc:
            logger.error("Sarah could not resolve the LLM config: %s", exc, exc_info=True)
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message([str(exc)]),
                message_type="error",
            )
            return

        await self.send_message(
            "Thanks! Generating scripts from your approved test cases against "
            f"{self._target_url} …",
            message_type="text",
        )
        await self.transition_to(AgentState.PROCESSING)
        try:
            result = await self.process(self._start_input_data, feedback=None)
        except Exception as exc:
            logger.error("Sarah process failed: %s", exc)
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message([str(exc)]),
                message_type="error",
            )
            return

        if result.success:
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self._present_script_review()
        else:
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message(result.errors),
                message_type="error",
            )

    async def handle_start(self, input_data: dict[str, Any]) -> None:
        """Override handle_start to insert the input-selection gate (13.1).

        Flow: preconditions → load approved test cases → AC3 block if empty →
        present test_case_selection (REVIEW_REQUEST).  After the user confirms,
        handle_approve dispatches to _confirm_inputs → _begin_generation (chrome-
        path check → PROCESSING → generate → per-item script review).

        Re-entry when Chrome path was missing: if we are awaiting a Chrome path
        (``_awaiting_inputs``), skip the selection gate and go straight to
        _begin_generation, preserving the already-confirmed selection.
        """
        await self.send_message(
            "I'll generate Playwright test scripts for your approved test cases."
        )

        # Store input_data for context preservation in reject/regeneration
        self._start_input_data = input_data

        # Re-entry after inputs were missing: capture the submitted target URL +
        # Chrome path (transient, per-run), then skip the selection gate and go straight
        # to generation with the already-confirmed test cases.
        if self._awaiting_inputs:
            submitted_chrome = (input_data.get("chrome_path") or "").strip()
            if submitted_chrome:
                self._chrome_path = submitted_chrome
            submitted_url = (input_data.get("target_url") or "").strip()
            if submitted_url:
                self._target_url = submitted_url
            submitted_cdp = (input_data.get("cdp_url") or "").strip()
            if submitted_cdp:
                self._cdp_url = submitted_cdp
            # The environment NAME (authoritative session-resolve key) rides the re-start.
            submitted_env = (input_data.get("environment") or "").strip()
            if submitted_env:
                self._environment = submitted_env
            await self._begin_generation()
            return

        # Fresh run: reset all per-run state so a re-start never inherits stale
        # selection / generation / review bookkeeping from a previous run.
        self.phase = "input_selection"
        self.confirmed_test_cases = []
        self.candidate_test_cases = []
        self._generated_scripts = []
        self._reviewed_indices = set()
        self._test_case_source_ids = []
        self._current_review_index = 0
        # Re-ask the application URL + CDP URL each fresh run (run-specific, not
        # saved settings). The Chrome path is also run-specific (no longer persisted),
        # but kept across re-starts of THIS agent instance as a convenience hint.
        self._target_url = None
        self._cdp_url = None
        self._environment = None

        # --- Precondition gate ---
        blockers = self._check_preconditions()
        for msg in blockers:
            await self.send_message(
                content=self._format_error_message([msg]),
                message_type="error",
            )
        if blockers:
            return  # Stay START — re-submittable

        # --- Load approved test cases (AC1) ---
        if self.project_context is None:
            return
        candidates = PipelineArtifactAdapter(self.project_context).load_approved_test_cases()

        # --- AC3 block: no approved test cases ---
        if not candidates:
            await self.send_message(
                content=self._format_no_test_cases_message(),
                message_type="error",
            )
            return  # Stay START — no PROCESSING, no generation

        # Resolve the LLM config now that the context (and the user's encrypted secret
        # store) is attached; surface a clean UX-DR12 message if the key is genuinely
        # missing (mirrors Mary). Done before the selection gate so a missing key fails
        # fast instead of surfacing as a raw provider auth error during generation.
        try:
            self._ensure_llm_ready()
        except Exception as exc:
            logger.error("Sarah could not resolve the LLM config: %s", exc, exc_info=True)
            await self.transition_to(AgentState.ERROR)
            await self.send_message(self._format_error_message([str(exc)]), message_type="error")
            return

        # --- Present input-selection panel (AC2) ---
        self.candidate_test_cases = candidates
        await self.transition_to(AgentState.REVIEW_REQUEST)
        await self._present_test_case_selection()

    def _resolve_script_index(self, data: dict[str, Any] | None) -> int:
        """Resolve the target script index from ``data["script_index"]``.

        Falls back to ``_current_review_index`` when no index is supplied. A malformed
        (non-int) client value degrades to ``-1`` so callers hit the existing out-of-range
        warning instead of raising (C37/C38).
        """
        raw_index = data.get("script_index") if data else None
        if raw_index is None:
            return self._current_review_index
        try:
            return int(raw_index)
        except TypeError, ValueError:
            return -1

    @staticmethod
    def _script_base_name(script: GeneratedScript) -> str:
        """The ``.py`` base name for a script (``{filename}.py`` fallback when no path)."""
        return Path(script.file_path).name or f"{script.test_case.filename}.py"

    def _unique_script_name(self, script: GeneratedScript, index: int) -> str:
        """Return a unique, flat ``.py`` artifact name for the approved script.

        Scripts are saved flat at the folder root. Collisions are resolved PER base name
        across ALL scripts regardless of role. Two test cases that normalise to the same
        base name get a source-test-case (or per-index) suffix so each maps to a distinct artifact.
        """
        base = self._script_base_name(script)

        collides = any(
            i != index and self._script_base_name(other) == base
            for i, other in enumerate(self._generated_scripts)
        )
        if collides:
            stem = Path(base).stem
            suffix = script.source_test_case_id or str(index)
            base = f"{stem}__{suffix}.py"

        return base

    async def handle_approve(self, data: dict[str, Any] | None = None) -> None:
        """Handle approve — phase-dispatched.

        * ``phase == "input_selection"``: user confirmed the test-case selection set.
        * ``phase == "script_review"`` (or any other): existing per-item script-review
          approve logic (Epic 5, unchanged).
        """
        if self.phase == "input_selection":
            await self._confirm_inputs(data)
            return

        # --- Script-review branch: index-addressable approve (13.5) ---

        # Route skip through approve with action discriminator (WS only dispatches approve/reject)
        action = data.get("action", "") if data else ""
        if action == "skip":
            await self._handle_skip_script(data)
            return

        # Resolve target index: data["script_index"] falls back to _current_review_index.
        # A malformed client value degrades to the out-of-range warning (C37) rather than raising.
        index = self._resolve_script_index(data)

        if index < 0 or index >= len(self._generated_scripts):
            await self.send_message(
                "No script to approve at that index.",
                message_type="warning",
            )
            return

        # --- 13.6: edit + validate step ---
        current_script = self._generated_scripts[index]

        # C3: a failed-generation placeholder (error_message set) is skip-only, never
        # approvable — reject the approval, do not advance or save.
        if current_script.error_message is not None:
            await self.send_message(
                "This script failed to generate and cannot be approved. "
                "Skip it (hand to Minh) or reject it to regenerate.",
                message_type="warning",
                metadata={
                    "action": "script_not_approvable",
                    "script_index": index,
                },
            )
            return

        edited: Any = data.get("script_content") if data else None
        if isinstance(edited, str) and edited.strip():
            result = validate_script(edited, unsafe_patterns=self._unsafe_patterns())
            if not result.is_valid:
                # AC2: actionable errors; do NOT save/approve/advance; stay REVIEW_REQUEST.
                # Critical: do NOT re-emit _present_script_review() — that would send the
                # original script_content and overwrite the client's edit buffer (AC1 violation).
                await self.send_message(
                    content=self._format_validation_errors(result.errors),
                    message_type="error",
                    metadata={
                        "type": "script_validation_error",
                        "script_index": index,
                        "errors": [e.model_dump() for e in result.errors],
                    },
                )
                return
            # AC3: editing approved → authoritative content is the edited version
            current_script.script_content = edited
            current_script.validation_status = "validated"  # AC2 (13.8): track validated edit

        # Mark script as approved and persist.
        # AC3 (13.7): only approved scripts are persisted to test_scripts/ (kind="playwright_script").
        # The approved flag + approved_by/approved_at are the Jack-eligibility discriminator
        # consumed by Story 15.1 (load_approved_scripts). Rejected/skipped/regenerated scripts
        # are never marked or saved as approved.
        current_script.approved = True
        if self.project_context is None:
            raise ValueError("SarahAgent requires an active project context.")

        # C17/C18: derive a UNIQUE-per-test-case script artifact name. The base name is the
        # .py filename (with a .py fallback when file_path is empty). If another script in
        # this run normalises to the same name, disambiguate with the source test case ID
        # (or a per-index suffix) so each test case maps to a distinct artifact. The saved
        # name is recorded on the script so the sidecar (C18) shares the same stem.
        save_name = self._unique_script_name(current_script, index)
        current_script.saved_file_name = save_name

        PipelineArtifactAdapter(self.project_context).save_script(
            save_name,
            current_script.script_content,
        )

        # AC1 (13.7): stamp who approved and when. Mirrors 12.4's TestCase stamp.
        # Durable sidecar persistence of these fields is Story 13.8.
        assert self.project_context is not None  # narrowed above
        current_script.approved_by = self.project_context.user_email or str(
            self.project_context.user_id
        )
        current_script.approved_at = datetime.now(UTC).isoformat()

        await self.send_message(
            f"Script '{current_script.test_case.title}' approved and saved.",
            message_type="success",
            metadata={
                "action": "script_approved",
                "file_path": current_script.file_path,
                "script_index": index,
            },
        )

        self._reviewed_indices.add(index)
        self._current_review_index = index

        # DONE when every script has been reviewed (approved OR skipped)
        if len(self._reviewed_indices) >= len(self._generated_scripts):
            # C39: re-emit the present-all payload ONCE before DONE so the final approved
            # script's approved_by/approved_at/status reach the client (AC1 of 13.7).
            await self._present_script_review()
            await self._write_approved_scripts_metadata()
            await self.transition_to(AgentState.DONE)
            approved_count = sum(1 for s in self._generated_scripts if s.approved)
            await self.send_message(
                f"{approved_count} of {len(self._generated_scripts)} scripts approved and saved "
                "to project artifacts",
                message_type="success",
            )
        else:
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self._present_script_review()

    async def handle_reject(self, feedback: str, data: dict[str, Any] | None = None) -> None:
        """Handle rejection of a script with feedback (index-addressable, 13.5).

        Args:
            feedback: User rejection feedback
            data: Optional payload carrying ``script_index`` (defaults to
                  ``_current_review_index`` for back-compat).
        """
        # C37: malformed client index degrades to the out-of-range warning, not a raise.
        index = self._resolve_script_index(data)

        if index < 0 or index >= len(self._generated_scripts):
            await self.send_message(
                "No script to reject at that index.",
                message_type="warning",
            )
            return

        # Set index before regeneration so _regenerate_current_script targets the right one
        self._current_review_index = index

        # Clear the prior approval/review state for the rejected script.
        # AC2/AC3 (13.7): a rejected script is never eligible for Jack execution.
        self._generated_scripts[index].approved = False
        self._generated_scripts[index].approved_by = None
        self._generated_scripts[index].approved_at = None
        self._reviewed_indices.discard(index)

        current_script = self._generated_scripts[index]

        await self.send_message(
            f"I'll revise the script for '{current_script.test_case.title}' "
            f"to address your feedback: '{feedback}'",
            message_type="text",
        )

        await self.transition_to(AgentState.PROCESSING)

        try:
            result = await self.process(self._start_input_data, feedback=feedback)

            if result.success:
                await self.transition_to(AgentState.REVIEW_REQUEST)
                await self._present_script_review()
            else:
                await self.transition_to(AgentState.ERROR)
                await self.send_message(
                    content=self._format_error_message(result.errors),
                    message_type="error",
                )
        except Exception as e:
            logger.error(f"Error handling reject: {e}")
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                f"Failed to regenerate script: {e}",
                message_type="error",
            )

    async def handle_skip(self) -> None:
        """Handle skip request via direct call (back-compat shim; routes to _handle_skip_script)."""
        await self._handle_skip_script(None)

    async def _handle_skip_script(self, data: dict[str, Any] | None) -> None:
        """Skip a script by index (index-addressable, 13.5).

        Skip = hand off to Minh for manual review; script not saved but still accessible.
        Routed from handle_approve when data["action"] == "skip".
        """
        # C37: malformed client index degrades to the out-of-range warning, not a raise.
        index = self._resolve_script_index(data)

        if index < 0 or index >= len(self._generated_scripts):
            await self.send_message(
                "No script to skip at that index.",
                message_type="warning",
            )
            return

        current_script = self._generated_scripts[index]

        await self.send_message(
            f"Script '{current_script.test_case.title}' skipped. "
            f"It will remain available for manual review by Minh.",
            message_type="info",
            metadata={
                "action": "script_skipped",
                "file_path": current_script.file_path,
                "script_index": index,
            },
        )

        self._reviewed_indices.add(index)
        self._current_review_index = index

        if len(self._reviewed_indices) >= len(self._generated_scripts):
            await self._write_approved_scripts_metadata()
            await self.transition_to(AgentState.DONE)
            approved_count = sum(1 for s in self._generated_scripts if s.approved)
            await self.send_message(
                f"Review complete. {approved_count} of {len(self._generated_scripts)} "
                "scripts approved and saved to project artifacts",
                message_type="success",
            )
        else:
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self._present_script_review()

    async def handle_navigate(self, direction: str) -> None:
        """Handle navigation between scripts.

        Args:
            direction: "next" or "previous"
        """
        if direction == "next":
            if self._current_review_index < len(self._generated_scripts) - 1:
                self._current_review_index += 1
                await self._present_current_script_for_review()
            else:
                await self.send_message(
                    "Already at the last script.",
                    message_type="warning",
                )
        elif direction == "previous":
            if self._current_review_index > 0:
                self._current_review_index -= 1
                await self._present_current_script_for_review()
            else:
                await self.send_message(
                    "Already at the first script.",
                    message_type="warning",
                )
        else:
            await self.send_message(
                f"Invalid navigation direction: {direction}. Use 'next' or 'previous'.",
                message_type="error",
            )

    async def _present_script_review(self) -> None:
        """Present all generated scripts in a single present-all payload (13.5).

        Emits metadata.type=="script_review" with the full scripts list so the
        frontend panel owns Prev/Next and can display per-item review status.
        Replaces the one-at-a-time _present_current_script_for_review call sites.
        """
        if not self._generated_scripts:
            await self.send_message(
                "No scripts to review.",
                message_type="warning",
            )
            return

        scripts_payload: list[dict[str, Any]] = []
        for i, s in enumerate(self._generated_scripts):
            raw_warnings = getattr(s, "warnings", [])
            warnings_list: list[str] = list(raw_warnings) if raw_warnings else []
            if i in self._reviewed_indices:
                status = "approved" if s.approved else "skipped"
            else:
                status = "pending"
            scripts_payload.append(
                {
                    "index": i,
                    "test_case": s.test_case.model_dump(),
                    "script_content": s.script_content,
                    "script_language": "python",
                    "file_path": s.file_path,
                    "confidence": s.confidence,
                    "warnings": warnings_list,
                    "approved": s.approved,
                    "approved_by": s.approved_by,
                    "approved_at": s.approved_at,
                    "status": status,
                    "error_message": s.error_message,
                }
            )

        total = len(self._generated_scripts)
        await self.send_message(
            content=f"Review {total} generated script(s)",
            message_type="text",
            metadata={
                "type": "script_review",
                "scripts": scripts_payload,
                "current_index": self._current_review_index,
                "total_count": total,
            },
        )

    async def _present_current_script_for_review(self) -> None:
        """Present current script for side-by-side review (back-compat; kept for tests)."""
        if not self._generated_scripts or self._current_review_index >= len(
            self._generated_scripts
        ):
            await self.send_message(
                "No scripts to review.",
                message_type="warning",
            )
            return

        script = self._generated_scripts[self._current_review_index]
        total = len(self._generated_scripts)
        current = self._current_review_index + 1

        # Format review data for side-by-side display
        review_data = {
            "test_case": script.test_case.model_dump(),
            "script_content": script.script_content,
            "script_language": "python",
            "current_index": current,
            "total_count": total,
            "can_approve": True,
            "can_reject": True,
            "can_skip": True,
            "file_path": script.file_path,
            "confidence": script.confidence,
            "warnings": script.warnings,
        }

        await self.send_message(
            content=f"Script {current} of {total}: {script.test_case.title}",
            message_type="text",
            metadata={
                "type": "review_request",
                "review_data": review_data,
                "current_index": self._current_review_index,
                "total_count": total,
            },
        )

    async def _write_approved_scripts_metadata(self) -> None:
        """Write real provenance side-car for APPROVED scripts only (AC1, AC2 — 13.8).

        Iterates only approved scripts; skipped/failed/unapproved scripts are excluded
        so the configuration/ folder never contains metadata for unreviewed scripts.
        The side-car is the sole durable home for script-specific provenance because
        the script is saved as raw .py text (no model_dump_json content carrier).
        """
        if self.project_context is None:
            raise ValueError("SarahAgent requires an active project context.")

        adapter = PipelineArtifactAdapter(self.project_context)
        for script in self._generated_scripts:
            if not script.approved:
                continue
            # C18: derive the sidecar name from the SAME (flat) name as the saved
            # .py so the script and its sidecar stay 1:1.
            saved_name = script.saved_file_name or self._script_base_name(script)
            sidecar_name = (
                f"{saved_name.removesuffix('.py')}.metadata.json"
                if saved_name.endswith(".py")
                else f"{Path(saved_name).stem}.metadata.json"
            )
            try:
                adapter.save_metadata(
                    sidecar_name,
                    {
                        "source_test_case_id": script.source_test_case_id,
                        "logical_path": script.file_path,
                        # Role the script runs as (Slice 5) — the per-role grouping key a
                        # future role-aware Jack uses (different roles = different accounts).
                        "role": script.test_case.role,
                        "approved_by": script.approved_by,
                        "approved_at": script.approved_at,
                        "validation_status": script.validation_status,
                        "model": self.config.model_name,
                        "confidence": script.confidence,
                        "test_case_title": script.test_case.title,
                    },
                )
            except Exception as e:
                logger.warning("Failed to save metadata for %s: %s", script.test_case.title, e)

    # -------------------------------------------------------------------------
    # 13.6 helpers — validation
    # -------------------------------------------------------------------------

    def _unsafe_patterns(self) -> list[str]:
        """Return the active unsafe-pattern denylist from AppSettings.

        An empty ``script_unsafe_patterns`` means "use the module default".
        """
        from ai_qa.pipelines.script_validator import DEFAULT_UNSAFE_SCRIPT_PATTERNS

        configured = self.app_settings.script_unsafe_patterns
        return configured if configured else list(DEFAULT_UNSAFE_SCRIPT_PATTERNS)

    def _format_validation_errors(self, errors: list[ScriptValidationError]) -> str:
        """Format validation errors as a three-part UX-DR12 actionable message."""
        error_lines = []
        for err in errors:
            prefix = f"Line {err.line}: " if err.line is not None else ""
            error_lines.append(f"- {prefix}{err.message}")
        error_body = "\n".join(error_lines)
        return (
            "**What happened:** Your edited script did not pass validation.\n\n"
            f"**Why:**\n{error_body}\n\n"
            "**What to do:** Fix the highlighted issues in the Edit pane and approve again "
            "— your edits were kept."
        )

    def _format_review_content(self, result: StageResult) -> str:
        """Format review content for display.

        Args:
            result: StageResult with generated scripts

        Returns:
            Formatted markdown string
        """
        if not self._generated_scripts:
            return "No scripts to review."

        script = self._generated_scripts[self._current_review_index]
        total = len(self._generated_scripts)
        current = self._current_review_index + 1

        lines = [
            f"## Script {current} of {total}: {script.test_case.title}",
            "",
            "**Test Case (Left Panel):**",
            f"- Title: {script.test_case.title}",
            f"- Steps: {len(script.test_case.steps)}",
            f"- Expected Results: {len(script.test_case.expected_results)}",
            "",
            "**Generated Script (Right Panel):**",
            f"- File: {script.file_path}",
            f"- Confidence: {script.confidence:.2f}",
            "",
            "Please review the script. Click **Approve** to save, "
            "**Reject** to provide feedback for revision, or **Skip** "
            "to hand to Minh for manual review.",
        ]

        return "\n".join(lines)

    def get_review_state(self) -> dict[str, Any]:
        """Get current review state for frontend.

        Returns:
            Dictionary with review state information (consistent shape)
        """
        if not self._generated_scripts:
            return {
                "has_scripts": False,
                "current_index": 0,
                "total_count": 0,
                "current_script": None,
                "approved_count": 0,
            }

        return {
            "has_scripts": True,
            "current_index": self._current_review_index,
            "total_count": len(self._generated_scripts),
            "current_script": (
                self._generated_scripts[self._current_review_index].test_case.title
                if self._current_review_index < len(self._generated_scripts)
                else None
            ),
            "approved_count": sum(1 for s in self._generated_scripts if s.approved),
        }
