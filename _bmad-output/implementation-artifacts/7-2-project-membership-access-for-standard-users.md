---
baseline_commit: 4869945c792df86bd3fa58f85b4f8dfa3855475d
---
# Story 7.2: Project Membership Access for Standard Users

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a standard user,
I want to see only projects assigned to me,
So that I can choose from authorized project workspaces only.

## Acceptance Criteria

1. **Given** an authenticated standard user belongs to one or more projects
   **When** the frontend requests the user's accessible project list
   **Then** the backend returns only projects where the user has active membership
   **And** admin-only project records are not exposed beyond the user's authorization
2. **Given** an authenticated standard user belongs to zero projects
   **When** the frontend requests accessible projects
   **Then** the backend returns an empty project list
   **And** the frontend can display the no-access state required by FR53
3. **Given** an unauthenticated request is made to the project list endpoint
   **When** the backend evaluates the request
   **Then** the request is rejected as unauthorized

## Tasks / Subtasks

- [x] Create/Update Project Service (`src/ai_qa/projects/service.py`) (AC: 1, 2)
  - [x] Implement `get_user_projects(user_id: UUID) -> list[Project]` to query only assigned projects.
- [x] Create/Update API Routes (`src/ai_qa/api/routes/projects.py`) (AC: 1, 2, 3)
  - [x] Implement `GET /api/projects` authenticated endpoint using `Depends(get_current_user)`.
  - [x] Ensure endpoint returns a list of projects the user is authorized to see.
- [x] Frontend API Client updates (`frontend/src/types/` and `frontend/src/features/workspace/`) (AC: 1, 2)
  - [x] Implement `getUserProjects()` API call.
- [x] Frontend UI Component Updates (`frontend/src/features/workspace/`) (AC: 2)
  - [x] Create or update the workspace shell to handle the zero-projects (no-access) state.

### Review Findings

- [x] Review - Patch: N+1 Query / Missing Eager Loading [src/ai_qa/projects/service.py]
- [x] Review - Patch: Missing UI Implementation for Zero-Projects State [frontend/src/features/workspace/]
- [x] Review - Patch: Missing API Endpoint Tests [tests/test_api/test_routes.py]
- [x] Review - Patch: Accidental Binary Commit [diff.txt]
- [x] Review - Patch: Improper Import Placement [src/ai_qa/api/projects.py]
- [x] Review - Patch: Unused Query Construction [src/ai_qa/api/projects.py]
- [x] Review - Defer: Incorrect API Routes File Path [src/ai_qa/api/projects.py] — deferred, pre-existing
- [x] Review - Defer: Scale Boundary: Unbounded Result Sets [src/ai_qa/projects/service.py] — deferred, pre-existing

## Dev Notes

- **Architecture Patterns and Constraints**:
  - API responses must use Pydantic models with snake_case keys. No secrets should be returned.
  - Enforce RBAC/authorization checks on the project operation. Use `current_user` from the auth dependency.
  - The UI must use the Professional Calm color system, display empty states gracefully, and adhere to WCAG 2.1 AA standards (focus rings, labels, etc.).
- **Source Tree Components to Touch**:
  - `src/ai_qa/projects/` (Domain service)
  - `src/ai_qa/api/routes/projects.py` (FastAPI router)
  - `frontend/src/features/workspace/` (React components for standard workspace flow)
- **Testing Standards**:
  - Write tests for the `GET /api/projects` endpoint in `tests/test_api/test_routes.py` (or similar).
  - Verify that a standard user only receives their assigned projects.
  - Verify that a standard user with no projects receives an empty list `[]`.
  - Verify that unauthenticated requests receive `401 Unauthorized`.

### Project Structure Notes

- Ensure `ai_qa/projects/` is used for the business logic querying project memberships, keeping `api/routes/projects.py` thin and focused on HTTP transport.

### References

- [Epic 7: Secure Multi-User Workspace Foundation](file:///_bmad-output/planning-artifacts/epics.md#L238)
- [Story 7.2: Project Membership Access for Standard Users](file:///_bmad-output/planning-artifacts/epics.md#L267)
- [Architecture: Security Architecture](file:///_bmad-output/planning-artifacts/architecture.md#L362)

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro (High)

### Debug Log References

- Created by bmad-create-story workflow.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created
- ✅ Implemented `get_user_projects` in `src/ai_qa/projects/service.py` with SQLAlchemy tests.
- ✅ Refactored `GET /api/projects` in `src/ai_qa/api/projects.py` to use `get_user_projects`.
- ✅ Renamed `listProjects` to `getUserProjects` in `frontend/src/lib/projects.ts` to strictly match the requested API function name.
- ✅ Verified workspace shell handles zero-projects state gracefully in `App.tsx` (using the Professional Calm system).

### File List

- `_bmad-output/implementation-artifacts/7-2-project-membership-access-for-standard-users.md` (MODIFIED)
- `src/ai_qa/projects/__init__.py` (NEW)
- `src/ai_qa/projects/service.py` (NEW)
- `tests/test_projects_service.py` (NEW)
- `src/ai_qa/api/projects.py` (MODIFIED)
- `frontend/src/lib/projects.ts` (MODIFIED)
- `frontend/src/contexts/ProjectContext.tsx` (MODIFIED)
