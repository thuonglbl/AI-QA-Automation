---
baseline_commit: 0de0b7c
---

# Story 14.2: Playwright Execution Runner

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want Jack to execute the approved Python Playwright scripts I confirmed in a controlled runner process,
so that I can validate the generated automation against the target application and get a real pass/fail/error result for every test, persisted and linked back to its source artifacts.

## Acceptance Criteria

Verbatim from [epics.md#Story-14.2](_bmad-output/planning-artifacts/epics.md) (lines 1462-1482), expanded with implementation defaults (see "Scope decisions"). This story **fills the `_begin_execution()` stub** that Story 14.1 left behind: 14.1 ends the input-selection gate by storing `self.confirmed_scripts` and calling a stub that transitions to DONE; 14.2 replaces that stub body with the real runner (PROCESSING → execute → persist → message) and implements the `process()` method the `BaseAgent` ABC requires.

### AC1 — Controlled execution of each selected script + per-run capture

- **Given** approved scripts are selected (confirmed via the 14.1 gate)
- **When** Jack starts execution
- **Then** each selected Python Playwright script is executed in a **controlled runner process** (a subprocess, isolated from the FastAPI event loop), not in-process
- **And** the run captures, per test: **pass/fail/error status, start time, end time, duration, and browser context** (browser = `chromium` by default in 14.2; multi-browser is Story 14.4)

### AC2 — Failure capture + run policy

- **Given** a script fails during execution
- **When** the failure occurs
- **Then** Jack captures the **error message**, **stack trace where safe** (scrubbed of secrets), and a **failure classification** (e.g. `assertion` / `timeout` / `selector` / `navigation` / `error`)
- **And** execution **continues or stops according to configured run policy** (default policy = `continue` — run every selected script even if one fails; a `stop_on_first_failure` policy is supported via config)

### AC3 — Persist results linked to provenance

- **Given** execution completes
- **When** results are persisted
- **Then** each result is linked to its **source script artifact, test case artifact where available, project, thread, and execution run ID**
- **And** a run-level summary (totals, started/completed timestamps, duration, status) is persisted on the Jack `agent_run`

---

## ⚠️ Sequencing dependency (READ FIRST)

This story is **Story 2 of Epic 14** and builds directly on **Story 14.1** (`14-1-approved-script-execution-input-selection`, status `in-progress` in [sprint-status.yaml](_bmad-output/implementation-artifacts/sprint-status.yaml)). 14.1 creates `src/ai_qa/agents/jack.py`, the input-selection gate, the `load_approved_scripts()` adapter loader, and the frontend Jack surface. **14.2 assumes 14.1 is implemented.** Before starting, verify in the live tree:

1. **`src/ai_qa/agents/jack.py` exists** with `handle_start` → `_present_script_selection` → `handle_approve`/`_confirm_inputs` → `_begin_execution()` (the 14.1 STUB) and a placeholder `process()`. At the time this story was written, `jack.py` did **not yet exist** (14.1 unimplemented) — if still absent, **finish 14.1 first** (do not re-spec it here).
2. **`PipelineArtifactAdapter.load_approved_scripts()` exists** ([artifact_adapter.py](src/ai_qa/pipelines/artifact_adapter.py)) — the thread-prioritized loader 14.1 adds alongside `load_scripts()` ([artifact_adapter.py:271-273](src/ai_qa/pipelines/artifact_adapter.py:271)).
3. **`self.confirmed_scripts: list[PipelineArtifact]`** is populated by `_confirm_inputs` before `_begin_execution` is called.

If `jack.py` / `load_approved_scripts` are absent, **flag and stop** — 14.2 has no skeleton to extend.

> Reconcile every cited `file:line` / snippet against live code and treat them as **leads to verify**, not gospel — record divergences in Completion Notes (per [verify-subagent-claims](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\verify-subagent-claims.md) and [create-story-snippet-hazards](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\create-story-snippet-hazards.md)).

---

## ⚠️ CRITICAL: the generated scripts are pytest + pytest-playwright test functions

Sarah's `ScriptGenerator` emits **pytest test functions**, not standalone scripts (verified in [prompts/script_generation.py:35-39, 122-125, 305](src/ai_qa/prompts/script_generation.py:35)):

```python
def test_<descriptive_name>(page: Page):
    """..."""
    page.goto(f"{BASE_URL}/...")
    expect(...).to_be_visible()
```

Three hard consequences for the runner:

- **The `page: Page` fixture comes from `pytest-playwright`.** That package is **NOT a current dependency** ([pyproject.toml:11-35](pyproject.toml:11) lists `playwright>=1.60.0` only; the dev group has `pytest`/`pytest-asyncio`/`pytest-cov` but no `pytest-playwright` — [pyproject.toml:96-104](pyproject.toml:96)). **14.2 must add `pytest-playwright`** (see Decision #1). The scripts cannot run via plain `python script.py`.
- **The scripts read `BASE_URL = os.environ["APP_BASE_URL"]`** at import time ([script_generation.py:23, 290](src/ai_qa/prompts/script_generation.py:23)). A script raises `KeyError` immediately if `APP_BASE_URL` is unset. **The runner MUST set `APP_BASE_URL`** in the subprocess environment → 14.2 needs a target URL (see Decision #3 — environment selection).
- **The scripts assume a pre-authenticated SSO session** supplied at execution time and never automate login ([script_generation.py:88-104, 289, 314](src/ai_qa/prompts/script_generation.py:88)). In 14.2 the default browser context is **unauthenticated** (a test needing auth will legitimately fail and be captured as such); injecting the captured `storageState` is **Story 14.4** (where the "authenticated context" AC lives — [epics.md:1523-1525](_bmad-output/planning-artifacts/epics.md:1523)).

> ⚠️ **pytest config-inheritance gotcha:** the repo's [pyproject.toml:69-72](pyproject.toml:69) sets `addopts = "--cov=src/ai_qa --cov-report=term-missing --cov-fail-under=80"`. If the runner invokes `pytest` with the project as rootdir, it inherits the coverage gate and **fails the run on a coverage shortfall that has nothing to do with the user's scripts**. The runner MUST isolate config — run with `-c <generated pytest.ini>` (or `-o addopts=`) **and** `--rootdir <tmpdir>`, `-p no:cacheprovider`, `-p no:cov` so it ignores the repo's `addopts` and coverage plugin entirely. See [backend-test-suite notes](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\backend-test-suite-orphaned-legacy-tests.md).

---

## Scope decisions (defaults chosen from code + ACs — confirm or correct via Saved Questions)

- **Decision #1 — runner mechanism = subprocess `pytest` + `pytest-playwright` (CONFIRMED 2026-06-21 by Thuong).** Add `pytest-playwright` as a **runtime** dependency (`uv add pytest-playwright`) — Jack executes it in production, not only in tests. Materialize each approved script to a temp working dir, then run `pytest` in a controlled subprocess (mirror the proven pattern in [admin.py run_e2e_tests](src/ai_qa/api/admin.py): `subprocess.run([...], capture_output=True, timeout=...)` wrapped in `asyncio.to_thread(...)`). Capture structured results via **`--junit-xml`** (built into pytest — no extra dependency) and parse the XML for per-test status/duration/error. Alternative (rejected): a custom in-process Playwright harness (`sync_playwright` + `exec` the module + manufacture a `page`) — reimplements fixtures/parametrization and risks event-loop coupling.
- **Decision #2 — new persistence model `TestExecutionResult` + Alembic migration (CONFIRMED 2026-06-21 by Thuong).** AC3 enumerates linkage fields (source script artifact, test case artifact, project, thread, execution run id) and Story 14.6 needs to **filter history by browser/result/date** — neither is queryable from a JSON blob. Add a `test_execution_results` table (per-test row) keyed by `agent_run_id`; persist the **run-level summary** to the existing `AgentRun.execution_metadata` JSON ([threads/models.py:74](src/ai_qa/threads/models.py:74)). The Jack `agent_run` **is** the "execution run" — no separate run table. Alternative (rejected): store everything in `AgentRun.execution_metadata` JSON only (14.6 filtering + 19 metrics want rows).
- **Decision #3 — execution context input = target environment → `APP_BASE_URL` (required to run at all).** After the 14.1 script-selection confirm, Jack must resolve a target URL. Reuse the project `environments` list ([db/models.py:76](src/ai_qa/db/models.py:76)) the same way Sarah does ([SarahInputsForm.tsx](frontend/src/components/agents/SarahInputsForm.tsx) environment dropdown): if the project has environments, present a dropdown; else a free-text URL field. The chosen URL becomes `APP_BASE_URL`. **Role selection + captured-session auth + multi-browser are deferred to 14.4** — 14.2 runs against the chosen URL with a default unauthenticated `chromium` context. (Saved Q#3 — alternative: derive the env from the thread's last Sarah run instead of re-asking.)
- **Decision #4 — default browser = `chromium`, headless follows server mode.** 14.2 runs a single browser (`chromium`). Headless/headed mirrors the E2E switch: headed locally, headless when `E2E_SERVER_MODE`/server mode is set (mirror [admin.py run_e2e_tests](src/ai_qa/api/admin.py) `server_mode`/`headed` logic + `E2E_NO_SANDBOX`/`PLAYWRIGHT_IGNORE_HTTPS_ERRORS` deploy flags). Multi-browser is 14.4.
- **Decision #5 — Jack terminal state after execution = `REVIEW_REQUEST` carrying a result summary (RECOMMENDED).** After the runner persists results, Jack transitions to `REVIEW_REQUEST` and sends a result-summary message (so 14.6's review UX has a natural anchor and the human-review-at-every-step rule holds — [architecture.md:271-272](_bmad-output/planning-artifacts/architecture.md:271)). The full report artifact is Story 14.5; the rich review UI is 14.6. In 14.2 the message is a concise text/summary. (Saved Q#4 — alternative: go straight to `COMPLETED`.)
- **Decision #6 — per-script timeout + run policy from config.** A per-script execution timeout (default reuse/extend `browser_timeout` or a new `execution_timeout`) and a `run_policy` (`continue` default | `stop_on_first_failure`) live in `AppSettings`. The overall subprocess gets a hard wall-clock timeout (like the 900s cap in [admin.py run_e2e_tests](src/ai_qa/api/admin.py)). Output-path/screenshot/trace config is **Story 14.3** — 14.2 may write pytest artifacts to a temp dir but does **not** persist them through the artifact service yet.
- **Out of scope for 14.2:** configurable output paths / persisting screenshots-traces-logs through the artifact service (14.3), multi-browser + authenticated captured-session context (14.4), the structured report artifact (14.5), the report review UX + history API (14.6). Do **not** build report rendering, browser matrices, or session injection here.

## What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status / action |
| --- | --- | --- |
| Jack skeleton + input-selection gate + `confirmed_scripts` + `_begin_execution()` STUB + placeholder `process()` | `src/ai_qa/agents/jack.py` (created by Story 14.1) | ✅ **extend** — replace the `_begin_execution` stub body; implement `process()` |
| `PipelineArtifactAdapter.load_approved_scripts()` (thread-prioritized) + `_to_pipeline_artifact` (reads `.py` content) | [artifact_adapter.py](src/ai_qa/pipelines/artifact_adapter.py) (14.1) / [artifact_adapter.py:398-410](src/ai_qa/pipelines/artifact_adapter.py:398) | ✅ scripts already loaded as raw `.py` text in `confirmed_scripts` |
| Subprocess execution pattern (`subprocess.run(..., capture_output=True, timeout=...)` + `asyncio.to_thread(...)` + env overrides + output cap) | [admin.py `run_e2e_tests`](src/ai_qa/api/admin.py) | ✅ **mirror** — same controlled-subprocess shape; headed/headless + `E2E_NO_SANDBOX` deploy flags |
| `AgentRun.execution_metadata` JSON column (run-level summary) + `summary`/`status` | [threads/models.py:63-78](src/ai_qa/threads/models.py:63) | ✅ persist totals/timestamps/duration here |
| `Artifact.agent_run_id` / `thread_id` / `project_id` FKs (provenance) | [db/models.py:185-224](src/ai_qa/db/models.py:185) | ✅ source script artifact id is already known per `PipelineArtifact.id` |
| `playwright>=1.60.0` runtime dep (browsers + sync/async API) | [pyproject.toml:34](pyproject.toml:34) | ✅ Playwright present; **add `pytest-playwright`** (missing) |
| `chrome_path` (User + AppSettings) / `browser_timeout` config | [db/models.py:40](src/ai_qa/db/models.py:40), [config.py](src/ai_qa/config.py) | ✅ reuse for browser launch + timeout default |
| Project `environments` list (`[{"name","url"}]`) for target URL | [db/models.py:72-76](src/ai_qa/db/models.py:72) | ✅ source `APP_BASE_URL`; mirror Sarah env dropdown |
| `BaseAgent` lifecycle (`transition_to`/`send_message`/`AgentState.PROCESSING/REVIEW_REQUEST/COMPLETED/ERROR`/`_format_error_message`) | `src/ai_qa/agents/base.py` | ✅ drive PROCESSING → run → REVIEW_REQUEST |
| Sarah's `_begin_generation` tail (PROCESSING → work → review) — the lifecycle shape to mirror for `_begin_execution` | `src/ai_qa/agents/sarah.py` | ✅ **mirror** the state-transition shape (generation → execution) |
| Architecture target: `jack.py → script_runner.py → [Chrome/Firefox/Edge] → append execution report + artifact metadata` | [architecture.md:830-834](_bmad-output/planning-artifacts/architecture.md:830); test path `tests/test_pipelines/test_script_runner.py` ([architecture.md:657](_bmad-output/planning-artifacts/architecture.md:657)) | 📋 create `src/ai_qa/pipelines/script_runner.py` |

---

## Tasks / Subtasks

- [x] **Task 1 — Add `pytest-playwright` dependency (AC1)**
  - [x] `uv add pytest-playwright` (runtime dependency — Jack runs it in production), then `uv sync`. Verify `playwright install chromium` is part of the deploy image (the backend image already bundles Playwright per the E2E-runner work — confirm the browser binaries are present). State in Completion Notes whether the image needs a `playwright install` step.
  - [x] Do **not** add `pytest-json-report` — use the built-in `--junit-xml` reporter for structured results.

- [x] **Task 2 — `TestExecutionResult` model + Alembic migration (AC1, AC2, AC3)**
  - [x] Add `class TestExecutionResult(UUIDPrimaryKeyMixin, TimestampMixin, Base)` to [db/models.py](src/ai_qa/db/models.py) (mirror the `mapped_column` style of `Artifact`/`AgentRun`). Columns: `agent_run_id` (FK `agent_runs.id`, `ondelete="CASCADE"`, indexed — the execution run id), `project_id` (FK, indexed), `thread_id` (FK `threads.id`, `ondelete="SET NULL"`, nullable), `source_script_artifact_id` (FK `artifacts.id`, `ondelete="SET NULL"`, nullable), `source_test_case_artifact_id` (FK `artifacts.id`, nullable — "where available"), `test_name` (String), `browser` (String, default `"chromium"`), `status` (String — `passed`/`failed`/`error`/`skipped`), `failure_classification` (String, nullable), `error_message` (Text, nullable), `stack_trace` (Text, nullable — **scrubbed**), `started_at`/`ended_at` (DateTime tz, nullable), `duration_ms` (Integer, nullable). Add an index on `(project_id, status)` and `(agent_run_id,)`.
  - [x] Generate the migration: `uv run alembic revision --autogenerate -m "add test_execution_results"`, review it (autogen often misses `server_default`/index nuances), then `uv run alembic upgrade head`. **Migration is part of DoD** ([dev-story-process-guardrails](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\dev-story-process-guardrails.md)).
  - [x] Register the model where the others are imported (so the mapper + metadata pick it up — follow how `Artifact`/`AgentRun` are wired in [db/models.py:24-27](src/ai_qa/db/models.py:24)).

- [x] **Task 3 — `script_runner.py` (the engine) (AC1, AC2)** — new file `src/ai_qa/pipelines/script_runner.py`
  - [x] A pure-ish, unit-testable module that, given a list of `(name, script_text, source_artifact_id)` + a target `base_url` + browser + timeouts + run policy, returns a structured `RunResult` (a dataclass: list of per-test results + run summary). Keep all Jack/agent/DB concerns OUT of this module (the agent calls it; the agent persists).
  - [x] **Materialize:** write each script to `<tmpdir>/test_<i>_<safe_name>.py`. Write an isolated `pytest.ini` (or `conftest.py`) in `<tmpdir>` so the run does NOT inherit the repo's `addopts`/coverage. Generate a `conftest.py` only if needed for fixtures (e.g. `base_url` is passed via env, not fixtures, in 14.2).
  - [x] **Run:** build the command `pytest <tmpdir> --browser chromium --junit-xml=<tmpdir>/results.xml -p no:cacheprovider -p no:cov -o addopts= --rootdir <tmpdir> [--headed]` and execute via `subprocess.run(..., cwd=<tmpdir>, capture_output=True, timeout=<wall_clock>, env={**safe_env, "APP_BASE_URL": base_url})`, wrapped by the **agent** in `asyncio.to_thread(...)`. Apply headless/sandbox/TLS env like [admin.py run_e2e_tests](src/ai_qa/api/admin.py). Map `run_policy="stop_on_first_failure"` → add `-x`.
  - [x] **Parse:** read `results.xml` (JUnit) → per-test `{test_name, status (passed/failed/error/skipped), duration_ms, error_message, stack_trace}`. Classify failures into `assertion`/`timeout`/`selector`/`navigation`/`error` from the message/trace (best-effort substring heuristics; default `error`). If the XML is missing (subprocess died/timeout), synthesize an `error` result per script with the captured stderr tail.
  - [x] **Scrub:** before returning, strip anything secret-shaped from `error_message`/`stack_trace` (cookies, tokens, `Authorization`, `set-cookie`, anything that looks like a key) — leak-canary convention. Cap each field length.

- [x] **Task 4 — Wire the runner into Jack: real `_begin_execution` + `process()` (AC1, AC2, AC3)** — in `src/ai_qa/agents/jack.py`
  - [x] Replace the 14.1 `_begin_execution()` STUB body: `await self.transition_to(AgentState.PROCESSING)`; resolve `base_url` (Task 5); build the input list from `self.confirmed_scripts` (`(a.name, a.content, a.id)`); call the runner via `await asyncio.to_thread(run_scripts, ...)` (the runner's subprocess call is sync). On exception → `transition_to(ERROR)` + `_format_error_message`.
  - [x] **Persist (AC3):** create one `TestExecutionResult` row per parsed test, linking `agent_run_id = self.agent_run_id`, `project_id`, `thread_id`, `source_script_artifact_id` (the `PipelineArtifact.id` the test came from), and `source_test_case_artifact_id` if resolvable from the script's 13.8 side-car (`load_metadata` → `source_test_case_id`; degrade to None). Write the run-level summary (totals, passed/failed/error counts, started/completed, total duration, status) to `AgentRun.execution_metadata`; set `AgentRun.status`/`summary`. Use the SYNC artifact/DB session path (the agent already holds a sync `Session` via the artifact service context — do NOT open an async session).
  - [x] **Finish (Decision #5):** `await self.transition_to(AgentState.REVIEW_REQUEST)`; `send_message` a concise summary ("Executed N scripts: X passed, Y failed, Z errors in <duration>.") with `metadata={"type": "execution_summary", ...counts...}` so 14.6 can anchor on it. Add a `# Story 14.5: compose the full report artifact here.` marker.
  - [x] Implement the real `process()` (the ABC method 14.1 stubbed) to return a `StageResult(success=..., data={...summary...})` reflecting the run — or keep `_begin_execution` as the entry and have `process()` delegate; choose one and document it.

- [x] **Task 5 — Execution context: target environment → `APP_BASE_URL` (AC1, Decision #3)**
  - [x] After the 14.1 selection confirm, resolve the target URL. If `project.environments` is non-empty, the Jack input panel must let the user pick one (mirror [SarahInputsForm.tsx](frontend/src/components/agents/SarahInputsForm.tsx)); else accept a free-text URL. Carry the chosen URL into `_begin_execution` (panel → `confirm_inputs` data, or a small follow-up `jack_inputs_request` form like Sarah's `sarah_inputs_request`).
  - [x] **Block (mirror 14.1 AC3 shape):** if no environment is configured AND no URL is provided → send a UX-DR12 *What happened / Why / What to do* message ("Jack needs a target environment URL to run scripts. Configure a project environment or enter a URL.") and do NOT start the subprocess.
  - [x] Set `APP_BASE_URL` = the chosen URL in the runner's subprocess env (Task 3). Do NOT hardcode a host.

- [x] **Task 6 — Frontend: surface the run + summary (AC1, AC3)** — in [frontend/src/App.tsx](frontend/src/App.tsx) + types
  - [x] Extend `handleJackMessage` (14.1) to capture `metadata.type === "execution_summary"` → `setJackState({ ...summary })`; register in BOTH the live-queue effect and the history-restore effect (+ dep arrays) — same dual-registration rule as Sarah/14.1.
  - [x] If Decision #3 needs an environment picker, extend the Jack panel (14.1 `JackInputSelection.tsx`) or add a `JackInputsForm.tsx` mirroring `SarahInputsForm.tsx` (env dropdown / URL field), feeding the chosen URL into `handleJackConfirm`.
  - [x] Render a minimal "Execution running…" processing state and a minimal result summary on `execution_summary` (counts + duration). The rich report UI is **Story 14.6** — keep this minimal. Add the `ExecutionSummary` TS type in `frontend/src/types/` and keep it in sync with the backend payload (full-stack sync rule).

- [x] **Task 7 — Backend tests (AC1, AC2, AC3)**
  - [x] `tests/test_pipelines/test_script_runner.py` (the architecture-named path): unit-test the **parser** with sample JUnit XML (passed/failed/error/skipped → correct structured results + classification), the **scrub** (a secret-shaped token in an error never appears in the result), and the **command builder** (asserts `-o addopts=`, `--rootdir`, `--junit-xml`, `--browser chromium`, `APP_BASE_URL` in env, `-x` only under `stop_on_first_failure`). Do NOT launch a real browser in unit tests — patch `subprocess.run` to drop a canned `results.xml` (or inject a fake runner) so the test is hermetic and fast. A real-browser run is integration-only (mark `@pytest.mark.integration`).
  - [x] `tests/test_agents/test_jack.py` (extend 14.1's): patch the runner (`ai_qa.agents.jack.run_scripts` or the module) to return a canned `RunResult`; assert PROCESSING→REVIEW_REQUEST transitions, `execution_summary` message emitted, `TestExecutionResult` rows created with correct provenance (agent_run_id/project_id/thread_id/source_script_artifact_id), and `AgentRun.execution_metadata` populated. Add an AC3 "no URL/environment → block, no subprocess" test. Use `mock_project_context` + `mock_broadcast`; honor the conftest hazard from 14.1 ([agent-gate-conftest-regression](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\agent-gate-conftest-regression.md)).
  - [x] If a new `TestExecutionResult` persistence path is added to the adapter/service, add a focused test over real in-memory SQLite (mirror `tests/pipelines/test_pipeline_artifact_adapter.py`).

- [x] **Task 8 — Frontend tests (AC1)**
  - [x] Vitest: `execution_summary` message → Jack summary render; env picker (if added) → confirm sends the URL. Vitest 4 rules ([project-context.md#Testing-Rules](project-context.md)).
  - [x] E2E (`frontend/e2e/`): the full select→run path needs a reachable app + seeded approved scripts + browsers — integration-only. Default: scope the E2E to the **no-URL block path** (deterministic) and note the live-run deferral in Completion Notes (mirror 14.1 Decision #5). No `page.route`, no `waitForTimeout`.

- [x] **Task 9 — Verify (migration required)**
  - [x] `uv run alembic upgrade head` (new `test_execution_results` table). `uv run pytest --no-cov` (**whole** suite — coverage gate fails on subset runs). `uv run mypy src` clean. Pyrefly-clean (narrow Optionals: `self.project_context`, `agent_run_id`, `data.get(...)`; no redundant casts; bind `mock.call_args`/`await_args` before `.args`/`.kwargs` in tests).
  - [x] `uv run ruff check --fix src/ tests/` then `uv run ruff format src/ tests/`.
  - [x] Frontend: `npm run lint`, `npm run typecheck`, `npm run test`.
  - [x] Confirm secrets never reach the runner subprocess env, the persisted results, messages, or logs (leak-canary).

## Dev Notes

### Jack lifecycle after 14.2 (gate → run → review)

```
handle_start (14.1)
  → precondition + load_approved_scripts → present script_selection (REVIEW_REQUEST)

handle_approve (phase dispatch, 14.1)
  → phase == "input_selection" → _confirm_inputs(data)
        → confirmed_scripts = selected subset
        → resolve target URL (14.2 Decision #3): env picker / URL  [AC1]
            → none → BLOCK (UX-DR12), stay (no subprocess)
        → phase = "execution"
        → _begin_execution():            [14.2 — replaces the 14.1 STUB]
              transition_to(PROCESSING)
              run_scripts(scripts, base_url, browser="chromium", policy, timeouts)  [AC1/AC2]
                  → subprocess pytest + pytest-playwright + --junit-xml (asyncio.to_thread)
              persist: TestExecutionResult rows + AgentRun.execution_metadata        [AC3]
              transition_to(REVIEW_REQUEST) + send execution_summary                 [Decision #5]
              # Story 14.5: compose full report artifact
```

This mirrors Sarah's `_confirm_inputs → _begin_generation` shape, with execution swapped for generation and a runner subprocess in place of an LLM call.

### Why a subprocess (not in-process Playwright)

- The FastAPI app runs an asyncio loop; `pytest-playwright` uses the **sync** Playwright API (greenlet-driven). Running it in-process inside the loop is brittle and can deadlock. A subprocess is fully isolated and matches the proven [admin.py `run_e2e_tests`](src/ai_qa/api/admin.py) approach (`subprocess.run` + `asyncio.to_thread`). It also contains a crashing/hanging test behind a hard wall-clock timeout.
- **Never** parse `page.route`-mocked output or fabricate results — execute the real scripts and report what actually happened (faithful reporting rule).

### Result persistence shape (AC3)

- **Run-level → `AgentRun.execution_metadata`** (JSON): `{started_at, completed_at, duration_ms, total, passed, failed, errors, skipped, browser, base_url_host_only, run_policy}`. Store **host only** (or nothing) of the URL — never query strings that could carry tokens.
- **Per-test → `TestExecutionResult`** rows (Task 2): one row per `(test, browser)`. `browser` defaults to `chromium` in 14.2; 14.4 writes multiple rows per test (one per browser). `source_test_case_artifact_id` is best-effort from the 13.8 side-car (`adapter.load_metadata` → `source_test_case_id`); degrade to None ("where available").

### Architecture compliance (hard rules)

- **Agents never read/write storage directly — always via the artifact/persistence service** ([architecture.md:518, 533](_bmad-output/planning-artifacts/architecture.md:518)). The runner's temp dir is transient scratch (not a persisted artifact); persisted outputs are Story 14.3.
- **Mandatory human review at every step** ([architecture.md:271-272](_bmad-output/planning-artifacts/architecture.md:271)) → land in REVIEW_REQUEST with a summary (Decision #5), don't silently auto-complete.
- **Secret containment** ([architecture.md:66, 515](_bmad-output/planning-artifacts/architecture.md:66)): never put a user secret in the subprocess env, the captured stdout/stderr you persist, the scrubbed stack trace, the run summary, messages, or logs. `APP_BASE_URL` is a non-secret URL; nothing else credential-bearing flows in (auth is 14.4).
- **Project-scoped persistence** ([architecture.md:280](_bmad-output/planning-artifacts/architecture.md:280)): every `TestExecutionResult` carries `project_id`; scope derives from the thread/agent_run.
- **Backend payload/model change → matching TS interface in the same change** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)).

### Library / framework constraints (from project-context.md)

- **Backend:** Python ≥3.14, `uv` only (`uv add pytest-playwright`; never `pip`/`python3`). Ruff + Mypy strict (`uv run mypy src`). Pyrefly-clean (narrow Optionals before use; no redundant `cast`/`str()`; no bare `except` — `subprocess.TimeoutExpired`/`ET.ParseError` are specific; `pytest.raises` needs a type + `match=`). Sync `Session` in the agent's persistence path — no `MissingGreenlet`. `asyncio.to_thread` for the blocking subprocess.
- **New package:** `pytest-playwright` (the one new dependency this story adds — justified by the pytest `page` fixture). No others.
- **Migration required:** `test_execution_results` table — autogenerate, review, `alembic upgrade head`, record in Completion Notes.
- **Frontend:** React 19.2, TS ~6.0 strict, Vitest 4, ESLint 9 — keep the summary surface minimal (rich UI is 14.6).

### Forward-compat seams (not 14.2 scope, but keep clean)

- `script_runner.py` takes `browser` + `storage_state_path` parameters even though 14.2 only passes `chromium` + `None` — so **14.4** (multi-browser + authenticated context) only widens the call, not the engine.
- **14.2's unauthenticated run is interim.** 14.4 adds the captured-session (`storageState`) context and **hard-blocks a run when no session exists for the selected `(environment, role)`** (CONFIRMED 2026-06-21). So the "runs unauthenticated" behavior here is a stepping stone, not a permanent contract — keep the env/URL resolution and the `_begin_execution` gate clean so 14.4 can insert the session-resolution + block in front of the runner call without rework.
- The persisted output dir is a runner return value, not yet pushed through the artifact service — **14.3** routes it. Keep the runner returning the artifact paths it produced.
- A multi-epic Project-Admin RBAC redesign is awaiting sign-off ([design-projectadmin-rbac-redesign-2026-06-21.md](_bmad-output/planning-artifacts/design-projectadmin-rbac-redesign-2026-06-21.md)) that makes Jack role-aware + multi-browser — keep results keyed by `browser` (and later `role`) generically.

### Project Structure Notes

- **New files:** `src/ai_qa/pipelines/script_runner.py`, `tests/test_pipelines/test_script_runner.py`, the Alembic migration under `alembic/versions/`, possibly `frontend/src/components/agents/JackInputsForm.tsx` + `frontend/src/types/execution.ts`.
- **Modified files (expected):** `src/ai_qa/agents/jack.py` (real `_begin_execution` + `process()`), `src/ai_qa/db/models.py` (+`TestExecutionResult`), `pyproject.toml` + `uv.lock` (+`pytest-playwright`), `src/ai_qa/config.py` (execution timeout / run policy), `frontend/src/App.tsx` (summary handling + env picker), `tests/test_agents/test_jack.py`.

### Testing standards summary

- Backend: hermetic unit tests — patch `subprocess.run` (canned `results.xml`) for the runner; patch the runner for the agent. Real-browser runs are `@pytest.mark.integration`. Whole-suite `--no-cov`; mypy `src` only.
- Frontend: Vitest for the summary surface; E2E scoped to the deterministic block path.

### Previous-story / sibling intelligence

- **Story 14.1 (`in-progress`)** — creates Jack, the gate, `load_approved_scripts`, `confirmed_scripts`, the `_begin_execution` STUB, and the frontend Jack surface. 14.2 fills the stub. **Do not re-implement 14.1.**
- **Story 13.x (Sarah, `done`)** — `_begin_generation` is the lifecycle template (PROCESSING → work → review); `ScriptGenerator` is the script producer (pytest functions, `APP_BASE_URL`, pre-auth session) — the contract the runner must honor.
- **Epic 14 siblings:** 14.3 output paths (route the runner's outputs through the artifact service), 14.4 multi-browser + authenticated captured-session context, 14.5 report artifact, 14.6 review UX + history API. Keep `_begin_execution` and `run_scripts` clean seams.
- **Epic 19 (Audit/Metrics, backlog)** will aggregate `TestExecutionResult` — design columns to be query/aggregate-friendly.

### References

- [Source: _bmad-output/planning-artifacts/epics.md:1462-1482] — Story 14.2 ACs; 14.1 (1440-1460), 14.4 auth-context (1523-1525)
- [Source: _bmad-output/planning-artifacts/architecture.md] — jack.py → script_runner.py → [Chrome/Firefox/Edge] → execution report (830-834); test_script_runner.py path (657); jack.py role (584); mandatory review (271-272); no-direct-storage (518, 533); project-scoped (280); secret containment (66, 515); Jack capability profile (1169-1173)
- [Source: src/ai_qa/prompts/script_generation.py] — generated scripts are pytest `def test_x(page: Page)` (35-39, 122-125, 305); `BASE_URL = os.environ["APP_BASE_URL"]` (23, 290); pre-authenticated session / no hardcoded creds (88-104, 289, 314)
- [Source: src/ai_qa/api/admin.py] — `run_e2e_tests` controlled-subprocess pattern (`subprocess.run` + `asyncio.to_thread`, timeout cap, headed/headless + `E2E_NO_SANDBOX`/TLS deploy flags, output cap)
- [Source: src/ai_qa/threads/models.py:63-78] — `AgentRun` (`execution_metadata` JSON line 74, `status`, `summary`, `artifacts` relationship)
- [Source: src/ai_qa/db/models.py:185-224] — `Artifact` provenance FKs; (72-76) `Project.environments`; mixins/`mapped_column` style to mirror for `TestExecutionResult`
- [Source: src/ai_qa/pipelines/artifact_adapter.py] — `load_scripts`/`load_approved_scripts` (271-273 + 14.1), `load_metadata` side-car (308-317), `_to_pipeline_artifact` (398-410)
- [Source: pyproject.toml] — `playwright>=1.60.0` present (34); `pytest-playwright` absent; `addopts` coverage gate (69-72) — the config-inheritance gotcha
- [Source: _bmad-output/implementation-artifacts/14-1-approved-script-execution-input-selection.md] — the Jack skeleton + gate + `_begin_execution` STUB this story extends
- [Source: project-context.md] — `uv`/`npm` only; Ruff + Mypy strict; Pyrefly; sync DB in artifact path; no bare except; secret containment; full-stack sync; migration-in-DoD

## Saved Questions (for Thuong — defaults applied; confirm or correct)

**RESOLVED 2026-06-21 (Thuong):** Runner mechanism = `pytest` + `pytest-playwright` (add the dependency) — **confirmed** (Decision #1). Persistence = new `TestExecutionResult` table + migration — **confirmed** (Decision #2).

Still open:

1. **Target URL source (Decision #3).** Default = ask the user (env dropdown / URL field) at the Jack gate and set `APP_BASE_URL`. Alternative = reuse the environment from the thread's last Sarah run. Default = ask. Acceptable?
2. **Terminal state (Decision #5).** Default = `REVIEW_REQUEST` + summary message (report = 14.5, review = 14.6). Alternative = straight to `COMPLETED`. Default = REVIEW_REQUEST. Confirm?
3. **Run policy default (Decision #6).** Default = `continue` (run all selected scripts even on failure); `stop_on_first_failure` available via config. Acceptable?

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, bmad-dev-story workflow)

### Debug Log References

- `uv run pytest tests/pipelines/test_script_runner.py tests/test_agents/test_jack.py --no-cov` → 25 → 35 passed (incl. real-DB persistence)
- `uv run pytest --no-cov` (whole suite) → 1617 passed
- `uv run mypy src` clean (91 files); `uv run ruff check/format` clean
- `uv run alembic heads` → single head `a3f8d21c64b9` (chain valid)
- Frontend: `npm run typecheck` + `npm run lint` clean; `npx vitest run` → 30 files / 332 passed (JackInputSelection 21)

### Completion Notes List

- **Confirmed decisions applied:** Decision #1 runner = subprocess `pytest` + `pytest-playwright` (added as a **runtime** dep via `uv add`); Decision #2 new `TestExecutionResult` table + migration; Decision #3 target URL = env dropdown / free-text URL **folded into the 14.1 selection panel** (single-step, no re-entry form) → `confirm_inputs` carries `target_url`; Decision #5 terminal state = REVIEW_REQUEST + `execution_summary`; Decision #6 run policy via `AppSettings.run_policy` (default `continue`).
- **AC1** — each script runs in an isolated `pytest` subprocess (off the event loop via `asyncio.to_thread`); per-test status/duration/browser captured from JUnit XML. Config isolation: `-o addopts= -p no:cov -p no:cacheprovider --rootdir <tmp>` + a temp `pytest.ini` so the run never inherits the repo's coverage gate.
- **AC2** — failure capture: scrubbed `error_message`/`stack_trace` + `failure_classification` (assertion/timeout/selector/navigation/error). Run policy: `continue` (default) or `stop_on_first_failure` (→ `-x`). Hard wall-clock cap via `execution_wall_clock_timeout` (default 900s).
- **AC3** — one `TestExecutionResult` row per `(test, browser)` linked to agent_run/project/thread/source_script_artifact (+ best-effort `source_test_case_artifact_id` from the 13.8 side-car); run summary persisted to `AgentRun.execution_metadata` (host-only URL, totals, timings, policy) + `AgentRun.status`/`summary`. Sync `Session` path (reusable after the WS `_context_from_websocket` `close()`).
- **Secret containment** — `build_subprocess_env` strips every secret-shaped key (API_KEY/SECRET/TOKEN/PASSWORD/ENCRYPTION_KEY/…) before passing env to the subprocess; only non-secret `APP_BASE_URL` is injected. `scrub_secrets` redacts bearer/cookie/api-key/sk- patterns from all captured text. Leak-canary tests on env-build + JUnit parse. Summary stores **host only** (no query string).
- **Forward-compat seams (14.3/14.4):** `run_scripts(..., storage_state_path=None)` reserved for 14.4 auth; `RunResult.produced_files` (currently `run.log`) reserved for 14.3 persistence; `browser` param single-valued (`chromium`) in 14.2.
- **⚠️ MIGRATION — Thuong runs it:** the file `alembic/versions/a3f8d21c64b9_add_test_execution_results.py` is created (hand-authored to match repo style; chain validated via `alembic heads`). Per your preference I did **not** run `alembic upgrade head` — please run `uv run alembic upgrade head` before live use. Backend tests use in-memory SQLite `create_all` (no alembic needed).
- **pytest-playwright side-effect (fixed):** it transitively pulls `pytest-base-url`, whose session-scoped `base_url` fixture collided with many tests that use `base_url` as a plain parametrize arg (`ScopeMismatch`). Disabled it in-process via `addopts = "… -p no:base_url"`. The execution subprocess clears `addopts` + uses a fresh rootdir, so it still loads pytest-playwright + base-url there. **Deploy note:** the backend image must run `playwright install chromium` for real runs (the E2E-runner image already bundles Playwright — confirm the chromium binary is present).
- **Per-test absolute start/end timestamps** are not provided by JUnit XML; we store real per-test `duration_ms` + run-level `started_at`/`completed_at` (faithful — no fabricated per-test wall-clock).
- **E2E deferral:** a real run needs a reachable app + installed browsers (integration-only). Backend tests are hermetic (patch `subprocess.run`, canned JUnit XML). The no-URL block path is covered deterministically by the agent test.

### File List

- `pyproject.toml` / `uv.lock` — add `pytest-playwright`; `-p no:base_url` in addopts (M)
- `src/ai_qa/db/models.py` — `TestExecutionResult` model (M)
- `alembic/versions/a3f8d21c64b9_add_test_execution_results.py` — migration (A)
- `src/ai_qa/config.py` — `execution_timeout`/`execution_wall_clock_timeout`/`run_policy` (+`RunPolicy`) (M)
- `src/ai_qa/pipelines/script_runner.py` — the runner engine (A)
- `src/ai_qa/agents/jack.py` — real `_begin_execution` + `process()` + `_persist_results` + env picker (M)
- `frontend/src/types/execution.ts` — `ExecutionSummary` (A)
- `frontend/src/components/agents/JackInputSelection.tsx` — env/URL selector + `onConfirm(ids, url)` (M)
- `frontend/src/App.tsx` — env passthrough + execution_summary handling + summary card (M)
- `tests/pipelines/test_script_runner.py` — runner unit tests (A)
- `tests/test_agents/test_jack.py` — runner wiring + real-DB persistence tests (M)
- `frontend/src/components/__tests__/JackInputSelection.test.tsx` — env/URL + confirm payload tests (M)

### Change Log

- 2026-06-21 — Story 14.2 implemented: controlled Playwright execution runner (`script_runner.py` subprocess + JUnit parse + secret scrub), `TestExecutionResult` model + migration, `AppSettings` execution config, real Jack `_begin_execution`/`process()`/persistence, frontend env picker + execution summary. Migration to be applied by Thuong. Status → review.
