"""Unit tests for DB-backed local authentication services."""

from collections.abc import Generator
from typing import cast

import pytest
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.auth.service import (
    ADMIN_ROLE,
    STANDARD_ROLE,
    AuthFailure,
    DuplicateUserError,
    InvalidBootstrapInputError,
    authenticate_user,
    bootstrap_admin,
    register_user,
)
from ai_qa.db.base import Base
from ai_qa.db.models import User


@pytest.fixture
def db_session() -> Generator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=cast("list[Table]", [User.__table__]))
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
    engine.dispose()


def test_register_user_normalizes_email_and_assigns_standard_role(db_session: Session) -> None:
    user = register_user(db_session, "Person@Example.COM", "Person One", "super-secret")

    assert user.email == "person@example.com"
    assert user.display_name == "Person One"
    assert user.role == STANDARD_ROLE
    assert user.is_active is True
    assert user.password_hash != "super-secret"


def test_register_duplicate_email_is_case_insensitive(db_session: Session) -> None:
    register_user(db_session, "person@example.com", "Person One", "super-secret")

    with pytest.raises(DuplicateUserError):
        register_user(db_session, "PERSON@example.com", "Other", "another-secret")

    assert db_session.query(User).count() == 1


def test_authenticate_user_success_and_generic_failures(db_session: Session) -> None:
    user = register_user(db_session, "person@example.com", "Person One", "super-secret")

    assert authenticate_user(db_session, "PERSON@example.com", "super-secret") == user
    assert isinstance(authenticate_user(db_session, "person@example.com", "wrong"), AuthFailure)
    assert isinstance(authenticate_user(db_session, "missing@example.com", "wrong"), AuthFailure)

    user.is_active = False
    db_session.commit()
    assert isinstance(
        authenticate_user(db_session, "person@example.com", "super-secret"), AuthFailure
    )


def test_bootstrap_admin_creates_and_updates_idempotently(db_session: Session) -> None:
    admin = bootstrap_admin(db_session, "Admin@Example.COM", "Admin User", "first-secret")

    assert admin.email == "admin@example.com"
    assert admin.role == ADMIN_ROLE
    assert admin.is_active is True
    first_hash = admin.password_hash

    updated = bootstrap_admin(
        db_session,
        "admin@example.com",
        "Updated Admin",
        "second-secret",
        update_password=False,
    )

    assert updated.id == admin.id
    assert updated.display_name == "Updated Admin"
    assert updated.role == ADMIN_ROLE
    assert updated.password_hash == first_hash
    assert db_session.query(User).count() == 1


def test_authenticate_user_handles_malformed_password_hash(db_session: Session) -> None:
    user = register_user(db_session, "person@example.com", "Person One", "super-secret")
    user.password_hash = "not-a-valid-password-hash"
    db_session.commit()

    result = authenticate_user(db_session, "person@example.com", "super-secret")

    assert isinstance(result, AuthFailure)


@pytest.mark.parametrize(
    ("email", "display_name", "password"),
    [
        ("not-an-email", "Admin User", "valid-secret"),
        ("admin@example.com", "Admin User", "short"),
        ("admin@example.com", "   ", "valid-secret"),
    ],
)
def test_bootstrap_admin_rejects_invalid_input(
    db_session: Session,
    email: str,
    display_name: str,
    password: str,
) -> None:
    with pytest.raises(InvalidBootstrapInputError):
        bootstrap_admin(db_session, email, display_name, password)

    assert db_session.query(User).count() == 0
