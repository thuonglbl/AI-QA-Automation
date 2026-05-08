# 12-1: PostgreSQL Persistence Foundation with SQLAlchemy and Alembic

## Header

```yaml
story_id: 12.1
story_key: 12-1-postgresql-persistence-foundation-with-sqlalchemy-and-alembic
epic: Epic 12 - Decoupled Backend, Database, Auth, and Project Foundation
status: done
created_by: BMad Story Agent
updated_by: BMad Dev Agent
created_at: 2026-05-04
updated_at: 2026-05-04
---
story_title: PostgreSQL Persistence Foundation with SQLAlchemy and Alembic
epic_title: Decoupled Backend, Database, Auth, and Project Foundation
epic_description: Pivot from single-user file-based workspace storage to a decoupled multi-user system with React frontend, FastAPI backend, PostgreSQL source of truth, and project-scoped artifacts.
```

## Requirements

### User Story

**As a** R&D engineer,
**I want** PostgreSQL persistence configured with SQLAlchemy models and Alembic migrations,
**So that** backend data has a versioned, scalable source of truth instead of ad-hoc workspace files.

### Acceptance Criteria (BDD)

**Scenario 1: Environment-driven PostgreSQL configuration**
```gherkin
Given the backend starts in development mode
When database configuration is loaded
Then the application can derive a SQLAlchemy-compatible PostgreSQL database URL from environment-driven settings
And database secrets are not hard-coded or committed
And configuration uses the existing Pydantic Settings pattern in src/ai_qa/config.py
```

**Scenario 2: Core SQLAlchemy 2.x schema models exist**
```gherkin
Given the persistence layer is imported
When SQLAlchemy metadata is inspected
Then SQLAlchemy 2.x models are defined for users, projects, project_memberships, pipeline_runs, artifacts, artifact_versions, and audit_events
And models use typed Mapped/mapped_column declarations
And relationships and constraints represent project membership, pipeline ownership, artifact versions, and audit context
```

**Scenario 3: Alembic initial migration is configured**
```gherkin
Given Alembic is installed and configured
When alembic upgrade head is run against a configured PostgreSQL database
Then the initial core schema migration creates or updates all persistence foundation tables successfully
And Alembic env.py uses the application model metadata as target_metadata
And migrations get the database URL from application settings or ALEMBIC/database environment variables
```

**Scenario 4: Database health is exposed through backend health check**
```gherkin
Given the FastAPI application is running
When a caller requests a backend health/readiness endpoint
Then the response reports application health
And includes database connectivity status based on a lightweight SELECT 1 check
And database connection failures return a clear degraded/unready status without leaking credentials
```

**Scenario 5: Tests run without polluting shared data**
```gherkin
Given backend tests need database access
When pytest database fixtures are used
Then tests can run against an isolated test database or transaction-scoped SQLAlchemy session
And test changes are rolled back or isolated between tests
And unit tests can validate metadata/configuration without requiring a live PostgreSQL server
```

## Developer Context

### Critical Architecture Requirements

**Architecture pivot guardrails:**
- React remains the frontend and FastAPI/Python remains the backend.
- PostgreSQL is now the source of truth for multi-user/project data.
- This story establishes persistence only; do not implement auth flows, admin APIs, project APIs, or business endpoints beyond health/readiness checks.
- R&D auth will use local email/password in later stories; Azure Entra ID SSO is deferred and must not be expanded here.
- Generated Markdown/Mermaid/script files remain project-scoped artifacts; this story only creates artifact metadata/version schema, not full artifact management APIs.

**Security/data requirements:**
- All data remains on-premises; no cloud database or external storage integration.
- Database credentials must come from `.env`, process environment, or local ignored config.
- Never log full database URLs with passwords.
- Store only password hash fields in schema; do not implement password hashing/auth endpoints in this story.

**SQLAlchemy/Alembic requirements:**
- Use SQLAlchemy 2.x typed ORM style (`DeclarativeBase`, `Mapped`, `mapped_column`, `relationship`).
- Use Alembic for schema versioning with `target_metadata = Base.metadata`.
- Prefer sync SQLAlchemy engine/session initially unless current code already requires async DB access. FastAPI health checks may use a sync dependency in a thread-safe, short-lived way or an explicit database service function.
- PostgreSQL-specific UUID support is acceptable, but keep tests able to inspect metadata without a live DB.

### Existing Codebase Context

**Current relevant files:**
```text
src/ai_qa/
├── config.py              # Existing AppSettings Pydantic Settings; extend here for DB config
├── models.py              # Existing Pydantic/shared API models; avoid mixing ORM models here if possible
└── api/
    ├── app.py             # FastAPI app factory; add/register health route or include router
    ├── routes.py          # Existing API routes; avoid unrelated business changes
    ├── schemas.py         # Existing API schemas
    └── auth/              # Existing auth-related code from earlier/deferred work; do not expand SSO

tests/
├── conftest.py            # Existing pytest fixtures; add DB fixtures carefully
├── test_api.py
└── test_config.py
```

**Recommended new structure:**
```text
src/ai_qa/db/
├── __init__.py
├── base.py                # DeclarativeBase, shared naming conventions, common mixins
├── models.py              # ORM model definitions for core schema
├── session.py             # engine/sessionmaker helpers and FastAPI session dependency
└── health.py              # SELECT 1 connectivity helper

alembic.ini
alembic/
├── env.py                 # Imports Base.metadata and settings-derived DB URL
├── script.py.mako
└── versions/
    └── <revision>_initial_core_schema.py

tests/db/
├── test_models_metadata.py
├── test_database_settings.py
└── test_session_strategy.py
```

### Core Schema Guidance

Implement the following tables at minimum:

| Table | Purpose | Required fields/constraints |
| --- | --- | --- |
| `users` | Local user/account foundation | `id`, `email` unique, `display_name`, `password_hash`, `role`, `is_active`, timestamps |
| `projects` | Project/workspace boundary | `id`, `name`, optional `description`, `created_by_user_id`, timestamps |
| `project_memberships` | User-to-project access | `id`, `project_id`, `user_id`, `role`, timestamps, unique `(project_id, user_id)` |
| `pipeline_runs` | Execution history | `id`, `project_id`, `started_by_user_id`, `status`, timestamps, provider/model/config summary JSON fields |
| `artifacts` | Project-scoped generated artifact metadata | `id`, `project_id`, optional `pipeline_run_id`, `kind`, `name`, `storage_path`, current version, timestamps |
| `artifact_versions` | Versioned artifact metadata | `id`, `artifact_id`, `version`, `content_hash`, optional `storage_path`, `created_by_user_id`, timestamps, unique `(artifact_id, version)` |
| `audit_events` | Compliance and troubleshooting trail | `id`, optional `user_id`, optional `project_id`, optional `pipeline_run_id`, `event_type`, `resource_type`, `resource_id`, `details` JSON, `created_at` |

Recommended implementation details:
- Use UUID primary keys for all entities.
- Use timezone-aware `DateTime(timezone=True)` timestamps.
- Use PostgreSQL `JSONB` for JSON fields if using dialect types; otherwise use generic JSON with PostgreSQL-compatible migration output.
- Add useful indexes for lookup paths: user email, membership user/project, pipeline project/status, artifact project/kind, audit project/event/created_at.
- Keep enums either as Python string enums mapped to SQLAlchemy Enum or constrained strings. If using PostgreSQL enums, ensure Alembic migration handles creation cleanly.
- Include cascade behavior intentionally: deleting projects should not accidentally erase audit history unless explicitly designed. Prefer nullable FKs with `ondelete="SET NULL"` for audit references.

### Configuration Requirements

Extend `AppSettings` with database fields, for example:
```python
database_url: str = Field(default="", description="Full SQLAlchemy database URL")
database_host: str = Field(default="localhost")
database_port: int = Field(default=5432)
database_name: str = Field(default="ai_qa_automation")
database_user: str = Field(default="ai_qa")
database_password: str = Field(default="")
database_pool_size: int = Field(default=5, ge=1)
database_max_overflow: int = Field(default=10, ge=0)
database_echo: bool = Field(default=False)
```

Provide a helper/property to build the URL when `database_url` is not set. Use URL escaping for usernames/passwords. Tests should verify this behavior without requiring PostgreSQL.

Expected environment variables:
```bash
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=ai_qa_automation
DATABASE_USER=<db-user>
DATABASE_PASSWORD=<db-password>
```

### FastAPI Health Check Requirements

Add or update health endpoints with minimal scope:
- Keep existing routes compatible.
- Add database readiness info to an endpoint such as `GET /health` or `GET /api/health`.
- Return no secrets.
- Recommended shape:
```json
{
  "status": "healthy|degraded",
  "database": {
    "status": "healthy|unhealthy|not_configured",
    "latency_ms": 3.2
  }
}
```

If the existing health endpoint currently has a different shape, preserve backwards compatibility and add fields rather than breaking tests/frontend.

### Testing Requirements

**Unit tests (no live DB required):**
- Settings derive a PostgreSQL URL from env/constructor values.
- URL masking helper hides credentials.
- `Base.metadata.tables` contains all required tables.
- Required unique constraints/indexes exist.
- Alembic env/migration files exist and reference expected table names.

**Optional integration tests (live PostgreSQL):**
- Gate live DB tests behind `TEST_DATABASE_URL`.
- Skip if not configured.
- Create schema in an isolated transaction or temporary schema and roll back/drop after test.
- Verify `SELECT 1` health check succeeds against configured test DB.

**Pytest fixture strategy:**
- Provide an `engine` fixture using `TEST_DATABASE_URL` when present.
- Provide a transaction-scoped `db_session` fixture that opens a connection, begins a transaction, yields a `Session`, then rolls back/closes.
- Avoid using developer/local production database by default.

### Implementation Sequence

1. **Dependencies**
   - Add runtime dependencies: `sqlalchemy>=2.0`, `alembic>=1.13`, and a PostgreSQL driver (`psycopg[binary]>=3.1` recommended).
   - Keep dependencies in `pyproject.toml` PEP 621 format.

2. **Design system for persistence code**
   - Create `src/ai_qa/db/base.py` with naming conventions and common timestamp/id mixins.
   - Create `src/ai_qa/db/models.py` with all core ORM models.
   - Export key objects from `src/ai_qa/db/__init__.py`.

3. **Database configuration/session**
   - Extend `AppSettings` with database settings and URL helper/masking helper.
   - Add `src/ai_qa/db/session.py` with engine/sessionmaker creation helpers.
   - Ensure helpers are lazy and do not connect at import time.

4. **Alembic setup**
   - Add `alembic.ini` and `alembic/env.py`.
   - Configure `target_metadata` from `ai_qa.db.base.Base.metadata` and import `ai_qa.db.models` so metadata is populated.
   - Add initial migration under `alembic/versions/` with explicit `upgrade()` and `downgrade()`.

5. **Health check**
   - Add `src/ai_qa/db/health.py` with a lightweight database connectivity check.
   - Register/extend a FastAPI health endpoint in `api/app.py` or `api/routes.py`.

6. **Tests**
   - Add metadata/config tests first.
   - Add fixture strategy for optional live database integration.
   - Run `pytest` for relevant tests. If full suite fails due unrelated prior work, document failures precisely.

## Out of Scope

Do **not** implement in Story 12.1:
- Local registration/login endpoints.
- Password hashing service or token/session issuance.
- Admin bootstrap CLI.
- RBAC enforcement middleware.
- Project management APIs.
- Pipeline persistence integration into existing agent workflows.
- Artifact upload/download/version APIs.
- Azure Entra ID SSO or MSAL changes.
- Frontend changes unless required to keep health display/tests passing.

## Project Context Reference

**From epics.md:**
- Epic 12 pivots to decoupled frontend/backend/database services.
- Story 12.1 acceptance criteria explicitly require PostgreSQL config, SQLAlchemy models, Alembic initial migration, DB health check, and isolated test DB/session strategy.
- Story 12.2 handles local email/password auth later; Story 12.3 handles RBAC later; Story 12.4 handles project APIs later.

**From architecture.md:**
- Backend is Python 3.12+ with FastAPI and `src/` layout.
- Pydantic Settings is the established configuration approach.
- Tests are top-level `tests/` with pytest/pytest-asyncio/pytest-cov.
- Data sovereignty and `.env` secret handling are non-negotiable.

**From PRD:**
- AI QA Automation is an on-premises enterprise tool.
- Security and data sovereignty are critical for banking/pharma/government clients.
- Auditability is required for future milestones; this story lays the audit schema foundation.

## Tasks/Subtasks

- [x] Add persistence dependencies (`sqlalchemy`, `alembic`, `psycopg[binary]`) to PEP 621 project dependencies.
- [x] Extend `AppSettings` with environment-driven PostgreSQL settings, URL derivation, and credential masking.
- [x] Create SQLAlchemy persistence package with declarative base, typed ORM models, relationships, constraints, indexes, UUID primary keys, timezone timestamps, and JSONB fields.
- [x] Add lazy SQLAlchemy engine/session helpers and optional transaction-scoped pytest database fixtures.
- [x] Configure Alembic with application metadata and an explicit initial core schema migration.
- [x] Extend backend health endpoint with database readiness status using a lightweight `SELECT 1` check.
- [x] Add unit tests for settings, metadata, migration presence, health behavior, and session strategy.
- [x] Run relevant and full validation suites.

## Dev Agent Record

### Implementation Plan

Implemented Story 12.1 as a persistence-only foundation:

1. Added SQLAlchemy/Alembic/psycopg dependencies and synced the lockfile.
2. Extended the existing Pydantic Settings pattern in `src/ai_qa/config.py`.
3. Added a dedicated `src/ai_qa/db/` package for ORM base, models, session helpers, and health checks.
4. Added Alembic config, env, script template, and explicit initial migration.
5. Extended `/api/health` to include database readiness while preserving `status` and `version` response fields.
6. Added metadata/config/unit tests that do not require live PostgreSQL and optional live DB fixtures gated by `TEST_DATABASE_URL`.

### Debug Log

- `python -m pytest tests/db -q` failed because the active Python environment did not have newly added SQLAlchemy installed.
- Ran `uv sync` to install/sync declared dependencies and update `uv.lock`.
- `uv run pytest tests/db -q` passed functionally but failed repository coverage gate because only DB tests were selected.
- `uv run pytest tests/db -q --no-cov` passed targeted DB tests without coverage gating.
- `uv run ruff check .` found import ordering and DB base naming issues; fixed with Ruff and minimal base cleanup.
- Final `uv run pytest -q` passed the full suite with coverage gate.

### Completion Notes

- PostgreSQL configuration is environment-driven and uses existing `AppSettings`.
- Database URLs can be derived from individual settings or supplied via `DATABASE_URL`.
- Credential masking avoids leaking passwords in safe representations.
- Core SQLAlchemy 2.x ORM schema exists for all required tables.
- Alembic uses `Base.metadata` as `target_metadata` and includes an explicit initial migration.
- Health endpoint now reports database readiness as `healthy`, `unhealthy`, or `not_configured` without secrets.
- Optional live DB fixtures are gated by `TEST_DATABASE_URL` and roll back per-test changes.
- No auth flows, business APIs, project APIs, artifact APIs, or frontend changes were implemented for this story.

### Validation

- `uv run pytest tests/db -q --no-cov` → `11 passed`
- `uv run ruff check .` → `All checks passed!`
- `uv run pytest -q` → `434 passed, 2 skipped`, coverage `76.94%` (threshold `50%`)

## File List

- `pyproject.toml`
- `uv.lock`
- `alembic.ini`
- `alembic/env.py`
- `alembic/script.py.mako`
- `alembic/versions/20260504_1201_initial_core_schema.py`
- `src/ai_qa/config.py`
- `src/ai_qa/api/routes.py`
- `src/ai_qa/db/__init__.py`
- `src/ai_qa/db/base.py`
- `src/ai_qa/db/models.py`
- `src/ai_qa/db/session.py`
- `src/ai_qa/db/health.py`
- `tests/db/conftest.py`
- `tests/db/test_database_settings.py`
- `tests/db/test_models_metadata.py`
- `tests/db/test_session_strategy.py`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/12-1-postgresql-persistence-foundation-with-sqlalchemy-and-alembic.md`

## Change Log

- 2026-05-04: Implemented PostgreSQL persistence foundation with SQLAlchemy models, Alembic migration, DB settings/session/health helpers, optional DB fixtures, and validation tests.
- 2026-05-04: User accepted implementation; story workflow marked done.

## Story Completion Status

```yaml
status: done
completion_notes: |
  Story 12.1 implementation accepted and workflow completed.

  Implemented persistence foundation only:
  - SQLAlchemy 2.x ORM schema
  - Alembic initial migration
  - environment-driven DB config
  - database health/readiness check
  - isolated test DB/session strategy

  Auth/business API work remained explicitly out of scope.
```
