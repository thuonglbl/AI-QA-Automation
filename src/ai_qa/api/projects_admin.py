"""Project-admin API: per-project configuration + membership management.

These endpoints move project *configuration* (Confluence/Jira links, providers,
environments, app roles) and *membership* off the platform-admin surface and gate them
with :func:`require_project_admin_for_project` — a platform admin (backdoor) or a
``project_admin`` who holds a ``project_admin`` membership on the target project. The
platform-admin project endpoints keep working during the migration (Slice 2 is additive;
the admin UI is trimmed in the FE slice).
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ai_qa.api.admin import (
    AdminMembershipResponse,
    AdminProjectResponse,
    Environment,
    MembershipCreateRequest,
)
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import get_current_active_user, require_project_admin_for_project
from ai_qa.api.projects import ProjectMembershipSummary
from ai_qa.auth.service import ADMIN_ROLE, PROJECT_ADMIN_ROLE, STANDARD_ROLE
from ai_qa.db.models import Project, ProjectAccount, ProjectMembership, User

LoginType = Literal["SSO", "PASSWORD"]

# The only membership role a project_admin may assign or remove. Elevated roles
# (project_admin, owner) are platform-admin-only operations.
MEMBER_ROLE = "member"

DbSessionDependency = Depends(get_db_session_dependency)
CurrentUserDependency = Depends(get_current_active_user)
ProjectAdminDependency = Depends(require_project_admin_for_project)

router = APIRouter(prefix="/project-admin", tags=["project-admin"])


class ProjectAdminProjectResponse(AdminProjectResponse):
    """Administered-project view: all config fields plus the membership list."""

    memberships: list[ProjectMembershipSummary] = Field(default_factory=list)


class AssignableUserResponse(BaseModel):
    """Display-safe user summary so a project_admin can pick members to assign."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str
    role: str
    is_active: bool


class AccountResponse(BaseModel):
    """A test-login account WITHOUT its password (only whether one is stored)."""

    id: UUID
    environment: str
    role: str
    login_identifier: str
    label: str | None
    has_password: bool


def _account_response(acc: ProjectAccount) -> AccountResponse:
    # Reading encrypted_password decrypts it (EncryptedString); we only expose whether
    # a password exists — never the value.
    return AccountResponse(
        id=acc.id,
        environment=acc.environment,
        role=acc.role,
        login_identifier=acc.login_identifier,
        label=acc.label,
        has_password=bool(acc.encrypted_password),
    )


class AccountUpsertRequest(BaseModel):
    environment: str = Field(min_length=1, max_length=64)
    role: str = Field(min_length=1, max_length=64)
    login_identifier: str = Field(min_length=1, max_length=320)
    password: str | None = Field(default=None, max_length=512)
    label: str | None = Field(default=None, max_length=255)


class ProjectConfigRequest(BaseModel):
    """Project-admin-owned configuration (everything except name/description)."""

    confluence_base_url: str | None = Field(default=None, max_length=512)
    jira_base_url: str | None = Field(default=None, max_length=512)
    enabled_providers: list[str] = Field(default_factory=list)
    environments: list[Environment] = Field(default_factory=list)
    app_roles: list[str] = Field(default_factory=list)
    login_type: LoginType = "SSO"

    @field_validator("environments")
    @classmethod
    def normalize_environments(cls, value: list[Environment]) -> list[Environment]:
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
            cleaned.append(Environment(name=name, url=url))
        return cleaned

    @field_validator("app_roles")
    @classmethod
    def normalize_app_roles(cls, value: list[str]) -> list[str]:
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

    @model_validator(mode="after")
    def require_link_and_provider(self) -> ProjectConfigRequest:
        conf = (self.confluence_base_url or "").strip()
        jira = (self.jira_base_url or "").strip()
        if not conf and not jira:
            raise ValueError(
                "No link to extract requirement. Please provide Confluence URL, Jira URL, or both."
            )
        self.confluence_base_url = conf or None
        self.jira_base_url = jira or None
        if not self.enabled_providers:
            raise ValueError("No provider to execute. Please enable at least one provider.")
        return self


@router.get("/projects", response_model=list[ProjectAdminProjectResponse])
async def list_administered_projects(
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> list[Project]:
    """List the projects the caller administers (platform admin → all), with members."""
    if current_user.role == ADMIN_ROLE:
        rows = db.execute(select(Project).options(selectinload(Project.memberships)))
        return list(rows.scalars().unique().all())
    if current_user.role == PROJECT_ADMIN_ROLE:
        rows = db.execute(
            select(Project)
            .options(selectinload(Project.memberships))
            .join(ProjectMembership, ProjectMembership.project_id == Project.id)
            .where(
                ProjectMembership.user_id == current_user.id,
                ProjectMembership.role == PROJECT_ADMIN_ROLE,
            )
        )
        return list(rows.scalars().unique().all())
    raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/users", response_model=list[AssignableUserResponse])
async def list_assignable_users(
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> list[User]:
    """List active users a project_admin can assign to a project (display-safe)."""
    if current_user.role == ADMIN_ROLE:
        pass  # platform admin: full directory
    elif current_user.role == PROJECT_ADMIN_ROLE:
        # A project_admin must actually administer at least one project before they can
        # enumerate the user directory — holding the role alone is not enough.
        administers = db.execute(
            select(ProjectMembership.id).where(
                ProjectMembership.user_id == current_user.id,
                ProjectMembership.role == PROJECT_ADMIN_ROLE,
            )
        ).first()
        if administers is None:
            raise HTTPException(status_code=403, detail="Forbidden")
    else:
        raise HTTPException(status_code=403, detail="Forbidden")
    rows = db.execute(select(User).where(User.is_active.is_(True)))
    return list(rows.scalars().all())


@router.put("/projects/{project_id}/config", response_model=AdminProjectResponse)
async def update_project_config(
    project_id: UUID,
    request: ProjectConfigRequest,
    _admin: User = ProjectAdminDependency,
    db: Session = DbSessionDependency,
) -> Project:
    """Update a project's Confluence/Jira, providers, environments, and app roles."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    project.confluence_base_url = request.confluence_base_url
    project.jira_base_url = request.jira_base_url
    project.enabled_providers = request.enabled_providers
    project.environments = [env.model_dump() for env in request.environments]
    project.app_roles = request.app_roles
    project.login_type = request.login_type
    db.commit()
    db.refresh(project)
    return project


@router.post("/projects/{project_id}/members", response_model=AdminMembershipResponse)
async def add_project_member(
    project_id: UUID,
    request: MembershipCreateRequest,
    _admin: User = ProjectAdminDependency,
    db: Session = DbSessionDependency,
) -> ProjectMembership:
    """Assign (or update) a user's membership on the project."""
    project = db.get(Project, project_id)
    target_user = db.get(User, request.user_id)
    if project is None or target_user is None or not target_user.is_active:
        raise HTTPException(status_code=404, detail="Resource not found")

    # A project_admin may only assign standard users as standard members; promoting a user
    # to project_admin/owner is a platform-admin-only operation. Platform admins are exempt.
    if _admin.role == PROJECT_ADMIN_ROLE:
        if target_user.role != STANDARD_ROLE:
            raise HTTPException(
                status_code=403,
                detail="Project admins can only assign standard users.",
            )
        if request.role != MEMBER_ROLE:
            raise HTTPException(
                status_code=403,
                detail="Project admins can only assign the standard member role.",
            )

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
        # Defense-in-depth: the top guard blocks elevated *target users*; this blocks an
        # elevated *existing row* so a project_admin cannot reach an owner/project_admin
        # membership through the upsert and silently rewrite its role.
        if _admin.role == PROJECT_ADMIN_ROLE and membership.role != MEMBER_ROLE:
            raise HTTPException(
                status_code=403,
                detail="Project admins can only manage standard members.",
            )
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


@router.delete("/projects/{project_id}/members/{user_id}", status_code=204)
async def remove_project_member(
    project_id: UUID,
    user_id: UUID,
    _admin: User = ProjectAdminDependency,
    db: Session = DbSessionDependency,
) -> None:
    """Remove a user's membership from the project."""
    membership = db.execute(
        select(ProjectMembership).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == user_id,
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    # A project_admin may only remove standard members — never themselves, another
    # project_admin, or an owner (those are platform-admin-only). This subsumes the old
    # self-removal guard: a project_admin's own row is never a `member`.
    if _admin.role == PROJECT_ADMIN_ROLE and membership.role != MEMBER_ROLE:
        raise HTTPException(
            status_code=403,
            detail="Project admins can only remove standard members.",
        )
    db.delete(membership)
    db.commit()


@router.get("/projects/{project_id}/accounts", response_model=list[AccountResponse])
async def list_project_accounts(
    project_id: UUID,
    _admin: User = ProjectAdminDependency,
    db: Session = DbSessionDependency,
) -> list[AccountResponse]:
    """List the project's test-login accounts (passwords never returned)."""
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    rows = (
        db.execute(select(ProjectAccount).where(ProjectAccount.project_id == project_id))
        .scalars()
        .all()
    )
    return [_account_response(acc) for acc in rows]


@router.post("/projects/{project_id}/accounts", response_model=AccountResponse)
async def upsert_project_account(
    project_id: UUID,
    request: AccountUpsertRequest,
    _admin: User = ProjectAdminDependency,
    db: Session = DbSessionDependency,
) -> AccountResponse:
    """Create or update the test-login account for one (environment, role)."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    env_names = {str(e.get("name")) for e in (project.environments or []) if isinstance(e, dict)}
    if request.environment not in env_names:
        raise HTTPException(status_code=422, detail="Unknown environment for this project.")
    if request.role not in (project.app_roles or []):
        raise HTTPException(status_code=422, detail="Unknown role for this project.")

    existing = db.execute(
        select(ProjectAccount).where(
            ProjectAccount.project_id == project_id,
            ProjectAccount.environment == request.environment,
            ProjectAccount.role == request.role,
        )
    ).scalar_one_or_none()

    provided_pwd = (request.password or "").strip() or None
    if project.login_type == "SSO":
        # SSO projects never store a password (only the email/username).
        new_pwd: str | None = None
    else:
        # PASSWORD: use the provided password, or keep the existing one on update.
        new_pwd = provided_pwd or (existing.encrypted_password if existing else None)
        if not new_pwd:
            raise HTTPException(
                status_code=422,
                detail="A password is required for a password-login project.",
            )

    if existing is None:
        existing = ProjectAccount(
            project_id=project_id,
            environment=request.environment,
            role=request.role,
            login_identifier=request.login_identifier,
            encrypted_password=new_pwd,
            label=request.label,
        )
        db.add(existing)
    else:
        existing.login_identifier = request.login_identifier
        existing.encrypted_password = new_pwd
        existing.label = request.label
    try:
        db.commit()
    except IntegrityError:
        # Concurrent first-create for the same (project, environment, role): re-select the row
        # the other request inserted and apply this update on top (keeps the upsert idempotent).
        db.rollback()
        existing = db.execute(
            select(ProjectAccount).where(
                ProjectAccount.project_id == project_id,
                ProjectAccount.environment == request.environment,
                ProjectAccount.role == request.role,
            )
        ).scalar_one()
        existing.login_identifier = request.login_identifier
        existing.encrypted_password = new_pwd
        existing.label = request.label
        db.commit()
    db.refresh(existing)
    return _account_response(existing)


@router.delete("/projects/{project_id}/accounts/{account_id}", status_code=204)
async def delete_project_account(
    project_id: UUID,
    account_id: UUID,
    _admin: User = ProjectAdminDependency,
    db: Session = DbSessionDependency,
) -> None:
    """Delete a project test-login account."""
    deleted = (
        db.query(ProjectAccount)
        .filter(
            ProjectAccount.id == account_id,
            ProjectAccount.project_id == project_id,
        )
        .delete(synchronize_session=False)
    )
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Resource not found")
    db.commit()
