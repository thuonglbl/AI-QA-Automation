# Deferred Work

## Deferred from: code review of skip-testcases-reuse-existing (2026-06-24)

- [LOW, cosmetic] The pipeline stepper marks Mary (step 3) as a green "completed" dot after a blank-id skip routes 2→4, because the stepper is purely positional (`idx + 1 < currentStep`) in `frontend/src/App.tsx` (step-dot renderer) and `usePipelineState.ts` `completedSteps = currentStep - 1`. A skipped stage looks identical to a run-and-completed stage. Fixing properly needs a real "skipped" state in the step model — out of scope for this change.
- [LOW–MED UX] Blank-id skip with ZERO approved test cases project-wide routes the user to Sarah, which correctly blocks at its AC3 "no approved test cases" message and stays START — but there is no in-thread back-navigation to reach Mary (a pre-existing UI limitation), so the user must start a new thread. The spec's "Ask First" boundary explicitly chose to rely on Sarah's existing AC3 block rather than add a Bob-side guard or new flow, so this is recorded rather than fixed. Revisit if/when back-navigation is added.

## Deferred from: code review of 16-12-fix-sarah-browser-use-chrome-driven-script-generation (2026-06-22)

- `_generate_scripts` constructs `ScriptGenerator(llm_config=self.config)` without calling `_ensure_llm_ready` internally — works correctly in production (always reached via `_begin_generation` which already resolved); design choice per spec call-site list. [src/ai_qa/agents/sarah.py:416]
- `handle_reject` → `_regenerate_current_script`: `PipelineError` from `_ensure_llm_ready` propagates through `process()`'s generic catch → `errors=["Failed to generate scripts: {PipelineError msg}"]` → double-wrapped by `_format_error_message` in handle_reject — garbled UX-DR12 message; spec-approved design ("runs inside process()'s try/except"). [src/ai_qa/agents/sarah.py:580]
- `handle_reject` exception path (line 1219) sends `f"Failed to regenerate script: {e}"` directly without `_format_error_message` — pre-existing behavior unrelated to this story. [src/ai_qa/agents/sarah.py:1219]

## Deferred from: code review of Epic 15 stories 15-1 through 15-5 (2026-06-21)

- [15-1] Downgrade migration fills `confluence_base_url = ''` for NULL rows — by design (mirrors f3a9c8b21d47); `normalize_links` converts `""` → `None`; rarely executed path.
- [15-3] `DuplicateUserError` catch branch in `create_user` is dead code — pre-existing; auth service raises `DuplicateUserError` only from `create_user_from_form`, not from ORM model construction.
- [15-4] No test for unknown/`other` role in sort comparator — `?? 3` fallback is correct; unknown roles impossible in current user model.
- [15-4] Status badge test checks text only, not icon — impractical to test SVG icons in JSDOM/Vitest; text verification satisfies AC3 accessibility intent.
- [15-5] `project_admin → project_admin` same-role update silently ignores `project_id` — not covered by AC2 ("role change between project_admin and standard"); alternative via existing membership endpoints.
- [15-5] `cancelEditingUser` does not reset `editUserRole`/`editUserTimezone`/`editUserIsActive` — stale values not visible (guarded by `editingUserId === null`); `startEditingUser` resets all before re-display.
- [15-5] N+1 queries on `create_user`/`update_user` response: `_to_admin_user_response` accesses `membership.project.name` without `selectinload` — performance, not correctness; admin-only + low volume.
- [15-5] Self-deactivation guard in `update_user` / self-delete guard in `delete_user` are dead code (immutability guard fires first) — defense-in-depth for future multi-admin design; 403 behavior tested via immutability guard.
- [15-5] `_to_admin_user_response` would `AttributeError` if `membership.project` is `None` — theoretical; `ondelete=CASCADE` prevents orphan memberships.
- [15-5] No test for demoting project_admin with mixed-role memberships (verifying non-`project_admin` rows survive) — correct behavior by design; filter-delete targets only `role == project_admin` rows.
- [15-5] No confirmation dialog before `handleDeleteUser` — UX enhancement; same pattern as `handleDeleteProject` (pre-existing).
- [15-5] No project picker for existing project_admin (cannot re-assign to a different project via the UI) — out of scope for AC2; alternative via membership endpoints.
- [15-5] `AdminUserUpdateRequest` model validator does not require `project_id` for standard→project_admin transition — design decision; endpoint runtime check is correct.
- [15-5] No test for promoting a standard user with an existing non-`project_admin` membership on the target project — idempotent upsert by design (per dev notes; avoids `uq_project_memberships_project_user` IntegrityError).

## Deferred from: code review of Epic 14 + project-admin RBAC (2026-06-21)

- ✅ RESOLVED 2026-06-21 — [HIGH, pre-existing] Unauthenticated E2E report file server — `GET /admin/tests/e2e/report/view/{file_path}` [src/ai_qa/api/admin.py:634-661] had no auth dependency (sibling `download_e2e_report` requires admin) and was explicitly whitelisted public in `AuthMiddleware.PUBLIC_PATHS` [src/ai_qa/api/auth/middleware.py:47]. Path-traversal was guarded, but any unauthenticated caller could read the entire `playwright-report/` directory (Playwright traces, screenshots, request/response data, and app URLs captured during E2E runs against real DB projects). Verified pre-existing — NOT introduced by the Epic 14 changeset. **Fix applied:** added `_admin: User = AdminDependency` to `view_e2e_report` + removed `/api/admin/tests/e2e/report/view` from `PUBLIC_PATHS` (report opens in a browser tab, authenticates via the session cookie). The route-level dependency is the sole guard for static-suffixed report assets (`.png`/`.js`/`.css`) that bypass the middleware `is_static` rule. Negative test: `tests/api/test_admin_rbac_api.py::test_e2e_report_view_requires_admin`. Gate green (ruff/format/mypy clean, 1711 passed). Full triage: `code-review-findings-2026-06-21.md` (W1).

## Deferred from: code review of fix-cross-thread-conversation-bleed (2026-06-18)

- Project-only (no-`threadId`) conversation no longer auto-restores agent panels [frontend/src/App.tsx history-restore effect] — the restore effect was re-keyed from `selectedProject?.id` to `loadedThreadId`, which is null on the legacy `/projects/{id}/conversation` load branch. Chat text restores but Alice/Bob/Mary/Sarah panels won't replay for a project-only load. Dormant: the app bootstraps exactly one starter thread per project, so an active conversation always has a `threadId`. Generalizing to a combined `threadId ?? projectId` key was rejected here because it would reintroduce the stale-`isLoaded` read race the thread-keyed design avoids. If the project-only path is ever revived, expose a race-free `loadedKey` from `usePipelineState` set on both load branches.
- Cross-project thread switch double-fetches `GET /threads/{id}` [frontend/src/hooks/usePipelineState.ts load effect deps `[projectId, threadId]`; frontend/src/App.tsx:503 passes `projectId: selectedProjectId`] — on a cross-project switch `threadId` changes a render before `selectedProjectId` catches up, so the load effect runs twice (stale then fresh projectId). Correct (thread branch ignores projectId; `cancelled` guard prevents stale hydration) but redundant. Pre-existing, not introduced by this fix. Collapse to one fetch by passing `activeProjectId` (derived synchronously from the active thread) or dropping `projectId` from the thread-branch deps.

## Deferred from: code review of 11-2-bob-confluence-url-intake-and-pipeline-trigger (2026-06-12)

- Capability checks added to `handle_start` violate spec — The diff adds an MCP capability check block before `transition_to(PROCESSING)` that decrypts secrets and connects to MCP, violating the explicit "Do NOT" rule for `handle_start`. — deferred (Reason: chưa cần thiết lúc này)

- Frontend Jira input block is copy-pasted verbatim — deferred, pre-existing (UI component refactor out of scope).
- Out-of-scope Quality Detection code leaked — deferred, pre-existing (Story 11.5 code `_detect_quality_issues`, `_run_quality_detection`, `_has_quality_warnings` merged early).
- `_load_project` uses lazy import inside instance method — deferred, pre-existing.

## Deferred from: code review of 10-2-artifact-list-and-empty-folder-browsing (2026-06-11)

- Pagination page not reset on equal-length item swap [frontend/src/components/conversations/ProjectSidebar.tsx:95] — `SubFolder`'s `useEffect(() => setPage(1), [items.length])` misses content swaps where the item count is unchanged (e.g. a realtime add+delete in the same refresh window), leaving the user on a stale page. Pre-existing `SubFolder` behavior, not introduced by this story. Re-key the effect on item identity (e.g. a join of ids) when hardening realtime pagination.
- Frontend silently drops backend folder names absent from `FOLDER_CONFIG` [frontend/src/components/conversations/ProjectSidebar.tsx:455] — `renderArtifactFolder` returns `null` for any folder name not in `FOLDER_CONFIG`. Dormant today (backend `browse_order` keys match the frontend config exactly) but reintroduces the "silent drop" class this story fixed if the backend later adds a 5th browse folder without a matching frontend entry. Add a shared source of truth or a visible fallback bucket.

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

## Deferred from: code review of 11-7-requirements-artifact-save (2026-06-12)

> Most items below belong to Story 11.8 / decision D8 (single-artifact-per-page), whose code was merged into the 11.7 working tree during review. Flag them to the live 11.8 dev process.

- Side-car `save_metadata` is not deduped — duplicate `configuration` metadata rows accumulate on retry/re-approve while `save_requirement` (D8) dedupes the requirement. [src/ai_qa/agents/bob.py:1153] — deferred to 11.8
- No `"deleted"` change event for the dedupe-removed row — realtime artifact-sync clients may keep a stale entry; `delete_artifact` emits no event. [src/ai_qa/pipelines/artifact_adapter.py:97] — deferred to 11.8
- `not_requirement` skip leaves the orphan draft — `delete_draft_requirement` runs only on the approved branch, so a skipped page keeps its `{page_id}.md` draft, violating D8's one-artifact-per-page intent. [src/ai_qa/agents/bob.py:1128-1152] — deferred to 11.8
- No test for D8 dedupe / re-approval / the zero-approved-row window — the existing AC3 failure test makes `save_requirement` itself raise (before any commit), so the post-delete-commit failure path is uncovered. — deferred to 11.8
- `output_files_saved` count drift — re-approving an already-resolved page increments the counter again (can exceed the unique page count); an all-skipped run hands "Saved 0 approved requirements" to Mary. [src/ai_qa/agents/bob.py:1165,1183] — deferred
- `source_type` defaults to `"confluence"` when the page dict lacks it (mislabels a Jira-origin page that lost its type); `source_url` is persisted as `""` not NULL. Spec-sanctioned defensive default — revisit only if a source can legitimately lack `source_type`. [src/ai_qa/agents/bob.py:1139-1140] — deferred
- `source_type` `String(50)` has no length guard — an over-long value fails at PostgreSQL commit (handled as a save failure) but passes SQLite tests. [src/ai_qa/db/models.py:152] — deferred
- `warnings=[]` vs NULL semantic untested on Postgres — the `[]`=approved-no-issues vs NULL=draft distinction is load-bearing and only verified on SQLite. [src/ai_qa/db/models.py:154] — deferred
- Duplicate `page_id` in `self.pages` breaks the DONE invariant (`len(_resolved_page_ids) >= len(self.pages)` can never be reached). [src/ai_qa/agents/bob.py:1183] — deferred

## Deferred from: code review of 11-8-technical-debt-sweep-and-hardening (2026-06-12)

> D6/CI (non-functional) is a Decision-needed item in the 11.8 story, not deferred. The items below are the LOW-severity deferrals.

- D2 AdminDashboard timer test deviates from the prescribed Vitest fake timers to a `window.setTimeout` spy that hard-codes the component's `delay === 3000` and asserts the callback effect rather than the timing boundary. Functional + deterministic + component untouched, but a maintainability/spec-deviation smell. [frontend/src/components/admin/AdminDashboard.test.tsx:169-206] — deferred
- `test_coverage_tracking_active` asserts only that pytest-cov is loaded (`hasplugin("pytest_cov")`), not that coverage is enforced — passes even under `--no-cov`; the test name overstates the guarantee. [tests/unit/test_infrastructure.py:73-77] — deferred
- Latent test-ordering flakiness: `test_broadcast_artifact_change_filtered_by_project` + `test_websocket_connection_invalid_uuid` failed in one adversarial full-suite run but pass in isolation and in the canonical run (1188 passed). Possible shared-state leak exposed by D4's collection-order change; CI-flake risk, not a hard red. [tests/api/test_artifact_events.py] — deferred
- D7 story-10-7 comment fixes are source-accurate and behaviour-preserving but remain uncommitted (whole Epic-11 tree is uncommitted); the DoD "E2E fixes committed" claim is unmet. No behavioural risk. [frontend/e2e/story-10-7-artifact-refresh.spec.ts] — deferred

## Deferred from: code review of spec-fix-stuck-thread-startup-recovery (2026-06-22)

- Startup reconciliation (`reconcile_interrupted_work`) is global/unscoped — only safe for a SINGLE app worker. Current deployment IS single-worker (Dockerfile.backend:69 runs one uvicorn; local `--reload` fully joins the old worker before booting the new), so it is safe today. Under `--workers N` or multiple replicas sharing one DB, a booting worker would reset another live worker's `processing`/`running` rows. An `updated_at` age-filter is NOT a valid fix (a legitimately long on-prem LLM call has a stale `updated_at` and would be falsely reset) — needs a per-worker lease/heartbeat before multi-worker is adopted. [src/ai_qa/threads/service.py reconcile_interrupted_work] — deferred (becomes High if multi-worker is ever adopted)
- Recovery is only visible after a manual page reload — the reconciler updates the DB but does not push a status/refresh event over the WebSocket, and `useWebSocket` reconnect does not re-fetch thread state. A user watching the spinner when the worker dies keeps seeing it (or a reconnect notice) until reload. Consider re-reading thread status on WS (re)subscribe or emitting a recovery event. [frontend/src/hooks/useWebSocket.ts, usePipelineState.ts] — deferred (Medium)
- `invoke_vision` reuses the full `config.timeout` (600s) as its per-call bound, so a page with N images against a stalled vision endpoint can serialize N×up-to-600s within one extraction step. Give vision a shorter dedicated ceiling and/or a cumulative per-page caption budget. [src/ai_qa/ai_connection/client.py invoke_vision] — deferred (Low)
- `wait_for`-cancelled `ainvoke` may not eagerly close the shared httpx connection (pool leak under repeated timeouts). Pre-existing pattern (Bob's clarify loop does the same); httpcore generally closes on cancellation. Revisit if timeout frequency rises. [src/ai_qa/ai_connection/client.py, src/ai_qa/pipelines/requirement_formatter.py] — deferred (Low)

## Deferred from: code review of spec-sarah-stageresult-warnings-cap (2026-06-23)

- `ScriptGenerator.generate()` partial-success can construct an invalid `StageResult` — `success = len(generated_scripts) > 0 or not errors` yields `success=True` when SOME test cases generate AND some fail (each failure appends to `errors` at lines 177/182). The `StageResult` model_validator then raises `ValueError("success=True but errors list is not empty …")`. PRE-EXISTING and NOT caused by the warnings-cap change (bounding preserves emptiness, so it neither causes nor cures this); the spec's "Never" clause explicitly scoped it out. NOT triggered in the live Sarah flow because Sarah calls `generate()` with a SINGLE test case per iteration (sarah.py:448-449), so `generated_scripts` and `errors` are mutually exclusive there. Fires only if `generate()` is ever called with a multi-item `test_cases` list that partially fails. Fix idea: make the success rule consistent with the validator (`success = bool(generated_scripts) and not errors`) OR mirror Sarah's design and route per-item failures to `warnings` instead of `errors`. [src/ai_qa/pipelines/script_generator.py:198-206] — deferred (Medium; becomes real if a multi-test-case caller of generate() is added)
- Helper hardening (Low, optional): `bound_stage_messages` is safe for all reachable inputs (both call sites use the default `limit=100`; output is always ≤ limit, dedupe is order/first-occurrence preserving). Only a theoretical `limit=0` with non-empty input is unsafe (negative slice `deduped[:-1]`), and it is unreachable today. A `limit >= 1` guard or `max(0, limit-1)` slice would harden it if the helper is ever reused with a custom limit. [src/ai_qa/models.py bound_stage_messages] — deferred (Low)

## Deferred from: code review of spec-bob-resume-continue-extraction (2026-06-23)

- Continue button visibility is gated on a *persisted message* (`metadata.resume_available`) rather than live `bob_resume_parent` state. A stale resume message from an earlier interruption can therefore render the button when the column has since been cleared (e.g. the thread was later interrupted during the clarify/select-id phase, where `bob_resume_parent` is already `None`, so reconcile adds no new flag but the OLD flagged message survives in history). Clicking then hits `_handle_resume` → no persisted parent → a friendly "There is no interrupted extraction to continue" error (the BE safety net). A precise FE gate would need the live column on the thread payload, which the spec's "Never expand the Thread API/TS type" boundary deliberately precludes — so the friendly BE error is the accepted trade-off. [frontend/src/App.tsx Continue-button gate; src/ai_qa/agents/bob.py `_handle_resume`] — deferred (Low)
- Repeated mid-extraction interruptions append one `resume_available` system message per reconcile pass (the exact targeted scenario — a slow batch restarted more than once). `messages.some(...)` still renders a single Continue button, but the chat shows N stacked identical "interrupted… Click Continue" warnings with no dedupe. Cosmetic. Fix idea: skip adding a new reconcile message when the most recent one already carries `resume_available`. [src/ai_qa/threads/service.py reconcile_interrupted_work] — deferred (Low)
- A resume whose extraction FAILS (parent persisted but `_extract_descendants` errors, e.g. a Confluence re-fetch failure) falls into `handle_approve`'s ERROR branch → thread `status="error"`. Both the intake form and the Continue button are gated on `status==="start"`, so neither affordance renders on reload until the next reconcile re-resets to `start`. `bob_resume_parent` is correctly left set (not cleared on failure), so the run stays resumable, but the user has no in-UI path back within that session. Spec I/O matrix wording ("stay at start, intake form still usable") is not literally met for the extraction-failure sub-case. Pre-existing ERROR-state behavior reused by the resume path. [src/ai_qa/agents/bob.py handle_approve error branch; frontend/src/App.tsx status gating] — deferred (Low)

## Deferred from: review of Bob version-based change-detection (2026-06-23)

> Change-detection (store Confluence `version` per page in the sidecar; reuse only when unchanged, else re-extract+override) + parent-node-shows-real-title. Implemented sidecar-only (no migration). All items below are Low and were verified safe by the adversarial review.

- Legacy artifacts saved BEFORE this change have no `source_version` in their sidecar, so `prior_v` is None → they are re-extracted once on the first run after deploy to establish a version baseline (then reused thereafter). One-time LLM cost, safe; not a bug. [src/ai_qa/agents/bob.py `_extract_descendants` saved_version load] — deferred (Low)
- Perpetual re-extract when Confluence reports NO version: `_save_page_version` early-returns on `version is None`, so such a page never stores a version and never satisfies the reuse guards → re-converted by the LLM every run, with no content-hash fallback. Real Confluence pages are always versioned, so rare; Epic 18's `content_hash` is the proper long-term fallback. [src/ai_qa/agents/bob.py `_save_page_version`; confluence_reader `_extract_version`] — deferred (Low)
- The cheap no-fetch fast-path (reuse via `summary.version` from the listing) is inert for DESCENDANTS: `confluence_search` rejects the `expand` param, so search-listed children carry no version → they always fall to the per-page `read_page_by_id` fetch, after which the version check still reuses the saved content (the expensive LLM convert IS still skipped). So the goal holds; only the cheap fetch-skip optimization is lost for descendants (the prepended parent is fetched anyway). [src/ai_qa/pipelines/confluence_reader.py get_children_by_id / get_descendants_by_title] — deferred (Low)
- Version-extraction asymmetry: the new listing helper `_extract_version` coerces with `int()` and returns None on failure, while `read_page_by_id`/`read_page_by_url` pass the raw value into `ConfluencePage(version: int|None)` relying on Pydantic — a non-numeric version (e.g. `"rev-5"`, which Confluence never emits) would raise a ValidationError that aborts the whole run instead of degrading to unknown-version. Pre-existing; now load-bearing since version drives control flow. Fix idea: coerce in the readers too. [src/ai_qa/pipelines/confluence_reader.py read_page_by_id version assignment] — deferred (Low)

## Deferred from: review of artifact missing-blob resilience (2026-06-25)

> Fix made artifact loaders skip+log an artifact whose backing storage object is missing (spec `spec-artifact-missing-blob-resilience.md`). All items below are Low and were verified safe by the adversarial review.

- Observability gap: if the storage backend is wholesale-misconfigured/unmounted (wrong bucket/prefix, volume gone), EVERY artifact raises `StorageObjectNotFoundError` and `_load_text_artifacts` returns an empty list with only N WARNING log lines — indistinguishable from a legitimately-empty project. No error/alert is surfaced, so an operator could miss a corrupted storage volume. By design for this fix (the boundary is skip+log to unblock Bob), but a "many/all artifacts missing" heuristic that escalates to an error/metric would harden it. [src/ai_qa/pipelines/artifact_adapter.py `_load_text_artifacts`] — deferred (Low)

## Deferred from: code review (2026-06-25)
- Un-normalized Email Insertion in create_user [src/ai_qa/api/admin.py]: create_user saves equest.email without 
ormalize_email. Might fail SSO logins. (Pre-existing issue, unrelated to password removal story).
