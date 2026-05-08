"""Database fixtures for optional live PostgreSQL integration tests."""

import os
from collections.abc import Generator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session


@pytest.fixture(scope="session")
def test_database_url() -> str | None:
    """Optional live database URL for integration tests."""
    return os.getenv("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def db_engine(test_database_url: str | None) -> Generator[Engine]:
    """Create a live test engine only when TEST_DATABASE_URL is configured."""
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")

    engine = create_engine(test_database_url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Generator[Session]:
    """Yield a transaction-scoped session that rolls back after each test."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
