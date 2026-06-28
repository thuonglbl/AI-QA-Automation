---
baseline_commit: 7641ef215742a18d6f5ca7951b6193abcf80164a
---
# Story 16.15: Fix per-request DB engine/pool leak

Status: done

> **Priority: P0 (freeze).** UAT finding #1 — strongest code-verified cause of the
> whole-system freeze observed during Bob's stage (thread create/delete hang).

## Story

As a QA user on a long-running deployed environment,
I want the backend to reuse one bounded database connection pool,
so that a long session on a slow on-prem model does not exhaust the database's connections and freeze thread create/delete and every other request.

### Observed bug

On UAT, after Bob runs for a while on the slow 235B model, the whole system freezes: creating a new thread or deleting an old one hangs. Local (fast models, frequent restarts) never hits it.

### Root cause (forensic, code-verified)

`get_db_session` ([db/session.py:29-36](src/ai_qa/db/session.py:29)) is the FastAPI DB dependency for every route; it calls `create_session_factory` → `create_db_engine` → `create_engine(...)` on **every request**, building a NEW connection pool (`pool_size=5, max_overflow=10, pool_pre_ping=True`) that is **never `dispose()`d** (`finally` only `session.close()`). The WS path ([websocket.py:247](src/ai_qa/api/websocket.py:247)) also builds a fresh factory per use. Under a long slow-model session with frontend polling, leaked pools accumulate until Postgres `max_connections` is exhausted → new connections (incl. thread create POST `/threads`, delete PATCH `/threads/{id}`) block/fail → freeze.

## Acceptance Criteria

1. **One pooled engine per DB config.** Given repeated `create_db_engine(settings)` calls for the same real database configuration, when they run, then they return the SAME engine instance (one shared, bounded pool) rather than a new pool per call.
2. **Test isolation preserved.** Given an in-memory SQLite URL, when `create_db_engine` runs, then it is NOT cached (a fresh engine per call) so the test suite's per-call database isolation is unchanged.
3. **Clean shutdown.** Given application shutdown, when the lifespan exits, then all cached engines are disposed and the cache cleared.
4. **No behavior change for callers.** Given routes, the WS path, health, and bootstrap that build sessions, when they obtain a session, then they transparently use the shared engine with no API change.

## Tasks / Subtasks

- [x] **Task 1 — Engine cache in `db/session.py` (AC1, AC2, AC4)**
  - [x] Add `_ENGINE_CACHE` keyed by `(url, pool_size, max_overflow, echo)`; `create_db_engine` returns the cached engine for real DBs and builds a fresh, uncached one for in-memory SQLite (`_engine_cache_key` returns `None`).
  - [x] `create_session_factory` / `get_db_session` unchanged in signature; they now bind a (cheap) sessionmaker to the shared engine.
- [x] **Task 2 — Dispose on shutdown (AC3)**
  - [x] Add `dispose_all_engines()`; call it in the `app.py` lifespan after `yield` (best-effort, never blocks shutdown).
- [x] **Task 3 — Tests (AC1, AC2, AC3)**
  - [x] `tests/db/test_session_engine_cache.py`: same engine reused for a real DB; in-memory sqlite never cached; dispose clears the cache and a fresh engine is built afterwards.
- [ ] **Task 4 — Verification gates**
  - [ ] ruff + mypy + full pytest green.
  - [ ] **On UAT during a freeze (diagnostic, Thuong):** `SELECT count(*) FROM pg_stat_activity;` — confirm it no longer climbs toward `max_connections` after redeploy.

## Files changed

- `src/ai_qa/db/session.py` (engine cache + `dispose_all_engines`)
- `src/ai_qa/api/app.py` (dispose on lifespan shutdown)
- `tests/db/test_session_engine_cache.py` (new)
