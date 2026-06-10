# Story 17-4: Mary Review Workflow

**Story Key:** 17-4-mary-review-workflow
**Epic:** 17
**Status:** deferred

## Story

As a QA user,
I want to review, approve, reject, and give feedback on Mary’s generated test cases,
So that only validated natural-language test cases become script-generation inputs.

## Acceptance Criteria

- Given Mary generated one or more test cases, when the review UI opens, the user can review each test case with source requirement references and confidence warnings visible.
- Given the user approves a generated test case, when approval is submitted, the test case becomes eligible for Sarah script generation and the approval is recorded with user and timestamp metadata.
- Given the user rejects a generated test case with feedback, when feedback is submitted, Mary regenerates or revises the affected test case where possible and prior rejected output is not treated as approved input.

## Tasks

- Implement review UI (per-test-case view) showing source references, confidence, and edit actions.
- Add approve/reject actions with feedback capture and audit metadata.
- Wire approvals to mark artifacts as eligible for Sarah and persist approval metadata.

## Dev Notes

- Keep review actions idempotent and auditable; store user/timestamp and originating thread/agent run.
- Re-generation should be explicit and based on captured feedback.

## Testing

- E2E tests simulating approve/reject flows and verifying artifact state transitions.
