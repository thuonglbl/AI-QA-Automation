---
baseline_commit: 0de0b7c
---

# Story 14.3: Configurable Execution Output Path

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a system administrator,
I want execution reports and run artifacts (logs, screenshots, traces, result files) saved to configured, project-scoped artifact locations through the artifact service,
so that execution outputs are organized consistently, never collide across runs, and never rely on ad-hoc workspace filesystem writes.

## Acceptance Criteria

Verbatim from [epics.md#Story-14.3](_bmad-output/planning-artifacts/epics.md) (lines 1484-1503), expanded with implementation defaults (see "Scope decisions"). This story **formalizes the output persistence** that Story 14.2's runner produces: 14.2 runs the scripts in a transient temp dir and returns the files it produced; 14.3 routes those outputs through the `ArtifactService` to a **configurable, unique, project-scoped logical path** with **fail-fast config validation**.

### AC1 — All execution outputs go through the artifact service at configured logical paths

- **Given** Jack produces execution outputs
- **When** logs, reports, screenshots, traces, or result files are saved
- **Then** they are written **through the artifact service** using **configured project-scoped logical paths** (artifact `kind` + a configurable logical name prefix; storage keys derive from `build_artifact_key` under `projects/{project_id}/...`)
- **And** **direct, arbitrary filesystem writes are not required** for application-managed outputs (the runner's temp dir is transient scratch that is read once and persisted; nothing app-managed is left on an ad-hoc workspace path)

### AC2 — Fail-fast on missing/invalid output configuration

- **Given** output-path configuration is missing or invalid
- **When** Jack starts execution (and at app startup)
- **Then** startup/runtime validation reports a **clear configuration error before output is lost** (fail-fast — do not run the scripts, do not silently fall back to an ad-hoc path)

### AC3 — Unique per-run logical path; no silent overwrite

- **Given** multiple execution runs exist
- **When** outputs are saved
- **Then** each run uses a **unique logical run path** (keyed by the execution run id / `agent_run_id`)
- **And** it **does not overwrite prior reports** unless overwrite is **explicitly configured**

---

## ⚠️ Sequencing dependency (READ FIRST)

This is **Story 3 of Epic 14**, building on **14.1** (Jack gate) and **14.2** (the runner). Verify before starting:

1. **`src/ai_qa/pipelines/script_runner.py` exists** (Story 14.2) and the runner **returns the output files it produced** (report XML/HTML, per-test screenshots, traces, logs) as part of its `RunResult` — that return value is the forward-compat seam 14.2 reserved for this story. If the runner does not yet surface produced files, extend it minimally to do so (or coordinate with 14.2).
2. **`TestExecutionResult` + `AgentRun.execution_metadata`** persist *structured* results (14.2). 14.3 persists the *files* (reports/attachments) — distinct concern; do not duplicate.
3. **The Jack `agent_run` is the execution run id** (no separate run table). The unique run path uses `agent_run_id`.

If 14.2's runner is absent, **flag and stop** — there is nothing to route.

> Reconcile every cited `file:line` / snippet against live code and treat them as **leads to verify**, not gospel — record divergences in Completion Notes ([verify-subagent-claims](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\verify-subagent-claims.md), [create-story-snippet-hazards](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\create-story-snippet-hazards.md)).

---

## ⚠️ CRITICAL: storage key vs browse folder — two classifiers, on purpose

The artifact layer has **two intentionally-distinct classifiers** ([project-context.md#Artifacts](project-context.md)) — do not fold them together:

- **`build_artifact_key`** ([storage.py:12-38](src/ai_qa/artifacts/storage.py:12)) — the **storage** key. `kind="report"` (and any unrecognized kind) falls into the catch-all `projects/{id}/artifacts/{artifact_id}/v{n}/{name}`. There is **no `reports/` storage prefix** — the storage catch-all is `artifacts/`.
- **`folder_for_kind`** ([storage.py:41-69](src/ai_qa/artifacts/storage.py:41)) — the **browse** folder shown in the sidebar. `kind="report"` (and any unrecognized kind) → `"reports"`. `kind="screenshot"`/`"image"` → `"requirements"` (NOT reports — beware: execution screenshots must NOT reuse `kind="screenshot"` or they land in the Requirements tree).
- **`ARTIFACT_KINDS`** ([service.py:17-31](src/ai_qa/artifacts/service.py:17)) — a `frozenset` that **validates** `kind`. `"report"` is already a member; any NEW kind (trace/log/execution-screenshot) must be added here or `save_artifact` raises.

So "configurable output path" in this codebase = a configurable **logical name prefix** (folded into the artifact `name`, e.g. `{prefix}/{run_id}/report.md`) — the physical S3/SeaweedFS key is derived by `build_artifact_key` from `kind` and is not a free-form path. Frame the config accordingly (Decision #1). The frontend Reports folder currently **hides `kind="configuration"`** ([ProjectSidebar.tsx](frontend/src/components/projects/ProjectSidebar.tsx)) — make sure execution outputs use kinds that surface (not `configuration`).

---

## Scope decisions (defaults chosen from code + ACs — confirm or correct via Saved Questions)

- **Decision #1 — config = a logical prefix + capture toggles + overwrite flag (RECOMMENDED).** Add to `AppSettings` ([config.py](src/ai_qa/config.py), near the SeaweedFS block ~224-239):
  - `execution_output_prefix: str = "runs"` — the logical name prefix; outputs are named `{execution_output_prefix}/{run_id}/{file}`.
  - `execution_capture_screenshots: bool = True`, `execution_capture_traces: bool = True`, `execution_capture_logs: bool = True` — what to persist.
  - `execution_overwrite_reports: bool = False` — AC3 explicit-overwrite switch.
  These are **non-secret** config. The physical storage stays in SeaweedFS via the existing `build_artifact_key` mapping; the prefix only governs the logical/browse name. (Saved Q#1 — alternative: a fully free-form storage path, which would require teaching `build_artifact_key` an execution branch.)
- **Decision #2 — new artifact kinds for attachments (RECOMMENDED).** Add `"trace"` and `"log"` to `ARTIFACT_KINDS`; for screenshots add `"execution_screenshot"` (NOT the existing `"screenshot"`, which browses under Requirements). Teach `folder_for_kind` to route `trace`/`log`/`execution_screenshot` → `"reports"` (the catch-all already returns `"reports"` for unknown kinds, but make it explicit and keep `build_artifact_key` catch-all `artifacts/`). The human-readable report stays `kind="report"` (Story 14.5 composes its content). (Saved Q#2 — alternative: stuff all attachments under `kind="report"` with name suffixes.)
- **Decision #3 — validation = pydantic field validators (startup) + a runtime guard (AC2).** `field_validator` on `execution_output_prefix` rejects empty, absolute paths, drive letters, and `..` traversal (fail-fast at app startup, like the existing encryption-key fail-fast — [architecture.md:323](_bmad-output/planning-artifacts/architecture.md:323)). Plus a runtime check inside the persistence helper: before writing, validate the resolved prefix/run-id and raise a clear `ConfigurationError`-style message that Jack surfaces as a UX-DR12 error **before** the scripts run (or before outputs are persisted). Never silently fall back to a workspace path.
- **Decision #4 — persistence helper on the adapter (RECOMMENDED).** Add `PipelineArtifactAdapter.save_execution_output(...)` (and/or a small `persist_run_outputs(run_id, files)` helper) mirroring the existing idempotent-by-name `save_*` methods ([artifact_adapter.py:319-349](src/ai_qa/pipelines/artifact_adapter.py:319) `save_raw_html`/`save_image` are the closest — text + binary). It builds the `{prefix}/{run_id}/{name}` logical name, picks the kind (report/trace/log/execution_screenshot), and calls `service.save_artifact(...)`. Binary blobs (screenshots/traces/zips) use the `content: bytes` path already supported by `save_artifact` ([service.py:76-146](src/ai_qa/artifacts/service.py:76)) — same mechanism as `save_image` ([artifact_adapter.py:337-349](src/ai_qa/pipelines/artifact_adapter.py:337)).
- **Decision #5 — uniqueness via `agent_run_id` + overwrite guard (AC3).** The logical run folder is `{prefix}/{run_id}/...` where `run_id = agent_run_id` (globally unique per Jack run), so two runs never collide. Before persisting, if artifacts already exist under that run's logical prefix AND `execution_overwrite_reports is False` → raise/skip (should not happen with a fresh run id; the guard protects against re-runs that reuse an id). Do **not** delete prior runs' reports.
- **Out of scope for 14.3:** the runner engine itself (14.2), the multi-browser matrix (14.4 — but persisted paths should already be browser-aware: include `browser` in the attachment name so 14.4 needs no path change), the report *content/composition* (14.5 — 14.3 persists files; 14.5 decides what the report `.md` contains and links the attachment ids), the review UX (14.6).

## What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status / action |
| --- | --- | --- |
| `ArtifactService.save_artifact(*, kind, name, content: str\|bytes, ...)` (text + binary, project-scoped, versioned) | [service.py:76-146](src/ai_qa/artifacts/service.py:76) | ✅ the single write path — outputs flow through here |
| `ARTIFACT_KINDS` validation set (incl. `"report"`) | [service.py:17-31](src/ai_qa/artifacts/service.py:17) | ⚠️ **add** `trace`/`log`/`execution_screenshot` |
| `build_artifact_key` (storage key; catch-all `artifacts/`) | [storage.py:12-38](src/ai_qa/artifacts/storage.py:12) | ✅ no change needed (catch-all already covers report/trace/log) |
| `folder_for_kind` (browse folder; catch-all `reports`) | [storage.py:41-69](src/ai_qa/artifacts/storage.py:41) | ⚠️ **route** trace/log/execution_screenshot → `reports` (explicit) |
| `save_image(name, bytes)` / `save_raw_html(name, text)` (binary + text adapter writes) | [artifact_adapter.py:319-349](src/ai_qa/pipelines/artifact_adapter.py:319) | ✅ **mirror** for `save_execution_output` |
| `_save_text` + `_schedule_change_event` (adapter write + realtime broadcast) | [artifact_adapter.py:351-392](src/ai_qa/pipelines/artifact_adapter.py:351) | ✅ reuse so the Reports folder refreshes live |
| `AppSettings` pydantic-settings (env-driven config + field validators + startup fail-fast) | [config.py](src/ai_qa/config.py) (SeaweedFS block ~224-239) | ✅ **add** the execution-output fields + validators |
| `S3ArtifactStorage` / `LocalArtifactStorage` (both accept `str\|bytes`) | [storage.py](src/ai_qa/artifacts/storage.py) | ✅ no change — binary already supported |
| Reports browse folder filter (hides `kind="configuration"`) | [ProjectSidebar.tsx](frontend/src/components/projects/ProjectSidebar.tsx) | ✅ ensure execution kinds are NOT `configuration` so they surface |
| `agent_run_id` (unique per Jack run) | [threads/models.py:63-78](src/ai_qa/threads/models.py:63) | ✅ the unique run-path key |

---

## Tasks / Subtasks

- [x] **Task 1 — Config fields + fail-fast validation (AC2)** — [config.py](src/ai_qa/config.py)
  - [x] Add `execution_output_prefix` (default `"runs"`), `execution_capture_screenshots`/`execution_capture_traces`/`execution_capture_logs` (default `True`), `execution_overwrite_reports` (default `False`) to `AppSettings`, near the SeaweedFS block, with `Field(..., description=...)`.
  - [x] Add a `field_validator("execution_output_prefix")` that rejects empty/whitespace, absolute paths, drive-letter/UNC prefixes, and any `..` segment — raise a clear `ValueError` (pydantic surfaces it at startup → fail-fast). Keep it cross-platform (POSIX + Windows).
  - [x] Confirm the app surfaces config errors at startup (the encryption-key fail-fast is the precedent — [architecture.md:323](_bmad-output/planning-artifacts/architecture.md:323)).

- [x] **Task 2 — Artifact kinds + browse routing (AC1)** — [service.py](src/ai_qa/artifacts/service.py) + [storage.py](src/ai_qa/artifacts/storage.py)
  - [x] Add `"trace"`, `"log"`, `"execution_screenshot"` to `ARTIFACT_KINDS` ([service.py:17-31](src/ai_qa/artifacts/service.py:17)).
  - [x] In `folder_for_kind` ([storage.py:41-69](src/ai_qa/artifacts/storage.py:41)) route the three new kinds (and confirm `"report"`) → `"reports"` explicitly. Leave `build_artifact_key` on its `artifacts/` catch-all (do not add a `reports/` storage branch — the two classifiers diverge by design).
  - [x] Confirm `kind="report"` and the new kinds are NOT `"configuration"`, so the FE Reports filter does not hide them.

- [x] **Task 3 — Adapter persistence helper (AC1, AC3 — incl. uniqueness)** — [artifact_adapter.py](src/ai_qa/pipelines/artifact_adapter.py)
  - [x] Add `save_execution_output(self, *, run_id: UUID, file_name: str, content: str | bytes, kind: str) -> Artifact`: builds the logical name `f"{settings.execution_output_prefix}/{run_id}/{file_name}"`, validates the resolved prefix (Decision #3 runtime guard), and calls `self.service.save_artifact(... kind=kind, name=<logical>, content=content, agent_run_id=run_id, thread_id=..., owner_user_id=...)` then `_schedule_change_event`. Use the binary path for screenshots/traces (`bytes`) and text for report/log.
  - [x] Optional convenience `persist_run_outputs(self, *, run_id, report_md, attachments: list[(name, bytes|str, kind)]) -> list[UUID]` that loops `save_execution_output` and returns the created artifact ids (these ids feed Story 14.5's report links).
  - [x] **Uniqueness/overwrite guard:** before writing, if any artifact already exists under `f"{prefix}/{run_id}/"` and `not settings.execution_overwrite_reports` → raise a clear error (AC3). A fresh run id makes this a no-op; the guard protects re-runs.

- [x] **Task 4 — Wire into Jack's post-run persistence (AC1)** — [jack.py](src/ai_qa/agents/jack.py)
  - [x] In `_begin_execution` (14.2), after the runner returns, read the produced files from the runner's `RunResult` and persist each via `save_execution_output`/`persist_run_outputs`, honoring the capture toggles (skip screenshots if `execution_capture_screenshots is False`, etc.). Name attachments browser-aware (`{test}__{browser}.png`) so 14.4 needs no path change.
  - [x] **AC2 runtime guard:** if the output config is invalid, surface a UX-DR12 *What happened / Why / What to do* error and do NOT leave outputs on disk — fail before/at persistence, not after partial writes.
  - [x] Do NOT write any app-managed output to a workspace/filesystem path directly — everything app-managed goes through `save_execution_output`. (The runner's temp dir is transient scratch only.)

- [x] **Task 5 — Backend tests (AC1, AC2, AC3)**
  - [x] `tests/test_config.py`: the validator rejects empty/absolute/`..`/drive-letter prefixes and accepts a clean relative prefix (fail-fast).
  - [x] `tests/pipelines/test_pipeline_artifact_adapter.py`: `save_execution_output` writes under `{prefix}/{run_id}/{name}` with the right kind; binary (bytes) screenshots round-trip via `read_current_content`; two different run ids never collide; same run id + `overwrite=False` raises (and `overwrite=True` allows). Real `ArtifactService` over in-memory SQLite (copy an existing scaffold).
  - [x] `tests/test_agents/test_jack.py`: with a canned `RunResult` carrying files, assert Jack persists the report + attachments through the adapter (patch/inspect the adapter), respects capture toggles, and blocks on invalid config without persisting.
  - [x] `tests/artifacts/` (storage/service): `folder_for_kind` routes the new kinds → `reports`; `ARTIFACT_KINDS` accepts them.

- [x] **Task 6 — Frontend (AC1, light)**
  - [x] Confirm the persisted execution outputs appear under the **Reports** folder in `ProjectSidebar` and are NOT filtered out (they are not `kind="configuration"`). No new UI here — the rich report view is Story 14.6. Add a Vitest assertion only if the Reports filter logic changes.

- [x] **Task 7 — Verify (no schema migration — config + kinds only)**
  - [x] `uv run pytest --no-cov` (whole suite). `uv run mypy src` clean. Pyrefly-clean (narrow Optionals; bytes vs str handled; no redundant cast).
  - [x] `uv run ruff check --fix src/ tests/` then `uv run ruff format src/ tests/`.
  - [x] Frontend: `npm run lint`, `npm run typecheck`, `npm run test`.
  - [x] **No Alembic migration** — this story adds config + artifact kinds, no DB columns. State explicitly in Completion Notes. New env vars (`EXECUTION_OUTPUT_PREFIX`, etc.) should be documented in the example env / settings docs.

## Dev Notes

### Where outputs live (the full picture)

```
runner (14.2) executes in a temp dir → produces: results.xml, *.png (failures), trace.zip, run.log
        │  (RunResult returns these file paths/bytes)
        ▼
Jack._begin_execution (14.3) persists each through the artifact service:
        save_execution_output(run_id, "report.md",            text,  kind="report")     (content from 14.5)
        save_execution_output(run_id, "test__chromium.png",   bytes, kind="execution_screenshot")
        save_execution_output(run_id, "test__chromium.zip",   bytes, kind="trace")
        save_execution_output(run_id, "run.log",              text,  kind="log")
        │   logical name = f"{execution_output_prefix}/{run_id}/<file>"
        ▼
ArtifactService.save_artifact → build_artifact_key → projects/{project_id}/artifacts/{artifact_id}/v1/<safe_name>  (SeaweedFS)
        │   folder_for_kind → browse folder "reports"
        ▼
temp dir is deleted — nothing app-managed left on an ad-hoc workspace path  (AC1)
```

### Config / validation (AC2)

- Startup fail-fast: a malformed `execution_output_prefix` (absolute, `..`, empty) fails pydantic validation at `AppSettings()` construction — the app refuses to start with a clear message, exactly like the user-secrets encryption key.
- Runtime guard: even with a valid prefix, the persistence helper re-checks before the first write and raises a clear configuration error that Jack converts to a UX-DR12 message **before** outputs are lost. "Before output is lost" = validate before/at the first persist, never after a partial write.

### Uniqueness & no-overwrite (AC3)

- `agent_run_id` is unique per Jack run → `{prefix}/{run_id}/...` is unique by construction; prior runs' reports are never touched.
- `execution_overwrite_reports` (default `False`) is the only switch that permits re-writing an existing run's outputs; document that re-running normally creates a NEW run id (so overwrite rarely matters).

### Architecture compliance (hard rules)

- **No direct/ad-hoc filesystem writes for app-managed outputs — everything via the artifact service** ([architecture.md:518, 533](_bmad-output/planning-artifacts/architecture.md:518)). This is the core of AC1. The runner's temp dir is transient scratch (read once, then deleted) — not a persisted app output.
- **Fail fast on missing/invalid config** ([architecture.md:323](_bmad-output/planning-artifacts/architecture.md:323)).
- **Project-scoped artifacts** under `projects/{project_id}/...` ([architecture.md:280](_bmad-output/planning-artifacts/architecture.md:280)) — `save_artifact` already enforces this.
- **Secret containment** ([architecture.md:66, 515](_bmad-output/planning-artifacts/architecture.md:66)): logs/traces can contain request data — scrub before persisting (the runner already scrubs error text in 14.2; apply the same to any `run.log`/trace text you persist, and never persist a `storage_state`/cookie blob).
- **Two classifiers stay separate** ([project-context.md#Artifacts](project-context.md)): never wire `folder_for_kind` into `build_artifact_key`.

### Library / framework constraints (from project-context.md)

- **Backend:** Python ≥3.14, `uv` only. Ruff + Mypy strict. Pyrefly-clean (handle `str | bytes` unions explicitly; narrow `Optional`; no redundant cast; specific exceptions). `Path`/string prefix handling must be cross-platform (Windows + POSIX) — prefer `posixpath`-style joins for the logical name (storage keys use `/`).
- **No new packages. No Alembic migration** (config fields + artifact-kind strings only).
- **Frontend:** no functional change expected; if the Reports filter is touched, keep Vitest 4 rules.

### Forward-compat seams (not 14.3 scope)

- Name attachments **browser-aware** now (`{test}__{browser}.png`) so Story 14.4 (multi-browser) reuses the same paths with no change.
- The created artifact ids returned by `persist_run_outputs` are the **link targets** Story 14.5 stamps into the report metadata and Story 14.6 renders.

### Project Structure Notes

- **Modified files (expected):** `src/ai_qa/config.py` (+fields/+validator), `src/ai_qa/artifacts/service.py` (+kinds), `src/ai_qa/artifacts/storage.py` (`folder_for_kind` routing), `src/ai_qa/pipelines/artifact_adapter.py` (+`save_execution_output`/`persist_run_outputs`), `src/ai_qa/agents/jack.py` (persist after run). Tests: `tests/test_config.py`, `tests/pipelines/test_pipeline_artifact_adapter.py`, `tests/test_agents/test_jack.py`, artifact storage/service tests.
- **No new runtime modules, no migration.**

### Testing standards summary

- Backend: real `ArtifactService` over in-memory SQLite for the adapter helper; config validator unit tests; agent test with a canned `RunResult`. Whole-suite `--no-cov`; mypy `src` only.
- Frontend: assert Reports surfaces execution outputs only if the filter changes.

### Previous-story / sibling intelligence

- **Story 14.2** — produces the output files in a temp dir and returns them; 14.3 persists them. Coordinate the `RunResult` shape (it must carry produced files).
- **Story 10.x (Artifacts, `done`)** — established the storage/browse classifier split, the `ArtifactService` write/version path, and the realtime change-event broadcast — all reused here ([epic-10-artifact-ui-gotchas](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\epic-10-artifact-ui-gotchas.md)).
- **Story 14.5** — composes the report `.md` content and links the attachment ids 14.3 returns. 14.3 persists; 14.5 decides report contents.

### References

- [Source: _bmad-output/planning-artifacts/epics.md:1484-1503] — Story 14.3 ACs
- [Source: _bmad-output/planning-artifacts/architecture.md] — no-direct-storage (518, 533); fail-fast config (323); project-scoped artifacts (280); secret containment (66, 515)
- [Source: src/ai_qa/artifacts/storage.py:12-69] — `build_artifact_key` (storage key, `artifacts/` catch-all) + `folder_for_kind` (browse, `reports` catch-all) — the two-classifier rule
- [Source: src/ai_qa/artifacts/service.py:17-31, 76-146] — `ARTIFACT_KINDS` (incl. `report`) + `save_artifact` (str|bytes, project-scoped, versioned)
- [Source: src/ai_qa/pipelines/artifact_adapter.py:319-392] — `save_raw_html`/`save_image`/`_save_text`/`_schedule_change_event` (the write+broadcast pattern to mirror)
- [Source: src/ai_qa/config.py] — `AppSettings` pydantic-settings + SeaweedFS block (~224-239) — where to add execution-output fields + validators
- [Source: src/ai_qa/threads/models.py:63-78] — `agent_run_id` (unique run-path key)
- [Source: frontend/src/components/projects/ProjectSidebar.tsx] — Reports folder hides `kind="configuration"` — keep execution kinds out of `configuration`
- [Source: project-context.md] — two-classifier rule; `uv`/`npm` only; Ruff + Mypy strict; Pyrefly; secret containment; no new packages

## Saved Questions (for Thuong — defaults applied; confirm or correct)

1. **Config shape (Decision #1).** Default = a logical name prefix (`execution_output_prefix`, default `"runs"`) + capture toggles + overwrite flag; physical S3 path stays derived by `build_artifact_key`. Alternative = a fully free-form storage path (teach `build_artifact_key` an execution branch). Default = logical prefix. OK?
2. **Attachment kinds (Decision #2).** Default = add `trace`/`log`/`execution_screenshot` kinds routed to the Reports browse folder. Alternative = one `report` kind with name suffixes. Default = distinct kinds. Confirm?
3. **Overwrite default (Decision #5).** Default = `execution_overwrite_reports=False` (never overwrite prior runs; re-runs get a new run id). Acceptable?
4. **Capture defaults (Decision #1).** Default = screenshots/traces/logs all captured `True`. Acceptable, or default traces off (size)?

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, bmad-dev-story workflow)

### Debug Log References

- `uv run pytest tests/unit/test_config.py tests/unit/test_artifact_service.py tests/pipelines/test_pipeline_artifact_adapter.py tests/pipelines/test_script_runner.py tests/test_agents/test_jack.py --no-cov` → 97 passed
- `uv run pytest --no-cov` (whole suite) → 1660 passed
- `uv run mypy src` clean (93 files); ruff clean
- No migration (config + artifact-kind strings only)

### Completion Notes List

- **Defaults applied:** Decision #1 config = logical prefix (`execution_output_prefix="runs"`) + capture toggles + overwrite flag (physical S3 key still from `build_artifact_key`); Decision #2 new kinds `trace`/`log`/`execution_screenshot` routed to the Reports browse folder; Decision #3 startup `field_validator` + runtime guard; Decision #5 uniqueness by `agent_run_id`, no-overwrite default.
- **AC1** — all execution outputs persist through `ArtifactService` via the new `PipelineArtifactAdapter.save_execution_output`/`persist_run_outputs`; logical name `{prefix}/{run_id}/{file}`; storage key derived by `build_artifact_key` (catch-all `artifacts/`). The runner's temp dir is transient scratch (read once, deleted). Jack persists in `_persist_outputs`.
- **AC2** — `validate_execution_output_prefix` (shared by the `AppSettings` field validator = startup fail-fast, and the adapter runtime guard) rejects empty/absolute/drive-letter/UNC/`..`. A misconfig raises in the adapter → Jack surfaces a UX-DR12 warning (non-fatal; results already persisted; produced files still in memory, not lost on disk).
- **AC3** — `{prefix}/{run_id}/…` is unique per run (run_id is unique); `persist_run_outputs` guards once-per-batch: existing outputs under the run prefix + `overwrite=False` → raise; `overwrite=True` allows. Prior runs are never touched.
- **Runner extension (the 14.2→14.3 seam):** `run_scripts` now passes `--output/--screenshot only-on-failure/--tracing retain-on-failure` (gated by capture flags) and `_collect_output_files` collects `.png`→`execution_screenshot`, `.zip`→`trace`, plus the always-present `run.log`→`log`, browser-aware-named (`{stem}__{browser}.ext`) so Story 14.4 reuses the paths unchanged.
- **Two-classifier rule honored:** `folder_for_kind` routes the new kinds → `reports` (explicit); `build_artifact_key` keeps its `artifacts/` catch-all (not folded together). Execution kinds are NOT `configuration`, so they surface in the Reports sidebar (14.5's `report.json` companion stays `configuration` = hidden).
- **Secret containment:** runner already scrubs `run.log`/error text (14.2); no `storage_state`/cookie blob is ever persisted.
- **No migration** — config fields + artifact-kind strings only. New env vars: `EXECUTION_OUTPUT_PREFIX`, `EXECUTION_CAPTURE_SCREENSHOTS/TRACES/LOGS`, `EXECUTION_OVERWRITE_REPORTS`.
- **Windows test note:** the nested `runs/{run_id}/` logical path + per-artifact UUID + temp suffix can exceed Windows 260-char MAX_PATH inside pytest's deep tmp dir, so the two adapter tests use a short `tempfile.mkdtemp` storage root. Production uses S3/SeaweedFS (no limit); the existing `test_build_artifact_key_covers_every_kind` table was extended with the new kinds (→ `artifacts/`).
- **Frontend:** no code change — Reports surfaces the new kinds automatically (not `configuration`); rich report UI is 14.6.

### File List

- `src/ai_qa/config.py` — execution-output fields + `validate_execution_output_prefix` + field validator (M)
- `src/ai_qa/artifacts/service.py` — add `trace`/`log`/`execution_screenshot` to `ARTIFACT_KINDS` (M)
- `src/ai_qa/artifacts/storage.py` — `folder_for_kind` routes new kinds → reports (M)
- `src/ai_qa/pipelines/artifact_adapter.py` — `save_execution_output` + `persist_run_outputs` + uniqueness guard (M)
- `src/ai_qa/pipelines/script_runner.py` — capture flags + `_collect_output_files` (M)
- `src/ai_qa/agents/jack.py` — `_persist_outputs` (capture toggles + AC2 guard) (M)
- `tests/unit/test_config.py` — prefix validator tests (M)
- `tests/unit/test_artifact_service.py` — new kinds + folder routing tests (M)
- `tests/pipelines/test_pipeline_artifact_adapter.py` — `save_execution_output`/`persist_run_outputs` tests (M)
- `tests/pipelines/test_script_runner.py` — output-collection test (M)
- `tests/test_agents/test_jack.py` — output-persistence test (M)

### Change Log

- 2026-06-21 — Story 14.3 implemented: configurable execution output paths through the artifact service (logical prefix + capture toggles + overwrite guard), new `trace`/`log`/`execution_screenshot` kinds routed to Reports, fail-fast config validation, runner output capture, Jack output persistence. No migration. Status → review.
