---
baseline_commit: "47547b1"
---
# Story 8.5: Admin Dashboard UI Layout

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> [!IMPORTANT]
> **This is a verification/coverage story** — the entire admin dashboard layout is **already implemented** in [AdminDashboard.tsx](file:///frontend/src/components/admin/AdminDashboard.tsx) (built across 6-9, 8-1, 8-2, 8-3, 8-4, 8-6) and is heavily covered by the [AdminDashboard unit test](file:///frontend/src/components/admin/AdminDashboard.test.tsx). Every AC maps to existing rendered UI: the top-nav identity block + Logout ([AdminDashboard.tsx#L353-L375](file:///frontend/src/components/admin/AdminDashboard.tsx#L353-L375)), the two-column `lg:grid-cols-2` layout ([L410](file:///frontend/src/components/admin/AdminDashboard.tsx#L410)) with Projects/Create Project on the left ([L412-L629](file:///frontend/src/components/admin/AdminDashboard.tsx#L412-L629)) and Users/Create User on the right ([L632-L875](file:///frontend/src/components/admin/AdminDashboard.tsx#L632-L875)), assigned-project chips with `×` remove ([L728-L750](file:///frontend/src/components/admin/AdminDashboard.tsx#L728-L750)), the per-user add-project `select` + `+` assign ([L685-L725](file:///frontend/src/components/admin/AdminDashboard.tsx#L685-L725)), and the Create User form (Email/Display Name/Role/Initial Password) + disabled "Sync existing company's users" button ([L778-L871](file:///frontend/src/components/admin/AdminDashboard.tsx#L778-L871)). **The dev work is: verify each AC against existing UI + unit coverage, close the AC1 gap (header identity trio shown together + a functional logout that returns the admin to the login screen — only the logout `fetch` call is unit-asserted today, not the post-logout redirect) with a focused assertion, and add the consolidated `story-8-5-admin-dashboard-ui-layout.spec.ts` e2e that exercises the whole layout against a live stack. No runtime/source changes are expected.**

## Story

As an admin,
I want a clear dashboard for managing projects, users, and memberships,
so that I can perform administrative tasks efficiently.

## Acceptance Criteria

1. **Given** an authenticated admin is on the dashboard
   **When** the dashboard loads
   **Then** the admin's email, display name, and role are displayed together in the top navigation near a functional Logout button ([AdminDashboard.tsx#L353-L375](file:///frontend/src/components/admin/AdminDashboard.tsx#L353-L375))
   **And** clicking Logout clears the authenticated session and returns the user to the login screen (the Sign In form is shown again).

2. **Given** the dashboard is displayed
   **When** the admin reviews the layout
   **Then** projects are shown in a left-side management area with create, rename (Edit), and delete actions ([AdminDashboard.tsx#L412-L629](file:///frontend/src/components/admin/AdminDashboard.tsx#L412-L629))
   **And** users are shown in a right-side management area with project membership controls ([AdminDashboard.tsx#L632-L769](file:///frontend/src/components/admin/AdminDashboard.tsx#L632-L769)).

3. **Given** the admin views a standard-user card
   **When** the user has assigned projects
   **Then** the card shows a Projects section with assigned project chips ([AdminDashboard.tsx#L728-L750](file:///frontend/src/components/admin/AdminDashboard.tsx#L728-L750))
   **And** each assigned project can be removed through an `×` action (`Remove {project_name} from {display_name}`).

4. **Given** assignable (unassigned) projects exist for a standard user
   **When** the admin uses the add-project control for that user
   **Then** the UI allows selecting an unassigned project from the `Select project for {display_name}` combobox and assigning it via the `Assign project to {display_name}` (`+`) button ([AdminDashboard.tsx#L685-L725](file:///frontend/src/components/admin/AdminDashboard.tsx#L685-L725)).

5. **Given** the user management area is displayed
   **When** the admin needs to create a user
   **Then** a Create User form is available with Email, Display Name, Role, and Initial Password fields ([AdminDashboard.tsx#L778-L856](file:///frontend/src/components/admin/AdminDashboard.tsx#L778-L856))
   **And** a disabled "Sync existing company's users" button explains that the feature is not available yet ([AdminDashboard.tsx#L857-L871](file:///frontend/src/components/admin/AdminDashboard.tsx#L857-L871)).

## Tasks / Subtasks

- [x] Task 1: Verify the top-nav identity block + functional Logout (AC: 1)
  - [x] Confirm the nav renders `display_name` (falls back to `name`), `email`, and `role` together at [AdminDashboard.tsx#L353-L362](file:///frontend/src/components/admin/AdminDashboard.tsx#L353-L362), and a Logout button calling `logout()` at [L364-L374](file:///frontend/src/components/admin/AdminDashboard.tsx#L364-L374). The identity block is `hidden md:block` — it is visible at the Playwright default 1280px viewport but NOT below `md` (768px); do not assert it on a mobile viewport.
  - [x] **Genuine gap:** the unit test only asserts the logout `POST /auth/logout` fetch call ([AdminDashboard.test.tsx#L284-L290](file:///frontend/src/components/admin/AdminDashboard.test.tsx#L284-L290)) and the display name; it does not assert the email+role trio together nor the post-logout redirect to the login screen. The 8-5 e2e closes this: after clicking Logout, assert the `Sign In` button (login form) is visible again.
- [x] Task 2: Verify the two-column management layout (AC: 2)
  - [x] Confirm the `grid gap-6 lg:grid-cols-2` wrapper at [L410](file:///frontend/src/components/admin/AdminDashboard.tsx#L410): left column = Projects list (Edit/Delete per card at [L509-L528](file:///frontend/src/components/admin/AdminDashboard.tsx#L509-L528)) + Create Project form ([L565-L628](file:///frontend/src/components/admin/AdminDashboard.tsx#L565-L628)); right column = Users Management ([L633-L769](file:///frontend/src/components/admin/AdminDashboard.tsx#L633-L769)) + Create User ([L772-L874](file:///frontend/src/components/admin/AdminDashboard.tsx#L772-L874)). Layout/CRUD behavior already e2e-covered by [story-8-3](file:///frontend/e2e/story-8-3-admin-project-management.spec.ts) — the 8-5 e2e asserts **presence/placement** of both areas, not re-testing CRUD.
- [x] Task 3: Verify assigned-project chips + `×` remove (AC: 3)
  - [x] Confirm chips render at [L728-L750](file:///frontend/src/components/admin/AdminDashboard.tsx#L728-L750) with per-chip `aria-label={`Remove ${up.name} from ${u.display_name}`}`. Removal flow itself is owned/covered by [story-8-4](file:///frontend/e2e/story-8-4-project-membership-assignment.spec.ts) — the 8-5 e2e seeds a user+assigned project via the admin API and asserts the chip + its `×` control render.
- [x] Task 4: Verify add-project select + `+` assign (AC: 4)
  - [x] Confirm the per-user `Select project for {display_name}` combobox ([L685-L710](file:///frontend/src/components/admin/AdminDashboard.tsx#L685-L710)) + `Assign project to {display_name}` button ([L711-L725](file:///frontend/src/components/admin/AdminDashboard.tsx#L711-L725)) render for a standard user with assignable projects. Both are disabled when `assignableProjects.length === 0` or the user is inactive — seed an unassigned project so the controls are enabled. Assign behavior covered by 8-4; the 8-5 e2e asserts the controls are present and enabled.
- [x] Task 5: Verify the Create User form + disabled Sync button (AC: 5)
  - [x] Confirm the Create User form fields: Email ([L786-L793](file:///frontend/src/components/admin/AdminDashboard.tsx#L786-L793)), Display Name ([L802-L808](file:///frontend/src/components/admin/AdminDashboard.tsx#L802-L808)), Role `<select aria-label="Role">` ([L817-L830](file:///frontend/src/components/admin/AdminDashboard.tsx#L817-L830)), Initial Password ([L839-L847](file:///frontend/src/components/admin/AdminDashboard.tsx#L839-L847)). Confirm the disabled `Sync existing company's users` button + `sync-users-help` explanatory text ([L857-L871](file:///frontend/src/components/admin/AdminDashboard.tsx#L857-L871)). Already unit-asserted at [AdminDashboard.test.tsx#L199-L206](file:///frontend/src/components/admin/AdminDashboard.test.tsx#L199-L206) — the 8-5 e2e re-asserts the disabled state + helper copy live.
- [x] Task 6: Add the consolidated Story 8.5 e2e (AC: 1, 2, 3, 4, 5)
  - [x] Create [story-8-5-admin-dashboard-ui-layout.spec.ts](file:///frontend/e2e/story-8-5-admin-dashboard-ui-layout.spec.ts) mirroring the [story-8-3](file:///frontend/e2e/story-8-3-admin-project-management.spec.ts) / [story-8-4](file:///frontend/e2e/story-8-4-project-membership-assignment.spec.ts) scaffold **verbatim**: `apiBaseUrl`/`adminEmail`/`adminPassword` env resolution + the throw-if-`adminPassword`-missing guard, `ensureAdminToken`, `createAdminUser`, `createAdminProject`, `assignMembership`, `loginViaApi`, `listAccessibleProjects`, the `beforeEach` `addInitScript` localStorage cleanup, the `afterEach` admin-token cleanup (**delete projects before users** — project delete cascades memberships), and the `loginAsAdmin(page)` helper (`getByLabel("Email")` → `getByLabel("Password")` → `getByRole("button", { name: "Sign In" })` → expect `/admin dashboard/i`).
  - [x] **Layout case (AC2/AC5):** after `loginAsAdmin`, assert the left-side area shows `Projects` + the `Create Project` form (`#create-project-button`), and the right-side area shows `Users Management` + the `Create User` form (Email, Display Name, `Role` combobox, Initial Password) and the disabled `Sync existing company's users` button with the helper text `This feature is not available at the moment, please add manually.`
  - [x] **Identity + logout case (AC1):** assert the nav shows the admin's email and role near the Logout button, click `Logout`, then assert the login `Sign In` button is visible again (session cleared → redirected to login).
  - [x] **Chips + assign-controls case (AC3/AC4):** seed (via admin API) one standard user + two projects; assign **one** project to the user. After `loginAsAdmin`, locate that user's card, assert the assigned-project chip + its `Remove {project_name} from {display_name}` `×` control render (AC3), and assert the `Select project for {display_name}` combobox (with the still-unassigned project as an option) + the `Assign project to {display_name}` button render and are enabled (AC4).
  - [x] **No-mocking + cleanup:** prepare all state via real admin API calls; clean up every created project + user in `afterEach` with an admin token. No `page.route` mocks.
- [x] Task 7: (Optional, only if Task 1 shows a unit gap) add a focused unit assertion in [AdminDashboard.test.tsx](file:///frontend/src/components/admin/AdminDashboard.test.tsx) that the header renders email + role alongside the display name. Prefer extending the existing `manages projects, users, and per-user memberships` test over adding a near-duplicate test.
- [x] Task 8: Validation gate (project-context.md Verification Workflow)
  - [x] Frontend: `npm run lint` (pass), `npm run typecheck` (pass) — strict `noUnusedLocals`/`noUnusedParameters`; remove any unused Playwright helper you copy but don't use.
  - [x] If a unit test was added/changed: run the relevant Vitest file.
  - [x] E2E: live-stack run `npx playwright test e2e/story-8-5-admin-dashboard-ui-layout.spec.ts` — all pass; `afterEach` + global teardown confirmed clean.
  - [x] Backend ruff/mypy/pytest are **not** required unless you (unexpectedly) touch Python — no backend change is anticipated for this story.
  - [x] Markdown diagnostics on this story file (MD032: blank lines around lists).

## Dev Notes

- **The layout already exists and is correct — this is a coverage story (mirrors 8-1/8-2/8-3/8-4).** [AdminDashboard.tsx](file:///frontend/src/components/admin/AdminDashboard.tsx) is a single ~987-line component that already renders all five ACs. The dev job is to verify each AC, close the AC1 logout-redirect/identity-trio gap, and add the consolidated 8-5 e2e. **Avoid reinventing or refactoring the dashboard — do not split it into subcomponents, do not restyle it, and do not add a new route.**
- **AC1 identity source.** The nav identity comes from the `useAuth()` `user` ([useAuth](file:///frontend/src/hooks/useAuth.ts) → [AuthContext](file:///frontend/src/contexts/AuthContext.tsx)), populated from `GET /auth/status`. The display name renders as `(user as any)?.display_name || user?.name` ([L356](file:///frontend/src/components/admin/AdminDashboard.tsx#L356)); in the live backend `/auth/status` returns `name` (display name), so the fallback is the normal path. AC1 is satisfied by showing *a* name + email + role — do **not** add a code change to force `display_name` unless live verification shows the name is blank.
- **AC1 logout.** `logout()` comes from `useAuth` and calls `POST /auth/logout`, clears the token, and flips auth state so [App.tsx](file:///frontend/src/App.tsx) re-renders the login screen. The e2e asserts the redirect by waiting for the `Sign In` button after clicking `Logout`. Do **not** add a confirmation dialog (UX-DR11 forbids confirmation dialogs).
- **AC2 columns are responsive.** The two-column split is `lg:grid-cols-2` ([L410](file:///frontend/src/components/admin/AdminDashboard.tsx#L410)) — it stacks below `lg` (1024px). Playwright's default 1280px viewport renders the true two-column layout, so left/right assertions hold without resizing. The card max-height is `md:max-h-[600px]` with `overflow-auto` — long lists scroll inside the card; don't assert against absolute pixel positions, assert against headings/regions (`Projects`, `Users Management`, `Create Project`, `Create User`).
- **AC3/AC4 controls only render for non-admin users.** The Projects section, chips, select, and assign button are inside `{!isAdminUser && (…)}` ([L678-L757](file:///frontend/src/components/admin/AdminDashboard.tsx#L678-L757)) — admin user cards intentionally show none of these (unit-asserted at [AdminDashboard.test.tsx#L236-L245](file:///frontend/src/components/admin/AdminDashboard.test.tsx#L236-L245)). Seed a **standard** user for the chip/assign assertions, not an admin.
- **AC4 select/assign are disabled when there is nothing to assign.** Both the combobox and `+` button are `disabled` when `assignableProjects.length === 0 || !u.is_active` ([L693-L721](file:///frontend/src/components/admin/AdminDashboard.tsx#L693-L721)). To assert AC4's "allows selecting and assigning", seed a user with **at least one unassigned** active project so the controls are enabled. `assignableProjectsByUserId` ([L319-L333](file:///frontend/src/components/admin/AdminDashboard.tsx#L319-L333)) filters out already-assigned projects — that's also the AC2-from-8-4 duplicate guard, so a project already assigned will not appear as an option.
- **Exact labels to assert (label drift is the #1 failure mode here):**
  - Nav: `Logout` button ([L364-L374](file:///frontend/src/components/admin/AdminDashboard.tsx#L364-L374)); login screen button is `Sign In`.
  - Headings: `Projects`, `Create Project`, `Users Management`, `Create User`, `E2E Test Execution`.
  - Per-user: `Select project for {display_name}` (combobox), `Assign project to {display_name}` (button), `Remove {project_name} from {display_name}` (chip `×`).
  - Create User: `Email`, `Display Name`, `Role` (combobox, `aria-label="Role"`), `Initial Password`; `Create user` submit; `Sync existing company's users` (disabled) + helper text `This feature is not available at the moment, please add manually.`
  - Create Project: `#create-project-button` (`Create project`), `Confluence Base URL *` is required.
- **Do not regress 8.1/8.2/8.3/8.4/8.6.** They all share this component. If you make any DOM/aria change (even a label tweak), re-run the [AdminDashboard unit suite](file:///frontend/src/components/admin/AdminDashboard.test.tsx) and the 8-1…8-4 + 8-6 e2e specs. The 8-6 E2E Test Execution panel ([L878-L982](file:///frontend/src/components/admin/AdminDashboard.tsx#L878-L982)) sits **below** the two-column grid and is out of scope for 8-5 — do not assert against it here (8-6 owns it).
- **Expected change footprint:** **1 new e2e spec** (`story-8-5-admin-dashboard-ui-layout.spec.ts`), optionally **1 small unit assertion**, and the **sprint-status.yaml `8-5` entry**. No runtime/source code changes are anticipated. If a code change becomes unavoidable (e.g. a genuinely missing aria-label), scope it to the smallest possible diff and document it in the Dev Agent Record + File List.

### Project Structure Notes

- Component: [frontend/src/components/admin/AdminDashboard.tsx](file:///frontend/src/components/admin/AdminDashboard.tsx) (single component; nav + two-column grid + E2E panel). Rendered for admins via the routing fork owned by Story 8.1 in [App.tsx](file:///frontend/src/App.tsx).
- Auth/identity: [useAuth](file:///frontend/src/hooks/useAuth.ts) + [AuthContext](file:///frontend/src/contexts/AuthContext.tsx) (`user`, `logout`); project state: [useProject](file:///frontend/src/hooks/useProject.ts) (`projects`, `reloadProjects`).
- API client: [frontend/src/lib/projects.ts](file:///frontend/src/lib/projects.ts) (`listAdminUsers`, `createAdminUser`, `createAdminProject`, `assignProjectMembership`, `removeProjectMembership`, …); error shaping via `getSafeApiErrorMessage` in [frontend/src/lib/api.ts](file:///frontend/src/lib/api.ts).
- Unit test: [AdminDashboard.test.tsx](file:///frontend/src/components/admin/AdminDashboard.test.tsx) (Vitest/jsdom, `fetch` spy). E2E: `frontend/e2e/*.spec.ts` (Playwright, real backend) importing from [../support/fixtures](file:///frontend/support/fixtures); shared cleanup in [global-teardown.ts](file:///frontend/e2e/global-teardown.ts).
- New e2e file: `frontend/e2e/story-8-5-admin-dashboard-ui-layout.spec.ts`.

### Testing Standards (from project-context.md)

- **E2E no-mocking + cleanup:** hit the real backend; bootstrap state via real admin API calls (`ensureAdminToken`, then `POST /api/admin/users` + `POST /api/admin/projects` + `POST /api/admin/projects/{id}/memberships`); clean up every created project + user in `afterEach` with an admin token (**delete projects before users** — project delete cascades memberships). No `page.route` mocks (the 8-6 self-trigger-loop mock is a narrow exception — do not copy it).
- **TS strictness:** `npm run typecheck` enforces `noUnusedLocals`/`noUnusedParameters` — delete any copied helper you don't use, and any caught-response `.json()` variable you don't read (ts6133).
- **Playwright env noise** (`DEP0205`, dotenv banner) is benign/suppressed; keep `timeout: 60*1000` in [playwright.config.ts](file:///frontend/playwright.config.ts) (do not shrink — slow-mo adds per-action cost).
- **Lint/type gates mandatory** for frontend changes; markdown diagnostics for this story file (MD032: blank lines around lists).
- No backend Python change expected, so backend ruff/ruff-format/mypy/pytest gates are skipped unless Python is touched.

### Previous Story Intelligence

From 8-4 (Membership Assignment), 8-3 (Project Management), 8-2 (User Management), 8-1 (Admin Routing), and 8-6 (Admin E2E Execution):

- 8-1→8-4 established the **verification-story pattern**: confirm pre-existing impl, add only the focused test gap + a consolidated `story-8-X-*.spec.ts`, and reuse the e2e helper scaffold **verbatim** from [story-8-3](file:///frontend/e2e/story-8-3-admin-project-management.spec.ts) / [story-8-4](file:///frontend/e2e/story-8-4-project-membership-assignment.spec.ts) (`ensureAdminToken`, `createAdminUser`, `createAdminProject`, `assignMembership`, `loginViaApi`, `listAccessibleProjects`, `loginAsAdmin`, the throw-if-no-`adminPassword` guard, `beforeEach` localStorage cleanup, `afterEach` projects-before-users cleanup). Follow it here.
- 8-3/8-4 already e2e-cover the **behaviors** behind 8-5's layout (project CRUD, membership assign/remove). 8-5 is the **layout/structure** story — assert presence/placement of the regions and the AC1 identity+logout flow, not a re-test of CRUD round-trips. Keep the spec lean to avoid duplicate coverage.
- 8-2's `getSafeApiErrorMessage` finding: a `409` maps to `kind="server"` → the banner shows the generic safe fallback, not the raw backend `detail`. Not directly relevant to 8-5 (no new error paths), but if you assert any error banner, assert the safe fallback string, not a literal backend message.
- The AdminDashboard unit test already covers most of AC2–AC5 (project CRUD, create-user form fields, disabled Sync button, admin-card-has-no-membership-controls, chips, assign/remove). The **only** clear unit gap is AC1's identity-trio + post-logout redirect — and the redirect is inherently an e2e concern (App-level routing), so the e2e is the primary new artifact.
- **Sprint-status gap (same as 8-4):** `8-5-admin-dashboard-ui-layout` is **missing** from [sprint-status.yaml](file:///_bmad-output/implementation-artifacts/sprint-status.yaml) (epic-8 lists `8-1`, `8-2`, `8-3`, `8-4`, `8-6`, `8-7`). This story creation inserts the `8-5` entry between `8-4` and `8-6` and sets it `ready-for-dev`.

### Git Intelligence

- Baseline commit: `47547b1` (`story 8-4 code and test OK`). Recent: `2b59ae9` (8-3), `132d2c1` (8-2), `7835943` (8-1), `d4f825f` (fix bug admin create thread). The admin dashboard layout, handlers, API client, and unit suite are already committed and green from 6-9 / 8-1…8-4 / 8-6 work. **8.5 ideally adds: 1 e2e spec + the sprint-status entry (+ optionally 1 unit assertion). No runtime code changes expected.** If a code change is unavoidable, scope it narrowly and call it out in the Dev Agent Record.

### Latest Tech Information

- Frontend: React 18 + TypeScript + Vite; Vitest + Testing Library (unit, jsdom); Playwright (e2e, real backend). `lucide-react` icons. Tailwind utility classes for layout (`grid lg:grid-cols-2`, responsive `hidden md:block`). Auth/project state via React context hooks (`useAuth`, `useProject`).
- Backend (unchanged for this story): FastAPI with `Depends(require_admin)` RBAC for the admin endpoints the dashboard calls (`/api/admin/users`, `/api/admin/projects`, `/api/admin/projects/{id}/memberships`); login/logout/status at `/auth/login`, `/auth/logout`, `/auth/status`.

### References

- [Epic 8: Admin Dashboard and Project Membership Management](file:///_bmad-output/planning-artifacts/epics.md#L428-L432)
- [Story 8.5 definition](file:///_bmad-output/planning-artifacts/epics.md#L537-L567)
- [AdminDashboard.tsx — full component](file:///frontend/src/components/admin/AdminDashboard.tsx)
- [Nav identity block + Logout (AC1)](file:///frontend/src/components/admin/AdminDashboard.tsx#L353-L375)
- [Two-column layout grid (AC2)](file:///frontend/src/components/admin/AdminDashboard.tsx#L410-L411)
- [Projects list + Edit/Delete (AC2)](file:///frontend/src/components/admin/AdminDashboard.tsx#L412-L562)
- [Create Project form (AC2)](file:///frontend/src/components/admin/AdminDashboard.tsx#L565-L628)
- [Users Management + chips + assign controls (AC2/AC3/AC4)](file:///frontend/src/components/admin/AdminDashboard.tsx#L633-L769)
- [Create User form + disabled Sync button (AC5)](file:///frontend/src/components/admin/AdminDashboard.tsx#L772-L874)
- [AdminDashboard unit test (existing coverage)](file:///frontend/src/components/admin/AdminDashboard.test.tsx)
- [Story 8-3 e2e (helpers to reuse verbatim)](file:///frontend/e2e/story-8-3-admin-project-management.spec.ts)
- [Story 8-4 e2e (membership UI — behavior already covered)](file:///frontend/e2e/story-8-4-project-membership-assignment.spec.ts)
- [project-context.md (testing + verification rules)](file:///project-context.md)

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro (High)

### Debug Log References

- Generated via bmad-create-story workflow.
- `npm run lint` → pass (eslint, 0 warnings).
- `npm run typecheck` → pass (`tsc --noEmit`).
- `npx playwright test e2e/story-8-5-admin-dashboard-ui-layout.spec.ts` → 3 passed (28.8s); e2e teardown removed 0 leftover users/projects (per-test `afterEach` cleaned up).
- `npx vitest run src/components/admin/AdminDashboard.test.tsx` → 9 passed. First run failed because the AC1 identity regex `/admin@example\.com/` also matched `super.admin@example.com` in the users list; fixed by scoping the query to the `<nav>` via `within(screen.getByRole("navigation"))`.

### Completion Notes List

- Story drafted from epics.md Story 8.5 plus exhaustive analysis of [AdminDashboard.tsx](file:///frontend/src/components/admin/AdminDashboard.tsx) (nav identity + Logout, two-column grid, project CRUD, user cards with chips + assign controls, Create User form + disabled Sync button, E2E panel), the existing [AdminDashboard unit test](file:///frontend/src/components/admin/AdminDashboard.test.tsx), and the 8-3/8-4 e2e helper scaffold.
- **Verification-story scope** (mirrors 8-1…8-4): all five layout ACs are already implemented and largely unit-covered. **Real gaps:** (1) AC1's header identity-trio shown together + a functional logout that redirects to the login screen (the unit test only asserts the logout fetch call, and the post-logout redirect is an App-level/e2e concern); (2) the consolidated `story-8-5-admin-dashboard-ui-layout.spec.ts` e2e exercising the whole layout live. AC2's project CRUD and AC3/AC4's membership behaviors are already owned/covered by 8-3/8-4 — the 8-5 e2e asserts layout presence/placement, not duplicate round-trips.
- **Note:** `8-5-admin-dashboard-ui-layout` was missing from [sprint-status.yaml](file:///_bmad-output/implementation-artifacts/sprint-status.yaml) (epic-8 listed `8-1`, `8-2`, `8-3`, `8-4`, `8-6`, `8-7`); inserted between `8-4` and `8-6` and set to `ready-for-dev` per the create-story workflow contract.
- **Dev outcome (verification confirmed):** All five ACs were verified against the already-implemented [AdminDashboard.tsx](file:///frontend/src/components/admin/AdminDashboard.tsx) — **no runtime/source changes were needed**. AC1: nav renders the display-name + email + role trio ([L353-L375](file:///frontend/src/components/admin/AdminDashboard.tsx#L353-L375)); AC2: `lg:grid-cols-2` two-column split ([L410](file:///frontend/src/components/admin/AdminDashboard.tsx#L410)); AC3: chips + `×` remove ([L728-L750](file:///frontend/src/components/admin/AdminDashboard.tsx#L728-L750)); AC4: select + assign button ([L685-L725](file:///frontend/src/components/admin/AdminDashboard.tsx#L685-L725)); AC5: Create User form + disabled Sync button ([L778-L871](file:///frontend/src/components/admin/AdminDashboard.tsx#L778-L871)).
- **AC1 unit gap closed:** extended the existing `manages projects, users, and per-user memberships` Vitest case to assert the email + role appear together in the nav identity block (scoped to `<nav>` to avoid matching the `super.admin@example.com` admin-user card). The post-logout redirect remains an App-level concern and is covered by the new e2e (`Sign In` button visible after Logout).
- **New e2e (3 cases, all green):** `[P0][AC2][AC5]` layout placement + disabled Sync button; `[P0][AC1]` nav identity + logout-returns-to-login; `[P0][AC3][AC4]` seeded standard-user chip + enabled assign controls. Reused the 8-3/8-4 scaffold verbatim; omitted the unused `loginViaApi`/`listAccessibleProjects` helpers to satisfy `noUnusedLocals`.

### File List

- `frontend/e2e/story-8-5-admin-dashboard-ui-layout.spec.ts` (NEW) — consolidated 8-5 e2e exercising the admin dashboard layout, identity+logout, chips, and assign controls live (3 cases, all pass).
- `frontend/src/components/admin/AdminDashboard.test.tsx` (MODIFIED) — added the focused AC1 nav identity-trio (email + role together) assertion to the existing `manages projects, users, and per-user memberships` test, scoped to the `<nav>`.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (MODIFIED) — 8-5 status transitions (in-progress → review).
- **No runtime/source changes** — `AdminDashboard.tsx` was verified, not modified.

## Change Log

| Date | Version | Description | Author |
| --- | --- | --- | --- |
| 2026-06-06 | 0.1 | Story drafted: verification of the existing admin dashboard layout. Identified AC1 (identity-trio + post-logout redirect) as the genuine gap and the consolidated 8-5 e2e as the primary new artifact; AC2–AC5 behaviors already owned/covered by 8-3/8-4 + the unit suite. Inserted missing `8-5` entry into sprint-status. Status → ready-for-dev. | Bob (SM) |
| 2026-06-06 | 1.0 | Implemented: verified all 5 ACs against existing UI (no source change), closed the AC1 unit gap (nav email+role trio, scoped to `<nav>`), added the consolidated `story-8-5-admin-dashboard-ui-layout.spec.ts` e2e (3 cases). Gates green: lint, typecheck, e2e 3/3, unit 9/9. Status → review. | Amelia (Dev) |
| 2026-06-06 | 1.1 | Full epic regression confirmed: `npx playwright test e2e` → 30/30 passed (1.2m), e2e teardown clean. No regression in 8-1–8-4 / 8-6 from the 8-5 unit assertion or new spec. Status → done. | Amelia (Dev) |
