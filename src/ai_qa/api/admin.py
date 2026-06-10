"""Admin-only project and user management API routes."""

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
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import require_admin
from ai_qa.auth.password import hash_password
from ai_qa.auth.service import (
    DuplicateUserError,
    get_user_by_email,
    normalize_email,
)
from ai_qa.db.models import Project, ProjectMembership, User

DbSessionDependency = Depends(get_db_session_dependency)
AdminDependency = Depends(require_admin)
ProjectMembershipRole = Literal["member", "owner"]
AdminUserRole = Literal["admin", "standard"]

router = APIRouter(prefix="/admin", tags=["admin"])

# Resolve the frontend directory relative to this file's location
# src/ai_qa/api/admin.py → project root is 3 levels up → frontend/
_PROJECT_ROOT = Path(__file__).parents[3]
_FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", _PROJECT_ROOT / "frontend"))


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
    created_at: datetime
    updated_at: datetime
    project_memberships: list[AdminUserProjectMembershipResponse] = Field(default_factory=list)


class ProjectCreateRequest(BaseModel):
    """Admin project creation request."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    confluence_base_url: str | None = Field(default=None, max_length=512)
    jira_base_url: str | None = Field(default=None, max_length=512)
    enabled_providers: list[str] = Field(default_factory=list)

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

    @model_validator(mode="after")
    def at_least_one_link(self) -> "ProjectCreateRequest":
        """Require at least one of confluence_base_url or jira_base_url."""
        conf = (self.confluence_base_url or "").strip()
        jira = (self.jira_base_url or "").strip()
        if not conf and not jira:
            raise ValueError(
                "No link to extract requirement. Please provide Confluence URL, Jira URL, or both."
            )
        self.confluence_base_url = conf or None
        self.jira_base_url = jira or None
        return self

    @model_validator(mode="after")
    def at_least_one_provider(self) -> "ProjectCreateRequest":
        """Require at least one enabled provider."""
        if not self.enabled_providers:
            raise ValueError("No provider to execute. Please enable at least one provider.")
        return self


class ProjectUpdateRequest(ProjectCreateRequest):
    """Admin project update request."""


class AdminUserCreateRequest(BaseModel):
    """Admin-managed user creation request."""

    email: str = Field(min_length=1, max_length=320)
    display_name: str = Field(min_length=1, max_length=255)
    role: AdminUserRole = "standard"
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
    jira_base_url: str | None
    enabled_providers: list[str]
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


def _to_admin_user_response(user: User) -> AdminUserResponse:
    """Build a display-safe admin user response with project memberships."""
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
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
    users = list(db.execute(select(User).order_by(User.email)).scalars().unique())
    return [_to_admin_user_response(user) for user in users]


@router.post("/users", response_model=AdminUserResponse)
async def create_user(
    request: AdminUserCreateRequest,
    _admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> AdminUserResponse:
    """Create an active user from the admin dashboard."""
    if get_user_by_email(db, request.email) is not None:
        raise HTTPException(status_code=409, detail="User already exists")

    user = User(
        email=request.email,
        display_name=request.display_name,
        password_hash=hash_password(request.initial_password),
        role=request.role,
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
    return _to_admin_user_response(user)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID,
    _admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> None:
    """Delete a user from the admin dashboard."""
    deleted = db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Resource not found")
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
        created_by_user_id=admin.id,
    )
    db.add(project)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Project name already exists") from exc
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
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Project name already exists") from exc
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


class E2ETestRunResponse(BaseModel):
    """Result summary returned after an E2E test run."""

    exit_code: int
    passed: bool
    report_available: bool
    stdout: str
    stderr: str


@router.post("/tests/e2e", response_model=E2ETestRunResponse)
async def run_e2e_tests(
    request: Request,
    _admin: User = AdminDependency,
) -> E2ETestRunResponse:
    """Trigger a Playwright E2E test run in headed mode with slow motion.

    Only admins can invoke this endpoint. Runs the full Playwright suite
    synchronously and returns a structured result. Use the companion
    GET /admin/tests/e2e/report endpoint to download the HTML report.
    """
    if not _FRONTEND_DIR.is_dir():
        return E2ETestRunResponse(
            exit_code=-1,
            passed=False,
            report_available=False,
            stdout="",
            stderr=f"Frontend directory not found: {_FRONTEND_DIR}",
        )

    # Determine the npx executable path relative to the frontend directory
    npx_cmd = shutil.which("npx")
    if not npx_cmd:
        return E2ETestRunResponse(
            exit_code=-1,
            passed=False,
            report_available=False,
            stdout="",
            stderr="npx not found. Ensure Node.js and Playwright are installed.",
        )

    def run_process_sync() -> tuple[bytes, bytes, int]:
        result = subprocess.run(
            [npx_cmd, "playwright", "test", "--headed", "--workers=1"],
            cwd=str(_FRONTEND_DIR),
            capture_output=True,
            timeout=900,
            env={
                **os.environ,
                "PLAYWRIGHT_SLOW_MO": "500",
                "FORCE_COLOR": "0",
                "PLAYWRIGHT_HTML_REPORT_OPEN": "never",
                "CI": "1",
            },
        )
        return result.stdout, result.stderr, result.returncode

    try:
        try:
            stdout_bytes, stderr_bytes, returncode = await asyncio.to_thread(run_process_sync)
            stdout = stdout_bytes.decode(errors="replace") if stdout_bytes else ""
            stderr = stderr_bytes.decode(errors="replace") if stderr_bytes else ""
        except subprocess.TimeoutExpired as exc:
            return E2ETestRunResponse(
                exit_code=-1,
                passed=False,
                report_available=False,
                stdout=exc.stdout.decode(errors="replace") if exc.stdout else "",
                stderr="E2E test run timed out after 15 minutes.",
            )
    except Exception:
        import traceback

        return E2ETestRunResponse(
            exit_code=-1,
            passed=False,
            report_available=False,
            stdout="",
            stderr=f"Error executing npx:\n{traceback.format_exc()}",
        )

    # Resolve the HTML report path generated by Playwright (playwright-report/index.html)
    report_dir = _FRONTEND_DIR / "playwright-report"
    report_available = (report_dir / "index.html").exists()

    return E2ETestRunResponse(
        exit_code=returncode,
        passed=returncode == 0,
        report_available=report_available,
        stdout=stdout[-8000:] if stdout else "",  # cap at 8 KB
        stderr=stderr[-4000:] if stderr else "",
    )


@router.get("/tests/e2e/report/view/{file_path:path}")
async def view_e2e_report(
    file_path: str,
) -> FileResponse:
    """Serve the Playwright HTML report files directly in the browser."""
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
