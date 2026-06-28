"""Local PostgreSQL-backed authentication routes for FastAPI."""

from collections.abc import Generator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai_qa.api.auth.session import SessionManager
from ai_qa.config import AppSettings
from ai_qa.db.models import User
from ai_qa.db.session import get_db_session


def get_db_session_dependency(request: Request) -> Generator[Session]:
    """FastAPI dependency that binds DB sessions to the app settings instance."""
    settings = request.app.state.settings
    yield from get_db_session(settings)


DbSessionDependency = Depends(get_db_session_dependency)


class UserProfileResponse(BaseModel):
    """Secret-free authenticated user profile."""

    authenticated: bool = True
    id: str
    email: str
    display_name: str
    role: str
    # Full platform role set (Epic 23). Defaults to ``[role]`` for back-compat with
    # local-login sessions that predate the multi-role model.
    roles: list[str] = []
    is_active: bool
    timezone: str = "UTC"
    # Backend-served Azure avatar URL (story 23.4); null => FE renders initials.
    avatar_url: str | None = None


# Stable, backend-served avatar URL (the photo bytes live in users.avatar; this route
# decodes + streams them). Same-origin <img> requests carry the session cookie.
AVATAR_URL = "/auth/me/avatar"


def _avatar_url_for(user: User) -> str | None:
    return AVATAR_URL if user.avatar else None


def _decode_data_uri(data_uri: str) -> tuple[str, bytes | None]:
    """Decode a ``data:<mime>;base64,<data>`` URI into (mime, bytes)."""
    import base64

    if not data_uri.startswith("data:") or ";base64," not in data_uri:
        return "application/octet-stream", None
    header, _, b64 = data_uri.partition(",")
    mime = header[len("data:") :].split(";")[0] or "application/octet-stream"
    try:
        return mime, base64.b64decode(b64)
    except ValueError:
        return mime, None


def _session_payload(user: User) -> dict[str, Any]:
    return {
        "user_id": str(user.id),
        "email": user.email,
        "name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "timezone": user.timezone,
    }


def _profile_response(user: User, roles: list[str] | None = None) -> dict[str, Any]:
    return UserProfileResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        roles=roles if roles is not None else [user.role],
        is_active=user.is_active,
        timezone=user.timezone,
        avatar_url=_avatar_url_for(user),
    ).model_dump()


def get_auth_router(settings: AppSettings) -> APIRouter:
    """Create authentication router with local DB-backed auth endpoints."""
    router = APIRouter(prefix="/auth", tags=["authentication"])
    session_manager = SessionManager(settings)

    @router.post("/logout")
    async def logout(request: Request, response: Response) -> dict[str, Any]:
        """Logout and clear session."""
        cookie_settings = session_manager.get_cookie_settings()
        response.delete_cookie(
            key=settings.session_cookie_name,
            path=cookie_settings.get("path", "/"),
            secure=cookie_settings.get("secure", False),
            samesite=cookie_settings.get("samesite", "lax"),
        )
        response.delete_cookie(
            key="aiqa_oauth_session",
            path="/",
            secure=settings.session_cookie_secure,
            samesite="lax",
        )
        if hasattr(request, "session"):
            request.session.clear()
        return {"success": True, "message": "Logged out successfully"}

    @router.get("/me")
    async def get_current_user(
        request: Request,
        db: Session = DbSessionDependency,
    ) -> dict[str, Any]:
        """Get current authenticated user info from a valid local session."""
        session_user = getattr(request.state, "user", None)
        if not session_user or session_user.is_expired:
            raise HTTPException(status_code=401, detail="Not authenticated")

        try:
            user_id = UUID(str(session_user.user_id))
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Not authenticated") from exc

        user = db.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Not authenticated")

        roles = list(getattr(session_user, "roles", None) or [user.role])
        return _profile_response(user, roles=roles)

    @router.get("/me/avatar")
    async def get_avatar(
        request: Request,
        db: Session = DbSessionDependency,
    ) -> Response:
        """Serve the current user's Azure-synced avatar bytes (story 23.4).

        Returns 404 when there is no photo (or no session) so the FE Avatar falls
        back to initials. Public-by-prefix (under /auth/me) but scoped to the
        caller's own session — never another user's photo.
        """
        session_user = getattr(request.state, "user", None)
        if not session_user or session_user.is_expired:
            raise HTTPException(status_code=404, detail="No avatar")
        try:
            user = db.get(User, UUID(str(session_user.user_id)))
        except ValueError:
            user = None
        if user is None or not user.avatar:
            raise HTTPException(status_code=404, detail="No avatar")
        mime, data = _decode_data_uri(user.avatar)
        if data is None:
            raise HTTPException(status_code=404, detail="No avatar")
        return Response(content=data, media_type=mime)

    @router.get("/status")
    async def auth_status(
        request: Request,
        db: Session = DbSessionDependency,
    ) -> dict[str, Any]:
        """Check authentication status without requiring auth."""
        user = getattr(request.state, "user", None)
        if user and not user.is_expired:
            roles = list(getattr(user, "roles", None) or ([user.role] if user.role else []))
            avatar_url: str | None = None
            try:
                db_user = db.get(User, UUID(str(user.user_id)))
            except TypeError, ValueError:
                db_user = None
            if db_user is not None:
                avatar_url = _avatar_url_for(db_user)
            return {
                "authenticated": True,
                "id": user.user_id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "roles": roles,
                "avatar_url": avatar_url,
                "timezone": getattr(user, "timezone", "UTC") or "UTC",
            }
        return {"authenticated": False}

    return router
