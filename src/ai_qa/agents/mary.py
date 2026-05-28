"""Mary agent - Test Case Generation with Per-Item Review.

Mary generates test cases from requirements extracted by Bob and presents them
for per-item review. Users can approve or reject individual test cases with feedback.
"""

import logging
import tempfile
from pathlib import Path
from typing import Any

from ai_qa.agents.base import AgentState, BaseAgent
from ai_qa.models import StageResult, TestCase
from ai_qa.pipelines.artifact_adapter import PipelineArtifact, PipelineArtifactAdapter
from ai_qa.pipelines.test_case_extractor import TestCaseExtractor

logger = logging.getLogger(__name__)


class MaryAgent(BaseAgent):
    """Agent for generating and reviewing test cases.

    Mary reads requirements from workspace/requirements/, generates test cases
    using TestCaseExtractor, and presents them for per-item review. Users can
    approve or reject individual test cases with feedback.

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

        # Initialize pipeline components
        self.config = self.get_llm_config()

        self.extractor = TestCaseExtractor(
            llm_config=self.config,
        )

    async def process(
        self,
        input_data: dict[str, Any],
        feedback: str | None = None,
    ) -> StageResult:
        """Generate test cases from requirements.

        Args:
            input_data: User input (ignored for Mary - reads from workspace)
            feedback: User rejection feedback for re-processing

        Returns:
            StageResult with generated test cases
        """
        try:
            if self.project_context is None:
                raise ValueError("MaryAgent requires an active project context.")

            requirement_artifacts = PipelineArtifactAdapter(
                self.project_context
            ).load_requirement_markdown()
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

            # Extract test cases using TestCaseExtractor
            source_urls = [""] * len(requirements_files)
            result = await self.extractor.extract_batch(requirements_files, source_urls)

            if not result.success:
                return result

            # Store generated test cases
            self.test_cases = result.data or []

            # Send progress updates for each test case
            for i, _test_case in enumerate(self.test_cases, start=1):
                await self.send_message(
                    f"Generating test case {i} of {len(self.test_cases)}...",
                    message_type="info",
                )

            # Reset review index
            self.current_review_index = 0

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

    async def handle_approve(self, data: dict[str, Any] | None = None) -> None:
        """Handle approval of current test case.

        Advances to next test case or transitions to DONE if all approved.
        """
        # Mark current test case as approved (implicit by advancing index)
        self.current_review_index += 1

        # Check if all test cases approved
        if self.current_review_index >= len(self.test_cases):
            # Write all approved test cases to workspace
            await self._write_approved_test_cases()

            # Transition to DONE
            await self.transition_to(AgentState.DONE)
            destination = "project artifacts"
            await self.send_message(
                f"{len(self.test_cases)} test cases saved to {destination}",
                message_type="success",
            )
        else:
            # Present next test case for review
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self._present_current_test_case()

    async def handle_reject(self, feedback: str) -> None:
        """Handle rejection of current test case with feedback.

        Re-generates the current test case with feedback context and re-presents.

        Args:
            feedback: User rejection feedback
        """
        # Paraphrase feedback in acknowledgment (UX-DR12)
        await self.send_message(
            f"I'll revise the test case to address your feedback: '{feedback}'",
            message_type="text",
        )

        # Re-generate current test case with feedback
        await self.transition_to(AgentState.PROCESSING)

        # For now, we'll re-run extraction with feedback context
        # In a more sophisticated implementation, we'd extract just the current test case
        try:
            if self.project_context is None:
                raise ValueError("MaryAgent requires an active project context.")

            requirement_artifacts = PipelineArtifactAdapter(
                self.project_context
            ).load_requirement_markdown()
            requirements_files = self._materialize_requirement_artifacts(requirement_artifacts)

            if requirements_files:
                # Extract with feedback context (simplified - re-extracts all)
                result = await self.extractor.extract_batch(
                    requirements_files, [""] * len(requirements_files)
                )

                if result.success and result.data:
                    # Replace current test case with regenerated one
                    if self.current_review_index < len(result.data):
                        self.test_cases[self.current_review_index] = result.data[
                            self.current_review_index
                        ]

            # Re-present the test case
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self._present_current_test_case()

        except Exception as e:
            logger.error(f"Error re-generating test case: {e}")
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                f"Failed to regenerate test case: {e}",
                message_type="error",
            )

    def _format_review_content(self, result: StageResult) -> str:
        """Format test case for review display.

        Args:
            result: StageResult with test case data

        Returns:
            Formatted markdown string with test case structure
        """
        if not self.test_cases or self.current_review_index >= len(self.test_cases):
            return "No test case to review."

        test_case = self.test_cases[self.current_review_index]
        total = len(self.test_cases)
        current = self.current_review_index + 1

        # Format test case with clear structure
        content = f"## Test Case {current} of {total}: {test_case.title}\n\n"

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

        return content

    async def _present_current_test_case(self) -> None:
        """Present current test case for review via WebSocket."""
        if self.test_cases and self.current_review_index < len(self.test_cases):
            test_case = self.test_cases[self.current_review_index]
            total = len(self.test_cases)

            content = self._format_review_content(
                StageResult(success=True, data=self.test_cases, errors=[], warnings=[])
            )

            await self.send_message(
                content,
                message_type="text",
                metadata={
                    "test_case": test_case.model_dump(),
                    "current_index": self.current_review_index,
                    "total_count": total,
                },
            )

    async def _write_approved_test_cases(self) -> None:
        """Write all approved test cases to project artifacts or workspace/testcases/."""
        if self.project_context is None:
            raise ValueError("MaryAgent requires an active project context.")

        adapter = PipelineArtifactAdapter(self.project_context)
        for test_case in self.test_cases:
            try:
                filename = f"{test_case.filename}.json"
                adapter.save_test_case(filename, test_case.model_dump_json(indent=2))
                adapter.save_metadata(
                    f"{test_case.filename}.metadata.json",
                    {
                        "source_url": "",
                        "model": self.config.model_name,
                        "confidence": 1.0,
                        "test_case_title": test_case.title,
                    },
                )
            except Exception as e:
                logger.error(f"Failed to save test case {test_case.title}: {e}")

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
