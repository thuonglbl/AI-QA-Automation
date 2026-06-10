# Deferred Work

## Deferred from: code review of 9-7-saved-provider-configuration-and-rotation-behavior (2026-06-10)

- `save_provider_config` has no defense-in-depth guard against accidental secret leakage [`src/ai_qa/userconfig/service.py:28`] — mirrors `secrets/service.py` pattern (caller discipline); no confirmed leak. Add assert guards when tightening AC1 cross-cutting enforcement.
- Deleted project in validity check treated as "all providers allowed" [`src/ai_qa/agents/alice.py:650`] — low real-world risk; FK constraints on commit would catch downstream failures. Handle with a proper "project not found → skip saved config" guard in a future auth/cleanup story.

## Deferred from: code review of 12-10-user-project-selection-in-alice-configuration-flow (2026-05-15)

- Conversation persistence API is not scoped to selected project [frontend/src/hooks/usePipelineState.ts:34] — pre-existing persistence architecture issue; current story already preserves existing conversation API and scopes WebSocket/start/approve/reject/navigate payloads.

## Deferred from: code review of 12-9-admin-dashboard-refinement (2026-05-15)

- Project deletion has no confirmation: deleting a project is a destructive UX action that may need confirmation/undo, but the acceptance criteria only required wiring the implemented delete API.
- Project deletion may conflict with future dependent data beyond memberships: current story scope covers projects and memberships; future artifact/testcase/report dependencies need a separate domain deletion policy.
- Admin-created password flow lacks forced reset/invite semantics: current story requires initial password creation only; invite/reset-password semantics should be handled by a broader auth policy story.

## Deferred from: code review of 1-4-shared-pydantic-models-stageresult-agentmessage (2026-04-09)

- `StageResult.data: Any|None` defeats type safety — intentional; different pipeline stages return different types. Consider TypeVar or typed subclasses when stage types are finalized.
- `success=False` but `data` populated: no validation — intentional design; partial results on failure are valid for progressive pipeline stages.
- errors/warnings as plain strings, no structured error codes — future enhancement; add structured error types (code, severity, source) when i18n or error recovery is needed.
- `ALL_AGENTS`/`ALL_STAGES` lists not enforced as validation — future stories will add validation where these constants are used in routing and dispatch logic.
- Circular import risk if `models.py` imports `exceptions.py` in future — pre-existing concern; monitor as pipeline grows; ensure models stay import-free of other ai_qa modules.

## Deferred from: code review of 1-2-configuration-system-with-pydantic-settings (2026-04-08)

- `file_secret_settings` dropped from pydantic-settings source chain — intentional per current spec; revisit if Docker/K8s secret-file injection is needed later.
- Missing negative temperature boundary test (`-0.1`) — lower-bound validation untested; expand in Story 1.5 when test infra (conftest, pytest-cov) is set up.
- URL format validation (`AnyHttpUrl`) not enforced on `on_premises_ai_server_url` — bare `str` field; add Pydantic URL type when provider validation is tightened.
- `reload(cfg)` in tests leaves module in reloaded state — proper conftest fixtures with import isolation deferred to Story 1.5.
- Malformed YAML parse error (`config.yaml` with invalid syntax) is untested — add error-handling test in Story 1.5 with full test infrastructure.

## Deferred from: code review of 1-1-project-restructure-to-src-layout (2026-04-07)

- `browser.kill()` without error handling — cleanup exception will propagate uncaught in `src/ai_qa/__main__.py`. Will be addressed in browser agent story (Epic 5).
- Non-standard env var naming with hyphens: `ON-PREMISES-AI-SERVER-URL` should use underscores per POSIX convention. Pre-existing issue from original `main.py`.
- Missing `[tool.hatch.build.targets.sdist]` config in `pyproject.toml` — sdist builds may misbehave. Not required by current story scope; address before first public release.

## Deferred from: code review of 2-3-baseagent-lifecycle-start-processing-review-done (2026-04-15)

- Missing logging level configuration [src/ai_qa/api/routes.py:30] — Logger instantiated but no configuration shown for log levels or handlers. Pre-existing issue not caused by this change.

## Deferred from: code review of 3-2-confluence-reader-pipeline-stage (2026-04-17)

- Pipeline trigger integration missing — FR10 requires stage to work as pipeline trigger. No trigger registration or pipeline integration code present. Out of scope for this story; requires separate integration work with pipeline orchestrator.

## Deferred from: code review of 3-3-content-parser-markdown-mermaid-and-images (2026-04-18)

- ReDoS risk on `.*?` with DOTALL in Confluence macro regexes [content_parser.py:127–160] — pre-existing regex pattern; mitigate when/if Confluence payloads are untrusted or from external sources.
- `warnings` local parameter shadows Python's built-in `warnings` module [content_parser.py:126] — low risk now (no `import warnings` in file); rename parameter if `warnings` module is ever imported.
- `TEST_CASE_HEADING_PATTERN` greedily captures entire document body if no subsequent `##` heading exists — complex regex edge case; defer to Epic 4 LLM-powered extraction (Story 4.2) which supersedes regex detection.
- Image format not validated — non-image file URLs in `<img src>` attributes will be downloaded; add file extension allowlist (PNG, JPG, GIF, WebP, SVG) when security posture is tightened.

## Deferred from: code review of 4-1-llm-abstraction-layer-langchain-litellm (2026-04-18)

- Timeout substring match is too broad and may cause false positives [client.py:60-61] — not required by acceptance criteria; current heuristic sufficient for internal LiteLLM proxy usage.

## Deferred from: code review of 5-2-script-generator-pipeline-stage (2026-04-19)

- No parallelism for large test suites [script_generator.py:77-91] — Sequential for-loop processes test cases one-by-one. Pre-existing architecture pattern from other pipeline stages; consider asyncio.gather or ThreadPoolExecutor when performance becomes a bottleneck.

## Deferred from: code review of 12-8-bugfix-admin-routing-and-dashboard (2026-05-14)

- Fake/Missing functional implementation for Edit, Delete, and Remove User actions — backend APIs are not implemented yet.
- Tight Coupling to Hardcoded String Roles — pre-existing architectural choice.

## Deferred from: code review (2026-05-21) - 2-9-dynamic-provider-model-discovery-and-alice-reasoning-transparency.md

- Stripped model metadata when calling LLM: Loss of detailed model information when passed to the LLM (pre-existing constraint).
- Scattered imports in code: Import statements are placed inside functions, which may cause minor performance degradation (pre-existing code style).
- Hardcoded agent names (bob, mary...): Pre-existing issue, needs to be refactored later.

## Deferred from: code review of 12-13-fix-mcp-extraction-failure-and-implement-proactive-session-cleanup (2026-05-29)

- Test Design Issues (Encapsulation, private methods, mock explosion) [tests/test_agents/test_bob.py]

## Deferred from: code review of 12-12-fix-frontend-401-unauthorized-api-calls (2026-05-29)

- Security Vulnerability (XSS) — Using localStorage instead of HttpOnly cookies for session tokens is a security risk. Pre-existing architectural choice.

## Deferred from: code review of 7-2-project-membership-access-for-standard-users.md (2026-05-31)

- Incorrect API Routes File Path [src/ai_qa/api/projects.py] - Spec mentioned api/routes/projects.py but existing code uses api/projects.py.
- Scale Boundary: Unbounded Result Sets [src/ai_qa/projects/service.py] - Fetching all records may degrade performance at scale.

## Deferred from: code review of 7-6-membership-removal-access-enforcement (2026-06-06)

- Thread-list admin scoping uses the stale session/JWT role [src/ai_qa/api/threads.py] — `get_user_threads` reads `is_admin` from the JWT/session while `assert_thread_access` reads the live DB `User.role`. A mid-session admin demotion keeps `role=admin` in the token until expiry, so the list endpoint still shows all the user's own threads. Outside 7.6's membership-removal scope; only relevant on role demotion.

## Deferred from: code review of 7-7-standard-user-workspace-shell-routing (2026-06-06)

- Undocumented `run_in_threadpool` wrapping of register/login [src/ai_qa/api/auth/local.py] — correct improvement (bcrypt is CPU-bound) but not listed in the story File List; flagged for traceability only, no correctness concern.
- Partial failure of the multi-project starter bootstrap is not self-healing for the session [frontend/src/App.tsx] — if `createThread` throws mid-loop, already-created threads aren't committed to state, `threadCreationError` blocks the effect, and ensured projects stay marked, so recovery requires a page reload. Safe (error banner shown) but degraded; low frequency.
- E2E Playwright suite not executed against a live stack [frontend/e2e/story-7-7-workspace-shell.spec.ts] — Task 7 left unchecked by dev; run a live e2e pass (running backend+frontend + admin bootstrap) before marking the epic done.

## Deferred from: code review of 9-1-encrypted-per-user-secret-storage-foundation (2026-06-07)

- Corrupt/wrong-key ciphertext is returned as plaintext by `UserSecretEncryptedString.process_result_value` and, being truthy, is used as the API key in `get_llm_config` (env fallback skipped). Pre-existing `EncryptedString` pattern; reconsider with key-rotation handling in Story 9.7. [src/ai_qa/db/types.py, src/ai_qa/agents/base.py]
- Provider lookup uses silent `PROVIDER_SECRET_TYPE_MAP.get()` (None on unknown/mis-cased provider) instead of the raising/normalizing `resolve_secret_type`, which is exported but unused. [src/ai_qa/agents/alice.py:351, src/ai_qa/agents/base.py:154, src/ai_qa/secrets/__init__.py:45]
- `set_user_secret` SELECT-then-INSERT cross-session race can raise `IntegrityError` on commit; unique constraint protects integrity. [src/ai_qa/secrets/service.py]
- `api_key` is stored unstripped while the connection test validates the stripped value (whitespace mismatch). Pre-existing. [src/ai_qa/agents/alice.py:349 vs :596]
- Module-level Fernet cache (`_user_secrets_fernet_instance`) prevents key rotation / can carry a stale key across reloads. Rotation is Story 9.7. [src/ai_qa/db/types.py]
- alice `get_on_prem_defaults` / `process` pass `user_id` without the `None` guard base.py has; latent, write path try/except-wrapped. [src/ai_qa/agents/alice.py:270,352]
- `mock_broadcast` yield-fixtures lack `Generator` typing (project rule #3); non-gating (mypy src-only). [tests/test_agents/test_alice.py, tests/test_agents/test_base.py]

## Deferred from: code review of story 9-3-provider-adapter-interface-and-connection-validation (2026-06-07)

- Sequential 4×10s endpoint probing → ~40s worst-case validation latency [src/ai_qa/ai_connection/providers/openai_compatible.py:_probe]. Pre-existing sequential-probe pattern; perf, not correctness. Consider parallel probing or a shorter per-endpoint timeout.
- 8-char key floor blocks genuinely keyless on-prem/no-auth deployments [src/ai_qa/ai_connection/providers/openai_compatible.py:validate_connection]. Pre-existing Alice behavior + spec-mandated format floor; revisit if no-auth on-prem support is required.

## Deferred from: code review of stories 9-4 & 9-5 (2026-06-09)

- Inconsistent agent key casing — `_assign_fallback_models` uses capitalized keys; `_assign_models_via_llm` uses lowercase. Fragile cross-consumer contract. [src/ai_qa/agents/alice.py] — deferred, pre-existing
- Duplicate comment in E2E spec — copy-paste artifact, no functional impact. [frontend/e2e/story-9-4-dynamic-model-discovery.spec.ts] — deferred, cosmetic
- Promise.race dangling locator watches — Playwright test may leak unresolved `waitFor` promises. [frontend/e2e/story-9-4-dynamic-model-discovery.spec.ts] — deferred, pre-existing
- `role→sender` rename without migration — schema evolution belongs in dedicated migration story. [src/ai_qa/threads/models.py] — deferred, pre-existing
- `conversation_data` removal without migration — existing threads lose conversation history. [src/ai_qa/threads/models.py] — deferred, pre-existing
- `enabled_providers` JSON column no DB constraint — data integrity nice-to-have. [src/ai_qa/db/models.py] — deferred, pre-existing

## Deferred from: code review of story 9-6 (2026-06-10)

- process() MCP failure doesn't disconnect client — Pre-existing: if `connect()` fails, `finally` block is in wrong try scope. [src/ai_qa/agents/bob.py:169-193] — deferred, pre-existing
- Redundant db/project re-read in _extract_descendants — Project fetched again inside extraction loop. Minor perf, pre-existing pattern. [src/ai_qa/agents/bob.py:349-355] — deferred, pre-existing

## Deferred from: code review of 10-1-project-artifact-storage-foundation (2026-06-10)

- `thread_id` column + `_validate_thread` are foundation-only — no production caller passes `thread_id` (the create API has no such field; the pipeline adapter omits it), and `_validate_thread` only checks project match, not `agent_run.thread_id == thread_id` when both are supplied. [src/ai_qa/artifacts/service.py:227] — deferred, intended foundation for Story 10.2; wire a real caller + add the run↔thread consistency check there.
- `created_by_user_id`/`updated_by_user_id` are stamped from `owner_user_id` with no project-membership validation at the service layer (unlike `_validate_thread`/`_validate_agent_run`). [src/ai_qa/artifacts/service.py:64] — deferred, defense-in-depth; the only current writer (create API) already passes an authorized member via `ProjectAccessDependency`.
- `create_version` unconditionally sets `updated_by_user_id = created_by_user_id`, so a caller passing `None` wipes a previously-known updater. [src/ai_qa/artifacts/service.py:136] — deferred, not reachable with None from the current API path.
- Migration is not SQLite-batch-safe: `op.create_foreign_key`/`op.drop_constraint` are unsupported on SQLite without `render_as_batch=True` in `env.py`. [alembic/versions/604f28c24393_add_artifact_ownership_and_thread_.py] — deferred, production target is PostgreSQL and tests build schema via `metadata.create_all`, not Alembic.
