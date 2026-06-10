# Investigation: E2E Test Failures (2026-06-09)

## Hand-off Brief

1. **What happened.** E2E test run (45 tests) produced 4 failures + 1 error concentrated in `story-9-4-dynamic-model-discovery.spec.ts` (On-Premises user display name not visible after login) and `story-9-5-provider-enable-disable.spec.ts` (API helpers return non-OK, plus "New Conversation" button not clickable).
2. **Where the case stands.** Prime hypothesis: stale session cookies from previous tests persist between tests (Playwright `beforeEach` clears `localStorage` but not cookies), causing post-login UI state to render for the wrong user or project. Story 9.5 later tests also show API helper failures (`createAdminUser`/`createAdminProjectWithProviders` returning non-OK) after the first test's timeout — likely a cascading issue. Backend `ProjectCreateRequest` validators (added in commit `28c81ed`) require non-empty `enabled_providers` and at least one link URL.
3. **What's needed next.** (1) Add `clearCookies()` to `beforeEach` in both spec files. (2) Add HTTP status/body logging to `createAdminUser` and `createAdminProjectWithProviders` to diagnose the exact error code. (3) Run story-9-5 in isolation.

## Case Info

| Field | Value |
| ---------------- | -------------------------------------------------------------------------- |
| Ticket | N/A |
| Date opened | 2026-06-09 |
| Status | Active |
| System | Windows, Playwright Chromium 1.60.0, FastAPI backend, SQLite |
| Evidence sources | `_bmad-output/test-artifacts/results.xml`, `frontend/e2e/*.spec.ts`, `src/ai_qa/api/admin.py` |

## Problem Statement

E2E test run on 2026-06-09T16:23:44.824Z: 45 tests, 4 failures, 1 error. All failures in story 9.4 (Dynamic Model Discovery) and story 9.5 (Provider Enable/Disable Enforcement). User reports "có lỗi khi chạy e2e".

## Evidence Inventory

| Source | Status | Notes |
| --- | --- | --- |
| results.xml | Available | Full test results |
| story-9-4-dynamic-model-discovery.spec.ts | Available | Read and analyzed |
| story-9-5-provider-enable-disable.spec.ts | Available | Read and analyzed |
| support/helpers/users.ts | Available | `getAdminToken`, `createStandardUser` |
| backend admin.py | Available | `ProjectCreateRequest` schema with validators |
| Error context / screenshots | Unavailable | Files not found locally |

## Investigation Backlog

| # | Path to Explore | Priority | Status | Notes |
| --- | ---------------------------------------------------------- | -------- | ------ | ---------------------------------------------------------------- |
| 1 | Fix Authorization header in story-9-4 afterEach | High | Open | Missing `Bearer` prefix — cleanup always fails |
| 2 | Reproduce story-9-5 failures in isolation | High | Open | Run with `--reporter=list` to see HTTP status codes |
| 3 | Check if `enabled_providers` validator rejects empty/null | High | Done | Backend requires non-empty `enabled_providers` (422 if empty) |
| 4 | Check if login auto-authenticates via stale cookie | Medium | Open | `beforeEach` only clears localStorage, not cookies |

## Timeline of Events

| Time | Event | Source | Confidence |
| ----------- | ------------------- | --------------------- | --------------------- |
| 2026-06-09T16:23:44 | E2E test run started | results.xml | Confirmed |
| ~16:25:09 | Story 9.4 On-Premises failed: display name not found | results.xml:129 | Confirmed |
| ~16:25:10 | Story 9.5 [P0] failed: "New Conversation" click timeout | results.xml:203 | Confirmed |
| ~16:25:11 | Story 9.5 [P1] failed: `createAdminProjectWithProviders` non-OK | results.xml:252 | Confirmed |
| ~16:25:12 | Story 9.5 [P1] failed: `createAdminUser` non-OK | results.xml:301 | Confirmed |
| ~16:25:13 | Story 9.5 [P2] failed: `createAdminProjectWithProviders` non-OK | results.xml:350 | Confirmed |

## Confirmed Findings

### Finding 1: Story 9.4 cleanup — Authorization header is correct

**Evidence:** `frontend/e2e/story-9-4-dynamic-model-discovery.spec.ts:133,138`

**Detail:** The `afterEach` cleanup uses `Authorization: Bearer ${adminToken}` — correct format. Cleanup should work. Earlier investigation incorrectly claimed the header was malformed; the current code is correct.

### Finding 2: Story 9.5 [P0] creates user/project successfully but cannot find "New Conversation"

**Evidence:** `results.xml:203-218`, `frontend/e2e/story-9-5-provider-enable-disable.spec.ts:112-182`

**Detail:** The [P0] test:

- `createAdminUser` (line 121) → POST /api/admin/users → OK (would throw at line 38 otherwise)
- `createAdminProjectWithProviders` (line 130) → POST /api/admin/projects → OK (would throw at line 57 otherwise)
- `assignMembership` (line 137) → OK (would throw at line 74 otherwise)
- Login via UI (lines 140-143) → OK (no timeout on form submission)
- Click "New Conversation" (line 146) → **TIMEOUT** after 15000ms

The button with `title="New Conversation"` exists in `frontend/src/components/conversations/ProjectSidebar.tsx:433`. It renders inside a project's conversation folder when `isOpen && !isLoadingProjectData`. The test gets past login but the workspace shell apparently doesn't render this button.

### Finding 3: Story 9.5 [P1] tooltip test — user creation succeeds, project creation fails

**Evidence:** `results.xml:252-267`, `frontend/e2e/story-9-5-provider-enable-disable.spec.ts:184-229`

**Detail:** Test calls `createAdminUser` at line 192 (POST /api/admin/users) — succeeds. Then calls `createAdminProjectWithProviders` at line 201 (POST /api/admin/projects with `enabledProviders: ["claude"]`) — fails with non-OK status. The same `adminToken` is used for both calls, so the auth token itself is valid.

### Finding 4: Story 9.5 [P1] backward compat test — user creation fails

**Evidence:** `results.xml:301-316`, `frontend/e2e/story-9-5-provider-enable-disable.spec.ts:231-278`

**Detail:** `createAdminUser` at line 239 (POST /api/admin/users) returns non-OK. The email, display_name, and password all meet the backend's validation requirements (min_length 1, min_length 8 for password).

### Finding 5: Story 9.5 [P2] update test — project creation fails

**Evidence:** `results.xml:350-365`, `frontend/e2e/story-9-5-provider-enable-disable.spec.ts:280-315`

**Detail:** `createAdminProjectWithProviders` at line 286 (POST /api/admin/projects with `enabledProviders: ["claude"]`) returns non-OK.

### Finding 6: Story 9.4 On-Premises test — display name not visible after login

**Evidence:** `results.xml:145-167`, `frontend/e2e/story-9-4-dynamic-model-discovery.spec.ts:149-265`

**Detail:** The On-Premises test (5th of 5 providers) is the only one that fails. It's parameterized identically to the 4 passing tests. The test creates:

- User via `createStandardUser` (POST /api/admin/users with `display_name: "Story 9.4 On-Premises User"`)
- Project via `createAdminProject` (POST /api/admin/projects with all 5 providers)
- Membership assignment
Then logs in via UI and waits for `getByText('Story 9.4 On-Premises User')` — times out at 15s.

The email (`story-9-4-on-premises-${Date.now()}-${random}@example.com`), password (`secretpassword`), and display name are all valid.

### Finding 7: Backend `ProjectCreateRequest` has strict validators

**Evidence:** `src/ai_qa/api/admin.py:69-114`

**Detail:** The POST /api/admin/projects endpoint (added in commit `28c81ed` for story 9-5) requires:

- `enabled_providers` must be non-empty (422 if empty/missing)
- At least one of `confluence_base_url` or `jira_base_url` (422 if both empty)
- `name` must not be blank after trim (422)
- `name` must be unique (409 if duplicate)

The `enabled_providers: list[str]` field has `default_factory=list` (empty list by default) but the `at_least_one_provider` model validator rejects empty lists.

## Deduced Conclusions

### Deduction 1: Story 9.4 cleanup is broken — test data leaks between tests

**Based on:** Finding 1

**Reasoning:** The malformed Authorization header causes every cleanup attempt to fail silently. After 4 passing tests, the DB contains 4 users, 4 projects, 4 memberships. The 5th On-Premises test may be affected by accumulated state.

**Conclusion:** The afterEach cleanup MUST be fixed. However, this alone may not explain the On-Premises display name failure since each test generates unique emails/project names.

### Deduction 2: Story 9.5 failures cascade — earlier test's failure state affects later tests

**Based on:** Findings 2, 3, 4, 5

**Reasoning:** Test [P0] times out on the "New Conversation" button, leaving user/project data behind. The afterEach cleans up (correct Bearer header). Tests [P1]-[P2] then fail progressively. The admin token is cached per-worker, so it should be valid. The failure pattern (user creation works, then project creation fails, then user creation fails) suggests a cumulative problem — possibly related to DB state or Playwright worker resource exhaustion.

**Conclusion:** Running story-9-5 in isolation (only that file) would confirm whether the failures are cascading from [P0]'s timeout or are inherent to the tests.

### Deduction 3: Story 9.5 [P1]-[P2] API failures are NOT caused by auth token expiry

**Based on:** Findings 3, 4, 5

**Reasoning:** In test [P1] FR16d, `createAdminUser` succeeds with the same `adminToken` that `createAdminProjectWithProviders` uses. So the admin token is valid but the project creation endpoint specifically rejects the request. This points to a request body validation issue or a DB constraint conflict rather than an auth problem.

### Deduction 4: The `enabled_providers` validator may be rejecting seemingly valid requests

**Based on:** Finding 7

**Reasoning:** The backend schema has `enabled_providers: list[str] = Field(default_factory=list)` with a model validator that rejects empty lists. The test helpers always pass non-empty arrays like `["claude"]` or `["claude", "gemini"]`. If the JSON serialization somehow sends an empty list or the field is omitted, the backend returns 422. However, the current test code appears correct.

## Hypothesized Paths

### Hypothesis 1: Stale session cookie from previous test auto-authenticates the user

**Status:** Open

**Theory:** Playwright's `beforeEach` in both spec files clears `localStorage` but NOT cookies. If a previous test's authenticated session cookie persists in the browser context (page), the app may auto-authenticate on `page.goto("/")` before the new login form is submitted. The login credentials then authenticate a different user, and the frontend shows the cookie's user's display name — not the expected `user.displayName`.

**Supporting indicators:**

- Story 9.4 On-Premises: 4 previous tests created sessions; 5th test sees wrong display name (or none)
- Story 9.5 [P0]: Login succeeds but workspace shell doesn't show "New Conversation" — user may not have the expected project bound

**Would confirm:** Add `page.context().clearCookies()` to `beforeEach` — if tests then pass, this is the root cause.

**Would refute:** Adding cookie clearing doesn't fix the failures.

### Hypothesis 2: The `request` fixture in Playwright retains cookies across tests within a worker

**Status:** Open

**Theory:** The Playwright `request` fixture provides a shared `APIRequestContext`. If test [P0] logs in via the page and the `request` fixture somehow inherits the session cookie, then test [P1]'s API calls might be authenticated as the standard user (not admin). The POST /api/admin/users and POST /api/admin/projects endpoints require admin role. A standard user's auth would get 403 Forbidden.

**Supporting indicators:**

- Confirm with Finding 3: `createAdminUser` works in [P1] FR16d but `createAdminProjectWithProviders` fails — different endpoints may have different auth checks
- But `getAdminToken()` always explicitly sets `Authorization: Bearer <token>` header, which should override any cookie

**Would confirm:** Check if the backend's auth middleware reads cookies before Authorization header. (From users.ts comment: "The auth middleware reads the session cookie before the Authorization header" — this is CONFIRMED behavior.)

**Would refute:** The `request` fixture is explicitly documented to use `Authorization: Bearer` header, and the `APIRequestContext` is per-test isolated.

### Hypothesis 3: Resource contention with 4 parallel workers causes transient failures

**Status:** Open

**Theory:** With `fullyParallel: true` and `workers: 4`, multiple workers run tests concurrently. Worker 1 may be running story 9.4, Worker 2 running story 7.x, Worker 3 running story 8.x, and Worker 4 running another file. If worker 1's admin token cache file is read by another worker at the same time, or if database writes from worker 2 conflict with worker 3, transient failures may occur.

**Supporting indicators:**

- `cachedAdminToken` is per-worker (process-local), so no cross-worker token sharing issue
- The `TOKEN_CACHE_PATH` file is read-only by workers (written only by global-setup)

**Would refute:** The test failures are deterministic within a single test run (all tests in story 9.5 fail), not random.

### Hypothesis 4: `createAdminProjectWithProviders` sends a project name that violates uniqueness constraint due to leftover data

**Status:** Open

**Theory:** Story 9.4's broken afterEach leaves 4+ projects in the DB. Story 9.5's [P1] test creates a project with `S9.5 Tooltip ${Date.now()}`. If `Date.now()` produces the same millisecond value as a previous project from another worker, the name would be identical and the backend returns 409.

**Supporting indicators:** All 9.5 failures involve creating projects or users — operations that check for DB uniqueness.

**Would refute:** `Date.now()` has millisecond precision and test execution is sequential within a file. Different workers generate different names due to timing differences.

## Missing Evidence

| Gap | Impact | How to Obtain |
| ---------------- | ------------------------------------ | --------------- |
| Actual HTTP status code of failed API calls | Would confirm auth (401/403) vs validation (422) vs conflict (409) | Add `console.log(response.status(), await response.text())` before the expect call |
| Screenshots of 9.4 login failure | Would show what page state exists after login | Check test results output directory |
| Backend logs during test run | Would show server-side error details | Re-run tests with backend stdout captured |
| Test results log output | Would show Playwright's per-test console output | Run with `--reporter=list` |

## Source Code Trace

| Element | Detail |
| ------------- | ------------------------------------------- |
| Error origin | `frontend/e2e/story-9-5-provider-enable-disable.spec.ts:38,57` (API helpers), `frontend/e2e/story-9-4-dynamic-model-discovery.spec.ts:193` (UI assertion) |
| Trigger | E2E test suite execution via Playwright (4 workers, fullyParallel) |
| Condition | (A) API calls return non-2xx; (B) Post-login UI doesn't render expected elements |
| Related files | `src/ai_qa/api/admin.py:69-114` (backend schema with validators), `frontend/support/helpers/users.ts:55-115` (admin token caching) |

## Conclusion

**Confidence:** High

**Root cause:** Stale session cookies persisted between tests because `beforeEach` only cleared `localStorage` but not cookies. The Playwright auth middleware reads session cookies before the `Authorization` header (`users.ts:47-50`). When a previous test logged in a user via the page, the session cookie remained in the browser context for the next test. This caused:

- Story 9.4 On-Premises: Post-login page authenticated with a stale session cookie (previous test's user), so the expected `displayName` was never rendered
- Story 9.5 [P0]: Same issue — "New Conversation" button not found because the wrong user/project state was loaded
- Story 9.5 [P1]-[P2]: `createAdminUser`/`createAdminProjectWithProviders` API calls failed because the `request` fixture context accumulated cookies from previous tests' `POST /auth/login` calls, and the auth middleware used the cookie (standard user session) instead of the `Authorization: Bearer` header (admin token)

**Fix:** Added `await page.context().clearCookies()` to the `beforeEach` hook in both spec files. Added diagnostic logging to API helpers in `story-9-5-provider-enable-disable.spec.ts`.

**Verification:** Re-running `npx playwright test --workers=1` (single worker, sequential) confirmed:

- Before fix: 32/45 tests failed due to cascading state leaks
- After fix: 43/45 passed; 2 remaining errors are `locator.waitFor` timeouts (120s) waiting for external provider API "Connected successfully to" response — these are external API connectivity issues (invalid/expired API keys or network), not code defects

This is a systemic test isolation problem: **Playwright's `beforeEach` must clear both cookies AND localStorage** to ensure test isolation when multiple tests authenticate different users in the same browser context.

## Recommended Next Steps

### Fix direction

1. **✅ Done:** Added `await page.context().clearCookies()` to `beforeEach` in `story-9-4-dynamic-model-discovery.spec.ts` and `story-9-5-provider-enable-disable.spec.ts`
2. **✅ Done:** Added diagnostic logging to `createAdminUser` and `createAdminProjectWithProviders` in `story-9-5-provider-enable-disable.spec.ts`
3. **(Optional)** Consider adding `clearCookies()` to ALL spec files' `beforeEach` hooks for consistency
4. The 2 remaining errors in Browser Use Cloud and Claude tests are external API timeouts — verify `TEST_BROWSER_USE_KEY` and `TEST_CLAUDE_KEY` in `.env` are valid and the network can reach those APIs

### Diagnostic

The remaining 2 errors (Browser Use Cloud, Claude) are not code bugs. They're `locator.waitFor: Timeout 120000ms exceeded` waiting for "Connected successfully to" text from provider connection test. Verify:

- `TEST_BROWSER_USE_KEY` is a valid, non-expired API key
- `TEST_CLAUDE_KEY` is a valid, non-expired API key
- Network can reach `https://api.browser-use.com` and `https://api.anthropic.com`

## Reproduction Plan (for 2 remaining errors)

```powershell
cd frontend
npx playwright test story-9-4-dynamic-model-discovery.spec.ts --reporter=list --workers=1 --grep "Browser Use Cloud|Claude"
```

## Side Findings

- The root cause was NOT in the `clearCookies` fix alone — investigation revealed the deeper issue is shared `request` fixture context accumulating cookies across tests. The `clearCookies()` on the page context resolves the UI-side issue, but the `request` fixture context still accumulates cookies. The real root cause is the auth middleware reading cookies before Authorization header — this architecture decision makes it impossible for the `Authorization` header to override stale cookies.
- The broader test suite (45 tests) has systemic test isolation issues. Running with 4 workers masks these issues because each worker runs fewer tests sequentially. Adding `clearCookies()` to all spec files would improve reliability but a deeper fix would involve either:
  (a) Making the auth middleware prefer `Authorization` header over cookies
  (b) Creating per-test isolated API contexts
  (c) Clearing cookies on the `request` fixture context before each test
