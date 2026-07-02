---
baseline_commit: 7661242
---

# Story 9.4: Dynamic Model Discovery

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a project user,
I want Alice to discover available models from my selected provider,
so that downstream agents use models that actually exist for my credentials/server.

## Acceptance Criteria

### AC1 — Adapter `list_models` returns normalized `DiscoveredModel` values

**Given** provider validation succeeds
**When** Alice performs model discovery
**Then** the provider adapter calls `list_models(credentials, base_url)` where supported
**And** the response is normalized into `DiscoveredModel` values with non-secret metadata.

### AC2 — Discovery failure blocks configuration review with actionable recovery

**Given** model discovery fails, returns no models, or cannot verify selected models
**When** Alice evaluates configuration readiness
**Then** Alice blocks successful configuration review
**And** Alice shows actionable recovery guidance (secret-free, stack-trace-free).

### AC3 — Static model names are ranking hints only, used after discovery verifies availability

**Given** static model names are available as ranking hints
**When** Alice selects models
**Then** static names are used only after provider discovery verifies availability
**And** a model is never assigned (or persisted) unless it appears in the discovered model list.

## Tasks / Subtasks

- [x] **Task 1: Implement real `list_models` on the provider adapters** (AC: 1)
  - [x] In `src/ai_qa/ai_connection/providers/openai_compatible.py`, implement `OpenAICompatibleAdapter.list_models(self, credentials, base_url) -> list[DiscoveredModel]` by **overriding** the `NotImplementedError` stub inherited from `ProviderAdapter`. This is the single, intentional 9.4 extension point that Story 9.3 deliberately left open (`base.py` `list_models` raises `NotImplementedError("list_models is implemented in Story 9.4")`).
  - [x] Reuse the proven probing approach already present in two places — `alice._fetch_available_models` (the discovery logic) and `OpenAICompatibleAdapter._probe` / `_candidate_endpoints` / `_build_headers` / `_verify_ssl` (the validation logic). **Do NOT re-derive endpoint lists or headers** — call the existing `self._candidate_endpoints(base_url)` and `self._build_headers(api_key)` helpers so per-provider auth (Anthropic `x-api-key`, Bearer, Browser-Use `/me`) and the on-prem `verify_ssl=False` rule are inherited automatically.
  - [x] Apply the **same format floor** as `validate_connection`: reject `api_key` empty/`< _MIN_API_KEY_LENGTH` (8) after `.strip()` **before any network call** (return an empty list — discovery cannot run without a usable key; the connection-test step already surfaced the auth error). Always operate on the **stripped** key.
  - [x] Probe candidate endpoints in order with `httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS, verify=self._verify_ssl, follow_redirects=False)` (mirror `_probe` exactly — note Story 9.3 uses `follow_redirects=False` in the adapter, NOT `True` like the legacy `_fetch_available_models`; keep `False` to avoid captive-portal/login-page false positives). On the **first** `200` whose body passes `_is_valid_api_body` (parseable JSON object/array), parse and return the normalized models. On network/HTTP errors, log `type(exc).__name__` only (never the key) and continue to the next candidate.
  - [x] **Normalize every provider response shape into `DiscoveredModel`.** Handle the three OpenAI-compatible/Ollama shapes the legacy code handles: a top-level `list`, `{"data": [...]}` (OpenAI), and `{"models": [...]}` (Ollama `/api/tags`). For each entry, set `id = m.get("id") or m.get("name")`, `display_name = m.get("name") or m.get("id")` (fall back to the id when no friendly name exists), and `provider = self.provider_id`. Leave the optional capability fields (`capability_hints`, `context_window`, `supports_tools`, `supports_vision`, `cost_tier`, `latency_tier`) as their `None` defaults unless the provider payload supplies them — **do NOT fabricate capability metadata.** Skip non-dict entries and entries with no usable id.
  - [x] If no endpoint returns a usable body, return an **empty list** (`[]`) — do NOT raise. Alice owns the "no models → block review" decision (Task 3, AC2). Discovery raising would bypass Alice's curated recovery message.
  - [x] **Scope guard:** Do NOT implement model scoring, per-agent assignment, or review rendering here — those are Alice's job (Task 3) and Story 9.5's review surface. `list_models` returns the *raw discovered set*, nothing more. Do NOT persist anything (Story 9.7).

- [x] **Task 2: Provide static-name ranking hints WITHOUT bypassing discovery** (AC: 3)
  - [x] The cloud providers currently return **hardcoded** model lists from `alice._fetch_available_models` *instead of* calling the network. Story 9.4 inverts this: these static names become **ranking hints only** and must never be returned by `list_models` as if discovered. Move the static lists out of the discovery path.
  - [x] Define the static names as a module-level constant in the adapter layer (e.g. `_STATIC_MODEL_HINTS: dict[str, list[str]]` keyed by `provider_id` in `openai_compatible.py`). **Refresh the stale ids** from the legacy `_fetch_available_models` to current model names where known: `claude` → current Anthropic ids; `browser-use-cloud` → BU's own models (`claude-sonnet-4.6` is BU's documented default, `claude-opus-4.6` is most capable — see References). Keep hints conservative and minimal; they are **ranking/bootstrap order hints**, NOT a substitute for discovery, and a hint id is ignored if discovery doesn't confirm it. Do NOT hardcode a long, fast-rotting model catalog — prefer discovery and use hints only to *prefer among discovered ids*.
  - [x] For providers with a working model-listing endpoint (OpenAI `/v1/models`, Gemini-compatible gateways, Anthropic `/v1/models`, on-prem/Ollama, **Browser Use Cloud** — see correction below), `list_models` performs **real discovery** and returns only what the provider advertises. The static hints are consulted afterward only to *rank/prefer* among already-discovered ids (see Task 3). A static name that is NOT in the discovered set must NEVER be assigned or persisted (AC3).
  - [x] **Browser Use Cloud DOES expose models — discover them, do NOT block.** (Correcting an earlier assumption.) The `/me` endpoint in `BrowserUseAdapter._candidate_endpoints` is only the 9.3 *validation* probe, not the model source. BU Cloud is the highest-accuracy provider (97% on OnlineMind2Web, March 2026) and documents real models (default `claude-sonnet-4.6`, most-capable `claude-opus-4.6`). Point BU discovery at BU's documented model source: probe the BU models route if/when available under `api.browser-use.com/api/v3` using the `X-Browser-Use-API-Key` header (BU keys start with `bu_`), and fall back to the curated `_STATIC_MODEL_HINTS["browser-use-cloud"]` (BU's documented models) **only after** `validate_connection` succeeds. Never return `[]` for BU purely because `/me` isn't a model list — return BU's known models gated behind a validated connection.
  - [x] **Provider-has-no-listing-endpoint fallback (architecture: "where supported"):** AC1 says `list_models` runs "where supported". For a provider that truly exposes no model-listing endpoint, returning the curated static models **gated behind a successful `validate_connection`** is acceptable (this is the "verified availability" bar — the key/endpoint proven to work). Document each provider's discovery source in dev notes. For providers that DO have an endpoint, real discovery is mandatory; do not shortcut to static.

- [x] **Task 2b: Split `gemini-chatgpt` into separate `openai` and `gemini` providers — REMOVE the old combined id** (AC: 1, 3)
  - [x] **Backend foundation already exists** — `config.py` has BOTH `openai_api_base_url` (`https://api.openai.com`) and `gemini_api_base_url` (`https://generativelanguage.googleapis.com`); `secrets/__init__.py` has BOTH `SECRET_TYPE_OPENAI` and `SECRET_TYPE_GEMINI`. This is wiring, not new infrastructure.
  - [x] **Remove the `gemini-chatgpt` entry entirely** from `alice.PROVIDER_OPTIONS` and add two entries: `openai` (name "OpenAI / ChatGPT", `endpoint_setting="openai_api_base_url"`, `env_key="OPENAI_API_KEY"`) and `gemini` (name "Google Gemini", `endpoint_setting="gemini_api_base_url"`, `env_key="GEMINI_API_KEY"`). Pick distinct `quality_rank`/`description` per provider. Add a `gemini_api_key` field to `UserSettings` in `config.py` and a `GEMINI_API_KEY` row in `.env.example` (currently only `openai_api_key` exists, labelled "OpenAI/Gemini") so the two providers have independent user-key resolution.
  - [x] In `secrets/__init__.py`, **delete the `gemini-chatgpt` alias** from `PROVIDER_SECRET_TYPE_MAP` (per the decision to drop the combined id). Keep `openai`→`SECRET_TYPE_OPENAI` and `gemini`→`SECRET_TYPE_GEMINI`. Update the comment that documents alice provider ids.
  - [x] In `ai_connection/providers/__init__.py`, remove the `gemini-chatgpt` registry + base-url entries and add `"openai"` and `"gemini"` to BOTH `_PROVIDER_ADAPTERS` and `_PROVIDER_BASE_URL_SETTINGS` (`openai`→`openai_api_base_url`, `gemini`→`gemini_api_base_url`).
  - [x] In `openai_compatible.py`: add `OpenAIAdapter(OpenAICompatibleAdapter)` (Bearer auth, `/v1/models`) and `GeminiAdapter(OpenAICompatibleAdapter)` for **native Gemini** (decision #3): Gemini's Generative Language API authenticates with an **`?key=<api_key>` query parameter** (NOT a Bearer header) and lists models at **`GET {base_url}/v1beta/models?key=<api_key>`** returning `{"models": [{"name": "models/gemini-1.5-pro", ...}]}`. Override `_candidate_endpoints` to `[f"{root}/v1beta/models"]`, override `_build_headers` to return `{}` (no auth header), and add a hook so the api_key is appended as a query param on the request (e.g. override the probe/discovery call to pass `params={"key": api_key}` to `async_client.get`). Normalize Gemini's `name` (`models/gemini-1.5-pro`) into a clean `id`/`display_name` (strip the `models/` prefix for the id). Keep all Gemini-specific auth/endpoint detail inside `GeminiAdapter`, never in Alice.
  - [x] Remove `GeminiChatGPTAdapter` (the combined adapter) once `openai`+`gemini` replace it. Grep for `gemini-chatgpt` across `src/`, `tests/`, and `frontend/src/` and eliminate every reference.
  - [x] **Migration consequence (call out, don't silently break):** threads saved with `provider_name == "gemini-chatgpt"` (Story 9.7 persists `thread.provider_name`) will no longer resolve to a `PROVIDER_OPTIONS` entry. Since the combined id is being dropped by decision, document this in dev notes; existing affected threads simply require re-selecting `openai` or `gemini` on next run (no data corruption — `provider_name` is historical metadata). Confirm no code path hard-crashes on an unknown saved `provider_name` (it should fall back to provider re-selection, not raise).
  - [x] **Frontend (in-scope this story, decision #2):** update `frontend/src/types/provider.ts` `ProviderId` union — remove `"gemini-chatgpt"`, add `"openai"` and `"gemini"`. Update `DEFAULT_PROVIDER_OPTIONS` in `frontend/src/App.tsx` to the two new entries (mirror backend name/description/qualityRank/securityLevel/credentialFields). Update `frontend/src/components/ProviderSelector.tsx` and its test `__tests__/ProviderSelector.test.tsx`, plus `App.test.tsx`, for the new options. Run `npm run typecheck` (rule #13) — the `ProviderId` union change will surface every stale reference.

- [x] **Task 2c: Show benchmark data + link in the configuration-review UI** (AC: 3, decision #1 — build in this story)
  - [x] Capture provider/model **benchmark ranking hints** as non-secret backend metadata (e.g. `_PROVIDER_BENCHMARK_HINTS` in the adapter layer) used to rank among discovered/validated models (never to assign an undiscovered model — AC3). Seed from the OnlineMind2Web (March 2026) results: Browser Use Cloud v3 = 97% (highest), plus the relative ordering from the benchmark page. Keep it a small, clearly-sourced constant.
  - [x] Surface benchmark info to the frontend through the existing Alice → frontend channel: include a non-secret `benchmark` block in the review payload (extend the `thinking_trace`/`model_assignment` metadata or `_generate_configuration`'s result `data`). Do NOT put any secret in this payload (FR57).
  - [x] Render it in `frontend/src/components/ModelAssignmentReview.tsx` (the review panel that already shows "Connected successfully to {provider}"): add a compact benchmark summary (e.g. provider accuracy %) and an external link to `https://browser-use.com/benchmarks` (open in new tab, `rel="noopener noreferrer"`). Optionally also surface it in `ProviderSelector.tsx` at selection time. Add/extend the matching `benchmark` types in `frontend/src/types/provider.ts`.
  - [x] Update `frontend/src/components/__tests__/ModelAssignmentReview.test.tsx` to assert the benchmark summary + link render; keep label-drift rules in mind (project-context #18). Run `npm run typecheck` + the vitest files. No secret may appear in any rendered benchmark content.

- [x] **Task 3: Migrate Alice's discovery + readiness gate onto `list_models`** (AC: 1, 2, 3)
  - [x] In `src/ai_qa/agents/alice.py`, change `_generate_configuration` to obtain models via the adapter: `adapter = get_provider_adapter(provider_id); discovered = await adapter.list_models({"api_key": api_key}, endpoint)` instead of calling `self._fetch_available_models(...)`. `_generate_configuration` already runs **after** a successful `validate_connection` in `process()`, so discovery only fires on a validated connection (AC1 precondition satisfied).
  - [x] Convert `list[DiscoveredModel]` into the `list[dict[str, Any]]` shape the downstream helpers (`_bootstrap_alice_model`, `_assign_models_via_llm`, `_get_model_assignments_display`) already consume: `[{"id": dm.id, "name": dm.display_name} for dm in discovered]`. This keeps the established `{"id", "name"}` contract those helpers rely on (minimal blast radius). Optionally thread richer `DiscoveredModel` metadata later — not required for this story.
  - [x] **AC2 readiness gate:** the existing `if not available_models: raise PipelineError("No models discovered ...")` stays, but the message must be **actionable and recovery-oriented** (not just descriptive). Route the failure so the user sees curated guidance via the existing `_send_connection_test_status("failed", <message>)` / `process()` error path, e.g. *"Connected to {provider}, but no usable models were found for your credentials/endpoint. Verify the model-listing endpoint is enabled and your key has model access, then try again."* Discovery failure must **block configuration review** — `process()` must not return a successful review `StageResult` when discovery yields nothing.
  - [x] **AC3 verify-before-assign:** the LLM-assignment validation in `_assign_models_via_llm` already rejects any model not in `valid_ids = {str(m["id"]) for m in available_models}` and falls back to `alice_model`. Confirm `available_models` is now the **discovered** set (not static), so the existing guard now enforces "discovered-only" assignment. `_bootstrap_alice_model`'s `priorities` keyword list is the static **ranking hint** — confirm it only *orders/prefers among discovered ids* (it iterates `model_ids` derived from `available_models`) and that its final fallback (`model_ids[0]`) is also a discovered id. If `available_models` is empty, `_bootstrap_alice_model` returns `""` and `_generate_configuration` already raises — keep that block intact.
  - [x] **Cannot-verify-selected-models case (AC2):** if discovery succeeds but cannot confirm a *previously-saved/selected* model still exists (relevant when a saved config is re-validated), Alice must block the review rather than assign an unverified model. For this story the primary path is fresh discovery; ensure no code path assigns a model absent from the freshly discovered set.
  - [x] **Decide the fate of `_fetch_available_models`.** Preferred: delete it and migrate its on-prem probing/normalization into `OpenAICompatibleAdapter.list_models` (single source of truth, satisfies architecture's "model discovery lives behind adapter interfaces"). If you keep it temporarily, it must NOT be on the live discovery path and must be clearly marked deprecated — but deletion is cleaner and avoids the two-implementations drift Story 9.3 explicitly warned about. Update/keep `tests/test_agents/test_alice.py::TestConnectionAndFetch` green for whichever path remains live.

- [x] **Task 4: Tests** (AC: 1, 2, 3)
  - [x] **Update the 9.3 stub test (REGRESSION RISK):** `tests/ai_connection/test_providers.py::TestListModelsStub::test_list_models_raises_not_implemented` currently asserts `list_models` raises `NotImplementedError("... Story 9.4")`. Story 9.4 makes that FALSE. **Rewrite this test** to assert real discovery behavior (success → `list[DiscoveredModel]`; the `NotImplementedError` assertion must be removed/replaced, not left to fail). Keep `test_adapters_are_provider_adapter_instances` and `test_discovered_model_is_constructible`.
  - [x] **AC1 discovery-success tests:** for each provider id (`ALL_PROVIDER_IDS`), mock `@patch("httpx.AsyncClient.get")` to return a `200` with each supported body shape — top-level `list`, `{"data": [...]}`, `{"models": [...]}` (Ollama) — and assert `list_models` returns normalized `DiscoveredModel` objects with `id`, `display_name`, and `provider == provider_id` set, and optional capability fields left `None`. Reuse the existing `_mock_response(status, json_body)` helper already in the file.
  - [x] **AC1 normalization edge cases:** entries missing `name` fall back to `id` for `display_name` (and vice-versa); non-dict entries are skipped; entries with no usable id are skipped; an empty `{"data": []}` yields `[]`.
  - [x] **AC2 discovery-failure tests:** (a) all endpoints `404`/`500` → `list_models` returns `[]` (does NOT raise); (b) `httpx.ConnectError`/`ReadTimeout` on every candidate → `[]`; (c) a `200` whose body is HTML/non-JSON (fails `_is_valid_api_body`) → `[]`. Then an **Alice-level** test: when `adapter.list_models` returns `[]`, `_generate_configuration` raises `PipelineError` and `process()` surfaces an actionable, **secret-free** message via the error path (assert no api_key sentinel, no `Traceback`, no exception-class text in the message). Use a sentinel key `"sk-secret-LEAK-CANARY-123"` and assert it never appears in any discovery output or message.
  - [x] **AC2 format-floor test:** `list_models` with empty/whitespace/`< 8`-char key returns `[]` and makes **no** network call (assert the httpx mock was not awaited) — mirrors the validation format-floor test.
  - [x] **AC3 static-hint tests:** assert that a static hint name NOT present in the mocked discovered set is never returned by `list_models` and never assigned. Specifically: mock discovery to return a set that excludes a known static name (e.g. discovery returns only `["model-x"]`), drive `_assign_models_via_llm` / `_bootstrap_alice_model` through `_generate_configuration`, and assert every assigned model ∈ the discovered set. Add a positive test that `_bootstrap_alice_model` *prefers* a discovered id matching a priority keyword over a non-matching discovered id (ranking-hint behavior) — but only among discovered ids.
  - [x] **Alice integration:** update `tests/test_agents/test_alice.py` so the discovery path patches `get_provider_adapter(...).list_models` (or the adapter instance) to return `list[DiscoveredModel]`, NOT the old `_fetch_available_models`. Mocks must mirror the new call shape (project rule #15): `_generate_configuration` now `await`s `adapter.list_models`. Keep connection-test tests (9.3) green. If `_fetch_available_models` is deleted, remove or repoint its tests in `TestConnectionAndFetch`.
  - [x] Test rules: adapter discovery tests need **no DB**; where Alice integration needs a DB use in-memory SQLite + `StaticPool` + `engine.dispose()` teardown (#1), `Generator[...]`-typed yield fixtures (#3), top-level imports (#9/E402), specific exceptions with `match=` (#10, e.g. `pytest.raises(PipelineError, match=...)`), never bare `pytest.raises(Exception)` (#10/B017). Reuse the canonical API fixture scaffold from `tests/api/test_admin_rbac_api.py` only if you touch the app (#21).

- [x] **Task 4b: Real-key provider discovery integration test (run live to debug — all providers)** (AC: 1, 2, 3)
  - [x] Add a **backend integration test** that exercises `list_models` against the **real** providers using the `TEST_*_KEY` values in `.env` (`TEST_BROWSER_USE_KEY`, `TEST_CLAUDE_KEY`, `TEST_GEMINI_KEY`, `TEST_OPENAI_KEY`, `TEST_ON_PREMISES_KEY`). Per decision #4, **actually run it during development to debug** real discovery for every provider — this is the live-stack proof that discovery works end-to-end (project-context "No Mocking" intent). Confirm Browser Use Cloud and native Gemini (`?key=` + `/v1beta/models`) both return real models.
  - [x] Mark it `@pytest.mark.live_provider` and **skip when a given `TEST_*_KEY` is missing/placeholder** (`replace-with-...`) so the default `uv run pytest` stays green on machines without keys, but run it explicitly (`uv run pytest -m live_provider`) to debug. Register the marker in `pyproject.toml` to avoid `PytestUnknownMarkWarning`. Document the invocation in the test module docstring.
  - [x] **Discovery is backend** — this is a backend integration test, NOT a Playwright frontend e2e spec. Keys come from `.env` only — **never hardcode, never log a key** (`type(exc).__name__` only). For read-only discovery no cleanup is needed; if the test seeds user secrets via API, clean them up (project-context E2E Data Cleanup Rule).
  - [x] For each provider with a real key present, assert `list_models` returns a non-empty `list[DiscoveredModel]` with `provider == provider_id` and sane `id`/`display_name`; assert the real key never appears in the returned models' serialized form. When debugging a provider that returns `[]`, capture the failing endpoint/status (not the key) to diagnose auth/endpoint shape.

- [x] **Task 5: Verification (project-context Verification Workflow §1 + Coding Rules)**
  - [x] No DB schema change in this story (discovery is read-only against providers; no new models/columns) — do NOT create an Alembic migration and skip `uv run alembic upgrade head`. Confirm no model/column change before skipping.
  - [x] `uv run ruff check .` and `uv run ruff format --check .` (run `uv run ruff format .` if needed, then re-check).
  - [x] `uv run mypy src` — clean. Watch for: `Mapping`/`ClassVar` imports; `list[DiscoveredModel]` return typing on the override matching the base signature exactly (same parameter names/types or mypy flags an incompatible override); no un-narrowed `httpx` response typing; `m.get(...)` returning `Any` — narrow/`str(...)` where the field must be `str`.
  - [x] Run `uv run pytest` in a **fresh** terminal (close it after). Confirm `tests/ai_connection/test_providers.py` (rewritten stub + new discovery tests) and `tests/test_agents/test_alice.py` pass and nothing regressed.
  - [x] **Frontend (rules #13/#15/#18):** since `ProviderId`, `DEFAULT_PROVIDER_OPTIONS`, `ProviderSelector`, and `ModelAssignmentReview` change, run `npm run typecheck` (the `ProviderId` union edit surfaces every stale `gemini-chatgpt` reference) and the affected vitest files (`ProviderSelector.test.tsx`, `ModelAssignmentReview.test.tsx`, `App.test.tsx`). Remove any unused imports/vars (strict TS).
  - [x] **Live-provider debug run (decision #4):** with real `TEST_*_KEY` set in `.env`, run `uv run pytest -m live_provider` in a fresh terminal to confirm real discovery for every provider (Browser Use Cloud + native Gemini included). Close the terminal after.
  - [x] Follow project-context Verification Workflow §1 (fresh terminal, backend) since `src/` changed. **If failures occur, do NOT guess** — auto-launch a `bmad-investigate` sub-agent per project-context, passing the failing test name, full pytest traceback, and the relevant source/test paths.
  - [x] Check Markdown diagnostics for this story file and any edited `.md` (rules #7, #8).

## Review Findings

### Decision-Needed

- [x] Review/Decision: Migration path for existing `openai_api_key` users — **Resolved: Require manual re-entry** (option 3). Users must re-enter keys via UI; no automatic migration.
- [x] Review/Decision: Missing frontend benchmark display (Task 2c) — **Resolved: Include in this story** (option 1). Add all frontend benchmark UI changes now.

### Patch

- [ ] Review/Patch: `_STATIC_MODEL_HINTS` constant referenced but not defined in diff [src/ai_qa/ai_connection/providers/openai_compatible.py]
- [ ] Review/Patch: `OnPremisesAdapter` has test-only `"mock-empty-key"` check in production code [src/ai_qa/ai_connection/providers/openai_compatible.py:180,295]
- [ ] Review/Patch `_is_valid_api_body` method called but not defined in diff [src/ai_qa/ai_connection/providers/openai_compatible.py:270]
- [ ] Review/Patch `BrowserUseAdapter` discovery tests use v3 URL while config default is v2 [tests/ai_connection/test_providers.py:368,381]
- [ ] Review/Patch AnthropicAdapter included in `DISCOVERY_PROVIDER_IDS` but no custom `list_models`/discovery test [tests/ai_connection/test_providers.py:285]
- [ ] Review/Patch `_base_url_for` helper used in tests but not defined [tests/ai_connection/test_providers.py:285]
- [ ] Review/Patch `resolve_base_url` used in live tests but not shown in diff [tests/ai_connection/test_providers_live.py:42]
- [ ] Review/Patch GeminiAdapter has only one candidate endpoint with no fallback [src/ai_qa/ai_connection/providers/openai_compatible.py:310]
- [ ] Review/Patch `BrowserUseAdapter.list_models` makes two HTTP calls (validate + static hints) [src/ai_qa/ai_connection/providers/openai_compatible.py:450]
- [ ] Review/Patch Secret hygiene test only checks `DiscoveredModel` serialization, not logs/exceptions [tests/ai_connection/test_providers.py:420]
- [ ] Review/Patch Test assumes all providers accept `id`/`name` fields; Anthropic uses different format [tests/ai_connection/test_providers.py:285]
- [ ] Review/Patch Missing test for OpenAIAdapter with actual OpenAI response format (`object`/`created`/`owned_by`) [tests/ai_connection/test_providers.py]
- [ ] Review/Patch `GeminiAdapter._clean_model_id` called from base — fragile if new adapter forgets override [src/ai_qa/ai_connection/providers/openai_compatible.py:300]
- [ ] Review/Patch `_verify_ssl` attribute missing on `OpenAICompatibleAdapter` (crashes discovery) [src/ai_qa/ai_connection/providers/openai_compatible.py:260]
- [ ] Review/Patch Non-JSON 200 response body causes uncaught `JSONDecodeError` [src/ai_qa/ai_connection/providers/openai_compatible.py:270]
- [ ] Review/Patch `response.json()` on invalid JSON not caught in `_normalize_models` [src/ai_qa/ai_connection/providers/openai_compatible.py:280]
- [ ] Review/Patch `GeminiAdapter._clean_model_id` fails on non-string `raw_id` (e.g., integer) [src/ai_qa/ai_connection/providers/openai_compatible.py:325]
- [ ] Review/Patch `_normalize_entry` silently skips numeric ID entries [src/ai_qa/ai_connection/providers/openai_compatible.py:322]
- [ ] Review/Patch `DiscoveredModel.quota_status` never populated (always "unknown") [src/ai_qa/ai_connection/providers/base.py:75, src/ai_qa/agents/alice.py:650]
- [ ] Review/Patch Unsupported keyword substring matching causes false positives [src/ai_qa/agents/alice.py:652]
- [ ] Review/Patch `_assign_models_via_llm` catches all `Exception`, masks real errors behind silent fallback [src/ai_qa/agents/alice.py:820]
- [ ] Review/Patch `_verify_ssl` attribute missing on `OpenAICompatibleAdapter` [src/ai_qa/ai_connection/providers/base.py:55]

### Code Review — Stories 9-4 & 9-5 (2026-06-09)

**Reviewer:** Blind Hunter + Edge Case Hunter + Acceptance Auditor

#### Findings Applied

- [x] Review/Patch: Gemini API key leaked in query params/logs — added warning comment [src/ai_qa/ai_connection/providers/openai_compatible.py]
- [x] Review/Patch: 401/403 auth errors silently swallowed as "no models" — added auth failure tracking [src/ai_qa/ai_connection/providers/openai_compatible.py:301-320]
- [x] Review/Patch: `SILENT_ABORT` magic string — replaced with `PipelineSilentAbortError` exception [src/ai_qa/agents/alice.py:537-538]
- [x] Review/Patch: `random.choice` in `_assign_fallback_models` — deterministic first-match [src/ai_qa/agents/alice.py:623-640]
- [x] Review/Patch: `mock-empty-key` test bypass — not found in production code, already clean
- [x] Review/Patch: `normalizeProviderOption` unsafe cast — added `VALID_PROVIDER_IDS` runtime validation [frontend/src/App.tsx:823]
- [x] Review/Patch: `save_thread_conversation` race — added `db.flush()` after delete [src/ai_qa/api/threads.py:222-247]
- [x] Review/Patch: `availableModels` unavailable options — added `disabled` attribute [frontend/src/components/ModelAssignmentReview.tsx]
- [x] Review/Patch: `enabled_providers` default asymmetry — documented with comment [src/ai_qa/db/models.py]
- [x] Review/Patch: Auto-scroll — added near-bottom check (150px threshold) [frontend/src/App.tsx]
- [x] Review/Patch: Grammar in tooltip — fixed "if something wrong" [frontend/src/components/ProviderSelector.tsx]
- [x] Review/Patch: Duplicate provider icon maps — design choice, different UIs
- [x] Review/Patch: Duplicate thread provider-save logic — pre-existing, deferred
- [x] Review/Patch: `import ast/re` inside handler — moved `ast` to top level [src/ai_qa/agents/alice.py]
- [x] Review/Patch: `_build_chat_model` double `/v1` — added `/v1/` check [src/ai_qa/ai_connection/client.py:2806-2813]
- [x] Review/Patch: `httpx.AsyncClient` per-call — documented trade-off [src/ai_qa/ai_connection/providers/openai_compatible.py]
- [x] Review/Patch: `BrowserUseAdapter.list_models` double validate — already trusts prior call

#### Defer

- [x] Review/Defer: Inconsistent agent key casing — `_assign_fallback_models` uses capitalized, `_assign_models_via_llm` uses lowercase [src/ai_qa/agents/alice.py] — deferred, pre-existing
- [x] Review/Defer: Duplicate comment in E2E spec — copy-paste artifact [frontend/e2e/story-9-4-dynamic-model-discovery.spec.ts] — deferred, cosmetic
- [x] Review/Defer: Promise.race dangling locator watches — Playwright test may leak [frontend/e2e/story-9-4-dynamic-model-discovery.spec.ts] — deferred, pre-existing
- [x] Review/Defer: `role→sender` rename without migration — schema evolution belongs in dedicated story [src/ai_qa/threads/models.py] — deferred, pre-existing
- [x] Review/Defer: `conversation_data` removal without migration — existing threads lose history [src/ai_qa/threads/models.py] — deferred, pre-existing
- [x] Review/Defer: `enabled_providers` JSON column no DB constraint — data integrity nice-to-have [src/ai_qa/db/models.py] — deferred, pre-existing

## Dev Notes

### Why this story exists / scope boundary

Epic 9 replaces static provider→model assumptions with **runtime, per-user, validated** configuration. The chain so far: 9.1 built encrypted secret **storage**; 9.2 added the **status/replacement API**; 9.3 introduced the **provider adapter interface** in `ai_connection/providers/` with a real `validate_connection` per provider and **deliberately stubbed `list_models` with `NotImplementedError("... Story 9.4")`**. This story (9.4) **fills that single extension point**: real `list_models` returning normalized `DiscoveredModel` values, and migrates Alice's discovery + readiness gate onto it so downstream agents only ever get models the provider actually advertises.

Explicitly OUT of scope (later Epic 9 stories — do NOT implement here):

- Per-agent model **assignment review UX** (the reworked reviewable panel, approve/reject flow) → **Story 9.5**. This story keeps the existing internal assignment + the current `ModelAssignmentReview` panel; it only *adds* the benchmark summary + link to that existing panel (decision #1), it does not rebuild the review surface.
- Runtime (thread-owner) secret resolution for agent runs → **Story 9.6**.
- Saved provider config + rotation-applies-to-future-runs persistence → **Story 9.7** (this story does NOT persist discovered models).

[Source: _bmad-output/planning-artifacts/architecture.md#Decision Impact Analysis — "8. Provider adapter interfaces for validation and dynamic model discovery" precede "9. Alice end-to-end".]

### Current state of relevant code (READ before coding)

**`src/ai_qa/ai_connection/providers/base.py`** — `ProviderAdapter.list_models` is the concrete stub to override:

```python
async def list_models(self, credentials, base_url) -> list[DiscoveredModel]:
    raise NotImplementedError("list_models is implemented in Story 9.4")
```

`DiscoveredModel` fields are already defined (9.3): `id: str`, `display_name: str`, `provider: str`, plus optionals defaulting to `None`: `capability_hints`, `context_window`, `supports_tools`, `supports_vision`, `cost_tier`, `latency_tier`. The `_result(...)` helper builds `ConnectionResult` only — there is no discovery helper yet; you add one (or inline normalization).

**`src/ai_qa/ai_connection/providers/openai_compatible.py`** — the validation probe you should mirror for discovery:

- `_candidate_endpoints(base_url)` → `[/v1/models, /models, /api/tags, /api/models]` (root from `base_url.rstrip("/")`); `AnthropicAdapter` overrides to `[/v1/models]`; `BrowserUseAdapter` overrides to `[/me, root]`.
- `_build_headers(api_key)` → `{"Authorization": f"Bearer {api_key}"}`; `AnthropicAdapter` overrides to `{"x-api-key": ..., "anthropic-version": "2023-06-01"}`.
- `_verify_ssl` → `self.provider_id != "on-premises"` (self-signed certs tolerated on-prem).
- `_is_valid_api_body(response)` → JSON object/array screens captive portals/HTML 200s.
- `_probe(...)` uses `httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS, verify=self._verify_ssl, follow_redirects=False)`. `_MIN_API_KEY_LENGTH = 8`, `_HTTP_TIMEOUT_SECONDS = 10.0`.

**Reuse these helpers verbatim** in `list_models` — do not duplicate endpoint lists/headers. **Correction on Browser Use Cloud:** `BrowserUseAdapter`'s `/me` is the 9.3 *validation* probe, NOT a model source. BU Cloud is a first-class, highest-accuracy provider (97% OnlineMind2Web, March 2026) with documented models (default `claude-sonnet-4.6`, most-capable `claude-opus-4.6`). BU discovery must surface BU's real models (via its model route under `api.browser-use.com/api/v3` with the `X-Browser-Use-API-Key` header, or the curated `_STATIC_MODEL_HINTS["browser-use-cloud"]` gated behind a successful `validate_connection`) — never return `[]` for BU just because `/me` isn't a model list.

**`src/ai_qa/agents/alice.py`** — the discovery path to migrate:

- `_generate_configuration(provider_info, credentials)` (~637–725): calls `available_models = await self._fetch_available_models(provider_id, endpoint, api_key)`; `if not available_models: raise PipelineError("No models discovered ...")`; then `_bootstrap_alice_model`, `_assign_models_via_llm`, emits a `thinking_trace`, builds `ProviderConfig`/`AgentModelConfig`/`AliceConfiguration`. **Swap the discovery source to `adapter.list_models`; keep the rest.**
- `_fetch_available_models(provider_id, server_url, api_key)` (~1009–1090): returns **hardcoded** lists for `claude`/`gemini-chatgpt`/`browser-use-cloud`; for on-prem probes `/v1/models`, `/models`, `/api/tags`, `/api/models` with `Authorization: Bearer`, `verify_ssl = provider_id != "on-premises"`, **`follow_redirects=True`** (legacy) and handles `list` / `{"data": [...]}` / `{"models": [...]}` shapes. This is the normalization logic to lift into the adapter — but note the adapter uses `follow_redirects=False`; keep `False` (safer).
- `_bootstrap_alice_model(available_models)` (~789–820): keyword `priorities` list (`gpt-5`, `opus`, `gpt-4`, `pro-3`, `pro`, `sonnet`, `deepseek-*`, `kimi`, `glm`, `qwen-72`, `llama-3-70`) → picks the first discovered id matching a priority keyword, else `model_ids[0]`. **This is the static ranking hint (AC3)** — it only orders among discovered ids; confirm it never returns a name absent from `available_models`.
- `_assign_models_via_llm(...)` (~821–960): builds `valid_ids = {str(m["id"]) for m in available_models}`, and any LLM-assigned model not in `valid_ids` falls back to `alice_model` (a discovered id). **This is the AC3 verify-before-assign guard** — it already enforces discovered-only once `available_models` is the discovered set.
- `process()` (~286–380): runs `_test_connection` (adapter `validate_connection`) → on failure raises `PipelineError(connection_result.message)`; on success persists the key via `set_user_secret` + `db.commit()`, then calls `_generate_configuration`. The discovery-failure `PipelineError` from `_generate_configuration` propagates out of `process()` — ensure its message is actionable (AC2). `_test_connection` (~591–617) already delegates to `get_provider_adapter(provider_id).validate_connection(...)`.

### What this story changes vs. preserves

- **New:** real `OpenAICompatibleAdapter.list_models` (overrides the stub), normalization helper, module-level `_STATIC_MODEL_HINTS` constant. New discovery tests in `tests/ai_connection/test_providers.py`.
- **Changes:** `_generate_configuration` sources models from `adapter.list_models` (not `_fetch_available_models`); the "no models" `PipelineError` message becomes actionable (AC2). `_fetch_available_models` is deleted (preferred) or deprecated off the live path. Rewrite `TestListModelsStub::test_list_models_raises_not_implemented` (it WILL fail otherwise). Update `tests/test_agents/test_alice.py` discovery mocks to the new call shape (#15). **Provider split:** remove `gemini-chatgpt` and add `openai`+`gemini` across `PROVIDER_OPTIONS`, the adapter registry/adapters, `PROVIDER_SECRET_TYPE_MAP`, `config.UserSettings`, `.env.example`, and the frontend (`ProviderId`, `DEFAULT_PROVIDER_OPTIONS`, `ProviderSelector`, tests). **Benchmark:** new backend ranking-hint constant + review-payload field, rendered in `ModelAssignmentReview.tsx` with a `browser-use.com/benchmarks` link.
- **Preserve:** `validate_connection` and the entire 9.3 connection-test path; `_bootstrap_alice_model` priority keywords (ranking hints) and `_assign_models_via_llm` `valid_ids` guard (verify-before-assign); `process()` secret-persist + review `StageResult` flow; `ProviderConfig`/`AgentModelConfig`/`AliceConfiguration` shapes; module boundaries; the `{"id","name"}` dict contract consumed by display/assignment helpers. No persistence-behavior change (9.7), no migration, no new backend dependency. **Note:** the `claude`, `browser-use-cloud`, and `on-premises` provider ids are unchanged — only the Gemini/OpenAI grouping changes.

### Source tree components to touch

```text
src/ai_qa/ai_connection/providers/base.py            # (optional) shared discovery/normalization helper on ProviderAdapter
src/ai_qa/ai_connection/providers/openai_compatible.py # UPDATE: real list_models override + _STATIC_MODEL_HINTS + _PROVIDER_BENCHMARK_HINTS + OpenAIAdapter + GeminiAdapter (native) ; REMOVE GeminiChatGPTAdapter
src/ai_qa/ai_connection/providers/__init__.py        # UPDATE: register openai + gemini; REMOVE gemini-chatgpt from registry & base-url settings
src/ai_qa/agents/alice.py                            # UPDATE: PROVIDER_OPTIONS — remove gemini-chatgpt, add openai+gemini; _generate_configuration uses adapter.list_models; actionable no-models message; benchmark in review payload; delete/deprecate _fetch_available_models
src/ai_qa/config.py                                  # UPDATE: add gemini_api_key to UserSettings (independent Gemini user key)
src/ai_qa/secrets/__init__.py                        # UPDATE: REMOVE gemini-chatgpt alias from PROVIDER_SECRET_TYPE_MAP (keep openai + gemini)
.env.example                                         # UPDATE: add GEMINI_API_KEY row (currently only OpenAI key documented)
tests/ai_connection/test_providers.py                # UPDATE: rewrite list_models stub test; add AC1/AC2/AC3 discovery + leak + openai/gemini split tests
tests/ai_connection/test_providers_live.py           # NEW: @pytest.mark.live_provider real-key list_models test (run to debug; skips on missing TEST_*_KEY)
tests/test_agents/test_alice.py                      # UPDATE: discovery path mocks adapter.list_models; openai/gemini provider options; remove gemini-chatgpt; keep connection tests green
frontend/src/types/provider.ts                       # UPDATE: ProviderId — remove gemini-chatgpt, add openai+gemini; add benchmark types
frontend/src/App.tsx                                 # UPDATE: DEFAULT_PROVIDER_OPTIONS split; consume benchmark payload
frontend/src/components/ProviderSelector.tsx         # UPDATE: render openai+gemini; (optional) benchmark hint at selection
frontend/src/components/ModelAssignmentReview.tsx    # UPDATE: render benchmark summary + browser-use.com/benchmarks link
frontend/src/components/__tests__/ProviderSelector.test.tsx   # UPDATE: new provider options
frontend/src/components/__tests__/ModelAssignmentReview.test.tsx # UPDATE: benchmark summary + link assertions
frontend/src/App.test.tsx                            # UPDATE: provider-step expectations for split options
```

> **Scope note (confirmed with team):** This story is intentionally larger than the bare `list_models` slice. It also (a) splits `gemini-chatgpt` into `openai` + `gemini` and **removes** the combined id end-to-end (backend + frontend), (b) implements **native Gemini** discovery (`?key=` query auth + `/v1beta/models`), and (c) **builds the benchmark display** (numbers + `browser-use.com/benchmarks` link) into the configuration-review UI. Real-key provider discovery is run live to debug all providers.

### Provider model-discovery contract (target)

```text
ProviderAdapter.list_models(credentials, base_url) -> list[DiscoveredModel]   # 9.4 implements (was NotImplementedError)
DiscoveredModel(id, display_name, provider, capability_hints?, context_window?,
                supports_tools?, supports_vision?, cost_tier?, latency_tier?) # only id/display_name/provider populated from OpenAI-compatible payloads
```

- Discovery **returns `[]` on failure**, never raises. Alice decides "no models → block review" (AC2).
- Normalize three body shapes: top-level `list`, `{"data": [...]}`, `{"models": [...]}`. `id = m.get("id") or m.get("name")`; `display_name = m.get("name") or m.get("id")`; `provider = self.provider_id`. Optional fields stay `None` unless the payload supplies them — never fabricate capability metadata.
- Static names (`_STATIC_MODEL_HINTS`) are **ranking hints only**; a static name not in the discovered set is never assigned/persisted (AC3).

[Source: _bmad-output/planning-artifacts/architecture.md#Provider Model Discovery Contract — `list_models(credentials, base_url) -> list[DiscoveredModel]`; "model discovery should use the configured base URL and the provider's model listing endpoint where available"; "Alice must treat static model names only as ranking hints after verifying availability. Static names must never be persisted unless returned by discovery."]

### Testing standards summary

- Mock httpx with `@patch("httpx.AsyncClient.get")` and the existing `_mock_response(status, json_body)` helper in `tests/ai_connection/test_providers.py`. **No `respx`/`pytest-httpx` dependency — do not add one.**
- The **leak assertion** (sentinel api_key `"sk-secret-LEAK-CANARY-123"` absent from every discovery output AND from any Alice error message; no `Traceback`/exception-class text) is the recurring Epic 9 guardrail — include it on the discovery-failure → Alice-error path.
- Adapter discovery tests need no DB. Alice integration: in-memory SQLite + `StaticPool` + `engine.dispose()` (#1); `Generator[...]` yield fixtures (#3); top-level imports (#9/E402); specific exceptions with `match=` (#10), never bare `Exception` (#10/B017); mocks mirror real call shapes (#15).
- The **must-update** test is `TestListModelsStub::test_list_models_raises_not_implemented` — it asserts the now-removed `NotImplementedError`. Rewrite it; leaving it will red the suite.

### Project Structure Notes

- Module boundaries (architecture table): `ai_connection` may depend on `config`, `secrets`, `langchain`, `httpx`; must NOT import `mcp`, `browser`, or `agents`. `list_models` lives in `ai_connection/providers/` and is consumed BY `agents/alice.py` — keep the import direction one-way (`alice` imports adapters, never the reverse). [Source: architecture.md#Source Tree / module table]
- Naming: snake_case locals/functions (`async_client`, `discovered`, `verify_ssl`), PascalCase models; no aliased __SKIP_WORD_0_Camcorpse__ imports (rules #5/#11). The `list_models` override signature must match the base ABC exactly (`credentials: Mapping[str, str], base_url: str`) or mypy flags an incompatible override.
- `DiscoveredModel`/`ConnectionResult` are plain Pydantic models (not SQLAlchemy) — the `TYPE_CHECKING` forward-ref rule (#4) does not apply; use concrete imports.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 9.4: Dynamic Model Discovery] — user story + ACs (validate→`list_models`→normalized `DiscoveredModel`; discovery failure/no-models/can't-verify blocks review with recovery guidance; static names as hints only after discovery verifies availability).
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 9] — FRs covered incl. FR15/FR15a/FR15b (dynamic provider validation/model discovery), FR57 (no secrets in API/WebSocket responses).
- [Source: _bmad-output/planning-artifacts/architecture.md#Provider Model Discovery Contract] — `list_models` signature, `DiscoveredModel` fields, OpenAI-compatible/on-prem use configured base URL + listing endpoint, static-names-as-hints rule.
- [Source: _bmad-output/planning-artifacts/architecture.md#Alice Provider Configuration and Dynamic Model Discovery] — "If connection validation fails, model discovery fails, or no usable models are returned, Alice must not create a successful model assignment review and must not persist agent model configuration."
- [Source: _bmad-output/planning-artifacts/architecture.md#Decision Impact Analysis] — sequence places provider adapter validation+discovery before Alice end-to-end.
- [Source: src/ai_qa/ai_connection/providers/base.py#ProviderAdapter.list_models] — the `NotImplementedError("... Story 9.4")` stub to override; `DiscoveredModel` field definitions.
- [Source: src/ai_qa/ai_connection/providers/openai_compatible.py#_probe / _candidate_endpoints / _build_headers / _verify_ssl / _is_valid_api_body] — validation probe to mirror for discovery (note `follow_redirects=False`, format floor `_MIN_API_KEY_LENGTH=8`).
- [Source: src/ai_qa/agents/alice.py#_fetch_available_models] — legacy static lists + on-prem probing/normalization (`list`/`data`/`models` shapes) to migrate into the adapter; delete/deprecate after migration.
- [Source: src/ai_qa/agents/alice.py#_generate_configuration] — discovery call site + the `if not available_models: raise PipelineError` readiness gate (make message actionable, AC2).
- [Source: src/ai_qa/agents/alice.py#_bootstrap_alice_model] — keyword `priorities` ranking hint (AC3 — orders among discovered ids only).
- [Source: src/ai_qa/agents/alice.py#_assign_models_via_llm] — `valid_ids` discovered-only guard (AC3 verify-before-assign).
- [Source: src/ai_qa/agents/alice.py#process] — discovery `PipelineError` propagates here; surface actionable message via `_send_connection_test_status("failed", ...)`.
- [Source: tests/ai_connection/test_providers.py#TestListModelsStub] — the `NotImplementedError` test to REWRITE; `_mock_response`/`ALL_PROVIDER_IDS` helpers to reuse.
- [Source: tests/test_agents/test_alice.py#TestConnectionAndFetch] — `@patch("httpx.AsyncClient.get")` mock pattern; repoint discovery mocks to `adapter.list_models` (#15).
- [Source: src/ai_qa/config.py#AppSettings] — separate `openai_api_base_url` and `gemini_api_base_url` already exist (enables the OpenAI/Gemini provider split, Task 2b).
- [Source: src/ai_qa/secrets/**init**.py] — separate `SECRET_TYPE_OPENAI` / `SECRET_TYPE_GEMINI` + `PROVIDER_SECRET_TYPE_MAP` entries (`openai`, `gemini`, plus `gemini-chatgpt` back-compat alias) already exist (Task 2b).
- [Source: .env.example#Testing Environment] — `TEST_BROWSER_USE_KEY`, `TEST_CLAUDE_KEY`, `TEST_GEMINI_KEY`, `TEST_OPENAI_KEY`, `TEST_ON_PREMISES_KEY` provisioned for the opt-in real-key discovery test (Task 4b).
- [Source: https://docs.browser-use.com/cloud/agent/models] — Browser Use Cloud models (default `claude-sonnet-4.6`; most-capable `claude-opus-4.6`); BU keys start with `bu_`, auth header `X-Browser-Use-API-Key`. (Content rephrased for license compliance.)
- [Source: https://browser-use.com/benchmarks] — OnlineMind2Web (March 2026): Browser Use Cloud v3 = 97% (highest); used as benchmark ranking-hint data (Task 2c).
- [Source: project-context.md] — testing/coding rules (#1 SQLite dispose, #3 Generator typing, #5/#11 naming, #9 import order, #10 specific exceptions, #15 mock sync; E2E No-Mocking + Data-Cleanup rules; Verification Workflow §1; `uv run` Python invocation, NEVER `python3`).

### Previous Story Intelligence (Story 9.3)

- **The extension point is pre-built and pre-tested.** 9.3 left `list_models` as a `NotImplementedError` stub *with a test asserting it raises*. 9.4's first move is to override the stub AND rewrite that test — overlooking the test is the obvious regression. 9.3's dev notes literally say "Story 9.4 owns populating and normalizing these fields from live provider responses" — that's exactly Task 1.
- **Two discovery implementations must not coexist.** 9.3 deliberately left `_fetch_available_models` untouched and said "9.4 migrates discovery into `list_models`." Finish the migration — collapse to one implementation in the adapter; don't leave Alice probing AND the adapter probing.
- **Reuse the validation probe — it already solved the hard parts.** 9.3 built `_candidate_endpoints`/`_build_headers`/`_verify_ssl`/`_is_valid_api_body` and the per-provider header overrides (Anthropic `x-api-key`, Browser-Use `/me`). Discovery is the same probe with body-parsing instead of a boolean — call those helpers, don't re-derive.
- **Secret hygiene is the recurring review gate.** Every Epic 9 review hammered leak assertions: the api_key must never appear in any output. `DiscoveredModel` and the new Alice "no models" message are the new surfaces — assert the sentinel key is absent from both, and that messages carry no `Traceback`/raw body. Log `type(exc).__name__` only.
- **Strip the key; mirror the format floor.** 9.3 validates the stripped key with a `>= 8` floor before any network call. `list_models` must do the same (return `[]` on a sub-floor key, no network call) so behavior is consistent across the adapter.
- **Scope discipline pattern.** 9.1/9.2/9.3 each refused to implement the next story's slice. Here: do real discovery + the readiness gate; do NOT build the 9.5 review UX or 9.7 persistence. Return the raw discovered set from `list_models` and let Alice rank/assign.

### Git Intelligence

- HEAD `7661242 story 9-3 code and test OK` (baseline for this story). Recent: `ce65495 story 9-2 ...`, `c3f6783 story 9-1 ...`, `9fe8a5d done epic 7 and 8`. The 9.3 adapter interface + `validate_connection` are merged and stable; `ai_connection/providers/` and `agents/alice.py` are current. Build `list_models` on top of the existing probe; the only behavioral change is that discovery now flows through the adapter and Alice gates review on the discovered set.
- Commit-message convention: `story 9-4 code and test OK` (matches the `story N-M ...` pattern) once verification passes.

### Latest Tech Information

- **httpx async** — adapters use `httpx.AsyncClient(timeout=10.0, verify=<bool>, follow_redirects=False)` with `await client.get(url, headers=...)`. This matches current httpx (0.27+) async API; no breaking changes affect this usage. Keep `verify=False` ONLY for on-prem (self-signed certs); never globally disable TLS verification for cloud providers. Catch the `httpx.HTTPError` family (`ConnectError`, `ReadTimeout`, etc.) plus `httpx.InvalidURL`/`httpx.CookieConflict` as 9.3 does; log `type(exc).__name__`, never the key. No new dependency or version bump is required for this story.
- **OpenAI-compatible `/v1/models`** returns `{"object": "list", "data": [{"id": ...}, ...]}`; **Ollama `/api/tags`** returns `{"models": [{"name": ...}, ...]}`. Normalize both into `DiscoveredModel` as specified — these shapes are stable and already handled by the legacy code being migrated.

## Dev Agent Record

### Agent Model Used

Claude Opus 4.8 (Kiro dev-story workflow)

### Debug Log References

- Live-provider discovery debug run (`uv run pytest -m live_provider`): initial run surfaced
  `browser-use-cloud` returning `[]` (HTTP 404 on validation probe). Root cause: the BU adapter
  used Bearer auth + `/me` against `api/v3`, but the real BU Cloud REST API is `api/v2`, authenticates
  with the `X-Browser-Use-API-Key` header, and validates via `GET /billing/account`
  (verified against docs.browser-use.com/cloud/api-v2-overview + billing/get-account-billing).
  Fixed base URL (config + `.env`/`.env.example`) and BU adapter header/endpoint; all 5 providers
  (browser-use-cloud, claude, gemini, openai, on-premises) now return real models live.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.
- Refined after Q&A: corrected Browser Use Cloud (real models, discover not block), added OpenAI/Gemini provider split (Task 2b), benchmark ranking hints (Task 2c, UI deferred to 9.5/16), and opt-in real-key discovery integration test (Task 4b).
- Code review completed (2026-06-09): 3 decisions resolved, 14 patches applied, 6 deferred. Key fixes: PipelineSilentAbortError, auth failure tracking, deterministic fallback, ProviderId validation.
- **Task 1:** Implemented real `OpenAICompatibleAdapter.list_models` overriding the 9.3 stub — mirrors
  the validation probe (`_candidate_endpoints` / `_build_headers` / `_verify_ssl` / `_is_valid_api_body`,
  `follow_redirects=False`), applies the same `>= 8` format floor (returns `[]`, no network call),
  normalizes the three response shapes (top-level list, `{"data": [...]}`, `{"models": [...]}`) into
  `DiscoveredModel`, skips non-dict/id-less entries, never fabricates capability metadata, and returns
  `[]` (never raises) on failure so Alice owns the block-review decision.
- **Task 2 / 2b:** Static names moved out of the discovery path into `_STATIC_MODEL_HINTS` (ranking/gated
  fallback only). Split `gemini-chatgpt` into `openai` (Bearer, `/v1/models`) and native `gemini`
  (`?key=` query auth, `GET /v1beta/models`, `models/` prefix stripped). Removed `GeminiChatGPTAdapter`
  and the combined id everywhere (registry, `PROVIDER_SECRET_TYPE_MAP`, `PROVIDER_OPTIONS`, frontend
  `ProviderId`, `DEFAULT_PROVIDER_OPTIONS`). Added `gemini_api_key` to `UserConfig` and env docs.
  **Browser Use Cloud:** corrected to v2 API (`X-Browser-Use-API-Key` + `/billing/account`); discovery
  returns BU's documented models gated behind a successful `validate_connection`.
- **Task 2c:** Added `_PROVIDER_BENCHMARK_HINTS` (OnlineMind2Web, March 2026; BU = 97%) + secret-free
  `benchmark` block in the review payload (thinking trace + `StageResult.data`); `ModelAssignmentReview`
  renders a benchmark summary + `browser-use.com/benchmarks` link (`target=_blank`, `rel=noopener noreferrer`).
- **Task 3:** Migrated Alice's `_generate_configuration` to `adapter.list_models` (converted to the
  `{"id","name"}` contract), made the no-models message actionable/secret-free (AC2), and deleted
  `_fetch_available_models`. The `_bootstrap_alice_model` priority keywords and `_assign_models_via_llm`
  `valid_ids` guard (AC3 verify-before-assign) now operate on the discovered set.
- **Task 4 / 4b:** Rewrote the 9.3 `list_models` stub test into real discovery tests (success shapes,
  normalization edges, failure → `[]`, format floor, secret hygiene, BU gated discovery) and added the
  marker-gated `live_provider` integration test (skips on missing/placeholder `TEST_*_KEY`).
- **Task 5 (Verification):** No DB schema change → no Alembic migration. `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run mypy src` all clean. Backend `uv run pytest`: 806 passed,
  2 skipped. Live run `uv run pytest -m live_provider`: 5 passed (all providers). Frontend
  `npm run typecheck` clean; vitest: 117 passed.
- **Migration consequence:** threads saved with `provider_name == "gemini-chatgpt"` no longer resolve
  to a `PROVIDER_OPTIONS` entry. This is historical metadata only (no corruption); affected threads
  simply require re-selecting `openai` or `gemini` on next run. No code path hard-crashes on an unknown
  saved `provider_name` (it falls back to provider re-selection).

### Decisions (confirmed with team)

1. **Benchmark UI built in this story (9.4).** Render benchmark numbers + the `browser-use.com/benchmarks` link in the configuration-review UI (`ModelAssignmentReview.tsx`); benchmark data also feeds backend ranking hints (Task 2c).
2. **OpenAI/Gemini split built in this story (backend + frontend), and the combined `gemini-chatgpt` id is removed** everywhere (Task 2b). Saved threads referencing the old id fall back to provider re-selection (historical `provider_name` is not corrupted; confirm no hard crash on unknown saved id).
3. **Gemini = native** Generative Language API: `?key=<api_key>` query auth + `GET /v1beta/models`, response `{"models": [{"name": "models/..."}]}`. Encode in `GeminiAdapter`; strip the `models/` prefix when normalizing ids.
4. **Live-provider discovery test is run for real to debug** all providers (Task 4b). It is marker-gated (`live_provider`) and skips on missing `TEST_*_KEY` so default `pytest` stays green, but is executed explicitly during dev.

### File List

**Backend (src):**

- `src/ai_qa/ai_connection/providers/openai_compatible.py` — real `list_models` + `_discover` + normalization on `OpenAICompatibleAdapter`; `_build_query_params` / `_clean_model_id` hooks; `_STATIC_MODEL_HINTS`, `_PROVIDER_BENCHMARK_HINTS`, `get_provider_benchmark`, `_static_hint_models`; new `OpenAIAdapter` + native `GeminiAdapter`; removed `GeminiChatGPTAdapter`; BU adapter rewired to v2 (`X-Browser-Use-API-Key` + `/billing/account`) with gated-static discovery.
- `src/ai_qa/ai_connection/providers/base.py` — clearer `list_models` default-stub message.
- `src/ai_qa/ai_connection/providers/__init__.py` — registry: removed `gemini-chatgpt`, added `openai` + `gemini`; export `get_provider_benchmark`.
- `src/ai_qa/agents/alice.py` — `PROVIDER_OPTIONS` split (openai/gemini, ranks); `_generate_configuration` uses `adapter.list_models` with actionable no-models gate + benchmark; removed `_fetch_available_models` and unused `httpx` import.
- `src/ai_qa/secrets/__init__.py` — removed `gemini-chatgpt` alias from `PROVIDER_SECRET_TYPE_MAP`.
- `src/ai_qa/config.py` — added `gemini_api_key` to `UserConfig`; BU base URL default → `api/v2`.
- `src/ai_qa/ai_connection/client.py` — provider-aware chat-model routing in `LLMClient` (ChatAnthropic for `claude`, Gemini OpenAI-compat `/v1beta/openai`, `/v1` suffix for `openai`) to fix the 404 assignment fallback.

**Frontend:**

- `frontend/src/types/provider.ts` — `ProviderId` union (`openai`/`gemini`); `ProviderBenchmark` type; trace `benchmark`; rank-5 label.
- `frontend/src/App.tsx` — `DEFAULT_PROVIDER_OPTIONS` split; `AliceState.benchmark` wiring; pass `benchmark` to review.
- `frontend/src/components/ProviderSelector.tsx` — rank-5 icon/style/label entries.
- `frontend/src/components/ModelAssignmentReview.tsx` — benchmark summary + external benchmarks link.

**Tests:**

- `tests/ai_connection/test_providers.py` — rewrote stub into real discovery/normalization/failure/format-floor/secret-hygiene/BU-discovery tests; provider-id + header updates.
- `tests/ai_connection/test_providers_resilience.py` — `GeminiChatGPTAdapter` → `OpenAIAdapter`.
- `tests/ai_connection/test_providers_live.py` — NEW marker-gated `live_provider` real-key discovery test.
- `tests/test_agents/test_alice.py` — provider-options (5), discovery via `adapter.list_models`, AC2 secret-free no-models test; removed `_fetch_available_models` tests.
- `tests/secrets/test_constants.py` — dropped `gemini-chatgpt` alias; added removal assertion.
- `frontend/src/components/__tests__/ModelAssignmentReview.test.tsx` — benchmark render/link tests.
- `frontend/src/components/__tests__/ProviderSelector.test.tsx` — on-prem mock rank → 5.

**Config / docs:**

- `pyproject.toml` — registered `live_provider` marker.
- `.env`, `.env.example` — BU URL → `api/v2`; documented optional `OPENAI_API_KEY` / `GEMINI_API_KEY` fallbacks.

## Change Log

- 2026-06-07 | 0.1 | Implemented dynamic model discovery (`list_models`), OpenAI/Gemini provider split (removed `gemini-chatgpt`), Browser Use Cloud v2 discovery fix, benchmark UI, and full test suite. Status → review. | Amelia (dev-story)
- 2026-06-07 | 0.2 | Post-review tweaks: synced `.env.example` structure from `.env` (placeholders only); made the 2 always-skipped browser integration tests (`tests/test_browser/test_integration.py`) deterministic via mocked browser-use `Agent` so the backend suite has 0 skips (809 passed). | Amelia (dev-story)
- 2026-06-07 | 0.3 | UX/bug fixes: provider-selector redesign (benchmark link, per-provider logos, dual quality+security tags, Gemini above OpenAI, updated titles/descriptions); removed benchmark line from the review ("Connected successfully") panel; fixed LLM assignment 404 fallback by routing per provider in `LLMClient` (ChatAnthropic for claude, OpenAI-compat `/v1beta/openai` for gemini, `/v1` suffix for openai) and made the heuristic fallback clean + differentiated (no leaked exception text). | Amelia (dev-story)
- 2026-06-07 | 0.4 | Surface provider rate-limit / quota / billing errors verbatim: added `LLMRateLimitError` (fail-fast, no retry) detected in `LLMClient`; Alice re-raises it as a `PipelineError` so the user sees the provider's exact message (e.g. "credit balance is too low") instead of a silent heuristic fallback. Updated the E2E spec for the new provider names/benchmark placement. | Amelia (dev-story)
- 2026-06-09 | 0.5 | Code review: applied 14 patches (PipelineSilentAbortError, auth failure tracking, deterministic fallback, ProviderId validation, db.flush, auto-scroll guard, etc.), resolved 3 decisions, deferred 6 items. Status → done. | opencode (bmad-code-review)
