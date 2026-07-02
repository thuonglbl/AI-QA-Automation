"""Per-user captured browser-session API (project-scoped).

A tester captures their OWN authenticated session for a project's (environment, role)
by logging into a debug browser and letting the backend export its Playwright
``storageState`` over CDP. The blob is encrypted at rest and NEVER returned here — only
non-secret status (timestamps, cookie count). Sarah/Jack rehydrate it server-side.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import get_current_active_user
from ai_qa.db.models import Project, User
from ai_qa.sessions import service as session_service

logger = logging.getLogger(__name__)

DbSessionDependency = Depends(get_db_session_dependency)
CurrentUserDependency = Depends(get_current_active_user)

router = APIRouter(prefix="/projects", tags=["sessions"])

router = APIRouter(prefix="/projects", tags=["sessions"])


class SessionStatusResponse(BaseModel):
    """Non-secret captured-session status (the blob itself is never serialized)."""

    environment: str
    role: str
    auth_method: str
    captured_at: datetime
    expires_at: datetime | None
    last_validated_at: datetime | None
    cookie_count: int


class SessionMatrixResponse(BaseModel):
    """The project's (environment × role) matrix plus this user's captured sessions."""

    environments: list[dict[str, str]]
    app_roles: list[str]
    captured: list[SessionStatusResponse]


async def _project_for_member(project_id: UUID, current_user: User, db: Session) -> Project:
    """Return the project if the current user is an admin or a member, else 404."""
    from ai_qa.api.projects import require_project_member_or_admin

    return await require_project_member_or_admin(project_id, current_user, db)


def _matrix(db: Session, project: Project, user: User) -> SessionMatrixResponse:
    statuses = session_service.list_session_status(db, user_id=user.id, project_id=project.id)
    return SessionMatrixResponse(
        environments=list(project.environments or []),
        app_roles=list(project.app_roles or []),
        captured=[SessionStatusResponse(**vars(s)) for s in statuses],
    )


@router.get("/{project_id}/sessions", response_model=SessionMatrixResponse)
async def list_sessions(
    project_id: UUID,
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> SessionMatrixResponse:
    """List the project's env×role matrix + the current user's captured sessions."""
    project = await _project_for_member(project_id, current_user, db)
    return _matrix(db, project, current_user)


@router.delete("/{project_id}/sessions", status_code=204)
async def delete_session(
    project_id: UUID,
    environment: str,
    role: str,
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> None:
    """Delete the current user's captured session for (environment, role)."""
    project = await _project_for_member(project_id, current_user, db)
    session_service.delete_captured_session(
        db,
        user_id=current_user.id,
        project_id=project.id,
        environment=environment,
        role=role,
    )
