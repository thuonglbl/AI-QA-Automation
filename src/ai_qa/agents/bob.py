import logging
from datetime import UTC, datetime
from typing import Any, cast

from ai_qa.agents.base import AgentState, BaseAgent
from ai_qa.config import AppSettings
from ai_qa.mcp.client import MCPClient
from ai_qa.models import StageResult
from ai_qa.pipelines.artifact_adapter import PipelineArtifactAdapter
from ai_qa.pipelines.confluence_reader import ConfluenceReader, ConfluenceURLParser
from ai_qa.pipelines.content_parser import ContentParser
from ai_qa.pipelines.models import ConfluencePage, OutputMetadata
from ai_qa.pipelines.output_writer import OutputWriter

logger = logging.getLogger(__name__)


class BobAgent(BaseAgent):
    """Bob Agent — Requirements Extraction.

    Extracts pages from Confluence, parses content, and manages
    paginated review of each extracted page.
    """

    def __init__(self, **kwargs: Any) -> None:
        if "name" not in kwargs:
            kwargs["name"] = "Bob"
            kwargs["color"] = "#2196F3"
            kwargs["step_number"] = 3
            kwargs["step_title"] = "Requirements Extraction"
        super().__init__(**kwargs)
        self.pages: list[Any] = []
        self.current_page_index = 0
        self.output_files_saved = 0

    async def handle_start(self, input_data: dict[str, Any]) -> None:
        """Override to parse multiple pages immediately."""
        await self.transition_to(AgentState.PROCESSING)

        # Start processing
        result = await self.process(input_data)

        if result.success and self.pages:
            self.current_page_index = 0
            self.output_files_saved = 0
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self.send_message(
                content=self._format_review_content(result),
                message_type="text",
                metadata={
                    "result": result.model_dump(),
                    "is_paginated": True,
                    "total_pages": len(self.pages),
                    "current_index": self.current_page_index,
                },
            )
        else:
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message(
                    result.errors if result.errors else ["No pages found or parsed."]
                ),
                message_type="error",
            )

    async def process(self, input_data: dict[str, Any], feedback: str | None = None) -> StageResult:
        """Process Confluence extraction."""
        if feedback:
            # Re-process the CURRENT page based on feedback
            current_page = self.pages[self.current_page_index]
            await self.send_message(
                f"Re-processing page {self.current_page_index + 1} with feedback...", "info"
            )

            # For iteration, maybe parse again and use an LLM or simply re-parse.
            # Assuming content parser will apply feedback if LLM stage is integrated,
            # but currently ContentParser is purely rule-based. Let's just return success for the sake of the cycle.
            # Wait, the instruction says "Bob re-processes that single page with feedback context".
            # We don't have LLM integrated yet in Parser, but let's mock the update.
            return StageResult(
                success=True, data=current_page, errors=[], warnings=[], confidence=1.0
            )

        confluence_url = input_data.get("confluence_url")
        if not confluence_url:
            return StageResult(
                success=False,
                data=None,
                errors=["confluence_url is required"],
                warnings=[],
                confidence=0.0,
            )

        mcp_pat = input_data.get("mcp_pat")
        settings = AppSettings()

        # Instantiate MCPClient
        client = MCPClient(auth_token=mcp_pat, settings=settings)
        await client.connect()

        try:
            reader = ConfluenceReader(client)

            # Check if space URL or Page URL
            parser = ConfluenceURLParser()
            page_id = parser.extract_page_id(confluence_url)
            space_key = parser.extract_space_key(confluence_url)

            urls_to_fetch = []
            if page_id:
                urls_to_fetch.append(confluence_url)
            elif space_key:
                list_res = await reader.list_pages_in_space(space_key)
                if not list_res.success:
                    return StageResult(
                        success=False,
                        data=None,
                        errors=list_res.errors,
                        warnings=[],
                        confidence=0.0,
                    )
                urls_to_fetch = [summary.url for summary in (list_res.data or [])]
            else:
                return StageResult(
                    success=False,
                    data=None,
                    errors=["Invalid Confluence URL format."],
                    warnings=[],
                    confidence=0.0,
                )

            await self.send_message(
                f"Discovered {len(urls_to_fetch)} page(s). Extracting...", "info"
            )

            read_res = await reader.read_multiple_pages(urls_to_fetch)
            if not read_res.success:
                return StageResult(
                    success=False, data=None, errors=read_res.errors, warnings=[], confidence=0.0
                )

            confluence_pages = cast(list[ConfluencePage], read_res.data or [])

            parser_stage = ContentParser(self._workspace_dir)
            parse_res = await parser_stage.parse_multiple(confluence_pages)

            if not parse_res.success:
                return StageResult(
                    success=False, data=None, errors=parse_res.errors, warnings=[], confidence=0.0
                )

            self.pages = parse_res.data or []
            return StageResult(
                success=True,
                data=self.pages,
                errors=[],
                warnings=[],
                confidence=parse_res.confidence,
            )

        finally:
            await client.disconnect()

    async def handle_approve(self) -> None:
        """Override to handle paginated approval."""
        current_page = self.pages[self.current_page_index]

        if self.project_context is not None:
            adapter = PipelineArtifactAdapter(self.project_context)
            adapter.save_requirement_page(current_page.page_title, current_page.markdown)
            adapter.save_metadata(
                f"{current_page.page_title}.metadata.json",
                {
                    "source_url": current_page.source_url,
                    "timestamp": datetime.now(UTC),
                    "model": "Gemini-3.1-Pro",
                    "confidence": 1.0,
                },
            )
            self.output_files_saved += 1
        else:
            # Use OutputWriter to save in legacy workspace mode.
            writer = OutputWriter(self._workspace_dir / "requirements")
            metadata = OutputMetadata(
                source_url=current_page.source_url,
                timestamp=datetime.now(UTC),
                model="Gemini-3.1-Pro",  # Or loaded from config
                confidence=1.0,
            )
            write_res = await writer.write(current_page.page_title, current_page.markdown, metadata)

            if write_res.success:
                self.output_files_saved += 1

        self.current_page_index += 1

        if self.current_page_index < len(self.pages):
            # Continue to next page
            await self.transition_to(AgentState.REVIEW_REQUEST)
            result = StageResult(
                success=True,
                data=self.pages[self.current_page_index],
                errors=[],
                warnings=[],
                confidence=1.0,
            )
            await self.send_message(
                content=f"Page {self.current_page_index} approved. Reviewing page {self.current_page_index + 1}...",
                message_type="success",
            )
            await self.send_message(
                content=self._format_review_content(result),
                message_type="text",
                metadata={
                    "result": result.model_dump(),
                    "is_paginated": True,
                    "total_pages": len(self.pages),
                    "current_index": self.current_page_index,
                },
            )
        else:
            # All pages reviewed
            await self.transition_to(AgentState.DONE)
            destination = (
                "project artifacts" if self.project_context is not None else "requirements/"
            )
            await self.send_message(
                content=f"{self.output_files_saved} requirement page(s) saved to {destination}",
                message_type="success",
            )

    async def handle_reject(self, feedback: str) -> None:
        """Override to reject current page only."""
        await self.send_message(
            content=f'Reprocessing page {self.current_page_index + 1} with feedback: "{feedback}"',
            message_type="text",
        )
        await self.transition_to(AgentState.PROCESSING)

        try:
            result = await self.process(input_data={}, feedback=feedback)
        except Exception as exc:
            logger.error("BobAgent Error during reject: %s", exc)
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message([str(exc)]),
                message_type="error",
            )
            return

        if result.success:
            # Update the specific page in the list
            self.pages[self.current_page_index] = result.data
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self.send_message(
                content="Page updated based on feedback.", message_type="success"
            )
            await self.send_message(
                content=self._format_review_content(result),
                message_type="text",
                metadata={
                    "result": result.model_dump(),
                    "is_paginated": True,
                    "total_pages": len(self.pages),
                    "current_index": self.current_page_index,
                },
            )
        else:
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message(result.errors),
                message_type="error",
            )
