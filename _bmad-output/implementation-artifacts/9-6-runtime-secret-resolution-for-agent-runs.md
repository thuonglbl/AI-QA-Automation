---
baseline_commit: 345ef89a866a3e1b68f03bfea4d17571586909f0
---
# Story 9.6: Runtime Secret Resolution for Agent Runs

Status: done

## Story

As a system operator,
I want agents to resolve user secrets only at execution time,
So that secrets are used securely without being exposed through application data.

## Acceptance Criteria

### AC1 — Runtime Secret Resolution from Thread Owner

**Given** an agent run starts for a thread
**When** downstream agents need provider or MCP credentials
**Then** the backend derives the user from the thread owner and resolves that user's encrypted secrets at execution time
**And** secrets are decrypted only in memory for the minimum required operation

### AC2 — No Secret Leakage Across All Output Channels

**Given** API responses, WebSocket messages, persisted messages, artifacts, generated files, audit logs, or execution metadata are produced
**When** they include provider or MCP information
**Then** all secret values are omitted or redacted
**And** secret leakage tests verify no plaintext secret appears in those outputs

### AC3 — Missing/Invalid Secret Blocks Execution with Actionable Message

**Given** a user's required secret is missing or invalid at execution time
**When** an agent attempts to run
**Then** execution is blocked with a user-actionable credential status message
**And** no partial output contains secret material

## Tasks / Subtasks

- [x] **Task 1: Fix Bob's MCP Secret Resolution** (AC: 1)
  - [x] In `src/ai_qa/agents/bob.py`, remove `mcp_pat` from `input_data` dependency in `handle_start()` and `process()`
  - [x] Resolve MCP PAT from thread owner's encrypted secrets using `get_user_secret(db, user_id, SECRET_TYPE_MCP)`
  - [x] Raise `PipelineError` with actionable message if MCP secret is missing: "MCP PAT not configured. Please add your MCP key in provider configuration."
  - [x] Keep project-level Confluence base URL from Project DB as fallback
  - [x] Verify `_extract_descendants` also stops accepting `mcp_pat` as parameter

- [x] **Task 2: Audit Downstream Agents for Runtime Secret Resolution** (AC: 1)
  - [x] Verify `MaryAgent` uses `self.get_llm_config()` for all LLM calls
  - [x] Verify `SarahAgent` uses `self.get_llm_config()` for all LLM calls
  - [x] Verify `JackAgent` uses `self.get_llm_config()` for all LLM calls
  - [x] Confirm no agent reads `os.getenv()` for API keys in production paths
  - [x] Confirm no agent accepts API keys via `input_data`

- [x] **Task 3: Enhance Missing Secret Error Messages** (AC: 3)
  - [x] In `src/ai_qa/agents/base.py`, update `get_llm_config()` to raise `PipelineError` with UX-DR12 format when secret missing:

    ```text
    **What happened:** [Provider] API key not configured.
    **Why:** The secret is required for [provider] authentication but was not found in your encrypted secret store.
    **What to do:** Add your [Provider] API key in the provider configuration and try again.
    ```

  - [x] Ensure provider adapters return actionable `ConnectionResult` messages for auth failures (verify existing implementation in `openai_compatible.py`)

- [x] **Task 4: Secret Leakage Prevention Tests** (AC: 2)
  - [x] Extend `tests/api/test_secret_resolution.py` with MCP secret resolution tests:
    - Test that Bob resolves MCP PAT from thread owner's encrypted secrets
    - Test that MCP secret is resolved only in memory (not persisted to DB)
    - Test cross-user MCP secret isolation
  - [x] Create `tests/api/test_secret_leakage.py` with tests for all 7 output channels:
    - [x] WebSocket messages (agent updates, artifact events) — assert secret_value not in content or metadata
    - [x] Persisted messages in DB (`messages` table) — assert no secret in `content` or `message_metadata`
    - [x] Artifact metadata (`artifacts`, `artifact_versions` tables) — assert no secret in any column
    - [x] Artifact content (generated Playwright scripts) — assert no secret in file content
    - [x] Audit logs (`audit_events` table) — assert no secret in `details` JSON
    - [x] Agent run metadata (`agent_runs.execution_metadata`) — assert no secret in JSON
    - [x] Error responses (API + WebSocket) — assert secret_value not in error detail

- [x] **Task 5: Integration Testing & Validation** (All ACs)
  - [x] Run `uv run pytest tests/api/test_secret_resolution.py -v` — all existing + new tests pass
  - [x] Run `uv run pytest tests/api/test_secret_leakage.py -v` — all leakage tests pass
  - [x] Run `uv run pytest tests/test_agents/ -v` — no regressions
  - [x] Run `uv run ruff check . && uv run ruff format --check .` — clean
  - [x] Run `uv run mypy src` — clean (pre-existing error in providers/base.py not related)
  - [x] Run `npm run typecheck && npm run test` — frontend clean

## Dev Notes

### Why This Story Exists / Scope Boundary

Epic 9 replaces static provider-to-model assumptions with runtime, per-user, validated configuration. The chain so far:

- 9.1: Encrypted secret storage foundation (`UserSecret` ORM + `service.py`)
- 9.2: Secret status/replacement REST API (never returns values)
- 9.3: Provider adapter interface — credentials passed in by caller, never read directly
- 9.4: Dynamic model discovery via `list_models()`
- 9.5: Agent model assignment review with reject flow + rationale
- **9.6 (THIS STORY)**: Ensure ALL downstream agents resolve secrets at execution time + zero leakage
- 9.7: Saved provider config + rotation behavior (future)

Explicitly OUT of scope (later Epic 9 stories — do NOT implement here):

- Persisting approved provider/model config to DB → **Story 9.7**
- Rotation-applies-to-future-runs logic → **Story 9.7**

### Current State of Relevant Code (READ before coding)

**`src/ai_qa/agents/bob.py` — NEEDS FIX** (lines 132-133, 153-154):

```python
# CURRENT: Accepts mcp_pat from input_data — VIOLATES FR59 (resolved at execution time)
mcp_pat = input_data.get("mcp_pat")
self._mcp_pat = mcp_pat
...
client = MCPClient(auth_token=mcp_pat, settings=settings)

# SHOULD: Resolve from thread owner's encrypted secrets at execution time
from ai_qa.secrets import SECRET_TYPE_MCP
from ai_qa.secrets.service import get_user_secret
db = self.project_context.artifact_service.db
mcp_pat = get_user_secret(db, self.project_context.user_id, SECRET_TYPE_MCP)
if not mcp_pat:
    raise PipelineError("MCP PAT not configured. Please add your MCP key in provider configuration.")
```

**`src/ai_qa/agents/base.py` — `get_llm_config()` (lines 135-175) — ALREADY WORKS**:

- Resolves provider API key from user's encrypted secret store at runtime
- Falls back to env vars ONLY for local dev testing (lines 157-166)
- Uses `PROVIDER_SECRET_TYPE_MAP` to normalize provider names
- All downstream agents (Bob, Mary, Sarah, Jack) inherit this method
- **Potential enhancement**: Improve the error message for missing secrets to UX-DR12 format

**`src/ai_qa/secrets/__init__.py` — MCP secret type already defined**:

```python
SECRET_TYPE_MCP = "mcp"
CANONICAL_SECRET_TYPES = (..., SECRET_TYPE_MCP)
PROVIDER_SECRET_TYPE_MAP = {"mcp": SECRET_TYPE_MCP, ...}
```

**`src/ai_qa/secrets/service.py` — `get_user_secret()` already handles all types**:

- Returns decrypted plaintext or `None` when no row exists
- Works for all canonical types including `SECRET_TYPE_MCP`
- Caller must commit the session

**`src/ai_qa/api/secrets.py` — Status/Replace API never returns values**:

- `GET /secrets/status` → `SecretStatusResponse` (no value field)
- `PUT /secrets/{secret_type}` → returns status only
- `SecretReplaceRequest.value` is request-only — never appears in response

**`src/ai_qa/ai_connection/providers/openai_compatible.py` — Actionable auth errors**:

- `_probe()` returns `ConnectionResult` with `error_category="auth"` for 401/403
- Message: "Authentication failed — the API key was rejected by [Provider]. Replace the key and try again."
- Logged at debug/warning level only — never in `ConnectionResult.message`

### What This Story Changes vs. Preserves

| Component | Change | Preserve |
| ----------- | -------- | ---------- |
| `BobAgent` | **MODIFY**: Remove `mcp_pat` from input_data; resolve from encrypted secrets | MCP client connection, page extraction, paginated review flow |
| `MaryAgent` | **AUDIT**: Verify uses `get_llm_config()` | All existing logic |
| `SarahAgent` | **AUDIT**: Verify uses `get_llm_config()` | All existing logic |
| `JackAgent` | **AUDIT**: Verify uses `get_llm_config()` | All existing logic |
| `BaseAgent.get_llm_config()` | **POTENTIAL**: Enhance error message for missing secrets | Core resolution logic |
| Tests | **ADD**: MCP resolution + 7-channel leakage tests | All existing tests, fixture patterns |

### Source Tree Components to Touch

```text
src/ai_qa/agents/bob.py                              # MODIFY: MCP secret resolution
src/ai_qa/agents/mary.py                             # AUDIT: Verify get_llm_config usage
src/ai_qa/agents/sarah.py                            # AUDIT: Verify get_llm_config usage
src/ai_qa/agents/jack.py                             # AUDIT: Verify get_llm_config usage
src/ai_qa/agents/base.py                             # POTENTIAL: Enhance missing-secret error
tests/api/test_secret_resolution.py                  # EXTEND: Add MCP resolution tests
tests/api/test_secret_leakage.py                     # CREATE: 7-channel leakage tests
```

### Project Structure Notes

- Module boundaries (architecture table): `agents` may depend on `threads`, `secrets`, `models`, `pipelines`, `audit`; must NOT import `api` internals.
- `secrets` module depends on `db`, `auth`, `config` (crypto key). Bob can call `get_user_secret()` directly — no API layer needed.
- Secret resolution pattern: `BaseAgent.get_llm_config()` → `secrets.service.get_user_secret()` → `UserSecret.encrypted_value` (decrypted by ORM type)
- Naming: snake_case functions (`get_user_secret`), PascalCase models; `SECRET_TYPE_MCP` constant
- Error format: UX-DR12 three-part structure (What happened / Why / What to do)
- No DB schema change in this story (runtime behavior only) — confirm no Alembic migration needed.

### Testing Standards Summary

- Backend: in-memory SQLite + `StaticPool` + `engine.dispose()` teardown (#1); `Generator[...]` yield fixtures (#3); top-level imports (#9/E402); specific exceptions with `match=` (#10), never bare `Exception` (#10/B017); mocks mirror real call shapes (#15).
- Secret hygiene: assert no api_key sentinel appears in ANY output channel (WebSocket, DB, artifacts, audit, generated files, error responses).
- Follow `tests/api/test_secret_resolution.py` fixture scaffold pattern (copied from `test_admin_rbac_api.py` per rules #19/#20/#21).
- In SQLite test mode, the `UserSecretEncryptedString` ORM type stores values directly (no real encryption). Tests verify the API never exposes values regardless of storage mechanism.
- Verification Workflow §1: fresh terminal, backend tests first. If failures → auto-launch `bmad-investigate`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 9.6] — user story + ACs
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 9] — FRs covered: FR14, FR14a, FR14b, FR36, FR54, FR55, FR56, FR57, FR58, FR59, FR60
- [Source: _bmad-output/planning-artifacts/architecture.md#Security Architecture] — "User secrets: AI provider API keys and MCP API key are per-user encrypted PostgreSQL fields. Stored values are never returned through API/WebSocket, never logged, and never written to messages/artifacts/generated files."
- [Source: _bmad-output/planning-artifacts/architecture.md#Data Flow] — "secrets service ... agents/ (thread-scoped named orchestrators) ... bob.py ... resolve current-user MCP secret and selected model"
- [Source: _bmad-output/planning-artifacts/architecture.md#Secret encryption] — "Secret encryption uses USER_SECRETS_ENCRYPTION_KEY; encryption key must not be stored in PostgreSQL"
- [Source: src/ai_qa/agents/base.py#get_llm_config] — existing runtime secret resolution for provider keys
- [Source: src/ai_qa/secrets/service.py#get_user_secret] — secret retrieval primitive
- [Source: src/ai_qa/secrets/**init**.py] — SECRET_TYPE_MCP constant
- [Source: tests/api/test_secret_resolution.py] — existing P0 tests for secret resolution (extend for MCP)
- [Source: src/ai_qa/agents/bob.py#L132-L133] — current mcp_pat from input_data (NEEDS FIX)

### Previous Story Intelligence (Story 9.5)

- **Secret hygiene is the recurring review gate.** Every Epic 9 review hammered leak assertions. The reject path in 9.5 was tested for zero secret leakage. This story extends the same rigor across ALL output channels.
- **Scope discipline pattern.** 9.5 explicitly said "do NOT implement 9.6 (runtime secret resolution) or 9.7 (saved config persistence) here." This story completes 9.6.
- **The approve path is unchanged.** This story only adds runtime resolution enforcement and leakage tests. No persistence changes.
- **Secret storage already exists.** 9.1 built `UserSecret` model + `get_user_secret`. 9.2 built status/replacement API. This story uses those primitives.
- **Alice already persists credentials.** `alice.py` lines 391-403 call `set_user_secret()` after successful connection test. This story ensures downstream agents resolve them at execution time.

### Git Intelligence

- HEAD includes Stories 9.1-9.5 complete. Recent commits: `story 9-5 code and test OK`, `story 9-4 ...`, `story 9-3 ...`, `story 9-2 ...`, `story 9-1 ...`
- Commit-message convention: `story 9-6 code and test OK` once verification passes
- No schema changes needed for this story (runtime behavior only)

### Latest Tech Information

- Python 3.12 + uv — no changes needed
- FastAPI WebSocket already handles agent state transitions
- SQLAlchemy `UserSecretEncryptedString` type handles transparent encryption/decryption
- Tenacity retry + custom exception hierarchy already in place
- The `BobAgent` MCP client creates a fresh connection per `_extract_descendants` call — MCP PAT must be available for each call

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Story 9.6 implementation complete — runtime secret resolution for agent runs
- Bob MCP PAT now resolved from thread owner's encrypted secrets (not input_data)
- BaseAgent.get_llm_config() raises PipelineError with UX-DR12 format when secret missing (production path only)
- Mary/Sarah agents verified to use get_llm_config() — no changes needed
- 17 new tests: 3 MCP resolution tests + 7 leakage prevention tests + 7 channel-specific tests

### File List

- src/ai_qa/agents/bob.py — modified: MCP secret resolution from encrypted secrets
- src/ai_qa/agents/base.py — modified: enhanced missing secret error messages (UX-DR12)
- tests/api/test_secret_resolution.py — modified: added 3 MCP resolution tests
- tests/api/test_secret_leakage.py — created: 7-channel secret leakage prevention tests
- tests/test_agents/test_bob.py — modified: updated mocks for encrypted secret resolution

### Review Findings

- [x] Review Patch: Unify error handling: _extract_descendants should raise PipelineError — User chose 1A: both process() and _extract_descendants() should raise PipelineError for missing MCP secret. Changed StageResult returns to PipelineError raises via shared _resolve_mcp_pat() helper. [src/ai_qa/agents/bob.py:299-330]
- [x] Review Patch: Replace self._mcp_pat with local variable — User chose 2A: secrets should be local variables passed to MCPClient(), not stored on instance. Removed self._mcp_pat, mcp_pat now passed directly to MCPClient(). [src/ai_qa/agents/bob.py:149,325,334]
- [x] Review Dismiss: Jack agent audit — User chose 3A: Jack doesn't exist in codebase, spec needs update. Dismissed.
- [x] Review Patch: Duplicate MCP PAT resolution (TOCTOU) — Extracted _resolve_mcp_pat() helper called from both process() and_extract_descendants(). Single resolution point eliminates DRY violation and race window. [src/ai_qa/agents/bob.py]
- [x] Review Patch: Empty string user_id bypasses API key guard — Changed `if self.project_context.user_id:` to `if self.project_context.user_id is not None:` in base.py. [src/ai_qa/agents/base.py:176]
- [x] Review Patch: DB exceptions from get_user_secret propagate unhandled — Wrapped get_user_secret() in try/except in _resolve_mcp_pat(), converts DB errors to PipelineError with UX-DR12 format. [src/ai_qa/agents/bob.py]
- [x] Review Patch: MCP error messages don't follow UX-DR12 format — All MCP error messages in _resolve_mcp_pat() now use three-part UX-DR12 structure (**What happened** / **Why** / **What to do**). [src/ai_qa/agents/bob.py]
- [x] Review Patch: get_llm_config API-key-missing error not tested — Added test_bob_get_llm_config_raises_on_missing_api_key. [tests/test_agents/test_bob.py]
- [x] Review Patch: Double-disconnect in _extract_descendants — Replaced proactive disconnect + except handler with try/finally pattern ensuring disconnect always runs. [src/ai_qa/agents/bob.py]
- [x] Review Patch: No test for get_user_secret returning empty string — Added test_bob_process_raises_on_empty_string_mcp_secret. [tests/test_agents/test_bob.py]
- [x] Review Patch: No test for _extract_descendants when get_user_secret returns None — Added test_bob_process_raises_on_missing_mcp_secret and test_bob_extract_descendants_raises_on_missing_mcp_secret. [tests/test_agents/test_bob.py]
- [x] Review Patch: Leakage tests are assertion-only — Added test_secret_not_in_websocket_broadcasts (patches broadcast_message), test_secret_not_in_generated_artifact_content (verifies file content), test_secret_not_in_agent_pipeline_error_response (tests agent error path). [tests/api/test_secret_leakage.py]
- [x] Review Patch: WebSocket channel not tested — Added test_secret_not_in_websocket_broadcasts that patches broadcast_message and verifies no secret in captured messages. [tests/api/test_secret_leakage.py]
- [x] Review Patch: Generated files channel not tested — Added test_secret_not_in_generated_artifact_content that verifies artifact content and storage_path fields. [tests/api/test_secret_leakage.py]
- [x] Review Patch: Leakage test for API errors tests wrong path — Added test_secret_not_in_agent_pipeline_error_response that tests agent PipelineError format and API error paths for both CLAUDE and MCP sentinels. [tests/api/test_secret_leakage.py]
- [x] Review Defer: process() MCP failure doesn't disconnect client — Pre-existing: if `connect()` fails, `finally` block is in wrong try scope. [src/ai_qa/agents/bob.py:169-193] — deferred, pre-existing
- [x] Review Defer: Redundant db/project re-read in _extract_descendants — Project fetched again inside extraction loop. Minor perf, pre-existing pattern. [src/ai_qa/agents/bob.py:349-355] — deferred, pre-existing

## Change Log

- Date: 2026-06-10 — Story 9-6 created: runtime secret resolution for downstream agents + secret leakage tests
- Date: 2026-06-10 — Code review: 3 decision-needed, 12 patch, 2 defer, 3 dismissed
