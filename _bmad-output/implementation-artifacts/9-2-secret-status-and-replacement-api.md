---
baseline_commit: c3f6783462b0fcf9685b68f614524dce9320ce74
---

# Story 9.2: Secret Status and Replacement API

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a project user,
I want to see whether my credentials are configured and replace expired keys,
so that I can recover from provider/MCP authentication failures without admin support.

## Acceptance Criteria

**AC1 — Status returns non-secret fields only**

**Given** a user has stored provider or MCP secrets
**When** the frontend requests secret status
**Then** the API returns only non-secret status fields such as configured/missing, provider name, last updated, and validation state
**And** no stored secret value or masked reversible token is returned.

**AC2 — Replacement stores and supersedes the previous value**

**Given** a user submits a replacement key
**When** the backend validates and stores it
**Then** the previous encrypted value is replaced or superseded securely
**And** future runs use the new value.

**AC3 — Stored key is never displayed; replacement-only flow**

**Given** a user attempts to view an existing key
**When** the UI renders credential status
**Then** the stored key is never displayed
**And** the UI provides replacement flow only.

## Tasks / Subtasks

- [x] **Task 1: Extend the secret service with status + replacement read/write helpers** (AC: 1, 2)
  - [x] In `src/ai_qa/secrets/service.py`, add `list_secret_status(db: Session, user_id: UUID) -> list[SecretStatus]` that returns **non-secret metadata only** for every canonical secret type — never the decrypted `encrypted_value`. For each canonical `secret_type` (see `ai_qa.secrets` constants), return: `secret_type`, `configured: bool` (a row exists), `status` (the stored `status` string, or a sentinel like `"missing"` when no row), `last_updated: datetime | None` (the row's `updated_at`), and `validation_state` (see Task 2 note). Iterate over the canonical types so "missing" providers are represented too (the AC requires a configured/missing signal).
  - [x] Add `get_secret_status(db: Session, user_id: UUID, secret_type: str) -> SecretStatus` for a single type (used by the single-item endpoint if added; otherwise reuse the list helper internally).
  - [x] Add `replace_user_secret(db: Session, user_id: UUID, secret_type: str, value: str) -> UserSecret` OR document that the existing `set_user_secret` already performs the secure upsert (replace-or-supersede). **Reuse `set_user_secret`** — it already updates `encrypted_value` + `status` on the existing `(user_id, secret_type)` row (verified in `service.py`), satisfying AC2's "previous encrypted value is replaced". Do NOT write a parallel upsert. Add only thin format validation (Task 2) before calling it.
  - [x] Define a small typed return shape for status. Prefer a frozen `@dataclass` `SecretStatus` (or a Pydantic model) declared in `src/ai_qa/secrets/service.py` or a new `src/ai_qa/secrets/schemas.py`. It must contain ONLY non-secret fields. Keep it free of any field that could carry secret bytes.
  - [x] The caller commits the session (mirror the existing service contract — `set_user_secret` does not commit). The API endpoint (Task 4) performs `db.commit()`.
- [x] **Task 2: Format-level validation for replacement (scope-bounded — NOT provider connection validation)** (AC: 2)
  - [x] Add a pure helper `validate_secret_format(secret_type: str, value: str) -> None` (raises `ValueError` with an actionable, secret-free message) OR return a bool — pick one and be consistent with how Task 4 maps it to an HTTP error. Validate: non-empty after `.strip()`, and minimum length `>= 8` to mirror the existing `alice._test_connection` guard (`len(api_key) < 8` → reject). Do not log or echo the value.
  - [x] **Scope boundary — do NOT implement provider connection validation here.** Live provider `validate_connection(...)` / model discovery is **Story 9.3 / 9.4**. The `validation_state` field in `SecretStatus` for 9.2 reflects only stored/format state (e.g. `"configured"` vs `"missing"` vs `"unvalidated"`), NOT a live provider check. Populate it from the row's `status` column; default newly-replaced secrets to `"configured"` (matching `set_user_secret`). Add a code comment that 9.3 will enrich this with real connection results.
  - [x] Strip the value before storing (call `value.strip()`), because the AC's "future runs use the new value" must match what a later connection test validates. Note: 9.1 review flagged that `alice.py` stores the **unstripped** value while it validates the stripped value (deferred item). Fix the asymmetry **only inside this new replacement path** by storing the stripped value; do not refactor `alice.py` here.
- [x] **Task 3: Define request/response schemas (secret-free by construction)** (AC: 1, 2, 3)
  - [x] Add Pydantic models. Follow the existing pattern in `src/ai_qa/api/projects.py` (module-local `BaseModel` classes) — either co-locate in the new router module (Task 4) or add to `src/ai_qa/api/schemas.py`. Match the project's secret-free response convention (see `ProjectResponse` docstring "Secret-free ... representation").
  - [x] `SecretStatusResponse`: `secret_type: str`, `provider_name: str` (human-readable label, see Task 4 mapping), `configured: bool`, `status: str`, `validation_state: str`, `last_updated: datetime | None`. **No `value`, no `encrypted_value`, no masked token, no `••••` field.** AC1 forbids returning even a masked reversible token.
  - [x] `SecretReplaceRequest`: `secret_type: str`, `value: str`. Add a field constraint that mirrors Task 2 (e.g. `min_length` is acceptable for early rejection but the canonical validation lives in `validate_secret_format`). The `value` field is write-only (request only) and must never appear in any response model.
  - [x] Reuse the canonical `secret_type` set: validate the incoming `secret_type` against `PROVIDER_SECRET_TYPE_MAP` values / the `SECRET_TYPE_*` constants from `ai_qa.secrets`. Reject unknown types with `422` (or `400`) and a secret-free message.
- [x] **Task 4: New FastAPI router `src/ai_qa/api/secrets.py`** (AC: 1, 2, 3)
  - [x] Create `src/ai_qa/api/secrets.py` mirroring `src/ai_qa/api/projects.py` structure: `router = APIRouter(prefix="/secrets", tags=["secrets"])`, `DbSessionDependency = Depends(get_db_session_dependency)`, `CurrentUserDependency = Depends(get_current_active_user)`.
  - [x] `GET /secrets/status` → returns `list[SecretStatusResponse]` for the **current authenticated user only** (`current_user.id`). Never accept a `user_id` query param — ownership derives from the session (mirrors `projects.list_projects`). This satisfies FR36 (per-user ownership) and AC1.
  - [x] `PUT /secrets/{secret_type}` (or `POST /secrets/replace`) → body `SecretReplaceRequest`; resolve/validate `secret_type`, run `validate_secret_format`, call `set_user_secret(db, current_user.id, secret_type, value.strip())`, then `db.commit()`. Return a `SecretStatusResponse` for the updated secret (status only — never the value). Choose `PUT /secrets/{secret_type}` for REST-idempotent replacement; keep the path `secret_type` consistent with the body or omit it from the body to avoid mismatch (if both present, validate they match and `400` on conflict).
  - [x] Provider display-name mapping: add a small `secret_type -> label` map (e.g. `claude -> "Claude"`, `openai -> "OpenAI"`, `gemini -> "Gemini / ChatGPT"`, `browser_use -> "Browser Use Cloud"`, `on_premises -> "On-Premises"`, `mcp -> "MCP"`). Source the labels from the UX provider table (ux-design-specification.md §AI Provider Selection). Keep it in `secrets.py` or `ai_qa.secrets` constants.
  - [x] Error handling: map validation failures to `HTTPException(422 or 400, detail=<secret-free message>)`. Never put the submitted value in the error detail or logs. Auth is enforced by `get_current_active_user` (raises `401` for missing/stale sessions) plus the global `AuthMiddleware`.
- [x] **Task 5: Register the router** (AC: 1, 2)
  - [x] In `src/ai_qa/api/app.py`, import `from ai_qa.api.secrets import router as secrets_router` (alphabetical with the other imports) and add `app.include_router(secrets_router, prefix="/api")` next to the other protected routers. Endpoints will be served under `/api/secrets/...` and protected by `AuthMiddleware` like the rest.
- [x] **Task 6: Tests** (AC: 1, 2, 3)
  - [x] New `tests/api/test_secrets_api.py` — copy the in-memory SQLite `TestClient` fixture scaffold from [tests/api/test_admin_rbac_api.py](tests/api/test_admin_rbac_api.py) verbatim (project rules #19, #20, #21): `create_engine` + `StaticPool`, `Base.metadata.create_all(engine, tables=cast(list[Table], [User.__table__, UserSecret.__table__]))`, `dependency_overrides` wiring, `cast(FastAPI, client.app)` for any app-state access, and `engine.dispose()` teardown (rule #1). Import `UserSecret.__table__` so the table is created.
  - [x] **AC1 tests:** GET `/api/secrets/status` for a user with some stored secrets returns 200; assert every entry has `configured`, `status`, `last_updated`, `provider_name`, `validation_state`; assert NO field named `value`/`encrypted_value`/masked token appears anywhere in the JSON; assert "missing" providers are reported with `configured=false`. Leak assertion: store a known plaintext via `set_user_secret`, then assert that plaintext string does NOT appear anywhere in `response.text`.
  - [x] **AC2 tests:** PUT a replacement key → 200; then `get_user_secret(db, user_id, secret_type)` returns the new (stripped) value, proving "future runs use the new value". Replace again with a different key → assert still exactly one row for `(user_id, secret_type)` (no duplicate; the unique constraint + upsert). Assert the previous value is no longer retrievable.
  - [x] **AC2 validation tests:** empty / whitespace-only / `< 8` char values are rejected with `422`/`400` and the response body contains NO submitted value. Unknown `secret_type` rejected.
  - [x] **AC3 / ownership tests:** unauthenticated request → `401`; a user only ever sees/replaces their OWN secrets (no `user_id` param; a second user's secret is not returned). Confirm the replace endpoint cannot return the stored value.
  - [x] Unit-test the service helpers directly in `tests/secrets/test_service.py` (extend the existing file): `list_secret_status` returns metadata-only objects (no secret), `validate_secret_format` raises/returns per the rules. Use the existing `tests/secrets/conftest.py` SQLite scaffold + `make_user` factory.
  - [x] Follow rule #10: use specific exceptions with `match=` (e.g. `pytest.raises(ValueError, match=...)`), never bare `Exception`. Fixtures using `yield` must be typed `Generator[...]` (rule #3).
- [x] **Task 7: Verification (project-context Verification Workflow + Coding Rules)**
  - [x] No DB schema change in this story (the `user_secrets` table already exists from 9.1) — **do NOT** create a new Alembic migration and **skip** `uv run alembic upgrade head` unless you add a column. Confirm no model change before skipping.
  - [x] `uv run ruff check .` and `uv run ruff format --check .` (run `ruff format .` if needed).
  - [x] `uv run mypy src`.
  - [x] Run `uv run pytest` in a fresh terminal (per project-context Verification Workflow §1); confirm the new `tests/api/test_secrets_api.py` and the extended `tests/secrets/test_service.py` pass and nothing regressed.
  - [x] Check Markdown diagnostics for any edited `.md` (rules #7, #8).

## Dev Notes

### Why this story exists / scope boundary

Story 9.1 built the **storage** (`user_secrets` table, `UserSecretEncryptedString`, `set_user_secret`/`get_user_secret` accessor, canonical `secret_type` constants). This story (9.2) puts a **user-facing REST surface** on top of that storage: a read-only **status** endpoint (configured/missing + metadata, never the value) and a **replacement** endpoint (validate format → secure upsert → commit). It lets a user self-recover from an expired/invalid key without admin help.

**Explicitly OUT of scope (later Epic 9 stories — do NOT implement here):**

- Live provider **connection validation** / `validate_connection(...)` → **Story 9.3**.
- Provider **model discovery** / `list_models(...)` → **Story 9.4**.
- Agent **model-assignment review** → **Story 9.5**.
- **Runtime (thread-owner) secret resolution** for agent runs → **Story 9.6**.
- **Saved provider config + rotation-applies-to-future-runs** persistence semantics → **Story 9.7**.
- Full dedicated **secret status/replacement UI panel** → primarily **Epic 16** (FR58 maps to Epic 9 / Epic 16). This story delivers the API + the AC3 contract guarantees; it does not build a new settings page.

This story's `validation_state` is a **stored/format** signal only. 9.3 will enrich it with real provider check results. Leave a code comment marking that extension point so the next dev does not reinvent the field.

### Current state of relevant code (read before coding)

- **`src/ai_qa/secrets/service.py`** (from 9.1) — `set_user_secret(db, user_id, secret_type, value)` upserts by `(user_id, secret_type)` (update `encrypted_value`+`status`, else insert), **caller commits**. `get_user_secret(...)` returns the decrypted value or `None`. Reuse `set_user_secret` for replacement (it already "replaces or supersedes the previous value" per AC2). Add `list_secret_status` / `validate_secret_format` alongside.
- **`src/ai_qa/secrets/__init__.py`** (from 9.1) — canonical `SECRET_TYPE_CLAUDE/OPENAI/GEMINI/BROWSER_USE/ON_PREMISES/MCP`, `PROVIDER_SECRET_TYPE_MAP`, and `resolve_secret_type(provider)` (raises `KeyError` on unknown). Use these constants for the canonical type list and for validating incoming `secret_type`. `resolve_secret_type` lowercases/strips and raises `KeyError` — wrap it if you want a `422` instead of a 500.
- **`src/ai_qa/secrets/models.py`** (from 9.1) — `UserSecret(user_id, secret_type, status="configured", encrypted_value, created_at, updated_at)`; unique `(user_id, secret_type)`. `status` is plaintext metadata; `encrypted_value` is the ONLY secret-bearing column. `updated_at` is the "last updated" metadata for AC1.
- **`src/ai_qa/api/projects.py`** — the reference router shape to mirror: `APIRouter(prefix=..., tags=...)`, `DbSessionDependency`/`CurrentUserDependency` module constants, module-local `BaseModel` response classes documented as "Secret-free", ownership derived from `current_user` (never a `user_id` param). `list_projects` shows the "current user only" pattern for standard users.
- **`src/ai_qa/api/auth/rbac.py`** — `get_current_active_user(request, db)` returns the active `User` from the session (raises `401` for missing/stale/inactive). This is the auth dependency to use. `require_admin` is NOT needed — secrets are per-user, any authenticated active user manages their own.
- **`src/ai_qa/api/app.py`** — routers are registered with `app.include_router(<router>, prefix="/api")` after `AuthMiddleware` is added, so a new router is auth-protected automatically. Add `secrets_router` here.
- **`src/ai_qa/agents/alice.py`** — `_test_connection` rejects `api_key` shorter than 8 chars (the format floor to mirror in `validate_secret_format`). `process()` (~line 344-362) already writes the secret on config-save via `set_user_secret` + `db.commit()`. 9.2 adds an **independent** management surface; do not change alice's flow. Note the 9.1-deferred asymmetry (alice stores unstripped, validates stripped) — fix it only in the NEW replacement path by storing `value.strip()`.
- **Frontend (context only):** `frontend/src/components/ProviderSelector.tsx` already masks credential display (`••••••••`) and never renders stored values — consistent with AC3. `frontend/src/types/provider.ts` has `ProviderConfig.credential_reference` (a reference, not the secret). No new UI is required for this story's ACs; the AC3 "replacement flow only / never display" contract is satisfied by the API never returning a value plus the existing masked input.

### What this story changes vs. preserves

- **Changes / New:** `src/ai_qa/secrets/service.py` (add `list_secret_status`, `get_secret_status`, `validate_secret_format`, `SecretStatus` shape), NEW `src/ai_qa/api/secrets.py` (router + schemas), `src/ai_qa/api/app.py` (register router). NEW `tests/api/test_secrets_api.py`; extend `tests/secrets/test_service.py`.
- **Preserve:** the `user_secrets` table + `UserSecretEncryptedString` (no schema change), `set_user_secret`/`get_user_secret` semantics (caller commits), alice's existing write path, the canonical `secret_type` constants. Do not add a `user_id` request parameter anywhere (ownership is session-derived).

### Source tree components to touch

```
src/ai_qa/secrets/service.py     # UPDATE: list_secret_status / get_secret_status / validate_secret_format / SecretStatus
src/ai_qa/secrets/schemas.py     # OPTIONAL NEW: SecretStatus dataclass (or keep it in service.py)
src/ai_qa/api/secrets.py         # NEW: APIRouter(prefix="/secrets") + request/response Pydantic models
src/ai_qa/api/app.py             # UPDATE: import + include_router(secrets_router, prefix="/api")
tests/api/test_secrets_api.py    # NEW: status + replacement + ownership + leak tests
tests/secrets/test_service.py    # UPDATE: list_secret_status + validate_secret_format unit tests
```

### Endpoint contract (target)

- `GET /api/secrets/status` → `200` `list[SecretStatusResponse]` for the session user. Every canonical secret type represented; `configured=false`/`status="missing"` for types with no row. No secret/masked value anywhere.
- `PUT /api/secrets/{secret_type}` → body `{ "value": "<new key>" }` (and/or `secret_type` in body — keep consistent). `200` `SecretStatusResponse` (metadata only). `422`/`400` on empty/short/unknown-type, with a secret-free detail. `401` when unauthenticated.

### Testing standards summary

- Reuse the canonical API fixture scaffold from `tests/api/test_admin_rbac_api.py` (rules #19/#20/#21): `StaticPool` in-memory SQLite, `cast(list[Table], [...])` in `create_all`, `cast(FastAPI, client.app)` for app access, `dependency_overrides`, `engine.dispose()` teardown.
- Create `UserSecret.__table__` (and `User.__table__`) in the test engine; import `Table` from `sqlalchemy`.
- `Generator[...]`-typed yield fixtures (#3); imports at top (#9, E402); specific exceptions with `match=` (#10); no `client.app.<attr>` chains without `cast(FastAPI, ...)` (#19).
- Leak-style assertions (the known plaintext must not appear in `response.text`) are the primary AC1 guardrail — include at least one per response-returning endpoint.

### Project Structure Notes

- Module boundaries (architecture): the new router lives in `src/ai_qa/api/` (API layer), depends on `ai_qa.secrets` (domain) + `ai_qa.api.auth` (auth) — consistent with how `projects.py`/`admin.py` depend on `ai_qa.projects`/`ai_qa.auth`. Keep secret-handling logic in `ai_qa.secrets`; the router stays a thin HTTP adapter.
- Naming: snake_case locals (#5), PascalCase Pydantic/dataclass models, `secrets_router` import alias matching the `*_router` convention in `app.py`.
- Response models must be secret-free by construction (no field can carry secret bytes) — document each with a "Secret-free" docstring like `projects.py`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 9.2: Secret Status and Replacement API] — user story + acceptance criteria (status non-secret fields; replace/supersede; never display stored key, replacement-only).
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 9] — FRs covered incl. FR36 (per-user ownership of secrets), FR57 (no secrets in API/WebSocket responses), FR58 (secret status and replacement UI), FR59/FR60 (runtime resolution / rotation — later stories).
- [Source: _bmad-output/planning-artifacts/architecture.md#Security (critical)] — "User secrets must never appear in ... logs, WebSocket payload history ... artifacts"; per-user keys encrypted with `USER_SECRETS_ENCRYPTION_KEY`.
- [Source: _bmad-output/planning-artifacts/architecture.md#Secret Storage] — "per-user encrypted PostgreSQL secret fields with rotation UX and no secret echoing in API/WebSocket responses".
- [Source: _bmad-output/planning-artifacts/architecture.md#Secret UX] — "UI shows provider/MCP secret status and replacement actions, but never displays stored secret values."
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#AI Provider Selection] — provider labels for `provider_name` mapping (Browser Use Cloud, Claude, Gemini / ChatGPT, On-Premises).
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Provider Credential Input Rules] — credential form collects user-specific API key only; base URLs are deployment config; never display secrets.
- [Source: src/ai_qa/secrets/service.py] — `set_user_secret` (reuse for replacement), `get_user_secret`; caller-commits contract.
- [Source: src/ai_qa/secrets/__init__.py] — canonical `SECRET_TYPE_*`, `PROVIDER_SECRET_TYPE_MAP`, `resolve_secret_type`.
- [Source: src/ai_qa/secrets/models.py#UserSecret] — `status`/`updated_at` non-secret metadata; `encrypted_value` the only secret column; unique `(user_id, secret_type)`.
- [Source: src/ai_qa/api/projects.py] — reference router pattern (prefix/tags, `CurrentUserDependency`, secret-free response models, session-derived ownership).
- [Source: src/ai_qa/api/auth/rbac.py#get_current_active_user] — per-user auth dependency (401 on missing/stale/inactive).
- [Source: src/ai_qa/api/app.py] — router registration with `prefix="/api"` behind `AuthMiddleware`.
- [Source: src/ai_qa/agents/alice.py#_test_connection] — `< 8` char rejection (format floor); existing `set_user_secret` write path to leave unchanged.
- [Source: tests/api/test_admin_rbac_api.py] — canonical in-memory SQLite TestClient fixture to copy (rules #19/#20/#21).
- [Source: project-context.md] — testing/coding rules (#1 SQLite dispose, #3 Generator typing, #9 import order, #10 specific exceptions, #19 TestClient cast, #20 create_all cast, #21 reuse canonical fixture).

### Previous Story Intelligence (Story 9.1)

- 9.1 established the storage + accessor. **Reuse `set_user_secret` for replacement** — do not write a second upsert path (9.1 review already flagged a SELECT-then-INSERT race as deferred; do not widen it).
- 9.1 **deferred** items relevant here: (a) corrupt/wrong-key ciphertext returns raw ciphertext as plaintext on decrypt failure — out of scope for 9.2 (status never decrypts; it reads metadata only — lean on that, do NOT call `get_user_secret` in the status path); (b) provider lookup uses silent `.get()` — when validating incoming `secret_type`, prefer an explicit reject (`422`) over silent skip; (c) alice stores unstripped value — fix only in the new replacement path by storing `value.strip()`.
- 9.1 test patterns to mirror: ciphertext-at-rest leak assertions, the `tests/secrets/conftest.py` SQLite scaffold + `make_user` factory, and supplying a valid `USER_SECRETS_ENCRYPTION_KEY` before importing config-dependent modules.
- The shared `tests/conftest.py` `mock_db.scalar` returns `None` (fresh user = no stored secret) — useful if you unit-test status against a mock.

### Git Intelligence

- HEAD `c3f6783 story 9-1 code and test OK` (baseline). Recent commits: `9fe8a5d done epic 7 and 8`, `5a01a33 story 8-7 ...`. The `user_secrets` table and accessor landed in 9.1 and are stable. Build the API directly on top; do not touch auth/RBAC or the 9.1 storage layer.
- Commit convention: per-story commits like `story 9-2 code and test OK`.

### Latest Tech Information

- No new dependencies. Uses already-pinned `fastapi`, `pydantic`/`pydantic-settings>=2.4`, `sqlalchemy>=2.0` (typed `Mapped[...]`), `cryptography` (via the existing `UserSecretEncryptedString`). Python 3.12+, `uv`, `ruff` (py312, line-length 100), `mypy strict`.
- FastAPI router/dependency patterns are identical to the existing `projects.py`/`admin.py` — no version-specific gotchas. Pydantic v2 `BaseModel` + `ConfigDict(from_attributes=True)` is the in-repo convention when mapping ORM rows to responses.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (Amelia dev agent)

### Debug Log References

- `uv run ruff check .` → All checks passed.
- `uv run ruff format .` → 2 test files reformatted, then `--check` clean.
- `uv run mypy src` → Success: no issues found in 74 source files.
- `uv run pytest` → 724 passed, 2 skipped; total coverage 81.79% (>= 80% gate). New `src/ai_qa/api/secrets.py` and `src/ai_qa/secrets/service.py` at 100% coverage.

### Implementation Plan

- **Service layer (`secrets/service.py`):** Added a frozen, secret-free `SecretStatus` dataclass plus `list_secret_status` (iterates `CANONICAL_SECRET_TYPES`, reports missing providers as `configured=False`/`status="missing"`), `get_secret_status` (single type), and `validate_secret_format` (format-only floor: non-empty after strip, `>= 8` chars). Reused the existing `set_user_secret` upsert for replacement — no parallel write path. Status reads metadata only and never decrypts.
- **Constants (`secrets/__init__.py`):** Added ordered `CANONICAL_SECRET_TYPES` tuple for iteration + incoming-type validation.
- **Router (`api/secrets.py`):** New thin HTTP adapter mirroring `projects.py`. `GET /secrets/status` returns `list[SecretStatusResponse]` for the session user only; `PUT /secrets/{secret_type}` validates the canonical type + format, stores `value.strip()`, commits, and returns metadata only. Provider display-name map sourced from the UX provider table. `value` lives only on the write-only request model; no response model can carry secret bytes.
- **App (`api/app.py`):** Registered `secrets_router` with `prefix="/api"` behind `AuthMiddleware`.
- **Scope discipline:** No live provider connection validation (Story 9.3), no model discovery (9.4), no schema change. `validation_state` reflects stored/format state only, with a code comment marking the 9.3 extension point.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.
- AC1 satisfied: status endpoint returns only non-secret metadata (`secret_type`, `provider_name`, `configured`, `status`, `validation_state`, `last_updated`); leak tests assert stored plaintext never appears in `response.text`.
- AC2 satisfied: replacement reuses `set_user_secret` (single-row upsert), stores the stripped value, and tests confirm `get_user_secret` returns the new value with exactly one row (no duplicate, previous value superseded).
- AC3 satisfied: no endpoint returns a stored or masked value; the replace endpoint returns status only; ownership is session-derived (no `user_id` param), with auth (`401`) and cross-user isolation tests.
- Fixed the 9.1-deferred strip asymmetry only inside the new replacement path (stores `value.strip()`); `alice.py` left unchanged.

### File List

- `src/ai_qa/secrets/__init__.py` (modified) — added `CANONICAL_SECRET_TYPES` tuple + export.
- `src/ai_qa/secrets/service.py` (modified) — added `SecretStatus`, `list_secret_status`, `get_secret_status`, `validate_secret_format`, `STATUS_MISSING`, `MIN_SECRET_LENGTH`.
- `src/ai_qa/api/secrets.py` (new) — secrets status/replacement router + `SecretStatusResponse`/`SecretReplaceRequest` schemas + provider display-name map.
- `src/ai_qa/api/app.py` (modified) — import and register `secrets_router` under `/api`.
- `tests/api/test_secrets_api.py` (new) — AC1/AC2/AC3 + ownership + leak API tests.
- `tests/secrets/test_service.py` (modified) — unit tests for `list_secret_status`, `get_secret_status`, `validate_secret_format`.

## Change Log

| Date       | Version | Description                                                              |
| ---------- | ------- | ------------------------------------------------------------------------ |
| 2026-06-07 | 0.1     | Story drafted by create-story context engine. Status → ready-for-dev.    |
| 2026-06-07 | 0.2     | Implemented secret status + replacement API (service helpers, router, registration, tests). All checks pass. Status → review. |
