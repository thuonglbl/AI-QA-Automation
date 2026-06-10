---
baseline_commit: 9314c412d1e2ddbb6ef22f38d684bea464c87092
---

# Story 8.7: Lock Down Public Self-Service Registration Endpoint

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a security-conscious system,
I want the public `POST /auth/register` endpoint removed or gated to admins,
so that user accounts can only be created by admins, fully satisfying the admin-only user-management requirement (FR16, Story 8.2 AC3).

## Context

Story 8.2 AC3 requires that "self-service registration is not shown" and "user creation is available only to admins." The authenticated UI satisfies this, but a public, unauthenticated `POST /auth/register` endpoint still exists (whitelisted in `PUBLIC_PATHS`) and creates standard users without admin authorization. 

**Breaking Change**: This endpoint is currently relied upon by every Epic 7 E2E spec (`registerStandardUser` helper function) to bootstrap test users, so removing it requires migrating the test suite to use the admin endpoint instead.

## Acceptance Criteria

1. **Given** an unauthenticated client calls `POST /auth/register`
   **When** backend authorization is evaluated
   **Then** the request is rejected (endpoint removed, disabled, or admin-gated)
   **And** no user account is created without admin authorization

2. **Given** the E2E test suite previously bootstrapped users via `POST /auth/register`
   **When** the registration endpoint is locked down
   **Then** the affected E2E specs are migrated to a replacement bootstrap path (e.g. seeding via an admin token calling `POST /api/admin/users`)
   **And** the full E2E suite passes against the live stack

3. **Given** the registration endpoint is gated rather than removed
   **When** a standard or unauthenticated caller attempts it
   **Then** the request is rejected as forbidden/unauthorized without leaking whether an email exists
   **And** only admins can create users through any path

## Tasks / Subtasks

- [x] Task 1: Lock down the public registration endpoint (AC: 1, 3)
  - [x] Remove `/auth/register` from `PUBLIC_PATHS` in `src/ai_qa/api/auth/middleware.py`
  - [x] Either remove the endpoint or add admin-only authorization check
  - [x] Ensure proper 401/403 responses for unauthorized attempts
  - [x] Update backend API tests in `tests/api/test_auth_api.py`

- [x] Task 2: Create E2E test helper for admin user creation (AC: 2)
  - [x] Create shared helper function that uses admin credentials and `POST /api/admin/users`
  - [x] Ensure helper can be used as drop-in replacement for `registerStandardUser`
  - [x] Handle admin authentication and token management

- [x] Task 3: Migrate all E2E tests to use admin endpoint (AC: 2)
  - [x] Replace `registerStandardUser` calls in all affected E2E specs:
    - `frontend/e2e/story-7-1-auth.spec.ts`
    - `frontend/e2e/story-7-2-project-membership.spec.ts`
    - `frontend/e2e/story-7-3-project-selection.spec.ts`
    - `frontend/e2e/story-7-3-thread-creation.spec.ts`
    - `frontend/e2e/story-7-5-conversation-history.spec.ts`
    - `frontend/e2e/story-7-6-membership-removal.spec.ts`
    - `frontend/e2e/story-7-7-workspace-shell.spec.ts`
    - `frontend/e2e/story-8-1-admin-routing.spec.ts`
  - [x] Verify all E2E tests pass with new approach

- [x] Task 4: Verification (AC: 1, 2, 3)
  - [x] Run full E2E test suite and confirm all tests pass
  - [x] Run backend API tests and confirm registration tests properly validate admin-only access
  - [x] Manual test: Verify unauthenticated `POST /auth/register` returns 401/403

## Dev Notes

### Architecture Context

**Authentication System**:
- Backend uses JWT session tokens via `SessionManager` in `src/ai_qa/api/auth/session.py`
- `AuthMiddleware` in `src/ai_qa/api/auth/middleware.py` validates tokens and protects routes
- `PUBLIC_PATHS` set (line 30-46) defines routes accessible without authentication
- Admin-only endpoints use `AdminDependency` from `src/ai_qa/api/auth/rbac.py`

**Admin User Creation Endpoint**:
- Already exists: `POST /api/admin/users` in `src/ai_qa/api/admin.py` (lines 194-221)
- Requires admin role via `AdminDependency`
- Accepts `AdminUserCreateRequest` with email, name, password, and role
- Returns `AdminUserResponse` with safe user data (no password hash)

### Current Implementation to Modify

**File: `src/ai_qa/api/auth/middleware.py`**
- Line 32: Remove `/auth/register` from PUBLIC_PATHS set
- This will cause the middleware to require authentication for the endpoint

**File: `src/ai_qa/api/auth/local.py`**
- Lines 83-99: `POST /auth/register` endpoint implementation
- Options:
  1. **Remove entirely** (cleanest, recommended)
  2. **Add admin guard** using `AdminDependency` (if keeping for future use)
- Current implementation uses `register_user` service function

**File: `tests/api/test_auth_api.py`**
- Lines 46, 87, 92, 115, 144: Backend tests for `/auth/register`
- Need to update these tests to expect 401/403 or test admin-only access

### E2E Test Migration Pattern

**Current Pattern** (from `story-7-1-auth.spec.ts` lines 50-60):
```typescript
const registerResponse = await request.post(`${apiBaseUrl}/auth/register`, {
  data: {
    email: user.email,
    name: user.displayName,
    password: user.password,
  },
});
```

**New Pattern** (use admin endpoint):
```typescript
// 1. Login as admin to get admin token
const adminLoginResponse = await request.post(`${apiBaseUrl}/auth/login`, {
  data: { email: adminEmail, password: adminPassword },
});
const adminToken = (await adminLoginResponse.json()).access_token;

// 2. Create user via admin endpoint
const registerResponse = await request.post(`${apiBaseUrl}/api/admin/users`, {
  headers: { Authorization: `Bearer ${adminToken}` },
  data: {
    email: user.email,
    display_name: user.displayName,
    password: user.password,
    role: "standard",
  },
});
```

**Note**: Admin credentials available from environment variables:
- `process.env.ADMIN_EMAIL` or `process.env.E2E_ADMIN_EMAIL` (default: `admin@example.com`)
- `process.env.ADMIN_PASSWORD` or `process.env.E2E_ADMIN_PASSWORD`

### Files Being Modified

**UPDATE** `src/ai_qa/api/auth/middleware.py`:
- Current: PUBLIC_PATHS includes `/auth/register` (line 32)
- Change: Remove `/auth/register` from the set to require authentication
- Preserve: All other public paths and middleware logic

**UPDATE** `src/ai_qa/api/auth/local.py`:
- Current: Public `/auth/register` endpoint (lines 83-99)
- Change: Either remove endpoint entirely OR add `AdminDependency` to protect it
- Preserve: All other auth endpoints (login, logout, me, status)

**UPDATE** `tests/api/test_auth_api.py`:
- Current: Tests assume public registration endpoint
- Change: Update tests to expect 401/403 for unauthenticated calls, or test admin-only access
- Preserve: Core authentication test logic

**UPDATE** All E2E test files with `registerStandardUser`:
- Create shared helper function (e.g., in `frontend/e2e/support/test-helpers.ts`)
- Replace all direct calls to `/auth/register` with admin-authenticated calls
- Ensure cleanup logic in `afterEach` hooks continues to work

### Security Requirements

From NFR7: "User-provided MCP keys and AI provider API keys are stored only in encrypted PostgreSQL fields and never appear in `.env`, plaintext JSON columns, logs, WebSocket payload history, conversation history, artifacts, or generated files."

- Endpoint responses must never expose password hashes or secrets
- Error messages must not leak whether an email exists (timing-safe responses)
- Admin authorization must be validated server-side, not just in middleware

### Testing Standards

**Backend Tests** (`tests/api/test_auth_api.py`):
- Test unauthenticated `/auth/register` returns 401 or 404
- Test standard user cannot access registration endpoint
- Test admin can create users via `/api/admin/users`

**E2E Tests**:
- All Epic 7 and Epic 8 E2E tests must pass
- User creation via admin endpoint must work in all test scenarios
- Cleanup in `afterEach` hooks must successfully delete test users

### Previous Story Intelligence

From Story 8.6 (Admin E2E Test Execution):
- Admin endpoints use `AdminDependency` for role checking
- E2E test patterns established for admin operations
- Environment variable patterns: `ADMIN_EMAIL`, `ADMIN_PASSWORD`
- Test cleanup patterns: Authenticate as admin, then delete resources
- Error handling: Always handle missing admin credentials gracefully

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 8.7]
- [Source: _bmad-output/planning-artifacts/architecture.md#Authentication Architecture]
- [Source: src/ai_qa/api/auth/middleware.py]
- [Source: src/ai_qa/api/auth/local.py]
- [Source: src/ai_qa/api/admin.py#Admin User Management]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (bmad-dev-story workflow)

### Debug Log References

- Backend: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` — all clean.
- Backend: `uv run pytest` — 644 passed, 2 skipped, total coverage 81.26% (>= 80% gate).
- Frontend: `npm run typecheck` and `npm run lint` — clean.
- E2E: `npx playwright test --workers=1` — 30 passed (1.6m).
  - Note: the suite must run serially (`--workers=1`, as the in-app admin runner does). Argon2
    (`PasswordHash.recommended()`) password verification is intentionally CPU/memory heavy; the
    default parallel workers all log in at once and saturate the single backend process, tripping
    Playwright's 15s action timeout on `/auth/login`. Serial runs are stable.

### Implementation Plan

1. Lock down backend: removed `/auth/register` from `PUBLIC_PATHS` and deleted the public `register`
   endpoint (plus its `RegisterRequest` model and now-unused imports/constant) from `local.py`.
   Chose the dev-notes "recommended" option (remove entirely). Admin-only user creation is fully
   served by the pre-existing `POST /api/admin/users` (`require_admin`), which already returns
   proper 401/403 without leaking email existence — satisfying AC3's protected-path intent.
2. Updated backend tests to seed users via the `register_user` domain service and added two lock-down
   tests (route removed; unauthenticated attempt creates no account and leaks nothing).
3. Added shared E2E helper `frontend/support/helpers/users.ts` (`createStandardUser`,
   `getAdminToken`) as a drop-in replacement for the per-spec `registerStandardUser`, and migrated
   all 8 affected specs to delegate to it.

### Completion Notes List

- AC1: Public `POST /auth/register` is removed and de-whitelisted. An unauthenticated attempt is
  rejected by the auth middleware and creates no account (verified by backend test
  `test_unauthenticated_registration_attempt_creates_no_account` and route-removal assertion).
- AC2: All Epic 7 + Story 8.1 specs that previously bootstrapped users via `/auth/register` now use
  the admin endpoint through `createStandardUser`. Full E2E suite (30 tests) passes against the live
  stack.
- AC3: Removal makes the "gated rather than removed" clause moot; the sole user-creation path
  `POST /api/admin/users` is admin-gated and returns 401/403 without revealing whether an email
  exists.
- Helper design note: the admin login in `getAdminToken` runs in an isolated Playwright request
  context so its session cookie cannot leak into a test's request context. The auth middleware reads
  the session cookie before the Authorization header, so a leaked admin cookie would otherwise
  override a standard user's bearer token on `GET /auth/me`. The token is also cached per worker to
  avoid redundant Argon2 verifies.
- Updated `README.md` auth-routes table to drop `/auth/register` and document admin-only creation.

### File List

- `src/ai_qa/api/auth/middleware.py` (modified) — removed `/auth/register` from `PUBLIC_PATHS`; added explanatory comment.
- `src/ai_qa/api/auth/local.py` (modified) — removed the public `register` endpoint, `RegisterRequest` model, and now-unused imports/constant.
- `tests/api/test_auth_api.py` (modified) — seed users via service; added lock-down tests.
- `frontend/support/helpers/users.ts` (new) — shared `createStandardUser` / `getAdminToken` helper.
- `frontend/e2e/story-7-1-auth.spec.ts` (modified) — migrated inline registration to `createStandardUser`.
- `frontend/e2e/story-7-2-project-membership.spec.ts` (modified) — delegate `registerStandardUser` to shared helper.
- `frontend/e2e/story-7-3-project-selection.spec.ts` (modified) — delegate `registerStandardUser` to shared helper.
- `frontend/e2e/story-7-3-thread-creation.spec.ts` (modified) — delegate `registerStandardUser` to shared helper.
- `frontend/e2e/story-7-5-conversation-history.spec.ts` (modified) — delegate `registerStandardUser` to shared helper.
- `frontend/e2e/story-7-6-membership-removal.spec.ts` (modified) — delegate `registerStandardUser` to shared helper.
- `frontend/e2e/story-7-7-workspace-shell.spec.ts` (modified) — delegate `registerStandardUser` to shared helper.
- `frontend/e2e/story-8-1-admin-routing.spec.ts` (modified) — delegate `registerStandardUser` to shared helper.
- `README.md` (modified) — auth-routes table updated for the lockdown.

## Change Log

| Date | Version | Description |
| --- | --- | --- |
| 2026-06-06 | 0.1 | Locked down public `/auth/register` (removed endpoint + de-whitelisted), migrated all Epic 7/8.1 E2E specs to admin-endpoint user bootstrap via a shared helper, updated backend tests and README. All backend + E2E suites green. |
