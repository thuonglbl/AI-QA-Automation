---
baseline_commit: 0de0b7c
---

# Story 14.6: Execution Report Review UX

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want to view execution summaries and drill into individual test details, and browse past runs,
so that I can quickly understand pass/fail/error status, investigate failures with the linked script, source test case, logs, screenshots and traces, and compare runs over time.

## Acceptance Criteria

Verbatim from [epics.md#Story-14.6](_bmad-output/planning-artifacts/epics.md) (lines 1548-1566), expanded with implementation defaults (see "Scope decisions"). This is the **review-UX capstone** of Epic 14: it renders the structured results (14.2/14.4), the report (14.5), and the linked attachments (14.3) into Jack's step-5 surface, and adds a filterable execution history.

### AC1 — Report summary view

- **Given** an execution report exists
- **When** the user opens it
- **Then** the UI shows **overall pass/fail/error counts, success rate, duration, browser breakdown, and run metadata**

### AC2 — Per-test drilldown

- **Given** individual test results exist
- **When** the user selects a test result
- **Then** the UI shows the **linked script, source test case, failure details, logs, screenshots/traces where available, and safe stack trace details**

### AC3 — Filterable execution history

- **Given** multiple reports exist for a project
- **When** the user views execution history
- **Then** reports are **sorted by run time** and **filterable by project, thread, browser, result, and date range**

---

## ⚠️ Sequencing dependency (READ FIRST)

This is **Story 6 (final) of Epic 14**, consuming **14.1** (Jack step-5 surface + `handleJackMessage`/`jackState`), **14.2/14.4** (`TestExecutionResult` rows + `AgentRun.execution_metadata` summary, browser breakdown, unavailable browsers), **14.3** (persisted screenshot/trace/log attachments), and **14.5** (the `report.md` + hidden `report.json` link map + `execution_summary.report_artifact_id`). Verify before starting:

1. **`TestExecutionResult` rows** carry per-`(test, browser)` status/duration/error/classification + `source_script_artifact_id`/`source_test_case_artifact_id`.
2. **`execution_summary` message** (14.2) reaches the frontend with counts + `report_artifact_id` (14.5); `handleJackMessage` (14.1) already routes Jack messages into `jackState`.
3. **`report.json`** (14.5, `kind="configuration"`) holds the attachment link map (`{test::browser} → {screenshot_id, trace_id, log_id}`) and per-test data; the existing artifact content endpoint can fetch it by id.
4. **The artifact content endpoint** ([api/artifacts.py](src/ai_qa/api/artifacts.py)) serves attachment bytes (screenshots/traces/logs) membership-gated; the FE `ArtifactPreview` already renders `.md`/`.json`/images.

If the structured results or `report.json` are absent, **flag and stop** — this story is a consumer.

> Reconcile every cited `file:line` / snippet against live code; treat them as **leads to verify** ([verify-subagent-claims](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\verify-subagent-claims.md), [create-story-snippet-hazards](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\create-story-snippet-hazards.md)).

---

## ⚠️ CRITICAL: this story needs a small NEW read API (filtering can't come from artifacts alone)

The summary view (AC1) and the drilldown (AC2) can be served from `report.json` (14.5) for a single run. But **AC3's history filtering "by project, thread, browser, result, and date range"** cannot come from artifact blobs — it needs to **query `TestExecutionResult` rows + `AgentRun`** in the DB. So 14.6 adds a small **executions read API** (membership-gated, project-scoped), mirroring the existing routers:

- `GET /api/projects/{project_id}/executions` → list run summaries (one per Jack `agent_run` that produced results), **sorted by run time desc**, with query filters `thread_id?`, `browser?`, `result?` (passed/failed/error), `date_from?`, `date_to?`. Each item: run id, started/completed, totals, success rate, browsers, thread id, report artifact id.
- `GET /api/projects/{project_id}/executions/{run_id}` → one run's detail: summary + per-`(test, browser)` results (status, duration, classification, scrubbed error/stack) + `source_script_artifact_id`/`source_test_case_artifact_id` + attachment link map (from `report.json` or result columns).

Reuse the existing project-membership dependency (the pattern in [api/sessions.py](src/ai_qa/api/sessions.py)/[api/artifacts.py](src/ai_qa/api/artifacts.py)) so access is gated by membership (AC3 "according to project membership"). Register the router in [api/app.py](src/ai_qa/api/app.py) next to the others. Per project memory, **never `mock.patch` a FastAPI dependency** — test via `app.dependency_overrides` ([project-context.md#FastAPI](project-context.md)).

---

## Scope decisions (defaults chosen from code + ACs — confirm or correct via Saved Questions)

- **Decision #1 — new `executions` read API for summaries + detail + history (RECOMMENDED).** Add `src/ai_qa/api/executions.py` (list + detail, membership-gated, filterable). It reads `TestExecutionResult` + `AgentRun` (eager-loaded — no `MissingGreenlet`). The single-run summary/drilldown the chat opens can come from this detail endpoint and/or `report.json`; history comes from the list endpoint. (Saved Q#1 — alternative: serve single-run from `report.json` only and add just the list endpoint for history.)
- **Decision #2 — UI = three React pieces in `components/agents` (RECOMMENDED):**
  - `JackExecutionReport.tsx` — the summary card (counts, success-rate ring/bar, duration, browser breakdown, unavailable browsers, run metadata) + a per-test results **table** (test, browser, status chip, duration, failure summary) with row-select.
  - `ExecutionResultDetail.tsx` — the per-test drilldown panel (linked script + source test case links, failure classification, **safe stack trace**, logs preview, screenshots inline, trace download) shown on row-select.
  - `ExecutionHistory.tsx` — the filterable, run-time-sorted run list (filters: thread, browser, result, date range) that opens a run into the report view.
  Mirror existing agent panels (`SarahScriptReviewPanel.tsx`/`MaryReviewPanel.tsx`) for structure/styling and the `ArtifactPreview` patterns for attachment rendering. (Saved Q#2 — alternative: fold history into the existing artifacts/Reports sidebar instead of a dedicated panel.)
- **Decision #3 — rendering attachments via the existing artifact content endpoint (RECOMMENDED).** Screenshots → inline `<img>` from the artifact content endpoint (base64/image path `ArtifactPreview` already supports); logs → text preview; traces (`.zip`) → a **download link** (the Playwright trace viewer is external — do not try to render a trace inline). Each attachment is fetched by its artifact id from the link map; **missing attachment → "(not available)"**, never a broken image/crash (mirrors 14.5 AC2 tolerance).
- **Decision #4 — Jack step-5 render flow.** Extend `handleJackMessage` (14.1) to store `execution_summary` (counts + `report_artifact_id`) in `jackState`; render `JackExecutionReport` when `isJackStep && jackState` has a summary. Keep the live-queue + history-restore dual-registration rule (both effects + dep arrays) so the report restores on reload. The "Execution History" entry can live in the Jack panel header and/or the project sidebar Reports area.
- **Decision #5 — safe stack trace = render the already-scrubbed field as-is.** `TestExecutionResult.stack_trace` was scrubbed at capture time (14.2); the UI renders it in a collapsible `<pre>` and **does not** re-fetch or re-derive raw traces. No secret ever transits this surface (the data is pre-scrubbed server-side).
- **Decision #6 — TS types in `frontend/src/types/execution.ts`** (mirror `testcase.ts`/`pipeline.ts` patterns): `ExecutionRunSummary`, `ExecutionResult`, `ExecutionReport`, `ExecutionHistoryFilters` — kept in **exact sync** with the new API payloads (full-stack sync rule).
- **Out of scope for 14.6:** the runner/execution (14.2), output persistence (14.3), the browser matrix/auth (14.4), report composition (14.5), and the leadership **metrics dashboard / aggregation** (that is Epic 19 — 14.6 is per-project execution review, not cross-project KPIs).

## What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status / action |
| --- | --- | --- |
| Jack step-5 surface: `isJackStep`/`jackState`/`handleJackMessage`/render/auto-start (14.1) | [frontend/src/App.tsx](frontend/src/App.tsx) | ✅ **extend** to render the report on `execution_summary` |
| `execution_summary` message + `report_artifact_id` (14.2/14.5) | (backend messages) | ✅ the entry point — open the report from it |
| `TestExecutionResult` + `AgentRun.execution_metadata` (per-test + summary data) | `src/ai_qa/db/models.py` / [threads/models.py:63-78](src/ai_qa/threads/models.py:63) | ✅ the read API's data source |
| `report.json` link map (14.5) | execution report artifact (`kind="configuration"`) | ✅ attachment ids per `(test, browser)` |
| Artifact content endpoint (membership-gated bytes; images/text) + `ArtifactPreview` | [api/artifacts.py](src/ai_qa/api/artifacts.py), [ArtifactPreview.tsx](frontend/src/components/artifacts/ArtifactPreview.tsx) | ✅ render screenshots/logs; download traces |
| Existing membership-gated routers + project dependency (the API pattern) | [api/sessions.py](src/ai_qa/api/sessions.py), [api/projects.py](src/ai_qa/api/projects.py) | ✅ **mirror** for `executions.py`; register in [app.py](src/ai_qa/api/app.py) |
| Agent review-panel components (table, chips, expandable detail, side-by-side) | [SarahScriptReviewPanel.tsx](frontend/src/components/agents/SarahScriptReviewPanel.tsx), [MaryReviewPanel.tsx](frontend/src/components/agents/MaryReviewPanel.tsx) | ✅ **mirror** for the report panel + drilldown |
| `AGENTS.Jack` metadata (step 5, color `#F97316`, title) | [pipeline.ts:229-236](frontend/src/types/pipeline.ts:229) | ✅ use for labels/colors |
| TS payload-type pattern (`TestCaseInput`, `ScriptReviewItem`) | [testcase.ts](frontend/src/types/testcase.ts) | ✅ **mirror** for `execution.ts` |
| `useArtifactSync` / realtime artifact refresh (a new report appears live in Reports) | [useArtifactSync.ts](frontend/src/hooks/useArtifactSync.ts) | ✅ history list/Reports refresh when a run finishes |
| Reports sidebar folder (shows `report.md`, hides `configuration`) | [ProjectSidebar.tsx](frontend/src/components/projects/ProjectSidebar.tsx) | ✅ `report.md` opens via preview; history can link from here |

---

## Tasks / Subtasks

- [x] **Task 1 — Executions read API (AC1, AC2, AC3)** — new `src/ai_qa/api/executions.py`
  - [x] `GET /api/projects/{project_id}/executions` — list run summaries (one per Jack `agent_run` with results), **ordered by run time desc**, with optional filters `thread_id`, `browser`, `result`, `date_from`, `date_to`. Query `TestExecutionResult`/`AgentRun` with eager loading; aggregate counts + success rate per run. Pydantic response models (`ExecutionRunSummaryResponse`).
  - [x] `GET /api/projects/{project_id}/executions/{run_id}` — one run: summary + per-`(test, browser)` results (status, duration, classification, **scrubbed** error/stack) + `source_script_artifact_id`/`source_test_case_artifact_id` + attachment link map (from `report.json` or result columns).
  - [x] Gate both with the existing project-membership dependency; register the router in [app.py](src/ai_qa/api/app.py). Async SQLAlchemy: eager-load (`selectinload`/`joinedload`) + `.unique()` on joined collections; only serialize what the schema needs ([project-context.md#SQLAlchemy](project-context.md)).

- [x] **Task 2 — TS types (AC1, AC2, AC3)** — new `frontend/src/types/execution.ts`
  - [x] `ExecutionResult` (`test_name`, `browser`, `status`, `duration_ms`, `failure_classification?`, `error_message?`, `stack_trace?`, `source_script_artifact_id?`, `source_test_case_artifact_id?`, `screenshot_artifact_id?`, `trace_artifact_id?`, `log_artifact_id?`), `ExecutionRunSummary` (run id, started/completed, totals, `success_rate`, `browsers`, `unavailable_browsers`, `thread_id`, `report_artifact_id`), `ExecutionReport` (summary + `results: ExecutionResult[]`), `ExecutionHistoryFilters`. Match the API payloads exactly.

- [x] **Task 3 — `JackExecutionReport.tsx` (AC1)** — `frontend/src/components/agents/`
  - [x] Summary card: pass/fail/error counts, **success rate** (ring or bar), total duration, **browser breakdown** (per-browser passed/failed), **unavailable browsers** with reasons, run metadata (run id, started/completed, environment host, thread). Use `AGENTS.Jack.color` `#F97316`.
  - [x] Per-test results **table** (test, browser chip, status chip, duration, short failure summary), with row-select → opens `ExecutionResultDetail`. Accessible: `getByRole` table/row/button names.

- [x] **Task 4 — `ExecutionResultDetail.tsx` (AC2)** — `frontend/src/components/agents/`
  - [x] On a selected result: **linked script** (open the script artifact) + **source test case** (open the test-case artifact) by id; **failure details** (classification + message); **safe stack trace** in a collapsible `<pre>` (render the pre-scrubbed field — Decision #5); **logs** preview (text); **screenshots** inline (`<img>` via artifact content); **trace** as a download link. **Missing attachment → "(not available)"**, never a broken image (Decision #3). Reuse `ArtifactPreview` patterns for fetching/rendering.

- [x] **Task 5 — `ExecutionHistory.tsx` (AC3)** — `frontend/src/components/agents/`
  - [x] A run-time-sorted list of runs (from the list API) with filter controls: **thread**, **browser**, **result**, **date range** (the API does the filtering; the UI passes query params). Selecting a run opens it in `JackExecutionReport`. Empty/zero-state and loading/error states (UX-DR12 style messaging).

- [x] **Task 6 — Wire into Jack step-5 (AC1)** — [App.tsx](frontend/src/App.tsx)
  - [x] Extend `handleJackMessage` (14.1) to capture `execution_summary` (counts + `report_artifact_id`) into `jackState`; register in BOTH the live-queue effect and the history-restore effect (+ dep arrays). Render `JackExecutionReport` (and the history entry) when `isJackStep` and a summary/report exists. Open the detail/history on demand (fetch via the new API). Reset `jackState` in the thread-switch effect.
  - [x] Optional: from the Reports sidebar, opening a `report.md` shows the markdown preview; add an "Open structured report" affordance that routes to `JackExecutionReport` for that run id.

- [x] **Task 7 — Backend tests (AC1, AC2, AC3)**
  - [x] `tests/api/test_executions_api.py` (copy the canonical scaffold from [tests/api/test_admin_rbac_api.py](tests/api/test_admin_rbac_api.py), adapt auth context): list returns runs **sorted by run time desc**; filters by `thread_id`/`browser`/`result`/`date_from`/`date_to` work; detail returns per-test results + provenance + link map; **membership gating** — a member reads, a non-member / other-project member is denied (use `app.dependency_overrides`, NEVER `mock.patch` the dependency). Seed `TestExecutionResult`/`AgentRun` via `session.add`+`commit` (avoid the "forgot to commit → []" trap — [project-context.md#Testing-Rules](project-context.md)).
  - [x] Leak-canary: the API never returns a secret/credential/storageState; `error_message`/`stack_trace` are the scrubbed fields only.

- [x] **Task 8 — Frontend tests (AC1, AC2, AC3)**
  - [x] Vitest for each component: `JackExecutionReport` renders counts/success-rate/browser-breakdown/unavailable + row-select; `ExecutionResultDetail` renders links + safe stack trace + inline screenshot + "(not available)" on missing attachments; `ExecutionHistory` renders sorted list + filter controls drive the query. Vitest 4 rules ([project-context.md#Testing-Rules](project-context.md)) — `vi.spyOn(globalThis,"fetch")` for the executions API; `importOriginal()` when partially mocking; non-null-assert known array elements (`mock.calls[0]![0]`).
  - [x] App-level: `execution_summary` message → report renders in step 5; reload restores it (history-restore effect).
  - [x] Playwright E2E (`frontend/e2e/`): a full run→report E2E needs a reachable app + seeded results — integration-only. Default: seed `TestExecutionResult`/report via the API (or admin), navigate to Jack, assert the summary + a drilldown + a history filter render; clean up in `afterEach` (users/projects/artifacts/results). No `page.route`, no `waitForTimeout`. Note any live-run deferral.

- [x] **Task 9 — Verify (no migration — read-only over existing tables)**
  - [x] `uv run pytest --no-cov` (whole suite). `uv run mypy src` clean. Pyrefly-clean (eager-load; narrow Optionals; bind `mock.call_args` before `.args`/`.kwargs` in tests). `uv run ruff check --fix` + `ruff format`.
  - [x] Frontend: `npm run lint`, `npm run typecheck`, `npm run test`, E2E spec.
  - [x] **No Alembic migration** (read-only API over 14.2/14.4 tables). State explicitly in Completion Notes. Confirm full-stack sync: every new API payload field has a matching `execution.ts` field (`npm run build`).

## Dev Notes

### Data flow into the review UX

```
Jack run finishes (14.2/14.4)  → TestExecutionResult rows + AgentRun.execution_metadata
                               → report.md (visible) + report.json link map (14.5)
                               → execution_summary message (+ report_artifact_id)
        ▼ frontend
handleJackMessage → jackState.summary   → render JackExecutionReport (AC1)
GET /executions/{run_id}                → per-test results + link map → ExecutionResultDetail (AC2)
        attachments via artifact content endpoint (screenshot inline / log text / trace download)
GET /executions?filters…                → ExecutionHistory (sorted, filterable) (AC3)
```

### Why a read API (and not just artifacts)

- A single run's summary/drilldown *could* come from `report.json`, but **history filtering by browser/result/date/thread** is a DB query over `TestExecutionResult`/`AgentRun` — artifact blobs can't filter. The `executions` API is the clean home for both, and it sets up Epic 19's metrics aggregation to reuse the same rows.

### Attachment rendering (AC2)

- Screenshot → `<img src={artifact-content-url}>` (membership-gated endpoint; `ArtifactPreview` already does images).
- Log → text preview (truncate + "view full").
- Trace (`.zip`) → **download** link only (Playwright trace viewer is external; never attempt to render a zip inline).
- Every attachment is keyed by artifact id from the link map; a `null`/missing id renders "(not available)" — never a broken image or a crash (tolerant, mirrors 14.5 AC2).

### Architecture compliance (hard rules)

- **Project-scoped + membership-gated retrieval** ([architecture.md:280](_bmad-output/planning-artifacts/architecture.md:280); AC3) — reuse the existing membership dependency; test member vs non-member vs other-project.
- **Secret containment** ([architecture.md:66, 515](_bmad-output/planning-artifacts/architecture.md:66)) — the API returns only scrubbed `error_message`/`stack_trace` and artifact ids; no credential/storageState ever reaches the client. Add a leak-canary API test.
- **Async DB correctness** ([project-context.md#SQLAlchemy](project-context.md)) — eager-load, `.unique()` on joined collections, don't over-fetch.
- **FastAPI dep testing** — `app.dependency_overrides` + `cast(FastAPI, client.app)`, never `mock.patch` a dependency.
- **Full-stack sync** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)) — `execution.ts` matches the API payloads; `npm run build`.
- **App UI English-only** ([app-ui-english-only](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\app-ui-english-only.md)) — every label/button/empty-state string in English.

### Library / framework constraints (from project-context.md)

- **Backend:** Python ≥3.14, `uv` only. Ruff + Mypy strict. Pyrefly-clean (eager-load; `session.get` → `T | None` filtering; specific exceptions; bind mock call records before `.args`/`.kwargs`). New router registered in `app.py`.
- **Frontend:** React 19.2, TS ~6.0 strict (`noUncheckedIndexedAccess` → `arr[0]!`), Tailwind v4, Vitest 4 (`vi.mock` hoisted file-wide; prefer fetch-spy; `importOriginal()`), ESLint 9. Path alias `@`. Accessible names on table rows/filters/buttons (`getByRole`). Charts/visuals: prefer simple CSS/SVG (success-rate bar/ring) — no new chart package unless justified.
- **No new backend packages. No migration** (read-only over existing tables).

### Forward-compat note (not 14.6 scope)

- Epic 19 (Audit/Metrics, backlog) builds the **leadership cross-project metrics dashboard** on the same `TestExecutionResult` rows. Keep the `executions` API/list shape generic and the success-rate/duration aggregation reusable so 19-4/19-5 can extend rather than fork.

### Project Structure Notes

- **New files:** `src/ai_qa/api/executions.py`, `tests/api/test_executions_api.py`, `frontend/src/components/agents/JackExecutionReport.tsx`, `ExecutionResultDetail.tsx`, `ExecutionHistory.tsx`, `frontend/src/types/execution.ts`, their Vitest specs, an `frontend/e2e/` Jack-report spec.
- **Modified files (expected):** `src/ai_qa/api/app.py` (register `executions` router), `frontend/src/App.tsx` (render report on `execution_summary` + history entry + thread reset), possibly `ProjectSidebar.tsx` (open-structured-report affordance). No model/migration.

### Testing standards summary

- Backend: canonical RBAC scaffold for the API tests; `app.dependency_overrides` for auth; seed rows with `add`+`commit`; assert sort/filter/membership + leak-canary. Whole-suite `--no-cov`; mypy `src` only.
- Frontend: Vitest per component (fetch-spy); App-level render+restore; E2E seeded via API with `afterEach` cleanup.

### Previous-story / sibling intelligence

- **Story 14.1** — the Jack step-5 surface (`handleJackMessage`/`jackState`/render) this story fills with the report.
- **Story 14.2/14.4** — `TestExecutionResult` + `AgentRun.execution_metadata` (the API's data); browser breakdown + unavailable browsers (the summary's fields).
- **Story 14.5** — `report.md` (markdown preview) + `report.json` (attachment link map) + `report_artifact_id` in the message.
- **Story 13.5/13.6 (Sarah review UX, `done`)** — the agent review-panel + side-by-side + expandable-detail patterns to mirror; and the lesson that the review gate is mandatory and explicit ([architecture.md:271-272](_bmad-output/planning-artifacts/architecture.md:271)).
- **Message timestamps / realtime artifact refresh** ([message-timestamps-feature](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\message-timestamps-feature.md), [epic-10-artifact-ui-gotchas](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\epic-10-artifact-ui-gotchas.md)) — reuse `useArtifactSync` so a finished run surfaces live; watch the history-restore dual-registration rule.

### References

- [Source: _bmad-output/planning-artifacts/epics.md:1548-1566] — Story 14.6 ACs (summary, drilldown, filterable history)
- [Source: _bmad-output/planning-artifacts/architecture.md] — project-scoped + membership (280); FR25-29 reporting/observability (745); secret containment (66, 515); mandatory review (271-272)
- [Source: src/ai_qa/threads/models.py:63-78] — `AgentRun.execution_metadata` (run summary) + `agent_runs` per thread
- [Source: src/ai_qa/api/sessions.py] / [api/projects.py](src/ai_qa/api/projects.py) — membership-gated router pattern to mirror for `executions.py`; register in [app.py](src/ai_qa/api/app.py)
- [Source: src/ai_qa/api/artifacts.py] — membership-gated artifact content endpoint (serves screenshots/logs/traces by id)
- [Source: frontend/src/App.tsx] — Jack step-5 wiring (14.1): `handleJackMessage`/`jackState`/render/thread-reset to extend
- [Source: frontend/src/components/agents/SarahScriptReviewPanel.tsx] / [MaryReviewPanel.tsx](frontend/src/components/agents/MaryReviewPanel.tsx) — review-panel + drilldown templates to mirror
- [Source: frontend/src/components/artifacts/ArtifactPreview.tsx] — image/text/markdown rendering to reuse for attachments
- [Source: frontend/src/types/testcase.ts] / [pipeline.ts:229-236](frontend/src/types/pipeline.ts:229) — TS payload-type + `AGENTS.Jack` patterns
- [Source: tests/api/test_admin_rbac_api.py] — canonical API-test scaffold (auth via `dependency_overrides`)
- [Source: _bmad-output/implementation-artifacts/14-2-...](_bmad-output/implementation-artifacts/14-2-playwright-execution-runner.md) / [14-5-...](_bmad-output/implementation-artifacts/14-5-execution-result-report-generation.md) — the data + report this UX consumes
- [Source: project-context.md] — SQLAlchemy async rules; FastAPI dep testing; Vitest 4; full-stack sync; App-UI-English-only; no new packages

## Saved Questions (for Thuong — defaults applied; confirm or correct)

1. **Read source (Decision #1).** Default = a new `executions` API (list + detail) reading `TestExecutionResult`/`AgentRun` for both single-run and history. Alternative = single-run from `report.json` + a list endpoint only for history. Default = full API. OK?
2. **History placement (Decision #2).** Default = a dedicated `ExecutionHistory` panel (filters: thread/browser/result/date) in the Jack surface. Alternative = fold history into the existing Reports sidebar. Default = dedicated panel. Confirm?
3. **Trace handling (Decision #3).** Default = traces are download-only (external Playwright viewer); screenshots inline; logs text. Acceptable, or embed a trace viewer (heavier)?
4. **Metrics scope.** Confirm 14.6 stays per-project execution review and the cross-project leadership KPI dashboard remains **Epic 19** (not built here). Default = yes.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, bmad-dev-story workflow)

### Debug Log References

- `uv run pytest tests/api/test_executions_api.py --no-cov` → 5 passed
- `uv run pytest --no-cov` (whole suite) → 1693 passed; `uv run mypy src` clean (95); ruff clean
- Frontend: `npm run typecheck` + `npm run lint` clean; `npx vitest run` → 33 files / 333 passed (JackExecutionReport 3, ExecutionHistory 4, ExecutionResultDetail 2)

### Completion Notes List

- **Defaults applied:** Decision #1 new `executions` read API (list + detail) over `TestExecutionResult`/`AgentRun`; Decision #2 three React pieces in `components/agents`; Decision #3 screenshots inline / logs viewable / traces download-only, missing → "(not available)"; Decision #4 step-5 render via `handleJackMessage`; Decision #5 render the pre-scrubbed stack trace as-is; Decision #6 TS types in `execution.ts`. Metrics scope stays per-project (Epic 19 owns cross-project KPIs).
- **AC1** — `JackExecutionReport.tsx`: summary card (counts, success-rate bar, browser list, unavailable browsers, duration) + per-`(test, browser)` results table with row-select. Fed by `execution_summary` (counts + `run_id` + `report_artifact_id`) and the detail API.
- **AC2** — `ExecutionResultDetail.tsx`: linked **script** + **source test case** (artifact-content links), failure classification + message, **safe stack trace** in a `<pre>` (rendered as-is — pre-scrubbed server-side), inline **screenshot** (`<img>` via the content endpoint), **trace** download link, **log** viewer. Every missing attachment/provenance → "(not available)", never a broken image/crash.
- **AC3** — `ExecutionHistory.tsx` + new `GET /api/projects/{id}/executions` (run-time-sorted desc, filters `thread_id`/`browser`/`result`/`date_from`/`date_to`) + `GET /executions/{run_id}` (detail). Row-level filters select which runs appear; the displayed counts stay each run's full totals. `src/ai_qa/api/executions.py` registered in `app.py`; membership-gated via `require_project_member_or_admin` (404 for non-members — tested).
- **Backend correctness** — sync `Session` (matches the existing routers; no `MissingGreenlet`); reads only scalar columns + `execution_metadata` JSON (no relationship lazy-load). Attachment link map loaded best-effort from the run's `report.json` (14.5); degrades to `{}`.
- **Secret containment** — the API returns only scrubbed `error_message`/`stack_trace` + artifact ids; no credential/storageState transits the surface (the data is pre-scrubbed by the 14.2 runner). FastAPI dep testing via `app.dependency_overrides` (never `mock.patch` a dependency).
- **App-UI English-only**; full-stack sync via `execution.ts`; `run_id` added to the `execution_summary` message so the FE can open the detail.
- **No migration** (read-only over 14.2/14.4 tables). **E2E deferral:** a full run→report E2E needs a reachable app + seeded results + installed browsers (integration-only); component behavior is covered by Vitest (fetch-spy) and the API by `test_executions_api.py`.

### File List

- `src/ai_qa/api/executions.py` — executions list/detail read API (A)
- `src/ai_qa/api/app.py` — register `executions_router` (M)
- `src/ai_qa/agents/jack.py` — `run_id` in the `execution_summary` message (M)
- `frontend/src/types/execution.ts` — `ExecutionRunSummary`/`ExecutionResult`/`ExecutionDetail`/`AttachmentLink`/`ExecutionHistoryFilters` (+`run_id`) (M)
- `frontend/src/components/agents/JackExecutionReport.tsx` — summary + results table + drilldown (A)
- `frontend/src/components/agents/ExecutionResultDetail.tsx` — per-test drilldown (A)
- `frontend/src/components/agents/ExecutionHistory.tsx` — filterable history (A)
- `frontend/src/App.tsx` — render report + history on step 5; open historical runs (M)
- `tests/api/test_executions_api.py` — list/detail/filters/membership tests (A)
- `frontend/src/components/__tests__/{JackExecutionReport,ExecutionHistory,ExecutionResultDetail}.test.tsx` — component tests (A)

### Change Log

- 2026-06-21 — Story 14.6 implemented: executions read API (list/detail, sorted + filterable, membership-gated) + Jack step-5 review UX (summary report, per-test drilldown with linked artifacts + attachments, filterable history). No migration. Status → review. **Epic 14 complete (all 6 stories in review).**
