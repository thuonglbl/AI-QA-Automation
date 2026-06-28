import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_qa.browser.login import generate_session_storage_state
from ai_qa.db.models import Project, TestAccountCredential
from ai_qa.exceptions import BrowserError, ConfigError
from ai_qa.sessions import service as session_service

logger = logging.getLogger(__name__)


async def resolve_or_generate_storage_state(
    db: Session,
    user_id: UUID,
    project_id: UUID,
    environment: str,
    role: str,
    chrome_path: str,
    llm: Any = None,
    timeout: int = 60,
    raise_on_failure: bool = False,
) -> dict[str, Any] | None:
    """Resolve storageState from cache, or generate a new one via auto-login.

    This acts as a transparent cache over auto-login for Sarah explore and Jack run.
    If the session is present and not expired, it returns the cached blob.
    Otherwise, it checks for a TestAccountCredential. If one exists, it uses
    browser automation to log in, caches the result for 1 hour, and returns it.

    Args:
        db: Synchronous database session.
        user_id: User requesting the session (used for cache partitioning).
        project_id: Project the session is for.
        environment: The name of the target environment.
        role: The role to authenticate as.
        chrome_path: Path to the Chrome executable.
        llm: Optional language model to drive browser-use.
        timeout: Timeout for the login routine.
        raise_on_failure: When True (e.g. the interactive "Test Login" button),
            raise a typed error explaining WHY login could not be produced
            (``ConfigError`` for missing credential/URL, ``BrowserError`` for a
            failed login attempt) instead of returning ``None``. Sarah/Jack keep the
            default (False) so they fail soft and fall back to other session sources.
    """
    # 1. Try to resolve from cache (respects expires_at)
    blob = session_service.resolve_storage_state(
        db,
        user_id=user_id,
        project_id=project_id,
        environment=environment,
        role=role,
    )
    if blob is not None:
        logger.info("Using cached session for environment '%s', role '%s'", environment, role)
        return blob

    # 2. Cache miss or expired: attempt auto-login
    credential = db.execute(
        select(TestAccountCredential).where(
            TestAccountCredential.project_id == project_id,
            TestAccountCredential.environment == environment,
            TestAccountCredential.role == role,
        )
    ).scalar_one_or_none()

    if credential is None:
        if raise_on_failure:
            raise ConfigError("No saved test credentials for this environment and role.")
        return None

    project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
    if project is None:
        if raise_on_failure:
            raise ConfigError("Project not found.")
        return None

    # Find the matching environment dictionary to get the URL
    env_data = next(
        (e for e in project.environments if isinstance(e, dict) and e.get("name") == environment),
        None,
    )
    if env_data is None:
        if raise_on_failure:
            raise ConfigError(f"Environment '{environment}' is not configured for this project.")
        return None

    login_url = env_data.get("url")
    if not login_url:
        if raise_on_failure:
            raise ConfigError(f"Environment '{environment}' has no login URL configured.")
        return None

    logger.info(
        "Auto-login triggered for environment '%s', role '%s' at URL %s",
        environment,
        role,
        login_url,
    )

    try:
        new_blob = await generate_session_storage_state(
            credential=credential,
            login_url=login_url,
            chrome_path=chrome_path,
            llm=llm,
            timeout=timeout,
        )
    except BrowserError as exc:
        logger.error("Auto-login failed for role '%s': %s", role, exc)
        if raise_on_failure:
            raise
        return None

    # 3. Cache the new session (TTL: 1 hour)
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    session_service.save_captured_session(
        db,
        user_id=user_id,
        project_id=project_id,
        environment=environment,
        role=role,
        auth_method="TEST_ACCOUNT",
        storage_state=new_blob,
        expires_at=expires_at,
    )

    return new_blob
