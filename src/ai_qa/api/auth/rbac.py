"""Reusable RBAC dependencies for protected FastAPI routes."""

from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.auth.service import ADMIN_ROLE, STANDARD_ROLE
from ai_qa.db.models import User

DbSessionDependency = Depends(get_db_session_dependency)

NOT_AUTHENTICATED_DETAIL = "Not authenticated"
FORBIDDEN_DETAIL = "Forbidden"


def _not_authenticated() -> HTTPException:
    return HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)


async def get_current_active_user(
    request: Request,
    db: Session = DbSessionDependency,
) -> User:
    """Return the active DB user for the current session, rejecting stale tokens."""
    session_user = getattr(request.state, "user", None)
    if session_user is None or getattr(session_user, "is_expired", True):
        raise _not_authenticated()

    try:
        user_id = UUID(str(session_user.user_id))
    except (TypeError, ValueError) as exc:
        raise _not_authenticated() from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _not_authenticated()

    return user


CurrentUserDependency = Depends(get_current_active_user)


async def require_admin(
    current_user: User = CurrentUserDependency,
) -> User:
    """Require an active admin user from the current database state."""
    if current_user.role != ADMIN_ROLE:
        raise HTTPException(status_code=403, detail=FORBIDDEN_DETAIL)
    return current_user


__all__ = [
    "ADMIN_ROLE",
    "STANDARD_ROLE",
    "FORBIDDEN_DETAIL",
    "NOT_AUTHENTICATED_DETAIL",
    "get_current_active_user",
    "require_admin",
]
