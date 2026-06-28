"""Integration tests for browser automation module.

These tests require a real Chrome installation and are marked as integration tests.
They can be skipped during normal test runs.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_qa.browser.agent import BrowserAgent
from ai_qa.browser.session import SessionManager
from ai_qa.db.base import Base
from ai_qa.exceptions import BrowserError


@pytest.mark.integration
class TestBrowserAgentIntegration:
    """Integration tests for BrowserAgent wiring.

    The underlying browser-use ``Agent`` is mocked so these run deterministically
    without a GUI Chrome launch (the placeholder browser-use call shape cannot
    drive a real browser). They still exercise BrowserAgent's own logic: Chrome
    path validation, agent construction, navigation delegation, and cleanup.
    """

    @pytest.mark.asyncio
    async def test_browser_agent_with_real_chrome(self, tmp_path):
        """BrowserAgent validates the Chrome path and constructs its agent."""
        fake_chrome = tmp_path / "chrome.exe"
        fake_chrome.write_text("")

        with patch("ai_qa.browser.agent.Agent") as mock_agent:
            agent = BrowserAgent(chrome_path=str(fake_chrome), timeout=30)

            assert agent.chrome_path == str(fake_chrome)
            assert agent.timeout == 30
            mock_agent.assert_called_once()
            await agent.close()

    @pytest.mark.asyncio
    async def test_browser_agent_invalid_chrome_path_raises(self):
        """A missing Chrome executable surfaces a BrowserError (not a skip)."""
        with pytest.raises(BrowserError, match="Chrome executable not found"):
            BrowserAgent(chrome_path="/no/such/chrome.exe", timeout=30)

    @pytest.mark.asyncio
    async def test_browser_navigation_integration(self, tmp_path):
        """BrowserAgent.navigate delegates to the underlying agent with the URL."""
        fake_chrome = tmp_path / "chrome.exe"
        fake_chrome.write_text("")

        with patch("ai_qa.browser.agent.Agent") as mock_agent:
            mock_agent.return_value.navigate = AsyncMock()
            agent = BrowserAgent(chrome_path=str(fake_chrome), timeout=30)

            await agent.navigate("https://example.com")

            mock_agent.return_value.navigate.assert_awaited_once_with("https://example.com")
            await agent.close()


@pytest.mark.integration
class TestSessionManagerIntegration:
    """Integration tests for SessionManager (Chrome path is transient/config-derived)."""

    def test_session_manager_transient_path(self):
        """A transiently-set Chrome path is held in-process (no DB persistence)."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session_local = sessionmaker(bind=engine)
        db = session_local()

        user_id = uuid.uuid4()
        chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"

        with patch("ai_qa.browser.session.AppSettings") as mock_settings:
            mock_settings.return_value.chrome_path = ""
            manager = SessionManager(db=db, user_id=user_id)
            manager.set_chrome_path(chrome_path)
            assert manager.chrome_path == chrome_path

            # A second instance does NOT see the first's transient path.
            manager2 = SessionManager(db=db, user_id=user_id)
            assert manager2.chrome_path is None

        db.close()
        engine.dispose()

    def test_session_manager_get_chrome_path_priority(self):
        """Test that a transiently-set path takes priority over AppSettings."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session_local = sessionmaker(bind=engine)
        db = session_local()

        user_id = uuid.uuid4()
        saved_path = "/saved/chrome/path"

        with patch("ai_qa.browser.session.AppSettings") as mock_settings:
            mock_settings.return_value.chrome_path = "/settings/path"
            manager = SessionManager(db=db, user_id=user_id)
            manager.set_chrome_path(saved_path)
            # Even if AppSettings has a different path, the transient value wins.
            assert manager.get_chrome_path() == saved_path

        db.close()
        engine.dispose()
