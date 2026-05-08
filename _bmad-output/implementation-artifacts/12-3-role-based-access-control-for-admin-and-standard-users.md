# 12-3: Role-Based Access Control for Admin and Standard Users

## Header

```yaml
story_id: 12.3
story_key: 12-3-role-based-access-control-for-admin-and-standard-users
epic: Epic 12 - Decoupled Backend, Database, Auth, and Project Foundation
status: ready-for-dev
created_by: BMad Story Agent
created_at: 2026-05-05
story_title: Role-Based Access Control for Admin and Standard Users
epic_title: Decoupled Backend, Database, Auth, and Project Foundation
epic_description: Pivot from single-user file-based workspace storage to a decoupled multi-user system with React frontend, FastAPI backend, PostgreSQL source of truth, and project-scoped artifacts.
```

## Requirements

### User Story

**As an** admin,  
**I want** role-based permissions enforced by the backend,  
**So that** only authorized users can manage users and projects.

### Acceptance Criteria (BDD)

**Scenario 1: Admin users can access admin APIs**
```gherkin
Given an authenticated user has the admin role
When they access admin-only APIs
Then they can view the user list
And they can create projects
And they can assign users to projects
And responses use secret-free Pydantic schemas
```

**Scenario 2: Standard users cannot access admin-only endpoints**
```gherkin
Given an authenticated user has the standard role
When they access any admin-only endpoint
Then the request is rejected with a consistent authorization error
And no project, membership, or user-management mutation occurs
And the response does not disclose sensitive implementation details
```

**Scenario 3: Protected endpoints reject unauthenticated requests**
```gherkin
Given a request has no valid session cookie or bearer token
When it targets any protected API endpoint
Then the backend rejects it consistently
And admin endpoints are never reachable anonymously
```

**Scenario 4: Authorization failures are consistent and safe**
```gherkin
Given a caller lacks a required role or uses a stale/invalid identity
When authorization fails
Then the response uses a consistent status code and detail message
And the response does not reveal whether hidden users, projects, or memberships exist
And the failure is safe for both cookie and Authorization bearer-token callers
```

**Scenario 5: RBAC checks are covered by API tests**
```gherkin
Given RBAC dependencies and admin endpoints are implemented
When the automated API test suite runs
Then admin success paths are covered
And standard-user forbidden paths are covered
And unauthenticated protected-path behavior is covered
And current local-auth tests from Story 12.2 continue to pass
```

## Developer Context

### Epic 12 Context and Boundaries

Epic 12 is the course-correction epic that moves the application from a single-user, file-oriented workspace to a multi-user, project-scoped system. Story 12.1 established PostgreSQL/SQLAlchemy/Alembic persistence. Story 12.2 replaced JSON-file auth with PostgreSQL-backed local accounts, Argon2 password hashing via `pwdlib`, JWT cookie/bearer sessions, `/auth/me`, and admin bootstrap.

This story must add backend authorization guardrails on top of that completed auth foundation. Treat Story 12.2 as the source of authenticated identity, but do not blindly trust role claims in old tokens when an endpoint needs authorization; re-check active user state from the database or through a shared current-user dependency.

**Do implement:**
- Central RBAC helpers/dependencies for authenticated user and admin-only access.
- Consistent 401/403 behavior for unauthenticated vs unauthorized API calls.
- Admin-only endpoints sufficient to satisfy the story: list users, create projects, assign users to projects.
- API tests for admin success, standard-user denial, and unauthenticated denial.
- Thin route handlers that use Pydantic request/response schemas and SQLAlchemy sessions.

**Do not implement:**
- Frontend admin/user/project management screens; Story 12.6 owns frontend UI.
- Full project list/member-scoped browsing behavior; Story 12.4 owns user-facing project and membership management depth.
- Project-scoped artifact persistence; Story 12.5 owns artifact service.
- Agent pipeline refactor from workspace paths to project context; Story 12.7 owns that.
- Azure Entra ID/MSAL/SSO; Epic 11 remains deferred.

### Existing Codebase Intelligence

Relevant current files and patterns:

```text
src/ai_qa/
├── api/
│   ├── app.py                    # create_app() includes AuthMiddleware, auth router, /api router
│   ├── routes.py                 # current protected pipeline endpoints under /api
│   └── auth/
│       ├── local.py              # /auth/register, /auth/login, /auth/me, /auth/status
│       ├── middleware.py         # session cookie/bearer auth; protects /api/* and /ws
│       └── session.py            # JWT session encode/decode
├── auth/
│   ├── password.py               # Argon2 password helpers
│   ├── service.py                # register/authenticate/bootstrap helpers and role constants
│   └── bootstrap_admin.py        # CLI/module admin bootstrap path
└── db/
    ├── models.py                 # User, Project, ProjectMembership, PipelineRun, Artifact, ArtifactVersion, AuditEvent
    └── session.py                # get_db_session(settings) and engine/session helpers

tests/
├── test_auth_api.py              # local auth route tests from Story 12.2
├── test_auth_service.py          # auth service tests
├── test_auth_password.py         # password helper tests
└── db/                           # DB metadata/settings/session tests
```

Important model fields already exist:
- `User.role`: string role, currently `admin` or `standard` by convention.
- `User.is_active`: inactive users must not be treated as authenticated/authorized.
- `Project.created_by_user_id`: can capture admin creator for admin project creation.
- `ProjectMembership.role`: project-level role, default `member`; use `member` unless the endpoint accepts a constrained role.
- `ProjectMembership` has a unique `(project_id, user_id)` constraint.

Existing middleware already protects `/api/*` and `/ws` from unauthenticated callers. Keep that behavior and layer route-level RBAC on top. Do not make admin endpoints public-path exceptions.

### Architecture and Security Guardrails

- Backend remains FastAPI in `src/ai_qa/api` with application factory in `api/app.py`.
- Use SQLAlchemy 2.x ORM models from `src/ai_qa/db/models.py`; do not introduce a second project/user store.
- Use Pydantic request/response schemas; never return `password_hash`, JWT tokens, session cookies, or raw ORM objects from admin APIs.
- Prefer central dependencies, e.g. `get_current_active_user(...)` and `require_admin(...)`, so later stories can reuse the same guardrails.
- Authorization checks should use database state, not only JWT role claims, to handle role changes, inactive users, deleted users, and stale tokens.
- Standardize errors:
  - unauthenticated / invalid / stale identity: `401` with a generic `Not authenticated`-style detail;
  - authenticated but insufficient role: `403` with a generic `Forbidden`-style detail.
- Avoid leaking whether a target user/project exists to unauthorized users. Since admin routes require admin first, detailed 404s are acceptable only after admin authorization succeeds.
- Enforce public registration remains standard-user only; do not add public role assignment.
- If adding project creation now, keep it minimal and admin-only; Story 12.4 may extend schemas and member-facing project APIs later.

### Recommended Implementation Shape

Create or extend a small RBAC module rather than scattering role checks in every route:

```text
src/ai_qa/api/auth/rbac.py
```

Suggested contents:

```python
from collections.abc import Generator
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.db.models import User

ADMIN_ROLE = "admin"
STANDARD_ROLE = "standard"

async def get_current_active_user(
    request: Request,
    db: Session = Depends(get_db_session_dependency),
) -> User:
    ...

async def require_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    ...
```

Implementation expectations:
- Pull `request.state.user` from middleware.
- Parse `user_id` as UUID where possible; fall back to email only if absolutely needed for compatibility.
- Load `User` from DB and verify `is_active`.
- Require `role == "admin"` for admin dependencies.
- Return ORM `User` internally, but route responses must serialize through Pydantic schemas.

Add a dedicated admin router, for example:

```text
src/ai_qa/api/admin.py
```

Recommended endpoints under `/api/admin`:

- `GET /api/admin/users`
  - Admin-only.
  - Returns list of users with `id`, `email`, `display_name`, `role`, `is_active`, `created_at`, `updated_at` if available.
  - Excludes password hash.

- `POST /api/admin/projects`
  - Admin-only.
  - Creates a project with `name` and optional `description`.
  - Sets `created_by_user_id` to current admin id.
  - Returns secret-free project schema.
  - Validate name is non-empty and bounded in length.

- `POST /api/admin/projects/{project_id}/memberships`
  - Admin-only.
  - Assigns a user to a project.
  - Request includes `user_id` and optional membership `role` defaulting to `member`.
  - Idempotency: if membership already exists, either return existing membership or update role predictably. Document/test the chosen behavior.
  - Return secret-free membership schema including project/user ids and role.

Wire the router in `src/ai_qa/api/app.py` after the main API router or near it:

```python
from ai_qa.api.admin import router as admin_router
...
app.include_router(admin_router, prefix="/api")
```

### Previous Story Intelligence (12.2)

Story 12.2 completed local auth but its story file contains review findings that matter for RBAC work:

- Revalidate current user against the database instead of trusting stale JWT claims.
- Apply consistent auth errors and avoid sensitive leakage.
- Protect WebSocket subpaths consistently if touching middleware.
- Replace brittle auth API test dependency override patterns with stable override hooks if adding tests.
- Bearer-token logout semantics are imperfect; avoid widening token behavior unless needed.

Use these learnings proactively. RBAC must not depend only on `request.state.user.role`, because role claims can become stale after an admin changes a user or deactivates an account.

### Testing Requirements

Minimum tests for this story:

- `require_admin` allows active admin users and rejects standard users.
- `require_admin` rejects inactive/deleted/stale-token users.
- `GET /api/admin/users`:
  - admin succeeds and response excludes `password_hash`;
  - standard user receives 403;
  - unauthenticated request receives 401 or the project-standard unauthenticated response.
- `POST /api/admin/projects`:
  - admin creates a project with `created_by_user_id`;
  - standard user cannot create a project.
- `POST /api/admin/projects/{project_id}/memberships`:
  - admin assigns a user to a project;
  - duplicate assignment behavior is deterministic and covered;
  - missing target user/project after admin authorization returns safe 404.
- Existing Story 12.2 tests continue to pass.

Prefer tests that can run without a live PostgreSQL server by using the existing app dependency override/test-session pattern or SQLite-compatible SQLAlchemy sessions. Keep optional live PostgreSQL tests gated by `TEST_DATABASE_URL`.

Validation commands:

```powershell
uv run ruff check .
uv run pytest tests -q
```

If the full suite is slow during development, targeted debugging is acceptable, but the final Dev Agent Record should capture the broadest practical validation.

## Tasks / Subtasks

- [x] Add central RBAC dependencies. (AC: 2, 3, 4)
  - [x] Implement current active user lookup that revalidates `request.state.user` against PostgreSQL.
  - [x] Implement `require_admin` with consistent 403 handling for standard users.
  - [x] Reuse role constants from `ai_qa.auth.service` or define one canonical role source to avoid spelling drift.
- [x] Add admin API schemas and router. (AC: 1, 2, 4)
  - [x] Add secret-free user, project, and membership response schemas.
  - [x] Implement admin-only user listing.
  - [x] Implement admin-only project creation.
  - [x] Implement admin-only project membership assignment with deterministic duplicate handling.
- [x] Wire admin router into the FastAPI app. (AC: 1, 2, 3)
  - [x] Include admin routes under `/api/admin`.
  - [x] Ensure middleware still protects `/api/admin/*` as protected API routes.
- [x] Preserve local-auth boundaries from Story 12.2. (AC: 2, 3, 4)
  - [x] Do not allow public registration to assign admin role.
  - [x] Do not return password hashes or token internals in admin responses.
  - [x] Ensure inactive users cannot pass RBAC even with old tokens.
- [x] Add automated RBAC/API tests. (AC: 5)
  - [x] Cover admin success paths.
  - [x] Cover standard-user forbidden paths.
  - [x] Cover unauthenticated protected endpoint behavior.
  - [x] Run Ruff and pytest; record results in Dev Agent Record.

### Review Findings

- [x] [Review][Patch] Project name validation allows whitespace-only names [src/ai_qa/api/admin.py:38,91-99]
- [x] [Review][Patch] Membership role accepts blank-after-trim values and arbitrary role strings [src/ai_qa/api/admin.py:59,118-130]
- [x] [Review][Patch] Membership assignment can assign inactive users to projects [src/ai_qa/api/admin.py:113-127]
- [x] [Review][Patch] Concurrent duplicate membership requests can raise an unhandled integrity error [src/ai_qa/api/admin.py:119-132]
- [x] [Review][Patch] RBAC request-state handling can 500 for malformed session user objects [src/ai_qa/api/auth/rbac.py:27-28]
- [x] [Review][Patch] Targeted validation command may fail under default coverage settings [_bmad-output/implementation-artifacts/12-3-role-based-access-control-for-admin-and-standard-users.md:315-318]
- [x] [Review][Patch] Tests catch broad Exception instead of HTTPException [tests/test_admin_rbac_api.py]
- [x] [Review][Patch] Test DB session helper uses next(db_override()) without retaining the generator [tests/test_admin_rbac_api.py]
- [x] [Review][Patch] Add tests for normalization and inactive-user membership edge cases [tests/test_admin_rbac_api.py]

## Out of Scope

- Frontend login, project picker, or admin management screens.
- Non-admin project list and member-scoped project visibility APIs.
- Full project CRUD, project deletion, invitation flows, or membership removal.
- Artifact storage/service implementation.
- Pipeline run/project-context refactor.
- Azure Entra ID SSO or enterprise OAuth flows.

## Project Context Reference

- `_bmad-output/planning-artifacts/epics.md`, Epic 12 and Story 12.3: RBAC must allow admins to list users/create projects/assign users, block standard users, reject unauthenticated protected requests, and cover checks with API tests.
- `_bmad-output/implementation-artifacts/12-2-local-authentication-and-admin-bootstrap.md`: completed DB-backed local auth, session payloads, `/auth/me`, admin bootstrap, and review learnings about stale JWT claims.
- `src/ai_qa/api/auth/local.py`: current auth router and `get_db_session_dependency` pattern.
- `src/ai_qa/api/auth/middleware.py`: cookie/bearer middleware that populates `request.state.user` and protects `/api/*`.
- `src/ai_qa/db/models.py`: existing User, Project, and ProjectMembership ORM models required for RBAC/admin endpoints.
- `src/ai_qa/api/app.py`: FastAPI app factory where new admin router must be included.

## Dev Agent Record

### Agent Model Used

GPT-OSS 120B (Medium)

### Debug Log References

- `uv run pytest tests/test_admin_rbac_api.py -q` initially exposed one test setup failure, then passed with `--no-cov` after fixing request-state setup. Use `--no-cov` for targeted test runs because repository-level pytest defaults enforce total project coverage.
- `uv run ruff check .` initially reported B008 dependency-default issues in new RBAC/admin modules; resolved with module-level dependency aliases.
- Final validation: `uv run ruff check .` passed.
- Final validation: `uv run pytest tests -q` passed (`454 passed, 2 skipped`, coverage 78.25%).
- Review fix validation: `uv run ruff check src/ai_qa/api/admin.py src/ai_qa/api/auth/rbac.py tests/test_admin_rbac_api.py` passed.
- Review fix validation: `uv run pytest tests/test_admin_rbac_api.py -q --no-cov` passed (`9 passed`).

### Completion Notes List

- Added central RBAC dependencies that revalidate `request.state.user` against the database and reject inactive/deleted/stale identities with `401 Not authenticated`.
- Added reusable admin authorization dependency returning consistent `403 Forbidden` for active standard users.
- Added `/api/admin/users`, `/api/admin/projects`, and `/api/admin/projects/{project_id}/memberships` with secret-free Pydantic schemas.
- Implemented deterministic duplicate membership handling by updating the existing membership role and returning the same membership record.
- Wired admin routes under `/api/admin`, preserving existing middleware protection for `/api/*` paths.
- Added RBAC/API tests for admin success paths, standard-user denials, unauthenticated access, stale inactive-user tokens, secret-free responses, project creation, and membership assignment.

### File List

- `src/ai_qa/api/admin.py`
- `src/ai_qa/api/app.py`
- `src/ai_qa/api/auth/rbac.py`
- `tests/test_admin_rbac_api.py`
- `_bmad-output/implementation-artifacts/12-3-role-based-access-control-for-admin-and-standard-users.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Story Completion Status

```yaml
status: done
completion_notes: |
  Story 12.3 implementation complete. Backend RBAC now revalidates current users from the database, enforces admin-only access for admin APIs, exposes secret-free user/project/membership schemas, supports deterministic membership reassignment, rejects inactive membership targets, validates normalized admin inputs, and includes automated API coverage for admin, standard-user, unauthenticated, malformed request-state, normalization, inactive-user, and stale-token paths.
```
