"""Thin accessor service for per-user encrypted secrets.

Scope is deliberately limited to "current user's secret by type" storage. It is
the storage primitive that later Epic 9 stories (status/replacement REST API,
provider validation, thread-owner resolution, rotation) will build on — it does
NOT implement any of those behaviors here.

The caller is responsible for committing the session (mirroring the existing
``alice.py`` flow which calls ``db.commit()`` itself).
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_qa.secrets import CANONICAL_SECRET_TYPES
from ai_qa.secrets.models import UserSecret

# Sentinel status reported for a canonical secret type that has no stored row.
STATUS_MISSING = "missing"

# Minimum accepted length for a replacement secret, mirroring the format floor
# enforced by ``ai_qa.agents.alice._test_connection`` (``len(api_key) < 8`` → reject).
MIN_SECRET_LENGTH = 8


@dataclass(frozen=True)
class SecretStatus:
    """Secret-free status metadata for a single canonical secret type.

    Contains ONLY non-secret fields — never the decrypted ``encrypted_value`` or
    any masked/reversible representation of it (AC1). This shape is what the
    status API surfaces to a user.
    """

    secret_type: str
    configured: bool
    status: str
    last_updated: datetime | None
    validation_state: str


def _status_from_row(secret_type: str, row: UserSecret | None) -> SecretStatus:
    """Build a :class:`SecretStatus` from a row (or its absence) — metadata only."""
    if row is None:
        return SecretStatus(
            secret_type=secret_type,
            configured=False,
            status=STATUS_MISSING,
            last_updated=None,
            validation_state=STATUS_MISSING,
        )
    # ``validation_state`` reflects only stored/format state for Story 9.2 (mirrors
    # the row's ``status`` column, default "configured"). Story 9.3 will enrich it
    # with real provider connection-validation results — extend it there, not here.
    return SecretStatus(
        secret_type=secret_type,
        configured=True,
        status=row.status,
        last_updated=row.updated_at,
        validation_state=row.status,
    )


def list_secret_status(db: Session, user_id: UUID) -> list[SecretStatus]:
    """Return non-secret status metadata for every canonical secret type.

    Iterates the canonical secret types so providers without a stored row are
    represented as ``configured=False`` / ``status="missing"`` (AC1's
    configured/missing signal). Never decrypts or returns ``encrypted_value``.

    Args:
        db: Active SQLAlchemy session.
        user_id: Owning user id (ownership is session-derived, never a param).

    Returns:
        One :class:`SecretStatus` per canonical secret type, in canonical order.
    """
    rows = db.scalars(select(UserSecret).where(UserSecret.user_id == user_id)).all()
    rows_by_type = {row.secret_type: row for row in rows}
    return [
        _status_from_row(secret_type, rows_by_type.get(secret_type))
        for secret_type in CANONICAL_SECRET_TYPES
    ]


def get_secret_status(db: Session, user_id: UUID, secret_type: str) -> SecretStatus:
    """Return non-secret status metadata for a single ``secret_type``.

    Reads metadata only (never decrypts). Returns a "missing" status when no row
    exists for ``(user_id, secret_type)``.
    """
    row = db.scalar(
        select(UserSecret).where(
            UserSecret.user_id == user_id,
            UserSecret.secret_type == secret_type,
        )
    )
    return _status_from_row(secret_type, row)


def validate_secret_format(secret_type: str, value: str) -> None:
    """Validate the *format* of a replacement secret before storing it.

    Scope boundary: this is format-only validation, NOT a live provider
    connection check (that is Story 9.3). It mirrors alice's format floor:
    non-empty after stripping and at least ``MIN_SECRET_LENGTH`` characters.

    The submitted value is never logged or echoed; error messages are
    secret-free.

    Args:
        secret_type: Canonical secret type (accepted for symmetry / future
            per-type rules; not yet used to vary validation).
        value: The candidate plaintext secret.

    Raises:
        ValueError: If the value is empty/whitespace-only or shorter than
            ``MIN_SECRET_LENGTH`` after stripping.
    """
    stripped = value.strip()
    if not stripped:
        raise ValueError("Secret value must not be empty.")
    if len(stripped) < MIN_SECRET_LENGTH:
        raise ValueError(
            f"Secret value is too short; minimum length is {MIN_SECRET_LENGTH} characters."
        )


def set_user_secret(db: Session, user_id: UUID, secret_type: str, value: str) -> UserSecret:
    """Upsert a user's secret for ``secret_type``.

    Updates ``encrypted_value`` + ``status`` on the existing row for
    ``(user_id, secret_type)``, or inserts a new row. The encrypted value is
    written via the ORM type, so the plaintext never touches the DB.

    The caller must commit the session.

    Args:
        db: Active SQLAlchemy session.
        user_id: Owning user id.
        secret_type: Canonical secret type (see ``ai_qa.secrets`` constants).
        value: Plaintext secret to encrypt and store.

    Returns:
        The inserted or updated :class:`UserSecret` (not yet committed).
    """
    secret = db.scalar(
        select(UserSecret).where(
            UserSecret.user_id == user_id,
            UserSecret.secret_type == secret_type,
        )
    )
    if secret is None:
        secret = UserSecret(
            user_id=user_id,
            secret_type=secret_type,
            status="configured",
            encrypted_value=value,
        )
        db.add(secret)
    else:
        secret.encrypted_value = value
        secret.status = "configured"
    return secret


def get_user_secret(db: Session, user_id: UUID, secret_type: str) -> str | None:
    """Return the decrypted secret for ``(user_id, secret_type)``.

    Args:
        db: Active SQLAlchemy session.
        user_id: Owning user id.
        secret_type: Canonical secret type (see ``ai_qa.secrets`` constants).

    Returns:
        The decrypted plaintext value, or ``None`` when no row exists.
    """
    secret = db.scalar(
        select(UserSecret).where(
            UserSecret.user_id == user_id,
            UserSecret.secret_type == secret_type,
        )
    )
    if secret is None:
        return None
    return secret.encrypted_value
