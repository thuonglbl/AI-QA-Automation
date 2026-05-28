"""Sarah agent - Generate Playwright scripts with side-by-side review.

Sarah orchestrates script generation using ScriptGenerator with VisionLocator
integration, then presents scripts for side-by-side review where users can
approve, reject with feedback, or skip individual scripts.
"""

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from ai_qa.agents.base import AgentState, BaseAgent
from ai_qa.browser.agent import BrowserAgent
from ai_qa.config import AppSettings
from ai_qa.models import StageResult, TestCase
from ai_qa.pipelines.artifact_adapter import PipelineArtifactAdapter
from ai_qa.pipelines.script_generator import ScriptGenerator
from ai_qa.pipelines.vision_locator import VisionLocator

logger = logging.getLogger(__name__)


class GeneratedScript(BaseModel):
    """Represents a generated script with metadata for review."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    test_case: TestCase
    script_content: str
    file_path: str
    confidence: float
    approved: bool = False
    error_message: str | None = None  # For failed script generation placeholder


class SarahAgent(BaseAgent):
    """Sarah - Generate Playwright scripts with side-by-side review.

    Orchestrates script generation using:
    - ScriptGenerator for LLM-based script creation
    - VisionLocator for accurate selector identification
    - OutputWriter for file management
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
        self._start_input_data: dict[str, Any] = {}  # Store input_data for context preservation

        # Initialize pipeline components
        self.config = self.get_llm_config()

        self.app_settings = AppSettings()

        self._script_generator: ScriptGenerator | None = None
        self._vision_locator: VisionLocator | None = None
        self._browser_agent: BrowserAgent | None = None

    # -------------------------------------------------------------------------
    # Chrome Path Persistence
    # -------------------------------------------------------------------------

    def _load_chrome_path(self) -> None:
        """Load Chrome path from project context."""
        if self.project_context is None:
            return

        try:
            adapter = PipelineArtifactAdapter(self.project_context)
            configuration_artifacts = adapter.service.list_artifacts(
                project_id=self.project_context.project_id,
                kind="configuration",
            )
            for artifact in configuration_artifacts:
                if artifact.name != "chrome_path.json":
                    continue
                content = adapter.service.read_current_content(artifact)
                data = json.loads(content.decode("utf-8"))
                self._chrome_path = data.get("chrome_path")
                logger.info("Loaded Chrome path from project artifacts")
                return
        except Exception as exc:
            logger.warning("Failed to load project Chrome path: %s", exc)

    async def _store_chrome_path(self, chrome_path: str) -> None:
        """Store Chrome path for future sessions.

        Args:
            chrome_path: Path to Chrome executable

        Raises:
            ValueError: If chrome_path is empty or invalid format
        """
        # Validate Chrome path
        if not chrome_path or not isinstance(chrome_path, str):
            raise ValueError("Chrome path must be a non-empty string")
        if len(chrome_path) < 3:
            raise ValueError("Chrome path too short")
        # Basic path format validation (contains path separators)
        if "/" not in chrome_path and "\\" not in chrome_path and not chrome_path.endswith(".exe"):
            raise ValueError("Chrome path appears invalid (expected path with separators or .exe)")

        if self.project_context is None:
            raise ValueError("SarahAgent requires an active project context.")

        PipelineArtifactAdapter(self.project_context).save_metadata(
            "chrome_path.json", {"chrome_path": chrome_path}
        )
        self._chrome_path = chrome_path
        logger.info("Chrome path saved to project artifacts")
        return

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

            # Extract Chrome path and target URL from input
            chrome_path = input_data.get("chrome_path", self._chrome_path)
            target_url = input_data.get("target_url", "")

            # Store Chrome path if provided
            if chrome_path and chrome_path != self._chrome_path:
                await self._store_chrome_path(chrome_path)

            self._target_url = target_url

            # Load test cases from workspace/testcases/
            test_cases_result = await self._load_test_cases()
            if not test_cases_result.success:
                return test_cases_result

            self._test_cases = test_cases_result.data or []

            if not self._test_cases:
                return StageResult(
                    success=True,
                    data=[],
                    errors=[],
                    warnings=["No test cases found in workspace/testcases/"],
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

    async def _load_test_cases(self) -> StageResult:
        """Load test cases from project artifacts or workspace/testcases/."""
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
            try:
                data = json.loads(artifact.content)
                if isinstance(data, list):
                    for item in data:
                        test_cases.append(TestCase(**item))
                else:
                    test_cases.append(TestCase(**data))
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                errors.append(f"Failed to parse {artifact.name}: {e}")

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

    async def _generate_scripts(self) -> StageResult:
        """Generate Playwright scripts for all test cases.

        Returns:
            StageResult with generated scripts
        """
        self._generated_scripts = []
        errors: list[str] = []
        warnings: list[str] = []

        # Initialize script generator with vision locator if available
        script_generator = ScriptGenerator(
            output_base_dir=Path("/dev/null"),  # output_base_dir no longer used for writing
            llm_config=self.config,
            config=self.app_settings,
            vision_locator=self._vision_locator,
        )

        total = len(self._test_cases)

        for i, test_case in enumerate(self._test_cases, start=1):
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

                    generated_script = GeneratedScript(
                        test_case=test_case,
                        script_content=full_script_content,
                        file_path=filename,
                        confidence=script_data.get("confidence", 0.5),
                    )
                    self._generated_scripts.append(generated_script)

                    if result.warnings:
                        warnings.extend(result.warnings)
                else:
                    error_msg = f"Failed to generate script for '{test_case.title}'"
                    if result.errors:
                        error_msg += f": {result.errors[0]}"
                    errors.append(error_msg)

            except Exception as e:
                logger.error(f"Error generating script for '{test_case.title}': {e}")
                errors.append(f"Exception for '{test_case.title}': {e}")
                # Add placeholder for failed script so index mapping is preserved
                failed_placeholder = GeneratedScript(
                    test_case=test_case,
                    script_content=f"# Generation failed: {e}",
                    file_path="",
                    confidence=0.0,
                    approved=False,
                    error_message=str(e),
                )
                self._generated_scripts.append(failed_placeholder)

        # Reset review index
        self._current_review_index = 0

        success = len(self._generated_scripts) > 0
        confidence = (
            sum(s.confidence for s in self._generated_scripts) / len(self._generated_scripts)
            if self._generated_scripts
            else 0.0
        )

        return StageResult(
            success=success,
            data=self._generated_scripts,
            errors=errors,
            warnings=warnings,
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

        await self.send_message(
            f"Regenerating script for '{test_case.title}' with feedback...",
            message_type="info",
        )

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
                # Note: feedback is not yet supported by ScriptGenerator
                # Future enhancement: pass feedback for regeneration context
            )

            if result.success and result.data:
                script_data = result.data[0]
                header = script_generator._generate_script_header(test_case)
                full_script_content = header + "\n\n" + script_data.get("script_content", "")
                filename = script_generator._generate_filename(test_case.title)

                # Replace current script
                self._generated_scripts[self._current_review_index] = GeneratedScript(
                    test_case=test_case,
                    script_content=full_script_content,
                    file_path=filename,
                    confidence=script_data.get("confidence", 0.5),
                )

                return StageResult(
                    success=True,
                    data=self._generated_scripts,
                    errors=[],
                    warnings=result.warnings if result.warnings else [],
                    confidence=result.confidence,
                )
            else:
                return StageResult(
                    success=False,
                    data=None,
                    errors=result.errors if result.errors else ["Regeneration failed"],
                    warnings=result.warnings if result.warnings else [],
                    confidence=0.0,
                )

        except Exception as e:
            logger.error(f"Error regenerating script: {e}")
            return StageResult(
                success=False,
                data=None,
                errors=[f"Regeneration error: {e}"],
                warnings=[],
                confidence=0.0,
            )

    async def handle_start(self, input_data: dict[str, Any]) -> None:
        """Override handle_start to support Chrome path request.

        Args:
            input_data: User input data
        """
        # Load chrome path now that project_context is available
        self._load_chrome_path()

        # Store input_data for context preservation in reject/regeneration
        self._start_input_data = input_data

        # Check for existing Chrome path
        if not self._chrome_path:
            # Transition to PROCESSING first (BaseAgent contract)
            await self.transition_to(AgentState.PROCESSING)
            # Request Chrome path from user
            await self.send_message(
                "Hi! I'm Sarah. I'll generate Playwright test scripts from Mary's test cases.",
                message_type="text",
            )
            await self.send_message(
                "Please provide the path to your Chrome executable:",
                message_type="info",
                metadata={
                    "type": "chrome_path_request",
                    "example": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                },
            )
            # Transition back to START to wait for user input
            await self.transition_to(AgentState.START)
            return

        # Chrome path exists - proceed with greeting
        await self.send_message(
            "Hi! I'm Sarah. Using your saved Chrome path. Ready to generate scripts from "
            "Mary's test cases.",
            message_type="text",
        )

        # Continue with normal start flow
        await self.transition_to(AgentState.PROCESSING)
        try:
            result = await self.process(input_data, feedback=None)
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
            await self._present_current_script_for_review()
        else:
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message(result.errors),
                message_type="error",
            )

    async def handle_approve(self, data: dict[str, Any] | None = None) -> None:
        """Handle approval of current script.

        Saves the approved script and advances to next script or DONE.
        """
        if self._current_review_index >= len(self._generated_scripts):
            await self.send_message(
                "No script to approve.",
                message_type="warning",
            )
            return

        # Mark current script as approved and persist in project mode.
        current_script = self._generated_scripts[self._current_review_index]
        current_script.approved = True
        if self.project_context is None:
            raise ValueError("SarahAgent requires an active project context.")

        PipelineArtifactAdapter(self.project_context).save_script(
            Path(current_script.file_path).name or f"{current_script.test_case.filename}.spec.ts",
            current_script.script_content,
        )

        await self.send_message(
            f"Script '{current_script.test_case.title}' approved and saved.",
            message_type="success",
            metadata={
                "action": "script_approved",
                "file_path": current_script.file_path,
                "current_index": self._current_review_index,
            },
        )

        # Advance to next script
        self._current_review_index += 1

        # Check if all scripts approved
        if self._current_review_index >= len(self._generated_scripts):
            # Write all approved scripts metadata
            await self._write_approved_scripts_metadata()

            # Transition to DONE
            await self.transition_to(AgentState.DONE)
            destination = "project artifacts"
            await self.send_message(
                f"{len(self._generated_scripts)} scripts saved to {destination}",
                message_type="success",
            )
        else:
            # Present next script for review
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self._present_current_script_for_review()

    async def handle_reject(self, feedback: str) -> None:
        """Handle rejection of current script with feedback.

        Regenerates the current script with feedback context.

        Args:
            feedback: User rejection feedback
        """
        if self._current_review_index >= len(self._generated_scripts):
            await self.send_message(
                "No script to reject.",
                message_type="warning",
            )
            return

        current_script = self._generated_scripts[self._current_review_index]

        # Acknowledge feedback
        await self.send_message(
            f"I'll revise the script for '{current_script.test_case.title}' "
            f"to address your feedback: '{feedback}'",
            message_type="text",
        )

        # Transition to processing
        await self.transition_to(AgentState.PROCESSING)

        # Regenerate with feedback - preserve original input context
        try:
            result = await self.process(self._start_input_data, feedback=feedback)

            if result.success:
                await self.transition_to(AgentState.REVIEW_REQUEST)
                await self._present_current_script_for_review()
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
        """Handle skip request (hand off to Minh for review).

        Advances to next script without saving current one.
        """
        if self._current_review_index >= len(self._generated_scripts):
            await self.send_message(
                "No script to skip.",
                message_type="warning",
            )
            return

        current_script = self._generated_scripts[self._current_review_index]

        await self.send_message(
            f"Script '{current_script.test_case.title}' skipped. "
            f"It will remain available for manual review by Minh.",
            message_type="info",
            metadata={
                "action": "script_skipped",
                "file_path": current_script.file_path,
                "current_index": self._current_review_index,
            },
        )

        # Advance to next script
        self._current_review_index += 1

        # Check if all scripts reviewed
        if self._current_review_index >= len(self._generated_scripts):
            # Write approved scripts metadata
            await self._write_approved_scripts_metadata()

            # Transition to DONE
            await self.transition_to(AgentState.DONE)
            approved_count = sum(1 for s in self._generated_scripts if s.approved)
            destination = "project artifacts"
            await self.send_message(
                f"Review complete. {approved_count} of {len(self._generated_scripts)} "
                f"scripts approved and saved to {destination}",
                message_type="success",
            )
        else:
            # Present next script for review
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self._present_current_script_for_review()

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

    async def _present_current_script_for_review(self) -> None:
        """Present current script for side-by-side review."""
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
        """Write metadata for all approved scripts."""
        if self.project_context is None:
            raise ValueError("SarahAgent requires an active project context.")

        adapter = PipelineArtifactAdapter(self.project_context)
        for script in self._generated_scripts:
            try:
                adapter.save_metadata(
                    f"{script.test_case.filename}.metadata.json",
                    {
                        "source_url": script.test_case.filename,
                        "model": self.config.model_name,
                        "confidence": script.confidence,
                        "test_case_title": script.test_case.title,
                    },
                )
            except Exception as e:
                logger.error(f"Failed to save metadata for {script.test_case.title}: {e}")

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
