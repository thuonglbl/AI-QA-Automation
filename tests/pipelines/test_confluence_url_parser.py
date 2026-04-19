"""Tests for Confluence URL parser.

Tests various Confluence URL formats and edge cases.
"""

import pytest

from ai_qa.pipelines.confluence_reader import ConfluenceURLParser


class TestConfluenceURLParser:
    """Test suite for ConfluenceURLParser."""

    # Cloud format URLs
    CLOUD_URLS = [
        (
            "https://company.atlassian.net/wiki/spaces/TEST/pages/123456/Page+Title",
            "123456",
            "TEST",
        ),
        ("https://company.atlassian.net/wiki/spaces/PROJ/pages/987654321", "987654321", "PROJ"),
        ("https://myworkspace.atlassian.net/wiki/spaces/DEV/pages/111222", "111222", "DEV"),
    ]

    # Server format URLs
    SERVER_URLS = [
        ("https://confluence.company.com/display/TEST/Page+Title", None, "TEST"),
        ("https://wiki.company.com/display/PROJ/Documentation", None, "PROJ"),
    ]

    # Server format with pageId parameter
    SERVER_PAGEID_URLS = [
        ("https://confluence.company.com/pages/viewpage.action?pageId=123456", "123456", None),
        (
            "https://wiki.company.com/pages/viewpage.action?pageId=987654&spaceKey=TEST",
            "987654",
            "TEST",
        ),
    ]

    @pytest.mark.parametrize("url,expected_page_id,expected_space", CLOUD_URLS)
    def test_extract_page_id_cloud_format(
        self, url: str, expected_page_id: str, expected_space: str
    ) -> None:
        """Test extracting page ID from cloud format URLs."""
        parser = ConfluenceURLParser()
        page_id = parser.extract_page_id(url)
        assert page_id == expected_page_id

    @pytest.mark.parametrize("url,expected_page_id,expected_space", CLOUD_URLS)
    def test_extract_space_key_cloud_format(
        self, url: str, expected_page_id: str, expected_space: str
    ) -> None:
        """Test extracting space key from cloud format URLs."""
        parser = ConfluenceURLParser()
        space_key = parser.extract_space_key(url)
        assert space_key == expected_space

    @pytest.mark.parametrize("url,expected_page_id,expected_space", SERVER_URLS)
    def test_extract_space_key_server_display(
        self, url: str, expected_page_id: str, expected_space: str
    ) -> None:
        """Test extracting space key from server display URLs."""
        parser = ConfluenceURLParser()
        space_key = parser.extract_space_key(url)
        assert space_key == expected_space

    @pytest.mark.parametrize("url,expected_page_id,expected_space", SERVER_PAGEID_URLS)
    def test_extract_page_id_server_pageid(
        self, url: str, expected_page_id: str, expected_space: str
    ) -> None:
        """Test extracting page ID from server URLs with pageId parameter."""
        parser = ConfluenceURLParser()
        page_id = parser.extract_page_id(url)
        assert page_id == expected_page_id

    def test_extract_page_id_invalid_url(self) -> None:
        """Test extracting page ID from invalid URLs."""
        parser = ConfluenceURLParser()
        assert parser.extract_page_id("") is None
        assert parser.extract_page_id("not-a-url") is None
        assert parser.extract_page_id("ftp://invalid.com/page") is None

    def test_extract_space_key_invalid_url(self) -> None:
        """Test extracting space key from invalid URLs."""
        parser = ConfluenceURLParser()
        assert parser.extract_space_key("") is None
        assert parser.extract_space_key("not-a-url") is None
        assert parser.extract_space_key("https://example.com/some-page") is None

    def test_normalize_url(self) -> None:
        """Test URL normalization."""
        parser = ConfluenceURLParser()

        # Remove trailing slashes
        assert (
            parser.normalize_url("https://confluence.company.com/path/")
            == "https://confluence.company.com/path"
        )

        # Keep path structure
        assert (
            parser.normalize_url("https://confluence.company.com/display/TEST/Page")
            == "https://confluence.company.com/display/TEST/Page"
        )

        # Empty URL handling
        assert parser.normalize_url("") == ""

    def test_is_valid_confluence_url_valid(self) -> None:
        """Test valid Confluence URL detection."""
        parser = ConfluenceURLParser()

        valid_urls = [
            "https://company.atlassian.net/wiki/spaces/TEST/pages/123456",
            "https://confluence.company.com/display/TEST/Page",
            "https://confluence.company.com/pages/viewpage.action?pageId=123",
            "https://wiki.company.com/confluence/display/SPACE/Page",
        ]

        for url in valid_urls:
            assert parser.is_valid_confluence_url(url) is True, f"Should be valid: {url}"

    def test_is_valid_confluence_url_invalid(self) -> None:
        """Test invalid Confluence URL detection."""
        parser = ConfluenceURLParser()

        invalid_urls = [
            "",
            "not-a-url",
            "ftp://invalid.com/page",
            "https://example.com/some-page",
            "https://google.com/search",
        ]

        for url in invalid_urls:
            assert parser.is_valid_confluence_url(url) is False, f"Should be invalid: {url}"

    def test_url_parser_edge_cases(self) -> None:
        """Test URL parser edge cases."""
        parser = ConfluenceURLParser()

        # URL with special characters
        url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123456/Page+With+Spaces"
        assert parser.extract_page_id(url) == "123456"
        assert parser.extract_space_key(url) == "TEST"

        # URL with query parameters
        url = "https://confluence.company.com/pages/viewpage.action?pageId=123456&spaceKey=TEST&action=view"
        assert parser.extract_page_id(url) == "123456"
        assert parser.extract_space_key(url) == "TEST"

        # URL with fragment
        url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123456#section"
        assert parser.extract_page_id(url) == "123456"
