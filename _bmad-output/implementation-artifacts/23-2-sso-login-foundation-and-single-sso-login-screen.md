---
baseline_commit: 0e05262e4d3e53e8bb60cd014effb430f91ad773
---
# Story 23.2: SSO Login Foundation and Single SSO-Only Login Screen

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Backend + frontend. This story stands up the **Azure Entra OIDC round-trip** and collapses the login UI to a **single "Sign in with SSO" button** (no email/password field). It mints the app's existing JWT session cookie from Entra claims, reusing `UserSession` + `SessionManager` unchanged. **Scope boundary:** this story logs in a user whose `User` row **already exists** (matched by email / `oid`); **first-login auto-provisioning + Azure-app-role → platform-role mapping is story 23.3.** Local password login still works in parallel until story 23.6 removes it (so we never lock ourselves out before SSO is proven end-to-end). The chosen mechanism follows the 23.1 spike verdict (topology A app-level OIDC vs B browser-side+cached-JWKS). Prior art: `git show 73980bf:src/ai_qa/api/auth/azure.py` (OAuth2 auth-code **+ PKCE** foundation — note it is **httpx-based**, NOT `msal`, so for topology A you may rewrite the exchange with the already-locked `msal` confidential client; reverted) and `frontend/src/components/auth/MicrosoftLoginButton.tsx`.

## Story

As an employee,
I want the login screen to offer a single "Sign in with SSO" button that authenticates me with my corporate Azure identity,
so that I sign in with my existing company account instead of a local password.

## Acceptance Criteria

1. **Azure SSO config in `AppSettings`.** Given the config pattern of the existing `claude_sso_*` block ([config.py:156-185](src/ai_qa/config.py:156)), when this story is implemented, then `AppSettings` ([config.py](src/ai_qa/config.py)) gains an `azure_sso_*` group: `azure_sso_tenant_id`, `azure_sso_client_id`, `azure_sso_client_secret` (server-side secret — never logged/returned to FE), `azure_sso_redirect_uri` (empty default → backend computes `/api/auth/sso/callback`), `azure_sso_scopes` (default `"openid profile email User.Read"`), `azure_sso_authority` (default `https://login.microsoftonline.com/{tenant}`), and `azure_sso_enabled` (bool). All have safe empty/false defaults so the suite and a no-SSO dev run are unaffected. The client secret follows the secret-handling rule (resolved server-side only).

2. **Backend SSO login + callback endpoints.** Given there is no user-login OIDC router today, when this story is implemented, then a new router (e.g. `src/ai_qa/api/auth/sso.py`, mirroring the recovered `azure.py` + the `claude_sso.py` flow shape) exposes: `GET /auth/sso/login` → builds the Entra authorization URL (auth-code + PKCE; `state` for CSRF) and redirects (or returns the URL for the FE to redirect to); `GET /auth/sso/callback` → validates `state`, exchanges `code` for tokens **per the 23.1 topology** (topology A: backend `msal` confidential-client exchange; topology B: backend receives a browser-obtained ID token to validate), validates the ID token signature/issuer/audience/expiry with `python-jose` against the tenant JWKS, and builds a `UserSession` from the claims. The router is registered in [app.py](src/ai_qa/api/app.py) next to the other auth routers ([app.py:158-171](src/ai_qa/api/app.py:158)).

3. **Claims → `UserSession` → app cookie.** Given a validated ID token, when the callback completes for an **existing** active user, then a `UserSession` is created via `SessionManager.create_session(...)` ([api/auth/session.py:87-110](src/ai_qa/api/auth/session.py:87)) populated from Entra claims: `email` from `preferred_username`/`upn`/`email`, `name`, `given_name`, `family_name`, `groups`, and the platform `role`/`user_id` loaded from the matched `User` row; and the app's HS256 JWT cookie (`aiqa_session`) is set via `get_cookie_settings()` ([api/auth/session.py:143-157](src/ai_qa/api/auth/session.py:143)). The session cookie + middleware (`request.state.user`) then work exactly as for local login — no change to `rbac.py`/middleware required.

4. **User matching (existing user only).** Given the callback receives validated claims, when an active `User` matches by the stable key (recommended: `oid`, with email as fallback — per 23.1), then that user is logged in; when **no** `User` matches, then this story returns a clear "account not provisioned" response (e.g. 403 with an actionable message) and does NOT create a user — **auto-provisioning is 23.3.** (After 23.3 lands, the no-match branch becomes "auto-provision".) This boundary keeps 23.2 reviewable on its own.

5. **Middleware allows the SSO paths.** Given the auth middleware's public-path allowlist ([api/auth/middleware.py:33-47](src/ai_qa/api/auth/middleware.py:33)), when this story is implemented, then `/auth/sso/login` and `/auth/sso/callback` are added to the unauthenticated allowlist (the user is not yet authenticated when hitting them), consistent with how `/auth/login` and `/auth/callback` are already public.

6. **Single SSO-only login screen (FE).** Given the current `LoginPage.tsx` renders an email + password form ([frontend/src/components/auth/LoginPage.tsx:144-186](frontend/src/components/auth/LoginPage.tsx:144)), when this story is implemented, then the page renders **only** a single "Sign in with SSO" button (English, App-UI-English-only) that navigates the browser to the SSO login endpoint; the email field, password field, and "Sign In" submit are removed. On callback success the FE lands authenticated (cookie set) and `AuthContext.refresh()` ([frontend/src/contexts/AuthContext.tsx:32-46](frontend/src/contexts/AuthContext.tsx:32)) picks up the user via `/auth/status` + `/auth/me`. Recover `MicrosoftLoginButton.tsx` from `git show 73980bf:frontend/src/components/auth/MicrosoftLoginButton.tsx` as a starting point if useful.

7. **Errors degrade gracefully.** Given the SSO round-trip can fail (state mismatch, token validation failure, backend egress blocked on air-gapped UAT, user not provisioned), when any failure occurs, then the FE shows a clear English error on the login screen (no stack traces, no token/secret in the message or logs) and the user can retry. A backend egress failure (UAT without proxy) maps to an actionable message ("SSO sign-in could not reach the identity provider") rather than a 500.

8. **Dev/E2E mock path (no live tenant required).** Given E2E and unit tests cannot reach a real Entra tenant (and air-gapped UAT may not either), when `azure_sso_authority`/tenant config is empty, then the router supports a **mock-IdP mode** mirroring `claude_sso.py`'s mock (`GET /auth/sso/authorize` renders/returns a dev login that issues a synthetic, signed-by-the-app token for an allowed domain) so the flow is testable without Microsoft. The existing E2E SSO assertions (which today only check the "Login SSO button renders" — memory `e2e-base-url-inline-comment-gotcha`) are updated to drive the single-button screen.

## Tasks / Subtasks

- [x] **Task 1 — Azure SSO settings (AC: 1)**
  - [x] Added the `azure_sso_*` field group to `AppSettings` ([config.py](src/ai_qa/config.py)) after the `claude_sso_*` block: `azure_sso_enabled`, `_tenant_id`, `_client_id`, `_client_secret`, `_redirect_uri`, `_scopes`, `_authority` (`{tenant}` template), `_allowed_email_domain`, `_jwks` (bundled-JWKS option). Empty/false defaults. Added the Azure block to `.env.example`. Client secret is server-side only (never logged/returned).

- [x] **Task 2 — SSO router: login + callback (AC: 2, 3, 4, 7)**
  - [x] Created `src/ai_qa/api/auth/sso.py` (topology A: `msal` confidential-client exchange + `python-jose` JWKS validation; bundled-JWKS option; mock-IdP for dev/CI/E2E). Adapted to the current `UserSession`/`SessionManager`. Dropped the prior art's unsafe `verify_signature=False` fallback.
  - [x] `GET /auth/sso/login`: real mode builds the authorize URL via `msal.initiate_auth_code_flow` (PKCE + state, stored in `_FLOWS` with TTL); mock mode redirects to the built-in `/auth/sso/authorize` form. Returns a 303 redirect.
  - [x] `GET /auth/sso/callback` (real) + `POST /auth/sso/callback` (mock): verify `state`; exchange/validate; match an existing active `User` (by email in 23.2; oid added in 23.3); on match build `UserSession` + set cookie + redirect `/`; on no-match redirect `/?sso_error=not_provisioned` (no user created). Egress/validation failures → safe `sso_error` redirect, never 500, no secret leak.
  - [x] Registered the router at root in [app.py](src/ai_qa/api/app.py) (next to the local auth router) so the FE navigates the browser straight to `/auth/sso/login`.

- [x] **Task 3 — Middleware allowlist (AC: 5)**
  - [x] Added `/auth/sso/login`, `/auth/sso/callback`, `/auth/sso/authorize` to `PUBLIC_PATHS` in [api/auth/middleware.py](src/ai_qa/api/auth/middleware.py).

- [x] **Task 4 — Single SSO login screen (AC: 6, 7)**
  - [x] Replaced the email/password form in [LoginPage.tsx](frontend/src/components/auth/LoginPage.tsx) with a single "Sign in with SSO" button (reused/relabeled `MicrosoftLoginButton.tsx`) → `window.location.assign('/auth/sso/login')`. Removed email/password state + handlers. Kept an error region that reads `?sso_error=` and maps codes → friendly English messages. **NB:** navigate to `/auth/sso/login` (root, Vite-proxied), not `/api/...` — the router is mounted at root like local auth, and the middleware allowlist is `/auth/sso/*`.
  - [x] `AuthContext.refresh()`/`checkAuthStatus()` picks up the session after redirect-back unchanged; no `useAuth`/`AuthContext` shape change.

- [x] **Task 5 — Mock-IdP dev/E2E path (AC: 8)**
  - [x] Implemented the mock branch in `sso.py` (authorize form + callback, `azure_sso_allowed_email_domain` restriction) — synthetic claims, no Microsoft/network.
  - [~] SSO e2e group update **deferred**: the `frontend/e2e/support/` helpers (`loginViaUI`, fixtures) are **absent from disk** (pre-existing uncommitted state; whole e2e changeset is uncommitted per memory `e2e-regroup-7-flow-groups`), so there is no runnable e2e to update here. The password-form removal means the e2e UI login must migrate to the mock-IdP single-button flow — that migration is **23.6's explicit scope** (e2e + CI de-password). Note: `verifyClaudeSsoLoginButton` (groups 4/5) targets the **Alice provider** Claude-SSO card, NOT user login — unaffected.

- [x] **Task 6 — Tests (all ACs)**
  - [x] Backend `tests/api/test_sso_api.py` (7 tests): login → mock authorize redirect with `state`; authorize renders the single-button form (no password field); callback for an existing user sets `aiqa_session` + `/auth/me` authenticates; no-match → `/?sso_error=not_provisioned`, no user created; inactive user rejected; unknown state → `state_mismatch`; allowed-email-domain enforced. `app.dependency_overrides` (no `mock.patch`).
  - [x] Frontend `LoginPage.test.tsx` (3 tests): renders exactly one SSO button + no password/email field; click navigates to `/auth/sso/login`; `?sso_error` renders the alert. `vi.spyOn(globalThis,"fetch")`, real `AuthProvider`.
  - [x] Ran: backend `uv run pytest` → **1850 passed** (coverage 85%); `ruff check`+`ruff format`; `uv run mypy src` → clean. Frontend `npm run typecheck` + `npm run lint` clean; `LoginPage.test.tsx` 3 passed.

## Dev Notes

### The session layer is already auth-source-agnostic — don't rebuild it

`UserSession` + `SessionManager` already encode/decode the app's own HS256 JWT cookie and carry `given_name`/`family_name`/`groups` ([api/auth/session.py:17-158](src/ai_qa/api/auth/session.py:17)). SSO only changes **how claims are obtained**; once you have a `UserSession`, `create_session` + `get_cookie_settings` mint the same cookie local login uses, and `AuthMiddleware` + `rbac.py` work unchanged. Do NOT introduce a parallel session/cookie scheme.

### Topology drives the callback internals (from 23.1)

- **Topology A (app-level OIDC):** the callback does the `msal` confidential-client code→token exchange (backend egress to `login.microsoftonline.com`). On UAT this needs the IT egress proxy (`HTTP(S)_PROXY`/`NO_PROXY`; `trust_env` already on — memory `uat-airgapped-egress-model-transfer`).
- **Topology B (browser-side + cached JWKS):** the FE (MSAL.js) obtains the ID token; the callback only **validates** it against bundled/cached signing keys so the backend makes no outbound call. If 23.1 picks B, Task 4 grows (FE acquires the token) and Task 2's "exchange" becomes "validate".

Implement to the 23.1 verdict; keep the token-validation step (issuer/audience/exp/signature) identical either way.

### Current behavior to PRESERVE (regression guardrails)

- **Local login keeps working this story.** Do NOT remove `/auth/login`, `authenticate_user`, or `password_hash` here — that is 23.6, sequenced after SSO is proven. Both paths coexist temporarily.
- **No secret leak.** The client secret and any token never appear in logs, responses, messages, or the FE. Log `.keys()`/safe ids only ([project-context.md](project-context.md)).
- **Cookie/middleware contract unchanged.** Same cookie name (`aiqa_session`), same `request.state.user` population, same 401-JSON-for-`/api` vs 307-redirect behavior ([api/auth/middleware.py](src/ai_qa/api/auth/middleware.py)).
- **`claude_sso.py` is untouched** — it is provider auth, a different concern; only mirror its mock-flow structure.

### Source tree components to touch

- `src/ai_qa/config.py` — **UPDATE** (`azure_sso_*` settings).
- `src/ai_qa/api/auth/sso.py` — **ADD** (login + callback + mock router).
- `src/ai_qa/api/app.py` — **UPDATE** (register router).
- `src/ai_qa/api/auth/middleware.py` — **UPDATE** (public-path allowlist).
- `frontend/src/components/auth/LoginPage.tsx` — **UPDATE** (single SSO button; remove password form).
- `.env.example` — **UPDATE** (Azure block).
- Tests — **ADD** (backend SSO router; FE LoginPage; e2e SSO group update).

### Decided scope (defaults — Thuong, correct if needed)

- **23.2 logs in EXISTING users only**; the no-match branch is a placeholder 403 until 23.3 turns it into auto-provision. This keeps the story bounded and reviewable.
- **Mock-IdP mode** is mandatory for testability (mirror `claude_sso.py`) — no live Entra tenant required for the suite/E2E.
- **One SSO button, password form removed** — matches Thuong's "chỉ 1 nút login SSO".

### Testing standards summary

- Backend pytest, whole-suite run; FastAPI deps via `app.dependency_overrides` + `try/finally`. No bare `pytest.raises(Exception)`.
- FE Vitest 4: `vi.mock` hoisting + `importOriginal()` to preserve `AuthProvider`; prefer `vi.spyOn(globalThis,"fetch")`.
- E2E: no `page.route` mocking; the SSO group asserts the single-button screen + (mock) round-trip.

### Project Structure Notes

- No schema change in this story (no migration). 23.3 may add `User.azure_oid` / `User.roles`; 23.6 drops `password_hash`. Sequence: 23.2 (login) → 23.3 (provision/roles) → … → 23.6 (drop passwords).

### References

- Epic + story: [epics.md#Epic-23](_bmad-output/planning-artifacts/epics.md:2371), [Story 23.2](_bmad-output/planning-artifacts/epics.md:2389)
- Prior art: `git show 73980bf:src/ai_qa/api/auth/azure.py`, `git show 73980bf:frontend/src/components/auth/MicrosoftLoginButton.tsx`, `git show 73980bf:.env.example`
- Session + cookie: [api/auth/session.py:17-158](src/ai_qa/api/auth/session.py:17)
- Local login (coexists this story): [api/auth/local.py:74-158](src/ai_qa/api/auth/local.py:74)
- Middleware allowlist: [api/auth/middleware.py:33-47](src/ai_qa/api/auth/middleware.py:33); router registration: [api/app.py:158-171](src/ai_qa/api/app.py:158)
- Config pattern: [config.py:156-185](src/ai_qa/config.py:156) (claude_sso block); deps [pyproject.toml:24-25](pyproject.toml:24)
- Mock-IdP pattern to mirror: [api/claude_sso.py](src/ai_qa/api/claude_sso.py)
- FE login: [frontend/src/components/auth/LoginPage.tsx](frontend/src/components/auth/LoginPage.tsx); auth lib [frontend/src/lib/auth.ts:80-122](frontend/src/lib/auth.ts:80); API base [frontend/src/lib/api.ts:34-44](frontend/src/lib/api.ts:34)
- Coding/security/testing rules: [project-context.md](project-context.md)
- Related memories: [[epic-23-sso-first-auth]], [[uat-airgapped-egress-model-transfer]], [[e2e-base-url-inline-comment-gotcha]], [[app-ui-english-only]]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (BMAD dev-story)

### Debug Log References

- `uv run pytest tests/api/test_sso_api.py --no-cov` → 7 passed; full `uv run pytest` → 1850 passed.
- `npx vitest run src/components/auth/LoginPage.test.tsx` → 3 passed; `npm run typecheck` + `npm run lint` clean.

### Completion Notes List

- **Topology A implemented per the 23.1 spike** with three modes behind one validation contract: real (`msal` confidential-client exchange + `python-jose` JWKS), bundled-JWKS (zero-egress validation when `azure_sso_jwks` is set), and mock IdP (default when the tenant/client/secret triple is empty — no Microsoft, no network). The mock path is what CI/E2E exercise.
- **Router mounted at root** (`/auth/sso/*`) like the local auth router, so the FE does a full-page `window.location.assign('/auth/sso/login')` and the dev Vite proxy (`/auth` → backend) forwards it with the app-origin cookie. Mock paths are root-relative for the same reason (mirrors `claude_sso.py`).
- **Existing-user-only boundary (23.2):** the no-match branch redirects to `/?sso_error=not_provisioned` and creates **no** user. 23.3 replaces that branch with auto-provisioning. I chose an **error-redirect** over a raw 403 because the callback is a full-page browser redirect — a JSON 403 would render as a bare blob; the redirect lets the SPA `LoginPage` show a friendly English message (still "does NOT create a user", AC4 intent preserved).
- **Local password login is untouched** (`/auth/login`, `authenticate_user`, `password_hash`) — both paths coexist until 23.6. `claude_sso.py` (provider auth) is untouched; only its mock-flow structure was mirrored.
- **No secret leak:** the client secret is never logged/returned; failures log `type(exc).__name__` only and map to safe `sso_error` codes.
- **E2E:** not modified — the `frontend/e2e/support/` helpers are absent on disk (pre-existing uncommitted state); the e2e UI-login migration is 23.6's scope. Live Azure round-trip is a deploy-time follow-up (23.1 §7); the mock IdP is the CI-proven equivalent.

### File List

- `src/ai_qa/config.py` — UPDATED (`azure_sso_*` settings group).
- `src/ai_qa/api/auth/sso.py` — ADDED (login + callback + mock IdP router; msal exchange + jose JWKS validation).
- `src/ai_qa/api/app.py` — UPDATED (import + register `sso_router` at root).
- `src/ai_qa/api/auth/middleware.py` — UPDATED (allowlist `/auth/sso/login|callback|authorize`).
- `.env.example` — UPDATED (Azure SSO block).
- `frontend/src/components/auth/LoginPage.tsx` — UPDATED (single SSO button; password form removed; `?sso_error` handling).
- `frontend/src/components/auth/MicrosoftLoginButton.tsx` — ADDED (recovered from `73980bf`, relabeled "Sign in with SSO").
- `tests/api/test_sso_api.py` — ADDED (7 backend SSO router tests).
- `frontend/src/components/auth/LoginPage.test.tsx` — ADDED (3 FE LoginPage tests).

### Change Log

- 2026-06-25 — Story 23.2: Azure SSO login foundation + single SSO-only login screen. Backend `sso.py` (msal/jose/mock-IdP), config, middleware allowlist; FE single SSO button. Existing-user-only (no-match → not-provisioned redirect; provisioning is 23.3). Suite green (1850 BE / FE LoginPage 3). Status → review.
