"""SQLAlchemy engine and session helpers."""

import threading
from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ai_qa.config import AppSettings

# Process-wide engine cache. Each SQLAlchemy Engine owns a connection pool, so building
# a NEW engine on every call (the previous behaviour of ``create_db_engine``) leaked a
# fresh pool per request and never disposed it. Under a long-lived process — e.g. a slow
# on-premises model keeping Bob's extraction running for many minutes while the frontend
# keeps polling — the leaked pools exhaust the database's ``max_connections`` and the
# whole API freezes (new thread create/delete hang waiting for a connection). Reusing one
# pooled engine per distinct database configuration bounds the connection count. The lock
# makes the cache miss safe under the threadpool that runs sync routes concurrently.
_ENGINE_CACHE: dict[str, Engine] = {}
_ENGINE_CACHE_LOCK = threading.Lock()


def _engine_cache_key(settings: AppSettings) -> str | None:
    """Cache key for a poolable engine, or ``None`` when it must stay per-call.

    In-memory SQLite holds its data in the connection itself, so a shared engine would
    leak state across callers; it is never cached, preserving the test suite's per-call
    database isolation. Every real (file/Postgres) database is cached and pooled.
    """
    url = settings.sqlalchemy_database_url
    if url.startswith("sqlite") and (
        ":memory:" in url or url in ("sqlite://", "sqlite:///:memory:")
    ):
        return None
    return (
        f"{url}|{settings.database_pool_size}"
        f"|{settings.database_max_overflow}|{settings.database_echo}"
    )


def create_db_engine(settings: AppSettings | None = None) -> Engine:
    """Return a pooled SQLAlchemy engine, reused per database configuration.

    Reuses a cached engine for real databases (so the connection pool is shared and
    bounded) and builds a fresh, uncached engine for in-memory SQLite (test isolation).
    Does not connect at creation time.
    """
    settings = settings or AppSettings()
    key = _engine_cache_key(settings)
    if key is None:
        return _build_engine(settings)
    cached = _ENGINE_CACHE.get(key)
    if cached is not None:
        return cached
    with _ENGINE_CACHE_LOCK:
        # Double-checked: another thread may have built it while we waited for the lock.
        cached = _ENGINE_CACHE.get(key)
        if cached is None:
            cached = _build_engine(settings)
            _ENGINE_CACHE[key] = cached
        return cached


def _build_engine(settings: AppSettings) -> Engine:
    """Build a fresh SQLAlchemy engine (no caching). Does not connect at creation time."""
    return create_engine(
        settings.sqlalchemy_database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        echo=settings.database_echo,
        pool_pre_ping=True,
    )


def create_session_factory(settings: AppSettings | None = None) -> sessionmaker[Session]:
    """Create a configured SQLAlchemy sessionmaker bound to the (pooled) engine."""
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


def dispose_all_engines() -> None:
    """Dispose every cached engine and clear the cache (call on application shutdown)."""
    with _ENGINE_CACHE_LOCK:
        for engine in _ENGINE_CACHE.values():
            engine.dispose()
        _ENGINE_CACHE.clear()
