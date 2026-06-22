"""Test case extractor pipeline stage.

Generates structured test cases from requirements using LLM.
"""

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from ai_qa.ai_connection.client import LLMClient
from ai_qa.ai_connection.config import LLMConfig
from ai_qa.exceptions import LLMError, PipelineError
from ai_qa.models import ConfidenceLevel, StageResult, TestCase, TestCaseStep
from ai_qa.prompts.test_extraction import format_test_extraction_prompt

logger = logging.getLogger(__name__)

CONFIDENCE_HIGH_THRESHOLD: float = 0.80
CONFIDENCE_MEDIUM_THRESHOLD: float = 0.55
WARNING_PENALTY_PER_CASE: float = 0.15
WARNING_PENALTY_PER_SOURCE: float = 0.10


@dataclass(frozen=True)
class RequirementSource:
    """Source attribution for a generated test case, derived from the originating requirement."""

    id: str | None
    name: str | None
    url: str | None
    warnings: list[dict[str, Any]] | None = None


SYSTEM_PROMPT = """You are a test automation expert specializing in browser-use test cases.
Your output must be valid JSON following the exact schema provided.
Always return test cases that are actionable, atomic, and locatable."""


def _content_to_text(content: Any) -> str:
    """Normalize a LangChain message/chunk ``content`` to plain text.

    Anthropic (and reasoning models) return ``content`` as a LIST of typed blocks
    (e.g. ``[{"type": "text", "text": "..."}]``), not a ``str``. ``str(content)`` on that
    list yields a Python repr (single-quoted, bracketed) that is NOT valid JSON and breaks
    both the streaming scanner and the safety-net parse. Concatenate the text of text
    blocks (skipping thinking/tool_use blocks); fall back to ``str`` for anything else.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type", "text") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


_TEST_CASES_KEY_RE = re.compile(r'"test_cases"\s*:\s*\[')


class StreamingArrayObjects:
    """Incrementally extract complete top-level ``{...}`` objects from a streamed JSON array.

    The LLM streams ``{"test_cases": [ {..}, {..}, ... ]}`` token-by-token. This locates
    the ``test_cases`` array's opening ``[`` once, then scans forward tracking string,
    escape, and brace-depth state, emitting each balanced object the moment it closes.
    Call :meth:`feed` with each streamed chunk; it returns the JSON strings of any objects
    that completed within that chunk (so the caller can parse + act on them immediately).
    """

    def __init__(self) -> None:
        self._buf = ""
        self._started = False
        self._pos = 0
        self._depth = 0
        self._in_str = False
        self._escape = False
        self._obj_start = -1

    def feed(self, text: str) -> list[str]:
        """Append ``text`` and return JSON strings of objects completed so far."""
        self._buf += text
        out: list[str] = []
        if not self._started:
            # Anchor on the GENUINE JSON key (`"test_cases" : [`), not a bare mention of
            # the words in a prose preamble — otherwise a stray `"test_cases"` + `[` in
            # chatter would misalign the scanner.
            m = _TEST_CASES_KEY_RE.search(self._buf)
            if m is None:
                return out
            self._started = True
            self._pos = m.end()  # just past the opening '['
        i = self._pos
        n = len(self._buf)
        while i < n:
            c = self._buf[i]
            if self._in_str:
                if self._escape:
                    self._escape = False
                elif c == "\\":
                    self._escape = True
                elif c == '"':
                    self._in_str = False
            elif c == '"':
                self._in_str = True
            elif c == "{":
                if self._depth == 0:
                    self._obj_start = i
                self._depth += 1
            elif c == "}":
                self._depth -= 1
                if self._depth == 0 and self._obj_start != -1:
                    out.append(self._buf[self._obj_start : i + 1])
                    self._obj_start = -1
            elif c == "]" and self._depth == 0:
                self._pos = i + 1
                return out
            i += 1
        self._pos = i
        return out


class TestCaseExtractor:
    """Pipeline stage for extracting structured test cases from requirements.

    Uses LLM to convert natural language requirements into browser-use-optimized
    test cases with clear action-target pairs.
    """

    __test__ = False  # Prevent pytest from collecting this as a test class

    def __init__(
        self,
        llm_config: LLMConfig | None = None,
    ) -> None:
        """Initialize the extractor.

        Args:
            llm_config: Optional LLM configuration. If None, loads from agents.json.
        """
        self.llm_config = llm_config

    async def extract(
        self,
        requirements_path: Path,
        source_url: str = "",
        source: RequirementSource | None = None,
        context: str = "",
    ) -> StageResult:
        """Extract test cases from a requirements file.

        Args:
            requirements_path: Path to markdown requirements file
            source_url: Original source URL for metadata (legacy param; prefer source)
            source: Optional source attribution stamped onto every generated TestCase
            context: Optional extra prompt context (project overview + clarifications)

        Returns:
            StageResult with list of TestCase objects on success
        """
        try:
            # Read requirements
            if not requirements_path.exists():
                return StageResult(
                    success=False,
                    data=None,
                    errors=[f"Requirements file not found: {requirements_path}"],
                    warnings=[],
                    confidence=0.0,
                )

            requirements = requirements_path.read_text(encoding="utf-8")
            if not requirements.strip():
                return StageResult(
                    success=True,
                    data=[],
                    errors=[],
                    warnings=["Empty requirements file - no test cases generated"],
                    confidence=1.0,
                )

            # Call LLM to extract test cases
            test_cases = await self._call_llm(requirements, context)

            if not test_cases:
                return StageResult(
                    success=True,
                    data=[],
                    errors=[],
                    warnings=["LLM returned no test cases from requirements"],
                    confidence=0.5,
                )

            # Stamp source attribution and confidence on every case
            source_warnings = source.warnings if source is not None else None
            test_cases = [self._stamp(tc, source, source_warnings) for tc in test_cases]

            # Calculate confidence based on results
            confidence = self._compute_confidence(test_cases)

            return StageResult(
                success=True,
                data=test_cases,
                errors=[],
                warnings=[],
                confidence=confidence,
            )

        except PipelineError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error extracting test cases: {e}")
            return StageResult(
                success=False,
                data=None,
                errors=[f"Extraction failed: {e}"],
                warnings=[],
                confidence=0.0,
            )

    async def extract_batch(
        self,
        requirements_paths: list[Path],
        source_urls: list[str] | None = None,
        sources: list[RequirementSource] | None = None,
        context: str = "",
    ) -> StageResult:
        """Extract test cases from multiple requirements files.

        Args:
            requirements_paths: List of paths to markdown requirements files
            source_urls: Optional list of source URLs (defaults to empty strings, legacy)
            sources: Optional list of RequirementSource objects for source attribution;
                     must match requirements_paths length when provided

        Returns:
            StageResult with combined list of all TestCase objects in path order
        """
        if source_urls is None:
            source_urls = [""] * len(requirements_paths)

        if len(source_urls) != len(requirements_paths):
            raise PipelineError("source_urls length must match requirements_paths length")

        if sources is not None and len(sources) != len(requirements_paths):
            raise PipelineError("sources length must match requirements_paths length")

        all_test_cases: list[TestCase] = []
        all_errors: list[str] = []
        all_warnings: list[str] = []
        confidences: list[float] = []

        for i, (req_path, source_url) in enumerate(
            zip(requirements_paths, source_urls, strict=False)
        ):
            source = sources[i] if sources is not None else None
            result = await self.extract(req_path, source_url, source=source, context=context)
            if result.success and result.data:
                all_test_cases.extend(result.data)
            all_errors.extend(result.errors)
            all_warnings.extend(result.warnings)
            confidences.append(result.confidence if result.confidence is not None else 0.0)

        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return StageResult(
            success=len(all_test_cases) > 0,
            data=all_test_cases if all_test_cases else None,
            errors=all_errors,
            warnings=all_warnings,
            confidence=overall_confidence,
        )

    def _stamp(
        self,
        tc: TestCase,
        source: RequirementSource | None,
        source_warnings: list[dict[str, Any]] | None,
    ) -> TestCase:
        """Return a copy of ``tc`` with source attribution + confidence stamped on."""
        updates: dict[str, Any] = {}
        if source is not None:
            updates["source_requirement_id"] = source.id
            updates["source_requirement_name"] = source.name
            updates["source_url"] = source.url
        score, level, rationale = self._assess_confidence(tc, source_warnings)
        updates["confidence"] = score
        updates["confidence_level"] = level
        updates["confidence_rationale"] = rationale
        return tc.model_copy(update=updates)

    async def extract_streaming(
        self,
        requirements_paths: list[Path],
        source_urls: list[str] | None = None,
        sources: list[RequirementSource] | None = None,
        context: str = "",
        on_case: Callable[[TestCase], Awaitable[None]] | None = None,
    ) -> StageResult:
        """Like :meth:`extract_batch`, but stream cases and invoke ``on_case`` per case.

        Streams the comprehensive generation so each test case is surfaced (and can be
        saved/reported by the caller) the MOMENT it finishes streaming — instead of
        waiting minutes for one opaque response. ``on_case`` is awaited for every
        completed, stamped case in order. The returned ``StageResult.data`` is the full
        ordered list (same contract as ``extract_batch``).
        """
        if source_urls is None:
            source_urls = [""] * len(requirements_paths)
        if len(source_urls) != len(requirements_paths):
            raise PipelineError("source_urls length must match requirements_paths length")
        if sources is not None and len(sources) != len(requirements_paths):
            raise PipelineError("sources length must match requirements_paths length")

        all_test_cases: list[TestCase] = []
        all_warnings: list[str] = []
        confidences: list[float] = []

        for i, (req_path, _source_url) in enumerate(
            zip(requirements_paths, source_urls, strict=False)
        ):
            source = sources[i] if sources is not None else None
            if not req_path.exists():
                all_warnings.append(f"Requirements file not found: {req_path}")
                continue
            requirements = req_path.read_text(encoding="utf-8")
            if not requirements.strip():
                all_warnings.append("Empty requirements file - no test cases generated")
                continue
            cases = await self._stream_one(requirements, source, context, on_case)
            all_test_cases.extend(cases)
            confidences.append(self._compute_confidence(cases) if cases else 0.0)

        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return StageResult(
            success=len(all_test_cases) > 0,
            data=all_test_cases if all_test_cases else None,
            errors=[],
            warnings=all_warnings,
            confidence=overall_confidence,
        )

    async def _stream_one(
        self,
        requirements: str,
        source: RequirementSource | None,
        context: str,
        on_case: Callable[[TestCase], Awaitable[None]] | None,
    ) -> list[TestCase]:
        """Stream one requirement's generation, emitting each completed case via ``on_case``.

        Falls back to a single non-streaming call when streaming yields nothing (e.g. the
        proxy errors before any object closes), so generation still produces cases.
        """
        config = self.llm_config or LLMConfig(
            provider="litellm", model_name="claude-sonnet-4-6", temperature=0.0
        )
        client = LLMClient(config)
        prompt = format_test_extraction_prompt(requirements, context)
        messages: list[BaseMessage] = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        source_warnings = source.warnings if source is not None else None
        parser = StreamingArrayObjects()
        full_text = ""
        collected: list[TestCase] = []

        async def _emit(obj_str: str) -> None:
            try:
                data = json.loads(obj_str)
            except json.JSONDecodeError:
                return
            if not isinstance(data, dict) or "test_cases" in data:
                # Skip non-objects and the wrapper itself (a real case never carries a
                # top-level "test_cases" key) — fail-safe if anchoring is ever fooled.
                return
            try:
                tc = self._stamp(self._parse_single_test_case(data), source, source_warnings)
            except Exception as exc:
                logger.warning("Failed to parse a streamed test case: %s", exc)
                return
            collected.append(tc)
            if on_case is not None:
                await on_case(tc)

        try:
            async for chunk in client.astream(messages):
                piece = _content_to_text(chunk.content if hasattr(chunk, "content") else chunk)
                full_text += piece
                for obj_str in parser.feed(piece):
                    await _emit(obj_str)
        except LLMError as exc:
            if collected:
                logger.warning("Streaming interrupted after %d case(s): %s", len(collected), exc)
                return collected
            # Nothing streamed yet — fall back to a single non-streaming generation. If
            # that ALSO fails, degrade to an empty result for this requirement (a warning,
            # not a propagating error) so extract_streaming can continue to other files.
            logger.warning("Streaming failed (%s); falling back to non-streaming generation", exc)
            try:
                fallback = await self._call_llm(requirements, context)
            except LLMError as exc2:
                logger.warning("Non-streaming fallback also failed (%s); no cases", exc2)
                return collected
            for tc in fallback:
                stamped = self._stamp(tc, source, source_warnings)
                collected.append(stamped)
                if on_case is not None:
                    await on_case(stamped)
            return collected

        # Safety net: a lenient full parse catches any objects the incremental scanner
        # missed (e.g. the model wrapped the array oddly or omitted the closing bracket).
        try:
            final = self._parse_llm_response(full_text)
        except Exception:
            final = []
        if len(final) > len(collected):
            for tc in final[len(collected) :]:
                stamped = self._stamp(tc, source, source_warnings)
                collected.append(stamped)
                if on_case is not None:
                    await on_case(stamped)
        return collected

    async def _call_llm(self, requirements: str, context: str = "") -> list[TestCase]:
        """Call LLM to extract test cases from requirements.

        Args:
            requirements: Markdown requirements text
            context: Optional extra prompt context (project overview + clarifications)

        Returns:
            List of parsed TestCase objects

        Raises:
            LLMError: If LLM call fails
        """
        config = self.llm_config or LLMConfig(
            provider="litellm", model_name="claude-sonnet-4-6", temperature=0.0
        )
        client = LLMClient(config)

        prompt = format_test_extraction_prompt(requirements, context)

        messages: list[BaseMessage] = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        try:
            # Async invoke so a slow provider (on-prem generation can take minutes)
            # never blocks the event loop — keeps WebSockets/other requests alive.
            response = await client.ainvoke(messages)
            # Normalize content: Anthropic returns a list of typed blocks, not a str.
            content = _content_to_text(
                response.content if hasattr(response, "content") else response
            )
            return self._parse_llm_response(content)
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"Failed to invoke LLM for test extraction: {e}") from e

    def _parse_llm_response(self, content: str) -> list[TestCase]:
        """Parse LLM response into TestCase objects.

        Args:
            content: Raw LLM response text (expected to be JSON)

        Returns:
            List of TestCase objects

        Raises:
            PipelineError: If parsing fails
        """
        # Extract JSON from markdown code blocks if present
        json_content = self._extract_json(content)

        try:
            data = json.loads(json_content)
        except json.JSONDecodeError as e:
            raise PipelineError(f"LLM returned invalid JSON: {e}") from e

        if not isinstance(data, dict):
            raise PipelineError("LLM response JSON must be an object with 'test_cases' key")

        if "test_cases" not in data:
            raise PipelineError("Missing 'test_cases' key in LLM response")

        test_cases_data = data["test_cases"]
        if not isinstance(test_cases_data, list):
            raise PipelineError("'test_cases' must be an array")

        test_cases: list[TestCase] = []
        for tc_data in test_cases_data:
            try:
                test_case = self._parse_single_test_case(tc_data)
                test_cases.append(test_case)
            except Exception as e:
                logger.warning(f"Failed to parse test case: {e}")
                continue

        return test_cases

    def _extract_json(self, content: str) -> str:
        """Extract JSON from LLM response that may be wrapped in markdown.

        Args:
            content: Raw LLM response

        Returns:
            Extracted JSON string
        """
        # Try to find JSON in code blocks
        code_block_pattern = re.compile(r"```(?:json)?\n(.*?)\n```", re.DOTALL)
        match = code_block_pattern.search(content)
        if match:
            return match.group(1).strip()

        # Try to find JSON between first { and last }
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            return content[start : end + 1]

        # Return as-is if no markers found
        return content.strip()

    def _parse_single_test_case(self, data: dict[str, Any]) -> TestCase:
        """Parse a single test case from JSON data.

        Args:
            data: Test case JSON object

        Returns:
            Parsed TestCase object
        """
        steps_data = data.get("steps", [])
        steps: list[TestCaseStep] = []

        for step_data in steps_data:
            if isinstance(step_data, dict):
                steps.append(
                    TestCaseStep(
                        number=step_data.get("number", 0),
                        action=step_data.get("action", ""),
                        target=step_data.get("target", ""),
                        data=step_data.get("data"),
                    )
                )

        role = data.get("role")
        return TestCase(
            title=data.get("title", "Untitled Test Case"),
            role=str(role).strip() or None if role else None,
            objective=data.get("objective", ""),
            preconditions=data.get("preconditions", []),
            test_data=data.get("test_data", []),
            steps=steps,
            expected_results=data.get("expected_results", []),
            automation_hints=data.get("automation_hints", []),
            tags=data.get("tags", []),
            feature_area=data.get("feature_area"),
            warnings=data.get("warnings", []),
        )

    def _compute_confidence(self, test_cases: list[TestCase]) -> float:
        """Compute overall confidence as average of per-case stamped scores."""
        if not test_cases:
            return 0.0
        scores = [tc.confidence if tc.confidence is not None else 0.0 for tc in test_cases]
        return sum(scores) / len(scores)

    def _assess_confidence(
        self,
        tc: TestCase,
        source_warnings: list[dict[str, Any]] | None,
    ) -> tuple[float, ConfidenceLevel, list[str]]:
        """Deterministic confidence assessment.

        Returns (score, level, rationale) for a single test case.
        Score is structural minus warning penalties, clamped to [0.0, 1.0].
        Level banding forces 'low' when any warnings exist.
        """
        structural_score: float = 0.0
        rationale: list[str] = []

        # --- Structural additive score ---
        if tc.title and tc.title != "Untitled Test Case":
            structural_score += 0.15
        else:
            rationale.append("Missing or placeholder title")

        if tc.objective:
            structural_score += 0.15
        else:
            rationale.append("No objective stated")

        if tc.steps:
            structural_score += 0.20
            missing = sum(1 for s in tc.steps if not s.action or not s.target)
            if missing == 0:
                structural_score += 0.10
            else:
                rationale.append(f"{missing} step(s) missing an action or target")
        else:
            rationale.append("No steps defined")

        if tc.expected_results:
            structural_score += 0.20
        else:
            rationale.append("No expected results — outcome not verifiable")

        if tc.preconditions:
            structural_score += 0.10
        else:
            rationale.append("No preconditions specified")

        steps_use_data = any(s.data for s in tc.steps)
        if tc.test_data or not steps_use_data:
            structural_score += 0.10
        else:
            rationale.append("Steps use input data but no consolidated test_data listed")

        # --- Warning penalties ---
        penalties: float = 0.0
        for w in tc.warnings:
            penalties += WARNING_PENALTY_PER_CASE
            rationale.append(w)

        sw = source_warnings or []
        for sw_item in sw:
            penalties += WARNING_PENALTY_PER_SOURCE
            category = sw_item.get("category", "unknown")
            message = sw_item.get("message", "")
            rationale.append(f"Source requirement issue ({category}): {message}")

        score = min(max(structural_score - penalties, 0.0), 1.0)

        # --- Level banding (AC2: warnings force low) ---
        level: ConfidenceLevel
        if tc.warnings or sw:
            level = "low"
            # Explain override when the displayed (post-penalty) score is medium/high
            if score >= CONFIDENCE_MEDIUM_THRESHOLD:
                rationale.insert(
                    0,
                    f"Flagged LOW because unresolved warnings exist; the {score:.2f} score reflects structure only.",
                )
        elif score >= CONFIDENCE_HIGH_THRESHOLD:
            level = "high"
        elif score >= CONFIDENCE_MEDIUM_THRESHOLD:
            level = "medium"
        else:
            level = "low"

        # Positive note for a clean high-confidence case
        if level == "high" and not rationale:
            rationale.append("All structural fields present; no source or generation warnings")

        return score, level, rationale
