---
baseline_commit: a0d2c7d59f44221fb0a2df7c40f9400e15dea4b6
---
# Story 16.12: Fix Sarah Browser-Use Chrome-Driven Script Generation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **Priority: P0 — highest in Epic 16.** This bug blocks the Sarah → Jack pipeline (no scripts are produced), so it MUST be worked before all other Epic 16 stories (16-1 … 16-11).

## Story

As a QA user,
I want Sarah to reliably drive Chrome via browser-use and produce Playwright scripts from approved test cases,
so that script generation succeeds instead of failing with an LLM authentication error and leaving the Scripts folder empty.

### Observed bug

When Sarah reaches "Generating script N of M", generation fails with:

```
LLM Authentication failed: "Could not resolve authentication method. Expected either
api_key or auth_token to be set. Or for one of the X-Api-Key or Authorization headers
to be explicitly omitted"
```

All N "Generating script…" progress messages appear, then the batch ends in an ERROR state with **0 scripts saved** — the Scripts folder stays empty and nothing is reviewable.

## Acceptance Criteria

1. **Credential resolves for both models.** Given approved test cases and a configured provider whose credential resolves successfully, when Sarah generates scripts, then the resolved credential authenticates correctly for **both** the browser-use driving model **and** the deterministic script-generation model, and no "Could not resolve authentication method" error occurs.

2. **Real exploration when browser is available.** Given a Chrome path (or CDP URL) and a target application URL are available, when Sarah generates a script for a test case, then the browser-use exploration path actually drives Chrome against the real app (real app → verified trace → deterministic Playwright) for that test case.

3. **Graceful fallback when driving credential is unavailable.** Given the browser-use driving credential is genuinely unavailable (e.g. Claude / Claude-SSO without a real Anthropic key), when the live exploration cannot run, then Sarah falls back cleanly to vision / LLM-only generation and **still produces a script per test case**, rather than hard-failing the entire batch.

4. **Scripts folder is populated.** Given generation completes for a batch of approved test cases, when the results are saved, then the Scripts folder is populated with the generated scripts (not left empty) and each script is reviewable.

5. **Errors are actionable and secret-safe.** Given any generation or authentication failure, when the error is surfaced in the conversation, then the message is actionable and secret-safe — it NEVER exposes `api_key`, `auth_token`, or `Authorization`/`X-Api-Key` header values.

## Tasks / Subtasks

- [x] **Task 1 — Resolve the deterministic LLM config against the live context (AC1, AC4) [ROOT CAUSE]**
  - [x] Add a private `_ensure_llm_ready()` method to `SarahAgent` that re-resolves `self.config = self.get_llm_config()` against the attached `project_context`. Mirror Mary exactly — see [src/ai_qa/agents/mary.py:112](src/ai_qa/agents/mary.py:112).
  - [x] Keep the provisional `self.config = self.get_llm_config()` in `__init__` (placeholder; context not yet attached) but document that it is a placeholder, like Mary's [mary.py:102-106](src/ai_qa/agents/mary.py:102).
  - [x] Call `_ensure_llm_ready()` in `handle_start()` **before** any generation path runs, wrapped in `try/except` that transitions to `ERROR` and surfaces a UX-DR12 message on a genuinely missing key (mirror [mary.py:195-199](src/ai_qa/agents/mary.py:195)). Place it after the precondition gate and approved-test-case load, before `_present_test_case_selection`.
  - [x] Call `_ensure_llm_ready()` defensively in `_begin_generation()` and in `_regenerate_current_script()` so every `ScriptGenerator(llm_config=self.config, …)` construction uses the refreshed config (mirror Mary's repeat-safe calls at [mary.py:658](src/ai_qa/agents/mary.py:658) / [mary.py:977](src/ai_qa/agents/mary.py:977)).
  - [x] Verify the deterministic generator now reads a non-empty `api_key` (the per-user encrypted secret) instead of the stale empty-key default captured at `__init__`.

- [x] **Task 2 — Confirm the exploration path keeps using a freshly-resolved credential (AC2)**
  - [x] Verify `_build_explore_llm()` already re-resolves via `self.get_llm_config()` at generation time ([sarah.py:345-373](src/ai_qa/agents/sarah.py:345)) — do NOT switch it to the cached `self.config`.
  - [x] Confirm that when a Chrome path / CDP URL + target URL are present and the credential resolves, exploration drives the real app (`_explore_enabled` true → `explore_test_case` → `extract_trace` → `_call_llm_with_trace`).

- [x] **Task 3 — Make per-test-case failure degrade, never abort the batch (AC3, AC4)**
  - [x] In `SarahAgent._generate_scripts()`, the `else` branch (generation returned `success=False`) must append a **failure placeholder** `GeneratedScript` (matching the existing `except Exception` placeholder at [sarah.py:463-472](src/ai_qa/agents/sarah.py:463)) so a single failed test case does not silently drop and so the review panel still renders. Today the `else` branch ([sarah.py:453-457](src/ai_qa/agents/sarah.py:453)) only records an error and appends nothing — when ALL fail, `_generated_scripts` is empty and the whole run flips to ERROR.
  - [x] Confirm that with the credential fixed (Task 1), a provider with a valid key produces real scripts for every test case; the placeholder path is the safety net for the genuinely-no-credential case (AC3).
  - [x] Verify failure placeholders are skip-only (never approvable) — the existing `error_message` gate at [sarah.py:990](src/ai_qa/agents/sarah.py:990) already enforces this; do not regress it.

- [x] **Task 4 — Verify error surfacing is actionable + secret-safe (AC5)**
  - [x] Confirm surfaced errors flow through `self._format_error_message(...)` (UX-DR12 three-part format) and never include the raw `api_key`/token. The provider auth message ("Could not resolve authentication method…") carries no secret, but assert this in a leak-canary test.
  - [x] Ensure no code path logs or sends the resolved key, base URL credentials, or `Authorization`/`X-Api-Key` header values.

- [x] **Task 5 — Tests (all ACs)**
  - [x] Add a regression test proving Sarah's deterministic generation uses the **context-resolved** key, not the `__init__` placeholder: construct Sarah, attach a `project_context` whose secret store returns a key, call `handle_start`/generation, assert the `ScriptGenerator`/`LLMClient` saw the resolved key (mirror the Mary auth-bug test).
  - [x] Add a test for the no-credential fallback (AC3): provider without a usable key → exploration skipped (`_build_explore_llm` returns `None`) AND the batch still produces a script-per-test-case (or a skip-only placeholder per test case) instead of an empty-folder ERROR.
  - [x] Add a leak-canary test (AC5): force an auth failure and assert the surfaced message + any broadcast metadata contain no `sk-`/key/`Authorization` substrings.
  - [x] Run the full backend suite green; add only assertions, never weaken existing 13.x review/approval/role-folder/sidecar tests.

- [x] **Task 6 — Verification gates**
  - [x] `uv run ruff check --fix src/ tests/` **and** `uv run ruff format src/ tests/`.
  - [x] `uv run mypy src` clean (tests not gated by CI mypy, but write Pyrefly-clean test code — see project-context anti-patterns).
  - [x] `uv run pytest` (whole suite, or `--no-cov` on a subset — coverage gate fails on subset runs).
  - [ ] Manual live confirmation (integration-only; not in CI): with a real provider key + Chrome/CDP + reachable app, run Sarah end-to-end and confirm the Scripts folder populates and each script is reviewable. **DEFERRED — cannot run in this environment (no real provider key + Chrome + reachable app). To be confirmed by Thuong on a live run, consistent with the project's integration-only Sarah-exploration validation.**

## Dev Notes

### Root cause (verified against live code)

The deterministic script-generation LLM is built from a **stale, empty-key config captured at agent construction**, before the project context (and thus the per-user encrypted secret) is attached.

- `SarahAgent.__init__` runs `self.config = self.get_llm_config()` at [sarah.py:116](src/ai_qa/agents/sarah.py:116). At construction time `self.project_context is None` (the agent is built by `agent_class()` and the context is attached later via `set_context`/`set_project_context`), so `get_llm_config()` returns an `LLMConfig` with `provider="claude"` (the default), `model_name="claude-3-5-sonnet-20241022"`, and **`api_key=""`** (no DB secret reachable, env fallback only). It does NOT raise because the no-key raise is guarded by `self.project_context and self.project_context.user_id` — both are absent at `__init__` ([base.py:184-197](src/ai_qa/agents/base.py:184)).
- `self.config` is **never refreshed** afterwards. `_generate_scripts()` builds `ScriptGenerator(llm_config=self.config, …)` ([sarah.py:389](src/ai_qa/agents/sarah.py:389)) and `_regenerate_current_script()` does the same ([sarah.py:528](src/ai_qa/agents/sarah.py:528)) — both with the empty-key config.
- `ScriptGenerator._get_llm_client()` → `LLMClient(self._llm_config)` → `_build_chat_model()` builds `ChatAnthropic(api_key=SecretStr(""), …)` for `claude`/`claude-sso` ([client.py:87-98](src/ai_qa/ai_connection/client.py:87)). An empty key makes the Anthropic SDK raise **"Could not resolve authentication method…"**, which `_map_provider_exception` maps (because `"auth" in err_msg`) to `LLMAuthenticationError("LLM Authentication failed: …")` ([client.py:60-62](src/ai_qa/ai_connection/client.py:60)) — the exact surfaced string.
- Because every test case hits the same auth failure, `_generated_scripts` ends empty → `process()` returns `success=False` → `_begin_generation` flips to ERROR with 0 scripts saved.

**The browser-use driving model is a red herring in the failure CHAIN.** `_build_explore_llm()` re-resolves `self.get_llm_config()` FRESH at generation time ([sarah.py:355](src/ai_qa/agents/sarah.py:355)), so it actually gets the real key; if the key is empty it returns `None` and exploration is simply skipped. The user-visible "LLM Authentication failed:" prefix is produced only by the **deterministic** `LLMClient` path (the browser-use path doesn't go through `_map_provider_exception`). Both paths share the same underlying Anthropic SDK message, which is why the epic text attributes it to browser-use; the fix target is the deterministic config.

### This is the SAME bug Mary already fixed — reuse her pattern

Mary had this exact defect and fixed it. **Do not reinvent — mirror it.** See `_ensure_llm_ready()` at [mary.py:112-125](src/ai_qa/agents/mary.py:112) and its call sites ([mary.py:196](src/ai_qa/agents/mary.py:196), [mary.py:659](src/ai_qa/agents/mary.py:659), [mary.py:977](src/ai_qa/agents/mary.py:977)). The pattern:

```python
def _ensure_llm_ready(self) -> None:
    """Re-resolve the LLM config against the attached project context.

    __init__ captured an empty api_key (the agent is constructed before
    set_project_context runs), which surfaces at call time as a raw provider
    auth error. Resolving here uses the context-resolved per-user secret.
    Raises PipelineError (UX-DR12) when the key is genuinely missing.
    """
    self.config = self.get_llm_config()
    # Re-apply to any already-built collaborator that captured the old config.
```

Sarah's twist: the collaborator (`ScriptGenerator`) is built fresh per generation call (not stored long-term like Mary's `extractor`), so re-applying is just "make sure `self.config` is fresh before each `ScriptGenerator(llm_config=self.config, …)`." Keep `_build_explore_llm()` resolving fresh on its own.

### Credential reality (do not fight it)

Per the design doc, **Claude and Claude-SSO both require a real `sk-ant-api…` key** — SSO login alone never yields one ([design-browseruse-driven-script-generation-2026-06-18.md:39-45](_bmad-output/planning-artifacts/design-browseruse-driven-script-generation-2026-06-18.md:39)). So:

- `provider="claude"` / `"claude-sso"` with a stored Anthropic key → both models authenticate (AC1, AC2). `PROVIDER_SECRET_TYPE_MAP` maps `claude`, `claude-sso`, `claude_sso` to their secret types ([secrets/__init__.py:42-43](src/ai_qa/secrets/__init__.py:42)).
- `provider="on-premises"` → free company gateway, OpenAI-compatible, self-signed SSL tolerated; this is the common CORP path and should "just work" once `self.config` is fresh.
- `provider="claude-sso"` with **no** real key stored → exploration AND deterministic both genuinely cannot authenticate. AC3 governs this: degrade per-test-case (placeholder), never empty-folder ERROR, and surface a secret-safe UX-DR12 message telling the user to add a key.

NOTE the env-var fallback in `get_llm_config` only handles `claude`/`anthropic`/`openai`/`gemini` — NOT `claude-sso`/`on-premises` ([base.py:177-182](src/ai_qa/agents/base.py:177)). That fallback is for local dev only; production resolves from the encrypted secret store, so do not rely on env for those providers.

### Source tree components to touch

- `src/ai_qa/agents/sarah.py` — **UPDATE** (primary). Add `_ensure_llm_ready()`; call it in `handle_start` + `_begin_generation` + `_regenerate_current_script`; fix the `_generate_scripts` `else` branch to append a placeholder.
- `src/ai_qa/agents/base.py` — **READ ONLY** (understand `get_llm_config`); no change expected.
- `src/ai_qa/browser/llm_factory.py` — **READ ONLY**; already correct (returns `None` upstream when no key). No change expected unless a provider-mapping gap surfaces.
- `src/ai_qa/pipelines/script_generator.py` — **READ ONLY**; explore gating + fallback already correct. No change expected — the bug is the config it's handed, not its logic.
- `src/ai_qa/ai_connection/client.py` — **READ ONLY**; `_build_chat_model` / `_map_provider_exception` are correct.
- `tests/test_agents/test_sarah.py` — **UPDATE** (add regression + fallback + leak-canary tests).

### Current behavior to PRESERVE (regression guardrails)

The end-to-end Sarah flow must keep working — these were delivered in Epic 13 and 14 and must not break:

- **Input-selection gate (13.1):** `handle_start` → preconditions → `load_approved_test_cases` → AC3 no-test-cases block → `_present_test_case_selection`; `handle_approve` dispatches `phase=="input_selection"` → `_confirm_inputs` → `_begin_generation`. Insert `_ensure_llm_ready()` without disturbing this dispatch.
- **Inputs request (bsg-5/bsg-6):** `_begin_generation` asks for target URL + Chrome path / CDP URL via `sarah_inputs_request`; `_awaiting_inputs` re-entry skips the selection gate. `_ensure_llm_ready()` must be safe to call on re-entry (idempotent — Mary's is).
- **Explore → trace → Playwright (bsg-2/bsg-3):** `_explore_enabled = explore_llm is not None and (chrome_path or cdp_url)`; ANY exploration failure already falls through to vision/LLM-only inside `_generate_single_script` ([script_generator.py:228-265](src/ai_qa/pipelines/script_generator.py:228)). Keep that fall-through.
- **Per-item review / approve / reject / skip (13.5–13.7):** index-addressable; failure placeholders (`error_message` set) are skip-only ([sarah.py:990](src/ai_qa/agents/sarah.py:990)). Do not make placeholders approvable.
- **Role-foldered unique save names + sidecar metadata (13.8 / Slice 5):** `_unique_script_name` (role folder + collision suffix) and `_write_approved_scripts_metadata`. Untouched by this fix — leave intact.
- **Secrets convention (project-wide):** resolve secrets at runtime only; never in API/WS/logs/messages/artifacts. Leak-canary tests across output channels are a project convention — add one here (AC5).

### Testing standards summary

- Backend pytest: copy the canonical auth-context fixture pattern; this repo already has `mock_project_context` (used in `test_sarah.py`). For the resolved-key test, give the mocked context a user_id + a secret-store stub that returns a key so `get_llm_config` resolves non-empty.
- FastAPI deps via `app.dependency_overrides` only; `mock.patch` reserved for internal business logic — but here you're testing an agent, so patch the secret-resolution / `LLMClient` at the seam, not FastAPI deps.
- No bare `pytest.raises(Exception)` — use the specific type (`LLMAuthenticationError`, `PipelineError`) + `match=`.
- LLM calls in async code must be awaited; note `ScriptGenerator._call_llm*` uses the **sync** `llm_client.invoke(...)` today — that is pre-existing and out of scope; do not "fix" it in this story (it would be a separate change and risks the event-loop concern in project-context).
- Coverage gate (`--cov-fail-under=80`) fails on subset runs → run the whole suite or pass `--no-cov`. `uv run` uses `.venv` py3.14. NEVER `python3` (Windows).
- Pyrefly-clean test code: assert each Optional layer before reaching `.return_value`/`.call_args` on mocked chains (see project-context "Pyrefly-clean patterns").

### Project Structure Notes

- All changes stay inside `src/ai_qa/agents/sarah.py` and `tests/test_agents/test_sarah.py`. No new modules, no migrations, no schema changes, no frontend change (the WS payloads and the React review panel are unaffected — the fix only changes which credential the backend resolves).
- No new dependencies. `browser-use`, `langchain-anthropic`, `tenacity` are already in the tree.
- No conflict with the unified structure: this mirrors the existing Mary agent pattern in the same package.

### References

- Epic + ACs: [epics.md#Story-16.12](_bmad-output/planning-artifacts/epics.md:1954)
- Sarah agent (bug site): [src/ai_qa/agents/sarah.py:116](src/ai_qa/agents/sarah.py:116), [sarah.py:345](src/ai_qa/agents/sarah.py:345), [sarah.py:389](src/ai_qa/agents/sarah.py:389), [sarah.py:453](src/ai_qa/agents/sarah.py:453)
- Mary fix pattern (reuse): [src/ai_qa/agents/mary.py:112](src/ai_qa/agents/mary.py:112), [mary.py:196](src/ai_qa/agents/mary.py:196)
- LLM config resolution: [src/ai_qa/agents/base.py:146](src/ai_qa/agents/base.py:146)
- Chat-model build + auth-error mapping: [src/ai_qa/ai_connection/client.py:60](src/ai_qa/ai_connection/client.py:60), [client.py:87](src/ai_qa/ai_connection/client.py:87)
- Browser-use LLM factory: [src/ai_qa/browser/llm_factory.py:32](src/ai_qa/browser/llm_factory.py:32)
- Explore gating + fallback: [src/ai_qa/pipelines/script_generator.py:228](src/ai_qa/pipelines/script_generator.py:228)
- Provider→secret mapping: [src/ai_qa/secrets/__init__.py:37](src/ai_qa/secrets/__init__.py:37)
- Credential reality table: [design-browseruse-driven-script-generation-2026-06-18.md:38](_bmad-output/planning-artifacts/design-browseruse-driven-script-generation-2026-06-18.md:38)
- Coding/testing rules (authoritative): [project-context.md](project-context.md)

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Opus 4.8)

### Debug Log References

- Verified the `except A, B:` lines in `sarah.py` (271/278/920) are **valid** under Python 3.14 (the grammar now accepts an unparenthesized except tuple, parsed as `(A, B)`) — `ast.parse` + `py_compile` confirm. Pre-existing, out of scope, left untouched.
- Confirmed `get_llm_config()` raises a Pydantic `ValidationError` (not `PipelineError`) under the `mock_project_context` MagicMock DB, because `get_user_secret` returns a MagicMock that fails `LLMConfig.api_key: str` validation. This is why the lazy resolve needed test-side stubbing.
- First fix attempt hit `StageResult` validator `success=True but errors list is not empty`: the failure-placeholder makes the stage a *degraded success*, so per-item failures were re-routed from `errors` → `warnings` in BOTH the `else` and the pre-existing `except` branch (the latter had the same latent inconsistency).

### Completion Notes List

Root cause was identical to the bug Mary already fixed: `SarahAgent.__init__` captured `self.config = self.get_llm_config()` while `project_context` was still `None`, yielding an empty-`api_key` config that surfaced at generation time as the raw provider error "Could not resolve authentication method".

Implemented (mirror of Mary's `_ensure_llm_ready` pattern):

- Added `SarahAgent._ensure_llm_ready()` which re-resolves `self.config = self.get_llm_config()` against the attached context. Documented the `__init__` config as a provisional placeholder.
- Called `_ensure_llm_ready()` in `handle_start()` (after the AC3 gate, before the selection panel; try/except → `ERROR` + UX-DR12), in `_begin_generation()` (after the inputs-request branch, only when about to generate; try/except → `ERROR`), and in `_regenerate_current_script()` (before building the `ScriptGenerator`; runs inside `process()`'s try/except).
- Left `_build_explore_llm()` resolving its own fresh credential (Task 2 — read-only verify; unchanged).
- AC3/AC4: `_generate_scripts()` `else` branch now appends a skip-only failure placeholder (mirroring the `except` branch) so a batch never collapses to an empty Scripts folder; per-item failures recorded as warnings (degraded success). Failure placeholders remain skip-only via the existing `error_message` gate.
- AC5: surfaced errors flow through `_format_error_message` (UX-DR12); a leak-canary test asserts the resolved key / `sk-ant-` / `Authorization` / `X-Api-Key` never reach message content or broadcast metadata.

Tests: added `TestSarahLazyLLMConfigAuthFix` (6 tests: empty-key placeholder, context-resolved-key regression, genuinely-missing-key ERROR, explore-skipped-on-no-key, degrade-to-placeholder, leak-canary). Added a module-level autouse fixture `_stub_sarah_llm_config` (mirrors Mary's fixture stub) so the new lazy resolve does not reach the mock DB in the existing suite.

Verification: `ruff check` + `ruff format` clean; `mypy src` clean (101 files); full backend suite **1794 passed** (coverage 84.52%, gate 80% met). No frontend/schema/migration changes (per the story's scope notes). **One outstanding item:** the manual live end-to-end confirmation (integration-only) is deferred — it needs a real provider key + Chrome/CDP + a reachable app and cannot run in CI/this environment; Thuong to confirm on a live run.

### File List

- `src/ai_qa/agents/sarah.py` — MODIFIED: added `_ensure_llm_ready()`; call it in `handle_start`/`_begin_generation`/`_regenerate_current_script`; documented the `__init__` placeholder; `_generate_scripts` `else` branch now appends a skip-only failure placeholder and routes per-item failures to warnings (also fixed the same latent issue in the `except` branch).
- `tests/test_agents/test_sarah.py` — MODIFIED: added autouse `_stub_sarah_llm_config` fixture and `TestSarahLazyLLMConfigAuthFix` (6 tests).

### Review Findings

- [x] [Review][Patch] Vacuous test — `test_init_captures_empty_key_placeholder` always passes due to autouse fixture, not due to `__init__` behavior; add second assertion that `_ensure_llm_ready()` changes the config from "" to a resolved key to make the test meaningful [tests/test_agents/test_sarah.py:3690]
- [x] [Review][Patch] Leak-canary incomplete — `test_auth_failure_surfacing_is_secret_safe` only checks broadcast `msg.content`/`msg.metadata` but not `GeneratedScript.error_message`; add `assert sentinel not in (s.error_message or "")` for all `agent._generated_scripts` to cover the storage path surfaced in `_present_script_review` payload [tests/test_agents/test_sarah.py:3828]
- [x] [Review][Defer] `_generate_scripts` constructs `ScriptGenerator` without internal `_ensure_llm_ready` call [src/ai_qa/agents/sarah.py:416] — deferred, design choice (always reached via `_begin_generation` which already resolved; spec-approved call sites)
- [x] [Review][Defer] `handle_reject` → `_regenerate_current_script`: `PipelineError` double-wrapped through `process()`'s generic catch → garbled UX-DR12 message [src/ai_qa/agents/sarah.py:580] — deferred, spec-approved ("runs inside process()'s try/except")
- [x] [Review][Defer] `handle_reject` exception path (line 1219) sends raw `str(e)` without `_format_error_message` [src/ai_qa/agents/sarah.py:1219] — deferred, pre-existing behavior

### Change Log

- 2026-06-22: Fixed Sarah's stale empty-key LLM config (the "Could not resolve authentication method" auth failure) by resolving the config lazily against the attached project context before every generation path (mirrors Mary's `_ensure_llm_ready`); made per-test-case generation failures degrade to skip-only placeholders so a batch never leaves the Scripts folder empty; added regression + fallback + leak-canary tests. Backend suite 1794 passed.
