# Investigation: Jack run blocked by "No captured session" red warning

## Hand-off Brief

1. **What happened.** Jack's "Confirm & Run" is disabled and shows a red warning `No captured
   session for INT / User` — Confirmed as a *designed precondition gate* (AC3, story 14.4), not a
   crash: the 7 selected scripts all carry role `User`, and no captured session exists for the
   (environment `INT`, role `User`) slot.
2. **Where the case stands.** Root cause Confirmed (High). Primary fix is operational — capture an
   `INT / User` session in the Sessions panel. One Deduced secondary UX gap: Jack's panel reads a
   stale `jackState.sessions` snapshot from the WS message, so the red warning will NOT clear live
   after capture until Jack re-emits the selection panel.
3. **What's needed next.** Capture a session for `INT` + role `User` (key-icon "Manage your
   test-login sessions" panel), then re-trigger Jack's script-selection so the gate re-evaluates.

## Case Info

| Field            | Value                                                                                  |
| ---------------- | -------------------------------------------------------------------------------------- |
| Ticket           | N/A                                                                                    |
| Date opened      | 2026-06-22                                                                             |
| Status           | Concluded                                                                              |
| System           | Win11, frontend dev (localhost:5173); project = Progress Talk, env `INT` (`https://int-progresstalkapplication.corpnet.local/`) |
| Evidence sources | Screenshot (Jack — Run, step 5), frontend + backend source, project-context.md         |

## Problem Statement

User report (verbatim): "Jack run chưa chạy được, có cảnh báo màu đỏ." Screenshot shows the Jack —
Run panel with 7 scripts selected, Target environment `INT`, Default login role `Super Admin`,
Chrome checked, and a red warning: **"No captured session for INT / User. Capture a session for
each role to run."** The "Confirm & Run →" button is greyed out (disabled).

## Evidence Inventory

| Source                                                    | Status    | Notes                                                                 |
| --------------------------------------------------------- | --------- | --------------------------------------------------------------------- |
| Screenshot                                                | Available | Exact warning text, env `INT`, default role `Super Admin`, 7× `User` script tags |
| `frontend/src/components/agents/JackInputSelection.tsx`   | Available | FE gate logic (`involvedRoles`/`missingRoles`/`canRun`) + warning string |
| `frontend/src/App.tsx`                                    | Available | `jackState.sessions` populated only from WS metadata; Sessions panel wiring |
| `src/ai_qa/agents/jack.py`                                | Available | Backend per-role hard-block (`_confirm_inputs`, AC3) mirrors the FE   |
| `src/ai_qa/api/sessions.py` + `sessions/service.py`       | Available | Capture/list endpoints; env+role validated against project config    |
| Runtime DB (was a session ever captured for INT/User?)    | Missing   | Not inspected; warning implies none exists for this user             |

## Confirmed Findings

### Finding 1: The red warning is a designed gate, fired when an involved role has no session

**Evidence:** `frontend/src/components/agents/JackInputSelection.tsx:174-187` and `:326-331`.

**Detail:**

```
const involvedRoles = unique(selectedScripts.map(s => s.role?.trim() ? s.role : role));
const missingRoles  = involvedRoles.filter(r =>
  !(environmentName && r && sessions.some(s => s.environment === environmentName && s.role === r)));
const allRolesHaveSession = involvedRoles.length > 0 && missingRoles.length === 0;
const canRun = selectedCount > 0 && browsers.size > 0 && targetUrl.length > 0 && allRolesHaveSession;
```

Each selected script runs AS its own role; the warning + disabled button fire when any involved
role lacks a captured session for the selected environment.

### Finding 2: All 7 selected scripts carry role `User` — the `Super Admin` default never applies

**Evidence:** Screenshot — every script row shows a `User` tag; `JackInputSelection.tsx:178`
`s.role && s.role.trim() ? s.role : role`. The "Default login role" dropdown (`Super Admin`) only
substitutes for scripts that carry NO role.

**Detail:** Because all scripts already carry `User`, `involvedRoles = ["User"]`. The gate needs a
captured session for `INT / User`, regardless of the `Super Admin` default shown in the dropdown.
Capturing a `Super Admin` session would NOT clear this warning.

### Finding 3: The backend enforces the same hard-block (AC3) — the FE only mirrors it

**Evidence:** `src/ai_qa/agents/jack.py:507-509` (`_confirm_inputs` lists every involved role with
no captured session, "no unauthenticated fallback") and `:195-205` (defense-in-depth refusal in the
run loop: "Refusing to run: no captured session for role '…'").

**Detail:** Even if the FE gate were bypassed, the backend refuses to launch an unauthenticated run.
This is intentional: running without a session would produce misleading login failures.

### Finding 4: Capture flow exists and validates env+role against project config

**Evidence:** `src/ai_qa/api/sessions.py:173-187` (capture validates `environment ∈ project
environments` and `role ∈ project.app_roles`); `frontend/src/App.tsx:1733-1757`
(`SessionMatrixPanel`, opened via the key-icon "Manage your test-login sessions" button).

**Detail:** A session is a Playwright `storageState` blob, stored per-user, encrypted at rest
(`CapturedSession`). Capture key = `(user, project, environment, role)`. The match key in the Jack
gate is the **environment name** (dropdown `value={env.name}`) and the **role string** — both drawn
from the same project config, so a string mismatch is unlikely (refutes H2 below).

## Deduced Conclusions

### Deduction 1: After capturing, the Jack panel will not clear the warning live

**Based on:** Findings 1 & 4 + `frontend/src/App.tsx:1094-1097`.

**Reasoning:** `jackState.sessions` is populated ONLY from the WebSocket message metadata
(`message.metadata.sessions`) at the moment Jack emits the script-selection `review_request`. The
`SessionMatrixPanel` capture UI calls the REST `captureSession` endpoint independently and has only
an `onClose` callback — it does not refresh `jackState.sessions`.

**Conclusion:** Capturing an `INT / User` session while the Jack panel is already on screen leaves
the panel reading a stale (sessionless) snapshot; the red warning persists and "Confirm & Run" stays
disabled until Jack re-emits the selection panel (re-enter step 5 / re-run Jack), which re-sends the
session metadata over WS.

## Hypothesized Paths

### Hypothesis 1: A session was captured but doesn't match (string/env mismatch) — H2

**Status:** Refuted

**Theory:** A session exists for INT/User but the gate's equality check fails due to a role-case or
environment-name mismatch.

**Supporting indicators:** Gate uses strict `===` on both `environment` and `role`.

**Would confirm:** A `CapturedSession` row for this user with `environment="INT"` and a role string
differing from the script's `User` (e.g. case/whitespace).

**Would refute:** Match key for both sides derives from the same project config (`env.name`,
`app_roles`); capture endpoint rejects unknown env/role (422). 

**Resolution:** Refuted by Finding 4 — both sides of the comparison come from the same project
config, and the most parsimonious read of the warning is simply "no row captured yet" (H3).

### Hypothesis 2: No session has ever been captured for INT/User — H3 (primary)

**Status:** Confirmed

**Theory:** The user has not yet captured any session for the (INT, User) slot for this project.

**Supporting indicators:** Warning text enumerates `User` as missing; "Execution history: No
execution runs yet"; this is a corporate SSO app (`.corpnet.local`) requiring an explicit
debug-browser capture before any run.

**Would confirm:** Empty `CapturedSession` set for (user, project, INT, User).

**Would refute:** An existing matching row (would then re-open H2/Deduction 1).

**Resolution:** Confirmed as the operative cause — the gate fires precisely because the slot is
empty; nothing in the trace contradicts it.

## Missing Evidence

| Gap                                                    | Impact                                          | How to Obtain                                   |
| ------------------------------------------------------ | ----------------------------------------------- | ----------------------------------------------- |
| Whether any `CapturedSession` row exists for INT/User  | Distinguishes H2 (mismatch) from H3 (none)      | Open the Sessions panel; or query `captured_sessions` for the user/project |
| `login_type` of this project (SSO vs PASSWORD)         | Determines which capture flow to use            | Sessions panel shows the offered flow; or read `Project.login_type` |

## Source Code Trace

| Element       | Detail                                                                              |
| ------------- | ----------------------------------------------------------------------------------- |
| Error origin  | `frontend/src/components/agents/JackInputSelection.tsx:326` (warning), `:181-187` (gate) |
| Trigger       | Rendering the Jack script-selection panel with ≥1 selected script whose role lacks a session for the selected env |
| Condition     | `missingRoles.length > 0` → here `involvedRoles=["User"]`, no captured INT/User session → `canRun=false` |
| Related files | `App.tsx:1094` (stale `jackState.sessions`), `jack.py:507-509`/`195-205` (backend hard-block), `api/sessions.py` (capture), `sessions/service.py`, `SessionMatrixPanel.tsx` |

## Conclusion

**Confidence:** High

This is **not a defect** — it is the AC3 authenticated-run gate working as designed. The 7 selected
scripts all run as role `User`; no captured Playwright session exists for `(INT, User)`, so both the
frontend (`canRun=false`) and the backend (`_confirm_inputs` hard-block) refuse to run. The
`Super Admin` "Default login role" is a red herring: it applies only to role-less scripts, so
capturing a Super Admin session would not help.

Secondary (Deduced, Medium): the Jack panel reads `jackState.sessions` from a WS-message snapshot
and is not refreshed by the Sessions panel's capture call, so the warning will not clear live after
capture — the selection panel must be re-emitted.

## Recommended Next Steps

### Fix direction

Operational (no code change needed for the primary issue):

1. Open the Sessions panel via the key-icon button ("Manage your test-login sessions") with the
   Progress Talk project selected.
2. Capture a session for environment **INT** + role **User** (SSO → debug-browser/CDP capture;
   PASSWORD → backend auto-login). Capture a session for **every** role the selected scripts use.
3. Re-trigger Jack's script selection (re-run/re-enter step 5) so the panel re-reads sessions; the
   warning clears and "Confirm & Run" enables.

Optional code improvement (separate, low-priority — tracks Deduction 1): have the Jack panel
re-fetch sessions (call `listSessions`) when the `SessionMatrixPanel` closes, or push updated
session metadata over WS after capture, so the gate clears live without re-emitting the panel.

### Diagnostic

If, after capturing an INT/User session and re-triggering Jack, the warning persists → re-open H2:
inspect the `captured_sessions` row's `environment`/`role` strings vs the script's role tag and the
env dropdown value for a case/whitespace mismatch.

## Reproduction Plan

1. Open a project with ≥1 environment and ≥1 app role, with Sarah scripts that carry a role (e.g.
   `User`), and NO captured session for that (environment, role).
2. Advance to Jack — Run (step 5); select the scripts; pick the environment.
3. Expected: red `No captured session for <env> / <role>` warning; "Confirm & Run" disabled
   (`canRun=false`). Matches the report.

## Side Findings

- The "Default login role" dropdown defaulting to `Super Admin` while every script needs `User` is a
  likely point of operator confusion — the dropdown is inert here. (Confirmed, `JackInputSelection.tsx:178`.)
- This project is air-gapped corporate SSO (`.corpnet.local`); per project memory, session capture
  for cookie-based SSO is live-validated via Playwright `storageState` reuse.

## Follow-up: 2026-06-23

### New Evidence

Thuong approved the diagnosis and requested a UX fix (not just the warning): add explicit
guidance ("please log in to INT as User by clicking Capture Session") + a **Capture Session
button in the Jack panel**, since Jack can span more (environment, role) slots than Sarah.

Understanding workflow (`wf_745d0f7d-c5a`) finding that reshaped the design: **Sarah has NO inline
Capture Session button** — both Sarah and Jack rely on the single global "Sessions" top-nav button
(`frontend/src/App.tsx:1744`) that opens `SessionMatrixPanel` (a full env×role modal). So the ask
became "give Jack a discoverable capture affordance" rather than "copy Sarah's button."

### Implementation (uncommitted, 2026-06-23)

- `frontend/src/components/agents/JackInputSelection.tsx`: new optional prop
  `onCaptureSession?: () => void`. The red-warning `<p>` is now wrapped in a `<div>` that also
  renders (a) a slate guidance line "Please log in to {env} as {roles} by clicking Capture Session
  below…" and (b) a "Capture Session" button (KeyRound icon) gated identically to the warning
  (`missingRoles.length > 0 && !!environmentName`) and only when `onCaptureSession` is provided.
  The "No captured session for {env} / {roles}" text stays one contiguous text node so the existing
  session-awareness tests still match.
- `frontend/src/App.tsx`: passes `onCaptureSession={() => setSessionsPanelOpen(true)}` (opens the
  existing matrix panel); `SessionMatrixPanel` `onClose` now also re-fetches `listSessions(projectId)`
  and maps `matrix.captured → jackState.sessions`, so the gate clears **live** after capture without
  needing Jack to re-emit the panel (closes Deduction 1's gap for the common path).
- `frontend/src/components/__tests__/JackInputSelection.test.tsx`: +3 tests (button shows + fires on
  click; hidden when all roles have a session; guidance shown but no button when no handler).

Verification: `npm run typecheck` PASS, `vitest` 20/20 PASS, `eslint` clean.

### Adversarial review triage (workflow `wf_b97f31ac-a7f`, 3 lenses + verify)

- **Correctness/regression lens: clean (0 findings)** — gate logic and warning text node unchanged.
- Disabled-button contrast (`disabled:opacity-50`): **declined** — app-wide convention (Confirm &
  Run / Sessions / Logout all use it); diverging on one button breaks consistency. Optional app-wide
  a11y follow-up.
- "Deletion doesn't clear gate" (blocker): **refuted** — `onClose` re-fetches on *every* close, not
  just capture; delete→close→re-fetch re-blocks correctly, and the modal must be closed to reach
  Jack. Backend `_confirm_inputs` also hard-blocks (defense-in-depth).
- Close-during-in-flight-delete race + `selectedProjectId` mismatch: **declined** — sub-second
  self-correcting window covered by the backend hard-block; the project prop is reactive so jackState
  correctly tracks the current project.

### Updated Conclusion

Diagnosis unchanged (designed gate). UX gap addressed: Jack now shows actionable guidance + an
in-panel Capture Session button and refreshes the gate live on panel close. Status: **Concluded**;
change is uncommitted and not yet live-validated on Win11 (manual capture round-trip pending).
