"""Local PostgreSQL-backed authentication routes for FastAPI."""

from collections.abc import Generator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from ai_qa.api.auth.session import SessionManager
from ai_qa.auth.service import AuthFailure, DuplicateUserError, authenticate_user, register_user
from ai_qa.config import AppSettings
from ai_qa.db.models import User
from ai_qa.db.session import get_db_session

_DUPLICATE_REGISTRATION_DETAIL = "Registration could not be completed"


def get_db_session_dependency(request: Request) -> Generator[Session]:
    """FastAPI dependency that binds DB sessions to the app settings instance."""
    settings = request.app.state.settings
    yield from get_db_session(settings)


DbSessionDependency = Depends(get_db_session_dependency)


class LoginRequest(BaseModel):
    """Local login request."""

    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    """Public registration request; role fields are ignored if provided."""

    model_config = ConfigDict(extra="ignore")

    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8)


class UserProfileResponse(BaseModel):
    """Secret-free authenticated user profile."""

    authenticated: bool = True
    id: str
    email: str
    display_name: str
    role: str
    is_active: bool


def _session_payload(user: User) -> dict[str, Any]:
    return {
        "user_id": str(user.id),
        "email": user.email,
        "name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
    }


def _profile_response(user: User) -> dict[str, Any]:
    return UserProfileResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
    ).model_dump()


def get_auth_router(settings: AppSettings) -> APIRouter:
    """Create authentication router with local DB-backed auth endpoints."""
    router = APIRouter(prefix="/auth", tags=["authentication"])
    session_manager = SessionManager(settings)

    @router.post("/register")
    async def register(
        request: RegisterRequest,
        db: Session = DbSessionDependency,
    ) -> dict[str, Any]:
        """Register a new standard user."""
        try:
            user = register_user(db, request.email, request.name, request.password)
        except DuplicateUserError as exc:
            raise HTTPException(status_code=400, detail=_DUPLICATE_REGISTRATION_DETAIL) from exc
        return {
            "success": True,
            "message": "Registration successful. Please log in.",
            "user": _profile_response(user),
        }

    @router.post("/login")
    async def login(
        request: LoginRequest,
        response: Response,
        db: Session = DbSessionDependency,
    ) -> dict[str, Any]:
        """Log in a user and set a JWT session cookie."""
        user = authenticate_user(db, request.email, request.password)
        if isinstance(user, AuthFailure):
            raise HTTPException(status_code=401, detail=user.reason)

        session = session_manager.create_session(_session_payload(user))
        session_token = session_manager.encode_session(session)
        response.set_cookie(value=session_token, **session_manager.get_cookie_settings())

        return {
            "success": True,
            "message": "Logged in successfully",
            "access_token": session_token,
            "token_type": "bearer",
            "user": _profile_response(user),
        }

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

        return _profile_response(user)

    @router.get("/status")
    async def auth_status(request: Request) -> dict[str, Any]:
        """Check authentication status without requiring auth."""
        user = getattr(request.state, "user", None)
        if user and not user.is_expired:
            return {
                "authenticated": True,
                "email": user.email,
                "name": user.name,
                "role": user.role,
            }
        return {"authenticated": False}

    return router
