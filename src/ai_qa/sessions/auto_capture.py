"""Backend-driven PASSWORD auto-capture orchestration.

For a ``login_type="PASSWORD"`` project, this resolves the shared
:class:`~ai_qa.db.models.ProjectAccount` credential for an (environment, role), drives an
automated login (scripted → browser-use LLM fallback, see
:mod:`ai_qa.browser.password_login`), and stores the resulting Playwright ``storageState``
as the *triggering tester's own* :class:`~ai_qa.db.models.CapturedSession`
(``auth_method="PASSWORD"``). Each tester therefore ends up with their own per-user session
blob even though the project shares one login identity.

Security: the decrypted password is read here only to hand it to the browser driver. It is
never logged, never returned, and never placed in any raised error (the driver's
:class:`PasswordLoginError` messages are credential-free by contract).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_qa.browser.password_login import PasswordLoginError, login_and_capture_storage_state
from ai_qa.db.models import Project, ProjectAccount
from ai_qa.sessions.service import SessionStatus, save_captured_session

PASSWORD_LOGIN_TYPE = "PASSWORD"
PASSWORD_AUTH_METHOD = "PASSWORD"

# A login driver: given the resolved login URL + credentials, returns a Playwright
# storageState dict (or raises PasswordLoginError). Injectable so the orchestration is
# unit-testable without launching a browser.
CaptureFn = Callable[..., Awaitable[dict[str, Any]]]


class AutoCaptureError(RuntimeError):
    """A user-actionable auto-capture failure carrying the HTTP status to surface.

    The message is always credential-free and safe to return to the client.
    """

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _environment_url(project: Project, environment: str) -> str | None:
    """Return the configured URL for ``environment`` (by name), or ``None``."""
    for env in project.environments or []:
        if isinstance(env, dict) and str(env.get("name")) == environment:
            url = (env.get("url") or "").strip()
            return url or None
    return None


def resolve_project_account(
    db: Session, *, project_id: UUID, environment: str, role: str
) -> ProjectAccount | None:
    """Return the project-level login account for (environment, role), or ``None``."""
    return db.execute(
        select(ProjectAccount).where(
            ProjectAccount.project_id == project_id,
            ProjectAccount.environment == environment,
            ProjectAccount.role == role,
        )
    ).scalar_one_or_none()


async def auto_capture_password_session(
    db: Session,
    *,
    user_id: UUID,
    project: Project,
    environment: str,
    role: str,
    chrome_path: str,
    capture_fn: CaptureFn | None = None,
    llm: Any | None = None,
    headless: bool = True,
) -> SessionStatus:
    """Auto-log in with the project's shared account and save the tester's session.

    Args:
        db: Active DB session.
        user_id: The tester triggering the capture (the session is stored under THEM).
        project: The already-loaded project (must be ``login_type="PASSWORD"``).
        environment: Environment name (must exist in ``project.environments``).
        role: Application role (must exist in ``project.app_roles``).
        chrome_path: Path to the Chrome/Edge binary the backend launches for the login.
        capture_fn: The login driver (injectable for tests; defaults to the real launcher,
            resolved at call time so it can be patched).
        llm: Optional browser-use chat model enabling the scripted→LLM fallback.
        headless: Launch the auto-login browser headless (default True).

    Returns:
        The non-secret :class:`SessionStatus` for the saved session.

    Raises:
        AutoCaptureError: project not PASSWORD / unknown environment or role / no account or
            password configured (4xx), or the automated login failed (502).
    """
    if (project.login_type or "").upper() != PASSWORD_LOGIN_TYPE:
        raise AutoCaptureError(
            "Auto-capture is only available for PASSWORD projects; "
            "SSO projects must capture the session manually.",
            status_code=409,
        )

    if role not in (project.app_roles or []):
        raise AutoCaptureError("Unknown role for this project.", status_code=422)

    login_url = _environment_url(project, environment)
    if login_url is None:
        raise AutoCaptureError("Unknown environment for this project.", status_code=422)

    account = resolve_project_account(db, project_id=project.id, environment=environment, role=role)
    if account is None:
        raise AutoCaptureError(
            "No test-login account is configured for this environment and role. "
            "Ask a project admin to add one.",
            status_code=404,
        )

    # Reading ``encrypted_password`` decrypts it (EncryptedString). Used only to drive the
    # login; never logged, returned, or placed in an error.
    password = account.encrypted_password
    if not password:
        raise AutoCaptureError(
            "The test-login account has no password configured.", status_code=422
        )

    driver = capture_fn or login_and_capture_storage_state
    try:
        storage_state = await driver(
            login_url=login_url,
            username=account.login_identifier,
            password=password,
            chrome_path=chrome_path,
            llm=llm,
            headless=headless,
        )
    except PasswordLoginError as exc:
        # PasswordLoginError messages are credential-free by contract.
        raise AutoCaptureError(str(exc), status_code=502) from exc

    return save_captured_session(
        db,
        user_id=user_id,
        project_id=project.id,
        environment=environment,
        role=role,
        auth_method=PASSWORD_AUTH_METHOD,
        storage_state=storage_state,
    )
