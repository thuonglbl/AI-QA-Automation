"""SSO session management for browser automation.

This module provides SessionManager for detecting and reusing active
Chrome SSO sessions, and managing Chrome path configuration.
"""

from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from ai_qa.config import AppSettings
from ai_qa.db.models import User
from ai_qa.exceptions import SessionError


class SessionManager:
    """Manages SSO session detection and Chrome path configuration.

    Detects active Chrome sessions with SSO cookies and reuses them
    to avoid additional credential storage. Also manages Chrome path
    configuration persistence.

    Attributes:
        db: Database session.
        user_id: ID of the user owning the session.
        chrome_path: Current Chrome executable path.
    """

    def __init__(self, db: Session, user_id: UUID) -> None:
        """Initialize session manager.

        Args:
            db: Database session.
            user_id: ID of the user.
        """
        self.db = db
        self.user_id = user_id
        self.chrome_path: str | None = self._load_chrome_path()

    def _load_chrome_path(self) -> str | None:
        """Load Chrome path from database for the user.

        Returns:
            Chrome path if configured, None otherwise.
        """
        try:
            user = self.db.get(User, self.user_id)
            if user and user.chrome_path:
                return user.chrome_path
            return None
        except Exception as e:
            raise SessionError(
                f"Failed to load browser configuration from database: {e}",
            ) from e

    def save_chrome_path(self, chrome_path: str) -> None:
        """Save Chrome path to database for persistence.

        Args:
            chrome_path: Path to Chrome executable.

        Raises:
            SessionError: If configuration cannot be saved.
        """
        try:
            user = self.db.get(User, self.user_id)
            if not user:
                raise SessionError(f"User {self.user_id} not found")

            user.chrome_path = chrome_path
            self.db.commit()
            self.chrome_path = chrome_path
        except Exception as e:
            self.db.rollback()
            raise SessionError(
                f"Failed to save browser configuration to database: {e}",
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
