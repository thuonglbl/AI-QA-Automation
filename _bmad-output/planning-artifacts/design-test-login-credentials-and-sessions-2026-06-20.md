# Test-Login Credentials & Browser Sessions — Design Recommendation

*For the AI QA pipeline (Alice → Bob → Mary → Sarah → Jack). Produced 2026-06-20 from a multi-agent codebase + Playwright/SSO research pass. **Status: core mechanism LIVE-VALIDATED 2026-06-20 (see below); implementation in progress (Slice 0).***

---

## 0. Validation (2026-06-20) — the mechanism is proven on a real managed machine

Hand-tested on Thuong's managed Windows 11 laptop against the real internal SSO app `https://[IP_ADDRESS]`, using Node Playwright (`connectOverCDP`):

1. **Corporate policy allows it.** Launching Chrome with `--remote-debugging-port=9222` exposed the CDP endpoint (`curl http://localhost:9222/json/version` returned the DevTools JSON). Remote-debugging is **not** blocked by managed-device policy.
2. **Capture works.** `connectOverCDP` + `context.storageState()` captured **33 cookies, 0 localStorage origins** — i.e. this app's auth is entirely **cookie-based**.
3. **Reuse works (the crux).** Injecting that blob into a brand-new, clean Chrome via `new_context({ storageState })` loaded `.../dashboard` **fully authenticated** — not bounced to the corporate SSO login. The captured session is genuinely portable across browser instances.

**Implications:** the `SSO_MANUAL` capture-once → reuse-blob model is confirmed for cookie-based corporate SSO; the sessionStorage/IndexedDB "blob insufficient" risk did **not** apply to this app. The three open questions are resolved: **policy = allows CDP**; **session lifetime = short & unpredictable** (VPN drop / wifi change / hours) → design must *validate-before-run and signal re-capture*, never assume longevity; **ownership scope = per-user** (each tester captures their own session; no project-shared store).

---

## 1. Mental model

The single most important insight: **the shared currency between Sarah (debug/selector capture) and Jack (run) is an authenticated *session*, not a login routine and not a live browser window.** A Playwright `storageState` JSON blob (cookies + localStorage, captured *after* a successful login) is the portable, reusable proof-of-authentication. We capture it once per (environment, role), encrypt it like any other per-user secret, and both Sarah and Jack rehydrate it into a fresh, isolated browser context via `new_context(storage_state=...)`. This means **we almost never automate the login itself** — for username/password apps we automate it once at *capture* time; for corporate SSO we let a human log in once and capture the result. The codebase already leans exactly this way: the script-generation prompts forbid login automation and hardcoded credentials and tell scripts to "assume a pre-authenticated session supplied at execution time" (`src/ai_qa/prompts/script_generation.py`); we are now defining the thing that *supplies* it.

---

## 2. Direct answers to the four concerns

### Concern 1 — Multiple roles, multiple test accounts per project

**Yes, and the model is one captured session per role, not one shared login.** Playwright's documented multi-role pattern is exactly this: separate `admin.json`, `user.json`, `guest.json` storageState files, each test selecting its role ([playwright.dev/docs/auth](https://playwright.dev/docs/auth)). So we key everything by **(project, environment, role)** and allow N test accounts per project. The mapping is flexible: one account that holds several roles → one session that satisfies several role checks; or one account per role → one session each. A single browser can hold multiple authenticated contexts simultaneously, which matters only if Jack ever needs two roles live in one test (e.g. admin approves what a user submitted).

> **Important distinction.** These **app-under-test roles** (Admin/User/Guest *of the customer's application*) are completely separate from the existing **`ProjectMembership.role` / `User.role`** (`src/ai_qa/db/models.py`), which govern *pipeline* access control (who can use Alice/Bob/Mary/Sarah/Jack). Do not overload those columns. App-under-test roles are a new, project-scoped concept.

### Concern 2 — Username/password apps vs corporate-SSO apps

**Both are handled by the same session-reuse model; only the *capture* step differs.** Add a per-(environment, role) **auth-method flag**:

| Auth method | How the session is captured |
| ------------ | ------------ |
| `PASSWORD` | Automated login routine fills stored username/password → captures storageState. |
| `SSO_MANUAL` | **Human logs in once** through the corporate IdP in a headed browser → app captures storageState. *(Default for corporate SSO.)* |
| `SSO_TOTP` | Automated login + TOTP code from a stored TOTP secret. *(Opt-in, per-app, security-approved only.)* |
| `API_TOKEN` | If the app exposes a token/API login, use it for the setup step (Playwright's preferred path). |

The customer app delegating to the corporate IdP does **not** change the run-time contract. Once we hold the storageState, Sarah and Jack are authenticated regardless of how the login happened.

### Concern 3 — Can Sarah-debug and Jack-run share one Chrome/Edge session?

**They should share the session *state*, not a live window — and that is better.**

- **Recommended:** Sarah captures/uses storageState; Jack rehydrates the *same encrypted blob* into its own fresh context. Identical code path → guaranteed parity, full isolation, works in CI, no human's browser must stay open. Playwright's intended hand-off.
- **Sharing one live Chrome/Edge window via CDP** is technically possible — the codebase already supports it (`src/ai_qa/agents/sarah.py` `cdp_url`; `src/ai_qa/browser/explorer.py` builds `BrowserProfile(cdp_url=...)` attaching to a Chrome started with `--remote-debugging-port=9222`). **But keep it as a capture/debug convenience only, never the run-time contract.** Chromium-only, known CDP limitations ([Playwright #15370](https://github.com/microsoft/playwright/issues/15370)), requires the human's browser running, no isolation — unsuitable for Jack's repeatable/CI runs.

### Concern 4 — Is SSO login automatable?

**Feasible in many cases, but for corporate IdP, do *not* fully automate it — capture once, manually.**

- Plain OAuth/SAML/OIDC redirects (Okta/Entra/Azure AD) are often scriptable — Playwright follows the IdP redirect and back ([Checkly](https://www.checklyhq.com/docs/learn/playwright/authentication/)).
- **But** push-MFA, hardware tokens, biometrics, conditional access, device compliance (typical of a corporate IdP) make scripted login brittle/impossible and can trip security controls. The universal recommendation there: **human one-time manual login → capture storageState → reuse the blob** ([browser-use auth](https://docs.browser-use.com/open-source/customize/browser/authentication)).

**Recommended fallback hierarchy:** (1) API/token login → (2) scripted UI login (password, or SSO+TOTP) → (3) **human one-time manual login + capture (the SSO+MFA default)** → (4) CDP-attach to a human's live session (debug-only, last resort).
**Do NOT:** automate push-MFA/biometrics/conditional-access; store the human's corporate domain password; make CDP-attach the run-time contract; assume "capture once, run forever" (corporate sessions are short-lived).

---

## 3. Recommended architecture

### What to store, and where

Two artifacts, both **per-user Fernet-encrypted secrets** in the existing `user_secrets` machinery (same pattern as the MCP key — `src/ai_qa/secrets/`):

1. **Browser session blob** (`storageState` JSON) — the primary currency. This blob *is* a live credential (it can impersonate the test account), so encrypt it like a password and **never** write it into scripts, logs, messages, or artifacts.
2. **Test-account credentials** (username/password, optional TOTP secret) — only for the `PASSWORD`/`SSO_TOTP` capture paths. For `SSO_MANUAL`, **store no credentials at all** — only the resulting session blob (a real security advantage: the SSO path never holds the corporate password or second factor).

> **Store the captured session blob, not (only) raw credentials.** Blobs work for SSO where credentials don't, and make Sarah↔Jack parity trivial.

### Keying model: `(project_id, environment, role_name)`

Reuse the just-added **`Project.environments`** (`{name, url}`) as the environment dimension; layer roles + accounts on top:

```
Project
 ├─ environments: [{name, url}]              # existing — the "where"
 └─ app_roles:    ["Admin", "User", "Guest"] # NEW — app-under-test roles (NOT ProjectMembership.role)

TestAccount  (NEW, project-scoped)
   project_id, environment_name, role_name,
   auth_method: PASSWORD | SSO_MANUAL | SSO_TOTP | API_TOKEN, label
   → credentials (if any) + session blob held as encrypted per-user secrets,
     keyed by (user_id, "browser_session::{project}::{env}::{role}")
   → metadata: captured_at, expires_at, last_validated_at
```

**Storage-shape change required.** `user_secrets.encrypted_value` is `UserSecretEncryptedString(1024)` (`src/ai_qa/secrets/models.py:35`); storageState blobs are 2–10 KB (larger after encryption) → **widen to TEXT / a dedicated table** before storing blobs. Use a **composite secret type** (`browser_session::{project}::{env}::{role}`) rather than the flat single-secret-per-type constraint today; non-secret metadata lives in the new `TestAccount` table, not inside the encrypted blob.

### How Sarah consumes it (debug / generation time)

A helper `resolve_session(user, project, env, role)` decrypts the blob → temp file → `new_context(storage_state=tmp)`. Sarah's existing exploration path (`src/ai_qa/browser/explorer.py`, `src/ai_qa/pipelines/script_generator.py`) already supports a pre-authenticated browser; feed it the rehydrated context instead of an ad-hoc running Chrome. Sarah keeps emitting credential-free scripts (prompts + static secret detectors in `src/ai_qa/pipelines/script_validator.py` enforce this) and **tags each generated script with the `(environment, role)`** it was built against (sidecar metadata, alongside `approved_by`/`approved_at`).

### How Jack consumes it (run time — Jack does not exist yet; Epic 15)

Jack calls the **same `resolve_session(...)`** using the `(env, role)` tag Sarah stamped, sets `APP_BASE_URL` from `Project.environments`, runs in a fresh context. Identical resolution = guaranteed parity. Before each run Jack **validates the session** (one cheap authenticated request); if stale, **fail loudly with a "re-capture needed" signal** rather than silently re-logging in.

---

## 4. The SSO path specifically (recommended `SSO_MANUAL` flow — the default)

1. User opens a **"Connect & Capture Session"** action for a `(project, environment, role)`.
2. App launches a **headed** Chrome or Edge (both support `--remote-debugging-port` + Playwright `connect_over_cdp` / browser-use `cdp_url`), or attaches via CDP to the user's own browser where corporate SSO already works.
3. The **human completes the full corporate IdP login once** (incl. MFA/biometrics) — no automation.
4. On success, app calls `context.storage_state()`, **encrypts** the blob (Fernet) into `user_secrets`, records `captured_at`/`expires_at`/`auth_method=SSO_MANUAL`.
5. Sarah and Jack thereafter rehydrate that blob — **no human in the loop again until it expires.**

Reusing the user's real profile (`user_data_dir` / browser-use `from_system_chrome()`) is fine *at capture time* (inherits existing corporate logins, passes 2FA implicitly), but the **durable artifact is always the exported storageState blob** so Jack/CI never need the human's profile.

---

## 4b. Capture-mechanism implementation note (added after backend recon)

**The backend has NO Playwright Python** — `browser-use` 0.13.1 drives Chrome via its own CDP client (no `playwright`/`patchright` package in `.venv`). The validated capture used **Node** Playwright (`frontend/node_modules/playwright` v1.60, `connectOverCDP().storageState()`). So the capture step needs a deliberate choice:

- **(Recommended) Add `playwright` Python to the backend purely for capture/resolve.** `connect_over_cdp(cdp_url).contexts[0].storage_state()` is exactly the validated flow; `connect_over_cdp` attaches to an already-running browser, so **no `playwright install` / browser binaries are required** — a light dependency. Cleanest and matches the proven path.
- *(Alt)* read cookies + localStorage straight from `browser-use`'s CDP session (`Network.getAllCookies` / `Runtime.evaluate`) — no new dep, but we hand-assemble the storageState shape.
- *(Avoid)* shelling out to the Node script from the backend.

For Sarah to *consume* a session at debug time, verify whether `browser-use` 0.13 accepts a `storage_state`/cookies input on its `BrowserProfile`/`BrowserSession`; if not, inject cookies via its CDP session before navigation. (Jack's run-time consumption is plain Playwright `new_context(storage_state=...)` — Epic 15.)

---

## 5. Phased plan

**Slice 0a — project-level config (DONE 2026-06-20):** `Project.environments` (done earlier) + **`Project.app_roles`** (app-under-test role names) — admin defines the (environment × role) matrix per project. Pure config, no browser dependency.

**Slice 0b — capture + resolve. BACKEND DONE 2026-06-20; FE + Sarah remaining.**

- **Done (backend, tested):** `playwright` Python added (connect-only); `UserSecretEncryptedText` (Fernet TEXT); `CapturedSession` table (migration `f1a9d3c75b62`) keyed `(user, project, environment, role)` with encrypted `storageState` + `auth_method` + `captured_at`/`expires_at`/`last_validated_at` — a dedicated per-user table (NOT the flat `user_secrets`, whose `secret_type String(50)` + single-value-per-type can't hold the composite key or 2–10KB blobs); `sessions/service.py` (save/list/`resolve_storage_state`/delete); `browser/session_capture.py` `capture_storage_state_over_cdp()` (async `connect_over_cdp().storage_state()`); `api/sessions.py` (`GET` matrix / `POST capture` / `DELETE`). Blob encrypted at rest + never serialized to the FE. 7 tests (round-trip + no-leak).
- **Remaining:** (1) **FE Sessions UI** — env×role matrix + Capture/Delete + the "launch Chrome/Edge with `--remote-debugging-port=9222`, log in, then Capture" instructions; (2) **Sarah consumption** — pick role, `resolve_storage_state`, inject the blob into the browser-use exploration (verify browser-use 0.13 accepts `storage_state`/cookies — needs live validation), tag generated scripts with (env, role). → then concerns 2, 3 (Sarah side), 4 are fully closed end-to-end.

**Slice 1 — `PASSWORD` auto-capture:** store user/pass encrypted per (env, role); automated login routine produces the blob. Covers non-SSO apps end-to-end.

**Slice 2 — Jack (Epic 15, depends on Jack being built):** reads script's (env, role) tag → `resolve_session()` → fresh context → run; sets `APP_BASE_URL`; validates freshness. → fully closes concern 3 (run side).

**Slice 3 — robustness & breadth:** session expiry + re-capture prompts; Edge support in the runner (currently Chromium-only); multi-role-in-one-test; optional `SSO_TOTP` (security-gated).

---

## 6. Open questions (blocking decisions)

1. **Managed-machine policy:** On managed laptops, may our app launch a headed Chrome/Edge with `--remote-debugging-port` (or attach via CDP) for the one-time SSO capture? If corporate browser policy forbids remote-debugging, we need an alternative capture UX before Slice 0.
2. **Session lifetime:** Corporate SSO sessions likely last hours — OK for testers to periodically re-do the one-time manual login (`SSO_MANUAL`), or prioritize `API_TOKEN`/`SSO_TOTP` for a specific high-frequency app?
3. **Credential ownership scope:** Sessions are stored **per-user** today. If two testers on the same project must run Jack against the same role, should each capture their own session, or do we need a **project-shared** session store (new scoping concept)?

---

### Flagged uncertainties

- **Schema capacity:** `user_secrets.encrypted_value` is `UserSecretEncryptedString(1024)`; storageState blobs won't fit → schema change required (high confidence).
- **Edge support:** browser-use exploration is **Chrome-only** today (`src/ai_qa/browser/explorer.py`); Edge for Sarah needs verification against the pinned browser-use version. Edge for Jack's Playwright runner is feasible (`msedge` channel) but unbuilt.
- **sessionStorage/IndexedDB:** `storageState` does not capture `sessionStorage` and IndexedDB capture is conditional — if a target app keeps its auth token there, the blob alone may be insufficient (verify per app).
- **"SSO 99% scriptable"** is for plain OAuth/SAML redirects; for MFA-enforcing IdP, assume `SSO_MANUAL` is the norm.

**Sources:** [Playwright auth](https://playwright.dev/python/docs/auth) · [browser-use auth](https://docs.browser-use.com/open-source/customize/browser/authentication) · [Checkly SSO/MFA](https://www.checklyhq.com/docs/learn/playwright/authentication/) · [Playwright CDP limits #15370](https://github.com/microsoft/playwright/issues/15370)
