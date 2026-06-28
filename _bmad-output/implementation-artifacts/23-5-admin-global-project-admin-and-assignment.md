---
baseline_commit: 0e05262e4d3e53e8bb60cd014effb430f91ad773
---
# Story 23.5: Admin Global Project-Admin Authority and Project-Admin Assignment

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Backend + frontend. Two related capabilities Thuong asked for: (1) the platform **`admin` role implicitly has project-admin authority over EVERY project** — this is **already true** in the backend (the `require_project_admin_for_project` admin backdoor at [rbac.py:68-69](src/ai_qa/api/auth/rbac.py:68); admin sees all projects at [projects_admin.py:125-127](src/ai_qa/api/projects_admin.py:125)), so this part is mostly **audit-and-confirm + close any gaps**; and (2) an admin can **assign a project-admin user to one or more projects** (1..n), preserving the existing many-to-many `ProjectMembership(role="project_admin")` model. The NEW shift vs Epic 15: a user becomes "project-admin-capable" via their **Azure app role** (23.3), so the admin no longer *promotes* a standard user — they choose **which projects** an already-project-admin user manages. This also subsumes the deferred 16-13 bug (edit-a-project-admin had no project picker).

## Story

As a platform admin,
I want implicit project-admin rights over every project plus the ability to assign project-admin users to one or more projects,
so that I can delegate project administration without hand-managing each membership row.

## Acceptance Criteria

1. **Admin implicitly administers every project (confirm + close gaps).** Given the platform `admin` role, when an admin accesses any project-admin-gated capability (config, members, project list), then access is granted for ALL projects without requiring a `ProjectMembership` row — confirmed against `require_project_admin_for_project` ([rbac.py:56-80](src/ai_qa/api/auth/rbac.py:56), admin backdoor :68-69), `list_administered_projects` ([projects_admin.py:119-139](src/ai_qa/api/projects_admin.py:119)), `user_can_access_project` ([projects/service.py:39-47](src/ai_qa/projects/service.py:39)), and `list_projects` ([projects.py:114-116](src/ai_qa/api/projects.py:114)). This story AUDITS every project-admin-gated route for the admin bypass and adds it anywhere it is missing (a test asserts an admin can reach each project-admin route for a project they have NO membership on). No new "admin owns all" mechanism is invented — the backdoor is the single source of truth.

2. **Assign a project-admin user to one or more projects (BE).** Given a user who is project-admin-capable (holds the `project_admin` role from their Azure app role — 23.3), when an admin assigns them to project(s), then the backend supports setting the user's administered-project set to **1..n** projects by creating/keeping `ProjectMembership(project_id, user_id, role="project_admin")` rows and removing the ones no longer selected — **without stripping that user's other memberships or other users' memberships** (many-to-many preserved). This generalizes the current single-project transition in `update_user` ([admin.py:444-475](src/ai_qa/api/admin.py:444)) to a multi-project set operation.

3. **Assignment endpoint shape.** Given the admin user-management API ([admin.py](src/ai_qa/api/admin.py)), when this story is implemented, then either `AdminUserUpdateRequest` accepts a `project_ids: list[UUID]` (replacing/augmenting the single `project_id` at [admin.py:249](src/ai_qa/api/admin.py:249)) **or** a dedicated endpoint (e.g. `PUT /admin/users/{user_id}/project-admin-projects`) sets the administered-project set. The chosen shape is idempotent (re-sending the same set is a no-op), validates every project id exists, and returns the resulting membership set. Decide and document one shape; prefer extending `update_user` for minimal surface, but a dedicated endpoint is acceptable if cleaner.

4. **Project-admin role is conferred by in-app membership (Thuong 2026-06-25) — works before first login.** Given the membership-confers-role decision (23.3 AC4: effective roles ∪ `project_admin` when the user holds a `ProjectMembership(role="project_admin")`), when an admin makes someone a project-admin, then creating a `ProjectMembership(role="project_admin")` is **sufficient** — **no Azure `project-admin` app-role grant is required**. An admin can therefore **create a user AND assign them as project-admin of one or more projects entirely in-app, before that person has ever logged in** (reuse the `create_user` User+`ProjectMembership` path, identity-only after 23.6), and it takes effect on their first SSO login (23.3 derives `project_admin` from the membership and `require_project_admin_for_project` then passes). The platform **`admin`** role still comes **only** from Azure (never assignable in-app); the Azure `project-admin` app role is honored additively but is not necessary. The picker (AC6) is shown for any user who holds — or is being given — a `project_admin` membership.

5. **Platform-admin immutability preserved (Epic 15).** Given Epic 15's rule that the platform admin account is immutable, when assignment operations run, then they never demote/alter a platform `admin` and never let an admin strip their own implicit authority. Reuse the existing immutability guards in `admin.py` ([admin.py:418-491](src/ai_qa/api/admin.py:418)).

6. **Frontend assignment UI (multi-project).** Given today's Admin Dashboard edit-user flow only shows a project picker while PROMOTING a standard user and shows none when editing an existing project-admin (the deferred 16-13 bug — [AdminDashboard.tsx:896-1062](frontend/src/components/admin/AdminDashboard.tsx:896)), when this story is implemented, then editing a project-admin user shows a **multi-select** of projects (their current administered set pre-checked), and saving calls the AC3 endpoint. The picker is shown whenever the target user's role set includes `project_admin` (not only on the standard→project_admin transition). **Adapt** the per-id `useRef` hydration guard pattern that fixed the form-clobber bug — it currently lives in [ProjectAdminDashboard.tsx:93](frontend/src/components/admin/ProjectAdminDashboard.tsx:93) as `hydratedProjectIdRef`, **not** in `AdminDashboard.tsx` (which has no `useRef` today), so model a new guard on it (memory `e2e-login-user-email-test-tld-gotcha`).

7. **Project-admin self-view reflects the full set.** Given a project-admin manages multiple projects, when they open the Project Admin Dashboard, then the project selector lists **all** projects they administer ([projects_admin.py:128-138](src/ai_qa/api/projects_admin.py:128) already joins the many-to-many) — confirm this still holds after the assignment changes, and that an admin sees all projects there (AC1).

8. **No regression to Epic 15 user management.** Given Epic 15 delivered create/edit/delete user, project-admin picker on create, user sort, and admin immutability, when this story changes assignment to multi-project, then all Epic 15 behaviors still pass (create user with project-admin + project, sort, delete, immutability) — the change is additive (single→set), not a rewrite.

## Tasks / Subtasks

- [x] **Task 1 — Audit the admin-implicit-all-projects path (AC: 1, 7)**
  - [x] Audited all project-admin-gated routes: `require_project_admin_for_project` ([rbac.py:68](src/ai_qa/api/auth/rbac.py:68) admin backdoor), `require_project_member_or_admin` ([projects.py:95](src/ai_qa/api/projects.py:95)), `user_can_access_project` ([projects/service.py:45](src/ai_qa/projects/service.py:45)), `list_administered_projects` (admin-sees-all). The admin bypass is **already applied consistently — no gaps to close**. No parallel "admin owns all" mechanism added.
  - [x] Added a test (`test_admin_reaches_project_with_no_membership`): an admin with zero `ProjectMembership` rows can `POST /project-admin/projects/{id}/members` on an arbitrary project (200, not 403) and sees it in `GET /project-admin/projects`.

- [x] **Task 2 — Multi-project assignment (BE) (AC: 2, 3, 4, 5)**
  - [x] Chose **extending `update_user`**: added `AdminUserUpdateRequest.project_ids: list[UUID] | None` (replaces the set; `project_id` kept for legacy promotion). `_reconcile_project_admin_memberships` sets the user's `project_admin` membership set to exactly `project_ids` — adds missing (promoting an existing member/owner row in place), deletes only the de-selected `project_admin` rows, never touches non-project_admin rows or other users. Validates every id exists (404), requires ≥1 (422), idempotent.
  - [x] In-app role transitions KEPT as the mechanism: standard→project_admin creates the first PA membership(s); project_admin→standard removes all PA memberships. Platform-admin immutability guard preserved ([admin.py update_user](src/ai_qa/api/admin.py)).

- [x] **Task 3 — Frontend multi-select assignment (AC: 6)**
  - [x] `AdminDashboard.tsx` edit-user form: a checkbox multi-select ("Administered projects") is shown whenever `editUserRole === "project_admin"` (covers editing an existing PA, not only promotion — **fixes 16-13**). Pre-checked from the user's current `project_admin` memberships (`startEditingUser`). Save sends `project_ids`. **Hydration note:** AdminDashboard's edit form is **event-hydrated** in `startEditingUser` (not a `useEffect`), so the ProjectAdminDashboard `useRef` clobber-guard does not apply — the multi-select's checked state is local component state and is not re-clobbered when the user list reloads.
  - [x] Updated `UpdateAdminUserRequest` ([types/project.ts](frontend/src/types/project.ts)) with `project_ids?: string[] | null` (full-stack sync).

- [x] **Task 4 — Tests (all ACs)**
  - [x] Backend `tests/api/test_admin_pa_assignment.py`: {A}→{A,B}→{B,C} reconcile + idempotent; other users' + non-PA memberships untouched; unknown id → 404; empty set for project_admin → 422; project_ids on a standard user → 422; admin-reaches-any-project.
  - [x] Frontend `AdminDashboard.test.tsx`: editing a project_admin shows the pre-checked multi-select + saving sends both `project_ids`; editing a standard user shows no picker. (Existing Epic-15 create/edit/delete/immutability tests still green.)
  - [x] `npm run typecheck` + lint clean; `npx vitest run` → **383 passed**. Backend ruff + `mypy src` clean; `uv run pytest` whole suite → **1873 passed** (coverage 85%).

## Dev Notes

### Most of "admin = global project-admin" already exists — this story confirms it

The backend already treats `admin` as a project-admin everywhere via the backdoor ([rbac.py:68-69](src/ai_qa/api/auth/rbac.py:68)) and returns all projects for admins ([projects_admin.py:125-127](src/ai_qa/api/projects_admin.py:125), [projects.py:114-116](src/ai_qa/api/projects.py:114), [projects/service.py:39-47](src/ai_qa/projects/service.py:39)). Do NOT build a parallel "admin owns all" table or flag. The real work of AC1 is an **audit** that the bypass is applied on *every* project-admin-gated route and a test that proves it — plus the new multi-project assignment (AC2/AC3) and the FE picker (AC6).

### The semantic shift: an in-app membership CONFERS project-admin

Pre-SSO, an admin promoted a standard user to project_admin and attached one project ([admin.py:444-470](src/ai_qa/api/admin.py:444)). In the SSO model the platform **`admin`** role comes from Azure, but per Thuong's 2026-06-25 decision **`project_admin` is conferred by holding a `ProjectMembership(role="project_admin")`** (23.3 AC4) — NOT by an Azure app role. So the admin's in-app assignment is fully authoritative for project-admins: create the user + give them a `project_admin` membership on 1..n projects, and they are a project-admin on first login with **no Azure step and without logging in first**. AC2 generalizes the single `project_id` to a `project_ids` set; AC6 shows the picker for any project_admin user; AC4 makes pre-login assignment work. This also closes the deferred 16-13 bug by construction.

### Current behavior to PRESERVE (regression guardrails)

- **Many-to-many integrity** ([db/models.py:136-154](src/ai_qa/db/models.py:136), unique `(project_id, user_id)`): reconciliation must add/remove only the targeted user's `project_admin` rows for the targeted projects — never touch other users, other roles (`member`/`owner`), or non-selected projects.
- **Platform-admin immutability** (Epic 15): never demote/alter the admin account; reuse existing guards.
- **Epic 15 user-management flows** must still pass (create/edit/delete/sort/immutability) — additive change only.
- **Backend RBAC is the boundary**; the FE picker is convenience. The set endpoint must itself be admin-gated (`require_admin`).
- **Full-stack type sync** for the new request/response shape ([project-context.md](project-context.md)).

### Source tree components to touch

- `src/ai_qa/api/admin.py` — **UPDATE** (`project_ids` on `AdminUserUpdateRequest` or new set endpoint; reconciliation logic).
- `src/ai_qa/api/auth/rbac.py` / `src/ai_qa/api/projects_admin.py` / `src/ai_qa/api/projects.py` / `src/ai_qa/projects/service.py` — **AUDIT/UPDATE** (confirm/add admin bypass where missing).
- `frontend/src/components/admin/AdminDashboard.tsx` — **UPDATE** (multi-select project picker on edit project-admin; fixes 16-13).
- `frontend/src/types/project.ts` — **UPDATE** (request/response types).
- Tests — **ADD/UPDATE** (assignment reconciliation, admin-reaches-any-project, FE picker).

### Decided scope (defaults — Thuong, correct if needed)

- **Keep the backdoor as the admin-all mechanism** (audit, don't reinvent).
- **Generalize assignment to a project set** (1..n); prefer extending `update_user` with `project_ids`, dedicated endpoint acceptable.
- **Picker shown for any project_admin user** (closes 16-13), not just on promotion.
- **`project_admin` is conferred by in-app membership** (Thuong 2026-06-25) — admin create+assign is authoritative and works **before the PA's first login**; no Azure `project-admin` app-role needed. Only the platform **`admin`** role is Azure-sourced. In-app role transitions are KEPT (they are the mechanism), not deprecated.

### Testing standards summary

- Backend pytest whole-suite; FastAPI deps via `dependency_overrides`. FE Vitest 4 with the Epic-15 admin scaffold + `importOriginal`/`useRef`-guard patterns. No `page.route` mocking in e2e.

### Project Structure Notes

- No schema change (reuses `ProjectMembership`). No migration in this story.

### References

- Epic + story: [epics.md#Epic-23](_bmad-output/planning-artifacts/epics.md:2371), [Story 23.5](_bmad-output/planning-artifacts/epics.md:2407)
- Admin backdoor + project-admin gate: [api/auth/rbac.py:56-80](src/ai_qa/api/auth/rbac.py:56)
- Admin-sees-all-projects: [api/projects_admin.py:119-139](src/ai_qa/api/projects_admin.py:119), `list_projects` admin-all branch [api/projects.py:114-116](src/ai_qa/api/projects.py:114) (NB: the bypass at [projects.py:95-96](src/ai_qa/api/projects.py:95) is the SINGLE-project `require_project_member_or_admin` dependency — a different function), [projects/service.py:39-47](src/ai_qa/projects/service.py:39)
- Current single-project transition: [api/admin.py:235-278](src/ai_qa/api/admin.py:235) (request), [:444-491](src/ai_qa/api/admin.py:444) (update_user)
- Membership model: [db/models.py:136-154](src/ai_qa/db/models.py:136)
- FE edit-user form (16-13): [AdminDashboard.tsx:896-1062](frontend/src/components/admin/AdminDashboard.tsx:896); types [types/project.ts:52-80](frontend/src/types/project.ts:52)
- Coding/testing rules: [project-context.md](project-context.md)
- Related memories: [[epic-15-admin-rbac-sprint-change]], [[projectadmin-rbac-redesign-plan]], [[e2e-login-user-email-test-tld-gotcha]], [[epic-23-sso-first-auth]]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (BMAD dev-story)

### Debug Log References

- `uv run pytest tests/api/test_admin_pa_assignment.py tests/api/test_admin_users_api.py tests/api/test_admin_rbac_api.py` → 61 passed.
- FE `npx vitest run` → 383 passed; typecheck + lint clean. Backend `mypy src` clean.

### Completion Notes List

- **AC1 is audit-and-confirm:** the admin backdoor (`current_user.role == ADMIN_ROLE`) is already applied on every project-admin-gated path (`require_project_admin_for_project`, `require_project_member_or_admin`, `user_can_access_project`, `list_administered_projects`/`list_projects`). No gaps, no new mechanism — only a proving test added.
- **Assignment shape = extend `update_user` with `project_ids`** (minimal surface, idempotent set operation; legacy `project_id` still works for promotion). Set-reconciliation scopes deletes to the de-selected `project_admin` rows only — it does NOT reuse the old blanket-delete (that stays as the project_admin→standard demotion path).
- **Membership confers `project_admin` (23.3/Thuong):** creating the membership is sufficient — an admin can create a user + assign 1..n projects entirely in-app, before that person ever logs in, and it takes effect on first SSO login. The picker is shown for any project_admin user (closes 16-13). Only the platform `admin` role is Azure-sourced.
- **Guardrails preserved:** many-to-many integrity (reconcile touches only the targeted user's PA rows for the targeted projects), platform-admin immutability, and all Epic-15 user-management flows (create/edit/delete/sort) still pass.
- **A project_admin must administer ≥1 project** (422 on an empty set) — to drop all projects, demote the role to Standard. FE disables Save + shows guidance when the set is empty.

### File List

- `src/ai_qa/api/admin.py` — UPDATED (`AdminUserUpdateRequest.project_ids` + validator; `_resolve_target_project_ids` + `_reconcile_project_admin_memberships`; `update_user` multi-project branch).
- `frontend/src/types/project.ts` — UPDATED (`UpdateAdminUserRequest.project_ids`).
- `frontend/src/components/admin/AdminDashboard.tsx` — UPDATED (`editUserProjectIds` multi-select checkbox picker for any project_admin; pre-fill in `startEditingUser`; save `project_ids`; Save-disabled guard).
- `tests/api/test_admin_pa_assignment.py` — ADDED (6 backend assignment/audit tests).
- `frontend/src/components/admin/AdminDashboard.test.tsx` — UPDATED (2 new picker tests).

### Change Log

- 2026-06-25 — Story 23.5: multi-project project-admin assignment (`project_ids` set-reconciliation on `update_user`) + admin global-authority audit (backdoor confirmed, proving test) + FE multi-select picker for any project_admin (closes 16-13). BE 61-subset / FE 383 green. Status → review.
