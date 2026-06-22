---
title: 'Self-healing recovery for pipeline threads orphaned by a mid-run worker restart'
type: 'bugfix'
created: '2026-06-22'
status: 'done'
baseline_commit: 'd97e58533b04901b688a1c04f24032cfc8dc0e53'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/investigations/bob-stuck-parsing-thread1-investigation.md'
  - '{project-root}/project-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** When the backend worker dies mid-run (uvicorn `--reload` restart, crash, OOM, kill), the in-flight asyncio pipeline task is killed by process death — it never raises a Python exception, so no `except` runs, no error message is sent, and no DB status is updated. The thread is left at `status="processing"` forever; on reload the frontend re-reads `processing` and shows an endless "Step X of 5 · Testing connection…" spinner with no way to recover. (Confirmed root cause: thread #1, worker restart 08:28:19 UTC mid-extraction.)

**Approach:** Make the system self-heal. (1) On every worker startup, reconcile orphaned work: any thread still `processing` → reset to the re-runnable `start` status plus a persisted system message explaining the interruption; any agent_run still `running` → `interrupted`. (2) Defense-in-depth: bound each Bob "convert" LLM call with a hard wall-clock timeout so a single hung/slow call surfaces as a failed conversion instead of stalling the step. The existing frontend `start` path then renders the agent's intake form (the retry affordance) with no risky UI rework.

## Boundaries & Constraints

**Always:** Reconciliation runs once per worker boot inside the FastAPI `lifespan` startup, in one committed transaction, and is idempotent (only touches rows currently `processing` / `running`). Reset thread status to the EXISTING `AgentState.START` value (`"start"`) — fully supported across the frontend (status pill, Bob input form at App.tsx:2259). Convert-LLM timeout is a generous total bound (reuse the 600s LLM budget) so legitimate slow conversions (observed up to 140s) still succeed. Secrets never logged. `uv run` only (never `python3`).

**Ask First:** Introducing any NEW thread/agent-run status string not already in `AgentState` / the TS `AgentStatus` union (would require a coordinated full-stack change). Changing how/where a thread is first set to `processing`.

**Never:** Do not invent an `interrupted`/`failed` THREAD status that the frontend can't render (the status pill else-branch would wrongly show green "Done"). Do not auto-restart the interrupted run (no expensive on-prem re-run without the user). Do not add a DB migration (status columns are free-form strings). Do not just disable `--reload` as the fix — the recovery must be robust to ANY process death. Do not change agent business logic or Bob's extraction flow beyond the timeout guard. Do not auto-commit or run alembic (Thuong does both).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Orphaned thread on boot | Thread `status="processing"` exists at startup | Status set to `"start"`; one system Message appended ("previous run interrupted by server restart — start again"); counts logged | N/A |
| Orphaned run on boot | AgentRun `status="running"` at startup | Status set to `"interrupted"`; thread status NOT forced to the run value (thread → `"start"`) | N/A |
| Clean boot | No `processing` threads, no `running` runs | No rows changed; no messages added; logs "0 reconciled" | N/A |
| Reconcile DB failure | DB unavailable at startup | Log a warning, do NOT crash app startup (match SeaweedFS init resilience) | swallow + log |
| Convert call hangs | `_format_story`/`invoke_vision` exceeds the total timeout | `asyncio.TimeoutError`/`LLMTimeoutError` raised → caught at bob.py:1184 → "⚠ Failed to convert '<page>'" → loop continues | typed timeout |
| Convert call slow-but-ok | Conversion takes <timeout (e.g. 140s) | Completes normally, "✓ Converted" emitted | N/A |

</frozen-after-approval>

## Code Map

- `src/ai_qa/api/app.py` -- `lifespan` (line 48); add reconciliation call after SeaweedFS init, wrapped in try/except like the existing block.
- `src/ai_qa/threads/service.py` -- add `reconcile_interrupted_work()` method (only `update_thread`/`update_agent_run` exist today; no stuck-reset path). Uses existing `add_message`.
- `src/ai_qa/agents/base.py` -- `AgentState` enum (`START="start"`, `PROCESSING="processing"`) — source of the status constants to use.
- `src/ai_qa/db/session.py` -- `create_session_factory(settings)` for a sync session inside `lifespan` (same pattern as websocket.py:242-247).
- `src/ai_qa/pipelines/requirement_formatter.py` -- `_format_story` (line 311) direct `_chat_model.ainvoke` → wrap with hard timeout (mirror Bob clarify loop bob.py:1582).
- `src/ai_qa/ai_connection/client.py` -- `invoke_vision` (line 249) `_chat_model.ainvoke` → wrap with hard timeout; map `asyncio.TimeoutError` → `LLMTimeoutError`.
- `frontend/src/App.tsx` -- (CHANGED, see Change Log) the inline Bob MCP form (~line 2150) is gated by `submittedMcp`, which replays `true` from the persisted `bob_start` carrier on a recovered thread → the retry form was disabled/hidden. Re-enable the key input + Start button when `status === "start"`. `confluence_url` comes from the project (`handleBobStart`, App.tsx:1503), so retry only needs the MCP key.
- `frontend/src/hooks/usePipelineState.ts` -- reset-to-`start` correctly turns the `processing` spinner off (`isProcessing` is gated on `processing`, App.tsx:1600/1785); the persisted system warning renders (passes the chat filter).
- `tests/threads/` + `tests/pipelines/` -- new unit tests.
- `project-context.md` -- (low priority) document recommended `--reload-exclude` for `_bmad-output`/artifacts dirs.

## Tasks & Acceptance

**Execution:**
- [x] `src/ai_qa/threads/service.py` -- add `reconcile_interrupted_work()` -- bulk-find threads `status==PROCESSING` → set `START` + append a system Message; find agent_runs `status=="running"` → `"interrupted"` (do NOT cascade to thread); single commit; return `(threads_count, runs_count)`.
- [x] `src/ai_qa/api/app.py` -- call reconciliation in `lifespan` startup -- open a sync session via `create_session_factory`, run the method, log counts, wrap in try/except so a failure never blocks startup; close the session.
- [x] `src/ai_qa/pipelines/requirement_formatter.py` -- bound `_format_story` -- wrap the LLM call in `asyncio.wait_for` with a generous total timeout (module constant, e.g. `_CONVERT_LLM_TIMEOUT`); prefer routing via `LLMClient.ainvoke` for typed errors.
- [x] `src/ai_qa/ai_connection/client.py` -- bound `invoke_vision` -- wrap in `asyncio.wait_for`; map `asyncio.TimeoutError` to `LLMTimeoutError`.
- [x] `tests/unit/test_threads_service.py` -- unit-test the I/O matrix: orphaned thread→start+message, orphaned run→interrupted, clean boot no-op, idempotency (second run changes nothing).
- [x] `tests/pipelines/test_requirement_formatter.py` -- unit-test convert timeout: a hung fake LLM raises within the bound; a fast fake completes normally.
- [x] `project-context.md` -- (low) note `--reload-exclude` recommendation.
- [x] `frontend/src/App.tsx` -- re-enable the inline Bob MCP key input + Start button when `status === "start"` so a recovered thread can actually retry (the persisted `bob_start` otherwise disables them via replayed `submittedMcp`). Added during review (Change Log CL-1).

**Acceptance Criteria:**
- Given a thread left at `status="processing"` from a prior process, when the worker starts, then it becomes `status="start"`, gains exactly one explanatory system message, and the UI shows the agent's start form (no spinner) on reload.
- Given agent_runs left at `running`, when the worker starts, then they become `interrupted` without forcing their thread to `interrupted`.
- Given reconciliation raises (DB down), when the worker starts, then startup still succeeds (warning logged), matching SeaweedFS-init resilience.
- Given a Bob convert call that never returns, when the total timeout elapses, then it raises and is caught at bob.py:1184 as "⚠ Failed to convert", and the extraction loop proceeds to the next page.
- Given the backend test suite, when run, then it passes and `mypy src` is clean.
- Given a recovered Bob thread (reset to `start` with a persisted `bob_start`), when it loads, then the MCP key input is enabled and the Start button is shown so the user can re-trigger extraction (see CL-1).

## Spec Change Log

- **CL-1 (2026-06-22, review):** The acceptance auditor's finding (verified against App.tsx) refuted the Design-Note assumption that "the frontend needs NO change." For a thread that had already started Bob, a persisted `bob_start` carrier replays `submittedMcp=true` on reload, which **disables the MCP input and hides the Start button** (inline form, App.tsx:2150/2153), while the standalone fresh form is gated out by `!messages.some(bob_start)` (App.tsx:2257). Net: the spinner cleared and the warning showed, but there was **no usable retry control** — the frozen intent "retry affordance" was unmet. **Amended:** added a frontend task + Code Map entry; the fix re-enables the inline MCP key input + Start button when `status === "start"`. Known-bad avoided: a "recovered" thread the user cannot actually restart. KEEP: reset-to-`start` (not a new status) and the persisted system message — both verified correct/load-bearing. Backend code unchanged (auditor confirmed all backend ACs met), so no revert/re-derive was needed.

## Design Notes

Why reset to `start` (not a new `interrupted` status): the App.tsx status pill (1804-1833) maps only `start/processing/review_request` and an else→green "Done"; `error`/`failed` would render as "Done" and need pill + `StatusBadge` + input-gating rework. `start` is fully supported and mirrors the existing `isAliceStart` recovery (usePipelineState:252-285). The persisted system message carries the "why"; the agent's start form is the retry.

Frontend note (CL-1): "reset to `start`" stops the spinner with no frontend change, but the Bob *retry control* needed one — the persisted `bob_start` carrier replays `submittedMcp=true`, which disabled the MCP form. The fix re-enables that form when `status === "start"`. Other agents (Mary/Sarah/Jack) don't gate their start affordance on a carrier message, so this is Bob-specific.

Reconciliation must update agent_runs directly (not via `update_agent_run`, which syncs `run.thread.status = status` and would clobber the thread back to `interrupted`). Set runs first or independently, then set threads to `start`.

## Verification

**Commands:**
- `uv run pytest tests/threads tests/pipelines -p no:cov` -- expected: new + existing tests pass.
- `uv run pytest` -- expected: full suite green.
- `uv run mypy src` -- expected: clean (strict).
- `uv run ruff check src tests && uv run ruff format --check src tests` -- expected: clean.
- `cd frontend && npm run typecheck` -- expected: clean (only if frontend touched).

**Manual checks:**
- Reproduce: start a Bob extraction, restart the worker mid-"Parsing…", reload the page → thread shows Bob's start form + the interruption system message, no spinner. (Confirms end-to-end recovery.)

## Suggested Review Order

**Startup recovery (the core fix)**

- Entry point — the reconciliation logic: resets `processing`→`start` + system message, `running`→`interrupted`, single commit, idempotent.
  [`service.py:264`](../../src/ai_qa/threads/service.py#L264)

- Wired once per worker boot in the FastAPI lifespan, resilient (failure never blocks startup).
  [`app.py:79`](../../src/ai_qa/api/app.py#L79)

**Bounded LLM calls (defense-in-depth)**

- Hard wall-clock timeout around the requirement-conversion call so a hung provider can't stall the step.
  [`requirement_formatter.py:322`](../../src/ai_qa/pipelines/requirement_formatter.py#L322)

- Same guard on the vision call, mapped to `LLMTimeoutError`.
  [`client.py:253`](../../src/ai_qa/ai_connection/client.py#L253)

**Frontend recovery (retry affordance — see CL-1)**

- Re-enable Bob's MCP key input + Start button when `status === "start"` so a recovered thread can actually retry.
  [`App.tsx:2152`](../../frontend/src/App.tsx#L2152)

**Peripherals (tests + config)**

- Reconciliation unit tests (reset, no-cascade, clean-boot no-op, idempotency).
  [`test_threads_service.py:118`](../../tests/unit/test_threads_service.py#L118)

- Convert-timeout unit test (hung LLM raises within the bound).
  [`test_requirement_formatter.py:376`](../../tests/pipelines/test_requirement_formatter.py#L376)

- `--reload` mid-run hazard note + `--reload-exclude` recommendation.
  [`project-context.md`](../../project-context.md)
