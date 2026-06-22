---
baseline_commit: 0de0b7c
---

# Story 14.1: Approved Script Execution Input Selection

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want Jack to load only **approved** Playwright script artifacts for the selected project (originating-thread scripts prioritized) and to let me confirm or adjust which scripts feed execution,
so that test runs use only reviewed, validated automation assets and never an unapproved, draft, or partial script set.

## Acceptance Criteria

Verbatim from [epics.md#Story-14.1](_bmad-output/planning-artifacts/epics.md) (lines 1440-1460), expanded with implementation defaults (see "Scope decisions"). This is the **third instance** of the `12.1 → 13.1 → 14.1` "load approved {X}, prioritize originating thread, confirm-before-{next stage}" pattern — the script analog of **Story 13.1** (Sarah's approved-test-case input selection), which is itself the test-case analog of **Story 12.1** (Mary's approved-requirements input selection). Story 13.8 explicitly reserved `load_approved_scripts` and the structural "only approved is automatic" guarantee for this story.

### AC1 — Approved, project-scoped scripts only (no workspace paths)

- **Given** approved script artifacts exist for the selected project
- **When** Jack prepares an execution run
- **Then** Jack loads only project-scoped **approved** script artifacts through the artifact service (`ArtifactService.list_artifacts(project_id, kind="playwright_script")` / the new `PipelineArtifactAdapter.load_approved_scripts()`)
- **And** rejected, draft, or unapproved scripts are excluded — this is **structural**, not a query predicate: `save_script` runs **only** in Sarah's approve path (skip/reject/regenerate never persist a script), so every `kind="playwright_script"` artifact is approved by construction (Story 13.8). **No discriminator column / filter is needed** — exactly like test cases (no draft script exists).
- **And** direct workspace path reads are not used (storage reads go through `ArtifactStorage` keyed by `storage_path`).

### AC2 — Thread prioritization + user confirm/adjust before execution

- **Given** the current thread has approved script artifacts
- **When** Jack prepares execution inputs
- **Then** artifacts from the originating thread (`Artifact.thread_id == context.thread_id`) are prioritized (listed first and pre-selected)
- **And** the user can confirm or adjust the selected scripts **before** execution runs (full-stack input-selection panel; deselect/select then Confirm)
- **And** execution does not start until the user confirms the input set

### AC3 — Block when nothing is approved

- **Given** no approved script artifact is available for the project
- **When** Jack is asked to run tests
- **Then** Jack blocks execution (**no** PROCESSING transition, **no** execution, **no** runner invocation) and stays START (re-submittable)
- **And** explains in a UX-DR12 *What happened / Why / What to do* message that **Sarah generation and approval must happen first**

---

## ⚠️ CRITICAL: Jack is a BRAND-NEW agent — 14.1 creates the skeleton + the input-selection gate ONLY

Unlike Story 13.1 (where Sarah already existed from Epic 5 and 13.1 inserted a gate **in front** of an existing generation flow), **`JackAgent` does not exist yet.** The codebase has only `AliceAgent`, `BobAgent`, `MaryAgent`, `SarahAgent` ([agents/\_\_init\_\_.py:7-13](src/ai_qa/agents/__init__.py:7)). 14.1 must **create `src/ai_qa/agents/jack.py`** and wire it into the registry — but it implements **only the input-selection gate**. The actual Playwright execution runner is **Story 14.2**; output paths 14.3; multi-browser 14.4; report generation 14.5; report review UX 14.6.

**What is ALREADY wired for Jack (do NOT recreate — reuse):**

| Surface | Where | Status |
| --- | --- | --- |
| `AgentMessage.agent_name` Literal includes `"Jack"` | [models.py:97](src/ai_qa/models.py:97) | ✅ backend message model accepts Jack |
| WebSocket navigate step→agent map `5: "Jack"` | [websocket.py:356-362](src/ai_qa/api/websocket.py:356) | ✅ Sarah→Jack navigate needs no backend change |
| `register_agent` enforces `1 <= step_number <= 5` (Jack=5 is valid) | [routes.py:304-305](src/ai_qa/api/routes.py:304) | ✅ registry accepts step 5 |
| Frontend `AGENTS.Jack` (`stepNumber: 5`, `stepTitle: "Test Execution"`, `color: "#F97316"`, `avatar: "J"`) | [pipeline.ts:229-236](frontend/src/types/pipeline.ts:229) | ✅ agent metadata exists |
| Frontend `AgentName` union includes `"Jack"` | [pipeline.ts:5](frontend/src/types/pipeline.ts:5) | ✅ |
| Frontend step→agent routing `5: "Jack"` | [usePipelineState.ts:54-60](frontend/src/hooks/usePipelineState.ts:54) | ✅ any Jack message auto-routes UI to step 5 |
| Planned location `src/ai_qa/agents/jack.py` + `tests/test_agents/test_jack.py` | [architecture.md:641,830](_bmad-output/planning-artifacts/architecture.md:641) | 📋 to create |

**What is MISSING (14.1 builds):** the `JackAgent` class, its registration in [app.py:135-140](src/ai_qa/api/app.py:135) + [agents/\_\_init\_\_.py](src/ai_qa/agents/__init__.py), the `load_approved_scripts()` adapter loader, and the **entire** frontend Jack handler/state/render layer (`jackState`, `handleJackMessage`, `handleJackConfirm`, the step-5 render block, the Sarah→Jack navigate button, Jack auto-start) + the `JackInputSelection.tsx` component + the `ScriptInput` TS type. **No backend route/schema/WS-action change** — the selection payload rides `send_message` metadata; confirm rides the existing `approve`/`data` channel; Sarah→Jack uses the existing navigate handler.

> Reconcile every cited `file:line` / snippet against live code and treat them as **leads to verify**, not gospel — record divergences in Completion Notes (per [verify-subagent-claims](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\verify-subagent-claims.md) and [create-story-snippet-hazards](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\create-story-snippet-hazards.md)).

---

## ⚠️ Sequencing dependency (READ FIRST)

**Epic 13 (Sarah, incl. 13.8 the script-save story) is `done`** ([sprint-status.yaml](_bmad-output/implementation-artifacts/sprint-status.yaml) — `epic-13: done`). The producer side is live: `PipelineArtifactAdapter.save_script` is idempotent-by-name, `kind="playwright_script"` → `test_scripts/`, and the structural approved-only guarantee holds. **Verify present in the live tree** before relying on it (do NOT re-implement Epic 13):

1. **`PipelineArtifactAdapter.save_script` (the producer)** — idempotent-by-name, `kind="playwright_script"`, runs only on approve ([artifact_adapter.py:226-269](src/ai_qa/pipelines/artifact_adapter.py:226)). Confirmed live.
2. **`PipelineArtifactAdapter.load_scripts()`** — `_load_text_artifacts(kind="playwright_script")`, project-scoped, no thread ordering ([artifact_adapter.py:271-273](src/ai_qa/pipelines/artifact_adapter.py:271)). 14.1 adds `load_approved_scripts()` (thread-prioritized) **alongside** it.
3. **`load_approved_test_cases()`** — the exact thread-prioritization template to mirror ([artifact_adapter.py:202-224](src/ai_qa/pipelines/artifact_adapter.py:202)).
4. **Sarah's input-selection gate** — the literal lifecycle template (`_check_preconditions` / `handle_start` override / `_present_test_case_selection` / phase-dispatched `handle_approve` / `_confirm_inputs`) at [sarah.py:617-905, 943-952](src/ai_qa/agents/sarah.py:617). 14.1 re-applies the **shape** for Jack, with scripts (raw `.py` text) instead of test cases (JSON), and an **execution** handoff (stub for 14.2) instead of a generation tail.

If any of the above is unexpectedly absent, **flag and stop** rather than re-implementing upstream.

---

## Scope decisions (defaults chosen from code + ACs + the 13.1 precedent — confirm or correct via Saved Questions)

- **Decision #1 — AC2 delivery = full-stack rich (mirror 13.1).** Build `frontend/src/components/agents/JackInputSelection.tsx` (sibling to `SarahInputSelection.tsx`) + the full step-5 Jack surface (`isJackStep`/`jackState`/`handleJackMessage`/render/confirm) + the Sarah→Jack "Proceed to Jack" navigate button + Jack auto-start. NOT backend-only. The frontend `AGENTS`/step-maps already know Jack, but there are **zero** Jack handlers/state/render today.
- **Decision #2 — Post-confirm handoff = a documented STUB seam for 14.2 (RECOMMENDED).** After the user confirms the script selection, `_confirm_inputs` stores `self.confirmed_scripts`, sets `self.phase = "execution"`, and calls `_begin_execution()`. **In 14.1, `_begin_execution()` is a stub** that sends a success/info message ("✓ N approved script(s) selected and queued for execution.") and transitions to **DONE** — it does **not** run Playwright (no runner exists until 14.2). 14.2 replaces the stub body with the real runner (PROCESSING → execute → REVIEW_REQUEST/COMPLETED). `process()` (required by the `BaseAgent` ABC) is the 14.2 execution entry point; in 14.1 it returns a placeholder `StageResult` and is **not** on the happy path. (See Saved Q#1 — alternative is to leave Jack in REVIEW_REQUEST awaiting a 14.2 "Run" action.)
- **Decision #3 — `load_approved_scripts` filter = NONE (structural).** Unlike `load_approved_test_cases` (which filters `source_type != "draft"` because Mary streams drafts — [artifact_adapter.py:202-224](src/ai_qa/pipelines/artifact_adapter.py:202)), **scripts have no draft**: every `playwright_script` artifact is approved by construction (13.8). So `load_approved_scripts` = `load_scripts()` + thread-prioritization, **no** discriminator. It is effectively a thread-prioritized `load_scripts()`.
- **Decision #4 — Jack needs NO LLM for 14.1.** Input selection lists artifacts; execution (14.2) runs pre-generated Playwright scripts. Do **NOT** call `get_llm_config()` in `JackAgent.__init__` (Sarah does, for its ScriptGenerator — Jack has none). Keep `__init__` minimal: state fields only. (Failure-analysis/backlog LLM use, if ever, is a later epic — out of scope.)
- **Decision #5 — E2E coverage = scoped to the AC3 block path (mirror 13.1).** Backend pytest is the guardrail + Vitest for the panel. A full navigate→select→confirm→execute E2E needs approved scripts seeded *and* a runner (14.2) + a reachable app — not 14.1-reproducible (`page.route` mocking is forbidden — [project-context.md#Testing-Rules](project-context.md)). Default: if approved scripts can be seeded via the artifact API, cover navigate-to-Jack → selection panel lists the seeded script with the thread badge → Confirm → assert the flow reaches the "queued for execution" / DONE state; otherwise scope to the **AC3 block path** (no approved scripts → blocking message) and note the deferral in Completion Notes.
- **Out of scope for 14.1:** the Playwright execution runner / `script_runner.py` (14.2), configurable output paths (14.3), multi-browser (14.4), report generation (14.5), report review UX (14.6). Do **not** build any execution, browser-launch, or report logic here — only the gate.

## What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status / action |
| --- | --- | --- |
| `kind="playwright_script"` → storage key `projects/{id}/test_scripts/{artifact_id}/v{version}/{name}` | [storage.py:34-35](src/ai_qa/artifacts/storage.py:34) | ✅ AC1 path already correct; no storage change |
| `kind in ("testscript","playwright_script")` → browse folder `test_scripts` | [storage.py:66-67](src/ai_qa/artifacts/storage.py:66) | ✅ tree/UI folder already correct |
| `PipelineArtifactAdapter.load_scripts()` → `_load_text_artifacts(kind="playwright_script")` (project-scoped, no workspace path, no thread order) | [artifact_adapter.py:271-273](src/ai_qa/pipelines/artifact_adapter.py:271) | ✅ **keep it**; 14.1 adds `load_approved_scripts()` (thread-prioritized) alongside |
| `PipelineArtifactAdapter.load_approved_test_cases()` (thread-prioritized loader — the template) | [artifact_adapter.py:202-224](src/ai_qa/pipelines/artifact_adapter.py:202) | ✅ **mirror exactly**, minus the `source_type != "draft"` filter |
| `PipelineArtifact` DTO (carries `id`/`name`/`kind`/`content`/`version`/`thread_id`) | [artifact_adapter.py:18-30](src/ai_qa/pipelines/artifact_adapter.py:18) | ✅ already has `thread_id` — no DTO change |
| `ArtifactService.list_artifacts(*, project_id, kind=None)` (project-scoped, ordered by name) + `read_current_content` | [service.py:194-201,236-238](src/ai_qa/artifacts/service.py:194) | ✅ partition/sort current-thread-first in Python (stable sort) |
| `PipelineArtifactAdapter.load_metadata(name)` → side-car dict (test_case_title/confidence/etc., 13.8) | [artifact_adapter.py:308-317](src/ai_qa/pipelines/artifact_adapter.py:308) | ✅ **optional** enrichment for the panel preview/title (degrade gracefully if absent) |
| `BaseAgent` lifecycle (`handle_start`/`handle_approve`/`transition_to`/`send_message`/`_format_error_message`) | [base.py:212-413](src/ai_qa/agents/base.py:212) | ✅ subclass it; override `handle_start`/`handle_approve` like Sarah |
| `AgentState` incl. `DONE`/`COMPLETED`/`REVIEW_REQUEST`/`ERROR` (note: step-5 Jack uses `COMPLETED` as the whole-pipeline terminal) | [base.py:32-44](src/ai_qa/agents/base.py:32) | ✅ reuse |
| Sarah precondition gate + AC3 block + selection-present + phase-dispatch (the literal template) | [sarah.py:617-905, 943-952](src/ai_qa/agents/sarah.py:617) | ✅ **mirror** for Jack (scripts, not test cases) |
| `register_agent(...)` + `_clone_agent_for_workspace` (constructs `agent_class()` with **no args**) | [routes.py:74-84, 293-314](src/ai_qa/api/routes.py:74) | ✅ Jack `__init__` must take all-default args (like Sarah); register in app.py |
| Agent registration block (`register_agent(AliceAgent())` …) | [app.py:135-140](src/ai_qa/api/app.py:135) | ⚠️ **add** `register_agent(JackAgent())` |
| WebSocket dispatch: `approve`→`handle_approve(data)` with `data` passthrough; navigate map step 5 → "Jack" | [websocket.py:312-322, 356-362](src/ai_qa/api/websocket.py:312) | ✅ confirm rides existing `data`; navigate needs **no** change |
| `SarahInputSelection.tsx` (checkbox list + thread/confidence badges + source link + preview + Confirm) | [SarahInputSelection.tsx](frontend/src/components/agents/SarahInputSelection.tsx) | ✅ **mirror** as `JackInputSelection.tsx` (scripts; "Confirm & Run") |
| `TestCaseInput` TS payload type (the panel entry shape) | [testcase.ts:103-114](frontend/src/types/testcase.ts:103) | ✅ **mirror** as `ScriptInput` in a new `frontend/src/types/script.ts` (or `pipeline.ts`) |
| App.tsx Sarah wiring: `isSarahStep`/`sarahState`/`handleSarahMessage`/`handleSarahConfirm`/render/auto-start/reset | [App.tsx:571,573-583,1006-1051,1242-1253,2444-2467,1174-1192,699,724-730](frontend/src/App.tsx:571) | ✅ **mirror** all for Jack (step 5) |
| Mary→Sarah "Proceed to Sarah" navigate button (the navigate-button template) | [App.tsx:2497-2535](frontend/src/App.tsx:2497) | ✅ **mirror** as Sarah→Jack "Proceed to Jack" (`step: 5`, `agentName: "Jack"`) |

---

## Tasks / Subtasks

- [x] **Task 1 — Adapter: `load_approved_scripts()` (AC1, AC2)**
  - [x] Add `load_approved_scripts(self) -> list[PipelineArtifact]` to `PipelineArtifactAdapter`, **alongside** (not replacing) `load_scripts()`. Mirror `load_approved_test_cases` ([artifact_adapter.py:202-224](src/ai_qa/pipelines/artifact_adapter.py:202)) **minus the `source_type != "draft"` filter** — scripts have no draft (Decision #3). Implementation: take `self._load_text_artifacts(kind="playwright_script")`, then partition into current-thread (`art.thread_id == self.context.thread_id`, only when `ctx_thread_id is not None`) and other, return `current_thread + other` (stable; `list_artifacts` already name-orders within each group).
  - [x] Docstring must state the structural approved-only contract (every `playwright_script` artifact is approved by construction — 13.8) and the thread-prioritization semantics. Do **not** add a discriminator filter.
  - [x] Do **not** remove or alter `load_scripts()` (other callers / future code may use it).

- [x] **Task 2 — Create `JackAgent` skeleton (AC1, AC3)** — new file `src/ai_qa/agents/jack.py`
  - [x] `class JackAgent(BaseAgent)` with `__init__(self, name: str = "Jack", color: str = "#F97316", step_number: int = 5, step_title: str = "Run Tests", workspace_dir: Path | None = None)` calling `super().__init__(...)`. **All-default args** (so `_clone_agent_for_workspace`'s `agent_class()` works — [routes.py:79-84](src/ai_qa/api/routes.py:79)). Match the frontend `AGENTS.Jack.color` (`#F97316`) and a `step_title` consistent with the UI ("Test Execution" is the FE `stepTitle`; the backend label is display-only).
  - [x] `__init__` state (mirror Sarah's input-selection state, [sarah.py:103-112](src/ai_qa/agents/sarah.py:103)): `self.phase: str = "input_selection"`, `self.candidate_scripts: list[PipelineArtifact] = []`, `self.confirmed_scripts: list[PipelineArtifact] = []`. **Do NOT** call `get_llm_config()` or construct any generator/runner (Decision #4).
  - [x] `_check_preconditions(self) -> list[str]` — mirror [sarah.py:617-624](src/ai_qa/agents/sarah.py:617): require `project_context` with non-None `project_id`/`user_id`/`thread_id` and a non-None `artifact_service`; blocker message "Start Jack from inside an active project thread." / storage-unavailable. Jack needs **no** MCP/provider/browser check to *list* scripts.
  - [x] `_format_no_scripts_message(self) -> str` — AC3 UX-DR12: *What happened* = "Jack cannot run tests yet."; *Why* = "No approved test scripts were found for this project."; *What to do* = "Run Sarah to generate Playwright scripts from approved test cases and approve at least one script, then start Jack again."
  - [x] Implement `process(self, input_data, feedback=None) -> StageResult` to satisfy the ABC. **14.1 placeholder** (not on the happy path; 14.2 fills it): return `StageResult(success=True, data={"selected_scripts": [str(a.id) for a in self.confirmed_scripts], "note": "Execution runner — Story 14.2"})`. Add a `# Story 14.2: implement the Playwright execution runner here.` marker.

- [x] **Task 3 — Jack lifecycle: input-selection gate (AC1, AC2, AC3)** — in `jack.py`
  - [x] **Override `handle_start`** mirroring [sarah.py:825-905](src/ai_qa/agents/sarah.py:825) but simpler (no chrome/url inputs):
    1. Reset per-run state: `self.phase = "input_selection"`, `self.confirmed_scripts = []`, `self.candidate_scripts = []`.
    2. `blockers = self._check_preconditions()`; for each blocker `send_message(self._format_error_message([msg]), message_type="error")`; if `blockers` → `return` (stay START).
    3. `if self.project_context is None: return`. Load `candidates = PipelineArtifactAdapter(self.project_context).load_approved_scripts()`.
    4. **AC3 block:** `if not candidates:` → `send_message(self._format_no_scripts_message(), message_type="error")` and `return` (stay START; **no** PROCESSING, **no** execution).
    5. `self.candidate_scripts = candidates`; `await self.transition_to(AgentState.REVIEW_REQUEST)`; `await self._present_script_selection()`.
  - [x] Implement `_present_script_selection(self)` — mirror [sarah.py:639-676](src/ai_qa/agents/sarah.py:639). Compute `any_from_thread`; for each candidate emit an entry: `{ "artifact_id": str(a.id), "name": a.name, "title": <a.name without ".py">, "from_current_thread": <a.thread_id is not None and == ctx.thread_id>, "default_selected": <from_thread or not any_from_thread>, "preview": <first ~20 lines of a.content, or a side-car-derived summary> }`. **Optional enrichment:** call `adapter.load_metadata(f"{stem}.metadata.json")` to surface `test_case_title`/`confidence` — wrap in `getattr`/`None`-tolerant access so the panel degrades if the side-car is missing (don't hard-fail). `send_message(content="Please select which approved scripts to run.", message_type="text", metadata={"type": "script_selection", "is_input_selection": True, "scripts": entries})`.
  - [x] **Phase-dispatch `handle_approve`** mirroring [sarah.py:943-952](src/ai_qa/agents/sarah.py:943): `if self.phase == "input_selection": await self._confirm_inputs(data); return` — else fall through (no other phase exists in 14.1; 14.2 may add an execution-review branch).
  - [x] Implement `_confirm_inputs(self, data)` — mirror [sarah.py:678-726](src/ai_qa/agents/sarah.py:678): read `selected_artifact_ids` from `data` (default = all candidates if absent/empty); filter `self.candidate_scripts` to the selected set; if empty → `send_message("Please select at least one script before confirming.", message_type="warning")` + re-present + `return`. Else set `self.confirmed_scripts = filtered`, `self.phase = "execution"`, and `await self._begin_execution()`.
  - [x] Implement `_begin_execution(self)` — **14.1 STUB** (Decision #2): `await self.transition_to(AgentState.DONE)`; `await self.send_message(f"✓ {len(self.confirmed_scripts)} approved script(s) selected and queued for execution.", message_type="success")`. Add a `# Story 14.2: replace this stub with the Playwright runner (PROCESSING → execute → report).` marker. Do **not** run Playwright, launch a browser, or read script bytes for execution here.

- [x] **Task 4 — Register Jack (AC1)**
  - [x] [agents/\_\_init\_\_.py](src/ai_qa/agents/__init__.py): `from ai_qa.agents.jack import JackAgent` and add `"JackAgent"` to `__all__`.
  - [x] [app.py:135-140](src/ai_qa/api/app.py:135): add `JackAgent` to the lazy import and `register_agent(JackAgent())` after `register_agent(SarahAgent())`.
  - [x] Verify the WS dispatch path (`_handle_action` → `_agent_for_context(5, ...)` → `_get_agent_for_project`/`_clone_agent_for_workspace`) resolves a Jack instance for step 5 (it returns `None` and logs "No agent registered for step 5" until registered).

- [x] **Task 5 — Frontend: `JackInputSelection.tsx` + `ScriptInput` type (AC2)**
  - [x] Create `frontend/src/components/agents/JackInputSelection.tsx` mirroring `SarahInputSelection.tsx`. Props: `{ scripts: ScriptInput[]; onConfirm: (selectedIds: string[]) => void; disabled?: boolean }`. Render: header ("Select scripts to run" + current-thread count + All/None), a checkbox row per script (default-selected per `default_selected`, "from this conversation" badge when `from_current_thread`, optional confidence/source label, expandable preview via `ReviewContent` or a `<pre>` for the `.py` snippet), and a **"Confirm & Run"** button (disabled when zero selected) calling `onConfirm(Array.from(selected))`. Accessible names per project rules (checkbox labels; `getByRole`).
  - [x] Add a `ScriptInput` interface — mirror `TestCaseInput` ([testcase.ts:103-114](frontend/src/types/testcase.ts:103)) — **matching the backend `script_selection` payload exactly** (full-stack sync). Put it in a new `frontend/src/types/script.ts` (or extend `pipeline.ts`). Shape: `{ artifact_id: string; name: string; title: string; from_current_thread: boolean; default_selected: boolean; preview?: string | null; source_test_case_title?: string | null; confidence?: number | null }` — include only the fields the backend actually emits.

- [x] **Task 6 — Frontend: step-5 Jack surface + Sarah→Jack navigate + Jack auto-start (AC2 prerequisites)** — in [App.tsx](frontend/src/App.tsx)
  - [x] Add `const isJackStep = currentStep === 5;` (mirror `isSarahStep` [App.tsx:571](frontend/src/App.tsx:571)).
  - [x] Add `jackState` + `setJackState` (e.g. `{ scripts: ScriptInput[] | null }`) mirroring `sarahState` ([App.tsx:573-583](frontend/src/App.tsx:573)). Reset it in the thread-switch effect ([App.tsx:724-730](frontend/src/App.tsx:724)).
  - [x] Add `handleJackMessage` (gated on `message.agentName === "Jack"`) capturing `metadata.type === "script_selection"` → `setJackState({ scripts })`, mirroring `handleSarahMessage` ([App.tsx:1006-1051](frontend/src/App.tsx:1006)). **Register it in BOTH** the live-queue effect (next to `handleSarahMessage(msg)` ~[App.tsx:1063](frontend/src/App.tsx:1063)) **and** the history-restore effect (~[App.tsx:1097](frontend/src/App.tsx:1097)), and add it to both effects' dependency arrays.
  - [x] Add `handleJackConfirm(selectedIds)` → `sendMessage({ type: "approve", step: 5, data: { action: "confirm_inputs", selected_artifact_ids: selectedIds } })` (mirror `handleSarahConfirm` [App.tsx:1242-1253](frontend/src/App.tsx:1242)).
  - [x] Render `<JackInputSelection>` when `isJackStep && status === "review_request" && jackState.scripts?.length` (mirror the Sarah block [App.tsx:2444-2467](frontend/src/App.tsx:2444); use `AGENTS.Jack.color` `#F97316` for the label).
  - [x] **Sarah→Jack navigate:** add a "Proceed to Jack →" button shown when `isSarahStep && (status === "completed" || status === "done")`, sending `{ type: "navigate", step: 5, direction: "next", agentName: "Jack", sender: "user", content: "Navigate to Jack", messageType: "info" }` (mirror the Mary→Sarah button [App.tsx:2497-2535](frontend/src/App.tsx:2497)).
  - [x] **Jack auto-start:** add `hasSentJackStartRef = useRef(false)` (next to `hasSentSarahStartRef` ~[App.tsx:633](frontend/src/App.tsx:633)); reset it in the thread-switch effect (~[App.tsx:699](frontend/src/App.tsx:699)); add an effect that sends `{ type: "start", step: 5, inputData: {} }` when `isConnected && currentStep === 5 && status === "start" && threadId && !hasSentJackStartRef.current` (mirror Sarah auto-start [App.tsx:1174-1192](frontend/src/App.tsx:1174)). Jack needs no user input to list approved scripts.

- [x] **Task 7 — Backend tests (AC1, AC2, AC3)**
  - [x] Adapter test in [tests/pipelines/test_pipeline_artifact_adapter.py](tests/pipelines/test_pipeline_artifact_adapter.py) (real `ArtifactService` + in-memory SQLite; copy the `load_approved_test_cases` scaffold): `load_approved_scripts` is project-scoped (other project → `[]`), returns **all** `kind="playwright_script"` rows (no discriminator), and orders current-thread rows first. Seed via `adapter.save_script("test_a.py", "...")` across two threads + a second project.
  - [x] Jack tests in new `tests/test_agents/test_jack.py` (mirror the Sarah input-selection tests; patch `ai_qa.agents.jack.PipelineArtifactAdapter`; use `mock_project_context` + `mock_broadcast`):
    - `handle_start` with **no** approved scripts → AC3 error message sent, stays START, **no** REVIEW_REQUEST, no execution.
    - `handle_start` **with** approved scripts → emits `script_selection` payload, transitions to REVIEW_REQUEST; thread-prioritized ordering + pre-selection reflected in the payload entries.
    - `handle_approve({action:"confirm_inputs", selected_artifact_ids:[...]})` in `phase=="input_selection"` → sets `confirmed_scripts` to the selected subset and reaches the `_begin_execution` stub (assert DONE transition + the "queued for execution" success message; assert the confirmed set = the selected subset only).
    - `_check_preconditions` returns a blocker when `project_context`/`thread_id`/`artifact_service` is missing.
  - [x] **Conftest hazard:** `mock_project_context` ([tests/conftest.py](tests/conftest.py)) is a `MagicMock(spec=PipelineContext)` whose `project_id`/`thread_id` resolve to truthy auto-child mocks (not `None`), so an `is not None` precondition passes. For empty-vs-populated load tests, patch `PipelineArtifactAdapter.load_approved_scripts` on the patched adapter (as the Sarah tests patch the adapter). Fix any shared-fixture break **centrally** in conftest ([agent-gate-conftest-regression](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\agent-gate-conftest-regression.md)).

- [x] **Task 8 — Frontend tests (AC2)**
  - [x] Vitest `frontend/src/components/__tests__/JackInputSelection.test.tsx` (mirror `SarahInputSelection.test.tsx`): renders candidates, default selection honored, deselect/select adjusts, thread-origin badge, preview toggle, Confirm disabled at zero-selected, Confirm emits the selected ids. Vitest 4 rules — [project-context.md#Testing-Rules](project-context.md) (`vi.mock` hoisted file-wide; prefer `vi.spyOn(globalThis,"fetch")`; `importOriginal()` to preserve real exports).
  - [x] Optional App-level test: a `script_selection` message → `JackInputSelection` render path; confirm → `approve` step-5 send with `selected_artifact_ids`.
  - [x] Playwright E2E (`frontend/e2e/`, scoped per Decision #5): if approved scripts can be seeded via the artifact API, cover navigate-to-Jack → selection panel lists the seeded script with the thread badge → Confirm → assert it reaches the "queued for execution"/DONE state; **else** scope to the AC3 block path (no approved scripts → blocking message) — note the deferral in Completion Notes. Real-API state prep + `afterEach` cleanup of users/projects/artifacts; no `page.route`, no `waitForTimeout`.

- [x] **Task 9 — Verify (no migration needed)**
  - [x] Backend: `uv run pytest --no-cov` (**whole** suite — the coverage gate fails on subset runs; see [backend-test-suite-orphaned-legacy-tests](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\backend-test-suite-orphaned-legacy-tests.md)). `uv run mypy src` clean. **Pyrefly-clean** (see Library constraints below).
  - [x] Frontend: `npm run lint`, `npm run typecheck`, `npm run test` (Vitest), and the new E2E spec.
  - [x] Confirm **no Alembic migration** — `kind="playwright_script"` → `test_scripts/` mapping already exists; scripts persist as raw text (no DB table change); `Artifact.thread_id` already exists. State explicitly in Completion Notes.

## Dev Notes

### Jack lifecycle after 14.1 (one pre-execution gate)

```
handle_start
  → reset per-run state (phase=input_selection, confirmed/candidate cleared)
  → _check_preconditions()                  (project context)            [AC3 gate #0]
  → load_approved_scripts()                 (project-scoped, thread-first) [AC1/AC2]
      → [] → AC3 block message, stay START                                [AC3]
      → present script_selection (REVIEW_REQUEST, phase=input_selection)  [AC2]

handle_approve (phase dispatch)
  → phase == "input_selection" → _confirm_inputs(data)
        → confirmed_scripts = selected subset                            [AC1/AC2]
        → phase = "execution"
        → _begin_execution():   [14.1 STUB] DONE + "queued for execution"
                                [14.2] PROCESSING → run Playwright → report
```

This is the **same two-helper shape** as Sarah's `_confirm_inputs` → `_begin_generation`, with execution swapped for generation. Keep `_begin_execution` a clean seam so 14.2 only replaces its body.

### Why no approved/draft discriminator (the load-bearing fact, restated for scripts)

`PipelineArtifactAdapter.save_script` runs **only** in Sarah's approve path — skip/reject/regenerate never call it ([artifact_adapter.py:226-269](src/ai_qa/pipelines/artifact_adapter.py:226), confirmed by Story 13.8). So **every `kind="playwright_script"` artifact under `test_scripts/` is approved by construction.** `load_approved_scripts` therefore lists `playwright_script` directly with **no** filter. Contrast `load_approved_test_cases`, which *does* filter `source_type != "draft"` because Mary streams pre-approval drafts ([artifact_adapter.py:202-224](src/ai_qa/pipelines/artifact_adapter.py:202)) — scripts have **no** draft. AC1's "rejected/draft/unapproved excluded" is satisfied **structurally**. (If a future story ever persists a pre-approval draft script, it must add a discriminator — do **not** build that here.)

### Thread prioritization & default selection (AC2)

- "Originating thread" = `Artifact.thread_id`, set by `save_script` → `save_artifact` from `context.thread_id`. Current thread = `PipelineContext.thread_id`.
- `list_artifacts` orders by name only — **no** thread ordering; partition/stable-sort in Python (current-thread group first, name order preserved within each group). Exact mirror of `load_approved_test_cases`.
- **Default selection (mirror Sarah [sarah.py:644-665](src/ai_qa/agents/sarah.py:644)):** if any approved script has `thread_id == ctx.thread_id`, pre-select those (listed first); other project-level scripts are listed below, **deselected** by default. If there are **no** current-thread scripts, pre-select **all** so the user is never stuck with an empty set. Satisfies "prioritized" (order + pre-select + badge) and "confirm or adjust".

### Script panel entry (no JSON parse needed — unlike Sarah)

A script artifact's `content` is **raw `.py` text** (not JSON), so — unlike Sarah's `_present_test_case_selection` which parses `TestCase(**json.loads(content))` — Jack builds each entry straight from the `PipelineArtifact`: `title` = `name` with the `.py` suffix stripped; `preview` = the first ~20 lines of `content` (or a side-car summary). **Optional** richer title/confidence: `adapter.load_metadata(f"{stem}.metadata.json")` returns the 13.8 side-car (`test_case_title`, `confidence`, `source_test_case_id`, …) — surface `test_case_title`/`confidence` if present, degrade to `None` if not. Do **not** make the panel hard-depend on the side-car (an older script may lack one).

### Agent registration & per-step instancing (don't get surprised)

- Agents are **module-level templates** registered at startup via `register_agent(JackAgent())` → `_active_agents[5]` ([routes.py:293-314](src/ai_qa/api/routes.py:293), [app.py:135-140](src/ai_qa/api/app.py:135)). Per request, `_get_agent_for_project` **clones** the template via `_clone_agent_for_workspace` → `agent_class()` (no args) and keys it by `(user_id, project_id, step)` ([routes.py:74-124](src/ai_qa/api/routes.py:74)). → **`JackAgent.__init__` MUST accept zero positional args** (all defaults), exactly like Sarah.
- Until `register_agent(JackAgent())` is added, step-5 actions log "No agent registered for step 5" and silently no-op ([websocket.py:308-310](src/ai_qa/api/websocket.py:308)). The frontend navigate/auto-start will fire but nothing answers — so Task 4 (registration) is what makes the gate live.
- `set_project_context` triggers `_load_agent_config` (reads `thread.provider_name` / `thread.agent_configs`) — harmless for Jack (it has no LLM config to apply in 14.1). No change needed.

### `process()` is required by the ABC but off the 14.1 happy path

`BaseAgent.process` is `@abstractmethod` ([base.py:279-301](src/ai_qa/agents/base.py:279)) — `JackAgent` won't instantiate without it. 14.1's flow (`handle_start` → present → `handle_approve` → `_confirm_inputs` → `_begin_execution` stub) never calls `process`. Provide a minimal placeholder `StageResult` (Decision #2 / Task 2) and let 14.2 implement the real runner there (or in `_begin_execution`, whichever 14.2 chooses). Don't raise `NotImplementedError` (a stray base-class `handle_start`/`handle_reject` path could surface it as an ERROR) — return a benign success placeholder.

### Architecture compliance (hard rules)

- **Agents never read/write storage directly — always through the artifact service** ([architecture.md:518](_bmad-output/planning-artifacts/architecture.md:518), forbidden anti-pattern [:533](_bmad-output/planning-artifacts/architecture.md:533)). Jack lists/reads scripts only via `PipelineArtifactAdapter`/`ArtifactService`; no `workspace/...` path. The architecture's Jack flow is `jack.py → read scripts via artifact service → script_runner.py → execution report` ([architecture.md:830-834](_bmad-output/planning-artifacts/architecture.md:830)) — 14.1 implements the "read scripts via artifact service" leg; `script_runner.py` is 14.2.
- **Mandatory human review at every step — no auto-advance through a Review Request** ([architecture.md:271-272](_bmad-output/planning-artifacts/architecture.md:271)). The input-selection confirm IS the review gate; do not auto-confirm or auto-run.
- **No credential/secret leakage:** the `script_selection` payload + panel carry only artifact ids, script names, titles, previews (script source text — already scrubbed of secrets by Sarah's 13.4 generation), thread-origin flags, and optional confidence — **never** tokens, cookies, session blobs, or config dicts. The leak-canary convention applies.
- **Backend payload/model change → update the matching TS interface in the same change** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)) and `npm run build`/`typecheck`. The `script_selection` payload ↔ `ScriptInput` must stay in sync.
- **Artifacts are project-scoped** under `projects/{project_id}/test_scripts/` ([architecture.md:280](_bmad-output/planning-artifacts/architecture.md:280)).

### Library / framework constraints (from project-context.md)

- **Backend:** Python ≥3.14, `uv` only (`uv run`, never `pip`/`python3`). Ruff + Mypy strict (`uv run mypy src`). **Pyrefly-clean:** narrow `Optional` before use (`self.project_context`, `ctx.project_id`, `ctx.thread_id`, `data.get("selected_artifact_ids")`); only `str(artifact.id)` (a `UUID`) needs conversion — don't `str()` a value already `str`; no redundant casts; no bare `except` where a specific type fits; `pytest.raises` needs a specific type + `match=`. The artifact path is a **sync** `Session`. When mocking `mock.call_args`/`await_args` in tests, bind + assert not-None before reading `.args`/`.kwargs`.
- **Frontend:** React 19.2, TS ~6.0 strict, Tailwind v4, Vitest 4, ESLint 9. Path alias `@` → `./src`. Strict null/index access — non-null-assert known array elements (`mock.calls[0]![0]`). Playwright: `getByRole`/`getByText`; checkbox controls need accessible names; no `page.route`, no `waitForTimeout`.
- **No new packages. No Alembic migration** (existing kind mapping + `thread_id` column; scripts are raw-text artifacts).

### Forward-compat note (not 14.1 scope)

A multi-epic **Project-Admin RBAC redesign** is awaiting sign-off ([design-projectadmin-rbac-redesign-2026-06-21.md](_bmad-output/planning-artifacts/design-projectadmin-rbac-redesign-2026-06-21.md)) that would later make Jack **role-aware** (role-grouped scripts) and **multi-browser** (multi-browser is independently Story 14.4). 14.1 stays **role-agnostic** — keep `load_approved_scripts` + `JackInputSelection` generic (filtered + thread-prioritized load → selection panel → confirm) so a future role grouping can layer on without rework. Don't build role logic here.

### Project Structure Notes

- **New files:** `src/ai_qa/agents/jack.py`, `tests/test_agents/test_jack.py`, `frontend/src/components/agents/JackInputSelection.tsx`, `frontend/src/components/__tests__/JackInputSelection.test.tsx`, `frontend/src/types/script.ts` (or extend `pipeline.ts`), a Playwright spec under `frontend/e2e/` (e.g. `epic-14.spec.ts`).
- **Modified files (expected):** `src/ai_qa/pipelines/artifact_adapter.py` (add `load_approved_scripts`), `src/ai_qa/agents/__init__.py` (export `JackAgent`), `src/ai_qa/api/app.py` (register Jack), `frontend/src/App.tsx` (isJackStep + jackState + handleJackMessage + render + confirm + Sarah→Jack navigate + Jack auto-start + thread reset), `tests/pipelines/test_pipeline_artifact_adapter.py`, possibly `tests/conftest.py`.
- **No backend route/schema change, no new WS action:** the selection payload rides the existing `send_message` metadata channel; confirm rides the existing `approve`/`data` channel; Sarah→Jack uses the existing navigate handler ([websocket.py:356-362](src/ai_qa/api/websocket.py:356)).

### Testing standards summary

- Backend agent: `@pytest.mark.asyncio`; patch `ai_qa.agents.jack.PipelineArtifactAdapter` at the class boundary; use `mock_project_context` + `mock_broadcast` (mirror the Sarah scaffold in [tests/test_agents/test_sarah.py](tests/test_agents/test_sarah.py)). Set `mock_adapter.load_approved_scripts.return_value` to drive AC2/AC3.
- Adapter: real `ArtifactService` over in-memory SQLite (copy `tests/pipelines/test_pipeline_artifact_adapter.py`'s `load_approved_test_cases` test). Assert project isolation, all-rows-returned (no discriminator), thread-first ordering.
- Run the **whole** suite with `--no-cov` (subset runs trip the coverage gate). Mypy gate is `src` only.
- Frontend: Vitest for the component; Playwright E2E with real-API state prep + `afterEach` cleanup, scoped per Decision #5.

### Previous-story / sibling intelligence

- **Story 13.1 (Sarah input selection, `done`)** — the **direct analog** and literal template: precondition gate, `handle_start` override with AC3 block, `_present_*_selection` payload, phase-dispatched `handle_approve`, `_confirm_inputs`, the `XInputSelection.tsx` panel, App.tsx per-agent state/handler/render/confirm, and the predecessor→agent navigate + auto-start. 14.1 re-applies all of it for Jack. **Key differences:** (a) Jack is a *new* agent (create the class + register it); (b) scripts are raw text (no JSON parse, no draft filter); (c) the post-confirm tail is an *execution* stub (14.2), not an existing generation flow.
- **Story 13.8 (Test Script Artifact Save, `done`)** — the **producer**. It made `save_script` idempotent-by-name + approved-only and **explicitly reserved** `load_approved_scripts` + the "only approved is structural" guarantee for **this** story (then numbered 15.1). 14.1 consumes that surface; it adds **no** producer-side change.
- **Story 12.1 (Mary input selection)** — the original of the pattern (requirements). 13.1's Dev Notes flagged 14.1 as "the third instance" and asked that the loader/panel stay generic — honored here.
- **Epic 14 stories 14.2–14.6** — 14.2 is the Playwright runner (`script_runner.py`, fills `_begin_execution`/`process`); 14.3 output paths; 14.4 multi-browser; 14.5 report generation; 14.6 report review UX. Keep 14.1's `_begin_execution` a clean seam.

### Git intelligence (recent work patterns)

Recent commits (`0de0b7c replan based on business value`, `4f76575 update e2e tests`, `af899de Mary change test cases from json to MD`) reflect the Epic-13-done / roadmap-reprioritization state. The whole changeset is **uncommitted on `main`** — Thuong commits + migrates himself ([git-commit-and-branch-preferences](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\git-commit-and-branch-preferences.md)); do **not** auto-commit. Closest code to copy: [sarah.py:617-952](src/ai_qa/agents/sarah.py:617) (the gate), [artifact_adapter.py:202-273](src/ai_qa/pipelines/artifact_adapter.py:202) (`load_approved_test_cases`/`load_scripts`), [SarahInputSelection.tsx](frontend/src/components/agents/SarahInputSelection.tsx) + its test, the Sarah wiring in [App.tsx](frontend/src/App.tsx), and [tests/pipelines/test_pipeline_artifact_adapter.py](tests/pipelines/test_pipeline_artifact_adapter.py).

### References

- [Source: _bmad-output/planning-artifacts/epics.md:1432-1460] — Epic 14 intro + FRs FR11/FR13/FR26 (1432-1438); Story 14.1 ACs (1440-1460); siblings 14.2 runner (1462-1482), 14.5 report (1527-1546)
- [Source: _bmad-output/planning-artifacts/architecture.md] — agent flow Alice→…→Jack (270, 301); jack.py read-scripts→script_runner→report (830-834); no-direct-storage (518, 533); mandatory review / no auto-advance (271-272); project-scoped artifacts (280); test_jack.py + agents dir (641, 711); Jack execution analysis (1169-1170); secret containment (66, 515)
- [Source: src/ai_qa/agents/sarah.py] — input-selection gate template: `__init__` state (70-122, esp. 103-112), `_check_preconditions` (617-624), `_format_no_test_cases_message` (626-633), `_present_test_case_selection` (639-676), `_confirm_inputs` (678-726), `_begin_generation` tail (754-823), `handle_start` override (825-905), phase-dispatched `handle_approve` (943-952)
- [Source: src/ai_qa/agents/base.py] — `BaseAgent` lifecycle (47-413), `AgentState` (32-44), `handle_start`/`handle_approve` (307-347), `_format_error_message` UX-DR12 (402-413), `process` abstract (279-301)
- [Source: src/ai_qa/pipelines/artifact_adapter.py] — `load_approved_test_cases` template (202-224), `load_scripts` (271-273), `save_script` structural-approved contract (226-269), `load_metadata` side-car (308-317), `PipelineArtifact` DTO incl. `thread_id` (18-30), `_load_text_artifacts`/`_to_pipeline_artifact` (394-410)
- [Source: src/ai_qa/artifacts/storage.py] — `kind="playwright_script"` → `test_scripts/` (34-35); `folder_for_kind` (66-67)
- [Source: src/ai_qa/artifacts/service.py] — `list_artifacts` (194-201), `read_current_content` (236-238)
- [Source: src/ai_qa/api/routes.py] — `_agent_for_context` (285-290), `register_agent` (293-314, step 1-5 guard 304-305), `_clone_agent_for_workspace` no-arg construction (74-84), `_get_agent_for_project` (102-124)
- [Source: src/ai_qa/api/app.py:135-140] — agent registration block (add `register_agent(JackAgent())`)
- [Source: src/ai_qa/api/websocket.py] — dispatch passing `data` to `handle_approve` (312-322), navigate step→agent map incl. `5: "Jack"` (356-362), "No agent registered" no-op (308-310)
- [Source: src/ai_qa/agents/__init__.py:7-13] — agent exports (add `JackAgent`)
- [Source: src/ai_qa/models.py:97] — `AgentMessage.agent_name` Literal includes `"Jack"`
- [Source: frontend/src/types/pipeline.ts] — `AgentName` union incl. Jack (5); `AGENTS.Jack` stepNumber 5 / color `#F97316` (229-236); Sarah entry (221-228)
- [Source: frontend/src/hooks/usePipelineState.ts:54-60] — step→agent `5: "Jack"`
- [Source: frontend/src/App.tsx] — Sarah wiring to mirror: `isSarahStep` (571), `sarahState` (573-583), `handleSarahMessage` (1006-1051) + registration (1063, 1097), `handleSarahConfirm` (1242-1253), Sarah selection render (2444-2467), Sarah auto-start + ref (1174-1192, 633), thread reset (699, 724-730), Mary→Sarah navigate button (2497-2535)
- [Source: frontend/src/components/agents/SarahInputSelection.tsx] — panel template (props, checkbox list, badges, preview, Confirm)
- [Source: frontend/src/types/testcase.ts:103-114] — `TestCaseInput` payload-type pattern to mirror as `ScriptInput`
- [Source: _bmad-output/implementation-artifacts/13-1-approved-test-case-input-selection.md] — the analog input-selection story (the entire pattern)
- [Source: _bmad-output/implementation-artifacts/13-8-test-script-artifact-save.md] — the producer; reserves `load_approved_scripts` + "only approved is structural / no discriminator" for this story
- [Source: project-context.md] — `uv`/`npm` only; Ruff + Mypy strict; Pyrefly (narrow Optional, no redundant cast); no bare except; no `# type: ignore`; full-stack sync; security (no secrets in payloads/logs); App UI English-only

## Saved Questions (for Thuong — defaults applied; confirm or correct)

1. **Post-confirm handoff (Decision #2).** After the user confirms the script selection, 14.1's default is: store the selection, send "✓ N script(s) queued for execution", and transition Jack to **DONE** (a clean stub seam that 14.2 replaces with the real runner). **Alternative:** keep Jack in **REVIEW_REQUEST** after confirm and add an explicit "Run" affordance in 14.2 (so confirm ≠ done). Default = transition to DONE. Confirm?
2. **Backend `step_title` for Jack.** Frontend `AGENTS.Jack.stepTitle` is "Test Execution"; the backend label is display-only. Default backend `step_title = "Run Tests"` (consistent with the roadmap "Run" role). Acceptable, or align to "Test Execution"?
3. **Panel preview source.** Default preview = first ~20 lines of the `.py` script content, with optional `test_case_title`/`confidence` enrichment from the 13.8 side-car when present. Acceptable, or prefer side-car title only (hide raw code in the panel)?
4. **E2E scope (Decision #5).** Default = AC3 block path (no approved scripts → blocking message) via real backend, plus the select→confirm→queued path **only if** scripts can be seeded via the artifact API. Acceptable, or require the seeded-select path?

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, bmad-dev-story workflow)

### Debug Log References

- `uv run pytest tests/test_agents/test_jack.py tests/pipelines/test_pipeline_artifact_adapter.py --no-cov` → 28 passed
- `uv run pytest --no-cov` (whole suite) → 1594 passed
- `uv run mypy src` → clean (90 files); `uv run ruff check/format` → clean
- Frontend: `npm run typecheck` + `npm run lint` clean; `npx vitest run` → 30 files / 329 passed (incl. JackInputSelection 18)

### Completion Notes List

- **All defaults applied** (Saved Questions): Q1 post-confirm → DONE stub seam; Q2 backend `step_title="Run Tests"`; Q3 preview = first 20 lines of `.py` + optional side-car `test_case_title`/`confidence`; Q4 E2E scope = AC3 block path (E2E spec deferred — see below).
- **Verified vs live code (no divergences):** Jack metadata already present in `pipeline.ts` (`AGENTS.Jack`, `AgentName`), `usePipelineState.ts` step→agent `5: "Jack"`, WS navigate map `5: "Jack"` ([websocket.py:356-362](src/ai_qa/api/websocket.py:356)), `register_agent` step-1..5 guard, `_clone_agent_for_workspace` no-arg construction. All confirmed as the story described.
- **AC1** — `load_approved_scripts()` added alongside `load_scripts()` (no discriminator — scripts are approved by construction, 13.8); thread-prioritized stable sort. Storage stays via `ArtifactService` (no workspace paths).
- **AC2** — full-stack input-selection panel: `JackInputSelection.tsx` + `ScriptInput` type + step-5 App.tsx surface (`isJackStep`/`jackState`/`handleJackMessage` dual-registered in live-queue **and** history-restore effects + dep arrays/`handleJackConfirm`/render/auto-start/thread-reset) + Sarah→Jack "Proceed to Jack" navigate button. Execution does not start until the user Confirms.
- **AC3** — no approved scripts → UX-DR12 block message, stays START (no PROCESSING/execution); precondition gate blocks when project context/thread/artifact_service is missing.
- **Decision #2 stub** — `_begin_execution` transitions to DONE + "✓ N approved script(s) selected and queued for execution." with a `# Story 14.2` marker; `process()` is a benign placeholder (off the happy path) also marked for 14.2.
- **Decision #4** — Jack `__init__` is LLM-free (no `get_llm_config`), all-default args (clone-safe).
- **No Alembic migration** — `kind="playwright_script"`→`test_scripts/` mapping + `Artifact.thread_id` already exist; scripts persist as raw text. Confirmed.
- **E2E deferral (Decision #5):** a full navigate→select→confirm E2E needs seeded approved scripts + (for the run tail) the 14.2 runner; the backend pytest (`test_jack.py`) + Vitest (`JackInputSelection.test.tsx`) cover the gate + AC3 block deterministically. A Playwright spec is deferred to the Epic 14 E2E pass (after 14.2 makes a real run possible). Noted per the story's Decision #5.
- **Secret containment** — the `script_selection` payload carries only artifact ids, names, titles, previews (already-scrubbed `.py` text), thread flags, optional confidence — no secrets.

### File List

- `src/ai_qa/pipelines/artifact_adapter.py` — add `load_approved_scripts()` (M)
- `src/ai_qa/agents/jack.py` — new `JackAgent` (input-selection gate) (A)
- `src/ai_qa/agents/__init__.py` — export `JackAgent` (M)
- `src/ai_qa/api/app.py` — register `JackAgent()` (M)
- `frontend/src/types/script.ts` — new `ScriptInput` type (A)
- `frontend/src/components/agents/JackInputSelection.tsx` — new panel (A)
- `frontend/src/App.tsx` — step-5 Jack surface + Sarah→Jack navigate (M)
- `tests/pipelines/test_pipeline_artifact_adapter.py` — `load_approved_scripts` tests (M)
- `tests/test_agents/test_jack.py` — Jack gate tests (A)
- `frontend/src/components/__tests__/JackInputSelection.test.tsx` — panel tests (A)

### Change Log

- 2026-06-21 — Story 14.1 implemented: Jack agent skeleton + approved-script input-selection gate (backend adapter loader, agent lifecycle, registration; frontend type + panel + step-5 wiring + navigate). All ACs satisfied; no migration. Status → review.
