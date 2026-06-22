---
baseline_commit: d97e58533b04901b688a1c04f24032cfc8dc0e53
---
# Story 16.3: Processing and Progress Indicators

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Builds on [16-1](16-1-agent-based-conversational-shell.md) / [16-2](16-2-stateful-workflow-controls.md). Progress UI mostly exists (`ProcessingIndicator`, `AgentTopBar` status badge, `StepDots`); the **named gap is that `ProcessingIndicator` hardcodes "Alice"** and there is no explicit operation label / cancellation state. This story makes progress agent-accurate and verifies non-blocking behavior.

## Story

As a QA user,
I want clear progress indicators during long-running agent work,
so that I know what is happening without losing context.

## Acceptance Criteria

1. **Active agent + operation label + non-blocking state.** Given an agent starts a long-running operation, when processing begins, then the UI shows the active agent (correct name, not hardcoded), a current operation label, and a non-blocking progress state.

2. **Live progress without resetting input/scroll.** Given progress updates arrive over WebSocket, when the operation advances, then step progress, status text, and current agent state update without resetting chat input or scroll position.

3. **Terminal complete/fail/cancel states.** Given an operation completes, fails, or is cancelled, when the terminal status is received, then the UI shows a clear completion, failure, or cancellation state with the next available actions.

## Tasks / Subtasks

- [ ] **Task 1 — Make the processing indicator agent-accurate (AC: 1) [PRIMARY GAP]**
  - [ ] `ProcessingIndicator` currently hardcodes the label "Alice" ([frontend/src/components/ProcessingIndicator.tsx](frontend/src/components/ProcessingIndicator.tsx)). Make the agent name a prop sourced from the active agent (`AGENTS[currentAgent]`), defaulting safely.
  - [ ] Render the current operation label from `metadata.processingMessage` (already plumbed through `usePipelineState.updateFromMessage` → `processingMessage`) or the agent's status text; show the agent name + operation label together.
  - [ ] Confirm the indicator remains non-blocking (renders alongside chat history; input area shows the `processing` state from 16-2).

- [ ] **Task 2 — Verify live progress preserves input + scroll (AC: 2)**
  - [ ] Confirm WS progress updates update `StepDots` (current/completed) and `AgentTopBar` status badge without remounting the chat input or forcing a scroll reset (`ChatArea` only auto-scrolls when the user is at the bottom).
  - [ ] Confirm `processingMessage` / status updates do not clear the user's in-progress textarea content. Add a regression test if not covered.

- [ ] **Task 3 — Verify/complete terminal states (AC: 3)**
  - [ ] Confirm complete (`done`/`completed` → Continue/Completed control), and failure (error bubble + `ErrorFeedback` retry) terminal states render with next actions.
  - [ ] **Cancellation:** research found no cancellation UI today. Determine whether a cancel/terminal-cancelled status exists on the backend pipeline. If a cancel path exists, render a clear cancelled state + next action; if it does not exist, document that AC3's "cancelled" arm is N/A for this build in Completion Notes and cover only complete/fail (do NOT invent a backend cancel mechanism in this FE story).

- [ ] **Task 4 — Tests (AC: 1, 2, 3)**
  - [ ] Extend `ProcessingIndicator` tests: renders the active agent's name (e.g. "Bob", not "Alice") and the operation label.
  - [ ] Add a test that a progress update does not clear chat input or jump scroll when the user has scrolled up.
  - [ ] Add tests for the terminal complete + failure states' next-action affordances.
  - [ ] `npm run typecheck` + `npm run lint` + `npm test` green.

## Dev Notes

### What already exists (do not rebuild)

- **`ProcessingIndicator`** — three bouncing dots + a message label, but the agent label is hardcoded "Alice" (the bug this story targets). Props: `message`, `isActive`, `className`.
- **`AgentTopBar` status badge** — `start` / `processing` (amber + spinner) / `review_request` (blue eye) / `done`/`completed` (green check).
- **`StepDots`** — completed/current/pending across 5 steps.
- **`usePipelineState`** — extracts `metadata.processingMessage` into `processingMessage` and `metadata.state` into `status`; derives `currentAgent`/`currentStep` from `agentName`.
- **`ChatArea`** — auto-scrolls only when at the bottom; floating "New message" pill otherwise (so progress updates do not yank scroll).
- **Failure terminal state** — `ChatMessage` renders `error` type via `ErrorFeedback` with a retry button.

### The gaps this story closes

1. **Hardcoded "Alice"** in `ProcessingIndicator` — make it agent-accurate (AC1). This is the named Epic-16 gap.
2. **Operation label** — surface `processingMessage` next to the agent name (AC1).
3. **Cancellation state** — likely absent; handle per Task 3 (verify backend, render if present, else document N/A). Do not fabricate a cancel backend.

### Source tree components to touch

- `frontend/src/components/ProcessingIndicator.tsx` — **UPDATE** (agent-name prop + operation label).
- `frontend/src/components/ChatMessage.tsx` — **READ / VERIFY** (it renders the indicator for `processing` messages; pass through the agent name).
- `frontend/src/App.tsx` — **READ / VERIFY** wiring of `currentAgent` + `processingMessage` into the indicator.
- `frontend/src/hooks/usePipelineState.ts` — **READ** (`processingMessage`, `status` derivation).
- `src/ai_qa/agents/*.py` — **READ ONLY**: confirm what each agent sends as `processingMessage`/status; confirm whether any cancellation/terminal-cancelled status is emitted.
- `frontend/src/components/__tests__/ProcessingIndicator.test.tsx` (+ App/ChatArea tests) — **UPDATE/ADD**.

### Current behavior to PRESERVE (regression guardrails)

- Non-blocking indicator (must not block the chat or input).
- `ChatArea` scroll discipline (only auto-scroll at bottom) — do not force scroll on progress updates.
- The pure-metadata carrier WS gate ([[message-timestamps-feature]]).
- App-UI-English-only ([[app-ui-english-only]]).

### Testing standards summary

- Vitest 4 + RTL; assert the rendered agent name + operation label text. Use `vi.spyOn` fetch / `importOriginal` per [[project-context]].
- For the scroll/input-preservation test, simulate a progress message arriving while the textarea has content and assert the content is intact.

### Project Structure Notes

- FE-only; no schema/migration; no new dependencies.

### References

- Epic + ACs: [epics.md#Story-16.3](_bmad-output/planning-artifacts/epics.md:1747)
- Coding/testing rules: [project-context.md](project-context.md)
- Related: [16-1](16-1-agent-based-conversational-shell.md), [16-2](16-2-stateful-workflow-controls.md), [16-5](16-5-error-empty-and-recovery-states.md), [[message-timestamps-feature]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
