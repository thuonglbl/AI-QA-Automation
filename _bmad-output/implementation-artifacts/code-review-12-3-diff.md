diff --git a/_bmad-output/implementation-artifacts/12-3-role-based-access-control-for-admin-and-standard-users.md b/_bmad-output/implementation-artifacts/12-3-role-based-access-control-for-admin-and-standard-users.md
new file mode 100644
index 0000000..ffbd8c6
--- /dev/null
+++ b/_bmad-output/implementation-artifacts/12-3-role-based-access-control-for-admin-and-standard-users.md
@@ -0,0 +1,344 @@
+# 12-3: Role-Based Access Control for Admin and Standard Users
+
+## Header
+
+```yaml
+story_id: 12.3
+story_key: 12-3-role-based-access-control-for-admin-and-standard-users
+epic: Epic 12 - Decoupled Backend, Database, Auth, and Project Foundation
+status: ready-for-dev
+created_by: BMad Story Agent
+created_at: 2026-05-05
+story_title: Role-Based Access Control for Admin and Standard Users
+epic_title: Decoupled Backend, Database, Auth, and Project Foundation
+epic_description: Pivot from single-user file-based workspace storage to a decoupled multi-user system with React frontend, FastAPI backend, PostgreSQL source of truth, and project-scoped artifacts.
+```
+
+## Requirements
+
+### User Story
+
+**As an** admin,  
+**I want** role-based permissions enforced by the backend,  
+**So that** only authorized users can manage users and projects.
+
+### Acceptance Criteria (BDD)
+
+**Scenario 1: Admin users can access admin APIs**
+```gherkin
+Given an authenticated user has the admin role
+When they access admin-only APIs
+Then they can view the user list
+And they can create projects
+And they can assign users to projects
+And responses use secret-free Pydantic schemas
+```
+
+**Scenario 2: Standard users cannot access admin-only endpoints**
+```gherkin
+Given an authenticated user has the standard role
+When they access any admin-only endpoint
+Then the request is rejected with a consistent authorization error
+And no project, membership, or user-management mutation occurs
+And the response does not disclose sensitive implementation details
+```
+
+**Scenario 3: Protected endpoints reject unauthenticated requests**
+```gherkin
+Given a request has no valid session cookie or bearer token
+When it targets any protected API endpoint
+Then the backend rejects it consistently
+And admin endpoints are never reachable anonymously
+```
+
+**Scenario 4: Authorization failures are consistent and safe**
+```gherkin
+Given a caller lacks a required role or uses a stale/invalid identity
+When authorization fails
+Then the response uses a consistent status code and detail message
+And the response does not reveal whether hidden users, projects, or memberships exist
+And the failure is safe for both cookie and Authorization bearer-token callers
+```
+
+**Scenario 5: RBAC checks are covered by API tests**
+```gherkin
+Given RBAC dependencies and admin endpoints are implemented
+When the automated API test suite runs
+Then admin success paths are covered
+And standard-user forbidden paths are covered
+And unauthenticated protected-path behavior is covered
+And current local-auth tests from Story 12.2 continue to pass
+```
+
+## Developer Context
+
+### Epic 12 Context and Boundaries
+
+Epic 12 is the course-correction epic that moves the application from a single-user, file-oriented workspace to a multi-user, project-scoped system. Story 12.1 established PostgreSQL/SQLAlchemy/Alembic persistence. Story 12.2 replaced JSON-file auth with PostgreSQL-backed local accounts, Argon2 password hashing via `pwdlib`, JWT cookie/bearer sessions, `/auth/me`, and admin bootstrap.
+
+This story must add backend authorization guardrails on top of that completed auth foundation. Treat Story 12.2 as the source of authenticated identity, but do not blindly trust role claims in old tokens when an endpoint needs authorization; re-check active user state from the database or through a shared current-user dependency.
+
+**Do implement:**
+- Central RBAC helpers/dependencies for authenticated user and admin-only access.
+- Consistent 401/403 behavior for unauthenticated vs unauthorized API calls.
+- Admin-only endpoints sufficient to satisfy the story: list users, create projects, assign users to projects.
+- API tests for admin success, standard-user denial, and unauthenticated denial.
+- Thin route handlers that use Pydantic request/response schemas and SQLAlchemy sessions.
+
+**Do not implement:**
+- Frontend admin/user/project management screens; Story 12.6 owns frontend UI.
+- Full project list/member-scoped browsing behavior; Story 12.4 owns user-facing project and membership management depth.
+- Project-scoped artifact persistence; Story 12.5 owns artifact service.
+- Agent pipeline refactor from workspace paths to project context; Story 12.7 owns that.
+- Azure Entra ID/MSAL/SSO; Epic 11 remains deferred.
+
+### Existing Codebase Intelligence
+
+Relevant current files and patterns:
+
+```text
+src/ai_qa/
+Γö£ΓöÇΓöÇ api/
+Γöé   Γö£ΓöÇΓöÇ app.py                    # create_app() includes AuthMiddleware, auth router, /api router
+Γöé   Γö£ΓöÇΓöÇ routes.py                 # current protected pipeline endpoints under /api
+Γöé   ΓööΓöÇΓöÇ auth/
+Γöé       Γö£ΓöÇΓöÇ local.py              # /auth/register, /auth/login, /auth/me, /auth/status
+Γöé       Γö£ΓöÇΓöÇ middleware.py         # session cookie/bearer auth; protects /api/* and /ws
+Γöé       ΓööΓöÇΓöÇ session.py            # JWT session encode/decode
+Γö£ΓöÇΓöÇ auth/
+Γöé   Γö£ΓöÇΓöÇ password.py               # Argon2 password helpers
+Γöé   Γö£ΓöÇΓöÇ service.py                # register/authenticate/bootstrap helpers and role constants
+Γöé   ΓööΓöÇΓöÇ bootstrap_admin.py        # CLI/module admin bootstrap path
+ΓööΓöÇΓöÇ db/
+    Γö£ΓöÇΓöÇ models.py                 # User, Project, ProjectMembership, PipelineRun, Artifact, ArtifactVersion, AuditEvent
+    ΓööΓöÇΓöÇ session.py                # get_db_session(settings) and engine/session helpers
+
+tests/
+Γö£ΓöÇΓöÇ test_auth_api.py              # local auth route tests from Story 12.2
+Γö£ΓöÇΓöÇ test_auth_service.py          # auth service tests
+Γö£ΓöÇΓöÇ test_auth_password.py         # password helper tests
+ΓööΓöÇΓöÇ db/                           # DB metadata/settings/session tests
+```
+
+Important model fields already exist:
+- `User.role`: string role, currently `admin` or `standard` by convention.
+- `User.is_active`: inactive users must not be treated as authenticated/authorized.
+- `Project.created_by_user_id`: can capture admin creator for admin project creation.
+- `ProjectMembership.role`: project-level role, default `member`; use `member` unless the endpoint accepts a constrained role.
+- `ProjectMembership` has a unique `(project_id, user_id)` constraint.
+
+Existing middleware already protects `/api/*` and `/ws` from unauthenticated callers. Keep that behavior and layer route-level RBAC on top. Do not make admin endpoints public-path exceptions.
+
+### Architecture and Security Guardrails
+
+- Backend remains FastAPI in `src/ai_qa/api` with application factory in `api/app.py`.
+- Use SQLAlchemy 2.x ORM models from `src/ai_qa/db/models.py`; do not introduce a second project/user store.
+- Use Pydantic request/response schemas; never return `password_hash`, JWT tokens, session cookies, or raw ORM objects from admin APIs.
+- Prefer central dependencies, e.g. `get_current_active_user(...)` and `require_admin(...)`, so later stories can reuse the same guardrails.
+- Authorization checks should use database state, not only JWT role claims, to handle role changes, inactive users, deleted users, and stale tokens.
+- Standardize errors:
+  - unauthenticated / invalid / stale identity: `401` with a generic `Not authenticated`-style detail;
+  - authenticated but insufficient role: `403` with a generic `Forbidden`-style detail.
+- Avoid leaking whether a target user/project exists to unauthorized users. Since admin routes require admin first, detailed 404s are acceptable only after admin authorization succeeds.
+- Enforce public registration remains standard-user only; do not add public role assignment.
+- If adding project creation now, keep it minimal and admin-only; Story 12.4 may extend schemas and member-facing project APIs later.
+
+### Recommended Implementation Shape
+
+Create or extend a small RBAC module rather than scattering role checks in every route:
+
+```text
+src/ai_qa/api/auth/rbac.py
+```
+
+Suggested contents:
+
+```python
+from collections.abc import Generator
+from uuid import UUID
+
+from fastapi import Depends, HTTPException, Request
+from sqlalchemy.orm import Session
+
+from ai_qa.api.auth.local import get_db_session_dependency
+from ai_qa.db.models import User
+
+ADMIN_ROLE = "admin"
+STANDARD_ROLE = "standard"
+
+async def get_current_active_user(
+    request: Request,
+    db: Session = Depends(get_db_session_dependency),
+) -> User:
+    ...
+
+async def require_admin(
+    current_user: User = Depends(get_current_active_user),
+) -> User:
+    ...
+```
+
+Implementation expectations:
+- Pull `request.state.user` from middleware.
+- Parse `user_id` as UUID where possible; fall back to email only if absolutely needed for compatibility.
+- Load `User` from DB and verify `is_active`.
+- Require `role == "admin"` for admin dependencies.
+- Return ORM `User` internally, but route responses must serialize through Pydantic schemas.
+
+Add a dedicated admin router, for example:
+
+```text
+src/ai_qa/api/admin.py
+```
+
+Recommended endpoints under `/api/admin`:
+
+- `GET /api/admin/users`
+  - Admin-only.
+  - Returns list of users with `id`, `email`, `display_name`, `role`, `is_active`, `created_at`, `updated_at` if available.
+  - Excludes password hash.
+
+- `POST /api/admin/projects`
+  - Admin-only.
+  - Creates a project with `name` and optional `description`.
+  - Sets `created_by_user_id` to current admin id.
+  - Returns secret-free project schema.
+  - Validate name is non-empty and bounded in length.
+
+- `POST /api/admin/projects/{project_id}/memberships`
+  - Admin-only.
+  - Assigns a user to a project.
+  - Request includes `user_id` and optional membership `role` defaulting to `member`.
+  - Idempotency: if membership already exists, either return existing membership or update role predictably. Document/test the chosen behavior.
+  - Return secret-free membership schema including project/user ids and role.
+
+Wire the router in `src/ai_qa/api/app.py` after the main API router or near it:
+
+```python
+from ai_qa.api.admin import router as admin_router
+...
+app.include_router(admin_router, prefix="/api")
+```
+
+### Previous Story Intelligence (12.2)
+
+Story 12.2 completed local auth but its story file contains review findings that matter for RBAC work:
+
+- Revalidate current user against the database instead of trusting stale JWT claims.
+- Apply consistent auth errors and avoid sensitive leakage.
+- Protect WebSocket subpaths consistently if touching middleware.
+- Replace brittle auth API test dependency override patterns with stable override hooks if adding tests.
+- Bearer-token logout semantics are imperfect; avoid widening token behavior unless needed.
+
+Use these learnings proactively. RBAC must not depend only on `request.state.user.role`, because role claims can become stale after an admin changes a user or deactivates an account.
+
+### Testing Requirements
+
+Minimum tests for this story:
+
+- `require_admin` allows active admin users and rejects standard users.
+- `require_admin` rejects inactive/deleted/stale-token users.
+- `GET /api/admin/users`:
+  - admin succeeds and response excludes `password_hash`;
+  - standard user receives 403;
+  - unauthenticated request receives 401 or the project-standard unauthenticated response.
+- `POST /api/admin/projects`:
+  - admin creates a project with `created_by_user_id`;
+  - standard user cannot create a project.
+- `POST /api/admin/projects/{project_id}/memberships`:
+  - admin assigns a user to a project;
+  - duplicate assignment behavior is deterministic and covered;
+  - missing target user/project after admin authorization returns safe 404.
+- Existing Story 12.2 tests continue to pass.
+
+Prefer tests that can run without a live PostgreSQL server by using the existing app dependency override/test-session pattern or SQLite-compatible SQLAlchemy sessions. Keep optional live PostgreSQL tests gated by `TEST_DATABASE_URL`.
+
+Validation commands:
+
+```powershell
+uv run ruff check .
+uv run pytest tests -q
+```
+
+If the full suite is slow during development, targeted debugging is acceptable, but the final Dev Agent Record should capture the broadest practical validation.
+
+## Tasks / Subtasks
+
+- [x] Add central RBAC dependencies. (AC: 2, 3, 4)
+  - [x] Implement current active user lookup that revalidates `request.state.user` against PostgreSQL.
+  - [x] Implement `require_admin` with consistent 403 handling for standard users.
+  - [x] Reuse role constants from `ai_qa.auth.service` or define one canonical role source to avoid spelling drift.
+- [x] Add admin API schemas and router. (AC: 1, 2, 4)
+  - [x] Add secret-free user, project, and membership response schemas.
+  - [x] Implement admin-only user listing.
+  - [x] Implement admin-only project creation.
+  - [x] Implement admin-only project membership assignment with deterministic duplicate handling.
+- [x] Wire admin router into the FastAPI app. (AC: 1, 2, 3)
+  - [x] Include admin routes under `/api/admin`.
+  - [x] Ensure middleware still protects `/api/admin/*` as protected API routes.
+- [x] Preserve local-auth boundaries from Story 12.2. (AC: 2, 3, 4)
+  - [x] Do not allow public registration to assign admin role.
+  - [x] Do not return password hashes or token internals in admin responses.
+  - [x] Ensure inactive users cannot pass RBAC even with old tokens.
+- [x] Add automated RBAC/API tests. (AC: 5)
+  - [x] Cover admin success paths.
+  - [x] Cover standard-user forbidden paths.
+  - [x] Cover unauthenticated protected endpoint behavior.
+  - [x] Run Ruff and pytest; record results in Dev Agent Record.
+
+## Out of Scope
+
+- Frontend login, project picker, or admin management screens.
+- Non-admin project list and member-scoped project visibility APIs.
+- Full project CRUD, project deletion, invitation flows, or membership removal.
+- Artifact storage/service implementation.
+- Pipeline run/project-context refactor.
+- Azure Entra ID SSO or enterprise OAuth flows.
+
+## Project Context Reference
+
+- `_bmad-output/planning-artifacts/epics.md`, Epic 12 and Story 12.3: RBAC must allow admins to list users/create projects/assign users, block standard users, reject unauthenticated protected requests, and cover checks with API tests.
+- `_bmad-output/implementation-artifacts/12-2-local-authentication-and-admin-bootstrap.md`: completed DB-backed local auth, session payloads, `/auth/me`, admin bootstrap, and review learnings about stale JWT claims.
+- `src/ai_qa/api/auth/local.py`: current auth router and `get_db_session_dependency` pattern.
+- `src/ai_qa/api/auth/middleware.py`: cookie/bearer middleware that populates `request.state.user` and protects `/api/*`.
+- `src/ai_qa/db/models.py`: existing User, Project, and ProjectMembership ORM models required for RBAC/admin endpoints.
+- `src/ai_qa/api/app.py`: FastAPI app factory where new admin router must be included.
+
+## Dev Agent Record
+
+### Agent Model Used
+
+GPT-OSS 120B (Medium)
+
+### Debug Log References
+
+- `uv run pytest tests/test_admin_rbac_api.py -q` initially exposed one test setup failure, then passed with `--no-cov` after fixing request-state setup.
+- `uv run ruff check .` initially reported B008 dependency-default issues in new RBAC/admin modules; resolved with module-level dependency aliases.
+- Final validation: `uv run ruff check .` passed.
+- Final validation: `uv run pytest tests -q` passed (`454 passed, 2 skipped`, coverage 78.25%).
+
+### Completion Notes List
+
+- Added central RBAC dependencies that revalidate `request.state.user` against the database and reject inactive/deleted/stale identities with `401 Not authenticated`.
+- Added reusable admin authorization dependency returning consistent `403 Forbidden` for active standard users.
+- Added `/api/admin/users`, `/api/admin/projects`, and `/api/admin/projects/{project_id}/memberships` with secret-free Pydantic schemas.
+- Implemented deterministic duplicate membership handling by updating the existing membership role and returning the same membership record.
+- Wired admin routes under `/api/admin`, preserving existing middleware protection for `/api/*` paths.
+- Added RBAC/API tests for admin success paths, standard-user denials, unauthenticated access, stale inactive-user tokens, secret-free responses, project creation, and membership assignment.
+
+### File List
+
+- `src/ai_qa/api/admin.py`
+- `src/ai_qa/api/app.py`
+- `src/ai_qa/api/auth/rbac.py`
+- `tests/test_admin_rbac_api.py`
+- `_bmad-output/implementation-artifacts/12-3-role-based-access-control-for-admin-and-standard-users.md`
+- `_bmad-output/implementation-artifacts/sprint-status.yaml`
+
+## Story Completion Status
+
+```yaml
+status: review
+completion_notes: |
+  Story 12.3 implementation complete. Backend RBAC now revalidates current users from the database, enforces admin-only access for admin APIs, exposes secret-free user/project/membership schemas, supports deterministic membership reassignment, and includes automated API coverage for admin, standard-user, unauthenticated, and stale-token paths.
+```
diff --git a/_bmad-output/implementation-artifacts/sprint-status.yaml b/_bmad-output/implementation-artifacts/sprint-status.yaml
index 4029363..df25f87 100644
--- a/_bmad-output/implementation-artifacts/sprint-status.yaml
+++ b/_bmad-output/implementation-artifacts/sprint-status.yaml
@@ -1,5 +1,5 @@
 # generated: 2026-04-07T16:11:19+07:00
-# last_updated: 2026-05-04T15:58:43+0700
+# last_updated: 2026-05-05T09:34:00+0700
 # project: ai-qa-automation
 # project_key: NOKEY
 # tracking_system: file-system
@@ -37,7 +37,7 @@
 # - Course correction 2026-05-04: prioritize decoupled DB/Auth/Project foundation before Epic 6+.
 
 generated: 2026-04-07T16:11:19+07:00
-last_updated: 2026-05-04T15:58:43+0700
+last_updated: 2026-05-05T09:34:00+0700
 project: ai-qa-automation
 project_key: NOKEY
 tracking_system: file-system
@@ -84,7 +84,7 @@ development_status:
   epic-12: in-progress
   12-1-postgresql-persistence-foundation-with-sqlalchemy-and-alembic: done
   12-2-local-authentication-and-admin-bootstrap: done
-  12-3-role-based-access-control-for-admin-and-standard-users: backlog
+  12-3-role-based-access-control-for-admin-and-standard-users: review
   12-4-project-and-membership-management-api: backlog
   12-5-project-scoped-artifact-service: backlog
   12-6-frontend-login-project-selection-and-api-client-foundation: backlog
diff --git a/src/ai_qa/api/admin.py b/src/ai_qa/api/admin.py
new file mode 100644
index 0000000..aaae4f9
--- /dev/null
+++ b/src/ai_qa/api/admin.py
@@ -0,0 +1,134 @@
+"""Admin-only project and user management API routes."""
+
+from datetime import datetime
+from uuid import UUID
+
+from fastapi import APIRouter, Depends, HTTPException
+from pydantic import BaseModel, ConfigDict, Field
+from sqlalchemy import select
+from sqlalchemy.orm import Session
+
+from ai_qa.api.auth.local import get_db_session_dependency
+from ai_qa.api.auth.rbac import require_admin
+from ai_qa.db.models import Project, ProjectMembership, User
+
+DbSessionDependency = Depends(get_db_session_dependency)
+AdminDependency = Depends(require_admin)
+
+router = APIRouter(prefix="/admin", tags=["admin"])
+
+
+class AdminUserResponse(BaseModel):
+    """Secret-free user representation for admin APIs."""
+
+    model_config = ConfigDict(from_attributes=True)
+
+    id: UUID
+    email: str
+    display_name: str
+    role: str
+    is_active: bool
+    created_at: datetime
+    updated_at: datetime
+
+
+class ProjectCreateRequest(BaseModel):
+    """Admin project creation request."""
+
+    name: str = Field(min_length=1, max_length=255)
+    description: str | None = Field(default=None, max_length=4000)
+
+
+class AdminProjectResponse(BaseModel):
+    """Secret-free project representation for admin APIs."""
+
+    model_config = ConfigDict(from_attributes=True)
+
+    id: UUID
+    name: str
+    description: str | None
+    created_by_user_id: UUID | None
+    created_at: datetime
+    updated_at: datetime
+
+
+class MembershipCreateRequest(BaseModel):
+    """Admin project membership assignment request."""
+
+    user_id: UUID
+    role: str = Field(default="member", min_length=1, max_length=50)
+
+
+class AdminMembershipResponse(BaseModel):
+    """Secret-free membership representation for admin APIs."""
+
+    model_config = ConfigDict(from_attributes=True)
+
+    id: UUID
+    project_id: UUID
+    user_id: UUID
+    role: str
+    created_at: datetime
+    updated_at: datetime
+
+
+@router.get("/users", response_model=list[AdminUserResponse])
+async def list_users(
+    _admin: User = AdminDependency,
+    db: Session = DbSessionDependency,
+) -> list[User]:
+    """List users for active admins without exposing password hashes."""
+    return list(db.execute(select(User).order_by(User.email)).scalars())
+
+
+@router.post("/projects", response_model=AdminProjectResponse)
+async def create_project(
+    request: ProjectCreateRequest,
+    admin: User = AdminDependency,
+    db: Session = DbSessionDependency,
+) -> Project:
+    """Create a project owned by the current admin user."""
+    project = Project(
+        name=request.name.strip(),
+        description=request.description.strip() if request.description else None,
+        created_by_user_id=admin.id,
+    )
+    db.add(project)
+    db.commit()
+    db.refresh(project)
+    return project
+
+
+@router.post(
+    "/projects/{project_id}/memberships",
+    response_model=AdminMembershipResponse,
+)
+async def assign_project_membership(
+    project_id: UUID,
+    request: MembershipCreateRequest,
+    _admin: User = AdminDependency,
+    db: Session = DbSessionDependency,
+) -> ProjectMembership:
+    """Create or update a project membership deterministically for admins."""
+    project = db.get(Project, project_id)
+    target_user = db.get(User, request.user_id)
+    if project is None or target_user is None:
+        raise HTTPException(status_code=404, detail="Resource not found")
+
+    role = request.role.strip()
+    membership = db.execute(
+        select(ProjectMembership).where(
+            ProjectMembership.project_id == project_id,
+            ProjectMembership.user_id == request.user_id,
+        )
+    ).scalar_one_or_none()
+
+    if membership is None:
+        membership = ProjectMembership(project_id=project_id, user_id=request.user_id, role=role)
+        db.add(membership)
+    else:
+        membership.role = role
+
+    db.commit()
+    db.refresh(membership)
+    return membership
diff --git a/src/ai_qa/api/app.py b/src/ai_qa/api/app.py
index 1794e0c..ae937af 100644
--- a/src/ai_qa/api/app.py
+++ b/src/ai_qa/api/app.py
@@ -12,6 +12,7 @@ from fastapi.staticfiles import StaticFiles
 from starlette.middleware.sessions import SessionMiddleware
 
 from ai_qa.agents import AliceAgent
+from ai_qa.api.admin import router as admin_router
 from ai_qa.api.auth import AuthMiddleware, get_auth_router
 from ai_qa.api.routes import register_agent
 from ai_qa.api.routes import router as api_router
@@ -72,6 +73,7 @@ def create_app(settings: AppSettings | None = None) -> FastAPI:
 
     # REST API routes (protected by auth middleware)
     app.include_router(api_router, prefix="/api")
+    app.include_router(admin_router, prefix="/api")
 
     # WebSocket endpoint (protected by auth middleware)
     app.add_api_websocket_route("/ws", websocket_endpoint)
diff --git a/src/ai_qa/api/auth/rbac.py b/src/ai_qa/api/auth/rbac.py
new file mode 100644
index 0000000..10d25de
--- /dev/null
+++ b/src/ai_qa/api/auth/rbac.py
@@ -0,0 +1,62 @@
+"""Reusable RBAC dependencies for protected FastAPI routes."""
+
+from uuid import UUID
+
+from fastapi import Depends, HTTPException, Request
+from sqlalchemy.orm import Session
+
+from ai_qa.api.auth.local import get_db_session_dependency
+from ai_qa.auth.service import ADMIN_ROLE, STANDARD_ROLE
+from ai_qa.db.models import User
+
+DbSessionDependency = Depends(get_db_session_dependency)
+
+NOT_AUTHENTICATED_DETAIL = "Not authenticated"
+FORBIDDEN_DETAIL = "Forbidden"
+
+
+def _not_authenticated() -> HTTPException:
+    return HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)
+
+
+async def get_current_active_user(
+    request: Request,
+    db: Session = DbSessionDependency,
+) -> User:
+    """Return the active DB user for the current session, rejecting stale tokens."""
+    session_user = getattr(request.state, "user", None)
+    if session_user is None or session_user.is_expired:
+        raise _not_authenticated()
+
+    try:
+        user_id = UUID(str(session_user.user_id))
+    except (TypeError, ValueError) as exc:
+        raise _not_authenticated() from exc
+
+    user = db.get(User, user_id)
+    if user is None or not user.is_active:
+        raise _not_authenticated()
+
+    return user
+
+
+CurrentUserDependency = Depends(get_current_active_user)
+
+
+async def require_admin(
+    current_user: User = CurrentUserDependency,
+) -> User:
+    """Require an active admin user from the current database state."""
+    if current_user.role != ADMIN_ROLE:
+        raise HTTPException(status_code=403, detail=FORBIDDEN_DETAIL)
+    return current_user
+
+
+__all__ = [
+    "ADMIN_ROLE",
+    "STANDARD_ROLE",
+    "FORBIDDEN_DETAIL",
+    "NOT_AUTHENTICATED_DETAIL",
+    "get_current_active_user",
+    "require_admin",
+]
diff --git a/tests/test_admin_rbac_api.py b/tests/test_admin_rbac_api.py
new file mode 100644
index 0000000..2e6276a
--- /dev/null
+++ b/tests/test_admin_rbac_api.py
@@ -0,0 +1,223 @@
+"""API tests for admin RBAC routes."""
+
+from collections.abc import Generator
+
+import pytest
+from fastapi import Request
+from fastapi.testclient import TestClient
+from sqlalchemy import create_engine
+from sqlalchemy.orm import Session, sessionmaker
+from sqlalchemy.pool import StaticPool
+
+from ai_qa.api.app import create_app
+from ai_qa.api.auth.local import get_db_session_dependency
+from ai_qa.api.auth.rbac import get_current_active_user, require_admin
+from ai_qa.api.auth.session import SessionManager
+from ai_qa.auth.password import hash_password
+from ai_qa.auth.service import ADMIN_ROLE, STANDARD_ROLE
+from ai_qa.db.base import Base
+from ai_qa.db.models import Project, ProjectMembership, User
+
+
+@pytest.fixture
+def admin_client() -> Generator[TestClient]:
+    engine = create_engine(
+        "sqlite+pysqlite:///:memory:",
+        connect_args={"check_same_thread": False},
+        poolclass=StaticPool,
+    )
+    Base.metadata.create_all(engine, tables=[User.__table__, Project.__table__, ProjectMembership.__table__])
+    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
+
+    def override_get_db_session() -> Generator[Session]:
+        session = session_factory()
+        try:
+            yield session
+        finally:
+            session.close()
+
+    app = create_app()
+    app.dependency_overrides[get_db_session_dependency] = override_get_db_session
+    with TestClient(app) as client:
+        yield client
+    app.dependency_overrides.clear()
+
+
+def _create_user(client: TestClient, email: str, role: str, *, active: bool = True) -> User:
+    db_override = client.app.dependency_overrides[get_db_session_dependency]
+    session = next(db_override())
+    try:
+        user = User(
+            email=email,
+            display_name=email.split("@")[0],
+            password_hash=hash_password("super-secret"),
+            role=role,
+            is_active=active,
+        )
+        session.add(user)
+        session.commit()
+        session.refresh(user)
+        session.expunge(user)
+        return user
+    finally:
+        session.close()
+
+
+def _token(client: TestClient, user: User) -> str:
+    session_manager = SessionManager(client.app.state.settings)
+    session = session_manager.create_session(
+        {
+            "user_id": str(user.id),
+            "email": user.email,
+            "name": user.display_name,
+            "role": user.role,
+            "is_active": user.is_active,
+        }
+    )
+    return session_manager.encode_session(session)
+
+
+def _auth_headers(client: TestClient, user: User) -> dict[str, str]:
+    return {"Authorization": f"Bearer {_token(client, user)}"}
+
+
+@pytest.mark.asyncio
+async def test_require_admin_allows_active_admin_and_rejects_standard(admin_client: TestClient) -> None:
+    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
+    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)
+    db_override = admin_client.app.dependency_overrides[get_db_session_dependency]
+
+    async def _current_user_for(user: User) -> User:
+        request = Request(
+            {
+                "type": "http",
+                "method": "GET",
+                "path": "/api/admin/users",
+                "headers": [],
+                "app": admin_client.app,
+            }
+        )
+        request.state.user = SessionManager(admin_client.app.state.settings).decode_session(_token(admin_client, user))
+        session = next(db_override())
+        try:
+            return await get_current_active_user(request, session)
+        finally:
+            session.close()
+
+    current_admin = await _current_user_for(admin)
+    assert (await require_admin(current_admin)).email == "admin@example.com"
+
+    current_standard = await _current_user_for(standard)
+    with pytest.raises(Exception) as exc_info:
+        await require_admin(current_standard)
+    assert exc_info.value.status_code == 403
+    assert exc_info.value.detail == "Forbidden"
+
+
+def test_admin_can_list_users_without_password_hash(admin_client: TestClient) -> None:
+    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
+    _create_user(admin_client, "standard@example.com", STANDARD_ROLE)
+
+    response = admin_client.get("/api/admin/users", headers=_auth_headers(admin_client, admin))
+
+    assert response.status_code == 200
+    users = response.json()
+    assert [user["email"] for user in users] == ["admin@example.com", "standard@example.com"]
+    assert all("password_hash" not in user for user in users)
+
+
+def test_standard_and_unauthenticated_users_cannot_list_admin_users(admin_client: TestClient) -> None:
+    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)
+
+    forbidden = admin_client.get("/api/admin/users", headers=_auth_headers(admin_client, standard))
+    unauthenticated = admin_client.get("/api/admin/users")
+
+    assert forbidden.status_code == 403
+    assert forbidden.json()["detail"] == "Forbidden"
+    assert unauthenticated.status_code == 401
+    assert unauthenticated.json()["detail"] == "Not authenticated"
+
+
+def test_admin_can_create_project_and_standard_user_cannot(admin_client: TestClient) -> None:
+    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
+    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)
+
+    created = admin_client.post(
+        "/api/admin/projects",
+        headers=_auth_headers(admin_client, admin),
+        json={"name": "Quality Workspace", "description": "Core QA project"},
+    )
+    denied = admin_client.post(
+        "/api/admin/projects",
+        headers=_auth_headers(admin_client, standard),
+        json={"name": "Denied"},
+    )
+
+    assert created.status_code == 200
+    project = created.json()
+    assert project["name"] == "Quality Workspace"
+    assert project["created_by_user_id"] == str(admin.id)
+    assert "password_hash" not in project
+    assert denied.status_code == 403
+
+
+def test_admin_assigns_membership_and_duplicate_updates_role(admin_client: TestClient) -> None:
+    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
+    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)
+    project_response = admin_client.post(
+        "/api/admin/projects",
+        headers=_auth_headers(admin_client, admin),
+        json={"name": "Quality Workspace"},
+    )
+    project_id = project_response.json()["id"]
+
+    first = admin_client.post(
+        f"/api/admin/projects/{project_id}/memberships",
+        headers=_auth_headers(admin_client, admin),
+        json={"user_id": str(standard.id)},
+    )
+    duplicate = admin_client.post(
+        f"/api/admin/projects/{project_id}/memberships",
+        headers=_auth_headers(admin_client, admin),
+        json={"user_id": str(standard.id), "role": "owner"},
+    )
+
+    assert first.status_code == 200
+    assert first.json()["role"] == "member"
+    assert duplicate.status_code == 200
+    assert duplicate.json()["id"] == first.json()["id"]
+    assert duplicate.json()["role"] == "owner"
+
+
+def test_admin_membership_assignment_returns_safe_404_for_missing_resources(admin_client: TestClient) -> None:
+    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
+    standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)
+
+    response = admin_client.post(
+        "/api/admin/projects/00000000-0000-0000-0000-000000000001/memberships",
+        headers=_auth_headers(admin_client, admin),
+        json={"user_id": str(standard.id)},
+    )
+
+    assert response.status_code == 404
+    assert response.json()["detail"] == "Resource not found"
+
+
+def test_inactive_user_with_old_token_cannot_pass_rbac(admin_client: TestClient) -> None:
+    admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
+    token = _token(admin_client, admin)
+
+    db_override = admin_client.app.dependency_overrides[get_db_session_dependency]
+    session = next(db_override())
+    try:
+        user = session.get(User, admin.id)
+        assert user is not None
+        user.is_active = False
+        session.commit()
+    finally:
+        session.close()
+
+    response = admin_client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
+
+    assert response.status_code == 401
+    assert response.json()["detail"] == "Not authenticated"
