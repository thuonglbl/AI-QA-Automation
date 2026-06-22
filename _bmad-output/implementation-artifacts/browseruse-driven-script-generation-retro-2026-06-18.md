# Sprint Retrospective — Browser-Use Driven Script Generation (BSG)

**Date:** 2026-06-18
**Sprint:** Browser-Use Driven Script Generation (bsg-1 to bsg-6)
**Participants:** Thuong (Project Lead), Amelia (Facilitator/Dev), Alice (Product Owner), Charlie (Senior Dev), Dana (QA Engineer), Elena (Junior Dev)
**Sprint type:** Correct-Course / Feature Sprint (Sarah agent enhancement)

---

## Executive Summary

The BSG sprint delivered a complete browser-use-driven script generation subsystem for Sarah. All 6 slices were completed in a single session with all quality gates green (backend 1459 passed, frontend 273 passed, mypy/ruff/eslint/typecheck/build clean).

The key outcome: Sarah can now drive a real Chrome through approved test cases against the live application, capture a verified DOM action trace, and synthesize a deterministic Playwright script grounded in real selectors — eliminating invented locators. A graceful fallback to the existing LLM-only path is preserved throughout.

---

## Sprint Delivery

| Slice | Title | Status |
|-------|-------|--------|
| bsg-1 | Provider → browser_use LLM factory (`llm_factory.py`) | ✅ done |
| bsg-2 | Explorer + trace-to-Playwright translation (`explorer.py`, `trace.py`) | ✅ done |
| bsg-3 | Wire into Sarah with fallback (`script_generator.py`, `sarah.py`) | ✅ done |
| bsg-4 | Docs and sprint-status update | ✅ done |
| bsg-5 | Sarah target URL + Chrome path UI form (`SarahInputsForm.tsx`) | ✅ done |
| bsg-6 | Chrome SSO reuse via CDP connect | ✅ done |

**Note:** Design doc proposed 4 slices; implementation grew to 6 organically. bsg-5 closed a UI gap discovered during implementation (Sarah needed a way to collect target URL + Chrome path from the user). bsg-6 added CDP connect mode — attaching to a running Chrome to reuse its live SSO session without re-login.

**Key files:**
- `src/ai_qa/browser/llm_factory.py` — 6-provider factory
- `src/ai_qa/browser/explorer.py` — live agent run (integration-only)
- `src/ai_qa/browser/trace.py` — DOM trace extraction (pure/testable)
- `src/ai_qa/pipelines/script_generator.py` — three-tier wiring
- `src/ai_qa/agents/sarah.py` — wired with UI inputs handling
- `frontend/src/components/agents/SarahInputsForm.tsx` — new React form

---

## What Went Well

### 1. Design spec quality was high — implementation followed it closely

`design-browseruse-driven-script-generation-2026-06-18.md` covered the provider × credential matrix, acceptance criteria, test plan with testable seams, and a risk register. The implementation matched the design. Thuong identified this as the top highlight of the sprint.

This continues the pattern from PA sprint: a well-specified design document enables fast, low-rework implementation.

### 2. Three-tier fallback is first-class, not an afterthought

The fallback cascade (explore→trace→Playwright → vision→LLM → LLM-only) was designed in from the start, not retrofitted. Every failure path in the explorer and script generator degrades gracefully. The live path never hard-fails — the existing review/approve/save UX is completely unchanged regardless of which generation path ran.

### 3. CDP connect mode (bsg-6) eliminates SSO re-login friction

Attaching to an already-running Chrome via CDP URL (`http://localhost:9222`) reuses the live authenticated session — no profile lock, no re-login. This is significantly better UX than launching a fresh Chrome for SSO-protected apps. The implementation in `explorer.py:97-99` is clean and minimal.

### 4. Shared `_postprocess_script` — DRY across all three paths

All three generation paths (trace, vision, LLM-only) feed through the same `_postprocess_script` at `script_generator.py:328`. A single fix to validators, confidence scoring, or warning detection applies to all paths. Good separation of concerns.

### 5. Test coverage is solid for the testable parts

`test_llm_factory.py` covers all 6 providers, blank-key guard, and unknown-provider guard. `test_explorer.py` covers all guard paths (no Chrome, no URL, no LLM, no browser source) and both browser modes (CDP connect + launch). The integration-only nature of the live agent run is explicitly documented and follows the same policy as the existing vision path.

### 6. Privacy defaults are correct

`ANONYMIZED_TELEMETRY=false` and `BROWSER_USE_CLOUD_SYNC=false` are set before any browser-use call. No third-party telemetry by default.

---

## Challenges & Growth Areas

### 1. Multi-layer third-party dependencies create compounding assumption risk

The live exploration path has 4 dependency layers:

```
browser-use library (0.13.1)
  → provider LLM (Claude/Gemini/OpenAI/on-prem)
    → Chrome local (launch or CDP)
      → app running + active SSO session
```

Any single layer failing causes fallback — which is the correct behavior. But the assumptions at each layer (browser-use works with provider X, CDP API is compatible with Chrome version Y, LLM credentials are valid) were not all adversarially verified before implementation.

This is the same class of issue as PA sprint's "Anthropic subscription SSO ≠ API access" discovery. **Pattern:** third-party integration assumptions should be verified before implementation, not after.

### 2. Live path is integration-only — no CI coverage for the core feature

The most important behavior of this sprint (real browser → real trace → real selectors) cannot run in CI. It requires Chrome + reachable app + SSO session + provider key. This is documented and expected (same policy as vision path), but means the primary value delivered by the sprint has never been end-to-end verified automatically.

### 3. Minor technical debt: `_call_llm_with_trace` lacks `@retry`

`_call_llm` and `_call_llm_with_vision` both have `@retry(stop=stop_after_attempt(3), ...)`. `_call_llm_with_trace` does not. A transient LLM timeout in the trace path immediately falls back to LLM-only without retry. May be intentional (trace calls are already preceded by an expensive exploration run, retry might be undesirable), but not documented.

### 4. `process()` facade does not expose new parameters

The `process()` function at `script_generator.py:1044` is the legacy entry point and does not expose `explore_llm`, `chrome_path`, or `cdp_url`. Any caller using `process()` directly cannot access the new explore path. The `ScriptGenerator` class constructor is the correct API, but this could confuse future callers.

### 5. No per-story spec files

Like the PA sprint, bsg-1 through bsg-6 exist only as keys in `sprint-status.yaml`. The design doc served as the combined specification. Works for rapid sprints, but reduces individual-story traceability.

---

## Key Insights

1. **Spec quality pays compound dividends.** A clear design doc with explicit scope, non-goals, cost/credential matrix, acceptance criteria, and testable seams enables fast implementation with minimal rework. This is now a validated pattern across 2+ sprints.

2. **Multi-layer third-party dependencies need adversarial verification upfront.** For features depending on external systems (browser automation, auth, LLM APIs), run a "what could be wrong?" research pass on key assumptions before writing code. The cost of a one-hour pre-implementation check is much lower than a post-implementation discovery.

3. **Fallback-first design is the correct default for AI-dependent features.** Any feature that can fall back to a simpler path (explore→LLM-only, vision→LLM-only) should be designed with that fallback as first-class from the start. It reduces risk, keeps the existing UX unchanged, and makes CI-testing tractable.

4. **Scope can grow organically (4→6 slices) — that's healthy discovery.** The key is that each addition (bsg-5 UI, bsg-6 CDP) was a genuine improvement with clear value, not a scope creep. The sprint remained coherent.

---

## Previous Sprint Action Items Follow-Through

**From Provider Auth Enhancements retro (2026-06-17):**

| Action | Status | Notes |
|--------|--------|-------|
| Commit working tree (PA-1–PA-5 + 3 new files) | ✅ Done | Committed before PA retro closed |
| Await IT response on Console API key for `claude-sso` | ⏳ On-hold | IT timeline unknown; may not happen (permissions issue). Decision: leave `claude-sso` as-is until IT confirms. |
| Decide code direction once IT responds | 🔲 Blocked | Depends on IT response above; no action for now. |

---

## Readiness Assessment

| Dimension | Status |
|-----------|--------|
| Backend suite | ✅ 1459 passed |
| Frontend suite | ✅ 273 passed |
| mypy / ruff / eslint / typecheck / build | ✅ All clean |
| Working tree committed | ⚠️ Uncommitted — changes in working tree at retro time |
| Live exploration E2E | ⚠️ Integration-only; needs Chrome + reachable app + provider key for manual verification |
| `claude-sso` production path | ⚠️ Requires IT-provisioned Console API key (on-hold) |

---

## Action Items

| # | Action | Owner | Status |
|---|--------|-------|--------|
| 1 | Commit working tree (BSG sprint changes) | Thuong | 🔲 Pending |
| 2 | Document `_call_llm_with_trace` retry behavior (intentional or oversight?) | Thuong | 🔲 Low priority |
| 3 | Consider adding `explore_llm`/`chrome_path`/`cdp_url` to `process()` facade or deprecate it | Thuong | 🔲 Low priority |

---

## Next Steps

Focus for the team is **bug fixes and improvements** (tracked in other threads). Epic 14 (Audit Logging & Leadership Metrics) and later epics remain backlog — not a current priority.

When a manual live run opportunity arises (Chrome + reachable app + provider key + active SSO):
- Verify bsg-2/bsg-3 end-to-end: a real trace is captured and translated into a deterministic Playwright script
- Verify bsg-6: CDP connect mode reuses the authenticated session correctly

---

*Retrospective facilitated by Amelia (Developer). Document language: English per project config.*
