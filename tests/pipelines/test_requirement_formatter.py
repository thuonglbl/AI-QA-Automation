"""Tests for RequirementFormatter."""

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
async def test_caption_image_vision_failure(mock_llm_client):
    """Test that vision failure doesn't crash the pipeline."""
    mock_llm_client.invoke_vision.side_effect = Exception("Vision API down")
    formatter = RequirementFormatter(mock_llm_client)

    result = await formatter._caption_image(b"fake data", "test.png")
    assert result == "Image could not be captioned"
