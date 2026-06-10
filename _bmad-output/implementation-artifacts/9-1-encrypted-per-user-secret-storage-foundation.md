---
baseline_commit: 9fe8a5d97eb2917f3f099da7a53a7dd8f46a4a9c
---

# Story 9.1: Encrypted Per-User Secret Storage Foundation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a project user,
I want my AI provider keys and MCP key stored securely under my own account,
so that my credentials are isolated from other users and never stored in plaintext configuration.

## Acceptance Criteria

**AC1 — Encryption before persistence**

**Given** a user submits an AI provider API key or MCP key
**When** the backend stores the value
**Then** the secret is encrypted using `AppSettings.user_secrets_encryption_key` before persistence
**And** the plaintext secret is not stored in `.env`, plaintext JSON columns, logs, messages, artifacts, or WebSocket payload history.

**AC2 — Secret value / metadata separation**

**Given** the backend stores secret records
**When** secret metadata is queried
**Then** encrypted secret values are stored separately from non-secret metadata such as provider name, status, last updated timestamp, and owning user id.

**AC3 — Fail-fast key validation, key never in DB**

**Given** `USER_SECRETS_ENCRYPTION_KEY` is missing or invalid
**When** the application starts
**Then** startup validation fails fast with an actionable configuration error
**And** the encryption key is never stored in PostgreSQL.

## Tasks / Subtasks

- [x] **Task 1: Add `user_secrets_encryption_key` setting with fail-fast validation** (AC: 1, 3)
  - [x] In `src/ai_qa/config.py`, add a `user_secrets_encryption_key: str` field to `AppSettings` (env var `USER_SECRETS_ENCRYPTION_KEY`). Do **not** give it a usable real default — use empty string `""` so a missing value is detectable.
  - [x] Add a Pydantic `@field_validator("user_secrets_encryption_key")` (or `@model_validator(mode="after")`) that fails fast when the value is empty OR not a valid Fernet key. Validate by attempting `Fernet(value.encode("utf-8"))` inside a `try/except` and raising `ValueError` (Pydantic converts to `ValidationError`) with an actionable message, e.g. `"USER_SECRETS_ENCRYPTION_KEY is missing or invalid. Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""`.
  - [x] Because `src/ai_qa/api/__init__.py` runs `create_app(AppSettings())` at import, this validation already fails fast at process startup — confirm no separate startup hook is needed. Add the import `from cryptography.fernet import Fernet` at the top of `config.py` (E402 rule).
  - [x] Confirm the key is sourced only from environment / `AppSettings` and is never written to any ORM model or migration (AC3 second clause).
- [x] **Task 2: Create a user-secrets Fernet/encryption type bound to the new key** (AC: 1)
  - [x] Do **not** reuse `db_encryption_key`. The existing `EncryptedString` in `src/ai_qa/db/types.py` is bound to `settings.db_encryption_key` via `get_fernet()`. Add a parallel `get_user_secrets_fernet()` returning a module-level cached `Fernet` built from `settings.user_secrets_encryption_key`, plus a `UserSecretEncryptedString(TypeDecorator[str])` that mirrors `EncryptedString` but calls `get_user_secrets_fernet()`.
  - [x] Keep the same `process_bind_param` / `process_result_value` semantics (None passthrough, encrypt-on-write, decrypt-on-read, `cache_ok = True`). Reuse the existing corrupt-value fallback behavior.
- [x] **Task 3: Create the `UserSecret` ORM model (value/metadata separation)** (AC: 1, 2)
  - [x] Add `src/ai_qa/secrets/__init__.py` and `src/ai_qa/secrets/models.py` (architecture names `src/ai_qa/secrets/` as the home for per-user secret storage — see References).
  - [x] Define `UserSecret(UUIDPrimaryKeyMixin, TimestampMixin, Base)` with `__tablename__ = "user_secrets"`. Columns:
    - `user_id: Mapped[UUID]` → `ForeignKey("users.id", ondelete="CASCADE")`, `nullable=False`, `index=True` (owning user id metadata).
    - `secret_type: Mapped[str]` = `mapped_column(String(50), nullable=False)` — provider/MCP identifier (e.g. `claude`, `openai`, `gemini`, `browser_use`, `on_premises`, `mcp`). This is non-secret metadata.
    - `status: Mapped[str]` = `mapped_column(String(50), nullable=False, default="configured")` — non-secret status metadata.
    - `encrypted_value: Mapped[str]` = `mapped_column(UserSecretEncryptedString(1024), nullable=False)` — the only secret-bearing column.
    - `TimestampMixin` already supplies `created_at` / `updated_at` (the "last updated timestamp" metadata).
    - `__table_args__ = (UniqueConstraint("user_id", "secret_type", name="uq_user_secrets_user_secret_type"),)` so each user has one row per secret type.
  - [x] Add `secrets: Mapped[list["UserSecret"]] = relationship(back_populates="user", cascade="all, delete-orphan")` to `User` in `src/ai_qa/db/models.py`, and a matching `user: Mapped["User"] = relationship(back_populates="secrets")` on `UserSecret`. Use `TYPE_CHECKING` imports for cross-module forward refs (project rule #4) to avoid runtime import cycles between `ai_qa.secrets.models` and `ai_qa.db.models`.
  - [x] The legacy inline `*_key` columns on `User` are being **retired** in this story (Task 5 migrates consumers, Task 6 drops the columns). Add the `User.secrets` relationship now; do not preserve the old columns.
- [x] **Task 4: Minimal secret accessor service** (AC: 1, 2)
  - [x] Add `src/ai_qa/secrets/service.py` with a thin, well-typed accessor that the existing consumers will use instead of the inline columns:
    - `set_user_secret(db: Session, user_id: UUID, secret_type: str, value: str) -> UserSecret` — upsert by `(user_id, secret_type)`: update `encrypted_value` + `status` on the existing row, or insert a new row. Caller commits (mirror current `alice.py` which calls `db.commit()` itself), or commit inside and document it — pick one and be consistent.
    - `get_user_secret(db: Session, user_id: UUID, secret_type: str) -> str | None` — return the decrypted value (the ORM type decrypts on read) or `None` when no row exists.
  - [x] Define canonical `secret_type` constants + a provider→secret_type mapping (in `src/ai_qa/secrets/__init__.py` or `constants.py`). Must cover every id used by current consumers: `base.py` provider names (`claude`/`anthropic`, `openai`, `gemini`/`google`, `on_premises`) and `alice.py` provider ids (`claude`, `gemini-chatgpt`/`gemini`, `openai`, `on-premises`, `browser-use-cloud`). Normalize aliases to one canonical key per provider.
  - [x] Keep behavior scoped to "current user's secret by provider" — do NOT add thread-owner resolution (9.6), provider validation (9.3), or a status/replacement REST API (9.2). This is only the storage accessor those stories will extend.
- [x] **Task 5: Migrate existing consumers off the inline columns** (AC: 1, regression)
  - [x] `src/ai_qa/agents/base.py` (~lines 150–163): read each provider key via `get_user_secret(db, user.id, <secret_type>)` instead of `user.claude_key` / `user.openai_key` / `user.gemini_key` / `user.on_premises_key`. Read the full surrounding function first to confirm a `Session` is in scope; if not, thread one through from the caller.
  - [x] `src/ai_qa/agents/alice.py`: replace the read at ~line 273 (`user.on_premises_key`) with `get_user_secret(...)`, and replace the writes at ~lines 351–362 (`user.<provider>_key = api_key`) with `set_user_secret(...)`. Preserve the existing `db.commit()` semantics so config-save still persists.
  - [x] `mcp_key` has **no source consumer today** (only the model + migration reference it) — no runtime migration needed, just drop the column in Task 6.
  - [x] Grep the codebase again after editing to confirm zero remaining references to `*_key` attributes on `User` outside the model definition.
- [x] **Task 6: Alembic migration — add `user_secrets`, drop legacy columns** (AC: 2)
  - [x] Register the new model with `Base.metadata` for autogenerate: add `import ai_qa.secrets.models  # noqa: F401` to `alembic/env.py` next to the existing model imports.
  - [x] One migration that (a) **creates** the `user_secrets` table (FK, unique constraint, timestamps) and (b) **drops** the 6 legacy columns from `users`: `browser_use_key`, `claude_key`, `gemini_key`, `openai_key`, `on_premises_key`, `mcp_key`. Follow `NAMING_CONVENTION` in `src/ai_qa/db/base.py`. Generate via `uv run alembic revision --autogenerate -m "add user_secrets, drop inline user keys"`, then review (autogenerate may miss the custom type — ensure `encrypted_value` is `sa.String(length=1024)`; ensure `downgrade()` re-adds the dropped columns as `ai_qa.db.types.EncryptedString(length=512)` to mirror migration `e1287c77977a`).
  - [x] **Dev-phase data note:** dropping the columns discards any existing encrypted keys (acceptable in dev — users re-enter keys). Call this out in the migration docstring.
  - [x] Apply locally with `uv run alembic upgrade head` and confirm schema (project-context Verification Workflow §1, schema changed).
- [x] **Task 7: Tests** (AC: 1, 2, 3)
  - [x] `tests/db/test_types.py` (or a new `tests/secrets/test_types.py`): roundtrip encrypt/decrypt for `UserSecretEncryptedString`, None passthrough, and that the bound param output differs from plaintext and is NOT decryptable with the `db_encryption_key` Fernet (proves key separation).
  - [x] `tests/unit/test_config.py`: missing `USER_SECRETS_ENCRYPTION_KEY` raises `ValidationError`; invalid (non-Fernet) value raises `ValidationError`; a valid generated Fernet key loads successfully. Use `monkeypatch.setenv` + `importlib.reload(cfg)` exactly like the existing tests in that file, and set a valid key in the positive case.
  - [x] New `tests/secrets/test_service.py`: `set_user_secret` inserts then upserts (no duplicate row for same `user_id`+`secret_type`), `get_user_secret` returns the decrypted value and `None` when absent. Use the in-memory SQLite scaffold from `tests/api/test_admin_rbac_api.py` with `cast(list[Table], [User.__table__, UserSecret.__table__])` and `engine.dispose()` teardown.
  - [x] New `tests/secrets/test_models.py`: persist a `UserSecret`, assert the raw stored DB value is ciphertext (not the plaintext) and that metadata columns (`secret_type`, `status`, `user_id`, `updated_at`) are queryable in plaintext. Same SQLite scaffold; set `USER_SECRETS_ENCRYPTION_KEY` before importing config-dependent modules.
  - [x] Update `tests/test_agents/test_alice.py`: it currently sets `mock_user.claude_key`, `on_premises_key`, etc. directly. Rework those mocks to the new accessor (e.g. patch `get_user_secret` / `set_user_secret`) so the suite reflects real behavior (project rule #15 — mocks must follow the new signatures).
  - [x] Leak-style assertion: dump the row via raw SQL / column access and assert the plaintext secret string does not appear in the stored `encrypted_value`.
- [x] **Task 8: Document the new required env var** (AC: 3)
  - [x] Add `USER_SECRETS_ENCRYPTION_KEY=replace-with-fernet-key` to `.env.example` under a clear comment block explaining it is required at startup and how to generate it. Note in the comment that it must never be committed or stored in the database.
- [x] **Task 9: Verification (project-context Verification Workflow + Coding Rules)**
  - [x] `uv run ruff check .` and `uv run ruff format --check .` (run `ruff format .` if needed).
  - [x] `uv run mypy src`.
  - [x] `uv run alembic upgrade head` (schema changed), then `uv run pytest` in a fresh terminal. Confirm `test_agents` and any secret tests pass after the consumer migration.
  - [x] Check Markdown diagnostics for any edited `.md` (project rule #7, #8).

### Review Findings

_Adversarial code review (Blind Hunter + Edge Case Hunter + Acceptance Auditor), 2026-06-07. Result: 0 decision-needed, 1 patch, 7 deferred, 8 dismissed as noise. AC1/AC2/AC3 audited as PASS; scope boundary respected._

#### Patch

- [x] [Review][Patch] File List / Change Log omits the new `tests/secrets/conftest.py` [_bmad-output/implementation-artifacts/9-1-encrypted-per-user-secret-storage-foundation.md] — the conftest (SQLite scaffold + `make_user` factory used by `test_service.py` and `test_models.py`) was added but not recorded in the story's File List. _Resolved: added to File List + Change Log._

#### Deferred (pre-existing / out of scope)

- [x] [Review][Defer] Corrupt/wrong-key ciphertext returned as plaintext and used as the API key [src/ai_qa/db/types.py:process_result_value, src/ai_qa/agents/base.py:get_llm_config] — deferred, pre-existing. On decrypt failure the type returns the raw ciphertext; in `get_llm_config` that value is truthy so it is sent to the provider as the key and the env fallback is skipped. Identical to the existing `EncryptedString` behavior that Task 2 mandated reusing. Reconsider alongside key-rotation handling in Story 9.7.
- [x] [Review][Defer] Provider lookup uses silent `PROVIDER_SECRET_TYPE_MAP.get()` instead of the raising/normalizing `resolve_secret_type` (which is exported but unused) [src/ai_qa/agents/alice.py:351, src/ai_qa/agents/base.py:154, src/ai_qa/secrets/__init__.py:45] — deferred, pre-existing. Unknown/mis-cased provider yields `None` and silently skips persist/read. base.py lowercases and alice passes canonical lowercase ids, so it is theoretical today; old if/elif code skipped unknowns too.
- [x] [Review][Defer] `set_user_secret` SELECT-then-INSERT cross-session race can raise `IntegrityError` on commit [src/ai_qa/secrets/service.py] — deferred. Low likelihood; the unique constraint protects data integrity and alice's write path is try/except-wrapped.
- [x] [Review][Defer] `api_key` stored unstripped while the connection test validates the stripped value [src/ai_qa/agents/alice.py:349 vs :596] — deferred, pre-existing. Old inline-column code stored the same unstripped value.
- [x] [Review][Defer] Module-level Fernet cache prevents key rotation and can carry a stale key across reloads [src/ai_qa/db/types.py:get_user_secrets_fernet] — deferred. Mirrors existing `get_fernet`; rotation is Story 9.7.
- [x] [Review][Defer] alice `get_on_prem_defaults` / `process` pass `user_id` without the `None` guard base.py has [src/ai_qa/agents/alice.py:270,352] — deferred, latent. Harmless read (returns `None`); write path is try/except-wrapped.
- [x] [Review][Defer] `mock_broadcast` yield-fixtures in test_alice.py/test_base.py lack `Generator` typing (rule #3) [tests/test_agents/test_alice.py, tests/test_agents/test_base.py] — deferred, pre-existing, non-gating (mypy runs on src only).

#### Dismissed (verified non-issues)

- Migration drops 6 legacy columns without backfill — spec explicitly accepts dev-phase data loss; documented in the migration docstring.
- Fail-fast validator "won't run on default `""`" — false: `tests/unit/test_config.py` proves a missing `USER_SECRETS_ENCRYPTION_KEY` raises `ValidationError` (7/7 config tests pass).
- `encrypted_value` "misleading name" — spec-mandated name; mirrors the `EncryptedString` TypeDecorator pattern (column holds ciphertext, attribute holds plaintext in memory).
- `status` column lacks server_default — moot: new table, ORM inserts always set `status="configured"`.
- Circular import `db/models` ↔ `secrets/models` — false: `secrets/models` uses `TYPE_CHECKING` for `User`; imports verified working (tests pass).
- Empty/blank api_key persisted as `configured` — guarded: `_test_connection` rejects keys `< 8` chars before the persist block runs.
- `encrypted_value` String(1024) overflow — spec-mandated size; ~700-char plaintext capacity, ample for real keys/tokens.
- `logger.warning` on persist failure — pre-existing unchanged behavior.

## Dev Notes

### Why this story exists / scope boundary

This is the **foundation** story for Epic 9 (Per-User Secret Management). It establishes (a) a single shared encryption key for user secrets in `.env`, (b) fail-fast startup validation of that key, and (c) a dedicated `user_secrets` table that separates encrypted secret values from non-secret metadata. It also **retires the legacy inline `*_key` columns** on `users` and migrates current consumers onto the new storage via a thin accessor (so no dead/duplicate secret paths are left behind). **Do not implement** the status/replacement REST API (Story 9.2), provider validation (9.3), model discovery (9.4), assignment review (9.5), thread-owner runtime resolution (9.6), or saved-config/rotation behavior (9.7). The consumer migration here keeps the existing "current user's key by provider" behavior — only the storage backing changes.

### Current state of secret handling (read before coding)

- `src/ai_qa/db/models.py` → `User` currently has inline encrypted secret columns: `browser_use_key`, `claude_key`, `gemini_key`, `openai_key`, `on_premises_key`, `mcp_key`, all `EncryptedString(512)` encrypted with **`db_encryption_key`**. **These are being removed in this story.** Known runtime consumers (must be migrated, then columns dropped):
  - `src/ai_qa/agents/base.py` (~lines 150–163): reads `user.claude_key` / `user.openai_key` / `user.gemini_key` / `user.on_premises_key` to build the LLM `api_key`.
  - `src/ai_qa/agents/alice.py` (~line 273): reads `user.on_premises_key`; (~lines 351–362): writes `user.<provider>_key = api_key` on config save, then `db.commit()`.
  - `mcp_key`: **no source consumer** — only the model + migration `e1287c77977a` reference it. Drop the column; nothing to migrate.
  - `tests/test_agents/test_alice.py`: sets these attributes on a mock user — update to the new accessor.
- `src/ai_qa/db/types.py` → `EncryptedString` + `get_fernet()` use `AppSettings().db_encryption_key`. This is the pattern to mirror, but bind the new type to `user_secrets_encryption_key`. Note `db_encryption_key` currently ships a hardcoded default; the new `user_secrets_encryption_key` must NOT — AC3 requires fail-fast when missing.
- `src/ai_qa/config.py` → `AppSettings` is a `pydantic_settings.BaseSettings`. There is currently **no** field validator that fails fast on a missing key. Add one for the new field. Existing tests show the reload pattern (`importlib.reload(cfg)`).
- `src/ai_qa/api/__init__.py` → `app = create_app(AppSettings())` instantiates settings at import time, so a Pydantic validator is sufficient to fail the process fast at startup. No separate lifespan check required.
- `alembic/env.py` → imports `ai_qa.db.models` and `ai_qa.threads.models` to populate `Base.metadata`; `target_metadata = Base.metadata`. Add the new module import here or the migration autogenerate will miss the table.

### What this story changes vs. preserves

- **Changes:** `config.py` (new field + validator), `db/types.py` (new fernet getter + type), `db/models.py` (remove 6 inline `*_key` columns, add `secrets` relationship), `agents/base.py` + `agents/alice.py` (read/write via the new accessor), `alembic/env.py` (new import), `.env.example`. New files: `src/ai_qa/secrets/__init__.py`, `src/ai_qa/secrets/models.py`, `src/ai_qa/secrets/service.py`, one Alembic migration (create `user_secrets` + drop legacy columns), new tests.
- **Preserve:** `db_encryption_key` and the existing `EncryptedString` type/behavior (still used for other encrypted columns); all current migrations; the *behavioral contract* of base.py/alice.py (same provider→key resolution, just sourced from `user_secrets`).

### Source tree components to touch

```
src/ai_qa/config.py                  # UPDATE: add user_secrets_encryption_key + validator
src/ai_qa/db/types.py                # UPDATE: add get_user_secrets_fernet + UserSecretEncryptedString
src/ai_qa/db/models.py               # UPDATE: drop 6 inline *_key columns, add User.secrets relationship
src/ai_qa/agents/base.py             # UPDATE: read provider key via get_user_secret
src/ai_qa/agents/alice.py            # UPDATE: read/write secrets via accessor
src/ai_qa/secrets/__init__.py        # NEW (+ canonical secret_type constants/mapping)
src/ai_qa/secrets/models.py          # NEW: UserSecret ORM model
src/ai_qa/secrets/service.py         # NEW: set_user_secret / get_user_secret accessor
alembic/env.py                       # UPDATE: import ai_qa.secrets.models
alembic/versions/<rev>_add_user_secrets_drop_inline_keys.py  # NEW migration
.env.example                         # UPDATE: document USER_SECRETS_ENCRYPTION_KEY
tests/secrets/test_models.py         # NEW
tests/secrets/test_service.py        # NEW
tests/secrets/test_types.py          # NEW (or extend tests/db/test_types.py)
tests/unit/test_config.py            # UPDATE: key validation tests
tests/test_agents/test_alice.py      # UPDATE: mock the new accessor instead of *_key attrs
```

### Testing standards summary

- Tests mirror `src/ai_qa/` structure under top-level `tests/` (architecture). New `tests/secrets/` dir is appropriate; add `__init__.py` if sibling dirs have one (some do, e.g. `tests/mcp/__init__.py`).
- In-memory SQLite + `StaticPool`; dispose the engine in teardown (project rule #1, `ResourceWarning`).
- Use `cast(list[Table], [...])` in `Base.metadata.create_all(engine, tables=...)` and import `Table` from `sqlalchemy` (project rule #20).
- Fixtures using `yield` must be typed `Generator[...]` (project rule #3).
- No bare `pytest.raises(Exception)` — use `ValidationError` / `ValueError` with `match=` (project rule #10).
- All imports at top of file (project rule #9, E402).

### Project Structure Notes

- Module boundaries (architecture): `config` depends on `pydantic-settings` only and must NOT depend on domain services or user secret values. The new validator stays inside `config.py` and only references `cryptography.fernet.Fernet` — acceptable. `db` depends on `config` + `sqlalchemy`. The new `secrets` module depends on `db` (Base, mixins, types) — consistent with the documented dependency direction.
- Naming: snake_case columns/locals, PascalCase model classes. Local Fernet variables must be snake_case, e.g. `user_secrets_fernet` not `Fernet` aliasing (project rule #5).
- Forward references across `ai_qa.secrets.models` ↔ `ai_qa.db.models` must use `TYPE_CHECKING` imports to avoid a runtime import cycle and satisfy ruff `F821` / mypy `name-defined` (project rule #4).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 9.1: Encrypted Per-User Secret Storage Foundation] — user story + acceptance criteria.
- [Source: _bmad-output/planning-artifacts/architecture.md#Security Architecture] — "System secrets such as `USER_SECRETS_ENCRYPTION_KEY` are loaded from environment configuration and must not be stored in PostgreSQL"; "User secrets ... per-user encrypted PostgreSQL fields ... never returned through API/WebSocket, never logged."
- [Source: _bmad-output/planning-artifacts/architecture.md#Configuration & Environment] — environment owns `USER_SECRETS_ENCRYPTION_KEY`; per-user keys not in `.env`; PostgreSQL stores secret status metadata separately; startup fail-fast if encryption key missing/invalid.
- [Source: _bmad-output/planning-artifacts/architecture.md#FR14-15b (component mapping)] — `src/ai_qa/secrets/` is the designated module for per-user encrypted AI provider and MCP key storage.
- [Source: _bmad-output/planning-artifacts/architecture.md#Decision Impact Analysis] — implementation sequence: config + encryption key validation → exceptions → DB models/migrations incl. user secrets → secret encryption service.
- [Source: src/ai_qa/db/types.py] — `EncryptedString` Fernet pattern to mirror (bound to `db_encryption_key`).
- [Source: src/ai_qa/db/models.py#User] — inline encrypted secret columns being removed in this story.
- [Source: src/ai_qa/agents/base.py] — provider→`user.<provider>_key` read sites to migrate (~lines 150–163).
- [Source: src/ai_qa/agents/alice.py] — `on_premises_key` read (~273) and provider-key writes + `db.commit()` (~351–362) to migrate.
- [Source: alembic/versions/e1287c77977a_move_agent_config_to_thread.py] — migration that originally added the inline `*_key` columns; mirror its column types in the new migration's `downgrade()`.
- [Source: src/ai_qa/db/base.py] — `Base`, `UUIDPrimaryKeyMixin`, `TimestampMixin`, `NAMING_CONVENTION`.
- [Source: src/ai_qa/config.py#AppSettings] — settings/validation insertion point; `db_encryption_key` reference field.
- [Source: src/ai_qa/api/__init__.py] — `create_app(AppSettings())` at import → validator gives startup fail-fast.
- [Source: alembic/env.py] — model imports + `target_metadata` for autogenerate.
- [Source: tests/api/test_admin_rbac_api.py] — canonical in-memory SQLite TestClient fixture scaffold (project rule #21).
- [Source: project-context.md] — global testing/coding rules (#1 SQLite dispose, #3 Generator typing, #4 TYPE_CHECKING forward refs, #5 snake_case locals, #9 import order, #10 specific exceptions, #20 `create_all(tables=...)` cast).

### Previous Story Intelligence

This is the first story in Epic 9 — no prior Epic 9 story. Cross-epic learnings carried from `project-context.md` and prior epics:

- The Fernet-based `EncryptedString` infra was introduced in the Epic 6 persistence work (Story 6.1) — reuse its proven `process_bind_param`/`process_result_value` shape rather than reinventing encryption.
- API/DB test failures in earlier epics traced to un-disposed SQLite engines and un-cast `create_all(tables=...)` lists — both codified as project rules; apply them here from the start.
- mypy `strict = true` and ruff (`E,W,F,I,B,N,UP`) gate every change; `db_encryption_key.encode("utf-8")` style is the existing pattern for feeding Fernet.

### Git Intelligence

Recent commits (`git log --oneline`): `9fe8a5d done epic 7 and 8`, `5a01a33 story 8-7 ...`, … The repo just closed Epics 7 & 8 (auth, RBAC, admin dashboard). The `User` model and auth/session infra are stable and current — build the secret storage on top of the existing `users` table and `Base` metadata without touching auth flows. Commit convention observed: per-story commits like `story X-Y code and test OK`.

### E2E test secrets (future use — not consumed by this story)

`.env` / `.env.example` now define real per-user E2E secrets under `# --- Testing Environment ---`: `TEST_BROWSER_USE_KEY`, `TEST_CLAUDE_KEY`, `TEST_GEMINI_KEY`, `TEST_OPENAI_KEY`, `TEST_ON_PREMISES_KEY`, `TEST_MCP_KEY`.

- This story's tests use **in-memory SQLite + a generated Fernet key** and do NOT read these variables. Do not wire them into unit/api tests.
- In later Epic 9 E2E work, tests will read these `TEST_*` values and **seed them into `user_secrets` via the real API** (per project-context "No Mocking" rule), then clean up afterward with an Admin token (project-context "Data Cleanup" rule). They are deliberately separate from the system base-URL settings (`CLAUDE_API_BASE_URL`, etc.) which remain environment-owned.
- These are secrets: keep `.env` gitignored; never echo the values in logs, messages, or assertions.

### Latest Tech Information

Already-pinned dependencies (no upgrades needed for this story):

- `cryptography` (transitive, via `python-jose[cryptography]>=3.3`) provides `cryptography.fernet.Fernet` — already used by `db/types.py`. Fernet keys are 32 url-safe base64-encoded bytes; generate with `Fernet.generate_key()`. `Fernet(badkey)` raises `ValueError` — use that for validation.
- `sqlalchemy>=2.0` (typed `Mapped[...]` / `mapped_column`), `alembic>=1.13`, `psycopg[binary]>=3.1`, `pydantic-settings>=2.4.0`. Use SQLAlchemy 2.0 declarative typing consistent with existing models.
- Python 3.12+, `uv` package manager, `ruff` (target py312, line-length 100), `mypy` strict.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (bmad-dev-story workflow)

### Debug Log References

- `uv run ruff check .` → All checks passed
- `uv run ruff format --check .` → 156 files formatted
- `uv run mypy src` → Success: no issues found in 73 source files
- `uv run alembic upgrade head` → applied `b7d2f1a9c4e5`; downgrade/upgrade round-trip verified
- `uv run pytest` → 663 passed, 2 skipped (pre-existing browser-integration skips); coverage 81.55%

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.
- **Task 1:** Added `user_secrets_encryption_key` (env `USER_SECRETS_ENCRYPTION_KEY`, empty default) to `AppSettings` with a `@field_validator` that fails fast (empty or non-Fernet → `ValueError`/`ValidationError`) using the actionable generate-key message. Validation runs at import via `create_app(AppSettings())`, so no separate startup hook is needed. Key is sourced only from env/settings, never persisted (AC1, AC3).
- **Task 2:** Added `get_user_secrets_fernet()` (module-cached) and `UserSecretEncryptedString(TypeDecorator[str])` in `db/types.py`, mirroring `EncryptedString` semantics but bound to the dedicated user-secrets key. `db_encryption_key`/`EncryptedString` left intact.
- **Task 3:** Created `src/ai_qa/secrets/{__init__,models}.py`. `UserSecret` separates the single encrypted column (`encrypted_value`) from plaintext metadata (`secret_type`, `status`, `user_id`, timestamps) with a unique `(user_id, secret_type)` constraint (AC2). Added `User.secrets` relationship and dropped the 6 inline `*_key` columns. `User` mapper registration of `UserSecret` is guaranteed by a top-level import in `db/models.py` (no runtime cycle — `secrets.models` only uses `TYPE_CHECKING` for `User`).
- **Task 4:** Added `src/ai_qa/secrets/service.py` with `set_user_secret` (upsert, caller commits) and `get_user_secret` (decrypts on read, `None` when absent), plus canonical `secret_type` constants and a `PROVIDER_SECRET_TYPE_MAP` / `resolve_secret_type` covering every base.py/alice.py provider alias.
- **Task 5:** Migrated `agents/base.py` (`get_llm_config`) and `agents/alice.py` (`get_on_prem_defaults` read + `process` write) onto the accessor; preserved `db.commit()` semantics. Grep confirms zero remaining `*_key` user attribute references in `src/`.
- **Task 6:** Registered `ai_qa.secrets.models` in `alembic/env.py`; hand-authored migration `b7d2f1a9c4e5` creates `user_secrets` (FK CASCADE, unique constraint, timestamps; `encrypted_value` as `String(1024)`) and drops the 6 legacy columns, with `downgrade()` re-adding them as `EncryptedString(512)` mirroring `e1287c77977a`. Dev-phase data-loss note included in the docstring.
- **Task 7:** Added `tests/secrets/{test_types,test_service,test_models}.py` (roundtrip + key-separation, upsert/None accessor behavior, ciphertext-at-rest leak check + plaintext metadata). Added 3 key-validation tests to `tests/unit/test_config.py` and updated the env-isolation tests to supply a valid key. Reworked `tests/test_agents/test_alice.py` to patch the accessor instead of the dropped attributes, and updated shared `tests/conftest.py` `mock_db` so `db.scalar` returns `None` (fresh user = no stored secret).
- **Task 8:** `.env.example` already documented `USER_SECRETS_ENCRYPTION_KEY` with generation instructions and a "never commit / never store in DB" note — verified, no change needed.

### File List

- `src/ai_qa/config.py` (modified)
- `src/ai_qa/db/types.py` (modified)
- `src/ai_qa/db/models.py` (modified)
- `src/ai_qa/agents/base.py` (modified)
- `src/ai_qa/agents/alice.py` (modified)
- `src/ai_qa/secrets/__init__.py` (new)
- `src/ai_qa/secrets/models.py` (new)
- `src/ai_qa/secrets/service.py` (new)
- `alembic/env.py` (modified)
- `alembic/versions/b7d2f1a9c4e5_add_user_secrets_drop_inline_keys.py` (new)
- `tests/secrets/__init__.py` (new)
- `tests/secrets/conftest.py` (new)
- `tests/secrets/test_types.py` (new)
- `tests/secrets/test_service.py` (new)
- `tests/secrets/test_models.py` (new)
- `tests/unit/test_config.py` (modified)
- `tests/test_agents/test_alice.py` (modified)
- `tests/conftest.py` (modified)

## Change Log

| Date       | Version | Description                                                                 |
| ---------- | ------- | --------------------------------------------------------------------------- |
| 2026-06-07 | 0.1     | Implemented encrypted per-user secret storage foundation (Tasks 1–9). Added `user_secrets` table + accessor, fail-fast key validation, migrated consumers, retired inline `*_key` columns. Status → review. |
| 2026-06-07 | 0.2     | Code review: recorded `tests/secrets/conftest.py` in the File List (shared SQLite scaffold + `make_user` factory). Review findings appended; 7 items deferred to Story 9.7 / future hardening. |
