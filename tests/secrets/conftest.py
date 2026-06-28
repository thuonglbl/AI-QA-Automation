"""Shared fixtures for the per-user secret storage test suite.

Centralizes the in-memory SQLite scaffold and the user factory that both
``test_service.py`` and ``test_models.py`` rely on, so the setup lives in one
place (project rule #21 — reuse the canonical fixture instead of re-deriving).
"""

from collections.abc import Callable, Generator
from typing import cast

import pytest
from sqlalchemy import Table, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.auth.service import STANDARD_ROLE
from ai_qa.db.base import Base
from ai_qa.db.models import User
from ai_qa.secrets.models import UserSecret


@pytest.fixture
def session() -> Generator[Session]:
    """A fresh in-memory SQLite session with foreign-key enforcement enabled.

    Foreign keys are turned on per connection so the migration's
    ``ON DELETE CASCADE`` is genuinely exercised; the engine is disposed in
    teardown to avoid ``ResourceWarning: unclosed database`` (project rule #1).
    """
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(
        engine,
        tables=cast(list[Table], [User.__table__, UserSecret.__table__]),
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture
def make_user(session: Session) -> Callable[..., User]:
    """Factory that persists and returns a standard ``User`` (unique email per call)."""

    def _make(
        email: str = "user@example.com", role: str = STANDARD_ROLE, active: bool = True
    ) -> User:
        user = User(
            email=email,
            display_name=email.split("@")[0],
            role=role,
            is_active=active,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user

    return _make
