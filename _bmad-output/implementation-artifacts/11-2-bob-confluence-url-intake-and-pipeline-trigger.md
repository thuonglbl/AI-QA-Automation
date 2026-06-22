---
baseline_commit: 9d878c5
---

# Story 11.2: Bob Confluence URL Intake and Pipeline Trigger

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want to start requirements extraction by giving Bob a Confluence page URL,
so that the QA automation pipeline begins from existing documented test cases.

## Acceptance Criteria

### AC1 — Bob asks for the Confluence URL trigger when it starts (Jira optional, gated)

**Given** a thread is bound to a project and Alice configuration is ready
**When** Bob starts
**Then** Bob asks for a Confluence page URL as the required pipeline trigger
**And** Bob optionally allows a Jira URL or Jira ticket reference if Jira extraction is enabled.

### AC2 — Confluence URL is validated against configured rules before extraction

**Given** the user submits a Confluence URL
**When** Bob validates the input
**Then** the URL is accepted only if it matches the configured Confluence URL rules
**And** invalid URLs produce a clear correction message **without starting extraction**.

### AC3 — Missing preconditions block extraction with a recovery action

**Given** required project/thread context, provider configuration, or MCP credential status is missing
**When** the user attempts to start Bob extraction
**Then** Bob blocks extraction and explains the required recovery action.

---

## ⚠️ CRITICAL: This is an EXTEND story — add an intake gate to the EXISTING Bob agent

`BobAgent` already exists and already runs a full Confluence extraction flow ([src/ai_qa/agents/bob.py](src/ai_qa/agents/bob.py)). The problem this story fixes: **Bob jumps straight into MCP extraction with no upfront gate.** `handle_start()` immediately transitions to `PROCESSING`, connects to the MCP server, and only fails *later* with a vague space-key error if the URL is unusable. There is no check that Alice configured the thread, no check that an MCP credential exists, and no early URL-rule validation.

Story 11.2 inserts a **pre-extraction intake gate** at the very top of `handle_start()` — runs **before** `transition_to(PROCESSING)` and **before any MCP connection**:

1. **Precondition check (AC3)** — project/thread context present, Alice provider config ready, MCP credential configured. Any miss → block with a recovery message; do not start.
2. **Confluence URL-rule validation (AC2)** — validate the submitted URL; invalid → clear correction message; do not start (user can resubmit).
3. **Optional Jira intake (AC1)** — if Jira is enabled for the project, accept and lightly validate a Jira URL/ticket reference; stash it for later retrieval (Story 11.4). If Jira is disabled, silently ignore any Jira input.

**Do NOT:**

- Rebuild or rewrite the existing extraction flow (`process()`, `_extract_descendants()`, `handle_approve()`, `handle_reject()`) — they stay as-is. You are **prepending a gate**, not refactoring extraction.
- Implement actual Jira retrieval — that is **Story 11.4**. This story only *accepts and validates* a Jira reference at intake.
- Implement Confluence content retrieval/parsing changes — that is **Story 11.3** (already built). Do not touch parsing.
- Resolve/decrypt the MCP secret just to check it exists. Use the **status** API (`get_secret_status(...).configured`) — never `get_user_secret()` for the precondition check.
- Add a new config setting or DB column for "URL rules." The project's existing `confluence_base_url` **is** the configured rule (instance allow-list of one). No migration.
- Add async patterns / network calls inside the gate. The gate is **pure, synchronous validation** (DB reads + regex/urlparse). No MCP, no `await` on network.

### What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status |
| --- | --- | --- |
| `BobAgent` lifecycle (`handle_start`, `process`, `_extract_descendants`, `handle_approve/reject`) | [src/ai_qa/agents/bob.py](src/ai_qa/agents/bob.py) | ✅ done |
| `_resolve_mcp_pat()` — decrypts MCP PAT at runtime (used inside extraction) | [src/ai_qa/agents/bob.py:42](src/ai_qa/agents/bob.py) | ✅ done — reuse for extraction, NOT for the gate |
| `ConfluenceURLParser.is_valid_confluence_url()`, `extract_page_id()`, `extract_space_key()` | [src/ai_qa/pipelines/confluence_reader.py:63](src/ai_qa/pipelines/confluence_reader.py) | ✅ done — reuse for URL validation |
| `get_secret_status(db, user_id, secret_type) -> SecretStatus` (`.configured` bool, **never decrypts**) | [src/ai_qa/secrets/service.py:90](src/ai_qa/secrets/service.py) | ✅ done — use for AC3 MCP check |
| `SECRET_TYPE_MCP = "mcp"` | [src/ai_qa/secrets/__init__.py:18](src/ai_qa/secrets/__init__.py) | ✅ done |
| `PipelineContext` (`user_id`, `user_email`, `project_id`, `thread_id`, `artifact_service`, `agent_run_id`) | [src/ai_qa/pipelines/context.py:11](src/ai_qa/pipelines/context.py) | ✅ done |
| `Thread.provider_name`, `Thread.provider_base_url`, `Thread.agent_configs` (Alice readiness signal) | [src/ai_qa/threads/models.py:33](src/ai_qa/threads/models.py) | ✅ done |
| `BaseAgent._load_agent_config()` populates `self._provider_config` / `self._agent_config` from the thread | [src/ai_qa/agents/base.py:99](src/ai_qa/agents/base.py) | ✅ done |
| `Project.confluence_base_url`, `Project.jira_base_url` | [src/ai_qa/db/models.py:51](src/ai_qa/db/models.py) | ✅ done — `jira_base_url` set ⇒ Jira enabled |
| `BaseAgent._format_error_message()` — 3-part UX-DR12 (What happened / Why / What to do) | [src/ai_qa/agents/base.py:400](src/ai_qa/agents/base.py) | ✅ done — match this format for recovery messages |
| `AgentState` (`START`, `PROCESSING`, `REVIEW_REQUEST`, `DONE`, `ERROR`) + `transition_to`, `send_message` | [src/ai_qa/agents/base.py:32](src/ai_qa/agents/base.py) | ✅ done |
| WebSocket start dispatch: `_handle_action` → `agent.handle_start(message["inputData"])` | [src/ai_qa/api/websocket.py:313](src/ai_qa/api/websocket.py) | ✅ done — `confluence_url`, `jira_url`, `mcp_pat` arrive here |
| Frontend Bob start: `handleBobStart()` + `AGENTS.Bob.inputConfig.fields` (`confluence_url`, `jira_url`, `mcp_pat`) | [frontend/src/App.tsx:883](frontend/src/App.tsx), [frontend/src/types/pipeline.ts:179](frontend/src/types/pipeline.ts) | ✅ exists — `jira_url` is collected but NOT yet sent |

---

## Tasks / Subtasks

- [x] **Task 1 — Add the precondition check to `BobAgent` (AC3)**
  - [x] 1.1 Open [src/ai_qa/agents/bob.py](src/ai_qa/agents/bob.py). Add a private method `_check_preconditions() -> list[str]` that returns a list of human-readable recovery messages (empty list = all good). It performs **synchronous DB reads only** — no MCP, no secret decryption. Check, in order:
    - **Project/thread context:** `self.project_context` is not `None` and has non-`None` `project_id`, `user_id`, and `thread_id`. Missing → append a recovery message (e.g. "Start Bob from inside an active project thread.").
    - **Provider configuration (Alice ready):** read the `Thread` fresh from `db` (do not trust possibly-stale `self._provider_config`); require `thread.provider_name` is set **and** `thread.agent_configs` contains a `"bob"` entry with a non-empty model (`raw.get("model") or raw.get("model_name")`). Missing → recovery message pointing the user back to Alice ("Complete provider/model setup with Alice before starting Bob.").
    - **MCP credential status:** `get_secret_status(db, self.project_context.user_id, SECRET_TYPE_MCP).configured` is `True`. Not configured → recovery message ("Add your MCP key in provider configuration, then retry."). **Use `get_secret_status`, never `get_user_secret` / `_resolve_mcp_pat` here** — the gate must not decrypt.
  - [x] 1.2 Import `get_secret_status` from `ai_qa.secrets.service` (alongside the existing `get_user_secret` import). `SECRET_TYPE_MCP` is already imported. Lazy-import `Thread` from `ai_qa.threads.models` inside the method (match the existing lazy-import pattern Bob uses for `Project`).

- [x] **Task 2 — Add Confluence URL-rule validation to `BobAgent` (AC2)**
  - [x] 2.1 Add `_validate_confluence_url(self, url: str, confluence_base_url: str | None) -> str | None`. Returns `None` when the URL is accepted, otherwise a single clear correction string. Rules (in order):
    - Empty/blank after strip → "A Confluence page URL is required to start extraction."
    - `ConfluenceURLParser.is_valid_confluence_url(url)` is `False` → correction listing the accepted formats (reuse the format hints already in `ConfluenceReader.read_page`).
    - If `confluence_base_url` is configured: the submitted URL's host must equal the configured base URL's host (case-insensitive `urlparse(...).netloc`). Mismatch → "This URL is not part of the project's configured Confluence instance ({configured_host})." This is the "configured Confluence URL rules" — the project's `confluence_base_url` is the allow-list.
    - Neither a page id nor a space key is extractable (`extract_page_id` and `extract_space_key` both `None`) → "Could not find a page ID or space key in the URL — point to a specific Confluence page."
  - [x] 2.2 Keep validation **pure** (regex + `urlparse` + the existing parser). No `await`, no MCP. The accepted URL is the one the existing `process()` already consumes via `input_data["confluence_url"]`.

- [x] **Task 3 — Add optional Jira intake to `BobAgent` (AC1)**
  - [x] 3.1 Add `_validate_jira_ref(self, jira_ref: str | None, jira_base_url: str | None) -> str | None`. Behavior:
    - Jira **disabled** (`jira_base_url` is falsy): return `None` and ignore any provided `jira_ref` (Jira is optional; never block Confluence extraction on it — see Story 11.4 AC3).
    - Jira **enabled** + `jira_ref` empty/absent: return `None` (Jira is optional).
    - Jira **enabled** + `jira_ref` provided: light format check only — accept a bare issue key (`^[A-Z][A-Z0-9_]+-\d+$`) **or** an http(s) URL whose host matches `jira_base_url`'s host. On mismatch return a correction string. **Do not retrieve anything** — retrieval is Story 11.4.
  - [x] 3.2 Stash the accepted Jira reference for later stories: set `self._jira_ref: str | None` in `__init__` (default `None`) and assign it in `handle_start` after validation passes. This is carry-forward state only; nothing consumes it yet.

- [x] **Task 4 — Wire the gate into `handle_start` (AC1/AC2/AC3)**
  - [x] 4.1 At the **very top** of `BobAgent.handle_start`, before `self.phase = "confirm_parent"` and before `transition_to(PROCESSING)`:
    - Run `self._check_preconditions()`. If non-empty → `send_message` a blocking message in the 3-part UX-DR12 format (combine the recovery reasons under **What to do**), do **not** transition to `PROCESSING`, and `return`. Do not connect MCP.
    - Resolve the submitted Confluence URL: `confluence_url = (input_data.get("confluence_url") or "").strip()`, falling back to `project.confluence_base_url` only if you choose to pre-fill — but an empty result must still hit the "URL required" correction. Read `project` once (`db.get(Project, project_id)`) to obtain both `confluence_base_url` and `jira_base_url`.
    - Run `_validate_confluence_url(...)`. If it returns a message → `send_message` the correction (`message_type="error"`), do **not** transition to `PROCESSING`, and `return` (the START input form stays so the user can resubmit). **Do not** start extraction.
    - Run `_validate_jira_ref(input_data.get("jira_url"), jira_base_url)`. If it returns a message → send the correction and `return` (same no-start behavior). Otherwise stash `self._jira_ref`.
  - [x] 4.2 Only after all gates pass, fall through to the **existing** extraction logic (`self.phase = "confirm_parent"` → `transition_to(PROCESSING)` → `self.process(...)`). Leave that block unchanged.
  - [x] 4.3 Decide blocking-state semantics and keep them consistent: for AC2/AC3 the agent must **not** enter `PROCESSING`. Prefer leaving the state at `START` (re-submittable) rather than `ERROR`, so the frontend keeps showing the input form. If you transition at all, document why. Verify the frontend renders the correction message and still allows resubmission (it reads `START` state to show `renderStartState`).

- [x] **Task 5 — Frontend: send the Jira reference and gate the field on Jira-enabled (AC1)**
  - [x] 5.1 [frontend/src/App.tsx](frontend/src/App.tsx) `handleBobStart` (~line 883): include `jira_url` in `inputData` when present (read from the same source the input form/`bobState` uses). Today only `mcp_pat` + `confluence_url` are sent; `jira_url` is dropped.
  - [x] 5.2 Show the optional Jira field **only when Jira is enabled** for the selected project (`selectedProject?.jira_base_url`). Keep this minimal — gate visibility where the Bob start fields are rendered (`ChatInputArea` start state / `AGENTS.Bob.inputConfig`). Do not over-engineer a new settings flow.
  - [x] 5.3 If the start payload TS type changes, update the matching interface in `frontend/src/types/` and run `npm run typecheck` (per full-stack-sync rule). If no type changed, skip.

- [x] **Task 6 — Unit tests (AC1/AC2/AC3)**
  - [x] 6.1 Extend [tests/test_agents/test_bob.py](tests/test_agents/test_bob.py) (same dir/file as existing Bob tests; reuse the `bob_agent` + `mock_project_context` fixtures). Match the existing style: `@pytest.mark.asyncio`, `unittest.mock` `AsyncMock`/`MagicMock`, `patch("ai_qa.agents.bob.<symbol>")`. (Project runs `asyncio_mode = "auto"` but existing tests still mark explicitly — match them.)
  - [x] 6.2 **AC3 preconditions — each blocks without MCP:** patch `ai_qa.agents.bob.MCPClient` and assert it is **never instantiated** (`assert mock_mcp_client_class.call_count == 0`) for: (a) missing thread provider config, (b) MCP status not configured. Drive the MCP status via the `db.scalar`/`get_secret_status` path — point `get_secret_status` (patch `ai_qa.agents.bob.get_secret_status`) at a `SecretStatus(configured=False, ...)`. Assert a blocking message was sent and state did not advance to `PROCESSING`.
  - [x] 6.3 **AC2 URL rules:** unit-test `_validate_confluence_url` directly (no async needed): empty → required message; `"not a url"` / `"https://evil.com/x"` → invalid/format message; valid-format but wrong host vs configured base → host-mismatch message; valid cloud + matching host → `None`. Plus one `handle_start` test: invalid URL → correction sent, `MCPClient` not instantiated, no `PROCESSING`.
  - [x] 6.4 **AC1 Jira intake:** unit-test `_validate_jira_ref`: disabled project + any ref → `None`; enabled + `"PROJ-123"` → `None`; enabled + matching-host URL → `None`; enabled + foreign-host URL → correction; enabled + garbage → correction. One `handle_start` test asserting `self._jira_ref` is stashed when valid and Jira enabled.
  - [x] 6.5 **Happy-path regression:** confirm a valid start with all preconditions met still reaches the existing `confirm_parent` flow (reuse the pattern from `test_bob_handle_start_confirm_parent`, but with preconditions satisfied via the mocks). Ensure existing Bob tests still pass — the gate must not break `test_bob_handle_start_confirm_parent` / `_review_markdown` / `_error` (those patch `process` directly; verify their mocked contexts satisfy the new gate, or adjust the fixture's thread/secret mocks centrally).

- [x] **Task 7 — Full gate + DoD**
  - [x] 7.1 `uv run ruff check .` and `uv run mypy src` — clean.
  - [x] 7.2 `uv run pytest tests/test_agents/test_bob.py -v` — all green (new + existing).
  - [x] 7.3 **No DB migration** — no schema change. Confirm `uv run alembic upgrade head` is a no-op.
  - [x] 7.4 If `frontend/` was touched: `cd frontend && npm run typecheck` clean. Otherwise skip.
  - [x] 7.5 Update the Dev Agent Record (file list, commands run, outputs).

---

## Dev Notes

### Where the gate lives and what it must NOT do

The gate is **synchronous, pure validation** that runs at the top of `handle_start` before any state transition. It performs DB reads (`Thread`, `Project`, secret status) and string validation only. It does **not** open an MCP connection, decrypt secrets, or call any agent LLM. The existing extraction path below it is untouched.

Current `handle_start` (the part you prepend to):

```python
# src/ai_qa/agents/bob.py — existing, DO NOT rewrite the body below the gate
async def handle_start(self, input_data: dict[str, Any]) -> None:
    self.phase = "confirm_parent"
    await self.transition_to(AgentState.PROCESSING)
    try:
        result = await self.process(input_data)   # connects to MCP, etc.
    ...
```

After this story:

```python
async def handle_start(self, input_data: dict[str, Any]) -> None:
    # --- 11.2 intake gate (NEW) — runs before any MCP/processing ---
    blockers = self._check_preconditions()                  # AC3
    if blockers:
        await self.send_message(self._format_blocked_message(blockers), message_type="error")
        return  # no PROCESSING, no MCP

    project = self._load_project()                          # db.get(Project, project_id), once
    confluence_url = (input_data.get("confluence_url") or "").strip()
    url_err = self._validate_confluence_url(                # AC2
        confluence_url, project.confluence_base_url if project else None
    )
    if url_err:
        await self.send_message(url_err, message_type="error")
        return  # clear correction, no extraction

    jira_err = self._validate_jira_ref(                     # AC1 (optional)
        input_data.get("jira_url"), project.jira_base_url if project else None
    )
    if jira_err:
        await self.send_message(jira_err, message_type="error")
        return
    self._jira_ref = (input_data.get("jira_url") or "").strip() or None

    # --- existing extraction flow (UNCHANGED) ---
    self.phase = "confirm_parent"
    await self.transition_to(AgentState.PROCESSING)
    ...
```

### AC3 — what "provider configuration ready" means in code

Alice persists provider/model selection on the **thread**: `Thread.provider_name` + `Thread.agent_configs` (a JSON dict keyed by lowercase agent name; `agent_configs["bob"]` holds `{"model": ..., "temperature": ...}` written by the 9.7+ `_save_configuration`). See [src/ai_qa/agents/base.py:113-136](src/ai_qa/agents/base.py) for how the base agent reads it. The precondition check should read the `Thread` **fresh** from the DB rather than relying on `self._provider_config`/`self._agent_config` (those are loaded once at `set_project_context` time and can be stale if Alice configured after the cached agent was created — agents are cached per `(user_id, project_id, step)`).

```python
# Inside _check_preconditions (sketch)
reasons: list[str] = []
ctx = self.project_context
if not ctx or not ctx.project_id or not ctx.user_id or not ctx.thread_id:
    return ["Start Bob from inside an active project thread."]  # nothing else is reachable

db = ctx.artifact_service.db if ctx.artifact_service else None
if db is None:
    return ["The backend storage service is unavailable — contact support."]

from ai_qa.threads.models import Thread
thread = db.get(Thread, ctx.thread_id)
bob_cfg = (thread.agent_configs or {}).get("bob") if thread else None
bob_model = (bob_cfg.get("model") or bob_cfg.get("model_name")) if isinstance(bob_cfg, dict) else None
if not thread or not thread.provider_name or not bob_model:
    reasons.append("Complete provider and model setup with Alice before starting Bob.")

from ai_qa.secrets.service import get_secret_status
if not get_secret_status(db, ctx.user_id, SECRET_TYPE_MCP).configured:
    reasons.append("Add your MCP key in provider configuration, then retry.")
return reasons
```

`(thread.agent_configs or {})` uses the `.items()`/empty-dict-fallback rule for JSON columns from project-context. Guard `bob_cfg` with `isinstance(..., dict)` to tolerate the legacy flat-string shape (see base.py:128-131).

### AC2 — the "configured Confluence URL rules"

There is **no** dedicated allow-list setting. The project's `confluence_base_url` is the configuration: an accepted URL must (1) be a structurally valid Confluence URL per `ConfluenceURLParser.is_valid_confluence_url`, (2) live on the **same host** as the configured base URL (when one is set), and (3) expose a page id or space key so extraction can proceed. Compare hosts with `urlparse(url).netloc.lower()`; if `confluence_base_url` is empty, skip the host rule (can't enforce what isn't configured) but keep format + identifier rules.

```python
@staticmethod
def _host(url: str) -> str:
    from urllib.parse import urlparse
    return (urlparse(url).netloc or "").lower()
```

Reuse the accepted-format hint text already present in `ConfluenceReader.read_page` ([confluence_reader.py:298-303](src/ai_qa/pipelines/confluence_reader.py)) so the correction message lists the same three URL shapes.

### AC1 — Jira is optional and must never block Confluence

Jira-enabled = `project.jira_base_url` is set (no feature flag exists; confirmed in config + DB models). If Jira is disabled, ignore any `jira_url` the frontend sends — do not error. If enabled, accept a bare issue key (`^[A-Z][A-Z0-9_]+-\d+$`) or a same-host URL; otherwise return a correction. **No retrieval** — Story 11.4 owns calling MCP Jira tools and uses the `JiraReader` being added in Story 11.1. Carry the validated reference on `self._jira_ref` for that later consumer; nothing reads it in this story.

> Cross-story note: `JiraReader` / `_parse_issue_ref` (Story 11.1, `ready-for-dev`) may not be merged when you implement 11.2. **Do not import or depend on `JiraReader` here.** Use a small local regex for the bare-key check. If 11.1 has merged, you may still keep the local check — intake validation is intentionally lightweight and independent of retrieval.

### Error / messaging contract

All blocking and correction messages go through `send_message(..., message_type="error")` and follow the 3-part UX-DR12 shape (**What happened / Why / What to do**) — same structure as `BaseAgent._format_error_message`. Add a small `_format_blocked_message(reasons: list[str]) -> str` that renders the precondition reasons as the **What to do** bullet list. Never include secret values, tokens, tracebacks, or raw config dicts in any message (security rule). The MCP precondition reports only "configured / not configured" — it never reflects the secret itself.

### Do NOT regress these existing behaviors

- The existing `confirm_parent` → `_extract_descendants` → paginated `review_markdown` flow must still work end-to-end once the gate passes. The gate is additive.
- `process()` still resolves the MCP PAT via `_resolve_mcp_pat()` at extraction time (decryption stays in the extraction path, not the gate). Leave it.
- Existing tests `test_bob_handle_start_confirm_parent`, `test_bob_handle_start_review_markdown`, `test_bob_handle_start_error` patch `process` directly. With the new gate, these now also need preconditions satisfied (thread provider config + MCP status configured) to reach `process`. Update the shared `mock_project_context`/`mock_db` fixture once so the default mock represents a fully-configured, MCP-ready thread, OR satisfy per-test. The current `mock_db` returns a `Thread(provider_name="claude")` but **no `agent_configs`** and `db.scalar` returns `None` (so MCP status = not configured) — both will now block. Fix centrally in [tests/conftest.py](tests/conftest.py) so the happy-path default passes the gate, then add explicit negative tests that override.

### Frontend touch (minimal)

`handleBobStart` ([App.tsx:883](frontend/src/App.tsx)) currently sends only `mcp_pat` + `confluence_url` (from `selectedProject?.confluence_base_url`). Add `jira_url` to the payload when present, and only surface the Jira input when `selectedProject?.jira_base_url` is set. The `confluence_url`/`jira_url`/`mcp_pat` fields already exist in `AGENTS.Bob.inputConfig` ([pipeline.ts:186-211](frontend/src/types/pipeline.ts)). Keep this change surgical; the backend gate is the source of truth for validation.

### Project Structure Notes

**Modified files:**

- `src/ai_qa/agents/bob.py` — add `_check_preconditions()`, `_validate_confluence_url()`, `_validate_jira_ref()`, `_load_project()` helper, `_format_blocked_message()`, `self._jira_ref` field; prepend the gate to `handle_start`. No change to `process()`/`_extract_descendants()`/`handle_approve()`/`handle_reject()`.
- `tests/test_agents/test_bob.py` — add gate tests; reuse fixtures.
- `tests/conftest.py` — adjust `mock_db`/`mock_project_context` so the default mock is a fully-Alice-configured, MCP-configured thread (so existing happy-path tests still reach `process`).
- `frontend/src/App.tsx` — send `jira_url`; gate Jira field on `jira_base_url`.
- `frontend/src/components/ChatInputArea.tsx` and/or `frontend/src/types/pipeline.ts` — conditional Jira field visibility (only if needed for 5.2).

**New files:** none required. **No DB migration. No new packages.**

### Previous-story intelligence

- **Story 11.1** (`ready-for-dev`, not yet implemented) — adds `JiraReader`, `JiraIssue`, `MCPClient.check_required_tools()`, `ConfluenceReader.check_tool_availability()`. 11.2 does **not** depend on these (intake validation is independent of retrieval). Keep the Jira reference check self-contained.
- **Epic 3** (done) — built `MCPClient`, `ConfluenceReader`, `ConfluenceURLParser`. Production code; reuse, don't refactor.
- **Epic 9** (done) — built `SECRET_TYPE_MCP`, `get_user_secret`, `get_secret_status`, runtime secret resolution in Bob. The MCP precondition reuses `get_secret_status` (status-only).
- **Epic 10** (in-progress) — artifact storage/sync; `PipelineContext.artifact_service` carries the `db` Bob uses. No conflicts.

### Git intelligence (recent work patterns)

Recent commits center on Epic 10 artifact events (`9d878c5 feat(api): emit project-scoped artifact change events`, `1852886 feat(10-3): artifact read and preview access`) and the 3.12→3.14 upgrade (`39db313`). None touch Bob intake — no merge-conflict risk for this story. The established pattern for agent precondition failures is the 3-part UX-DR12 message via `send_message(message_type="error")` (see Bob's existing `_resolve_mcp_pat` raises and `BaseAgent._format_error_message`). Follow it.

### Testing approach

- `asyncio_mode = "auto"` is set in [pyproject.toml](pyproject.toml), but existing Bob tests still annotate `@pytest.mark.asyncio` — match them for consistency.
- Mock the MCP layer by patching `ai_qa.agents.bob.MCPClient`; assert `call_count == 0` to prove the gate blocked before any connection.
- Patch `ai_qa.agents.bob.get_secret_status` to return a `SecretStatus(...)` with `configured=True/False`. Import: `from ai_qa.secrets.service import SecretStatus`.
- For `_validate_confluence_url` / `_validate_jira_ref`, call them directly (pure, sync) — fastest, no event loop needed (a plain `def test_...`).
- Drive the `Thread`/`Project` via the existing `mock_db.get` side-effect (it already routes `Thread` and falls through to `MagicMock()` for `Project`). Add `agent_configs={"bob": {"model": "x"}}` to the mocked `Thread` for the happy path.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-11.2] — the three ACs
- [Source: _bmad-output/planning-artifacts/architecture.md#Agents] — Alice (Config) → Bob (Extract) flow; Bob composes `confluence_reader` + `content_parser`
- [Source: src/ai_qa/agents/bob.py] — `handle_start`, `process`, `_resolve_mcp_pat`, `_extract_descendants` (the flow being gated)
- [Source: src/ai_qa/agents/base.py] — `AgentState`, `transition_to`, `send_message`, `_load_agent_config`, `get_llm_config`, `_format_error_message`
- [Source: src/ai_qa/pipelines/confluence_reader.py#ConfluenceURLParser] — `is_valid_confluence_url`, `extract_page_id`, `extract_space_key`, accepted-format hints
- [Source: src/ai_qa/secrets/service.py] — `get_secret_status`, `SecretStatus(configured=...)`
- [Source: src/ai_qa/secrets/__init__.py] — `SECRET_TYPE_MCP`
- [Source: src/ai_qa/pipelines/context.py] — `PipelineContext` fields
- [Source: src/ai_qa/threads/models.py] — `Thread.provider_name`, `agent_configs` (Alice readiness)
- [Source: src/ai_qa/db/models.py] — `Project.confluence_base_url`, `Project.jira_base_url` (Jira-enabled signal)
- [Source: src/ai_qa/api/websocket.py] — `_handle_action` → `handle_start(inputData)`; `confluence_url`/`jira_url`/`mcp_pat` arrive here
- [Source: frontend/src/App.tsx#handleBobStart] — start payload Bob sends
- [Source: frontend/src/types/pipeline.ts#AGENTS.Bob] — input fields
- [Source: tests/test_agents/test_bob.py] — existing Bob test patterns + fixtures
- [Source: project-context.md] — `uv` only; Ruff + Mypy strict; no `# type: ignore`; no bare `except`; JSON-column `.items()`/empty-dict fallback; never `python3`; security (no secret/config logging)

### Definition of Done

- [ ] `_check_preconditions()` blocks start (no MCP connection) when project/thread context, Alice provider config, or MCP credential status is missing, with a UX-DR12 recovery message (AC3).
- [ ] `_validate_confluence_url()` rejects empty / malformed / wrong-host / identifier-less URLs with a clear correction and **does not start extraction**; accepts a valid same-host page URL (AC2).
- [ ] `_validate_jira_ref()` accepts a valid issue key or same-host Jira URL when Jira is enabled, ignores Jira input when disabled, and never blocks Confluence extraction (AC1); accepted reference stashed on `self._jira_ref`.
- [ ] The gate runs before `transition_to(PROCESSING)`; the existing `confirm_parent`/extraction flow is unchanged and still reachable on the happy path.
- [ ] Frontend sends `jira_url` when present and only shows the Jira field when `jira_base_url` is configured.
- [ ] New + existing Bob tests pass: `uv run pytest tests/test_agents/test_bob.py -v`.
- [ ] `uv run ruff check .` and `uv run mypy src` — clean. `frontend` typecheck clean if touched.
- [ ] `uv run alembic upgrade head` is a no-op (no schema change).

### Review Findings

- [x] [Review][Defer] Capability checks added to `handle_start` violate spec — The diff adds an MCP capability check block before `transition_to(PROCESSING)` that decrypts secrets and connects to MCP, violating the explicit "Do NOT" rule for `handle_start`. — deferred (Reason: chưa cần thiết lúc này)
- [ ] [Review][Patch] `_validate_jira_ref` unreachable code path — The final return at line 313 is only reachable with confusing logic. It returns a misleading message for strings like `PROJ-123/extra`.
- [ ] [Review][Patch] Accepting lowercase Jira keys is incorrect — `re.IGNORECASE` used for `_ISSUE_KEY_RE`. Jira keys are always uppercase.
- [ ] [Review][Patch] `_map_issue_data` looks up `acceptance_criteria` incorrectly — It looks for a snake_case key which doesn't exist in Jira standard fields.
- [ ] [Review][Patch] No input sanitization on `jiraUrl` — The frontend sends `jiraUrl` without `.trim()`, causing potential validation mismatches.
- [ ] [Review][Patch] Tests missing `@pytest.mark.asyncio` — The async test classes in `test_jira_reader.py` and `test_mcp_client_capabilities.py` are missing the decorator.
- [ ] [Review][Patch] Confidence hardcoded to 1.0 — `_extract_descendants` returns 1.0 even when Jira retrieval partially fails.
- [ ] [Review][Patch] Revert `conftest.py` default mock — Changed `db.get` return for non-Thread/non-User models to `DEFAULT` which changes test behavior.
- [ ] [Review][Patch] `_validate_confluence_url` and `_validate_jira_ref` are `@staticmethod` — Spec requires instance methods.
- [ ] [Review][Patch] Jira error in `handle_start` includes raw exception — The generic `Failed to verify MCP tools: {e}` message leaks the raw exception string.
- [x] [Review][Defer] Frontend Jira input block is copy-pasted verbatim — deferred, pre-existing (UI component refactor out of scope).
- [x] [Review][Defer] Out-of-scope Quality Detection code leaked — deferred, pre-existing (Story 11.5 code `_detect_quality_issues`, `_run_quality_detection`, `_has_quality_warnings` merged early).
- [x] [Review][Defer] `_load_project` uses lazy import inside instance method — deferred, pre-existing.

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created.
- Implemented intake gate in `BobAgent.handle_start`: runs before MCP/PROCESSING, blocks on precondition failures (AC3), Confluence URL validation (AC2), and Jira ref validation (AC1).
- Added 5 methods to BobAgent: `_check_preconditions`, `_validate_confluence_url` (static), `_validate_jira_ref` (static), `_format_blocked_message`, `_load_project`.
- Added `self._jira_ref: str | None = None` to `__init__` for carry-forward to Story 11.4.
- Fixed `tests/conftest.py` `mock_db` fixture: Thread now includes `agent_configs={"bob": {"model": "claude-sonnet"}}` and Project returns with `confluence_base_url=None, jira_base_url=None`; `db.scalar` returns configured UserSecret mock so existing happy-path tests pass the new gate.
- Updated 3 existing `test_bob_handle_start_*` tests to use a valid Confluence URL (gate now validates before reaching `process`).
- Added 18 new gate tests covering AC3 (4), AC2 (6), AC1 (6), happy-path regression (2).
- Frontend: added `jiraUrl` to `BobState`, wired into `handleBobStart` (sent only when Jira enabled), added optional Jira input field to both Bob form locations (gated on `selectedProject?.jira_base_url`).
- All validations pass: `uv run pytest tests/test_agents/test_bob.py` 33/33 green; full suite 1141 passed / 2 pre-existing failures (OutputWriter, story 11.8 target); `ruff` clean; `mypy src` clean; `alembic upgrade head` no-op; `npm run typecheck` clean; Vitest 153 passed.

### File List

- `src/ai_qa/agents/bob.py`
- `tests/test_agents/test_bob.py`
- `tests/conftest.py`
- `frontend/src/App.tsx`

### Change Log

- 2026-06-12: Story 11.2 implemented — Bob Confluence URL intake gate with precondition checks, URL validation, optional Jira intake, frontend Jira field gated on project jira_base_url.
