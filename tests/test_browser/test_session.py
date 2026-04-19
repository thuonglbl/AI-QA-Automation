"""Unit tests for SessionManager."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_qa.browser.session import SessionManager
from ai_qa.exceptions import SessionError


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create temporary configuration directory."""
    config_dir = tmp_path / "configuration"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


class TestSessionManagerInitialization:
    """Tests for SessionManager initialization."""

    def test_init_custom_config_dir(self, temp_config_dir: Path):
        """Test SessionManager initialization with custom config directory."""
        manager = SessionManager(config_dir=temp_config_dir)
        assert manager.config_dir == temp_config_dir

    def test_init_creates_config_dir(self, tmp_path: Path):
        """Test that initialization creates config directory if it doesn't exist."""
        config_dir = tmp_path / "new_config"
        SessionManager(config_dir=config_dir)
        assert config_dir.exists()
        assert config_dir.is_dir()

    def test_init_default_config_dir(self):
        """Test SessionManager initialization with default config directory."""
        # This test uses the actual default path resolution
        manager = SessionManager()
        # The default should be project_root/workspace/configuration
        # We just verify it creates the structure correctly
        assert manager.config_dir.name == "configuration"
        assert manager.config_dir.parent.name == "workspace"


class TestChromePathLoading:
    """Tests for Chrome path loading from configuration."""

    def test_load_chrome_path_no_config_file(self, temp_config_dir: Path):
        """Test loading Chrome path when config file doesn't exist."""
        manager = SessionManager(config_dir=temp_config_dir)
        assert manager.chrome_path is None

    def test_load_chrome_path_valid_config(self, temp_config_dir: Path):
        """Test loading Chrome path from valid config file."""
        config_path = temp_config_dir / "browser_config.json"
        config_path.write_text(json.dumps({"chrome_path": "/path/to/chrome"}))
        manager = SessionManager(config_dir=temp_config_dir)
        assert manager.chrome_path == "/path/to/chrome"

    def test_load_chrome_path_invalid_json(self, temp_config_dir: Path):
        """Test loading Chrome path from invalid JSON file."""
        config_path = temp_config_dir / "browser_config.json"
        config_path.write_text("invalid json")
        with pytest.raises(SessionError, match="Failed to load browser configuration"):
            SessionManager(config_dir=temp_config_dir)

    def test_load_chrome_path_no_chrome_path_key(self, temp_config_dir: Path):
        """Test loading Chrome path when config file has no chrome_path key."""
        config_path = temp_config_dir / "browser_config.json"
        config_path.write_text(json.dumps({"other_key": "value"}))
        manager = SessionManager(config_dir=temp_config_dir)
        assert manager.chrome_path is None


class TestChromePathSaving:
    """Tests for Chrome path saving to configuration."""

    def test_save_chrome_path(self, temp_config_dir: Path):
        """Test saving Chrome path to configuration."""
        manager = SessionManager(config_dir=temp_config_dir)
        manager.save_chrome_path("/new/path/to/chrome")
        assert manager.chrome_path == "/new/path/to/chrome"

        # Verify file was saved
        config_path = temp_config_dir / "browser_config.json"
        assert config_path.exists()
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        assert config["chrome_path"] == "/new/path/to/chrome"

    def test_save_chrome_path_overwrites_existing(self, temp_config_dir: Path):
        """Test that saving Chrome path overwrites existing value."""
        config_path = temp_config_dir / "browser_config.json"
        config_path.write_text(json.dumps({"chrome_path": "/old/path"}))

        manager = SessionManager(config_dir=temp_config_dir)
        manager.save_chrome_path("/new/path/to/chrome")

        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        assert config["chrome_path"] == "/new/path/to/chrome"

    def test_save_chrome_path_io_error(self, temp_config_dir: Path):
        """Test saving Chrome path when directory is read-only."""
        manager = SessionManager(config_dir=temp_config_dir)
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            with pytest.raises(SessionError, match="Failed to save browser configuration"):
                manager.save_chrome_path("/path/to/chrome")


class TestGetChromePath:
    """Tests for getting Chrome path."""

    def test_get_chrome_path_from_saved_config(self, temp_config_dir: Path):
        """Test getting Chrome path from saved configuration."""
        config_path = temp_config_dir / "browser_config.json"
        config_path.write_text(json.dumps({"chrome_path": "/saved/path"}))

        manager = SessionManager(config_dir=temp_config_dir)
        assert manager.get_chrome_path() == "/saved/path"

    def test_get_chrome_path_from_app_settings(self, temp_config_dir: Path):
        """Test getting Chrome path from AppSettings when not saved."""
        with patch("ai_qa.browser.session.AppSettings") as mock_settings:
            mock_settings.return_value.chrome_path = "/settings/path"
            manager = SessionManager(config_dir=temp_config_dir)
            assert manager.get_chrome_path() == "/settings/path"

    def test_get_chrome_path_not_configured(self, temp_config_dir: Path):
        """Test getting Chrome path when not configured anywhere."""
        with patch("ai_qa.browser.session.AppSettings") as mock_settings:
            mock_settings.return_value.chrome_path = ""
            manager = SessionManager(config_dir=temp_config_dir)
            with pytest.raises(SessionError, match="Chrome path is not configured"):
                manager.get_chrome_path()


class TestSSOSessionDetection:
    """Tests for SSO session detection."""

    def test_detect_active_sso_session_default(self, temp_config_dir: Path):
        """Test SSO session detection (default implementation returns False)."""
        manager = SessionManager(config_dir=temp_config_dir)
        # Current implementation returns False
        assert manager.detect_active_sso_session() is False


class TestChromePathValidation:
    """Tests for Chrome path validation."""

    def test_validate_chrome_path_valid_file(self, temp_config_dir: Path):
        """Test validating a valid Chrome path (existing file)."""
        chrome_exe = temp_config_dir / "chrome.exe"
        chrome_exe.touch()
        manager = SessionManager(config_dir=temp_config_dir)
        assert manager.validate_chrome_path(str(chrome_exe)) is True

    def test_validate_chrome_path_not_exists(self, temp_config_dir: Path):
        """Test validating a non-existent Chrome path."""
        manager = SessionManager(config_dir=temp_config_dir)
        assert manager.validate_chrome_path("/nonexistent/chrome.exe") is False

    def test_validate_chrome_path_is_directory(self, temp_config_dir: Path):
        """Test validating when Chrome path is a directory."""
        manager = SessionManager(config_dir=temp_config_dir)
        assert manager.validate_chrome_path(str(temp_config_dir)) is False
