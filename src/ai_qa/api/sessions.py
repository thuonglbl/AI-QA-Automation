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

import httpx
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

# Timeout (seconds) for the environment connectivity probe. Bounds a hung target so the
# request cannot block indefinitely.
_CONNECTION_CHECK_TIMEOUT = 10.0


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


class EnvConnectionStatus(BaseModel):
    """Reachability of a single project environment (no response body is exposed)."""

    name: str
    url: str
    reachable: bool
    status_code: int | None
    detail: str


class CheckConnectionResponse(BaseModel):
    """Per-environment results of the server-side reachability probe."""

    results: list[EnvConnectionStatus]


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


def _is_http_url(url: str) -> bool:
    return url.strip().lower().startswith(("http://", "https://"))


async def _probe_environment(
    http_client: httpx.AsyncClient, name: str, url: str
) -> EnvConnectionStatus:
    """Probe one environment URL and map the outcome to an :class:`EnvConnectionStatus`.

    Any HTTP response (302 redirect to a login page, 4xx, 5xx, …) counts as *reachable*; a
    connection/DNS/TLS error, timeout, or a malformed/non-http(s) URL counts as unreachable.
    The response body is never read or returned — only the status code and a short, non-secret
    detail string.
    """
    stripped = url.strip()
    if not stripped:
        return EnvConnectionStatus(
            name=name, url=url, reachable=False, status_code=None, detail="No URL configured."
        )
    if not _is_http_url(stripped):
        return EnvConnectionStatus(
            name=name,
            url=url,
            reachable=False,
            status_code=None,
            detail="The URL must start with http:// or https://.",
        )
    try:
        response = await http_client.get(stripped)
    except httpx.TimeoutException:
        return EnvConnectionStatus(
            name=name,
            url=url,
            reachable=False,
            status_code=None,
            detail="The connection timed out.",
        )
    except httpx.HTTPError, httpx.InvalidURL:
        # DNS failure, connection refused, TLS error, or a malformed URL (httpx.InvalidURL is
        # NOT an HTTPError subclass, so it must be caught explicitly or it would 500). Never
        # echo the raw exception — keep the message short and stable.
        return EnvConnectionStatus(
            name=name,
            url=url,
            reachable=False,
            status_code=None,
            detail="Could not connect to the environment URL.",
        )
    return EnvConnectionStatus(
        name=name,
        url=url,
        reachable=True,
        status_code=response.status_code,
        detail=f"Reachable (HTTP {response.status_code}).",
    )


@router.post("/{project_id}/environments/check-connections", response_model=CheckConnectionResponse)
async def check_environment_connections(
    project_id: UUID,
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> CheckConnectionResponse:
    """Probe reachability of the project's OWN configured environments from the backend.

    The server reads ``project.environments`` itself (no user-supplied URL) so there is no
    SSRF surface. One result per environment; envs with a blank URL are reported as
    unreachable with ``"No URL configured."``. Gated to project members/admins.
    """
    project = await _project_for_member(project_id, current_user, db)

    results: list[EnvConnectionStatus] = []
    async with httpx.AsyncClient(
        timeout=_CONNECTION_CHECK_TIMEOUT, follow_redirects=False
    ) as http_client:
        for env in project.environments or []:
            if not isinstance(env, dict):
                continue
            # env is dict[str, str] here, so `.get(...) or ""` is already str — no str()
            # wrapping (Pyrefly unnecessary-type-conversion).
            name = env.get("name") or ""
            url = env.get("url") or ""
            results.append(await _probe_environment(http_client, name, url))
    return CheckConnectionResponse(results=results)


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
