import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ai_qa.pipelines.artifact_adapter import PipelineArtifactAdapter

import httpx
import markdownify

from ai_qa.models import StageResult
from ai_qa.pipelines.models import ConfluencePage, ParsedContent

logger = logging.getLogger(__name__)

# Compile regex patterns at module level
TEST_CASE_HEADING_PATTERN = re.compile(
    r"##\s+((?:TC-\d+\s+|Test Case:\s+).+?)(?:\n|$)(.*?)(?=##\s+|\Z)", re.DOTALL
)
PRECONDITIONS_PATTERN = re.compile(
    r"Preconditions?:\s*(.+?)(?=Steps:|Expected Result:|\Z)", re.IGNORECASE | re.DOTALL
)
STEPS_PATTERN = re.compile(r"Steps?:\s*(.+?)(?=Expected Result:|\Z)", re.IGNORECASE | re.DOTALL)
EXPECTED_RESULT_PATTERN = re.compile(
    r"Expected Result:\s*(.+?)(?=\Z|##|Test Case:)", re.IGNORECASE | re.DOTALL
)
TEST_CASE_NUMBERED_PATTERN = re.compile(
    r"(Test Case:\s*.+?)(?:\n|$)(.*?)(?=Test Case:|\Z)", re.DOTALL
)
MERMAID_BLOCK_PATTERN = re.compile(r"```mermaid\n(.*?)\n```", re.DOTALL)
MULTIPLE_BLANK_LINES = re.compile(r"\n{3,}")


class ContentParser:
    """Pipeline stage for converting Confluence content to LLM-friendly formats."""

    def __init__(self, adapter: PipelineArtifactAdapter) -> None:
        self.adapter = adapter

    async def parse(self, page: ConfluencePage) -> StageResult:
        warnings: list[str] = []

        if not page.content.strip():
            parsed = ParsedContent(
                page_id=page.page_id,
                page_title=page.title,
                source_url=page.url,
                markdown="",
                mermaid_diagrams=[],
                image_paths=[],
                test_cases_detected=[],
                parsed_at=datetime.now(UTC),
            )
            return StageResult(
                success=True,
                data=parsed,
                errors=[],
                warnings=["Page has no content"],
                confidence=0.5,
            )

        html_content = page.content
        code_blocks: dict[str, str] = {}
        html_content = self._handle_confluence_macros(html_content, warnings, code_blocks)
        mermaid_diagrams = self._extract_mermaid(html_content, warnings)

        try:
            markdown = self._html_to_markdown(html_content)
            for k, v in code_blocks.items():
                markdown = markdown.replace(k, v)
        except Exception as e:
            logger.warning(f"Failed to convert HTML to Markdown for {page.page_id}: {e}")
            # Do NOT fall back to raw HTML — that would violate the clean-Markdown contract
            # for downstream LLM stages. Return empty markdown with a clear warning.
            markdown = ""
            warnings.append(f"HTML-to-Markdown conversion failed — content unavailable: {e}")

        # Ensure original mermaid blocks in plain markdown are also caught
        for m in MERMAID_BLOCK_PATTERN.finditer(markdown):
            mermaid = m.group(1).strip()
            if mermaid not in mermaid_diagrams:
                mermaid_diagrams.append(mermaid)

        image_paths = await self._save_images(page, html_content, warnings)
        test_cases = self._extract_test_cases(markdown)
        confidence = self._compute_confidence(page, warnings, markdown)

        parsed = ParsedContent(
            page_id=page.page_id,
            page_title=page.title,
            source_url=page.url,
            markdown=markdown,
            mermaid_diagrams=mermaid_diagrams,
            image_paths=image_paths,
            test_cases_detected=test_cases,
            parsed_at=datetime.now(UTC),
        )

        return StageResult(
            success=True, data=parsed, errors=[], warnings=warnings, confidence=confidence
        )

    async def parse_multiple(self, pages: list[ConfluencePage]) -> StageResult:
        all_warnings: list[str] = []
        all_errors: list[str] = []
        parsed_pages = []
        confidences = []

        for page in pages:
            res = await self.parse(page)
            if res.success and res.data:
                parsed_pages.append(res.data)
                all_warnings.extend(res.warnings)
                confidences.append(res.confidence if res.confidence is not None else 0.0)
            else:
                all_warnings.extend(res.warnings)
                all_errors.extend(res.errors)
                confidences.append(0.0)  # failed pages drag down overall confidence

        if not parsed_pages:
            return StageResult(
                success=False,
                data=None,
                errors=all_errors or ["All pages failed to parse"],
                warnings=all_warnings,
                confidence=0.0,
            )

        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return StageResult(
            success=True,
            data=parsed_pages,
            errors=[],
            warnings=all_warnings,
            confidence=overall_confidence,
        )

    def _html_to_markdown(self, html: str) -> str:
        # Annotated because markdownify ships no type stubs (its return is Any);
        # the annotation keeps mypy from reporting a no-any-return on md.strip().
        md: str = markdownify.markdownify(html, heading_style="ATX", escape_asterisks=False)
        md = MULTIPLE_BLANK_LINES.sub("\n\n", md)
        return md.strip()

    def _handle_confluence_macros(
        self, html: str, warnings: list[str], code_blocks: dict[str, str]
    ) -> str:
        # info + note macros → ℹ️ Note blockquote (spec groups them as equivalent)
        html = re.sub(
            r'<ac:structured-macro.*?ac:name="(?:info|note)".*?><ac:rich-text-body>(.*?)</ac:rich-text-body></ac:structured-macro>',
            r"<blockquote><strong>ℹ️ Note:</strong> \1</blockquote>",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        html = re.sub(
            r'<ac:structured-macro.*?ac:name="warning".*?><ac:rich-text-body>(.*?)</ac:rich-text-body></ac:structured-macro>',
            r"<blockquote><strong>⚠️ Warning:</strong> \1</blockquote>",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        html = re.sub(
            r'<ac:structured-macro.*?ac:name="tip".*?><ac:rich-text-body>(.*?)</ac:rich-text-body></ac:structured-macro>',
            r"<blockquote><strong>💡 Tip:</strong> \1</blockquote>",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        # panel macro → section heading + content
        html = re.sub(
            r'<ac:structured-macro.*?ac:name="panel".*?><ac:rich-text-body>(.*?)</ac:rich-text-body></ac:structured-macro>',
            r"<section>\1</section>",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )

        def replace_code_macro(match: re.Match[str]) -> str:
            full_macro = match.group(0)
            lang_match = re.search(
                r'<ac:parameter ac:name="language">(.*?)</ac:parameter>', full_macro
            )
            lang = lang_match.group(1) if lang_match else ""
            body_match = re.search(
                r"<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>",
                full_macro,
                re.DOTALL,
            )
            body = body_match.group(1) if body_match else ""
            if body.startswith("\n"):
                body = body[1:]

            placeholder = f"CODEBLOCKPLACEHOLDER{len(code_blocks)}MAGIC"
            code_blocks[placeholder] = f"```{lang}\n{body}\n```"
            return f"<p>{placeholder}</p>"

        html = re.sub(
            r'<ac:structured-macro.*?ac:name="code".*?>.*?</ac:structured-macro>',
            replace_code_macro,
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )

        html = re.sub(
            r'<ac:structured-macro.*?ac:name="expand".*?><ac:rich-text-body>(.*?)</ac:rich-text-body></ac:structured-macro>',
            r"\1",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )

        if 'ac:name="gliffy"' in html:
            warnings.append(
                "Gliffy diagram detected but cannot be converted to Mermaid automatically — manual review recommended"
            )

        return html

    def _extract_mermaid(self, html: str, warnings: list[str]) -> list[str]:
        mermaids = []
        for m in MERMAID_BLOCK_PATTERN.finditer(html):
            mermaids.append(m.group(1).strip())

        for m in re.finditer(
            r'<ac:structured-macro.*?ac:name="drawio".*?><ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>',
            html,
            re.DOTALL | re.IGNORECASE,
        ):
            xml_content = m.group(1)
            mermaid_lines = ["flowchart TD"]
            nodes = {}
            for node_m in re.finditer(
                r'<mxCell\s+id="([^"]+)"\s+value="([^"]*)"\s+style="([^"]*)"[^>]*vertex="1"',
                xml_content,
            ):
                nid, label, style = node_m.groups()
                # Escape chars that break Mermaid node syntax
                safe_label = label.replace("[", "(").replace("]", ")").replace(">", "≥")
                if "ellipse" in style:
                    nodes[nid] = f"{nid}([{safe_label}])"
                elif "rounded=1" in style:
                    nodes[nid] = f"{nid}({safe_label})"
                else:
                    nodes[nid] = f"{nid}[{safe_label}]"

            for edge_m in re.finditer(
                r'<mxCell\s+id="[^"]*"\s+edge="1"\s+(?:parent="[^"]*"\s+)*source="([^"]+)"\s+target="([^"]+)"',
                xml_content,
            ):
                src, tgt = edge_m.groups()
                if src in nodes and tgt in nodes:
                    mermaid_lines.append(f"    {src} --> {tgt}")

            if nodes:
                mermaids.append("\n".join(mermaid_lines))
            else:
                warnings.append("Draw.io diagram too complex to auto-convert to Mermaid")
                # Spec: add placeholder Mermaid block so downstream consumers have something
                mermaids.append(
                    'flowchart TD\n    A[Diagram could not be auto-converted]\n    note["See original Confluence page"]'
                )

        for m in re.finditer(
            r'<ac:structured-macro.*?ac:name="plantuml".*?><ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>',
            html,
            re.DOTALL | re.IGNORECASE,
        ):
            body = m.group(1)
            # Convention: PlantUML blocks are prefixed with "%% PlantUML original format"
            # so downstream consumers can detect them without a separate type field.
            mermaids.append(f"%% PlantUML original format\n{body}")

        return mermaids

    async def _save_images(self, page: ConfluencePage, html: str, warnings: list[str]) -> list[str]:
        image_paths: list[str] = []
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", page.title).strip("-").lower()

        img_urls = []
        for m in re.finditer(r'<img[^>]+src="([^"]+)"', html):
            raw_url = m.group(1)
            # Handle relative URLs: prepend ConfluencePage.url base
            if not raw_url.startswith("http"):
                base = page.url.rstrip("/")
                raw_url = f"{base}/{raw_url.lstrip('/')}"
            img_urls.append(raw_url)

        if not img_urls:
            return image_paths

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            for i, url in enumerate(img_urls):
                filename = url.split("/")[-1]
                if "?" in filename:
                    filename = filename.split("?")[0]
                if not filename:
                    filename = f"image_{i}.png"

                # Use adapter to save image
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()

                    # Dedup filename across artifacts could be done by adapter if necessary,
                    # but here we just prepend slug to the artifact name
                    artifact_name = f"{slug}/images/{filename}"
                    self.adapter.save_image(artifact_name, resp.content)

                    image_paths.append(artifact_name)
                except httpx.HTTPError as e:
                    warnings.append(f"HTTPError fetching image {filename}: {e}")
                except Exception as e:
                    warnings.append(f"Error saving image {filename}: {e}")

        return image_paths

    def _extract_test_cases(self, markdown: str) -> list[dict[str, Any]]:
        test_cases = []

        for m in TEST_CASE_HEADING_PATTERN.finditer(markdown):
            title = m.group(1).strip()
            body = m.group(2)
            tc = self._parse_tc_body(title, body)
            test_cases.append(tc)

        if not test_cases:
            for m in TEST_CASE_NUMBERED_PATTERN.finditer(markdown):
                title = m.group(1).strip()
                body = m.group(2)
                tc = self._parse_tc_body(title, body)
                test_cases.append(tc)

        # Table-format detection only runs when no heading/numbered TCs found
        # (avoids duplicate entries in mixed-format documents)
        if not test_cases:
            for m in re.finditer(r"(?:\|.*\|(?:\n|$))+", markdown):
                table = m.group(0).strip()
                rows = table.split("\n")
                if (
                    len(rows) >= 3
                    and "step" in rows[0].lower()
                    and "action" in rows[0].lower()
                    and "expected" in rows[0].lower()
                ):
                    steps = []
                    expected = []
                    for row in rows[2:]:
                        cols = [c.strip() for c in row.split("|")[1:-1]]
                        if len(cols) >= 3 and cols[1]:
                            steps.append(cols[1])
                            expected.append(cols[2])
                    if steps or expected:
                        tc = {
                            "title": "Table Test Case",
                            "preconditions": [],
                            "steps": steps,
                            "expected_results": expected,
                        }
                        test_cases.append(tc)

        return test_cases

    def _parse_tc_body(self, title: str, body: str) -> dict[str, Any]:
        preconditions = []
        steps = []
        expected_results = []

        pm = PRECONDITIONS_PATTERN.search(body)
        if pm:
            preconditions.append(pm.group(1).strip())

        sm = STEPS_PATTERN.search(body)
        if sm:
            step_lines = sm.group(1).strip().split("\n")
            for line in step_lines:
                clean_line = re.sub(r"^\d+\.\s*", "", line).strip()
                if clean_line:
                    steps.append(clean_line)

        em = EXPECTED_RESULT_PATTERN.search(body)
        if em:
            expected_results.append(em.group(1).strip())

        return {
            "title": title,
            "preconditions": preconditions,
            "steps": steps,
            "expected_results": expected_results,
        }

    def _compute_confidence(self, page: ConfluencePage, warnings: list[str], md: str) -> float:
        """Score parse quality. 1.0=full, 0.8=minor issues, 0.5=significant, 0.3=mostly unparseable."""
        warning_count = len(warnings)
        if warning_count >= 5:
            return 0.3
        if warning_count >= 2:
            return 0.5
        if warning_count >= 1:
            return 0.8
        return 1.0
