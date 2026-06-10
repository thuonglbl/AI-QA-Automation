---
baseline_commit: "2b6b5be"
---
# Story 7.6: Membership Removal Access Enforcement

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an admin-managed system,
I want project membership removal to immediately affect thread visibility and access,
so that users cannot access project-bound work after losing membership.

## Acceptance Criteria

1. **Given** a user is removed from a project (their `ProjectMembership` row is deleted via `DELETE /api/admin/projects/{project_id}/memberships/{user_id}`)
   **When** the user opens Conversation History (`GET /api/threads`)
   **Then** threads bound to that project are hidden from the user
   **And** threads not bound to any project, and threads bound to projects the user still belongs to, remain visible.

2. **Given** a removed user attempts direct API access to a thread bound to the removed project
   **When** the backend authorizes the request (thread details, conversation load/save, messages list/create, agent-run create/update, project bind)
   **Then** access is denied
   **And** the response does not expose thread, project, artifact, or agent-run details (a generic `404 Resource not found` is returned, mirroring `require_project_member_or_admin`).

3. **Given** a removed user has an active frontend session (e.g. a stale `ai-qa-thread-id` in `localStorage` pointing at a now-inaccessible thread, or a thread row that disappears mid-session)
   **When** project-scoped access is next checked and the API returns a denial (`403`/`404`)
   **Then** the UI handles the denial safely (no crash, no infinite spinner, no leaked content)
   **And** it clears the stale thread state and prompts the user to choose an accessible workflow state (pick another project / start a new conversation) or contact an administrator.

## Tasks / Subtasks

- [x] Task 1: Backend — Membership-aware thread authorization helper (AC: 1, 2)
  - [x] Add a single reusable check (e.g. `ThreadService.assert_thread_access(thread, user_id)` or a small module-level helper in `api/threads.py`) that enforces BOTH: (a) ownership (`thread.user_id == user_id`) and (b) when `thread.project_id` is set, the user is a global admin (`User.role == ADMIN_ROLE`) OR has an active `ProjectMembership` for that project.
  - [x] Reuse the existing authorization semantics from `require_project_member_or_admin` in `src/ai_qa/api/projects.py` (admin bypass + membership lookup). Do not duplicate raw SQL if it can be shared cleanly.
  - [x] On membership denial for a project-bound thread, surface a result that the API layer maps to `404 Resource not found` (do not expose thread/project details). Keep the distinct "different owner" path returning the existing behavior, but prefer `404` for project-membership denial to avoid leaking existence.
- [x] Task 2: Backend — Filter Conversation History list (AC: 1)
  - [x] Update `ThreadService.get_user_threads` so that, for non-admin users, threads whose `project_id` references a project the user no longer belongs to are excluded. Threads with `project_id IS NULL` and threads in still-active memberships remain. Admins continue to see their own threads.
  - [x] Implement via a join/subquery against `ProjectMembership` (e.g. `project_id IS NULL OR project_id IN (user's membership project_ids)`), preserving the existing `is_archived == False` filter and `updated_at DESC` ordering.
- [x] Task 3: Backend — Enforce membership on direct thread access (AC: 2)
  - [x] Apply the Task 1 helper to every project-scoped thread endpoint in `src/ai_qa/api/threads.py`: `GET /{thread_id}`, `GET /{thread_id}/conversation`, `POST /{thread_id}/conversation`, `GET /{thread_id}/messages`, `POST /{thread_id}/messages`, `POST /{thread_id}/runs`, `PATCH /{thread_id}/runs/{run_id}`.
  - [x] Ensure `ThreadService.get_thread_details`, `add_message`, `get_thread_messages`, `create_agent_run`, and `update_agent_run` paths are covered (either the route enforces before delegating, or the service method enforces). Avoid double-fetching the thread where practical.
  - [x] Confirm the WebSocket/pipeline path already enforces membership for project-bound threads via `_build_pipeline_context` → `require_project_member_or_admin` (`src/ai_qa/api/routes.py`). Add a regression test rather than new enforcement code if it is already correct.
- [x] Task 4: Frontend — Safe denial handling on resume/select (AC: 3)
  - [x] Locate where a selected/persisted thread is hydrated (thread selection in `frontend/src/App.tsx` `onSelectThread`, persisted `ai-qa-thread-id`, and the conversation fetch in the pipeline/thread hooks). When a thread-scoped fetch throws an `ApiError` of kind `forbidden` or `not_found`, clear the stale thread id from state and `localStorage` and surface a non-blocking message.
  - [x] Reuse the existing error-surface pattern (e.g. the `threadCreationError` banner / `clearSelectedProject` flow in `App.tsx`) to prompt the user to pick another project, start a new conversation, or contact an administrator. Do not trigger the global `auth-error` logout flow for `403`/`404` (that is reserved for `401`).
  - [x] Verify `ProjectSidebar` no longer renders threads from removed projects: it derives threads from `GET /api/threads` (now filtered) and projects from `GET /api/projects` (already membership-filtered), so removed-project threads/folders should disappear on next load.
- [x] Task 5: Testing and Validation (AC: 1, 2, 3)
  - [x] Backend service tests (`tests/threads/test_service.py`): `get_user_threads` hides threads bound to a project the user was removed from, keeps unbound threads and still-member threads, and an admin still sees their own threads.
  - [x] Backend API tests (`tests/threads/test_threads_api.py`): a removed member receives the generic denial (`404`) on each project-scoped thread endpoint and the body exposes no thread/project/artifact/agent-run fields; the owner who is still a member succeeds; an admin succeeds.
  - [x] Backend regression test asserting WebSocket/pipeline context build is denied for a removed member of a project-bound thread.
  - [x] Frontend test covering denial handling: a `forbidden`/`not_found` response while resuming a thread clears the stale thread and shows the recovery prompt without crashing.

## Dev Notes

- **The actual gap.** Thread REST endpoints authorize on ownership only (`thread.user_id == current_user.user_id`). They never re-check current project membership, so a user removed from a project can still list and open threads bound to that project, and read/append messages, conversation data, and agent runs. See [get_thread_details_api](file:///src/ai_qa/api/threads.py#L78-L94) and the repeated ownership-only checks across [threads.py](file:///src/ai_qa/api/threads.py#L147-L288).
- **The pattern to follow** already exists. [require_project_member_or_admin](file:///src/ai_qa/api/projects.py#L75-L94) returns the project only for admins or active members and raises `404 Resource not found` otherwise (no detail leak). The artifact API composes this as `ProjectAccessDependency` on every route ([artifacts.py](file:///src/ai_qa/api/artifacts.py#L171-L285)). Thread endpoints should gain an equivalent membership gate layered on top of the existing ownership check.
- **Already enforced — verify, don't re-add.** The pipeline/WebSocket path derives `project_id` from the thread and calls `require_project_member_or_admin`, so project-bound agent actions are already membership-gated. See [_build_pipeline_context](file:///src/ai_qa/api/routes.py#L230-L282) (thread ownership check at L236, membership check at L261). The WebSocket entrypoint routes through this same builder ([websocket.py](file:///src/ai_qa/api/websocket.py#L200-L237)).
- **Authorization model.**
  - `ProjectMembership` is the source of truth: unique on `(project_id, user_id)`, indexed on `(user_id, project_id)` ([models.py](file:///src/ai_qa/db/models.py#L74-L92)). Removal is a hard delete of that row ([remove_project_membership](file:///src/ai_qa/api/admin.py#L358-L381)), so enforcement is a simple presence check — no soft-delete/`is_active` flag on membership.
  - Admins (`User.role == ADMIN_ROLE`) bypass membership, matching every other resource gate. `ADMIN_ROLE` comes from `ai_qa.auth.service`.
  - Threads with `project_id IS NULL` are personal/unbound and must stay accessible to the owner regardless of any membership.
- **Status code decision (flag for review).** For project-membership denial, return `404 Resource not found` to match `require_project_member_or_admin` and satisfy "does not expose thread, project, artifact, or agent-run details." This differs from the current thread `403 "Forbidden thread access"` used for a different owner. Keep ownership-by-a-different-user behavior as-is; apply `404` specifically to membership-loss on project-bound threads. Confirm during dev if a unified `404` for all denials is preferred.
- **Architecture patterns and constraints.**
  - Keep `ai_qa/threads/service.py` focused on domain logic and `api/threads.py` thin (HTTP transport + error mapping), consistent with Story 7.5.
  - API responses use Pydantic models with snake_case keys; never return secrets; resolve the user via the auth dependency / `request.state.user`.
  - A bound `project_id` on a thread is immutable once Alice binds it (Story 7.5 constraint) — enforcement must not mutate it.
- **Source tree components to touch.**
  - `src/ai_qa/threads/service.py` — membership-aware list filter + access helper.
  - `src/ai_qa/api/threads.py` — apply the gate to all project-scoped thread routes; map denial to `404`.
  - `src/ai_qa/api/projects.py` — reuse/extract the admin-or-member check (`require_project_member_or_admin`).
  - `frontend/src/App.tsx`, `frontend/src/lib/api.ts`, `frontend/src/lib/threads.ts`, `frontend/src/components/conversations/ProjectSidebar.tsx` — safe denial handling and recovery prompt.
- **Frontend wiring notes.**
  - `apiFetch` already classifies `403 → "forbidden"` and `404 → "not_found"` and only fires the global `auth-error` (logout) flow on `401` ([api.ts](file:///frontend/src/lib/api.ts#L62-L133)). Membership denials must NOT logout the user.
  - `ProjectSidebar` filters threads by `project_id` after fetching `/threads`, and lists projects from `/projects` ([ProjectSidebar.tsx](file:///frontend/src/components/conversations/ProjectSidebar.tsx#L295-L340)). Once the backend list is filtered, removed-project content drops out on the next fetch.
  - There is precedent for recovering from project-scope failures: the `wsError` effect calls `clearSelectedProject(...)` with a user-facing message ([App.tsx](file:///frontend/src/App.tsx#L529-L547)) and a `threadCreationError` banner with a Retry/clear action (App.tsx ~L905-L920). Mirror this for thread-resume denial.

### Project Structure Notes

- Backend domain logic stays in `src/ai_qa/threads/service.py`; HTTP mapping stays in `src/ai_qa/api/threads.py`. The membership check should be expressed once and reused, not copy-pasted into each of the ~7 endpoints.
- Frontend conversation/threads code currently lives under `frontend/src/components/conversations/` and `frontend/src/lib/`, not the `frontend/src/features/conversations/` path referenced in older epics — follow the actual layout.

### Previous Story Intelligence

From Story 7.5 (Conversation History and Thread Resume):
- `get_user_threads` returns the owner's non-archived threads ordered by `updated_at DESC`; `get_thread_details` enforces ownership only — both are the focal points for this story.
- Threads carry `conversation_data` (JSON) loaded/saved via `/{thread_id}/conversation`; messages and agent runs hang off the thread. All of these are the "details" AC2 says must not leak to a removed member.
- Private-thread isolation (user B cannot see user A's threads) is already covered; 7.6 adds the orthogonal project-membership dimension on top of ownership.

### Git Intelligence

- Baseline commit: `2b6b5be`. Recent work (7.4 thread-scoped messages/agent runs, 7.5 history & resume) established the thread models, service queries, and `ProjectSidebar`. 7.6 is primarily an authorization-tightening story plus a list filter and frontend denial handling — no new tables.

### Latest Tech Information

- Python 3.12+, FastAPI, SQLAlchemy/Alembic, PostgreSQL (SQLite in-memory for tests via `StaticPool`).
- React 18+, TypeScript, Vite.

### References

- [Epic 7: Secure Multi-User Workspace Foundation](file:///_bmad-output/planning-artifacts/epics.md#L238)
- [Story 7.6 definition](file:///_bmad-output/planning-artifacts/epics.md#L364-L383)
- [require_project_member_or_admin (authorization pattern)](file:///src/ai_qa/api/projects.py#L75-L94)
- [Thread REST routes (ownership-only gaps)](file:///src/ai_qa/api/threads.py#L78-L288)
- [ThreadService.get_user_threads / get_thread_details](file:///src/ai_qa/threads/service.py#L220-L246)
- [_build_pipeline_context (already membership-gated)](file:///src/ai_qa/api/routes.py#L200-L282)
- [Admin membership removal endpoint](file:///src/ai_qa/api/admin.py#L358-L381)
- [ProjectMembership model](file:///src/ai_qa/db/models.py#L74-L92)
- [Frontend apiFetch error classification](file:///frontend/src/lib/api.ts#L62-L136)
- [ProjectSidebar data loading](file:///frontend/src/components/conversations/ProjectSidebar.tsx#L280-L340)

## Dev Agent Record

### Agent Model Used

Gemini 3 Pro (High)

### Debug Log References

- Generated via bmad-create-story workflow.

### Completion Notes List

- Story drafted from epics.md Story 7.6 plus deep code analysis of the thread authorization surface (REST vs. artifact vs. pipeline/WebSocket paths).
- Backend: added reusable membership helpers `is_project_member` / `user_can_access_project` in `projects/service.py` (mirrors `require_project_member_or_admin`), a `ThreadAccessDeniedError` + `assert_thread_access` in `threads/service.py`, and a membership-scoped `get_user_threads(is_admin=...)` list filter. `api/threads.py` was refactored to gate all 7 project-scoped endpoints through one `_authorize_thread` helper that maps membership loss to a generic `404 Resource not found` (different-owner stays `403`).
- Decision (was flagged for review): project-membership denial returns `404` to avoid existence leaks; a different-owner request keeps the existing `403`. The pipeline/WebSocket path was already gated via `_build_pipeline_context` → `require_project_member_or_admin`, so it received a regression test only (no new enforcement code).
- Frontend: `usePipelineState` now returns a `"denied"` sentinel for `403`/`404` thread fetches and invokes an `onThreadDenied` callback (via a ref to avoid re-fetch loops). `App.tsx` clears the stale `ai-qa-thread-id` and shows a dismissible amber recovery banner (no global logout); the notice clears on thread select / new conversation.
- Verification: `ruff check` + `ruff format --check` clean, `mypy src` clean, full backend suite `632 passed, 2 skipped` at 81.16% coverage; frontend `tsc --noEmit` clean, new `usePipelineState` denial tests (4) and existing `App.test.tsx` (8) pass.

### File List

- `_bmad-output/implementation-artifacts/7-6-membership-removal-access-enforcement.md` (NEW)
- `src/ai_qa/projects/service.py` (MODIFY) — `is_project_member`, `user_can_access_project` helpers.
- `src/ai_qa/threads/service.py` (MODIFY) — `ThreadAccessDeniedError`, `assert_thread_access`, membership-scoped `get_user_threads`.
- `src/ai_qa/api/threads.py` (MODIFY) — `_authorize_thread` gate on all project-scoped endpoints; generic `404` denial mapping; `is_admin` list scoping.
- `frontend/src/hooks/usePipelineState.ts` (MODIFY) — thread-denial detection + `onThreadDenied` callback.
- `frontend/src/App.tsx` (MODIFY) — `handleThreadDenied`, stale-thread clearing, recovery banner, notice clearing on recovery.
- `tests/threads/test_service.py` (MODIFY) — membership list-filter + `assert_thread_access` tests.
- `tests/threads/test_threads_api.py` (MODIFY) — list hiding + per-endpoint generic-404 denial + member/admin success tests.
- `tests/api/test_routes_extended.py` (MODIFY) — pipeline/WebSocket membership-denial regression test.
- `frontend/src/hooks/usePipelineState.test.tsx` (NEW) — frontend denial-handling tests.

## Review Findings (code review 2026-06-06)

- [x] [Review][Patch] `PATCH /threads/{id}/runs/{run_id}` never verifies the run belongs to the path thread [src/ai_qa/api/threads.py:L266-L276] — **Fixed (2026-06-06).** Added a keyword-only `expected_thread_id` to `ThreadService.update_agent_run` that raises `ThreadAccessDeniedError` *before* any mutation when `run.thread_id != thread_id`; the route now passes `expected_thread_id=thread_id` and maps the denial to the generic `404 Resource not found` (replacing the old post-commit `400` check that still persisted the cross-thread write). Regression test `test_update_run_via_sibling_thread_is_denied_without_mutation` proves the run is not mutated.
- [x] [Review][Defer] Thread-list admin scoping uses the stale session/JWT role [src/ai_qa/api/threads.py:L99-L101] — deferred, edge/pre-existing. `get_user_threads` derives `is_admin` from `current_user.role` (JWT/session) while `assert_thread_access` uses the live DB `User.role`. An admin demoted to standard mid-session keeps `role=admin` in the JWT until expiry, so the list endpoint still shows all their own threads while per-thread access uses DB truth. Outside 7.6's membership-removal scope; only relevant on role demotion.
