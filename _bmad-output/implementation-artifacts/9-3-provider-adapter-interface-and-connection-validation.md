---
baseline_commit: ce65495
---

# Story 9.3: Provider Adapter Interface and Connection Validation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a project user,
I want Alice to validate my selected AI provider connection,
so that I know the provider credentials and endpoint work before running the pipeline.

## Acceptance Criteria

**AC1 — Adapter `validate_connection` + normalized result**

**Given** a supported provider is selected
**When** Alice validates the connection
**Then** the provider adapter calls `validate_connection(credentials, base_url)`
**And** the result is normalized into success/failure status, provider name, and actionable non-secret error guidance.

**AC2 — Failure produces a secret-free, stack-trace-free recovery message**

**Given** validation fails due to invalid credentials, unreachable endpoint, or provider error
**When** Alice presents the result
**Then** the user sees a recovery message without stack traces, raw provider responses, or secrets.

**AC3 — Config-owned base URLs, secret-storage-owned credentials**

**Given** provider base URLs are needed
**When** adapter configuration is loaded
**Then** deployment-level base URLs come from system environment/configuration
**And** user-specific secrets come only from encrypted per-user secret storage.

## Tasks / Subtasks

- [x] **Task 1: Create the provider adapter interface package** (AC: 1, 3)
  - [x] Create `src/ai_qa/ai_connection/providers/__init__.py` (package marker + public exports). Architecture designates `ai_connection/providers/` as the home for provider validation/model-discovery adapters (see References).
  - [x] Create `src/ai_qa/ai_connection/providers/base.py` defining the normalized result models and the adapter contract:
    - `ConnectionResult` — a Pydantic `BaseModel` (mirror the repo convention: `model_config = ConfigDict(validate_assignment=True)`). Fields, **all non-secret**: `success: bool`, `provider: str` (canonical provider id), `provider_name: str` (human label), `status: Literal["success", "failed"]`, `message: str` (actionable, secret-free, stack-trace-free guidance), `error_category: Literal["auth", "unreachable", "provider_error", "config", "none"] = "none"`. **No** field may carry an api_key, raw provider response body, or stack trace.
    - `DiscoveredModel` — define it now because the interface signature references it (architecture lists its fields). Pydantic `BaseModel`: `id: str`, `display_name: str`, `provider: str`, plus optionals defaulting to `None`: `capability_hints: list[str] | None = None`, `context_window: int | None = None`, `supports_tools: bool | None = None`, `supports_vision: bool | None = None`, `cost_tier: str | None = None`, `latency_tier: str | None = None`. Add a docstring noting Story 9.4 owns its population/normalization.
    - `ProviderAdapter` — an `abc.ABC` (or `typing.Protocol`; prefer ABC so a shared OpenAI-compatible base can hold reused logic). Define `provider_id: ClassVar[str]` and `provider_name: ClassVar[str]`, an **abstract** `async def validate_connection(self, credentials: Mapping[str, str], base_url: str) -> ConnectionResult`, and a **concrete** `async def list_models(self, credentials: Mapping[str, str], base_url: str) -> list[DiscoveredModel]` that raises `NotImplementedError("list_models is implemented in Story 9.4")`. This keeps every 9.3 adapter instantiable (validate_connection is real) while giving 9.4 a single clear extension point.
  - [x] **Scope guard:** Do NOT implement real `list_models` logic, model normalization, scoring, or assignment here — those are Stories 9.4/9.5. Do NOT persist any configuration here — that is Story 9.7. This story delivers the *interface* + a working `validate_connection` for every supported provider, plus wiring Alice's connection-test step to it.

- [x] **Task 2: Implement concrete adapters with real connection checks** (AC: 1, 2, 3)
  - [x] Add `src/ai_qa/ai_connection/providers/openai_compatible.py` with `OpenAICompatibleAdapter(ProviderAdapter)`. `validate_connection` performs a lightweight, real reachability+auth probe against the configured `base_url` using the same endpoint-probing approach already proven in `alice._fetch_available_models` (`GET {base_url}/v1/models`, fallbacks `/models`, `/api/tags`, `/api/models`, `Authorization: Bearer <api_key>`). A `200` → `success`; `401`/`403` → `error_category="auth"`; connection/timeout error → `error_category="unreachable"`; other non-2xx → `error_category="provider_error"`. Use `httpx.AsyncClient(timeout=10.0, verify=verify_ssl, follow_redirects=True)`. **`verify_ssl` must be `False` only for the on-premises provider** (mirrors the existing `verify_ssl = provider_id != "on-premises"` rule — self-signed certs are common on-prem).
  - [x] On-premises and OpenAI/Gemini-ChatGPT are OpenAI-compatible — reuse `OpenAICompatibleAdapter` (parameterized by `provider_id`/`provider_name`). For **on-premises**, additionally fail fast with `error_category="config"` and an actionable message when `base_url` is empty or does not start with `http` (preserves the current `_test_connection` on-prem guard).
  - [x] Claude (Anthropic) and Browser Use Cloud: the current code returns *static* model lists for these without a live call. For 9.3, give each a `validate_connection` that performs a real auth/reachability check appropriate to the provider (Anthropic: a minimal authenticated request to `{base_url}` models/health route with `x-api-key`/`anthropic-version` headers; Browser Use Cloud: an authenticated request to its API base). If a provider has no cheap validation endpoint, do a HEAD/GET against the base URL that distinguishes auth (401/403) from unreachable — **do not** fabricate success. Keep provider-specific header/auth details in the adapter, never in Alice.
  - [x] **Format floor:** before any network call, reject `api_key` that is empty after `.strip()` or `< 8` chars with `error_category="auth"` and a non-secret message (mirrors `alice._test_connection`'s `len(api_key) < 8` guard and 9.2's `validate_secret_format`). Always operate on the stripped key.
  - [x] **Message hygiene (AC2):** every `message` must be human-friendly and contain NO api_key, NO raw `response.text`/JSON body, NO exception/stack trace. Catch provider/httpx exceptions, log details at `debug`/`warning` (the logger may include the exception, never the key), and return a curated message such as `"Authentication failed — the API key was rejected by {provider_name}. Replace the key and try again."` / `"Could not reach {provider_name} at the configured endpoint. Check the deployment base URL and network access."`.

- [x] **Task 3: Provider registry / factory (config-owned base URL resolution)** (AC: 1, 3)
  - [x] In `src/ai_qa/ai_connection/providers/__init__.py` (or a `registry.py`), add a mapping from canonical provider id → (adapter instance/factory, settings attribute name for the base URL). Use the exact `AppSettings` attribute names already in `config.py`: `claude_api_base_url`, `openai_api_base_url`, `gemini_api_base_url`, `on_premises_api_base_url`, `browser_use_cloud_url`. Provider ids must match `alice.PROVIDER_OPTIONS` ids: `claude`, `gemini-chatgpt`, `on-premises`, `browser-use-cloud` (note: there is no separate `openai` id in Alice — OpenAI is grouped under `gemini-chatgpt`; reuse that mapping and do NOT invent a new provider id).
  - [x] Add `get_provider_adapter(provider_id: str) -> ProviderAdapter` (raise a clear, secret-free error for unknown ids) and `resolve_base_url(settings: AppSettings, provider_id: str) -> str` that reads the base URL **only** from `AppSettings` (env/config-owned). The adapter layer must NEVER read `user_secrets`, `.env` user keys, or decrypt anything — credentials are always passed in by the caller (Alice), satisfying AC3's separation. Base URLs come from config; api keys come from the caller (which sources them from per-user secret storage via the 9.1 accessor).
  - [x] Keep the registry pure (no DB, no secrets service import). Allowed deps for `ai_connection`: `config`, `secrets` (types/constants only — but for 9.3 you do not even need secrets here since keys are passed in), `langchain`, `httpx` (architecture module-boundary table). Do NOT import `agents`, `mcp`, or `browser` from here (dependency direction).

- [x] **Task 4: Wire Alice's connection-test step to the adapter** (AC: 1, 2)
  - [x] In `src/ai_qa/agents/alice.py`, refactor `_test_connection` to delegate to the adapter: resolve `provider_id` and the config-owned `endpoint` (already done via `_get_provider_info` → `getattr(self._settings, endpoint_setting)`), build credentials `{"api_key": ...}` from the user-supplied/stored value, call `await get_provider_adapter(provider_id).validate_connection(credentials, endpoint)`, and return/propagate the `ConnectionResult`. Preserve the current public behavior: `process()` still raises `PipelineError` on failure and continues to model generation on success.
  - [x] Replace the generic failure text in `process()` with the adapter's actionable `ConnectionResult.message` so the user gets provider-specific recovery guidance (AC2). Route it through the existing `_send_connection_test_status("failed", <message>)` path; keep the `message_type="error"` mapping. Ensure the message shown to the user is the curated adapter message, never an exception string.
  - [x] **Do NOT** change the model-discovery path in this story. `_fetch_available_models` / `_generate_configuration` stay as-is (Story 9.4 migrates discovery into `list_models`). The only behavioral change is that the *connection test* now runs through the adapter and yields a normalized, actionable result. Confirm the success path still reaches `_generate_configuration` unchanged.
  - [x] Read `alice.process()` (~lines 281–369), `_get_provider_info` (~567–577), and `_test_connection` (~578–607) fully before editing. Confirm a `provider_info["endpoint"]` is populated from settings (it is, via `_get_provider_info`) so no base URL ever comes from user input or secrets.

- [x] **Task 5: Tests** (AC: 1, 2, 3)
  - [x] New `tests/ai_connection/__init__.py` (add if sibling test dirs use package markers) and `tests/ai_connection/test_providers.py`.
  - [x] **AC1 tests:** for each adapter, a `200` model-list response → `ConnectionResult(success=True, status="success", provider/provider_name set, error_category="none")`. Mock httpx with the established repo pattern `@patch("httpx.AsyncClient.get")` (see `tests/test_agents/test_alice.py::TestConnectionAndFetch`) — there is no `respx` dependency; do not add one. Build a `MagicMock`/`AsyncMock` response with `.status_code` and `.json()`.
  - [x] **AC2 tests (the core guardrail):** simulate (a) `401` → `error_category="auth"`, (b) `httpx.ConnectError`/timeout → `error_category="unreachable"`, (c) `500` → `error_category="provider_error"`. For every failure path assert: `success is False`, `status == "failed"`, and a **leak assertion** that the api_key string and any raw body text do NOT appear in `result.message` (and that `message` contains no `Traceback`/exception class name). Pass a known sentinel api_key (e.g. `"sk-secret-LEAK-CANARY-123"`) and assert it is absent from `result.message`.
  - [x] **AC2 format-floor tests:** empty / whitespace / `< 8` char key → `success=False`, `error_category="auth"`, no network call made (assert the httpx mock was not awaited).
  - [x] **AC3 tests:** `resolve_base_url(settings, provider_id)` returns the value from the matching `AppSettings` attribute; assert the adapter receives that base URL and that the adapter code path never reads `user_secrets`/decrypts (structurally: the adapter signature only takes `credentials, base_url`). On-premises with empty/non-http base URL → `error_category="config"`, no network call.
  - [x] **`list_models` stub test:** calling `adapter.list_models(...)` raises `NotImplementedError` (proves the 9.4 extension point exists and is intentionally unimplemented).
  - [x] **Alice integration:** update/extend `tests/test_agents/test_alice.py` so the connection-test path exercises the adapter. Patch `get_provider_adapter` (or the adapter's `validate_connection`) to return a `ConnectionResult`; assert `process()` succeeds when `success=True` and raises `PipelineError` carrying the adapter's actionable `message` when `success=False`. Keep existing `_fetch_available_models` tests green (discovery path unchanged). Mocks must mirror the new call shape (project rule #15).
  - [x] Follow test rules: in-memory SQLite + `StaticPool` + `engine.dispose()` only where a DB is actually needed (adapter tests need none); `Generator[...]`-typed yield fixtures (#3); imports at top (#9, E402); specific exceptions with `match=` (#10, e.g. `pytest.raises(NotImplementedError, match=...)`), never bare `Exception` (#10/B017).

- [x] **Task 6: Verification (project-context Verification Workflow §1 + Coding Rules)**
  - [x] No DB schema change in this story — do NOT create an Alembic migration and skip `uv run alembic upgrade head`. Confirm no model/column change before skipping.
  - [x] `uv run ruff check .` and `uv run ruff format --check .` (run `uv run ruff format .` if needed, then re-check).
  - [x] `uv run mypy src` — clean. Watch for: `Mapping`/`Literal`/`ClassVar` imports from `typing`; `ConfigDict` from pydantic; no un-narrowed `httpx` response typing.
  - [x] Run `uv run pytest` in a fresh terminal (close it after). Confirm the new `tests/ai_connection/test_providers.py` and the updated `tests/test_agents/test_alice.py` pass and nothing regressed.
  - [x] If any backend source under `src/` changed, follow project-context Verification Workflow §1 (fresh terminal). If failures occur, do NOT guess — auto-launch a `bmad-investigate` sub-agent per project-context.
  - [x] Check Markdown diagnostics for this story file and any edited `.md` (rules #7, #8).

## Dev Notes

### Why this story exists / scope boundary

Epic 9 moves the system off static provider→model assumptions toward **runtime, per-user, validated** provider configuration. Stories 9.1/9.2 built the secret **storage** and a **status/replacement API**. This story (9.3) introduces the **provider adapter interface** — the architecture's designated seam in `ai_connection/providers/` — and implements a real `validate_connection(credentials, base_url)` for every supported provider, then wires Alice's connection-test step to it so users get a normalized, actionable, secret-free result before the pipeline runs.

**This story = the interface + connection validation only.** Explicitly OUT of scope (later Epic 9 stories — do NOT implement here):

- Real `list_models` / model normalization into `DiscoveredModel` → **Story 9.4** (this story defines the signature + a `NotImplementedError` stub).
- Model scoring / per-agent assignment review → **Story 9.5**.
- Runtime (thread-owner) secret resolution for agent runs → **Story 9.6**.
- Saved provider config + rotation-applies-to-future-runs persistence → **Story 9.7**.

The architecture's implementation sequence confirms this ordering: "8. Provider adapter interfaces for validation and dynamic model discovery" precede "9. Alice end-to-end". `validate_connection` is the 9.3 slice; `list_models` is 9.4.

### Current state of relevant code (READ before coding)

- **`src/ai_qa/ai_connection/`** already exists with `client.py` (`LLMClient` wrapping LangChain `ChatOpenAI`) and `config.py` (`LLMConfig`). There is **no** `providers/` subpackage yet — you are creating it. The `verify_ssl = self._config.provider != "on-premises"` line in `client.py` is the canonical SSL rule to mirror in the adapter.
- **`src/ai_qa/agents/alice.py`**:
  - `PROVIDER_OPTIONS` (lines ~48–115) defines provider ids and `endpoint_setting` → `AppSettings` attribute: `browser-use-cloud`→`browser_use_cloud_url`, `claude`→`claude_api_base_url`, `gemini-chatgpt`→`openai_api_base_url`, `on-premises`→`on_premises_api_base_url`. **There is no standalone `openai` provider id** — OpenAI is folded into `gemini-chatgpt`. Match these ids exactly.
  - `_get_provider_info(provider_id)` (~567–577) copies the option and sets `info["endpoint"] = getattr(self._settings, endpoint_setting, "")` — this is where the **config-owned base URL** is resolved (AC3 already honored for endpoint; keep it that way).
  - `_test_connection(provider_info, credentials)` (~578–607): currently returns `bool`. On-prem guard: empty/non-`http` endpoint → `False`. Format floor: `len(api_key) < 8` → `False`. Then calls `_fetch_available_models(...)` and returns `True` only if models came back. **Refactor this to delegate to the adapter** and return/propagate a `ConnectionResult`; keep the on-prem + format-floor semantics inside the adapter.
  - `_fetch_available_models(provider_id, server_url, api_key)` (~999–1080): returns static lists for `claude`/`gemini-chatgpt`/`browser-use-cloud`; for on-prem probes `/v1/models`, `/models`, `/api/tags`, `/api/models` with `Authorization: Bearer`. This is the proven probing logic to lift into `OpenAICompatibleAdapter.validate_connection` — but **leave `_fetch_available_models` itself untouched** (9.4 migrates discovery). Only the connection-test path changes in 9.3.
  - `process()` (~281–369): on connection failure sends `_send_connection_test_status("failed", ...)` and raises `PipelineError(...)`. After success it persists the api_key via `set_user_secret(...)` + `db.commit()` (from 9.1) and calls `_generate_configuration`. Preserve all of this; only swap the test mechanism + use the adapter's actionable message.
- **`src/ai_qa/config.py`** owns the base URLs (env/config): `claude_api_base_url` (`https://api.anthropic.com`), `openai_api_base_url` (`https://api.openai.com`), `gemini_api_base_url` (`https://generativelanguage.googleapis.com`), `on_premises_api_base_url` (`""` default), `browser_use_cloud_url` (`https://api.browser-use.com/api/v3`). Read base URLs only from here (AC3).
- **`src/ai_qa/secrets/`** (9.1/9.2): `get_user_secret`, `PROVIDER_SECRET_TYPE_MAP`, `CANONICAL_SECRET_TYPES`, `resolve_secret_type`. Alice already sources the user key from here / from `credentials` input. The adapter does **not** call into secrets — it takes `credentials` as a parameter (clean separation, AC3).
- **`src/ai_qa/models.py`**: repo convention for Pydantic models — `BaseModel` + `model_config = ConfigDict(validate_assignment=True)`, `Literal[...]` for enums (see `ProviderConfig.test_result: Literal["success", "failed"]`). Mirror this for `ConnectionResult`/`DiscoveredModel`.
- **`src/ai_qa/exceptions.py`**: `LLMError` → `LLMTimeoutError`, `LLMAuthenticationError`, `LLMProviderError` already exist. The adapter **returns a normalized `ConnectionResult`** rather than raising for expected validation failures (so Alice can present a friendly message). Reserve exceptions for truly unexpected internal errors. Do not leak these exception strings into `ConnectionResult.message`.

### What this story changes vs. preserves

- **New:** `src/ai_qa/ai_connection/providers/__init__.py`, `.../base.py` (`ConnectionResult`, `DiscoveredModel`, `ProviderAdapter`), `.../openai_compatible.py` (+ Claude/Browser-Use adapters — can live in `openai_compatible.py` or sibling modules), registry/factory (`get_provider_adapter`, `resolve_base_url`). New `tests/ai_connection/test_providers.py`.
- **Changes:** `src/ai_qa/agents/alice.py` — `_test_connection` delegates to the adapter and yields a `ConnectionResult`; `process()` surfaces the actionable `message`. Update `tests/test_agents/test_alice.py` mocks to the new call shape.
- **Preserve:** `_fetch_available_models` and the entire model-discovery/assignment path (9.4+ territory); `process()`'s secret-persist + `_generate_configuration` flow; `PROVIDER_OPTIONS` ids and `endpoint_setting` mapping; `LLMClient`/`LLMConfig`; all of `secrets/`, the DB schema, and auth. No new dependency, no migration.

### Source tree components to touch

```text
src/ai_qa/ai_connection/providers/__init__.py        # NEW: package + registry (get_provider_adapter, resolve_base_url)
src/ai_qa/ai_connection/providers/base.py            # NEW: ConnectionResult, DiscoveredModel, ProviderAdapter ABC
src/ai_qa/ai_connection/providers/openai_compatible.py # NEW: OpenAICompatibleAdapter (on-prem, gemini-chatgpt) + Claude/Browser-Use adapters
src/ai_qa/agents/alice.py                            # UPDATE: _test_connection delegates to adapter; process() uses ConnectionResult.message
tests/ai_connection/__init__.py                      # NEW (if sibling test dirs use package markers)
tests/ai_connection/test_providers.py                # NEW: AC1/AC2/AC3 + leak + NotImplementedError tests
tests/test_agents/test_alice.py                      # UPDATE: connection-test path via adapter; keep discovery tests green
```

### Provider adapter contract (target)

```text
ConnectionResult(success, provider, provider_name, status, message, error_category)   # all non-secret
DiscoveredModel(id, display_name, provider, capability_hints?, context_window?,
                supports_tools?, supports_vision?, cost_tier?, latency_tier?)          # 9.4 populates
ProviderAdapter.validate_connection(credentials, base_url) -> ConnectionResult         # 9.3 implements
ProviderAdapter.list_models(credentials, base_url) -> list[DiscoveredModel]            # raises NotImplementedError (9.4)
get_provider_adapter(provider_id) -> ProviderAdapter
resolve_base_url(settings, provider_id) -> str   # reads AppSettings only
```

- `error_category` values: `"none"` (success), `"auth"` (bad/short/rejected key — 401/403), `"unreachable"` (connect/timeout/DNS), `"provider_error"` (other non-2xx / malformed response), `"config"` (missing/invalid base URL, e.g. empty on-prem URL).
- `message` is the **only** user-facing text and must be curated, actionable, secret-free, and stack-trace-free (AC2).

### Testing standards summary

- Mock httpx with `@patch("httpx.AsyncClient.get")` (and `.post`/`.head` as needed) — the established pattern in `tests/test_agents/test_alice.py::TestConnectionAndFetch` and `tests/pipelines/test_content_parser.py`. **No `respx`/`pytest-httpx` dependency exists — do not add one.**
- Adapter tests need no DB. Where a DB is unavoidable (Alice integration), reuse the in-memory SQLite + `StaticPool` scaffold, `cast(list[Table], [...])` in `create_all` (rule #20), `cast(FastAPI, client.app)` if touching app (rule #19), and `engine.dispose()` teardown (rule #1).
- The **leak assertion** (sentinel api_key absent from `result.message`/`response.text`, plus no `Traceback`/exception-class text) is the primary AC2 guardrail — include one per failure path.
- `Generator[...]`-typed yield fixtures (#3); top-level imports (#9, E402); specific exceptions with `match=` (#10); never bare `pytest.raises(Exception)` (#10/B017).

### Project Structure Notes

- Module boundaries (architecture module table): `ai_connection` may depend on `config`, `secrets`, `langchain` and must NOT depend on `mcp`, `browser`, or `agents`. The new `providers/` package therefore imports only `config` (for the base-URL resolver type) + `httpx` + pydantic — and is consumed BY `agents/alice.py`, not the reverse. Keep the import direction clean: `alice.py` imports from `ai_connection.providers`, never the other way.
- Naming: snake_case locals/functions, PascalCase models/classes; local httpx client variables like `async_client`, not aliased CamelCase (rule #5/#11). SSL flag `verify_ssl` (snake_case).
- Forward refs: if `ConnectionResult`/`DiscoveredModel` reference each other or `AppSettings`, prefer concrete imports here (no cross-module ORM cycle risk — these are plain Pydantic models, not SQLAlchemy). Rule #4 (TYPE_CHECKING) applies only to SQLAlchemy string forward refs, which this story has none of.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 9.3: Provider Adapter Interface and Connection Validation] — user story + acceptance criteria (validate_connection, normalized result, secret-free recovery, config-owned base URLs vs per-user secret credentials).
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 9] — FRs covered incl. FR15 (dynamic provider validation/model discovery), FR15a, FR57 (no secrets in API/WebSocket responses).
- [Source: _bmad-output/planning-artifacts/architecture.md#Provider Model Discovery Contract] — `validate_connection(credentials, base_url) -> ConnectionResult`; `list_models(credentials, base_url) -> list[DiscoveredModel]`; `DiscoveredModel` field list; OpenAI-compatible/on-prem use configured base URL + model listing endpoint.
- [Source: _bmad-output/planning-artifacts/architecture.md#Alice Provider Configuration and Dynamic Model Discovery] — runtime model-selection pipeline; "If connection validation fails ... Alice must not create a successful model assignment review and must not persist agent model configuration."
- [Source: _bmad-output/planning-artifacts/architecture.md#Configuration Ownership Boundary] — env-owned base URLs (Claude/Gemini/OpenAI/On-Premises/Browser-Use) vs per-user-stored secrets (AC3).
- [Source: _bmad-output/planning-artifacts/architecture.md#Source Tree / module table] — `src/ai_qa/ai_connection/providers/` is the designated home; `ai_connection` deps = config, secrets, langchain; must not import mcp/browser/agents.
- [Source: _bmad-output/planning-artifacts/architecture.md#Decision Impact Analysis] — implementation sequence places provider adapter interfaces (validation + discovery) before Alice end-to-end.
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md] — "Human-friendly error message, suggested action, no stack traces"; Step 1 "Alice confirms connection"; errors are "guided recovery, not dead ends" (AC2 tone).
- [Source: src/ai_qa/agents/alice.py#_test_connection] — current bool connection test (on-prem guard + `<8` format floor + model-fetch) to refactor onto the adapter.
- [Source: src/ai_qa/agents/alice.py#_fetch_available_models] — proven endpoint-probing logic (`/v1/models` + fallbacks, `Authorization: Bearer`, `verify_ssl` per on-prem) to lift into the OpenAI-compatible adapter; leave the original untouched (9.4 migrates discovery).
- [Source: src/ai_qa/agents/alice.py#PROVIDER_OPTIONS / _get_provider_info] — provider ids and `endpoint_setting`→`AppSettings` mapping; config-owned endpoint resolution.
- [Source: src/ai_qa/ai_connection/client.py] — `verify_ssl = provider != "on-premises"` SSL rule + httpx usage pattern to mirror.
- [Source: src/ai_qa/config.py#AppSettings] — base URL fields: `claude_api_base_url`, `openai_api_base_url`, `gemini_api_base_url`, `on_premises_api_base_url`, `browser_use_cloud_url`.
- [Source: src/ai_qa/models.py] — Pydantic convention (`ConfigDict(validate_assignment=True)`, `Literal[...]`) for `ConnectionResult`/`DiscoveredModel`.
- [Source: src/ai_qa/exceptions.py] — existing `LLMError`/`LLMAuthenticationError`/`LLMProviderError`; adapter returns normalized results, reserving exceptions for unexpected internals.
- [Source: src/ai_qa/secrets/__init__.py] — canonical secret types / `PROVIDER_SECRET_TYPE_MAP` (Alice maps provider→key; adapter receives the key as a param, never reads secrets).
- [Source: tests/test_agents/test_alice.py#TestConnectionAndFetch] — `@patch("httpx.AsyncClient.get")` mock pattern + response shape to reuse for adapter tests.
- [Source: project-context.md] — testing/coding rules (#1 SQLite dispose, #3 Generator typing, #5 snake_case locals, #9 import order, #10 specific exceptions, #11 naming, #15 mock sync, #19/#20/#21 API test scaffolds; Verification Workflow §1; Python invocation via `uv run`).

### Previous Story Intelligence (Stories 9.1, 9.2)

- **Reuse, don't reinvent:** 9.1 built `get_user_secret`/`set_user_secret` + canonical `secret_type` constants; 9.2 added `validate_secret_format` (`>=8` chars, non-empty after strip) and `list_secret_status`. 9.3's adapter format-floor mirrors that same `>=8` rule — keep it consistent, but **do not** import the API-layer validator into `ai_connection` (avoid an `api`→`ai_connection` coupling); inline the tiny check or import the pure helper from `secrets.service` if it is dependency-clean.
- **Secret hygiene is the recurring gate:** every Epic 9 review hammered leak assertions (plaintext key must not appear in any output). 9.3's `ConnectionResult.message` is the new surface — assert the sentinel key never lands there. 9.1 deferred "corrupt/wrong-key ciphertext returned as plaintext" — not in scope here, but be aware the api_key passed in may be a stored value; never echo it.
- **Strip asymmetry:** 9.1/9.2 noted alice stored the unstripped key while validating the stripped one. In 9.3, always validate the **stripped** key in the adapter; do not re-open the alice persist path (it already calls `set_user_secret`).
- **Scope discipline pattern:** 9.1 and 9.2 each left a clearly-commented extension point for the next story and refused to implement ahead. Do the same: `list_models` raises `NotImplementedError("... Story 9.4")`, and a comment marks where 9.4 plugs discovery into the adapter.
- **Test scaffolds:** mocks must mirror real call shapes (rule #15) — when `_test_connection` changes from returning `bool` to producing a `ConnectionResult`, update every test/mocked path. `tests/conftest.py` `mock_db.scalar` returns `None` (no stored secret) — useful for the missing-key path.

### Git Intelligence

- HEAD `ce65495 story 9-2 code and test OK` (baseline). Recent: `c3f6783 story 9-1 ...`, `9fe8a5d done epic 7 and 8`. The 9.1 storage + 9.2 status/replacement API are merged and stable; `ai_connection/` (LLMClient) and `agents/alice.py` are current. Build the adapter on top without touching secrets storage, auth/RBAC, or the DB.
- Commit convention: per-story commits like `story 9-3 code and test OK`. One migration-free story; expect a single backend+test commit after `uv run pytest` is green.

### Latest Tech Information

- **No new dependencies.** Uses already-pinned `httpx` (async client, `verify`, `follow_redirects`, `timeout`), `pydantic`/`pydantic-settings>=2.4` (BaseModel + `ConfigDict`), `langchain`/`langchain-openai` (only if an adapter chooses a langchain-based probe — prefer a direct httpx call for a lightweight validation). Python 3.14+, `uv`, `ruff` (target py314, line-length 100), `mypy strict`.
- httpx async error taxonomy to map in `validate_connection`: `httpx.ConnectError`/`httpx.ConnectTimeout`/`httpx.ReadTimeout` → `unreachable`; a `Response` with `401/403` → `auth`; `>=500` or unexpected `4xx`/non-JSON → `provider_error`. Catch `httpx.HTTPError` broadly for the network family; never let the raw exception text reach `ConnectionResult.message`.
- OpenAI-compatible model listing remains `GET {base_url}/v1/models` (Bearer auth). Anthropic uses `x-api-key` + `anthropic-version` headers (no Bearer); keep that provider-specific detail inside the Claude adapter, not in shared code.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (Kiro dev-story workflow)

### Debug Log References

- `uv run ruff check .` → All checks passed.
- `uv run ruff format --check .` → all files formatted.
- `uv run mypy src` → Success: no issues found in 77 source files.
- `uv run pytest` → 769 passed, 2 skipped; total coverage 82.15% (≥80% gate).
- App boot smoke test (`import ai_qa.api` + adapter resolution for all 4 provider ids) → OK.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.
- Created the `ai_connection/providers/` package (the architecture's designated validation/discovery seam):
  - `base.py` — `ConnectionResult` and `DiscoveredModel` Pydantic models (all non-secret fields, `ConfigDict(validate_assignment=True)`) and the `ProviderAdapter` ABC with an abstract `validate_connection` and a concrete `list_models` stub that raises `NotImplementedError("list_models is implemented in Story 9.4")`.
  - `openai_compatible.py` — `OpenAICompatibleAdapter` performing a real httpx reachability+auth probe (`GET {base_url}/v1/models` + `/models`, `/api/tags`, `/api/models` fallbacks, Bearer auth, `timeout=10.0`, `verify_ssl=False` only for on-prem). Subclasses: `GeminiChatGPTAdapter`, `OnPremisesAdapter` (adds empty/non-http base-url config guard), `AnthropicAdapter` (x-api-key + anthropic-version headers, `/v1/models`), `BrowserUseAdapter` (authenticated reachability probe against the API base).
  - `__init__.py` — pure registry/factory `get_provider_adapter()` + `resolve_base_url()` (reads base URLs ONLY from `AppSettings`; never reads secrets). Provider ids match `alice.PROVIDER_OPTIONS` exactly (`gemini-chatgpt` maps to `openai_api_base_url`; no standalone `openai` id).
- Adapter status taxonomy: `200`→success/`none`; `401`/`403`→`auth`; connect/timeout (`httpx.HTTPError`)→`unreachable`; other non-2xx→`provider_error`; empty/non-http on-prem URL→`config`; sub-8-char/empty key→`auth` (format floor, no network call).
- Message hygiene (AC2): every `ConnectionResult.message` is curated and secret-free. httpx/provider exceptions are logged at warning level by exception *type* only — never the api_key, raw response body, or traceback. Verified by leak-canary assertions in the tests.
- Wired Alice: `_test_connection` now delegates to `get_provider_adapter(provider_id).validate_connection({"api_key": ...}, endpoint)` and returns a `ConnectionResult`; `process()` surfaces the adapter's actionable `message` via `_send_connection_test_status("failed", message)` and raises `PipelineError(message)`. The model-discovery path (`_fetch_available_models`/`_generate_configuration`) is unchanged (Story 9.4 territory).
- Scope discipline: no `list_models` logic, no model normalization/scoring/assignment, no config persistence, no DB/migration, no new dependency (reused already-pinned httpx + pydantic). `list_models` left as the single intentional Story 9.4 extension point.
- Tests: new `tests/ai_connection/test_providers.py` covers AC1 (per-adapter success), AC2 (401/timeout/500 + leak guardrails + format floor no-network), AC3 (config-owned base-url resolution + on-prem config guard), provider-specific header wiring, and the `list_models` NotImplementedError stub. Updated `tests/test_agents/test_alice.py` connection-test path to the new `ConnectionResult` call shape (project rule #15) while keeping the `_fetch_available_models` discovery tests green.

### File List

- src/ai_qa/ai_connection/providers/__init__.py (new)
- src/ai_qa/ai_connection/providers/base.py (new)
- src/ai_qa/ai_connection/providers/openai_compatible.py (new)
- src/ai_qa/agents/alice.py (modified)
- tests/ai_connection/__init__.py (new)
- tests/ai_connection/test_providers.py (new)
- tests/test_agents/test_alice.py (modified)

## Change Log

| Date       | Version | Description                                                           |
| ---------- | ------- | --------------------------------------------------------------------- |
| 2026-06-07 | 0.1     | Story drafted by create-story context engine. Status → ready-for-dev. |
| 2026-06-07 | 1.0     | Implemented provider adapter interface + per-provider `validate_connection`, wired Alice's connection-test step, added tests. All checks (ruff/mypy/pytest) green. Status → review. |

### Review Findings

Code review (2026-06-07) — adversarial 3-layer review (Blind Hunter, Edge Case Hunter, Acceptance Auditor). ACs AC1/AC2/AC3 confirmed met by the Acceptance Auditor; findings below are robustness/security/maintainability gaps.

**Patch (incl. resolved decisions) — all applied 2026-06-07:**

- [x] [Review][Patch] Validate response body, not just HTTP 200 [src/ai_qa/ai_connection/providers/openai_compatible.py:_probe] — (resolved decision, option 1) a `200` must additionally parse as JSON with a recognizable shape before success; otherwise treat as `provider_error`. Prevents captive-portal / login-page / bare-root false positives.
- [x] [Review][Patch] Auth failure must not short-circuit the fallback loop [src/ai_qa/ai_connection/providers/openai_compatible.py:_probe] — (resolved decision, option 1) record 401/403 and continue probing remaining candidates; only conclude `auth` if no endpoint succeeds.
- [x] [Review][Patch] Non-`httpx.HTTPError` exceptions escape the probe loop [src/ai_qa/ai_connection/providers/openai_compatible.py:_probe] — `httpx.InvalidURL` / `httpx.CookieConflict` are NOT subclasses of `httpx.HTTPError` (verified on httpx 0.28.1), so a malformed candidate URL aborts the whole fallback loop instead of continuing.
- [x] [Review][Patch] `base_url` None/empty/non-http crashes non-on-prem adapters [src/ai_qa/ai_connection/providers/openai_compatible.py:validate_connection] — added a shared config-floor guard returning `error_category="config"` for non-string/non-http base URLs (previously only `OnPremisesAdapter` guarded this).
- [x] [Review][Patch] Non-string `api_key` raises AttributeError [src/ai_qa/ai_connection/providers/openai_compatible.py:validate_connection] — format floor now rejects non-string keys via `isinstance` before `.strip()`, returning the auth-failure message instead of crashing.
- [x] [Review][Patch] `follow_redirects=True` forwards custom auth headers cross-host [src/ai_qa/ai_connection/providers/openai_compatible.py:_probe] — validation probe now uses `follow_redirects=False`; removes the cross-host `x-api-key` exposure risk (esp. with on-prem `verify=False`).
- [x] [Review][Patch] `resolve_base_url` is dead in production [src/ai_qa/agents/alice.py:_get_provider_info] — Alice now resolves the config-owned endpoint via `resolve_base_url`, making the registry the single source of truth (removes the parallel-map drift risk).

- [ ] [Review][Patch] Non-`httpx.HTTPError` exceptions escape the probe loop [src/ai_qa/ai_connection/providers/openai_compatible.py:_probe] — `httpx.InvalidURL` / `httpx.CookieConflict` are NOT subclasses of `httpx.HTTPError` (verified on httpx 0.28.1), so a malformed candidate URL aborts the whole fallback loop instead of continuing.
- [ ] [Review][Patch] `base_url` None/empty/non-http crashes non-on-prem adapters [src/ai_qa/ai_connection/providers/openai_compatible.py:_candidate_endpoints] — `base_url.rstrip("/")` runs before any guard; only `OnPremisesAdapter` validates base_url. A `None` base URL raises `AttributeError`. Add a shared guard returning `error_category="config"`.
- [ ] [Review][Patch] Non-string `api_key` raises AttributeError [src/ai_qa/ai_connection/providers/openai_compatible.py:validate_connection] — `(credentials.get("api_key") or "").strip()` crashes when `api_key` is a non-string truthy value (e.g. int). Coerce/guard to the auth-failure message instead of crashing.
- [ ] [Review][Patch] `follow_redirects=True` forwards custom auth headers cross-host [src/ai_qa/ai_connection/providers/openai_compatible.py:_probe] — httpx strips standard `Authorization` on cross-host redirects but NOT custom headers like Anthropic `x-api-key`; combined with on-prem `verify=False` this risks credential/transport exposure. Disable redirect-following for the validation probe.
- [ ] [Review][Patch] `resolve_base_url` is dead in production [src/ai_qa/ai_connection/providers/__init__.py:resolve_base_url] — Alice resolves the endpoint via `_get_provider_info` and never calls `resolve_base_url`, leaving two parallel provider-id→AppSettings-attribute maps that can silently drift. Route Alice's resolution through `resolve_base_url` for a single source of truth.

**Deferred:**

- [x] [Review][Defer] Sequential 4×10s endpoint probing → ~40s worst-case validation latency [src/ai_qa/ai_connection/providers/openai_compatible.py:_probe] — deferred, pre-existing sequential-probe pattern (perf, not correctness).
- [x] [Review][Defer] 8-char key floor blocks genuinely keyless on-prem/no-auth deployments [src/ai_qa/ai_connection/providers/openai_compatible.py:validate_connection] — deferred, pre-existing Alice behavior + spec-mandated floor.
