# Code Review Findings — Epic 14 (Jack Test Execution) + Project-Admin RBAC / Credentials

- Date: 2026-06-21
- Scope: full uncommitted working tree (Epic 14 stories 14.1–14.6 + project-admin RBAC + credentials/sessions), ~12,600 diff lines across ~73 files.
- Method: adversarial multi-lens review (14 file-group units + 6 cross-cutting sweeps), each finding verified against the real code (refute-by-default), then a completeness critic. 84 agents. 51 confirmed / 11 refuted. Deduplicated here to ~36 unique issues.
- Severity reflects the verifier's corrected severity, not the reporter's.

## Status: all 32 patches APPLIED + verified (2026-06-21)

All 4 decision-needed items were resolved into patches and all 32 patches were applied to the working tree (still uncommitted — Thuong commits + runs `alembic upgrade head` himself). W1 (pre-existing, was out of scope) is now **RESOLVED 2026-06-21** — see the W1 section below. Verification after applying:

- Backend: `ruff check` ✓, `ruff format` ✓, `mypy src` ✓ (95 files), `pytest` **1710 passed** (+9 new tests), single alembic head `c5b1e9a4d762`.
- Frontend: `tsc` ✓, `eslint` ✓ (0 warnings), `vitest` **344 passed**, `vite build` ✓.
- Added dependency: `pytest-timeout` (D2).

## Triage summary

| Bucket | HIGH | MED | LOW | Total |
| ------ | ---- | --- | --- | ----- |
| decision-needed | 1 | 2 | 1 | 4 → all resolved into patches (2026-06-21) |
| patch | 5 | 10 | 17 | 32 |
| defer | 1 | 0 | 0 | 1 |
| dismiss | — | — | — | 0 (+11 refuted by the workflow) |

### Decisions resolved (2026-06-21)

- **D1** → FE decodes the JSON `/content` payload and builds `data:<mime>;base64,<content>`, mirroring `ArtifactPreview.tsx`. (now a patch)
- **D2** → wire `pytest-timeout` through (`execution_timeout` → `run_scripts` → `build_pytest_command --timeout`). (now a patch)
- **D3** → FE-only: surface a clear "configure a project environment to run" message when in free-URL mode; do NOT relax the run gate. (now a patch)
- **D4** → drop `started_at`/`ended_at` from `db/models.py` and edit the uncommitted migration `a3f8d21c64b9` in place. (now a patch)

---

## DECISION-NEEDED (resolve first — the fix depends on your intent)

### D1 — [HIGH] Attachment rendering is broken: screenshot/trace/log URLs point at the JSON content endpoint

- Files: `frontend/src/components/agents/ExecutionResultDetail.tsx:11-13,89-131`; consumes `src/ai_qa/api/artifacts.py:352` (`read_artifact_content`, `response_model=ArtifactContentResponse`).
- `contentUrl()` returns `/projects/{p}/artifacts/{id}/content`, fed straight into `<img src>`, `<a href download>`, `<iframe src>`. That endpoint returns JSON `{content, content_encoding}` (binary is base64 inside the string), NOT raw bytes — so screenshots render broken, the trace "download" yields a JSON file, the log iframe shows JSON. The whole 14.6 attachment drilldown is non-functional in a real browser; Vitest masks it (jsdom never loads `<img>`). (#6, #48)
- **Decision:** (a) FE fetches the JSON via `apiFetch` and builds `data:<mime>;base64,<content>` (mirror the existing `ArtifactPreview.tsx` pattern — recommended, established in-repo), OR (b) add a dedicated raw-bytes streaming endpoint with correct `Content-Type` (cleaner for large trace zips, but new BE surface + must auth via session cookie since raw `<img>`/`<iframe>` don't carry the bearer header).

### D2 — [MED] Per-script execution timeout was specified but not implemented; `execution_timeout` config is dead

- File: `src/ai_qa/pipelines/script_runner.py:206-250,454-468`; dead config at `src/ai_qa/config.py:194`.
- Story 14.2 Decision #6 mandates BOTH a per-script timeout AND the wall-clock cap; only the wall-clock cap exists. `AppSettings.execution_timeout` (default 120s) is referenced nowhere in `src`, and `pytest-timeout` is not a dependency. One hung test (outside Playwright's 30s per-action default) consumes the entire 900s wall-clock budget, starving remaining scripts. (#19)
- **Decision:** (a) wire it through — add `pytest-timeout`, thread `execution_timeout` → `run_scripts` → `build_pytest_command` as `--timeout`; OR (b) deliberately defer — delete/relabel the misleading dead config and add a deviation note to 14.2 Completion Notes.

### D3 — [MED] Free-URL Jack run dead-ends with no feedback (and is structurally non-runnable server-side)

- File: `frontend/src/components/agents/JackInputSelection.tsx:181-187,326-332`; backend `src/ai_qa/agents/jack.py:533` (`_resolve_session` requires a non-empty environment).
- When a project has no configured environments (free-URL mode), `environmentName === ""` short-circuits the per-role session gate so `canRun` is always false and the explanatory text (gated on `!!environmentName`) is hidden — the Confirm button greys out with zero explanation. Captured sessions are keyed by (environment, role), so free-URL is also non-runnable on the backend today. (#14)
- **Decision:** (a) support free-URL runs (needs a backend session-resolution design change), OR (b) keep it unsupported but surface a clear "configure a project environment to run" message (FE-only).

### D4 — [LOW] `started_at` / `ended_at` columns are dead (never written, never read)

- File: `src/ai_qa/db/models.py:390-391` + migration `a3f8d21c64b9`; Jack's `_persist_results` (`jack.py:621-637`) only sets `duration_ms`; the runner's `TestResult` has no per-test start/end. (#44)
- **Decision:** (a) populate from real per-test timing (runner → `_persist_results` → API → TS), OR (b) drop both columns from the model + migration (it's uncommitted — edit in place).

---

## PATCH (fix is unambiguous)

### HIGH

- **P1 — [HIGH] Execution-history date filter crashes (HTTP 500) on PostgreSQL.** `src/ai_qa/api/executions.py:80-86,173-176`. `_parse_date` returns a naive `datetime.fromisoformat()`; `summary.created_at` is `DateTime(timezone=True)` (tz-aware on Postgres) → `TypeError: can't compare offset-naive and offset-aware`. The whole 14.6 AC3 date filter is broken in prod; SQLite (tests) strips tzinfo and masks it. Fix: normalize parsed bounds to UTC-aware in `_parse_date`; also fix the `datetime.now()` naive fallback at `:116` to `datetime.now(UTC)`; make `date_to` inclusive of the selected day (compare `.date()` or `+ timedelta(days=1)`); add a regression test that exercises the aware path (not SQLite-maskable). (#1/2/3/5/24/28/29 + test-gap #10/21)
- **P2 — [HIGH] Attachment key omits role → cross-role collision / data loss.** `src/ai_qa/pipelines/execution_report.py:21-22`, `src/ai_qa/agents/jack.py:780`, `frontend/src/components/agents/JackExecutionReport.tsx:148`. The map is keyed `f"{test}::{browser}"`; in a role-grouped run two results with the same test+browser under different roles overwrite each other (last-write-wins) and the FE mis-attributes attachments. Fix: include role in the key byte-identically on all three sites; add a two-roles-same-test regression test. Also surface role in the report.md table, report.json, and the FE detail header. (#4 + #33/#39/#47)
- **P3 — [HIGH] Runner subprocess env is a secret denylist, not the spec'd allowlist.** `src/ai_qa/pipelines/script_runner.py:322-358`. `build_subprocess_env` copies all of `os.environ` minus name-matched secrets; `DATABASE_URL` (embeds `<user>:<pass>`) and `SEAWEEDFS_ACCESS_KEY` match no token and leak into the subprocess running LLM-generated Playwright code. The docstring even claims "only APP_BASE_URL + run flags". Fix: switch to an allowlist (PATH/SystemRoot/TEMP + APP_BASE_URL + run flags); add a leak test; optionally extend `scrub_secrets` to redact `<scheme>://<user>:<pass>@<host>`. (#9)
- **P4 — [HIGH] `password_login` passes `sensitive_data` without locking `allowed_domains`.** `src/ai_qa/browser/password_login.py:172-185`. The flat `sensitive_data={placeholder: password}` form is the "expose to all domains (legacy)" form; with no `allowed_domains`, browser-use can type the real password into a password field on any redirected origin (SSO/IdP). browser-use itself logs the ☠️ warning for this config. Fix: derive host from `login_url`, set `BrowserProfile(allowed_domains=[host])` and the domain-scoped `sensitive_data={host: {placeholder: password}}`. (#8)

### MEDIUM

- **P5 — [MED] Jack has no `handle_reject` → a reject re-runs scripts UNAUTHENTICATED.** `src/ai_qa/agents/jack.py` (no override). Falls through to `BaseAgent.handle_reject` → `process()` with stale `confirmed_scripts`/`_target_url` but cleared sessions → `run_scripts(storage_state=None)`, bypassing the AC3 session hard-block. Not reachable from today's UI (no step-5 reject control) but reachable via crafted WS/HTTP. Fix: override `handle_reject` to re-present input selection + defense-in-depth session-None check inside `process()`. (#16)
- **P6 — [MED] `use_vision=True` ships login-page screenshots to the LLM provider.** `src/ai_qa/browser/password_login.py:184`. The placeholder protects only the prompt text; vision sends pixels — the username (always plaintext) is sent every run; the password conditionally (show-password toggle, error echo). Fix: `use_vision=False` for the scripted auto-login (mirror `explorer.py`'s param); correct the docstring's absolute "never sent to the LLM" claim. (#17)
- **P7 — [MED] Target-URL embedded credentials leak into the persisted, user-visible report + metadata.** `src/ai_qa/pipelines/script_runner.py:483`. `urlsplit(base_url).netloc` keeps `user:pass@host`; it lands in `base_url_host` → report.md ("Environment host"), report.json, and `AgentRun.execution_metadata`, plus raw `APP_BASE_URL` in the subprocess. Fix: use `.hostname` (+ port), sanitize `APP_BASE_URL`; add a leak test. (#18)
- **P8 — [MED] `encrypted_password` `String(512)` overflows on Postgres for long passwords.** migration `b2f5c9d81a34:32`, `src/ai_qa/db/models.py:129`. The varchar holds the Fernet ciphertext (~780 chars for a 512-char plaintext); the API allows `max_length=512` plaintext → `StringDataRightTruncation` on Postgres past ~290 chars. Fix: make it Text-backed (mirror `captured_sessions.encrypted_storage_state`); edit the uncommitted migration in place. (#11)
- **P9 — [MED] project_admin can remove their own (last) administering membership and self-lock-out.** `frontend/src/components/admin/ProjectAdminDashboard.tsx:443-467`, `src/ai_qa/api/projects_admin.py:250-268`. The members list renders an unconditional × on every row incl. the caller's own project_admin row; removal returns 403 on every later call. Fix: FE hide/disable remove on own/last-project_admin row + confirm dialog; BE reject self/last-project_admin removal; negative test. (#13)
- **P10 — [MED] Auto-capture blocks the asyncio event loop during browser teardown.** `src/ai_qa/browser/password_login.py:329,354-363`. Sync `subprocess.Popen` + `proc.wait(timeout=10/5)` in the `finally` of an `async def` reached from `POST /sessions/auto-capture` freezes all requests for up to ~15s on a hung teardown. Fix: `asyncio.create_subprocess_exec` + `await proc.wait()`, or wrap teardown in `asyncio.to_thread`. (#12/#26)
- **P11 — [MED] browser-use fallback reports success even when the LLM never logs in.** `src/ai_qa/browser/password_login.py:186-193`. `agent.run(max_steps=15)` doesn't raise when it stops without authenticating; the only backstop (`_ensure_authenticated`) false-positives on any pre-auth/CSRF cookie. A failed login is stored as a valid session, failing confusingly later in Sarah/Jack. Fix: inspect the returned `AgentHistoryList` (`is_done()`/final url) and raise a credential-free `PasswordLoginError`. (#15)
- **P12 — [MED] Test-gap: FE per-role session hard-block (Slice 6) has zero coverage.** `frontend/src/components/__tests__/JackInputSelection.test.tsx`. `makeEntry` never sets `role`; `involvedRoles`/`missingRoles`/role-badge logic (the UI guard on a credential boundary) is untested. Fix: add per-script-role + mixed-role + badge cases. (#20)
- **P13 — [MED] Test-gap: required leak-canary test for the report composer is missing.** `tests/pipelines/test_execution_report.py`. Story 14.5 marks the leak-canary tasks `[x]` but no test feeds a secret-shaped token through `error_message`/`stack_trace` and asserts absence in report.md / report.json. Fix: add the canary test; reconcile the over-claimed story tasks. (#22)

### LOW

- **P14 — [LOW] `datetime.now()` naive fallback** at `executions.py:116` — fold into P1.
- **P15 — [LOW] `date_to` off-by-one (excludes the selected end day)** — fold into P1. (#28/#29)
- **P16 — [LOW] Duplicate index on `project_accounts.project_id`.** migration `b2f5c9d81a34:48-51` + `db/models.py:118,122` create two identical single-column indexes (copy-paste collapse from `captured_sessions`' composite). Fix: keep one. (#40/#41)
- **P17 — [LOW] N+1 in `list_executions`.** `executions.py:105-133,170`. ~2R queries (per-run `db.get(AgentRun)` + report-artifact lookup). Fix: batch-load run + report-artifact maps with `IN (...)`. (Perf cleanup, not a convention violation as originally framed.) (#42/#43)
- **P18 — [LOW] `upsert_project_account` has no `IntegrityError` handling** for the concurrent first-create race; sibling `add_project_member` does. `projects_admin.py:286-341`. Fix: mirror the try/except → rollback → re-select → update. (#25)
- **P19 — [LOW] `list_project_accounts` returns `200 []` for a missing project** (siblings 404). `projects_admin.py:271-283`. Fix: add `db.get(Project, …)` existence check. (#30)
- **P20 — [LOW] `GET /project-admin/users` discloses the full active-user directory** to any `project_admin` (incl. those with zero project-admin memberships); not project-scoped, exposes emails (PII) + platform roles. `projects_admin.py:174-183`. Fix: require ≥1 project_admin membership for non-platform-admins; drop the `role` field; consider project-scoping the picker. (#45)
- **P21 — [LOW] Scripted login doesn't wrap Playwright `fill`/`click`/`press`.** `password_login.py:141-155`. A non-`PasswordLoginError` Playwright error bypasses the LLM fallback and escapes the module's credential-free contract as a raw 500. Fix: wrap → `PasswordLoginError`. (#31)
- **P22 — [LOW] No test exercises the real `perform_browser_use_login` credential wiring** (task-string password-free, `sensitive_data` correct, credential-free error). `tests/test_browser/test_password_login.py`. Fix: fake-Agent test capturing kwargs (mirror `test_explorer.py`). (#51)
- **P23 — [LOW] `JackExecutionReport` never resets `error` on run-id change.** `JackExecutionReport.tsx:26-42`. Stale "Could not load…" banner pins above a freshly-loaded run. Fix: `setError(null)` in the effect. (#23)
- **P24 — [LOW] Accounts table not refreshed after a config save** that changes environments/app_roles. `ProjectAdminDashboard.tsx:140-156`. Fix: also `await reloadAccounts(selected.id)`. (#27)
- **P25 — [LOW] `ExecutionHistory` omits the thread filter required by AC3** (backend + TS already support `thread_id`). `ExecutionHistory.tsx:16-37,50-84`. Fix: add a `threadId` prop/selector + one `params.set` line; or document the deferral. (#46)
- **P26 — [LOW] Browser/parametrization extraction assumes `[...]` is exactly the engine.** `script_runner.py:421-427`. A script with its own `parametrize` (e.g. `test_x[chromium-case1]`) corrupts the browser label / truncates the name. Fix: anchor on the known engine set `chromium|firefox|webkit`. (#32)
- **P27 — [LOW] `updateProjectConfig` return type drift.** `frontend/src/lib/projectAdmin.ts:58-66` declares `Promise<ProjectAdminProject>` (requires `memberships`) but PUT `/config` returns `AdminProjectResponse` (no memberships). Latent (caller discards result). Fix: narrow FE type to `AdminProject`. (#34/#35/#38)
- **P28 — [LOW] `TestCase.role` missing from the FE `TestCase` interface** it documents as full-stack-synced. `frontend/src/types/testcase.ts`. Backend `TestCase.model_dump()` now includes `role`. Fix: add `role?: string | null`. (#36)
- **P29 — [LOW] `CreateMembershipRequest` TS union omits `project_admin`.** `frontend/src/types/project.ts` (vs backend `ProjectMembershipRole`). Dead-code interface today but drifted. Fix: add `"project_admin"`. (#37)
- **P30 — [LOW] Test-gaps: execution-detail `role` round-trip unasserted** (#49) and **empty `selected_artifact_ids` ⇒ select-all branch untested** (#50). Fix: seed `role` + assert; add omitted/`[]` selection test.

---

## DEFER

### W1 — [HIGH, pre-existing] Unauthenticated E2E report file server — RESOLVED 2026-06-21

- File: `src/ai_qa/api/admin.py:634-661` (`view_e2e_report`) + `src/ai_qa/api/auth/middleware.py:47` (PUBLIC_PATHS).
- `GET /admin/tests/e2e/report/view/{file_path}` has no auth dependency (sibling `download_e2e_report` requires admin) and is explicitly whitelisted public; path-traversal is guarded but anyone can read the entire `playwright-report/` (traces, screenshots, request/response data, app URLs from real-DB E2E runs). **Verified pre-existing — not introduced by this changeset** (admin.py diff doesn't touch it; middleware.py has no diff). (#7)
- **Fixed 2026-06-21 (separate from the Epic 14 changeset):** added `_admin: User = AdminDependency` to `view_e2e_report` and removed the `/api/admin/tests/e2e/report/view` entry from `AuthMiddleware.PUBLIC_PATHS`. The HTML report still opens in a browser tab via the session cookie (`AuthMiddleware._get_user_from_request` reads the cookie). Note the endpoint dependency is the *sole* guard for static-suffixed assets (`.png`/`.js`/`.css`) — those still bypass the middleware via its `is_static` rule, so the route-level `AdminDependency` is load-bearing, not redundant. Negative RBAC test added: `tests/api/test_admin_rbac_api.py::test_e2e_report_view_requires_admin` (anon `.html` → 401 at middleware, anon `.png` asset → 401 at endpoint dependency, non-admin → 403, admin not blocked). Gate green: ruff/format/mypy clean, 1711 passed.

---

## Refuted (not real / handled elsewhere) — 11

The workflow's verifiers refuted 11 reporter claims against the real code (already-guarded, masked-by-design, or non-reproducible). Not listed individually; they are excluded from the buckets above.
