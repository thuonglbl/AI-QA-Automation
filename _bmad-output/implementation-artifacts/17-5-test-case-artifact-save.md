# Story 17-5: Test Case Artifact Save

**Story Key:** 17-5-test-case-artifact-save
**Epic:** 17
**Status:** deferred

## Story

As a project member,
I want approved generated test cases saved as project artifacts,
So that Sarah and other project members can use them as shared automation inputs.

## Acceptance Criteria

- Given a generated test case is approved, when Mary saves it, the `ArtifactService` stores it under `projects/{project_id}/test_cases/` and artifact metadata includes source requirement IDs, confidence data, approval status, creator, updater, originating thread, originating agent run, and timestamp.
- Given saved test case artifacts exist, when Sarah requests approved test cases for the selected project, Sarah receives only project-scoped approved test case artifacts through artifact service queries.
- Given saving fails, when Mary reports the failure, partial output is not marked approved or available to Sarah and the user receives a clear retry or recovery message.

## Tasks

- Persist approved test cases via `ArtifactService` into `projects/{project_id}/test_cases/`.
- Validate metadata fields and ensure auditability and thread/agent-run linkage.
- Add error handling and user guidance for save failures.

## Dev Notes

- Do not perform direct SeaweedFS or filesystem writes; use the artifact service abstraction for all storage operations.

## Testing

- Unit tests mocking `ArtifactService` for save success/failure and metadata correctness.
