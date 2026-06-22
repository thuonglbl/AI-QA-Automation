"""Authentication middleware for FastAPI.

Protects routes by requiring valid JWT session tokens.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import HTTPException, Request, Response
from fastapi.security import HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ai_qa.api.auth.session import SessionManager, UserSession
from ai_qa.config import AppSettings

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to handle authentication on all requests.

    Validates session cookies and attaches user context to requests.
    Public paths can be accessed without authentication.
    """

    # Paths that don't require authentication
    # NOTE: /auth/register is intentionally NOT public. Public self-service
    # registration is locked down (Story 8.7); user accounts are created only
    # by admins via POST /api/admin/users.
    PUBLIC_PATHS = {
        "/auth/login",
        "/auth/callback",
        "/auth/logout",
        "/auth/me",
        "/auth/status",
        "/api/health",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/health",
        "/",
        "/assets",
        "/vite.svg",
    }

    def __init__(self, app: ASGIApp, settings: AppSettings):
        super().__init__(app)
        self.session_manager = SessionManager(settings)
        self.cookie_name = settings.session_cookie_name

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process request and validate authentication.

        Args:
            request: Incoming request.
            call_next: Next middleware/endpoint in chain.

        Returns:
            Response from next handler.
        """
        path = request.url.path

        # WebSocket upgrade requests authenticate themselves inside websocket_endpoint
        # via query-param token or session cookie. Do not block them at HTTP middleware
        # level, otherwise the 101 Upgrade handshake can never succeed.
        is_websocket_upgrade = (
            request.headers.get("upgrade", "").lower() == "websocket"
            or path == "/ws"
            or path.startswith("/ws/")
        )
        if is_websocket_upgrade:
            # Still attach user if cookie is present (nice-to-have for logging),
            # but always let the request through.
            user = self._get_user_from_request(request)
            request.state.user = user
            return await call_next(request)

        # Check if path is public
        is_public = any(
            path == public_path or path.startswith(public_path + "/")
            for public_path in self.PUBLIC_PATHS
        )

        # Check for static files
        is_static = path.startswith("/assets/") or path.endswith(
            (".js", ".css", ".ico", ".png", ".svg")
        )

        # Always try to get user from session (for public paths that need to know auth status)
        user = self._get_user_from_request(request)

        if is_public or is_static:
            # For public paths, attach user if available but don't require auth
            request.state.user = user
            return await call_next(request)

        if user is None:
            # Check if this is an API request (return 401) or page request (redirect to login)
            if path.startswith("/api/"):
                return Response(
                    content='{"detail": "Not authenticated"}',
                    status_code=401,
                    media_type="application/json",
                )
            # Redirect to login for page requests
            return Response(
                status_code=307,  # Temporary redirect
                headers={"Location": "/auth/login"},
            )

        # Check session expiration
        if user.is_expired:
            if path.startswith("/api/"):
                return Response(
                    content='{"detail": "Session expired"}',
                    status_code=401,
                    media_type="application/json",
                )
            return Response(
                status_code=307,
                headers={"Location": "/auth/login"},
            )

        # Attach user to request state
        request.state.user = user

        return await call_next(request)

    def _get_user_from_request(self, request: Request) -> UserSession | None:
        """Extract and validate user session from request.

        Args:
            request: FastAPI request object.

        Returns:
            UserSession if valid, None otherwise.
        """
        # Try to get token from cookie first
        token = request.cookies.get(self.cookie_name)

        if not token:
            # Fallback to Authorization header
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]

        if not token:
            return None

        return self.session_manager.decode_session(token)


def require_auth(request: Request) -> UserSession:
    """Dependency to require authentication in route handlers.

    Usage:
        @router.get("/protected")
        async def protected_route(user: UserSession = Depends(require_auth)):
            return {"message": f"Hello {user.name}"}

    Args:
        request: FastAPI request object.

    Returns:
        UserSession for authenticated user.

    Raises:
        HTTPException: If user is not authenticated.
    """
    user = getattr(request.state, "user", None)

    if not user or user.is_expired:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return cast(UserSession, user)


async def get_optional_user(request: Request) -> UserSession | None:
    """Get current user if authenticated, None otherwise.

    Usage:
        @router.get("/optional")
        async def optional_route(user: UserSession | None = Depends(get_optional_user)):
            if user:
                return {"message": f"Hello {user.name}"}
            return {"message": "Hello guest"}

    Args:
        request: FastAPI request object.

    Returns:
        UserSession if authenticated, None otherwise.
    """
    user = getattr(request.state, "user", None)

    if user and not user.is_expired:
        return cast(UserSession, user)

    return None
