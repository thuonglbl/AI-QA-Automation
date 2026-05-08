"""SQLAlchemy engine and session helpers."""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ai_qa.config import AppSettings


def create_db_engine(settings: AppSettings | None = None) -> Engine:
    """Create a SQLAlchemy engine without connecting at import time."""
    settings = settings or AppSettings()
    return create_engine(
        settings.sqlalchemy_database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        echo=settings.database_echo,
        pool_pre_ping=True,
    )


def create_session_factory(settings: AppSettings | None = None) -> sessionmaker[Session]:
    """Create a configured SQLAlchemy sessionmaker."""
    engine = create_db_engine(settings)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def get_db_session(settings: AppSettings | None = None) -> Generator[Session]:
    """FastAPI dependency that yields a short-lived database session."""
    session_factory = create_session_factory(settings)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
