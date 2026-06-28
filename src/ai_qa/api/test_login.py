"""Test-login endpoint: verify credentials by attempting a real browser login.

Users can trigger a test login for an (environment, role) pair. The endpoint
reuses the auto-login machinery (headless Chrome → storageState capture) and
returns a simple success/failure result. On success the generated session is
cached for 1 hour (same as regular auto-login).
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import get_current_active_user
from ai_qa.api.projects import require_project_member_or_admin
from ai_qa.config import AppSettings
from ai_qa.db.models import User
from ai_qa.exceptions import AIQAError
from ai_qa.sessions.auto_login import resolve_or_generate_storage_state
from ai_qa.sessions.mfa_manager import submit_mfa

logger = logging.getLogger(__name__)

DbSessionDependency = Depends(get_db_session_dependency)
CurrentUserDependency = Depends(get_current_active_user)

router = APIRouter(prefix="/projects", tags=["test-credentials"])


class TestLoginRequest(BaseModel):
    environment: str
    role: str


class TestLoginResponse(BaseModel):
    success: bool
    error: str | None = None


class SubmitMFARequest(BaseModel):
    session_id: str
    code: str


@router.post("/{project_id}/test-credentials/submit-mfa", response_model=TestLoginResponse)
async def api_submit_mfa(
    project_id: UUID,
    payload: SubmitMFARequest,
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> TestLoginResponse:
    """Submit an interactive MFA code to a waiting browser session."""
    await require_project_member_or_admin(project_id, current_user, db)

    success = submit_mfa(payload.session_id, payload.code)
    if success:
        return TestLoginResponse(success=True)
    else:
        return TestLoginResponse(
            success=False, error="Invalid session ID or session already expired."
        )


@router.post("/{project_id}/test-credentials/test-login", response_model=TestLoginResponse)
async def test_login(
    project_id: UUID,
    payload: TestLoginRequest,
    http_request: Request,
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> TestLoginResponse:
    """Attempt a real browser login using the user's saved test credentials.

    Looks up the TestAccountCredential for the given (environment, role) pair,
    drives headless Chrome through the login flow, and returns whether it
    succeeded. On success the captured session is cached (1-hour TTL).
    """
    await require_project_member_or_admin(project_id, current_user, db)

    settings: AppSettings = getattr(http_request.app.state, "settings", AppSettings())
    chrome_path = settings.chrome_path or ""

    try:
        blob = await resolve_or_generate_storage_state(
            db=db,
            user_id=current_user.id,
            project_id=project_id,
            environment=payload.environment,
            role=payload.role,
            chrome_path=chrome_path,
            timeout=settings.browser_timeout,
            raise_on_failure=True,
        )
    except AIQAError as exc:
        # Typed failure: surface the user-facing message (e.g. "connect to VPN",
        # "no saved credentials", "login did not complete"). `.message` never
        # includes the technical `details`, so nothing sensitive leaks to the UI.
        logger.warning(
            "Test login failed for env='%s' role='%s': %s",
            payload.environment,
            payload.role,
            exc,
        )
        return TestLoginResponse(success=False, error=exc.message)
    except Exception:
        logger.exception(
            "Test login errored unexpectedly for env='%s' role='%s'",
            payload.environment,
            payload.role,
        )
        return TestLoginResponse(
            success=False, error="Login test failed unexpectedly. Please check the server logs."
        )

    if blob is None:
        return TestLoginResponse(
            success=False, error="Login test did not produce a session. Please try again."
        )

    return TestLoginResponse(success=True)
