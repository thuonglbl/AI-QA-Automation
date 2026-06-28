"""SSO session management for browser automation.

This module provides SessionManager for detecting and reusing active
Chrome SSO sessions, and resolving the Chrome path configuration.
"""

from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from ai_qa.config import AppSettings
from ai_qa.exceptions import SessionError


class SessionManager:
    """Manages SSO session detection and Chrome path resolution.

    Detects active Chrome sessions with SSO cookies and reuses them
    to avoid additional credential storage. The Chrome path is resolved
    from the instance configuration (``AppSettings.chrome_path``) or set
    transiently for the current process — it is NOT persisted per user.

    Attributes:
        db: Database session.
        user_id: ID of the user owning the session.
        chrome_path: Current Chrome executable path (transient/config-derived).
    """

    def __init__(self, db: Session, user_id: UUID) -> None:
        """Initialize session manager.

        Args:
            db: Database session.
            user_id: ID of the user.
        """
        self.db = db
        self.user_id = user_id
        # Chrome path is no longer persisted per user; default to the configured path.
        self.chrome_path: str | None = AppSettings().chrome_path or None

    def set_chrome_path(self, chrome_path: str) -> None:
        """Set the Chrome path for the current process (not persisted).

        Args:
            chrome_path: Path to Chrome executable.
        """
        self.chrome_path = chrome_path

    def get_chrome_path(self) -> str:
        """Get Chrome path from the transient value or AppSettings.

        Returns:
            Chrome executable path.

        Raises:
            SessionError: If Chrome path is not configured.
        """
        # Try the transient value first
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
