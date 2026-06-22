---
baseline_commit: 0de0b7c
---

# Story 14.5: Execution Result Report Generation

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want Jack to generate a structured execution report from the run results,
so that I can understand test outcomes at a glance, diagnose failures, and reach the linked screenshots/traces/logs and the source script/test-case artifacts.

## Acceptance Criteria

Verbatim from [epics.md#Story-14.5](_bmad-output/planning-artifacts/epics.md) (lines 1527-1546), expanded with implementation defaults (see "Scope decisions"). This story **composes the report content** from the structured data Stories 14.2/14.4 persisted (`TestExecutionResult` rows + `AgentRun.execution_metadata`) and the attachment artifacts Story 14.3 persisted, and saves it as a project-scoped report artifact. The **review UI** is Story 14.6.

### AC1 — The report content

- **Given** execution results exist
- **When** Jack generates the report
- **Then** the report includes: **run summary, per-test result, browser, duration, failure details, skipped/unavailable states, and linked source script/test case artifacts**

### AC2 — Linked attachments; missing ones tolerated

- **Given** screenshots, traces, logs, or attachments are available
- **When** report artifacts are saved
- **Then** they are **linked from the execution report metadata**
- **And** **unavailable attachments are represented as missing** rather than breaking report generation

### AC3 — Project-scoped, membership-gated retrieval

- **Given** the report is saved
- **When** project members retrieve it
- **Then** it is **accessible as a project-scoped artifact according to project membership permissions**

---

## ⚠️ Sequencing dependency (READ FIRST)

This is **Story 5 of Epic 14**, building on **14.2** (results), **14.3** (persisted attachments + the `save_execution_output` helper), and **14.4** (per-browser rows + unavailable browsers). Verify before starting:

1. **`TestExecutionResult` rows** (14.2/14.4) carry per-`(test, browser)` status/duration/error/classification + provenance FKs (`source_script_artifact_id`, `source_test_case_artifact_id`).
2. **`AgentRun.execution_metadata`** (14.2/14.4) carries the run summary (totals, timestamps, duration, `browsers`, `unavailable_browsers`, per-browser counts).
3. **`PipelineArtifactAdapter.save_execution_output` / `persist_run_outputs`** (14.3) persist the report file + attachments and **return the created attachment artifact ids** (the link targets this story stamps into the report). The execution artifact kinds exist in `ARTIFACT_KINDS` (`report` pre-existing; `trace`/`log`/`execution_screenshot` added by Story 14.3).

If the structured results or the 14.3 persistence helper are absent, **flag and stop** — this story only *composes and links*, it does not re-run or re-persist.

> Reconcile every cited `file:line` / snippet against live code; treat them as **leads to verify** ([verify-subagent-claims](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\verify-subagent-claims.md), [create-story-snippet-hazards](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\create-story-snippet-hazards.md)).

---

## ⚠️ CRITICAL: report = a visible `.md` + a hidden `.json` companion (mirror requirement.md/.metadata)

The project already has a precedent for "human-readable artifact + machine-readable companion": Bob saves `{page}/requirement.md` (`kind="requirements"`, visible) **plus** a `requirement.metadata.json` (`kind="configuration"`, hidden from the Reports/Requirements raw view) ([artifact-ui-storage-overhaul](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\artifact-ui-storage-overhaul.md); [project-context.md#Artifacts](project-context.md)). Mirror it for the execution report:

- **`{prefix}/{run_id}/report.md`** — `kind="report"` → browses under **Reports** (visible). The human-readable report (AC1). The Reports folder shows non-`configuration` artifacts, so this surfaces.
- **`{prefix}/{run_id}/report.json`** — `kind="configuration"` → **hidden** from the Reports browse list (the FE filters `kind="configuration"` — [ProjectSidebar.tsx](frontend/src/components/projects/ProjectSidebar.tsx)) but **fetchable by name/id**. This is the structured payload Story 14.6 fetches for the rich drilldown: the run summary, per-`(test, browser)` results, and the **attachment link map** (`{test, browser} → {screenshot_id?, trace_id?, log_id?}`).

This keeps the sidebar clean (one visible report per run) while giving 14.6 a stable machine-readable source — without a new DB migration. (Story 14.6 may alternatively read `TestExecutionResult` rows via an API; the `report.json` covers the attachment link map either way.)

---

## Scope decisions (defaults chosen from code + ACs — confirm or correct via Saved Questions)

- **Decision #1 — composer module + visible `.md` + hidden `.json` (RECOMMENDED).** Add a pure, unit-testable formatter (`src/ai_qa/pipelines/execution_report.py`) that takes `(run_summary, results: list[TestExecutionResult-like], attachment_link_map)` and returns `(markdown: str, structured: dict)`. Jack persists `report.md` (`kind="report"`) and `report.json` (`kind="configuration"`) via the 14.3 adapter helpers. (Saved Q#1 — alternative: `.md` only, with 14.6 reading everything from `TestExecutionResult` via API.)
- **Decision #2 — attachment links live in the `.json` link map (RECOMMENDED), no new DB columns.** The 14.3 persist step returns attachment artifact ids; the composer records `{test, browser} → {screenshot_id, trace_id, log_id}` in `report.json` and renders inline links in `report.md` (e.g. an artifact-content URL or an "Open screenshot" reference by id). Avoids adding nullable id columns to `TestExecutionResult` (Saved Q#2 — alternative: add `screenshot_artifact_id`/`trace_artifact_id`/`log_artifact_id` columns + migration for first-class querying).
- **Decision #3 — missing attachments are first-class, never fatal (AC2).** When a screenshot/trace/log is absent for a result (passed tests have none; an unavailable browser produced nothing; a write failed), the link map stores `null`/omits it and the `.md` renders "(no screenshot)" / "(trace unavailable)". Report generation **never raises** because an attachment is missing — wrap each link in a tolerant lookup. The composer must also handle **empty result sets** (a run where every browser was unavailable) by producing a valid "no results" report, not crashing.
- **Decision #4 — composed in Jack right after persistence (RECOMMENDED).** Extend Jack's `_begin_execution` (14.2/14.3): after results are persisted and attachments saved (ids known), call the composer and persist the report `.md`/`.json` via 14.3's helper, then include the report artifact id in the `execution_summary` message so 14.6 can open it. Mark the seam with `# Story 14.6: render this report in the review UX.`
- **Decision #5 — retrieval reuses the existing artifact read endpoint (AC3).** No new read API — the report is a normal project-scoped `Artifact`; project members fetch it via the existing artifact content endpoint, which already enforces membership ([api/artifacts.py](src/ai_qa/api/artifacts.py) + the project-scoped `ArtifactService.get_artifact`/`read_current_content`). Confirm the membership guard covers the report kinds (it is kind-agnostic, scoped by `project_id`).
- **Decision #6 — report format = Markdown summary + table(s) (RECOMMENDED).** Matches the "Reports/Requirements show `.md`" convention and renders in the existing `ReviewContent`/`ArtifactPreview` markdown path. Sections: a run-summary header (totals, success rate, duration, browsers, unavailable browsers, run metadata), a per-test results table (test, browser, status, duration, failure summary), and a per-failure detail block (classification, scrubbed error/stack, links to script/test-case + screenshot/trace/log). (Saved Q#3 — also emit an HTML report? Default: no — MD only; the playwright HTML report is a separate concern.)
- **Out of scope for 14.5:** the review **UI** (14.6), the runner/execution (14.2), output paths/persistence mechanics (14.3), the browser matrix/auth (14.4). 14.5 reads structured results + saved attachment ids and produces the report document(s) — it does not run anything or open browsers.

## What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status / action |
| --- | --- | --- |
| `TestExecutionResult` rows (per-test+browser status/duration/error/classification + provenance) | `src/ai_qa/db/models.py` (14.2/14.4) | ✅ the report's data source |
| `AgentRun.execution_metadata` run summary (`browsers`, `unavailable_browsers`, counts, timings) | [threads/models.py:63-78](src/ai_qa/threads/models.py:63) | ✅ the summary section's data source |
| `save_execution_output`/`persist_run_outputs` (14.3) returning attachment artifact ids | `src/ai_qa/pipelines/artifact_adapter.py` (14.3) | ✅ persist `report.md`/`report.json`; ids are the link targets |
| `save_metadata` (idempotent JSON `kind="configuration"`) | [artifact_adapter.py:275-306](src/ai_qa/pipelines/artifact_adapter.py:275) | ✅ pattern for the hidden `report.json` companion |
| `ARTIFACT_KINDS` incl. `report` (+ 14.3's `trace`/`log`/`execution_screenshot`) | [service.py:17-31](src/ai_qa/artifacts/service.py:17) | ✅ kinds ready |
| `folder_for_kind` → `report` browses under **Reports**; `configuration` hidden there | [storage.py:41-69](src/ai_qa/artifacts/storage.py:41), [ProjectSidebar.tsx](frontend/src/components/projects/ProjectSidebar.tsx) | ✅ `.md` visible, `.json` hidden |
| Requirement `.md` + `.metadata.json` precedent (visible doc + hidden companion) | [artifact_adapter.py:55-111, 275-306](src/ai_qa/pipelines/artifact_adapter.py:55) | ✅ **mirror** the two-file shape |
| Membership-gated artifact read (`get_artifact`/`read_current_content`, project-scoped) | [service.py:209-244](src/ai_qa/artifacts/service.py:209), [api/artifacts.py](src/ai_qa/api/artifacts.py) | ✅ AC3 satisfied by the existing endpoint |
| Markdown render path (`ReviewContent` / `ArtifactPreview` for `.md`) | [frontend/src/components/.../ArtifactPreview.tsx](frontend/src/components/artifacts/ArtifactPreview.tsx) | ✅ the `.md` renders with no new viewer (rich UI = 14.6) |
| `source_script_artifact_id` / `source_test_case_artifact_id` on results | `TestExecutionResult` (14.2) | ✅ the linked-artifact references for AC1 |

---

## Tasks / Subtasks

- [x] **Task 1 — Report composer (AC1, AC2, AC3-data)** — new `src/ai_qa/pipelines/execution_report.py` (pure/testable)
  - [x] `def compose_execution_report(*, summary: dict, results: list[ExecResultView], attachments: dict, project_id, run_id) -> tuple[str, dict]` returning `(markdown, structured_json)`.
  - [x] **Markdown (AC1):** a summary header (totals, passed/failed/error/skipped, success rate, total duration, browsers, **unavailable browsers with reasons**, run id, started/completed, environment host); a per-test table (`test | browser | status | duration | failure summary`); and per-failure detail blocks (classification, **scrubbed** error message + safe stack trace, links to source script + source test case + screenshot/trace/log). Use real headings (no bold-as-heading — MD036) and spaced table separators (MD060).
  - [x] **Structured JSON:** the same data machine-readably + the **attachment link map** `{f"{test}::{browser}": {"screenshot_id": ..|null, "trace_id": ..|null, "log_id": ..|null}}` + provenance ids — the payload Story 14.6 consumes.
  - [x] **Tolerant (AC2):** every attachment/provenance lookup degrades to `null`/"(unavailable)" — never raise on a missing attachment; handle an empty `results` list (all-unavailable run) gracefully.
  - [x] **No secrets:** the composer only consumes already-scrubbed result fields; do not re-introduce raw error text. Add a leak-canary assertion in tests.

- [x] **Task 2 — Persist the report (AC2, AC3)** — [jack.py](src/ai_qa/agents/jack.py) (extend `_begin_execution`)
  - [x] After results + attachments are persisted (14.2/14.3, ids known), build the attachment link map, call `compose_execution_report(...)`, then persist via 14.3's helper: `report.md` (`kind="report"`) and `report.json` (`kind="configuration"`) under `{prefix}/{run_id}/`.
  - [x] Capture the report artifact id; include it in the `execution_summary` message metadata (`{"type":"execution_summary", ..., "report_artifact_id": ...}`) for 14.6. Add the `# Story 14.6: render this report` marker.
  - [x] Keep persistence ordering safe (mirror the idempotent "save new before delete old" discipline of `save_requirement`/`save_metadata` — [artifact_adapter.py:73-111](src/ai_qa/pipelines/artifact_adapter.py:73)); a per-run report is unique so overwrite shouldn't occur, but be robust.

- [x] **Task 3 — Linked source artifacts (AC1)** — composer + Jack
  - [x] For each result, resolve `source_script_artifact_id` (always) and `source_test_case_artifact_id` ("where available") into renderable links (artifact id → the FE artifact route / content endpoint). If a referenced artifact was deleted, render "(source removed)" — do not raise (tolerant).

- [x] **Task 4 — Retrieval / access check (AC3)**
  - [x] Confirm the existing artifact read endpoint enforces project membership for the new report kinds (it is kind-agnostic, scoped by `project_id`). Add an API test: a member can read the report; a non-member gets 403/404; another project's member cannot read it. No new endpoint expected.

- [x] **Task 5 — Backend tests (AC1, AC2, AC3)**
  - [x] `tests/test_pipelines/test_execution_report.py`: composer renders all AC1 sections from sample data; **missing attachment → "(unavailable)" not an exception** (AC2); empty results → valid "no results" report; unavailable browsers appear with reasons; markdown passes the project's MD rules (headings not bold, spaced table separators); **leak-canary** (a secret-shaped token in input never appears, and inputs are already-scrubbed).
  - [x] `tests/test_agents/test_jack.py` (extend): after a canned run, Jack composes + persists `report.md` (`kind="report"`) and `report.json` (`kind="configuration"`) via the adapter, and the `execution_summary` message carries `report_artifact_id`. Patch the adapter to capture the saved kinds/names/content.
  - [x] `tests/api/` artifact-read membership test for the report (member vs non-member vs other-project).

- [x] **Task 6 — Frontend (AC1, light)**
  - [x] Confirm `report.md` renders via the existing markdown preview when opened from the Reports folder (no new viewer here). Confirm `report.json` (kind=`configuration`) stays hidden in the Reports list. The rich, structured review UI is **Story 14.6**.
  - [x] If `execution_summary.report_artifact_id` should make the report openable from the chat, add only a minimal "Open report" affordance (full UX = 14.6). Keep TS types in sync.

- [x] **Task 7 — Verify (no migration with Decision #2)**
  - [x] `uv run pytest --no-cov` (whole suite). `uv run mypy src` clean. Pyrefly-clean (tolerant `dict.get` → narrow before use; no redundant cast; specific exceptions). `uv run ruff check --fix` + `ruff format`.
  - [x] Frontend: `npm run lint`, `npm run typecheck`, `npm run test`.
  - [x] **No Alembic migration** with Decision #2 (links live in `report.json`). If Saved Q#2 is chosen (id columns), a migration is required — note it. State the decision in Completion Notes.
  - [x] Leak-canary: no secret/credential/storageState value in `report.md` or `report.json`.

## Dev Notes

### Report composition flow

```
TestExecutionResult rows (14.2/14.4) + AgentRun.execution_metadata (summary)
        + attachment artifact ids (14.3 persist return)
        ▼
compose_execution_report(summary, results, attachments) → (markdown, structured_json)
        │  AC1 sections: summary • per-test table • per-failure detail • linked script/test-case/attachments
        │  AC2: missing attachment → "(unavailable)", never raises; empty results → valid report
        ▼
persist (14.3 helper):  {prefix}/{run_id}/report.md   kind="report"          (visible in Reports)
                        {prefix}/{run_id}/report.json kind="configuration"   (hidden; 14.6 fetches)
        ▼
execution_summary message gains report_artifact_id  → Story 14.6 opens it
        ▼
members read via the existing project-scoped, membership-gated artifact endpoint  (AC3)
```

### Why the `.md` + hidden `.json` split

- The `.md` is the deliverable a human reads (and the sidebar shows one clean report per run).
- The `.json` is the stable machine source for the 14.6 drilldown (attachment link map + per-test data), hidden from the browse list exactly like `requirement.metadata.json`.
- This avoids a DB migration (no attachment-id columns) while still giving 14.6 first-class structured access. Choose Saved Q#2 only if cross-run attachment querying (e.g. "all runs with a trace") becomes a real need.

### Architecture compliance (hard rules)

- **Reliable structured reporting** is Jack's named capability ([architecture.md:1169-1173](_bmad-output/planning-artifacts/architecture.md:1169)) and the epic's reporting FRs (FR25-29 — [architecture.md:745](_bmad-output/planning-artifacts/architecture.md:745)). The report must be complete and faithful — never omit failures or fabricate passes.
- **Through the artifact service only** ([architecture.md:518, 533](_bmad-output/planning-artifacts/architecture.md:518)) — persist via the 14.3 adapter helper, not direct writes.
- **Project-scoped + membership-gated** ([architecture.md:280](_bmad-output/planning-artifacts/architecture.md:280)) — AC3 is satisfied by the existing artifact endpoint; just verify and test it.
- **Secret containment** ([architecture.md:66, 515](_bmad-output/planning-artifacts/architecture.md:66)) — the report consumes already-scrubbed fields; never re-introduce raw error/trace text or any credential/storageState into `.md`/`.json`.
- **Markdown rules** ([project-context.md#Code-Quality](project-context.md)): real headings (MD036), spaced table separators (MD060), `-` lists; add `<!-- markdownlint-disable -->` only where the existing artifacts do.

### Library / framework constraints (from project-context.md)

- **Backend:** Python ≥3.14, `uv` only. Ruff + Mypy strict. Pyrefly-clean (tolerant `.get` → narrow; no redundant cast; specific exceptions; no bare except). Sync DB/artifact path.
- **No new packages.** **No migration** (Decision #2).
- **Frontend:** minimal — markdown renders via the existing preview; keep Vitest 4 rules if touched.

### Forward-compat note (not 14.5 scope)

- Story 14.6 reads `report.json` (and/or `TestExecutionResult` via a list/filter API it adds) for the rich UI + history. Keep `report.json`'s schema stable and versioned (`"schema_version": 1`) so 14.6 (and Epic 19 metrics) can evolve it safely.

### Project Structure Notes

- **New files:** `src/ai_qa/pipelines/execution_report.py`, `tests/test_pipelines/test_execution_report.py`.
- **Modified files (expected):** `src/ai_qa/agents/jack.py` (compose + persist + message id), tests `tests/test_agents/test_jack.py`, `tests/api/` (membership read). No model/migration with Decision #2.

### Testing standards summary

- Backend: composer unit tests (sections, tolerant missing-attachment, empty results, MD rules, leak-canary); agent test (composes + persists the two artifacts); API membership read test. Whole-suite `--no-cov`; mypy `src` only.
- Frontend: confirm `.md` renders + `.json` hidden; rich UI is 14.6.

### Previous-story / sibling intelligence

- **Story 14.2/14.4** — produce the structured results the report reads.
- **Story 14.3** — persists the report + attachments and returns attachment ids (the link targets). 14.5 composes; 14.3 persists the bytes.
- **Story 11.7 (Requirements Artifact Save, `done`) + Bob's `requirement.md` + `requirement.metadata.json`** — the visible-doc + hidden-companion precedent ([artifact-ui-storage-overhaul](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\artifact-ui-storage-overhaul.md)).
- **Story 14.6** — the consumer (rich review UX + history). Keep `report.json` schema stable.
- **Mary MD test cases** ([mary-md-testcases-reports-cleanup](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\mary-md-testcases-reports-cleanup.md)) — the project's "save as Markdown, hide configuration in Reports" direction; the report follows it.

### References

- [Source: _bmad-output/planning-artifacts/epics.md:1527-1546] — Story 14.5 ACs (report content, linked/missing attachments, membership-gated retrieval)
- [Source: _bmad-output/planning-artifacts/architecture.md] — Jack reliable structured reporting (1169-1173); FR25-29 reporting (745); through-the-service (518, 533); project-scoped (280); secret containment (66, 515)
- [Source: src/ai_qa/pipelines/artifact_adapter.py:55-111, 275-306] — `save_requirement`/`save_metadata` idempotent visible-doc + hidden-`.json` pattern to mirror
- [Source: src/ai_qa/artifacts/service.py:17-31, 209-244] — `ARTIFACT_KINDS` (incl. `report`) + membership-gated `get_artifact`/`read_current_content`
- [Source: src/ai_qa/artifacts/storage.py:41-69] — `folder_for_kind` (report→Reports, configuration hidden there)
- [Source: frontend/src/components/projects/ProjectSidebar.tsx] — Reports list hides `kind="configuration"` (so the `.json` companion stays hidden, the `.md` shows)
- [Source: src/ai_qa/threads/models.py:63-78] — `AgentRun.execution_metadata` run summary source
- [Source: _bmad-output/implementation-artifacts/14-2-playwright-execution-runner.md] / [14-3-...](_bmad-output/implementation-artifacts/14-3-configurable-execution-output-path.md) / [14-4-...](_bmad-output/implementation-artifacts/14-4-multi-browser-execution-support.md) — the upstream results/persistence/matrix this story composes
- [Source: project-context.md] — Markdown rules (MD036/MD060); two-classifier artifacts; `uv`/`npm` only; Ruff + Mypy strict; Pyrefly; secret containment; no new packages

## Saved Questions (for Thuong — defaults applied; confirm or correct)

1. **Report shape (Decision #1/#2).** Default = visible `report.md` (`kind="report"`) + hidden `report.json` (`kind="configuration"`, holds the attachment link map + per-test data); no DB migration. Alternative = `.md` only with 14.6 reading everything from `TestExecutionResult` via API. Default = `.md` + `.json`. OK?
2. **Attachment linking (Decision #2).** Default = link map in `report.json` (no schema change). Alternative = add `screenshot_artifact_id`/`trace_artifact_id`/`log_artifact_id` columns to `TestExecutionResult` (+migration) for first-class querying. Default = JSON map. Confirm?
3. **HTML report (Decision #6).** Default = Markdown only (renders in the existing preview). Also emit a Playwright HTML report artifact? Default = no. Acceptable?

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, bmad-dev-story workflow)

### Debug Log References

- `uv run pytest tests/pipelines/test_execution_report.py tests/test_agents/test_jack.py tests/api/test_artifact_api.py::test_execution_report_artifacts_are_membership_gated --no-cov` → all pass
- `uv run pytest --no-cov` (whole suite) → 1688 passed; `uv run mypy src` clean (94); ruff clean
- No migration (Decision #2 — links in report.json)

### Completion Notes List

- **Defaults applied:** Decision #1 composer module + visible `report.md` (`kind="report"`) + hidden `report.json` (`kind="configuration"`); Decision #2 attachment link map in `report.json` (no DB columns / no migration); Decision #3 missing attachments first-class/never fatal; Decision #4 composed in Jack right after persistence; Decision #5 retrieval via the existing membership-gated artifact endpoint; Decision #6 Markdown summary + tables (no HTML report).
- **AC1** — `compose_execution_report` (pure, `src/ai_qa/pipelines/execution_report.py`) renders run summary (totals, success rate, duration, browsers, **unavailable browsers**, run metadata), a per-`(test, browser)` results table, and per-failure detail blocks (classification, scrubbed error/stack, links to script + source test case + screenshot/trace/log). Real headings (MD036), spaced table separators (MD060).
- **AC2** — every attachment/provenance lookup degrades to `(no …)` / `null`; empty result set → valid "No results" report; never raises. `report.json` carries `schema_version: 1` + the `{test::browser}` link map for the 14.6 drilldown.
- **AC3** — the report is a normal project-scoped artifact served by the existing kind-agnostic, membership-gated content endpoint (no new read API). Added `test_execution_report_artifacts_are_membership_gated` (member reads report.md + report.json; non-member → 404); the existing `test_artifact_api_enforces_project_membership_and_allows_admin` already exercises `kind="report"`.
- **Jack wiring** — `_persist_outputs` now returns `(name, kind, artifact_id)` records; `_persist_report` builds the best-effort `{test::browser}` attachment link map (matching produced-file names by test+browser; run.log as the run-level log), composes the report, and persists `report.md` + `report.json` via `save_execution_output` (no overwrite-guard conflict — the attachments batch ran the guard first). The `execution_summary` message now carries `report_artifact_id` (the entry point for 14.6).
- **Secret containment** — the composer consumes only already-scrubbed `error_message`/`stack_trace` (scrubbed by the 14.2 runner); no credential/storageState reaches `report.md`/`report.json`.
- **No migration.** **Frontend** unchanged for 14.5 (the `.md` renders via the existing artifact preview; `report_artifact_id` is already in `execution.ts`). The rich structured report UI is Story 14.6.

### File List

- `src/ai_qa/pipelines/execution_report.py` — report composer (`.md` + structured `.json`) (A)
- `src/ai_qa/agents/jack.py` — `_persist_report` + `_build_report_inputs` + records-returning `_persist_outputs` + `report_artifact_id` in summary (M)
- `tests/pipelines/test_execution_report.py` — composer tests (A)
- `tests/test_agents/test_jack.py` — report compose/persist + report_artifact_id test (M)
- `tests/api/test_artifact_api.py` — report membership AC3 test (M)

### Change Log

- 2026-06-21 — Story 14.5 implemented: execution report composer (visible `report.md` + hidden `report.json` link map), Jack composes + persists after a run and links it via `report_artifact_id`, membership-gated retrieval (existing endpoint). No migration. Status → review.
