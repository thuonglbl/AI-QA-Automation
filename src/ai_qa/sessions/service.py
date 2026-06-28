"""Service layer for per-user captured browser sessions.

All access is keyed by ``(user_id, project_id, environment, role)``. The ``storageState``
blob is stored encrypted in :class:`CapturedSession.encrypted_storage_state` and is NEVER
returned to the frontend or logged — only the non-secret status (timestamps, auth method,
cookie count) is surfaced. ``resolve_storage_state`` is the only reader that returns the
blob, for backend browser rehydration (Sarah/Jack).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_qa.db.models import CapturedSession

# Recognised capture methods (see the design doc). SSO_MANUAL is the corporate-SSO default.
AUTH_METHODS = ("SSO_MANUAL", "PASSWORD", "API_TOKEN", "SSO_TOTP")
DEFAULT_AUTH_METHOD = "SSO_MANUAL"


@dataclass(frozen=True)
class SessionStatus:
    """Non-secret status of a captured session (safe to return to the frontend)."""

    environment: str
    role: str
    auth_method: str
    captured_at: datetime
    expires_at: datetime | None
    last_validated_at: datetime | None
    cookie_count: int


def _cookie_count(storage_state_json: str) -> int:
    """Best-effort cookie count from a storageState JSON string (0 on any problem)."""
    try:
        data = json.loads(storage_state_json)
    except json.JSONDecodeError, ValueError:
        return 0
    cookies = data.get("cookies") if isinstance(data, dict) else None
    return len(cookies) if isinstance(cookies, list) else 0


def _to_status(row: CapturedSession) -> SessionStatus:
    return SessionStatus(
        environment=row.environment,
        role=row.role,
        auth_method=row.auth_method,
        captured_at=row.captured_at,
        expires_at=row.expires_at,
        last_validated_at=row.last_validated_at,
        cookie_count=_cookie_count(row.encrypted_storage_state),
    )


def save_captured_session(
    db: Session,
    *,
    user_id: UUID,
    project_id: UUID,
    environment: str,
    role: str,
    auth_method: str,
    storage_state: dict[str, Any],
    expires_at: datetime | None = None,
) -> SessionStatus:
    """Upsert the captured session for ``(user, project, environment, role)``.

    ``storage_state`` is the Playwright storageState dict; it is JSON-serialized and
    stored encrypted. A re-capture overwrites the prior blob (same unique key). Returns
    the non-secret status.
    """
    method = auth_method if auth_method in AUTH_METHODS else DEFAULT_AUTH_METHOD
    blob = json.dumps(storage_state)
    now = datetime.now(UTC)

    row = db.execute(
        select(CapturedSession).where(
            CapturedSession.user_id == user_id,
            CapturedSession.project_id == project_id,
            CapturedSession.environment == environment,
            CapturedSession.role == role,
        )
    ).scalar_one_or_none()

    if row is None:
        row = CapturedSession(
            user_id=user_id,
            project_id=project_id,
            environment=environment,
            role=role,
            auth_method=method,
            encrypted_storage_state=blob,
            captured_at=now,
            expires_at=expires_at,
            last_validated_at=now,
        )
        db.add(row)
    else:
        row.auth_method = method
        row.encrypted_storage_state = blob
        row.captured_at = now
        row.expires_at = expires_at
        row.last_validated_at = now

    db.commit()
    db.refresh(row)
    return _to_status(row)


def list_session_status(db: Session, *, user_id: UUID, project_id: UUID) -> list[SessionStatus]:
    """Return non-secret status for every session the user captured in this project."""
    rows = (
        db.execute(
            select(CapturedSession).where(
                CapturedSession.user_id == user_id,
                CapturedSession.project_id == project_id,
            )
        )
        .scalars()
        .all()
    )
    return [_to_status(row) for row in rows]


def resolve_storage_state(
    db: Session,
    *,
    user_id: UUID,
    project_id: UUID,
    environment: str,
    role: str,
) -> dict[str, Any] | None:
    """Return the decrypted storageState dict for backend rehydration, or None.

    The ONLY path that exposes the blob — for injecting into a browser context
    (Sarah/Jack). Never expose the result to the frontend or logs.
    """
    row = db.execute(
        select(CapturedSession).where(
            CapturedSession.user_id == user_id,
            CapturedSession.project_id == project_id,
            CapturedSession.environment == environment,
            CapturedSession.role == role,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.expires_at is not None and row.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        return None
    try:
        parsed = json.loads(row.encrypted_storage_state)
    except json.JSONDecodeError, ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def delete_captured_session(
    db: Session,
    *,
    user_id: UUID,
    project_id: UUID,
    environment: str,
    role: str,
) -> bool:
    """Delete the user's captured session for the slot; True if one was removed."""
    row = db.execute(
        select(CapturedSession).where(
            CapturedSession.user_id == user_id,
            CapturedSession.project_id == project_id,
            CapturedSession.environment == environment,
            CapturedSession.role == role,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
