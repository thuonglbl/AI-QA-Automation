"""Unit tests for SessionManager (Chrome path resolution, no per-user persistence)."""

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from ai_qa.browser.session import SessionManager
from ai_qa.exceptions import SessionError


@pytest.fixture
def mock_db() -> MagicMock:
    """Mock database session."""
    return MagicMock(spec=Session)


class TestChromePathResolution:
    """Tests for Chrome path resolution (config-derived / transient)."""

    def test_defaults_to_app_settings_chrome_path(self, mock_db: MagicMock) -> None:
        """The manager seeds chrome_path from AppSettings.chrome_path."""
        with patch("ai_qa.browser.session.AppSettings") as mock_settings:
            mock_settings.return_value.chrome_path = "/settings/path"
            manager = SessionManager(db=mock_db, user_id=uuid.uuid4())
            assert manager.chrome_path == "/settings/path"

    def test_empty_app_settings_yields_none(self, mock_db: MagicMock) -> None:
        """An empty configured path leaves chrome_path unset (None)."""
        with patch("ai_qa.browser.session.AppSettings") as mock_settings:
            mock_settings.return_value.chrome_path = ""
            manager = SessionManager(db=mock_db, user_id=uuid.uuid4())
            assert manager.chrome_path is None

    def test_set_chrome_path_is_transient(self, mock_db: MagicMock) -> None:
        """set_chrome_path updates the in-process value and never touches the DB."""
        with patch("ai_qa.browser.session.AppSettings") as mock_settings:
            mock_settings.return_value.chrome_path = ""
            manager = SessionManager(db=mock_db, user_id=uuid.uuid4())
            manager.set_chrome_path("/new/path/to/chrome")
        assert manager.chrome_path == "/new/path/to/chrome"
        mock_db.commit.assert_not_called()


class TestGetChromePath:
    """Tests for getting Chrome path."""

    def test_get_chrome_path_from_transient(self, mock_db: MagicMock) -> None:
        """Test getting Chrome path from the transient value."""
        with patch("ai_qa.browser.session.AppSettings") as mock_settings:
            mock_settings.return_value.chrome_path = ""
            manager = SessionManager(db=mock_db, user_id=uuid.uuid4())
            manager.set_chrome_path("/transient/path")
            assert manager.get_chrome_path() == "/transient/path"

    def test_get_chrome_path_from_app_settings(self, mock_db: MagicMock) -> None:
        """Test getting Chrome path from AppSettings when not set transiently."""
        with patch("ai_qa.browser.session.AppSettings") as mock_settings:
            mock_settings.return_value.chrome_path = "/settings/path"
            manager = SessionManager(db=mock_db, user_id=uuid.uuid4())
            assert manager.get_chrome_path() == "/settings/path"

    def test_get_chrome_path_not_configured(self, mock_db: MagicMock) -> None:
        """Test getting Chrome path when not configured anywhere."""
        with patch("ai_qa.browser.session.AppSettings") as mock_settings:
            mock_settings.return_value.chrome_path = ""
            manager = SessionManager(db=mock_db, user_id=uuid.uuid4())
            with pytest.raises(SessionError, match="Chrome path is not configured"):
                manager.get_chrome_path()


class TestSSOSessionDetection:
    """Tests for SSO session detection."""

    def test_detect_active_sso_session_default(self, mock_db: MagicMock) -> None:
        """Test SSO session detection (default implementation returns False)."""
        with patch("ai_qa.browser.session.AppSettings") as mock_settings:
            mock_settings.return_value.chrome_path = ""
            manager = SessionManager(db=mock_db, user_id=uuid.uuid4())
            assert manager.detect_active_sso_session() is False


class TestChromePathValidation:
    """Tests for Chrome path validation."""

    def test_validate_chrome_path_valid_file(self, mock_db: MagicMock, tmp_path: Path) -> None:
        """Test validating a valid Chrome path (existing file)."""
        chrome_exe = tmp_path / "chrome.exe"
        chrome_exe.touch()
        with patch("ai_qa.browser.session.AppSettings") as mock_settings:
            mock_settings.return_value.chrome_path = ""
            manager = SessionManager(db=mock_db, user_id=uuid.uuid4())
            assert manager.validate_chrome_path(str(chrome_exe)) is True

    def test_validate_chrome_path_not_exists(self, mock_db: MagicMock) -> None:
        """Test validating a non-existent Chrome path."""
        with patch("ai_qa.browser.session.AppSettings") as mock_settings:
            mock_settings.return_value.chrome_path = ""
            manager = SessionManager(db=mock_db, user_id=uuid.uuid4())
            assert manager.validate_chrome_path("/nonexistent/chrome.exe") is False

    def test_validate_chrome_path_is_directory(self, mock_db: MagicMock, tmp_path: Path) -> None:
        """Test validating when Chrome path is a directory."""
        with patch("ai_qa.browser.session.AppSettings") as mock_settings:
            mock_settings.return_value.chrome_path = ""
            manager = SessionManager(db=mock_db, user_id=uuid.uuid4())
            assert manager.validate_chrome_path(str(tmp_path)) is False
