"""Tests for the UserSecret ORM model — encrypted value vs. plaintext metadata."""

from collections.abc import Callable

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_qa.db.models import User
from ai_qa.secrets import SECRET_TYPE_CLAUDE
from ai_qa.secrets.models import UserSecret


def test_persist_and_read_back_decrypted(session: Session, make_user: Callable[..., User]) -> None:
    user = make_user()
    secret = UserSecret(
        user_id=user.id,
        secret_type=SECRET_TYPE_CLAUDE,
        status="configured",
        encrypted_value="plaintext-claude-key",
    )
    session.add(secret)
    session.commit()
    session.expire_all()

    loaded = session.query(UserSecret).filter_by(user_id=user.id).one()
    # The ORM type decrypts on read.
    assert loaded.encrypted_value == "plaintext-claude-key"


def test_value_stored_as_ciphertext_at_rest(
    session: Session, make_user: Callable[..., User]
) -> None:
    """Leak check: the raw DB cell must NOT contain the plaintext secret (AC1)."""
    user = make_user()
    plaintext = "plaintext-claude-key"
    session.add(
        UserSecret(
            user_id=user.id,
            secret_type=SECRET_TYPE_CLAUDE,
            status="configured",
            encrypted_value=plaintext,
        )
    )
    session.commit()

    # Read the raw column value, bypassing the TypeDecorator.
    raw = session.execute(text("SELECT encrypted_value FROM user_secrets")).scalar_one()
    assert raw != plaintext
    assert plaintext not in raw


def test_metadata_columns_queryable_in_plaintext(
    session: Session, make_user: Callable[..., User]
) -> None:
    """AC2: non-secret metadata is stored separately and readable in plaintext."""
    user = make_user()
    session.add(
        UserSecret(
            user_id=user.id,
            secret_type=SECRET_TYPE_CLAUDE,
            status="configured",
            encrypted_value="plaintext-claude-key",
        )
    )
    session.commit()

    # Raw read (bypassing the ORM type) proves metadata is stored as plaintext.
    row = session.execute(text("SELECT secret_type, status FROM user_secrets")).one()
    assert row.secret_type == SECRET_TYPE_CLAUDE
    assert row.status == "configured"

    # Owning-user id and updated-at metadata are queryable via the ORM.
    loaded = session.query(UserSecret).filter_by(secret_type=SECRET_TYPE_CLAUDE).one()
    assert loaded.user_id == user.id
    assert loaded.updated_at is not None


def test_duplicate_user_secret_type_violates_unique_constraint(
    session: Session, make_user: Callable[..., User]
) -> None:
    """AC2 integrity: the DB-level unique guard rejects a second row for the
    same (user_id, secret_type) even when the service upsert is bypassed."""
    user = make_user()
    session.add(
        UserSecret(
            user_id=user.id,
            secret_type=SECRET_TYPE_CLAUDE,
            status="configured",
            encrypted_value="first-key",
        )
    )
    session.commit()

    session.add(
        UserSecret(
            user_id=user.id,
            secret_type=SECRET_TYPE_CLAUDE,
            status="configured",
            encrypted_value="second-key",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_deleting_user_cascades_to_secrets(
    session: Session, make_user: Callable[..., User]
) -> None:
    """Data-cleanup rule: the migration's ``ON DELETE CASCADE`` removes a
    user's secrets when the user row is deleted (no orphaned ciphertext)."""
    user = make_user()
    session.add(
        UserSecret(
            user_id=user.id,
            secret_type=SECRET_TYPE_CLAUDE,
            status="configured",
            encrypted_value="plaintext-claude-key",
        )
    )
    session.commit()
    assert session.query(UserSecret).count() == 1

    # Core delete (not ORM session.delete) so the DB-level FK cascade is what
    # removes the dependent row, rather than ORM relationship handling.
    session.execute(delete(User).where(User.id == user.id))
    session.commit()

    assert session.query(UserSecret).count() == 0


def test_no_inline_secret_key_columns_remain_on_user() -> None:
    """AC3.2 (structural): the encryption key lives only in settings — no
    per-user ``*_key`` secret columns survive on ``users`` after the migration,
    so secret key material is never persisted to PostgreSQL."""
    user_columns = set(User.__table__.columns.keys())
    legacy_key_columns = {
        "browser_use_key",
        "claude_key",
        "gemini_key",
        "openai_key",
        "on_premises_key",
        "mcp_key",
    }
    assert user_columns.isdisjoint(legacy_key_columns)


def test_user_secrets_table_has_no_encryption_key_column() -> None:
    """AC3.2 (structural): the ``user_secrets`` table stores only ciphertext +
    metadata — there is no column that would hold the Fernet key itself."""
    columns = set(UserSecret.__table__.columns.keys())
    assert columns == {
        "id",
        "user_id",
        "secret_type",
        "status",
        "encrypted_value",
        "created_at",
        "updated_at",
    }
