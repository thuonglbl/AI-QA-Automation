"""Unit tests for SessionManager."""

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from ai_qa.browser.session import SessionManager
from ai_qa.db.models import User
from ai_qa.exceptions import SessionError


@pytest.fixture
def mock_db() -> MagicMock:
    """Mock database session."""
    return MagicMock(spec=Session)


@pytest.fixture
def mock_user() -> User:
    """Mock user object."""
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        display_name="Test User",
        password_hash="hash",
    )
    user.chrome_path = "/path/to/chrome"
    return user


class TestChromePathLoading:
    """Tests for Chrome path loading from database."""

    def test_load_chrome_path_valid(self, mock_db: MagicMock, mock_user: User):
        """Test loading Chrome path from valid user."""
        mock_db.get.return_value = mock_user
        manager = SessionManager(db=mock_db, user_id=mock_user.id)
        assert manager.chrome_path == "/path/to/chrome"

    def test_load_chrome_path_no_user(self, mock_db: MagicMock):
        """Test loading Chrome path when user does not exist."""
        mock_db.get.return_value = None
        manager = SessionManager(db=mock_db, user_id=uuid.uuid4())
        assert manager.chrome_path is None

    def test_load_chrome_path_no_chrome_path(self, mock_db: MagicMock, mock_user: User):
        """Test loading Chrome path when user has no chrome_path."""
        mock_user.chrome_path = None
        mock_db.get.return_value = mock_user
        manager = SessionManager(db=mock_db, user_id=mock_user.id)
        assert manager.chrome_path is None

    def test_load_chrome_path_db_error(self, mock_db: MagicMock):
        """Test loading Chrome path with DB error."""
        mock_db.get.side_effect = Exception("DB Error")
        with pytest.raises(
            SessionError, match="Failed to load browser configuration from database"
        ):
            SessionManager(db=mock_db, user_id=uuid.uuid4())


class TestChromePathSaving:
    """Tests for Chrome path saving to database."""

    def test_save_chrome_path(self, mock_db: MagicMock, mock_user: User):
        """Test saving Chrome path to database."""
        mock_db.get.return_value = mock_user
        manager = SessionManager(db=mock_db, user_id=mock_user.id)

        manager.save_chrome_path("/new/path/to/chrome")

        assert manager.chrome_path == "/new/path/to/chrome"
        assert mock_user.chrome_path == "/new/path/to/chrome"
        mock_db.commit.assert_called_once()

    def test_save_chrome_path_no_user(self, mock_db: MagicMock):
        """Test saving Chrome path when user not found."""
        mock_db.get.return_value = None
        manager = SessionManager(db=mock_db, user_id=uuid.uuid4())

        with pytest.raises(SessionError, match="User .* not found"):
            manager.save_chrome_path("/new/path/to/chrome")

    def test_save_chrome_path_db_error(self, mock_db: MagicMock, mock_user: User):
        """Test saving Chrome path when DB commit fails."""
        mock_db.get.return_value = mock_user
        manager = SessionManager(db=mock_db, user_id=mock_user.id)

        mock_db.commit.side_effect = Exception("Commit failed")
        with pytest.raises(SessionError, match="Failed to save browser configuration to database"):
            manager.save_chrome_path("/new/path/to/chrome")

        mock_db.rollback.assert_called_once()


class TestGetChromePath:
    """Tests for getting Chrome path."""

    def test_get_chrome_path_from_db(self, mock_db: MagicMock, mock_user: User):
        """Test getting Chrome path from database."""
        mock_db.get.return_value = mock_user
        manager = SessionManager(db=mock_db, user_id=mock_user.id)
        assert manager.get_chrome_path() == "/path/to/chrome"

    def test_get_chrome_path_from_app_settings(self, mock_db: MagicMock, mock_user: User):
        """Test getting Chrome path from AppSettings when not in DB."""
        mock_user.chrome_path = None
        mock_db.get.return_value = mock_user

        with patch("ai_qa.browser.session.AppSettings") as mock_settings:
            mock_settings.return_value.chrome_path = "/settings/path"
            manager = SessionManager(db=mock_db, user_id=mock_user.id)
            assert manager.get_chrome_path() == "/settings/path"

    def test_get_chrome_path_not_configured(self, mock_db: MagicMock, mock_user: User):
        """Test getting Chrome path when not configured anywhere."""
        mock_user.chrome_path = None
        mock_db.get.return_value = mock_user

        with patch("ai_qa.browser.session.AppSettings") as mock_settings:
            mock_settings.return_value.chrome_path = ""
            manager = SessionManager(db=mock_db, user_id=mock_user.id)
            with pytest.raises(SessionError, match="Chrome path is not configured"):
                manager.get_chrome_path()


class TestSSOSessionDetection:
    """Tests for SSO session detection."""

    def test_detect_active_sso_session_default(self, mock_db: MagicMock, mock_user: User):
        """Test SSO session detection (default implementation returns False)."""
        mock_db.get.return_value = mock_user
        manager = SessionManager(db=mock_db, user_id=mock_user.id)
        assert manager.detect_active_sso_session() is False


class TestChromePathValidation:
    """Tests for Chrome path validation."""

    def test_validate_chrome_path_valid_file(
        self, mock_db: MagicMock, mock_user: User, tmp_path: Path
    ):
        """Test validating a valid Chrome path (existing file)."""
        chrome_exe = tmp_path / "chrome.exe"
        chrome_exe.touch()

        mock_db.get.return_value = mock_user
        manager = SessionManager(db=mock_db, user_id=mock_user.id)
        assert manager.validate_chrome_path(str(chrome_exe)) is True

    def test_validate_chrome_path_not_exists(self, mock_db: MagicMock, mock_user: User):
        """Test validating a non-existent Chrome path."""
        mock_db.get.return_value = mock_user
        manager = SessionManager(db=mock_db, user_id=mock_user.id)
        assert manager.validate_chrome_path("/nonexistent/chrome.exe") is False

    def test_validate_chrome_path_is_directory(
        self, mock_db: MagicMock, mock_user: User, tmp_path: Path
    ):
        """Test validating when Chrome path is a directory."""
        mock_db.get.return_value = mock_user
        manager = SessionManager(db=mock_db, user_id=mock_user.id)
        assert manager.validate_chrome_path(str(tmp_path)) is False
