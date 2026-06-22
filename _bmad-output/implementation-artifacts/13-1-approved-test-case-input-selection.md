---
baseline_commit: 2a1f170
---

# Story 13.1: Approved Test Case Input Selection

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want Sarah to use only approved test cases for the current project/thread for script generation, and to let me confirm or adjust which test cases feed generation,
so that generated Playwright scripts are based only on validated test design I have explicitly selected.

## Acceptance Criteria

Verbatim from [epics.md#Story-13.1](_bmad-output/planning-artifacts/epics.md) (lines 1259-1279), expanded with implementation defaults (see "Scope decisions" — **all four defaults CONFIRMED by Thuong 2026-06-13**, "làm toàn bộ theo default"; no pending input remains). This is the **test-case analog of Story 12.1** (Mary's approved-requirements input selection): same "filtered + thread-prioritized load → selection panel → confirm-before-generate" shape, one agent downstream.

### AC1 — Approved, project-scoped test cases only (no workspace paths)

- **Given** approved test case artifacts exist for the selected project
- **When** Sarah starts script generation
- **Then** Sarah loads only project-scoped **approved** test cases through the artifact service
- **And** direct workspace path reads are not used
- **And** rejected or draft test cases are excluded (see Dev Notes — "only approved" is **structural**: there is no draft test case, so no `source_type`-style discriminator is needed, unlike requirements)

### AC2 — Thread prioritization + user confirm/adjust before generation

- **Given** the current thread has approved test case artifacts
- **When** Sarah prepares generation input
- **Then** artifacts from the originating thread (`Artifact.thread_id == context.thread_id`) are prioritized (listed first and pre-selected)
- **And** the user can confirm or adjust the selected test cases **before** generation runs (full-stack input-selection panel; deselect/select then Confirm)
- **And** generation does not start until the user confirms the input set

### AC3 — Block when nothing is approved

- **Given** no approved test case artifact is available for the project
- **When** Sarah is asked to generate scripts
- **Then** Sarah blocks generation (no PROCESSING transition, no script generation, no LLM call)
- **And** explains in a UX-DR12 message that **Mary generation and approval must happen first**

---

## ⚠️ Sequencing dependency (READ FIRST — critical)

**Story 13.1 is the first story of Epic 13 (Sarah), and it consumes the output of Epic 12 (Mary). Epic 12 is NOT yet `done` — Stories 12.1–12.5 are all `ready-for-dev` and none are implemented in the working tree.** Before starting 13.1, confirm Epic 12 has landed; otherwise this story has nothing to load and several of the patterns it mirrors do not exist yet.

What 13.1 depends on from Epic 12 (verify present in the live tree; **flag and stop** if missing — do NOT re-implement Epic 12 here):

1. **12.5 (the producer).** `MaryAgent._write_approved_test_cases` writes each approved `TestCase` as a `kind="testcase"` artifact under `projects/{id}/test_cases/`, only at `DONE`, after per-item review. **Without 12.5 there are no approved test cases to select** — `load_approved_test_cases()` returns `[]` and AC3's block path is the only reachable branch.
2. **12.2/12.3/12.4 `TestCase` fields.** The selection panel displays per-case attribution + confidence. Those fields (`source_requirement_id`/`source_requirement_name`/`source_url`/`feature_area`/`warnings` from 12.2; `confidence`/`confidence_level`/`confidence_rationale` from 12.3; `approved_by`/`approved_at` from 12.4) only exist after those stories land. On the **pre-12.2** baseline, `TestCase` ([models.py:265-298](src/ai_qa/models.py:265)) has only `title`/`preconditions`/`steps`/`expected_results`/`automation_hints`/`tags` + the `filename` property — render only what exists and treat the richer fields as optional.
3. **12.1 patterns this story mirrors:** the `PipelineArtifact` DTO extended with `thread_id` ([artifact_adapter.py:18-26](src/ai_qa/pipelines/artifact_adapter.py:18)), the `load_approved_requirements` thread-prioritized loader, the `frontend/src/components/agents/` directory, `frontend/src/types/testcase.ts`, the `App.tsx` per-agent `maryState`/`handleMaryMessage`/render/confirm wiring, the Bob→Mary auto-navigate + Mary auto-start effects. 13.1 reuses these as the template for Sarah (`load_approved_test_cases`, `SarahInputSelection.tsx`, `sarahState`/`handleSarahMessage`, Mary→Sarah navigate + Sarah auto-start). If 12.1 added the DTO `thread_id`, **reuse it**; if not, 13.1 adds it.
4. **12.4 likely already adds the Mary→Sarah "Proceed to Sarah" navigation** (its Task 6) — landing on the (then-empty) step 4. 13.1 builds the step-4 UI that navigation lands on. If 12.4 added the navigate, reuse it; do not duplicate.

Reconcile against live code and note any divergence in Completion Notes (per [verify-subagent-claims](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\verify-subagent-claims.md) and [create-story-snippet-hazards](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\create-story-snippet-hazards.md)).

---

## Scope decisions (CONFIRMED — Thuong locked all four defaults 2026-06-13)

All defaults below are chosen from the code + ACs + planning docs + the 12.1 precedent and **confirmed by Thuong** ("làm toàn bộ theo default", 2026-06-13). The four formerly-open questions are now resolved decisions (full list under "Confirmed decisions" at the end of this file). No pending input remains; the dev agent implements exactly as written.

- **AC2 delivery = full-stack rich (mirror 12.1) — CONFIRMED.** Build a dedicated Sarah input-selection component (`frontend/src/components/agents/SarahInputSelection.tsx`, sibling to 12.1's `MaryInputSelection.tsx`) AND wire the step-4 Sarah surface that does not exist yet (no `sarahState`, no `handleSarahMessage`, no step-4 render block, no Mary→Sarah navigation, no Sarah auto-start — see Dev Notes "Frontend reality"). Each candidate row: per-test-case checkbox, thread-origin badge, source-requirement label/link, confidence badge (if 12.3 fields present), and an expandable preview. **Confirm & Generate** button. (Decision #1.)
- **Sarah lifecycle = input-selection is the NEW first gate, BEFORE the existing chrome-path/generation flow — CONFIRMED.** Sarah's `handle_start` today ([sarah.py:456-517](src/ai_qa/agents/sarah.py:456)) requests a Chrome path and then immediately generates from **all** loaded test cases. 13.1 inserts the selection gate **in front**: `handle_start` → preconditions → load approved test cases (thread-prioritized) → **AC3 block if empty** → present `test_case_selection` (REVIEW_REQUEST, `phase="input_selection"`); the user confirms → `handle_approve` (phase-dispatched) stores `confirmed_test_cases` → **then** the existing chrome-path check + generation runs (which presents the existing per-item script review). Order = **selection → chrome-path → generate**. The chrome-path request and the per-item **script** review loop are **preserved unchanged** (they are Epic-5 behavior; refining them is Stories 13.2/13.4/13.5+). (Decision #2.)
- **`load_approved_test_cases` is the new adapter loader (the seam 12.5 explicitly reserved for 13.1).** It is the analog of 12.1's `load_approved_requirements`, but **without** an approved/draft discriminator — every `kind="testcase"` artifact is approved by construction (12.5: the save runs only at `DONE`; there is no draft test case). So the loader = `list_artifacts(kind="testcase")` → stable-sort current-thread-first → map via `_to_pipeline_artifact`. Keep `load_test_cases()` (other callers depend on it — the existing Epic-5 `process` path).
- **Out of scope for 13.1:** the per-item **script** side-by-side review UX (Story 13.5), script edit-before-approval (13.6), script approval/rejection/regeneration semantics (13.7), the script-artifact save (13.8), the actual generation prompt/selectors/SSO (13.2/13.3/13.4), and the Chrome-path **frontend** UI (a pre-existing Epic-5 gap — **confirmed deferred**, do not build the chrome-path input here; Decision #3). Do **not** modify Sarah's `_generate_scripts`, `_present_current_script_for_review`, `handle_skip`, `handle_navigate`, or `GeneratedScript`.

## What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status / action |
| --- | --- | --- |
| `kind="testcase"` → storage key `projects/{project_id}/test_cases/{artifact_id}/v{version}/{name}` | [storage.py:32-33](src/ai_qa/artifacts/storage.py:32) | ✅ done — AC1 path already correct; no storage change |
| `PipelineArtifactAdapter.load_test_cases()` → `_load_text_artifacts(kind="testcase")` (project-scoped, no workspace path) | [artifact_adapter.py:139-141](src/ai_qa/pipelines/artifact_adapter.py:139), [:234-246](src/ai_qa/pipelines/artifact_adapter.py:234) | ✅ done — **keep it**; 13.1 adds `load_approved_test_cases` (thread-prioritized) alongside |
| `ArtifactService.list_artifacts(*, project_id, kind=None)` (project-scoped, ordered by name; no thread filter) | [service.py:194-201](src/ai_qa/artifacts/service.py:194) | ✅ done — partition/sort current-thread-first in Python (stable sort) |
| `PipelineArtifact` DTO + `_to_pipeline_artifact` (content is the test-case JSON string) | [artifact_adapter.py:18-26](src/ai_qa/pipelines/artifact_adapter.py:18), [:238-246](src/ai_qa/pipelines/artifact_adapter.py:238) | ⚠️ bare DTO (id/name/kind/content/version) — needs `thread_id` for prioritization (12.1 may have added it; else add) |
| `SarahAgent.handle_start` (chrome-path request → greet → PROCESSING → `process` → per-item review) | [sarah.py:456-517](src/ai_qa/agents/sarah.py:456) | ⚠️ exists — **insert the input-selection gate in front**; preserve the chrome-path + generation tail |
| `SarahAgent.process` → `_load_test_cases` → `adapter.load_test_cases()` | [sarah.py:146-242](src/ai_qa/agents/sarah.py:146) | ⚠️ exists — already reads via artifact service (AC1 mostly true); make it generate from `confirmed_test_cases`; **fix stale "workspace/testcases/" docstrings/messages** ([:175](src/ai_qa/agents/sarah.py:175), [:187](src/ai_qa/agents/sarah.py:187), [:209](src/ai_qa/agents/sarah.py:209)) |
| Per-item **script** review loop (`handle_approve`/`handle_reject`/`handle_skip`/`handle_navigate`/`_present_current_script_for_review`/`GeneratedScript`) | [sarah.py:519-736](src/ai_qa/agents/sarah.py:519), [:26-37](src/ai_qa/agents/sarah.py:26) | ✅ Epic-5 — **do not change** (13.5+ owns it); only phase-dispatch `handle_approve` |
| `_format_error_message(errors)` — UX-DR12 three-part error (What happened / Why / What to do) | [base.py:402-413](src/ai_qa/agents/base.py:402) | ✅ done — reuse for the AC3 block message |
| Bob precondition-gate pattern (`_check_preconditions -> list[str]`, blockers → error + stay START) | [bob.py:124-157](src/ai_qa/agents/bob.py:124), [:243-250](src/ai_qa/agents/bob.py:243), [:503-518](src/ai_qa/agents/bob.py:503) | ✅ done — mirror for Sarah's lighter gate (project context only; no MCP/provider check) |
| WebSocket dispatch routes `approve`→`handle_approve(data)` with `data` passthrough; step map + navigate map step 4 → "Sarah" (broadcasts `state:"start"`) | [websocket.py:312-322](src/ai_qa/api/websocket.py:312), [:356-362](src/ai_qa/api/websocket.py:356), [:369-382](src/ai_qa/api/websocket.py:369) | ✅ done — confirm rides the existing `data` channel; **no router change** |
| Bob `SplitPanel` render block (template for a new step-N panel render) | [App.tsx:1661-1677](frontend/src/App.tsx:1661) | ✅ done — mirror for the Sarah selection render |
| Alice→Bob auto-navigate effect; Alice auto-start effect | [App.tsx:833-855](frontend/src/App.tsx:833), [:621](frontend/src/App.tsx:621) | ✅ done — mirror for Mary→Sarah navigate + Sarah auto-start |
| `ReviewContent` markdown renderer (for an expandable preview) | [ReviewContent.tsx](frontend/src/components/ReviewContent.tsx) | ✅ done — reuse for the preview pane |
| `frontend/src/components/agents/MaryInputSelection.tsx` + `frontend/src/types/testcase.ts` | created by 12.1 | ✅ (after 12.1) — **mirror, do not modify**; add `SarahInputSelection.tsx` + Sarah-selection types alongside |

---

## Tasks / Subtasks

- [x] **Task 1 — New approved-test-case loader on the adapter (AC1, AC2)**
  - [x] Confirm the `PipelineArtifact` DTO ([artifact_adapter.py:18-26](src/ai_qa/pipelines/artifact_adapter.py:18)) carries `thread_id: UUID | None = None` (added by 12.1). If absent, add it (frozen dataclass — append with a default so existing loaders are unaffected) and populate it in `_to_pipeline_artifact` ([:238-246](src/ai_qa/pipelines/artifact_adapter.py:238)) from `artifact.thread_id`. (Also `source_type`/`source_url` if 13.1 needs them for the panel; test cases store provenance in the JSON content, so `thread_id` is the only field strictly required for prioritization.)
  - [x] Add `load_approved_test_cases(self) -> list[PipelineArtifact]` to `PipelineArtifactAdapter`, alongside (not replacing) `load_test_cases()`. It must: call `self.service.list_artifacts(project_id=self.project_id, kind="testcase")`, then **stable-sort** so `thread_id == self.context.thread_id` rows come first (Python sort is stable; `list_artifacts` already orders by name, so name order is preserved within each group), then map via `_to_pipeline_artifact`. **No `source_type` filter** — every `kind="testcase"` row is approved by construction (12.5; see Dev Notes "Why no discriminator").
  - [x] Do **not** remove or alter `load_test_cases()` — Sarah's existing Epic-5 `process`→`_load_test_cases` path and any other callers depend on it.

- [x] **Task 2 — Sarah precondition gate + AC3 block (AC3)**
  - [x] Add `_check_preconditions(self) -> list[str]` to `SarahAgent`, mirroring Bob ([bob.py:124-157](src/ai_qa/agents/bob.py:124)) but **only** the context checks Sarah needs at selection time: `project_context` present with non-None `project_id`/`user_id`/`thread_id`, and `artifact_service` available. Sarah does **not** need MCP or an Alice provider gate to *list* test cases (the LLM/browser is only needed at generation time, post-confirm; the Chrome-path request already handles the browser prerequisite there).
  - [x] Add `_format_no_test_cases_message(self) -> str` returning the AC3 UX-DR12 message (reuse `_format_error_message` shape at [base.py:402-413](src/ai_qa/agents/base.py:402), or build the three-part body directly): *What happened* = "Sarah cannot generate scripts yet."; *Why* = "No approved test cases were found for this project."; *What to do* = "Run Mary to generate test cases from approved requirements and approve at least one test case, then start Sarah again."

- [x] **Task 3 — Restructure Sarah's lifecycle: input-selection gate before chrome-path/generation (AC1, AC2, AC3)**
  - [x] Add Sarah state in `__init__` ([sarah.py:70-86](src/ai_qa/agents/sarah.py:70)): `self.phase: str = "input_selection"`, `self.candidate_test_cases: list[PipelineArtifact] = []`, `self.confirmed_test_cases: list[TestCase] = []`.
  - [x] **Restructure `handle_start`** ([sarah.py:456-517](src/ai_qa/agents/sarah.py:456)). New flow (preserving the chrome-path + generation tail as a helper):
    1. `blockers = self._check_preconditions()`; if non-empty → `send_message(message_type="error")` per blocker and `return` (stay START).
    2. `self._load_chrome_path()` (keep — loads the saved path now that project_context is set) and store `self._start_input_data = input_data` (keep).
    3. Resolve candidates: `PipelineArtifactAdapter(self.project_context).load_approved_test_cases()`.
    4. If empty → `send_message(self._format_no_test_cases_message(), message_type="error")` and `return` (AC3; **no** PROCESSING, **no** chrome-path request, **no** generation).
    5. Store `self.candidate_test_cases = candidates`; compute the default selection (current-thread pre-selected; if none, all pre-selected — see Dev Notes).
    6. `await self.transition_to(AgentState.REVIEW_REQUEST)`; `await self._present_test_case_selection()`.
  - [x] Implement `_present_test_case_selection(self)` — `send_message` with `metadata={"type": "test_case_selection", "is_input_selection": True, "test_cases": [...]}`. Each entry parses the artifact's JSON content into a `TestCase` (`TestCase(**json.loads(a.content))`, tolerating a list per the existing `_load_test_cases` shape) and emits: `{ "artifact_id": str(a.id), "name": a.name, "title": tc.title, "source_requirement_name": getattr(tc, "source_requirement_name", None), "source_url": getattr(tc, "source_url", None), "confidence_level": getattr(tc, "confidence_level", None), "from_current_thread": a.thread_id == ctx.thread_id, "default_selected": bool, "preview": <readable summary or the JSON> }`. Use `getattr(..., None)` so the panel degrades gracefully on the pre-12.2/12.3 `TestCase`.
  - [x] **Phase-dispatch `handle_approve`** ([sarah.py:519-570](src/ai_qa/agents/sarah.py:519)): if `self.phase == "input_selection"` → `await self._confirm_inputs(data)`; **else** fall through to the existing per-item **script**-review approve logic (unchanged). Do the same minimal guard in `handle_reject`/`handle_skip` if needed so a stray pre-confirm reject/skip can't index into an empty `_generated_scripts` (they already guard on `_current_review_index >= len(self._generated_scripts)` — verify that guard covers the pre-generation state).
  - [x] Implement `_confirm_inputs(self, data)`: read `selected_artifact_ids` from `data` (default = all candidates if absent/empty); filter `self.candidate_test_cases` to the selected set and parse each into a `TestCase` → `self.confirmed_test_cases`; if the result is empty, re-present the selection with a corrective message and `return`. Otherwise set `self.phase = "script_review"` and **run the existing chrome-path + generation tail** that `handle_start` used to run inline: the chrome-path check (request the path and `return` at START if missing — unchanged), else `transition_to(PROCESSING)` → `process(self._start_input_data)` → on success `transition_to(REVIEW_REQUEST)` + `_present_current_script_for_review()`; on failure `transition_to(ERROR)` + `_format_error_message`. Extract that tail into a helper (e.g. `_begin_generation(self)`) called from both `_confirm_inputs` and (if Chrome path was already requested-and-supplied) wherever generation resumes.
  - [x] Update `process(...)` ([sarah.py:146-206](src/ai_qa/agents/sarah.py:146)) to generate from `self.confirmed_test_cases` instead of re-loading **all** test cases via `_load_test_cases()`: when `self.confirmed_test_cases` is populated, set `self._test_cases = self.confirmed_test_cases` and skip the `_load_test_cases()` reload; keep the feedback/regenerate branch and the empty-guard. Do **not** delete `_load_test_cases` (regeneration/back-compat may still call it) — just bypass it when a confirmed set exists.
  - [x] Delete/fix the stale "workspace/testcases/" wording: the comment at [sarah.py:175](src/ai_qa/agents/sarah.py:175), the warning text at [:187](src/ai_qa/agents/sarah.py:187), and the docstring at [:209](src/ai_qa/agents/sarah.py:209). Sarah reads only via the artifact service.

- [x] **Task 4 — Frontend: Sarah input-selection component (AC2)**
  - [x] Create `frontend/src/components/agents/SarahInputSelection.tsx` (mirror 12.1's `MaryInputSelection.tsx` in the same dir). Props: `testCases: TestCaseInput[]`, `onConfirm: (selectedIds: string[]) => void`, `disabled: boolean`. Render: a checkbox list (default-selected per `default_selected`), a "from this conversation" badge when `from_current_thread`, a `source_requirement_name` label + clickable `source_url` link (hide when empty — Confluence stores `""`), a confidence badge keyed on `confidence_level` (green/amber/red; reuse the 12.4 `MaryReviewPanel` badge convention if present, else SplitPanel's amber token at [SplitPanel.tsx:164-189](frontend/src/components/SplitPanel.tsx:164)), an expandable preview (reuse `ReviewContent`), and a **"Confirm & Generate"** button that calls `onConfirm(selectedIds)`. Disable Confirm when zero selected. Prefer `getByRole`/accessible names (checkboxes need labels) per project rules.
  - [x] Add a `TestCaseInput` interface (the `test_case_selection` payload entry) to `frontend/src/types/testcase.ts` (created by 12.1) — match the backend payload exactly (full-stack sync, [project-context.md#Critical-Don't-Miss-Rules](project-context.md)). Reuse 12.1/12.4's `TestCase`/`ConfidenceLevel` types where they overlap; mirror the shape/casing of [extraction.ts](frontend/src/types/extraction.ts).

- [x] **Task 5 — Frontend: step-4 Sarah surface + Mary→Sarah navigation + Sarah auto-start (AC2 prerequisites)**
  - [x] Add `isSarahStep = currentStep === 4` (mirror `isAliceStep` [App.tsx:499](frontend/src/App.tsx:499), `isBobStep` [:511](frontend/src/App.tsx:511)).
  - [x] Add `sarahState` (e.g. `{ testCases: TestCaseInput[] | null }`) + a `handleSarahMessage` callback that captures `metadata.type === "test_case_selection"` into `sarahState.testCases`, gated on `message.agentName === "Sarah"` (mirror `handleBobMessage` [App.tsx:721-774](frontend/src/App.tsx:721); register it where `handleBobMessage` is wired into the message stream). No `sarahState`/`handleSarahMessage` exists today.
  - [x] Render `<SarahInputSelection>` when `isSarahStep && status === "review_request" && sarahState.testCases?.length` (mirror the Bob `SplitPanel` render block [App.tsx:1661-1677](frontend/src/App.tsx:1661)).
  - [x] Add `handleSarahConfirm(selectedIds)` → `sendMessage({ type: "approve", step: 4, data: { action: "confirm_inputs", selected_artifact_ids: selectedIds } })` (mirror `handleBobApprove` [App.tsx:974-988](frontend/src/App.tsx:974)).
  - [x] **Mary→Sarah navigation:** if 12.4 already added the "Proceed to Sarah" navigate (its Task 6), reuse it. If not, add it: when `currentStep === 3 && (status === "completed" || status === "done")`, send `{ type: "navigate", step: 4, direction: "next", agentName: "Sarah", ... }` (mirror Alice→Bob [App.tsx:833-855](frontend/src/App.tsx:833)). Backend `_handle_navigate` already maps step 4 → "Sarah" ([websocket.py:356-362](src/ai_qa/api/websocket.py:356)).
  - [x] **Sarah auto-start:** when `isConnected && currentStep === 4 && status === "start" && threadId && !hasSentStartRef`, send `{ type: "start", step: 4, inputData: {} }` (mirror Alice auto-start [App.tsx:621](frontend/src/App.tsx:621)). Sarah needs no user input to begin resolving approved test cases. Guard the start ref per-step so it does not collide with the Alice start guard.

- [x] **Task 6 — Backend tests (AC1, AC2, AC3)**
  - [x] Adapter test in [tests/pipelines/test_pipeline_artifact_adapter.py](tests/pipelines/test_pipeline_artifact_adapter.py): `load_approved_test_cases` is project-scoped (other project → `[]`), returns all `kind="testcase"` rows (no discriminator), and orders current-thread rows first. Use the real `ArtifactService` over in-memory SQLite (copy the existing scaffold). Seed test cases via `adapter.save_test_case("tc-1.json", tc.model_dump_json())` in two threads + a second project.
  - [x] Sarah tests in [tests/test_agents/test_sarah.py](tests/test_agents/test_sarah.py):
    - `handle_start` with no approved test cases → AC3 error message sent, stays START, `process`/`ScriptGenerator` never called, **no** chrome-path request.
    - `handle_start` with approved test cases → emits `test_case_selection` payload, transitions to REVIEW_REQUEST, **does not** generate (ScriptGenerator not constructed yet); thread-prioritized ordering + pre-selection reflected in the payload.
    - `handle_approve({action:"confirm_inputs", selected_artifact_ids:[...]})` in `phase=="input_selection"` → sets `confirmed_test_cases` to the selected subset, then runs the chrome-path/generation tail (assert chrome-path request when no saved path; assert generation from the **selected subset only** when a path exists).
    - **Regression:** the existing per-item **script**-review tests (`TestSarahAgentHandleApprove`/`HandleReject`/`HandleSkip`/`HandleNavigate`, [test_sarah.py:411-800](tests/test_agents/test_sarah.py:411)) still pass — set `agent.phase = "script_review"` (and `_generated_scripts`) in those tests so `handle_approve` dispatches to the existing script logic, OR default the dispatch so a populated `_generated_scripts` routes to script review. Rename the stale `test_process_loads_test_cases_from_workspace` ([:180](tests/test_agents/test_sarah.py:180)) and update the "workspace/testcases" assertions ([:237](tests/test_agents/test_sarah.py:237)).
  - [x] **Conftest hazard:** `mock_project_context` ([tests/conftest.py:58-64](tests/conftest.py:58)) is a `MagicMock(spec=PipelineContext)` that sets only `user_id`/`user_email`/`artifact_service.db` — `project_id`/`thread_id` resolve to auto-child MagicMocks (truthy, **not** `None`), so a `_check_preconditions` that only checks `is not None` will **pass** and the blast radius is small. If a Sarah test needs a real empty-vs-populated load, patch `PipelineArtifactAdapter.load_approved_test_cases` on the patched adapter (existing tests already patch `ai_qa.agents.sarah.PipelineArtifactAdapter`). Fix any shared-fixture break **centrally** in conftest ([agent-gate-conftest-regression](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\agent-gate-conftest-regression.md)), not per-test.

- [x] **Task 7 — Frontend tests (AC2)**
  - [x] Vitest `frontend/src/components/__tests__/SarahInputSelection.test.tsx` (mirror `MaryInputSelection`'s test / `SplitPanel.test.tsx`): renders candidates, default selection honored, deselect/select adjusts, thread-origin + confidence badges, source link (hidden when empty), Confirm disabled at zero-selected, Confirm emits the selected ids. Vitest 4 rules — [project-context.md#Testing-Rules](project-context.md).
  - [x] Optional App-level test: `test_case_selection` message → `SarahInputSelection` render path; confirm → `approve` step-4 send with `selected_artifact_ids`.
  - [x] Playwright E2E (`frontend/e2e/`, e.g. extend `epic-13.spec.ts`): **scope realistically.** Seeding an approved test case via API + driving the full generate path needs Mary's LLM output (not E2E-reproducible without a provider key; `page.route` mocking is forbidden — [project-context.md#Testing-Rules](project-context.md)). Default: if approved test cases can be seeded via the artifact API, cover navigate-to-Sarah → selection panel lists the seeded case with the thread badge → Confirm → assert the flow reaches the chrome-path/processing state. Otherwise scope to the **AC3 block path** (no approved test cases → blocking message) and note the deferral in Completion Notes. Real-API state prep + `afterEach` cleanup of users/projects/artifacts.

- [x] **Task 8 — Verify (no migration needed)**
  - [x] Backend: `uv run pytest --no-cov` (whole suite — the coverage gate fails on subset runs; see Dev Notes). Mypy gate: `uv run mypy src`. Pyrefly-clean (narrow `self.project_context`/`project_id`/`thread_id`/`data.get(...)` before use; no redundant casts; `from uuid import UUID` if annotating the loader).
  - [x] Frontend: `npm run lint`, `npm run typecheck`, `npm run test` (Vitest), and the new E2E spec.
  - [x] Confirm **no Alembic migration** is required — `kind="testcase"` → `test_cases/` mapping already exists; `TestCase` persists via `model_dump_json` (Pydantic, no DB table); the `thread_id` column already exists on `Artifact`. State this explicitly in Completion Notes.

## Dev Notes

### Current state of the files this story touches (READ FIRST)

**`src/ai_qa/agents/sarah.py` — the primary change target (substantial Epic-5 implementation already exists).**

- **`handle_start`** ([sarah.py:456-517](src/ai_qa/agents/sarah.py:456)) is **already overridden** (unlike Mary's inherited base in 12.1). It: `_load_chrome_path()`; stores `input_data`; if **no** Chrome path → sends a greeting + a `chrome_path_request` metadata message, transitions back to START, and returns; if a Chrome path **exists** → greets, transitions to PROCESSING, calls `process(input_data)`, then on success → REVIEW_REQUEST + `_present_current_script_for_review()`, else → ERROR. 13.1 inserts the **input-selection gate in front of all of this** and moves the chrome-path + generation tail behind the confirm step. **Preserve the chrome-path behavior verbatim** — only its *position* in the flow changes.
- **`process`** ([sarah.py:146-206](src/ai_qa/agents/sarah.py:146)) → `_load_test_cases()` ([:208-242](src/ai_qa/agents/sarah.py:208)) **already reads via the artifact service**: `PipelineArtifactAdapter(self.project_context).load_test_cases()` ([:213](src/ai_qa/agents/sarah.py:213)). So AC1's "no workspace path reads" is **mostly already true** (exactly the 12.1 situation for Mary). The real AC1/AC2 gap: it loads **all** test cases with **no** thread prioritization and **no** user confirm step, and the docstrings/messages still **lie** about "workspace/testcases/" ([:175](src/ai_qa/agents/sarah.py:175), [:187](src/ai_qa/agents/sarah.py:187), [:209](src/ai_qa/agents/sarah.py:209)) — delete that wording.
- **Empty-load handling today is NOT the AC3 block:** `_load_test_cases` returns `StageResult(success=False, errors=["No test case artifacts found for this project"])` ([:214-221](src/ai_qa/agents/sarah.py:214)), which bubbles to `handle_start` → ERROR + generic `_format_error_message`. AC3 requires a **block before PROCESSING** with a message that names the cause ("Mary generation and approval must happen first"). 13.1's gate replaces that path: detect empty **at selection time** (`load_approved_test_cases() == []`), send the dedicated UX-DR12 message, and **stay START** (no PROCESSING, no ERROR, re-submittable).
- **The per-item SCRIPT review loop is Epic-5 and out of scope:** `handle_approve` ([:519-570](src/ai_qa/agents/sarah.py:519)), `handle_reject` ([:572-619](src/ai_qa/agents/sarah.py:572)), `handle_skip` ([:621-666](src/ai_qa/agents/sarah.py:621)), `handle_navigate` ([:668-696](src/ai_qa/agents/sarah.py:668)), `_present_current_script_for_review` ([:698-736](src/ai_qa/agents/sarah.py:698)), `GeneratedScript` ([:26-37](src/ai_qa/agents/sarah.py:26)). 13.1 only **phase-dispatches** `handle_approve` (input-selection vs the existing script-review branch). Stories 13.5–13.8 own the script review/edit/approve/save behavior — do not refactor it here.

**`src/ai_qa/pipelines/artifact_adapter.py` — add the approved-test-case loader.**

- `load_test_cases()` → `_load_text_artifacts(kind="testcase")` ([:139-141](src/ai_qa/pipelines/artifact_adapter.py:139), [:234-236](src/ai_qa/pipelines/artifact_adapter.py:234)) does **no** thread ordering. Add `load_approved_test_cases()` (thread-prioritized) **alongside** it. The DTO ([:18-26](src/ai_qa/pipelines/artifact_adapter.py:18)) needs `thread_id` to prioritize (12.1 adds it; else add). The content is the **JSON** `model_dump_json` of a `TestCase` (not markdown) — parse it for the panel (`TestCase(**json.loads(content))`).
- `save_test_case` ([:134-137](src/ai_qa/pipelines/artifact_adapter.py:134)) is the producer 12.5 makes idempotent — 13.1 only **reads**.

**`src/ai_qa/models.py` — `TestCase` ([:265-298](src/ai_qa/models.py:265)).** On the live (pre-12.2) baseline it has only `title`/`preconditions`/`steps`/`expected_results`/`automation_hints`/`tags` + the `filename` property ([:291-298](src/ai_qa/models.py:291)). After 12.2/12.3/12.4 it gains source/confidence/approval fields. The selection panel reads them via `getattr(tc, "...", None)` so it degrades gracefully if a dependency is unmerged.

### Why no approved/draft discriminator (the single most load-bearing fact)

Unlike **requirements** — where Bob writes a pre-approval **draft** (`{page_id}.md`, provenance NULL) and an approved copy (`{page_id}/requirement.md`, provenance set), discriminated by `source_type IS NOT NULL` (12.1) — **there is no draft test case.** `MaryAgent._write_approved_test_cases` writes `kind="testcase"` artifacts **only at `DONE`**, after every case has been approved through the per-item review loop (12.5 confirms this and explicitly notes it for 13.1). So **every `kind="testcase"` artifact is approved by construction**: `load_approved_test_cases` can `list_artifacts(kind="testcase")` directly with **no** filter. AC1's "rejected or draft test cases are excluded" is therefore satisfied **structurally**, not by a query predicate. (If a future story ever introduces a pre-approval draft test case, it must add a discriminator the way requirements did — but do **not** build that here.)

### Thread prioritization & default selection (AC2)

- "Originating thread" = `Artifact.thread_id` ([models.py:145](src/ai_qa/db/models.py:145)), set by `save_test_case` → `save_artifact` from `context.thread_id`. The current thread = `PipelineContext.thread_id` ([context.py:18](src/ai_qa/pipelines/context.py:18)).
- `ArtifactService.list_artifacts(*, project_id, kind=None)` ([service.py:194-201](src/ai_qa/artifacts/service.py:194)) filters by `project_id` + `kind` only, ordered by `Artifact.name`. **No thread filter/ordering exists** — partition/sort in Python (stable sort preserves name order within each group).
- **Chosen default selection (document as implemented; user-adjustable):** if any approved test case has `thread_id == ctx.thread_id`, pre-select those (list first); other project-level approved test cases are listed below, **deselected** by default, available to add. If there are **no** current-thread approved test cases, pre-select **all** project-level approved test cases so the user is never stuck with an empty set. Satisfies "prioritized" (ordering + pre-selection + badge) and "confirm or adjust" (deselect/select then Confirm).

### Gate pattern to mirror (Bob / Story 11.2)

Synchronous, pure, DB-reads-only `_check_preconditions() -> list[str]` at the **top** of `handle_start`, before any transition; empty list = pass ([bob.py:124-157](src/ai_qa/agents/bob.py:124)). Each blocker → `send_message(message_type="error")` with the UX-DR12 *What happened / Why / What to do* body. On block, **return without transitioning** (stay START so the step is re-submittable) — do **not** go to ERROR. Sarah's gate is lighter than Bob's (no MCP, no provider check) — it only needs a valid project context to *list* test cases. The Chrome path / browser readiness is handled by the existing chrome-path request at generation time, post-confirm.

### Sarah lifecycle after 13.1 (the two pre-generation gates)

```
handle_start
  → _check_preconditions()            (project context)         [AC3 gate #0]
  → load_approved_test_cases()
      → [] → AC3 block message, stay START                       [AC3]
      → present test_case_selection (REVIEW_REQUEST, phase=input_selection)  [AC2]

handle_approve (phase dispatch)
  → phase == "input_selection" → _confirm_inputs(data)
        → confirmed_test_cases = selected subset                 [AC1/AC2]
        → phase = "script_review"
        → _begin_generation():
              chrome path missing? → chrome_path_request, stay START (UNCHANGED)
              else → PROCESSING → process(confirmed) → REVIEW_REQUEST → _present_current_script_for_review()
  → else → existing per-item SCRIPT-review approve (UNCHANGED, 13.5+)
```

The chrome-path request remains a **second** pre-generation gate (it loops back to START to collect the path, then re-enters `handle_start`/generation). Because `confirmed_test_cases` is now set, the re-entry must skip the selection gate and resume generation — guard `handle_start` so that if `self.confirmed_test_cases` is already populated and only the Chrome path was missing, it goes straight to `_begin_generation()` rather than re-presenting the selection. **Ordering CONFIRMED (Thuong 2026-06-13): selection → chrome-path → generate** (Decision #2).

### Frontend reality (what must be built from scratch)

The frontend has **zero** Sarah UI today (confirmed): no `isSarahStep`, no `sarahState`, no `handleSarahMessage`, no step-4 render block, no `chrome_path_request` handler, no `review_data` (script side-by-side) handler, no Mary→Sarah navigation, no Sarah auto-start. The `frontend/src/components/agents/` directory and `frontend/src/types/testcase.ts` are created by 12.1 (verify present). 13.1 mirrors the Bob wiring (state + message handler + render block at [App.tsx:721-774, 974-988, 1661-1677](frontend/src/App.tsx:721)) and the Alice navigate/auto-start effects ([:621, :833-855](frontend/src/App.tsx:621)) for Sarah. The `AGENTS` map ([pipeline.ts](frontend/src/types/pipeline.ts) Sarah `stepNumber: 4`) and `usePipelineState` step→agent routing (`4: "Sarah"`) already exist, so any Sarah message moves the UI to step 4 automatically.

> **Known pre-existing gap (CONFIRMED deferred, Thuong 2026-06-13 — Decision #3):** the Chrome-path request (`metadata.type === "chrome_path_request"`) has **no** frontend handler at all (Epic-5 backend, never wired). After the user confirms the test-case selection, a real run reaches the chrome-path request, which the UI cannot render today. **Confirmed: defer** the chrome-path UI (it is a generation prerequisite, more 13.2/13.4 territory) and scope the 13.1 E2E to the selection panel + AC3 block. Building the chrome-path input is a small add but would expand 13.1 scope — explicitly **out of 13.1**.

### WebSocket wiring (already in place — reuse it)

- Dispatch: `_handle_action` routes `start`→`handle_start(inputData)`, `approve`→`handle_approve(data)`, `reject`→`handle_reject(feedback, data)` ([websocket.py:312-322](src/ai_qa/api/websocket.py:312)). `data` is already passed to `handle_approve` — the confirm payload (`{action:"confirm_inputs", selected_artifact_ids:[...]}`) rides this channel. A new `agent_run` is created on `start` ([websocket.py:303](src/ai_qa/api/websocket.py:303)).
- `_handle_navigate` maps step 4 → "Sarah" ([websocket.py:356-362](src/ai_qa/api/websocket.py:356)) and broadcasts a `state:"start"` navigation message ([:369-382](src/ai_qa/api/websocket.py:369)) — Mary→Sarah needs **no** backend change.

### Architecture compliance (hard rules)

- **Agents never read/write storage directly — always through the artifact service** ([architecture.md:518](_bmad-output/planning-artifacts/architecture.md:518), forbidden anti-pattern [:533](_bmad-output/planning-artifacts/architecture.md:533)). Sarah already reads test cases via `PipelineArtifactAdapter`; the new loader keeps that contract.
- **Mandatory human review at every step — no auto-advance through a Review Request** ([architecture.md:271-272](_bmad-output/planning-artifacts/architecture.md:271), [ux-design-specification.md:188](_bmad-output/planning-artifacts/ux-design-specification.md:188)). The input-selection confirm is itself a review gate; do not auto-confirm.
- **No credential/secret leakage:** the selection payload + panel carry only test-case titles, source-requirement names/URLs, confidence, and artifact ids — **never** Chrome paths-as-secrets, tokens, or config dicts. The leak-canary convention applies (FR-aligned with 13.4's secret rules).
- **Backend payload/model change → update the TS interface simultaneously** and `npm run build`/`typecheck` ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)).
- Artifacts are project-scoped under `projects/{project_id}/requirements|test_cases|test_scripts/` ([architecture.md:280](_bmad-output/planning-artifacts/architecture.md:280)).

### Library / framework constraints (from project-context.md)

- **Backend:** Python ≥3.14, `uv` only (`uv run`, never `pip`/`python3`). Ruff + Mypy strict (`uv run mypy src`). Pyrefly-clean — narrow `Optional` before use (`ctx.project_id`, `ctx.thread_id`, `data.get("selected_artifact_ids")`); no redundant casts/conversions. The artifact path is a **sync** `Session` (no async SQLAlchemy caveats). `pytest.raises(Exception)` prohibited — specific type + `match=`.
- **Frontend:** React 19.2, TS ~6.0 strict, Tailwind v4, Vitest 4 (`vi.mock` hoisted file-wide; prefer `vi.spyOn(globalThis,"fetch")`; preserve real exports via `importOriginal()`), ESLint 9. Path alias `@` → `./src`. Strict null/index access — non-null assert known array elements. Playwright: `getByRole`/`getByText`; checkbox controls need accessible names; no `page.route`, no `waitForTimeout`.
- **No new packages.** **No Alembic migration** (the `thread_id` column + `kind="testcase"` mapping already exist; `TestCase` is a Pydantic JSON model).

### Project Structure Notes

- **New files:** `frontend/src/components/agents/SarahInputSelection.tsx`, `frontend/src/components/__tests__/SarahInputSelection.test.tsx`, and a Playwright spec under `frontend/e2e/` (e.g. `epic-13.spec.ts`).
- **Modified files (expected):** `src/ai_qa/agents/sarah.py`, `src/ai_qa/pipelines/artifact_adapter.py` (loader + DTO `thread_id` if not from 12.1), `frontend/src/App.tsx` (isSarahStep + sarahState + handleSarahMessage + render + confirm + Mary→Sarah navigate + Sarah auto-start), `frontend/src/types/testcase.ts` (add `TestCaseInput`), `tests/test_agents/test_sarah.py`, `tests/pipelines/test_pipeline_artifact_adapter.py`, possibly `tests/conftest.py`.
- **No backend route/schema changes:** the selection payload rides the existing WebSocket `send_message` metadata channel; confirm rides the existing `approve`/`data` channel; Mary→Sarah uses the existing navigate handler. No REST endpoint added.

### Testing standards summary

- Backend: pytest; the existing Sarah tests patch `ai_qa.agents.sarah.PipelineArtifactAdapter` + `ai_qa.agents.sarah.ScriptGenerator` ([test_sarah.py:174-177, 193](tests/test_agents/test_sarah.py:174)) and use `mock_project_context` + `mock_broadcast` — reuse that scaffold and set `mock_adapter.load_approved_test_cases.return_value`. Adapter test uses the real `ArtifactService` over in-memory SQLite (copy `tests/pipelines/test_pipeline_artifact_adapter.py`). Run the **whole** suite with `--no-cov` (subset runs fail the coverage gate; live baseline prior epic = 1098 passed). Mypy gate is `src` only.
- Frontend: Vitest for the component; Playwright E2E with real-API state prep + `afterEach` cleanup, scoped per Task 7 because LLM-driven generation isn't E2E-reproducible without a provider key.

### Previous-story intelligence

- **Story 12.1 (Mary input selection)** — the **direct analog**. Same shape: a filtered + thread-prioritized adapter loader (`load_approved_requirements`), a confirm-before-generate lifecycle (`self.phase` + `handle_approve` phase-dispatch), a `MaryInputSelection.tsx` panel, `App.tsx` per-agent state/handler/render/confirm, and Bob→Mary navigate + Mary auto-start. 13.1 re-applies all of it for Sarah. **Key difference:** Mary needed an approved/draft discriminator (`source_type IS NOT NULL`); Sarah needs **none** (no draft test case). Keep the loader + panel generic (12.1 already flagged this reusability note — [12.1 "Sibling-story note"](_bmad-output/implementation-artifacts/12-1-test-case-generation-input-selection.md)).
- **Story 12.5 (Test Case Artifact Save)** — the **producer**. It reserved `load_approved_test_cases` (the loader 13.1 adds) explicitly for this story and proved the `kind="testcase"` query surface is project-scoped with no workspace path. 12.5 also established that "only approved" is **structural** (no draft) — the basis for AC1 here.
- **Story 12.4 (Mary review workflow)** — likely adds the **Mary→Sarah "Proceed to Sarah" navigation** (its Task 6) landing on the empty step 4; 13.1 builds that step-4 UI. Reuse its navigate effect + the `TestCase`/`ConfidenceLevel` TS types if present.
- **Epic 5 (Sarah, `done`)** — built Sarah's chrome-path flow, `process`/`_load_test_cases` (already artifact-service-based), the `ScriptGenerator`/`VisionLocator` integration, and the per-item script review loop. 13.1 layers the selection gate **in front** and does not touch the Epic-5 review loop.
- **Stories 11.7/11.8** — the requirements analog of the save/idempotency pattern (informs 13.8, not 13.1). Relevant only as the discriminator contrast (requirements have a draft; test cases do not).

### Git intelligence (recent work patterns)

Recent commits (`2a1f170 epic 11 code e2e unit done`, `b4ce65f epic 10 all e2e test OK`, `8cf53eb epic 10 all code done`) are Epic 10/11. **Epic 12 (12.1–12.5) is NOT implemented** — the live `sarah.py`/`mary.py`/`TestCase`/`App.tsx`/adapter are pre-12.1. Before relying on 12.1's `MaryInputSelection`/`testcase.ts`/DTO `thread_id`, 12.2–12.4's `TestCase` fields, and 12.5's saved approved test cases, **verify they are present in the live tree**; if Epic 12 is unmerged it is a blocking prerequisite — flag and stop rather than re-implementing. Closest existing patterns to copy: [SplitPanel.tsx](frontend/src/components/SplitPanel.tsx) + [SplitPanel.test.tsx](frontend/src/components/__tests__/SplitPanel.test.tsx), the Bob render/handlers in [App.tsx:721-1013, 1661-1677](frontend/src/App.tsx:721), [tests/test_agents/test_sarah.py](tests/test_agents/test_sarah.py) (Sarah lifecycle scaffold), [tests/pipelines/test_pipeline_artifact_adapter.py](tests/pipelines/test_pipeline_artifact_adapter.py) (real-service adapter scaffold), [extraction.ts](frontend/src/types/extraction.ts) (TS payload-type pattern), [epic-11.spec.ts](frontend/e2e/epic-11.spec.ts) (latest E2E pattern).

### Sibling-story note (reusability)

Story **15.1 (Jack — approved-script input selection)** has the identical "load approved {scripts}, prioritize originating thread, user confirms/adjusts before {execution}" shape ([epics.md](_bmad-output/planning-artifacts/epics.md) Epic 15). Keep `load_approved_test_cases` + `SarahInputSelection` generic enough that the pattern (filtered + thread-prioritized load → selection panel → confirm) re-applies for `load_approved_scripts` in 15.1. Don't over-engineer a shared abstraction now, but avoid Sarah-only hardcoding that would block reuse — this is the third instance of the same pattern (12.1 → 13.1 → 15.1).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-13.1] — ACs (lines 1259-1279); Epic 13 intro + FRs FR6/FR7/FR8/FR9/FR12/FR13/FR19/FR20/FR21/FR22 (1253-1257); sibling 13.5 side-by-side review (1345-1365), 13.8 script save (1411-1430)
- [Source: _bmad-output/planning-artifacts/architecture.md] — no-direct-storage (518, 533), mandatory review / no auto-advance (271-272), project-scoped artifacts (280)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md] — mandatory review gate (188); Sarah/script step UX
- [Source: src/ai_qa/agents/sarah.py] — `handle_start` override + chrome-path (456-517), `process` (146-206), `_load_test_cases` + stale "workspace/testcases/" wording (208-242, esp. 175/187/209/213), per-item script review loop (519-736, do NOT change), `__init__` state (70-86), `GeneratedScript` (26-37)
- [Source: src/ai_qa/pipelines/artifact_adapter.py] — `load_test_cases` (139-141), `_load_text_artifacts`/`_to_pipeline_artifact` (234-246), `PipelineArtifact` DTO (18-26), `save_test_case` (134-137)
- [Source: src/ai_qa/artifacts/service.py] — `list_artifacts` (194-201), `read_current_content` (236-238), `delete_artifact` (211-234)
- [Source: src/ai_qa/artifacts/storage.py] — `kind="testcase"` → `test_cases/` (32-33), `folder_for_kind` (53-60)
- [Source: src/ai_qa/models.py:265-298] — `TestCase` (pre-12.2 fields + `filename` 291-298); `TestCaseStep` (244-262)
- [Source: src/ai_qa/pipelines/context.py:11-20] — `PipelineContext` (`thread_id` 18, provenance fields)
- [Source: src/ai_qa/agents/base.py] — `handle_start` (307-339), `_format_error_message` UX-DR12 (402-413), `handle_approve`/`handle_reject` base (341-387)
- [Source: src/ai_qa/agents/bob.py] — gate pattern (124-157, 243-250, 503-518)
- [Source: src/ai_qa/api/websocket.py] — dispatch passing `data` (276-332, esp. 316-322), navigate + step→agent map incl. 4→Sarah (335-388, 356-362)
- [Source: frontend/src/App.tsx] — isAliceStep (499), isBobStep (511), aliceState/bobState (488, 501-510), handleBobMessage (721-774), handleBobApprove (974-988), Bob SplitPanel render (1661-1677), Alice→Bob navigate (833-855), Alice auto-start (621)
- [Source: frontend/src/types/pipeline.ts] — `AGENTS` Sarah `stepNumber: 4`; [frontend/src/hooks/usePipelineState.ts:48-54] — step→agent `4: "Sarah"`
- [Source: frontend/src/components/SplitPanel.tsx] — review-panel pattern (nav, amber badge 164-189, source link, footer); [frontend/src/components/ReviewContent.tsx] — markdown preview
- [Source: frontend/src/types/extraction.ts] — TS payload-type pattern to mirror
- [Source: tests/test_agents/test_sarah.py] — Sarah test scaffold (patch adapter+ScriptGenerator; stale `test_process_loads_test_cases_from_workspace` 180, "workspace/testcases" assertion 237; script-review tests 411-800)
- [Source: tests/pipelines/test_pipeline_artifact_adapter.py] — real-service in-memory SQLite adapter scaffold
- [Source: tests/conftest.py:27-64] — `mock_db` / `mock_project_context` (no project_id/thread_id set; central gate-fix point)
- [Source: _bmad-output/implementation-artifacts/12-1-test-case-generation-input-selection.md] — the analog input-selection story (loader + panel + confirm-before-generate + navigation patterns to mirror)
- [Source: _bmad-output/implementation-artifacts/12-5-test-case-artifact-save.md] — the producer; reserves `load_approved_test_cases` for 13.1; "only approved is structural / no discriminator"
- [Source: project-context.md] — `uv`/`npm` only; Ruff + Mypy strict; Pyrefly (narrow Optional, no redundant cast); no bare except; no `# type: ignore`; full-stack sync; security (no secrets in payloads/logs)

## Confirmed decisions (defaults locked by Thuong 2026-06-13 — "làm toàn bộ theo default")

All four formerly-open questions are resolved to their defaults. No pending input — implement exactly as stated.

1. **AC2 delivery = full-stack rich (CONFIRMED).** Build `SarahInputSelection.tsx` + the step-4 Sarah surface (`isSarahStep`/`sarahState`/`handleSarahMessage`/render/confirm) + Mary→Sarah navigation + Sarah auto-start (none exist today). NOT backend-only.
2. **Pre-generation gate ordering = selection FIRST, then Chrome-path, then generation (CONFIRMED).** The test-case selection becomes the new first gate; the existing Chrome-path request moves behind confirm; the AC3 block fires before any chrome-path prompt.
3. **Chrome-path frontend UI = DEFERRED (CONFIRMED).** Out of 13.1 scope (a generation prerequisite closer to 13.2/13.4). Do not build the chrome-path input here; scope the 13.1 E2E to the selection panel + AC3 block.
4. **E2E coverage = scoped (CONFIRMED).** Backend pytest is the guardrail + Vitest for the panel; Playwright E2E covers navigate→selection→Confirm→processing **if** approved test cases can be seeded via the artifact API, else just the **AC3 block path** (LLM-driven generation isn't E2E-reproducible without a provider key; `page.route` forbidden). No stub-provider E2E required.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Integration test `test_sarah_loads_test_cases_and_saves_approved_script` failed because it called `handle_approve()` without setting `phase = "script_review"`. Fixed by adding `sarah.phase = "script_review"` before the call (mirrors the fix applied to all three `TestSarahAgentHandleApprove` tests).
- `MaryInputSelection.tsx` was not present (12.1 used a different Bob-style approach). `SarahInputSelection.tsx` was created from scratch mirroring `MaryReviewPanel.tsx` style instead.
- Vitest "This conversation" test: `getByText(/This conversation/i)` matched both the header span `(1 from this conversation)` and the badge. Fixed to `getByText("This conversation")` (exact match).
- Vitest "Confirm subset" test: `getByLabelText(/Login/i)` matched multiple elements because the second row's label also contained "Login requirement" (default factory). Fixed to `getByRole("checkbox", { name: "Login" })` (aria-label match).

### Completion Notes List

- **No Alembic migration required.** `kind="testcase"` → `test_cases/` mapping already exists in `storage.py:32-33`. `TestCase` is a Pydantic model persisted as JSON (`model_dump_json`), not a DB table. `Artifact.thread_id` column already exists from Epic 10.
- **`MaryInputSelection.tsx` absent from working tree.** Story referenced it as the template; the 12.1 implementation used a different approach (Bob SplitPanel style). `SarahInputSelection.tsx` was written from scratch mirroring `MaryReviewPanel.tsx` and `SplitPanel.tsx` patterns.
- **`PipelineArtifact.thread_id`** was already present in the working tree (added by 12.1). No new field needed.
- **Mary→Sarah navigation**: 12.4 added a manual "Proceed to Sarah" button; this story added the `hasSentSarahStartRef` guard + `handleSarahMessage` + auto-start effect so clicking that button triggers the full 13.1 selection flow automatically.
- **E2E scope**: scoped to AC3 block path (no approved test cases → WS error response) as confirmed. The Playwright spec uses a direct WebSocket connection from `page.evaluate()` to test the real backend precondition check without LLM generation.
- **`confirmed_test_cases` re-entry guard**: when the Chrome-path was missing after confirm, Sarah returns to START. On re-entry from the user providing a Chrome path, `handle_start` detects `confirmed_test_cases` is already set and skips directly to `_begin_generation()` — preserving the confirmed selection across the two-step input→chrome-path→generate flow.

### File List

- `src/ai_qa/pipelines/artifact_adapter.py` — added `thread_id` to `PipelineArtifact` DTO; added `load_approved_test_cases()` method; populated `thread_id` in `_to_pipeline_artifact`
- `src/ai_qa/agents/sarah.py` — added `phase`/`candidate_test_cases`/`confirmed_test_cases` state; added `_check_preconditions()`/`_format_no_test_cases_message()`/`_present_test_case_selection()`/`_confirm_inputs()`/`_begin_generation()`; restructured `handle_start`; phase-dispatched `handle_approve`; updated `process()` to use `confirmed_test_cases`; fixed stale "workspace/testcases/" wording
- `frontend/src/types/testcase.ts` — added `TestCaseInput` interface
- `frontend/src/components/agents/SarahInputSelection.tsx` — new file: checkbox list + thread/confidence badges + source req link + expandable preview + Confirm & Generate button
- `frontend/src/App.tsx` — added `isSarahStep`/`sarahState`/`hasSentSarahStartRef`; added `handleSarahMessage`/`handleSarahConfirm`; added Sarah auto-start effect; added SarahInputSelection render block
- `tests/pipelines/test_pipeline_artifact_adapter.py` — added 4 tests for `load_approved_test_cases` (project isolation, all-testcase-kind, thread prioritization, DTO thread_id)
- `tests/test_agents/test_sarah.py` — renamed stale test; rewrote 2 handle_start tests for AC2/AC3; added `phase = "script_review"` to 3 handle_approve tests; added `TestSarahAgentInputSelection` class (8 new tests)
- `tests/integration/test_project_scoped_agents.py` — added `sarah.phase = "script_review"` before `handle_approve()` call
- `frontend/src/components/__tests__/SarahInputSelection.test.tsx` — new file: 23 Vitest tests
- `frontend/e2e/epic-13.spec.ts` — new file: AC3 block path Playwright E2E (WS direct connection, no LLM)
