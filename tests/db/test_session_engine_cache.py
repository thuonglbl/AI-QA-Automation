"""Regression tests for the DB engine/pool cache (Story 16.15).

``get_db_session`` used to build a NEW SQLAlchemy engine (and connection pool) on every
request and never dispose it, leaking pools until the database's ``max_connections`` was
exhausted and the API froze (thread create/delete hung). ``create_db_engine`` now reuses
one pooled engine per database configuration; in-memory SQLite stays per-call so the test
suite keeps its database isolation.
"""

import ai_qa.db.session as session_mod
from ai_qa.config import AppSettings
from ai_qa.db.session import _engine_cache_key, create_db_engine, dispose_all_engines


def _file_db_settings() -> AppSettings:
    # A non-memory sqlite URL is cacheable and needs no running server (engine creation
    # is lazy — no connection is opened in these tests).
    return AppSettings(database_url="sqlite:///./_engine_cache_regression.db")


def test_real_db_engine_is_cached_and_reused() -> None:
    dispose_all_engines()
    settings = _file_db_settings()
    try:
        first = create_db_engine(settings)
        second = create_db_engine(settings)
        assert first is second  # one pooled engine reused, not leaked per call
    finally:
        dispose_all_engines()


def test_in_memory_sqlite_is_never_cached() -> None:
    # In-memory SQLite must be excluded from the shared engine cache so each caller gets
    # an isolated database. We assert the cache-key guard directly: create_db_engine
    # itself cannot build an in-memory engine with pool args (SQLite uses a
    # SingletonThreadPool) and prod never does — the point is only that such a URL is
    # never cached, so a None key (= per-call, uncached) is the correct contract.
    assert _engine_cache_key(AppSettings(database_url="sqlite://")) is None
    assert _engine_cache_key(AppSettings(database_url="sqlite:///:memory:")) is None


def test_dispose_clears_cache_so_a_fresh_engine_is_built() -> None:
    dispose_all_engines()
    settings = _file_db_settings()
    try:
        first = create_db_engine(settings)
        assert session_mod._ENGINE_CACHE  # cached
        dispose_all_engines()
        assert not session_mod._ENGINE_CACHE  # cleared on shutdown
        third = create_db_engine(settings)
        assert first is not third  # a fresh engine after dispose
    finally:
        dispose_all_engines()
