from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ai_qa.pipelines.content_parser import ContentParser
from ai_qa.pipelines.models import ConfluencePage, ParsedContent


@pytest.fixture
def mock_output_dir(tmp_path: Path) -> Path:
    base_dir = tmp_path / "workspace" / "requirements"
    base_dir.mkdir(parents=True)
    return base_dir


@pytest.fixture
def mock_adapter(mock_output_dir: Path) -> MagicMock:
    adapter = MagicMock()

    def mock_save_image(artifact_name, content):
        path = mock_output_dir / artifact_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    adapter.save_image.side_effect = mock_save_image
    return adapter


@pytest.fixture
def test_page() -> ConfluencePage:
    return ConfluencePage(
        page_id="123",
        title="Test Page",
        content="<p>Hello world</p>",
        space_key="TEST",
        url="http://confluence/123",
        retrieved_at=datetime.now(UTC),
        labels=[],
    )


@pytest.mark.asyncio
async def test_parse_plain_html_returns_markdown(
    mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    test_page.content = "<h1>Title</h1><p>Some text</p>"
    parser = ContentParser(mock_adapter)
    result = await parser.parse(test_page)

    assert result.success
    assert isinstance(result.data, ParsedContent)
    assert "# Title" in result.data.markdown
    assert "Some text" in result.data.markdown


@pytest.mark.asyncio
async def test_parse_already_markdown_content_passes_through(
    mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    test_page.content = "# Already Markdown\nWith some text."
    parser = ContentParser(mock_adapter)
    result = await parser.parse(test_page)

    assert result.success
    assert result.data is not None
    assert "# Already Markdown" in result.data.markdown


@pytest.mark.asyncio
async def test_parse_empty_content_returns_warning_not_error(
    mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    test_page.content = ""
    parser = ContentParser(mock_adapter)
    result = await parser.parse(test_page)

    assert result.success
    assert result.data is not None
    assert result.data.markdown == ""
    assert any("no content" in w.lower() for w in result.warnings)
    assert result.confidence == 0.5


@pytest.mark.asyncio
async def test_parse_confluence_info_macro_converted_to_blockquote(
    mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    test_page.content = '<ac:structured-macro ac:name="info"><ac:rich-text-body><p>Some info text</p></ac:rich-text-body></ac:structured-macro>'
    parser = ContentParser(mock_adapter)
    result = await parser.parse(test_page)

    assert result.success
    assert result.data is not None
    assert "> **ℹ️ Note:**" in result.data.markdown
    assert "Some info text" in result.data.markdown


@pytest.mark.asyncio
async def test_parse_confluence_code_macro_converted_to_fenced_block(
    mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    test_page.content = '<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">python</ac:parameter><ac:plain-text-body><![CDATA[def hello():\n    pass]]></ac:plain-text-body></ac:structured-macro>'
    parser = ContentParser(mock_adapter)
    result = await parser.parse(test_page)

    assert result.success
    assert result.data is not None
    assert "```python\ndef hello():\n    pass\n```" in result.data.markdown


@pytest.mark.asyncio
async def test_parse_table_preserved_as_markdown_table(
    mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    test_page.content = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
    parser = ContentParser(mock_adapter)
    result = await parser.parse(test_page)

    assert result.success
    assert result.data is not None
    assert "| A | B |" in result.data.markdown
    assert "| 1 | 2 |" in result.data.markdown


@pytest.mark.asyncio
async def test_mermaid_existing_block_extracted_as_is(
    mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    test_page.content = "<p>Here is a diagram:</p>\n```mermaid\ngraph TD\nA-->B\n```"
    parser = ContentParser(mock_adapter)
    result = await parser.parse(test_page)

    assert result.success
    assert result.data is not None
    assert len(result.data.mermaid_diagrams) == 1
    assert "graph TD" in result.data.mermaid_diagrams[0]


@pytest.mark.asyncio
async def test_mermaid_gliffy_macro_adds_warning(
    mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    test_page.content = '<ac:structured-macro ac:name="gliffy"></ac:structured-macro>'
    parser = ContentParser(mock_adapter)
    result = await parser.parse(test_page)

    assert result.success
    assert any("gliffy" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_mermaid_drawio_simple_flowchart_converted(
    mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    test_page.content = '<ac:structured-macro ac:name="drawio"><ac:plain-text-body><![CDATA[<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/><mxCell id="2" value="Node A" style="ellipse" vertex="1" parent="1"/><mxCell id="3" value="Node B" style="rounded=1" vertex="1" parent="1"/><mxCell id="4" edge="1" parent="1" source="2" target="3"/></root></mxGraphModel>]]></ac:plain-text-body></ac:structured-macro>'
    parser = ContentParser(mock_adapter)
    result = await parser.parse(test_page)

    assert result.success
    assert result.data is not None
    assert len(result.data.mermaid_diagrams) == 1
    assert "flowchart TD" in result.data.mermaid_diagrams[0]


@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_image_save_happy_path(
    mock_get: AsyncMock, mock_output_dir: Path, mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.content = b"fakeimagecontent"
    mock_get.return_value = mock_response

    test_page.content = '<img src="http://confluence/images/test.png" />'
    parser = ContentParser(mock_adapter)
    result = await parser.parse(test_page)

    assert result.success
    assert result.data is not None
    assert len(result.data.image_paths) == 1
    expected_path = Path("test-page/images/test.png")

    assert expected_path.as_posix() in result.data.image_paths

    # Check that file was actually written
    full_path = mock_output_dir / "test-page" / "images" / "test.png"
    assert full_path.exists()
    assert full_path.read_bytes() == b"fakeimagecontent"


@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_image_save_http_error_adds_warning_continues(
    mock_get: AsyncMock, mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    mock_get.side_effect = httpx.HTTPError("Failed to fetch")

    test_page.content = '<img src="http://confluence/images/fail.png" /><p>Some text</p>'
    parser = ContentParser(mock_adapter)
    result = await parser.parse(test_page)

    assert result.success
    assert result.data is not None
    assert len(result.data.image_paths) == 0
    assert any("fail.png" in w for w in result.warnings)
    assert "Some text" in result.data.markdown


@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
@patch("pathlib.Path.write_bytes")
async def test_image_save_filesystem_error_adds_warning_continues(
    mock_write: MagicMock, mock_get: AsyncMock, mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.content = b"fakeimagecontent"
    mock_get.return_value = mock_response

    mock_write.side_effect = OSError("Permission denied")

    test_page.content = '<img src="http://confluence/images/test.png" />'
    parser = ContentParser(mock_adapter)
    result = await parser.parse(test_page)

    assert result.success
    assert result.data is not None
    assert len(result.data.image_paths) == 0
    assert any("permission" in w.lower() or "oserror" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_test_case_detection_heading_pattern(
    mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    test_page.content = "## TC-001 Title\nPreconditions: User logged in\nSteps:\n1. Do this\n2. Do that\nExpected Result: Success\n"
    parser = ContentParser(mock_adapter)
    result = await parser.parse(test_page)

    assert result.success
    assert result.data is not None
    assert len(result.data.test_cases_detected) == 1
    tc = result.data.test_cases_detected[0]
    assert "TC-001 Title" in tc["title"]
    assert "User logged in" in tc["preconditions"][0]
    assert len(tc["steps"]) == 2
    assert "Success" in tc["expected_results"][0]


@pytest.mark.asyncio
async def test_test_case_detection_table_pattern(
    mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    test_page.content = "<table><tr><th>Step</th><th>Action</th><th>Expected Result</th></tr><tr><td>1</td><td>Click login</td><td>Form submits</td></tr></table>"
    parser = ContentParser(mock_adapter)
    result = await parser.parse(test_page)

    assert result.success
    assert result.data is not None
    assert len(result.data.test_cases_detected) == 1
    tc = result.data.test_cases_detected[0]
    assert tc["steps"] == ["Click login"]
    assert tc["expected_results"] == ["Form submits"]


@pytest.mark.asyncio
async def test_test_case_detection_numbered_pattern(
    mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    test_page.content = "Test Case: Login\nPreconditions: None\nSteps:\n1. Enter username\nExpected Result: Logged in"
    parser = ContentParser(mock_adapter)
    result = await parser.parse(test_page)

    assert result.success
    assert result.data is not None
    assert len(result.data.test_cases_detected) == 1
    tc = result.data.test_cases_detected[0]
    assert "Login" in tc["title"]
    assert "Enter username" in tc["steps"][0]


@pytest.mark.asyncio
async def test_parse_multiple_pages_returns_list(
    mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    page1 = test_page
    page2 = test_page.model_copy()
    page2.page_id = "456"

    parser = ContentParser(mock_adapter)
    result = await parser.parse_multiple([page1, page2])

    assert result.success
    assert isinstance(result.data, list)
    assert len(result.data) == 2


@pytest.mark.asyncio
async def test_parse_multiple_pages_partial_failure_adds_warnings(
    mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    page1 = test_page
    page2 = test_page.model_copy()
    page2.content = '<ac:structured-macro ac:name="gliffy"></ac:structured-macro>'

    parser = ContentParser(mock_adapter)
    result = await parser.parse_multiple([page1, page2])

    assert result.success
    assert result.data is not None
    assert len(result.data) == 2
    assert len(result.warnings) > 0


@pytest.mark.asyncio
async def test_stage_result_confidence_scoring(
    mock_adapter: MagicMock, test_page: ConfluencePage
) -> None:
    test_page.content = "<p>Standard text</p>"
    parser = ContentParser(mock_adapter)

    result = await parser.parse(test_page)
    assert result.success
    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_no_llm_calls_made(mock_adapter: MagicMock, test_page: ConfluencePage) -> None:
    # Just asserting that we don't import or use LLM providers
    # In practice, ContentParser itself has no LLM instances inside
    with patch("httpx.AsyncClient.post") as mock_post:
        parser = ContentParser(mock_adapter)
        await parser.parse(test_page)
        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# Story 11.3 — RequirementFormatter.convert_markdown (no image re-fetch)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_convert_markdown_calls_format_story_without_image_refetch() -> None:
    """Task 6.6: convert_markdown feeds markdown to _format_story; no httpx client opened."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock, MagicMock, patch

    from ai_qa.ai_connection.client import LLMClient
    from ai_qa.pipelines.requirement_formatter import RequirementFormatter

    mock_llm = MagicMock(spec=LLMClient)
    mock_response = MagicMock()
    mock_response.content = "# Formatted Story"
    mock_llm._chat_model = MagicMock()
    mock_llm._chat_model.ainvoke = AsyncMock(return_value=mock_response)

    formatter = RequirementFormatter(mock_llm)

    page = ConfluencePage(
        page_id="p1",
        title="My Page",
        content="<p>Original HTML — must NOT be re-parsed</p>",
        space_key="TEST",
        url="https://confluence.example.com/p1",
        retrieved_at=datetime.now(UTC),
        labels=[],
    )
    clean_md = "# My Page\n\n| Col A | Col B |\n| --- | --- |\n| 1 | 2 |"

    with patch("httpx.AsyncClient") as mock_httpx:
        result = await formatter.convert_markdown(page, clean_md)

    # No httpx client was instantiated — images must not be re-fetched
    mock_httpx.assert_not_called()

    # The LLM was invoked exactly once (via _format_story)
    mock_llm._chat_model.ainvoke.assert_called_once()

    assert result == "# Formatted Story"
