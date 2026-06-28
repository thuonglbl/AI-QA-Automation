---
baseline_commit: d97e58533b04901b688a1c04f24032cfc8dc0e53
---
# Story 16.2: Stateful Workflow Controls

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Builds on the [16-1 conversational shell](16-1-agent-based-conversational-shell.md). The 5-state input-area state machine already exists in `ChatInputArea`; this story **audits it against the ACs and closes the disabled-with-reason gap**, not a rebuild.

## Story

As a QA user,
I want the input area to change based on the current workflow state,
so that I see only relevant actions at each pipeline step.

## Acceptance Criteria

1. **Source-input controls when Bob is active.** Given the workflow is waiting for source input, when Bob is active, then the input area supports Confluence URL input and optional Jira input where enabled (driven by `inputConfig.fields`).

2. **Review-decision controls when a review is pending.** Given the workflow is waiting for review, when requirements, test cases, scripts, or execution reports require a decision, then the input area shows the relevant approve, reject, feedback, regenerate, run, or export actions for that step.

3. **Unavailable actions are disabled with a reason.** Given an action is unavailable because required state is missing, when the control is shown, then it is disabled with an explanatory reason (tooltip/inline text) rather than silently failing or disappearing without explanation.

## Tasks / Subtasks

- [ ] **Task 1 — Audit the input-area state machine against AC1/AC2 (AC: 1, 2)**
  - [ ] Confirm `ChatInputArea` renders the five states `start` / `processing` / `review` / `reject_feedback` / `done` with the correct controls per state ([frontend/src/components/ChatInputArea.tsx](frontend/src/components/ChatInputArea.tsx)).
  - [ ] Confirm the `start` state renders fields from `inputConfig.fields` (text/url/password/textarea) including Bob's Confluence URL + optional Jira/MCP fields (from the `AGENTS.Bob.inputConfig` in `frontend/src/types/pipeline.ts`).
  - [ ] Confirm review-state actions for each agent: Bob/Mary/Sarah approve+reject(+feedback)+regenerate; Jack run/export. Map each AC2 action to its rendering site (`ChatInputArea` review/done states + the per-agent review panels). Record any missing action as a gap subtask.

- [ ] **Task 2 — Verify state is driven by backend status, not guessed on the FE (AC: 1, 2)**
  - [ ] Confirm the input state derives from `metadata.state` / pipeline status flowing through `usePipelineState.updateFromMessage` and the per-agent metadata handlers in [frontend/src/App.tsx](frontend/src/App.tsx) (e.g. `bob_start`, `confirm_parent`, `clarify_request`, `test_cases_review`, script/exec review).
  - [ ] Confirm step-appropriate controls only — no test-case actions render while Bob is active, etc.

- [ ] **Task 3 — Close the disabled-with-reason gap (AC: 3) [PRIMARY GAP]**
  - [ ] Today the `start` state disables the primary button with a `disabledReason` tooltip when required fields are empty (`ChatInputArea` start state). Verify this and confirm coverage extends to the OTHER states where an action can be unavailable: review actions blocked by missing prerequisites (e.g. approve disabled when no item selected; Jack run disabled when a role has no captured session; export disabled before a run completes).
  - [ ] Where an action is currently hidden or silently no-ops when state is missing, change it to render disabled + an explanatory reason (tooltip or inline helper text), consistent with the existing `disabledReason` pattern. Keep messages user-safe and English-only.
  - [ ] Cross-check the Jack "block when one role has no session" path — surface the reason in the control, not only as a thrown error (coordinate with [16-5 error/recovery states](16-5-error-empty-and-recovery-states.md)).

- [ ] **Task 4 — Tests (AC: 1, 2, 3)**
  - [ ] Extend `frontend/src/components/__tests__/ChatInputArea.test.tsx`: each state renders its expected controls; required-field gating disables Start with a reason; a review action with a missing prerequisite renders disabled + reason.
  - [ ] Add an App-level (or panel-level) test for at least one review action's disabled-with-reason path.
  - [ ] `npm run typecheck` + `npm run lint` + `npm test` green.

## Dev Notes

### What already exists (do not rebuild)

- **`ChatInputArea`** implements a 5-state machine via per-state render functions: `start` (form fields from `inputConfig`, validation, `disabledReason` tooltip, focus management), `processing` (disabled "Agent is working…"), `review` (Approve/Reject + optional Prev/Next item navigation), `reject_feedback` (textarea + char counter), `done` (Continue / Completed).
- **State transitions** are orchestrated in `App.tsx` and driven by backend status + per-agent `metadata.type` handlers; `usePipelineState.updateFromMessage` maps `metadata.state` → status.
- **Bob's input fields** (Confluence URL, optional Jira, MCP PAT with localStorage prefill) come from `AGENTS.Bob.inputConfig.fields`.
- **Per-agent review panels** render the rich decision surfaces: `MaryReviewPanel`, `SarahScriptReviewPanel`, `SplitPanel`/`BobRequirementReview`, `JackExecutionReport`.

### The gap this story closes

The disabled-with-reason pattern (AC3) is implemented for the `start` state's required-field gating but is **not uniformly applied** to review/run/export actions that can be unavailable due to missing state. Make those controls render disabled + reason instead of vanishing or silently failing. Reuse the existing `disabledReason` + tooltip pattern; do not invent a new mechanism.

### Source tree components to touch

- `frontend/src/components/ChatInputArea.tsx` — **UPDATE** (extend disabled-with-reason coverage; verify state controls).
- `frontend/src/App.tsx` — **READ / VERIFY** state derivation + metadata handlers; minimal edit if a review action lacks a reason.
- `frontend/src/components/agents/{MaryReviewPanel,SarahScriptReviewPanel,JackExecutionReport}.tsx` + `SplitPanel.tsx` — **READ / VERIFY** the action surfaces; edit only where an unavailable action needs a reason.
- `frontend/src/types/pipeline.ts` — **READ** the `ChatInputAreaProps` + `AGENTS` input config.
- `frontend/src/components/__tests__/ChatInputArea.test.tsx` — **UPDATE**.

### Current behavior to PRESERVE (regression guardrails)

- The Bob inputs flow (Confluence URL + Jira + MCP PAT prefill from localStorage) — do not change field semantics.
- Per-item review navigation (Mary/Sarah) and the skip-only failure placeholders (script `error_message` gate) — do not make placeholders approvable ([[story-16-12-sarah-auth-bug]]).
- Sarah's inputs-request re-entry (bsg-5/bsg-6: target URL + Chrome path / CDP URL) must keep working.
- App-UI-English-only for all control labels and reasons ([[app-ui-english-only]]).

### Testing standards summary

- Vitest 4 + RTL; `getByRole('button', { name })`, `getByLabelText`. Assert `toBeDisabled()` and that the reason text/tooltip is present.
- Tooltip is mocked in `src/test-setup.ts` to pass children through — assert the reason via its accessible text, not a hover.

### Project Structure Notes

- FE-only; no schema/migration; no new dependencies. Stays inside `frontend/src/`.

### References

- Epic + ACs: [epics.md#Story-16.2](_bmad-output/planning-artifacts/epics.md:1727)
- Coding/testing rules: [project-context.md](project-context.md)
- Related: [16-1](16-1-agent-based-conversational-shell.md), [16-5](16-5-error-empty-and-recovery-states.md), [[story-16-12-sarah-auth-bug]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
