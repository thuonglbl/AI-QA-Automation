---
baseline_commit: 345ef89a866a3e1b68f03bfea4d17571586909f0
---
# Story 9.7: Saved Provider Configuration and Rotation Behavior

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a returning project user,
I want my non-secret provider/model configuration remembered while secret rotation applies only to future runs,
so that setup is convenient without rewriting conversation history.

## Acceptance Criteria

### AC1 — Approved Configuration Persisted (non-secret only)

**Given** a user approves Alice's provider/model configuration
**When** the configuration is saved
**Then** PostgreSQL stores selected provider, selected model assignments, non-secret runtime settings (e.g. temperature), and selection rationale
**And** encrypted secret values remain in separate per-user secret storage (`user_secrets`) — never copied into the config storage

### AC2 — Future Thread Offers Saved Config via Explicit Action

**Given** a user starts a future thread (bound to a project the user is a member of)
**When** a valid saved provider configuration exists for that (user, project) — config present AND its provider is still allowed by the project's `enabled_providers` AND the required provider secret is still configured
**Then** Alice exposes the saved configuration through an explicit UI inspect/use/change action (NOT auto-applied silently)
**And** returning users are NOT shown noisy saved-config chat messages automatically (no auto "Welcome back, using your saved…" narration); the user must explicitly choose to reuse it or pick a different provider before the pipeline proceeds

### AC3 — Rotation Applies to Future Runs Only; History Immutable

**Given** a user rotates an AI provider or MCP secret
**When** future runs execute
**Then** future runs use the rotated value (resolved at execution time per Story 9.6)
**And** existing thread messages, conversation history, previous `agent_runs` metadata, and previously saved per-thread/per-(user,project) config snapshots remain unchanged

## Resolved Design Decisions (confirmed by product owner 2026-06-10)

1. **Storage granularity = per-(user, project).** One user works across multiple projects; within a single project the user may pick different providers across threads depending on quota/policy; within a single thread exactly one provider is used. Therefore the "remembered" config is stored per **(user_id, project_id)** as a default *suggestion*, NOT a single per-user value and NOT a per-thread lock.
2. **Behavior = Always-explicit.** A valid saved config is NEVER auto-applied silently. On a new thread Alice presents an explicit "[Use saved configuration] / [Choose a different provider]" affordance (pre-highlighting the last-used provider for that project). The user must click to proceed. This honors the per-thread provider flexibility above.
3. **Harden corrupt-ciphertext handling (in scope).** When a user secret fails to decrypt, treat it as missing/invalid (return `None`) so `get_llm_config` raises the UX-DR12 actionable error, instead of using raw ciphertext as the API key. Limited to the user-secrets ORM type.

## Tasks / Subtasks

- [x] **Task 1: New per-(user, project) saved-config table + migration** (AC: 1)
  - [x] In `src/ai_qa/db/models.py`, add ORM model `AiProviderConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base)`, `__tablename__ = "ai_provider_configs"`:
    - `user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)`
    - `project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)`
    - `ai_provider_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)`
    - `ai_agents_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)`
    - `__table_args__ = (UniqueConstraint("user_id", "project_id", name="uq_ai_provider_configs_user_project"),)`
    - Add `from typing import Any` import if absent. Mirror `ProjectMembership` (db/models.py:77-95) for the FK + unique-constraint pattern.
  - [x] Create an Alembic migration. Current head is `7cef1ea1a837` (verify with `uv run alembic heads`). Set `down_revision = "7cef1ea1a837"`. Follow the header style of `alembic/versions/b7d2f1a9c4e5_add_user_secrets_drop_inline_keys.py`.
    - `upgrade()`: `op.create_table("ai_provider_configs", ...)` with the columns above + `UniqueConstraint` + FK constraints; `op.create_index` on user_id and project_id.
    - `downgrade()`: `op.drop_table("ai_provider_configs")`.
  - [x] These columns store **non-secret** data only. NEVER write any `api_key`/secret value into them (AC1 leakage guard). The provider secret continues to live exclusively in `user_secrets`.
  - [x] Run `uv run alembic upgrade head` and confirm the table exists.

- [x] **Task 2: Persist non-secret config on approve** (AC: 1)
  - [x] Create `src/ai_qa/userconfig/__init__.py` and `src/ai_qa/userconfig/service.py` (mirror `src/ai_qa/secrets/service.py` — module-level functions taking `db: Session`). Functions:
    - `save_provider_config(db, user_id, project_id, provider_config: dict, agents_config: dict) -> None` — upsert the single `(user_id, project_id)` row (SELECT-then-update/insert like `set_user_secret`). Caller commits.
    - `get_provider_config(db, user_id, project_id) -> dict | None` — return `{"provider": dict, "agents": dict}` or `None`.
  - [x] Define the exact JSON shapes (module docstring + a frozen dataclass/TypedDict for readers):
    - `ai_provider_config`: `{"provider": str, "provider_name": str, "endpoint": str, "tested_at": str, "test_result": "success"|"failed", "rationale": str}`
    - `ai_agents_config`: `{"version": str, "updated_at": str, "agents": {<agent_name>: {"model": str, "temperature": float, "prompt_template": str, "tools": list[str], "rationale": str}}}`
  - [x] In `src/ai_qa/agents/alice.py` `handle_approve()` (lines 597-624): after the successful `self._save_configuration(...)` (thread snapshot), ALSO call `save_provider_config(db, user_id, self.project_context.project_id, ...)` built from `self._configuration` + `self._model_reasoning`. Wrap in the same try/except; commit the session. (`project_id` comes from `self.project_context.project_id` — the thread is already project-bound at approve time.)
  - [x] Build `agents[name]["rationale"]` from `self._model_reasoning` (list of `{"agent","model","rationale"}` — `_assign_models_via_llm`, alice.py:1139-1145) and `temperature` from each `AgentModelConfig.temperature`. Do NOT fabricate a rationale when none exists — use empty string.

- [x] **Task 3: Persist temperature + rationale in the thread snapshot; fix format inconsistency** (AC: 1, 2)
  - [x] **CRITICAL pre-existing bug**: `_save_configuration` (alice.py:1002-1007) writes `thread.agent_configs = {name: agent_cfg.model}` (flat string); `base.py._load_agent_config` (line 122) reads it as a flat string; but `check_existing_configuration` (alice.py:231-237) reads `agent_cfg.get("model_name")` expecting a dict → returning users get `model=None`. Unify the format.
  - [x] Change `_save_configuration` to write structured per-agent entries: `thread.agent_configs = {name: {"model": cfg.model, "temperature": cfg.temperature, "rationale": <from _model_reasoning>} ...}`.
  - [x] Update `src/ai_qa/agents/base.py` `_load_agent_config()` (lines 121-124) to read the structured shape AND tolerate the legacy flat-string shape (back-compat for existing threads):
    - dict value → `model_name = value.get("model")`, `temperature = value.get("temperature", 0.0)`.
    - str value → `model_name = value`, `temperature = 0.0`.
    - Set `self._agent_config = {"model_name": model_name, "temperature": temperature}` so `get_llm_config()` (base.py:191) persists the saved temperature instead of always defaulting to 0.0.
  - [x] Update `check_existing_configuration()` (alice.py:218-253) to read the same structured/legacy shapes and populate `temperature` + per-agent `rationale` (so a resumed thread's inspect view shows real values, not `model=None`/empty rationale).

- [x] **Task 4: Explicit "use saved / change" flow on new thread** (AC: 2)
  - [x] In `alice.py` `handle_start()` (lines 419-585): the existing branch at line 518 (`if existing_config and not input_data.get("force_reconfigure")`) currently transitions to `REVIEW_REQUEST` and **auto-sends a model-assignment chat message** (525-535). Replace this auto-apply behavior. New logic after project binding:
    - Resolve a saved-config candidate for `(user_id, project_id)` via `get_provider_config(db, user_id, project_id)`.
    - Compute **validity**: provider ∈ `project.enabled_providers` (Story 9.5 restriction — empty/missing list means all allowed, per Project model comment db/models.py:60-63) AND the provider secret is configured (`get_user_secret(db, user_id, PROVIDER_SECRET_TYPE_MAP.get(provider)) is not None`; guard the `.get()` returning `None` for unknown provider).
    - If a **valid** saved config exists AND no provider chosen yet AND not `force_reconfigure`: send ONE `info` message whose metadata offers an explicit choice (e.g. `{"type": "saved_config_prompt", "saved_config": <non-secret summary: provider_name, masked endpoint, per-agent model+rationale>, "options": self.get_provider_options(), "enabled_providers": project.enabled_providers}`). Do NOT transition to DONE and do NOT auto-apply. Wait for the user's explicit action.
    - When the user picks **"Use saved configuration"** (frontend sends `input_data={"use_saved_config": true}`): load the saved config into `self._configuration`, write the thread snapshot (`_save_configuration`), transition to `DONE`. (Secret resolved at runtime by Story 9.6 — never sent to the frontend.)
    - When the user picks **"Choose a different provider"** (frontend sends a normal provider selection or `force_reconfigure`): run the existing provider-selection flow.
  - [x] If NO valid saved config: fall through to the current greeting + provider-options flow unchanged.
  - [x] NEVER auto-emit a "Welcome back" / "Using your saved configuration" narration (UX spec lines 1748-1756). The only saved-config surface is the explicit affordance.
  - [x] Preserve the `force_reconfigure` escape hatch for the "Change configuration" affordance on an already-configured thread.

- [x] **Task 5: API endpoint for explicit inspection** (AC: 2)
  - [x] Add `GET /api/threads/{thread_id}/provider-config` (in `src/ai_qa/api/threads.py`). Returns the **non-secret** config for that thread: the thread snapshot if present, else the saved `(user, project)` default. Derive `project_id` from the thread.
  - [x] New response schema `ProviderConfigResponse` (threads `schemas.py`): `{ "configured": bool, "source": "thread"|"saved"|"none", "provider": str|None, "provider_name": str|None, "endpoint": str|None, "test_result": str|None, "tested_at": str|None, "agents": list[{"agent": str, "model": str, "temperature": float, "rationale": str}] }`.
  - [x] MUST mask the endpoint (reuse `_mask_endpoint` style, alice.py:1274) and MUST NOT return any secret value or `credential_reference`. Return `configured: false`, `source: "none"` when nothing saved.
  - [x] Authorization: thread owner only — reuse `ThreadService.assert_thread_access` (threads/service.py:281) and the existing auth dependency (see `tests/api/test_provider_config_persistence.py` `_auth_headers`).

- [x] **Task 6: Harden corrupt-ciphertext handling** (AC: 3; resolves deferred-work.md#L94)
  - [x] In `src/ai_qa/db/types.py`, `UserSecretEncryptedString.process_result_value` (lines 81-88): on Fernet decrypt failure, return `None` (treat as missing/invalid) instead of returning the raw ciphertext via `cast(str, value)`. This makes `get_llm_config` (base.py:158-186) raise the UX-DR12 "key not configured/invalid" error rather than sending garbage to the provider.
  - [x] Scope this change to `UserSecretEncryptedString` ONLY — do NOT change `EncryptedString` (shared DB-column type) behavior.
  - [x] Verify it does NOT break valid round-trips: tests use a real `USER_SECRETS_ENCRYPTION_KEY` so encrypt→decrypt succeeds and this branch is not hit for good data. Add a test that stores a deliberately corrupt value and asserts `get_user_secret` returns `None` (not ciphertext).

- [x] **Task 7: Frontend — saved-config affordance + inspect/change** (AC: 2)
  - [x] Handle the `saved_config_prompt` message in `App.tsx` (`handleAliceMessage`, ~line 540): render an explicit choice UI — pre-highlight the saved provider with a "Use saved configuration ({provider}, N models)" primary button and a "Choose a different provider" secondary that opens the existing `ProviderSelector`. This is the Step-1 selection UI with a default — NOT a chat narration.
    - "Use saved configuration" → send WebSocket `{ type: "start", step: 1, inputData: { use_saved_config: true } }`.
    - "Choose a different provider" → reveal `ProviderSelector` as today (respect `enabled_providers` from the message metadata, Story 9.5).
  - [x] Add a persistent "Provider Configuration" inspect affordance (gear/"Config") in the agent/thread top bar (`src/components/AgentTopBar.tsx` or App.tsx top bar ~line 971). On click, fetch `GET /api/threads/{thread_id}/provider-config` and show provider/per-agent model+temperature+rationale + test status. Never display secrets. Include a "Change configuration" button → send `{ type: "start", step: 1, inputData: { force_reconfigure: true } }`.
  - [x] Ensure returning users do NOT see a synthesized saved-config chat message — the only saved-config surfaces are the explicit prompt (Step 1) and the inspect affordance.
  - [x] Add TS types in `src/types/provider.ts` (`ProviderConfigResponse`, `SavedConfigPrompt`) and an API client function in `src/lib/` (mirror `src/lib/threads.ts`). Run `npm run typecheck`.

- [x] **Task 8: Backend tests — rewrite/extend persistence + rotation coverage** (AC: 1, 2, 3)
  - [x] **Rewrite the misleading parts of** `tests/api/test_provider_config_persistence.py`. Its current 7 tests only exercise secret rotation via `PUT /api/secrets/{type}` while their docstrings claim AC1/AC2/AC3 *config* coverage — they do not. Keep the working secret-rotation tests; add real coverage:
    - AC1: approving config upserts provider + per-agent model + temperature + rationale into `ai_provider_configs` keyed `(user_id, project_id)`; assert the stored blobs contain NO secret sentinel value (leakage guard); assert one row per `(user, project)` after repeated approvals.
    - AC1/AC2: `GET /api/threads/{thread_id}/provider-config` returns the non-secret config and never the secret; returns `configured: false`/`source: none` when nothing saved; rejects non-owner (403).
    - AC2: validity gating — saved config whose provider is NOT in `project.enabled_providers` is treated as invalid; saved config whose provider secret is deleted is treated as invalid (Alice does NOT offer it).
    - AC3: after `PUT /api/secrets/{type}` rotation, `ai_provider_configs`, the thread snapshot, persisted `messages`, and `agent_runs.execution_metadata` are unchanged; a subsequent secret resolution returns the rotated value.
  - [x] Follow the canonical fixture scaffold already in this file (in-memory SQLite + `StaticPool`, `Generator[...]` yield fixture, `engine.dispose()` teardown, `cast(FastAPI, client.app)`). When creating tables, include `User`, `Project`, `ProjectMembership`, `UserSecret`, `AiProviderConfig`, `Thread`, `Message`, `AgentRun` `__table__`s as needed.
  - [x] Unit tests in `tests/test_agents/test_alice.py`: save→load round-trip preserves model + temperature + rationale; `check_existing_configuration` returns real model (not `None`) + rationale for both structured and legacy flat-string thread snapshots; the saved-config path emits a `saved_config_prompt` (NOT auto-apply, NOT a chat narration — patch `broadcast_message` and assert); `use_saved_config=true` writes the thread snapshot and transitions to `DONE`; `force_reconfigure=true` re-runs provider selection; invalid saved config (provider disabled / secret missing) falls through to provider selection.
  - [x] Unit test `src/ai_qa/userconfig/service.py` in `tests/unit/test_userconfig_service.py` (mirror `tests/unit/test_secret_service.py`): upsert keeps one row per `(user, project)`; independent rows for different projects of the same user; `get_provider_config` returns `None` when absent.
  - [x] Unit test the Task 6 hardening: corrupt stored ciphertext → `get_user_secret` returns `None`.
  - [x] On-prem leak (Task 10): extend `tests/api/test_secret_leakage.py` — assert the `SECRET_TYPE_ON_PREMISES` value NEVER appears in the `provider_options`/`on_prem_defaults` WebSocket metadata emitted by `handle_start` (patch `broadcast_message`, scan all payloads); assert a blank-api_key on-prem submit reuses the stored secret without overwriting it (stored value unchanged after submit).

- [x] **Task 9: Frontend tests** (AC: 2)
  - [x] Unit: `__tests__` test for the inspect panel + saved-config prompt component (mirror `src/components/__tests__/ModelAssignmentReview.test.tsx`); mock the api client with `vi.mock`. Assert it renders provider/model/rationale, never a secret; "Use saved configuration" and "Change configuration" fire the right callbacks.
  - [x] E2E: `frontend/e2e/story-9-7-saved-config.spec.ts` following `story-9-4`/`story-9-5` patterns (bootstrap user via Admin token + `createStandardUser`/`createAdminProject`/`assignMembership`; real provider key from env, skip if absent/placeholder; `test.afterEach` cleanup of users/projects/artifacts). Cover: approve config in thread A → open a NEW thread in the same project → assert NO auto saved-config chat message; assert the explicit "[Use saved configuration] / [Choose a different provider]" prompt appears; clicking "Use" completes Step 1 without re-entering the key; clicking "Choose a different provider" reveals the selector; the gear inspect affordance shows the saved provider/models (no secret).

- [x] **Task 10: Fix on-premises API key leak to frontend** (AC: 1; secret hygiene / FR57 / FR58)
  - [x] **Pre-existing leak (must fix here)**: `get_on_prem_defaults()` (alice.py:273-298) returns the decrypted on-prem `api_key` (line 293); `handle_start` puts it into the `on_prem_defaults` WebSocket metadata (line 583); `ProviderSelector` pre-fills it into the password field (ProviderSelector.tsx:95-96). This serializes a stored secret into a WebSocket payload — violates FR57 / architecture.md#L365 ("stored values never returned through API/WebSocket") and FR58 ("UI never reveals existing secret values").
  - [x] Backend — stop returning the value: change `get_on_prem_defaults()` to return ONLY non-secret fields `{"server_url": str, "api_key_configured": bool}` (the boolean = whether a `SECRET_TYPE_ON_PREMISES` secret exists). NEVER return the value. Update the `on_prem_defaults` metadata shape accordingly.
  - [x] Backend — reuse without reveal: in `process()` (alice.py:304-417), when the submitted on-prem `credentials["api_key"]` is blank/missing AND a stored on-prem secret exists, resolve and use the stored secret for the connection test; do NOT overwrite the stored secret with blank. Only call `set_user_secret` when a new non-blank key is actually submitted.
  - [x] Frontend — no pre-fill: `ProviderSelector` must NOT pre-fill the api_key field. When `api_key_configured` is true, show a non-secret "Key on file — leave blank to reuse" hint and treat a blank api_key submit as "reuse saved key". Update the `onPremDefaults` prop type to `{ api_key_configured: boolean; server_url?: string }` (drop `api_key`); update `App.tsx` metadata parsing (lines 555-557) to the new shape.
  - [x] Consistency: the same "never send the value, show configured-status only" rule applies to the new `saved_config_prompt` (Task 4) and `GET .../provider-config` (Task 5).

- [x] **Task 11: Verification & validation** (All ACs)
  - [x] `uv run alembic upgrade head` (schema changed in Task 1).
  - [x] `uv run pytest tests/api/test_provider_config_persistence.py tests/test_agents/test_alice.py tests/unit -v` — all pass.
  - [x] `uv run pytest tests/api/test_secret_leakage.py tests/api/test_secret_resolution.py -v` — no regressions (9.6 leakage + the Task-6 hardening + the Task-10 on-prem leak fix must not break valid resolution).
  - [x] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` — clean (pre-existing `providers/base.py` mypy note unrelated).
  - [x] `cd frontend && npm run typecheck && npm run lint && npm run test` — clean (pre-existing AdminDashboard.test.tsx failures unrelated to this story).
  - [ ] E2E (3 terminals per project-context Verification Workflow): backend uvicorn, `npm run dev`, `TEST_CLAUDE_KEY=<key> npx playwright test e2e/story-9-7-saved-config.spec.ts` — spec created and type-checks clean; requires live Claude key to run (skips gracefully without one).

## Dev Notes

### Why This Story Exists / Scope Boundary

Story 9.7 is the capstone of Epic 9. Stories 9.1-9.6 built encrypted per-user secrets, the status/replacement API, provider adapters, dynamic model discovery, the agent-model assignment review, and runtime secret resolution. 9.7 adds the **persistence + convenience layer**: remember the user's approved non-secret config (per project) so future threads start fast, while keeping secret rotation a future-runs-only operation that never rewrites history.

**Three concerns kept strictly separate (the heart of the story):**

| Concern | Where it lives | Mutated by rotation? |
| --------- | ---------------- | ---------------------- |
| Encrypted secret (API key / MCP PAT) | `user_secrets` table, per-user (Story 9.1) | Replaced in place by `PUT /api/secrets/{type}` |
| Remembered non-secret config (default suggestion per project) | `ai_provider_configs` table, per **(user, project)** (NEW) | No — overwritten only on next approve |
| Per-thread config snapshot (what THAT thread's agents used) | `threads.provider_name` / `provider_base_url` / `agent_configs` | **Never** — immutable history (AC3) |

**Why per-(user, project) + always-explicit (confirmed with PO):** A user works across multiple projects; within one project they may switch providers thread-to-thread depending on quota and project policy; a thread always uses exactly one provider. So a single auto-applied per-user config would be wrong. Instead the saved `(user, project)` config is a *default suggestion* the user explicitly confirms (1 click) or overrides each new thread. Provider validity is re-checked against the project's `enabled_providers` (Story 9.5) before offering it. The per-thread snapshot remains the immutable execution record so rotation/reconfiguration never alters past threads.

**Explicitly OUT of scope:**

- Encryption-**key** rotation (rotating `USER_SECRETS_ENCRYPTION_KEY` itself) and the module-level Fernet cache (`_user_secrets_fernet_instance`, deferred-work.md#L98) — infra-key concerns, not user-secret rotation. Task 6 only hardens decrypt-failure handling; it does NOT add key rotation.
- Provider config audit logging (Epic 14/20).
- Any change to the discovery/assignment algorithm (Stories 9.4/9.5 own that).

### Current State of Relevant Code (READ before coding)

**`src/ai_qa/agents/alice.py`** — configuration state machine:

- `handle_start()` (419-585): project binding (427-513) → `check_existing_configuration()` (516) → existing-config branch (518-536) currently **auto-applies** + sends a model-assignment chat message ← Task 4 replaces with the explicit prompt. Else if `input_data["provider"]` → process; else → greeting + provider options (568-585).
- `process()` (304-417): tests connection, persists the secret via `set_user_secret` (391-403), generates configuration, returns `StageResult`.
- `handle_approve()` (597-624): applies optional `data["assignments"]` overrides, `_save_configuration()` (614), → `DONE`. ← Task 2 adds the per-(user,project) save here.
- `handle_reject()` (626-639): clears config + reasoning, → `START`. Persists nothing (preserve).
- `check_existing_configuration()` (199-253): **BUGGY** — reads `agent_cfg.get("model_name")` with `isinstance(dict)` (231-237) but `_save_configuration` writes flat strings → `model=None`. Task 3 fixes.
- `_save_configuration()` (984-1012): writes `thread.provider_name/provider_base_url/agent_configs`. Task 3 makes `agent_configs` structured.
- `_model_reasoning` (192): `list[{"agent","model","rationale"}]` from `_assign_models_via_llm` (1095-1233). Ephemeral today — Task 2 persists it.
- `get_provider_options()` (255-271), `get_on_prem_defaults()` (273-298): provider option metadata for the selector. **LEAK — fixed by Task 10**: `get_on_prem_defaults` returns the decrypted on-prem `api_key` to the frontend (alice.py:293) via the `on_prem_defaults` WebSocket metadata (583). Task 10 removes the value (status-only); the new saved-config prompt + provider-config endpoint must likewise send NON-secret data only.
- `_mask_endpoint()` (1274): reuse for the API response (Task 5).

**`src/ai_qa/agents/base.py`** — `_load_agent_config()` (99-129) reads `thread.agent_configs.get(name)` as a flat string, sets only `{"model_name": ...}`. `get_llm_config()` (135-195) reads `self._agent_config.get("temperature", 0.0)` — temperature never loaded, so always 0.0. Task 3 fixes both. Runtime secret resolution (158-160), env fallback (162-171), and the UX-DR12 missing-key error (173-186, with the `user_id is not None` guard) are Story 9.6 — do NOT regress.

**`src/ai_qa/threads/models.py`** — `Thread` (15-41): `provider_name`, `provider_base_url`, `agent_configs` (JSON). `Message` (44-58) + `AgentRun` (61-76) append-only — AC3 forbids mutating them on rotation.

**`src/ai_qa/db/models.py`** — `User` (26-46), `Project` (49-74, `enabled_providers` JSON list at 64 with the empty=all back-compat comment), `ProjectMembership` (77-95, the FK + unique-constraint pattern to mirror for `AiProviderConfig`).

**`src/ai_qa/secrets/service.py`** — `get_user_secret`/`set_user_secret` (module functions, caller commits). `PROVIDER_SECRET_TYPE_MAP` (`secrets/__init__.py`) maps provider id → secret type (returns `None` for unknown — guard it). Rotation = `set_user_secret` overwriting `encrypted_value`; one row per `(user_id, secret_type)`. Story 9.6 runtime resolution already makes rotation future-runs-only; AC3 is mostly a **test** obligation + the immutability guarantee + Task 6 hardening.

**`src/ai_qa/db/types.py`** — `UserSecretEncryptedString.process_result_value` (81-88) currently returns raw ciphertext on decrypt failure. Task 6 returns `None` instead (scope: this type only).

**`src/ai_qa/api/threads.py`** + `threads/service.py` — `assert_thread_access` (281) for ownership checks; add `GET /api/threads/{thread_id}/provider-config` here.

**`src/ai_qa/threads/schemas.py`** — `ThreadResponse`/`ThreadDetailsResponse` do NOT expose provider config; add `ProviderConfigResponse`.

**`tests/api/test_provider_config_persistence.py`** — pre-existing (commit 14db0dc); 7 secret-rotation tests with overclaiming docstrings. Task 8 rewrites/extends. Keep the canonical fixture scaffold (lines 35-126).

### What This Story Changes vs. Preserves

| Component | Change | Preserve |
| ----------- | -------- | ---------- |
| `db/models.py` | **ADD** `AiProviderConfig` model (user_id, project_id, two JSON cols, unique) | All existing models |
| Alembic | **ADD** migration `create_table ai_provider_configs` (down_revision `7cef1ea1a837`) | Existing chain |
| `userconfig/service.py` | **CREATE** `save_provider_config`/`get_provider_config` | — |
| `alice.py` `handle_approve` | **MODIFY**: also upsert per-(user,project) config | Thread snapshot save, override handling, DONE transition |
| `alice.py` `handle_start` | **MODIFY**: explicit saved-config prompt; no auto-apply; re-validate enabled_providers + secret | Project binding, provider-selection flow, `force_reconfigure` |
| `alice.py` `check_existing_configuration` / `_save_configuration` | **MODIFY**: structured agent_configs (model+temp+rationale), fix bug | Provider fields |
| `base.py` `_load_agent_config` / `get_llm_config` | **MODIFY**: load temperature; tolerate legacy + structured | Story 9.6 resolution, env fallback, UX-DR12 error, user_id guard |
| `db/types.py` | **MODIFY**: `UserSecretEncryptedString` decrypt-fail → None | `EncryptedString` behavior |
| `alice.py` `get_on_prem_defaults` + `process` / `ProviderSelector.tsx` | **MODIFY (Task 10)**: stop leaking on-prem api_key to frontend; status-only + reuse-on-blank | On-prem connect flow, server_url pre-fill |
| `api/threads.py` + `schemas.py` | **ADD** `GET /api/threads/{id}/provider-config` + `ProviderConfigResponse` | Existing endpoints |
| Frontend | **ADD** saved-config prompt handling + inspect/change affordance + types + api fn | Existing Alice flow, ProviderSelector, ModelAssignmentReview |
| Tests | **REWRITE/ADD** persistence + explicit-prompt + rotation-immutability + corrupt-ciphertext | 9.6 leakage/resolution tests, fixture scaffolds |

### Source Tree Components to Touch

```text
src/ai_qa/db/models.py                               # MODIFY: add AiProviderConfig model
alembic/versions/<new>_add_ai_provider_configs.py    # CREATE: create_table (down_revision 7cef1ea1a837)
src/ai_qa/userconfig/__init__.py                     # CREATE
src/ai_qa/userconfig/service.py                      # CREATE: save/get_provider_config (per user+project)
src/ai_qa/agents/alice.py                            # MODIFY: handle_approve, handle_start (explicit prompt), check_existing_configuration, _save_configuration
src/ai_qa/agents/base.py                             # MODIFY: _load_agent_config (temperature + legacy/structured), get_llm_config
src/ai_qa/db/types.py                                # MODIFY: UserSecretEncryptedString decrypt-fail → None
src/ai_qa/api/threads.py                             # MODIFY: GET /api/threads/{id}/provider-config
src/ai_qa/threads/schemas.py                         # MODIFY: ProviderConfigResponse
frontend/src/App.tsx                                  # MODIFY: handle saved_config_prompt; wire use/change; on_prem_defaults shape (Task 10)
frontend/src/components/ProviderSelector.tsx         # MODIFY (Task 10): no api_key pre-fill; "key on file" status; onPremDefaults prop type
frontend/src/components/AgentTopBar.tsx              # MODIFY: inspect affordance (or App.tsx top bar)
frontend/src/components/ProviderConfigPanel.tsx      # CREATE (suggested): inspect/change panel + saved prompt
frontend/src/types/provider.ts                       # MODIFY: ProviderConfigResponse / SavedConfigPrompt
frontend/src/lib/providerConfig.ts                   # CREATE (suggested): GET /api/threads/{id}/provider-config client
tests/api/test_provider_config_persistence.py        # REWRITE/EXTEND: real AC1/AC2/AC3 coverage
tests/test_agents/test_alice.py                      # EXTEND: round-trip, explicit prompt, bug fix, validity gating
tests/unit/test_userconfig_service.py                # CREATE (mirror test_secret_service.py)
frontend/src/components/__tests__/ProviderConfigPanel.test.tsx  # CREATE
frontend/e2e/story-9-7-saved-config.spec.ts          # CREATE
```

### Project Structure Notes

- Module boundaries (architecture.md#L686): `agents` may depend on `threads`, `secrets`, `models`, `pipelines`, `audit`; must NOT import `api` internals. New `userconfig` module depends on `db` only — `agents/alice.py` may import it (same tier as `secrets`). The `AiProviderConfig` ORM model lives in `db/models.py` because it joins `users` + `projects`.
- Naming: snake_case functions (`save_provider_config`), PascalCase models, lowercase agent keys in JSON (base.py:102 comment: "Keys in `ai_agents_config` are agent names in lowercase").
- DB: UUID PKs, `TimestampMixin`. JSON columns nullable. PostgreSQL prod; SQLite in tests. `enabled_providers` empty/missing = "all providers allowed" (db/models.py:60-63) — honor in the validity check.
- Error format: UX-DR12 three-part (What happened / Why / What to do) for user-facing errors (incl. the Task-6 invalid-secret path).
- AC3 immutability: never `UPDATE`/rewrite `messages`, `agent_runs`, or a thread's existing `agent_configs` snapshot on rotation. Only `ai_provider_configs` (forward-looking default) changes, and only on approve.
- JSON dirty-tracking: assign a NEW dict to a JSON column (don't mutate in place) so SQLAlchemy flags the change — the codebase already does this in `_save_configuration`.

### Testing Standards Summary

- Backend (Pytest): in-memory SQLite + `StaticPool` + `engine.dispose()` teardown (#1); `Generator[...]` yield fixtures (#3); top-level imports (#9/E402); specific exceptions + `match=` (#10), never bare `Exception`/`B017`; `cast(FastAPI, client.app)` before `dependency_overrides` (#43); mocks mirror real call shapes (#15). Copy the fixture scaffold from `tests/api/test_provider_config_persistence.py`.
- Secret hygiene (carry forward from 9.6): assert NO secret sentinel appears in `ai_provider_configs`, the `GET .../provider-config` response, WebSocket/messages, the `saved_config_prompt` metadata, or error responses.
- Frontend (Playwright/Vitest): E2E no `page.route` mocking — prepare state via real API + admin token; `test.afterEach` cleanup of users/projects/artifacts; `timeout: 60*1000`, `expect.timeout: 5000`; prefer `getByRole`/`getByText`; no `page.waitForTimeout()`. Skip when the real provider key env var is missing/placeholder (mirror story-9-4 skip logic).
- On failure: launch `bmad-investigate` sub-agent with the test name, traceback, and relevant files.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 9.7] — user story + 3 ACs
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 9] — FRs: FR14b, FR36, FR54-60
- [Source: _bmad-output/planning-artifacts/prd.md#L361] — FR14b: `ai_provider_config`/`ai_agents_config` store provider, model assignments, non-secret rationale, runtime settings; secrets stay in secret storage
- [Source: _bmad-output/planning-artifacts/prd.md#L443] — FR60: rotated secrets apply to future runs; existing thread/message history unchanged
- [Source: _bmad-output/planning-artifacts/epics.md#L161] — UX-DR26: returning saved config may initialize silently; inspect/change via explicit UI action
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#L1746-1756] — Returning User Behavior: NO auto "Welcome back…" message; explicit UI inspect/change
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#L218-219,255,522] — returning-user fast start, "previous settings pre-filled", subsequent runs skip Step 1 unless reconfigure
- [Source: _bmad-output/planning-artifacts/architecture.md#L277] — Alice persists non-secret provider/model/runtime/rationale to PostgreSQL user configuration fields; secrets separate
- [Source: _bmad-output/planning-artifacts/architecture.md#L366] — Secret rotation: replacement without revealing values; future runs only; existing history unchanged
- [Source: _bmad-output/planning-artifacts/.decision-log.md#L59-64] — `ai_provider_config`/`ai_agents_config` hold only non-secret provider/model/runtime/rationale
- [Source: src/ai_qa/agents/alice.py#L597-624] — `handle_approve` (per-user,project save insertion point)
- [Source: src/ai_qa/agents/alice.py#L199-253] — `check_existing_configuration` (format bug to fix)
- [Source: src/ai_qa/agents/alice.py#L984-1012] — `_save_configuration` (thread snapshot)
- [Source: src/ai_qa/agents/alice.py#L515-536] — `handle_start` existing-config branch (auto-apply to replace with explicit prompt)
- [Source: src/ai_qa/agents/base.py#L99-195] — `_load_agent_config` + `get_llm_config` (temperature load, 9.6 resolution to preserve)
- [Source: src/ai_qa/db/models.py#L26-95] — `User`/`Project`/`ProjectMembership` (model + FK/unique pattern)
- [Source: src/ai_qa/db/types.py#L64-88] — `UserSecretEncryptedString` (Task 6 hardening)
- [Source: src/ai_qa/threads/models.py#L15-76] — Thread/Message/AgentRun (snapshot + append-only)
- [Source: src/ai_qa/threads/service.py#L281] — `assert_thread_access` (ownership)
- [Source: src/ai_qa/secrets/service.py] — `get_user_secret`/`set_user_secret` (rotation primitive)
- [Source: tests/api/test_provider_config_persistence.py] — fixture scaffold + tests to rewrite
- [Source: alembic/versions/b7d2f1a9c4e5_add_user_secrets_drop_inline_keys.py] — migration style; current head `7cef1ea1a837`
- [Source: _bmad-output/implementation-artifacts/deferred-work.md#L94,98] — corrupt-ciphertext + Fernet-cache items referencing Story 9.7

### Previous Story Intelligence (Story 9.6)

- **Secret hygiene is the recurring review gate.** Every Epic 9 review hammered leak assertions across all output channels. The NEW `ai_provider_configs` table, the `GET .../provider-config` response, and the `saved_config_prompt` metadata are three more channels — assert no secret sentinel appears in them.
- **Scope discipline.** 9.5 said "do NOT implement 9.6/9.7"; 9.6 said persistence + rotation are 9.7. This completes that — but keep encryption-KEY rotation out (Task 6 only hardens decrypt-failure).
- **Runtime resolution already exists (9.6).** `base.get_llm_config` resolves the secret at execution time → rotation is automatically future-runs-only. AC3's runtime half is done; your job is persistence + immutability tests + Task 6.
- **UX-DR12 error format** is the house style for missing/invalid secret errors (9.6 added it to `get_llm_config`). Task 6's invalid-secret path reuses it.
- **`user_id is not None` guard** (9.6 review fix, base.py:176) — keep it in any new user-scoped branch.
- **`PROVIDER_SECRET_TYPE_MAP.get()` returns None on unknown provider** — guard when checking "is the secret configured".

### Git Intelligence

- HEAD `345ef89` ("clean up garbage files") includes Stories 9.1-9.6 complete. Recent UI work (`1e2b663`, `06100f9`, `4cce6ab`) touched `ModelAssignmentReview.tsx`, `ThinkingBubble.tsx`, `App.tsx`, and the 9-4/9-5 e2e specs — re-grep those for current selectors before adding the affordance (locator drift rule).
- Commit-message convention: `story 9-7 code and test OK` once verification passes.
- Migration changes schema → run `uv run alembic upgrade head`; commit migration with the code.

### Latest Tech Information

- Python 3.12 + uv; FastAPI 0.115; SQLAlchemy 2.0 (`Mapped[...]`/`mapped_column`); Alembic 1.13. No new dependencies — JSON columns + a new table + existing patterns suffice.
- SQLAlchemy JSON column: `from sqlalchemy import JSON` (already imported in `db/models.py`); nullable `Mapped[dict[str, Any] | None]`. Assign a NEW dict on write so the change is flagged dirty.
- Frontend: React 18.3 + TS 5.6 strict + Vite + Tailwind; `npm run typecheck` catches what Vite skips. Path alias `@` → `./src`.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- SQLite "index already exists" error: `AiProviderConfig` with both `index=True` on columns AND explicit `Index()` in `__table_args__` caused duplicate index names. Fixed by removing `index=True` from mapped columns, keeping only explicit `Index` objects.
- `test_handle_start_invalid_saved_config_falls_through`: `mock_db.get.side_effect` in alice fixture overrides `return_value`. Fixed by creating a `mock_get_with_project` side-effect that handles `Project` lookups explicitly.

### Completion Notes List

- E2E spec `story-9-7-saved-config.spec.ts` created (4 tests: prompt appearance, use-saved, choose-different, inspect panel); all tests skip gracefully when `TEST_CLAUDE_KEY` is absent/placeholder; unit and integration tests fully cover the acceptance criteria.
- Pre-existing `AdminDashboard.test.tsx` (12 failures) and `providers/base.py` mypy redundant-cast are unrelated to this story.
- ProviderConfigPanel uses an inline SVG gear icon instead of importing from `AgentTopBar` to avoid coupling; `AgentTopBar` was also extended with `onInspectConfig` prop for future use.

### File List

- `src/ai_qa/db/models.py` — MODIFIED: added `AiProviderConfig` ORM model
- `alembic/versions/e9f1a2b3c4d5_add_ai_provider_configs.py` — CREATED: migration for `ai_provider_configs` table
- `src/ai_qa/userconfig/__init__.py` — CREATED: module init
- `src/ai_qa/userconfig/service.py` — CREATED: `save_provider_config` / `get_provider_config`
- `src/ai_qa/agents/alice.py` — MODIFIED: `handle_approve` (persist config), `handle_start` (explicit saved-config prompt), `check_existing_configuration` (structured+legacy shapes), `_save_configuration` (structured format), `get_on_prem_defaults` (status-only), `process` (reuse-on-blank)
- `src/ai_qa/agents/base.py` — MODIFIED: `_load_agent_config` (structured+legacy shapes)
- `src/ai_qa/db/types.py` — MODIFIED: `UserSecretEncryptedString.process_result_value` (corrupt-ciphertext → None)
- `src/ai_qa/api/threads.py` — MODIFIED: added `GET /api/threads/{id}/provider-config`
- `src/ai_qa/threads/schemas.py` — MODIFIED: added `AgentConfigEntry`, `ProviderConfigResponse`
- `frontend/src/types/provider.ts` — MODIFIED: updated `ProviderOptionsMessage.on_prem_defaults`, added `AgentConfigEntry`, `ProviderConfigResponse`, `SavedConfigPrompt`
- `frontend/src/components/ProviderSelector.tsx` — MODIFIED: `onPremDefaults` type (no `api_key`), removed prefill, added "Key on file" hint
- `frontend/src/components/AgentTopBar.tsx` — MODIFIED: added `onInspectConfig` prop + Settings button
- `frontend/src/components/ProviderConfigPanel.tsx` — CREATED: inspect/change panel
- `frontend/src/lib/providerConfig.ts` — CREATED: `getThreadProviderConfig` API client
- `frontend/src/App.tsx` — MODIFIED: imports, `AliceState` type, `savedConfigPrompt` state, `handleAliceMessage` for saved-config prompt, `on_prem_defaults` parsing, inspect button, `ProviderConfigPanel` render, `handleUseSavedConfig`, `handleInspectConfig`, `handleChangeConfig`
- `tests/api/test_provider_config_persistence.py` — EXTENDED: 6 new AC1/AC2/AC3 tests (13 total)
- `tests/test_agents/test_alice.py` — EXTENDED: `TestSavedConfigRoundTrip` (6 tests), `TestOnPremDefaults` fixes (64 total)
- `tests/unit/test_userconfig_service.py` — CREATED: 8 unit tests for service + corrupt-ciphertext
- `tests/api/test_secret_leakage.py` — EXTENDED: 2 new on-prem leak tests (12 total)
- `frontend/src/components/__tests__/ProviderSelector.test.tsx` — MODIFIED: updated 2 tests for new on-prem behavior
- `frontend/src/components/__tests__/ProviderConfigPanel.test.tsx` — CREATED: 8 unit tests
- `frontend/e2e/story-9-7-saved-config.spec.ts` — CREATED: 4 E2E tests (prompt, use-saved, choose-different, inspect)

### Review Findings

- [x] [Review][Patch] **[Critical] On-prem blank key: `_test_connection` runs BEFORE stored secret resolved** [`src/ai_qa/agents/alice.py:394`] — `process()` calls `_test_connection(provider_info, credentials)` at line 394 with the original credentials (blank api_key for reuse case), then resolves the stored on-prem secret into `credentials` at lines 429–436 only AFTER the test. Connection test fails with empty key before the stored secret is ever used, breaking the "leave blank to reuse" feature entirely.
- [x] [Review][Patch] **[High] `use_saved_config` path: `_model_reasoning` empty → empty rationales written to thread snapshot** [`src/ai_qa/agents/alice.py:617`] — When `use_saved_config=True`, `process()` is never called so `self._model_reasoning` stays `[]`. `_save_configuration` (line 617) then builds `reasoning_map` from an empty list, writing `"rationale": ""` for all agents into `thread.agent_configs`. The saved (user, project) rationale is permanently lost from the thread snapshot.
- [x] [Review][Patch] **[High] `use_saved_config` path: no guard for `project_id = None`** [`src/ai_qa/agents/alice.py:574`] — The `use_saved_config` block at line 574 calls `get_provider_config(db, user_id, self.project_context.project_id)` without checking that `project_id` is not `None`. If project binding was skipped or lost, a NULL project_id reaches the SELECT, producing wrong results or an error. The later saved-config prompt block (line 635) correctly guards with `and self.project_context.project_id`.
- [x] [Review][Patch] **[High] `use_saved_config` path: empty/unknown provider → silent DONE with broken config** [`src/ai_qa/agents/alice.py:603`] — If the saved provider was removed from `PROVIDER_OPTIONS` since it was saved, `prov.get("provider", "")` returns `""`. `AliceConfiguration` is built with `provider=""` and the agent transitions to DONE, leaving all downstream agents with a broken config and no user-visible error.
- [x] [Review][Patch] **[High] `use_saved_config` path: `saved["agents"]` None → only Alice injected, other agents dropped** [`src/ai_qa/agents/alice.py:587`] — If `saved["agents"]` is `None` (valid DB null), `agt = {}` and `agt.get("agents") or {}` is `{}`, so `agents_dict_s` stays empty. The fallback at line 594 injects only Alice. Bob, Mary, Sarah, Jack are silently dropped; the config transitions to DONE with an incomplete agent set.
- [x] [Review][Patch] **[Medium] `AliceAgent()` bare instantiation in `get_thread_provider_config` just for `_mask_endpoint`** [`src/ai_qa/api/threads.py:361`] — An `AliceAgent()` is constructed without context solely to call `alice._mask_endpoint(...)`. `AliceAgent.__init__` calls `AppSettings()`, which reads from environment/config. In test environments or edge configs this can raise, causing a 500 on every `GET /provider-config` call. `_mask_endpoint` should be a `@staticmethod` or module-level function.
- [x] [Review][Patch] **[Medium] `OSError` from `_save_configuration` in `use_saved_config` path caught → misleading fallthrough message** [`src/ai_qa/agents/alice.py:621`] — The `except Exception` at line 621 catches `OSError` from `_save_configuration`, logs a warning, then falls through to `send_message("Saved configuration is no longer valid. Please select a provider.")`. But the config WAS successfully loaded — only the DB write failed. The user sees a misleading "no longer valid" message instead of a DB error.
- [x] [Review][Patch] **[Medium] Double `get_provider_config` call: failed `use_saved_config` falls through and re-sends `saved_config_prompt`** [`src/ai_qa/agents/alice.py:629`] — After the `use_saved_config` failure message at line 626, execution continues into the saved-config prompt check block at line 630. If the config is still valid in DB (only the DB write failed), a `saved_config_prompt` is sent immediately after "no longer valid", confusing the user with contradictory messages.
- [x] [Review][Patch] **[Low] `provider_name.capitalize()` produces wrong display names for multi-word provider IDs** [`src/ai_qa/api/threads.py:369`] — `thread.provider_name` stores the provider id (e.g., `"on-premises"`). `.capitalize()` gives `"On-premises"` instead of the proper display name. The saved-config source path (line 385) correctly uses `prov.get("provider_name")` from stored data; the thread-snapshot path should do the same or use a lookup.
- [x] [Review][Patch] **[Low] Stale closure: `aliceState.savedConfigPrompt` read from outer scope in `setAliceState` updater** [`frontend/src/App.tsx:1237`] — The "Choose a different provider" `onClick` reads `aliceState.savedConfigPrompt?.options` from the captured outer scope instead of `prev.savedConfigPrompt?.options` inside the updater function. Under React 18 concurrent mode, the outer variable can be stale. Should use `prev.savedConfigPrompt?.options ?? prev.providerOptions`.
- [x] [Review][Patch] **[Low] `handleInspectConfig` silently swallows all errors — no user feedback** [`frontend/src/App.tsx:814`] — `.catch(() => {})` discards all errors from `getThreadProviderConfig()`. If the request fails (401, 500, network error), the panel simply does not open with no indication of failure. Should at minimum log the error or show a toast.
- [x] [Review][Patch] **[Low] `test_secret_rotation_preserves_only_latest_value` asserts directly on encrypted column value** [`tests/api/test_provider_config_persistence.py:275`] — `assert rows[0].encrypted_value == "rotated-key-2-12345678"` compares the ORM column (which returns the TypeDecorator-decrypted value) to plaintext. The assertion works coincidentally because the TypeDecorator decrypts on read, but it tests the wrong abstraction layer. Should use `get_user_secret(session, user.id, SECRET_TYPE_CLAUDE)` for reliability.
- [x] [Review][Patch] **[Low] No test for `force_reconfigure=True` bypassing a valid saved config in `handle_start`** [`tests/test_agents/test_alice.py`] — `TestSavedConfigRoundTrip` has tests for valid/invalid saved config and `use_saved_config`, but no test asserts that sending `force_reconfigure=True` skips an otherwise-valid saved-config prompt and runs the normal provider-selection flow.
- [Review/Defer] `save_provider_config` has no defense-in-depth guard against accidental secret leakage [`src/ai_qa/userconfig/service.py:28`] — deferred, pre-existing pattern (mirrors `secrets/service.py` which also relies on caller discipline). No confirmed leak — AC1 guard is enforced at call sites.
- [Review/Defer] Deleted project in validity check treated as "all providers allowed" [`src/ai_qa/agents/alice.py:650`] — deferred, pre-existing edge case. If project is deleted while user is mid-flow, downstream FK constraints on commit will catch the invalid state. Low real-world risk.

## Change Log

- Date: 2026-06-10 — Story 9-7 created: per-(user, project) saved provider/model configuration persistence, explicit "use saved / change" affordance for returning users (no silent auto-apply, no noisy chat), corrupt-ciphertext hardening, and secret-rotation-applies-to-future-runs with immutable history. Design decisions (per-project storage, always-explicit, ciphertext hardening) confirmed with product owner. Ultimate context engine analysis completed — comprehensive developer guide created.
- Date: 2026-06-10 — Added Task 10 (fix pre-existing on-premises API key leak: `get_on_prem_defaults` returned the decrypted key into WebSocket metadata and ProviderSelector pre-filled it — now status-only + reuse-on-blank), per product owner request to fix it within this story.
- Date: 2026-06-10 — Implementation complete. All 10 backend tasks + Task 9 unit tests done. 107 backend tests pass, 115/127 frontend tests pass (12 pre-existing AdminDashboard failures). Status set to review.
- Date: 2026-06-10 — Code review complete (bmad-code-review). Applied all 13 patch findings: F1 Critical (on-prem key resolved before _test_connection), F2-F5 High (use_saved_config hardening: _model_reasoning, project_id guard, empty provider, empty agents), F6-F8 Medium (_mask_endpoint @staticmethod + error fallthrough fix), F9-F13 Low (provider_name lookup, stale closure, console.error, test assertion, force_reconfigure test). All tests pass. Status set to done.

[patch]: about:blank
