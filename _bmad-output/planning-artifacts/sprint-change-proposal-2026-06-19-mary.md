# Sprint Change Proposal: Mary Auth Fix + Overview Reading + TD-Test-Design Clarification Loop

Date: 2026-06-19
Author: Developer (correct-course)
Epic context: Epic 12 (Mary — Test-case generation) — bug fix + UX/quality refinement. No structural epic change.

## 1. Issue Summary

- **Triggering issue**: Running the pipeline end-to-end against the "PTP Personal Travel Plan" project, **Bob now runs fine but Mary fails** at generation with: `Extraction failed: LLM Authentication failed: "Could not resolve authentication method. Expected either api_key or auth_token to be set…"`.
- **Root cause (verified)**: Mary builds its LLM config eagerly in `__init__` — `self.config = self.get_llm_config()` then `self.extractor = TestCaseExtractor(llm_config=self.config)` ([mary.py](../../src/ai_qa/agents/mary.py)). Agents are constructed via `agent_class()` ([routes.py:74](../../src/ai_qa/api/routes.py)) **before** `set_project_context()` attaches the context, so at construction `project_context is None`, `get_llm_config()` returns a config with `api_key=""` (it only raises when a context is present — [base.py:184](../../src/ai_qa/agents/base.py)), and the extractor freezes that empty-key config. At call time `ChatAnthropic(api_key="")` raises the auth error. Bob is unaffected because it resolves `get_llm_config()` **lazily** inside `process()` / `_extract_descendants` ([bob.py:700](../../src/ai_qa/agents/bob.py), [bob.py:1041](../../src/ai_qa/agents/bob.py)).
- **Requested enhancement (Thuong)**: Mary should (a) read **all** requirement MD files for an overview, then focus on the selected id — Confluence page id reuses Bob's saved copy, **Jira ticket id is fetched live via MCP**; (b) reference the BMAD **[TD] Test Design** method (`.claude/skills/bmad-testarch-test-design`) to ask the author about genuinely unclear points (like Bob's clarify loop) **before** writing test cases; (c) save test cases to the Test Cases folder and show them on the UI.

## 2. Impact Analysis

- **Epic impact**: Epic 12 only. No new/removed/reordered epics. Epic 13 (Sarah) is unaffected — it still consumes approved `testcase` artifacts; the change only improves their quality.
- **PRD / Architecture impact**: None structural. No DB schema change, **no migration**. Reuses the existing per-(user,project,step) cached agent instance (so Mary's multi-turn clarify state survives across websocket messages, exactly as Bob's does), the existing `PipelineArtifactAdapter` save/load paths, and the thread provider's LLM.
- **Artifact impact**: Test cases continue to save via `save_test_case` (kind `testcase` → browse folder `test_cases`). A Jira focus is persisted as an approved `requirements` artifact via the idempotent `save_requirement` (same write path Bob uses), so it appears in the Requirements tree and is re-loadable by reject-regeneration.
- **Decisions taken** (clarified with Thuong):
  - Confluence page id → reuse Bob's already-saved requirement (no MCP re-fetch); Jira ticket id → **Mary calls MCP** (`JiraReader`) to fetch + save the ticket.
  - The clarification loop **only asks when genuine gaps are detected** (mirrors Bob); a clean requirement generates immediately.
- **Technical impact** (files, all verified):
  - Backend — `src/ai_qa/prompts/test_extraction.py`: optional `context` arg + risk-based TD method block (P0–P3 priorities, coverage shape, no-invented-facts → warnings).
  - Backend — `src/ai_qa/pipelines/test_case_extractor.py`: thread optional `context` through `extract` / `extract_batch` / `_call_llm`; public `llm_config` attribute (lazily settable).
  - Backend — `src/ai_qa/agents/mary.py`: `_ensure_llm_ready()` (the fix); `phase` gate; overview digest; Confluence-vs-Jira focus resolution + MCP Jira fetch; risk-based clarification planner + one-question-at-a-time loop; generation-context injection.
  - Frontend — `frontend/src/App.tsx`: Mary clarify state, `test_clarify_request` message handler + bubble, and a clarify reply panel (Submit/Skip) on step 3, mirroring Bob's clarify UI.

## 3. Recommended Approach

**Direct Adjustment** within Epic 12 — no rollback, no MVP change. Rationale:

1. The auth failure is an isolated lifecycle-ordering bug; the minimal correct fix is to resolve the LLM config lazily (matching Bob), applied to the existing extractor object so injected test mocks are preserved.
2. The overview + clarification enhancement reuses Bob's proven phase/state-machine and clarify-loop pattern, the existing artifact contracts, and the existing test-extraction pipeline (context is purely additive). The TD method is encoded as prompt guidance + a pre-generation clarification pass, not a new subsystem.

Effort: ~1 focused dev session. Risk: low — additive, no schema/migration, broad existing test coverage retained. Timeline impact: none.

## 4. Detailed Change Proposals

### Story: [12.x] Mary LLM auth fix (lazy config)

Section: `MaryAgent.__init__` / new `_ensure_llm_ready`

OLD:

```
self.config = self.get_llm_config()           # at __init__, before context → empty key
self.extractor = TestCaseExtractor(llm_config=self.config)
# ...extractor never refreshed; process() uses the frozen empty-key config
```

NEW:

```
# __init__ keeps a provisional config (placeholder), then at call time:
def _ensure_llm_ready(self) -> None:
    self.config = self.get_llm_config()        # context attached → real key (or UX-DR12 raise)
    self.extractor.llm_config = self.config
# called at the top of process(), in handle_start, and before reject regeneration
```

Rationale: resolves the key after `set_project_context`, mirroring Bob; missing key now surfaces as a clean UX-DR12 message instead of a raw provider error.

### Story: [12.x] Overview reading + Confluence/Jira focus

- Mary reads every approved `requirement.md` and builds a bounded **Project Overview** digest (siblings of the focus), injected into generation as context-only.
- Focus resolution: Confluence page id → saved `{id}/requirement.md`; Jira ticket id (`PROJ-123` pattern or `source_type == "jira"`) → `JiraReader.read_issue` via MCP, saved as an approved `jira` requirement, then used as focus.

### Story: [12.x] Risk-based test-design clarification loop

- New `clarify` phase. Before generation, a single LLM pass (Master Test Architect / risk-based lens, informed by `bmad-testarch-test-design`) lists only genuine gaps (ambiguous AC/expected results, undefined preconditions/test data, unclear risk/priority, ambiguous UI controls, missing NFR thresholds). Empty → generate immediately.
- The author answers/skips one question at a time (`test_clarify_request` ↔ `approve` with `action: clarify_answer | skip`, step 3). Answers accumulate as authoritative Q/A context fed into the generation prompt. Mary does **not** edit the requirement MD (Bob owns requirements). Capped at 5 questions.

### Frontend: clarify panel

`frontend/src/App.tsx`: `maryState.clarifyPrompt/clarifyInput`; handler for `test_clarify_request`; a Mary bubble for the question; a Submit/Skip reply panel — mirroring Bob's clarify UI, green-themed for Mary.

## 5. Implementation Handoff

- **Scope classification**: **Minor → Moderate** — direct implementation by the Developer agent within Epic 12; no PO replan, no migration.
- **Status**: Implemented in this session. Backend + frontend changes complete; full backend suite green (952 passing after fix), frontend typecheck/lint/tests green. Uncommitted on `main` per the project's solo-commit convention — Thuong commits + migrates himself (no migration needed here).
- **Success criteria**:
  1. Mary generates test cases without the auth error.
  2. Mary reads all requirement MDs (overview) and focuses on the selected id; Jira id is fetched from MCP.
  3. When gaps exist, Mary asks before generating; answers shape the test cases.
  4. Test cases save to the Test Cases folder and render in the UI.
- **Next**: live end-to-end re-validation against the "PTP Personal Travel Plan" project (restart the backend first — `uv run ai-qa` has no auto-reload).
