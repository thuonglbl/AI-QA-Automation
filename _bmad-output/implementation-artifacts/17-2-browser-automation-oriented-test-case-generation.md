# Story 17-2: Browser-Automation-Oriented Test Case Generation

**Story Key:** 17-2-browser-automation-oriented-test-case-generation
**Epic:** 17
**Status:** deferred

## Story

As a QA user,
I want Mary to transform requirements into structured natural-language test cases,
So that Sarah can later convert them into browser automation scripts.

## Acceptance Criteria

- Given approved requirement inputs are selected, when Mary generates test cases, each generated test case includes title, objective, preconditions, test data, steps, expected results, and source requirement references.
- Given a requirement describes browser behavior, when Mary creates test steps, user actions and expected UI outcomes are written clearly enough for Playwright automation; ambiguous UI targets are preserved as warnings rather than invented selectors.
- Given multiple requirements are processed, when generation completes, Mary groups test cases by source requirement or feature area and ensures each test case is independently reviewable.

## Tasks

- Implement natural-language generation templates optimized for Playwright-friendly steps.
- Add warnings for ambiguous UI targets and include source references in generated items.
- Implement grouping metadata and per-test-case reviewability.

## Dev Notes

- Ensure generated output maps to the `test_case` artifact schema.
- Preserve traceability: include source requirement IDs and originating thread/agent run where applicable.

## Testing

- Validate generated test case structure and presence of required fields.
- Verify ambiguous targets generate warnings and do not produce selectors.
