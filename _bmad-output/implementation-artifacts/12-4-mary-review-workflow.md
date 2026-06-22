---
baseline_commit: 79f3f3cc797621c0ed3ae41e9b0c10edb59038fb
---

# Story 12.4: Mary Review Workflow

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want to review, approve, reject, and give feedback on Mary's generated test cases through a rich per-item review UI that shows each test case's source requirement references and confidence warnings,
so that only validated natural-language test cases become script-generation inputs for Sarah.

## Acceptance Criteria

Verbatim from [epics.md#Story-12.4](_bmad-output/planning-artifacts/epics.md) (lines 1209-1229), expanded with implementation defaults (see "Scope decisions" — confirm or correct).

### AC1 — Rich per-item review UI with source refs + confidence visible

- **Given** Mary generated one or more test cases
- **When** the review UI opens
- **Then** the user can review **each** test case in a structured card showing **title, objective, preconditions, test data, steps, expected results**, the **source requirement reference** (name + link), and the **confidence** (green/yellow/red badge + score + the rationale/causes), with **per-case ambiguity warnings** surfaced
- **And** the user can step through test cases (**Next/Previous**) — each test case is independently reviewable (preserves the per-item review semantics from 12.1–12.3)

### AC2 — Approve makes a test case eligible for Sarah, recorded with user + timestamp

- **Given** the user approves a generated test case
- **When** approval is submitted
- **Then** the test case becomes eligible for Sarah script generation (it is included in Mary's saved/approved output and the workflow can proceed to Sarah only after every case is reviewed)
- **And** the approval is recorded with **user and timestamp** metadata on the test case

### AC3 — Reject with feedback regenerates; rejected output is never treated as approved

- **Given** the user rejects a generated test case with feedback
- **When** feedback is submitted
- **Then** Mary regenerates/revises the affected test case where possible (the existing `handle_reject` regeneration path) and re-presents it for a fresh decision
- **And** the prior rejected output is **replaced** (not retained) — a rejected case is never carried into the approved/saved set without an explicit re-approval

## Scope decisions (defaults — confirm or correct)

These are sensible defaults chosen from the code + ACs + planning docs; Thuong can override. Saved questions are listed at the end of this file.

- **This is the capstone full-stack review-UX story for Mary.** It builds the rich per-item test-case **review card** + the strongly-typed TS `TestCase` interface + the **confidence visualization** (green/yellow/red badge + causes panel) + the **"Proceed to Sarah"** affordance + the low-confidence visual gate — all four were explicitly deferred to 12.4 by Stories 12.1, 12.2, and 12.3. The backend per-item approve/reject loop, generation, and confidence engine already exist (12.1–12.3); 12.4 adds the **rendering layer**, plus two focused backend changes: (a) **AC2 approval-metadata recording** (user + timestamp per approved case), and (b) the **review transport** so the FE can drive a rich, navigable card (see "The key design decision" below).
- **Review transport = present-all + client-side navigation, mirroring Bob's `SplitPanel` (recommended default).** After generation, Mary already holds the full `self.test_cases` list. 12.4 has Mary emit the **full list** in one review payload (analogous to Bob's `is_review_ready` + `pages`), and the new `MaryReviewPanel` does client-side Prev/Next + per-case Approve/Reject (sending the case's **id/index**). Backend `handle_approve`/`handle_reject` become **index/id-addressable** (reading `data["test_case_index"]`, default = `current_review_index` for back-compat) so a freely-navigated card maps to the right case. The per-item review **semantics** (each case decided independently, mandatory review, no bulk-approve, DONE only after all decided) are **preserved** — only the transport changes from "stream one bubble at a time" (the 12.1–12.3 placeholder) to "full list + rich client nav". This is consistent with the project's deliberate Bob pattern (bespoke inline panel, full list, client nav — [SplitPanel.tsx](frontend/src/components/SplitPanel.tsx)). See Saved Question #1.
- **AC2 approval recording is 12.4; the artifact-save metadata expansion + save-failure recovery is 12.5.** 12.4 stamps each approved `TestCase` with `approved_by` (user email/id from context) + `approved_at` (ISO timestamp) so the approval decision is recorded and persists via `model_dump_json`. **12.5** lifts those (plus source artifact IDs + confidence data + approval status) into the artifact-save **metadata sidecar / artifact row** and owns the save-failure retry/recovery. Do not expand the save metadata or the sidecar here. See Saved Question #2 for the exact boundary.
- **"Proceed to Sarah" = an explicit affordance shown at DONE that navigates to step 4 (Mary → Sarah), mirroring 12.1's Bob→Mary navigation.** Sarah's step-4 UI is **Epic 13** (not built yet), so landing on step 4 shows the existing/empty Sarah state — that is the expected handoff, not a 12.4 defect. The low-confidence **visual gate** (12.3 enforces it at the backend) is rendered here: surface a summary banner + red badges so the user's approve/reject of each low-confidence case is informed and explicit. See Saved Question #3.
- **Out of scope:** confidence **engine** changes (12.3 owns the deterministic algorithm — 12.4 only *renders* the triple), generation/prompt changes (12.2), the input-selection panel (12.1 owns `MaryInputSelection.tsx`), and Sarah's step-4 UI (Epic 13). **No Alembic migration** (TestCase is a Pydantic JSON model; the approval fields are new model fields, not DB columns).

## Sequencing dependency (READ FIRST — critical)

**Stories 12.1, 12.2, and 12.3 are `ready-for-dev`, NOT `done`.** As of this writing the working tree still holds the **pre-12.1** Mary ([mary.py](src/ai_qa/agents/mary.py): inherited `handle_start`→immediate generate, positional `handle_approve` advancing `current_review_index`, no `self.phase`/`confirmed_requirements`, plain-bubble `_present_current_test_case`; `TestCase` has none of the 12.2 source/objective/warnings fields nor the 12.3 confidence triple; no `MaryInputSelection.tsx`, no `frontend/src/types/testcase.ts`). 12.4 is the **last story in the 12.1 → 12.2 → 12.3 → 12.4 chain** and MUST be implemented **after all three land**. Specifically, 12.4 assumes:

1. **From 12.1:** Mary's confirm-before-generate lifecycle (`self.phase`, `self.candidate_requirements`, `self.confirmed_requirements`, the `handle_approve` phase-dispatch), `frontend/src/components/agents/MaryInputSelection.tsx`, `frontend/src/types/testcase.ts` (with `RequirementInput`), the App.tsx `maryState` + `handleMaryMessage` + Bob→Mary navigation + Mary auto-start.
2. **From 12.2:** the extended `TestCase` model (`objective`, `test_data`, `source_requirement_id`/`name`, `source_url`, `feature_area`, `warnings`), per-requirement generation, and the enriched `_format_review_content` (Objective/Source/Test-Data/Warnings sections).
3. **From 12.3:** the `TestCase` confidence triple (`confidence: float | None`, `confidence_level: ConfidenceLevel | None`, `confidence_rationale: list[str]`), the deterministic `_assess_confidence` engine, the `_reviewed_indices` set + the defensive DONE guard, and the optional `low_confidence`/`low_confidence_count` message metadata.

If 12.1/12.2/12.3 are not yet merged when you start, **stop and flag it** — do not re-implement them here. 12.4 **extends** the 12.3 versions of `handle_approve`/`handle_reject`/`_present_current_test_case`/`_format_review_content` and the `TestCase` model; it does not re-create them. Reconcile against the live code and note any divergence in Completion Notes.

## Tasks / Subtasks

- [x] **Task 1 — TS `TestCase` types for the client (AC1, full-stack sync)**
  - [x] Extend `frontend/src/types/testcase.ts` (created by 12.1 with `RequirementInput`) with strongly-typed interfaces matching the backend `TestCase.model_dump()` payload **exactly** (full-stack sync rule, [project-context.md#Critical-Don't-Miss-Rules](project-context.md); mirror the casing/shape of [extraction.ts](frontend/src/types/extraction.ts)):
    - `ConfidenceLevel = "high" | "medium" | "low"` (matches the backend `Literal`).
    - `TestCaseStep { number: number; action: string; target: string; data?: string }`.
    - `TestCase { title: string; objective?: string; preconditions: string[]; test_data?: string[]; steps: TestCaseStep[]; expected_results: string[]; automation_hints?: string[]; tags?: string[]; source_requirement_id?: string | null; source_requirement_name?: string | null; source_url?: string | null; feature_area?: string | null; warnings?: string[]; confidence?: number | null; confidence_level?: ConfidenceLevel | null; confidence_rationale?: string[]; approved_by?: string | null; approved_at?: string | null }`.
    - A `TestCaseReviewPayload` interface for the review message metadata: `{ type: "test_case_review"; test_cases: TestCase[]; low_confidence_count?: number }` (and/or the per-item `{ test_case: TestCase; current_index: number; total_count: number }` shape — match whichever transport you implement in Task 4).
  - [x] Keep `RequirementInput` (12.1) intact in the same file.

- [x] **Task 2 — Backend: AC2 approval-metadata recording on the `TestCase` model (AC2)**
  - [x] In [models.py](src/ai_qa/models.py) `TestCase` (the 12.3 version) append, **with backward-compatible defaults**: `approved_by: str | None = Field(default=None, description="User (email/id) who approved this test case")` and `approved_at: str | None = Field(default=None, description="ISO-8601 timestamp of approval")`. Update the docstring attribute list. New fields serialize via `model_dump`/`model_dump_json` → persist with **no migration**, and flow to the client through the review payload automatically.
  - [x] In Mary's `handle_approve` per-item branch (the 12.1 `phase == "test_case_review"` branch + 12.3's `_reviewed_indices` bookkeeping), stamp the **just-approved** case: `tc.approved_by = self.project_context.user_email or str(self.project_context.user_id)` and `tc.approved_at = datetime.now(UTC).isoformat()` **before** advancing/recording the index. Use `from datetime import UTC, datetime` (real runtime — not a Workflow sandbox, so `datetime.now` is fine). Narrow `self.project_context` is not None first (Pyrefly).
  - [x] Do **not** expand `_write_approved_test_cases`'s metadata sidecar (that is 12.5). The approval fields persist automatically because the sidecar/artifact serializes `model_dump_json()`. Note this boundary in Completion Notes.

- [x] **Task 3 — Backend: index/id-addressable approve + reject + full-list review payload (AC1, AC2, AC3)**
  - [x] **Emit the full review list.** Add `_present_test_case_review(self)` (or extend `_present_current_test_case`) to send ONE message after generation carrying the whole set: `metadata={"type": "test_case_review", "test_cases": [tc.model_dump() for tc in self.test_cases], "low_confidence_count": <k from 12.3>}`. Keep `message_type="text"` with a readable markdown summary as `content` (reuse 12.2/12.3's `_format_review_content` for the first/active case, or a brief group summary). This mirrors Bob's `is_review_ready` + `pages` payload ([bob.py] review-ready emit; consumed in [App.tsx:750-763](frontend/src/App.tsx:750)). Call it from `_confirm_inputs` after a successful generate (replacing/augmenting the single-case present) and after a successful regenerate.
  - [x] **Make `handle_approve` index-addressable.** Read `index = data.get("test_case_index", self.current_review_index)` (default preserves back-compat + the positional path). Validate `0 <= index < len(self.test_cases)`; stamp approval (Task 2) on `self.test_cases[index]`, add `index` to `self._reviewed_indices` (12.3). Transition to DONE only when **every** index is in `_reviewed_indices` (12.3's guard already enforces no unreviewed `low`-confidence case slips through — keep it). On DONE, call `_write_approved_test_cases` and send the success message (preserve existing behavior).
  - [x] **Make `handle_reject` index-addressable.** Read the same `test_case_index` from `data` (Bob already threads `page_id` through `handle_reject(feedback, data)` — same channel). Regenerate **that** case (reuse 12.2/12.3's regeneration via `self.confirmed_requirements` + the rejected case's `RequirementSource(warnings=...)`), replace `self.test_cases[index]` with the regenerated case (re-scored confidence per 12.3), clear `index` from `_reviewed_indices`, and **re-emit the full review payload** so the client refreshes that card. The replaced case must NOT retain its prior approval stamp (clear `approved_by`/`approved_at` on regenerate) — AC3 "rejected output never treated as approved".
  - [x] Preserve the empty-result / extractor-failure / `project_context is None` branches and the UX-DR12 acknowledgement messages.

- [x] **Task 4 — Frontend: `MaryReviewPanel` rich per-item review card (AC1, AC2, AC3)**
  - [x] Create `frontend/src/components/agents/MaryReviewPanel.tsx` (sibling to 12.1's `MaryInputSelection.tsx` in the same dir). **Mirror the structure of [SplitPanel.tsx](frontend/src/components/SplitPanel.tsx)** but for a structured test case (no raw-HTML iframe / no markdown edit). Props: `testCases: TestCase[]`, `onApprove: (index: number) => void`, `onReject: (index: number, feedback: string) => void`, `disabled?: boolean`. Render:
    - **Header:** `Review Test Case (i of N) — {title}` + a `{resolved} resolved` counter (track client-side resolved set like SplitPanel lines 27, 71-94).
    - **Nav bar** (when N > 1): Prev/Next buttons (`getByRole("button", { name: ... })` accessible; mirror SplitPanel lines 134-160), clamping index when the array shrinks.
    - **Confidence badge** (AC1): map `confidence_level` → color — `high` = green, `medium` = amber/yellow, `low` = red (use the existing `Badge` component + Tailwind tokens; the project's amber convention is in SplitPanel lines 164-189). Show the score (e.g. `0.42`) and an expandable **"Why this score"** causes panel listing `confidence_rationale` (and any per-case `warnings`). For `low`, render the red/amber warning styling so it reads as "needs review".
    - **Test-case body:** Objective, Source requirement (`source_requirement_name` as text + `source_url` as a clickable `Open Original`/`Open in Jira` link when non-empty — mirror SplitPanel lines 59-60, 122-129; Confluence `source_url` may be `""` → hide the link), Preconditions (ordered), Test Data, Steps (`{n}. {action} (target: {target})` + optional `Data:`), Expected Results, Automation Hints. Reuse `ReviewContent` ([ReviewContent.tsx](frontend/src/components/ReviewContent.tsx)) only if you render a markdown blob; otherwise structured JSX is fine.
    - **Reject feedback input** (AC3): a toggle + textarea + Submit, exactly like SplitPanel lines 256-294 (1000-char cap, disabled-when-empty).
    - **Footer:** `Reject` (toggles feedback) + `Approve` buttons (mirror SplitPanel lines 296-327). Approve calls `onApprove(currentIndex)`; reject-submit calls `onReject(currentIndex, feedback)`. Auto-advance to the next unresolved case after approve (SplitPanel lines 77-81).
  - [x] **Low-confidence gate (AC1/12.3):** when any `confidence_level === "low"` exists, render a summary banner (`"{k} of {N} test cases are low confidence — review each before proceeding."`). Do **not** add a bulk-approve. The "Proceed to Sarah" affordance (Task 6) only appears once all cases are resolved (DONE).

- [x] **Task 5 — Frontend: wire `MaryReviewPanel` into App.tsx (AC1, AC2, AC3)**
  - [x] Extend `maryState` (12.1) with `testCases: TestCase[] | null` (and reuse 12.1's `requirements` for input-selection). In `handleMaryMessage` (12.1), capture the new payload: when `metadata.type === "test_case_review"`, set `maryState.testCases = metadata.test_cases`. Keep the 12.1 `requirement_selection` branch. **Discriminator:** render `<MaryInputSelection>` when `phase`/payload is input-selection (12.1); render `<MaryReviewPanel>` when `maryState.testCases` is populated.
  - [x] Render `<MaryReviewPanel>` when `isMaryStep (currentStep === 3) && status === "review_request" && maryState.testCases?.length`, mirroring the Bob `SplitPanel` render block ([App.tsx:1660-1677](frontend/src/App.tsx:1660)).
  - [x] Add `handleMaryApprove(index)` → `sendMessage({ type: "approve", step: 3, data: { action: "approved", test_case_index: index } })` and `handleMaryReject(index, feedback)` → `sendMessage({ type: "reject", step: 3, feedback, data: { test_case_index: index } })` (mirror `handleBobApprove`/`handleBobReject` [App.tsx:974-1013](frontend/src/App.tsx:974)).

- [x] **Task 6 — Frontend: "Proceed to Sarah" / Mary→Sarah navigation (AC2)**
  - [x] Add a Mary→Sarah affordance: when `currentStep === 3 && (status === "done")`, show a **"Proceed to Sarah"** button (or auto-navigate after a short delay) that sends `{ type: "navigate", step: 4, direction: "next", agentName: "Sarah", sender: "user", content: "Navigate to Sarah", messageType: "info" }` — mirror the Alice→Bob effect ([App.tsx:834-855](frontend/src/App.tsx:834)) and 12.1's Bob→Mary navigation. (Backend `_handle_navigate` already maps step 4 → "Sarah" — [websocket.py:356-362](src/ai_qa/api/websocket.py:356).)
  - [x] **Document the handoff:** Sarah's step-4 UI is Epic 13 — proceeding lands on the existing/empty Sarah step. That is expected. Prefer an **explicit button** over auto-navigate (mandatory-review philosophy; avoids dumping the user on an unbuilt step). Note in Completion Notes.

- [x] **Task 7 — Backend tests (AC1, AC2, AC3)**
  - [x] **Model** ([tests/test_agents/test_mary.py](tests/test_agents/test_mary.py) or a model test): a `TestCase` with `approved_by`/`approved_at` round-trips through `model_dump()`/`model_dump_json()`; defaults (`None`/`None`) hold when omitted (back-compat for existing fixtures).
  - [x] **Review payload**: after a confirmed generate, Mary emits a `test_case_review` message whose `metadata.test_cases` is the full `model_dump` list (incl. 12.2 source fields + 12.3 confidence triple) and `low_confidence_count` matches 12.3's count.
  - [x] **Index-addressable approve (AC2):** `handle_approve({action:"approved", test_case_index: i})` stamps `approved_by`/`approved_at` on case `i`, records `i` in `_reviewed_indices`, and reaches DONE only after all indices are recorded; the saved test cases carry the approval stamp (assert via the `save_test_case` mock). Back-compat: `handle_approve({})` with no index still advances positionally.
  - [x] **Index-addressable reject (AC3):** `handle_reject(feedback, {test_case_index: i})` regenerates case `i`, replaces it (new confidence re-scored), clears its `_reviewed_indices` entry and its approval stamp, and re-emits the full review payload. Assert the regenerated case is not in the approved set without a fresh approve.
  - [x] **12.3 gate still fires:** a `low`-confidence case left unreviewed blocks DONE (re-presents) — keep/extend 12.3's regression test against the index-addressable path.
  - [x] Run the **whole** suite with `--no-cov` (subset runs fail the coverage gate; live baseline prior epic = 1098 passed). If shared fixtures break, fix [tests/conftest.py](tests/conftest.py) **centrally** ([agent-gate-conftest-regression](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\agent-gate-conftest-regression.md)).

- [x] **Task 8 — Frontend tests (AC1, AC2, AC3)**
  - [x] Vitest `frontend/src/components/__tests__/MaryReviewPanel.test.tsx` (mirror [SplitPanel.test.tsx](frontend/src/components/__tests__/SplitPanel.test.tsx)): renders a test case with all fields + source link; **confidence badge color** maps high→green / medium→amber / low→red and shows the score + rationale; Prev/Next steps through cases and clamps; Approve emits `onApprove(index)`; Reject toggles feedback, Submit emits `onReject(index, feedback)`, disabled when empty; low-confidence summary banner appears when a `low` case exists. Vitest 4 rules — [project-context.md#Testing-Rules](project-context.md).
  - [x] Optional App-level test: `test_case_review` message → `MaryReviewPanel` render path; approve/reject → correct `sendMessage` payload (step 3 + `test_case_index`).
  - [x] Playwright E2E (`frontend/e2e/`, e.g. `epic-12.spec.ts`): **scope realistically.** Driving Mary's LLM generation end-to-end in E2E is impractical (no `page.route` mocking allowed — [project-context.md#Testing-Rules](project-context.md) — and real generation needs a provider key). Default: cover what's deterministic — navigate to Mary, confirm an input selection (12.1 seeded approved requirement), and assert the flow reaches the review/processing state; assert the review-panel **renders + approve/reject controls work** via the component (Vitest) rather than a full LLM round-trip. If a stub/fake provider is available in the E2E env, extend to the full approve→DONE→Proceed-to-Sarah path. Document any deferral in Completion Notes. `afterEach` cleanup of users/projects/artifacts (and any test cases) per project rules.

- [x] **Task 9 — Verify (no migration)**
  - [x] Backend: `uv run pytest --no-cov` (full suite) green. Mypy gate: `uv run mypy src` clean. Pyrefly-clean: narrow `self.project_context` / `data.get(...)` before use; no redundant casts; `datetime`/`UTC` import correct.
  - [x] Frontend: `npm run lint`, `npm run typecheck`, `npm run test` (Vitest), and the E2E spec.
  - [x] Confirm **no Alembic migration** is required (TestCase is a Pydantic JSON model; `approved_by`/`approved_at` are new model fields, not DB columns; 11.7 columns already exist). State explicitly in Completion Notes.

## Dev Notes

### Current state of the files this story touches (READ FIRST)

**`src/ai_qa/agents/mary.py` — heavily rewritten by 12.1/12.2/12.3 before you start.** The live (pre-12.1) version: inherited-then-overridden lifecycle; `handle_approve` ([mary.py:138-161](src/ai_qa/agents/mary.py:138)) advances `current_review_index` **positionally** (comment "implicit by advancing index") and transitions to DONE at `current_review_index >= len(self.test_cases)`, then `_write_approved_test_cases`; `handle_reject` ([mary.py:163-215](src/ai_qa/agents/mary.py:163)) regenerates the current case; `_present_current_test_case` ([mary.py:265-283](src/ai_qa/agents/mary.py:265)) emits **one** `test_case` per message (`metadata={"test_case": tc.model_dump(), "current_index", "total_count"}`); `_format_review_content` ([mary.py:217-263](src/ai_qa/agents/mary.py:217)) is the plain-bubble markdown; `_write_approved_test_cases` ([mary.py:285-305](src/ai_qa/agents/mary.py:285)) saves via `model_dump_json` + a sidecar that **hardcodes `"confidence": 1.0`** (12.5's to reconcile — leave it). **By the time you start, 12.1 has added `self.phase`/`confirmed_requirements` + the `handle_approve` phase-dispatch, 12.2 the per-requirement generation + enriched `_format_review_content`, and 12.3 the `_reviewed_indices` set + the defensive DONE guard + the `low_confidence` metadata.** Build 12.4 on top of those.

**`src/ai_qa/models.py` — `TestCase` ([:265](src/ai_qa/models.py:265)).** Pydantic model, `__test__ = False`. After 12.2/12.3 it carries title/objective/preconditions/test_data/steps/expected_results/automation_hints/tags/source_*/feature_area/warnings/confidence/confidence_level/confidence_rationale. **12.4 adds `approved_by`/`approved_at`.** All serialize via `model_dump_json` → no migration.

**`src/ai_qa/api/websocket.py` — dispatch + navigate.** `_handle_action` ([:276-332](src/ai_qa/api/websocket.py:276)) routes `approve`→`handle_approve(data)` and `reject`→`handle_reject(feedback, data)` — `data` already carries arbitrary payload (Bob uses `page_id`), so `test_case_index` rides the same channel with no router change. `_handle_navigate` ([:335-388](src/ai_qa/api/websocket.py:335)) maps step 4 → "Sarah" ([:356-362](src/ai_qa/api/websocket.py:356)) and broadcasts a `state:"start"` navigation message — Mary→Sarah needs no backend change.

**`src/ai_qa/agents/base.py` — lifecycle.** `handle_approve` ([:341-347](src/ai_qa/agents/base.py:341)) / `handle_reject` ([:349-387](src/ai_qa/agents/base.py:349)) are the base implementations Mary overrides; `handle_reject(feedback, data)` already takes the optional `data` param (added in 11.6). `transition_to` drives `metadata.state`, which the client maps to `status`.

**`frontend/src/App.tsx` — the wiring.** `isBobStep = currentStep === 2` ([:511](frontend/src/App.tsx:511)); `isMaryStep` is added by 12.1 (`currentStep === 3`). `bobState`/`handleBobMessage` ([:721-774](frontend/src/App.tsx:721)) capture the review payload; `handleBobApprove`/`handleBobSkip`/`handleBobReject` ([:974-1013](frontend/src/App.tsx:974)) send `approve`/`reject` step-2 with `data`; the Bob `SplitPanel` render block ([:1660-1677](frontend/src/App.tsx:1660)) is the template for the Mary review render. Alice→Bob auto-navigate ([:834-855](frontend/src/App.tsx:834)) is the template for Mary→Sarah. Agents array maps step 3 → Mary ([:1054-1060](frontend/src/App.tsx:1054)), step 4 → Sarah. `usePipelineState.updateFromMessage` ([usePipelineState.ts:296-303](frontend/src/hooks/usePipelineState.ts:296)) sets `status` from `metadata.state` and `currentStep` from `message.agentName` via `AGENTS[name].stepNumber` ([pipeline.ts:170+](frontend/src/types/pipeline.ts:170)).

**`frontend/src/components/SplitPanel.tsx` — the pattern to mirror (NOT reuse).** Bob's bespoke inline review panel: client-side `currentIndex` + `resolvedIds` set, Prev/Next nav bar, amber warnings banner, Preview/Edit tabs, reject-feedback textarea, footer Approve/Reject. `MaryReviewPanel` is a **sibling** — same skeleton, different body (structured test case + confidence badge instead of raw-HTML/markdown split). **Do not reuse `ChatInputArea`** — it exists with a full review state machine but is rendered nowhere (dormant; the project chose the bespoke inline panel, per 11.6/12.1 notes).

### The key design decision — review transport (most load-bearing)

The 12.1–12.3 placeholder presents test cases **one bubble at a time** (`_present_current_test_case`) and approves **positionally** (`current_review_index++`). A rich, navigable review card (AC1 "review **each** test case", UX spec "Next/Previous to step through test cases", [ux-design-specification.md:589](_bmad-output/planning-artifacts/ux-design-specification.md:589)) needs the **whole set** on the client. Recommended default (Saved Question #1):

- **Present-all:** Mary emits one `test_case_review` payload with `test_cases: [model_dump…]` (Mary already holds the full `self.test_cases`). The FE `MaryReviewPanel` owns Prev/Next + the resolved set, exactly like `SplitPanel`.
- **Index/id-addressable approve/reject:** because the user can navigate freely, approve/reject carry `test_case_index` in `data` (default `current_review_index` for back-compat). This pairs cleanly with **12.3's `_reviewed_indices` set**, which already decouples "decided" from positional order — keep that set authoritative for the DONE gate, and the 12.3 defensive guard becomes *more* meaningful (approval is no longer strictly positional).
- **Semantics preserved:** each case decided independently, no bulk-approve, mandatory review, DONE only after every case is in `_reviewed_indices`. Only the transport changes.

Alternative (if Thuong prefers minimal backend change): keep one-at-a-time streaming; FE accumulates messages and shows the current card with read-only look-back. Trade-off: asymmetric UX (can look back but only approve the backend's current case) and the navigation is less faithful to the spec. The recommended default is the present-all path for consistency with Bob.

### Confidence visualization (AC1 / 12.3)

12.3 stamps each case with `confidence` (0.0–1.0), `confidence_level` (`high`/`medium`/`low`), and `confidence_rationale` (`list[str]` causes), and forces `low` when any per-case or source/Bob warning exists. 12.4 renders it: green / amber / red badge keyed on `confidence_level`, the numeric score, and an expandable causes panel (the rationale + per-case `warnings`). This is the literal realization of the product's "confidence visualization (green/yellow/red)" goal ([ux-design-specification.md:81](_bmad-output/planning-artifacts/ux-design-specification.md:81), [:275](_bmad-output/planning-artifacts/ux-design-specification.md:275); FR22 [prd.md:384](_bmad-output/planning-artifacts/prd.md:384)) and "the problem is input quality, not the tool" narrative — the causes tell the reviewer *why* a test case is weak. The amber styling convention already exists in SplitPanel's warnings banner ([SplitPanel.tsx:164-189](frontend/src/components/SplitPanel.tsx:164)) — reuse the same `Badge` + Tailwind tokens.

### Architecture compliance (hard rules)

- **Mandatory human review at every step — no auto-advance through a Review Request, no bulk approve** ([architecture.md:271-272](_bmad-output/planning-artifacts/architecture.md:271), [ux-design-specification.md:188](_bmad-output/planning-artifacts/ux-design-specification.md:188)). 12.4's per-item card preserves this; the low-confidence gate reinforces it. "Proceed to Sarah" is an explicit user action, not an auto-advance.
- **Agents never read/write storage directly — always via the artifact service** ([architecture.md:518](_bmad-output/planning-artifacts/architecture.md:518), anti-pattern [:533](_bmad-output/planning-artifacts/architecture.md:533)). 12.4 adds no storage access; saves still go through `PipelineArtifactAdapter`.
- **Full-stack sync** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)): the new `TestCase` model fields (`approved_by`/`approved_at`) **and** the whole `test_case` payload (12.2 + 12.3 fields) must be mirrored in `frontend/src/types/testcase.ts` and verified with `npm run typecheck`/`build`. This is the full-stack-sync debt 12.2/12.3 explicitly handed to 12.4.
- **Per-item independent reviewability + grouping** ([epics.md#Story-12.4](_bmad-output/planning-artifacts/epics.md), [architecture.md:818-822](_bmad-output/planning-artifacts/architecture.md:818)): cases arrive grouped by source requirement (12.2 order); the panel may show `feature_area`/`source_requirement_name` as a group label, but each card is decided on its own.

### Library / framework constraints (from project-context.md)

- **Backend:** Python ≥3.14, `uv` only (`uv run`, never `pip`/`python3`). Ruff + Mypy strict (`uv run mypy src`). Pyrefly-clean: narrow `self.project_context` (and `data.get("test_case_index")`) before use; no redundant casts/conversions; `from datetime import UTC, datetime`. `pytest.raises(Exception)` prohibited — specific type + `match=`. The agent path uses a **sync** artifact `Session`.
- **Frontend:** React 19.2, TS ~6.0 strict (`npm run typecheck` catches what Vite skips), Tailwind v4, Vitest 4 (`vi.mock` hoisted file-wide; prefer `vi.spyOn(globalThis,"fetch")`; preserve real exports via `importOriginal()`), ESLint 9. Path alias `@` → `./src`. Strict null/index access — non-null assert known array elements (`arr[i]!`). Playwright: prefer `getByRole`/`getByText`; icon/checkbox controls need accessible names; no `page.route`, no `waitForTimeout`.
- **No new packages.** **No Alembic migration.** Reuse `Badge`, `Button`, `ReviewContent`, lucide-react icons already imported by SplitPanel.

### Project Structure Notes

- **New files:** `frontend/src/components/agents/MaryReviewPanel.tsx`, `frontend/src/components/__tests__/MaryReviewPanel.test.tsx`, and a Playwright spec (e.g. `frontend/e2e/epic-12.spec.ts`).
- **Extended files:** `frontend/src/types/testcase.ts` (add `TestCase`/`TestCaseStep`/`ConfidenceLevel`/`TestCaseReviewPayload` to 12.1's file), `frontend/src/App.tsx` (maryState.testCases + handleMaryMessage branch + render + approve/reject + Mary→Sarah), `src/ai_qa/models.py` (`TestCase` approval fields), `src/ai_qa/agents/mary.py` (full-list payload + index-addressable approve/reject + approval stamping), `tests/test_agents/test_mary.py`, possibly `tests/conftest.py`.
- **No backend route/schema/REST changes** — the review payload rides the existing WebSocket `send_message` metadata channel; approve/reject ride the existing `data` channel; Mary→Sarah uses the existing navigate handler.

### Testing standards summary

- Backend: pytest; mock `LLMClient` at `ai_qa.pipelines.test_case_extractor.LLMClient`; Mary tests patch `PipelineArtifactAdapter` + the extractor and set 12.1/12.2/12.3 state (`confirmed_requirements`, generated `self.test_cases` with confidence). `pytest.raises(Exception)` prohibited. Run the **whole** suite with `--no-cov`. Mypy gate is `src` only.
- Frontend: Vitest for `MaryReviewPanel` (mirror `SplitPanel.test.tsx`); Playwright E2E with real-API state prep + `afterEach` cleanup — scoped per Task 8 because LLM-driven generation isn't E2E-reproducible without a provider key.

### Previous Story Intelligence (12.1, 12.2, 12.3, 11.6)

- **12.1** owns `MaryInputSelection.tsx`, `frontend/src/types/testcase.ts` (with `RequirementInput`), `maryState` + `handleMaryMessage`, Bob→Mary navigation + Mary auto-start, and the `self.phase`/`confirmed_requirements` lifecycle + `handle_approve` phase-dispatch. 12.4 **extends** all of these (adds the review payload branch, the `TestCase` types, the `MaryReviewPanel`, the Mary→Sarah navigation). Keep `MaryInputSelection` and `RequirementInput` intact.
- **12.2** added the source/objective/test_data/feature_area/warnings fields + enriched `_format_review_content`, and explicitly deferred "the rich per-item review card and the strongly-typed TS `TestCase` interface" to 12.4. Render those fields here.
- **12.3** added the confidence triple + `_assess_confidence` + `_reviewed_indices` set + the defensive DONE guard + optional `low_confidence`/`low_confidence_count` metadata, and explicitly deferred "the confidence **visualization** (green/yellow/red badge + causes panel) + the 'Proceed to Sarah' navigation/UI gate" to 12.4. Render the badge/causes here and make `handle_approve` honor the `_reviewed_indices` gate. 12.3 warned the gate MUST key off `_reviewed_indices`, **not** `current_review_index` — the index-addressable approve in Task 3 makes that explicit; keep `_reviewed_indices` authoritative.
- **11.6** established the bespoke-inline review-panel pattern (SplitPanel, NOT the dormant `ChatInputArea`), Preview tab via `ReviewContent`, and `handle_reject` carrying optional `data` (`page_id`). `MaryReviewPanel` follows the same pattern; `test_case_index` is Mary's analog of Bob's `page_id`.

### Git Intelligence

- Recent commits are Epic 10 (`b4ce65f epic 10 all e2e test OK`, `8cf53eb epic 10 all code done`); Python was bumped 3.12→3.14 (`39db313`) — never pin back. **Epic 11 is uncommitted in the working tree, and Stories 12.1/12.2/12.3 are NOT yet implemented** (live `mary.py`/`TestCase`/App.tsx are pre-12.1). Before relying on 12.1's `MaryInputSelection`/`testcase.ts`/`maryState`, 12.2's `TestCase` fields, and 12.3's confidence triple + `_reviewed_indices`, **verify they are present in the live tree**; if any of the three is not yet implemented, it is a blocking prerequisite — flag and stop rather than re-implementing.
- Closest existing patterns: [SplitPanel.tsx](frontend/src/components/SplitPanel.tsx) + [SplitPanel.test.tsx](frontend/src/components/__tests__/SplitPanel.test.tsx) (review panel + test), the Bob render/handlers in [App.tsx:721-1013, 1660-1677](frontend/src/App.tsx:721), [tests/test_agents/test_mary.py](tests/test_agents/test_mary.py) (agent lifecycle), [extraction.ts](frontend/src/types/extraction.ts) (TS payload-type pattern), [epic-11.spec.ts](frontend/e2e/epic-11.spec.ts) (latest E2E pattern).

### Sibling-story note (reusability)

- **12.5 (Test Case Artifact Save)** expands the artifact-save metadata (source requirement artifact IDs, **confidence data, approval status, creator, updater, originating thread/agent run, timestamp**) and owns save-failure recovery. 12.4's per-case `approved_by`/`approved_at` are the hooks 12.5 lifts into save metadata; the `"confidence": 1.0` sidecar hardcode ([mary.py:300](src/ai_qa/agents/mary.py:300)) is still 12.5's to reconcile. Keep the `TestCase` payload stable + complete so 12.5 only lifts, not re-derives. **Confirm the 12.4/12.5 approval-metadata boundary (Saved Question #2).**
- **Epic 13 (Sarah)** builds the step-4 UI + the "approved test case input selection" (13.1, same shape as 12.1). `MaryReviewPanel` and the index-addressable approve/reject pattern should generalize to Sarah's side-by-side script review (13.5); avoid Mary-only hardcoding that blocks reuse. The "Proceed to Sarah" navigation is the seam Epic 13 plugs into.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-12.4] — ACs (lines 1209-1229); Epic 12 FRs FR5/FR22/FR27 (1141)
- [Source: _bmad-output/planning-artifacts/prd.md] — FR22 flag low-confidence for mandatory review (384); low-confidence flagging narrative (117, 183, 253)
- [Source: _bmad-output/planning-artifacts/architecture.md] — mandatory review / no auto-advance (271-272), no-direct-storage (518, 533), Mary flow + save to test_cases (818-822)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md] — Step 3 Create Test Cases incl. Next/Previous nav (572-597, esp. 589), confidence visualization green/yellow/red (81, 275), low-confidence amber token (682), mandatory review gate (188)
- [Source: src/ai_qa/agents/mary.py] — `handle_approve` (138-161), `handle_reject` (163-215), `_format_review_content` (217-263), `_present_current_test_case` (265-283), `_write_approved_test_cases` incl. sidecar (285-305)
- [Source: src/ai_qa/agents/base.py] — `handle_start` (307-339), `handle_approve` (341-347), `handle_reject` (349-387)
- [Source: src/ai_qa/models.py:265] — `TestCase` (add `approved_by`/`approved_at`); `TestCaseStep` (244-262, unchanged)
- [Source: src/ai_qa/api/websocket.py] — dispatch passing `data` to approve/reject (276-332), navigate + step→agent map incl. 4→Sarah (335-388, 356-362)
- [Source: frontend/src/App.tsx] — isBobStep/bobState (501-511), handleBobMessage (721-774), handleBobApprove/Skip/Reject (974-1013), agents array (1039-1075), Alice→Bob navigate (834-855), Bob SplitPanel render (1660-1677), BobState interface (173-183)
- [Source: frontend/src/components/SplitPanel.tsx] — review-panel pattern (full file: nav 134-160, warnings banner 164-189, source link 59-60/122-129, reject input 256-294, footer 296-327, resolved-set 27/71-94)
- [Source: frontend/src/components/ReviewContent.tsx] — markdown renderer (reuse for any markdown blob)
- [Source: frontend/src/types/extraction.ts] — TS payload-type pattern to mirror
- [Source: frontend/src/types/pipeline.ts] — `AgentStatus` (8-14), `AGENTS`/`stepNumber` (170+)
- [Source: frontend/src/hooks/usePipelineState.ts:285-313] — message→status/step mapping (296-303)
- [Source: frontend/src/components/__tests__/SplitPanel.test.tsx] — review-panel Vitest scaffold
- [Source: tests/test_agents/test_mary.py] — Mary agent test scaffold (reconcile with 12.1/12.2/12.3 renames)
- [Source: tests/conftest.py:27-63] — `mock_db`/`mock_project_context` (central fixture fix point)
- [Source: _bmad-output/implementation-artifacts/12-1-…md] + [12-2-…md] + [12-3-…md] — the lifecycle/model/engine/confidence/UI-deferral this story builds on

## Saved Questions (for Thuong — confirm or correct)

1. **Review transport (the big fork).** Default = **present-all + client-side navigation + index-addressable approve/reject** (mirrors Bob's `SplitPanel`; gives faithful Next/Previous and pairs with 12.3's `_reviewed_indices`). Alternative = keep 12.1–12.3's one-at-a-time streaming with read-only look-back (smaller backend change, less faithful UX). OK to go present-all?
2. **12.4 vs 12.5 approval-metadata boundary.** Default = 12.4 stamps `approved_by`/`approved_at` on the `TestCase` model (so the approval is recorded per AC2 and persists via `model_dump_json`); **12.5** lifts those + source IDs + confidence into the artifact-save metadata sidecar/row and owns save-failure recovery. Confirm, or should 12.4 stay purely frontend and push ALL approval recording to 12.5?
3. **"Proceed to Sarah" affordance.** Default = an **explicit "Proceed to Sarah" button** shown at Mary-DONE that navigates to step 4 (mirrors Bob→Mary), with the understanding that Sarah's step-4 UI is Epic 13 (lands on the existing/empty step). Or auto-navigate after a delay (like Alice→Bob), or omit navigation in 12.4 and just show a "ready for Sarah" completion message?
4. **Low-confidence gate UX.** Default = render red badges + a summary banner and rely on the mandatory per-item approve/reject (12.3's backend guard) — no extra confirmation modal. Or add an explicit "Approve low-confidence anyway?" confirmation step when approving a `low` case?

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- **DONE gate change broke 3 existing tests** (`test_handle_approve_transitions_to_done_when_all_approved`, `test_handle_approve_writes_approved_test_cases`, `test_ac3_guard_redirects_unreviewed_low_confidence`). Old gate: `current_review_index >= N`. New gate: `len(_reviewed_indices) >= N`. Fix: pre-populate `_reviewed_indices = set(range(N-1))` before calling approve on the last case; AC3 test rewritten to use `_reviewed_indices = {1, 99}` so guard finds index 0 missing.
- **`test_handle_reject_clears_approval_stamp` failed** because `mock_adapter.load_requirement_markdown.return_value = []` caused regeneration to be skipped. Fix: added a real `mock_artifact` with matching `source_requirement_id` so the regeneration path executes.
- **MaryReviewPanel test regex mismatch**: test asserted `/1 of 2 test cases are low confidence/i` (plural "cases are") but component renders "case is" (singular) when `lowConfidenceCount === 1`. Fix: changed to `/1 of 2 test case is low confidence/i`.
- **Story 12.1 was REDEFINED before 12.4 started**: `MaryInputSelection.tsx` was NOT built (Bob handles single-id selection), and `testcase.ts` did not exist. Created `testcase.ts` from scratch; skipped `RequirementInput`; adapted App.tsx wiring to the actual redefined state (no `self.phase`, just `maryState.testCases`).

### Completion Notes List

- **No Alembic migration required.** `TestCase` is a Pydantic JSON model stored in the artifact content column. `approved_by`/`approved_at` are new model fields only — not DB columns. All 11.7 columns already exist.
- **12.4/12.5 approval-metadata boundary confirmed.** 12.4 stamps `approved_by`/`approved_at` on the in-memory `TestCase` and they persist via `model_dump_json()` into the artifact content. 12.5 will lift them into the artifact-save metadata sidecar/row and fix the `"confidence": 1.0` hardcode in `_write_approved_test_cases`. This story does NOT expand the sidecar.
- **"Proceed to Sarah" = explicit button, not auto-navigate.** Shown when `currentStep === 3 && status === "done"`. Landing on step 4 is expected — Sarah's UI is Epic 13.
- **E2E scoped to deterministic checks only** (no LLM-driven generation in E2E — `page.route` mock not permitted per project rules and real generation needs a provider key). The full MaryReviewPanel + approve/reject path is covered by the Vitest component tests.
- **`_present_current_test_case` kept as a back-compat wrapper** calling `_present_test_case_review()` so existing callers from 12.1/12.2/12.3 still work without change.
- **Index-addressable DONE gate**: changed from positional `current_review_index >= N` to `len(_reviewed_indices) >= N` so users can freely navigate and approve out of order. DONE is reached only when every case has been explicitly reviewed.
- **Full backend suite: 1238 passed (0 failed)**. Frontend: 25/25 MaryReviewPanel tests passed. Lint and typecheck clean.

### File List

- `frontend/src/types/testcase.ts` — NEW: `ConfidenceLevel`, `TestCaseStep`, `TestCase`, `TestCaseReviewPayload` interfaces
- `src/ai_qa/models.py` — MODIFIED: added `approved_by`/`approved_at` fields to `TestCase`
- `src/ai_qa/agents/mary.py` — MODIFIED: `handle_start` override, index-addressable `handle_approve`/`handle_reject`, `_present_test_case_review()`, approval stamping, `from datetime import UTC, datetime`
- `frontend/src/components/agents/MaryReviewPanel.tsx` — NEW: rich per-item review card with confidence badge, nav, reject feedback, auto-advance
- `frontend/src/App.tsx` — MODIFIED: `maryState.testCases`, `handleMaryMessage` review branch, `handleMaryApprove`/`handleMaryReject`, `MaryReviewPanel` render block, "Proceed to Sarah" button
- `tests/test_agents/test_mary.py` — MODIFIED: 3 fixed existing tests + new `TestMaryApprovalMetadata` class (8 tests)
- `frontend/src/components/__tests__/MaryReviewPanel.test.tsx` — NEW: 25 Vitest tests covering AC1/AC2/AC3

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2026-06-16 | claude-sonnet-4-6 | Implemented Story 12.4: full-list review transport, index-addressable approve/reject, approval metadata stamping, MaryReviewPanel component, App.tsx wiring, "Proceed to Sarah", backend + frontend tests |
