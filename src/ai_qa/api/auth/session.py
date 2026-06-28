"""Session management for authenticated users.

Manages JWT session tokens, user context, and session storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from ai_qa.config import AppSettings


@dataclass
class UserSession:
    """Authenticated user session data."""

    email: str
    name: str
    user_id: str | None = None
    role: str | None = None
    is_active: bool = True
    given_name: str | None = None
    family_name: str | None = None
    groups: list[str] = field(default_factory=list)
    # Full platform role set derived from Azure App Roles (+ membership) each login
    # (Epic 23, story 23.3). ``role`` above stays the single derived primary for the
    # existing single-role surface; ``roles`` carries every entitled role for the FE.
    roles: list[str] = field(default_factory=list)
    timezone: str = "UTC"
    access_token: str | None = None
    expires_at: datetime | None = None

    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        if self.expires_at is None:
            return True
        return datetime.now(UTC) > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        """Convert session to dictionary for JWT encoding."""
        return {
            "sub": self.email,
            "user_id": self.user_id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "is_active": self.is_active,
            "given_name": self.given_name,
            "family_name": self.family_name,
            "groups": self.groups,
            "roles": self.roles,
            "timezone": self.timezone,
            "exp": int(self.expires_at.timestamp()) if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserSession:
        """Create session from decoded JWT dictionary."""
        exp_timestamp = data.get("exp")
        expires_at = None
        if exp_timestamp:
            expires_at = datetime.fromtimestamp(exp_timestamp, tz=UTC)

        return cls(
            email=data.get("email", ""),
            name=data.get("name", ""),
            user_id=data.get("user_id"),
            role=data.get("role"),
            is_active=data.get("is_active", True),
            given_name=data.get("given_name"),
            family_name=data.get("family_name"),
            groups=data.get("groups", []),
            roles=data.get("roles") or [],
            timezone=data.get("timezone") or "UTC",
            expires_at=expires_at,
        )


class SessionManager:
    """Manages user sessions with JWT tokens."""

    def __init__(self, settings: AppSettings):
        self.settings = settings
        self._secret_key = settings.session_secret_key
        self._cookie_name = settings.session_cookie_name
        self._expire_hours = settings.session_expire_hours

    def create_session(self, user_data: dict[str, Any]) -> UserSession:
        """Create a new user session.

        Args:
            user_data: Dictionary containing user information.

        Returns:
            New UserSession instance.
        """
        expires_at = datetime.now(UTC) + timedelta(hours=self._expire_hours)

        session = UserSession(
            email=str(user_data.get("email") or user_data.get("preferred_username") or ""),
            name=str(user_data.get("name") or user_data.get("displayName") or ""),
            user_id=user_data.get("user_id"),
            role=user_data.get("role"),
            is_active=user_data.get("is_active", True),
            given_name=user_data.get("given_name"),
            family_name=user_data.get("family_name"),
            groups=user_data.get("groups", []),
            roles=user_data.get("roles") or [],
            timezone=user_data.get("timezone") or "UTC",
            expires_at=expires_at,
        )
        return session

    def encode_session(self, session: UserSession) -> str:
        """Encode session to JWT token string.

        Args:
            session: UserSession to encode.

        Returns:
            JWT token string.
        """
        token: str = jwt.encode(
            session.to_dict(),
            self._secret_key,
            algorithm="HS256",
        )
        return token

    def decode_session(self, token: str) -> UserSession | None:
        """Decode JWT token to UserSession.

        Args:
            token: JWT token string.

        Returns:
            UserSession if valid, None otherwise.
        """
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=["HS256"])
            return UserSession.from_dict(payload)
        except JWTError:
            return None

    def get_cookie_settings(self) -> dict[str, Any]:
        """Get cookie settings for session cookie.

        Returns:
            Dictionary of cookie settings.
        """
        expires = timedelta(hours=self._expire_hours)
        return {
            "key": self._cookie_name,
            "httponly": True,
            "secure": self.settings.session_cookie_secure,
            "samesite": self.settings.session_cookie_samesite,
            "max_age": int(expires.total_seconds()),
            "path": "/",
        }
