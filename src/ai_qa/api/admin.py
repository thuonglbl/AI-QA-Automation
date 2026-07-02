"""Admin-only project and user management API routes."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from starlette.background import BackgroundTask

from ai_qa.admin.model_sync import ModelSyncResult, sync_models_and_benchmarks
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import require_admin
from ai_qa.auth.service import (
    ADMIN_ROLE,
    PROJECT_ADMIN_ROLE,
    STANDARD_ROLE,
    get_user_by_email,
    normalize_email,
)
from ai_qa.config import AppSettings
from ai_qa.db.models import (
    DiscoveredModelSnapshot,
    ModelBenchmarkScore,
    Project,
    ProjectMembership,
    User,
)

DbSessionDependency = Depends(get_db_session_dependency)
AdminDependency = Depends(require_admin)
# "project_admin" lets a member administer their project (config/accounts/membership).
ProjectMembershipRole = Literal["member", "owner", "project_admin"]
# A platform admin may only create project_admin / standard users — NOT another "admin"
# (the platform admin is provisioned solely by bootstrap_admin). Omitting "admin" here
# makes an attempt fail validation at the API boundary.
AdminUserRole = Literal["project_admin", "standard"]

router = APIRouter(prefix="/admin", tags=["admin"])

# Resolve the frontend directory relative to this file's location
# src/ai_qa/api/admin.py → project root is 3 levels up → frontend/
_PROJECT_ROOT = Path(__file__).parents[3]
_FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", _PROJECT_ROOT / "frontend"))


SUPPORTED_LANGUAGES = frozenset(["en", "fr", "it", "es", "de", "vi"])


class AdminUserProjectMembershipResponse(BaseModel):
    """Display-safe project membership summary for admin user lists."""

    id: UUID
    project_id: UUID
    project_name: str
    role: str
    created_at: datetime
    updated_at: datetime


class AdminUserResponse(BaseModel):
    """Secret-free user representation for admin APIs."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str
    role: str
    is_active: bool
    timezone: str = "UTC"
    conversation_language: str = "en"
    created_at: datetime
    updated_at: datetime
    project_memberships: list[AdminUserProjectMembershipResponse] = Field(default_factory=list)


class Environment(BaseModel):
    """One named target environment for the app under test (name + URL + login config).

    Both name and url are length-bounded but NOT min-length-constrained here: incomplete rows
    (a name with no URL yet, or vice-versa) are dropped by ``ProjectCreateRequest``'s
    cleaning validator rather than rejected, so admins can add/edit rows freely.
    """

    name: str = Field(max_length=64)
    url: str = Field(max_length=512)
    login_type: str = Field(default="standard", max_length=32)
    login_hint: str = Field(default="", max_length=128)


class ProjectCreateRequest(BaseModel):
    """Admin project creation request."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    confluence_base_url: str | None = Field(default=None, max_length=512)
    jira_base_url: str | None = Field(default=None, max_length=512)
    enabled_providers: list[str] = Field(default_factory=list)
    environments: list[Environment] = Field(default_factory=list)
    app_roles: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        """Normalize and reject project names that are blank after trimming."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("Project name is required")
        return normalized

    @field_validator("environments")
    @classmethod
    def normalize_environments(cls, value: list[Environment]) -> list[Environment]:
        """Trim entries, drop incomplete rows, and reject duplicate names.

        All environments are optional (an empty list is valid). A row is kept only when
        BOTH name and URL are non-blank; duplicates (case-insensitive name) are an error.
        """
        cleaned: list[Environment] = []
        seen: set[str] = set()
        for env in value:
            name = env.name.strip()
            url = env.url.strip()
            if not name or not url:
                continue
            key = name.lower()
            if key in seen:
                raise ValueError(f"Duplicate environment name: {name!r}")
            seen.add(key)
            cleaned.append(
                Environment(
                    name=name,
                    url=url,
                    login_type=env.login_type or "standard",
                    login_hint=(env.login_hint or "").strip(),
                )
            )
        return cleaned

    @field_validator("app_roles")
    @classmethod
    def normalize_app_roles(cls, value: list[str]) -> list[str]:
        """Trim role names, drop blanks, reject case-insensitive duplicates."""
        cleaned: list[str] = []
        seen: set[str] = set()
        for role in value:
            name = role.strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                raise ValueError(f"Duplicate role name: {name!r}")
            seen.add(key)
            cleaned.append(name)
        return cleaned

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        """Normalize optional descriptions while preserving absent values."""
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def normalize_links(self) -> ProjectCreateRequest:
        """Normalize blank links to None. The platform admin now creates a project with
        only name + description; the Confluence/Jira links, providers, environments,
        app_roles and the "at least one link / provider" invariants are owned by the
        project_admin config endpoint (``PUT /project-admin/projects/{id}/config``)."""
        self.confluence_base_url = (self.confluence_base_url or "").strip() or None
        self.jira_base_url = (self.jira_base_url or "").strip() or None
        return self


class ProjectUpdateRequest(ProjectCreateRequest):
    """Admin project update request."""


class AdminUserCreateRequest(BaseModel):
    """Admin-managed user creation request."""

    email: str = Field(min_length=1, max_length=320)
    display_name: str | None = Field(default=None, max_length=255)
    role: AdminUserRole = "standard"
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    conversation_language: str = Field(default="en", min_length=2, max_length=10)
    # A project_admin is linked to a project at creation via a ProjectMembership(role=
    # "project_admin"). Required for project_admin, forbidden for standard (see validator).
    project_id: UUID | None = Field(default=None)

    @field_validator("email")
    @classmethod
    def normalize_email_address(cls, value: str) -> str:
        """Normalize email before persistence and duplicate checks."""
        normalized = normalize_email(value)
        if not normalized:
            raise ValueError("Email is required")
        return normalized

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Reject anything that is not a valid IANA timezone name."""
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        candidate = value.strip()
        try:
            ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Invalid timezone: {value!r}") from exc
        return candidate

    @field_validator("conversation_language")
    @classmethod
    def validate_conversation_language(cls, value: str) -> str:
        """Reject anything outside the supported language set."""
        candidate = value.strip().lower()
        if candidate not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {value!r}")
        return candidate

    @field_validator("display_name")
    @classmethod
    def display_name_must_not_be_blank(cls, value: str | None) -> str | None:
        """Normalize and reject blank display names."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Display name cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_project_link(self) -> AdminUserCreateRequest:
        """A project_admin must be linked to a project; a standard user must not be."""
        if self.role == PROJECT_ADMIN_ROLE and self.project_id is None:
            raise ValueError("A project is required when creating a project admin.")
        if self.role != PROJECT_ADMIN_ROLE and self.project_id is not None:
            raise ValueError("A standard user cannot be linked to a project at creation.")
        return self


class AdminUserUpdateRequest(BaseModel):
    """Admin-managed user update request.

    ``role`` is the same ``Literal["project_admin", "standard"]`` as create — it can
    never carry ``"admin"``, so promoting a user to platform admin is rejected at the
    schema boundary (422). ``project_id`` is only meaningful for a standard→project_admin
    transition; it is forbidden when the target role is ``standard``.
    """

    display_name: str = Field(min_length=1, max_length=255)
    role: AdminUserRole
    timezone: str = Field(min_length=1, max_length=64)
    conversation_language: str = Field(min_length=2, max_length=10)
    is_active: bool
    # Single-project link (legacy; still accepted for a standard->project_admin promotion).
    project_id: UUID | None = Field(default=None)
    # The full administered-project set for a project_admin (Epic 23, story 23.5). When
    # provided it REPLACES the user's project_admin membership set (1..n, idempotent).
    # Takes precedence over project_id. Omit to leave memberships untouched (e.g. when
    # editing only name/timezone of an existing project_admin).
    project_ids: list[UUID] | None = Field(default=None)

    @field_validator("display_name")
    @classmethod
    def display_name_must_not_be_blank(cls, value: str) -> str:
        """Normalize and reject blank display names."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("Display name is required")
        return normalized

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Reject anything that is not a valid IANA timezone name."""
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        candidate = value.strip()
        try:
            ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Invalid timezone: {value!r}") from exc
        return candidate

    @field_validator("conversation_language")
    @classmethod
    def validate_conversation_language(cls, value: str) -> str:
        """Reject anything outside the supported language set."""
        candidate = value.strip().lower()
        if candidate not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {value!r}")
        return candidate

    @model_validator(mode="after")
    def validate_project_link(self) -> AdminUserUpdateRequest:
        """A standard user cannot be linked to a project (single or set)."""
        if self.role != PROJECT_ADMIN_ROLE and (
            self.project_id is not None or self.project_ids is not None
        ):
            raise ValueError("A standard user cannot be linked to a project.")
        return self


class AdminProjectResponse(BaseModel):
    """Secret-free project representation for admin APIs."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    confluence_base_url: str | None
    jira_base_url: str | None
    enabled_providers: list[str]
    environments: list[Environment] = Field(default_factory=list)
    app_roles: list[str] = Field(default_factory=list)
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class AdminConfigResponse(BaseModel):
    """Admin dashboard configuration and feature flags."""

    enable_model_benchmark_sync: bool


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


def _to_admin_user_response(user: User) -> AdminUserResponse:
    """Build a display-safe admin user response with project memberships."""
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        timezone=user.timezone,
        conversation_language=user.conversation_language,
        created_at=user.created_at,
        updated_at=user.updated_at,
        project_memberships=[
            AdminUserProjectMembershipResponse(
                id=membership.id,
                project_id=membership.project_id,
                project_name=membership.project.name,
                role=membership.role,
                created_at=membership.created_at,
                updated_at=membership.updated_at,
            )
            for membership in sorted(user.memberships, key=lambda item: item.project.name.lower())
        ],
    )


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    _admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> list[AdminUserResponse]:
    """List users for active admins without exposing password hashes or secrets."""
    # Eager-load memberships → project so building each user's project_memberships
    # (with project_name) does not trigger per-row lazy loads (N+1).
    users = list(
        db.execute(
            select(User)
            .options(selectinload(User.memberships).selectinload(ProjectMembership.project))
            .order_by(User.email)
        )
        .scalars()
        .unique()
    )
    return [_to_admin_user_response(user) for user in users]


@router.get("/config", response_model=AdminConfigResponse)
async def get_admin_config(
    request: Request,
    _admin: User = AdminDependency,
) -> AdminConfigResponse:
    """Return configuration and feature flags for the admin dashboard."""
    settings = getattr(request.app.state, "settings", None) or AppSettings()
    return AdminConfigResponse(
        enable_model_benchmark_sync=settings.enable_model_benchmark_sync,
    )


@router.post("/users", response_model=AdminUserResponse)
async def create_user(
    request: AdminUserCreateRequest,
    _admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> AdminUserResponse:
    """Create an active user from the admin dashboard.

    A ``project_admin`` is linked to an existing project in the SAME transaction via a
    ``ProjectMembership(role="project_admin")`` — both rows roll back together if the
    commit fails. The link is many-to-many: no uniqueness is enforced here, so a project
    may have several project_admins (further assignments use the membership endpoints).
    """
    if get_user_by_email(db, request.email) is not None:
        raise HTTPException(status_code=409, detail="User already exists")

    # Validate the project up front (the request model guarantees project_id is set for
    # a project_admin) so a missing project fails before any insert.
    if request.role == PROJECT_ADMIN_ROLE:
        assert request.project_id is not None
        if db.get(Project, request.project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found")

    user = User(
        email=request.email,
        display_name=request.display_name or request.email.split("@", 1)[0],
        role=request.role,
        is_active=True,
        timezone=request.timezone,
        conversation_language=request.conversation_language,
    )
    db.add(user)
    try:
        if request.role == PROJECT_ADMIN_ROLE:
            assert request.project_id is not None
            db.flush()  # assign user.id without committing the transaction
            db.add(
                ProjectMembership(
                    project_id=request.project_id,
                    user_id=user.id,
                    role=PROJECT_ADMIN_ROLE,
                )
            )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="User already exists") from exc
    db.refresh(user)
    return _to_admin_user_response(user)


def _resolve_target_project_ids(request: AdminUserUpdateRequest) -> set[UUID] | None:
    """The administered-project set the request asks for (None => leave unchanged)."""
    if request.project_ids is not None:
        return set(request.project_ids)
    if request.project_id is not None:
        return {request.project_id}
    return None


def _reconcile_project_admin_memberships(db: Session, user: User, target_ids: set[UUID]) -> None:
    """Make the user's ``project_admin`` membership set exactly ``target_ids``.

    Adds missing rows (promoting an existing member/owner row in place to satisfy the
    unique ``(project_id, user_id)`` constraint), removes ``project_admin`` rows for
    de-selected projects, and never touches non-project_admin rows or other users.
    """
    rows = (
        db.execute(
            select(ProjectMembership).where(
                ProjectMembership.user_id == user.id,
                ProjectMembership.role == PROJECT_ADMIN_ROLE,
            )
        )
        .scalars()
        .all()
    )
    existing_by_pid = {m.project_id: m for m in rows}
    for pid in target_ids - set(existing_by_pid):
        row = db.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == pid,
                ProjectMembership.user_id == user.id,
            )
        ).scalar_one_or_none()
        if row is None:
            db.add(ProjectMembership(project_id=pid, user_id=user.id, role=PROJECT_ADMIN_ROLE))
        else:
            row.role = PROJECT_ADMIN_ROLE
    for pid in set(existing_by_pid) - target_ids:
        db.delete(existing_by_pid[pid])


@router.put("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: UUID,
    request: AdminUserUpdateRequest,
    admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> AdminUserResponse:
    """Update a user from the admin dashboard.

    The platform admin account is immutable (no edit, no demote; promotion to admin is
    impossible at the schema boundary), and an admin cannot deactivate its own account.
    Role flips maintain the project_admin membership linkage (many-to-many):
    standard→project_admin links/updates a membership on the chosen project;
    project_admin→standard removes all of the user's project_admin memberships.
    """
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if target.role == ADMIN_ROLE:
        if not request.is_active and target.is_active:
            raise HTTPException(
                status_code=403, detail="The platform admin account cannot be deactivated."
            )
        old_role = target.role
        new_role = target.role
    else:
        old_role = target.role
        new_role = request.role

    if target.id == admin.id and not request.is_active:
        raise HTTPException(status_code=403, detail="You cannot deactivate your own account.")
    if new_role == PROJECT_ADMIN_ROLE:
        # Multi-project assignment (Epic 23, story 23.5): set the administered-project
        # set to 1..n. project_ids replaces the set; project_id is the legacy single.
        if request.project_ids is not None:
            target_ids = set(request.project_ids)
            if not target_ids:
                raise HTTPException(
                    status_code=422,
                    detail="A project admin must administer at least one project.",
                )
            for pid in target_ids:
                if db.get(Project, pid) is None:
                    raise HTTPException(status_code=404, detail="Project not found")
            _reconcile_project_admin_memberships(db, target, target_ids)
        elif request.project_id is not None:
            # Legacy 16-13 semantics: add/keep the selected project, do not delete others
            if db.get(Project, request.project_id) is None:
                raise HTTPException(status_code=404, detail="Project not found")
            row = db.execute(
                select(ProjectMembership).where(
                    ProjectMembership.project_id == request.project_id,
                    ProjectMembership.user_id == target.id,
                )
            ).scalar_one_or_none()
            if row is None:
                db.add(
                    ProjectMembership(
                        project_id=request.project_id, user_id=target.id, role=PROJECT_ADMIN_ROLE
                    )
                )
            else:
                row.role = PROJECT_ADMIN_ROLE
        else:
            if old_role == STANDARD_ROLE:
                raise HTTPException(
                    status_code=422,
                    detail="A project is required to make this user a project admin.",
                )
    elif old_role == PROJECT_ADMIN_ROLE and new_role == STANDARD_ROLE:
        db.query(ProjectMembership).filter(
            ProjectMembership.user_id == target.id,
            ProjectMembership.role == PROJECT_ADMIN_ROLE,
        ).delete(synchronize_session=False)

    target.display_name = request.display_name
    target.timezone = request.timezone
    target.conversation_language = request.conversation_language
    target.is_active = request.is_active
    target.role = new_role
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Could not save the user due to a data conflict."
        ) from exc
    db.refresh(target)
    return _to_admin_user_response(target)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID,
    admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> None:
    """Delete a user from the admin dashboard.

    The platform admin account is immutable and an admin cannot delete itself. FK
    cascades (memberships, secrets, captured sessions) clean up the user's rows.
    """
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if target.role == ADMIN_ROLE:
        raise HTTPException(
            status_code=403, detail="The platform admin account cannot be modified."
        )
    if target.id == admin.id:
        raise HTTPException(status_code=403, detail="You cannot delete your own account.")

    db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="User cannot be deleted") from exc
    return None


@router.post("/projects", response_model=AdminProjectResponse)
async def create_project(
    request: ProjectCreateRequest,
    admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> Project:
    """Create a project owned by the current admin user."""
    if (
        db.execute(select(Project).where(Project.name == request.name)).scalar_one_or_none()
        is not None
    ):
        raise HTTPException(status_code=409, detail="Project name already exists")

    project = Project(
        name=request.name,
        description=request.description,
        confluence_base_url=request.confluence_base_url,
        jira_base_url=request.jira_base_url,
        enabled_providers=request.enabled_providers,
        environments=[env.model_dump() for env in request.environments],
        app_roles=request.app_roles,
        created_by_user_id=admin.id,
    )
    db.add(project)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Only claim a duplicate when a same-name row genuinely exists; other integrity
        # violations (e.g. a NOT-NULL constraint) must not masquerade as a name clash.
        duplicate = db.execute(
            select(Project).where(Project.name == request.name)
        ).scalar_one_or_none()
        detail = (
            "Project name already exists"
            if duplicate is not None
            else "Could not save the project due to a data conflict."
        )
        raise HTTPException(status_code=409, detail=detail) from exc
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

    name_conflict = db.execute(
        select(Project).where(Project.name == request.name, Project.id != project_id)
    ).scalar_one_or_none()
    if name_conflict is not None:
        raise HTTPException(status_code=409, detail="Project name already exists")

    project.name = request.name
    project.description = request.description
    project.confluence_base_url = request.confluence_base_url
    project.jira_base_url = request.jira_base_url
    project.enabled_providers = request.enabled_providers
    project.environments = [env.model_dump() for env in request.environments]
    project.app_roles = request.app_roles
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Distinguish a real duplicate-name race from any other integrity violation
        # (exclude this project's own row from the re-check).
        duplicate = db.execute(
            select(Project).where(Project.name == request.name, Project.id != project_id)
        ).scalar_one_or_none()
        detail = (
            "Project name already exists"
            if duplicate is not None
            else "Could not save the project due to a data conflict."
        )
        raise HTTPException(status_code=409, detail=detail) from exc
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: UUID,
    _admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> None:
    """Delete a project, its memberships, and S3 storage from the admin dashboard."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    # Best-effort S3 cleanup before DB delete
    try:
        from ai_qa.api.artifacts import get_artifact_storage

        storage = get_artifact_storage()
        storage.delete_prefix(f"projects/{project_id}/")
    except Exception:
        pass  # Storage cleanup is best-effort; DB delete proceeds regardless

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


class E2ERunStatusResponse(BaseModel):
    """Current state of the (asynchronous) E2E test run.

    A full Playwright suite takes minutes; holding the HTTP request open that long
    is severed by reverse proxies (504). So the run executes in the background and
    the frontend polls this state. ``exit_code``/``passed`` are null until the run
    completes.
    """

    status: Literal["idle", "running", "completed"]
    exit_code: int | None = None
    passed: bool | None = None
    report_available: bool = False
    stdout: str = ""
    stderr: str = ""


# In-process run state. The deploy runs a single uvicorn worker, so a module-level
# holder is shared across requests; the background task reference is kept to stop
# it being garbage-collected mid-run.
_e2e_state = E2ERunStatusResponse(status="idle")
_e2e_task: asyncio.Task[None] | None = None


def _set_e2e_state(
    status: Literal["idle", "running", "completed"],
    *,
    exit_code: int | None = None,
    passed: bool | None = None,
    report_available: bool = False,
    stdout: str = "",
    stderr: str = "",
) -> None:
    _e2e_state.status = status
    _e2e_state.exit_code = exit_code
    _e2e_state.passed = passed
    _e2e_state.report_available = report_available
    _e2e_state.stdout = stdout
    _e2e_state.stderr = stderr


def _build_e2e_command_and_env(npx_cmd: str) -> tuple[list[str], dict[str, str]]:
    """Build the Playwright command + environment for the in-app runner.

    The runner always drives servers that are ALREADY running (locally uvicorn +
    Vite; on a deployed server this backend container + the Nginx frontend), so
    Playwright must never boot its own pair (``E2E_DISABLE_WEBSERVER=1``) — that
    was the local "port 8000 already used" failure. Headed mode + slow motion only
    make sense locally; a deployed server (``E2E_SERVER_MODE=1``) is headless with
    no X display, needs the container sandbox disabled, and ignores the deployed
    app's (often self-signed) TLS cert.
    """
    from dotenv import dotenv_values

    # Dynamically read .env so local developers don't need to restart the backend
    # when toggling E2E_SERVER_MODE or E2E_HEADED.
    env_vars = dotenv_values(_PROJECT_ROOT / ".env")

    def get_env_val(key: str, default: str) -> str:
        # Priority: .env file (live changes), then explicit os.environ, then default
        val = env_vars.get(key)
        if val is not None:
            return val
        if key in os.environ:
            return os.environ[key]
        return default

    server_mode = get_env_val("E2E_SERVER_MODE", "1") == "1"
    headed = not server_mode and get_env_val("E2E_HEADED", "1") != "0"

    cmd = [npx_cmd, "playwright", "test", "--workers=1"]
    if headed:
        cmd.append("--headed")

    run_env = {
        **os.environ,
        "FORCE_COLOR": "0",
        "PLAYWRIGHT_HTML_REPORT_OPEN": "never",
        "PLAYWRIGHT_SLOW_MO": "500" if headed else "0",
        "E2E_DISABLE_WEBSERVER": "1",
    }
    if server_mode:
        # setdefault lets an operator override either via the container env.
        run_env.setdefault("E2E_NO_SANDBOX", "1")
        run_env.setdefault("PLAYWRIGHT_IGNORE_HTTPS_ERRORS", "1")
    return cmd, run_env


def _run_e2e_subprocess(cmd: list[str], run_env: dict[str, str]) -> tuple[bytes, bytes, int]:
    result = subprocess.run(
        cmd,
        cwd=str(_FRONTEND_DIR),
        capture_output=True,
        timeout=900,
        env=run_env,
    )
    return result.stdout, result.stderr, result.returncode


async def _run_e2e_background(cmd: list[str], run_env: dict[str, str]) -> None:
    """Run the suite off the event loop and record the outcome in ``_e2e_state``."""
    try:
        try:
            stdout_bytes, stderr_bytes, returncode = await asyncio.to_thread(
                _run_e2e_subprocess, cmd, run_env
            )
        except subprocess.TimeoutExpired as exc:
            _set_e2e_state(
                "completed",
                exit_code=-1,
                passed=False,
                stdout=exc.stdout.decode(errors="replace") if exc.stdout else "",
                stderr="E2E test run timed out after 15 minutes.",
            )
            return
        stdout = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
        stderr = stderr_bytes.decode(errors="replace") if stderr_bytes else ""
        report_dir = _FRONTEND_DIR / "playwright-report"
        _set_e2e_state(
            "completed",
            exit_code=returncode,
            passed=returncode == 0,
            report_available=(report_dir / "index.html").exists(),
            stdout=stdout[-8000:] if stdout else "",  # cap at 8 KB
            stderr=stderr[-4000:] if stderr else "",
        )
    except Exception:
        import traceback

        _set_e2e_state(
            "completed",
            exit_code=-1,
            passed=False,
            stderr=f"Error executing npx:\n{traceback.format_exc()}",
        )
    finally:
        # Guarantee the state never stays "running" once the task exits — even via
        # an unexpected path (e.g. CancelledError at loop shutdown). Otherwise a
        # stuck "running" would block every future run until a process restart.
        if _e2e_state.status == "running":
            _set_e2e_state(
                "completed",
                exit_code=-1,
                passed=False,
                stderr="E2E run ended without producing a result.",
            )


@router.post("/tests/e2e", status_code=202, response_model=E2ERunStatusResponse)
async def run_e2e_tests(
    request: Request,
    _admin: User = AdminDependency,
) -> E2ERunStatusResponse:
    """Start a Playwright E2E run in the background and return immediately.

    Only admins can invoke this. The suite takes minutes, so this returns at once
    (HTTP 202) and the run proceeds in the background — poll
    GET /admin/tests/e2e/status for progress/result, then
    GET /admin/tests/e2e/report for the HTML report. A second request while a run
    is in progress is a no-op that just returns the running state.
    """
    global _e2e_task
    # Only refuse a new run if a previous one is genuinely still alive; if the task
    # died/was cancelled without updating the state, recover and start fresh.
    if _e2e_state.status == "running" and _e2e_task is not None and not _e2e_task.done():
        return _e2e_state.model_copy()

    if not _FRONTEND_DIR.is_dir():
        _set_e2e_state("completed", stderr=f"Frontend directory not found: {_FRONTEND_DIR}")
        return _e2e_state.model_copy()

    npx_cmd = shutil.which("npx")
    if not npx_cmd:
        _set_e2e_state(
            "completed", stderr="npx not found. Ensure Node.js and Playwright are installed."
        )
        return _e2e_state.model_copy()

    cmd, run_env = _build_e2e_command_and_env(npx_cmd)
    _set_e2e_state("running")
    _e2e_task = asyncio.create_task(_run_e2e_background(cmd, run_env))
    return _e2e_state.model_copy()


@router.get("/tests/e2e/status", response_model=E2ERunStatusResponse)
async def get_e2e_status(_admin: User = AdminDependency) -> E2ERunStatusResponse:
    """Return the current/last E2E run state. Poll while ``status == 'running'``."""
    return _e2e_state.model_copy()


@router.get("/tests/e2e/report/view/{file_path:path}")
async def view_e2e_report(
    file_path: str,
    _admin: User = AdminDependency,
) -> FileResponse:
    """Serve the Playwright HTML report files directly in the browser.

    Admin-only: the report bundles Playwright traces, screenshots, videos, and
    captured request/response data from E2E runs against real DB projects. The
    HTML opens in a browser tab and authenticates via the session cookie.
    """
    import mimetypes

    report_dir = _FRONTEND_DIR / "playwright-report"
    if not file_path:
        file_path = "index.html"

    target = (report_dir / file_path).resolve()

    # Prevent directory traversal
    try:
        target.relative_to(report_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden path") from None

    if not target.is_file():
        raise HTTPException(status_code=404, detail="Report file not found")

    # Ensure correct MIME type so browsers render HTML/CSS/JS properly
    content_type, _ = mimetypes.guess_type(str(target))
    if not content_type:
        content_type = "application/octet-stream"

    return FileResponse(target, media_type=content_type)


@router.get("/tests/e2e/report")
async def download_e2e_report(
    _admin: User = AdminDependency,
) -> FileResponse:
    """Download the latest Playwright HTML report as a zip archive.

    Returns 404 if no report has been generated yet.
    Only admins can download the report.
    """
    import io
    import zipfile

    report_dir = _FRONTEND_DIR / "playwright-report"
    if not report_dir.is_dir() or not (report_dir / "index.html").exists():
        raise HTTPException(
            status_code=404,
            detail="No E2E report available. Run the tests first.",
        )

    # Build an in-memory zip of the entire playwright-report directory
    zip_buffer = io.BytesIO()
    try:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in report_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(report_dir))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create zip file: {exc}") from exc
    zip_buffer.seek(0)

    # Write to a temp file and serve — FileResponse requires a real path
    import os
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.write(zip_buffer.read())
    tmp.flush()
    tmp.close()

    return FileResponse(
        path=tmp.name,
        media_type="application/zip",
        filename="playwright-report.zip",
        background=BackgroundTask(os.remove, tmp.name),
        headers={"Cache-Control": "no-cache"},
    )


# ---------------------------------------------------------------------------
# Model benchmark overrides — operator Tier-0 scores for Alice model selection
# ---------------------------------------------------------------------------

__SKIP_WORD_2_Modcorppability__ = Literal["global", "reasoning", "vision", "instruction", "coding", "fast"]
_DEFAULT_CAPABILITY: __SKIP_WORD_2_Modcorppability__ = "global"


class ModelScoreResponse(BaseModel):
    """A persisted operator benchmark score."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: UUID
    model_id: str
    capability: str
    score: float
    note: str | None
    updated_by_user_id: UUID | None
    updated_at: datetime


class ModelScoreUpsertRequest(BaseModel):
    """Create/replace a benchmark score for a (model_id, capability)."""

    model_config = ConfigDict(protected_namespaces=())

    model_id: str = Field(min_length=1, max_length=255)
    capability: __SKIP_WORD_2_Modcorppability__ = _DEFAULT_CAPABILITY
    score: float = Field(ge=0, le=100)
    note: str | None = Field(default=None, max_length=2000)


class ModelScoreDeleteRequest(BaseModel):
    """Identify a benchmark score to delete."""

    model_config = ConfigDict(protected_namespaces=())

    model_id: str = Field(min_length=1, max_length=255)
    capability: __SKIP_WORD_2_Modcorppability__ = _DEFAULT_CAPABILITY


class DiscoveredModelResponse(BaseModel):
    """A discovered model with its selection provenance for the admin dashboard."""

    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    display_name: str | None
    provider: str | None
    supports_vision: bool | None
    last_seen_at: datetime
    tier_source: str  # admin | curated | parsed
    unbenchmarked: bool
    scores: list[ModelScoreResponse] = Field(default_factory=list)


def _is_curated_model(model_id: str) -> bool:
    """True if the model id matches any curated benchmark preference substring."""
    from ai_qa.agents.alice import _AGENT_CAPABILITY_RANK

    low = model_id.lower()
    return any(pref in low for ranking in _AGENT_CAPABILITY_RANK.values() for pref in ranking)


@router.get("/discovered-models", response_model=list[DiscoveredModelResponse])
async def list_discovered_models(
    _admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> list[DiscoveredModelResponse]:
    """List the last-discovered model pool with selection provenance + scores.

    A model is flagged ``unbenchmarked`` when it has no operator score AND matches
    no curated benchmark list — i.e. it would be selected only by the parsed
    heuristic. These are the models an admin should consider scoring.
    """
    snapshots = list(
        db.execute(select(DiscoveredModelSnapshot).order_by(DiscoveredModelSnapshot.model_id))
        .scalars()
        .unique()
    )
    scores = list(db.execute(select(ModelBenchmarkScore)).scalars().unique())
    scores_by_model: dict[str, list[ModelBenchmarkScore]] = {}
    for score in scores:
        scores_by_model.setdefault(score.model_id, []).append(score)

    out: list[DiscoveredModelResponse] = []
    for snap in snapshots:
        model_scores = scores_by_model.get(snap.model_id, [])
        if model_scores:
            source = "admin"
        elif _is_curated_model(snap.model_id):
            source = "curated"
        else:
            source = "parsed"
        out.append(
            DiscoveredModelResponse(
                model_id=snap.model_id,
                display_name=snap.display_name,
                provider=snap.provider,
                supports_vision=snap.supports_vision,
                last_seen_at=snap.last_seen_at,
                tier_source=source,
                unbenchmarked=(source == "parsed"),
                scores=[ModelScoreResponse.model_validate(s) for s in model_scores],
            )
        )
    return out


@router.get("/model-scores", response_model=list[ModelScoreResponse])
async def list_model_scores(
    _admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> list[ModelScoreResponse]:
    """List all operator benchmark scores."""
    rows = list(
        db.execute(
            select(ModelBenchmarkScore).order_by(
                ModelBenchmarkScore.model_id, ModelBenchmarkScore.capability
            )
        )
        .scalars()
        .unique()
    )
    return [ModelScoreResponse.model_validate(row) for row in rows]


@router.put("/model-scores", response_model=ModelScoreResponse)
async def upsert_model_score(
    request: ModelScoreUpsertRequest,
    _admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> ModelBenchmarkScore:
    """Create or replace the benchmark score for a (model_id, capability)."""
    existing = db.execute(
        select(ModelBenchmarkScore).where(
            ModelBenchmarkScore.model_id == request.model_id,
            ModelBenchmarkScore.capability == request.capability,
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = ModelBenchmarkScore(
            model_id=request.model_id,
            capability=request.capability,
            score=request.score,
            note=request.note,
            updated_by_user_id=_admin.id,
        )
        db.add(existing)
    else:
        existing.score = request.score
        existing.note = request.note
        existing.updated_by_user_id = _admin.id

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.execute(
            select(ModelBenchmarkScore).where(
                ModelBenchmarkScore.model_id == request.model_id,
                ModelBenchmarkScore.capability == request.capability,
            )
        ).scalar_one()
        existing.score = request.score
        existing.note = request.note
        existing.updated_by_user_id = _admin.id
        db.commit()

    db.refresh(existing)
    return existing


@router.delete("/model-scores", status_code=204)
async def delete_model_score(
    request: ModelScoreDeleteRequest,
    _admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> None:
    """Delete the benchmark score for a (model_id, capability)."""
    deleted = (
        db.query(ModelBenchmarkScore)
        .filter(
            ModelBenchmarkScore.model_id == request.model_id,
            ModelBenchmarkScore.capability == request.capability,
        )
        .delete(synchronize_session=False)
    )
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Score not found")
    db.commit()
    return None


@router.post("/models/sync", response_model=ModelSyncResult)
async def sync_models(
    request: Request,
    _admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> ModelSyncResult:
    """Discover provider models and sync their benchmark scores in one action.

    Connects to each provider with its server-side ``TEST_<PROVIDER>_KEY``, lists the
    LLM models (skipping embedding/tts/stt families), detects vision support, and
    persists them to ``discovered_models``; then pulls per-capability scores from
    llm-stats.com into ``model_benchmark_scores`` (overwriting any prior scores).

    Admin-only. Runs synchronously (mirrors the E2E runner) and returns a per-provider
    + totals summary. Never leaks the server keys.
    """
    settings = getattr(request.app.state, "settings", None) or AppSettings()
    if not settings.enable_model_benchmark_sync:
        raise HTTPException(
            status_code=403,
            detail="Model and benchmark sync is disabled in this environment.",
        )
    return await sync_models_and_benchmarks(db, settings, triggered_by_user_id=_admin.id)
