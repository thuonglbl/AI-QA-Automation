"""Project membership service."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ai_qa.auth.service import ADMIN_ROLE
from ai_qa.db.models import Project, ProjectMembership, User


def get_user_projects(db: Session, user_id: UUID) -> list[Project]:
    """Return projects that the user has membership in."""
    query = (
        select(Project)
        .options(selectinload(Project.memberships))
        .join(ProjectMembership)
        .where(ProjectMembership.user_id == user_id)
        .order_by(Project.name)
    )
    projects = db.execute(query).scalars().unique().all()
    return list(projects)


def is_project_member(db: Session, user_id: UUID, project_id: UUID) -> bool:
    """Return True when an active membership row links the user to the project.

    Membership removal is a hard delete of the row, so a simple presence check
    is the source of truth for current access.
    """
    row = db.execute(
        select(ProjectMembership.id)
        .where(ProjectMembership.project_id == project_id)
        .where(ProjectMembership.user_id == user_id)
    ).first()
    return row is not None


def user_can_access_project(db: Session, user: User, project_id: UUID) -> bool:
    """Return True when the user is a global admin or an active project member.

    Mirrors the authorization semantics of ``require_project_member_or_admin``
    (admin bypass + membership lookup) for use in non-HTTP/service contexts.
    """
    if user.role == ADMIN_ROLE:
        return True
    return is_project_member(db, user.id, project_id)
