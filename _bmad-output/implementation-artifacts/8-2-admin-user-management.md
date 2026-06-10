---
baseline_commit: "7835943"
---
# Story 8.2: Admin User Management

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> [!IMPORTANT]
> **This is primarily a verification + test-coverage story, not a greenfield build.** The admin user-list (`GET /api/admin/users`) and admin user-create (`POST /api/admin/users`) endpoints, the secret-free `AdminUserResponse` schema, password hashing, duplicate rejection, and the AdminDashboard "Users Management" list + "Create User" form all already exist (built in 2-2, refined by 6-8/6-9). Story 8.2 formally owns AC1–AC3, hardens them as regression guards, and closes the genuine gaps: **(a)** a frontend test that AC2's duplicate-email rejection surfaces a safe error in the UI, and **(b)** a consolidated live-stack e2e spec for admin user management. Do NOT rebuild the endpoints or the form — verify, then add the missing focused tests. **Also resolve the AC3 Open Question below before writing tests** (public `/auth/register` endpoint vs. "user creation available only to admins").

## Story

As an admin,
I want to view and create local user accounts,
so that I can control who can access the AI QA Automation system.

## Acceptance Criteria

1. **Given** an authenticated admin opens user management
   **When** the frontend requests the user list (`GET /api/admin/users`)
   **Then** the backend returns users with `id`, `email`, `display_name`, `role`, `is_active` (status), and `project_memberships`
   **And** password hashes and secret values are never returned.

2. **Given** an authenticated admin submits a new user with `email`, `display_name`, `role`, and `initial_password`
   **When** the backend validates the request
   **Then** a user is created with the password stored only as a secure hash (never echoed back)
   **And** duplicate emails are rejected with a safe validation message (`409 "User already exists"`), which the dashboard surfaces to the admin without leaking internals.

3. **Given** the user management screen is displayed
   **When** the admin views available actions
   **Then** self-service registration is not shown in the authenticated UI
   **And** user creation is available only to admins (standard/anonymous callers to `POST /api/admin/users` are rejected `403`/`401`).

## Tasks / Subtasks

- [x] Task 1: Verify the admin user-list endpoint returns secret-free, complete user records (AC: 1)
  - [x] Confirm [list_users](file:///src/ai_qa/api/admin.py#L184-L191) returns `list[AdminUserResponse]` and that [AdminUserResponse](file:///src/ai_qa/api/admin.py#L54-L66) exposes exactly `id`, `email`, `display_name`, `role`, `is_active`, `created_at`, `updated_at`, `project_memberships` — and NO `password_hash`/secret fields. Keep this schema; do not add fields.
  - [x] Confirm `project_memberships` items use [AdminUserProjectMembershipResponse](file:///src/ai_qa/api/admin.py#L43-L51) (`project_name`, `role`, no `user_id`/secret leakage). The existing test [test_admin_can_list_users_with_safe_project_memberships](file:///tests/api/test_admin_rbac_api.py#L159-L193) already locks this — keep it green.
- [x] Task 2: Verify admin user-create with secure hashing + duplicate rejection (AC: 2)
  - [x] Confirm [create_user](file:///src/ai_qa/api/admin.py#L194-L221) hashes via [hash_password](file:///src/ai_qa/auth/password.py), creates `is_active=True`, rejects pre-existing email with `409 "User already exists"`, and also catches `IntegrityError`/`DuplicateUserError` → `409`. Confirm [AdminUserCreateRequest](file:///src/ai_qa/api/admin.py#L99-L123) enforces `initial_password` min_length 8 and `role ∈ {"admin","standard"}` (Literal). These are covered by [test_admin_can_create_user_with_approved_role_without_leaking_password_hash](file:///tests/api/test_admin_rbac_api.py#L400-L457) (create + 409 duplicate + 422 short-password + 422 invalid-role + no `password_hash` in body). Keep green; do NOT change the endpoint.
- [x] Task 3: Close the AC2 frontend gap — duplicate-email error is shown safely in the dashboard (AC: 2)
  - [x] [handleCreateUser](file:///frontend/src/components/admin/AdminDashboard.tsx#L125-L148) calls `createAdminUser(...)` and on failure runs `addError(getSafeApiErrorMessage(err))`. The existing dashboard test only mocks the **success** path. Add a Vitest case to [AdminDashboard.test.tsx](file:///frontend/src/components/admin/AdminDashboard.test.tsx) where `POST /api/admin/users` returns `409 {"detail":"User already exists"}`, then assert the red error banner shows the safe message and that the form did not falsely report success (no "User created successfully").
  - [x] Verify [getSafeApiErrorMessage](file:///frontend/src/lib/api.ts#L138) returns the backend `detail` (or a safe fallback) — assert against whatever it actually renders for a 409; do not change the helper unless the rendered text leaks internals.
- [x] Task 4: Verify AC3 — no self-service registration in the authenticated UI + admin-only creation (AC: 3)
  - [x] Confirm the authenticated admin UI shows no registration affordance: the dashboard test already asserts `queryByText(/register/i)` is absent and the "Sync existing company's users" button is `disabled` with the "not available… please add manually" help text ([AdminDashboard.test.tsx](file:///frontend/src/components/admin/AdminDashboard.test.tsx#L197-L251)). Keep these.
  - [x] Confirm [LoginPage.tsx](file:///frontend/src/components/auth/LoginPage.tsx) exposes login only (no sign-up / create-account link). If a registration affordance exists, flag it — current scope assumes login-only.
  - [x] Confirm `POST /api/admin/users` is `AdminDependency`-guarded so standard→403 and anonymous→401, with denial bodies carrying only `detail` (covered by [test_standard_user_cannot_create_or_delete_user](file:///tests/api/test_admin_rbac_api.py#L506-L526)). **AC3 Open Question resolved:** story `8-7-lock-down-public-self-service-registration-endpoint` exists in sprint-status (backlog) — AC3 is UI-only for 8.2.
- [x] Task 5: Consolidated E2E coverage for Story 8.2 (AC: 1, 2)
  - [x] Add `frontend/e2e/story-8-2-admin-user-management.spec.ts` mirroring the helpers in [story-8-1-admin-routing.spec.ts](file:///frontend/e2e/story-8-1-admin-routing.spec.ts) (`ensureAdminToken`, `userFactory` cleanup) and the 8-6 `ADMIN_DASHBOARD_E2E` skip guard.
  - [x] AC1/AC2 case: admin logs in → opens dashboard → fills the Create User form (Email, Display Name, Role, Initial Password) → clicks "Create user" → the new user appears in the Users Management list with correct role/status.
  - [x] AC2 duplicate case: submitting the same email again surfaces the safe error banner and creates no second user.
  - [x] **No-mocking + cleanup (project-context.md):** prepare state via real API calls; clean up every created user in `afterEach` with an admin token. Do NOT copy 8-6's `page.route` mock pattern.
- [x] Task 6: Validation gate (project-context.md Verification Workflow)
  - [x] Backend (only if Python changed): `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run pytest`. (No schema change expected → skip `alembic upgrade head`.)
  - [x] Frontend: `npm run lint`, `npm run typecheck`, `npm run test` for `AdminDashboard.test.tsx`.
  - [x] E2E: live-stack run `npx playwright test e2e/story-8-2-admin-user-management.spec.ts` (backend :8000 + dev server) per the 3-terminal workflow.

## Dev Notes

- **The endpoints already exist and are correct — this is a coverage story.** `GET/POST /api/admin/users` were built in Story 2.2 and the AdminDashboard UI was elevated to a full page in 6-8/6-9. The dev job is to verify against the ACs and add the two missing tests (AC2 duplicate-in-UI + consolidated e2e), not to re-implement.
- **Backend duplicate handling is layered.** [create_user](file:///src/ai_qa/api/admin.py#L194-L221) pre-checks `get_user_by_email` → `409`, AND catches `IntegrityError`/`DuplicateUserError` on commit → `409`. The detail string is the literal `"User already exists"`. The frontend must show this (or a safe equivalent) — never a stack trace or raw DB error.
- **Role is a closed set, case-sensitive on the backend.** `AdminUserCreateRequest.role` is `Literal["admin","standard"]` → invalid roles 422 at the schema. The frontend `<select id="create-user-role">` offers exactly `standard`/`admin`. Do not introduce a free-text role input.
- **Password is write-only.** `initial_password` (min 8) is hashed via `hash_password`; `AdminUserResponse` has no password field, so the create response and the list both omit it. The frontend password input is `type="password"` and is cleared after a successful create ([handleCreateUser](file:///frontend/src/components/admin/AdminDashboard.tsx#L137-L141)).
- **AC1 status field = `is_active`.** The epic says "status"; the model/response field is `is_active` (bool), rendered as the active/inactive badge in the user card. Treat `is_active` as the canonical "status".
- **Do not regress 8.1.** Story 8.1 owns the admin routing fork + the admin-RBAC denial-body guarantees that 8.2 AC3 leans on. If you touch `admin.py` or `AdminDashboard.tsx`, re-run the 8.1 backend RBAC tests and the App.test.tsx admin case.

### Project Structure Notes

- Admin user endpoints + schemas live in [admin.py](file:///src/ai_qa/api/admin.py); role constants in [service.py](file:///src/ai_qa/auth/service.py#L13-L14); password hashing in `src/ai_qa/auth/password.py`.
- Admin UI: [AdminDashboard.tsx](file:///frontend/src/components/admin/AdminDashboard.tsx) ("Users Management" list at L633-769; "Create User" form at L771-874). API client helpers `listAdminUsers`/`createAdminUser` in [projects.ts](file:///frontend/src/lib/projects.ts#L20-L31). Types `AdminUser`/`CreateAdminUserRequest` in `frontend/src/types/project.ts`.
- Backend tests: [tests/api/test_admin_rbac_api.py](file:///tests/api/test_admin_rbac_api.py) (in-memory SQLite via `StaticPool`, `engine.dispose()` teardown). Frontend unit: [AdminDashboard.test.tsx](file:///frontend/src/components/admin/AdminDashboard.test.tsx) (Vitest/jsdom, `fetch` spy). E2E: `frontend/e2e/*.spec.ts` (Playwright, real backend) using `frontend/support/fixtures`.

### Testing Standards (from project-context.md)

- **E2E no-mocking + cleanup:** hit the real backend; bootstrap state via real API calls (`ensureAdminToken`, then the admin `POST /admin/users`); clean up every created user in `afterEach` with an admin token. The 8-6 `page.route` mock is a narrow self-trigger-loop exception — do not copy it for 8.2.
- **Backend SQLite:** dispose the engine in teardown; annotate `yield` fixtures as `Generator[...]`; narrow `client.app` with `cast(FastAPI, client.app)` before `dependency_overrides`/`state`; wrap selective `create_all(tables=...)` with `cast(list[Table], [...])`.
- **TS strictness:** `npm run typecheck` enforces `noUnusedLocals`/`noUnusedParameters` — remove any unused Playwright helper you add. If you no longer read a caught response's `.json()`, delete the variable (ts6133).
- **Lint/type gates mandatory:** backend ruff + ruff format + mypy (only if Python changes); frontend lint + typecheck; markdown diagnostics for this file.
- **Playwright env noise** (`DEP0205`, dotenv banner) is benign/suppressed; keep `timeout: 60*1000` in `playwright.config.ts` (do not shrink — slow-mo adds per-action cost).
- **Assertion-label drift:** match `getByRole("button", { name: /create user/i })` and the `Email`/`Display Name`/`Role`/`Initial Password` labels exactly as rendered.

### Previous Story Intelligence

From 8-1 (Admin Routing) and 6-8/6-9 (Admin Dashboard):
- 8-1 established the verification-story pattern: confirm pre-existing impl, add only the focused test gap + a consolidated `story-8-X-*.spec.ts`, reuse 7-7 helpers (`ensureAdminToken`, `userFactory`) and the 8-6 `ADMIN_DASHBOARD_E2E` skip guard verbatim.
- 8-1 added a backend denial-matrix test asserting bodies equal exactly `{"detail": ...}`. 8.2's AC3 denial guarantees ride on the same `require_admin` layer — reuse, don't duplicate, that backend matrix.
- 6-8/6-9 made `AdminDashboard` a full page; the stable assertion target is the "Admin Dashboard" heading and the "Users Management" / "Create User" section headers.
- `8-2-admin-user-management` is **missing from `sprint-status.yaml`** (epic-8 lists only `8-1` and `8-6`), exactly as `8-1` was. This story creation adds it and sets it `ready-for-dev`.

### Git Intelligence

- Baseline commit: `7835943` ("story 8-1 code and test OK"). Recent: `d4f825f` (admin create-thread fix), `7d43f84`/`6cb3e09` (7-7). The admin user endpoints, schema, and dashboard form are already committed and green. 8.2 ideally adds **no runtime code** — verification + the AC2 duplicate-in-UI Vitest case + a consolidated e2e spec. If a genuine AC gap surfaces (e.g. the AC3 register question forces a backend change), scope it narrowly and flag it in the Dev Agent Record.

### Latest Tech Information

- Backend: Python 3.12+, FastAPI with `Depends(require_admin)` RBAC; Pydantic v2 `Field`/`field_validator` for `AdminUserCreateRequest` validation (min_length, Literal role, email normalization). 409 (duplicate) vs 422 (validation) split is deliberate.
- Frontend: React 18 + TypeScript + Vite, Vitest + Testing Library (unit), Playwright (e2e). Error surfacing goes through `getSafeApiErrorMessage` → red banner via `addError`.

### References

- [Epic 8: Admin Dashboard and Project Membership Management](file:///_bmad-output/planning-artifacts/epics.md#L428-L432)
- [Story 8.2 definition](file:///_bmad-output/planning-artifacts/epics.md#L460-L481)
- [list_users (AC1)](file:///src/ai_qa/api/admin.py#L184-L191)
- [create_user + duplicate 409 (AC2)](file:///src/ai_qa/api/admin.py#L194-L221)
- [AdminUserResponse / AdminUserCreateRequest schemas](file:///src/ai_qa/api/admin.py#L43-L123)
- [Create User form (AC2/AC3 UI)](file:///frontend/src/components/admin/AdminDashboard.tsx#L771-L874)
- [handleCreateUser (error surfacing)](file:///frontend/src/components/admin/AdminDashboard.tsx#L125-L148)
- [Backend user tests (list/create/duplicate/RBAC)](file:///tests/api/test_admin_rbac_api.py#L159-L207)
- [Backend create-user test (409 + 422 + no hash)](file:///tests/api/test_admin_rbac_api.py#L400-L457)
- [Standard user cannot create/delete user](file:///tests/api/test_admin_rbac_api.py#L506-L526)
- [Dashboard test: create-user POST + sync disabled + no register](file:///frontend/src/components/admin/AdminDashboard.test.tsx#L197-L251)
- [Public /auth/register endpoint (AC3 tension)](file:///src/ai_qa/api/auth/local.py#L83-L99)
- [PUBLIC_PATHS includes /auth/register](file:///src/ai_qa/api/auth/middleware.py#L29-L46)
- [Story 8-1 e2e (helpers to reuse)](file:///frontend/e2e/story-8-1-admin-routing.spec.ts#L35-L94)

### Open Questions

> [!IMPORTANT]
> **AC3 vs. the public `/auth/register` endpoint — resolve before writing tests.** AC3 says "self-service registration is not shown" and "user creation available only to admins." The authenticated **UI** satisfies this (no register affordance; creation is admin-only via `POST /api/admin/users`). **However, a public, unauthenticated `POST /auth/register` endpoint exists** ([local.py L83-99](file:///src/ai_qa/api/auth/local.py#L83-L99)) and is whitelisted in `PUBLIC_PATHS` — it creates standard users with no admin auth, and **every Epic 7 e2e spec depends on it** (`registerStandardUser` → `POST /auth/register`) to bootstrap test users. Two readings:
> 1. **AC3 is UI-only** (current assumption): the requirement is satisfied because the product UI never offers self-service signup; the register API is an internal test/bootstrap affordance. → No runtime change; just verify the UI and admin-only `POST /admin/users` guard, and document the endpoint's intended scope.
> 2. **AC3 requires the API locked down**: the register endpoint should be removed/gated (e.g. admin-only or disabled in production). → This is a **breaking change** for all Epic 7 e2e specs and must be scoped separately (new story or explicit approval), with a replacement test-bootstrap path (e.g. seed via admin token).
>
> Recommend **reading 1** for 8.2 (matches how FR16/6-8/7-7 shipped) and flagging the endpoint for a follow-up security review. Confirm before the dev locks AC3 behavior.

> [!NOTE]
> **AC2 "safe validation message" wording.** The backend returns `409 {"detail": "User already exists"}`. Confirm `getSafeApiErrorMessage` renders that (or a safe fallback) and that the existence of an email is acceptable to reveal here — unlike login (7.1), which deliberately hides whether an email exists. For an admin-only management screen, revealing "User already exists" is the intended, useful behavior; flag if the product wants it genericized.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (Thinking)

### Debug Log References

- Generated via bmad-create-story workflow.
- Implementation via bmad-dev-story workflow (Claude Opus 4.6 Thinking).

### Completion Notes List

- Story drafted from epics.md Story 8.2 plus exhaustive code analysis of the admin user endpoints ([admin.py](file:///src/ai_qa/api/admin.py)), schemas, the AdminDashboard "Users Management" + "Create User" UI, the API client ([projects.ts](file:///frontend/src/lib/projects.ts)), and existing coverage in `test_admin_rbac_api.py` and `AdminDashboard.test.tsx`.
- **Key finding:** AC1, AC2 (backend), and AC3 (UI no-register + admin-only API) are already implemented and tested. Genuine gaps: (a) no frontend test that AC2's `409` duplicate surfaces a safe UI error (existing dashboard test only mocks success), and (b) no consolidated e2e spec for admin user management. Scoped accordingly.
- **AC3 tension flagged:** a public `/auth/register` endpoint exists and is relied on by all Epic 7 e2e bootstraps — see Open Questions. Defaulting to "AC3 is UI-only" pending confirmation; locking the endpoint would be a breaking change requiring its own story.
- **Note:** `8-2-admin-user-management` was missing from `sprint-status.yaml` (epic-8 listed only `8-1` and `8-6`). This story creation adds it and sets it to `ready-for-dev`.
- ✅ **Tasks 1–4 (verification):** Confirmed all pre-existing implementations satisfy AC1–AC3. `list_users` returns secret-free `AdminUserResponse`; `create_user` hashes passwords, rejects duplicates (409), validates role/password (422); LoginPage is login-only; RBAC denials return only `{"detail": ...}`. All existing backend tests green.
- ✅ **Task 3 (AC2 frontend gap):** Added Vitest case `"surfaces a safe error when creating a duplicate user (409) and does not report success"` to `AdminDashboard.test.tsx`. Test mocks `POST /api/admin/users` → 409, asserts the red error banner shows the safe fallback message ("Something went wrong. Please try again.") via `getSafeApiErrorMessage`, no false "User created successfully", and no leaked internals (traceback/SQL).
- ✅ **Task 5 (consolidated E2E):** Created `story-8-2-admin-user-management.spec.ts` with 2 Playwright tests hitting the live stack: (1) admin creates a user via the dashboard form and it appears in the Users Management list, (2) submitting a duplicate email surfaces the safe error banner and creates no second user. No mocking; afterEach cleanup deletes created users via admin token. Uses `ADMIN_DASHBOARD_E2E` skip guard.
- ✅ **Task 6 (validation gate):** No Python changed → backend gates skipped. Frontend: `npm run lint` ✅, `npm run typecheck` ✅, Vitest 8/8 passed ✅. E2E: 2/2 passed on live stack ✅.
- **AC3 Open Question resolved:** Story `8-7-lock-down-public-self-service-registration-endpoint` exists in sprint-status (backlog) confirming reading 1 (AC3 is UI-only for 8.2).
- **AC2 safe message detail:** 409 maps to `kind="server"` in `api.ts` → `getSafeApiErrorMessage` returns the generic safe fallback, not the raw backend `detail`. No internals leaked. The helper was not changed as it already behaves safely.

### File List

- `frontend/src/components/admin/AdminDashboard.test.tsx` — Modified: added AC2 409 duplicate-email Vitest case + imported `ApiError`/`getSafeApiErrorMessage`
- `frontend/e2e/story-8-2-admin-user-management.spec.ts` — New: consolidated live-stack E2E spec (2 tests: create user, duplicate error)
- `_bmad-output/implementation-artifacts/8-2-admin-user-management.md` — Modified: task checkboxes, Dev Agent Record, File List, Change Log, Status
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — Modified: 8-2 status transitions (ready-for-dev → in-progress → review)

## Change Log

| Date | Version | Description | Author |
| --- | --- | --- | --- |
| 2026-06-06 | 0.1 | Story drafted: verification of existing admin user list/create endpoints + UI, AC2 duplicate-in-UI test-gap closure, consolidated 8-2 e2e spec, AC3 public-register Open Question. Added missing `8-2` entry to sprint-status. Status → ready-for-dev. | Bob (SM) |
| 2026-06-06 | 1.0 | Implementation complete: verified AC1-AC3 against existing code; added AC2 duplicate-email 409 Vitest case (AdminDashboard.test.tsx); created consolidated E2E spec (story-8-2-admin-user-management.spec.ts) with create-user and duplicate-error tests; all validation gates passed (lint, typecheck, Vitest 8/8, E2E 2/2). AC3 Open Question resolved (UI-only, per story 8-7 in backlog). Status → review. | Dev Agent (Claude Opus 4.6) |
| 2026-06-06 | 1.1 | Full E2E suite re-run on live stack (headed, slow-mo): 22 passed, 1 skipped (8-6 self-trigger guard). User confirmed tests OK. Status → done. | Dev Agent (Claude Opus 4.6) |
