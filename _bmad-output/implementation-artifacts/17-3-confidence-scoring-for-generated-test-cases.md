# Story 17-3: Confidence Scoring for Generated Test Cases

**Story Key:** 17-3-confidence-scoring-for-generated-test-cases
**Epic:** 17
**Status:** deferred

## Story

As a QA user,
I want Mary to score confidence for generated test cases,
So that low-confidence outputs receive explicit review before script generation.

## Acceptance Criteria

- Given Mary generates a test case, when quality analysis runs, the test case receives a confidence score or level and the confidence rationale is stored with the generated item.
- Given source content is incomplete, vague, contradictory, or includes unresolved Bob warnings, when Mary scores the generated test case, the test case is flagged as low confidence and the specific causes are shown to the reviewer.
- Given low-confidence test cases exist, when the user attempts to proceed to Sarah, the workflow requires explicit approval or regeneration decision for those test cases.

## Tasks

- Implement confidence scoring function (heuristics + model-based signals) and persist rationale.
- Surface confidence and rationale in the Mary review UI and artifact metadata.
- Enforce workflow gate preventing automatic progression of low-confidence items to script generation.

## Dev Notes

- Score should be numeric and include categorical levels (high/medium/low).
- Rationale must avoid including secrets or raw LLM responses that could leak provider data.

## Testing

- Unit tests for scoring logic covering high/medium/low samples.
- Integration tests ensuring gating prevents progression for low-confidence items.
