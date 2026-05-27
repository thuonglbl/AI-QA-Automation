"""Test case extractor pipeline stage.

Generates structured test cases from requirements using LLM.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from ai_qa.ai_connection.client import LLMClient
from ai_qa.ai_connection.config import LLMConfig
from ai_qa.exceptions import LLMError, PipelineError
from ai_qa.models import StageResult, TestCase, TestCaseStep
from ai_qa.prompts.test_extraction import format_test_extraction_prompt

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a test automation expert specializing in browser-use test cases.
Your output must be valid JSON following the exact schema provided.
Always return test cases that are actionable, atomic, and locatable."""


class TestCaseExtractor:
    """Pipeline stage for extracting structured test cases from requirements.

    Uses LLM to convert natural language requirements into browser-use-optimized
    test cases with clear action-target pairs.
    """

    def __init__(
        self,
        llm_config: LLMConfig | None = None,
    ) -> None:
        """Initialize the extractor.

        Args:
            llm_config: Optional LLM configuration. If None, loads from agents.json.
        """
        self._llm_config = llm_config

    async def extract(self, requirements_path: Path, source_url: str = "") -> StageResult:
        """Extract test cases from a requirements file.

        Args:
            requirements_path: Path to markdown requirements file
            source_url: Original source URL for metadata

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
            test_cases = await self._call_llm(requirements)

            if not test_cases:
                return StageResult(
                    success=True,
                    data=[],
                    errors=[],
                    warnings=["LLM returned no test cases from requirements"],
                    confidence=0.5,
                )

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
        self, requirements_paths: list[Path], source_urls: list[str] | None = None
    ) -> StageResult:
        """Extract test cases from multiple requirements files.

        Args:
            requirements_paths: List of paths to markdown requirements files
            source_urls: Optional list of source URLs (defaults to empty strings)

        Returns:
            StageResult with combined list of all TestCase objects
        """
        if source_urls is None:
            source_urls = [""] * len(requirements_paths)

        if len(source_urls) != len(requirements_paths):
            raise PipelineError("source_urls length must match requirements_paths length")

        all_test_cases: list[TestCase] = []
        all_errors: list[str] = []
        all_warnings: list[str] = []
        confidences: list[float] = []

        for req_path, source_url in zip(requirements_paths, source_urls, strict=False):
            result = await self.extract(req_path, source_url)
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

    async def _call_llm(self, requirements: str) -> list[TestCase]:
        """Call LLM to extract test cases from requirements.

        Args:
            requirements: Markdown requirements text

        Returns:
            List of parsed TestCase objects

        Raises:
            LLMError: If LLM call fails
        """
        config = self._llm_config or LLMConfig.from_agents_json(agent_name="mary")
        client = LLMClient(config)

        prompt = format_test_extraction_prompt(requirements)

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        try:
            response = client.invoke(messages)
            raw_content = response.content if hasattr(response, "content") else str(response)
            content = raw_content if isinstance(raw_content, str) else str(raw_content)
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

        return TestCase(
            title=data.get("title", "Untitled Test Case"),
            preconditions=data.get("preconditions", []),
            steps=steps,
            expected_results=data.get("expected_results", []),
            automation_hints=data.get("automation_hints", []),
            tags=data.get("tags", []),
        )

    def _compute_confidence(self, test_cases: list[TestCase]) -> float:
        """Compute overall confidence score for extraction.

        Args:
            test_cases: List of generated test cases

        Returns:
            Confidence score between 0.0 and 1.0
        """
        if not test_cases:
            return 0.0

        # Average individual test case quality
        quality_scores = [self._compute_single_confidence(tc) for tc in test_cases]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

        return avg_quality

    def _compute_single_confidence(self, test_case: TestCase) -> float:
        """Compute confidence for a single test case.

        Scoring criteria:
        - Has title: 0.2
        - Has steps: 0.3
        - Has expected_results: 0.2
        - Has automation_hints: 0.2
        - Has preconditions: 0.1

        Args:
            test_case: TestCase to evaluate

        Returns:
            Confidence score between 0.0 and 1.0
        """
        score = 0.0

        if test_case.title and test_case.title != "Untitled Test Case":
            score += 0.2

        if test_case.steps:
            score += 0.3
            # Bonus for well-structured steps (action and target present)
            valid_steps = sum(1 for s in test_case.steps if s.action and s.target)
            if valid_steps == len(test_case.steps):
                score += 0.1

        if test_case.expected_results:
            score += 0.2

        if test_case.automation_hints:
            score += 0.2

        if test_case.preconditions:
            score += 0.1

        return min(score, 1.0)
