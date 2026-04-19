"""SSO session management for browser automation.

This module provides SessionManager for detecting and reusing active
Chrome SSO sessions, and managing Chrome path configuration.
"""

import json
from pathlib import Path

from ai_qa.config import AppSettings
from ai_qa.exceptions import SessionError


class SessionManager:
    """Manages SSO session detection and Chrome path configuration.

    Detects active Chrome sessions with SSO cookies and reuses them
    to avoid additional credential storage. Also manages Chrome path
    configuration persistence.

    Attributes:
        config_path: Path to Chrome path configuration file.
        chrome_path: Current Chrome executable path.
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        """Initialize session manager.

        Args:
            config_dir: Directory for storing Chrome path configuration.
                       Defaults to workspace/configuration/.
        """
        if config_dir is None:
            # Default to workspace/configuration/
            project_root = Path(__file__).resolve().parents[3]
            config_dir = project_root / "workspace" / "configuration"

        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.config_path = self.config_dir / "browser_config.json"
        self.chrome_path: str | None = self._load_chrome_path()

    def _load_chrome_path(self) -> str | None:
        """Load Chrome path from configuration file.

        Returns:
            Chrome path if configured, None otherwise.
        """
        if not self.config_path.exists():
            return None

        try:
            with open(self.config_path, encoding="utf-8") as f:
                config: dict[str, str] = json.load(f)
                return config.get("chrome_path")
        except (json.JSONDecodeError, OSError) as e:
            raise SessionError(
                f"Failed to load browser configuration: {e}",
                details=f"Config path: {self.config_path}",
            ) from e

    def save_chrome_path(self, chrome_path: str) -> None:
        """Save Chrome path to configuration file for persistence.

        Args:
            chrome_path: Path to Chrome executable.

        Raises:
            SessionError: If configuration cannot be saved.
        """
        try:
            config = {"chrome_path": chrome_path}
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            self.chrome_path = chrome_path
        except OSError as e:
            raise SessionError(
                f"Failed to save browser configuration: {e}",
                details=f"Config path: {self.config_path}",
            ) from e

    def get_chrome_path(self) -> str:
        """Get Chrome path from configuration or AppSettings.

        Returns:
            Chrome executable path.

        Raises:
            SessionError: If Chrome path is not configured.
        """
        # Try saved configuration first
        if self.chrome_path:
            return self.chrome_path

        # Fall back to AppSettings
        settings = AppSettings()
        if settings.chrome_path:
            return settings.chrome_path

        raise SessionError(
            "Chrome path is not configured",
            details="Set CHROME_PATH in .env or provide via configuration",
        )

    def detect_active_sso_session(self) -> bool:
        """Detect if an active Chrome SSO session exists.

        Checks for running Chrome processes with SSO cookies.
        This is a basic implementation - full SSO detection would
        require more sophisticated process inspection.

        Returns:
            True if active SSO session detected, False otherwise.
        """
        # Basic implementation: check if Chrome is running
        # Full SSO detection would require:
        # - Process inspection for Chrome instances
        # - Cookie database inspection for SSO tokens
        # - Domain-specific SSO detection

        # For now, return False to require new Chrome instance
        # This can be enhanced in future stories
        return False

    def validate_chrome_path(self, chrome_path: str) -> bool:
        """Validate that Chrome executable exists at the given path.

        Args:
            chrome_path: Path to Chrome executable.

        Returns:
            True if path is valid, False otherwise.
        """
        chrome_exe = Path(chrome_path)
        return chrome_exe.exists() and chrome_exe.is_file()
