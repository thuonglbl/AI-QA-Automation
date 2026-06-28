# Investigation: Sarah fails at end of script generation — StageResult.warnings exceeds 100-item cap

## Hand-off Brief

1. **What happened.** Sarah generates all N Playwright scripts successfully, then crashes when building the final `StageResult` because the aggregated `warnings` list (112 items, dominated by per-script `# REVIEW:` markers) exceeds the field's `max_length=100` — a Pydantic `too_long` ValidationError surfaced to the user as "Failed to generate scripts" (**Confirmed**).
2. **Where the case stands.** Root cause Confirmed and deterministic: the more scripts and the more SSO/brittle/ambiguity markers per script, the more certain the overflow. Affects any large batch against an authenticated app (here: 9 rating-stars scripts vs `int-progresstalkapplication.corpnet.local`).
3. **What's needed next.** Cap/dedupe/summarize the aggregated `warnings` list before constructing the final `StageResult` in Sarah's generate loop (and the parallel paths). Trivial-to-moderate fix — recommend routing to `bmad-quick-dev`.

## Case Info

| Field            | Value                                                                                   |
| ---------------- | --------------------------------------------------------------------------------------- |
| Ticket           | N/A                                                                                     |
| Date opened      | 2026-06-22                                                                              |
| Status           | Active                                                                                  |
| System           | Win11; backend Python 3.14 / Pydantic 2.12; on-prem LLM; project PTP (SSO app)          |
| Evidence sources | UI screenshot (error text + timeline), source code (`models.py`, `sarah.py`, `script_generator.py`, `prompts/script_generation.py`) |

## Problem Statement

User report (Thuong): "Sarah có lúc bị error, phải rất lâu mới tiếp tục được" — Sarah sometimes errors out, and it takes a very long time before it can continue.

Screenshot shows Sarah at Step 4 of 5, after "Generating script 8 of 9..." (21:56:33) and "Generating script 9 of 9..." (21:57:14), then at 21:58:01 a friendly-wrapped error:

> **What happened:** Failed to generate scripts: 1 validation error for StageResult warnings List should have at most 100 items after validation, not 112 `[type=too_long, input_value=['REVIEW: SSO/session set...dividual star elements'], input_type=list]`

## Evidence Inventory

| Source                                    | Status    | Notes                                                                                  |
| ----------------------------------------- | --------- | -------------------------------------------------------------------------------------- |
| UI screenshot (error + timeline)          | Available | Exact ValidationError text + per-script timestamps                                     |
| `src/ai_qa/models.py`                     | Available | `StageResult.warnings` / `errors` both `max_length=100`                                |
| `src/ai_qa/agents/sarah.py`               | Available | Generate loop aggregates warnings unbounded; final `StageResult` at :535               |
| `src/ai_qa/pipelines/script_generator.py` | Available | `_postprocess_script` builds per-script `all_warnings` from 5 scanners                  |
| `src/ai_qa/prompts/script_generation.py`  | Available | Prompt instructs LLM to emit `# REVIEW:` markers, incl. `REVIEW: SSO/session setup`    |
| Backend runtime logs for this run         | Missing   | Would confirm exact per-script marker counts; not required (error text is conclusive)  |

## Investigation Backlog

| # | Path to Explore                                                              | Priority | Status | Notes                                                              |
| - | --------------------------------------------------------------------------- | -------- | ------ | ----------------------------------------------------------------- |
| 1 | Confirm `StageResult.warnings` constraint                                   | High     | Done   | `models.py:52-56`, `max_length=100`                               |
| 2 | Confirm Sarah aggregates warnings unbounded                                 | High     | Done   | `sarah.py:410,479,535`                                            |
| 3 | Confirm per-script warning source = REVIEW + 4 scanners                     | High     | Done   | `script_generator.py:355-367`                                     |
| 4 | Check regenerate path + parallel script_generator loop for same defect      | Medium   | Done   | `sarah.py:547+ (regen)`, `script_generator.py:155-203` — same shape |
| 5 | Confirm `errors` list shares the same 100-cap exposure                      | Low      | Done   | `models.py:47-50` — `errors` also `max_length=100`               |

## Timeline of Events

| Time (run)  | Event                                          | Source     | Confidence |
| ----------- | ---------------------------------------------- | ---------- | ---------- |
| 21:56:33    | "Generating script 8 of 9..."                  | screenshot | Confirmed  |
| 21:57:14    | "Generating script 9 of 9..." (~41s/script)    | screenshot | Confirmed  |
| 21:58:01    | StageResult `too_long` ValidationError (112>100) shown to user | screenshot | Confirmed  |

## Confirmed Findings

### Finding 1: `StageResult.warnings` is hard-capped at 100 items

**Evidence:** `src/ai_qa/models.py:52-56`

```python
warnings: list[str] = Field(
    default_factory=list,
    max_length=100,
    description="Non-fatal warnings (max 100 items)",
)
```

**Detail:** `errors` (`models.py:47-50`) has the same `max_length=100`. Pydantic enforces this at construction time; exceeding it raises `ValidationError(type=too_long)`. Unit tests `tests/unit/test_models.py:107-113` codify the 100-item limit as intended behavior.

### Finding 2: Sarah aggregates per-script warnings into one unbounded list, then constructs StageResult once at the end

**Evidence:** `src/ai_qa/agents/sarah.py:410`, `:479`, `:535-541`

**Detail:** The generate loop (`sarah.py:428-541`) starts `warnings: list[str] = []` (`:410`), and for each of the N test cases does `warnings.extend(result.warnings)` (`:479`) plus failure placeholders (`:488`, `:511`). After the loop it builds `StageResult(success=..., warnings=warnings, ...)` (`:535`) — with **no length cap, dedupe, or summarization**. The construction is the only place the cap is checked, so the failure is deferred to the very end of generation.

### Finding 3: Per-script warnings are dominated by `# REVIEW:` markers, one or more per authenticated/ambiguous step

**Evidence:** `src/ai_qa/pipelines/script_generator.py:355-367`; `src/ai_qa/prompts/script_generation.py:94,100,103`

```python
all_warnings: list[str] = (
    self._extract_review_warnings(script_content)      # every "# REVIEW:" / "# TODO:" line
    + self._detect_brittle_selectors(script_content)   # one per brittle CSS/XPath
    + self._detect_assertion_gaps(script_content, test_case)
    + self._detect_hardcoded_secrets(script_content)
    + self._detect_auth_setup_needed(script_content, test_case)
)
```

**Detail:** The prompt *requires* the LLM to emit `# REVIEW: SSO/session setup required before execution` for authenticated apps and `# REVIEW:` for every ambiguous assertion / brittle selector. The failing run targets `int-progresstalkapplication.corpnet.local` (an SSO app) and tests "rating stars … individual star elements" — exactly the multi-element, ambiguous-assertion shape that produces many markers per script. The truncated input in the error (`['REVIEW: SSO/session set...dividual star elements']`) confirms the overflowing list is composed of these REVIEW strings.

## Deduced Conclusions

### Deduction 1: Overflow is deterministic and scales with batch size × markers-per-script

**Based on:** Findings 1, 2, 3.

**Reasoning:** N scripts × (REVIEW + brittle + gap + secret + auth) markers, flattened with no cap, against a fixed limit of 100. For an SSO app with ambiguous multi-element assertions, ~12+ markers/script is plausible; 9 scripts → ~108–120 > 100.

**Conclusion:** Any sufficiently large batch (or marker-heavy test set) against an authenticated app will reproduce this. 112 in this run is just over the line; bigger test sets fail harder.

### Deduction 2: "Takes very long to continue" = wasted full run + deterministic re-failure, not a slow-recovery bug

**Based on:** Findings 1-2 + timeline.

**Reasoning:** The error only fires after all 9 LLM script calls complete (~40s each ≈ 6-7 min). Because the crash happens at `StageResult(...)` *before* the result is returned/saved, every generated script is discarded. Re-running re-does the full ~7-min generation and hits the identical deterministic overflow. The user perceives this as "very long to continue" — in fact it is a hard block that cannot succeed by retrying.

## Hypothesized Paths

### Hypothesis 1: User's premise that it is intermittent ("có lúc")

**Status:** Refuted (as worded).

**Theory:** The failure is random/intermittent.

**Supporting indicators:** User said "có lúc" (sometimes); earlier runs (19:04, "7 scripts" saved) succeeded.

**Would confirm:** A run with the same inputs that succeeds.

**Would refute:** Deterministic dependence on batch size / marker count.

**Resolution:** Refuted as "random". It is *conditionally* deterministic: it appears intermittent only because it depends on the test set (script count × markers/script). Small batches or marker-light tests stay under 100 and succeed; large/SSO/ambiguous batches cross 100 and fail every time. The 19:04 success had a different (smaller) test set.

## Missing Evidence

| Gap                                   | Impact                                              | How to Obtain                                            |
| ------------------------------------- | --------------------------------------------------- | -------------------------------------------------------- |
| Backend logs for the 21:xx run        | Exact per-script marker counts (nice-to-have only)  | Backend stdout / log file around 21:56–21:58            |
| Whether thread state is left `error`  | Confirms recovery requires full re-run vs auto-skip | Reproduce + inspect thread status after the failure     |

## Source Code Trace

| Element       | Detail                                                                                              |
| ------------- | --------------------------------------------------------------------------------------------------- |
| Error origin  | `src/ai_qa/agents/sarah.py:535` — `StageResult(... warnings=warnings ...)` raises Pydantic `too_long` |
| Trigger       | Sarah generate loop completes for a batch whose aggregated warnings > 100 (`sarah.py:428-541`)      |
| Condition     | `warnings` list ≥ 101 items; here 112, mostly `# REVIEW:` markers from `script_generator.py:355-367` |
| Related files | `models.py:47-56` (cap), `prompts/script_generation.py` (marker generation), `script_generator.py:155-203` (parallel loop with same unbounded aggregation), `sarah.py:547+` (regenerate path) |

## Conclusion

**Confidence:** High

**Confirmed root cause:** Sarah's script-generation stage aggregates one warning per `# REVIEW:`/brittle/gap/secret/auth marker across the whole batch into a single flat list and passes it to `StageResult(warnings=...)`, whose `warnings` field is hard-capped at `max_length=100` (`models.py:54`). A 9-script batch against an SSO app produced 112 warnings → Pydantic `too_long` ValidationError → "Failed to generate scripts". The "takes very long to continue" symptom is a side effect: the error fires only after the full multi-minute generation completes, all generated scripts are discarded, and any retry re-runs and deterministically re-fails. Not intermittent — conditionally deterministic on batch size × markers-per-script.

## Recommended Next Steps

### Fix direction

The aggregated `warnings` (and `errors`) lists must be bounded before constructing `StageResult`. Options, by mechanism (combine as desired):

1. **Cap + summarize at the aggregation site (minimal, surgical).** In `sarah.py` before `:535` (and the parallel `script_generator.py:161-203` loop, and the regenerate path `sarah.py:547+`), truncate to e.g. the first 99 warnings and append a single rollup line: `f"... and {n-99} more warnings suppressed"`. Keeps the contract, stops the crash.
2. **Aggregate, don't enumerate.** Most overflow comes from the *same* `REVIEW: SSO/session setup required` repeated per script. Dedupe identical warnings and/or collapse per-category counts (e.g. "REVIEW markers: 47 across 9 scripts") so warnings scale with categories, not steps. Per-script detail already lives on each `GeneratedScript.warnings`, so nothing is lost.
3. **Defensive guard in the model (belt-and-suspenders).** A `@field_validator` on `warnings`/`errors` that truncates-with-rollup instead of raising would make *every* stage (Bob/Mary/Jack) immune to this class of crash, not just Sarah. Higher blast radius — decide whether silent truncation is acceptable platform-wide.

Recommended: **(2) + (1)** at the Sarah aggregation sites — fixes the user's case and keeps warnings meaningful; consider (3) separately as a platform hardening.

### Diagnostic

If reproduction is wanted before fixing: run Sarah on the PTP rating-stars test set (≥9 cases) against the INT SSO environment; it should fail at `StageResult` construction with `too_long`. To confirm the count, log `len(warnings)` just before `sarah.py:535`.

## Reproduction Plan

1. Select a project whose target environment is an SSO/authenticated app (PTP / `int-progresstalkapplication.corpnet.local`).
2. Approve ≥9 test cases that involve multiple ambiguous/multi-element assertions ("rating stars", "individual star elements").
3. Run Sarah → Generate scripts.
4. Observe: all "Generating script i of N" messages complete, then `Failed to generate scripts: ... StageResult warnings List should have at most 100 items ... not 1xx [type=too_long]`.
5. Expected after fix: stage completes (success/degraded), warnings truncated-with-rollup or category-aggregated, scripts saved.

## Side Findings

- The careful design that routes per-item failures into `warnings` (to keep `success=True`, since `StageResult` forbids a non-empty `errors` list when `success=True`) — `sarah.py:484-488,508-511` — is exactly what inflates the warnings list. The graceful-degradation mechanism is what trips the hard cap. (Confirmed.)
- `errors` carries the identical `max_length=100` exposure (`models.py:47-50`); a failure-heavy batch could overflow it the same way, though `warnings` is the likelier offender given the per-item-failure-as-warning design. (Confirmed.)
- The 7 scripts visible in the sidebar (Jun 22, 7:04 PM) are from a prior, smaller successful run — unrelated to the failed 21:58 run, which saved nothing. (Deduced from timestamps.)
