# mypy: disable-error-code="misc"
"""Script generator pipeline stage.

Converts structured test cases into executable Playwright Python scripts via LLM.
"""

import logging
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from ai_qa.ai_connection.client import LLMClient
from ai_qa.ai_connection.config import LLMConfig
from ai_qa.config import AppSettings
from ai_qa.exceptions import ScriptGenerationError, VisionError
from ai_qa.models import StageResult, TestCase
from ai_qa.pipelines.vision_locator import LocatorResult, VisionLocator
from ai_qa.prompts.script_generation import (
    SCRIPT_GENERATION_PROMPT,
    SCRIPT_GENERATION_SYSTEM_PROMPT,
    TRACE_TO_PLAYWRIGHT_PROMPT,
    TRACE_TO_PLAYWRIGHT_SYSTEM_PROMPT,
    VISION_ASSISTED_SCRIPT_GENERATION_PROMPT,
    VISION_SCRIPT_GENERATION_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

# 13.3 — module-level compiled patterns for brittle-selector and step-attribution detection
_STEP_COMMENT_RE = re.compile(r"^\s*#\s*Step\s+(\d+)\b", re.IGNORECASE)
_XPATH_LOCATOR_RE = re.compile(r'\.locator\(\s*["\']xpath=')
_CSS_LOCATOR_RE = re.compile(r'\.locator\(\s*["\'](?!xpath=)[^"\']+["\']')

# 13.4 — module-level compiled patterns for credential/secret and auth detection
# Matches .fill/.type/.press_sequentially with a non-empty string literal
_CRED_FILL_LITERAL_RE = re.compile(
    r'\.(fill|type|press_sequentially)\s*\(\s*["\']([^"\']+)["\']',
)
# Credential-like keywords used to identify credential context (locator text, step comment).
# AC1/AC3 enumerate "usernames" alongside passwords/tokens, so username/user/login/email
# tokens are included — a literal filled into a username-named locator is flagged for review.
_CRED_KEYWORD_RE = re.compile(
    r"\b(?:password|passwd|pwd|secret|token|otp|credential|api_key|auth"
    r"|username|user|login|email)\b",
    re.IGNORECASE,
)
# Secret-named variable assignment with a non-empty string literal
_SECRET_VAR_ASSIGN_RE = re.compile(
    r"\b(password|passwd|pwd|token|api_key|secret|cookie|bearer|session)"
    r"\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
# add_cookies( call — always a credential-injection risk
_ADD_COOKIES_RE = re.compile(r"\.add_cookies\s*\(")
# Inline storage_state dict (allowed: storage_state="path" string; forbidden: storage_state={...})
_INLINE_STORAGE_STATE_DICT_RE = re.compile(r"\bstorage_state\s*=\s*\{")
# Authorization header with a literal Bearer/Basic token value
_AUTH_BEARER_LITERAL_RE = re.compile(
    r'["\']Authorization["\']\s*[,:]\s*["\'](?:Bearer|Basic)\s+[^"\']+["\']',
    re.IGNORECASE,
)
# URL with embedded credentials (scheme://user:pass@host)
_CREDS_IN_URL_RE = re.compile(
    r"[a-z][a-z0-9+\-.]*://[^\s\"'@/]+:[^\s\"'@/]+@",
    re.IGNORECASE,
)
# Approved env-read patterns (not flagged even when appearing on lines with secret var names)
_ENV_READ_RE = re.compile(r"\bos\.environ\b|\bos\.getenv\b")
# SSO/session-setup REVIEW marker already emitted by the LLM (suppresses duplicate auth warning)
_SSO_REVIEW_MARKER_RE = re.compile(r"#\s*REVIEW:.*?SSO", re.IGNORECASE)
# Auth-action keywords (login, sign-in, authenticate, …) for the auth-likely signal
_AUTH_KEYWORD_RE = re.compile(
    r"\b(?:login|log[-\s]?in|sign[-\s]?in|authenticate|logout|credentials?)\b",
    re.IGNORECASE,
)
# Auth-state keywords in preconditions ("User is authenticated / logged in / signed in")
_AUTH_PRECOND_RE = re.compile(
    r"\b(?:authenticated|logged[-\s]?in|signed[-\s]?in)\b",
    re.IGNORECASE,
)


class ScriptGenerator:
    """Pipeline stage for generating Playwright Python scripts from test cases.

    Uses LLM to convert natural language test cases into executable, well-structured
    test files with stable selectors and proper assertions.
    """

    def __init__(
        self,
        output_base_dir: Path,
        llm_config: LLMConfig | None = None,
        config: AppSettings | None = None,
        vision_locator: VisionLocator | None = None,
        explore_llm: Any = None,
        chrome_path: str = "",
        cdp_url: str = "",
    ) -> None:
        """Initialize the script generator.

        Args:
            output_base_dir: Base directory for script output (workspace/testscripts/)
            llm_config: Optional LLM configuration. If None, loads from agents.json.
            config: Optional AppSettings for script generation configuration.
            vision_locator: Optional VisionLocator for vision-assisted generation.
            explore_llm: Optional ``browser_use.llm`` chat model (from
                ``build_browser_use_llm``) used to DRIVE the real app and capture a
                verified trace. When set together with ``chrome_path``, generation
                prefers the trace path (real selectors) over LLM-invention.
            chrome_path: Path to the user's Chrome executable for live exploration.
        """
        self.output_base_dir = output_base_dir
        self._llm_config = llm_config
        self._config = config or AppSettings()
        self._vision_locator = vision_locator
        self._vision_enabled = (
            vision_locator is not None and getattr(config, "vision_enabled", True)
            if config
            else vision_locator is not None
        )
        self._explore_llm = explore_llm
        self._chrome_path = chrome_path
        self._cdp_url = cdp_url
        # browser-use-driven generation requires a driving LLM + a browser source
        # (a Chrome executable to launch, or a CDP URL to connect to a running one).
        self._explore_enabled = explore_llm is not None and (bool(chrome_path) or bool(cdp_url))

    async def generate(
        self,
        test_cases: list[TestCase],
        target_url: str | None = None,
        feedback: str | None = None,
    ) -> StageResult:
        """Generate Playwright scripts from test cases.

        Args:
            test_cases: List of structured test cases to convert to scripts.
            target_url: Optional target application URL for vision-assisted generation.
            feedback: Optional reviewer rejection feedback (AC2 — 13.7) injected into the
                      regeneration prompt so the revised script reflects the correction.

        Returns:
            StageResult with list of generated script paths on success.
        """
        if not test_cases:
            return StageResult(
                success=True,
                data=[],
                errors=[],
                warnings=["No test cases provided - no scripts generated"],
                confidence=1.0,
            )

        generated_scripts: list[dict[str, Any]] = []
        errors: list[str] = []
        warnings: list[str] = []
        total_confidence = 0.0

        for test_case in test_cases:
            try:
                result = await self._generate_single_script(
                    test_case, target_url, feedback=feedback
                )
                if result["success"]:
                    generated_scripts.append(result)
                    total_confidence += result.get("confidence", 0.5)
                    if result.get("warnings"):
                        warnings.extend(result["warnings"])
                else:
                    errors.append(
                        f"Failed to generate script for '{test_case.title}': {result.get('error', 'Unknown error')}"
                    )
                    warnings.append(f"Script generation failed for test case: {test_case.title}")
            except Exception as e:
                logger.error(f"Error generating script for '{test_case.title}': {e}")
                errors.append(f"Exception generating script for '{test_case.title}': {e}")
                warnings.append(f"Script generation exception for test case: {test_case.title}")

        # Calculate overall confidence
        if generated_scripts:
            avg_confidence = total_confidence / len(generated_scripts)
        else:
            avg_confidence = 0.0

        # Flag low confidence if below threshold
        confidence_threshold = getattr(self._config, "confidence_threshold", 0.7)
        if avg_confidence < confidence_threshold and generated_scripts:
            warnings.append(
                f"Low confidence generation: {avg_confidence:.2f} (threshold: {confidence_threshold})"
            )

        success = len(generated_scripts) > 0 or not errors

        return StageResult(
            success=success,
            data=generated_scripts if generated_scripts else None,
            errors=errors,
            warnings=warnings,
            confidence=avg_confidence if generated_scripts else 0.0,
        )

    async def _generate_single_script(
        self,
        test_case: TestCase,
        target_url: str | None = None,
        feedback: str | None = None,
    ) -> dict[str, Any]:
        """Generate a single Playwright script from a test case.

        Args:
            test_case: The test case to convert to a script.
            target_url: Optional target URL for vision-assisted generation.
            feedback: Optional reviewer rejection feedback (AC2 — 13.7) appended to the
                      prompt so the revision reflects the correction. Sanitized to 2000 chars.

        Returns:
            Dictionary with script generation result including file path and confidence.
        """
        # PREFERRED: drive the real app with browser-use → verified trace → translate
        # to deterministic Playwright (real selectors, no invention). Gated on a
        # driving LLM + Chrome + target URL; ANY failure falls through to the
        # existing vision / LLM-only generation below.
        if self._explore_enabled and target_url:
            try:
                from ai_qa.browser.explorer import explore_test_case
                from ai_qa.browser.trace import extract_trace

                history = await explore_test_case(
                    test_case,
                    target_url,
                    llm=self._explore_llm,
                    chrome_path=self._chrome_path,
                    cdp_url=self._cdp_url,
                    use_vision=self._vision_enabled,
                )
                if history is not None:
                    trace = extract_trace(history)
                    if trace:
                        script_content = await self._call_llm_with_trace(
                            test_case, trace, feedback=feedback
                        )
                        logger.info(
                            "Generated script for '%s' from a verified browser-use "
                            "trace (%d steps)",
                            test_case.title,
                            len(trace),
                        )
                        return self._postprocess_script(script_content, test_case, [])
            except ScriptGenerationError as e:
                logger.warning(
                    "Trace translation failed for '%s': %s — falling back to LLM generation",
                    test_case.title,
                    e,
                )
            except Exception as e:  # noqa: BLE001 — degrade to fallback on any error
                logger.warning(
                    "browser-use exploration error for '%s': %s — falling back",
                    test_case.title,
                    e,
                )

        locator_results: list[LocatorResult] = []

        # Try vision-assisted generation if enabled and URL provided
        if self._vision_enabled and target_url and self._vision_locator:
            try:
                vision_result = await self._vision_locator.identify_locators(test_case, target_url)
                if vision_result.success and vision_result.data:
                    locator_results = vision_result.data
                    logger.info(
                        f"Vision analysis completed for '{test_case.title}' with "
                        f"{len(locator_results)} locators identified"
                    )
                else:
                    warnings = vision_result.warnings or []
                    errors = vision_result.errors or []
                    logger.warning(
                        f"Vision analysis for '{test_case.title}': "
                        f"warnings={warnings}, errors={errors}"
                    )
                    if not getattr(self._config, "vision_fallback_on_error", True):
                        return {
                            "success": False,
                            "error": f"Vision analysis failed: {errors}",
                            "test_case_title": test_case.title,
                        }
            except VisionError as e:
                logger.warning(f"Vision analysis failed for '{test_case.title}': {e}")
                if not getattr(self._config, "vision_fallback_on_error", True):
                    return {
                        "success": False,
                        "error": f"Vision error: {e.message}",
                        "test_case_title": test_case.title,
                    }
                # Fall through to LLM-only generation

        try:
            # Generate script via LLM (with or without vision context)
            if locator_results:
                script_content = await self._call_llm_with_vision(
                    test_case, locator_results, feedback=feedback
                )
            else:
                script_content = await self._call_llm(test_case, feedback=feedback)

            return self._postprocess_script(script_content, test_case, locator_results)

        except ScriptGenerationError as e:
            logger.error(f"Script generation error for '{test_case.title}': {e}")
            return {
                "success": False,
                "error": str(e),
                "test_case_title": test_case.title,
            }
        except Exception as e:
            logger.error(f"Unexpected error generating script for '{test_case.title}': {e}")
            return {
                "success": False,
                "error": f"Unexpected error: {e}",
                "test_case_title": test_case.title,
            }

    def _postprocess_script(
        self,
        script_content: str,
        test_case: TestCase,
        locator_results: list[LocatorResult],
    ) -> dict[str, Any]:
        """Validate, score, and warning-scan a generated script (shared by the
        trace, vision, and LLM-only paths so all get identical downstream handling).
        """
        if not script_content or not script_content.strip():
            return {
                "success": False,
                "error": "LLM returned empty script",
                "test_case_title": test_case.title,
            }

        max_length = getattr(self._config, "max_script_length", 10000)
        if len(script_content) > max_length:
            return {
                "success": False,
                "error": (
                    f"Generated script exceeds max length ({len(script_content)} > {max_length})"
                ),
                "test_case_title": test_case.title,
            }

        confidence = self._calculate_confidence(script_content, test_case, locator_results)
        all_warnings: list[str] = (
            self._extract_review_warnings(script_content)
            + self._detect_brittle_selectors(script_content)
            + self._detect_assertion_gaps(script_content, test_case)
            + self._detect_hardcoded_secrets(script_content)
            + self._detect_auth_setup_needed(script_content, test_case)
        )
        return {
            "success": True,
            "script_content": script_content,
            "test_case_title": test_case.title,
            "confidence": confidence,
            "warnings": all_warnings,
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _call_llm(self, test_case: TestCase, feedback: str | None = None) -> str:
        """Call LLM to generate a Playwright script from a test case.

        Args:
            test_case: The test case to convert.
            feedback: Optional reviewer feedback (AC2 — 13.7) appended to the prompt.

        Returns:
            Generated Python script content.

        Raises:
            ScriptGenerationError: If LLM call fails after retries.
        """
        try:
            llm_client = self._get_llm_client()

            # Format the prompt with test case data
            test_case_md = test_case.to_markdown()
            prompt = SCRIPT_GENERATION_PROMPT.format(test_case=test_case_md)
            # AC2 (13.7): inject reviewer feedback so regenerated script reflects the correction.
            if feedback and feedback.strip():
                sanitized = feedback.strip()[:2000]
                prompt += (
                    "\n\n---\nReviewer feedback to address in this revision:\n"
                    + sanitized
                    + "\n---"
                )

            # Create messages for LLM
            from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

            messages: list[BaseMessage] = [
                SystemMessage(content=SCRIPT_GENERATION_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]

            # Call LLM
            timeout = getattr(self._config, "script_generation_timeout", 120)
            response = llm_client.invoke(messages, timeout=timeout)

            # Extract script content from response
            script_content = response.content

            # Handle both string and list content types from LangChain
            if isinstance(script_content, list):
                # Concatenate list items into a single string with type-safe handling
                parts: list[str] = []
                for item in script_content:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        # Extract text from dict with safe access
                        text = item.get("text")
                        if isinstance(text, str):
                            parts.append(text)
                        elif text is not None:
                            parts.append(str(text))
                    else:
                        parts.append(str(item))
                script_content = "\n".join(parts)

            if not isinstance(script_content, str) or not script_content.strip():
                raise ScriptGenerationError("LLM returned empty response")

            return script_content.strip()

        except Exception as e:
            if isinstance(e, ScriptGenerationError):
                raise
            logger.error(f"LLM call failed: {e}")
            raise ScriptGenerationError(f"LLM generation failed: {e}") from e

    async def _call_llm_with_trace(
        self,
        test_case: TestCase,
        trace: list[dict[str, Any]],
        feedback: str | None = None,
    ) -> str:
        """Translate a VERIFIED browser-use action trace into a Playwright script.

        The trace was captured by driving the real app, so its selectors are real
        (not invented). The LLM's job is translation, not invention. Mirrors
        :meth:`_call_llm` so the same downstream validators/confidence apply.

        Args:
            test_case: The test case the trace was explored for.
            trace: Structured ``[{action, params, element}]`` from ``extract_trace``.
            feedback: Optional reviewer feedback appended to the prompt (13.7).

        Returns:
            Generated Python script content.

        Raises:
            ScriptGenerationError: If the LLM call fails or returns empty.
        """
        from ai_qa.browser.trace import format_trace_for_prompt

        try:
            llm_client = self._get_llm_client()
            test_case_md = test_case.to_markdown()
            prompt = TRACE_TO_PLAYWRIGHT_PROMPT.format(
                test_case=test_case_md,
                trace=format_trace_for_prompt(trace),
            )
            if feedback and feedback.strip():
                sanitized = feedback.strip()[:2000]
                prompt += (
                    "\n\n---\nReviewer feedback to address in this revision:\n"
                    + sanitized
                    + "\n---"
                )

            from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

            messages: list[BaseMessage] = [
                SystemMessage(content=TRACE_TO_PLAYWRIGHT_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
            timeout = getattr(self._config, "script_generation_timeout", 120)
            response = llm_client.invoke(messages, timeout=timeout)

            script_content = response.content
            if isinstance(script_content, list):
                parts: list[str] = []
                for item in script_content:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        text = item.get("text")
                        parts.append(text if isinstance(text, str) else str(text))
                    else:
                        parts.append(str(item))
                script_content = "\n".join(parts)

            if not isinstance(script_content, str) or not script_content.strip():
                raise ScriptGenerationError("LLM returned empty response")
            return script_content.strip()

        except Exception as e:
            if isinstance(e, ScriptGenerationError):
                raise
            logger.error(f"Trace-to-Playwright LLM call failed: {e}")
            raise ScriptGenerationError(f"Trace translation failed: {e}") from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _call_llm_with_vision(
        self,
        test_case: TestCase,
        locator_results: list[LocatorResult],
        feedback: str | None = None,
    ) -> str:
        """Call LLM to generate a Playwright script with vision context.

        Args:
            test_case: The test case to convert.
            locator_results: Vision analysis results with identified locators.
            feedback: Optional reviewer feedback (AC2 — 13.7) appended to the prompt.

        Returns:
            Generated Python script content.

        Raises:
            ScriptGenerationError: If LLM call fails after retries.
        """
        try:
            llm_client = self._get_llm_client()

            # Format the prompt with test case and vision data
            test_case_md = test_case.to_markdown()
            locator_info = self._format_locator_info(locator_results)
            vision_context = "Vision-assisted analysis was performed on the target application."

            prompt = VISION_ASSISTED_SCRIPT_GENERATION_PROMPT.format(
                test_case=test_case_md,
                vision_context=vision_context,
                locator_info=locator_info,
            )
            # AC2 (13.7): inject reviewer feedback so regenerated script reflects the correction.
            if feedback and feedback.strip():
                sanitized = feedback.strip()[:2000]
                prompt += (
                    "\n\n---\nReviewer feedback to address in this revision:\n"
                    + sanitized
                    + "\n---"
                )

            # Create messages for LLM
            from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

            messages: list[BaseMessage] = [
                SystemMessage(content=VISION_SCRIPT_GENERATION_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]

            # Call LLM
            timeout = getattr(self._config, "script_generation_timeout", 120)
            response = llm_client.invoke(messages, timeout=timeout)

            # Extract script content from response
            script_content = response.content

            # Handle both string and list content types from LangChain
            if isinstance(script_content, list):
                parts: list[str] = []
                for item in script_content:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        text = item.get("text")
                        if isinstance(text, str):
                            parts.append(text)
                        elif text is not None:
                            parts.append(str(text))
                    else:
                        parts.append(str(item))
                script_content = "\n".join(parts)

            if not isinstance(script_content, str) or not script_content.strip():
                raise ScriptGenerationError(
                    "LLM returned empty response for vision-assisted generation"
                )

            return script_content.strip()

        except Exception as e:
            if isinstance(e, ScriptGenerationError):
                raise
            logger.error(f"Vision-assisted LLM call failed: {e}")
            raise ScriptGenerationError(f"Vision-assisted LLM generation failed: {e}") from e

    def _format_locator_info(self, locator_results: list[LocatorResult]) -> str:
        """Format locator results for inclusion in LLM prompt.

        Args:
            locator_results: List of locator analysis results.

        Returns:
            Formatted string describing locators.
        """
        lines: list[str] = []

        for result in locator_results:
            lines.append(f"\nStep {result.step_number}: {result.element_description}")
            lines.append(f"  Validation Status: {result.validation_status}")
            lines.append(f"  Overall Confidence: {result.confidence:.2f}")

            if result.selectors:
                lines.append("  Identified Selectors (in priority order):")
                for i, selector in enumerate(result.selectors[:3], 1):  # Top 3 selectors
                    validated_mark = "[✓]" if selector.validated else "[ ]"
                    lines.append(
                        f"    {i}. {validated_mark} {selector.type}='{selector.value}' "
                        f"(confidence: {selector.confidence:.2f})"
                    )
            else:
                lines.append("  No selectors identified")

        return "\n".join(lines)

    def _get_llm_client(self) -> LLMClient:
        """Get or create LLM client.

        Returns:
            Configured LLMClient instance.
        """
        if self._llm_config:
            return LLMClient(self._llm_config)

        # Build LLM config from AppSettings
        model = getattr(self._config, "script_generation_model", "sonnet")
        temperature = getattr(self._config, "script_generation_temperature", 0.0)

        # TODO: Update ScriptGenerator to accept user_email and load UserConfig
        # For now, safely access config attributes that may have been moved to per-user config
        api_key = getattr(self._config, "on_premises_ai_server_key", "") or getattr(
            self._config, "anthropic_api_key", ""
        )
        base_url = getattr(self._config, "on_premises_ai_server_url", "")

        llm_config = LLMConfig(
            model_name=model,
            temperature=temperature,
            api_key=api_key or "",
            base_url=base_url or "",
        )
        return LLMClient(llm_config)

    _MARKER_RE = re.compile(r"^\s*#\s*(TODO|REVIEW)\b[:\s]*(.*)", re.IGNORECASE)

    def _extract_review_warnings(self, script_content: str) -> list[str]:
        """Scan generated script for TODO/REVIEW markers and return them as warnings.

        Args:
            script_content: The generated Python script text.

        Returns:
            List of warning strings extracted from marker comments.
        """
        warnings: list[str] = []
        for line in script_content.splitlines():
            m = self._MARKER_RE.match(line)
            if m:
                tag = m.group(1).upper()
                text = m.group(2).strip()
                warnings.append(f"{tag}: {text}" if text else tag)
        return warnings

    def _detect_brittle_selectors(self, script_content: str) -> list[str]:
        """Detect brittle selectors (XPath, raw CSS) in the generated script.

        Flags each occurrence with step attribution for AC1/AC3 (13.3).
        Deterministic complement to the LLM's own # REVIEW: markers.

        Args:
            script_content: The generated Python script text.

        Returns:
            List of warning strings, one per brittle-selector occurrence.
        """
        warnings: list[str] = []
        current_step: int | None = None

        for line in script_content.splitlines():
            step_m = _STEP_COMMENT_RE.match(line)
            if step_m:
                current_step = int(step_m.group(1))
                continue

            step_ref = f" (Step {current_step})" if current_step is not None else ""
            suffix = " — prefer get_by_test_id/get_by_role/get_by_label/get_by_text"

            for m in _XPATH_LOCATOR_RE.finditer(line):
                snippet = m.group(0)[:60]
                warnings.append(f"Brittle selector{step_ref}: {snippet}{suffix}")

            for m in _CSS_LOCATOR_RE.finditer(line):
                snippet = m.group(0)[:60]
                warnings.append(f"Brittle selector{step_ref}: {snippet}{suffix}")

        return warnings

    def _detect_assertion_gaps(self, script_content: str, test_case: TestCase) -> list[str]:
        """Detect when fewer expect() assertions than declared expected results were generated.

        Aggregate AC2 gap warning; per-result detail comes from LLM # REVIEW markers (13.3).

        Args:
            script_content: The generated Python script text.
            test_case: Source test case (for expected_results count).

        Returns:
            List with one gap warning string when coverage is insufficient, else empty.
        """
        expected_count = len(test_case.expected_results)
        if expected_count == 0:
            return []
        expect_count = script_content.count("expect(")
        if expect_count < expected_count:
            return [
                f"Assertion gap: only {expect_count} of {expected_count} expected result(s) "
                f"mapped to expect() assertions — review for missing/ambiguous assertions"
            ]
        return []

    def _detect_hardcoded_secrets(self, script_content: str) -> list[str]:
        """Detect hardcoded credential/secret literals in a generated script (13.4 AC1/AC3).

        Deterministic complement to the prompt's no-hardcode-credentials instruction.
        Walks line by line with step attribution from the nearest # Step N: comment.
        Literal values are redacted in the warning text so the warning itself never leaks secrets.

        Args:
            script_content: The generated Python script text.

        Returns:
            List of warning strings, one per occurrence.
        """
        warnings: list[str] = []
        current_step: int | None = None
        current_step_text: str = ""

        for line in script_content.splitlines():
            step_m = _STEP_COMMENT_RE.match(line)
            if step_m:
                current_step = int(step_m.group(1))
                current_step_text = line[step_m.end() :].lstrip(":").strip()
                continue

            step_ref = f" (Step {current_step})" if current_step is not None else ""

            # 1. .fill/.type/.press_sequentially with a literal on a credential-named target
            fill_m = _CRED_FILL_LITERAL_RE.search(line)
            if fill_m and fill_m.group(2):
                method = fill_m.group(1)
                # Check if the locator prefix or the step comment names a credential field
                prefix = line[: fill_m.start()]
                if _CRED_KEYWORD_RE.search(prefix) or _CRED_KEYWORD_RE.search(current_step_text):
                    warnings.append(
                        f"Credential/secret literal{step_ref}: .{method}('<redacted>') — "
                        "never hardcode credentials; reuse the authenticated SSO session"
                    )

            # 2. Secret-named variable assignment with a string literal
            for var_m in _SECRET_VAR_ASSIGN_RE.finditer(line):
                if _ENV_READ_RE.search(line):
                    continue
                var_name = var_m.group(1)
                warnings.append(
                    f"Credential/secret literal{step_ref}: {var_name} = '<redacted>' — "
                    "never hardcode credentials; reuse the authenticated SSO session"
                )

            # 3. add_cookies() call — always a credential-injection risk
            if _ADD_COOKIES_RE.search(line):
                warnings.append(
                    f"Credential/secret literal{step_ref}: add_cookies(<redacted>) — "
                    "never inject cookies with literal values; use a pre-authenticated session"
                )

            # 4. Inline storage_state dict (string path is allowed; inline dict is not)
            if _INLINE_STORAGE_STATE_DICT_RE.search(line):
                warnings.append(
                    f"Credential/secret literal{step_ref}: storage_state={{<redacted>}} — "
                    "use a storage_state file path (string) supplied at execution time, not an inline dict"
                )

            # 5. Authorization header with a literal Bearer/Basic value
            if _AUTH_BEARER_LITERAL_RE.search(line):
                warnings.append(
                    f"Credential/secret literal{step_ref}: Authorization='<redacted>' — "
                    "never hardcode auth header values; reuse the authenticated SSO session"
                )

            # 6. URL with embedded credentials (scheme://user:pass@host)
            for url_m in _CREDS_IN_URL_RE.finditer(line):
                url_str = url_m.group(0)
                sep = "://"
                sep_idx = url_str.find(sep)
                scheme = url_str[: sep_idx + len(sep)] if sep_idx >= 0 else ""
                at_idx = url_str.rfind("@")
                host_part = url_str[at_idx + 1 :] if at_idx >= 0 else ""
                snippet = f"{scheme}<user>:<redacted>@{host_part}"[:60]
                warnings.append(
                    f"Credential/secret literal{step_ref}: URL with embedded credentials "
                    f"({snippet}) — never embed credentials in URLs"
                )

        return warnings

    def _detect_auth_setup_needed(self, script_content: str, test_case: TestCase) -> list[str]:
        """Detect when a script targets an authenticated area but carries no SSO-setup marker (13.4 AC2).

        Computes an auth-likely signal deterministically from the test case and script.
        If auth-likely and the LLM has NOT already emitted the SSO-setup # REVIEW: marker,
        emits one advisory warning identifying the required session setup.

        Args:
            script_content: The generated Python script text.
            test_case: The source test case (checked for auth keywords and preconditions).

        Returns:
            List with one warning string when SSO setup is required and not yet marked, else empty.
        """
        auth_likely = False

        # Signal 1: auth-action keywords in title or step actions/targets
        text_to_check = test_case.title
        for step in test_case.steps:
            text_to_check += f" {step.action}"
            if step.target:
                text_to_check += f" {step.target}"
        if _AUTH_KEYWORD_RE.search(text_to_check):
            auth_likely = True

        # Signal 2: "authenticated" / "logged in" / "signed in" in preconditions
        if not auth_likely:
            for precondition in test_case.preconditions:
                if _AUTH_PRECOND_RE.search(precondition):
                    auth_likely = True
                    break

        # Signal 3: password-field interaction in the script (locator or step comment + fill/type)
        if not auth_likely:
            current_step_text = ""
            for line in script_content.splitlines():
                step_m = _STEP_COMMENT_RE.match(line)
                if step_m:
                    current_step_text = line[step_m.end() :].lstrip(":").strip()
                    continue
                has_fill = bool(re.search(r"\.(fill|type|press_sequentially)\s*\(", line))
                if has_fill and (
                    _CRED_KEYWORD_RE.search(line) or _CRED_KEYWORD_RE.search(current_step_text)
                ):
                    auth_likely = True
                    break

        if not auth_likely:
            return []

        # Suppress if the LLM already emitted an SSO-setup REVIEW marker (AC2 is already satisfied)
        if _SSO_REVIEW_MARKER_RE.search(script_content):
            return []

        return [
            "SSO/session setup required: this test targets an authenticated area — "
            "run it against a pre-authenticated browser context (existing SSO session); "
            "no login automation or credentials are included"
        ]

    def _generate_filename(self, title: str) -> str:
        """Generate Python test filename from test case title.

        Args:
            title: The test case title.

        Returns:
            Filename like "test_user_login_flow.py".
        """
        # Handle empty or whitespace-only title
        if not title or not title.strip():
            return "test_unnamed_case.py"

        # Transliterate Unicode to ASCII (NFKD decomposition + remove non-ASCII)
        normalized = unicodedata.normalize("NFKD", title)
        ascii_title = "".join(c for c in normalized if ord(c) < 128)

        # Convert to lowercase, replace non-alphanumeric with underscores
        safe = re.sub(r"[^a-z0-9]+", "_", ascii_title.lower())
        safe = safe.strip("_")

        # Handle case where transliteration results in empty string
        if not safe:
            return "test_unnamed_case.py"

        # Limit to 80 characters (including "test_" prefix and ".py" extension)
        max_length = 80 - len("test_") - len(".py")
        if len(safe) > max_length:
            safe = safe[:max_length].rstrip("_")

        return f"test_{safe}.py"

    def _generate_script_header(self, test_case: TestCase) -> str:
        """Generate script header with durable source traceability.

        Links back to the originating test case by title and source requirement
        (when available from Story 12.2 fields), not a stale workspace path.

        Args:
            test_case: The source test case.

        Returns:
            Header string with metadata and imports.
        """
        timestamp = datetime.now(UTC).isoformat()
        model = getattr(self._config, "script_generation_model", "sonnet")

        # Build durable source traceability lines (graceful degradation on pre-12.2 TestCase)
        source_req_name: str | None = getattr(test_case, "source_requirement_name", None)
        source_url: str | None = getattr(test_case, "source_url", None)

        source_lines = []
        if source_req_name:
            source_lines.append(f"Source requirement: {source_req_name}")
        if source_url:
            source_lines.append(f"Source URL: {source_url}")

        source_block = "\n".join(source_lines)
        if source_block:
            source_block = f"\n{source_block}"

        header = f'''"""
Generated Playwright test script for: {test_case.title}{source_block}
Generated: {timestamp}
Model: {model}
"""

import pytest
from playwright.sync_api import Page, expect
'''
        return header

    def _calculate_confidence(
        self,
        script_content: str,
        test_case: TestCase,
        locator_results: list[LocatorResult] | None = None,
    ) -> float:
        """Calculate confidence score for generated script.

        Args:
            script_content: The generated script content.
            test_case: The source test case.
            locator_results: Optional vision analysis results for accuracy adjustment.

        Returns:
            Confidence score between 0.0 and 1.0.
        """
        score = 0.5  # Base score

        # Check for stable selectors (data-testid, role-based)
        if "data-testid" in script_content:
            score += 0.15
        if "get_by_role" in script_content:
            score += 0.15
        if "get_by_text" in script_content:
            score += 0.1

        # Check for proper assertions
        if "expect(" in script_content and ")" in script_content:
            score += 0.1

        # Check if all expected results are mapped
        expected_count = len(test_case.expected_results)
        if expected_count > 0:
            # Simple heuristic: count expect calls vs expected results
            expect_count = script_content.count("expect(")
            coverage = min(expect_count / expected_count, 1.0)
            score += 0.1 * coverage

        # Check for error handling
        if "try:" in script_content or "except" in script_content:
            score += 0.05

        # Penalize XPath usage (less stable)
        xpath_count = script_content.count("xpath=")
        if xpath_count > 2:
            score -= 0.05 * min(xpath_count - 2, 3)  # Max penalty 0.15

        # Penalize raw CSS selectors without data-testid
        css_selectors = len(re.findall(r'page\.locator\(["\']([^"\']+)["\']\)', script_content))
        if css_selectors > 3:
            score -= 0.02 * min(css_selectors - 3, 5)  # Max penalty 0.1

        # Adjust score based on vision accuracy if available
        if locator_results:
            vision_confidence = self._calculate_vision_confidence(locator_results)
            # Blend base score with vision confidence (60% base, 40% vision)
            score = score * 0.6 + vision_confidence * 0.4

        return max(0.0, min(1.0, score))

    def _calculate_vision_confidence(self, locator_results: list[LocatorResult]) -> float:
        """Calculate confidence based on vision analysis accuracy.

        Args:
            locator_results: Vision analysis results.

        Returns:
            Average vision confidence score.
        """
        if not locator_results:
            return 0.5

        total_confidence = sum(r.confidence for r in locator_results)
        avg_confidence = total_confidence / len(locator_results)

        # Bonus for validated locators
        validated_count = sum(1 for r in locator_results if r.validation_status == "valid")
        if validated_count > 0:
            validation_ratio = validated_count / len(locator_results)
            avg_confidence += 0.1 * validation_ratio

        return min(1.0, avg_confidence)


async def process(
    test_cases: list[TestCase],
    output_base_dir: Path,
    config: AppSettings | None = None,
    llm_config: LLMConfig | None = None,
    vision_locator: VisionLocator | None = None,
    target_url: str | None = None,
) -> StageResult:
    """Pipeline stage entry point for script generation.

    Args:
        test_cases: List of test cases to convert to scripts.
        output_base_dir: Base directory for script output.
        config: Optional AppSettings for configuration.
        llm_config: Optional LLM configuration.
        vision_locator: Optional VisionLocator for vision-assisted generation.
        target_url: Optional target application URL for vision analysis.

    Returns:
        StageResult with generated script paths and confidence score.
    """
    generator = ScriptGenerator(
        output_base_dir=output_base_dir,
        llm_config=llm_config,
        config=config,
        vision_locator=vision_locator,
    )
    return await generator.generate(test_cases, target_url)
