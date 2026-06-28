---
baseline_commit: 2a1f170
---

# Story 13.4: Browser SSO Session Compatibility

Status: done

> **Note (2026-06-25):** The "captured session" model discussed in this story has been superseded by the Epic 25 "Test Account Auto-Login" model. The core principles of isolating sessions and reusing `storageState` still apply, but the source of the session is now an automated login rather than a human session capture.

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want generated Playwright scripts to run against an existing authenticated browser session (enterprise SSO) instead of automating login, and to never store, print, or hardcode any usernames, passwords, tokens, cookies, or session secrets — flagging required SSO/session setup as a review warning when authentication is implied,
so that tests can execute against on-prem applications behind SSO without storing credentials and without leaking secret-like data into scripts, the UI, or the artifact store.

## Acceptance Criteria

Verbatim from [epics.md#Story-13.4](_bmad-output/planning-artifacts/epics.md) (lines 1324-1343), expanded with implementation defaults (see "Scope decisions" — **all four defaults CONFIRMED by Thuong 2026-06-12** ("hãy dùng default"); no pending input remains, see "Confirmed decisions" at the end of this file). This is the **SSO/secret specialization of Story 13.2** and a direct sibling of **Story 13.3** (selector/assertion specialization): 13.2 built the generic review-marker channel (`# TODO:`/`# REVIEW:` + `GeneratedScript.warnings`); **13.4 specializes that same channel** with (a) session-reuse-over-login prompt behavior, (b) a deterministic hardcoded-secret detector, and (c) a deterministic auth-setup-needed detector — **reusing 13.2's `warnings` surface, never inventing a parallel one**.

### AC1 — Generated scripts reuse a configured browser session and never hardcode credentials

- **Given** a test target requires authenticated browser access
- **When** Sarah generates the script
- **Then** the script is written to run against a **configured/pre-authenticated browser context** (an existing SSO session supplied at execution time) — it does **not** automate interactive login with credentials
- **And** it does **not** store, print, or hardcode usernames, passwords, tokens, cookies, or session secrets — surfaced as a categorized warning on `GeneratedScript.warnings` (and the inline `# REVIEW:` marker established in 13.2) **if any credential/secret literal is detected**, never silently emitted

### AC2 — Auth-likely scripts identify required SSO/session setup before execution

- **Given** browser session configuration is unavailable (the generated script artifact carries no wired session; session wiring is an execution-time concern — Epic 15/Jack)
- **When** Sarah generates a script that **likely requires authentication** (login/sign-in steps, an "authenticated"/"logged in" precondition, or password-field interaction)
- **Then** the **script or a review warning identifies the required SSO/session setup before execution** — surfaced on `GeneratedScript.warnings` (and the inline `# REVIEW:` marker from 13.2), so the (future Story 13.5) review UI shows the reviewer what must be set up before the test can run

### AC3 — No credential or secret-like data in saved or displayed content

- **Given** scripts are saved or displayed
- **When** content is rendered in the UI (`review_data`) or written to the artifact store (`projects/{project_id}/test_scripts/`)
- **Then** **no credential values or secret-like data are included** — the no-invent-credentials prompt rule, the deterministic secret detector (advisory flag the reviewer sees **before** approve), and a leak-canary test together guarantee the generated/approved script content and the review payload contain no usernames, passwords, tokens, cookies, or session secrets

---

## ⚠️ Sequencing dependency (READ FIRST — critical)

**Story 13.4 builds on Story 13.2 (the warning channel) and Story 13.1 (the confirm-before-generate lifecycle + approved-test-case loader), which build on Epic 12. As of `2a1f170`, NONE of these are implemented** — Stories 12.1–12.5, 13.1, 13.2 and 13.3 are all `ready-for-dev` and absent from the working tree. 13.4 is therefore **blocked**. Before starting, confirm the prerequisites are present in the live tree; **flag and stop** if missing — do NOT re-implement 13.2 / 13.1 / Epic 12 here.

What 13.4 assumes from upstream (verify present; reconcile against live code and note divergence in Completion Notes per [verify-subagent-claims](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\verify-subagent-claims.md)):

1. **13.2 (the warning channel).** 13.2 adds `warnings: list[str]` to `GeneratedScript` ([sarah.py:26-37](src/ai_qa/agents/sarah.py:26)), the `_extract_review_warnings(script_content) -> list[str]` helper in `ScriptGenerator._generate_single_script`, populates the per-case result `"warnings"` (today hardcoded `[]` at [script_generator.py:213](src/ai_qa/pipelines/script_generator.py:213) — pre-existing Epic-5 scaffolding, not yet fed), threads warnings onto `GeneratedScript(... warnings=...)` in `_generate_scripts` / `_regenerate_current_script`, adds `"warnings"` to the `review_data` payload ([sarah.py:714-725](src/ai_qa/agents/sarah.py:714)), establishes the `# TODO:` / `# REVIEW:` inline-marker convention in the prompts, adds the no-unsafe-inference rule, and rewrites `_generate_script_header` for durable source traceability. **13.4 extends these surfaces** — it adds *new deterministic detectors* that append to the **same** `warnings` list and *new prompt rules* on top of 13.2's marker convention. If `GeneratedScript.warnings` or `_extract_review_warnings` is absent, **13.2 is unmerged → 13.4 is blocked. Flag and stop.**
2. **13.1 (the lifecycle).** Sarah's lifecycle is restructured to confirm-before-generate (`self.phase`, `self.confirmed_test_cases`, `handle_approve` phase-dispatch, `process` rewritten to generate from `self.confirmed_test_cases`). 13.4 does not touch the lifecycle, but the test scaffold must set `agent.phase = "script_review"` so `handle_approve` dispatches to the existing script-review branch.
3. **13.3 (recommended but not required).** 13.3 adds `_detect_brittle_selectors` / `_detect_assertion_gaps` into the **same** merge point 13.4 extends. 13.4 appends two more detectors (`_detect_hardcoded_secrets`, `_detect_auth_setup_needed`) to that line. If 13.3 is unmerged, 13.4 still merges into 13.2's `_extract_review_warnings(...)` line — reconcile and note it.

If 13.2 / 13.1 / Epic 12 are unmerged when you start, this story is **blocked**: there is no `warnings` channel to extend and no script-generation engine in its 13.2 shape. Flag and stop rather than re-implementing upstream.

---

## Scope decisions (CONFIRMED — Thuong locked all four defaults 2026-06-12)

Chosen from the code + ACs + planning docs + the 13.2/13.3 sibling precedent, and **confirmed by Thuong** ("hãy dùng default", 2026-06-12). The four formerly-open questions are now resolved decisions (full list under "Confirmed decisions" at the end of this file). No pending input — the dev agent implements exactly as written.

- **This is a backend specialization story (mirror 13.3 / extend 13.2).** The work is: (a) **strengthen the prompts** with a session-reuse-over-login rule + a no-hardcoded-credentials rule + an SSO-setup-warning rule (on top of 13.2's no-unsafe-inference rule); (b) add **deterministic detectors** in the engine — `_detect_hardcoded_secrets(...)` and `_detect_auth_setup_needed(...)` — that append categorized, source-attributed strings to the **same** `warnings` list 13.2 created; and (c) ensure those warnings flow through the existing channel (`StageResult.warnings` → `GeneratedScript.warnings` → `review_data["warnings"]`), plus an AC3 **leak-canary** test. **No new frontend component** — the side-by-side review card that renders warnings is **Story 13.5**. **No new model field / no migration** — warnings stay a `list[str]`; the script persists as text artifact content (Saved Q#2).
- **Session-reuse model = "assume a pre-authenticated context, never automate login", NOT credential automation or inline session loading (Saved Q#1 default).** The generated standalone Playwright script is written to be **runnable against an existing authenticated browser context** (the active SSO session) supplied by the execution layer (Epic 15/Jack) — exactly the model the codebase already uses for the browser-use analysis pass (FR12: "control a local Chrome instance via browser-use using active SSO login session"; PRD line 471: "Browser sessions reuse existing SSO — pipeline must not store, cache, or log credentials"). 13.4 does **not** wire a concrete `storage_state` path or persistent-context launch into the generated artifact (that is execution-time config, Epic 15) and does **not** modify `SessionManager`/`BrowserAgent`. It makes the script **compatible** by (i) instructing the LLM to skip login automation and assume the session, and (ii) emitting a secret-free `# REVIEW:`/comment documenting the SSO-session assumption when auth is implied.
- **Detection is HYBRID: prompt-driven behavior + deterministic engine scan (Saved Q#3 default = hybrid, same as 13.3).** The prompt asks the LLM to skip login automation, never hardcode credentials, and emit a `# REVIEW:` marker noting required SSO setup (behavioral half, builds on 13.2). The deterministic scanner **independently** flags any credential/secret literal and any auth-implied-without-setup case in the finished script — so a hardcoded password is flagged **even if the LLM emitted it anyway**. Deterministic detection is authoritative for AC1/AC3 flagging; the LLM marker supplies the human-readable "why" and step attribution.
- **Hardcoded credentials from the test case itself are NOT copied into the script (Saved Q#1 default, paired).** Test-case step data may legitimately contain login values (e.g. the sample `TestCase` step `data="testpass"`). For credential-bearing steps the prompt instructs: do **not** emit `.fill("testpass")`/`.type(...)` with the literal — replace the login sequence with a comment noting the test assumes an authenticated SSO session and add a `# REVIEW:` marker. The deterministic detector flags any literal that slips through. This satisfies AC1 ("does not hardcode usernames, passwords, …") and AC3 (the literal never reaches the saved/displayed artifact).
- **Confidence stays as-is (do NOT touch `_calculate_confidence`).** SSO/secret flags are an **independent advisory surface** (no double-counting), matching 13.2's and 13.3's explicit fence. (Sarah's confidence is Epic-5 and intentionally left alone.)
- **AC3 is verified by a backend leak-canary test (Saved Q#4 default = focused backend test, no E2E).** A unit test asserts that a generated/approved script (saved via `save_script`) and the `review_data["warnings"]` payload contain no secret-like sentinel. LLM-driven generation is not E2E-reproducible without a provider key, and the detectors are deterministic units → backend is the right layer. Mirrors the project's existing 7-channel leak-prevention convention ([tests/api/test_secret_leakage.py](tests/api/test_secret_leakage.py), channel 4 = "Artifact content (generated Playwright scripts)").
- **Runtime SSO detection is out of scope.** [`SessionManager.detect_active_sso_session()`](src/ai_qa/browser/session.py:103) is a documented stub returning `False`; full process/cookie inspection is a future enhancement, not 13.4. 13.4 shapes the **generated script** and flags — it does not implement live session detection.
- **Feedback-driven regeneration is Story 13.7; the review UI is 13.5; artifact-save metadata is 13.8; selector/assertion warnings are 13.3.** All new detection lives in the **base** engine path, so it benefits both first-pass and regeneration automatically (no feedback wiring here).

## What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status / action |
| --- | --- | --- |
| SSO session-reuse concept (browser-use controls the user's real Chrome via the active SSO session, no credential storage) | [browser/agent.py](src/ai_qa/browser/agent.py) (`BrowserAgent`, `headless: False` "Visible for SSO session detection") + [browser/session.py](src/ai_qa/browser/session.py) (`SessionManager`) | ✅ **context only** — this is the *analysis-pass* session reuse; 13.4 extends the *no-credential* principle to the **generated script artifact**. **Do not modify** `BrowserAgent`/`SessionManager`. |
| `SessionManager.detect_active_sso_session()` stub (returns `False`) | [browser/session.py:103-121](src/ai_qa/browser/session.py:103) | ⛔ **out of scope** — full SSO detection is a future enhancement; do not implement here |
| Chrome-path request + persistence in Sarah's lifecycle | [sarah.py:456-494](src/ai_qa/agents/sarah.py:456) (`handle_start`), `_load_chrome_path`/`_store_chrome_path` ([:92-140](src/ai_qa/agents/sarah.py:92)) | ✅ **keep** — the Chrome path is the *session host*; 13.4 does not change this flow (13.1 restructures the lifecycle around it) |
| `# TODO:` / `# REVIEW:` inline-marker convention + `_extract_review_warnings(script)` scan | added by **13.2** in [script_generator.py](src/ai_qa/pipelines/script_generator.py) `_generate_single_script` | ⚠️ **reuse** — 13.4's detectors append to the **same** `warnings` list; the LLM SSO/credential `# REVIEW:` markers are caught by it automatically |
| `warnings: list[str]` on `GeneratedScript`; `StageResult.warnings` aggregation; `review_data["warnings"]` | `GeneratedScript` ([sarah.py:26-37](src/ai_qa/agents/sarah.py:26)) + `generate` warnings aggregation ([script_generator.py:98-99](src/ai_qa/pipelines/script_generator.py:98)) + `review_data` ([sarah.py:714-725](src/ai_qa/agents/sarah.py:714)) — all added by **13.2** | ⚠️ **reuse the entire channel** — 13.4 produces more warnings into the same list; no new field, no new payload key |
| Per-case `"warnings"` key in `_generate_single_script`'s return | [script_generator.py:213](src/ai_qa/pipelines/script_generator.py:213) (pre-existing Epic-5 scaffolding, today `[]`) | ✅ the merge point — 13.4 detectors append here (alongside 13.2/13.3 detectors) |
| Per-step `# Step N:` comments emitted by the prompt | added/strengthened by **13.2** ([prompts/script_generation.py:56-61](src/ai_qa/prompts/script_generation.py:56)) | ✅ **rely on** for credential/secret step attribution (best-effort; fall back to no step ref if absent) |
| Selector-priority + assertion-map prompt blocks | [prompts/script_generation.py:32-39](src/ai_qa/prompts/script_generation.py:32), [:48-54](src/ai_qa/prompts/script_generation.py:48) | ✅ **keep untouched** — 13.3 territory; 13.4 adds the SSO/credential rules in a **separate** prompt section |
| 7-channel secret-leakage test convention (channel 4 = generated Playwright scripts) | [tests/api/test_secret_leakage.py](tests/api/test_secret_leakage.py) | ✅ **mirror** the leak-canary pattern for the AC3 test (sentinel value, assert absent from saved content + payload) |
| Security rule: "never store user secrets in messages, logs, artifacts, or generated files" | [project-context.md#Critical-Don't-Miss-Rules](project-context.md), [architecture.md:44](_bmad-output/planning-artifacts/prd.md:44) | ✅ **the constraint 13.4 operationalizes** for the generated-script channel |
| `chrome_path` config + `browser_timeout` | [config.py:113-119](src/ai_qa/config.py:113), `User.chrome_path` ([db/models.py:38](src/ai_qa/db/models.py:38)) | ✅ **context** — no new `AppSettings` field needed; detection is deterministic with no tunable knob |
| `test_case.steps` (`.action`/`.target`/`.data`), `.preconditions`, `.expected_results`, `.title` | [models.py:244-298](src/ai_qa/models.py:244) | ✅ **read** for the auth-likely heuristic (login keywords, "logged in" precondition, password-field step) |
| LLM retry, LangChain string/list normalization | [script_generator.py:231-235](src/ai_qa/pipelines/script_generator.py:231), [:270-291](src/ai_qa/pipelines/script_generator.py:270) | ✅ **keep** — detectors run on the already-normalized `script_content` string |

---

## Tasks / Subtasks

- [x] **Task 0 — Confirm prerequisites (BLOCKING gate)**
  - [x] Verify the live tree contains 13.2's `warnings` channel: `GeneratedScript.warnings` ([sarah.py:26-37](src/ai_qa/agents/sarah.py:26)), `_extract_review_warnings` in `ScriptGenerator`, the populated `"warnings"` key flowing from `_generate_single_script`, and `"warnings"` in `_present_current_script_for_review`'s `review_data`. Verify 13.1's `self.phase`/`confirmed_test_cases` lifecycle and that `process` generates from `self.confirmed_test_cases`. If **any** is missing, 13.2/13.1/Epic 12 is unmerged → **flag and stop** (do not re-implement upstream). Record the verification result in Completion Notes (per [verify-subagent-claims](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\verify-subagent-claims.md)).
  - [x] Confirm `_generate_script_header` no longer emits the false `Source: workspace/testcases/…json` line (13.2's rewrite). 13.4 does **not** touch the header.

- [x] **Task 1 — Strengthen the prompts: session-reuse, no-hardcoded-credentials, SSO-setup warning (AC1, AC2, AC3)**
  - [x] In [prompts/script_generation.py](src/ai_qa/prompts/script_generation.py), in `SCRIPT_GENERATION_PROMPT` ([:20-73](src/ai_qa/prompts/script_generation.py:20)) add a new **"Authentication & session" rule block** (a distinct section, separate from 13.3's selector/assertion blocks):
    - **Session reuse over login:** "Assume the test runs in a browser context that already has an authenticated SSO session (supplied at execution time). Do NOT automate interactive login — do not generate steps that type a username/password or click a login button to authenticate. If the test case includes login/sign-in steps, replace them with a brief comment that the test assumes an existing authenticated session, and add an inline `# REVIEW:` comment noting that SSO/session setup is required before execution."
    - **Never hardcode credentials:** "NEVER write a literal username, password, token, cookie, API key, bearer token, or session secret into the script — not in `.fill()`/`.type()`, not in a variable, not in a header, not in a URL (`user:pass@host`), and not in `add_cookies(...)` or an inline `storage_state` dict. If a value is genuinely needed and unspecified, use a clearly-named placeholder/environment-variable reference and add a `# REVIEW:` comment — never invent a credential."
    - **Auth-setup visibility:** "If the test target appears to require authentication (a protected area, an 'authenticated'/'logged in' precondition, or any login interaction), add a `# REVIEW:` comment at the top of the test body identifying the required SSO/session setup before execution." (Reuses 13.2's `# REVIEW:` token — do **not** introduce a new marker token.)
  - [x] Apply the **same** authentication/session rules to `VISION_ASSISTED_SCRIPT_GENERATION_PROMPT` ([:134-161](src/ai_qa/prompts/script_generation.py:134)) so both generation paths produce identical SSO/credential behavior and marker tokens.
  - [x] Keep `SCRIPT_GENERATION_SYSTEM_PROMPT` / `VISION_SCRIPT_GENERATION_SYSTEM_PROMPT` consistent — add a one-line principle ("Never emit credentials; reuse the existing authenticated session"). Keep `__all__` ([:210-218](src/ai_qa/prompts/script_generation.py:210)) in sync if you add an exported constant (type any new module constant — avoid the `Literal`-default pitfall). Do **not** weaken the selector-priority / assertion-map blocks (13.3 territory).

- [x] **Task 2 — Deterministic hardcoded-secret detector in the engine (AC1, AC3)**
  - [x] Add `_detect_hardcoded_secrets(self, script_content: str) -> list[str]` to `ScriptGenerator`. Walk the script **line by line**, tracking the nearest preceding `# Step N:` comment (regex `^\s*#\s*Step\s+(\d+)\b` — capture N). Flag each occurrence of a credential/secret literal, including:
    - **Credential-entry literals:** `.fill("…")` / `.type("…")` / `.press_sequentially("…", …)` where the locator or a nearby `# Step` text references password/passwd/pwd/secret/token/otp/credential (and, more conservatively, any non-empty string literal filled into a field named like a password).
    - **Secret-named assignments:** `password = "…"`, `token = "…"`, `api_key = "…"`, `secret = "…"`, `cookie = "…"`, `bearer = "…"`, `session = "…<value>"` with a **non-empty string literal** (ignore env reads like `os.environ[...]` / `os.getenv(...)` — those are the *approved* placeholder pattern).
    - **Cookie / storage-state injection:** `add_cookies(` and inline `storage_state={…}` dict literals (a `storage_state="path"` **string path** is allowed — that is the configured-session reference, not a secret).
    - **Auth headers / creds-in-URL:** literal `Authorization` header values (Bearer-type or Basic-type) and URLs with embedded credentials of the form `<scheme>://<user>:<pass>@<host>`.
  - [x] Each flagged occurrence → one warning string: `f"Credential/secret literal (Step {n}): {snippet} — never hardcode credentials; reuse the authenticated SSO session"` (omit the `(Step {n})` segment if no preceding `# Step N:` comment — best-effort attribution). Keep the snippet short and **redact the literal value** in the warning text (show the variable/call shape, not the secret) so the warning itself never carries the secret. Compile `re` patterns at module level.

- [x] **Task 3 — Deterministic auth-setup-needed detector in the engine (AC2)**
  - [x] Add `_detect_auth_setup_needed(self, script_content: str, test_case: TestCase) -> list[str]` to `ScriptGenerator`. Compute an **auth-likely** signal deterministically from the test case + script:
    - Login keywords in `test_case.title` / any `step.action` / any `step.target` (login, log in, sign in, sign-in, authenticate, logout, credentials).
    - An "authenticated"/"logged in"/"signed in" phrase in any `test_case.preconditions`.
    - A password-field interaction in the script (a `# Step` or locator referencing password and a `.fill`/`.type`).
  - [x] If auth-likely **and** the script does not already contain an SSO/session-setup `# REVIEW:` marker (case-insensitive scan for the SSO-setup phrase the prompt emits), emit one warning: `"SSO/session setup required: this test targets an authenticated area — run it against a pre-authenticated browser context (existing SSO session); no login automation or credentials are included"`. (AC2: "the script **or** review warning identifies required SSO/session setup".) If the LLM already emitted the marker, the LLM half satisfies AC2 and the deterministic warning is suppressed (avoid double-noise).
  - [x] Do **not** attempt to determine the *specific* SSO provider/URL (LLM-judgment / execution-config territory, deferred to Epic 15).

- [x] **Task 4 — Wire the detectors into the warning flow (AC1, AC2, AC3)**
  - [x] In `_generate_single_script` ([script_generator.py:182-214](src/ai_qa/pipelines/script_generator.py:182)), **after** content validation and **after** 13.2's `_extract_review_warnings` (and 13.3's selector/assertion detectors, if merged) run, append both new detectors into the per-case `"warnings"` list: `warnings = _extract_review_warnings(...) + … + self._detect_hardcoded_secrets(script_content) + self._detect_auth_setup_needed(script_content, test_case)`. Return `{"success": True, …, "warnings": warnings}`. `generate` already aggregates `result.get("warnings")` into `StageResult.warnings` ([:98-99](src/ai_qa/pipelines/script_generator.py:98)) — **no change there**.
  - [x] **Overlap handling (light):** the LLM may emit a `# REVIEW:` marker on the same credential line the deterministic detector flags → two warnings for one issue. Acceptable (both advisory). For the **auth-setup** warning, suppress the deterministic one when the LLM marker is present (Task 3). For credential literals, default is allow-both. Note the choice in Completion Notes.
  - [x] Confirm the warnings flow downstream via 13.2's wiring: `StageResult.warnings` → Sarah `_generate_scripts` reads per-case warnings onto `GeneratedScript.warnings` → `_present_current_script_for_review` puts them in `review_data["warnings"]`. **13.4 adds nothing new to `sarah.py`** beyond confirming the flow. If 13.2 only populated aggregate `StageResult.warnings` and not per-`GeneratedScript.warnings`, reconcile so per-script warnings are populated (the AC1/AC2 surface the 13.5 review UI needs).

- [x] **Task 5 — Backend tests (AC1, AC2, AC3)**
  - [x] **Prompt** ([tests/pipelines/test_script_generator.py](tests/pipelines/test_script_generator.py)): assert `SCRIPT_GENERATION_PROMPT` (and the vision variant) contain the session-reuse rule, the no-hardcoded-credentials rule, and the SSO-setup-warning rule, and still forbid inventing credentials/URLs. Guards AC1/AC2/AC3 against prompt regression.
  - [x] **Hardcoded-secret detector** (AC1, AC3): feed `_detect_hardcoded_secrets` scripts containing (a) `# Step 1:` then `page.get_by_label("Password").fill("hunter2")` → one warning prefixed `Credential/secret literal` carrying `(Step 1)` and **not** containing `hunter2`; (b) `token = "abc123"` → flagged; (c) `add_cookies([...])` / inline `storage_state={...}` → flagged; (d) a `user:pass@host` URL → flagged. Assert a **clean** script (`os.environ["PW_USER"]`, `storage_state="state.json"` path, no literals) yields **zero** warnings (no false positives on the approved placeholder/path patterns).
  - [x] **Auth-setup detector** (AC2): a `TestCase` with a login step / "User is logged in" precondition + a script with **no** SSO marker → one `SSO/session setup required` warning; the same with the script already containing the SSO `# REVIEW:` marker → **no** deterministic warning (LLM half satisfies AC2); a non-auth `TestCase` (e.g. public search) → **no** warning.
  - [x] **End-to-end through the engine** (AC1/AC2/AC3): mock the LLM (`_call_llm`) to return a script with a hardcoded password and a login flow; assert the detected warnings appear in `StageResult.warnings` from `generate(...)`, and (via Sarah) on `GeneratedScript.warnings` and in `review_data["warnings"]` of `_present_current_script_for_review`. Set `agent.phase = "script_review"` (13.1) in the Sarah test.
  - [x] **AC3 leak-canary** (mirror [tests/api/test_secret_leakage.py](tests/api/test_secret_leakage.py) channel 4): with a `TestCase` whose step `data` carries a sentinel credential (e.g. `data="S3CRET-SENTINEL"`) and a mocked LLM that follows the prompt (no login automation), approve the script via Sarah `handle_approve` and assert the **saved** script content (`save_script` payload) and the `review_data["warnings"]` payload do **not** contain the sentinel. (Demonstrates the literal never lands in the saved/displayed artifact.)
  - [x] **Confidence untouched:** assert the existing confidence tests ([test_script_generator.py:273-328](tests/pipelines/test_script_generator.py:273)) still pass unchanged — `_calculate_confidence` behavior must not change.
  - [x] **Back-compat:** a clean script (session-reuse, no credentials, non-auth case) yields **empty** warnings — existing `test_generate_single_test_case` / `test_generate_multiple_test_cases` still pass.
  - [x] If shared fixtures break, fix [tests/conftest.py](tests/conftest.py) **centrally** ([agent-gate-conftest-regression](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\agent-gate-conftest-regression.md)), not per-test.

- [x] **Task 6 — Verify (no migration)**
  - [x] Backend: `uv run pytest --no-cov` (whole suite — the coverage gate fails on subset runs; see [backend-test-suite-orphaned-legacy-tests](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\backend-test-suite-orphaned-legacy-tests.md)). Mypy gate: `uv run mypy src`. Code must also pass **Pyrefly** — narrow `Any`/`Optional` before use (the per-case dict `result.get("warnings")` is `Any` → coerce to `list[str]` before merging; compiled `re` matches are `Match | None` → guard; `test_case.preconditions`/`expected_results` are `list[str]`). No redundant casts/conversions; type any new marker/category module constant. Note the file already carries `# mypy: disable-error-code="misc"` at the top of [script_generator.py:1](src/ai_qa/pipelines/script_generator.py:1) — keep new code clean regardless.
  - [x] Confirm **no Alembic migration** is required (warnings stay a `list[str]` on the in-memory `GeneratedScript`; the script persists as text artifact content; no new model field, no new `AppSettings` field). State explicitly in Completion Notes.
  - [x] Frontend: **no component change in 13.4.** Run `npm run typecheck` only to confirm nothing broke — the enriched `review_data["warnings"]` is still untyped on the client until 13.5 (full-stack-sync handoff). Note the deferral in Completion Notes.

## Dev Notes

### Current state of the files this story touches (READ FIRST)

**`src/ai_qa/prompts/script_generation.py` — the prompts (most load-bearing AC1/AC2/AC3 change).**

- `SCRIPT_GENERATION_PROMPT` ([:20-73](src/ai_qa/prompts/script_generation.py:20)) today has **no** mention of authentication, SSO, sessions, or credentials. The selector-priority block ([:32-39](src/ai_qa/prompts/script_generation.py:32)) and assertion map ([:48-54](src/ai_qa/prompts/script_generation.py:48)) are 13.3 territory — **leave them**. 13.4 appends a new "Authentication & session" rule block. The "Output ONLY the Python test function code" line ([:73](src/ai_qa/prompts/script_generation.py:73)) was reconciled by 13.2 to permit inline `# TODO:`/`# REVIEW:` comments — confirm that reconciliation is present; the new SSO `# REVIEW:` markers are valid Python comments and must not be suppressed.
- `VISION_ASSISTED_SCRIPT_GENERATION_PROMPT` ([:134-161](src/ai_qa/prompts/script_generation.py:134)) needs the same authentication/session rules so the vision path behaves identically.
- `SCRIPT_GENERATION_WITH_HINTS_PROMPT` ([:76-110](src/ai_qa/prompts/script_generation.py:76)) is **not used by the live engine** (the engine uses `SCRIPT_GENERATION_PROMPT` and `VISION_ASSISTED_SCRIPT_GENERATION_PROMPT`) — update for consistency only if you touch it.

**`src/ai_qa/pipelines/script_generator.py` — the engine (new deterministic detectors slot in here).**

- `_generate_single_script` ([:133-229](src/ai_qa/pipelines/script_generator.py:133)) is the merge point. 13.2 adds `_extract_review_warnings` + the populated `"warnings"` return; 13.3 adds `_detect_brittle_selectors`/`_detect_assertion_gaps`; **13.4 adds `_detect_hardcoded_secrets` + `_detect_auth_setup_needed`** after content validation ([after :206](src/ai_qa/pipelines/script_generator.py:206)) and merges into the same `"warnings"`. Today the return hardcodes `"warnings": []` ([:213](src/ai_qa/pipelines/script_generator.py:213)).
- `generate` ([:64-131](src/ai_qa/pipelines/script_generator.py:64)) already aggregates per-case `result.get("warnings")` into `StageResult.warnings` ([:98-99](src/ai_qa/pipelines/script_generator.py:98)) — the channel is complete; 13.4 only produces more into it.
- `_calculate_confidence` ([:494-552](src/ai_qa/pipelines/script_generator.py:494)) — **do not touch** (Epic-5 fence, reaffirmed by 13.2/13.3). 13.4's flags are independent of the confidence number.
- `_generate_script_header` ([:468-492](src/ai_qa/pipelines/script_generator.py:468)) is 13.2's rewrite target — **do not touch** in 13.4.

**`src/ai_qa/agents/sarah.py` — the agent (13.4 only confirms the flow; 13.2 did the plumbing).**

- `GeneratedScript.warnings` ([sarah.py:26-37](src/ai_qa/agents/sarah.py:26)) — added by 13.2. 13.4 does not add fields.
- `_generate_scripts` ([:273-367](src/ai_qa/agents/sarah.py:273)) reads per-case warnings onto each `GeneratedScript` (13.2). Confirm the **per-script** warnings (not just `StageResult.warnings`) are populated — AC1/AC2's review UI ties warnings to a specific script. If 13.2 only wired aggregate `StageResult.warnings`, reconcile here.
- `_present_current_script_for_review` ([:698-736](src/ai_qa/agents/sarah.py:698)) puts `"warnings"` in `review_data` (13.2). No change in 13.4.
- `handle_approve` ([:519-570](src/ai_qa/agents/sarah.py:519)) calls `save_script(...)` — note the live `.spec.ts` fallback at [:538](src/ai_qa/agents/sarah.py:538) is a **13.8** defect (wrong extension for Python scripts); **do not fix here**. The AC3 leak-canary test exercises this save path but asserts only the *absence of secrets*, not the filename.
- The per-item **script** review state machine (`handle_approve`/`handle_reject`/`handle_skip`/`handle_navigate`) is Epic-5 + 13.5+/13.7 territory — **do not change** beyond phase-dispatch already added by 13.1.

### The AC mechanic: specialize 13.2's channel, hybrid detection (most load-bearing change)

13.4 is to 13.2 what **13.3 is to 13.2**: 13.2 built the generic warning channel + the "preserve ambiguity, never invent" behavior; 13.4 adds a **specialized, deterministic** layer on top — this time for SSO/credentials rather than selectors/assertions.

1. **Prompt-side (behavioral):** the LLM skips login automation, assumes the authenticated session, never fabricates a credential, and emits a `# REVIEW:` marker for required SSO setup. Builds on 13.2's marker convention; adds the *authentication/session* category.
2. **Engine-side (deterministic, authoritative for flagging):** `_detect_hardcoded_secrets` and `_detect_auth_setup_needed` scan the finished script and append categorized, source-attributed strings to the **same** `warnings` list — so AC1/AC3 hold **even if the LLM emitted a credential anyway**, and AC2 holds even if the LLM forgot the setup note.

Both halves write to **one** `warnings: list[str]` (13.2's channel). Keep the category prefixes stable (`Credential/secret literal`, `SSO/session setup required`) and the step/context reference inside the string so the future 13.5 renderer can group/tie them without a model change.

### The session-reuse model (AC1) — assume, don't automate

The codebase already reuses SSO sessions for the **analysis pass**: `BrowserAgent` launches the user's real Chrome (`headless: False`, the live SSO cookies are in the profile) and browser-use drives it (FR12). 13.4 extends the **no-credential** principle to the **generated standalone script**:

- The generated `test_*.py` is meant to run under a browser context that is **already authenticated** (the execution layer — Epic 15/Jack — supplies `storage_state` or a persistent profile). 13.4 does **not** wire that config into the artifact; it ensures the script **does not authenticate itself** and **does not embed any secret**.
- Allowed in a generated script: `storage_state="<path>"` as a **string path** reference (not an inline dict), `os.environ[...]`/`os.getenv(...)` placeholders, and a documented `# REVIEW:` note. **Forbidden:** literal credentials anywhere, inline `storage_state={…}` dicts, `add_cookies([...])` with literal values, `user:pass@host` URLs.
- This satisfies the PRD constraint exactly: "Browser sessions reuse existing SSO — pipeline must not store, cache, or log credentials" ([prd.md:471](_bmad-output/planning-artifacts/prd.md:471), [:241](_bmad-output/planning-artifacts/prd.md:241)) and "browser agent remains read-only / no secret leakage" ([architecture.md:44](_bmad-output/planning-artifacts/architecture.md:44)).

### Boundary fences (what 13.4 must NOT do)

- **Confidence (`_calculate_confidence`):** do **not** change the score, thresholds, or blending. 13.4's flags are independent of the confidence number. Existing confidence tests must pass unchanged.
- **13.2 (the channel + no-unsafe-inference + header):** do not re-do `_extract_review_warnings`, the `# TODO:`/`# REVIEW:` token definition, or `_generate_script_header`. 13.4 **extends**, not rewrites.
- **13.3 (selectors/assertions):** do not touch the selector-priority/assertion-map blocks or `_detect_brittle_selectors`/`_detect_assertion_gaps`. 13.4 adds a separate authentication/session prompt block and separate detectors.
- **Runtime SSO detection:** do **not** implement `SessionManager.detect_active_sso_session()` or any live cookie/process inspection (future enhancement). Do **not** modify `BrowserAgent`/`SessionManager`.
- **13.5 (review UX):** no frontend component, no syntax-highlight, no warning-rendering UI, no TS type. Only the backend `review_data["warnings"]` carries the richer strings.
- **13.6/13.7 (edit/approve/regenerate):** do not wire feedback into the prompt; do not change the review state machine.
- **13.8 (artifact save):** do not expand save metadata or fix the `.spec.ts` save-fallback defect ([sarah.py:538](src/ai_qa/agents/sarah.py:538)) — leave it for 13.8.
- **No execution-time session wiring** (storage_state path resolution, persistent-context launch) — that is Epic 15/Jack.

### Architecture compliance (hard rules)

- **No credential/secret leakage — the central rule of this story** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md): "Never store user secrets in `.env`, plaintext, messages, logs, artifacts, or generated files. Never return secret values to frontend."; [prd.md:471](_bmad-output/planning-artifacts/prd.md:471), [architecture.md:44](_bmad-output/planning-artifacts/architecture.md:44)). The `warnings`/`review_data` payload carries only category tags, redacted snippets, step numbers — never the secret value itself. The leak-canary test (channel 4) is the guardrail.
- **Browser sessions reuse existing SSO — no additional credential storage** ([prd.md:241](_bmad-output/planning-artifacts/prd.md:241), FR12 [prd.md:354](_bmad-output/planning-artifacts/prd.md:354)). 13.4 is the story that operationalizes this for the generated-script channel.
- **Agents never read/write storage directly — always via the artifact service** ([architecture.md:518](_bmad-output/planning-artifacts/architecture.md:518), anti-pattern [:533](_bmad-output/planning-artifacts/architecture.md:533)). 13.4 stays inside the generator/prompt; the save path is `PipelineArtifactAdapter.save_script` (unchanged).
- **Mandatory human review at every step — no auto-advance** ([architecture.md:271-272](_bmad-output/planning-artifacts/architecture.md:271), [ux-design-specification.md:188](_bmad-output/planning-artifacts/ux-design-specification.md:188)). Credential literals and missing SSO setup are **flagged for review**, never auto-corrected or auto-approved.
- **Sarah flow** `script_generator.py → ai_connection + browser/agent.py → projects/{project_id}/test_scripts/` ([architecture.md:824-828](_bmad-output/planning-artifacts/architecture.md:824)); Sarah model needs (browser-automation/tool-use compatibility, framework-aware output) ([architecture.md:1163-1167](_bmad-output/planning-artifacts/architecture.md:1163)).
- **Full-stack sync** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)): the enriched `review_data["warnings"]` is **untyped on the client** until 13.5 builds the script-review panel + TS type. Flag this handoff in Completion Notes.

### Library / framework constraints (from project-context.md)

- **Backend:** Python ≥3.14, `uv` only (`uv run`, never `pip`/`python3`). Ruff + Mypy strict (`uv run mypy src`). Must also pass **Pyrefly** — narrow `Optional`/`Any` before use (`result.get("warnings")` is `Any` → coerce to `list[str]`; `re` matches are `Match | None` → guard); no redundant casts/conversions; type any new module constant (avoid `Literal`-default pitfalls). `pytest.raises(Exception)` prohibited — specific exception type + `match=`. The generator path is a **sync** LLM call inside async (no async-SQLAlchemy concerns). Compile `re` patterns at module level for the line scan.
- **Prompt strings are Python literals**, not markdown-linted; this story file follows the markdown rules (lists `-`, MD036 real headings, MD060 table spacing).
- **Config:** no new `AppSettings` field needed — SSO/credential detection is deterministic with no tunable knob.
- **No new packages. No Alembic migration.**

### Project Structure Notes

- **Modified files (expected):** `src/ai_qa/prompts/script_generation.py` (authentication/session prompt rules), `src/ai_qa/pipelines/script_generator.py` (two new deterministic detectors + merge into the per-case warnings), possibly a one-line confirm/reconcile in `src/ai_qa/agents/sarah.py` (per-`GeneratedScript.warnings` population, only if 13.2 left it aggregate-only), `tests/pipelines/test_script_generator.py` (prompt + detector tests + confidence-unchanged regression), `tests/test_agents/test_sarah.py` (warnings-on-`GeneratedScript` surfacing + AC3 leak-canary), possibly `tests/conftest.py`.
- **No new files required** (the detectors live in `script_generator.py`). **No frontend files** (13.5 owns the script-review component + TS type).
- **No backend route/schema/REST changes** — the richer `review_data["warnings"]` rides the existing WebSocket `send_message` metadata channel (added by 13.2).

### Testing standards summary

- Backend: pytest. `ScriptGenerator` tests patch `_get_llm_client` (or `ai_qa.pipelines.script_generator.LLMClient`) and set `mock_response.content`; the new detectors are **pure functions** — test them directly with literal script strings (no LLM needed). Sarah tests patch `ai_qa.agents.sarah.ScriptGenerator` (+ `PipelineArtifactAdapter`) and set the mocked `generate` return so `result.data[0]["warnings"]` carries the detected strings; set `agent.phase = "script_review"` (13.1). The AC3 leak-canary mirrors [tests/api/test_secret_leakage.py](tests/api/test_secret_leakage.py) (sentinel + assert-absent). Run the **whole** suite with `--no-cov` (subset runs fail the coverage gate; prior-epic baseline = 1098 passed). Mypy gate is `src` only.
- Frontend: no Vitest/Playwright change in 13.4 (deferred to 13.5). Only `npm run typecheck` to confirm no breakage. LLM-driven generation is not E2E-reproducible without a provider key, and the new detectors are deterministic units — E2E is **not** the right layer for AC1/AC2/AC3 (covered by backend unit + leak-canary tests).

### Previous-story intelligence

- **Story 13.3 (stable selector & assertion mapping)** — the **direct structural sibling**. Same shape: a **deterministic** specialization layer (detectors) added on top of 13.2's generic warning channel, hybrid prompt + deterministic detection, category-prefixed `list[str]` warnings, confidence left untouched, no new model field/migration, no FE (deferred to 13.5). 13.4 follows the identical pattern for a different category (SSO/credentials vs selectors/assertions). Both detectors merge into the **same** `_generate_single_script` warnings line.
- **Story 13.2 (Sarah generation engine — the channel)** — built `warnings: list[str]`, `_extract_review_warnings`, the `# TODO:`/`# REVIEW:` marker convention, the no-unsafe-inference rule, and the durable header. It reserved category-specific flagging for 13.3/13.4 and said reuse the same channel rather than invent a parallel one. 13.4 honors that: same channel, category prefix, no new token, no new field.
- **Story 13.1 (Sarah input selection)** — restructured Sarah's lifecycle (confirm-before-generate, `self.phase`, `confirmed_test_cases`). 13.4 does not touch it; tests set `agent.phase = "script_review"`.
- **Epic 5 (Sarah, `done`)** — built `ScriptGenerator`/`VisionLocator`/`BrowserAgent`/`SessionManager`, the prompts, the per-item script review loop, the chrome-path flow, and the existing confidence heuristic. **`browser/agent.py` + `browser/session.py` already embody SSO session reuse for the analysis pass** — 13.4 reuses the *principle* (no credential storage) for the generated artifact and **does not modify those modules**.
- **Epic 9 (per-user encrypted secrets, `done`)** — established the 7-channel leak-prevention convention and the "secrets never in artifacts/generated files" rule. The AC3 leak-canary test extends that convention to the script-generation channel.
- **Stories 13.5/13.7/13.8 + Epic 15** — the explicit fences above. 13.5 renders these warnings; 13.7 wires feedback regeneration; 13.8 saves the artifact + metadata; Epic 15/Jack supplies the execution-time authenticated session.

### Git intelligence (recent work patterns)

Recent commits (`2a1f170 epic 11 code e2e unit done`, `b4ce65f epic 10 all e2e test OK`, `8cf53eb epic 10 all code done`) are Epic 10/11. **Epic 12 (12.1–12.5), Stories 13.1, 13.2 and 13.3 are NOT implemented** — the live `sarah.py`/`script_generator.py`/`prompts/script_generation.py`/`TestCase` are pre-12.1/pre-13.1/pre-13.2 (verified: `GeneratedScript` has **no** `warnings` field, `_extract_review_warnings` does **not** exist, `review_data` has **no** `"warnings"` key, and `_generate_script_header` still emits `Source: workspace/testcases/…json` at [script_generator.py:484](src/ai_qa/pipelines/script_generator.py:484)). **13.4 is blocked until 13.2 lands** (it has no `warnings` channel to extend). Before relying on 13.2's surfaces, **verify they are present in the live tree** (Task 0); if unmerged, flag and stop rather than re-implementing upstream. Closest existing patterns to copy: [tests/pipelines/test_script_generator.py](tests/pipelines/test_script_generator.py) (engine test scaffold), [tests/test_agents/test_sarah.py](tests/test_agents/test_sarah.py) (Sarah lifecycle scaffold), [tests/api/test_secret_leakage.py](tests/api/test_secret_leakage.py) (leak-canary scaffold), and the **13.3 story** (the deterministic-specialization-on-top-of-13.2's-channel pattern).

### Sibling-story note (reusability)

13.4 reuses (does **not** fork) the review-marker channel 13.2 established and 13.3 extended: in-script `# TODO:`/`# REVIEW:` + `warnings: list[str]` on `GeneratedScript`/`StageResult`/`review_data`. The category-prefix convention (`Credential/secret literal …`, `SSO/session setup required …`) keeps the channel a flat `list[str]` while making warnings groupable by the future 13.5 renderer — no model change, no migration. Keep the detectors pure and prompt-agnostic so any later refinement can layer on without rewriting the scan.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-13.4] — ACs (lines 1324-1343); Epic 13 intro + FRs (1253-1257); sibling 13.2 generation engine (1281-1300), 13.3 selectors/assertions (1302-1322), 13.5 review UX with warnings-visible AC (1345-1365), 13.8 script save (1411-1430)
- [Source: _bmad-output/planning-artifacts/prd.md] — FR12 control local Chrome via active SSO session (354); SSO/no-credential-storage constraints (241, 471); on-prem data sovereignty (239-240); Sarah review scene (193)
- [Source: _bmad-output/planning-artifacts/architecture.md] — SSO/browser-use control of local Chrome (30, 60, 283); security/no-secret-leakage (44); Sarah flow `script_generator.py → … browser/agent.py → test_scripts/` (824-828); Sarah model needs (1163-1167); no-direct-storage (518, 533); no-auto-advance / mandatory review (271-272)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md] — mandatory review gate (188)
- [Source: src/ai_qa/prompts/script_generation.py] — system prompt + stable-selector principle (7-18), main prompt (20-73), selector-priority block (32-39, **keep, 13.3 territory**), assertion map (48-54, **keep**), vision-assisted prompt (134-161), `__all__` (210-218); **no auth/SSO/credential rules today — 13.4 adds them**
- [Source: src/ai_qa/pipelines/script_generator.py] — `generate` warnings aggregation (64-131, esp. 98-99), `_generate_single_script` warnings return (133-229, esp. 206-214), `_calculate_confidence` — **do not touch** (494-552), `_generate_script_header` (468-492, 13.2's target, do not touch), `# mypy: disable-error-code` header (1)
- [Source: src/ai_qa/agents/sarah.py] — `GeneratedScript` (+`warnings` from 13.2; 26-37), chrome-path flow (92-140, 456-494), `_generate_scripts` per-case construct (273-367), `handle_approve`→`save_script` + `.spec.ts` 13.8 defect (519-570, esp. 538), `_present_current_script_for_review` `review_data` incl. `warnings` from 13.2 (698-736), per-item review loop (519-696, do NOT change)
- [Source: src/ai_qa/browser/agent.py] — `BrowserAgent` SSO session reuse for analysis pass (`headless: False`, 47-54) — **context only, do not modify**
- [Source: src/ai_qa/browser/session.py] — `SessionManager`, `detect_active_sso_session()` stub (103-121, **out of scope**), chrome-path persistence (41-101)
- [Source: src/ai_qa/config.py] — `chrome_path`/`browser_timeout` (113-119), script-generation config (121-136); no new field needed
- [Source: src/ai_qa/db/models.py:38] — `User.chrome_path`
- [Source: src/ai_qa/models.py:244-298] — `TestCase` (`title`, `preconditions`, `steps` with `.action`/`.target`/`.data`, `expected_results`, `filename`) for the auth-likely heuristic
- [Source: tests/api/test_secret_leakage.py] — 7-channel leak-prevention scaffold (channel 4 = generated Playwright scripts) — mirror for the AC3 leak-canary
- [Source: tests/pipelines/test_script_generator.py] — engine test scaffold, LLM mock seam, confidence tests (273-328, keep passing)
- [Source: tests/test_agents/test_sarah.py] — Sarah lifecycle test scaffold (patches ScriptGenerator + adapter)
- [Source: _bmad-output/implementation-artifacts/13-2-python-playwright-script-generation.md] — the `warnings` channel, `_extract_review_warnings`, `# TODO:`/`# REVIEW:` convention, no-unsafe-inference, durable header; the "13.4 specializes this channel" handoff
- [Source: _bmad-output/implementation-artifacts/13-3-stable-selector-and-assertion-mapping.md] — the immediate sibling: deterministic-specialization-on-13.2's-channel pattern, hybrid detection, category-prefixed `list[str]`, confidence-untouched fence
- [Source: project-context.md] — `uv`/`npm` only; Ruff + Mypy strict; Pyrefly (narrow Optional/Any, no redundant cast); no bare except; no `# type: ignore`; full-stack sync; **security (no secrets in payloads/logs/artifacts/generated files)** — the core 13.4 rule

## Confirmed decisions (defaults locked by Thuong 2026-06-12 — "hãy dùng default")

All four formerly-open questions are resolved to their defaults. No pending input — implement exactly as stated.

1. **Session-reuse mechanism = assume a pre-authenticated context; do NOT emit storage_state/persistent-context scaffold (CONFIRMED).** The generated script skips login automation and assumes the runner supplies an authenticated SSO session at execution time (Epic 15/Jack); 13.4 only forbids credentials and emits an SSO-setup `# REVIEW:` note. (Rejected: also emitting a commented `storage_state="<path>"`/persistent-context scaffold — premature until the execution layer defines the wiring; and wiring a real session into the artifact — execution-time config, Epic 15, risks embedding paths/secrets.)
2. **Warning shape = flat `list[str]` with a stable category + source prefix (CONFIRMED).** Reuses 13.2's channel; no new model field, no migration; 13.5 renders strings and can group by prefix. (Rejected: structured warning objects `{category, step, text}` — heavier, speculative until the 13.5 renderer exists.) Same shape as 13.3.
3. **Detection method = hybrid prompt + deterministic (CONFIRMED, same as 13.3).** The prompt asks the LLM to skip login / never hardcode / mark SSO setup; a deterministic scanner independently flags credential literals and auth-without-setup so AC1/AC2/AC3 hold even if the LLM slips. (Rejected: deterministic-only — loses the human-readable "why"; prompt-only — a forgotten flag = a silently leaked credential.)
4. **AC3 verification layer = focused backend leak-canary unit test, no E2E (CONFIRMED).** A `ScriptGenerator`/Sarah test with a credential sentinel asserts the saved script + `review_data` payload omit it. (Rejected: extending the 7-channel `tests/api/test_secret_leakage.py` end-to-end harness — heavier; LLM generation not reproducible there without a provider key.)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Test failure in `test_clean_sso_script_no_13_4_warnings`: the `# REVIEW: SSO/session setup required before execution` marker in the clean script was captured by 13.2's `_extract_review_warnings` and put into `result.warnings` with a `"REVIEW: SSO…"` prefix. The test filter `"SSO/session setup required" in w` matched both 13.4's warning (prefix `"SSO/session setup required:"`) and 13.2's warning (prefix `"REVIEW: SSO…"`). Fixed: changed the filter to `w.startswith("SSO/session setup required:")` so the two categories are distinguished by their distinct prefixes.

### Completion Notes List

- **No Alembic migration required.** `warnings: list[str]` on `GeneratedScript` is an in-memory field; the script persists as text artifact content; no new model field, no new `AppSettings` field, no new DB column.
- **No frontend change in 13.4.** The enriched `review_data["warnings"]` is untyped on the client until 13.5 (script-review panel + TS type). `npm run typecheck` run and confirmed clean.
- **Overlap / double-warning policy:** For credential literals, both the LLM `# REVIEW:` marker and the deterministic detector may fire — two warnings for one issue is acceptable (both advisory). For the auth-setup warning, the deterministic detector is suppressed when `_SSO_REVIEW_MARKER_RE` matches a `# REVIEW:.*SSO` comment already emitted by the LLM — avoids double-noise while still satisfying AC2.
- **Warning prefix convention:** `"Credential/secret literal…"` (AC1/AC3) and `"SSO/session setup required:…"` (AC2). This differs deliberately from 13.2's `"REVIEW: SSO…"` scan output — the prefixes must not collide to allow caller-side filtering.
- **Redaction approach:** Detector warnings carry the variable/call shape (e.g., `password = '<redacted>'`, `add_cookies(<redacted>)`) but never the literal value, satisfying AC3's requirement that warnings themselves never carry secrets.
- **`storage_state` distinction:** `storage_state="path"` (string) is ALLOWED (execution-time config); `storage_state={…}` (dict) is FORBIDDEN (inline secret). `_INLINE_STORAGE_STATE_DICT_RE` targets only the dict form.
- **Verification results:** `uv run pytest --no-cov` → **1330 passed**, 1 warning (0 failures). `uv run mypy src` → **Success: no issues found in 79 source files**. `npm run typecheck` → **passed** (no errors).

### File List

- `src/ai_qa/prompts/script_generation.py` — added auth/session rules to all 4 prompt strings (principle 7 in both system prompts; section 9 in main prompt; section 6 in vision prompt)
- `src/ai_qa/pipelines/script_generator.py` — added 11 module-level compiled regex patterns; new `_detect_hardcoded_secrets` method; new `_detect_auth_setup_needed` method; wired both detectors into `_generate_single_script`
- `tests/pipelines/test_script_generator.py` — added 23 new tests in 4 new classes: `TestScriptGenerationPromptAC13_4`, `TestHardcodedSecretDetector`, `TestAuthSetupDetector`, `TestStory134EndToEnd`
- `tests/test_agents/test_sarah.py` — added 4 new tests in 2 new classes: `TestStory134SarahWarningFlow`, `TestStory134LeakCanary`
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `13-4-browser-sso-session-compatibility` → `review`
- `_bmad-output/implementation-artifacts/13-4-browser-sso-session-compatibility.md` — status → `review`; tasks marked complete; Dev Agent Record filled

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-06-16 | 1.0 | Initial implementation: SSO session-reuse prompt rules, hardcoded-secret detector, auth-setup-needed detector, 27 new backend tests, AC3 leak-canary | claude-sonnet-4-6 |
