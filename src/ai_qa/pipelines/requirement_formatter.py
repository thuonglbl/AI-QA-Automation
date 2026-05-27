"""Converts Confluence raw HTML into BMAD story-style markdown requirements."""

import base64
import logging
import re
from datetime import UTC, datetime

from bs4 import BeautifulSoup
from markdownify import markdownify

from ai_qa.ai_connection.client import LLMClient
from ai_qa.pipelines.models import ConfluencePage

logger = logging.getLogger(__name__)


class RequirementFormatter:
    """Converts raw Confluence HTML into BMAD story-style requirement.md."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def convert_page(self, page: ConfluencePage) -> str:
        """Full conversion pipeline for one page."""
        # 1. HTML -> Markdown text
        md = markdownify(page.content, heading_style="ATX")
        # We need to extract images. Instead of using beautiful soup on html to find images,
        # we can find img urls from html, download them, caption them, and then replace in markdown.
        soup = BeautifulSoup(page.content, "html.parser")

        import httpx

        img_captions: dict[str, str] = {}

        # Gather images
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            for img in soup.find_all("img"):
                src_attr = img.get("src")
                if not src_attr:
                    continue

                src = str(src_attr)

                url = src
                if not url.startswith("http"):
                    base = page.url.rstrip("/")
                    url = f"{base}/{url.lstrip('/')}"

                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    caption = await self._caption_image(resp.content, src)
                    img_captions[src] = caption
                except Exception as e:
                    logger.warning(f"Failed to fetch/caption image {url}: {e}")
                    img_captions[src] = "Image could not be processed"

        # Now replace images in markdown
        # Markdownify outputs images like ![alt](src)
        for src, caption in img_captions.items():
            # simple replacement for ![...](src) -> [Image: caption]
            # Since markdownify might escape things, we use regex
            escaped_src = re.escape(src)
            pattern = re.compile(rf"!\[[^\]]*\]\({escaped_src}[^\)]*\)")
            md = pattern.sub(f"\n\n[Image: {caption}]\n\n", md)

        return await self._format_story(page, md)

    async def _caption_image(self, image_bytes: bytes, filename: str) -> str:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        prompt = "Describe this image in a single sentence as it relates to software requirements."
        try:
            return await self._llm.invoke_vision(prompt, b64)
        except Exception as e:
            logger.warning(f"Vision model failed for {filename}: {e}")
            return "Image could not be captioned"

    async def _format_story(self, page: ConfluencePage, raw_markdown: str) -> str:
        prompt = f"""You are a Product Manager converting Confluence content into a BMAD-style Requirement Story.

Page Title: {page.title}
Source: {page.url}

Content:
{raw_markdown}

Format the output EXACTLY like this (do not output any markdown code blocks, just the text):

# {page.title}

**Source:** {page.url}
**Extracted:** {datetime.now(UTC).isoformat()}

## Story

As a [role inferred from content],
I want [feature/capability from content],
So that [benefit/outcome from content].

## Acceptance Criteria

**Given** [precondition from content]
**When** [action from content]
**Then** [expected result from content]

## Technical Requirements

[Reorganize the remaining content logically under headings here. Keep all Image captions and text.]
"""
        from langchain_core.messages import HumanMessage

        # Use ainvoke directly from the inner chat model to support async
        resp = await self._llm._chat_model.ainvoke([HumanMessage(content=prompt)])
        return str(resp.content)
