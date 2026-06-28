---
baseline_commit: current
---
# Story 25.5: Wire Auto-Login into Sarah Explore and Jack Run

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a project user,
I want Sarah's exploration and Jack's runs to dynamically parse the selected test cases to extract ONLY the specific roles actually required, and to resolve their session via auto-login (using my secure user-scoped test credentials). The FE `SarahInputsForm` should prompt me to enter credentials only for those missing test roles,
so that script generation and execution authenticate securely and efficiently without over-asking for unused roles.

## Acceptance Criteria

1. Implement dynamic role extraction in the backend (from selected test cases) so that Sarah and Jack only require sessions for roles actually involved in the current execution.
2. Update `SarahInputsForm` to display inputs ONLY for the missing test credentials of the required roles.
3. Wire the new user-scoped auto-login credential resolution into the Sarah and Jack execution flows.
4. Ensure the auto-login mechanism passes the correct `login_type` and `login_hint` to the browser-use prompt or playwright script.

## Tasks / Subtasks

- [ ] Task 1: Backend Dynamic Role Filtering
  - [ ] Subtask 1.1: Parse test cases in Sarah/Jack endpoints to identify required roles.
- [ ] Task 2: Frontend Updates
  - [ ] Subtask 2.1: Update `SarahInputsForm` to dynamically query missing roles and prompt user.
- [ ] Task 3: Backend Session Resolution
  - [ ] Subtask 3.1: Wire the auto-login resolution logic to fetch user-scoped secrets instead of project-level ones.
  - [ ] Subtask 3.2: Pass `login_type` and `login_hint` to the login routine.

## Dev Notes

- **Source tree components to touch**: `src/ai_qa/api/sessions.py`, `src/ai_qa/browser/login.py`, `src/ai_qa/frontend/src/components/` (specifically `SarahInputsForm.tsx`).

### Project Structure Notes

- Integrates with existing role and environment concepts.

### References

- [Source: epics.md] Epic 25 description.
- [Source: sprint-change-proposal-2026-06-27-test-credentials.md]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
