"""Tests for RequirementFormatter."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_qa.ai_connection.client import LLMClient
from ai_qa.pipelines.models import ConfluencePage
from ai_qa.pipelines.requirement_formatter import RequirementFormatter


@pytest.fixture
def mock_llm_client():
    client = MagicMock(spec=LLMClient)
    client.invoke_vision = AsyncMock(return_value="A test image caption.")

    chat_mock = MagicMock()
    # Mocking the HumanMessage response
    resp_mock = MagicMock()
    resp_mock.content = "Story content based on page."
    chat_mock.ainvoke = AsyncMock(return_value=resp_mock)
    client._chat_model = chat_mock
    return client


@pytest.mark.asyncio
async def test_convert_page_with_images(mock_llm_client):
    """Test convert_page converts HTML, fetches images, and formats story."""
    formatter = RequirementFormatter(mock_llm_client)

    html_content = """
    <h1>Test Page</h1>
    <p>This is a requirement.</p>
    <img src="http://example.com/img.png" alt="Test Image">
    <img src="/relative/img2.png" alt="Test Image 2">
    """

    page = ConfluencePage(
        page_id="123",
        title="Test Requirements",
        content=html_content,
        url="http://example.com/page",
        space_key="TST",
    )

    # Mock httpx.AsyncClient
    class MockResponse:
        def __init__(self, content):
            self.content = content

        def raise_for_status(self):
            pass

    async def mock_get(url):
        if "img.png" in url or "img2.png" in url:
            return MockResponse(b"fake image data")
        raise Exception("Not found")

    mock_client_instance = AsyncMock()
    mock_client_instance.get = AsyncMock(side_effect=mock_get)

    class MockClientContext:
        async def __aenter__(self):
            return mock_client_instance

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("httpx.AsyncClient", return_value=MockClientContext()):
        result = await formatter.convert_page(page)

    assert result == "Story content based on page."
    assert mock_llm_client.invoke_vision.call_count == 2
    mock_llm_client._chat_model.ainvoke.assert_called_once()

    # Check that prompt has the captions
    call_args = mock_llm_client._chat_model.ainvoke.call_args[0][0]
    prompt = call_args[0].content
    assert "[Image: A test image caption.]" in prompt
    assert "# Test Page" in prompt


@pytest.mark.asyncio
async def test_convert_page_image_fetch_failure(mock_llm_client):
    """Test convert_page handles image fetching errors gracefully."""
    formatter = RequirementFormatter(mock_llm_client)

    html_content = """
    <h1>Test Page</h1>
    <img src="http://example.com/bad.png">
    """

    page = ConfluencePage(
        page_id="123",
        title="Test Requirements",
        content=html_content,
        url="http://example.com/page",
        space_key="TST",
    )

    class MockClientContext:
        async def __aenter__(self):
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Network error"))
            return mock_client

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("httpx.AsyncClient", return_value=MockClientContext()):
        result = await formatter.convert_page(page)

    assert result == "Story content based on page."
    assert mock_llm_client.invoke_vision.call_count == 0

    call_args = mock_llm_client._chat_model.ainvoke.call_args[0][0]
    prompt = call_args[0].content
    assert "[Image: Image could not be processed]" in prompt


@pytest.mark.asyncio
async def test_caption_image_vision_failure_returns_empty(mock_llm_client):
    """Vision failure doesn't crash; returns '' so the caller can fall back to alt text."""
    mock_llm_client.invoke_vision.side_effect = Exception("Vision API down")
    formatter = RequirementFormatter(mock_llm_client)

    result = await formatter._caption_image(b"fake data", "test.png", "image/png")
    assert result == ""


# A PNG magic-byte header so _sniff_image_mime + content-type checks treat it as a real image.
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"rest"


def _mock_httpx(content=_PNG_BYTES, content_type="image/png", status=200, raise_exc=None):
    """Return (ctx, calls) where calls records (url, headers) of each get."""
    calls: list[tuple[str, dict]] = []

    class MockResponse:
        def __init__(self):
            self.content = content
            self.headers = {"content-type": content_type}
            self.status_code = status

        def raise_for_status(self):
            pass

    async def mock_get(url, headers=None):
        calls.append((url, headers or {}))
        if raise_exc is not None:
            raise raise_exc
        return MockResponse()

    client = AsyncMock()
    client.get = AsyncMock(side_effect=mock_get)

    class Ctx:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *a):
            pass

    return Ctx(), calls


@pytest.mark.asyncio
async def test_caption_images_in_markdown_replaces_with_uri_and_caption(mock_llm_client):
    """Embedded ![alt](src) becomes [Image: {caption}]({uri}) — no broken <img>."""
    formatter = RequirementFormatter(mock_llm_client)
    page = ConfluencePage(
        page_id="1", title="T", content="", url="https://c.example/pages/1", space_key="TST"
    )
    md = "Intro\n\n![Dashboard](https://c.example/img/dash.png)\n\nMore"

    ctx, _ = _mock_httpx()
    with patch("httpx.AsyncClient", return_value=ctx):
        out = await formatter.caption_images_in_markdown(page, md)

    assert "![Dashboard]" not in out  # no broken embedded image survives
    assert "[Image: A test image caption.](https://c.example/img/dash.png)" in out
    assert mock_llm_client.invoke_vision.call_count == 1


@pytest.mark.asyncio
async def test_caption_images_in_markdown_no_images_is_passthrough(mock_llm_client):
    """No images → returned unchanged, no network/vision calls."""
    formatter = RequirementFormatter(mock_llm_client)
    page = ConfluencePage(
        page_id="1", title="T", content="", url="https://c.example/pages/1", space_key="TST"
    )
    md = "Just text, no images."
    out = await formatter.caption_images_in_markdown(page, md)
    assert out == md
    assert mock_llm_client.invoke_vision.call_count == 0


@pytest.mark.asyncio
async def test_caption_images_in_markdown_resolves_relative_src(mock_llm_client):
    """A relative image src resolves against the SITE ROOT (not the page path)."""
    formatter = RequirementFormatter(mock_llm_client)
    page = ConfluencePage(
        page_id="1", title="T", content="", url="https://c.example/pages/1", space_key="TST"
    )
    md = "![x](/download/attachments/9/a.png)"

    ctx, calls = _mock_httpx()
    with patch("httpx.AsyncClient", return_value=ctx):
        out = await formatter.caption_images_in_markdown(page, md)

    assert calls[0][0] == "https://c.example/download/attachments/9/a.png"
    assert "[Image: A test image caption.](https://c.example/download/attachments/9/a.png)" in out


@pytest.mark.asyncio
async def test_caption_images_in_markdown_fetch_failure_falls_back_to_alt(mock_llm_client):
    """A fetch failure keeps the URI link and falls back to the alt text — no broken img."""
    formatter = RequirementFormatter(mock_llm_client)
    page = ConfluencePage(
        page_id="1", title="T", content="", url="https://c.example/pages/1", space_key="TST"
    )
    md = "![Dashboard overview](https://c.example/img/broken.png)"

    ctx, _ = _mock_httpx(raise_exc=Exception("boom"))
    with patch("httpx.AsyncClient", return_value=ctx):
        out = await formatter.caption_images_in_markdown(page, md)

    assert out == "[Image: Dashboard overview](https://c.example/img/broken.png)"
    assert mock_llm_client.invoke_vision.call_count == 0


@pytest.mark.asyncio
async def test_caption_images_in_markdown_skips_non_image_content_type(mock_llm_client):
    """A login-page HTML (or any non-image) response is NOT sent to the vision model."""
    formatter = RequirementFormatter(mock_llm_client)
    page = ConfluencePage(
        page_id="1", title="T", content="", url="https://c.example/pages/1", space_key="TST"
    )
    md = "![Login required](https://c.example/img/x.png)"

    ctx, _ = _mock_httpx(content=b"<html>login</html>", content_type="text/html")
    with patch("httpx.AsyncClient", return_value=ctx):
        out = await formatter.caption_images_in_markdown(page, md)

    assert mock_llm_client.invoke_vision.call_count == 0  # never sent HTML to vision
    assert out == "[Image: Login required](https://c.example/img/x.png)"


@pytest.mark.asyncio
async def test_caption_images_falls_back_to_filename_when_no_caption_or_alt(mock_llm_client):
    """Empty alt + un-captionable image (e.g. SSO login HTML) → label from the filename."""
    formatter = RequirementFormatter(mock_llm_client)
    page = ConfluencePage(
        page_id="1", title="T", content="", url="https://c.example/pages/1", space_key="TST"
    )
    url = "https://c.example/download/attachments/9/EditJourney_Basis.png?api=v2"
    md = f"![]({url})"

    ctx, _ = _mock_httpx(content=b"<html>login</html>", content_type="text/html")
    with patch("httpx.AsyncClient", return_value=ctx):
        out = await formatter.caption_images_in_markdown(page, md)

    assert mock_llm_client.invoke_vision.call_count == 0
    assert out == f"[Image: EditJourney Basis]({url})"


@pytest.mark.asyncio
async def test_caption_images_sends_auth_only_to_confluence_host(mock_llm_client):
    """The PAT is attached for the Confluence host but never leaked to external hosts."""
    formatter = RequirementFormatter(mock_llm_client)
    page = ConfluencePage(
        page_id="1", title="T", content="", url="https://c.example/pages/1", space_key="TST"
    )
    md = "![internal](https://c.example/img/a.png)\n\n![external](https://evil.example/track.png)"

    ctx, calls = _mock_httpx()
    with patch("httpx.AsyncClient", return_value=ctx):
        await formatter.caption_images_in_markdown(page, md, auth_token="secret-pat")

    by_url = {url: headers for url, headers in calls}
    assert by_url["https://c.example/img/a.png"].get("Authorization") == "Bearer secret-pat"
    # External host must NOT receive the credential.
    assert "Authorization" not in by_url["https://evil.example/track.png"]


def test_absolutize_links_rewrites_relative_confluence_links(mock_llm_client):
    """Site-relative cross-page links get the Confluence host; absolute/anchor/mailto untouched."""
    formatter = RequirementFormatter(mock_llm_client)
    page = ConfluencePage(
        page_id="1",
        title="T",
        content="",
        url="https://confluence.svc.corp.ch/pages/1",
        space_key="TST",
    )
    md = (
        "See [US03](/spaces/EXPERTGROUP/pages/1252755298/US03+-+Advanced) and "
        "[ext](https://other.example/x) and [anchor](#section) and [mail](mailto:a@b.c)."
    )
    out = formatter._absolutize_links(page, md)

    assert (
        "[US03](https://confluence.svc.corp.ch/spaces/EXPERTGROUP/pages/1252755298/US03+-+Advanced)"
        in out
    )
    assert "[ext](https://other.example/x)" in out  # absolute link untouched
    assert "[anchor](#section)" in out  # in-page anchor untouched
    assert "[mail](mailto:a@b.c)" in out  # mailto untouched


def test_absolutize_links_noop_without_a_resolvable_host(mock_llm_client):
    """If page.url has no host, relative links are left as-is (nothing to resolve against)."""
    formatter = RequirementFormatter(mock_llm_client)
    page = ConfluencePage(page_id="1", title="T", content="", url="relative/only", space_key="TST")
    md = "[x](/spaces/Y/pages/1/Z)"
    assert formatter._absolutize_links(page, md) == md


@pytest.mark.asyncio
async def test_caption_images_uses_injected_fetcher(mock_llm_client):
    """When an image_fetcher is given, it supplies the bytes+mime (no HTTP) and the
    image is captioned via vision."""
    formatter = RequirementFormatter(mock_llm_client)
    page = ConfluencePage(
        page_id="1", title="T", content="", url="https://c.example/pages/1", space_key="TST"
    )
    url = "https://c.example/download/attachments/9/logo.png?api=v2"
    md = f"![]({url})"
    seen: list[str] = []

    async def fetcher(u: str):
        seen.append(u)
        return (_PNG_BYTES, "image/png")

    out = await formatter.caption_images_in_markdown(page, md, image_fetcher=fetcher)

    assert seen == [url]
    assert mock_llm_client.invoke_vision.call_count == 1
    assert out == f"[Image: A test image caption.]({url})"


@pytest.mark.asyncio
async def test_caption_images_fetcher_none_falls_back_to_filename(mock_llm_client):
    """If the fetcher can't resolve the image, degrade to a filename-derived label."""
    formatter = RequirementFormatter(mock_llm_client)
    page = ConfluencePage(
        page_id="1", title="T", content="", url="https://c.example/pages/1", space_key="TST"
    )
    url = "https://c.example/download/attachments/9/EditJourney_Basis.png"
    md = f"![]({url})"

    async def fetcher(_u: str):
        return None

    out = await formatter.caption_images_in_markdown(page, md, image_fetcher=fetcher)

    assert mock_llm_client.invoke_vision.call_count == 0
    assert out == f"[Image: EditJourney Basis]({url})"


@pytest.mark.asyncio
async def test_format_story_returns_content_within_timeout(mock_llm_client):
    """The timeout wrapper does not disturb a normal (fast) conversion."""
    formatter = RequirementFormatter(mock_llm_client)
    page = ConfluencePage(
        page_id="1", title="T", content="<p>x</p>", url="https://c.example/p", space_key="TST"
    )

    result = await formatter._format_story(page, "some requirement markdown")

    assert result == "Story content based on page."


@pytest.mark.asyncio
async def test_format_story_times_out_on_hung_llm(mock_llm_client, monkeypatch):
    """A hung provider call is bounded — it raises instead of stalling the step forever."""

    async def _hang(*_args, **_kwargs):
        await asyncio.sleep(5)
        return MagicMock(content="never")

    # Real coroutine fn so wait_for can cancel it deterministically on timeout.
    mock_llm_client._chat_model.ainvoke = _hang

    formatter = RequirementFormatter(mock_llm_client, timeout=0.05)
    page = ConfluencePage(
        page_id="1", title="T", content="<p>x</p>", url="https://c.example/p", space_key="TST"
    )

    with pytest.raises(TimeoutError):
        await formatter._format_story(page, "some requirement markdown")
