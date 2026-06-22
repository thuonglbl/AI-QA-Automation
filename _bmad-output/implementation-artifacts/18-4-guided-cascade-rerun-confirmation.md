---
baseline_commit: 39bec831e2b195b3121a2345a32b282211bd9872
---
# Story 18.4: Guided Cascade Re-Run with Confirmation

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Full-stack. The largest story in the epic. Given a detected change (18.2) and its staleness impact (18.3), present the user a confirmation prompt — "Source X changed; N requirements, M test cases, K scripts may be stale. Re-run the downstream chain?" — with a chosen SCOPE, and on confirm, drive the affected agents to regenerate. **Critical architectural constraint: there is NO cross-agent auto-handoff today** — agents chain only via the user clicking through each step, and each agent (Mary/Sarah) has a mandatory human review gate ([base.py:341-347](src/ai_qa/agents/base.py:341) approve→DONE; [base.py:349-387](src/ai_qa/agents/base.py:349) reject→re-run). So "cascade" here means **GUIDED re-run**: pre-load each affected stage's inputs (the changed source / the stale test cases) and walk the user through the existing per-stage review — it does NOT bypass review or silently overwrite approved artifacts.

## ⚠ DECISION GATE — cascade execution model + granularity (resolve at dev start)

1. **Execution model: GUIDED (recommended) vs AUTO.** The agents are built around mandatory human review (Mary's `test_case_review`, Sarah's `script_review`). **Guided** = the cascade pre-fills the next stage's inputs and prompts the user to proceed into the normal review UX; it never bypasses approval. **Auto** = regenerate + auto-approve downstream without review — this contradicts the whole "review-gated" design and risks silently replacing human-approved artifacts. **Recommended: GUIDED.** ACs below assume guided.
2. **Granularity: PER-SOURCE (recommended) vs whole-project vs single-test-case.** A changed page maps (via 18.3) to its requirement → its test cases → its scripts. **Recommended: per-source lineage** — the cascade scope is exactly the staleness set for the changed source(s), not the entire project, not a hand-picked single case. The user then chooses HOW FAR DOWN to cascade (requirements only → through test cases → through scripts → through execution).

If Thuong overrides either, adjust Task 3/Task 4 accordingly; the rest stands.

## Story

As a QA user,
I want to confirm whether to cascade an update through requirements → test cases → scripts → execution,
so that downstream regeneration only happens with my explicit approval and at the scope I choose.

## Acceptance Criteria

1. **Cascade confirmation prompt with impact + scope.** Given a changed source with a non-empty `StalenessImpact` (18.3), when Bob (or the change-detection flow) offers a cascade, then it emits a `cascade_confirm` prompt: a chat message carrying `metadata={"type": "cascade_confirm", "source": {...}, "impact": <StalenessImpact counts+lists>, "scope_options": ["requirements","test_cases","scripts","execution"]}`. The FE renders an explicit confirmation panel (mirroring the metadata-driven forms in [App.tsx:826-1080](frontend/src/App.tsx:826), e.g. `sarah_inputs_request`/`clarify_request`) showing what will be regenerated at each scope. All strings English ([[app-ui-english-only]]).

2. **Nothing regenerates without explicit confirmation.** Given the `cascade_confirm` prompt, when the user does nothing or declines, then NO artifact is regenerated, overwritten, or deleted, and the decision (`declined`) is recorded (audit handled in 18.5). Re-generation is strictly opt-in (epic intent: "only with my explicit approval").

3. **User chooses the cascade depth (scope).** Given the confirmation panel, when the user confirms, then they select how far down the chain to cascade — `requirements` (re-extract the changed source only), or additionally `test_cases`, `scripts`, or `execution`. The cascade regenerates exactly the stages within the chosen depth for exactly the staleness set (per-source granularity), not the whole project.

4. **Guided re-run respects existing review gates.** Given a confirmed cascade at depth ≥ `test_cases`, when regeneration runs, then each agent runs through its NORMAL review flow — Bob re-extracts the changed source → user reviews/approves the requirement (existing Bob review) → Mary regenerates ONLY the test cases whose `derived_from_artifact_id` is the affected requirement → user reviews via `test_case_review` → Sarah regenerates the affected scripts → user reviews via `script_review` → (if depth=`execution`) Jack re-runs. The cascade ORCHESTRATES (pre-loads inputs, advances the step) but the human approval at each gate is preserved — no auto-approve, no bypass.

5. **Pre-load the right inputs at each stage.** Given the cascade advances to a stage, when that agent starts, then its input is pre-populated from the impact map: Bob ← the changed source id/url; Mary ← the affected requirement artifact id(s) (so Mary regenerates the right group, reusing the `_replace_source_group` path at [mary.py:1059-1087](src/ai_qa/agents/mary.py:1059)); Sarah ← the affected approved test-case id(s). The user is not asked to re-enter the page id or re-select test cases that the cascade already knows from lineage.

6. **Cascade is resumable / interrupt-safe.** Given the cascade is multi-step and a step can run minutes (slow on-prem LLM), when the worker restarts or the user navigates away mid-cascade, then the existing interruption-recovery (`reconcile_interrupted_work`, [threads/service.py:264-318](src/ai_qa/threads/service.py:264)) leaves the thread in a recoverable state and the cascade can be resumed or restarted without corrupting approved artifacts. The cascade does not hold a long-lived in-memory-only state that is lost on restart — its scope/progress is derivable from the thread + impact map.

7. **Scope is bounded and reported; no silent over-reach.** Given a confirmed cascade, when it runs, then it touches ONLY the assets in the chosen-scope staleness set; anything skipped (out-of-scope tiers, `unmapped` legacy assets from 18.3 AC6) is reported to the user, not silently regenerated or silently ignored. The cascade never regenerates an asset outside the confirmed scope.

8. **Execution leg gated on Jack availability.** Given depth=`execution`, when the cascade reaches the execution stage, then it triggers a Jack run for the regenerated scripts (Jack/Epic 14 is DONE); if execution prerequisites are missing (no approved scripts, no environment), it degrades to a clear message and stops at the scripts tier — never silently claims execution ran.

## Tasks / Subtasks

- [ ] **Task 1 — `cascade_confirm` payload + emit (AC: 1, 2)**
  - [ ] Define the `cascade_confirm` metadata payload (Pydantic, near 18.2/18.3 models in `src/ai_qa/models.py`) carrying the source, the `StalenessImpact` (18.3), and `scope_options`. Add the matching TS type in `frontend/src/types/` ([[project-context]] full-stack-sync).
  - [ ] Emit it from the change-detection flow when `map_impact` (18.3) returns a non-empty impact — as an agent chat message with the metadata. Do NOT emit (or emit a benign "no downstream assets" note) when the impact is empty.

- [ ] **Task 2 — Confirmation panel (AC: 1, 2, 3, 7)**
  - [ ] FE: render `metadata.type === "cascade_confirm"` in [App.tsx](frontend/src/App.tsx) following the existing form-routing switch. Show per-tier counts (N requirements, M test cases, K scripts, J execution runs) + the asset names, a scope selector (radio/stepper: requirements → test_cases → scripts → execution), and explicit Confirm / Decline buttons. Surface `unmapped` legacy assets as "not auto-traceable" (AC7). English only.
  - [ ] On submit, send a WS action `{action: "cascade_confirm", confirm: bool, scope: <depth>, source_id, ...}` through the existing action channel.

- [ ] **Task 3 — Cascade orchestration (AC: 3, 4, 5, 7, 8) [GUIDED]**
  - [ ] Add a `_handle_cascade_confirm` action handler (dispatched like `clarify_answer`, [bob.py:1698-1727](src/ai_qa/agents/bob.py:1698) / [api/websocket.py:315-388](src/ai_qa/api/websocket.py:315)). On `confirm=false` → record `declined` (18.5) and stop (AC2).
  - [ ] On `confirm=true`: compute the in-scope stages from the chosen depth. Drive the guided re-run:
    - **requirements**: re-run Bob extraction for the changed source id only (reuse the existing extraction entry, pre-load the source id per AC5) → existing Bob review gate.
    - **test_cases**: after the requirement is re-approved, start Mary scoped to the affected requirement id(s); reuse the per-requirement regeneration group path (`_replace_source_group`, [mary.py:1059-1087](src/ai_qa/agents/mary.py:1059)) so only the affected group is regenerated, not all test cases → `test_case_review` gate.
    - **scripts**: start Sarah scoped to the affected approved test-case id(s) → `script_review` gate.
    - **execution**: start Jack for the regenerated scripts (AC8); degrade with a message if prerequisites missing.
  - [ ] Advance step-by-step honoring each review gate (do NOT auto-approve). Use the per-agent action lock so cascade steps serialize with other actions ([api/websocket.py:360](src/ai_qa/api/websocket.py:360)). Respect the LLM-call timeout/async rules ([[ws-nonblocking-clarify-timeout-fix]], [[project-context]] await ainvoke).
  - [ ] Bound the scope strictly to the impact set (AC7); never widen to the project.

- [ ] **Task 4 — Resumability (AC: 6)**
  - [ ] Ensure cascade progress is reconstructable from durable state (the thread's agent runs + the impact map recomputed from the changed source), not a long-lived in-memory object. Verify `reconcile_interrupted_work` ([threads/service.py:264-318](src/ai_qa/threads/service.py:264)) leaves a cascaded thread recoverable; add a system message on interruption so the user can restart the cascade. Do NOT corrupt or partially-overwrite approved artifacts on interruption (the `save_requirement` "save-new-then-delete-prior" ordering at [artifact_adapter.py:83-108](src/ai_qa/pipelines/artifact_adapter.py:83) already protects requirements — preserve that pattern for any new write).

- [ ] **Task 5 — Tests (all ACs)**
  - [ ] Confirm/decline: `confirm=false` regenerates nothing (assert no artifact writes, no agent start); `confirm=true, scope=requirements` re-runs only Bob extraction and stops at the requirement review.
  - [ ] Scope depth: `scope=scripts` drives Bob→Mary→Sarah for the impact set and stops before Jack; `scope=execution` reaches Jack (mock Jack) or degrades cleanly when prerequisites absent (AC8).
  - [ ] Scoping: Mary regenerates ONLY the affected requirement's test-case group (`_replace_source_group`), not unrelated groups; Sarah regenerates only affected scripts; out-of-scope + `unmapped` assets untouched + reported (AC7).
  - [ ] Review gates preserved: each stage transitions to its review state and waits — no auto-approve (assert the agent state machine pauses at review).
  - [ ] Resumability: simulate interruption mid-cascade → `reconcile_interrupted_work` recovers the thread; approved artifacts intact (AC6).
  - [ ] FE Vitest: `cascade_confirm` panel renders tiers/counts/scope selector, Confirm/Decline emit the right action, English strings.
  - [ ] `uv run pytest` (full suite) + ruff + `mypy src`; `npm run typecheck` + Vitest + `npm run build`.

## Dev Notes

### The architecture says "guided", not "auto" — design around the review gates

Every agent transition is human-gated by design: approve → DONE ([base.py:341-347](src/ai_qa/agents/base.py:341)), reject → re-run with feedback ([base.py:349-387](src/ai_qa/agents/base.py:349)). There is no programmatic "Mary, hand your output to Sarah" — the user clicks through. Three forensic sweeps confirmed this. So the cascade's job is NOT to invent an auto-pipeline; it is to make the EXISTING manual chain effortless by (a) pre-loading the right inputs from lineage and (b) advancing the user stage-to-stage. Trying to auto-regenerate-and-approve would bypass the review that is the product's core value and could silently overwrite human-approved work. Build guided.

### Reuse Mary's per-group regeneration — don't regenerate everything

Mary already has `_replace_source_group(source_requirement_id, replacements)` ([mary.py:1074-1087](src/ai_qa/agents/mary.py:1074)) and rejection-driven regeneration scoped to one `source_requirement_id` ([mary.py:979-1059](src/ai_qa/agents/mary.py:979)). The cascade should target the affected requirement id(s) from 18.3 and reuse this group-replacement path so only the stale group regenerates. Re-running Mary over ALL requirements would be wasteful and would touch unaffected, human-approved test cases (violates AC7).

### Current behavior to PRESERVE (regression guardrails)

- **Review gates are sacred.** Never auto-approve or skip `test_case_review`/`script_review`. The cascade advances steps; the human still approves each (AC4).
- **No silent overwrite of approved artifacts.** `save_requirement` saves-new-then-deletes-prior ([artifact_adapter.py:83-108](src/ai_qa/pipelines/artifact_adapter.py:83)) precisely to avoid a zero-row window — keep that ordering for any cascade write. A declined/interrupted cascade must leave the prior approved artifacts intact (AC2/AC6).
- **Scope discipline (AC7).** Touch only the confirmed-scope impact set. `unmapped` legacy assets (18.3 AC6) are reported, never auto-regenerated.
- **Async + WS non-blocking.** `await` LLM `ainvoke` (never sync `invoke` in async, [[project-context]]); dispatch cascade steps as background tasks under the per-agent lock so heartbeats don't freeze ([[ws-nonblocking-clarify-timeout-fix]]). On-prem LLM calls run minutes — keep prompts lean.
- **Interrupt recovery.** Don't store cascade scope only in memory — `uvicorn --reload`/restart kills in-flight tasks ([[stuck-thread-startup-recovery]], [[backend-no-autoreload]]); rely on durable thread state + recomputable impact.
- **English-only UI + full-stack sync** for the new payload/panel ([[app-ui-english-only]], [[project-context]]).

### Source tree components to touch

- `src/ai_qa/models.py` — **ADD** (`cascade_confirm` payload).
- `src/ai_qa/agents/bob.py` (or the change-detection flow owner) — **UPDATE** (emit `cascade_confirm`, `_handle_cascade_confirm` orchestration).
- `src/ai_qa/agents/mary.py` — **UPDATE if needed** (accept a pre-loaded affected-requirement scope; reuse `_replace_source_group`).
- `src/ai_qa/agents/sarah.py` — **UPDATE if needed** (accept pre-loaded affected test-case ids).
- `src/ai_qa/api/websocket.py` — **UPDATE** (route `cascade_confirm` action).
- `frontend/src/App.tsx` + `frontend/src/types/` — **UPDATE** (confirmation panel + TS type).
- Tests — **ADD** backend orchestration + FE panel.

### Decided scope (defaults — Thuong, correct via the DECISION GATE)

- **Guided** cascade (respect review gates), **per-source** granularity, user-chosen **depth** (requirements → test_cases → scripts → execution).
- **No auto-approve**; declined/interrupted ⇒ zero changes to approved artifacts.
- Execution leg uses Jack (Epic 14 DONE); degrades cleanly if prerequisites absent.

### Testing standards summary

- Backend pytest; drive the agent state machine with stubbed LLM/reader; assert step transitions pause at review gates and that scope is bounded. Full-suite run.
- FastAPI deps via `app.dependency_overrides` (never `mock.patch` a dependency); `try/finally` cleanup ([[project-context]]).
- FE Vitest with fetch-spy / `importOriginal()`.

### Project Structure Notes

- No Alembic migration in this story (uses 18.1/18.3 schema). Depends on 18.2 (detection) + 18.3 (impact map).
- Largest surface area in the epic — consider landing it behind the change-report (18.2) so the confirm prompt is additive to an already-shipped report.

### References

- Epic + story: [epics.md#Epic-18](_bmad-output/planning-artifacts/epics.md:2054), [Story 18.4](_bmad-output/planning-artifacts/epics.md:2080)
- Depends on: [18-2 detection](_bmad-output/implementation-artifacts/18-2-source-change-detection-on-rerun.md), [18-3 impact map](_bmad-output/implementation-artifacts/18-3-downstream-staleness-mapping.md)
- Agent review gates: [base.py:341-347](src/ai_qa/agents/base.py:341) (approve→DONE), [base.py:349-387](src/ai_qa/agents/base.py:349) (reject→re-run)
- Mary group regeneration: [mary.py:979-1059](src/ai_qa/agents/mary.py:979), [mary.py:1074-1087](src/ai_qa/agents/mary.py:1074) (`_replace_source_group`)
- Action dispatch + lock: [bob.py:1698-1727](src/ai_qa/agents/bob.py:1698) (`clarify_answer` precedent), [api/websocket.py:315-388](src/ai_qa/api/websocket.py:315), [api/websocket.py:360](src/ai_qa/api/websocket.py:360)
- FE form routing: [App.tsx:826-1080](frontend/src/App.tsx:826)
- Interrupt recovery: [threads/service.py:264-318](src/ai_qa/threads/service.py:264)
- Safe-overwrite ordering: [artifact_adapter.py:83-108](src/ai_qa/pipelines/artifact_adapter.py:83)
- Coding/testing rules: [project-context.md](project-context.md)
- Related memories: [[stuck-thread-startup-recovery]], [[ws-nonblocking-clarify-timeout-fix]], [[bob-clarify-loop]], [[mary-correct-course-clarify]], [[epic-14-jack-test-execution]], [[app-ui-english-only]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
