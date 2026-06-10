# Story 17-1: Test Case Generation Input Selection

**Story Key:** 17-1-test-case-generation-input-selection
**Epic:** 17
**Status:** deferred

## Story

As a QA user,
I want Mary to use approved extracted requirements for the current project/thread,
So that generated test cases are based only on reviewed source material.

## Acceptance Criteria

- Given approved requirement artifacts exist for the selected project, when Mary starts test case generation, Mary loads only project-scoped approved requirements through the `ArtifactService` and does not read direct workspace paths.
- Given the current thread has source requirement artifacts, when Mary prepares generation input, artifacts from the originating thread are prioritized and the user can confirm or adjust selected requirement inputs before generation.
- Given no approved requirement artifact is available, when Mary is asked to generate test cases, Mary blocks generation and explains that Bob extraction and approval must happen first.

## Tasks

- Implement stage to load project-scoped approved requirement artifacts via `ArtifactService`.
- Add UI selection/confirmation for chosen requirement inputs before generation.
- Add validation to block generation when no approved inputs exist and surface actionable guidance.

## Dev Notes

- Use project-scoped artifact queries; preserve originating thread metadata when prioritizing inputs.
- Do not access filesystem paths directly; always route through `ArtifactService`.

## Testing

- Unit tests should mock `ArtifactService` to verify input selection, prioritization, and blocking behavior.
