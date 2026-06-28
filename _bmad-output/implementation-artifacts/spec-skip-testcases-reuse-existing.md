---
title: 'Blank id at Bob skips test-case generation and hands off to Sarah reusing existing test cases'
type: 'feature'
created: '2026-06-24'
status: 'done'
baseline_commit: 'e5e1651534247640d288ff49c5ff6c000eef8ef2'
context: ['{project-root}/project-context.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** After Bob saves requirements it prompts *"input 1 Confluence page id or Jira ticket id to generate test cases"* and forces the user through Mary (test-case generation). When usable test cases already exist in the project — from a previous thread/session or a colleague — there is no way to skip Mary and go straight to script generation.

**Approach:** Treat a **blank** id as a "skip test cases" action: Bob hands off directly to Sarah (step 4) instead of Mary (step 3). Sarah already loads project-wide approved test cases and lets the user confirm which to use; surface the most-recently-updated ones first so the previous session's work is easy to reuse.

## Boundaries & Constraints

**Always:**
- A **non-empty** id keeps the current Bob→Mary path completely unchanged (saves `mary_selected_id.json`, navigates to step 3).
- The skip is signalled by Bob (backend) via DONE-message metadata (`skip_to_sarah`) and consumed by the existing frontend Bob-DONE navigate effect, which routes to step 4.
- Reuse Sarah's existing selection gate (`_present_test_case_selection` / `_confirm_inputs`) — the user confirms which test cases to generate. No new Sarah UI flow.
- All user-facing strings in English.

**Ask First:**
- If, on the skip path, Sarah finds **no** approved test cases, keep the existing AC3 "no approved test cases" block (stay START) — do NOT auto-fall back to Mary or invent a new flow.

**Never:**
- Don't make Sarah generate scripts from requirements or raw exploration (no test cases ⇒ blocked, as today).
- Don't change Mary or the non-empty-id path; don't write `mary_selected_id.json` on skip.
- No DB migration.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| -------- | ------------- | -------------------------- | -------------- |
| Non-empty id | user types a Confluence/Jira id, clicks OK | unchanged: Bob saves `mary_selected_id.json`, hands off to Mary (navigate step 3) | N/A |
| Blank id (skip) | select-id input empty, clicks OK | Bob goes DONE with `skip_to_sarah` metadata; FE navigates to step 4; Sarah loads approved test cases and shows selection panel, most-recent first | N/A |
| Blank id, no existing test cases | empty input, project has no approved test cases | Sarah shows existing "no approved test cases" block and stays START | user can go back / run Mary |

</frozen-after-approval>

## Code Map

- `src/ai_qa/agents/bob.py` -- `_handle_select_id` (empty→skip branch), `_prompt_select_id` (prompt text)
- `frontend/src/App.tsx` -- `handleBobSelectId` (allow blank), select-id panel static text + OK enable, `handleBobMessage` (detect `skip_to_sarah`), Bob-DONE auto-nav effect (step 4 vs 3), thread-reset of the skip flag
- `src/ai_qa/pipelines/artifact_adapter.py` -- `PipelineArtifact` + `_to_pipeline_artifact` add `updated_at`; `load_approved_test_cases` sort each group by recency
- `src/ai_qa/agents/sarah.py` -- VERIFY ONLY: `handle_start`→`load_approved_test_cases`→`_present_test_case_selection`→`_confirm_inputs` already does reuse + confirm

## Tasks & Acceptance

**Execution:**
- [x] `src/ai_qa/agents/bob.py` -- in `_handle_select_id`, when `selected_id` is empty: set `phase="done"`, transition DONE, send a success message *"Skipping test case generation. Handing off to Sarah to reuse existing test cases."* with metadata `{"skip_to_sarah": True}`; do NOT persist `mary_selected_id.json`. Leave the non-empty branch untouched.
- [x] `src/ai_qa/agents/bob.py` -- append to `_prompt_select_id` text: leave blank to skip and reuse existing test cases (chat-history consistency).
- [x] `frontend/src/App.tsx` -- `handleBobSelectId`: allow blank; on blank `addUserMessage("Skip test case generation")` and send `approve {action:"select_id", id:""}`; do not set `marySelectedId`.
- [x] `frontend/src/App.tsx` -- select-id panel: update static prompt text + input placeholder to mention blank-to-skip; OK `disabled` gates only on `!isConnected`; button label shows `Skip` when blank.
- [x] `frontend/src/App.tsx` -- `handleBobMessage`: when `metadata.skip_to_sarah`, set `bobSkipToSarahRef` (and clear `selectIdPrompt`).
- [x] `frontend/src/App.tsx` -- Bob-DONE auto-nav effect: navigate to step 4 when the skip ref is set (read inside the 2s timer to avoid the status→done vs skip-message race), else step 3; clear the ref on thread switch/reset.
- [x] `src/ai_qa/pipelines/artifact_adapter.py` -- add `updated_at: datetime | None` to `PipelineArtifact` + populate in `_to_pipeline_artifact`; `_sort_by_recency` helper (naive→UTC normalised) applied to both groups in `load_approved_test_cases`.
- [x] `tests/test_agents/test_bob.py` (+ `tests/pipelines/test_pipeline_artifact_adapter.py`) -- Bob blank→skip (DONE + `skip_to_sarah`, no adapter/selection persisted); recency ordering. **FE:** App.tsx has no unit-test harness in this repo, so the FE handoff is verified via `npm run typecheck` + ESLint + manual check (per Verification).

**Acceptance Criteria:**
- Given Bob's select-id prompt, when the user clicks OK with a blank input, then Bob transitions DONE with `skip_to_sarah` metadata and the UI navigates to Sarah (step 4), bypassing Mary.
- Given the skip handoff with ≥1 approved test case in the project, when Sarah starts, then it presents the selection panel with the most-recently-updated cases listed first and lets the user confirm which to generate.
- Given a non-empty id, when the user clicks OK, then the existing Bob→Mary flow is unchanged (`mary_selected_id.json` saved, navigate to step 3).
- Given the skip handoff with no approved test cases, when Sarah starts, then it shows the existing "no approved test cases" message and does not proceed.

## Design Notes

- Skip signal is backend-driven (`skip_to_sarah` on Bob's DONE message) consumed by the existing Bob-DONE navigate effect — mirrors how `is_select_id` / navigation already flow. Use a `useRef` alongside state for the flag so the effect doesn't race the status→done flip.
- Navigate 2→4 is already supported: `_handle_navigate` ([websocket.py](src/ai_qa/api/websocket.py)) is step-number driven with no sequential gate and broadcasts `state:"start"`, so Sarah's existing step-4 auto-start fires.
- Sarah needs no behavioral change — `load_approved_test_cases` already returns project-wide approved test cases (current-thread first, then other threads = cross-session/colleague reuse). Only recency ordering is added.

## Verification

**Commands:**
- `uv run pytest tests/test_agents/test_bob.py tests/test_agents/test_sarah.py tests/test_pipelines -p no:base_url --no-cov` -- expected: green
- `uv run ruff check --fix src/ tests/` then `uv run ruff format src/ tests/` -- expected: clean
- `uv run mypy src` -- expected: no new errors
- `cd frontend && npm run typecheck` then `npx vitest run` -- expected: green

**Manual checks:**
- Blank OK → lands on Sarah's test-case selection panel (no Mary); non-empty OK → Mary runs as before.

## Suggested Review Order

**Skip decision (backend entry point)**

- Entry point — blank id branch: go DONE + `skip_to_sarah`, persist nothing (Mary bypassed).
  [`bob.py:1595`](../../src/ai_qa/agents/bob.py#L1595)

- Prompt copy now advertises the blank-to-skip option.
  [`bob.py:2104`](../../src/ai_qa/agents/bob.py#L2104)

**Frontend handoff routing**

- Skip signal captured from Bob's DONE message into a ref.
  [`App.tsx:1025`](../../frontend/src/App.tsx#L1025)

- Auto-nav effect routes 2→4 (Sarah) vs 2→3 (Mary); ref read inside the 2s timer to win the message-ordering race.
  [`App.tsx:1272`](../../frontend/src/App.tsx#L1272)

- Blank submit allowed; non-blank path clears the skip ref (symmetric — review patch).
  [`App.tsx:1632`](../../frontend/src/App.tsx#L1632)

- Select-id panel: empty submit enabled, placeholder + dynamic OK/Skip label.
  [`App.tsx:2558`](../../frontend/src/App.tsx#L2558)

**Reuse ordering (Sarah's source)**

- Recency-first ordering so the previous session's reusable test cases surface on top.
  [`artifact_adapter.py:249`](../../src/ai_qa/pipelines/artifact_adapter.py#L249)

- `_sort_by_recency` helper (naive→UTC normalised) + `updated_at` added to the DTO.
  [`artifact_adapter.py:35`](../../src/ai_qa/pipelines/artifact_adapter.py#L35)

**Tests**

- Bob blank→skip: DONE + `skip_to_sarah`, nothing persisted.
  [`test_bob.py:230`](../../tests/test_agents/test_bob.py#L230)

- Recency ordering of approved test cases.
  [`test_pipeline_artifact_adapter.py:724`](../../tests/pipelines/test_pipeline_artifact_adapter.py#L724)
