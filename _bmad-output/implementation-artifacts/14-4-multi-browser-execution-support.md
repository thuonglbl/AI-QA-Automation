---
baseline_commit: 0de0b7c
---

# Story 14.4: Multi-Browser Execution Support

Status: done

> **Note (2026-06-25):** The "captured session" model discussed in this story has been superseded by the Epic 25 "Test Account Auto-Login" model. The core principles of isolating sessions and reusing `storageState` still apply, but the source of the session is now an automated login rather than a human session capture.

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want Jack to run the selected scripts against the browsers I configure (Chrome/Chromium, Firefox, Edge, and WebKit where available), reusing my captured authenticated session,
so that execution results reflect supported browser coverage and tests that need login actually pass without me re-authenticating or exposing any credentials.

## Acceptance Criteria

Verbatim from [epics.md#Story-14.4](_bmad-output/planning-artifacts/epics.md) (lines 1505-1525), expanded with implementation defaults (see "Scope decisions"). This story widens Story 14.2's single-browser runner into a **browser matrix** and adds the **authenticated context** (the captured-session `storageState`) — the AC that explicitly lives here, not in 14.2.

### AC1 — Run against configured browser targets, results recorded per browser

- **Given** one or more browser targets are configured
- **When** Jack runs selected scripts
- **Then** execution can run against configured targets such as **Chrome, Firefox, and Edge where available** (plus Chromium and WebKit where the runner supports them)
- **And** **results are recorded separately by browser** (one `TestExecutionResult` row per `(test, browser)`)

### AC2 — Unavailable browser is reported, others still run

- **Given** a requested browser is unavailable in the runner environment
- **When** execution starts
- **Then** Jack **reports that browser as unavailable with a clear reason**
- **And** **other available configured browsers can still run** if policy allows (default policy = run the available ones, report the rest as unavailable — do not abort the whole run)

### AC3 — Authenticated context without storing/logging credentials

- **Given** browser execution requires an authenticated context
- **When** a configured session is available
- **Then** Jack **uses the configured browser context/session** (the captured `storageState`) without **storing or logging credentials**
- **And** (implementation default, CONFIRMED 2026-06-21) when **no** captured session exists for the selected `(environment, role)`, Jack **hard-blocks** the run with a UX-DR12 guidance message — it does not fall back to an unauthenticated run (see Decision #3)

---

## ⚠️ Sequencing dependency (READ FIRST)

This is **Story 4 of Epic 14**, building on **14.1** (Jack gate + input panel), **14.2** (the runner + `TestExecutionResult` + environment→`APP_BASE_URL`), and **14.3** (output paths). Verify before starting:

1. **`src/ai_qa/pipelines/script_runner.py` (14.2)** already takes `browser` + a `storage_state_path` parameter as the forward-compat seam 14.2 reserved (single-browser passed `chromium` + `None`). If the runner does not yet accept these, widen its signature here.
2. **`TestExecutionResult.browser` column (14.2)** exists — 14.4 writes one row per `(test, browser)`.
3. **The captured-session stack exists and is live** (recently built, currently untracked): the `CapturedSession` model ([db/models.py:95-135](src/ai_qa/db/models.py:95)), `resolve_storage_state(...)` ([sessions/service.py:133-160](src/ai_qa/sessions/service.py:133)), and the capture API ([api/sessions.py](src/ai_qa/api/sessions.py)). Memory confirms the storageState-reuse design is **LIVE-VALIDATED** for cookie-based corporate SSO ([project-environments-feature](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\project-environments-feature.md), [design-test-login-credentials-and-sessions-2026-06-20.md](_bmad-output/planning-artifacts/design-test-login-credentials-and-sessions-2026-06-20.md)). If `resolve_storage_state` is absent, **flag and stop**.
4. **`Project.app_roles`** ([db/models.py:77-82](src/ai_qa/db/models.py:77)) supplies the role list; `Project.environments` ([db/models.py:72-76](src/ai_qa/db/models.py:72)) supplies the environment. Together they form the `(environment × role)` key a `CapturedSession` is stored under ([db/models.py:107-116](src/ai_qa/db/models.py:107)).

> Reconcile every cited `file:line` / snippet against live code and treat them as **leads to verify**, not gospel ([verify-subagent-claims](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\verify-subagent-claims.md), [create-story-snippet-hazards](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\create-story-snippet-hazards.md)).

---

## ⚠️ CRITICAL: how pytest-playwright takes browsers + storageState

The runner shells out to `pytest` with the `pytest-playwright` plugin (added in 14.2). Two mechanisms to get right:

- **Browser selection = repeated `--browser` flags + `--browser-channel`.** `pytest-playwright` parametrizes tests per browser engine: `--browser chromium --browser firefox --browser webkit` runs every test once per engine and suffixes the test id with `[chromium]`/`[firefox]`/`[webkit]` (which the JUnit XML carries → maps cleanly to the `browser` column). **Edge and Chrome are not separate engines** — they are Chromium **channels**: `--browser chromium --browser-channel msedge` (Edge) / `--browser-channel chrome` (Chrome). A `--browser-channel` applies to the whole pytest invocation, so **a distinct channel needs its own runner invocation** (you cannot mix `msedge` and `chrome` channels in one pytest call). Plan the matrix as a list of `(engine, channel)` invocations; merge results.
- **Authenticated context = override `browser_context_args` in a generated `conftest.py`.** `pytest-playwright` has **no `--storage-state` CLI flag**; you inject the session by writing the `storageState` JSON to a temp file and generating a `conftest.py` in the runner temp dir that overrides the `browser_context_args` fixture to include `storage_state=<path>` (and `base_url`/`ignore_https_errors` as needed):

  ```python
  # generated conftest.py (runner temp dir)
  import pytest
  @pytest.fixture(scope="session")
  def browser_context_args(browser_context_args):
      return {**browser_context_args, "storage_state": "storage_state.json"}
  ```

  The `storage_state.json` is the decrypted blob from `resolve_storage_state(...)` — **written only to the transient temp dir, deleted with it, never persisted/logged/messaged** (it is a live credential — [db/models.py:98-104](src/ai_qa/db/models.py:98)).

> ⚠️ **WebKit / "Safari" on Windows:** Playwright bundles a WebKit engine that *can* run on Windows, but real **Safari is not available on Windows** ([project-environments-feature](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\project-environments-feature.md), the RBAC redesign notes "Safari not on Windows"). Treat WebKit availability as **environment-dependent** and surface it through the AC2 "unavailable with a clear reason" path rather than assuming it.

---

## Scope decisions (defaults chosen from code + ACs — confirm or correct via Saved Questions)

- **Decision #1 — available browsers = a known set probed for availability; user picks per-run (RECOMMENDED).** The candidate set is `{chromium, firefox, webkit, msedge (chromium+channel), chrome (chromium+channel)}`. The runner **probes** each (e.g. attempt launch / check the installed Playwright browsers / channel resolution) and reports which are available. The Jack input panel (14.1) gains a **browser multi-select** (default = `chromium`). Requested-but-unavailable browsers → AC2 path. (Saved Q#1 — alternative: an admin-configured per-project browser list instead of per-run selection.)
- **Decision #2 — matrix = list of `(engine, channel)` runner invocations, merged (RECOMMENDED).** Because `--browser-channel` is per-invocation, run one pytest invocation per distinct channel group: e.g. `[chromium/none, firefox/none, webkit/none]` in one call (multiple `--browser`), plus a separate call for `chromium/msedge` and another for `chromium/chrome`. Each invocation writes its own JUnit XML; the runner merges per-`(test, browser_label)`. `browser_label` = the channel name when set (`msedge`/`chrome`), else the engine (`chromium`/`firefox`/`webkit`). Keep `script_runner.run_scripts(..., browsers: list[BrowserSpec])` as the single entry — the agent passes the selected matrix.
- **Decision #3 — authenticated context = resolve `storageState` for `(environment, role)` and inject via generated conftest; HARD-BLOCK when none exists (CONFIRMED 2026-06-21 by Thuong).** After environment selection (14.2), the Jack panel adds a **role** selector populated from `Project.app_roles`. Jack calls `resolve_storage_state(db, user_id=current_user, project_id, environment, role)`; if a blob exists, write it to the temp dir and inject via `browser_context_args` (above). If **no** session is captured for the chosen `(env, role)` → **BLOCK execution** (mirror the 14.1 AC3 block shape): send a UX-DR12 *What happened / Why / What to do* message ("Jack cannot run: no captured session for {env}/{role}. Capture a session for that environment+role first, then run again."), stay in the gate, start **no** subprocess and run **no** browser. Rationale (Thuong): the app under test is authenticated — running unauthenticated would produce misleading failures, so every Jack run requires a valid session. The message links the user to the capture flow ([api/sessions.py](src/ai_qa/api/sessions.py)).
- **Decision #4 — unavailable-browser policy = run-available-report-rest (AC2).** Default policy: run every available requested browser; for each unavailable one, write a synthetic per-script `status="skipped"`/`unavailable` `TestExecutionResult` (or a run-summary `unavailable_browsers` list) with a clear reason ("Edge channel not installed on the runner"). Never abort the whole matrix because one browser is missing. (Saved Q#3 — alternative: a strict policy that fails the run if any requested browser is unavailable.)
- **Decision #5 — per-browser result rows reuse the 14.2 schema.** No new table — `TestExecutionResult.browser` (14.2) already distinguishes rows; 14.4 just writes N rows per test (one per browser) and the run summary gains `browsers: [...]` + `unavailable_browsers: [...]`. Output attachments are already **browser-aware-named** (14.3 names them `{test}__{browser}.png`) — no path change.
- **Out of scope for 14.4:** the report *composition* (14.5) and the review UX/history (14.6) — though 14.4 must ensure the per-browser rows + browser breakdown data exist for them. Capturing a new session (the capture flow itself) is the existing sessions feature — 14.4 **consumes** `resolve_storage_state`, it does not build capture. Role-based *script grouping* (the RBAC redesign) is a future epic — keep role usage limited to session resolution + `APP`-context, not script filtering.

## What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status / action |
| --- | --- | --- |
| `script_runner.run_scripts(...)` with `browser` + `storage_state_path` seam (14.2) | `src/ai_qa/pipelines/script_runner.py` | ✅ **widen** to `browsers: list[BrowserSpec]` + per-browser merge |
| `TestExecutionResult.browser` column (per-browser rows) | `src/ai_qa/db/models.py` (14.2) | ✅ write N rows per test |
| `CapturedSession` model — `(user, project, environment, role)` unique, encrypted `storageState`, never returned to FE | [db/models.py:95-135](src/ai_qa/db/models.py:95) | ✅ the auth store; read-only here |
| `resolve_storage_state(db, *, user_id, project_id, environment, role) -> dict \| None` (the ONLY blob reader, for browser rehydration) | [sessions/service.py:133-160](src/ai_qa/sessions/service.py:133) | ✅ **call** to get the session; write to temp, inject, delete |
| `list_session_status(...)` (non-secret status — captured/role/env/cookie count) | [sessions/service.py:118-130](src/ai_qa/sessions/service.py:118) | ✅ tell the panel which (env, role) sessions exist |
| Capture API (`POST /{project_id}/sessions/capture`) + session router | [api/sessions.py](src/ai_qa/api/sessions.py) | ✅ existing capture flow — link the user to it when a session is missing |
| `Project.app_roles` (role list) + `Project.environments` (env list + URL) | [db/models.py:72-82](src/ai_qa/db/models.py:72) | ✅ populate the panel's role/env selectors |
| `SarahInputsForm.tsx` (env dropdown + CDP/Chrome choices) — the inputs-form template | [SarahInputsForm.tsx](frontend/src/components/agents/SarahInputsForm.tsx) | ✅ **mirror** for Jack's env+role+browser selection |
| pytest-playwright (added in 14.2) `--browser` / `--browser-channel` + `browser_context_args` fixture | (dependency, 14.2) | ✅ multi-browser + storageState injection mechanism |
| `run_e2e_tests` deploy flags (`E2E_NO_SANDBOX`, `PLAYWRIGHT_IGNORE_HTTPS_ERRORS`, headless) | [admin.py](src/ai_qa/api/admin.py) | ✅ apply per browser invocation |
| Browser-use CDP/launch precedent (Chrome path, headless-vis tradeoffs) | [browser/explorer.py](src/ai_qa/browser/explorer.py) | ✅ reference for browser-launch nuances (not reused directly — Jack uses pytest-playwright, not browser-use) |

---

## Tasks / Subtasks

- [x] **Task 1 — Browser matrix in `script_runner.py` (AC1, AC2)** — [script_runner.py](src/ai_qa/pipelines/script_runner.py)
  - [x] Define a `BrowserSpec` (engine: `chromium`/`firefox`/`webkit`, channel: `None`/`msedge`/`chrome`, label) and widen `run_scripts(..., browsers: list[BrowserSpec], storage_state_path: str | None)`.
  - [x] **Availability probe:** before running, determine which specs are available (probe via Playwright's installed-browsers / a cheap launch attempt / channel resolution). Return unavailable specs with a reason; do not let one missing browser abort the rest (AC2).
  - [x] **Invocation grouping:** build one pytest invocation per distinct channel group (no-channel engines can share one call via repeated `--browser`; each `--browser-channel` value needs its own call). Each invocation: own temp `--junit-xml`. Merge results into per-`(test, browser_label)` records, reading the `[engine]` suffix from the JUnit test ids and tagging the channel.
  - [x] Keep the engine pure-ish/unit-testable (probe + command-building + merge are testable without launching browsers).

- [x] **Task 2 — Authenticated context injection (AC3)** — [script_runner.py](src/ai_qa/pipelines/script_runner.py) + [jack.py](src/ai_qa/agents/jack.py)
  - [x] In Jack `_begin_execution` (14.2), after env+role selection, call `resolve_storage_state(db, user_id=<current user>, project_id, environment, role)`. If a blob is returned, write it to `<tmpdir>/storage_state.json` and pass `storage_state_path` to the runner. If **None** → **hard-block** (Decision #3): send the UX-DR12 "no captured session for {env}/{role}; capture one first" message, stay in the gate, and start **no** subprocess / **no** browser. Do NOT fall back to an unauthenticated run.
  - [x] In the runner, when `storage_state_path` is set, generate the `conftest.py` overriding `browser_context_args` to include `storage_state=<path>` (+ `ignore_https_errors` under server mode). The blob file lives **only** in the transient temp dir; ensure it is deleted with the dir even on failure (try/finally).
  - [x] **Secret containment:** never log/print the blob or its contents; never put it in a message, the run summary, `TestExecutionResult`, or any persisted output. The leak-canary convention applies (a captured-cookie value must never appear in any output channel).

- [x] **Task 3 — Persist per-browser results + unavailable browsers (AC1, AC2)** — [jack.py](src/ai_qa/agents/jack.py)
  - [x] Write one `TestExecutionResult` per `(test, browser_label)` (14.2 schema). For each unavailable requested browser, record it (synthetic `skipped`/`unavailable` rows per script, or a `unavailable_browsers` list in the run summary — pick one and be consistent; rows are friendlier for 14.6 filtering).
  - [x] Extend the run summary in `AgentRun.execution_metadata` with `browsers: [...]`, `unavailable_browsers: [{label, reason}]`, and per-browser counts (the "browser breakdown" 14.6 renders).

- [x] **Task 4 — Frontend: browser multi-select + role selector (AC1, AC3)** — Jack panel + [App.tsx](frontend/src/App.tsx)
  - [x] Extend the Jack input surface (14.1 `JackInputSelection.tsx` / 14.2 `JackInputsForm.tsx`) with a **browser multi-select** (Chromium, Chrome, Edge, Firefox, WebKit — default Chromium) and a **role** dropdown populated from `project.app_roles` (alongside the 14.2 environment dropdown).
  - [x] Surface which `(env, role)` sessions are captured (via `list_session_status`) — when the selected `(env, role)` has **no** session, **disable the Run/Confirm action** and show a clear "Capture a session for {env}/{role} to run" hint + a link to the capture flow (the backend hard-blocks too — Decision #3 — but disabling the control gives a better UX than a round-trip error). Do NOT display any session value — only the non-secret status.
  - [x] Carry the selected `browsers` + `role` into `handleJackConfirm` → the confirm/start payload. Add `browsers: string[]` + `role: string` to the Jack confirm TS type; keep full-stack sync with the backend payload.
  - [x] Reflect `unavailable_browsers` in the minimal summary surface (full report = 14.6).

- [x] **Task 5 — Backend tests (AC1, AC2, AC3)**
  - [x] `tests/test_pipelines/test_script_runner.py`: matrix grouping (engines vs channels → correct invocation count + flags); availability probe (a missing browser → reported unavailable, others still produce results — patch the probe + `subprocess.run`); merge produces per-`(test, browser_label)` records from per-invocation JUnit XML; `storage_state_path` set → generated conftest contains `storage_state` and the run env includes it; **scrub/containment** test: a storageState value never appears in returned results/logs. Hermetic — no real browsers (mark real-browser as `@pytest.mark.integration`).
  - [x] `tests/test_agents/test_jack.py`: with a captured session present → `resolve_storage_state` called, blob written to temp + passed to runner, then file gone; with **none → HARD-BLOCK** (UX-DR12 message sent, stays in gate, **no** subprocess started, runner NOT called); per-browser `TestExecutionResult` rows created; `unavailable_browsers` recorded. Patch `ai_qa.agents.jack.resolve_storage_state` and the runner. Honor the conftest hazard ([agent-gate-conftest-regression](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\agent-gate-conftest-regression.md)).
  - [x] `tests/sessions/` (if present): `resolve_storage_state` returns the blob for the right `(user, project, env, role)` and `None` otherwise (likely already covered by the sessions feature — extend only if needed).

- [x] **Task 6 — Frontend tests (AC1, AC3)**
  - [x] Vitest: browser multi-select default = Chromium, multi-select toggles, role dropdown from `app_roles`, "no session captured" hint + capture link when status is empty, confirm payload carries `browsers`+`role`. Vitest 4 rules ([project-context.md#Testing-Rules](project-context.md)) — `vi.spyOn(globalThis,"fetch")` for the session-status fetch.
  - [x] E2E: real multi-browser execution needs installed engines + a reachable app + a captured session — integration-only. Default: scope to the panel behavior (browser/role selection renders + confirm sends) and note the live-run deferral.

- [x] **Task 7 — Verify (no migration if 14.2 added `browser`; otherwise migrate)**
  - [x] If `TestExecutionResult.browser` already exists from 14.2 → no migration. If 14.4 adds any column (e.g. an `unavailable` status enum value is just a string — no schema change) → none expected. Confirm in Completion Notes.
  - [x] `uv run pytest --no-cov` (whole suite). `uv run mypy src` clean. Pyrefly-clean. `uv run ruff check --fix` + `ruff format`.
  - [x] Frontend: `npm run lint`, `npm run typecheck`, `npm run test`.
  - [x] **Leak-canary:** assert no `storageState`/cookie value reaches any message, summary, result row, persisted output, or log.

## Dev Notes

### Browser matrix → invocations

```
selected browsers (panel): [Chromium, Edge, Firefox]
        ▼ group by channel (--browser-channel is per-invocation)
invocation A: pytest --browser chromium --browser firefox            (engines, no channel)
invocation B: pytest --browser chromium --browser-channel msedge     (Edge = chromium+msedge)
        ▼ each writes its own results.xml (test ids carry [chromium]/[firefox])
merge → rows: (test, "chromium"), (test, "firefox"), (test, "msedge")
unavailable (e.g. WebKit if requested + missing) → reported with reason  (AC2)
```

### Authenticated context (AC3) — the storageState path

```
panel: environment (14.2) + role (14.4) selected
  → resolve_storage_state(db, user_id, project_id, environment, role)  [sessions/service.py]
      → dict  → write <tmpdir>/storage_state.json (transient)
                generate conftest.py: browser_context_args += {"storage_state": "storage_state.json"}
                run pytest (every browser context starts authenticated)
                delete temp dir (blob gone) — try/finally
      → None → HARD-BLOCK: UX-DR12 "capture a session for {env}/{role} first"; no subprocess  (Decision #3)
```

The `storageState` is a **live credential** ([db/models.py:98-104](src/ai_qa/db/models.py:98)): encrypted at rest, decrypted only by `resolve_storage_state`, materialized only in the transient temp dir, never logged/messaged/persisted. This is the same reuse design Sarah's debug-explore path uses and that is **live-validated** for cookie-based corporate SSO.

### Architecture compliance (hard rules)

- **Secret containment is the headline rule of this story** ([architecture.md:66, 515](_bmad-output/planning-artifacts/architecture.md:66); [db/models.py:98-104](src/ai_qa/db/models.py:98)): the captured `storageState` must never leave the transient temp dir except into the live browser context. No logs, no messages, no artifacts, no result rows. Add a leak-canary test.
- **Mandatory human review** ([architecture.md:271-272](_bmad-output/planning-artifacts/architecture.md:271)): browser/role selection happens before the run; the result review is 14.6.
- **Project-scoped** ([architecture.md:280](_bmad-output/planning-artifacts/architecture.md:280)): sessions and results are keyed by project; resolve only the current user's own session (per-user store — [db/models.py:101-103](src/ai_qa/db/models.py:101)).
- **Backend payload change → matching TS interface** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)): the confirm payload gains `browsers`+`role`.

### Library / framework constraints (from project-context.md)

- **Backend:** Python ≥3.14, `uv` only. Ruff + Mypy strict. Pyrefly-clean (narrow `resolve_storage_state`'s `dict | None`; specific exceptions for launch/probe failures; no bare except). Sync `Session` for `resolve_storage_state`. `asyncio.to_thread` for each subprocess invocation; run the matrix invocations sequentially or with a small bounded concurrency (don't overload the runner host).
- **No new packages** (pytest-playwright already added in 14.2). **No migration** (reuse 14.2's `browser` column).
- **Frontend:** React 19.2, TS strict, Vitest 4, ESLint 9. Path alias `@`. Accessible names on the multi-select + role dropdown (`getByRole`).

### Forward-compat note (not 14.4 scope)

- The Project-Admin RBAC redesign ([design-projectadmin-rbac-redesign-2026-06-21.md](_bmad-output/planning-artifacts/design-projectadmin-rbac-redesign-2026-06-21.md)) will make Jack **role-grouped** (run a script set per role) and add **multi-browser per role**. Keep `role` usage here limited to **session resolution + context**, and keep results keyed generically by `browser` (and resolvable by `role` later). Don't build role-based script grouping now.

### Project Structure Notes

- **Modified files (expected):** `src/ai_qa/pipelines/script_runner.py` (matrix + conftest injection + probe), `src/ai_qa/agents/jack.py` (resolve session, pass matrix, persist per-browser + unavailable), `frontend/src/App.tsx` + the Jack panel/form (browser multi-select + role), `frontend/src/types/` (confirm payload), tests as above.
- **No new runtime module, no migration** (assuming 14.2 added `TestExecutionResult.browser`).

### Testing standards summary

- Backend: hermetic — patch the availability probe + `subprocess.run` + `resolve_storage_state`; real browsers are `@pytest.mark.integration`. Whole-suite `--no-cov`; mypy `src` only. Leak-canary for the storageState blob.
- Frontend: Vitest for panel selection + session-status hint; E2E scoped to panel behavior.

### Previous-story / sibling intelligence

- **Story 14.2** — the runner + `TestExecutionResult.browser` + env→`APP_BASE_URL`; widen its `browser`/`storage_state_path` seam here.
- **Story 14.3** — names attachments browser-aware (`{test}__{browser}.png`) — multi-browser reuses those paths.
- **Captured-session feature (live, untracked)** — `resolve_storage_state` + `CapturedSession` + capture API; live-validated for cookie-based SSO ([project-environments-feature](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\project-environments-feature.md)). 14.4 consumes it; does not rebuild capture.
- **Story 13.4 (Sarah browser-SSO session compatibility, `done`)** — established the storageState-reuse precedent for driving the app with an authenticated session; Jack applies the same idea to execution.

### References

- [Source: _bmad-output/planning-artifacts/epics.md:1505-1525] — Story 14.4 ACs (multi-browser, unavailable handling, authenticated context)
- [Source: _bmad-output/planning-artifacts/architecture.md] — `[Chrome/Firefox/Edge]` execution target (833); secret containment (66, 515); mandatory review (271-272); project-scoped (280)
- [Source: src/ai_qa/db/models.py:95-135] — `CapturedSession` (`(user,project,env,role)` unique, encrypted blob, never to FE/logs); (72-82) `Project.environments`/`app_roles`
- [Source: src/ai_qa/sessions/service.py:118-160] — `list_session_status` (non-secret status) + `resolve_storage_state` (the only blob reader, for rehydration)
- [Source: src/ai_qa/api/sessions.py] — capture endpoint (the flow to link to when a session is missing)
- [Source: src/ai_qa/prompts/script_generation.py:88-104, 289, 314] — scripts assume a pre-authenticated session injected at execution time; never hardcode creds
- [Source: src/ai_qa/api/admin.py] — deploy flags (`E2E_NO_SANDBOX`, `PLAYWRIGHT_IGNORE_HTTPS_ERRORS`, headless) to apply per invocation
- [Source: frontend/src/components/agents/SarahInputsForm.tsx] — env dropdown / inputs-form template to mirror for env+role+browser
- [Source: _bmad-output/planning-artifacts/design-test-login-credentials-and-sessions-2026-06-20.md] — captured-session / storageState reuse design (live-validated)
- [Source: project-context.md] — secret containment; `uv`/`npm` only; Ruff + Mypy strict; Pyrefly; full-stack sync; no new packages

## Saved Questions (for Thuong — defaults applied; confirm or correct)

**RESOLVED 2026-06-21 (Thuong):** Missing `(env, role)` session = **HARD-BLOCK** the run (no unauthenticated fallback) — **confirmed** (Decision #3 / AC3).

Still open:

1. **Browser source (Decision #1).** Default = per-run user multi-select (default Chromium), runner probes availability. Alternative = admin-configured per-project browser list. Default = per-run selection. OK?
2. **Unavailable-browser policy (Decision #4).** Default = run the available browsers, report the rest as unavailable (don't abort). Alternative = strict (fail the run if any requested browser is missing). Default = run-available. Confirm?
3. **WebKit in the default offering.** Include WebKit in the panel's browser choices (availability-gated), or omit it on Windows hosts entirely? Default = offer it, gated by the availability probe.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, bmad-dev-story workflow)

### Debug Log References

- `uv run pytest tests/test_agents/test_jack.py tests/pipelines/test_script_runner.py --no-cov` → 37 passed
- `uv run pytest --no-cov` (whole suite) → 1677 passed; `uv run mypy src` clean (93); ruff clean
- Frontend: `npm run typecheck` + `npm run lint` clean; `npx vitest run` → 30 files / 324 passed (JackInputSelection 13)
- `resolve_storage_state`/`list_session_status` verified live in `sessions/service.py` (the captured-session stack)

### Completion Notes List

- **CONFIRMED + defaults:** Decision #3 (CONFIRMED) — missing `(env, role)` session = **HARD-BLOCK** (no unauthenticated fallback); Decision #1 per-run browser multi-select (default Chromium) with availability probe; Decision #2 matrix = `(engine, channel)` invocations merged; Decision #4 run-available-report-rest; WebKit offered, availability-gated.
- **AC1** — `script_runner` widened: `BrowserSpec(engine, channel)`, `run_scripts(..., browsers: list[BrowserSpec])`. `group_invocations` runs one pytest call for no-channel engines (repeated `--browser`) + one per channel (`--browser-channel`, per-invocation). Results merge per `(test, browser_label)`; channel groups relabel results to the channel (JUnit ids carry the engine). One `TestExecutionResult` row per `(test, browser)` (14.2 schema reused — **no migration**).
- **AC2** — `probe_browser_availability` does a cheap headless launch per spec; unavailable specs are reported (`{label, reason}`) and never abort the others. Run summary gains `browsers` + `unavailable_browsers`; the panel + execution-summary surface them.
- **AC3** — Jack `_confirm_inputs` calls `resolve_storage_state(db, user_id, project_id, environment, role)`; **None → hard-block** (UX-DR12, no subprocess). A blob is passed to the runner, which writes it to `<tmp>/storage_state.json` + generates a `conftest.py` overriding `browser_context_args` (`storage_state=…`). The runner-created tmp dir (holding the blob) is **always rmtree'd in `finally`** (created_tmp). Jack clears `self._storage_state` in a `finally` after the run.
- **Secret containment (headline rule):** the storageState never leaves the transient temp dir (deleted) or the agent's in-memory field (cleared); `build_subprocess_env` strips secret env keys; `scrub_secrets` redacts cookie/bearer/key patterns. Leak-canary test: a cookie value in the blob never appears in `run.log`/summary/results. The panel shows only non-secret `(env, role)` session status via `list_session_status` (never a value).
- **Frontend** — `JackInputSelection` gains a **role dropdown** (`app_roles`), a **browser multi-select** (Chromium/Chrome/Edge/Firefox/WebKit, default Chromium), and **session awareness** (disable Run + hint when the selected `(env, role)` has no captured session). `onConfirm` now emits `{targetUrl, environment, role, browsers}`. The summary card renders `browsers` + `unavailable_browsers`. Full-stack sync via `execution.ts`.
- **No migration** — reuses 14.2's `TestExecutionResult.browser`. The captured-session stack is consumed, not rebuilt.
- **E2E deferral:** real multi-browser + auth runs need installed engines + a reachable app + a captured session (integration-only). Hermetic backend tests patch `probe_browser_availability` + `subprocess.run` + `resolve_storage_state`. Panel behavior covered by Vitest.

### File List

- `src/ai_qa/pipelines/script_runner.py` — `BrowserSpec`/`browser_spec_from_label`/`group_invocations`/`probe_browser_availability`/conftest injection; `run_scripts` matrix + `storage_state` + temp-dir cleanup; `RunSummary.browsers`/`unavailable_browsers` (M)
- `src/ai_qa/agents/jack.py` — role/browser/session resolution + hard-block + matrix + secret clearing; `_project_app_roles`/`_captured_sessions` (M)
- `frontend/src/types/execution.ts` — `browsers`/`unavailable_browsers`/`UnavailableBrowser` (M)
- `frontend/src/components/agents/JackInputSelection.tsx` — role + browser multi-select + session hint; `JackRunConfig` (M)
- `frontend/src/App.tsx` — pass app_roles/sessions; confirm config; summary browsers/unavailable (M)
- `tests/pipelines/test_script_runner.py` — matrix/probe/grouping/conftest/leak-canary tests (M)
- `tests/test_agents/test_jack.py` — session hard-block + per-browser + payload-keys tests (M)
- `frontend/src/components/__tests__/JackInputSelection.test.tsx` — role/browser/session tests (M)

### Change Log

- 2026-06-21 — Story 14.4 implemented: multi-browser matrix (engine + channel invocations, availability probe, per-browser rows, unavailable reporting) + authenticated context (captured `storageState` injected via generated conftest, hard-block when none, strict secret containment) + role/browser panel UI. No migration. Status → review.
