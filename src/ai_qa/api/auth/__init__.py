"""Authentication module for local authentication.

Provides authentication routes, middleware, and session management
for local email/password authentication.
"""

from ai_qa.api.auth.local import get_auth_router
from ai_qa.api.auth.middleware import AuthMiddleware, require_auth
from ai_qa.api.auth.session import SessionManager, UserSession

__all__ = [
    "AuthMiddleware",
    "SessionManager",
    "UserSession",
    "get_auth_router",
    "require_auth",
]
