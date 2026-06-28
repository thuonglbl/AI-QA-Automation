# Investigation: Interactive MFA login fails (test-credentials "Save & Test Login")

## Hand-off Brief

1. **What happened.** The new Interactive-MFA "Save & Test Login" flow fails against `pttool-dev.corpdev.local`; the
   browser never pauses to ask for a code. **Confirmed** the target is Microsoft Entra ID (Azure AD) OIDC — `GET /`
   302-redirects to `login.microsoftonline.com/.../oauth2/v2.0/authorize`.
2. **Where the case stands.** Root cause **Confirmed/Deduced**: the raw-Playwright state machine in
   `src/ai_qa/browser/login.py` (a) only detects an OTP **input box** that never appears under Entra's default
   number-matching/push MFA, and (b) even on the "enter a code" screen, its OTP selector
   (`input[name*='code'|'token'|'totp']`) does **not** match Microsoft's real field `input[name='otc']`. So
   `wait_for_mfa()` / the `MFA_REQUIRED` broadcast is never reached; the loop spins to the 30s `browser_timeout` and
   the login is reported failed. Secondary: `browser_timeout` default is **30s**, too short to span a human MFA entry.
3. **What's needed next.** Decide the fix direction (see Recommended Next Steps) — Entra-aware MFA detection
   (number-matching handling + correct `otc` selector) plus raising the login timeout for the interactive path.

## Case Info

| Field            | Value                                                                                      |
| ---------------- | ------------------------------------------------------------------------------------------ |
| Ticket           | N/A (uncommitted feature: Interactive MFA)                                                  |
| Date opened      | 2026-06-27                                                                                  |
| Status           | Active                                                                                      |
| System           | Windows 11; backend FastAPI (py3.14); target = ASP.NET Core + Entra ID OIDC                 |
| Evidence sources | Uncommitted source (`login.py`, `mfa_manager.py`, `test_login.py`, `auto_login.py`, FE), live `curl` of target, config defaults |

## Problem Statement

User report (verbatim, paraphrased): the uncommitted code implementing the Interactive MFA feature still does not
work — login fails. Domain `https://pttool-dev.corpdev.local/`, user `thuong.lambale@corp-dev.com`. Screenshot shows
the "Test Credentials" dialog returning **"Credentials saved, but login test failed. Login failed. Please check your
credentials."** with the TOTP Secret field left blank (the intended Interactive-MFA trigger).

## Evidence Inventory

| Source                                   | Status    | Notes                                                                                  |
| ---------------------------------------- | --------- | -------------------------------------------------------------------------------------- |
| `src/ai_qa/browser/login.py` (modified)  | Available | New 30-step state-machine loop incl. Interactive MFA block (`login.py:181-216`)        |
| `src/ai_qa/sessions/mfa_manager.py` (new)| Available | In-memory `asyncio.Future` store; `wait_for_mfa` (120s), `submit_mfa`                  |
| `src/ai_qa/api/test_login.py` (modified) | Available | `/test-credentials/test-login` + `/submit-mfa`; calls `resolve_or_generate` w/o `llm` |
| `src/ai_qa/sessions/auto_login.py`       | Available | `llm=None` → routes to `_login_with_playwright` (raw)                                  |
| `frontend/.../InteractiveMFAPrompt.tsx`  | Available | Renders MFA modal; POSTs `/submit-mfa`                                                 |
| `frontend/src/App.tsx:1197-1206, 3141`   | Available | `handleSystemMessage` → `MFA_REQUIRED` → renders prompt                                |
| `src/ai_qa/api/websocket.py:446`         | Available | `broadcast_message` routes by `project_id`; thread filter skipped when absent          |
| `src/ai_qa/config.py:251-256`            | Available | `chrome_path` default `""`; `browser_timeout` default **30**                            |
| Live `curl https://pttool-dev.../`       | Available | **302 → login.microsoftonline.com/57989ee3-…/oauth2/v2.0/authorize** (Entra OIDC)      |
| Live Entra MFA page DOM                   | Missing   | Not scraped (requires completing SSO+MFA); `otc` field name asserted from MS knowledge |
| Backend runtime logs for the failed run  | Missing   | Backend not running on :8000 at investigation time; would pinpoint exception vs timeout |

## Confirmed Findings

### Finding 1: Target is Microsoft Entra ID OIDC, not a simple form

**Evidence:** `curl -i https://pttool-dev.corpdev.local/` → `302 Found`, `Location:
https://login.microsoftonline.com/57989ee3-4a14-44f1-8455-33eaabb38c12/oauth2/v2.0/authorize?...response_mode=form_post`
+ `.AspNetCore.OpenIdConnect.*` cookies.

**Detail:** Login is the full Microsoft hosted flow: email page → password page → **MFA** (Authenticator). Selectors
and screen sequence are Microsoft's, not the target app's.

### Finding 2: test-login always uses the raw-Playwright path (where Interactive MFA lives)

**Evidence:** `test_login.py:86` calls `resolve_or_generate_storage_state(...)` with no `llm`; `auto_login.py:92`
forwards `llm=None`; `login.py:54-59` → `llm` falsy → `_login_with_playwright`. The Interactive-MFA block
(`login.py:187-216`) exists ONLY in `_login_with_playwright` (the browser-use path `login.py:62-101` has no
interactive MFA). So the test dialog correctly reaches the interactive path — the defect is inside it.

### Finding 3: OTP-input selector cannot match Microsoft's code field

**Evidence:** `login.py:182` — `page.locator("input[name*='code'], input[name*='token'], input[name*='totp']")`.
Microsoft's verification-code input is `<input name="otc" id="idTxtBx_SAOTCC_OTC" type="tel">`. `"otc"` contains
none of `code` / `token` / `totp`.

**Detail:** Step 6 (`login.py:183`) is the ONLY trigger for the `MFA_REQUIRED` broadcast + `wait_for_mfa()`. If its
locator never becomes visible/matched, the interactive prompt is **never** shown and the browser never pauses.
Graded Confirmed (code) + Deduced (field name from Microsoft's well-known login DOM; see Missing Evidence).

### Finding 4: `browser_timeout` default 30s bounds the whole login, too short for human MFA

**Evidence:** `config.py:254` `browser_timeout: int = Field(default=30, ...)`; `test_login.py:93` passes it as
`timeout`; `login.py:125` `while time.time() - start_time < timeout`.

**Detail:** The outer loop budget is 30s. `wait_for_mfa` (`mfa_manager.py:20`) waits up to 120s independently, but the
moment it returns past the 30s mark the `while` exits before the post-MFA submit/redirect is verified — the happy
path is racy even if Steps 5-6 were fixed.

## Deduced Conclusions

### Deduction 1: The interactive MFA prompt is never triggered for this target

**Based on:** Findings 1, 3.

**Reasoning:** Entra's default second factor for Microsoft Authenticator is **number matching / push approval** — a
number is shown on the web page to be typed INTO the phone app; there is **no code input field** on the page. The
state machine has no handler for that screen (Steps 4-7 don't match it), so it falls through to the Step 8 success
check; the URL is still `login.microsoftonline.com` (contains `"login."`), so it does not break either — it just
loops. To reach a 6-digit-code screen at all, the flow must click "I can't use my Microsoft Authenticator app right
now" → "Use a verification code"; even if those brittle text clicks succeed, Finding 3 means the resulting `otc`
field is not detected.

**Conclusion:** `wait_for_mfa()` is never awaited → no `MFA_REQUIRED` WS message → the user never sees the prompt →
the loop runs out the 30s budget → login fails / captures an unauthenticated session.

### Deduction 2: The reported failure surfaces as either a click-timeout exception or a silent empty session

**Based on:** Findings 1-4 + control flow.

**Reasoning:** Two terminal shapes: (a) a `page.click(...)` (Step 1/3/5, `timeout=5000`) targets a button that isn't
present on some Microsoft screen → raises → `except Exception` (`login.py:234`) → `BrowserError` →
`resolve_or_generate` returns `None` (`auto_login.py:99-101`) → `test_login` returns the "No test credentials found…"
error; OR (b) the loop simply hits 30s, exits, and `context.storage_state()` returns an **unauthenticated** blob that
is wrongly cached + reported `success=True`. The FE "Login failed. Please check your credentials." string
(`SarahInputsForm.tsx:214`) is the fallback shown when `result.success===false` and `result.error` is empty.

**Conclusion:** Exact terminal message depends on which Microsoft screen the clicks stall on (needs runtime logs), but
in all branches the Interactive-MFA pause never occurs — the feature does not function for an Entra target.

## Hypothesized Paths

### Hypothesis 1: Entra tenant uses number-matching push as the default MFA (no code field)

**Status:** Open (very likely)

**Theory:** The tenant's default Authenticator method is number matching, so the bot reaches a screen with no input
and no matching fallback text → indefinite spin until timeout.

**Would confirm:** Run the flow with backend logs / non-headless screenshot at the MFA step; observe "Approve sign in
request" + number, no input box.

**Would refute:** The MFA screen presents a 6-digit code box directly (then Finding 3 alone is the blocker).

### Hypothesis 2: `chrome_path` is empty in the running backend

**Status:** Open

**Theory:** `config.py` default is `""` and no `.env` chrome entry was found; if unset at runtime,
`p.chromium.launch(executable_path="")` (`login.py:115`) fails immediately → BrowserError → failure before any MFA.

**Would confirm:** Print resolved `settings.chrome_path` at startup / check the backend's env. (User runs Sarah
explore which also needs Chrome, so it is probably set — verify.)

**Would refute:** A valid Chrome path is configured in the backend environment.

## Missing Evidence

| Gap                                   | Impact                                                        | How to Obtain                                      |
| ------------------------------------- | ------------------------------------------------------------ | -------------------------------------------------- |
| Live Entra MFA screen DOM/field names | Confirms Finding 3 (`otc`) + Hypothesis 1 (number matching)  | Run login non-headless or screenshot at MFA step    |
| Backend logs of the failed test-login | Distinguishes Deduction 2 (a) click-timeout vs (b) silent 30s| Run backend, retry, capture `login.py` log lines    |
| Resolved `settings.chrome_path`       | Confirms/refutes Hypothesis 2                                 | Log it at startup or inspect backend env            |

## Source Code Trace

| Element       | Detail                                                                                            |
| ------------- | ------------------------------------------------------------------------------------------------ |
| Error origin  | `src/ai_qa/browser/login.py:182-183` (OTP selector never matches Entra `otc`) + no number-match handler |
| Trigger       | FE "Save & Test Login" → `POST /api/projects/{id}/test-credentials/test-login` (`test_login.py:66`) |
| Condition     | Target = Entra OIDC; TOTP secret blank → meant to hit interactive path; MFA screen not detected   |
| Related files | `auto_login.py`, `mfa_manager.py`, `api/websocket.py` (broadcast), `config.py` (timeout), `App.tsx` (FE) |

## Conclusion

**Confidence:** High (mechanism Confirmed/Deduced); Medium only on which exact terminal message appears.

The Interactive-MFA "Test Login" cannot work against `pttool-dev.corpdev.local` because that target authenticates via
**Microsoft Entra ID**, and the raw-Playwright state machine never detects the Entra MFA screen: it has no handler for
the default number-matching/push experience, and its OTP-input selector (`name*='code'|'token'|'totp'`) does not match
Microsoft's actual field (`name='otc'`). Therefore `wait_for_mfa()` and the `MFA_REQUIRED` broadcast are never reached,
the user is never prompted, and the 30s `browser_timeout` elapses → login fails. `browser_timeout=30` is independently
too short for a human-in-the-loop MFA entry.

## Recommended Next Steps

### Fix direction

1. **Detect Entra MFA correctly (root cause).** Add the Microsoft OTP field to Step 6:
   `input[name='otc'], #idTxtBx_SAOTCC_OTC, input[type='tel'][name*='otc'], input[name*='code'], input[name*='token'], input[name*='totp']`.
2. **Handle number-matching/push.** When the page shows "Approve sign in request" / a displayed number and no input,
   either (a) click the "I can't use my Microsoft Authenticator app right now" → "Use a verification code" path
   (already partially attempted at `login.py:165-179` — verify the real link text) to force the code screen, or
   (b) surface the displayed number to the user via a richer `MFA_REQUIRED` payload. Decide which UX you want.
3. **Raise the interactive timeout.** The login budget must exceed `wait_for_mfa` (≥150s) for the interactive path,
   or decouple the MFA wait from the outer loop budget so the 30s `browser_timeout` doesn't truncate it.
4. **Don't report success on an unauthenticated capture.** After the loop, assert real authentication (URL left
   `login.microsoftonline.com` AND landed on `pttool-dev.corpdev.local/...`) before caching/returning success.

### Diagnostic

- Run the backend with the modified code, retry "Save & Test Login" with a **non-headless** browser (or add a
  screenshot/`page.content()` dump at each loop iteration) to capture the exact Entra MFA screen and confirm the
  `otc` field + number-matching hypothesis.
- Log resolved `settings.chrome_path` and the precise exception/timeout branch in `_login_with_playwright`.

## Reproduction Plan

1. Configure a `TestAccountCredential` for project "Test VN" / role "Super Admin", username
   `thuong.lambale@corp-dev.com`, password set, **TOTP secret blank**.
2. Ensure backend `chrome_path` points to a real Chrome; start backend.
3. In the Sarah inputs form, open Test Credentials → "Save & Test Login".
4. Observe: no MFA modal appears; after ~30s the dialog shows login failed. (Expected after fix: modal prompts for a
   6-digit code, accepts it, login succeeds and session is cached.)

## Side Findings

- `login.py:176` `text='I can\'t use my Microsoft Authenticator app right now'` — exact-text match is brittle across
  Entra UI revisions/locales; prefer role/`data-value` or partial text.
- `login.py:227` success heuristic `"login." not in url and "oauth" not in url and "auth" not in url` is fragile: a
  generic app whose post-login path contains `auth` would never break, and an app whose login path lacks those tokens
  could break prematurely (false success). Not the cause here, but a latent bug.
- Step 1 (`login.py:132-138`) `continue`s whenever the email/username field is *visible* regardless of whether it
  filled — on a **single-page** username+password form it would loop on Step 1 and never fill the password. Not
  triggered for this Entra target (two-step), but a real bug for non-Microsoft form logins.
- `broadcast_message` routes the MFA message by `project_id` only (thread filter skipped when absent) — fine, but it
  fans out to every connection in the project; verify the FE WS is project-scoped when on the Sarah form so the modal
  actually appears once Step 6 is fixed.

## Follow-up: 2026-06-28

### New Evidence (live reproduction with real credentials)

A standalone Playwright repro (`scratchpad/mfa_repro.py`) drove the **real** Entra login for
`thuong.lambale@corp-dev.com` against `pttool-dev.corpdev.local`, **both headful and headless**, dumping each screen's
DOM + screenshots (no secret values printed).

1. **`chrome_path` is empty AND empty path is fatal — CONFIRMED (High).** `AppSettings().chrome_path` resolves to
   `''` (no `CHROME_PATH` in `.env` or OS env; `env_prefix=''`). `chromium.launch(executable_path='')` raises
   **`BrowserType.launch: Failed to launch: Error: spawn . ENOENT`**. This is a **first-order blocker**: "Save & Test
   Login" crashes at browser launch and never reaches the target site — independent of any MFA logic.
2. **The real login is passwordless-push-first, but password alone completes it — CONFIRMED (High).** Observed screen
   sequence: email (`input[name=loginfmt]`) → **passwordless push** screen (live text: *"Request wasn't sent. We
   couldn't send a notification at this time… Use your password instead"*, link `#idA_PWD_SwitchToPassword`, plus a
   `Next`/`#idSIButton9` resend) → after clicking "Use your password instead", **password** page
   (`input[name=passwd]`, also offers `#idA_PWD_SwitchToRemoteNGC` "Use an app instead") → redirect to
   **`https://pttool-dev.corpdev.local/dashboard` = fully authenticated**. **No 6-digit code / number-matching code was
   ever required**, in either headless or headful mode.
3. **Seamless/desktop SSO is attempted first** ("Trying to sign you in", `#desktopSsoCancel`) before the email form
   appears — the state machine must tolerate this transient screen.

### Additional Findings

- **The empty-`chrome_path` bug is broader than test-login.** `jack.py:557` calls
  `resolve_or_generate_storage_state(..., chrome_path="")` (hardcoded empty, raw-Playwright path) → same
  `spawn . ENOENT` when it must generate (not reuse cached) a session. `test_login.py:92` uses `settings.chrome_path`
  (empty). **`sarah.py:461` is protected**: it passes `self._chrome_path` (from the frontend form) **and** an `llm`,
  so it uses the browser-use path with a real Chrome path.
- **The interactive 6-digit MFA machinery is not exercised by this account.** `mfa_manager.py` / `InteractiveMFAPrompt`
  / the `otc` selector gap are all moot here because password-only login succeeds. They would only matter for a
  tenant/account that actually enforces a typed code as a second factor.

### Updated Hypotheses

- **Hypothesis 1 (Entra default = number-matching/push):** **Confirmed** — the default factor is Authenticator push
  (passwordless). But it is **not** a typed-code gate; the password path bypasses it. So the original "interactive MFA
  code never fires" concern is real yet *irrelevant* to making login succeed for this account.
- **Hypothesis 2 (`chrome_path` empty):** **Confirmed** — and it is the actual first-order cause of the failure.

### Backlog Changes

- Add: verify whether Jack's auto-login (`jack.py:557` empty `chrome_path`) fails the same way in environments where it
  must generate a fresh session vs. reuse a cached `role_session`.
- Add (blocked): independent adversarial verification workflow (`verify-mfa-login-diagnosis`) was launched but its 4
  subagents aborted on a **session/usage limit** (resets ~01:40 Asia/Saigon) — re-run later to cross-check.
- Residual: my repro and the backend differ only in headless flag (both tested → same result) and in browser context
  freshness; production may reuse a cached `storage_state`, which would mask the launch bug until cache expiry.

### Updated Conclusion

**Confidence: High.** The "Save & Test Login" failure is caused **first** by an empty `chrome_path` →
`chromium.launch(executable_path='')` → `spawn . ENOENT`, so the browser never launches. Live reproduction proves the
target's real login is satisfiable by **email + password alone** (no typed MFA code), in both headless and headful
Chrome. The interactive-MFA code path (and its `otc`/number-matching/30s-timeout defects from the initial analysis) is
therefore **not required** to make this account's login work — those defects only matter for a tenant that enforces a
typed code. **Minimum fix to make the feature work:** give the login routine a real/bundled Chrome
(`executable_path=chrome_path or None`, or resolve via `BrowserSession.get_chrome_path()`), and ensure the state
machine reliably takes the "Use your password instead" → password branch (Step 4 already does). Revisit the interactive
6-digit MFA only for accounts that genuinely require a typed code.

### Revised Fix Direction (supersedes the initial list where they conflict)

1. **[P0] Fix Chrome launch.** In `browser/login.py` use `executable_path=chrome_path or None` in **both**
   `_login_with_playwright` (`login.py:115`) and `_login_with_browser_use` (`login.py:85`) so an empty path falls back
   to Playwright's bundled Chromium; and/or have `test_login.py` resolve a real path via `BrowserSession.get_chrome_path()`
   instead of raw `settings.chrome_path`. Apply the same to `jack.py:557`.
2. **[P1] Make the password-fallback branch robust.** Confirm Step 4 ("Use your password instead",
   `#idA_PWD_SwitchToPassword`) and a "Use an app instead"/`Sign in another way` handler reliably reach the password
   field across Entra UI variants; tolerate the seamless-SSO "Trying to sign you in" transient.
3. **[P2] Don't report success on an unauthenticated capture** — assert the final URL is on `pttool-dev.corpdev.local`
   (left `login.microsoftonline.com`) before caching/returning success (`login.py:227` heuristic is too loose).
4. **[P2] Only if a code-MFA account is in scope:** fix the OTP selector (`input[name='otc'], #idTxtBx_SAOTCC_OTC`),
   decouple `wait_for_mfa` from the 30s `browser_timeout`, and handle the number-matching-succeeds screen (which a bot
   cannot complete without a TOTP secret).

### Resolution — P0 implemented & verified (2026-06-28)

- **Change:** `browser/login.py` now launches with `executable_path=chrome_path or None` in both
  `_login_with_playwright` (`login.py:119`) and `_login_with_browser_use` (`login.py:87`) — an empty path falls back to
  Playwright's bundled Chromium instead of crashing with `spawn . ENOENT`. Bonus gate fix: `mfa_manager.py:25` annotated
  `future: asyncio.Future[str]` (cleared a `mypy src` `no-any-return`). Gates green: `ruff check` / `ruff format` /
  `mypy src` all pass.
- **End-to-end verification (real code path):** called `generate_session_storage_state(credential, login_url,
  chrome_path="", llm=None, timeout=30)` (i.e. exactly what `test_login.py` invokes) against the live target. Result:
  27-cookie storageState including target-domain auth cookies `PT.Auth`, `PT.AuthC1/2/3`, `.AspNetCore.Antiforgery`,
  plus `ESTSAUTH*` — **VERDICT: AUTHENTICATED**, within the 30s budget, no typed MFA code. P0 confirmed to unblock the
  feature for this account.
- **Status:** P0 done. Backend has no auto-reload — restart required for the change to take effect.

### Resolution — P1 + P2 implemented & verified (2026-06-28)

All in `browser/login.py` (state machine rewritten; gates green: `ruff` / `mypy src` / 9 unit tests pass):

- **[P1] Robust password-fallback + Entra navigation.** "Use your password instead" is matched by stable id first
  (`#idA_PWD_SwitchToPassword`) with a `.or_(get_by_text(...))` fallback; the number-matching escape ("I can't use my
  Authenticator app" / "Use a verification code" / `#idA_PWD_SwitchToCredPicker`) is likewise id+text. Seamless-SSO
  ("Trying to sign you in") is tolerated (no step matches → loop waits it out). Interactive-MFA block extracted to
  `_prompt_interactive_mfa`.
- **[P2a] Success is now positive + asserted.** Replaced the loose `"login."/"oauth"/"auth"` substring break with
  `urlparse(page.url).netloc == target_host` (landed back on the app's own host). If the loop never reaches the app,
  it raises `BrowserError("Login did not reach the authenticated app …")` instead of caching an unauthenticated
  session as success.
- **[P2b] Code-MFA path fixed (not live-validated — this account needs no typed code).** OTP selector now includes
  Microsoft's real field `input[name='otc'], #idTxtBx_SAOTCC_OTC, input[autocomplete='one-time-code']`. The
  interactive MFA wait is decoupled from the automation budget: `wait_for_mfa(..., timeout_seconds=180)` and
  `start_time` resets after the code is submitted so post-MFA navigation gets a fresh window.
- **Verification.** (1) Real code-path regression: `generate_session_storage_state(chrome_path="", timeout=30)` against
  the live target → 27 cookies incl. `PT.Auth*` → **AUTHENTICATED**. (2) New failure-assertion: bogus username →
  `BrowserError: Login did not reach the authenticated app 'pttool-dev.corpdev.local' … (still at
  'login.microsoftonline.com')`. (3) Unit tests updated (`test_login_with_playwright_success` → host-based) + added
  (`test_login_with_playwright_raises_if_never_authenticated`).
- **Open (not in scope of this fix):** the number-matching-**succeeds** push screen still cannot be completed by a bot
  without a TOTP secret (no typed input to fill) — for fully-unattended runs on a code-MFA account, configure the TOTP
  secret. `jack.py:557` still passes a hardcoded empty `chrome_path` (now harmless thanks to the `or None` fallback in
  `login.py`, but worth a deliberate decision).

## Follow-up: 2026-06-28 #2 — SEPARATE issue: app's own SSO went to a personal account

**Symptom (different from above):** Clicking "Sign in with SSO" on the AI QA app (localhost:5173) landed on
`login.live.com` with the personal account `thuong.lambale@gmail.com` instead of the corporate
`thuong.lambale@corp-dev.com`. This is the **app's own** Entra OIDC login (Epic 23), not the pttool target login.

### Findings (Confirmed)

- The frontend SSO button just navigates to the backend: `LoginPage.tsx:55` → `window.location.assign("/auth/sso/login")`
  (no client-side MSAL / no client id in the frontend — `frontend` grep clean).
- The backend builds the authorize URL via MSAL `initiate_auth_code_flow` (`sso.py:386` `sso_login`) using
  `settings.azure_sso_client_id` + `_authority()`.
- **The running backend is already correctly configured.** PID 35488 started 2026-06-28 08:22 (AFTER `.env` mtime
  2026-06-27 17:06); querying it live, `GET /auth/sso/login` → `302 Location:
  https://login.microsoftonline.com/57989ee3-…/oauth2/v2.0/authorize?client_id=43587c64-…` (company tenant + company
  app, tenant-pinned — not `/common`, not `login.live.com`).
- **The screenshot is stale config.** Its URL used `login.live.com` + `client_id=51483342-085c-4d86-bf88-cf50c7252078`,
  a client id that exists **nowhere** in the repo or current `.env`/settings — an earlier app registration from before
  the backend was last started.
- **Behavioral root cause for the personal-account pickup:** the authorize request sent **no `prompt`**, so Microsoft
  silently reused the browser's cached personal MSA (gmail) session.

### Fix (implemented + verified)

`sso.py` `sso_login` now passes `prompt="select_account"` (always show the account picker — never silently reuse a
cached personal account) and `domain_hint=<azure_sso_allowed_email_domain>` (= `corp-dev.com`, routes home-realm
discovery straight to the corporate IdP, skipping `login.live.com`). Verified by building the URL with live settings:
host `login.microsoftonline.com/57989ee3-…/authorize`, `client_id=43587c64-…`, `prompt=select_account`,
`domain_hint=corp-dev.com`. Gates green (`ruff`/`mypy src`); 16 `test_sso_api.py` tests pass. Defense in depth: the
callback already enforces `_domain_allowed` (`allowed_domain=corp-dev.com`), so a personal account is rejected
(`domain_not_allowed`) even if one reaches the callback.

- **Action required:** restart the backend (no auto-reload) to load the code change, then retry. Because the browser
  has a cached gmail MSA session, also use the account picker (now forced) to choose the `@corp-dev.com` account, or
  test in a fresh/incognito window.

## Follow-up: 2026-06-28 #3 — test-login still fails: environmental DNS, not code

After the backend was restarted (now PID 33492; live `GET /auth/sso/login` shows `prompt=select_account` → the
P0/P1/P2 `login.py` fixes ARE loaded), "Save & Test Login" still failed. Reproduced the **exact** backend flow against
the live DB (`scratchpad/diag_test_login.py`):

- DB is correct: env "Test VN" in project "PT Tool" → `login_url='https://pttool-dev.corpdev.local/'`; credential
  `thuong.lambale@corp-dev.com`, password present (len 13, not Fernet-looking), TOTP unset.
- The real login routine now raises: **`Page.goto: net::ERR_NAME_NOT_RESOLVED at https://pttool-dev.corpdev.local/`**.
- **Root cause (Confirmed, environmental):** the machine is no longer on the corporate network/VPN. `nslookup` resolves
  via `dynamic-ip-adsl.viettel.vn` (116.97.90.124, home ISP) and returns **no A record** for `pttool-dev.corpdev.local`;
  `curl` now returns `http_code=000`. Earlier in the same session the host resolved and the bundled-Chromium login
  reached `/dashboard` — i.e. it worked while the corporate DNS was reachable. **Fix: reconnect the corporate
  VPN/network; the code is correct.**

### Secondary bug exposed (error message is misleading)

`resolve_or_generate_storage_state` swallows the `BrowserError` (DNS/login failure) and returns `None`; `test_login`
then maps `None` → `"No test credentials found for this environment and role."` and the FE falls back to `"Login
failed. Please check your credentials."` So a **network/DNS failure is reported as a credentials problem**, which sent
the debugging down the wrong path (MFA/creds) when the real cause was VPN/DNS.

### Fix — accurate error messages (implemented & verified, 2026-06-28)

- `browser/login.py`: new `_classify_browser_failure(exc)` maps raw Playwright errors to clear, actionable messages —
  `ERR_NAME_NOT_RESOLVED` → "Could not resolve the target host … Connect to the corporate network/VPN"; connection/
  disconnect errors → "Could not reach the target application …"; timeouts → "Timed out reaching …". The technical
  string is kept in `BrowserError.details` (logged, never shown).
- `sessions/auto_login.py`: `resolve_or_generate_storage_state(..., raise_on_failure=False)`. When `True`, the failure
  paths raise typed errors (`ConfigError` for missing credential/env/URL; the real `BrowserError` is re-raised) instead
  of returning `None`. Default `False` keeps the fail-soft `None` contract Sarah/Jack depend on (verified by test).
- `api/test_login.py`: calls with `raise_on_failure=True`; on `AIQAError` returns `exc.message` (user-facing only —
  `.details` never leaks); on any other exception returns a generic "check the server logs" message. No more
  "No test credentials found" masking a network error.
- `frontend/.../SarahInputsForm.tsx`: neutral fallback "Login test failed. Please try again." (was the misleading
  "Login failed. Please check your credentials.").
- **Verified:** unit tests added (`_classify_browser_failure` params; `raise_on_failure` ConfigError + BrowserError
  re-raise + default-None); gates green (`ruff`/`mypy src`/17 tests). End-to-end: a bogus internal host now surfaces
  "Could not resolve the target host … Connect to the corporate network/VPN" with `ERR_NAME_NOT_RESOLVED` only in
  `details`. **Requires backend restart to take effect.**

## Follow-up: 2026-06-28 #4 — root cause of the "unexpected" failure: `uvicorn --reload` on Windows

After restart the UI showed "Login test failed **unexpectedly**. Please check the server logs." (the new generic
`except Exception` branch → a NON-`AIQAError`). Reproducing the full `resolve_or_generate_storage_state` path in a
standalone `asyncio.run()` returned **OK (27 cookies)** — yet the uvicorn endpoint failed. The difference is the
asyncio event loop:

- **Confirmed root cause:** the backend runs `uvicorn ai_qa.api:app --host 0.0.0.0 --port 8000 **--reload**`. uvicorn
  0.49's loop factory (`uvicorn/loops/asyncio.py`): `win32 and not use_subprocess → ProactorEventLoop; else
  SelectorEventLoop`. `--reload` (and `--workers>1`) sets `use_subprocess=True` → on Windows the worker runs a
  **SelectorEventLoop**, which **cannot spawn subprocesses**. Playwright starts its driver via an asyncio subprocess →
  `NotImplementedError` at `asyncio/base_events.py:_make_subprocess_transport` (reproduced directly under
  `WindowsSelectorEventLoopPolicy`). `asyncio.run()` uses the ProactorEventLoop → that is why every standalone repro in
  this case succeeded while the endpoint failed.
- The `NotImplementedError` originates at `async_playwright()` startup (driver subprocess), which is outside
  `_login_with_playwright`'s inner try, so it escaped as an untyped exception → "unexpectedly". (This also silently
  degrades Sarah's explore on Windows under --reload — `explorer.py` fails soft to vision/LLM-only.)

### Fix

- **Operational (the actual fix): run the backend WITHOUT `--reload`** → uvicorn uses the ProactorEventLoop on Windows
  → Playwright works. This matches the project's existing guidance (`--reload` is a documented hazard). Verified: the
  real code path returns AUTHENTICATED under the Proactor loop.
- **Code (clarity, so it's never cryptic again):**
  - `browser/login.py`: `generate_session_storage_state` now catches `NotImplementedError` from the login routine and
    raises `BrowserError(_EVENT_LOOP_HINT)` → the UI shows "Browser automation could not start under the server's event
    loop. On Windows, run the backend WITHOUT `uvicorn --reload` …" instead of a generic error.
  - `api/app.py` lifespan: logs a prominent WARNING at startup when the running loop is a `SelectorEventLoop` on Windows
    ("…browser automation WILL fail… restart without --reload").
  - Gates green (`ruff`/`mypy src`/18 tests, incl. a test mapping `NotImplementedError` → the event-loop hint).

**Action required:** restart the backend **without `--reload`** (e.g. `uv run uvicorn ai_qa.api:app --host 0.0.0.0
--port 8000`), then click "Save & Test Login" — it returns an authenticated session (verified, 27 cookies incl.
`PT.Auth*`).

## Follow-up: 2026-06-28 #5 — after the loop fix worked: "Not set" popup vs "Captured" Sarah; credential vanished

Running without `--reload` made test-login WORK (Sarah shows Super Admin = **Captured**). New symptom: the "Test
Accounts" matrix popup shows every cell **"Not set"** while Sarah shows **Captured**. (Investigated via a 3-thread
parallel workflow + direct live verification.)

### Confirmed findings

- **The `test_account_credentials` table is genuinely empty (0 rows, all projects)** while the single user
  (`53d621d5`) and project (`PT Tool`) still exist (so no FK cascade). The captured **session** row survives (separate
  table), so Sarah still shows "Captured".
- **UI divergence is by design (two data sources):** the matrix popup `TestCredentialsEditor` reads the credentials
  list (`GET /projects/{id}/test-credentials`, `TestCredentialsEditor.tsx:42`) → empty → "Not set"; Sarah's "Login
  sessions" reads captured sessions (`GET /projects/{id}/sessions` → `SessionMatrix.captured`, `SarahInputsForm.tsx:106`,
  `App.tsx:1145`). A stale captured session with no backing credential ⇒ the contradictory display.
- **Password IS encrypted at rest** — `password: UserSecretEncryptedString(1024)` (`models.py:410`); the earlier
  "plaintext" note was a misread (the ORM decrypts on read, so a 13-char value is the *decrypted* password).
  Correction recorded.
- **Data-destructive migration (the standout finding):** `alembic/versions/a6e9fdf81829_…user_scoped.py:22` runs
  `op.execute("DELETE FROM test_account_credentials")` at the top of `upgrade()` (to add a NOT NULL `user_id`). It is
  the **current DB head**. **Applying — or RE-applying via a downgrade→upgrade cycle — wipes ALL test credentials.**

### Honest timeline caveat (verify-subagent-claims)

The workflow concluded "the migration deleted them." That is the confirmed *mechanism*, but it cannot be the original
2026-06-27 run that emptied today's row: the credential existed **earlier today** (seen with `user_id` set, i.e. the
table was already user-scoped/migrated) and vanished afterward. So today's loss happened **after** the row existed →
most likely the migration's `DELETE` **re-ran** (an `alembic downgrade`→`upgrade` during the restarts) or the single
credential was removed. Open question for the user: did you run `alembic downgrade`/`upgrade` (or delete the
credential) while restarting? Encryption-key mismatch is ruled out — that leaves an unreadable row, not 0 rows.

### Recovery + fixes

- **Immediate:** re-enter the credential (Save & Test Login). Super Admin's captured session is still valid (1h TTL),
  so Sarah can "Generate scripts" for Super Admin right now regardless.
- **Recommended:** (1) never re-run `a6e9fdf81829`; future schema changes should backfill `user_id`, not `DELETE`.
  (2) Reconcile the two UIs — the matrix popup should also reflect captured-session status (or invalidate a captured
  session when its backing credential is deleted) so "Not set" + "Captured" can't contradict.

## Follow-up: 2026-06-28 #6 — user confirmations + fixes (items 1–4)

User confirmed: (2) they re-ran the migration before restarting → its `DELETE` re-fired and wiped the credential
(confirms the timeline caveat in #5); (3) they deleted the credential in the popup "to clean data" but the session
stayed → illogical; (4) asked to make the UIs consistent. Item (1): "Generate scripts" hangs.

### Item 1 — Generate is genuinely STUCK (diagnosed, not yet fixed)

Live DB: multiple `agent_runs` for PT Tool stuck in `status='running'` at `current_step=4` (Sarah), thread
`processing`; the latest ran ~11 min with no completion, and several orphaned "running" runs exist (the user clicked
Generate repeatedly). So Sarah hangs at step 4 (explore/codegen — browser-use driving the real app + on-prem LLM
codegen). Separate subsystem (likely slow/looping on-prem explore). Mitigation: restart (the lifespan reconciler resets
orphaned `running` runs) and avoid repeated clicks. **Deeper investigation deferred / offered.**

### Items 2–4 — fixed & verified (gates: ruff + `mypy src` + 25 tests + FE typecheck all green)

- **(2) Migration no longer destroys in-use data.** `a6e9fdf81829` upgrade() now adds `user_id` nullable, **backfills
  it from `projects.created_by_user_id`**, deletes only truly-unmappable rows, then sets NOT NULL — instead of the
  blanket `DELETE FROM test_account_credentials`. NOTE: the current DB is already at this revision, so the edit does not
  re-run on it (lost rows are unrecoverable); it protects fresh installs and any future downgrade→upgrade.
- **(3) Deleting a credential clears its captured session.** `api/test_credentials.py` `delete_test_credential` now
  calls `session_service.delete_captured_session(user,project,env,role)` after the delete — no more orphan
  "Captured" session without a credential. New test `test_delete_also_clears_captured_session`.
- **(4) Matrix popup now shows session status.** `TestCredentialsEditor.tsx` also fetches `listSessions()` and renders a
  green **"Captured"** badge per cell when a session exists (plus "Credentials saved"/"Not set"), so the popup and
  Sarah's panel agree.
- **Security note (corrected):** `TestAccountCredential.password` IS encrypted at rest (`UserSecretEncryptedString`,
  verified by `test_upsert_and_list_strips_secrets`). The earlier "plaintext" worry was a misread (ORM decrypts on
  read). The remaining items are not security defects.

**Action required:** restart the backend (no `--reload`) to load the FE/BE changes; the migration edit needs no action
on the current DB. Re-enter the credential (Save & Test Login) to restore it.

## Follow-up: 2026-06-28 #7 — Jack "no test account" while popup says "Captured": EXPIRED session

Sarah generated real scripts (confirmed: `a[href="/onboarding-talk"]`, `a[href="/admin/external-dlees"]`,
`get_by_placeholder("Search employees by name or email")` — real pttool DOM; the high warning count is by design:
standard SSO reminder + brittle-but-real href selectors (pttool lacks data-testid) + steps the trace couldn't complete
(add-user failed) commented as TODO). The "Generate" wasn't hung — just slow (~48 min for 7 on-prem scripts).

Then Jack blocked with "selected scripts include role(s) with no test account" even though the popup showed
**Captured** for Super Admin/Test VN. Root cause (Confirmed): the captured session **EXPIRED** — `captured_at`
02:22 UTC, `expires_at` 03:22 UTC (1h TTL), Jack ran 03:59 UTC → `is_expired=True`; and `test_account_credentials`
is empty (0 rows). Jack's gate (`_check_preconditions` → `_resolve_session_for_role` → `resolve_or_generate_storage_state`)
correctly ignores the expired session and has no credential to re-login, so it blocks — the message is accurate. The
**UI was misleading**: `list_session_status` (and the FE "Captured" badge in both Sarah and the new popup) showed the
session regardless of expiry.

Fix (FE, expiry-aware): `SessionStatus.expires_at` is now threaded into `CapturedSessionSlot`/`SarahSessionSlot` (+ the
two `App.tsx` maps); `SarahInputsForm.isCaptured` excludes expired sessions; `TestCredentialsEditor` shows a green
**Captured** only when valid and an amber **Session expired** otherwise. Gates: `npm run typecheck` + ESLint clean.

**To run Jack:** re-enter the credential for Super Admin/Test VN (Set Credentials → Save) — Jack then auto-logs-in
fresh (no expiry dependency). Captured sessions are short-lived (1h); the credential is the durable thing Jack needs.

## Follow-up: 2026-06-28 #8 — re-saved but "expired" lingers; Jack run no-feedback; new-thread skip

- **"Session expired" persists after re-saving (FE stale + no cleanup):** the live DB now has a VALID session +
  1 credential, so the badge is stale (loaded before). FIX: `upsert_test_credential` now also calls
  `delete_captured_session` so re-saving a credential drops the old/expired session (next run logs in fresh). Reload
  the page to clear the stale display. (Gate green; needs backend restart.)
- **Jack "run does nothing" = it actually STARTS but runs silently/long.** Message history for the Jack thread:
  4× "no test account" errors at 03:54-03:55 (clicked before re-entering the credential), then after re-entry two
  `running` agent_runs at 04:03:06/04:03:17 (double-click) with NO error and NO progress messages. Mechanism: Jack's
  precondition `_resolve_session_for_role` → `resolve_or_generate_storage_state` performs a **full silent browser login
  (~30-60s, Entra)** with no "logging in…" message, then `_begin_execution` runs pytest-playwright on scripts with
  brittle/incomplete selectors. Across all PT Tool runs only **1 ever reached `completed`** (vs 78 interrupted, 4
  running) → runs almost never finish on their own = hang or very slow, with no incremental feedback.
- **New thread skip:** thread `bcd3a7c8` last message is Bob "Saved 0 requirements… please input 1 page id" — i.e.
  waiting for input / mid-handoff, plus 2 leftover `running` runs (double-click). Likely the same slow/silent pattern.

### Jack run UX hardened (implemented 2026-06-28)

Per user request, three interactive-UX fixes so a run can't be double-launched and shows it's working:

- **Disable "Confirm & Run" on click + spinner.** `JackInputSelection` takes a `running` prop and keeps a local
  `submitting` guard; the button is disabled and shows "Running…" once clicked. `App.tsx` lifts `jackRunStarting`
  (set in `handleJackConfirm`, reset in `handleJackMessage` on an error / re-emitted selection / execution_summary,
  and on thread switch) — stops the duplicate-run double-clicks seen in the DB (2 runs/thread).
- **Removed the "Execution history" panel** (`ExecutionHistory` usage + imports dropped from `App.tsx`; component file
  kept). 
- **Jack now emits progress messages** so the run isn't silent: a "Preparing the run on '<env>'. Logging in for
  role(s)…" message before the silent per-role browser login, and a "Running N script(s) on <browsers>…" message at
  execution start (`jack.py`). Combined with the spinner, the user sees activity during the slow login+execute phase.
- Gates: backend `ruff`/`mypy src` green; frontend `typecheck`/ESLint green; `JackInputSelection` tests 11/11 pass.
  (Pre-existing, UNRELATED `App.test.tsx` failures remain — Alice provider / Bob popup / thread-routing WS-mock tests
  that time out on `findByText`, not touched by these changes.) FE hot-reloads via Vite; the `jack.py` messages need a
  backend restart.

### UAT / Docker browser availability (2026-06-28)

- **Docker image ships ONLY Chromium** (`Dockerfile.backend` `playwright install --with-deps chromium`). Chrome/Edge
  are Chromium *channels* (same engine), Firefox/WebKit are separate engines. Jack degrades gracefully:
  `probe_browser_availability` (`script_runner.py:282`) launches each selected browser; missing ones → "unavailable"
  (reason recorded), the run continues with what's available; the backend label map already supports
  chromium/firefox/webkit/chrome/msedge (`_LABEL_TO_SPEC`).
- **Change (per user):** Jack's browser choices collapsed to **Chromium (Chrome, Edge) / Firefox / WebKit**
  (`JackInputSelection.tsx` — dropped the separate Chrome/Edge options since headless Chromium covers both). Dockerfile
  now installs `chromium firefox webkit` (not chrome/msedge). Gates: FE typecheck/ESLint + 11 Jack tests green.
  **Needs a backend image rebuild** for Firefox/WebKit to exist on UAT.
- **UAT headless:** works in Docker (Linux + no `--reload` → subprocess OK; Chromium present). **Blocker deferred by
  user:** air-gapped UAT can't reach `login.microsoftonline.com` for the target's Entra SSO, and the browser launch
  passes no proxy — to be handled after the UAT release (add `proxy=` to `login.py`/`explorer.py` + IT-proxy egress).

## Follow-up: 2026-06-28 #10 — Jack run "error" = Markdown fence in the generated script; Playwright trace Q

After set-up worked (Captured + creds, 3-browser pick, progress messages all shown), the run reported **1 total /
1 error / 0.00s**. Root cause (Confirmed via `test_execution_results.stack_trace`):

```
File "…test_1_test_external_dlees_page_is_accessible….py", line 13
    ```python
SyntaxError: invalid syntax
```

The codegen LLM (model: sonnet) wrapped the script in a Markdown ` ```python ` fence; `_call_llm` returned it
unstripped and the formatter prepended a docstring+imports header around it, so the fence landed at line 13 → invalid
Python → **pytest collection failure** → the whole invocation errors before any browser runs (pytest collects all
files together, so one bad file fails the lot — that's the "1 total" for 2 scripts × 3 browsers). Confirmed the
review-message `script_content` for "External DLees page is accessible" (index 4) contains the fence at line 13.

**Fix:** `ScriptGenerator._strip_code_fences` (new) drops any fence-only line (` ``` `/` ```python `), applied at the
top of `_postprocess_script` — the single chokepoint all three codegen paths (trace/vision/LLM-only) pass through.
Verified: the broken sample now `ast.parse`s; gates green; 3 regression tests added (`TestFenceStripping`). NOTE: the
**already-saved 7 scripts still contain the fence** — they must be re-generated (or fence-stripped in place) before Jack
will run; the fix only affects future generations.

**Playwright report (user Q):** YES — the runner already produces Playwright **traces** (`--tracing retain-on-failure`
→ trace.zip) and **screenshots** (`--screenshot only-on-failure`), both default-on (`execution_capture_traces/_screenshots`),
persisted as artifacts (kind `trace`/`execution_screenshot`) which **already browse under the "Reports" folder**
(`folder_for_kind` → "reports", `storage.py:81`). They were absent this run only because it failed at *collection*
(no test executed → nothing to trace). After re-gen + a run where a test actually fails, a `trace.zip` appears in
Reports → open with `playwright show-trace` / trace.playwright.dev. Nothing to wire up; optionally switch tracing to
"on" (always) if QA wants traces for passing tests too.

## Follow-up: 2026-06-28 #11 — always-on Playwright report (trace/video) + download, for headless QA

Run passed 6/6, but Reports showed no Playwright artifact: tracing was `retain-on-failure` + screenshot
`only-on-failure`, so a 100%-pass run kept nothing. For headless UAT (QA can't watch the browser; locally it runs
headed via `headed = not server_mode`), QA needs a watchable artifact regardless of pass/fail. Implemented (mapped via
a 5-agent workflow, then verified):

- **Always-on trace:** `script_runner.build_pytest_command` now emits `--tracing on` (was `retain-on-failure`) → a
  `trace.zip` for every test; persistence still gated by `execution_capture_traces` (default True). config doc clarified.
- **Video (opt-in):** new `execution_capture_videos` (default False, heavy) → `--video on`; `.webm/.mp4 → "video"` in
  `_collect_output_files`; threaded through `run_scripts` + Jack `_persist_outputs` (`keep_by_kind["video"]`).
- **Artifact plumbing:** `"video"` added to `ARTIFACT_KINDS` and to `folder_for_kind` → "reports" (build_artifact_key
  uses the `artifacts/` catch-all, no change). trace/video/screenshot all browse under **Reports**.
- **Binary download endpoint:** `GET /projects/{id}/artifacts/{id}/download` (`api/artifacts.py`) → raw bytes as an
  attachment with MIME + safe filename, **no 1 MB cap** (the `/content` JSON path caps at 1 MB — too small for
  trace.zip/video).
- **Reports UI (`ArtifactPreview.tsx`):** universal **Download** button (header); `trace` → download + "open in
  trace.playwright.dev / `npx playwright show-trace`" hint; `video` → inline `<video>` player (streamed from the
  download endpoint); `execution_screenshot` → inline image; skips the `/content` fetch for trace/video.
- **Streaming verdict:** live-streaming the headless browser to local is NOT worth it (VNC/CDP screencast infra). The
  trace (interactive step-through) + optional video (linear replay) downloaded from Reports is the standard, simpler,
  superior QA workflow. Shipped that; skipped live streaming.

Gates: `ruff`/`mypy src` (104 files) green; **384 backend tests pass** (added `video` to artifact-kind/folder tests +
the earlier fence tests); FE `typecheck`/ESLint green. **Restart backend** to load it; re-run Jack → `trace.zip`
appears in Reports (downloadable). Enable video via `EXECUTION_CAPTURE_VIDEOS=true` in `.env` if QA wants recordings.

### Open (needs live backend logs — the missing evidence)

Where Jack hangs (silent browser login vs pytest execution vs a Playwright selector wait) can't be determined from the
DB. **Next:** restart the backend (reconciler resets the 4 stuck `running` runs), run Jack ONCE (no double-click), and
capture the backend terminal logs. Likely real fixes: emit a "Logging in / preparing…" progress message before the
silent login; add a hard timeout + cancellation around the per-role login and the pytest execution so a hang surfaces
as an error instead of an indefinite spinner; debounce the Run/Confirm button to stop duplicate runs.
