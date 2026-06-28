# Sprint Change Proposal — Group Security blocks browser session capture

- **Date:** 2026-06-25
- **Author:** Dev (BMAD correct-course)
- **Trigger source:** Group Security (Luvic, CORP Group Security) flagged the test-login session-capture mechanism as suspicious activity.
- **Change scope classification:** **MAJOR** — fundamental replan of how the AI QA pipeline authenticates against the *application under test*. Routes to PM/Architect (new design + epic) then Dev.
- **Mode:** Batch (all proposals presented together).
- **Decisions taken at intake (Thuong, 2026-06-25):**
  1. Primary mechanism = **dedicated test-account auto-login** (the tool logs in itself, in its own clean browser, with purpose-built test-account credentials; never reads the employee's session).
  2. **Remove the session-capture surface entirely** (CDP pull + client-side `capture-session.mjs/.cmd` + import-blob endpoints).
  3. Review in **batch**.

---

## Section 1 — Issue Summary

### What triggered it

Group Security observed and flagged the following on Thuong's managed laptop (Teams screenshot, 2026-06-25):

- A PowerShell command (`-NoProfile -ExecutionPolicy Bypass`) that reads a file and extracts a `// CAPTURE_PAYLOAD` marker;
- two downloaded/executed `.cmd` files: **`capture-session.cmd`** and **`capture-INT-Super-Admin.cmd`**;
- the resulting **capture of cookies from `int-progresstalkapplication.corpnet.local`**.

Security's position: this behaviour is indistinguishable from cookie-stealing malware. They asked whether the process was launched by a malicious user. Thuong confirmed it is the AI QA Automation tool capturing a session to replay Playwright scripts, and committed to finding a safe alternative.

### The precise problem

The pipeline's current target-app authentication is **"capture the tester's authenticated browser session (cookies / `storageState`) and replay it."** Two capture paths exist today:

1. **Backend CDP pull** — the backend `connect_over_cdp`s to a Chrome started with `--remote-debugging-port=9222` and exports its `storageState` ([`src/ai_qa/browser/session_capture.py:24`](src/ai_qa/browser/session_capture.py)).
2. **Client-side capture + upload** — `frontend/public/capture-session.mjs` / `capture-session.cmd` capture the blob on the tester's machine and POST it to `/sessions/import` ([`src/ai_qa/api/sessions.py:333`](src/ai_qa/api/sessions.py)). **These are the exact `.cmd` files Security flagged.**

Both read the **live corporate session of a real employee**. To endpoint security tooling this is cookie exfiltration, and it cannot continue on managed/corporate machines.

### The core insight (the safe alternative)

The problem is **not** `storageState` as a concept — it is **reading the employee's live session**. Playwright's standard, security-accepted authentication pattern is the inverse:

> **Automate the login itself, in the automation's own clean browser, using a dedicated test account's credentials — then reuse the session the tool generated. Never touch the employee's browser/session.**

This flips the original design (`design-test-login-credentials-and-sessions-2026-06-20.md`, which deliberately *avoided* automating login and preferred `SSO_MANUAL` capture). Security has effectively reversed that constraint: **automating login with a dedicated test account is the safe path; capturing the human's session is not.**

### Categorisation

- New external (security) constraint emerged during implementation → **strategic pivot of an architectural mechanism**, forced by a stakeholder (Group Security).

---

## Section 2 — Impact Analysis

### 2.1 Epic impact

| Epic | Status | Impact |
| --- | --- | --- |
| **Epic 16** (Conversational UX) — stories **16-19 / 16-20 / 16-21** | 16-19 `review`, 16-20 `deferred`, 16-21 `review` (all UNCOMMITTED) | **Capture surface superseded.** 16-19 (import-blob) + 16-21 (collapse-to-captured-session) carry the now-forbidden capture/import. The *consumption* halves of 16-21 (Tier-1 server-side `storage_state` injection, `check-connections`, the `c7e3a9f04b21` cleanup that dropped `login_type`/`project_accounts`/`chrome_path`) are **kept**. |
| **NEW Epic 25** (proposed) — Security-Compliant Target-App Authentication | new | Holds the dedicated test-account auto-login mechanism. High priority — it **unblocks Sarah/Jack** against any authenticated corporate app (the capture path is now dead). |
| **Epic 24** (DOM Snapshot Caching) | `backlog` | 24-2 "Get DOM — **session-authenticated** crawl" must consume the new auto-login session instead of a captured one. Backlog → adjust the story note, not blocking now. |
| **Epic 23** (SSO-First Auth for the *AI QA app itself*) | `in-progress` (23-1…23-5 `review`, 23-6 `deferred`) | **NOT affected.** Epic 23 is how *users log into our app* via Azure. This change is about how the tool authenticates into *target apps*. Independent. (Possible future synergy noted in §3, not in scope.) |

**Epic-order / priority change:** Epic 25 should be worked **before Epic 24** (24 depends on it) and is a natural companion to Epic 23's live-validation window (both are auth work needing the real environment). Recommended sequence after the current in-flight commit: **Epic 25 → Epic 24**, with 25-1 (spike + IT asks) startable immediately.

### 2.2 Story impact (PRD / epics.md requirement conflicts)

The original requirements were written for the "reuse the human's SSO session, store nothing" model and now **directly conflict** with the security-mandated approach:

| Artifact | Current text (conflict) | Conflict |
| --- | --- | --- |
| **NFR10** (epics.md:103) | "Browser sessions reuse existing SSO and the pipeline must **not store, cache, or log credentials**." | New approach **must store** dedicated test-account credentials (encrypted). |
| **FR12** (epics.md:30) | "control a local Chrome instance via browser-use using **active SSO login session**." | We no longer reuse the employee's active SSO session. |
| **Story 13.4** (epics.md:1324) | scripts run against "an **existing authenticated session** … without storing credentials." | Session is now produced by an automated test-account login, not a pre-existing human session. |
| **Story 14.4** (epics.md:1524) | "When a configured session is available, Jack uses the configured browser context/session **without storing or logging credentials**." | Same conflict; Jack now resolves a session via test-account login. |

> **FR1** ("connect to Confluence via MCP … using existing SSO session", epics.md:19) is **out of scope** — that is MCP server auth for Bob reading Confluence, not browser-cookie capture. Unchanged.

### 2.3 Artifact conflicts

- **Design doc `design-test-login-credentials-and-sessions-2026-06-20.md`** → **SUPERSEDED.** Its load-bearing `SSO_MANUAL` capture mechanism (§4) is now forbidden. Replace with a new design note (Story 25-1).
- **Investigation `uat-sso-session-copy-investigation.md`** → still valid as history; its "Recommended option 1 (client-capture → upload)" is now also forbidden — annotate.
- **Code (remove — the flagged surface):**
  - [`src/ai_qa/browser/session_capture.py`](src/ai_qa/browser/session_capture.py) (CDP pull) — delete.
  - [`src/ai_qa/api/sessions.py`](src/ai_qa/api/sessions.py) — remove `capture_session`, `import_session`, `create_import_token`, `import_session_with_token` (the 4 capture/import routes + their token helpers). **Keep** `list_sessions`, `delete_session`, `check_environment_connections`.
  - `frontend/public/capture-session.mjs` + `frontend/public/capture-session.cmd` — **delete (these are the flagged files).**
  - [`frontend/src/components/sessions/ImportSessionForm.tsx`](frontend/src/components/sessions/ImportSessionForm.tsx) — delete/replace with a test-account entry form.
  - [`frontend/src/components/sessions/SessionMatrixPanel.tsx`](frontend/src/components/sessions/SessionMatrixPanel.tsx) — rework from "captured sessions" to "test accounts + login status".
- **Code (keep — the reusable consumption seams):**
  - Tier-1 server-side injection [`src/ai_qa/browser/explorer.py:120`](src/ai_qa/browser/explorer.py) (browser-use `storage_state` temp file).
  - Jack conftest injection [`src/ai_qa/pipelines/script_runner.py:574`](src/ai_qa/pipelines/script_runner.py).
  - `ScriptGenerator(role_sessions=…)` plumbing [`src/ai_qa/pipelines/script_generator.py:105`](src/ai_qa/pipelines/script_generator.py); `sarah._resolve_role_sessions`.
  - `check_environment_connections` reachability probe.
- **DB / migrations:**
  - `CapturedSession` table → **repurpose** as the (optional) cache of the *tool-generated* session (no longer the employee's). Add **NEW `TestAccountCredential`** store (per `(project, environment, role)`; encrypted username/password + optional TOTP secret; reuse Fernet machinery `db/types.py`). New migration chained on the current head.
  - Migration `c7e3a9f04b21` (UNCOMMITTED, already RUN): its capture-removal cleanup (dropped `login_type`/`project_accounts`/`users.chrome_path`) is **kept** — no revert.
- **Prompts / validators:** [`src/ai_qa/prompts/script_generation.py`](src/ai_qa/prompts/script_generation.py) + `script_validator.py` rule "generated scripts assume a pre-authenticated session, never automate login, never hardcode credentials" → **stays true for the generated test body.** Login now happens in the *setup/harness* (global-setup pattern), not the test. Minor doc note only.
- **Tests / CI:** remove capture-path tests; add credential-store + login-automation + leak-canary tests (test-account credentials join the per-user-secret no-leak convention across API/WS/logs/artifacts).

### 2.4 Technical impact

- **Sarah / Jack are currently blocked** against any authenticated corporate target app: the only auth path was capture, which is now forbidden. This change is the unblock.
- New runtime behaviour: a **login phase** (browser-use- or Playwright-driven) runs before explore/run, authenticating a clean context with stored test-account credentials, producing the `storageState` the existing seams consume.
- **MFA / Conditional Access is the load-bearing risk** for internal Azure-SSO apps (mirrors Epic 23's egress risk). A scripted login cannot satisfy push-MFA/biometrics. Mitigation requires an **IT ask**: a dedicated QA test account that is either **MFA-exempt** (login = username/password form, fully scriptable) or **TOTP-based** (store the TOTP seed, compute the code at login). This is the §6 IT dependency.

---

## Section 3 — Recommended Approach

**Hybrid: Rollback the forbidden capture surface + new Epic 25 for the auto-login mechanism + reconcile FR/NFR + supersede the 2026-06-20 design doc.**

### Why hybrid (vs the checklist's single options)

- **Option 1 (Direct Adjustment within Epic 16):** viable but semantically wrong — the session work was always an awkward guest in "Conversational UX". Rejected as the home.
- **Option 2 (Rollback):** *partially* required — the uncommitted capture/import code (16-19, capture half of 16-21) must go. But a pure rollback would also throw away the reusable consumption seams + cleanup we want to keep. So: **targeted rollback of the capture surface only.**
- **Option 3 (MVP Review):** the MVP goal ("test authenticated apps") is **unchanged and still achievable** — only the *mechanism* changes. No scope reduction.

### The mechanism (new)

1. **Store dedicated test-account credentials** per `(project, environment, role)`, encrypted (Fernet, same machinery as provider keys), never logged/leaked. For internal Azure apps: a dedicated QA account. For external apps: username/password, or a 3rd-party-OAuth test account.
2. **Automate login** in a clean, isolated browser (browser-use-driven login fits the existing integration; given creds + login URL it performs the sign-in, incl. SSO redirect; TOTP step if configured). Export the resulting `storageState`.
3. **Feed the existing consumption seams** — the generated session is injected into Sarah's explore (browser-use) and Jack's run (conftest) exactly as today. Optionally cache the tool-generated session with a short TTL and re-login on expiry/failure (the cache is the *test account's* session, generated by us — never the employee's).
4. **Never read the employee's browser** — no CDP pull, no client capture, no cookie reads.

### Proposed Epic 25 stories (high level — created later via `bmad-create-story`)

- **25-1** Design note + feasibility spike + **IT asks** (dedicated test accounts; MFA-exempt or TOTP; login-automation choice; credential-storage + security sign-off). *Load-bearing gate, like 23-1.*
- **25-2** Remove the forbidden capture surface (§2.3 "remove" list); keep the consumption seams + `check-connections`.
- **25-3** Test-account credential store (table + migration + encrypted CRUD + admin/PA UI + leak-canary tests).
- **25-4** Automated login → session generation (browser-use/Playwright login routine; TOTP; per-app login hints; produces `storageState`).
- **25-5** Wire into Sarah explore + Jack run (resolve session via login/cache; rework `SessionMatrixPanel` → test accounts + login status; update `SarahInputsForm`).
- **25-6** External-app auth (username/password; 3rd-party OAuth Google/Apple via dedicated test accounts or app test-login; document hard limits).
- **25-7** Docs + FR/NFR reconciliation + `project-context.md` + live validation (local + UAT against a real app).

### Effort / risk / timeline

- **Effort:** High (new mechanism + credential store + login automation + FE rework + IT coordination). Partly offset by reusing the consumption seams and Fernet machinery.
- **Risk:** Medium-High — MFA/Conditional-Access on internal Azure apps is the dominant risk; mitigated by the dedicated-test-account IT ask (25-1 gate). 3rd-party-OAuth external apps may have residual hard limits (documented, not promised).
- **Timeline:** Replaces the now-dead capture work; unblocks live validation. Sequence Epic 25 before Epic 24.

### Possible future synergy (NOT in scope)

For internal apps in the same Entra tenant, the user's app-login token (Epic 23) could in theory be exchanged (OBO) for target-app access — but only if targets accept bearer tokens (not cookie-UI) and it borders on employee impersonation. **Rejected for now**; the dedicated-test-account model is cleaner and security-defensible.

---

## Section 4 — Detailed Change Proposals

### 4.1 PRD / epics.md (requirement reconciliation)

**NFR10 — OLD → NEW**
```
OLD: Browser sessions reuse existing SSO and the pipeline must not store, cache, or log credentials.

NEW: The pipeline must never read, store, or replay an END USER's browser session or
     corporate credentials. Target-app authentication uses DEDICATED TEST ACCOUNTS whose
     credentials are stored encrypted (per-user Fernet), resolved only at runtime, and never
     written to logs, messages, scripts, or artifacts (leak-canary enforced).
Rationale: Group Security prohibits session capture (2026-06-25). Storing dedicated
     test-account credentials is the security-accepted alternative.
```

**FR12 — OLD → NEW**
```
OLD: Pipeline can control a local Chrome instance via browser-use framework using active SSO login session.

NEW: Pipeline can control a browser via browser-use, authenticating the target app by an
     automated login with a dedicated test account (in the tool's own isolated browser),
     not by reusing the end user's session.
```

**Story 13.4 / 14.4** — replace "existing authenticated session … without storing credentials" framing with "a session produced by an automated test-account login; the GENERATED SCRIPT still hardcodes no credentials (login happens in setup/harness)."

### 4.2 Code (summary — full list in §2.3)

- **Remove:** `session_capture.py`; the 4 capture/import routes in `api/sessions.py`; `capture-session.mjs` + `.cmd`; `ImportSessionForm.tsx`.
- **Keep:** Tier-1 injection (`explorer.py`), Jack conftest (`script_runner.py`), `role_sessions` plumbing, `check_environment_connections`.
- **Add:** `TestAccountCredential` model + migration; credential-store service; `browser/test_login.py` (login automation); rewire `sarah._resolve_role_sessions` / `jack` session resolution to "login or cached".
- **Rework FE:** `SessionMatrixPanel.tsx` → test-account entry + per-(env,role) login status.

### 4.3 Story / sprint-status changes (applied on approval)

- `16-19-import-captured-session-blob`: `review` → **`superseded`** (capture/import path forbidden).
- `16-21-collapse-to-captured-session-and-tier1-explore`: `review` → **`superseded`** — with a note that its consumption-side deliverables (Tier-1 explore, check-connections, `c7e3a9f04b21` cleanup) are retained and carried into Epic 25.
- `16-20-local-capture-companion`: already `deferred` → annotate "permanently dropped — capture forbidden."
- **New `epic-25`** (`backlog`) + stories `25-1 … 25-7` (`backlog`), with the priority note (work before Epic 24).
- Epic 24 note: 24-2 to consume Epic 25 auto-login (not captured session).

### 4.4 Design docs

- `design-test-login-credentials-and-sessions-2026-06-20.md` → add a **SUPERSEDED** banner pointing to the new 25-1 design note.
- New `design-security-compliant-target-app-auth-2026-06-25.md` (authored in 25-1).

---

## Section 5 — Implementation Handoff

- **Scope:** **MAJOR** (fundamental replan of a core mechanism + PRD/NFR change + new epic).
- **Route to:**
  - **PM / Architect** — author the new design note (25-1), confirm Epic 25 shape, finalise FR12/NFR10/13.4/14.4 wording, own the **IT asks** (dedicated test accounts, MFA-exempt/TOTP, security sign-off on credential storage).
  - **Dev** — execute 25-2…25-7 once 25-1 lands; targeted rollback of the capture surface.
- **Immediate next step:** `bmad-create-story` for **Epic 25** (start with 25-1 spike); forward the IT asks (§6) in parallel.
- **Success criteria:** Sarah explores and Jack runs against a real authenticated corporate app using a dedicated test account, with **zero** capture of any employee session; Security has nothing to flag; FR/NFR reconciled; live-validated on local + UAT.

### Section 6 — IT asks (forward to Group Security / IT, verbatim)

1. **Provision a dedicated QA test account** (one or a small set per app-role) in Azure/Entra for the internal apps under test, **scoped to test/UAT data only** (non-privileged where possible). Confirm it may be used by an automated test harness.
2. **Resolve MFA / Conditional Access for that account — choose ONE:** (a) **exempt it from MFA** so login is a scriptable username/password form; or (b) provide a **TOTP seed** we can store (encrypted) and compute codes from. Push-MFA/biometrics cannot be automated.
3. **Confirm storing the dedicated test-account credentials encrypted at rest** (Fernet, never logged) is acceptable to Group Security as the replacement for session capture.
4. **External apps:** confirm, per app, whether a dedicated test login exists (username/password) or whether 3rd-party OAuth (Google/Apple) is required — the latter may need its own dedicated, MFA-exempt test account.

---

## Approval

- [ ] Thuong approves this proposal → proceed to `bmad-create-story` (Epic 25, starting 25-1) + apply the §4.3 sprint-status/epics.md edits + supersede banners.
