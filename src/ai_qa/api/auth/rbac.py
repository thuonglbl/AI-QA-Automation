"""Reusable RBAC dependencies for protected FastAPI routes."""

from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.auth.service import ADMIN_ROLE, PROJECT_ADMIN_ROLE, STANDARD_ROLE
from ai_qa.db.models import ProjectMembership, User

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


async def require_project_admin_for_project(
    project_id: UUID,
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> User:
    """Require the caller to administer ``project_id``.

    Allowed when the caller is a platform admin (backdoor), OR a ``project_admin`` who
    holds a ``ProjectMembership(role="project_admin")`` on this project. Denied as 403
    otherwise. Used to gate the per-project administration endpoints (config, accounts,
    membership) that move off the platform-admin surface.
    """
    if current_user.role == ADMIN_ROLE:
        return current_user
    if current_user.role == PROJECT_ADMIN_ROLE:
        membership = db.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == current_user.id,
                ProjectMembership.role == PROJECT_ADMIN_ROLE,
            )
        ).scalar_one_or_none()
        if membership is not None:
            return current_user
    raise HTTPException(status_code=403, detail=FORBIDDEN_DETAIL)


__all__ = [
    "ADMIN_ROLE",
    "PROJECT_ADMIN_ROLE",
    "STANDARD_ROLE",
    "FORBIDDEN_DETAIL",
    "NOT_AUTHENTICATED_DETAIL",
    "get_current_active_user",
    "require_admin",
    "require_project_admin_for_project",
]
