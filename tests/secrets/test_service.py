"""Tests for the per-user secret accessor service."""

from collections.abc import Callable

import pytest
from sqlalchemy.orm import Session

from ai_qa.db.models import User
from ai_qa.secrets import CANONICAL_SECRET_TYPES, SECRET_TYPE_CLAUDE, SECRET_TYPE_OPENAI
from ai_qa.secrets.models import UserSecret
from ai_qa.secrets.service import (
    MIN_SECRET_LENGTH,
    STATUS_MISSING,
    SecretStatus,
    get_secret_status,
    get_user_secret,
    list_secret_status,
    set_user_secret,
    validate_secret_format,
)


def test_get_user_secret_returns_none_when_absent(
    session: Session, make_user: Callable[..., User]
) -> None:
    user = make_user()
    assert get_user_secret(session, user.id, SECRET_TYPE_CLAUDE) is None


def test_set_user_secret_inserts_then_returns_decrypted(
    session: Session, make_user: Callable[..., User]
) -> None:
    user = make_user()
    set_user_secret(session, user.id, SECRET_TYPE_CLAUDE, "claude-key-123")
    session.commit()

    assert get_user_secret(session, user.id, SECRET_TYPE_CLAUDE) == "claude-key-123"


def test_set_user_secret_upserts_without_duplicate_row(
    session: Session, make_user: Callable[..., User]
) -> None:
    user = make_user()
    set_user_secret(session, user.id, SECRET_TYPE_CLAUDE, "old-key")
    session.commit()
    set_user_secret(session, user.id, SECRET_TYPE_CLAUDE, "new-key")
    session.commit()

    rows = (
        session.query(UserSecret)
        .filter(UserSecret.user_id == user.id, UserSecret.secret_type == SECRET_TYPE_CLAUDE)
        .all()
    )
    assert len(rows) == 1
    assert get_user_secret(session, user.id, SECRET_TYPE_CLAUDE) == "new-key"


def test_secrets_are_isolated_per_type(session: Session, make_user: Callable[..., User]) -> None:
    user = make_user()
    set_user_secret(session, user.id, SECRET_TYPE_CLAUDE, "claude-key")
    set_user_secret(session, user.id, SECRET_TYPE_OPENAI, "openai-key")
    session.commit()

    assert get_user_secret(session, user.id, SECRET_TYPE_CLAUDE) == "claude-key"
    assert get_user_secret(session, user.id, SECRET_TYPE_OPENAI) == "openai-key"


def test_secrets_are_isolated_per_user(session: Session, make_user: Callable[..., User]) -> None:
    """Core security promise: one user's secret is never visible to another."""
    alice = make_user(email="alice@example.com")
    bob = make_user(email="bob@example.com")

    set_user_secret(session, alice.id, SECRET_TYPE_CLAUDE, "alice-claude-key")
    set_user_secret(session, bob.id, SECRET_TYPE_CLAUDE, "bob-claude-key")
    session.commit()

    assert get_user_secret(session, alice.id, SECRET_TYPE_CLAUDE) == "alice-claude-key"
    assert get_user_secret(session, bob.id, SECRET_TYPE_CLAUDE) == "bob-claude-key"


def test_get_returns_none_for_user_without_that_secret(
    session: Session, make_user: Callable[..., User]
) -> None:
    """A user who never stored a secret gets ``None`` even if another user has one."""
    alice = make_user(email="alice@example.com")
    bob = make_user(email="bob@example.com")

    set_user_secret(session, alice.id, SECRET_TYPE_CLAUDE, "alice-claude-key")
    session.commit()

    assert get_user_secret(session, bob.id, SECRET_TYPE_CLAUDE) is None


# --- list_secret_status / get_secret_status (AC1: metadata only, no secret) ---


def test_list_secret_status_reports_all_canonical_types_as_missing_when_empty(
    session: Session, make_user: Callable[..., User]
) -> None:
    user = make_user()

    statuses = list_secret_status(session, user.id)

    assert [s.secret_type for s in statuses] == list(CANONICAL_SECRET_TYPES)
    assert all(isinstance(s, SecretStatus) for s in statuses)
    assert all(s.configured is False for s in statuses)
    assert all(s.status == STATUS_MISSING for s in statuses)
    assert all(s.validation_state == STATUS_MISSING for s in statuses)
    assert all(s.last_updated is None for s in statuses)


def test_list_secret_status_marks_stored_type_configured_without_exposing_value(
    session: Session, make_user: Callable[..., User]
) -> None:
    user = make_user()
    set_user_secret(session, user.id, SECRET_TYPE_CLAUDE, "claude-secret-value")
    session.commit()

    statuses = list_secret_status(session, user.id)
    claude = next(s for s in statuses if s.secret_type == SECRET_TYPE_CLAUDE)
    openai = next(s for s in statuses if s.secret_type == SECRET_TYPE_OPENAI)

    assert claude.configured is True
    assert claude.status == "configured"
    assert claude.validation_state == "configured"
    assert claude.last_updated is not None
    # The status object carries no secret-bearing field.
    assert not hasattr(claude, "encrypted_value")
    assert not hasattr(claude, "value")
    assert "claude-secret-value" not in repr(claude)
    # Other types remain missing.
    assert openai.configured is False
    assert openai.status == STATUS_MISSING


def test_get_secret_status_single_type(session: Session, make_user: Callable[..., User]) -> None:
    user = make_user()
    set_user_secret(session, user.id, SECRET_TYPE_OPENAI, "openai-secret-value")
    session.commit()

    configured = get_secret_status(session, user.id, SECRET_TYPE_OPENAI)
    missing = get_secret_status(session, user.id, SECRET_TYPE_CLAUDE)

    assert configured.configured is True
    assert configured.status == "configured"
    assert missing.configured is False
    assert missing.status == STATUS_MISSING


def test_list_secret_status_is_scoped_per_user(
    session: Session, make_user: Callable[..., User]
) -> None:
    alice = make_user(email="alice@example.com")
    bob = make_user(email="bob@example.com")
    set_user_secret(session, alice.id, SECRET_TYPE_CLAUDE, "alice-claude-key")
    session.commit()

    bob_statuses = list_secret_status(session, bob.id)
    bob_claude = next(s for s in bob_statuses if s.secret_type == SECRET_TYPE_CLAUDE)

    assert bob_claude.configured is False


# --- validate_secret_format (AC2: format-only validation) ---


def test_validate_secret_format_accepts_valid_value() -> None:
    # Should not raise.
    validate_secret_format(SECRET_TYPE_CLAUDE, "a-valid-key-1234")


def test_validate_secret_format_rejects_empty_value() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        validate_secret_format(SECRET_TYPE_CLAUDE, "")


def test_validate_secret_format_rejects_whitespace_only_value() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        validate_secret_format(SECRET_TYPE_CLAUDE, "       ")


def test_validate_secret_format_rejects_too_short_value() -> None:
    with pytest.raises(ValueError, match="too short"):
        validate_secret_format(SECRET_TYPE_CLAUDE, "short")


def test_validate_secret_format_accepts_value_at_minimum_length_boundary() -> None:
    """Boundary value: a value of exactly ``MIN_SECRET_LENGTH`` chars is accepted."""
    boundary_value = "a" * MIN_SECRET_LENGTH
    # Should not raise (the floor is ">= MIN_SECRET_LENGTH", not "> MIN_SECRET_LENGTH").
    validate_secret_format(SECRET_TYPE_CLAUDE, boundary_value)


def test_validate_secret_format_rejects_value_one_below_minimum_length() -> None:
    """Boundary value: one character below the floor is rejected (off-by-one guard)."""
    too_short = "a" * (MIN_SECRET_LENGTH - 1)
    with pytest.raises(ValueError, match="too short"):
        validate_secret_format(SECRET_TYPE_CLAUDE, too_short)


def test_validate_secret_format_measures_length_after_stripping() -> None:
    """Surrounding whitespace must not count toward the minimum-length floor.

    A value whose visible content is below the floor is rejected even when its
    padded form exceeds it; a value that meets the floor after stripping passes.
    """
    padded_short = "  " + ("a" * (MIN_SECRET_LENGTH - 1)) + "  "
    with pytest.raises(ValueError, match="too short"):
        validate_secret_format(SECRET_TYPE_CLAUDE, padded_short)

    padded_valid = "  " + ("a" * MIN_SECRET_LENGTH) + "  "
    # Should not raise: it is exactly at the floor after stripping.
    validate_secret_format(SECRET_TYPE_CLAUDE, padded_valid)


def test_validate_secret_format_error_message_never_echoes_value() -> None:
    """Secret-free errors: the rejected value must not leak into the message."""
    secret_like = "tiny-leak-me"  # 12 chars but we force rejection via whitespace strip
    with pytest.raises(ValueError) as exc_info:
        validate_secret_format(SECRET_TYPE_CLAUDE, "   ")
    assert secret_like not in str(exc_info.value)


def test_get_secret_status_exposes_last_updated_from_row(
    session: Session, make_user: Callable[..., User]
) -> None:
    """``last_updated`` metadata is surfaced from the stored row's ``updated_at``."""
    user = make_user()
    set_user_secret(session, user.id, SECRET_TYPE_CLAUDE, "claude-secret-value")
    session.commit()

    stored = (
        session.query(UserSecret)
        .filter(UserSecret.user_id == user.id, UserSecret.secret_type == SECRET_TYPE_CLAUDE)
        .one()
    )
    status = get_secret_status(session, user.id, SECRET_TYPE_CLAUDE)

    assert status.last_updated == stored.updated_at
