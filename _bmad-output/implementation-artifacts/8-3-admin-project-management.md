---
baseline_commit: "42c9acf"
---
# Story 8.3: Admin Project Management

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> [!IMPORTANT]
> **Product decisions LOCKED (2026-06-06):** (1) **project names must be unique** and (2) **`confluence_base_url` is required**. The backend portion of these decisions is **already implemented and verified** in this branch — see the Dev Agent Record. Remaining work is frontend test coverage + the consolidated e2e spec. The pre-existing admin project endpoints — create ([create_project](file:///src/ai_qa/api/admin.py#L242-L267)), rename/update ([update_project](file:///src/ai_qa/api/admin.py#L270-L297)), delete ([delete_project](file:///src/ai_qa/api/admin.py#L300-L319)) — plus the project listing ([GET /api/projects](file:///src/ai_qa/api/projects.py#L100-L111)) and the AdminDashboard "Projects" list + "Create Project" + inline edit/delete UI all exist (built in 2-2, 6-4, refined in 6-8/6-9). Story 8.3 owns AC1–AC5, hardens them as regression guards, and closes the gaps: the unique-name enforcement, an end-to-end spec proving create → rename → delete against the live stack, and the AC4 cross-user clause (a deleted project disappears from an affected member's accessible list).

## Story

As an admin,
I want to create, rename, delete, and list projects,
so that I can maintain the project workspace structure.

## Acceptance Criteria

1. **Given** an authenticated admin opens project management
   **When** the frontend requests the project list (`GET /api/projects`)
   **Then** the backend returns all projects with `id`, `name`, `created_at`/`updated_at` (timestamps), and a membership summary (`membership_count` + `memberships[]`)
   **And** no password hashes or secret values are returned.

2. **Given** an authenticated admin creates a project (`POST /api/admin/projects`)
   **When** the backend validates the project name and Confluence URL
   **Then** the project is created and appears in the admin project list after reload
   **And** blank/whitespace-only project names are rejected (`422`)
   **And** a missing or blank `confluence_base_url` is rejected (`422`)
   **And** a duplicate project name (case/whitespace-trimmed match of an existing project) is rejected (`409` `"Project name already exists"`).

3. **Given** an authenticated admin renames a project (`PUT /api/admin/projects/{project_id}`)
   **When** the backend validates the update
   **Then** the project name is updated consistently in subsequent project and user/membership views
   **And** blank/whitespace-only names are rejected (`422`)
   **And** renaming to a name already used by a *different* project is rejected (`409`), while keeping a project's own name is allowed.

4. **Given** an authenticated admin deletes a project (`DELETE /api/admin/projects/{project_id}`)
   **When** the backend validates deletion
   **Then** the project (and its memberships, via `ON DELETE CASCADE` + the explicit membership purge) is removed and no longer appears in any assignable project list
   **And** affected standard users no longer see the deleted project as accessible (`GET /api/projects` for that user omits it).

5. **Given** a standard or unauthenticated caller targets any project mutation endpoint
   **When** backend authorization is evaluated
   **Then** create/update/delete are rejected (`403` for standard, `401` for anonymous) with only a `{"detail": ...}` body and no project data leaked.

## Tasks / Subtasks

- [ ] Task 1: Verify admin project listing returns timestamps + membership summary, secret-free (AC: 1)
  - [ ] Confirm the admin Projects panel sources its list from [GET /api/projects](file:///src/ai_qa/api/projects.py#L100-L111) via [useProject](file:///frontend/src/hooks/useProject.ts) → [getUserProjects](file:///frontend/src/lib/projects.ts#L12-L14) — NOT a dedicated `GET /api/admin/projects` (none exists; do NOT create one).
  - [ ] Confirm [list_projects](file:///src/ai_qa/api/projects.py#L100-L111) returns ALL projects for admins, and [_response_for_project](file:///src/ai_qa/api/projects.py#L51-L72) populates `membership_count` and (admin-only) `memberships[]` plus `created_at`/`updated_at`. The [ProjectResponse](file:///src/ai_qa/api/projects.py#L36-L48) schema exposes no password/secret fields — keep it; do not add fields.
  - [ ] Confirm admin all-project listing + membership summary is already covered in [tests/test_project_api.py](file:///tests/test_project_api.py) (from Story 6-4). If a timestamp/membership-summary assertion is missing, add one focused case rather than duplicating the whole suite.
- [x] Task 2: Admin project create — name validation + uniqueness + required Confluence URL (AC: 2) — **backend DONE**
  - [x] [create_project](file:///src/ai_qa/api/admin.py#L242-L267) sets `created_by_user_id` to the admin; [ProjectCreateRequest](file:///src/ai_qa/api/admin.py#L69-L92) trims `name`, rejects blank `422`, and requires `confluence_base_url` (`min_length=1`). Covered by [test_admin_can_create_project_and_standard_user_cannot](file:///tests/api/test_admin_rbac_api.py#L210-L241) + [test_admin_create_project_requires_confluence_base_url](file:///tests/api/test_admin_rbac_api.py).
  - [x] **Unique names enforced:** `Project.name` is now `unique=True` ([models.py](file:///src/ai_qa/db/models.py#L59)) with a backing Alembic migration ([f3a9c8b21d47](file:///alembic/versions/f3a9c8b21d47_enforce_unique_project_name_and_required_confluence.py)), and `create_project` does an explicit duplicate pre-check → `409 "Project name already exists"` (with `IntegrityError` as a defensive fallback). Covered by [test_admin_cannot_create_project_with_duplicate_name](file:///tests/api/test_admin_rbac_api.py).
  - [x] **`confluence_base_url` required at the DB layer too:** the column is now `nullable=False` (with `default=""` so existing ORM-only test fixtures still construct). The migration backfills any legacy `NULL` to `""` before the `NOT NULL` alter.
- [ ] Task 3: Verify admin project rename consistency (AC: 3)
  - [x] [update_project](file:///src/ai_qa/api/admin.py#L270-L297) updates `name`/`description`/`confluence_base_url`, returns `404` for a missing project, rejects blank names `422`, and now rejects renaming to another project's name with `409` (own-name keep allowed). Covered by [test_admin_can_update_and_delete_project](file:///tests/api/test_admin_rbac_api.py) + [test_admin_cannot_rename_project_to_existing_name](file:///tests/api/test_admin_rbac_api.py).
  - [ ] Confirm the renamed name propagates to user/membership views: the admin user cards read `project_name` from [AdminUserProjectMembershipResponse](file:///src/ai_qa/api/admin.py#L43-L51), and the dashboard calls `reloadProjects()` + `loadUsers()` after edit ([handleEditProject](file:///frontend/src/components/admin/AdminDashboard.tsx#L164-L192)).
- [ ] Task 4: Verify project delete + cross-user accessibility (AC: 4)
  - [ ] Confirm [delete_project](file:///src/ai_qa/api/admin.py#L288-L307) purges `ProjectMembership` rows then the `Project`, returns `204`, and `404` on a second delete. Memberships also cascade via `ON DELETE CASCADE` ([models.py](file:///src/ai_qa/db/models.py#L83-L85)) — the explicit purge keeps SQLite (no FK enforcement by default) consistent. Covered by [test_admin_can_update_and_delete_project](file:///tests/api/test_admin_rbac_api.py#L333-L374).
  - [ ] Add the AC4 cross-user assertion (the genuine gap): after an admin deletes a project a member was assigned to, that member's [GET /api/projects](file:///src/ai_qa/api/projects.py#L100-L111) no longer lists it. Add this as a focused backend API test in [test_project_api.py](file:///tests/test_project_api.py) (or `test_admin_rbac_api.py` if the project-list fixtures live there) — assign a standard user, confirm the project is listed, delete it, confirm it is gone.
- [ ] Task 5: Verify RBAC denials are secret-free (AC: 5)
  - [ ] Confirm standard→`403` and anonymous→`401` for create/update/delete with only a `{"detail": ...}` body. Update/delete denials are covered by [test_standard_user_cannot_update_or_delete_project](file:///tests/api/test_admin_rbac_api.py#L377-L397); create denial by [test_admin_can_create_project_and_standard_user_cannot](file:///tests/api/test_admin_rbac_api.py#L210-L241). If an anonymous-create (`401`) assertion is missing, add one focused case mirroring the 8.1 denial-matrix style. Do NOT duplicate the existing 8.1 membership denial matrix.
- [ ] Task 6: Frontend unit coverage for the project lifecycle (AC: 2, 3, 4)
  - [ ] The existing [AdminDashboard.test.tsx "manages projects, users, and per-user memberships"](file:///frontend/src/components/admin/AdminDashboard.test.tsx#L93-L291) already exercises create (`POST`), edit (`PUT`), and delete (`DELETE`) via mocked fetch. Verify it asserts the user-visible outcomes (success status text and that the correct method/URL was called). If create-error surfacing is untested, add a focused Vitest case where `POST /api/admin/projects` fails (e.g. `409`/`422`) and assert the red banner shows the safe message via [getSafeApiErrorMessage](file:///frontend/src/lib/api.ts) with no false "Project created successfully".
- [ ] Task 7: Consolidated E2E coverage for Story 8.3 (AC: 1, 2, 3, 4)
  - [ ] Add `frontend/e2e/story-8-3-admin-project-management.spec.ts` mirroring the helpers/structure of [story-8-1-admin-routing.spec.ts](file:///frontend/e2e/story-8-1-admin-routing.spec.ts) (`ensureAdminToken`, `createAdminProject`, the `userFactory` fixture, the `ADMIN_DASHBOARD_E2E` skip guard, and `afterEach` admin-token cleanup).
  - [ ] AC1/AC2/AC3 case: admin logs in → fills Create Project (Project name + **Confluence Base URL is required**) → "Create project" → the project appears in the Projects list → click Edit → rename → Save → the new name shows in the list.
  - [ ] AC4 case: admin deletes a project → it disappears from the Projects list. For the cross-user clause, seed a standard user + membership via the real admin API, delete the project, then assert via the API (or by logging in as that user) that `GET /api/projects` no longer returns it.
  - [ ] **No-mocking + cleanup (project-context.md):** prepare state via real API calls; clean up every created project/user in `afterEach` with an admin token. Do NOT copy 8-6's `page.route` mock pattern.
- [ ] Task 8: Validation gate (project-context.md Verification Workflow)
  - [ ] Backend (only if Python changed): `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run pytest`. (No schema change expected unless the AC2 Open Question forces a migration → then run `uv run alembic upgrade head`.)
  - [ ] Frontend: `npm run lint`, `npm run typecheck`, `npm run test` for `AdminDashboard.test.tsx`.
  - [ ] E2E: live-stack run `npx playwright test e2e/story-8-3-admin-project-management.spec.ts` (backend :8000 + dev server) per the 3-terminal workflow.

## Dev Notes

- **The endpoints already exist and are correct — this is a coverage story.** `POST/PUT/DELETE /api/admin/projects` live in [admin.py](file:///src/ai_qa/api/admin.py#L242-L307); admin project listing is `GET /api/projects` (admins get all projects) in [projects.py](file:///src/ai_qa/api/projects.py#L100-L111). The dashboard UI (Projects list, Create Project, inline Edit, Delete) is in [AdminDashboard.tsx](file:///frontend/src/components/admin/AdminDashboard.tsx#L410-L628). The dev job is to verify against the ACs and add the missing AC4 cross-user test + a consolidated e2e, not to re-implement.
- **No `GET /api/admin/projects` exists — and none is needed.** AC1 "list projects" is satisfied by `GET /api/projects`, which for admins returns every project with `membership_count` + `memberships[]` + timestamps. Do not invent a new admin listing endpoint or you will create a duplicate, divergent code path.
- **`confluence_base_url` is REQUIRED to create/update a project — now at both layers.** [ProjectCreateRequest](file:///src/ai_qa/api/admin.py#L69-L92) declares `confluence_base_url: str = Field(min_length=1, ...)` (API → `422`), and the DB column is now `nullable=False` ([models.py](file:///src/ai_qa/db/models.py#L61)). Every test and the e2e MUST supply it. The UI marks it required (`Confluence Base URL *`, [input](file:///frontend/src/components/admin/AdminDashboard.tsx#L603-L617)).
- **Project names are UNIQUE (LOCKED + implemented).** `Project.name` is `unique=True` ([models.py](file:///src/ai_qa/db/models.py#L59)); migration [f3a9c8b21d47](file:///alembic/versions/f3a9c8b21d47_enforce_unique_project_name_and_required_confluence.py) adds the `uq_projects_name` constraint and aborts cleanly if pre-existing duplicates exist. `create_project`/`update_project` do an explicit `select` pre-check returning `409 "Project name already exists"` (mirrors the `create_user` email pattern), with `IntegrityError` kept as a race-safe fallback. The frontend banner shows the generic safe fallback for `409` (it maps to `kind="server"`), not the raw detail.
- **Delete is safe re: related rows.** `ProjectMembership`, `Artifact`, `AuditEvent`, and `Thread` all FK `projects.id` with `ON DELETE CASCADE` ([models.py](file:///src/ai_qa/db/models.py#L83-L85), [threads/models.py L24-26](file:///src/ai_qa/threads/models.py#L24-L26)). `delete_project` also explicitly purges memberships first, which matters for SQLite tests (SQLite does not enforce FKs by default). Don't add a confirmation dialog — per UX-DR11 the product uses no confirmation dialogs; delete is a direct action.
- **Do not regress 8.1 / 8.2.** Story 8.1 owns the admin routing fork + the RBAC denial-body guarantees (only `{"detail": ...}`) that 8.3 AC5 leans on; 8.2 owns user management. If you touch `admin.py` or `AdminDashboard.tsx`, re-run the 8.1 backend RBAC tests, the 8.2 user tests, and the `AdminDashboard.test.tsx` suite.

### Project Structure Notes

- Admin project endpoints + schemas live in [admin.py](file:///src/ai_qa/api/admin.py); user-facing project listing + `require_project_member_or_admin` in [projects.py](file:///src/ai_qa/api/projects.py); role constants in [service.py](file:///src/ai_qa/auth/service.py#L13-L14); ORM in [models.py](file:///src/ai_qa/db/models.py#L54-L92).
- Admin UI: [AdminDashboard.tsx](file:///frontend/src/components/admin/AdminDashboard.tsx) — Projects list at L410-562, Create Project form at L564-628 (`#create-project-button` at L619), inline Edit form at L425-501, Delete button at L519-528. API client `createAdminProject`/`updateAdminProject`/`deleteAdminProject` in [projects.ts](file:///frontend/src/lib/projects.ts#L33-L59). Types `AdminProject`/`CreateProjectRequest` in `frontend/src/types/project.ts`.
- Backend tests: [tests/api/test_admin_rbac_api.py](file:///tests/api/test_admin_rbac_api.py) (in-memory SQLite via `StaticPool`, `engine.dispose()` teardown) and [tests/test_project_api.py](file:///tests/test_project_api.py) (project listing). Frontend unit: [AdminDashboard.test.tsx](file:///frontend/src/components/admin/AdminDashboard.test.tsx) (Vitest/jsdom, `fetch` spy). E2E: `frontend/e2e/*.spec.ts` (Playwright, real backend) using `frontend/support/fixtures`.

### Testing Standards (from project-context.md)

- **E2E no-mocking + cleanup:** hit the real backend; bootstrap state via real API calls (`ensureAdminToken`, then admin `POST /api/admin/projects` / `POST /api/admin/users`); clean up every created project and user in `afterEach` with an admin token (delete projects before users — project delete cascades memberships). The 8-6 `page.route` mock is a narrow self-trigger-loop exception — do not copy it.
- **Backend SQLite:** dispose the engine in teardown; annotate `yield` fixtures as `Generator[...]`; narrow `client.app` with `cast(FastAPI, client.app)` before `dependency_overrides`/`state`; wrap selective `create_all(tables=...)` with `cast(list[Table], [...])`. The `admin_client` fixture in `test_admin_rbac_api.py` already creates `User`, `Project`, and `ProjectMembership` tables — if a cross-user delete test needs the project-list endpoint, reuse that fixture or the `test_project_api.py` fixture rather than inventing a new one.
- **TS strictness:** `npm run typecheck` enforces `noUnusedLocals`/`noUnusedParameters` — remove any unused Playwright helper you add. If you no longer read a caught response's `.json()`, delete the variable (ts6133).
- **Lint/type gates mandatory:** backend ruff + ruff format + mypy (only if Python changes); frontend lint + typecheck; markdown diagnostics for this file (MD032: blank lines around lists).
- **Playwright env noise** (`DEP0205`, dotenv banner) is benign/suppressed; keep `timeout: 60*1000` in `playwright.config.ts` (do not shrink — slow-mo adds per-action cost).
- **Assertion-label drift:** match the rendered labels exactly — `Project name`, `Description`, `Confluence Base URL *`, the `Create project` submit button, per-card `Edit {name}` / `Delete {name}` aria-labels ([AdminDashboard.tsx L515-525](file:///frontend/src/components/admin/AdminDashboard.tsx#L515-L525)), and the inline `Save`/`Cancel` buttons.

### Previous Story Intelligence

From 8-2 (Admin User Management), 8-1 (Admin Routing), and 6-4 (Project/Membership API):
- 8-1/8-2 established the **verification-story pattern**: confirm pre-existing impl, add only the focused test gap + a consolidated `story-8-X-*.spec.ts`, reuse 7-7/8-1 helpers (`ensureAdminToken`, `createAdminProject`, `userFactory`) and the 8-6 `ADMIN_DASHBOARD_E2E` skip guard verbatim. Follow it here.
- 8-1 added a backend denial-matrix test asserting bodies equal exactly `{"detail": ...}`. 8.3 AC5 rides the same `require_admin` layer — reuse, don't duplicate, that matrix.
- 6-4 delivered `GET /api/projects` with admin all-project visibility + membership summaries and `require_project_member_or_admin`, with tests in `test_project_api.py`. AC1/AC4's "accessible list" semantics are this endpoint — build the cross-user delete assertion on top of it.
- 8-2's `getSafeApiErrorMessage` finding: a `409` maps to `kind="server"` in [api.ts](file:///frontend/src/lib/api.ts) → the banner shows the generic safe fallback, not the raw backend `detail`. If you add a project-create error test, assert the safe fallback, not the literal backend string.
- **`8-3-admin-project-management` is missing from `sprint-status.yaml`** (epic-8 lists `8-1`, `8-2`, `8-6`, `8-7`), exactly as `8-1`/`8-2` were. This story creation adds it and sets it `ready-for-dev`.

### Git Intelligence

- Baseline commit: `42c9acf` ("story 8-2 test OK"). Recent: `132d2c1` (8-2 code+test), `7835943` (8-1 code+test). The project endpoints, schemas, API client, and dashboard CRUD UI are already committed and green. 8.3 ideally adds **no runtime code** — verification + the AC4 cross-user backend test + a consolidated e2e spec. If the AC2 duplicate-name Open Question is resolved as "enforce uniqueness," that is a backend + migration change to scope narrowly and flag in the Dev Agent Record.

### Latest Tech Information

- Backend: Python 3.12+, FastAPI with `Depends(require_admin)` RBAC; Pydantic v2 `Field`/`field_validator` for `ProjectCreateRequest`/`ProjectUpdateRequest` (name trim + blank rejection, required `confluence_base_url`). `422` (validation) vs `403`/`401` (authorization) split is deliberate. SQLAlchemy 2.x ORM with `ON DELETE CASCADE` on project-scoped FKs.
- Frontend: React 18 + TypeScript + Vite, Vitest + Testing Library (unit), Playwright (e2e). Project list state comes from the `useProject` context (`reloadProjects`); error surfacing goes through `getSafeApiErrorMessage` → red banner via `addError`.

### References

- [Epic 8: Admin Dashboard and Project Membership Management](file:///_bmad-output/planning-artifacts/epics.md#L428-L432)
- [Story 8.3 definition](file:///_bmad-output/planning-artifacts/epics.md#L483-L507)
- [create_project (AC2)](file:///src/ai_qa/api/admin.py#L242-L262)
- [update_project (AC3)](file:///src/ai_qa/api/admin.py#L265-L285)
- [delete_project (AC4)](file:///src/ai_qa/api/admin.py#L288-L307)
- [ProjectCreateRequest / ProjectUpdateRequest / AdminProjectResponse schemas](file:///src/ai_qa/api/admin.py#L69-L137)
- [list_projects (admin all-projects, AC1/AC4)](file:///src/ai_qa/api/projects.py#L100-L111)
- [ProjectResponse schema](file:///src/ai_qa/api/projects.py#L36-L48)
- [Project / ProjectMembership models (no name unique constraint; cascade)](file:///src/ai_qa/db/models.py#L54-L92)
- [Create Project + list + inline edit/delete UI](file:///frontend/src/components/admin/AdminDashboard.tsx#L410-L628)
- [handleCreateProject / handleEditProject / handleDeleteProject](file:///frontend/src/components/admin/AdminDashboard.tsx#L95-L208)
- [createAdminProject / updateAdminProject / deleteAdminProject API client](file:///frontend/src/lib/projects.ts#L33-L59)
- [Backend: create + standard-denied + blank-422](file:///tests/api/test_admin_rbac_api.py#L210-L241)
- [Backend: update + delete + blank-422 + 404](file:///tests/api/test_admin_rbac_api.py#L333-L374)
- [Backend: standard cannot update/delete (403)](file:///tests/api/test_admin_rbac_api.py#L377-L397)
- [Frontend: manages projects, users, memberships](file:///frontend/src/components/admin/AdminDashboard.test.tsx#L93-L291)
- [Story 8-1 e2e (helpers to reuse)](file:///frontend/e2e/story-8-1-admin-routing.spec.ts#L62-L135)
- [project-context.md (testing + verification rules)](file:///project-context.md)

### Resolved Decisions

> [!NOTE]
> **AC2 duplicate-name question — RESOLVED (2026-06-06): enforce uniqueness (former reading 2).** The product wants unique project names. Implemented as `unique=True` on `Project.name` + migration `f3a9c8b21d47` + explicit `409` pre-checks in `create_project`/`update_project` + backend tests. The migration guards against pre-existing duplicate data by aborting with a clear error listing the offending names — **if `alembic upgrade head` fails on a populated DB, dedupe project names first, then re-run.**
> **Required Confluence URL — RESOLVED: enforced at the DB layer too** (`nullable=False`, with legacy `NULL` backfilled to `""` and a `default=""` for ORM-only test fixtures).

> [!NOTE]
> **AC1/AC4 "accessible/assignable list" endpoint.** The admin Projects panel and the "accessible projects" for a standard user both resolve through `GET /api/projects` (admins → all; standard → memberships only). There is no separate admin listing endpoint. The AC4 cross-user clause ("affected standard users no longer see the deleted project") is therefore an assertion on that user's `GET /api/projects` after deletion — confirm this interpretation is acceptable rather than expecting a dedicated admin "assignable list" endpoint.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (Thinking)

### Debug Log References

- Generated via bmad-create-story workflow.

### Completion Notes List

- Story drafted from epics.md Story 8.3 plus exhaustive code analysis of the admin project endpoints ([admin.py](file:///src/ai_qa/api/admin.py)), the project-listing endpoint ([projects.py](file:///src/ai_qa/api/projects.py)), the ORM models, the AdminDashboard Projects/Create/Edit/Delete UI, the API client ([projects.ts](file:///frontend/src/lib/projects.ts)), and existing coverage in `test_admin_rbac_api.py`, `test_project_api.py`, and `AdminDashboard.test.tsx`.
- **Backend implementation of the LOCKED decisions is complete (2026-06-06):**
  - `Project.name` → `unique=True`; `confluence_base_url` → `nullable=False, default=""` ([models.py](file:///src/ai_qa/db/models.py#L59-L61)).
  - New migration [f3a9c8b21d47](file:///alembic/versions/f3a9c8b21d47_enforce_unique_project_name_and_required_confluence.py): duplicate-name guard, `NULL` → `""` backfill, `NOT NULL` alter, `uq_projects_name`. Applied to the dev DB (`alembic current` → `f3a9c8b21d47 (head)`).
  - `create_project` + `update_project` gained explicit duplicate-name `409` pre-checks ([admin.py](file:///src/ai_qa/api/admin.py#L242-L297)).
  - Backend tests added: `test_admin_create_project_requires_confluence_base_url`, `test_admin_cannot_create_project_with_duplicate_name`, `test_admin_cannot_rename_project_to_existing_name` in [test_admin_rbac_api.py](file:///tests/api/test_admin_rbac_api.py).
  - Verified: `ruff check`, `ruff format`, `mypy src` clean; full `pytest` = **639 passed, 2 skipped** (no fixture broke from the `NOT NULL`/`unique` change).
- **Remaining (for dev-story):** AC4 cross-user backend assertion, frontend unit test for project-create error surfacing, and the consolidated `story-8-3-admin-project-management.spec.ts` e2e. Frontend types/UI already require `confluence_base_url` and need no change.
- **Note:** `8-3-admin-project-management` was missing from `sprint-status.yaml`; added and set to `ready-for-dev`.

### File List

_(to be completed by dev-story)_

## Change Log

| Date | Version | Description | Author |
| --- | --- | --- | --- |
| 2026-06-06 | 0.1 | Story drafted: verification of existing admin project create/rename/delete/list endpoints + UI, AC4 cross-user-accessibility test-gap closure, consolidated 8-3 e2e spec, AC2 duplicate-name Open Question (no unique constraint on `Project.name`). Added missing `8-3` entry to sprint-status. Status → ready-for-dev. | Bob (SM) |
| 2026-06-06 | 0.2 | Product decisions locked: unique project names + required Confluence URL. Backend implemented — `Project.name` unique, `confluence_base_url` NOT NULL, migration `f3a9c8b21d47`, `409` pre-checks in create/update, 3 new backend tests. Full suite green (639 passed). ACs 2/3 updated; Open Question resolved. | Agent |
