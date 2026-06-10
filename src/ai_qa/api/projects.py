"""Project listing and membership authorization API routes."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import FORBIDDEN_DETAIL, get_current_active_user
from ai_qa.auth.service import ADMIN_ROLE
from ai_qa.db.models import Project, User
from ai_qa.projects.service import get_user_projects

DbSessionDependency = Depends(get_db_session_dependency)
CurrentUserDependency = Depends(get_current_active_user)
RESOURCE_NOT_FOUND_DETAIL = "Resource not found"

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectMembershipSummary(BaseModel):
    """Secret-free membership summary for project administration views."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    role: str
    created_at: datetime
    updated_at: datetime


class ProjectResponse(BaseModel):
    """Secret-free project representation for user-facing project APIs."""

    id: UUID
    name: str
    description: str | None
    confluence_base_url: str | None
    jira_base_url: str | None
    enabled_providers: list[str]
    created_by_user_id: UUID | None
    current_user_role: str | None
    membership_count: int
    memberships: list[ProjectMembershipSummary] = []
    created_at: datetime
    updated_at: datetime


def _response_for_project(project: Project, current_user: User) -> ProjectResponse:
    """Build a role-aware project response without exposing ORM internals."""
    memberships = list(project.memberships)
    current_membership = next(
        (membership for membership in memberships if membership.user_id == current_user.id), None
    )
    is_admin = current_user.role == ADMIN_ROLE

    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        confluence_base_url=project.confluence_base_url,
        jira_base_url=project.jira_base_url,
        enabled_providers=project.enabled_providers or [],
        created_by_user_id=project.created_by_user_id,
        current_user_role=current_membership.role if current_membership else None,
        membership_count=len(memberships),
        memberships=[ProjectMembershipSummary.model_validate(m) for m in memberships]
        if is_admin
        else [],
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


async def require_project_member_or_admin(
    project_id: UUID,
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> Project:
    """Return a project only when the current user is an admin or project member."""
    project = db.execute(
        select(Project).options(selectinload(Project.memberships)).where(Project.id == project_id)
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL)

    if current_user.role == ADMIN_ROLE:
        return project

    is_member = any(membership.user_id == current_user.id for membership in project.memberships)
    if not is_member:
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL)

    return project


ProjectAccessDependency = Depends(require_project_member_or_admin)


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> list[ProjectResponse]:
    """List all projects for admins and only memberships for standard users."""
    if current_user.role == ADMIN_ROLE:
        query = select(Project).options(selectinload(Project.memberships)).order_by(Project.name)
        projects = db.execute(query).scalars().unique().all()
    else:
        projects = get_user_projects(db, current_user.id)
    return [_response_for_project(project, current_user) for project in projects]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project: Project = ProjectAccessDependency,
    current_user: User = CurrentUserDependency,
) -> ProjectResponse:
    """Return project detail for admins or assigned project members."""
    return _response_for_project(project, current_user)


__all__ = [
    "FORBIDDEN_DETAIL",
    "ProjectMembershipSummary",
    "ProjectResponse",
    "require_project_member_or_admin",
    "router",
]
