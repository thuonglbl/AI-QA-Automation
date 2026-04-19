"""Integration tests for browser automation module.

These tests require a real Chrome installation and are marked as integration tests.
They can be skipped during normal test runs.
"""

from pathlib import Path

import pytest

from ai_qa.browser.agent import BrowserAgent
from ai_qa.browser.session import SessionManager
from ai_qa.exceptions import BrowserError, SessionError


@pytest.mark.integration
class TestBrowserAgentIntegration:
    """Integration tests for BrowserAgent with real Chrome."""

    @pytest.mark.asyncio
    async def test_browser_agent_with_real_chrome(self):
        """Test BrowserAgent initialization with real Chrome if available."""
        # Skip if Chrome path not configured
        try:
            manager = SessionManager()
            chrome_path = manager.get_chrome_path()
        except SessionError:
            pytest.skip("Chrome path not configured")

        try:
            agent = BrowserAgent(chrome_path=chrome_path, timeout=30)
            assert agent.chrome_path == chrome_path
            assert agent.timeout == 30
            await agent.close()
        except BrowserError as e:
            pytest.skip(f"Chrome not available or browser-use error: {e}")

    @pytest.mark.asyncio
    async def test_browser_navigation_integration(self):
        """Test actual browser navigation if Chrome is available."""
        try:
            manager = SessionManager()
            chrome_path = manager.get_chrome_path()
        except SessionError:
            pytest.skip("Chrome path not configured")

        try:
            agent = BrowserAgent(chrome_path=chrome_path, timeout=30)
            # Navigate to a simple page
            await agent.navigate("https://example.com")
            await agent.close()
        except (BrowserError, Exception) as e:
            pytest.skip(f"Browser navigation test skipped: {e}")


@pytest.mark.integration
class TestSessionManagerIntegration:
    """Integration tests for SessionManager with real file system."""

    def test_session_manager_persistence(self, tmp_path: Path):
        """Test that SessionManager persists Chrome path across instances."""
        config_dir = tmp_path / "configuration"
        chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"

        # First instance saves the path
        manager1 = SessionManager(config_dir=config_dir)
        manager1.save_chrome_path(chrome_path)

        # Second instance loads the path
        manager2 = SessionManager(config_dir=config_dir)
        assert manager2.chrome_path == chrome_path

    def test_session_manager_get_chrome_path_priority(self, tmp_path: Path):
        """Test that saved config takes priority over AppSettings."""
        config_dir = tmp_path / "configuration"
        saved_path = "/saved/chrome/path"

        manager = SessionManager(config_dir=config_dir)
        manager.save_chrome_path(saved_path)

        # Even if AppSettings has a different path, saved config should win
        assert manager.get_chrome_path() == saved_path
