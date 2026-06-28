---
title: 'Bound StageResult warnings/errors so Sarah never crashes at end of script generation'
type: 'bugfix'
created: '2026-06-23'
status: 'done'
baseline_commit: '04be2bbfb0143a7edaf2dd640b62b260a1dbcb88'
context:
  - '{project-root}/project-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/investigations/sarah-stageresult-warnings-overflow-investigation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Sarah generates all N Playwright scripts successfully, then crashes when building the final `StageResult` because the aggregated `warnings` list exceeds the field's `max_length=100` (Pydantic `too_long` ValidationError → "Failed to generate scripts"). The overflow is dominated by per-script `# REVIEW:` markers (e.g. `REVIEW: SSO/session setup required` repeated once per script against an SSO app). The error fires only after the full multi-minute generation, all generated scripts are discarded, and every retry re-runs and deterministically re-fails — the user experiences this as "Sarah errors out and takes very long to continue".

**Approach:** Add one shared, order-preserving dedupe-and-cap-with-rollup helper next to `StageResult` and apply it to the aggregated `warnings`/`errors` lists at the two true aggregation sites *before* constructing the final `StageResult`. Identical messages collapse to their first occurrence (kills the repeated-SSO offender); if more than the cap remain, keep the first `limit-1` and append a single rollup line (`... and N more warnings suppressed`). Leave the `StageResult` model contract unchanged (it still raises if a caller bypasses the helper).

## Boundaries & Constraints

**Always:** Keep the existing degraded-success contract intact — per-item failures stay in `warnings`, the batch stays `success=True`, and the `errors` list stays empty when `success=True` (sarah.py:484-488, 508-511; StageResult model_validator at models.py:66-71). Per-script detail must remain on each `GeneratedScript.warnings` (untouched). Reuse the existing literal cap of 100 via a single shared constant so the field's `max_length` and the helper's limit can never drift. Follow project-context.md (Ruff check+format on src+tests, mypy strict on src, Pyrefly-clean, async/await preserved). Any user-facing string stays English.

**Ask First:** Whether to also add a model-level `@field_validator` that truncates instead of raising (platform-wide hardening for Bob/Mary/Jack). Default = NO for this spec — it would break the documented `test_stage_result_*_max_length` tests and silently change behavior platform-wide; keep it deferred.

**Never:** Do not change the `StageResult` field types, the `max_length=100` value, or the success/errors model_validator. Do not raise the cap. Do not alter the per-script warning scanners (`_extract_review_warnings`, `_detect_brittle_selectors`, etc.) or the prompt. Do not "fix" the pre-existing latent partial-failure path in `script_generator.generate()` where a multi-script batch with some failures sets `success=True` with non-empty `errors` (out of scope — not hit in the single-test-case Sarah flow; record as deferred).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Under cap, distinct | 50 distinct warnings | Returned unchanged (50 items), no rollup | N/A |
| Repeated identical | 200× `"REVIEW: SSO/session setup required"` | Deduped to 1 item, no rollup | N/A |
| Over cap after dedupe | 150 distinct warnings | First 99 kept + `"... and 51 more warnings suppressed"` = 100 items total | N/A |
| Exactly at cap | 100 distinct warnings | Returned unchanged (100 items), no rollup | N/A |
| errors kind | 120 distinct errors | First 99 + `"... and 21 more errors suppressed"` | N/A |
| Bounded list into StageResult | bound output of any of the above | `StageResult(success=True, warnings=bounded)` constructs without ValidationError | N/A |

</frozen-after-approval>

## Code Map

- `src/ai_qa/models.py` -- defines `StageResult` (warnings/errors `max_length=100`); add `STAGE_RESULT_MESSAGE_LIMIT` constant + `bound_stage_messages(...)` helper here; wire the constant into both `Field(max_length=...)`.
- `src/ai_qa/agents/sarah.py:535` -- main generate-loop `StageResult` (the crash site); aggregates `warnings` across all scripts via `.extend` (sarah.py:410/479/488/511).
- `src/ai_qa/pipelines/script_generator.py:200` -- `generate()` per-call `StageResult`; loops `warnings.extend`/`errors.append` over `test_cases` (defense-in-depth; public method callable with a multi-item list).
- `tests/unit/test_models.py:98-113` -- existing max_length tests must keep passing (model unchanged); add new `bound_stage_messages` tests alongside.

## Tasks & Acceptance

**Execution:**
- [x] `src/ai_qa/models.py` -- Add `STAGE_RESULT_MESSAGE_LIMIT = 100` and a module-level `bound_stage_messages(messages: Sequence[str], *, limit: int = STAGE_RESULT_MESSAGE_LIMIT, kind: str = "warnings") -> list[str]` (order-preserving dedupe → if `len > limit`, keep first `limit-1` + append `f"... and {n} more {kind} suppressed"`). Reference the constant in both `errors`/`warnings` `Field(max_length=...)`. Add `Sequence` import from `collections.abc`. -- one shared, tested helper prevents drift and reuse.
- [x] `src/ai_qa/agents/sarah.py` -- At the final generate-loop `StageResult` (~:535) wrap `warnings=bound_stage_messages(warnings)` and `errors=bound_stage_messages(errors, kind="errors")`; import the helper from `ai_qa.models`. -- fixes the actual crash.
- [x] `src/ai_qa/pipelines/script_generator.py` -- At the `generate()` return (~:200) wrap `warnings=bound_stage_messages(warnings)` and `errors=bound_stage_messages(errors, kind="errors")`; import the helper. -- defense-in-depth for multi-item callers. Do NOT change the `success` computation.
- [x] `tests/unit/test_models.py` -- Add unit tests covering every I/O Matrix row, including that the bounded output constructs a `StageResult` without raising and never exceeds the cap.

**Acceptance Criteria:**
- Given a Sarah batch whose aggregated warnings exceed 100 (e.g. 9 SSO scripts), when generation finishes, then `StageResult` constructs successfully with `success` reflecting whether any scripts were generated, `warnings` length ≤ 100, and a rollup line present when items were suppressed — no `too_long` ValidationError.
- Given identical repeated warnings, when bounded, then duplicates collapse to a single entry so common SSO runs stay well under the cap.
- Given the model is unchanged, when the existing `test_stage_result_errors_list_max_length` / `test_stage_result_warnings_list_max_length` run, then they still raise `ValidationError` (no contract regression).

## Design Notes

Why aggregation-site + shared helper, not a model `@field_validator`: a truncating validator would silently change behavior for every stage and break the two documented `*_max_length` tests that assert raising is intended. Bounding at the aggregation sites keeps the model's strict contract as a backstop while making Sarah's pipeline resilient.

Helper sketch (models.py):

```python
STAGE_RESULT_MESSAGE_LIMIT = 100

def bound_stage_messages(
    messages: Sequence[str], *, limit: int = STAGE_RESULT_MESSAGE_LIMIT, kind: str = "warnings"
) -> list[str]:
    seen: set[str] = set()
    deduped = [m for m in messages if not (m in seen or seen.add(m))]
    if len(deduped) <= limit:
        return deduped
    kept = deduped[: limit - 1]
    kept.append(f"... and {len(deduped) - len(kept)} more {kind} suppressed")
    return kept
```

(Use an explicit loop if the `seen.add` walrus trips Ruff/readability — keep it order-preserving either way.)

## Verification

**Commands:**
- `uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/` -- expected: clean, no diff on re-run.
- `uv run mypy src` -- expected: no new errors.
- `uv run pytest tests/unit/test_models.py -p no:base_url` -- expected: existing max_length tests pass + new bound_stage_messages tests pass.
- `uv run pytest` -- expected: full suite green (Sarah/script_generator suites unaffected).

**Manual checks (if no CLI):**
- Re-run Sarah on the PTP rating-stars test set (≥9 cases) against the INT SSO environment; generation completes and saves scripts instead of failing with `StageResult warnings ... too_long`.

## Suggested Review Order

**Core fix — bounded message helper**

- Entry point: order-preserving dedupe → cap-with-rollup; the whole design intent
  [`models.py:33`](../../src/ai_qa/models.py#L33)

- Single shared constant wired into both Field caps so limit and `max_length` can't drift
  [`models.py:92`](../../src/ai_qa/models.py#L92)

**Aggregation sites (where the crash fired)**

- Sarah's batch generate loop — the actual crash site; aggregated warnings now bounded
  [`sarah.py:539`](../../src/ai_qa/agents/sarah.py#L539)

- `ScriptGenerator.generate()` return — defense-in-depth for any multi-item caller
  [`script_generator.py:204`](../../src/ai_qa/pipelines/script_generator.py#L204)

**Tests**

- Edge-case coverage for the helper — one test per I/O Matrix row + dedupe order + StageResult construction
  [`test_models.py:121`](../../tests/unit/test_models.py#L121)
