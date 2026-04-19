# Blind Hunter Review - Story 5-2

## Reviewer Role: Blind Hunter

You are a Blind Hunter code reviewer. You have NO project context, NO spec file, and NO knowledge of the codebase. You review only the diff below, treating it as if you've never seen this project before.

## Instructions

1. Review the diff as a complete stranger to the codebase
2. Look for bugs, security issues, performance problems, and anti-patterns visible from the code alone
3. Focus on:
   - Obvious logic errors
   - Exception handling gaps
   - Resource leaks
   - Security vulnerabilities (SQL injection, command injection, unsafe eval, etc.)
   - Race conditions
   - Type safety issues
   - Dead code or unreachable code
   - Misleading variable/function names
   - Hard-coded secrets or credentials
   - Unsafe file operations

4. Output findings as a Markdown list. Each finding must include:
   - One-line title
   - File and line location
   - Evidence from the diff
   - Why this is a problem

5. If you find no issues, state: "No issues found from blind review."

## Diff to Review

```diff
# New file: src/ai_qa/pipelines/script_generator.py
"""Script generator pipeline stage.

Converts structured test cases into executable Playwright Python scripts via LLM.
"""

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from ai_qa.ai_connection.client import LLMClient
from ai_qa.ai_connection.config import LLMConfig
from ai_qa.config import AppSettings
from ai_qa.exceptions import ScriptGenerationError
from ai_qa.models import StageResult, TestCase
from ai_qa.pipelines.models import OutputMetadata
from ai_qa.pipelines.output_writer import OutputWriter
from ai_qa.prompts.script_generation import (
    SCRIPT_GENERATION_PROMPT,
    SCRIPT_GENERATION_SYSTEM_PROMPT,
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
    ) -> None:
        """Initialize the script generator.

        Args:
            output_base_dir: Base directory for script output (workspace/testscripts/)
            llm_config: Optional LLM configuration. If None, loads from agents.json.
            config: Optional AppSettings for script generation configuration.
        """
        self.output_base_dir = output_base_dir
        self._llm_config = llm_config
        self._config = config or AppSettings()
        self._output_writer = OutputWriter(output_base_dir)

    async def generate(self, test_cases: list[TestCase]) -> StageResult:
        """Generate Playwright scripts from test cases.

        Args:
            test_cases: List of structured test cases to convert to scripts.

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
                result = await self._generate_single_script(test_case)
                if result["success"]:
                    generated_scripts.append(result)
                    total_confidence += result.get("confidence", 0.5)
                    if result.get("warnings"):
                        warnings.extend(result["warnings"])
                else:
                    errors.append(f"Failed to generate script for '{test_case.title}': {result.get('error', 'Unknown error')}")
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

    async def _generate_single_script(self, test_case: TestCase) -> dict[str, Any]:
        """Generate a single Playwright script from a test case.

        Args:
            test_case: The test case to convert to a script.

        Returns:
            Dictionary with script generation result including file path and confidence.
        """
        try:
            # Generate script via LLM
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

            # Calculate confidence based on script quality indicators
            confidence = self._calculate_confidence(script_content, test_case)

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

    @retry(
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
                # Concatenate list items into a single string
                script_content = "\n".join(
                    str(item) if not isinstance(item, dict) else str(item.get("text", ""))
                    for item in script_content
                )

            if not isinstance(script_content, str) or not script_content.strip():
                raise ScriptGenerationError("LLM returned empty response")

            return script_content.strip()

        except Exception as e:
            if isinstance(e, ScriptGenerationError):
                raise
            logger.error(f"LLM call failed: {e}")
            raise ScriptGenerationError(f"LLM generation failed: {e}") from e

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

        llm_config = LLMConfig(
            model_name=model,
            temperature=temperature,
            api_key=self._config.on_premises_ai_server_key or self._config.anthropic_api_key or "",
            base_url=self._config.on_premises_ai_server_url or "",
        )
        return LLMClient(llm_config)

    async def _write_script(self, script_content: str, test_case: TestCase, confidence: float) -> str:
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

        # Create metadata
        metadata = OutputMetadata(
            source_url=f"workspace/testcases/{test_case.filename}.json",
            timestamp=datetime.now(UTC),
            model=getattr(self._config, "script_generation_model", "sonnet"),
            confidence=confidence,
        )

        # Write using OutputWriter
        result = await self._output_writer.write(filename, full_content, metadata)

        if not result.success:
            raise ScriptGenerationError(f"Failed to write script: {result.errors}")

        return result.data["file_path"] if result.data else str(self.output_base_dir / filename)

    def _generate_filename(self, title: str) -> str:
        """Generate Python test filename from test case title.

        Args:
            title: The test case title.

        Returns:
            Filename like "test_user_login_flow.py".
        """
        # Convert to lowercase, replace non-alphanumeric with hyphens
        kebab = re.sub(r"[^a-z0-9]+", "-", title.lower())
        kebab = kebab.strip("-")

        # Limit to 80 characters (including "test_" prefix and ".py" extension)
        max_length = 80 - len("test_") - len(".py")
        if len(kebab) > max_length:
            kebab = kebab[:max_length].rstrip("-")

        return f"test_{kebab}.py"

    def _generate_script_header(self, test_case: TestCase) -> str:
        """Generate script header with metadata comments.

        Args:
            test_case: The source test case.

        Returns:
            Header string with metadata.
        """
        timestamp = datetime.now(UTC).isoformat()
        model = getattr(self._config, "script_generation_model", "sonnet")

        header = f'''"""
Generated Playwright test script for: {test_case.title}
Source: workspace/testcases/{test_case.filename}.json
Generated: {timestamp}
Model: {model}
"""

import pytest
from playwright.sync_api import Page, expect
'''
        return header

    def _calculate_confidence(self, script_content: str, test_case: TestCase) -> float:
        """Calculate confidence score for generated script.

        Args:
            script_content: The generated script content.
            test_case: The source test case.

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
        css_selectors = len(re.findall(r'page\.locator\(["\'\][^"\']+["\'\])\)', script_content))
        if css_selectors > 3:
            score -= 0.02 * min(css_selectors - 3, 5)  # Max penalty 0.1

        return max(0.0, min(1.0, score))


async def process(
    test_cases: list[TestCase],
    output_base_dir: Path,
    config: AppSettings | None = None,
    llm_config: LLMConfig | None = None,
) -> StageResult:
    """Pipeline stage entry point for script generation.

    Args:
        test_cases: List of test cases to convert to scripts.
        output_base_dir: Base directory for script output.
        config: Optional AppSettings for configuration.
        llm_config: Optional LLM configuration.

    Returns:
        StageResult with generated script paths and confidence score.
    """
    generator = ScriptGenerator(
        output_base_dir=output_base_dir,
        llm_config=llm_config,
        config=config,
    )
    return await generator.generate(test_cases)


# New file: src/ai_qa/prompts/script_generation.py
"""Prompt templates for Playwright script generation.

This module contains prompt templates used by the ScriptGenerator to convert
test cases into executable Playwright Python scripts.
"""

SCRIPT_GENERATION_SYSTEM_PROMPT = """You are an expert Playwright test automation engineer specializing in Python.

Your task is to convert structured test cases into complete, executable Playwright Python test scripts.

Key principles:
1. Generate clean, maintainable Python code following pytest conventions
2. Prefer stable selectors: data-testid > role-based > accessibility > CSS > XPath
3. Include proper assertions that match expected results from the test case
4. Add appropriate waits using Playwright's auto-waiting mechanisms
5. Follow Playwright best practices for reliability and maintainability

Output only valid Python code without markdown formatting or explanations."""

SCRIPT_GENERATION_PROMPT = """Convert the following structured test case into a complete Playwright Python test script.

Test Case (JSON format):
{test_case}

Requirements for the generated script:

1. **Function Definition**: Create a pytest test function with signature:
   ```python
   def test_<descriptive_name>(page: Page):
   ```

2. **Stable Selectors** (use in this priority order):
   - `page.get_by_test_id("...")` - Most stable, preferred when available
   - `page.get_by_role("button", name="...")` - Role-based selectors
   - `page.get_by_text("...")` - Text-based selectors
   - `page.get_by_label("...")` - Label-based selectors
   - `page.get_by_placeholder("...")` - Placeholder-based selectors
   - `page.locator("...")` - CSS selectors (use only when necessary)
   - `page.locator("xpath=...")` - XPath (last resort, avoid if possible)

3. **Actions**: Convert each test step to appropriate Playwright actions:
   - Navigation: `page.goto(url)`
   - Clicking: `element.click()`
   - Typing: `element.fill(text)` or `element.press_sequentially(text, delay=50)`
   - Selecting: `element.select_option(value)`
   - Waiting: Use implicit waits or `element.wait_for()`

4. **Assertions**: Map expected results to Playwright assertions:
   - "Verify X is visible" → `expect(element).to_be_visible()`
   - "Check Y equals Z" → `expect(element).to_have_text("Z")`
   - "Confirm button is disabled" → `expect(button).to_be_disabled()`
   - "Validate URL contains X" → `expect(page).to_have_url(re.compile(".*X.*"))`
   - "Verify element exists" → `expect(element).to_be_attached()`
   - "Check element count" → `expect(elements).to_have_count(n)`

5. **Structure**:
   - Include docstring describing what the test verifies
   - Add comments for each major step referencing the original test step number
   - Use descriptive variable names
   - Handle preconditions at the start of the test

6. **Error Handling**:
   - Use Playwright's built-in auto-waiting and retry mechanisms
   - Add explicit waits only when necessary for timing issues
   - Use `expect(...).to_be_visible(timeout=10000)` for custom timeouts

7. **Best Practices**:
   - One action per line for clarity
   - Chain locators for specificity: `page.get_by_test_id("form").get_by_role("button")`
   - Use `expect()` for all assertions (not `assert`)
   - Prefer user-visible selectors (text, role) over implementation details

Output ONLY the Python test function code. Do not include markdown code blocks or explanations. The code should be ready to run with pytest and Playwright."""


# Modified file: src/ai_qa/config.py
# Added fields to AppSettings class:
    # --- Script Generation (FR6-9, NFR14) ---
    script_generation_model: str = Field(
        default="sonnet", description="Model for script generation (can override per-agent config)"
    )
    script_generation_temperature: float = Field(
        default=0.0, ge=0.0, le=2.0, description="Temperature for deterministic script output"
    )
    script_generation_timeout: int = Field(
        default=120, ge=10, le=600, description="Timeout in seconds per script generation"
    )
    max_script_length: int = Field(
        default=10000, ge=1000, le=50000, description="Maximum characters per generated script"
    )
    confidence_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Threshold to flag low confidence generations"
    )


# Modified file: src/ai_qa/exceptions.py
# Added class:
class ScriptGenerationError(LLMError):
    """Raised when script generation via LLM fails.

    Examples: empty response, invalid script content, generation timeout,
    malformed output that cannot be written to file.
    """


# Modified file: src/ai_qa/prompts/__init__.py
# Added imports and exports for script generation prompts
```

---

**Output your findings below:**
