"""Unit tests for DB-backed local authentication services."""

from collections.abc import Generator
from typing import cast

import pytest
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.auth.service import (
    ADMIN_ROLE,
    InvalidBootstrapInputError,
    bootstrap_admin,
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


def test_bootstrap_admin_creates_and_updates_idempotently(db_session: Session) -> None:
    admin = bootstrap_admin(db_session, "Admin@Example.COM", "Admin User")

    assert admin.email == "admin@example.com"
    assert admin.role == ADMIN_ROLE
    assert admin.is_active is True

    updated = bootstrap_admin(
        db_session,
        "admin@example.com",
        "Updated Admin",
    )

    assert updated.id == admin.id
    assert updated.display_name == "Updated Admin"
    assert updated.role == ADMIN_ROLE
    assert db_session.query(User).count() == 1


@pytest.mark.parametrize(
    ("email", "display_name"),
    [
        ("not-an-email", "Admin User"),
        ("admin@example.com", "   "),
    ],
)
def test_bootstrap_admin_rejects_invalid_input(
    db_session: Session,
    email: str,
    display_name: str,
) -> None:
    with pytest.raises(InvalidBootstrapInputError):
        bootstrap_admin(db_session, email, display_name)

    assert db_session.query(User).count() == 0
