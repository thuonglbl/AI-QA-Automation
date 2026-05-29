from unittest.mock import AsyncMock

import pytest

from ai_qa.models import StageResult
from ai_qa.pipelines.confluence_reader import ConfluenceReader


@pytest.fixture
def mock_mcp_client():
    client = AsyncMock()
    client.is_connected = True
    client._settings = AsyncMock()
    client._settings.mcp_tool_prefix = ""
    return client


@pytest.fixture
def reader(mock_mcp_client):
    return ConfluenceReader(mock_mcp_client, confluence_base_url="https://test.atlassian.net")


def test_is_requirement_title(reader):
    """Test the title matcher correctly identifies requirement-related titles."""
    assert reader._is_requirement_title("System Requirements") is True
    assert reader._is_requirement_title("Project Spec") is True
    assert reader._is_requirement_title("FR - Login Feature") is True
    assert reader._is_requirement_title("functional requirement") is True
    # Negative cases
    assert reader._is_requirement_title("Project Plan") is False
    assert reader._is_requirement_title("Meeting Notes") is False
    assert reader._is_requirement_title("Friday Update") is False  # 'fr' is not isolated


@pytest.mark.asyncio
async def test_find_parent_pages_matches_requirement_title(reader, mock_mcp_client):
    """Test find_parent_pages parses the MCP result and returns PageSummary objects."""
    # Mock search result containing a requirement page
    mock_mcp_client.call_tool.return_value = StageResult(
        success=True,
        data={
            "results": [
                {
                    "id": "123",
                    "title": "System Requirements",
                    "_links": {"webui": "/spaces/TEST/pages/123/Requirements"},
                },
                {
                    "id": "456",
                    "title": "Unrelated Page",
                    "_links": {"webui": "/spaces/TEST/pages/456/Unrelated"},
                },
            ]
        },
        errors=[],
        warnings=[],
        confidence=1.0,
    )

    result = await reader.find_parent_pages("TEST")

    assert result.success is True
    assert len(result.data) == 1

    summary = result.data[0]
    assert summary.page_id == "123"
    assert summary.title == "System Requirements"
    assert summary.url == "https://test.atlassian.net/spaces/TEST/pages/123/Requirements"


@pytest.mark.asyncio
async def test_find_requirement_page_by_parent_id(reader, mock_mcp_client):
    """Test find_requirement_page_by_parent_id returns the first valid requirement page."""
    mock_mcp_client.call_tool.return_value = StageResult(
        success=True,
        data={
            "results": [
                {
                    "id": "999",
                    "title": "Technical Spec",
                    "_links": {"webui": "/spaces/TEST/pages/999/Spec"},
                }
            ]
        },
        errors=[],
        warnings=[],
        confidence=1.0,
    )

    result = await reader.find_requirement_page_by_parent_id("111")

    assert result.success is True
    assert result.data is not None
    assert result.data.page_id == "999"
    assert result.data.title == "Technical Spec"
    assert result.data.url == "https://test.atlassian.net/spaces/TEST/pages/999/Spec"
