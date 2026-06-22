"""Per-user captured browser-session API (project-scoped).

A tester captures their OWN authenticated session for a project's (environment, role)
by logging into a debug browser and letting the backend export its Playwright
``storageState`` over CDP. The blob is encrypted at rest and NEVER returned here — only
non-secret status (timestamps, cookie count). Sarah/Jack rehydrate it server-side.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import get_current_active_user
from ai_qa.browser.llm_factory import build_browser_use_llm
from ai_qa.browser.session_capture import (
    DEFAULT_CDP_URL,
    SessionCaptureError,
    capture_storage_state_over_cdp,
)
from ai_qa.config import AppSettings
from ai_qa.db.models import Project, User
from ai_qa.secrets import PROVIDER_SECRET_TYPE_MAP
from ai_qa.secrets.service import get_user_secret
from ai_qa.sessions import service as session_service
from ai_qa.sessions.auto_capture import AutoCaptureError, auto_capture_password_session

logger = logging.getLogger(__name__)

DbSessionDependency = Depends(get_db_session_dependency)
CurrentUserDependency = Depends(get_current_active_user)

router = APIRouter(prefix="/projects", tags=["sessions"])

# Per-provider default model + which providers can drive a browser-use LLM fallback. The
# fallback is best-effort/optional, so providers without a reliable default (on-premises,
# whose model id is deployment-specific) are simply omitted → scripted-only login.
_BROWSER_USE_DEFAULT_MODELS: dict[str, str] = {
    "claude": "claude-3-5-sonnet-20241022",
    "anthropic": "claude-3-5-sonnet-20241022",
    "claude-sso": "claude-3-5-sonnet-20241022",
    "openai": "gpt-4o",
    "gemini": "gemini-2.0-flash",
    "google": "gemini-2.0-flash",
    "browser-use-cloud": "bu-2-0",
}


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
    # How the app under test is logged into — lets the session panel offer the right capture
    # flow (SSO → manual debug-browser capture; PASSWORD → backend auto-login). Non-secret.
    login_type: str
    captured: list[SessionStatusResponse]


class CaptureSessionRequest(BaseModel):
    environment: str = Field(min_length=1, max_length=64)
    role: str = Field(min_length=1, max_length=64)
    auth_method: str = Field(default=session_service.DEFAULT_AUTH_METHOD)
    cdp_url: str = Field(default=DEFAULT_CDP_URL, max_length=512)


class AutoCaptureSessionRequest(BaseModel):
    """Trigger backend-driven login for a PASSWORD project's (environment, role)."""

    environment: str = Field(min_length=1, max_length=64)
    role: str = Field(min_length=1, max_length=64)
    chrome_path: str = Field(min_length=1, max_length=1024)
    headless: bool = True


def _provider_credential(
    db: Session, user: User, provider: str, settings: AppSettings
) -> tuple[str, str]:
    """Resolve (api_key, base_url) for ``provider``.

    The credential is the triggering user's per-user secret (the same source the pipeline
    uses); claude-sso additionally falls back to the server-side enterprise key. Base URLs
    come from :class:`AppSettings` (config-owned). Returns an empty key when none is set
    (the caller then skips the LLM fallback).
    """
    secret_type = PROVIDER_SECRET_TYPE_MAP.get(provider, "")
    user_key = (get_user_secret(db, user.id, secret_type) if secret_type else None) or ""
    if provider == "browser-use-cloud":
        return user_key, settings.browser_use_cloud_url
    if provider == "openai":
        return user_key, settings.openai_api_base_url
    if provider in ("gemini", "google"):
        return user_key, ""  # ChatGoogle takes no base_url
    if provider == "claude-sso":
        return user_key or settings.claude_sso_enterprise_api_key, settings.claude_api_base_url
    # claude / anthropic
    return user_key, settings.claude_api_base_url


def _resolve_browser_use_llm(
    db: Session, user: User, project: Project, settings: AppSettings
) -> Any:
    """Best-effort browser-use chat model for the LLM login fallback (None if unavailable).

    Uses the project's primary enabled provider + the triggering user's credential. The
    fallback is optional, so ANY miss (unknown provider, no credential, build error) returns
    None and the auto-login proceeds scripted-only.
    """
    provider = next(
        (p.strip().lower() for p in (project.enabled_providers or []) if p.strip()),
        "claude",
    )
    model = _BROWSER_USE_DEFAULT_MODELS.get(provider)
    if not model:
        return None
    try:
        api_key, base_url = _provider_credential(db, user, provider, settings)
        if not api_key:
            return None
        return build_browser_use_llm(provider, api_key=api_key, model=model, base_url=base_url)
    except Exception:  # noqa: BLE001 — fallback is optional; never block capture on it
        logger.debug("Auto-capture: could not build a browser-use LLM for provider %s", provider)
        return None


async def _project_for_member(project_id: UUID, current_user: User, db: Session) -> Project:
    """Return the project if the current user is an admin or a member, else 404."""
    from ai_qa.api.projects import require_project_member_or_admin

    return await require_project_member_or_admin(project_id, current_user, db)


def _matrix(db: Session, project: Project, user: User) -> SessionMatrixResponse:
    statuses = session_service.list_session_status(db, user_id=user.id, project_id=project.id)
    return SessionMatrixResponse(
        environments=list(project.environments or []),
        app_roles=list(project.app_roles or []),
        login_type=project.login_type or "SSO",
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


@router.post("/{project_id}/sessions/capture", response_model=SessionStatusResponse)
async def capture_session(
    project_id: UUID,
    request: CaptureSessionRequest,
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> SessionStatusResponse:
    """Capture the current user's session for (environment, role) from a debug browser."""
    project = await _project_for_member(project_id, current_user, db)

    env_names = {str(e.get("name")) for e in (project.environments or []) if isinstance(e, dict)}
    if request.environment not in env_names:
        raise HTTPException(status_code=422, detail="Unknown environment for this project.")
    if request.role not in (project.app_roles or []):
        raise HTTPException(status_code=422, detail="Unknown role for this project.")

    try:
        storage_state = await capture_storage_state_over_cdp(request.cdp_url)
    except SessionCaptureError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    status = session_service.save_captured_session(
        db,
        user_id=current_user.id,
        project_id=project.id,
        environment=request.environment,
        role=request.role,
        auth_method=request.auth_method,
        storage_state=storage_state,
    )
    return SessionStatusResponse(**vars(status))


@router.post("/{project_id}/sessions/auto-capture", response_model=SessionStatusResponse)
async def auto_capture_session(
    project_id: UUID,
    request: AutoCaptureSessionRequest,
    http_request: Request,
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> SessionStatusResponse:
    """Backend-drive the login for a PASSWORD project and save THIS user's session.

    Uses the project's shared :class:`ProjectAccount` credential (resolved backend-internally,
    never exposed) to log in via a scripted heuristic, falling back to a browser-use LLM
    driver when one can be built. The resulting storageState is stored as the current user's
    own captured session (``auth_method="PASSWORD"``).
    """
    project = await _project_for_member(project_id, current_user, db)
    settings = getattr(http_request.app.state, "settings", None) or AppSettings()
    llm = _resolve_browser_use_llm(db, current_user, project, settings)
    try:
        status = await auto_capture_password_session(
            db,
            user_id=current_user.id,
            project=project,
            environment=request.environment,
            role=request.role,
            chrome_path=request.chrome_path,
            headless=request.headless,
            llm=llm,
        )
    except AutoCaptureError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return SessionStatusResponse(**vars(status))


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
