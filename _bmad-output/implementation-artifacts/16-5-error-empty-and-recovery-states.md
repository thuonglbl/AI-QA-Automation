---
baseline_commit: d97e58533b04901b688a1c04f24032cfc8dc0e53
---
# Story 16.5: Error, Empty, and Recovery States

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> The 3-part error format (UX-DR12) and several empty states already exist. This story is an **audit-and-fill** pass: ensure every dependent step explains a missing prerequisite, every failure mode is actionable + secret-safe, and every empty panel guides the next action.

## Story

As a QA user,
I want clear UX for missing data, errors, and recovery paths,
so that I can resolve issues without guessing.

## Acceptance Criteria

1. **Missing-prerequisite guidance.** Given a required setup item is missing, when the user reaches a dependent workflow step, then the UI explains the missing prerequisite and provides the next recovery action.

2. **Actionable, secret-safe failures.** Given an operation fails due to permission, missing credentials, unavailable MCP tools, provider/model failure, validation failure, or artifact-save failure, when the error is shown, then the message is actionable, user-safe, and does NOT expose secrets or internal stack traces.

3. **Helpful empty states.** Given no project, thread, artifact, review item, or execution report exists, when the relevant panel is opened, then an appropriate empty state explains what to do next (not a bare blank/"Empty").

## Tasks / Subtasks

- [ ] **Task 1 — Enumerate dependent steps + their missing-prerequisite messaging (AC: 1)**
  - [ ] Walk each step's preconditions and confirm a clear "what's missing + next action" message: Alice provider/model not configured → CONFIG_ERROR path; Bob with no MCP/credentials; Mary with no approved requirements; Sarah with no approved test cases (and the inputs-request for target URL/Chrome); Jack with no approved scripts or no captured session for a role.
  - [ ] Confirm the FE error map already covers CONFIG_ERROR ("complete the AI provider setup") ([frontend/src/lib/error-messages.ts](frontend/src/lib/error-messages.ts)). Fill any step whose missing-prerequisite path is silent.

- [ ] **Task 2 — Verify failure messages are actionable + secret-safe (AC: 2)**
  - [ ] Confirm backend errors flow through `BaseAgent._format_error_message` (UX-DR12 three-part) ([src/ai_qa/agents/base.py](src/ai_qa/agents/base.py)) and FE maps backend codes/messages → `ErrorInfo` via `mapBackendError` ([frontend/src/lib/error-messages.ts](frontend/src/lib/error-messages.ts)), rendered by `ErrorFeedback` ([frontend/src/components/ErrorFeedback.tsx](frontend/src/components/ErrorFeedback.tsx)).
  - [ ] Audit the six failure classes in the AC (permission / missing credentials / unavailable MCP tools / provider-model failure / validation failure / artifact-save failure) — each maps to an actionable message with a recovery step.
  - [ ] **Secret-safety:** confirm NO path surfaces `api_key`/`auth_token`/`Authorization`/`X-Api-Key` or a raw stack trace. Add a leak-canary assertion (mirror Sarah's in [[story-16-12-sarah-auth-bug]]) for any error path touched here.

- [ ] **Task 3 — Upgrade bare empty states to guided ones (AC: 3) [PRIMARY GAP]**
  - [ ] Replace bare "Empty" / minimal placeholders with contextual guidance: empty artifact folder, no review item ("No scripts to review." / "No test case selected." → add "what to do next"), no execution report, no thread, no project (the no-access state already exists in `App.tsx`).
  - [ ] Confirm the stale-thread-access recovery message and the no-project-access message remain (App.tsx). Keep all copy English-only and user-safe.

- [ ] **Task 4 — Tests (AC: 1, 2, 3)**
  - [ ] Extend `ErrorFeedback.test.tsx` + error-map tests for the failure classes; add a leak-canary test on any backend error path edited.
  - [ ] Add tests that a dependent step with a missing prerequisite shows the explanation + recovery action, and that empty panels render guidance.
  - [ ] `npm run typecheck` + `npm run lint` + `npm test`; backend `uv run pytest` if a backend error path changed.

## Dev Notes

### What already exists (do not rebuild)

- **Backend UX-DR12** — `BaseAgent._format_error_message` produces the three-part **What happened / Why / What to do** markdown.
- **FE error model** — `ErrorInfo` (type/what/why/whatToDo), `error-messages.ts` map (MCP_TIMEOUT, LLM_FAILURE, NETWORK_ERROR, CONFIG_ERROR, UNKNOWN_ERROR) + `mapBackendError()`; rendered by `ErrorFeedback` (role="alert", autofocus retry, sr-only type).
- **Existing empty/recovery states** — no-project-access and stale-thread messages in `App.tsx`; per-panel "No X to review" placeholders; `ExecutionResultDetail` "(not available)" graceful degradation; `ProjectSidebar` empty-folder "Empty".
- **Secret-safety convention** — leak-canary tests across output channels; resolved secrets never logged/messaged/stored ([[story-16-12-sarah-auth-bug]], [[project-context]]).

### The gaps this story closes

1. **Bare empty states** (AC3) — "Empty"/minimal placeholders should explain the next action.
2. **Missing-prerequisite coverage** (AC1) — ensure every dependent step (not just Alice config) explains what's missing.
3. **Failure-class completeness + leak-canary** (AC2) — verify all six classes are actionable and assert secret-safety on touched paths.

### Source tree components to touch

- `frontend/src/lib/error-messages.ts` — **READ / VERIFY** (extend mapping only if a class is unmapped).
- `frontend/src/components/ErrorFeedback.tsx` — **READ / VERIFY**.
- `frontend/src/components/agents/*ReviewPanel*.tsx`, `SplitPanel.tsx`, `JackExecutionReport.tsx`, `conversations/ProjectSidebar.tsx`, `App.tsx` — **UPDATE** empty/missing-prerequisite copy where bare.
- `src/ai_qa/agents/base.py` + per-agent precondition gates — **READ ONLY** unless a missing-prerequisite message is absent server-side.
- Tests under `frontend/src/components/__tests__/` + `tests/` (leak-canary) — **UPDATE/ADD**.

### Current behavior to PRESERVE (regression guardrails)

- The three-part UX-DR12 format and the FE `ErrorInfo` shape — extend, don't replace.
- Secret-safety: never surface keys/tokens/headers or raw stack traces; resolve secrets at runtime only.
- Sarah's degraded-success placeholders + skip-only gate ([[story-16-12-sarah-auth-bug]]).
- App-UI-English-only for all messages ([[app-ui-english-only]]).

### Testing standards summary

- FE: `getByRole('alert')`, assert the three parts + retry. Backend leak-canary: force a failure, assert no `sk-`/key/`Authorization` substrings in message content or broadcast metadata (mirror `test_auth_failure_surfacing_is_secret_safe`).
- No bare `pytest.raises(Exception)` — specific type + `match=`.

### Project Structure Notes

- Mostly FE copy + tests; backend touched only if a server-side missing-prerequisite message is absent. No schema/migration; no new dependencies.

### References

- Epic + ACs: [epics.md#Story-16.5](_bmad-output/planning-artifacts/epics.md:1788)
- Coding/testing rules: [project-context.md](project-context.md)
- Related: [16-2](16-2-stateful-workflow-controls.md), [16-3](16-3-processing-and-progress-indicators.md), [[story-16-12-sarah-auth-bug]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
