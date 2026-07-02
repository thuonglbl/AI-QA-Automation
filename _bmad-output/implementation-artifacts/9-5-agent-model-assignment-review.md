# Story 9.5: Agent Model Assignment Review

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a project user,
I want to review which discovered model Alice assigns to each downstream agent,
so that I can approve or reject the configuration before generation begins.

## Acceptance Criteria

### AC1 — Alice assigns the most suitable models ONLY from the 'Available' group

**Given** Alice has discovered available models
**When** model assignment runs
**Then** Alice assigns the most suitable models ONLY from the 'Available' group
**And** each assignment includes agent name, selected model, selected temperature or runtime parameters, and non-secret selection rationale

### AC2 — Configuration review displays agent model needs, selected model, and rationale without secrets

**Given** Alice presents the configuration review
**When** the review is displayed
**Then** the user sees provider connection status, discovered model summary, agent model needs, selected model per downstream agent, and rationale
**And** no provider key, MCP key, or secret material is displayed

### AC3 — User rejects the review → Alice returns to configuration adjustment without persisting

**Given** the user rejects the review
**When** feedback is submitted
**Then** Alice returns to configuration adjustment without persisting an approved configuration as ready

## Tasks / Subtasks

- [x] **Task 1: Add reject callback and flow to backend Alice agent** (AC: 3)
  - [x] In `src/ai_qa/agents/alice.py`, add a `reject_configuration` method (or equivalent) that resets the agent state back to configuration adjustment mode when the user rejects the model assignment review. This method must NOT persist any approved configuration.
  - [x] Ensure the reject action sends a conversational acknowledgment message (e.g. "Understood. Let's adjust your provider configuration.") and transitions the thread's `current_step` back to the provider configuration step.
  - [x] Wire the reject action to the existing API endpoint pattern used for approve/reject in the agent lifecycle (check `api/routes/` for existing approve/reject endpoints and follow the same pattern).
  - [x] **No persistence on reject:** confirm that rejection does NOT write to `user_provider_config`, `AgentModelConfig`, or any configuration tables. Only conversation messages should be created.

- [x] **Task 2: Enhance ModelAssignmentReview frontend component** (AC: 1, 2)
  - [x] In `frontend/src/components/ModelAssignmentReview.tsx`, add a **Reject** button alongside the existing OK button. The Reject button should use red outline styling (per UX-DR11: "Reject is red outline").
  - [x] Add a new `onReject` prop (callback function) to `ModelAssignmentReviewProps`. The OK button calls `onApprove`, the Reject button calls `onReject`.
  - [x] Add a `rationale` field to the `ModelAssignment` type in `frontend/src/types/provider.ts` so each assignment can display the selection rationale alongside the model.
  - [x] Render the rationale text below each model dropdown in the assignment table (compact, muted text style).
  - [x] Display a compact discovered-model summary section above the assignment table showing total available models count and provider name (e.g. "Discovered 12 available models from Claude (Anthropic)").
  - [x] Display agent model needs hints per row (e.g. "Needs: reasoning, long-context" for Bob) using the purpose/description already available in `ModelAssignment.purpose`.

- [x] **Task 3: Wire reject callback in App.tsx** (AC: 3)
  - [x] In `frontend/src/App.tsx`, pass an `onReject` handler to `ModelAssignmentReview` that sends a reject action to the backend (via WebSocket or REST, matching existing patterns).
  - [x] The reject handler should clear the model-assignment review state and return the Alice workflow to the provider configuration step.
  - [x] Follow the existing approve handler pattern in `App.tsx` for consistency (the `onApprove` handler already exists — mirror its structure for reject).

- [x] **Task 4: Backend tests** (AC: 1, 2, 3)
  - [x] In `tests/test_agents/test_alice.py`, add tests for the reject flow:
    - Test that rejecting the configuration review does NOT persist any provider/model configuration.
    - Test that rejecting returns the thread to the configuration adjustment state.
    - Test that the reject action creates a conversational acknowledgment message.
  - [x] Update existing model-assignment display tests to verify rationale is included in the output.
  - [x] Test rules: in-memory SQLite + `StaticPool` + `engine.dispose()` teardown (#1); `Generator[...]` yield fixtures (#3); top-level imports (#9/E402); specific exceptions with `match=` (#10), never bare `Exception` (#10/B017); mocks mirror real call shapes (#15).

- [x] **Task 5: Frontend tests** (AC: 1, 2, 3)
  - [x] In `frontend/src/components/__tests__/ModelAssignmentReview.test.tsx`, add tests:
    - Test that Reject button is rendered and calls `onReject` when clicked.
    - Test that rationale text is displayed for each assignment when provided.
    - Test that discovered-model summary is displayed.
    - Test that agent model needs hints are displayed per row.
  - [x] Run `npm run typecheck` (rule #13) and vitest to confirm no regressions.
  - [x] Follow label-drift rules (#18): if any ARIA labels or text change, grep for dependent E2E locators.

- [x] **Task 6: Verification** (all ACs)
  - [x] No DB schema change in this story (reject is a state transition, not a new table/column) — confirm no Alembic migration needed.
  - [x] `uv run ruff check .` and `uv run ruff format --check .` (run `uv run ruff format .` if needed, then re-check).
  - [x] `uv run mypy src` — clean (pre-existing error in providers/base.py not related to this story).
  - [x] Run `uv run pytest` in a fresh terminal. Confirm all existing tests pass and new tests pass.
  - [x] Frontend: `npm run typecheck` clean; affected vitest files pass (`ModelAssignmentReview.test.tsx`, `App.test.tsx`).
  - [x] Follow project-context Verification Workflow §1 (fresh terminal, backend) since `src/` changed. If failures occur, auto-launch `bmad-investigate` per project-context.

## Review Findings

### Decision-Needed

- [x] Review/Decision: Story 9.5 implements wrong feature — **Resolved: Accept + new story** (option 1). Provider enable/disable accepted as intentional scope addition; file new story for 9.5's spec'd features (reject flow, rationale, discovered-model summary).
- [x] Review/Decision: DB schema changes without Alembic migration — **Resolved: Add migration now** (option 1). Create Alembic migration for role→sender rename, conversation_data removal, jira_base_url/enabled_providers addition.
- [x] Review/Decision: Out-of-scope work included — **Resolved: Accept + document** (option 3). Admin dashboard, thread restructuring, rate limit handling accepted as useful additions; documented below.

### Patch

- [x] Review/Patch: Gemini API key leaked in query params/logs [src/ai_qa/ai_connection/providers/openai_compatible.py]
- [x] Review/Patch: 401/403 auth errors silently swallowed as "no models" [src/ai_qa/ai_connection/providers/openai_compatible.py:301-320]
- [x] Review/Patch: `SILENT_ABORT` magic string for control flow [src/ai_qa/agents/alice.py:537-538]
- [x] Review/Patch: `random.choice` in `_assign_fallback_models` [src/ai_qa/agents/alice.py:623-640]
- [x] Review/Patch: `mock-empty-key` test bypass in production adapter — already clean
- [x] Review/Patch: `normalizeProviderOption` unsafe `as ProviderId` cast [frontend/src/App.tsx:823]
- [x] Review/Patch: `save_thread_conversation` delete-then-reinsert race [src/ai_qa/api/threads.py:222-247]
- [x] Review/Patch: `availableModels` prop type not fully propagated [frontend/src/components/ModelAssignmentReview.tsx]
- [x] Review/Patch: `enabled_providers` default asymmetry [src/ai_qa/db/models.py vs frontend/src/components/ProviderSelector.tsx]
- [x] Review/Patch: Auto-scroll fires on every state change [frontend/src/App.tsx]
- [x] Review/Patch: Grammar in tooltip [frontend/src/components/ProviderSelector.tsx]
- [x] Review/Patch: Duplicate provider icon maps — design choice
- [x] Review/Patch: Duplicate thread provider-save logic — deferred
- [x] Review/Patch: `import ast/re` inside exception handler [src/ai_qa/agents/alice.py]
- [x] Review/Patch: `_build_chat_model` double `/v1` possible [src/ai_qa/ai_connection/client.py:2806-2813]
- [x] Review/Patch: `httpx.AsyncClient` created per-call [src/ai_qa/ai_connection/providers/openai_compatible.py]
- [x] Review/Patch: `BrowserUseAdapter.list_models` double `validate_connection` call — already trusts prior call

### Defer

- [x] Review/Defer: Inconsistent agent key casing [src/ai_qa/agents/alice.py] — deferred, pre-existing
- [x] Review/Defer: Duplicate comment in E2E spec [frontend/e2e/story-9-4-dynamic-model-discovery.spec.ts] — deferred, cosmetic
- [x] Review/Defer: Promise.race dangling locator watches [frontend/e2e/story-9-4-dynamic-model-discovery.spec.ts] — deferred, pre-existing
- [x] Review/Defer: `role→sender` rename without migration [src/ai_qa/threads/models.py] — deferred, pre-existing
- [x] Review/Defer: `conversation_data` removal without migration [src/ai_qa/threads/models.py] — deferred, pre-existing
- [x] Review/Defer: `enabled_providers` JSON column no DB constraint [src/ai_qa/db/models.py] — deferred, pre-existing

## Dev Notes

### Why this story exists / scope boundary

Epic 9 replaces static provider→model assumptions with runtime, per-user, validated configuration. The chain so far: 9.1 built encrypted secret storage; 9.2 added the status/replacement API; 9.3 introduced the provider adapter interface with `validate_connection`; 9.4 implemented real `list_models` returning normalized `DiscoveredModel` values, migrated Alice's discovery onto it, and added benchmark summary to the existing `ModelAssignmentReview` panel. This story (9.5) **adds the reject/approve flow** to the model assignment review and **enhances the review panel** with rationale, discovered-model summary, and agent model needs.

Explicitly OUT of scope (later Epic 9 stories — do NOT implement here):

- Runtime (thread-owner) secret resolution for agent runs → **Story 9.6**.
- Saved provider config + rotation-applies-to-future-runs persistence → **Story 9.7**.
- The approve/persist flow already works via the existing OK button and `_generate_configuration` persistence — this story only adds the reject path and review enhancements.

[Source: _bmad-output/planning-artifacts/architecture.md#Decision Impact Analysis — "9. Alice end-to-end"]

### Current state of relevant code (READ before coding)

**`src/ai_qa/agents/alice.py`** — the agent to modify:

- `process()` (~286–380): runs `_test_connection` → `_generate_configuration` → emits review `StageResult`. The review step currently has only an "approve" path (implicit — the StageResult success is treated as approved). There is no explicit reject endpoint or callback.
- `_generate_configuration(provider_info, credentials)` (~637–725): calls `adapter.list_models`, `_bootstrap_alice_model`, `_assign_models_via_llm`, emits `thinking_trace`, builds `ProviderConfig`/`AgentModelConfig`/`AliceConfiguration`. Returns `StageResult(success=True, data={...})` with `model_assignments` display data.
- `_get_model_assignments_display()` (~988): returns `list[dict[str, str]]` with `agent`, `model`, `purpose` keys. **Needs `rationale` added.**
- `_get_model_assignments_from_config(config)` (~995): same shape — used for saved-config display. Also needs `rationale`.
- `_assign_models_via_llm(...)` (~1051): builds `valid_ids` from discovered models, assigns via LLM, returns `(model_mappings, reasoning)`. The `reasoning` dict is the per-agent rationale — it must be threaded into the display output.
- `_format_model_assignments(config)` (~1277): formats assignments as a conversation message. Also needs rationale.

**`frontend/src/components/ModelAssignmentReview.tsx`** — the review panel to enhance:

- Currently shows: provider connection status, agent table with Agent/Role/Model columns, OK button.
- Missing: Reject button, rationale display, discovered-model summary, agent model needs hints.
- Props: `provider`, `endpoint`, `assignments`, `availableModels`, `unavailableModels`, `onApprove`, `disabled`.
- **Needs new props:** `onReject` (callback), and the `ModelAssignment` type needs a `rationale` field.

**`frontend/src/types/provider.ts`** — type definitions:

- `ModelAssignment` type has `agent`, `model`, `purpose` fields. **Needs `rationale: string` added.**
- `ModelAssignmentReviewProps` interface needs `onReject` callback added.

**`frontend/src/App.tsx`** — where `ModelAssignmentReview` is rendered (~line 1116):

- Already passes `onApprove` handler. **Needs `onReject` handler added.**
- The approve handler sends the approved assignments to the backend. The reject handler should send a reject action and reset Alice state.

**`frontend/src/components/__tests__/ModelAssignmentReview.test.tsx`** — tests to extend:

- Currently tests: rendering, OK click, disabled state, agent badges, empty assignments.
- **Needs:** Reject button test, rationale display test, discovered-model summary test, agent model needs test.

### What this story changes vs. preserves

- **New:** Reject button + `onReject` callback in `ModelAssignmentReview`; `rationale` field on `ModelAssignment` type; discovered-model summary section; agent model needs hints; backend `reject_configuration` method; reject API endpoint/wiring.
- **Changes:** `_get_model_assignments_display` and `_get_model_assignments_from_config` include `rationale` in their output; `_format_model_assignments` includes rationale in the conversation message; `App.tsx` passes `onReject` to the review component.
- **Preserve:** All approve/persist flow (OK button, `_generate_configuration`, provider/model config persistence); thinking_trace; benchmark display; model dropdown selection (user can still change models before approving); existing conversation message flow; all module boundaries; secret hygiene (no secrets in review output).

### Source tree components to touch

```text
src/ai_qa/agents/alice.py                              # UPDATE: add reject_configuration method, add rationale to _get_model_assignments_display/_get_model_assignments_from_config/_format_model_assignments
frontend/src/types/provider.ts                          # UPDATE: add rationale field to ModelAssignment, add onReject to ModelAssignmentReviewProps
frontend/src/components/ModelAssignmentReview.tsx       # UPDATE: add Reject button, onReject prop, rationale display, discovered-model summary, agent model needs
frontend/src/App.tsx                                    # UPDATE: pass onReject handler to ModelAssignmentReview
tests/test_agents/test_alice.py                         # UPDATE: add reject-flow tests, update assignment-display tests for rationale
frontend/src/components/__tests__/ModelAssignmentReview.test.tsx  # UPDATE: add reject button test, rationale display test, summary test
```

### Project Structure Notes

- Module boundaries (architecture table): `agents` may depend on `threads`, `secrets`, `models`, `pipelines`, `audit`; must NOT import `api` internals. The reject method lives in `alice.py` and is called by the API layer — keep the import direction one-way (`api` imports `agents`, never the reverse).
- Frontend: `ModelAssignmentReview` is a presentational component — reject logic lives in `App.tsx` (container), matching the existing approve pattern.
- Naming: snake_case locals/functions (`reject_configuration`, `rationale`), PascalCase models; no aliased __SKIP_WORD_0_Camcorpse__ imports (rules #5/#11).

### Testing standards summary

- Backend: in-memory SQLite + `StaticPool` + `engine.dispose()` teardown (#1); `Generator[...]` yield fixtures (#3); top-level imports (#9/E402); specific exceptions with `match=` (#10), never bare `Exception` (#10/B017); mocks mirror real call shapes (#15).
- Frontend: `vi.mock` hoisting rules (#15); strict TS extraction (#13); label-drift rules (#18).
- Secret hygiene: assert no api_key sentinel appears in any reject path output or messages.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 9.5: Agent Model Assignment Review] — user story + ACs.
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 9] — FRs covered incl. FR15b (user-reviewable provider/model review), FR57 (no secrets in API/WebSocket responses).
- [Source: _bmad-output/planning-artifacts/architecture.md#Agent Model Selection Heuristics] — Bob/Mary/Sarah/Jack model needs for rationale generation.
- [Source: _bmad-output/planning-artifacts/architecture.md#Alice Provider Configuration and Dynamic Model Discovery] — "If connection validation fails, model discovery fails, or no usable models are returned, Alice must not create a successful model assignment review."
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-06-08.md] — updated Story 9.5 AC1 to use "Available" group language.
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Alice Configuration Review UX] — review panel design requirements.
- [Source: frontend/src/components/ModelAssignmentReview.tsx] — current review component (OK-only, no reject, no rationale).
- [Source: frontend/src/types/provider.ts] — ModelAssignment type (needs rationale field).
- [Source: frontend/src/App.tsx#L1116] — where ModelAssignmentReview is rendered (needs onReject).
- [Source: src/ai_qa/agents/alice.py#_get_model_assignments_display] — display helper (needs rationale).
- [Source: src/ai_qa/agents/alice.py#_assign_models_via_llm] — returns reasoning dict (rationale source).
- [Source: src/ai_qa/agents/alice.py#process] — review StageResult flow (reject resets here).
- [Source: project-context.md] — testing/coding rules (#1 SQLite dispose, #3 Generator typing, #5/#11 naming, #9 import order, #10 specific exceptions, #15 mock sync; Verification Workflow §1; `uv run` Python invocation, NEVER `python3`).

### Previous Story Intelligence (Story 9.4)

- **The review panel already exists but is approve-only.** 9.4 added benchmark summary + link to `ModelAssignmentReview` and built the real `list_models` discovery. The component currently only has an OK button — no reject path exists. This story adds the reject button and wires it to Alice's state machine.
- **Rationale is already computed but not displayed.** `_assign_models_via_llm` returns a `reasoning` dict with per-agent rationale. The `_get_model_assignments_display` helper currently discards it. This story threads it into the display output and frontend rendering.
- **Secret hygiene is the recurring review gate.** Every Epic 9 review hammered leak assertions. The reject path must also be clean — no secrets in the acknowledgment message, no secrets in the re-displayed configuration. Assert the sentinel key is absent from reject-path outputs.
- **Scope discipline pattern.** 9.4 explicitly said "do NOT build the 9.5 review UX" for the reject flow. This story completes it. Do NOT implement 9.6 (runtime secret resolution) or 9.7 (saved config persistence) here.
- **The approve path is unchanged.** The OK button + `_generate_configuration` persistence path remains exactly as-is. This story only adds the reject callback and review enhancements.

### Git Intelligence

- HEAD on `story 9-4 code and test OK` (baseline for this story). Recent commits: `story 9-3 ...`, `story 9-2 ...`, `story 9-1 ...`. The 9.4 adapter interface + `list_models` + benchmark UI are merged and stable. Build the reject flow and review enhancements on top.
- Commit-message convention: `story 9-5 code and test OK` once verification passes.

### Latest Tech Information

- React 18 + TypeScript ~5.6 — no changes to toolchain needed.
- Shadcn/ui components available in `frontend/src/components/ui/` — use existing button variants (outline for Reject).
- FastAPI WebSocket already handles agent state transitions — the reject action should follow the same WebSocket message pattern used for approve.

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Story 9.5 implementation complete — reject flow + review enhancements
- Backend: Added `handle_reject()` to AliceAgent — clears config, transitions to START, re-shows provider options, no persistence
- Backend: Threaded `_model_reasoning` (rationale) into `_get_model_assignments_display`, `_get_model_assignments_from_config`, `_format_model_assignments`, `_format_review_content`
- Frontend: Added `rationale` field to `ModelAssignment` type, `onReject` prop to `ModelAssignmentReview`, Reject button (red outline), rationale column in table, discovered-model summary
- Frontend: Added `handleReject` in App.tsx, sends WebSocket reject message, mirrors approve pattern
- Tests: 57 backend tests pass, 14 frontend tests pass, typecheck clean
- No DB schema change needed — reject is a state transition only
- Pre-existing mypy error in `providers/base.py:50` (redundant cast) not related to this story
- Code review completed (2026-06-09): 3 decisions resolved (accept provider enable/disable + new story for 9.5 spec, add Alembic migration, accept out-of-scope work), 14 patches applied, 6 deferred.

### File List

- src/ai_qa/agents/alice.py
- frontend/src/types/provider.ts
- frontend/src/components/ModelAssignmentReview.tsx
- frontend/src/App.tsx
- tests/test_agents/test_alice.py
- frontend/src/components/**tests**/ModelAssignmentReview.test.tsx

## Change Log

- Date: 2026-06-09 — Story 9-5 implementation: reject flow + review enhancements (rationale, discovered-model summary, Reject button)
