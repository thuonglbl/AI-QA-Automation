"""Converts Confluence raw HTML into BMAD story-style markdown requirements."""

import asyncio
import base64
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from bs4 import BeautifulSoup
from markdownify import markdownify

from ai_qa.ai_connection.client import LLMClient
from ai_qa.pipelines.models import ConfluencePage

logger = logging.getLogger(__name__)

# Hard wall-clock ceiling for one requirement-conversion LLM call. The httpx read
# timeout (LLMConfig.timeout) is per-chunk and can fail to fire if the provider
# trickles bytes, so this asyncio.wait_for total bound guarantees a hung/stalled
# call surfaces as a failed conversion (caught in Bob's convert loop) instead of
# stalling the whole extraction step indefinitely.
_CONVERT_LLM_TIMEOUT = 600.0

# Resolves an image URL to (bytes, mime), or None if unavailable. Lets the caller
# inject a fetch strategy (e.g. via the MCP attachment tools, which reach private
# Confluence across spaces) instead of the default direct HTTP GET.
ImageFetcher = Callable[[str], Awaitable[tuple[bytes, str] | None]]


def _sniff_image_mime(content: bytes) -> str:
    """Best-effort image MIME from magic bytes; '' when not a recognized raster image."""
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return ""


def _label_from_image_url(url: str) -> str:
    """Human-ish label from an image URL's filename — used when neither a vision
    caption nor alt text is available (e.g. ``.../EditJourney_Basis.png`` → 'EditJourney Basis').
    """
    from urllib.parse import urlparse

    name = urlparse(url).path.rstrip("/").split("/")[-1]
    if not name:
        return ""
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return stem.replace("_", " ").replace("-", " ").replace("+", " ").strip()


class RequirementFormatter:
    """Converts raw Confluence HTML into BMAD story-style requirement.md."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def convert_page(self, page: ConfluencePage, feedback: str | None = None) -> str:
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

        return await self._format_story(page, md, feedback)

    async def convert_markdown(
        self,
        page: ConfluencePage,
        markdown: str,
        *,
        auth_token: str | None = None,
        image_fetcher: ImageFetcher | None = None,
    ) -> str:
        """Convert pre-parsed Markdown to BMAD story format, then replace embedded
        images with a URI + LLM vision caption.

        The raw image is meaningless to the downstream test-case agent and won't
        render in the UI, so each ``![alt](src)`` becomes ``[Image: {caption}]({uri})`` —
        a plain link carrying a vision-generated caption Mary CAN use. ``image_fetcher``,
        when given, resolves the image bytes (e.g. via the MCP attachment tools, which
        reach private Confluence across spaces); otherwise a direct HTTP GET is used
        with ``auth_token`` attached only to the page's own host.
        """
        formatted = await self._format_story(page, markdown)
        captioned = await self.caption_images_in_markdown(
            page, formatted, auth_token=auth_token, image_fetcher=image_fetcher
        )
        return self._absolutize_links(page, captioned)

    def _absolutize_links(self, page: ConfluencePage, markdown: str) -> str:
        """Rewrite site-relative Confluence links (``[text](/spaces/...)``) to absolute
        URLs on the Confluence host.

        Markdownify keeps cross-page links as root-relative paths; rendered in the app
        they'd resolve against the app origin (e.g. http://localhost:5173/spaces/...).
        The Confluence host comes from page.url (derived from the project's
        ``confluence_base_url``). Leaves absolute/anchor/mailto links untouched.
        """
        from urllib.parse import urlparse

        site_root = ""
        if page.url:
            parsed = urlparse(page.url)
            if parsed.scheme and parsed.netloc:
                site_root = f"{parsed.scheme}://{parsed.netloc}"
        if not site_root:
            return markdown

        # Non-image markdown links ((?<!!)) whose href is a site-absolute path ("/..."
        # but not protocol-relative "//"); optional ("title") tail preserved-by-drop.
        link_re = re.compile(r"(?<!!)\[([^\]]*)\]\(\s*(/(?!/)[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
        return link_re.sub(lambda m: f"[{m.group(1)}]({site_root}{m.group(2)})", markdown)

    async def caption_images_in_markdown(
        self,
        page: ConfluencePage,
        markdown: str,
        *,
        auth_token: str | None = None,
        image_fetcher: ImageFetcher | None = None,
    ) -> str:
        """Replace every ``![alt](src)`` with ``[Image: {caption}]({uri})``.

        Resolves each image's bytes via ``image_fetcher`` when given (e.g. the MCP
        attachment tools, which reach private Confluence across spaces), else a direct
        HTTP GET (``auth_token`` attached only to the Confluence host). Verifies it is
        really an image, then captions it with the vision model. Degrades gracefully —
        vision caption → alt text → filename-derived label → bare URI — and never emits
        a broken ``<img>``. Deterministic.
        """
        from urllib.parse import urljoin, urlparse

        import httpx

        pattern = re.compile(r"!\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
        matches = pattern.findall(markdown)
        if not matches:
            return markdown

        page_parsed = urlparse(page.url) if page.url else None
        site_root = (
            f"{page_parsed.scheme}://{page_parsed.netloc}"
            if page_parsed and page_parsed.scheme and page_parsed.netloc
            else ""
        )
        confluence_host = page_parsed.netloc if page_parsed else ""

        resolved: dict[str, tuple[str, str]] = {}  # src -> (abs_url, label)
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as http_client:
            for alt, src in matches:
                if src in resolved:
                    continue
                abs_url = src
                if not src.startswith("http"):
                    abs_url = urljoin(f"{site_root}/", src.lstrip("/")) if site_root else src

                img_bytes: bytes = b""
                mime = ""
                try:
                    if image_fetcher is not None:
                        fetched = await image_fetcher(abs_url)
                        if fetched is not None:
                            img_bytes, mime = fetched
                    else:
                        # SECURITY: only send the Confluence credential to the Confluence
                        # host — never leak the PAT to an external image host.
                        headers: dict[str, str] = {}
                        if (
                            auth_token
                            and confluence_host
                            and urlparse(abs_url).netloc == confluence_host
                        ):
                            headers["Authorization"] = f"Bearer {auth_token}"
                        resp = await http_client.get(abs_url, headers=headers)
                        resp.raise_for_status()
                        img_bytes = resp.content
                        ct = (resp.headers.get("content-type") or "").split(";")[0].strip()
                        mime = ct.lower() or _sniff_image_mime(resp.content)
                except Exception as e:
                    logger.warning(
                        "Failed to fetch image %s (%s): %s", abs_url, type(e).__name__, e
                    )

                caption = ""
                if img_bytes:
                    if mime.startswith("image/") and mime != "image/svg+xml":
                        caption = await self._caption_image(img_bytes, src, mime or "image/png")
                    else:
                        # Login-page HTML, SVG, or non-raster: don't feed it to vision.
                        logger.warning(
                            "Skipping caption for %s: non-image content-type %r", abs_url, mime
                        )

                # Label priority: vision caption → source alt text → filename-derived
                # label (descriptive Confluence filenames are a useful last resort).
                label = caption.strip() or alt.strip() or _label_from_image_url(abs_url)
                resolved[src] = (abs_url, label)

        def _replace(m: re.Match[str]) -> str:
            src = m.group(2)
            abs_url, label = resolved.get(src, (src, m.group(1).strip()))
            return f"[Image: {label}]({abs_url})" if label else f"[Image]({abs_url})"

        return pattern.sub(_replace, markdown)

    async def _caption_image(
        self, image_bytes: bytes, filename: str, mime_type: str = "image/png"
    ) -> str:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        prompt = "Describe this image in a single sentence as it relates to software requirements."
        try:
            return await self._llm.invoke_vision(prompt, b64, mime_type=mime_type)
        except Exception as e:
            # Surface the provider's real rejection (e.g. a 400 'model does not support
            # image input' from the on-prem proxy) so the failure is diagnosable.
            # Never log the credential. Return "" so the caller can fall back to alt text.
            detail = getattr(e, "body", None) or getattr(getattr(e, "response", None), "text", None)
            logger.warning(
                "Vision model failed for %s (%s): %s%s",
                filename,
                type(e).__name__,
                e,
                f" | provider_detail={detail}" if detail else "",
            )
            return ""

    async def _format_story(
        self, page: ConfluencePage, raw_markdown: str, feedback: str | None = None
    ) -> str:
        revision = ""
        if feedback:
            revision = (
                "\n\nIMPORTANT — a reviewer rejected the previous version with this "
                f"feedback. Revise the requirement to address it:\n{feedback}\n"
            )
        prompt = f"""You are a Product Manager converting Confluence content into a BMAD-style Requirement Story.
{revision}
Page Title: {page.title}
Source: {page.url}

Content:
{raw_markdown}

CRITICAL: Base the requirement ONLY on the Content above. Do NOT invent, assume, or infer
requirements that are not present in the Content. If the Content is empty or has no
substantive requirements, output ONLY the title, the Source/Extracted lines, and the single
line "_No extractable requirements found on this page._" — do NOT emit Story, Acceptance
Criteria, or Technical Requirements sections.

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

[Reorganize the remaining content under logical headings. **Preserve all source headings, bulleted/numbered lists, and Markdown tables verbatim — do not collapse tables into prose or drop list items.** Keep all image references.]
"""
        from langchain_core.messages import HumanMessage

        # Bound the call with a hard wall-clock timeout (mirrors Bob's clarify loop,
        # bob.py:1581). A hung/stalled provider then raises asyncio.TimeoutError, which
        # Bob's convert loop catches as a failed conversion and moves on to the next
        # page instead of freezing the whole extraction step.
        resp = await asyncio.wait_for(
            self._llm._chat_model.ainvoke([HumanMessage(content=prompt)]),
            timeout=_CONVERT_LLM_TIMEOUT,
        )
        return str(resp.content)
