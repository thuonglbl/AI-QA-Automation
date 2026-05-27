"""Admin-only project and user management API routes."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import require_admin
from ai_qa.auth.password import hash_password
from ai_qa.auth.service import DuplicateUserError, get_user_by_email, normalize_email
from ai_qa.db.models import Project, ProjectMembership, User

DbSessionDependency = Depends(get_db_session_dependency)
AdminDependency = Depends(require_admin)
ProjectMembershipRole = Literal["member", "owner"]

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUserResponse(BaseModel):
    """Secret-free user representation for admin APIs."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProjectCreateRequest(BaseModel):
    """Admin project creation request."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    confluence_base_url: str = Field(min_length=1, max_length=512)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        """Normalize and reject project names that are blank after trimming."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("Project name is required")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        """Normalize optional descriptions while preserving absent values."""
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ProjectUpdateRequest(ProjectCreateRequest):
    """Admin project update request."""


class AdminUserCreateRequest(BaseModel):
    """Admin-managed standard user creation request."""

    email: str = Field(min_length=1, max_length=320)
    display_name: str = Field(min_length=1, max_length=255)
    initial_password: str = Field(min_length=8, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email_address(cls, value: str) -> str:
        """Normalize email before persistence and duplicate checks."""
        normalized = normalize_email(value)
        if not normalized:
            raise ValueError("Email is required")
        return normalized

    @field_validator("display_name")
    @classmethod
    def display_name_must_not_be_blank(cls, value: str) -> str:
        """Normalize and reject blank display names."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("Display name is required")
        return normalized


class AdminProjectResponse(BaseModel):
    """Secret-free project representation for admin APIs."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    confluence_base_url: str | None
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class MembershipCreateRequest(BaseModel):
    """Admin project membership assignment request."""

    user_id: UUID
    role: ProjectMembershipRole = "member"


class AdminMembershipResponse(BaseModel):
    """Secret-free membership representation for admin APIs."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    user_id: UUID
    role: str
    created_at: datetime
    updated_at: datetime


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    _admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> list[User]:
    """List users for active admins without exposing password hashes."""
    return list(db.execute(select(User).order_by(User.email)).scalars())


@router.post("/users", response_model=AdminUserResponse)
async def create_user(
    request: AdminUserCreateRequest,
    _admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> User:
    """Create a standard active user from the admin dashboard."""
    if get_user_by_email(db, request.email) is not None:
        raise HTTPException(status_code=409, detail="User already exists")

    user = User(
        email=request.email,
        display_name=request.display_name,
        password_hash=hash_password(request.initial_password),
        role="standard",
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="User already exists") from exc
    except DuplicateUserError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="User already exists") from exc
    db.refresh(user)
    return user


@router.post("/projects", response_model=AdminProjectResponse)
async def create_project(
    request: ProjectCreateRequest,
    admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> Project:
    """Create a project owned by the current admin user."""
    project = Project(
        name=request.name,
        description=request.description,
        confluence_base_url=request.confluence_base_url,
        created_by_user_id=admin.id,
    )
    db.add(project)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Project already exists") from exc
    db.refresh(project)
    return project


@router.put("/projects/{project_id}", response_model=AdminProjectResponse)
async def update_project(
    project_id: UUID,
    request: ProjectUpdateRequest,
    _admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> Project:
    """Update project details from the admin dashboard."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    project.name = request.name
    project.description = request.description
    project.confluence_base_url = request.confluence_base_url
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Project already exists") from exc
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: UUID,
    _admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> None:
    """Delete a project and its memberships from the admin dashboard."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    try:
        db.query(ProjectMembership).filter(ProjectMembership.project_id == project_id).delete(
            synchronize_session=False
        )
        db.query(Project).filter(Project.id == project_id).delete(synchronize_session=False)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Project cannot be deleted") from exc
    return None


@router.post(
    "/projects/{project_id}/memberships",
    response_model=AdminMembershipResponse,
)
async def assign_project_membership(
    project_id: UUID,
    request: MembershipCreateRequest,
    _admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> ProjectMembership:
    """Create or update a project membership deterministically for admins."""
    project = db.get(Project, project_id)
    target_user = db.get(User, request.user_id)
    if project is None or target_user is None or not target_user.is_active:
        raise HTTPException(status_code=404, detail="Resource not found")

    membership = db.execute(
        select(ProjectMembership).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == request.user_id,
        )
    ).scalar_one_or_none()

    if membership is None:
        membership = ProjectMembership(
            project_id=project_id, user_id=request.user_id, role=request.role
        )
        db.add(membership)
    else:
        membership.role = request.role

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        membership = db.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.user_id == request.user_id,
            )
        ).scalar_one()
        membership.role = request.role
        db.commit()

    db.refresh(membership)
    return membership


@router.delete("/projects/{project_id}/memberships/{user_id}", status_code=204)
async def remove_project_membership(
    project_id: UUID,
    user_id: UUID,
    _admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> None:
    """Remove a user's project membership from the admin dashboard."""
    deleted = (
        db.query(ProjectMembership)
        .filter(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == user_id,
        )
        .delete(synchronize_session=False)
    )
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Resource not found")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Membership cannot be removed") from exc
    return None
