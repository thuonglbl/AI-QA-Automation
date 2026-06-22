---
baseline_commit: d97e58533b04901b688a1c04f24032cfc8dc0e53
---
# Story 16.7: Alice Configuration Review UX Integration

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Alice's provider/model review UI exists (`ProviderSelector`, `ModelAssignmentReview`). This story closes two named gaps: the **scoring rationale is not rendered** in the assignment table, and the **credential-status feedback on save/continue** is indirect. Keep everything secret-safe.

## Story

As an admin or QA user,
I want Alice configuration decisions represented clearly in the conversational UI,
so that project/provider/model setup is reviewable, safe, and understandable.

## Acceptance Criteria

1. **Secret-safe config review.** Given Alice performs project setup or provider/model configuration, when the review step is shown, then the UI displays project scope, provider names, selected models, discovered-model scores, and assignment recommendations using secret-safe labels only (no api keys, no raw endpoints/credentials).

2. **Disabled save/continue on bad credentials.** Given provider credentials are missing, invalid, or untested, when the user attempts to save or continue, then save/continue controls are disabled with clear recovery guidance.

3. **Per-agent assignment with rationale + editable controls.** Given Alice proposes per-agent model assignments, when the user reviews assignments, then each assignment shows the agent, selected provider/model, scoring rationale, and editable selection controls where allowed.

## Tasks / Subtasks

- [ ] **Task 1 — Render the scoring rationale in the assignment table (AC: 3) [PRIMARY GAP]**
  - [ ] `ModelAssignmentReview` receives `rationale` per assignment (the TS `ModelAssignment.rationale` exists and the backend sends it) but does NOT render it ([frontend/src/components/ModelAssignmentReview.tsx](frontend/src/components/ModelAssignmentReview.tsx)). Add a rationale column/row (or expandable) showing the secret-free scoring reason per agent.
  - [ ] Confirm the backend supplies rationale via `AliceAgent._get_model_assignments_display()` → `{agent, model, purpose, rationale}` and the `model_assignments` payload ([src/ai_qa/agents/alice.py](src/ai_qa/agents/alice.py)). Source: deterministic selection ([[alice-model-selection]]).
  - [ ] Keep the editable per-agent `<select>` (user override wins — `handle_approve` applies `data.assignments`). Do not regress the override path.

- [ ] **Task 2 — Show discovered-model scores + project/provider scope (AC: 1)**
  - [ ] Confirm the review shows project scope, provider name (not endpoint), selected models, and discovered-model count. Surface discovered-model **scores** (the admin benchmark scores that drive Tier-0 selection) where available, secret-safe.
  - [ ] Audit that NO credential/endpoint/api-key string is rendered. Provider name + masked endpoint only (`_mask_endpoint`).

- [ ] **Task 3 — Disabled save/continue with recovery guidance on bad credentials (AC: 2) [GAP]**
  - [ ] Today the approve/continue is disabled indirectly via `!isConnected || status === "error"`. Make the disabled state explicit about WHY: missing credentials → "enter credentials"; invalid/failed test → "connection failed, fix and retry"; untested → "test the connection first". Reuse the disabled-with-reason pattern from [16-2](16-2-stateful-workflow-controls.md).
  - [ ] Confirm `ProviderSelector` credential validation (required fields, valid URL) and the connection-test flow feed this state ([frontend/src/components/ProviderSelector.tsx](frontend/src/components/ProviderSelector.tsx)).

- [ ] **Task 4 — Tests (AC: 1, 2, 3)**
  - [ ] Extend `ModelAssignmentReview.test.tsx`: rationale renders per agent; provider name shown but no key/endpoint; the OK/continue button disables with a reason when not connected / test failed; per-agent override still calls `onApprove` with the selected model map.
  - [ ] If a backend payload field is added, update the TS interface in `frontend/src/types/provider.ts` and `npm run build`; backend `uv run pytest` for the alice payload.
  - [ ] `npm run typecheck` + `npm run lint` + `npm test` green.

## Dev Notes

### What already exists (do not rebuild)

- **`ProviderSelector`** — provider choice + credential form (api_key / SSO), required-field + URL validation, auto-connect with a stored key, SSO IdP poll with timeout.
- **`ModelAssignmentReview`** — "Connected successfully to {provider}!" + discovered-model count + a 3-column table (Agent w/ color dot | Role/purpose | Model `<select>`), OK button. Disabled via `disabled` prop. Secret-safe today (provider name only).
- **Backend** — `AliceAgent.handle_approve()` applies `data["assignments"]` (per-agent overrides win); `_get_model_assignments_display()` returns `{agent, model, purpose, rationale}`; the `StageResult` carries `configuration`, `model_assignments`, masked `provider_endpoint`, `benchmark`. Selection is deterministic 3-tier ([[alice-model-selection]]).
- **TS** — `ModelAssignment {agent, model, purpose, rationale}` + `ModelAssignmentMessage` in `frontend/src/types/provider.ts`.

### The named gaps

1. **Rationale not rendered** — the field is sent + typed but the table omits it (AC3).
2. **Indirect disabled reason** — save/continue disables on `!isConnected`/`error` without telling the user which credential problem to fix (AC2).
3. **Discovered-model scores** — confirm they are visible (Tier-0 admin benchmark scores); surface secret-safe if missing (AC1).

### Source tree components to touch

- `frontend/src/components/ModelAssignmentReview.tsx` — **UPDATE** (render rationale + scores; explicit disabled reason).
- `frontend/src/components/ProviderSelector.tsx` — **READ / VERIFY** credential validation + connection-test → disabled state.
- `frontend/src/App.tsx` — **READ / VERIFY** disabled-state wiring (`!isConnected || status === "error"`) + `handleApprove`.
- `src/ai_qa/agents/alice.py` — **READ ONLY** (payload shape); edit only if a needed field (e.g. score) isn't sent.
- `frontend/src/types/provider.ts` — **UPDATE** only if a payload field is added.
- `frontend/src/components/__tests__/ModelAssignmentReview.test.tsx` — **UPDATE**.

### Current behavior to PRESERVE (regression guardrails)

- Deterministic model selection — NEVER reintroduce an LLM call for per-agent assignment ([[alice-model-selection]], [[project-context]]).
- Per-agent user override applied after selection (always wins) — keep the `<select>` → `data.assignments` → `handle_approve` path.
- Secret-safety: provider name + masked endpoint only; never render keys/endpoints; runtime-resolved secrets only.
- App-UI-English-only ([[app-ui-english-only]]).
- Model benchmark scores + new-model flagging live in the Admin Dashboard "Model Benchmark Overrides" and need `alembic upgrade head` ([[alice-model-selection]]).

### Testing standards summary

- Vitest 4 + RTL; assert rationale text per agent, provider name present + no key substring, disabled button + reason. Mock fetch via `vi.spyOn` per [[project-context]].
- Full-stack sync: any backend payload change updates the TS interface in the same change (`npm run build`).

### Project Structure Notes

- Mostly FE; backend read-only unless a score/rationale field must be added to the payload (then update the TS interface + a backend test). No schema/migration expected.

### References

- Epic + ACs: [epics.md#Story-16.7](_bmad-output/planning-artifacts/epics.md:1828)
- Coding/testing rules: [project-context.md](project-context.md)
- Related: [16-2](16-2-stateful-workflow-controls.md), [[alice-model-selection]], [[app-ui-english-only]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
