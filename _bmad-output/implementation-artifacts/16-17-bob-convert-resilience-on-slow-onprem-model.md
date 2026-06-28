---
baseline_commit: 7641ef215742a18d6f5ca7951b6193abcf80164a
---
# Story 16.17: Bob convert resilience on a slow on-prem model

Status: done

> **Priority: P1 (hardening).** UAT finding #1. NOT blocking once 16-14 fixes Bob's model
> back to a fast vision model — the convert failures are a downstream symptom of the wrong
> (slow 235B) model being selected. This story hardens the convert path so a slow/heavy
> on-prem model degrades gracefully rather than failing most pages.

## Story

As a QA user,
I want Bob's per-page requirement conversion to tolerate a slow or heavy on-prem model,
so that pages convert (or fail informatively) instead of timing out en masse.

### Root cause (forensic, code-verified)

The text convert `_format_story` ([requirement_formatter.py:322-325](src/ai_qa/pipelines/requirement_formatter.py:322)) is `await asyncio.wait_for(ainvoke, _CONVERT_LLM_TIMEOUT=600)` — the only uncaught LLM call in `convert_markdown` (vision-caption errors are swallowed to `""`). On a 235B model it raises (TimeoutError or provider error) → [bob.py:1184-1186](src/ai_qa/agents/bob.py:1184) emits "Failed to convert" per page. It is per-page `try/except`, so it does NOT abort the batch or freeze — but most pages fail.

## Acceptance Criteria

1. **Configurable convert timeout.** Given a deployment with a slower model, when conversion runs, then the convert wall-clock timeout is sourced from settings (fallback 600s) instead of a hard-coded constant.
2. **Actionable failure surface.** Given a page fails to convert, when the warning is surfaced, then it distinguishes a timeout from a provider error (so ops can tell "too slow" from "rejected"), and remains secret-safe.
3. **(Stretch) Decouple text vs vision model.** Given Bob is selected via the vision capability, when the TEXT convert runs, then it may use a faster instruction model while the vision sub-call keeps the vision model — so a heavy vision model does not also do the bulk text conversion. (Design decision required — flag in dev.)
4. **(Stretch) Oversized-page handling.** Given a very large page, when conversion runs, then the raw markdown is chunked/handled so a context-length 4xx does not fail the page outright.

## Tasks / Subtasks

- [ ] **Task 1 — Configurable convert timeout (AC1)**
  - [ ] Thread a `convert_llm_timeout` (settings, default 600) into `RequirementFormatter` instead of the module constant `_CONVERT_LLM_TIMEOUT`.
- [ ] **Task 2 — Failure classification (AC2)**
  - [ ] In Bob's convert loop, classify `asyncio.TimeoutError` vs provider error and word the warning accordingly; assert secret-safety in a leak-canary test.
- [ ] **Task 3 — DECISION GATE: text/vision model decoupling (AC3)**
  - [ ] Decide whether `_format_story` should use a fast instruction model (separate from Bob's vision model). Bring options to Thuong before implementing.
- [ ] **Task 4 — Tests + gates**
  - [ ] Unit tests for timeout config + failure classification; ruff + mypy + pytest green.

## Notes

Deferred until after 16-14/16-15/16-16 land — 16-14 alone removes the user-visible failures by restoring Bob to a fast vision model.
