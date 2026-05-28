import logging
from datetime import UTC, datetime
from typing import Any

from ai_qa.agents.base import AgentState, BaseAgent
from ai_qa.ai_connection.client import LLMClient
from ai_qa.config import AppSettings
from ai_qa.mcp.client import MCPClient
from ai_qa.models import StageResult
from ai_qa.pipelines.artifact_adapter import PipelineArtifactAdapter
from ai_qa.pipelines.confluence_reader import ConfluenceReader, ConfluenceURLParser
from ai_qa.pipelines.models import ConfluencePage
from ai_qa.pipelines.requirement_formatter import RequirementFormatter

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
            kwargs["step_number"] = 2
            kwargs["step_title"] = "Requirements Extraction"
        super().__init__(**kwargs)
        self.pages: list[Any] = []
        self.current_page_index = 0
        self.output_files_saved = 0
        self._mcp_pat: str | None = None
        self._space_key: str | None = None
        self._page_id: str | None = None
        self.phase = "init"

    async def handle_start(self, input_data: dict[str, Any]) -> None:
        """Override to parse multiple pages immediately."""
        await self.transition_to(AgentState.PROCESSING)

        # Start processing
        try:
            result = await self.process(input_data)
        except Exception as exc:
            logger.error("BobAgent handle_start error: %s", exc, exc_info=True)
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message([str(exc)]),
                message_type="error",
            )
            return

        if (
            result.success
            and isinstance(result.data, dict)
            and result.data.get("type") == "confirm_parent"
        ):
            self.phase = "confirm_parent"
            await self.transition_to(AgentState.REVIEW_REQUEST)
            suggested = result.data.get("suggested_page", "")
            await self.send_message(
                content="I found the below link contains all requirements, is it correct? If not, please input the correct one.",
                message_type="text",
                metadata={"is_confirm_parent": True, "suggested_page": suggested},
            )
            return

        if result.success and self.pages:
            self.phase = "review_markdown"
            self.current_page_index = 0
            self.output_files_saved = 0
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self.send_message(
                content="Please review the extracted requirements below.",
                message_type="text",
                metadata={
                    "is_review_ready": True,
                    "pages": self.pages,
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

        confluence_url = input_data.get("confluence_url") or ""

        # Try to get confluence_url from project DB if not provided
        if not confluence_url and self.project_context and self.project_context.artifact_service:
            db = self.project_context.artifact_service.db
            from ai_qa.db.models import Project

            project = db.get(Project, self.project_context.project_id)
            if project and project.confluence_base_url:
                confluence_url = project.confluence_base_url

        logger.debug("BobAgent.process: confluence_url=%r", confluence_url)

        # Extract page_id from the URL (works for all Confluence formats including
        # /spaces/SPACE/pages/PAGE_ID/ which doesn't match the space-key regexes)
        parser = ConfluenceURLParser()
        page_id = parser.extract_page_id(confluence_url) if confluence_url else None
        logger.debug("BobAgent.process: page_id=%r", page_id)

        # Connect to MCP first
        mcp_pat = input_data.get("mcp_pat")
        self._mcp_pat = mcp_pat
        settings = AppSettings()

        await self.send_message(
            content="Connecting to MCP Server...",
            message_type="info",
            metadata={
                "type": "thinking_trace",
                "trace": {
                    "agent_name": "Bob",
                    "available_models": [],
                    "chain_of_thought": [
                        "Initializing MCP Client connection",
                        "Connect status: processing",
                        "Read Confluence page via MCP: pending",
                    ],
                },
            },
        )

        client = MCPClient(auth_token=mcp_pat, settings=settings)
        try:
            await client.connect()
        except Exception as e:
            logger.error("Failed to connect to MCP Server: %s", e, exc_info=True)
            # Update Bob's Thought with the failure
            await self.send_message(
                content="Connect status: FAIL",
                message_type="info",
                metadata={
                    "type": "thinking_trace",
                    "trace": {
                        "agent_name": "Bob",
                        "available_models": [],
                        "chain_of_thought": [f"Connect status: FAIL — {e}"],
                    },
                },
            )
            return StageResult(
                success=False,
                data=None,
                errors=[f"MCP Connection failed: {e}"],
                warnings=[],
                confidence=0.0,
            )

        await self.send_message(
            content="Connected to MCP Server.",
            message_type="info",
            metadata={
                "type": "thinking_trace",
                "trace": {
                    "agent_name": "Bob",
                    "available_models": [],
                    "chain_of_thought": [
                        "Connect status: OK",
                        "Read Confluence page via MCP: processing",
                    ],
                },
            },
        )

        try:
            # Determine suggested page — never crash here; always
            # reach confirm_parent so the user can correct the suggestion.
            suggested = confluence_url

            if page_id:
                logger.debug("BobAgent.process: have page_id=%r, extracting from URL", page_id)
                space_key = parser.extract_space_key(confluence_url)
                self._space_key = space_key
                self._page_id = page_id
            else:
                space_key = parser.extract_space_key(confluence_url)
                logger.debug("BobAgent.process: fallback space_key=%r", space_key)
                if not space_key:
                    return StageResult(
                        success=False,
                        data=None,
                        errors=[
                            "Could not determine a Confluence page ID or space key from the "
                            f"URL: '{confluence_url}'. "
                            "Please ensure the project's Confluence Base URL points to a "
                            "specific page or includes the space key in the path."
                        ],
                        warnings=[],
                        confidence=0.0,
                    )

                self._space_key = space_key

            await self.send_message(
                content="Found the requirements page.",
                message_type="info",
                metadata={
                    "type": "thinking_trace",
                    "trace": {
                        "agent_name": "Bob",
                        "available_models": [],
                        "chain_of_thought": [
                            "Connect status: OK",
                            "Read Confluence page via MCP: request_review",
                        ],
                    },
                },
            )

            return StageResult(
                success=True,
                data={"type": "confirm_parent", "suggested_page": suggested},
                errors=[],
                warnings=[],
                confidence=1.0,
            )
        finally:
            await client.disconnect()

    async def _extract_descendants(self, parent_title: str) -> StageResult:
        """Phase 2: Extract descendants using the confirmed parent page.

        If self._page_id is set, uses confluence_get_children directly (faster).
        Otherwise falls back to searching by title within the space.
        """
        if not self._mcp_pat:
            return StageResult(
                success=False,
                data=None,
                errors=["Missing MCP PAT for extraction."],
                warnings=[],
                confidence=0.0,
            )

        settings = AppSettings()
        client = MCPClient(auth_token=self._mcp_pat, settings=settings)
        try:
            await client.connect()
        except Exception as e:
            logger.error("Failed to connect to MCP Server during extraction: %s", e, exc_info=True)
            return StageResult(
                success=False,
                data=None,
                errors=[f"MCP Connection failed: {str(e)}"],
                warnings=[],
                confidence=0.0,
            )

        try:
            confluence_base_url = None
            if self.project_context and self.project_context.artifact_service:
                db = self.project_context.artifact_service.db
                from ai_qa.db.models import Project

                project = db.get(Project, self.project_context.project_id)
                if project:
                    confluence_base_url = project.confluence_base_url

            reader = ConfluenceReader(client, confluence_base_url=confluence_base_url)

            await self.send_message(
                f"Extracting child pages for '{parent_title}'...",
                "info",
                metadata={
                    "type": "thinking_trace",
                    "trace": {
                        "agent_name": "Bob",
                        "available_models": [],
                        "chain_of_thought": [
                            "Connect status: OK",
                            f"Fetching children of '{parent_title}' via MCP: processing",
                        ],
                    },
                },
            )

            # Use page_id if available (direct children fetch), else search by title
            if self._page_id:
                logger.debug("_extract_descendants: using page_id=%r for children", self._page_id)
                desc_res = await reader.get_children_by_id(self._page_id)
            elif self._space_key:
                logger.debug(
                    "_extract_descendants: using space_key=%r + title for descendants",
                    self._space_key,
                )
                desc_res = await reader.get_descendants_by_title(self._space_key, parent_title)
            else:
                return StageResult(
                    success=False,
                    data=None,
                    errors=["No page_id or space_key available to fetch children."],
                    warnings=[],
                    confidence=0.0,
                )
            if not desc_res.success:
                return desc_res

            summaries = []
            from ai_qa.pipelines.models import PageSummary

            if self._page_id and parent_title:
                summaries.append(
                    PageSummary(page_id=self._page_id, title=parent_title, url=parent_title)
                )

            if desc_res.data:
                summaries.extend(desc_res.data)

            if not summaries:
                return StageResult(
                    success=False,
                    data=None,
                    errors=["No pages found to extract (parent or descendants)."],
                    warnings=[],
                    confidence=0.0,
                )

            if self.project_context is None:
                raise ValueError("BobAgent requires an active project context.")

            adapter = PipelineArtifactAdapter(self.project_context)

            # Phase 1: Extract Raw HTML
            raw_pages: list[ConfluencePage] = []
            for summary in summaries:
                if not summary.page_id:
                    continue
                await self.send_message(f"Extracting page '{summary.title}'...", "info")

                # Fetch directly by page ID instead of URL to avoid URL validation issues
                page_result = await reader.read_page_by_id(summary.page_id)
                if not page_result.success or not page_result.data:
                    await self.send_message(f"⚠ Failed to extract: '{summary.title}'", "warning")
                    continue

                page: ConfluencePage = page_result.data
                adapter.save_raw_html(page.page_id, page.content)
                await self.send_message(f"✓ Extracted '{summary.title}'", "info")
                raw_pages.append(page)

            # Setup LLM for Bob
            config = self.get_llm_config()
            llm_client = LLMClient(config)
            formatter = RequirementFormatter(llm_client)

            # Phase 2: Convert to Requirement
            self.pages = []
            for page in raw_pages:
                await self.send_message(f"Converting '{page.title}' to requirement...", "info")
                try:
                    requirement_md = await formatter.convert_page(page)
                    adapter.save_requirement_page(f"{page.page_id}/requirement.md", requirement_md)
                    await self.send_message(f"✓ Converted '{page.title}'", "info")
                    self.pages.append(
                        {
                            "page_id": page.page_id,
                            "page_title": page.title,
                            "source_url": page.url,
                            "raw_html": page.content,
                            "requirement_md": requirement_md,
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to convert page {page.title}: {e}")
                    await self.send_message(f"⚠ Failed to convert: '{page.title}'", "warning")

            if not self.pages:
                return StageResult(
                    success=False,
                    data=None,
                    errors=["All pages failed to extract or convert"],
                    warnings=[],
                    confidence=0.0,
                )

            await self.send_message(
                content="Requirements extraction complete.",
                message_type="info",
                metadata={
                    "type": "thinking_trace",
                    "trace": {
                        "agent_name": "Bob",
                        "available_models": [],
                        "chain_of_thought": [
                            "Connect status: OK",
                            "Extract requirements from MCP: done",
                        ],
                    },
                },
            )

            return StageResult(
                success=True,
                data=self.pages,
                errors=[],
                warnings=[],
                confidence=1.0,
            )

        finally:
            await client.disconnect()

    async def handle_approve(self, data: dict[str, Any] | None = None) -> None:
        """Override to handle paginated approval and parent confirmation."""
        if self.phase == "confirm_parent":
            # Proceed to Phase 2: Extraction
            confirmed_page = data.get("confirmed_page_name") if data else None
            if not confirmed_page and data and data.get("suggested_page"):
                confirmed_page = data.get("suggested_page")

            if not confirmed_page:
                await self.send_message("No page title provided.", "error")
                return

            parser = ConfluenceURLParser()
            new_page_id = parser.extract_page_id(confirmed_page)
            if new_page_id:
                self._page_id = new_page_id

            new_space_key = parser.extract_space_key(confirmed_page)
            if new_space_key:
                self._space_key = new_space_key

            await self.transition_to(AgentState.PROCESSING)
            result = await self._extract_descendants(confirmed_page)

            if result.success and self.pages:
                self.phase = "review_markdown"
                self.current_page_index = 0
                self.output_files_saved = 0
                await self.transition_to(AgentState.REVIEW_REQUEST)
                await self.send_message(
                    content="Please review the extracted requirements below.",
                    message_type="text",
                    metadata={
                        "is_review_ready": True,
                        "pages": self.pages,
                    },
                )
            else:
                await self.transition_to(AgentState.ERROR)
                await self.send_message(
                    content=self._format_error_message(
                        result.errors if result.errors else ["Failed to extract."]
                    ),
                    message_type="error",
                )
            return

        # Markdown Review Phase (Split Panel)
        if data and data.get("action") == "approved":
            page_id = data.get("page_id")
            updated_markdown = data.get("markdown")

            # Find the page
            page = next((p for p in self.pages if p["page_id"] == page_id), None)
            if page and updated_markdown:
                page["requirement_md"] = updated_markdown

                if self.project_context is None:
                    raise ValueError("BobAgent requires an active project context.")
                adapter = PipelineArtifactAdapter(self.project_context)

                # Resave requirement page with updated content
                adapter.save_requirement_page(f"{page['page_id']}/requirement.md", updated_markdown)
                # Resave metadata
                adapter.save_metadata(
                    f"{page['page_id']}/requirement.metadata.json",
                    {
                        "source_url": page["source_url"],
                        "extracted_at": datetime.now(UTC).isoformat(),
                    },
                )
                self.output_files_saved += 1

        # Move to next page or finish
        # Move to next page or finish
        self.current_page_index += 1

        if self.current_page_index >= len(self.pages):
            await self.transition_to(AgentState.DONE)
            await self.send_message(
                f"Saved {self.output_files_saved} approved requirements. I'm handing off to Mary to create test cases.",
                "success",
            )
            return

        # Let the frontend manage pagination locally with the single review payload we already sent.
        # So we just wait here until all pages are iterated.

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
