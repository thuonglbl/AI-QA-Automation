---
baseline_commit: "d4f825f"
---
# Story 8.1: Admin Dashboard Routing and Access Control

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> [!IMPORTANT]
> **This is primarily a verification + test-coverage story, not a greenfield build.** The full routing fork (admin → dashboard, non-admin → workspace) and the backend RBAC layer (401 unauthenticated, 403 forbidden) already exist and are exercised by earlier stories (6-2, 6-3, 6-8, 6-9, 7-7). Story 8.1 formally owns these four ACs, hardens them as regression guards, and closes the one genuine coverage gap: **AC2 — a standard user navigating directly to the `/admin` URL must land in (or be redirected to) the standard workspace, never the admin dashboard.** Do NOT rebuild the routing fork or RBAC; verify, then add the missing focused tests.

## Story

As an admin,
I want to be routed directly to the admin dashboard and protected from the standard workspace flow,
so that I can manage users and projects without entering the pipeline workspace.

## Acceptance Criteria

1. **Given** an authenticated user has the admin role (`role.toLowerCase() === "admin"`)
   **When** login routing completes (`/auth/status` or `/auth/me` resolves authenticated, admin role)
   **Then** the frontend routes the user directly to the admin dashboard (`<AdminDashboard />`)
   **And** the admin does not enter Alice project selection, starter-thread bootstrap, or the standard workspace shell.

2. **Given** an authenticated standard user (any non-admin role) attempts to access the admin dashboard route (e.g. navigates directly to `/admin`)
   **When** the SPA resolves the authenticated role
   **Then** the admin dashboard is not rendered
   **And** the user remains in / is shown the standard workspace shell (or the zero-project no-access message), never `<AdminDashboard />`.

3. **Given** an unauthenticated request targets an admin API endpoint (`/api/admin/*`)
   **When** backend authorization is evaluated
   **Then** the request is rejected with `401` and detail `"Not authenticated"`
   **And** no admin-only data is returned.

4. **Given** an authenticated non-admin request targets an admin API endpoint (`/api/admin/*`)
   **When** backend authorization is evaluated
   **Then** the request is rejected with `403` and detail `"Forbidden"`
   **And** the response body exposes no admin-only data (no user list, project list, or membership data).

## Tasks / Subtasks

- [x] Task 1: Verify and harden the post-login routing fork for admins (AC: 1)
  - [x] Confirm the render-switch in [App.tsx](file:///frontend/src/App.tsx#L760-L766) returns, in order: `<LoginPage />` when `!isAuthenticated && !isLoading`; `<AdminDashboard />` when `isAuthenticated && user?.role?.toLowerCase() === "admin"`; otherwise the workspace shell. Keep this structure — no router is introduced. VERIFIED: render-switch intact at L760-766; no router added.
  - [x] Confirm the admin path short-circuits BEFORE the per-project starter-thread bootstrap effect runs (admins must never POST `/threads`). The existing `App.test.tsx` AC5 test asserts `threadMock.postCount === 0`; keep that guarantee. VERIFIED: AC5 test still passes (postCount===0).
- [x] Task 2: Close the AC2 gap — standard user cannot reach the admin dashboard via URL (AC: 2)
  - [x] The frontend is a single-page render switch with no client-side router: any path (`/`, `/admin`, deep links) loads `<App />`, which renders by role. Confirm that a standard user who navigates to `/admin` gets the workspace shell, not `<AdminDashboard />`, purely because `role !== "admin"`. VERIFIED structurally + by test.
  - [x] Add a frontend test for this: added two Vitest cases in [App.test.tsx](file:///frontend/src/App.test.tsx) using `window.history.pushState(.../admin)` — one with a single project (lands on provider step, no admin dashboard) and one with zero projects (no-access message, no admin dashboard). Also added e2e cases (Task 5).
- [x] Task 3: Verify backend RBAC 401/403 on admin endpoints (AC: 3, 4)
  - [x] Confirm [require_admin](file:///src/ai_qa/api/auth/rbac.py#L46-L52) raises `403 "Forbidden"` for non-admins and [get_current_active_user](file:///src/ai_qa/api/auth/rbac.py#L22-L40) raises `401 "Not authenticated"` for missing/expired/inactive sessions. VERIFIED.
  - [x] Confirm [AuthMiddleware](file:///src/ai_qa/api/auth/middleware.py#L101-L113) returns `401` JSON for unauthenticated `/api/*` requests, and that `/api/admin/*` is NOT in `PUBLIC_PATHS` (only the report-view sub-path is public). VERIFIED.
  - [x] Confirm every route in [admin.py](file:///src/ai_qa/api/admin.py) declares `_admin: User = AdminDependency`. VERIFIED: all 11 admin routes are AdminDependency-guarded; only `GET /tests/e2e/report/view/{file_path}` is intentionally public (whitelisted, serves report assets) — left unchanged as directed.
- [x] Task 4: Backend test coverage (AC: 3, 4)
  - [x] The 401/403 matrix is already covered in [test_admin_rbac_api.py](file:///tests/api/test_admin_rbac_api.py) and [test_admin_e2e_api.py](file:///tests/api/test_admin_e2e_api.py). Found a genuine gap: the membership endpoints (`POST`/`DELETE .../memberships`) had only happy-path coverage, no denial pair. Added `test_standard_and_unauthenticated_users_cannot_manage_memberships` mirroring the existing pattern.
  - [x] Explicitly assert the 403/401 response bodies carry no admin data — the new test asserts the full body equals exactly `{"detail": "Forbidden"}` / `{"detail": "Not authenticated"}` (AC4: no user/project/membership data leaked).
- [x] Task 5: Consolidated E2E coverage for Story 8.1 (AC: 1, 2)
  - [x] Added [story-8-1-admin-routing.spec.ts](file:///frontend/e2e/story-8-1-admin-routing.spec.ts) mirroring the 7-7 helpers (`ensureAdminToken`, `registerStandardUser`, `createAdminProject`, `assignMembership`, `userFactory` cleanup).
  - [x] AC1 case: admin logs in → admin dashboard visible, provider/chooser hidden.
  - [x] AC2 cases: a standard user logs in, then `page.goto("/admin")` → admin dashboard NOT shown, workspace shell shown (member + zero-project variants).
  - [x] Guarded against the Story 8.6 self-trigger loop via `process.env.ADMIN_DASHBOARD_E2E` skip.
- [x] Task 6: Validation gate (project-context.md Verification Workflow)
  - [x] Backend: `uv run ruff check .` (passed), `uv run ruff format --check .` (passed after formatting the new test), `uv run mypy src` (no issues), `uv run pytest` (636 passed, 2 skipped, 81.26% coverage ≥ 80% gate).
  - [x] Frontend: `npm run lint` (clean), `npm run typecheck` (clean), `npm run test` for App.test.tsx (11 passed).
  - [x] E2E: live-stack Playwright run `npx playwright test e2e/story-8-1-admin-routing.spec.ts` → 3 passed (28.5s), against backend :8000 + dev server.

## Dev Notes

- **The routing fork is a render switch, not a router.** [App.tsx L760-766](file:///frontend/src/App.tsx#L760-L766) returns `<LoginPage />` → `<AdminDashboard />` → workspace shell in that order. There is no React Router; the SPA renders purely from `isAuthenticated` + `user.role`. This is why AC2 holds structurally: a standard user can type `/admin` but the same `<App />` renders, and `role !== "admin"` falls through to the shell. The dev job for AC2 is to **prove this with a test**, not to add route guards.
- **Backend is case-sensitive, frontend is case-insensitive.** `require_admin` compares `current_user.role != ADMIN_ROLE` where `ADMIN_ROLE = "admin"` ([service.py L13-14](file:///src/ai_qa/auth/service.py#L13-L14)) — exact match. The frontend gate lowercases: `user?.role?.toLowerCase() === "admin"`. Roles are seeded as the literal `"admin"` / `"standard"`, so they agree today, but do NOT "fix" one to match the other — both are intentional and tested. Tests mock `role: "user"` (a non-admin) and `role: "admin"`.
- **Two-layer backend defense.** Unauthenticated `/api/*` is stopped at the middleware ([middleware.py L101-113](file:///src/ai_qa/api/auth/middleware.py#L101-L113)) with a `401` JSON before the route runs. Authenticated-but-non-admin is stopped at the route via `Depends(require_admin)` → `403`. `get_current_active_user` also re-checks the DB so a stale token for a now-inactive/deleted user yields `401`, not `403` (see [test_inactive_user_with_old_token_cannot_pass_rbac](file:///tests/api/test_admin_rbac_api.py#L313-L330)).
- **Admin endpoints inventory** (all under `/admin`, prefixed `/api` at mount → `/api/admin/...`, all `AdminDependency`-guarded): `GET/POST /users`, `DELETE /users/{id}`, `POST/PUT/DELETE /projects[/{id}]`, `POST/DELETE /projects/{id}/memberships[/{user_id}]`, `POST /tests/e2e`, `GET /tests/e2e/report`. The lone unguarded route is `GET /tests/e2e/report/view/{file_path:path}` (static report assets for in-browser viewing) — public by design and whitelisted in `PUBLIC_PATHS` ([middleware.py L45](file:///src/ai_qa/api/auth/middleware.py#L45)). Leave it.
- **Admins must not touch the thread/project flow (AC1).** Because the admin branch returns before the workspace shell renders, the per-project starter-thread bootstrap never runs for admins. Preserve this — the regression signal is `threadMock.postCount === 0` in the App.test.tsx admin case and "provider step hidden" in the e2e admin case.
- **Do not regress 7-7.** Story 7-7 shares this exact routing fork (its AC5 is "admin → dashboard, never the shell"). Treat 7-7's `App.test.tsx` admin test and `story-7-7-workspace-shell.spec.ts` AC5 as a shared regression guard; if you touch `App.tsx`, re-run both.

### Project Structure Notes

- Routing/admin fork and the workspace shell markup live directly in [App.tsx](file:///frontend/src/App.tsx); there is no separate `WorkspaceShell` component. Do not introduce one (avoid churn on a verification story).
- Admin UI is [AdminDashboard.tsx](file:///frontend/src/components/admin/AdminDashboard.tsx) under `frontend/src/components/admin/`.
- Backend auth lives under `src/ai_qa/api/auth/` (`rbac.py`, `middleware.py`, `local.py`, `session.py`). Admin routes are in `src/ai_qa/api/admin.py`. Role constants are in `src/ai_qa/auth/service.py`.
- Backend tests: `tests/api/test_admin_rbac_api.py`, `tests/api/test_admin_e2e_api.py` (Vitest-style in-memory SQLite via `StaticPool`, engine disposed in teardown per project-context rule). Frontend unit: `frontend/src/App.test.tsx` (Vitest/jsdom). E2E: `frontend/e2e/*.spec.ts` (Playwright, real backend) using `frontend/support/fixtures`.

### Testing Standards (from project-context.md)

- **E2E no-mocking + cleanup:** E2E must hit the real backend; prepare state via real API calls (`createAdminProject`, `assignMembership`) and clean up created users/projects in `afterEach` with an admin token. (The `page.route` mocks in 8-6 are a narrow exception to avoid the recursive E2E-trigger loop — do not copy that pattern for 8.1 routing assertions, which should use the real stack.)
- **Backend SQLite:** dispose the engine in teardown (`engine.dispose()`); annotate `yield` fixtures as `Generator[...]`; narrow `client.app` with `cast(FastAPI, client.app)` before touching `dependency_overrides`/`state`; wrap selective `create_all(tables=...)` lists with `cast(list[Table], [...])`.
- **Lint/type gates are mandatory** before finishing: backend ruff + ruff format + mypy; frontend `npm run typecheck` (strict `noUnusedLocals`/`noUnusedParameters` — remove any unused Playwright helpers); markdown diagnostics for this file.
- **Playwright env noise** (`DEP0205`, dotenv banner) is benign and already suppressed; keep `timeout: 60*1000` in `playwright.config.ts` (do not shrink — slow-mo adds per-action cost).

### Previous Story Intelligence

From 7-7 (Workspace Shell Routing) and 6-8 (Admin Routing Bugfix):
- 7-7 hardened the same render-switch and added `story-7-7-workspace-shell.spec.ts` with an AC5 admin-routing case and an `ensureAdminToken` helper — reuse these helpers verbatim for the 8.1 e2e spec.
- 6-8 elevated the old inline `AdminPanel` to a full-page `AdminDashboard` and made `App.tsx` render it directly for admins, bypassing the project picker. 6-9 refined it. The dashboard text "Admin Dashboard" is the stable assertion target (`getByText(/admin dashboard/i)`).
- `/auth/status` returns `id` + `role` (7-7 root-cause fix in [local.py](file:///src/ai_qa/api/auth/local.py)); page-reload bootstrap depends on this. Don't regress it.
- Test harness conventions: `App.test.tsx` uses hoisted `useWebSocket`/`usePipelineState` mocks + a `fetch` spy (`mockFetchForUser`); e2e specs bootstrap an admin via `ensureAdminToken`. Reuse both.

### Git Intelligence

- Baseline commit: `d4f825f` ("fix bug admin create thread"). Recent: `7d43f84`/`6cb3e09` (7-7 code, e2e, tests), `cb61b9e` (7-6). The routing fork, RBAC, and admin router are already committed and green. 8.1 ideally adds no runtime code — it is verification + the AC2 test gap + a consolidated e2e spec. If a genuine AC gap surfaces, scope it narrowly and flag it in the Dev Agent Record.

### Latest Tech Information

- Backend: Python 3.12+, FastAPI with `BaseHTTPMiddleware` auth + `Depends(require_admin)` RBAC, session-cookie/JWT (`SessionManager`). 401 vs 403 split is deliberate: middleware = unauthenticated (401), route dependency = authenticated-but-forbidden (403).
- Frontend: React 18 + TypeScript + Vite, no router (render-switch SPA), Vitest + Testing Library (unit), Playwright (e2e).

### References

- [Epic 8: Admin Dashboard and Project Membership Management](file:///_bmad-output/planning-artifacts/epics.md#L428-L432)
- [Story 8.1 definition](file:///_bmad-output/planning-artifacts/epics.md#L434-L458)
- [Routing fork: LoginPage / AdminDashboard / shell](file:///frontend/src/App.tsx#L760-L766)
- [require_admin (403) + get_current_active_user (401)](file:///src/ai_qa/api/auth/rbac.py#L22-L52)
- [AuthMiddleware unauthenticated 401 for /api/](file:///src/ai_qa/api/auth/middleware.py#L101-L113)
- [PUBLIC_PATHS (admin report-view whitelist)](file:///src/ai_qa/api/auth/middleware.py#L29-L46)
- [Admin router (all AdminDependency-guarded)](file:///src/ai_qa/api/admin.py#L184-L381)
- [Role constants ADMIN_ROLE/STANDARD_ROLE](file:///src/ai_qa/auth/service.py#L13-L14)
- [Backend RBAC tests (401/403 matrix)](file:///tests/api/test_admin_rbac_api.py#L196-L207)
- [App.test.tsx admin-routing case (AC5/AC1)](file:///frontend/src/App.test.tsx#L353-L384)
- [Story 7-7 e2e (admin routing + helpers to reuse)](file:///frontend/e2e/story-7-7-workspace-shell.spec.ts#L51-L94)
- [Story 8-6 e2e self-trigger guard pattern](file:///frontend/e2e/story-8-6-admin-e2e-execution.spec.ts#L6-L9)

### Open Questions

> [!NOTE]
> **AC2 scope is "URL navigation stays in workspace," not a hard 403 page.** Because the app is a render-switch SPA with no router, "access denied" for a standard user hitting `/admin` means the admin dashboard simply never renders and the standard shell shows instead. If the product instead wants an explicit "Access Denied" screen or a redirect to `/`, flag it — current scope assumes the structural render-switch behavior is sufficient (matches FR16 and how 6-8/7-7 implemented it).

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (Thinking)

### Debug Log References

- Generated via bmad-create-story workflow.

### Completion Notes List

- Story drafted from epics.md Story 8.1 plus exhaustive code analysis of the routing fork ([App.tsx](file:///frontend/src/App.tsx)), the backend RBAC layer ([rbac.py](file:///src/ai_qa/api/auth/rbac.py), [middleware.py](file:///src/ai_qa/api/auth/middleware.py)), the admin router ([admin.py](file:///src/ai_qa/api/admin.py)), and existing coverage in `test_admin_rbac_api.py`, `test_admin_e2e_api.py`, `App.test.tsx`, and `story-7-7-workspace-shell.spec.ts`.
- **Key finding:** AC1, AC3, AC4 are already fully implemented and tested by earlier stories. The one real gap is **AC2** (standard user navigating to `/admin` URL stays in the workspace) which has no dedicated test. Scoped this as verification + a focused AC2 test + a consolidated `story-8-1-admin-routing.spec.ts`.
- **Note:** `8-1-admin-dashboard-routing-and-access-control` was missing from `sprint-status.yaml` (epic-8 listed only `8-6-...`). This story creation adds it and sets it to `ready-for-dev`.
- Backend `require_admin` is case-sensitive (`!= "admin"`) while the frontend gate lowercases; both are intentional and seeded roles agree — flagged to prevent a spurious "normalization fix."

**Dev execution (2026-06-06):**
- Confirmed AC1/AC3/AC4 were already implemented by earlier stories; no runtime code changed — this story is verification + closing two test gaps.
- **AC2 (frontend gap):** added two `App.test.tsx` cases that push `/admin` into `window.history` and assert a non-admin (`role: "user"`) renders the workspace shell (provider step or no-access message), never the admin dashboard. The render-switch SPA holds AC2 structurally; these tests now lock it as a regression guard.
- **AC4 (backend gap):** the membership assign/remove endpoints previously had only happy-path tests. Added a denial-matrix test (standard → 403, anonymous → 401) that also asserts the response body equals exactly `{"detail": ...}` so no user/project/membership data leaks.
- **E2E:** new `story-8-1-admin-routing.spec.ts` reuses the 7-7 fixtures/helpers and the 8-6 `ADMIN_DASHBOARD_E2E` skip guard. 3 tests pass against the live stack.
- **The public `GET /tests/e2e/report/view/{file_path}` route is unchanged** — confirmed it is the only unguarded admin route, intentional per Story 8.6 and the `PUBLIC_PATHS` whitelist. It serves only static report assets and exposes no admin data.
- Validation: backend ruff + ruff format + mypy + pytest (636 passed / 81.26% coverage); frontend lint + typecheck + 11 unit tests; e2e 3 passed.

### File List

- `frontend/src/App.test.tsx` (MODIFIED) — added two AC2 Vitest cases for standard-user `/admin` URL entry (member + zero-project).
- `tests/api/test_admin_rbac_api.py` (MODIFIED) — added `test_standard_and_unauthenticated_users_cannot_manage_memberships` closing the membership 401/403 + body-only-`detail` gap (AC4).
- `frontend/e2e/story-8-1-admin-routing.spec.ts` (NEW) — consolidated live-stack e2e: AC1 admin routing + AC2 standard-user `/admin` access control, with the 8.6 self-trigger skip guard.

## Change Log

| Date | Version | Description | Author |
| --- | --- | --- | --- |
| 2026-06-06 | 0.1 | Story drafted: verification of existing routing fork + RBAC, AC2 test-gap closure, consolidated 8-1 e2e spec. Added missing `8-1` entry to sprint-status. Status → ready-for-dev. | Bob (SM) |
| 2026-06-06 | 1.0 | Implemented: verified routing fork + RBAC; added AC2 Vitest cases (`/admin` URL entry), membership 401/403 denial test (AC4 body-only-detail), and consolidated `story-8-1-admin-routing.spec.ts` e2e. All gates green (pytest 636 passed/81%, frontend lint+typecheck+unit, e2e 3 passed). Status → review. | Amelia (Dev) |
