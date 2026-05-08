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
from ai_qa.pipelines.models import OutputMetadata
from ai_qa.pipelines.output_writer import OutputWriter
from ai_qa.pipelines.vision_locator import LocatorResult, VisionLocator
from ai_qa.prompts.script_generation import (
    SCRIPT_GENERATION_PROMPT,
    SCRIPT_GENERATION_SYSTEM_PROMPT,
    VISION_ASSISTED_SCRIPT_GENERATION_PROMPT,
    VISION_SCRIPT_GENERATION_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


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
    ) -> None:
        """Initialize the script generator.

        Args:
            output_base_dir: Base directory for script output (workspace/testscripts/)
            llm_config: Optional LLM configuration. If None, loads from agents.json.
            config: Optional AppSettings for script generation configuration.
            vision_locator: Optional VisionLocator for vision-assisted generation.
        """
        self.output_base_dir = output_base_dir
        self._llm_config = llm_config
        self._config = config or AppSettings()
        self._output_writer = OutputWriter(output_base_dir)
        self._vision_locator = vision_locator
        self._vision_enabled = (
            vision_locator is not None and getattr(config, "vision_enabled", True)
            if config
            else vision_locator is not None
        )

    async def generate(
        self,
        test_cases: list[TestCase],
        target_url: str | None = None,
    ) -> StageResult:
        """Generate Playwright scripts from test cases.

        Args:
            test_cases: List of structured test cases to convert to scripts.
            target_url: Optional target application URL for vision-assisted generation.

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
                result = await self._generate_single_script(test_case, target_url)
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
    ) -> dict[str, Any]:
        """Generate a single Playwright script from a test case.

        Args:
            test_case: The test case to convert to a script.
            target_url: Optional target URL for vision-assisted generation.

        Returns:
            Dictionary with script generation result including file path and confidence.
        """
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
                script_content = await self._call_llm_with_vision(test_case, locator_results)
            else:
                script_content = await self._call_llm(test_case)

            if not script_content or not script_content.strip():
                return {
                    "success": False,
                    "error": "LLM returned empty script",
                    "test_case_title": test_case.title,
                }

            # Validate script length
            max_length = getattr(self._config, "max_script_length", 10000)
            if len(script_content) > max_length:
                return {
                    "success": False,
                    "error": f"Generated script exceeds max length ({len(script_content)} > {max_length})",
                    "test_case_title": test_case.title,
                }

            # Calculate confidence based on script quality indicators and vision results
            confidence = self._calculate_confidence(script_content, test_case, locator_results)

            # Write script to file
            file_path = await self._write_script(script_content, test_case, confidence)

            return {
                "success": True,
                "file_path": file_path,
                "test_case_title": test_case.title,
                "confidence": confidence,
                "warnings": [],
            }

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

    @retry(  # type: ignore[misc]
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _call_llm(self, test_case: TestCase) -> str:
        """Call LLM to generate a Playwright script from a test case.

        Args:
            test_case: The test case to convert.

        Returns:
            Generated Python script content.

        Raises:
            ScriptGenerationError: If LLM call fails after retries.
        """
        try:
            llm_client = self._get_llm_client()

            # Format the prompt with test case data
            test_case_json = test_case.model_dump_json(indent=2)
            prompt = SCRIPT_GENERATION_PROMPT.format(test_case=test_case_json)

            # Create messages for LLM
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
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

    @retry(  # type: ignore[misc]
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _call_llm_with_vision(
        self,
        test_case: TestCase,
        locator_results: list[LocatorResult],
    ) -> str:
        """Call LLM to generate a Playwright script with vision context.

        Args:
            test_case: The test case to convert.
            locator_results: Vision analysis results with identified locators.

        Returns:
            Generated Python script content.

        Raises:
            ScriptGenerationError: If LLM call fails after retries.
        """
        try:
            llm_client = self._get_llm_client()

            # Format the prompt with test case and vision data
            test_case_json = test_case.model_dump_json(indent=2)
            locator_info = self._format_locator_info(locator_results)
            vision_context = "Vision-assisted analysis was performed on the target application."

            prompt = VISION_ASSISTED_SCRIPT_GENERATION_PROMPT.format(
                test_case=test_case_json,
                vision_context=vision_context,
                locator_info=locator_info,
            )

            # Create messages for LLM
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
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

    async def _write_script(
        self, script_content: str, test_case: TestCase, confidence: float
    ) -> str:
        """Write generated script to file.

        Args:
            script_content: The Python script content to write.
            test_case: The source test case for metadata.
            confidence: Confidence score for the generated script.

        Returns:
            Path to the written file.
        """
        # Generate filename from test case title
        filename = self._generate_filename(test_case.title)

        # Add script header with metadata
        header = self._generate_script_header(test_case)
        full_content = header + "\n\n" + script_content

        # Create metadata with safe filename access
        source_filename = getattr(test_case, "filename", None) or "unknown"
        metadata = OutputMetadata(
            source_url=f"workspace/testcases/{source_filename}.json",
            timestamp=datetime.now(UTC),
            model=getattr(self._config, "script_generation_model", "sonnet"),
            confidence=confidence,
        )

        # Write using OutputWriter
        result = await self._output_writer.write(filename, full_content, metadata)

        if not result.success:
            raise ScriptGenerationError(f"Failed to write script: {result.errors}")

        return result.data.get("file_path") if result.data else str(self.output_base_dir / filename)

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
        """Generate script header with metadata comments.

        Args:
            test_case: The source test case.

        Returns:
            Header string with metadata.
        """
        timestamp = datetime.now(UTC).isoformat()
        model = getattr(self._config, "script_generation_model", "sonnet")

        # Safely get filename for header
        source_filename = getattr(test_case, "filename", None) or "unknown"
        header = f'''"""
Generated Playwright test script for: {test_case.title}
Source: workspace/testcases/{source_filename}.json
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
