---
baseline_commit: "2b59ae9"
---
# Story 8.4: Project Membership Assignment

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> [!IMPORTANT]
> **This is a verification/coverage story** — the membership backend, frontend UI, and API client are **already implemented and well-tested**. The membership endpoints — assign ([assign_project_membership](file:///src/ai_qa/api/admin.py#L327-L368)), remove ([remove_project_membership](file:///src/ai_qa/api/admin.py#L371-L394)) — plus the user-facing project listing ([GET /api/projects](file:///src/ai_qa/api/projects.py#L100-L111)) and the AdminDashboard per-user assign-dropdown + chip-remove UI ([AdminDashboard.tsx L666-L755](file:///frontend/src/components/admin/AdminDashboard.tsx#L666-L755)) all exist (built across 6-4, 6-9, 7-6). Most ACs are already covered by existing backend tests in [test_admin_rbac_api.py](file:///tests/api/test_admin_rbac_api.py) and the AdminDashboard unit test. **The dev work is to verify each AC against existing coverage, close the AC1 round-trip gap (admin assigns → member sees the project in `GET /api/projects`) with a single focused backend test, and add the consolidated `story-8-4-project-membership-assignment.spec.ts` e2e that exercises the admin dashboard membership UI end-to-end against a live stack.**

## Story

As an admin,
I want to assign users to projects and remove users from projects,
so that each user can access only authorized project workspaces.

## Acceptance Criteria

1. **Given** users and projects exist
   **When** an admin assigns a user to a project (`POST /api/admin/projects/{project_id}/memberships`)
   **Then** the membership is stored in the project membership table with the requested `role` (default `"member"`)
   **And** the assigned user can see that project in their accessible project list (`GET /api/projects`) after the next refresh.

2. **Given** a user is already assigned to a project
   **When** an admin re-`POST`s the same `(project_id, user_id)` membership
   **Then** the system does not create a duplicate row — the existing membership row is reused (returned `id` is unchanged) and only the `role` is updated
   **And** the admin dashboard does not surface the already-assigned project in the per-user assignment dropdown (preventing duplicate assignment from the UI).

3. **Given** an admin removes a user from a project (`DELETE /api/admin/projects/{project_id}/memberships/{user_id}`)
   **When** the removal is saved
   **Then** the user no longer sees that project in their accessible project list (`GET /api/projects`)
   **And** thread access enforcement from Epic 7 (Story 7.6) continues to deny project-bound thread/artifact access for the removed user (no regression).

4. **Given** a standard or unauthenticated caller targets either membership endpoint
   **When** backend authorization is evaluated
   **Then** assign/remove are rejected (`403` for standard, `401` for anonymous) with **only** a `{"detail": ...}` body (no admin-only data leaked).

## Tasks / Subtasks

- [x] Task 1: Verify admin assigns a user to a project and the user can see it (AC: 1)
  - [x] Confirm [assign_project_membership](file:///src/ai_qa/api/admin.py#L327-L368) is mounted at `POST /api/admin/projects/{project_id}/memberships`, accepts `MembershipCreateRequest` ([admin.py L140-L144](file:///src/ai_qa/api/admin.py#L140-L144)), defaults `role` to `"member"`, validates project + user exist + user is active (returns `404 "Resource not found"` otherwise), and persists `ProjectMembership(project_id, user_id, role)`. **Verified** at [admin.py L334-L350](file:///src/ai_qa/api/admin.py#L334-L350).
  - [x] Confirm [list_projects](file:///src/ai_qa/api/projects.py#L100-L111) returns the just-assigned project for the assigned user (admin sees all; standard sees memberships only via `require_project_member_or_admin` at the listing layer). **Verified**: standard users resolve through [get_user_projects](file:///src/ai_qa/projects/service.py#L12-L22).
  - [x] **AC1 round-trip is the genuine test gap.** Added focused backend test [test_assigned_member_sees_project_in_accessible_list](file:///tests/api/test_admin_rbac_api.py#L647-L692): create admin + standard + project, confirm standard's `GET /api/projects` is `[]`, admin assigns membership, then confirm standard's next `GET /api/projects` includes the project (matching id + name). Reuses the existing `admin_client` fixture. **Passing.**
- [x] Task 2: Verify duplicate assignment is idempotent (AC: 2)
  - [x] Backend behavior already covered by [test_admin_assigns_membership_and_duplicate_updates_role](file:///tests/api/test_admin_rbac_api.py#L315-L346): a second `POST` with the same `(project_id, user_id)` returns `200` with the **same** `id` and updated `role`. **Verified passing — no duplicate test added.**
  - [x] UI duplicate guard in place: [assignableProjectsByUserId](file:///frontend/src/components/admin/AdminDashboard.tsx#L319-L333) filters out already-assigned projects from each per-user select. The 8-4 e2e asserts the assigned project leaves the select after assignment (AC2 UI guard). **Verified — no duplication.**
- [x] Task 3: Verify admin removes a user from a project and access is dropped (AC: 3)
  - [x] Confirm [remove_project_membership](file:///src/ai_qa/api/admin.py#L371-L394) returns `204` on success, `404 "Resource not found"` on a second delete, and `409 "Membership cannot be removed"` on `IntegrityError`. Covered by [test_admin_can_remove_project_membership](file:///tests/api/test_admin_rbac_api.py#L531-L557). **Verified passing.**
  - [x] AC3 round-trip "after admin removes membership, member's `GET /api/projects` no longer lists it" is proven by the 8-4 e2e AC3 case (chip removed → member's `GET /api/projects` no longer returns the project) plus the forward backend test. No separate backend test required.
  - [x] AC3's "thread access enforcement from Epic 7 applies" clause is **owned by Story 7.6** ([story-7-6-membership-removal.spec.ts](file:///frontend/e2e/story-7-6-membership-removal.spec.ts)) — referenced as the regression guardrail, not re-implemented.
- [x] Task 4: Verify RBAC denials are secret-free (AC: 4)
  - [x] standard→`403 {"detail": "Forbidden"}` and anonymous→`401 {"detail": "Not authenticated"}` for both assign (`POST`) and remove (`DELETE`) with exact body equality — covered by [test_standard_and_unauthenticated_users_cannot_manage_memberships](file:///tests/api/test_admin_rbac_api.py#L600-L644). **Verified passing — no duplication.**
- [x] Task 5: Consolidated E2E coverage for Story 8.4 (AC: 1, 2, 3)
  - [x] Added [story-8-4-project-membership-assignment.spec.ts](file:///frontend/e2e/story-8-4-project-membership-assignment.spec.ts) mirroring the 8-3 helpers verbatim — `apiBaseUrl`, `ensureAdminToken`, `createAdminUser`, `createAdminProject`, `listAccessibleProjects`, `loginViaApi`, the `ADMIN_DASHBOARD_E2E` skip guard, `beforeEach` localStorage cleanup, and `afterEach` cleanup that deletes projects before users.
  - [x] AC1/AC2 case: admin logs in, picks the seeded project from `Select project for {display_name}`, clicks `Assign project to {display_name}`, then asserts (a) `Project assigned successfully.` banner, (b) the chip appears, (c) the assigned project leaves the select (AC2 UI guard), and (d) the member's `GET /api/projects` returns the project. **Passing.**
  - [x] AC3 case: clicks `Remove {project_name} from {display_name}` (`×`), then asserts (a) `Project unassigned successfully.` banner, (b) chip gone, (c) the project re-appears as a select option, and (d) the member's `GET /api/projects` no longer returns the project. No Epic-7 thread-denial assertion (owned by 7.6). **Passing.**
  - [x] **No-mocking + cleanup:** state prepared via real admin API calls; every created project + user cleaned up in `afterEach` with an admin token. No `page.route` mocks.
- [x] Task 6: Validation gate (project-context.md Verification Workflow)
  - [x] Backend: `uv run ruff check .` (pass), `uv run ruff format --check .` (pass after formatting the test file), `uv run mypy src` (pass), `uv run pytest` (**642 passed, 2 skipped**). No schema change, so `alembic upgrade head` skipped.
  - [x] Frontend: `npm run lint` (pass), `npm run typecheck` (pass).
  - [x] E2E: live-stack run `npx playwright test e2e/story-8-4-project-membership-assignment.spec.ts` — **2 passed**; afterEach + global teardown confirmed clean.

## Dev Notes

- **The endpoints already exist and are correct — this is a coverage story.** `POST /api/admin/projects/{project_id}/memberships` and `DELETE /api/admin/projects/{project_id}/memberships/{user_id}` live in [admin.py](file:///src/ai_qa/api/admin.py#L323-L394). `MembershipCreateRequest` ([admin.py L140-L144](file:///src/ai_qa/api/admin.py#L140-L144)) accepts `user_id: UUID` + `role: Literal["member", "owner"] = "member"`. `AdminMembershipResponse` ([admin.py L147-L157](file:///src/ai_qa/api/admin.py#L147-L157)) is secret-free (no email, no password_hash). The dashboard membership UI (per-user select + `+` assign + `×` remove on chips) is in [AdminDashboard.tsx L666-L755](file:///frontend/src/components/admin/AdminDashboard.tsx#L666-L755). The dev job is to verify each AC against existing coverage, add **one** focused backend round-trip test (admin assigns → member's `GET /api/projects` now includes the project), and add the consolidated 8-4 e2e spec.
- **`assign_project_membership` is intentionally idempotent (AC2 backend semantics).** The endpoint runs an explicit `select` for an existing `(project_id, user_id)` row first; if found, it updates `role` in-place rather than inserting (returning the same membership `id`). The `IntegrityError` branch ([admin.py L356-L365](file:///src/ai_qa/api/admin.py#L356-L365)) is a race-safe fallback for concurrent inserts. The frontend's [assignableProjectsByUserId](file:///frontend/src/components/admin/AdminDashboard.tsx#L319-L333) filter is the **UI-side** AC2 guard — it removes already-assigned projects from each user's per-row select so admins cannot pick a duplicate from the dropdown.
- **`remove_project_membership` returns 404 for the second delete and is membership-row-scoped — not user-scoped.** A `DELETE` on `/api/admin/projects/{project_id}/memberships/{user_id}` removes only that one `ProjectMembership` row; the underlying `User` is untouched. Confirmed by [test_admin_can_remove_project_membership](file:///tests/api/test_admin_rbac_api.py#L531-L557).
- **AC1 "user can see the project after login or refresh" resolves through `GET /api/projects`, not a dedicated admin endpoint.** Admins receive every project; standard users receive only projects they have a `ProjectMembership` for. The frontend pulls this through [useProject](file:///frontend/src/hooks/useProject.ts) → [getUserProjects](file:///frontend/src/lib/projects.ts#L12-L14). The AC1 assertion is therefore an assertion on that user's `GET /api/projects` after the admin's `POST /memberships` succeeds — exactly the pattern used in [test_deleted_project_disappears_from_affected_member_project_list](file:///tests/api/test_admin_rbac_api.py#L647-L688) but in the **forward** direction.
- **Inactive users are silently rejected with `404 "Resource not found"`, not `409`.** [assign_project_membership](file:///src/ai_qa/api/admin.py#L334-L337) treats `target_user is None or not target_user.is_active` identically — both return `404`. This is intentional (no user enumeration leak) and is covered by [test_admin_cannot_assign_inactive_user_to_project](file:///tests/api/test_admin_rbac_api.py#L365-L381). The dashboard mirrors it client-side via the `Inactive users cannot be assigned to projects.` guard ([AdminDashboard.tsx L211-L213](file:///frontend/src/components/admin/AdminDashboard.tsx#L211-L213)).
- **Do not regress 8.1 / 8.2 / 8.3 / 7.6.** Story 8.1 owns the admin routing fork + the RBAC denial-body guarantees (`{"detail": ...}` only) that 8.4 AC4 leans on; 8.2 owns user management; 8.3 owns project CRUD; **7.6 owns the cross-membership thread-access enforcement that AC3 references**. If you touch `admin.py` or `AdminDashboard.tsx`, re-run the 8.1 backend RBAC tests, the 8.2 user tests, the 8.3 project tests, the AdminDashboard unit suite, and the 7-6 e2e.
- **Do NOT add a confirmation dialog on the chip `×`.** UX-DR11 (Epic 7-8 design system) forbids confirmation dialogs — chip removal is a direct action. Status feedback comes through the `Project unassigned successfully.` banner ([handleRemoveUserFromProject](file:///frontend/src/components/admin/AdminDashboard.tsx#L248-L265)).

### Project Structure Notes

- Admin membership endpoints + schemas live in [admin.py](file:///src/ai_qa/api/admin.py); user-facing accessible-project listing + `require_project_member_or_admin` in [projects.py](file:///src/ai_qa/api/projects.py); ORM in [models.py](file:///src/ai_qa/db/models.py#L83-L92) (`ProjectMembership` with composite uniqueness via the assign-or-update path; project-scoped FK uses `ON DELETE CASCADE`).
- Admin UI: [AdminDashboard.tsx](file:///frontend/src/components/admin/AdminDashboard.tsx) — per-user `Projects` section + `Select project for {name}` `<select>` + `+` Assign button at L666-L727, assigned-project chips with `×` Remove at L728-L750. Handlers: [handleAssignUserToProject](file:///frontend/src/components/admin/AdminDashboard.tsx#L210-L246), [handleRemoveUserFromProject](file:///frontend/src/components/admin/AdminDashboard.tsx#L248-L265). API client: [assignProjectMembership](file:///frontend/src/lib/projects.ts#L61-L72) / [removeProjectMembership](file:///frontend/src/lib/projects.ts#L74-L82). Types: [CreateMembershipRequest](file:///frontend/src/types/project.ts#L58) and `AdminUserProjectMembership` in [project.ts](file:///frontend/src/types/project.ts#L32-L49).
- Backend tests: [tests/api/test_admin_rbac_api.py](file:///tests/api/test_admin_rbac_api.py) (in-memory SQLite via `StaticPool`, `engine.dispose()` teardown, `cast(list[Table], [...])` selective `create_all`). Frontend unit: [AdminDashboard.test.tsx](file:///frontend/src/components/admin/AdminDashboard.test.tsx) (Vitest/jsdom, `fetch` spy). E2E: `frontend/e2e/*.spec.ts` (Playwright, real backend) using `frontend/support/fixtures`.

### Testing Standards (from project-context.md)

- **E2E no-mocking + cleanup:** hit the real backend; bootstrap state via real API calls (`ensureAdminToken`, then admin `POST /api/admin/users` + `POST /api/admin/projects` + `POST /api/admin/projects/{id}/memberships`); clean up every created project + user in `afterEach` with an admin token (delete projects **before** users — project delete cascades memberships). The 8-6 `page.route` mock pattern is a narrow self-trigger-loop exception — do **not** copy it.
- **Backend SQLite:** dispose the engine in teardown; annotate `yield` fixtures as `Generator[...]`; narrow `client.app` with `cast(FastAPI, client.app)` before `dependency_overrides`/`state`; wrap selective `create_all(tables=...)` with `cast(list[Table], [...])`. The `admin_client` fixture in `test_admin_rbac_api.py` already wires `User`, `Project`, and `ProjectMembership` tables — **reuse it** for the new AC1 round-trip test.
- **TS strictness:** `npm run typecheck` enforces `noUnusedLocals`/`noUnusedParameters` — remove any unused Playwright helper you add. If you no longer read a caught response's `.json()`, delete the variable (ts6133).
- **Lint/type gates mandatory:** backend ruff + ruff format + mypy (only if Python changes); frontend lint + typecheck; markdown diagnostics for this file (MD032: blank lines around lists).
- **Playwright env noise** (`DEP0205`, dotenv banner) is benign/suppressed; keep `timeout: 60*1000` in `playwright.config.ts` (do not shrink — slow-mo adds per-action cost).
- **Assertion-label drift:** match the rendered labels exactly — per-user `Select project for {display_name}` combobox, per-user `Assign project to {display_name}` button, per-chip `Remove {project_name} from {display_name}` button ([AdminDashboard.tsx L698-L744](file:///frontend/src/components/admin/AdminDashboard.tsx#L698-L744)), and the success banners `Project assigned successfully.` / `Project unassigned successfully.` ([AdminDashboard.tsx L238-L257](file:///frontend/src/components/admin/AdminDashboard.tsx#L238-L257)).

### Previous Story Intelligence

From 8-3 (Admin Project Management), 8-2 (Admin User Management), 8-1 (Admin Routing), 7-2 (Project Membership Access), 7-6 (Membership Removal), and 6-4 (Project/Membership API):

- 8-1/8-2/8-3 established the **verification-story pattern**: confirm pre-existing impl, add only the focused test gap + a consolidated `story-8-X-*.spec.ts`, reuse helpers (`ensureAdminToken`, `createAdminProject`, `createAdminUser`, `assignMembership`, `loginViaApi`, the `ADMIN_DASHBOARD_E2E` skip guard) **verbatim** from [story-8-3-admin-project-management.spec.ts](file:///frontend/e2e/story-8-3-admin-project-management.spec.ts). Follow it here.
- 8-1 added the backend denial-matrix test asserting bodies equal exactly `{"detail": ...}`. 8-4 AC4 rides the same `require_admin` layer and is **already covered** by [test_standard_and_unauthenticated_users_cannot_manage_memberships](file:///tests/api/test_admin_rbac_api.py#L600-L644). Reuse — do not duplicate.
- 8-2's `getSafeApiErrorMessage` finding: a `409` maps to `kind="server"` in [api.ts](file:///frontend/src/lib/api.ts) → the banner shows the generic safe fallback, not the raw backend `detail`. Membership endpoints generally return `200`/`204`/`404`/`403`/`401`, not `409`, so this is unlikely to bite — but if you add an error case, assert the safe fallback, not the literal backend string.
- 8-3 delivered the cross-user **forward direction** test (admin **deletes** project → member's `GET /api/projects` no longer lists it). 8-4 owns the **inverse forward direction** (admin **assigns** membership → member's `GET /api/projects` now lists it). Mirror that test structure exactly in `test_assigned_member_sees_project_in_accessible_list`.
- 7-2 owns the standard-user "membership-only visibility" semantics on `GET /api/projects`; 7-6 owns the cross-membership thread/artifact access denial that AC3 references. Both are already e2e-covered ([story-7-2-project-membership.spec.ts](file:///frontend/e2e/story-7-2-project-membership.spec.ts), [story-7-6-membership-removal.spec.ts](file:///frontend/e2e/story-7-6-membership-removal.spec.ts)) — do **not** re-implement them in 8-4.
- 6-4 delivered `GET /api/projects` with admin all-project visibility + `memberships[]` summaries and `require_project_member_or_admin`, with tests in [test_project_api.py](file:///tests/api/test_project_api.py). The new AC1 round-trip test stays in `test_admin_rbac_api.py` (because the assign call needs the admin fixture); do **not** sprawl it into `test_project_api.py`.
- **`8-4-project-membership-assignment` is missing from `sprint-status.yaml`** (epic-8 lists `8-1`, `8-2`, `8-3`, `8-6`, `8-7`), exactly as `8-1`/`8-2`/`8-3` were when their stories were drafted. This story creation adds it and sets it `ready-for-dev`. Story 8-5 (Admin Dashboard UI Layout) remains a separate gap — out of scope for this story.

### Git Intelligence

- Baseline commit: `2b59ae9` (`story 8-3 code and test OK`). Recent: `42c9acf` (8-3 baseline pre-impl), `132d2c1` (8-2 code+test), `7835943` (8-1 code+test). The membership endpoints, schemas, API client, and dashboard membership UI are already committed and green from 6-4 / 6-9 / 7-6 work. **8.4 ideally adds: 1 backend test + 1 e2e spec + the sprint-status entry. No runtime code changes are expected.** If a code change is unavoidable (e.g. a missing aria-label), scope it narrowly and call it out in the Dev Agent Record.

### Latest Tech Information

- Backend: Python 3.14+, FastAPI with `Depends(require_admin)` RBAC; Pydantic v2 with `Literal["member", "owner"]` for `MembershipCreateRequest.role` (a non-`member`/`owner` role yields `422`, covered by [test_admin_assigns_membership_and_duplicate_updates_role](file:///tests/api/test_admin_rbac_api.py#L335-L346)). SQLAlchemy 2.x ORM with `select(...).scalar_one_or_none()` for the assign-or-update branch.
- Frontend: React 18 + TypeScript + Vite, Vitest + Testing Library (unit), Playwright (e2e). Project list state comes from the `useProject` context (`reloadProjects`); user list from `loadUsers()`; both are re-fetched after assign/remove ([AdminDashboard.tsx L239-L259](file:///frontend/src/components/admin/AdminDashboard.tsx#L239-L259)). Error surfacing goes through `getSafeApiErrorMessage` → red banner via `addError`.

### References

- [Epic 8: Admin Dashboard and Project Membership Management](file:///_bmad-output/planning-artifacts/epics.md#L428-L432)
- [Story 8.4 definition](file:///_bmad-output/planning-artifacts/epics.md#L510-L535)
- [assign_project_membership (AC1, AC2)](file:///src/ai_qa/api/admin.py#L327-L368)
- [remove_project_membership (AC3)](file:///src/ai_qa/api/admin.py#L371-L394)
- [MembershipCreateRequest / AdminMembershipResponse schemas](file:///src/ai_qa/api/admin.py#L140-L157)
- [list_projects (admin all-projects, AC1/AC3)](file:///src/ai_qa/api/projects.py#L100-L111)
- [Project / ProjectMembership models (cascade)](file:///src/ai_qa/db/models.py#L54-L92)
- [Per-user assign-dropdown + chip-remove UI](file:///frontend/src/components/admin/AdminDashboard.tsx#L666-L755)
- [handleAssignUserToProject / handleRemoveUserFromProject](file:///frontend/src/components/admin/AdminDashboard.tsx#L210-L265)
- [assignProjectMembership / removeProjectMembership API client](file:///frontend/src/lib/projects.ts#L61-L82)
- [Backend: assign + duplicate-updates-role + invalid-role-422](file:///tests/api/test_admin_rbac_api.py#L315-L346)
- [Backend: missing-resource 404](file:///tests/api/test_admin_rbac_api.py#L349-L362)
- [Backend: inactive-user 404](file:///tests/api/test_admin_rbac_api.py#L365-L381)
- [Backend: remove + 204 + 404-on-second](file:///tests/api/test_admin_rbac_api.py#L531-L557)
- [Backend: standard 403 + anonymous 401, exact body equality](file:///tests/api/test_admin_rbac_api.py#L600-L644)
- [Backend: cross-user delete-loses-access (mirror this for assign)](file:///tests/api/test_admin_rbac_api.py#L647-L688)
- [Frontend: assign-then-remove via mocked fetch](file:///frontend/src/components/admin/AdminDashboard.test.tsx#L93-L291)
- [Story 8-3 e2e (helpers to reuse verbatim)](file:///frontend/e2e/story-8-3-admin-project-management.spec.ts)
- [Story 7-6 e2e (AC3 thread-enforcement guardrail — do not duplicate)](file:///frontend/e2e/story-7-6-membership-removal.spec.ts)
- [project-context.md (testing + verification rules)](file:///project-context.md)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (Thinking)

### Debug Log References

- Generated via bmad-create-story workflow.

### Completion Notes List

- Story drafted from epics.md Story 8.4 plus exhaustive code analysis of the admin membership endpoints ([admin.py L323-L394](file:///src/ai_qa/api/admin.py#L323-L394)), `MembershipCreateRequest` / `AdminMembershipResponse` schemas, the user-facing project listing ([projects.py L100-L111](file:///src/ai_qa/api/projects.py#L100-L111)), the AdminDashboard per-user assign-dropdown + chip-remove UI ([AdminDashboard.tsx L210-L265, L666-L755](file:///frontend/src/components/admin/AdminDashboard.tsx#L210-L265)), the API client ([projects.ts](file:///frontend/src/lib/projects.ts)), and existing coverage in [test_admin_rbac_api.py](file:///tests/api/test_admin_rbac_api.py) and [AdminDashboard.test.tsx](file:///frontend/src/components/admin/AdminDashboard.test.tsx).
- **Verification-story scope** (mirrors 8-3): all four membership ACs are implemented; existing tests cover assign idempotency, missing-resource 404, inactive-user 404, remove-with-double-delete, and the standard/anonymous denial matrix with exact `{"detail": ...}` bodies. **Real test gaps:** (1) the AC1 forward round-trip "admin assigns → member's `GET /api/projects` lists the project" — needs **one** focused backend test mirroring the inverse-direction test from 8-3; (2) the consolidated 8-4 e2e spec exercising the dashboard membership UI end-to-end. AC3's cross-thread-enforcement clause is owned by Story 7.6 — referenced as a regression guardrail, not re-implemented.
- **Note:** `8-4-project-membership-assignment` was missing from `sprint-status.yaml` (epic-8 lists `8-1`, `8-2`, `8-3`, `8-6`, `8-7`); added and set to `ready-for-dev` per the create-story workflow contract. Story 8-5 (Admin Dashboard UI Layout) remains a separate sprint-status gap — out of scope for this story.

### File List

- [tests/api/test_admin_rbac_api.py](file:///tests/api/test_admin_rbac_api.py) (MODIFIED) — added `test_assigned_member_sees_project_in_accessible_list` (AC1 forward round-trip).
- [frontend/e2e/story-8-4-project-membership-assignment.spec.ts](file:///frontend/e2e/story-8-4-project-membership-assignment.spec.ts) (NEW) — consolidated 8-4 e2e exercising the admin dashboard membership assign/remove UI end-to-end.
- [_bmad-output/implementation-artifacts/sprint-status.yaml](file:///_bmad-output/implementation-artifacts/sprint-status.yaml) (MODIFIED) — 8-4 status transitions (ready-for-dev → in-progress → review).

No runtime/source code changes were required — the membership endpoints, UI, and API client were already implemented and correct (verification story).

## Change Log

| Date | Version | Description | Author |
| --- | --- | --- | --- |
| 2026-06-06 | 0.1 | Story drafted: verification of existing admin membership assign/remove endpoints + UI. Identified the AC1 forward round-trip backend test as the genuine gap; consolidated 8-4 e2e spec to be added next. AC3 thread-enforcement clause delegated to Story 7.6 (no re-implementation). Added missing `8-4` entry to sprint-status. Status → ready-for-dev. | Bob (SM) |
| 2026-06-06 | 1.0 | Implemented verification story: added AC1 forward round-trip backend test and the consolidated 8-4 e2e spec. Verified AC2/AC3/AC4 against existing coverage (no duplication). All gates green: backend 642 passed/2 skipped, ruff + mypy clean, frontend lint + typecheck clean, 2 e2e passed. No source code changes needed. Status → review. | Amelia (Dev) |
