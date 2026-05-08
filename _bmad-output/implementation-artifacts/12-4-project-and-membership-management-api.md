# 12-4: Project and Membership Management API

## Header

```yaml
story_id: 12.4
story_key: 12-4-project-and-membership-management-api
epic: Epic 12 - Decoupled Backend, Database, Auth, and Project Foundation
status: done
created_by: BMad Story Agent
created_at: 2026-05-05
story_title: Project and Membership Management API
epic_title: Decoupled Backend, Database, Auth, and Project Foundation
epic_description: Pivot from single-user file-based workspace storage to a decoupled multi-user system with React frontend, FastAPI backend, PostgreSQL source of truth, and project-scoped artifacts.
```

## Requirements

### User Story

**As an** admin,  
**I want** to create projects and assign users to them,  
**So that** project teams can share the same QA automation workspace and results.

### Acceptance Criteria (BDD)

**Scenario 1: Admin-managed project memberships are persisted**
```gherkin
Given users and projects exist
When an active admin assigns an active user to a project
Then the project_memberships table stores the many-to-many relationship between the user and project
And duplicate assignments are deterministic and do not create duplicate membership rows
And response schemas do not expose password hashes, tokens, or raw ORM internals
```

**Scenario 2: Assigned users can list their projects after login**
```gherkin
Given a standard user is assigned to one or more active projects
When the authenticated user requests their project list
Then the API returns only projects where that user has a project_memberships row
And each result includes the user's membership role for that project
And the endpoint rejects unauthenticated requests consistently
```

**Scenario 3: Admins can list all projects**
```gherkin
Given an authenticated user has the admin role
When they request the project list
Then the API returns all projects regardless of membership
And each project includes enough membership summary data for administration
And standard users still only see their own projects
```

**Scenario 4: Project-scoped endpoints validate membership**
```gherkin
Given project-scoped API endpoints are available
When a standard user requests a project they do not belong to
Then the backend rejects the request without returning project data
And the response does not reveal sensitive details about hidden projects
When an admin requests any project-scoped endpoint
Then the request is allowed even if the admin is not an explicit member
```

**Scenario 5: OpenAPI documents the management schemas**
```gherkin
Given the FastAPI app starts
When a developer opens /docs or /openapi.json
Then project list, project detail, and membership management endpoints are present
And request/response models are typed through Pydantic schemas
And route tags make the project/member APIs discoverable
```

## Developer Context

### Epic 12 Context and Boundaries

Epic 12 moves the product from a single-user file workspace to a multi-user, project-scoped system. Stories 12.1 through 12.3 already established SQLAlchemy/Alembic persistence, PostgreSQL-backed local auth, JWT cookie/bearer sessions, central RBAC dependencies, and minimal admin APIs for user listing, project creation, and membership assignment.

This story deepens project and membership APIs beyond the RBAC smoke endpoints. The main value is that authenticated users can now discover the projects they may work in, and future pipeline/artifact endpoints can share a single membership guard rather than duplicating authorization logic.

**Do implement:**
- User-facing project list/detail APIs for authenticated users.
- Admin project list/detail visibility across all projects.
- Reusable project membership authorization dependency/helper for project-scoped endpoints.
- Membership persistence behavior based on the existing `ProjectMembership` ORM model.
- Tests for admin, member, non-member, unauthenticated, inactive/deleted/stale-user paths where relevant.
- OpenAPI-friendly Pydantic request/response schemas.

**Do not implement:**
- Frontend login/project picker/admin screens; Story 12.6 owns UI.
- Project-scoped artifact save/read service; Story 12.5 owns artifact persistence.
- Pipeline refactor from workspace paths to selected project context; Story 12.7 owns it.
- Azure Entra ID/MSAL/SSO; Epic 11 remains deferred.
- Complex invitation flows, email notifications, or self-service membership requests.

### Existing Codebase Intelligence

Relevant current files and patterns:

```text
src/ai_qa/
├── api/
│   ├── app.py                    # create_app() includes auth, main API, and admin routers
│   ├── admin.py                  # Story 12.3 admin schemas/routes under /api/admin
│   ├── routes.py                 # existing protected pipeline/action routes under /api
│   └── auth/
│       ├── local.py              # auth routes and get_db_session_dependency
│       ├── middleware.py         # cookie/bearer auth; protects /api/* and /ws
│       └── rbac.py               # get_current_active_user() and require_admin()
├── auth/
│   └── service.py                # ADMIN_ROLE/STANDARD_ROLE constants and local auth helpers
└── db/
    ├── models.py                 # User, Project, ProjectMembership, PipelineRun, Artifact...
    └── session.py                # SQLAlchemy session helpers

tests/
├── test_admin_rbac_api.py        # Story 12.3 admin/RBAC API test patterns
├── test_auth_api.py              # auth route tests
└── db/                           # DB model/session tests
```

Important model facts:
- `User.id` is UUID primary key; `User.role` is currently `admin` or `standard` by convention.
- `User.is_active` must be revalidated before any protected action.
- `Project.id`, `Project.name`, `Project.description`, and `Project.created_by_user_id` already exist.
- `ProjectMembership` has `project_id`, `user_id`, `role`, and a unique `(project_id, user_id)` constraint.
- Relationship fields exist for `Project.memberships` and `User.memberships`.

### Architecture and Security Guardrails

- Backend remains FastAPI in `src/ai_qa/api` with app composition in `api/app.py`.
- Use SQLAlchemy 2.x ORM and existing models; do not introduce a parallel project store.
- Use Pydantic schemas with `ConfigDict(from_attributes=True)` where returning ORM-backed responses.
- Reuse `get_current_active_user` and `require_admin` from `src/ai_qa/api/auth/rbac.py`; do not trust JWT role claims alone.
- Centralize project membership checks so Story 12.5 artifacts and Story 12.7 pipeline routes can reuse them.
- Error semantics should remain consistent with Story 12.3:
  - unauthenticated, invalid, deleted, inactive, or stale identity: `401` with generic `Not authenticated`-style detail;
  - authenticated but not allowed: `403` with generic `Forbidden`-style detail;
  - missing target resources after authorization succeeds: safe `404`.
- Avoid leaking hidden project existence to non-members. For member-scoped detail routes, a generic `404 Resource not found` or `403 Forbidden` is acceptable, but choose one behavior and test it.
- Admin routes under `/api/admin` are protected by existing middleware because `/api/*` is protected.

### Recommended Implementation Shape

Prefer adding a project router separate from the admin router, while keeping admin-only mutation routes in `admin.py` if they already exist.

Suggested new module:

```text
src/ai_qa/api/projects.py
```

Suggested user-facing endpoints under `/api/projects`:

- `GET /api/projects`
  - Authenticated users only.
  - Admins return all projects.
  - Standard users return only projects where `ProjectMembership.user_id == current_user.id`.
  - Include current user's project membership role when applicable.

- `GET /api/projects/{project_id}`
  - Authenticated users only.
  - Admins may access any project.
  - Standard users may access only projects where they are members.
  - Return secret-free project detail and membership information.

Suggested reusable helper/dependency:

```python
async def require_project_member_or_admin(
    project_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session_dependency),
) -> Project:
    ...
```

Implementation expectations:
- Query the database for the project and membership in the same request session.
- Do not return raw ORM objects that include relationship graphs accidentally; serialize through response schemas.
- Avoid N+1 surprises in list endpoints. Use explicit joins/selects or `selectinload` when returning membership summaries.
- Keep membership roles constrained to known values. Story 12.3 currently allows `member` and `owner` for admin membership assignment.
- Consider whether admins should be added as `owner` automatically when creating projects. If changing current 12.3 behavior, cover it with tests and document it in the Dev Agent Record; otherwise leave creation semantics unchanged.

### Previous Story Intelligence (12.3)

Story 12.3 added:
- `src/ai_qa/api/auth/rbac.py` with DB-backed `get_current_active_user()` and `require_admin()`.
- `src/ai_qa/api/admin.py` with `/api/admin/users`, `/api/admin/projects`, and `/api/admin/projects/{project_id}/memberships`.
- Deterministic duplicate membership assignment by updating the existing membership role.
- Validation preventing whitespace-only project names, arbitrary/blank membership roles, inactive membership targets, and malformed session-user 500s.
- Tests in `tests/test_admin_rbac_api.py` that should be reused as patterns for authenticated admin/standard requests and SQLite-compatible DB sessions.

Review lessons to preserve:
- Do not assign inactive users to projects.
- Do not rely only on middleware `request.state.user`; revalidate from DB through RBAC dependencies.
- Catch expected `HTTPException` in dependency tests, not broad `Exception`.
- If testing with generator-based DB overrides, retain/close the generator instead of using `next(db_override())` without cleanup.
- Use `--no-cov` for narrow targeted pytest runs when repository coverage settings interfere; full final validation should run the broad suite when practical.

### Git Intelligence

Recent commits show the implementation sequence and current architectural direction:

```text
db1a9ab feat 12-3: Role-Based Access Control for Admin and Standard Users
172b73b refactor: 12-2: Local Authentication and Admin Bootstrap
3fe606b refactor: 12-1: PostgreSQL Persistence Foundation with SQLAlchemy and Alembic
```

Build on the 12.3 APIs instead of replacing them. Any endpoint overlap should be backward-compatible unless tests are intentionally updated.

## Tasks / Subtasks

- [x] Add project-scoped API schemas and router. (AC: 2, 3, 5)
  - [x] Create `src/ai_qa/api/projects.py` or an equivalent cohesive module.
  - [x] Define secret-free project list/detail/membership summary response schemas.
  - [x] Tag routes so `/docs` clearly exposes project/member APIs.
- [x] Implement authenticated project listing. (AC: 2, 3)
  - [x] Return all projects for active admins.
  - [x] Return only membership projects for active standard users.
  - [x] Include current user's membership role where applicable.
  - [x] Ensure unauthenticated requests are rejected by existing auth middleware/dependencies.
- [x] Implement project detail and reusable membership authorization. (AC: 4)
  - [x] Add a helper/dependency such as `require_project_member_or_admin`.
  - [x] Allow admins to access all project detail routes.
  - [x] Reject standard-user access to non-member projects without leaking sensitive details.
  - [x] Revalidate inactive/deleted/stale identities through `get_current_active_user`.
- [x] Preserve and extend admin membership management. (AC: 1, 3, 5)
  - [x] Keep existing admin membership assignment deterministic and unique.
  - [x] Add admin project/member list or detail behavior if needed to satisfy all-project visibility.
  - [x] Keep membership roles constrained and inactive-user assignment blocked.
- [x] Wire routes into the FastAPI app. (AC: 2, 3, 4, 5)
  - [x] Include project router under `/api/projects` or equivalent protected prefix.
  - [x] Verify middleware protects all new `/api/*` endpoints.
- [x] Add automated API tests. (AC: 1, 2, 3, 4, 5)
  - [x] Cover admin project list/detail access across all projects.
  - [x] Cover standard user listing only assigned projects.
  - [x] Cover standard user denial/non-disclosure for non-member project detail.
  - [x] Cover unauthenticated project API rejection.
  - [x] Cover duplicate membership behavior remains deterministic.
  - [x] Cover OpenAPI includes new project/member routes and schemas.

### Review Findings

✅ Clean review — all adversarial review layers passed with no unresolved findings.

Review validation executed:
- Blind Hunter: no actionable findings after triage.
- Edge Case Hunter: no unhandled edge cases found in the Story 12.4 scope.
- Acceptance Auditor: implementation satisfies AC1-AC5 and documented guardrails.
- Targeted regression: `.\.venv\Scripts\python.exe -m pytest tests/test_project_api.py tests/test_admin_rbac_api.py --no-cov` passed (`15 passed`).

## Out of Scope

- React project picker and admin screens.
- Artifact storage/versioning service.
- Pipeline run scoping and WebSocket project selection.
- Deleting projects, removing members, invitations, audit-event expansion, or email notifications.
- Enterprise SSO or external identity-provider authorization.

## Project Context Reference

- `_bmad-output/planning-artifacts/epics.md`, Epic 12 and Story 12.4: project membership relationship, user project visibility, admin all-project visibility, membership validation, and OpenAPI documentation requirements.
- `_bmad-output/planning-artifacts/architecture.md`: FastAPI backend, SQLAlchemy/Pydantic patterns, security/data-sovereignty guardrails, pytest/Ruff standards.
- `_bmad-output/planning-artifacts/prd.md`: multi-user web expansion supports QA team collaboration while preserving zero workflow disruption for testers.
- `_bmad-output/implementation-artifacts/12-3-role-based-access-control-for-admin-and-standard-users.md`: established RBAC/admin implementation and review corrections.
- `src/ai_qa/api/admin.py`: existing admin project and membership endpoints from Story 12.3.
- `src/ai_qa/api/auth/rbac.py`: central active-user/admin dependencies to reuse.
- `src/ai_qa/db/models.py`: authoritative User, Project, and ProjectMembership models.

## Dev Agent Record

### Agent Model Used

GPT-OSS 120B (Medium)

### Debug Log References

- Initial validation with system Python failed because SQLAlchemy was not installed in that interpreter; switched to the repository virtual environment.
- Targeted validation: `.\.venv\Scripts\python.exe -m pytest tests/test_project_api.py --no-cov` initially exposed that `/openapi.json` was blocked by auth middleware; added OpenAPI/docs paths as public documentation routes.
- Targeted validation: `.\.venv\Scripts\python.exe -m pytest tests/test_project_api.py --no-cov` passed (`6 passed`).
- API regression validation: `.\.venv\Scripts\python.exe -m pytest tests/test_admin_rbac_api.py tests/test_project_api.py --no-cov` passed (`15 passed`).
- Full regression validation: `.\.venv\Scripts\python.exe -m pytest --no-cov` passed (`462 passed, 2 skipped`).

### Completion Notes List

- Added `/api/projects` list and `/api/projects/{project_id}` detail routes with role-aware Pydantic response schemas.
- Implemented admin all-project visibility with membership summaries and standard-user project filtering by `ProjectMembership` rows.
- Added reusable `require_project_member_or_admin` helper for future project-scoped endpoints, returning safe non-disclosing 404s for non-members.
- Wired the project router into the FastAPI app under `/api/projects` while preserving `/api/*` auth protection.
- Preserved deterministic admin membership assignment and role constraints from Story 12.3.
- Added API tests covering admin/member/outsider access, unauthenticated and stale-user rejection, OpenAPI route/schema publication, and admin duplicate membership regression coverage.
- Opened `/openapi.json`, `/docs`, and `/redoc` as public documentation endpoints so schemas remain discoverable without weakening `/api/*` route protection.

### File List

- `src/ai_qa/api/app.py`
- `src/ai_qa/api/auth/middleware.py`
- `src/ai_qa/api/projects.py`
- `tests/test_project_api.py`
- `_bmad-output/implementation-artifacts/12-4-project-and-membership-management-api.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Story Completion Status

```yaml
status: done
completion_notes: |
  Story 12.4 implementation complete. Project APIs now allow admins to list/detail all projects with membership summaries, standard users to list/detail only assigned projects with their membership role, and future project-scoped routes to reuse centralized membership-or-admin authorization. OpenAPI documentation exposes the new project schemas and routes, admin membership behavior remains deterministic, and automated API plus full regression tests pass.
```
