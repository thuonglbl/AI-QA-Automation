"""Unit tests for BrowserAgent."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_qa.browser.agent import BrowserAgent
from ai_qa.exceptions import BrowserError, NavigationError


@pytest.fixture
def mock_chrome_path(tmp_path: Path) -> str:
    """Create a mock Chrome executable path."""
    chrome_exe = tmp_path / "chrome.exe"
    chrome_exe.touch()
    return str(chrome_exe)


@pytest.fixture
def mock_browser_use_agent():
    """Mock browser-use Agent."""
    with patch("ai_qa.browser.agent.Agent") as mock:
        mock_agent = MagicMock()
        mock_agent.navigate = AsyncMock()
        mock.return_value = mock_agent
        yield mock


class TestBrowserAgentInitialization:
    """Tests for BrowserAgent initialization."""

    def test_init_with_valid_chrome_path(self, mock_chrome_path: str, mock_browser_use_agent):
        """Test BrowserAgent initialization with valid Chrome path."""
        agent = BrowserAgent(chrome_path=mock_chrome_path, timeout=30)
        assert agent.chrome_path == mock_chrome_path
        assert agent.timeout == 30
        mock_browser_use_agent.assert_called_once()

    def test_init_with_invalid_chrome_path_not_exists(self):
        """Test BrowserAgent initialization with non-existent Chrome path."""
        with pytest.raises(BrowserError, match="Chrome executable not found"):
            BrowserAgent(chrome_path="/nonexistent/chrome.exe")

    def test_init_with_invalid_chrome_path_is_directory(self, tmp_path: Path):
        """Test BrowserAgent initialization when Chrome path is a directory."""
        with pytest.raises(BrowserError, match="Chrome path is not a file"):
            BrowserAgent(chrome_path=str(tmp_path))

    def test_init_with_empty_chrome_path(self):
        """Test BrowserAgent initialization with empty Chrome path."""
        with pytest.raises(BrowserError, match="Chrome path is required"):
            BrowserAgent(chrome_path="")

    def test_init_with_browser_use_failure(self, mock_chrome_path: str):
        """Test BrowserAgent initialization when browser-use fails."""
        with patch("ai_qa.browser.agent.Agent", side_effect=Exception("browser-use error")):
            with pytest.raises(BrowserError, match="Failed to initialize browser-use agent"):
                BrowserAgent(chrome_path=mock_chrome_path)

    def test_default_timeout(self, mock_chrome_path: str, mock_browser_use_agent):
        """Test BrowserAgent initialization with default timeout."""
        agent = BrowserAgent(chrome_path=mock_chrome_path)
        assert agent.timeout == 30


class TestBrowserAgentNavigation:
    """Tests for BrowserAgent navigation."""

    @pytest.mark.asyncio
    async def test_navigate_success(self, mock_chrome_path: str, mock_browser_use_agent):
        """Test successful navigation."""
        agent = BrowserAgent(chrome_path=mock_chrome_path, timeout=30)
        await agent.navigate("https://example.com")
        agent.agent.navigate.assert_called_once_with("https://example.com")

    @pytest.mark.asyncio
    async def test_navigate_timeout(self, mock_chrome_path: str, mock_browser_use_agent):
        """Test navigation timeout."""
        mock_browser_use_agent.return_value.navigate = AsyncMock(side_effect=asyncio.TimeoutError)
        agent = BrowserAgent(chrome_path=mock_chrome_path, timeout=30)
        with pytest.raises(NavigationError, match="exceeded 30s timeout"):
            await agent.navigate("https://example.com")

    @pytest.mark.asyncio
    async def test_navigate_browser_crash(self, mock_chrome_path: str, mock_browser_use_agent):
        """Test navigation with browser crash."""
        mock_browser_use_agent.return_value.navigate = AsyncMock(
            side_effect=Exception("browser crashed")
        )
        agent = BrowserAgent(chrome_path=mock_chrome_path, timeout=30)
        with pytest.raises(BrowserError, match="Browser crashed"):
            await agent.navigate("https://example.com")

    @pytest.mark.asyncio
    async def test_navigate_generic_error(self, mock_chrome_path: str, mock_browser_use_agent):
        """Test navigation with generic error."""
        mock_browser_use_agent.return_value.navigate = AsyncMock(
            side_effect=Exception("network error")
        )
        agent = BrowserAgent(chrome_path=mock_chrome_path, timeout=30)
        with pytest.raises(NavigationError, match="Failed to navigate"):
            await agent.navigate("https://example.com")

    @pytest.mark.asyncio
    async def test_navigate_timeout_custom(self, mock_chrome_path: str, mock_browser_use_agent):
        """Test navigation with custom timeout."""
        agent = BrowserAgent(chrome_path=mock_chrome_path, timeout=60)
        mock_browser_use_agent.return_value.navigate = AsyncMock(side_effect=asyncio.TimeoutError)
        with pytest.raises(NavigationError, match="exceeded 60s timeout"):
            await agent.navigate("https://example.com")


class TestBrowserAgentClose:
    """Tests for BrowserAgent cleanup."""

    @pytest.mark.asyncio
    async def test_close_success(self, mock_chrome_path: str, mock_browser_use_agent):
        """Test successful browser close."""
        agent = BrowserAgent(chrome_path=mock_chrome_path, timeout=30)
        await agent.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_close_with_error(self, mock_chrome_path: str, mock_browser_use_agent):
        """Test browser close with error (should raise BrowserError)."""
        # This test is for future enhancement if cleanup logic is added
        agent = BrowserAgent(chrome_path=mock_chrome_path, timeout=30)
        await agent.close()  # Currently no-op, should not raise
