---
baseline_commit: 9d878c5
---

# Story 11.4: Jira Requirements Retrieval

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want Bob to retrieve test-related requirements from Jira,
so that Confluence source content can be supplemented with ticket-level context.

## Acceptance Criteria

### AC1 — Jira extraction starts only when Jira tools AND MCP credentials are available

**Given** the user provides a Jira URL, project key, or ticket reference
**When** Bob validates Jira input
**Then** Jira extraction starts only if Jira MCP tools are available and user MCP credentials are configured.

### AC2 — Test-related requirements retrieved from matching Jira tickets with rich content

**Given** Jira extraction starts
**When** Bob calls MCP Jira tools
**Then** test-related requirements are retrieved from matching Jira tickets
**And** retrieved ticket content includes relevant title, description, acceptance criteria, labels/status where available, and source reference.

### AC3 — Jira is optional and never fails the whole extraction

**Given** Jira input is optional or unavailable
**When** Confluence extraction can continue without Jira
**Then** Bob continues Confluence-only extraction and reports Jira as skipped or unavailable without failing the whole extraction.

---

## ⚠️ CRITICAL: This is the CONSUME story — turn the stashed Jira reference into a retrieved, reviewable ticket

Two prerequisite stories build everything this story needs; **11.4 is where the Jira reference is actually retrieved and surfaced.** Understand the dependency chain before writing any code:

- **Story 11.1** (`ready-for-dev`) builds the **retrieval engine**: `JiraReader` ([src/ai_qa/pipelines/jira_reader.py](src/ai_qa/pipelines/jira_reader.py)) with `read_issue(issue_ref)`, `check_tool_availability()`, `_parse_issue_ref()`, `JIRA_TOOLS`; plus the `JiraIssue` Pydantic model in [src/ai_qa/pipelines/models.py](src/ai_qa/pipelines/models.py). **11.4 calls these — it does not rebuild them.**
- **Story 11.2** (`ready-for-dev`) builds the **intake gate**: it validates an optional Jira URL / issue key at `handle_start` and stashes the accepted reference on `self._jira_ref` ([src/ai_qa/agents/bob.py](src/ai_qa/agents/bob.py)). **11.4 reads `self._jira_ref` — it does not re-validate at intake.**
- **Story 11.4** (this story) **wires `JiraReader` into Bob's live extraction path**: after Confluence pages are built in `_extract_descendants`, retrieve the referenced Jira ticket (best-effort), render it to Markdown, and append it as a review item to `self.pages` so it flows through the existing paginated review UI. If Jira tools or credentials are unavailable, or retrieval fails, **skip Jira and continue Confluence-only — never break the extraction** (AC3).

**The problem 11.4 solves:** Today `BobAgent._extract_descendants` ([bob.py:322](src/ai_qa/agents/bob.py)) extracts Confluence pages only. There is **no Jira call anywhere** in the agent. `self._jira_ref` (once 11.2 lands) is dead carry-forward state that nothing consumes. 11.4 is the consumer.

### Hard vs. soft dependencies — read this carefully

- **HARD prerequisite (11.1):** `JiraReader` and `JiraIssue` must exist. The natural build order is 11.1 → 11.2 → 11.3 → 11.4; by the time you implement 11.4 they should be merged. **If 11.1 is NOT merged, this story is blocked** — implement 11.1 first. Do not stub a fake `JiraReader` inside Bob.
- **HARD-ish prerequisite (11.2):** `self._jira_ref` is set by 11.2's gate. **Defensive read:** use `getattr(self, "_jira_ref", None)` so 11.4 degrades to "no Jira requested" if 11.2's field is absent, and add `self._jira_ref: str | None = None` to `BobAgent.__init__` if it is not already there (idempotent — 11.2 also adds it; keep a single definition). This keeps 11.4 independently testable.
- **SOFT, runtime (AC1/AC3):** "Jira tools available" is a **runtime capability check** via `JiraReader.check_tool_availability()`. Missing tools → skip gracefully. "MCP credentials configured" is already guaranteed: extraction only reaches `_extract_descendants` after 11.2's precondition gate passed and `_resolve_mcp_pat()` succeeded, so the connected client already carries a valid PAT.

**Do NOT:**

- Rebuild or modify `JiraReader` / `JiraIssue` / `MCPClient.check_required_tools` — they are Story 11.1 deliverables. You **call** them.
- Open a **second** `MCPClient`. `_extract_descendants` already constructs exactly one connected client (pinned by `test_bob_extract_descendants_creates_single_mcp_client`). **Reuse that same `client`** to build `JiraReader`. Adding Jira must not change the MCP client count.
- Touch `handle_start`'s intake gate or `_validate_jira_ref` — that is Story 11.2's territory. 11.4 only consumes `self._jira_ref`.
- Let any Jira error escape. Wrap the entire Jira step so that connection errors, tool errors, or mapping errors are caught and reported as a skip — the Confluence `self.pages` must survive intact (AC3).
- Run the LLM `RequirementFormatter` on Jira content for M1. Render Jira fields to Markdown with a small deterministic helper. (See Resolved Decisions.)
- Add a DB migration, a new package, or a frontend change. Jira review items reuse the existing `self.pages` dict shape the review UI already renders.
- Implement project-key **multi-ticket search** — 11.1 only built single-ticket `read_issue`. Multi-ticket search is out of scope for M1 (see Saved Questions).

### What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives | Status |
| --- | --- | --- |
| `JiraReader(mcp_client, jira_base_url, settings)` — `read_issue(issue_ref) -> StageResult(data=JiraIssue)`, `check_tool_availability() -> list[str]`, `_parse_issue_ref()`, `JIRA_TOOLS` | [src/ai_qa/pipelines/jira_reader.py](src/ai_qa/pipelines/jira_reader.py) | ⚠️ **Story 11.1 deliverable — HARD prerequisite, must be merged** |
| `JiraIssue` model (`issue_key`, `summary`, `description`, `acceptance_criteria`, `status`, `labels`, `project_key`, `url`, `retrieved_at`, `issue_type`, `reporter`, `assignee`) | [src/ai_qa/pipelines/models.py](src/ai_qa/pipelines/models.py) | ⚠️ **Story 11.1 deliverable** |
| `self._jira_ref` — validated Jira reference stashed at intake | [src/ai_qa/agents/bob.py](src/ai_qa/agents/bob.py) `handle_start` | ⚠️ **Story 11.2 deliverable — read via `getattr`** |
| `BobAgent._extract_descendants` — Confluence extraction that builds `self.pages` (the method you extend) | [src/ai_qa/agents/bob.py:322](src/ai_qa/agents/bob.py) | ✅ done |
| Single connected `MCPClient` inside `_extract_descendants` (reuse for `JiraReader`) | [src/ai_qa/agents/bob.py:332](src/ai_qa/agents/bob.py) | ✅ done |
| `project = db.get(Project, project_id)` already loaded in `_extract_descendants`; `project.jira_base_url` | [src/ai_qa/agents/bob.py:351](src/ai_qa/agents/bob.py), [src/ai_qa/db/models.py:61](src/ai_qa/db/models.py) | ✅ done — `jira_base_url` set ⇒ Jira enabled |
| `self.pages` review-item dict shape: `page_id`, `page_title`, `source_url`, `raw_html`, `requirement_md` | [src/ai_qa/agents/bob.py:461](src/ai_qa/agents/bob.py) | ✅ done — **append Jira items in the same shape** |
| Frontend review renderer consumes that exact shape; pagination over `pages` already works | [frontend/src/App.tsx:178](frontend/src/App.tsx), [frontend/src/components/SplitPanel.tsx:8](frontend/src/components/SplitPanel.tsx) | ✅ done — **no frontend change needed** |
| `StageResult` (`success`, `data`, `errors`, `warnings`, `confidence`) | [src/ai_qa/models.py](src/ai_qa/models.py) | ✅ done — Jira skip reasons go into `warnings` |
| `send_message(content, message_type, metadata=...)` for user-visible status/warnings | [src/ai_qa/agents/base.py](src/ai_qa/agents/base.py) | ✅ done |
| `AppSettings`, `MCPClient`, `get_user_secret`, `SECRET_TYPE_MCP` already imported in bob.py | [src/ai_qa/agents/bob.py:7-16](src/ai_qa/agents/bob.py) | ✅ done |

---

## Tasks / Subtasks

- [x] **Task 1 — Imports + carry-forward state (prereq wiring)**
  - [x] 1.1 Open [src/ai_qa/agents/bob.py](src/ai_qa/agents/bob.py). Add imports at the top: `from ai_qa.pipelines.jira_reader import JiraReader` and extend the existing models import to `from ai_qa.pipelines.models import ConfluencePage, JiraIssue`. (Both are Story 11.1 deliverables — if `ImportError`, 11.1 is not merged and this story is blocked; do not stub.)
  - [x] 1.2 In `BobAgent.__init__` ([bob.py:28-40](src/ai_qa/agents/bob.py)), ensure `self._jira_ref: str | None = None` exists. Story 11.2 also adds this; keep exactly one definition (idempotent). This guarantees `_extract_descendants` never `AttributeError`s on `self._jira_ref` even when run by a unit test that does not go through `handle_start`.

- [x] **Task 2 — Deterministic Jira→Markdown renderer (AC2)**
  - [x] 2.1 Add a pure, synchronous helper `def _format_jira_markdown(self, issue: JiraIssue) -> str`. Render the ticket fields into clean Markdown that the existing review panel can show as `requirement_md`. Include **only the fields that are present** (skip empty ones), and always include the source reference:
    - `# [{issue.issue_key}] {issue.summary}`
    - A metadata line: status, issue type, labels — each shown only when set (e.g. `**Status:** In Progress · **Type:** Story · **Labels:** auth, regression`). `labels` is a `list[str]` — render it with `", ".join(issue.labels)` (never the raw list, which would print `['auth', 'regression']`), and omit the entire Labels segment when the list is empty.
    - `**Source:** [{issue.issue_key}]({issue.url})`
    - `## Description` + `issue.description` (only if non-empty)
    - `## Acceptance Criteria` + `issue.acceptance_criteria` (only if non-empty)
  - [x] 2.2 Keep it deterministic and side-effect-free (no MCP, no LLM, no `await`). This is the M1 rendering — the LLM `RequirementFormatter` is **not** used for Jira (see Resolved Decisions). Guard every optional field with `or ""` / truthiness so `None` never leaks into the output.

- [x] **Task 3 — Best-effort Jira retrieval method (AC1 + AC2 + AC3)**
  - [x] 3.1 Add `async def _retrieve_jira_requirements(self, client: MCPClient, jira_base_url: str | None) -> list[str]`. It **appends** any retrieved Jira ticket to `self.pages` and **returns** a list of user-safe warning strings (for merging into the final `StageResult.warnings`). It reuses the **already-connected** `client` — it must NOT create a new `MCPClient` and must NOT call `client.connect()`/`disconnect()` (the caller owns the client lifecycle).
  - [x] 3.2 Wrap the **entire body** in a single `try/except Exception` so no error can escape (AC3). On any caught exception: `logger.error(...)`, `send_message` a user-safe "Jira step skipped" warning, and `return [<warning>]`. Never re-raise. Never include tokens/tracebacks/raw payloads in the message (security rule).
  - [x] 3.3 Inside the try, implement the gates in order:
    - **Not requested:** `jira_ref = getattr(self, "_jira_ref", None)`. If falsy → `return []` (no Jira input; silent — not a warning).
    - **Jira disabled:** if not `jira_base_url` → `return []` (project has no Jira instance configured; silent).
    - **Tool availability (AC1):** build `reader = JiraReader(client, jira_base_url)`; `missing = await reader.check_tool_availability()`. If `missing` is non-empty → `send_message("⚠ Jira skipped — required tools are not available on the MCP server.", "warning")` and `return ["Jira skipped: MCP Jira tools unavailable"]`. **Do not call `read_issue` when tools are missing** (AC1: "starts only if Jira MCP tools are available").
    - **Retrieve (AC2):** `result = await reader.read_issue(jira_ref)`. If `not result.success` or `result.data is None` → `send_message("⚠ Could not retrieve the referenced Jira ticket — continuing with Confluence only.", "warning")` and `return ["Jira ticket retrieval failed; skipped"]`. (`read_issue` returns `StageResult(success=False, ...)` on soft failure per 11.1 — handle it, do not assume it raises.)
    - **Append review item (AC2):** narrow `issue: JiraIssue = result.data`, then append to `self.pages` with `source_type="jira"`, `raw_html=""`, `requirement_md=self._format_jira_markdown(issue)`.
      `send_message(f"✓ Retrieved Jira ticket {issue.issue_key}", "info")` and `return []` (success → no warning).
  - [x] 3.4 The returned warning list is the AC3 "reports Jira as skipped or unavailable" signal at the data layer; the `send_message` calls are the user-facing signal. Both must be present.

- [x] **Task 4 — Wire the Jira step into `_extract_descendants` (AC2 + AC3)**
  - [x] 4.1 In `_extract_descendants`, capture `jira_base_url: str | None = None` alongside `confluence_base_url = None`, and set it inside the `if project:` block.
  - [x] 4.2 Insert `jira_warnings = await self._retrieve_jira_requirements(client, jira_base_url)` after the Confluence `if not self.pages:` guard and before the final success return.
  - [x] 4.3 Merge Jira warnings: `warnings=jira_warnings` in the success `StageResult`.
  - [x] 4.4 `except`/`raise`/`finally: disconnect()` blocks are unchanged.
  - [x] 4.5 Exactly one `MCPClient(...)` construction confirmed — `test_bob_extract_descendants_creates_single_mcp_client` still passes.

- [x] **Task 5 — Unit tests (AC1/AC2/AC3)**
  - [x] 5.1–5.9 All 11 new tests added to [tests/test_agents/test_bob.py](tests/test_agents/test_bob.py); all 43 tests pass.

- [x] **Task 6 — Full gate + DoD**
  - [x] 6.1 `uv run ruff check .` — clean. `uv run mypy src` — clean (80 files, no issues).
  - [x] 6.2 `uv run pytest tests/test_agents/test_bob.py -v --no-cov` — 43 passed. `tests/pipelines/test_jira_reader.py` — 25 passed.
  - [x] 6.3 `uv run alembic upgrade head` — no-op confirmed.
  - [x] 6.4 Frontend not touched.
  - [x] 6.5 Dev Agent Record updated below.

---

## Dev Notes

### The exact edit site in `_extract_descendants`

The success tail of the method today ([bob.py:474-505](src/ai_qa/agents/bob.py)):

```python
            if not self.pages:
                return StageResult(success=False, data=None,
                                   errors=["All pages failed to extract or convert"], ...)

            await self.send_message(content="Requirements extraction complete.", ...)

            return StageResult(success=True, data=self.pages, errors=[], warnings=[], confidence=1.0)
        except Exception as e:
            logger.error(f"Error in Bob _extract_descendants: {e}", exc_info=True)
            raise
        finally:
            await client.disconnect()
```

After this story. Note the `except`/`raise`/`finally` block is **unchanged** — only the two Jira lines and `warnings=jira_warnings` are new. `jira_base_url` is the hoisted local captured inside the project block (Task 4.1), **not** `project.jira_base_url` at the tail (`project` is not safely bound here):

```python
            if not self.pages:
                return StageResult(success=False, data=None,
                                   errors=["All pages failed to extract or convert"], ...)

            # --- 11.4: supplement Confluence with Jira (best-effort, never fatal) ---
            # jira_base_url was captured inside the `if project:` block above (Task 4.1)
            jira_warnings = await self._retrieve_jira_requirements(client, jira_base_url, settings)

            await self.send_message(content="Requirements extraction complete.", ...)

            return StageResult(success=True, data=self.pages, errors=[],
                               warnings=jira_warnings, confidence=1.0)
        except Exception as e:                      # UNCHANGED — regression test depends on re-raise
            logger.error(f"Error in Bob _extract_descendants: {e}", exc_info=True)
            raise
        finally:
            await client.disconnect()
```

> Variable-scope rule (authoritative): `project` is assigned only inside the `if self.project_context and self.project_context.artifact_service:` block ([bob.py:347-353](src/ai_qa/agents/bob.py)) — it is a conditionally-bound function local, not in scope-safe form at the tail. Capture `jira_base_url` the same way `confluence_base_url` is: init `jira_base_url: str | None = None` at [bob.py:346](src/ai_qa/agents/bob.py), assign `jira_base_url = project.jira_base_url` inside the `if project:` block, and reference only the `jira_base_url` local at the tail. Never reference `project` at the tail; never add a second `db.get(Project, ...)`. Only `client` and `settings` are reliably in scope at the insertion point.

### Why reuse the connected client (single-MCP-client invariant)

`test_bob_extract_descendants_creates_single_mcp_client` asserts exactly **one** `MCPClient` is constructed in `_extract_descendants`. `JiraReader` takes a client, it does not own one — pass the already-connected `client`. The client's `connect()`/`disconnect()` lifecycle stays with `_extract_descendants` (`disconnect()` in the shared `finally`). Building `JiraReader` does not open a connection, so the count stays at 1. **If you add `MCPClient(...)` for Jira, you break that test and the connection-pool contract.**

### AC1 — "starts only if Jira tools are available and MCP credentials are configured"

Two conditions, both already satisfiable without new infra:

1. **MCP credentials configured** — guaranteed by the time control reaches `_extract_descendants`: Story 11.2's gate blocks start unless the MCP secret status is configured, and `_resolve_mcp_pat()` ([bob.py:42](src/ai_qa/agents/bob.py)) decrypted a non-empty PAT to connect `client`. No extra credential check is needed here.
2. **Jira tools available** — `JiraReader.check_tool_availability()` (Story 11.1). Returns the list of **missing** required tools; empty list = all present. Only call `read_issue` when it returns empty. This is the AC1 runtime gate.

### AC2 — what content the ticket must carry

`JiraReader.read_issue` returns a `JiraIssue` with `summary`, `description`, `acceptance_criteria`, `status`, `labels`, `issue_type`, `url`, `issue_key` (mapped defensively from the MCP tool payload by 11.1). `_format_jira_markdown` packs title + description + acceptance criteria + status/labels into `requirement_md`, and `source_url` carries the source reference — exactly the AC2 field list ("title, description, acceptance criteria, labels/status where available, and source reference"). "Where available" = render only the fields that are non-empty.

### AC3 — Jira is a best-effort supplement, never a blocker

The whole Jira step is wrapped so it can only ever **add** to `self.pages` or **report a skip** — it can never fail the extraction:

- No `self._jira_ref` (user gave no Jira input) → silent no-op.
- `project.jira_base_url` unset (Jira not enabled for the project) → silent no-op.
- Jira tools missing → user-visible "skipped" warning + warning string; Confluence pages untouched.
- `read_issue` soft-fails (`StageResult.success=False`) → "skipped" warning; Confluence pages untouched.
- Any exception (connection/tool/mapping) → caught, logged, "skipped" warning; **re-raise is forbidden**.

In all skip cases `_extract_descendants` still returns `success=True` with the Confluence `self.pages`, and the run proceeds to review. This is the literal AC3 contract.

### M1 scope: single referenced ticket (not project-key search)

Story 11.2 stashes a **single** validated reference (a bare issue key like `PROJ-123` or a same-host Jira URL), and Story 11.1 built only `read_issue` (single-ticket). So M1 retrieves **the one referenced ticket**. The epic AC1 mentions "project key" as a possible input and AC2 says "matching tickets" (plural), but neither 11.1's reader surface nor 11.2's validator supports a project-key → multi-ticket search (`jira_search_issues` is declared in `JIRA_TOOLS` but no reader method wraps it). Multi-ticket search is **out of scope for M1** — see Saved Questions. Do not invent a search method here.

### Jira review item shares the Confluence page shape (no frontend change)

The review UI iterates `pages` and renders `page_title`, `source_url`, `requirement_md`, `raw_html` ([App.tsx:178](frontend/src/App.tsx), [SplitPanel.tsx:8](frontend/src/components/SplitPanel.tsx)). A Jira ticket maps onto the same keys (`raw_html=""` since there is no HTML source view). The extra `source_type` / `warnings` keys are ignored by the TS interface at runtime and are forward-compat carriers for 11.5 (quality detection), 11.6 (review rendering of source type + warnings), and 11.7 (artifact metadata `source type`). Appending a Jira item therefore needs **zero** frontend work.

### Reject/reprocess on a Jira item

`handle_reject` re-runs `process(feedback=...)` on the current page, which currently returns the page unchanged ([bob.py:139-153](src/ai_qa/agents/bob.py)). A reject on a Jira review item is thus a no-op re-process — acceptable for M1; per-item Jira reprocessing UX is Story 11.6's concern. No special handling is required in 11.4.

### Project-context rules that bite here

- **Type safety / narrow Optional:** `StageResult.data` is `Any | None`. After `read_issue`, guard `if not result.success or result.data is None: ...` then bind `issue: JiraIssue = result.data` before accessing `.summary` etc. (Pyrefly "narrow Optional before use"). No `# type: ignore`.
- **`StageResult`'s real field set:** it is exactly `{success, data, errors: list[str], warnings: list[str], confidence}` ([src/ai_qa/models.py](src/ai_qa/models.py)) — there is **no** singular `error` field and **no** `metadata` field. Read soft-failure via `not result.success or result.data is None`; construct failures with `errors=["…"]` (a list). Pydantic ignores unknown kwargs, so `StageResult(error=…, metadata=…)` would not raise but the values would be silently dropped — if the merged Story 11.1 `read_issue` was written with `error=`/`metadata=` kwargs, fix it there before relying on its error text.
- **No bare `except`** in production logic except the **one** intentional `except Exception` that guarantees AC3 (it logs + returns a warning, never silently swallows). In tests, any `pytest.raises` must include `match=` (project rule) — but note 11.4's design means `_retrieve_jira_requirements` should **not** raise, so the AC3 test asserts a returned value, not a raise.
- **Security:** never log the raw Jira payload, MCP token, or full config. Warning/skip messages are user-safe strings only (no ticket bodies, no tokens).
- **JSON / optional fields:** use `value or ""` / truthiness guards when rendering optional `JiraIssue` fields.
- **`uv` only**, never `pip`; **never `python3`** — use `uv run` / `py -3`. Force `PYTHONUTF8=1` only for BMAD emoji scripts, not for pytest.

### Do NOT regress these existing behaviors

- The `confirm_parent` → `_extract_descendants` → paginated `review_markdown` flow must still work end-to-end. The Jira step is purely additive at the tail.
- `_extract_descendants` still constructs exactly **one** `MCPClient` and `disconnect()`s it in `finally` (pinned by tests). `JiraReader` reuses the client and opens no connection.
- The review payload shape (`metadata={"is_review_ready": True, "pages": self.pages}`) in `handle_approve` is unchanged — you only append items (with extra keys) to `self.pages`.
- `process()` (Confluence parent suggestion) and `handle_start` are untouched.

### Testing approach (match the house style)

- `asyncio_mode = "auto"` is set, but existing Bob tests annotate `@pytest.mark.asyncio` — match them.
- Patch at the Bob module boundary: `patch("ai_qa.agents.bob.JiraReader")`. `JiraReader.check_tool_availability` and `read_issue` are `async` → `AsyncMock`. Set `mock_reader = mock_jira_reader_class.return_value` and configure `mock_reader.check_tool_availability = AsyncMock(return_value=[...])`, `mock_reader.read_issue = AsyncMock(return_value=StageResult(...))`.
- Drive `_retrieve_jira_requirements` directly with a `MagicMock()` client (it never calls `connect`/`disconnect`, so an `AsyncMock` client also works) — fastest, isolates the Jira logic from Confluence.
- For the integration test (5.8), reuse the `test_bob_extract_descendants_disconnects_mcp_on_completion` scaffold and add a successful `read_page_by_id` + a `JiraReader` patch.
- Build real `JiraIssue` instances for `read_issue` data so `_format_jira_markdown` and the dict-carry assertions exercise real field access. Import: `from ai_qa.pipelines.models import JiraIssue`.

### Project Structure Notes

**Modified files:**

- `src/ai_qa/agents/bob.py` — import `JiraReader` + `JiraIssue`; ensure `self._jira_ref` init; add `_format_jira_markdown()` and `_retrieve_jira_requirements()`; call the Jira step at the tail of `_extract_descendants`; merge Jira warnings into the success `StageResult`. No change to `handle_start`/`process`/`handle_approve`/`handle_reject`.
- `tests/test_agents/test_bob.py` — add the Jira retrieval/format/skip/exception/integration tests; add a defensive `patch("ai_qa.agents.bob.JiraReader")` to the existing extract-descendants tests.

**New files:** none. **No DB migration. No new packages. No frontend changes.**

### Previous-story intelligence

- **Story 11.1** (`ready-for-dev`) — **HARD prerequisite.** Adds `JiraReader` (`read_issue`, `check_tool_availability`, `_parse_issue_ref`, `JIRA_TOOLS`) at `src/ai_qa/pipelines/jira_reader.py`, the `JiraIssue` model, and `MCPClient.check_required_tools`. 11.4 calls `JiraReader` and consumes `JiraIssue`. If 11.1 is unmerged, `from ai_qa.pipelines.jira_reader import JiraReader` raises `ImportError` — the story is blocked; implement 11.1 first.
- **Story 11.2** (`ready-for-dev`) — adds the `handle_start` intake gate that validates and stashes `self._jira_ref`. 11.4 reads it via `getattr(self, "_jira_ref", None)` and (idempotently) keeps the `__init__` default. 11.4 does **not** re-validate at intake.
- **Story 11.3** (`ready-for-dev`) — wires `ContentParser` into the Confluence Phase 2 and adds `warnings` / `parsed_markdown` keys to Confluence page dicts. 11.4's Jira items add `warnings: []` for shape parity; the two stories touch adjacent code in `_extract_descendants` (Confluence loop vs. the tail) and do not conflict. If 11.3 merged first, leave its keys; just append Jira items after.
- **Epic 3** (done) — built `MCPClient`, `ConfluenceReader`, `ConfluenceURLParser`, the original Bob. Production code; reuse, do not refactor.
- **Epic 9** (done) — per-user MCP secret resolution; Bob already resolves the PAT at extraction time via `_resolve_mcp_pat()`. The connected `client` carries it; no extra credential work for Jira.
- **Epic 10** (in-progress) — `PipelineContext.artifact_service` carries the `db`; unaffected. See [epic-10-artifact-ui-gotchas](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/epic-10-artifact-ui-gotchas.md).
- See [agent-gate-conftest-regression](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/agent-gate-conftest-regression.md) and [backend-test-suite-orphaned-legacy-tests](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/backend-test-suite-orphaned-legacy-tests.md): a full `uv run pytest` is red from orphaned legacy tests — verify only the 11.4-touched files, not the whole-suite baseline.

### Git intelligence (recent work patterns)

Recent commits center on Epic 10 artifact events (`9d878c5 feat(api): emit project-scoped artifact change events`, `1852886 feat(10-3): artifact read and preview access`) and the 3.12→3.14 upgrade (`39db313`). None touch Bob/Jira — no merge-conflict risk. The established Bob extraction pattern is: connect MCP once, build `self.pages[]`, emit a single `is_review_ready` payload. 11.4 follows it exactly — one connected client, append to `self.pages`, no new payload shape.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-11.4] — the three ACs (lines 1031-1050)
- [Source: _bmad-output/planning-artifacts/architecture.md:35] — "Jira Integration (FR23-24, M1): On-prem Jira Data Center access via MCP for test-related requirements"
- [Source: _bmad-output/planning-artifacts/architecture.md:56] — MCP server is the single integration point for Confluence and Jira (M1)
- [Source: src/ai_qa/agents/bob.py:322] — `_extract_descendants` (the method to extend); :461 page dict shape; :499-511 success return + finally
- [Source: src/ai_qa/pipelines/jira_reader.py] — `JiraReader.read_issue`, `check_tool_availability`, `_parse_issue_ref`, `JIRA_TOOLS` (Story 11.1)
- [Source: src/ai_qa/pipelines/models.py] — `JiraIssue` (Story 11.1), `ConfluencePage` (:14), `StageResult` field usage
- [Source: src/ai_qa/db/models.py:61] — `Project.jira_base_url` (Jira-enabled signal)
- [Source: src/ai_qa/agents/base.py] — `send_message`, `AgentState`, `_format_error_message`
- [Source: frontend/src/App.tsx:178] — `extractedPages` interface (review item shape); :754 `is_review_ready` handling
- [Source: frontend/src/components/SplitPanel.tsx:8] — renders `page_title`/`source_url`/`requirement_md`/`raw_html`
- [Source: tests/test_agents/test_bob.py:126] — `test_bob_extract_descendants_creates_single_mcp_client` (single-client invariant); disconnect tests :247,:283
- [Source: tests/conftest.py] — `mock_db` / `mock_project_context` fixtures
- [Source: _bmad-output/implementation-artifacts/11-1-mcp-client-foundation-for-confluence-and-jira.md] — `JiraReader` / `JiraIssue` contract
- [Source: _bmad-output/implementation-artifacts/11-2-bob-confluence-url-intake-and-pipeline-trigger.md] — `self._jira_ref` stash contract
- [Source: project-context.md] — `uv` only; Ruff + Mypy strict; no `# type: ignore`; narrow Optional before use; no bare `except`; never `python3`; security (no secret/payload/config logging)

### Definition of Done

- [ ] `JiraReader` + `JiraIssue` imported into `bob.py`; `self._jira_ref` safely defaulted in `__init__`.
- [ ] `_format_jira_markdown` renders title, description, acceptance criteria, status/labels (where present), and source reference into clean Markdown with no `None` leakage (AC2).
- [ ] `_retrieve_jira_requirements` calls `check_tool_availability()` before `read_issue` (AC1), appends a Jira review item to `self.pages` on success (AC2), and is fully exception-wrapped so it never breaks the Confluence flow (AC3).
- [ ] The Jira step is wired at the tail of `_extract_descendants`, reusing the existing connected `MCPClient` (no second client), and Jira skip reasons surface via `send_message` **and** the returned `StageResult.warnings`.
- [ ] Existing Bob regression tests (single-MCP-client, disconnect on completion/exception, pagination, confirm-parent) still pass unchanged.
- [ ] New tests cover: format renderer, AC1 tools-unavailable skip, AC2 happy-path append, AC3 soft-fail + exception safety, no-ref short-circuit, and the `_extract_descendants` integration (Confluence + Jira → 2 items).
- [ ] `uv run ruff check .` and `uv run mypy src` — clean.
- [ ] `uv run pytest tests/test_agents/test_bob.py -v` — all green.
- [ ] `uv run alembic upgrade head` is a no-op (no schema change). No frontend change.

---

## Resolved Decisions (confirmed by Thuong — do NOT revisit)

These design forks were raised during story creation and **confirmed by Thuong to use the defaults below** (2026-06-11). They are locked; implement exactly as stated and do not re-open them.

1. **Jira items are appended to `self.pages` in the Confluence review-item shape.** This reuses the existing paginated review UI with zero frontend change. Extra `source_type` / `warnings` keys are forward-compat for 11.5/11.6/11.7. (Alternative considered and rejected for M1: a separate Jira review payload/section — unnecessary UI work.)

2. **Jira content is rendered with a deterministic `_format_jira_markdown`, not the LLM `RequirementFormatter`.** Jira tickets are already structured (summary/description/AC fields); a rule-based render is faithful, cheap, and testable. (Alternative: run the LLM story transform — deferred; revisit only if review feedback shows Jira tickets need reshaping.)

3. **Jira is a best-effort supplement at the tail of `_extract_descendants`.** It runs only after a successful Confluence extraction and can only add items or report a skip. (Alternative: allow Jira-only extraction when Confluence yields nothing — rejected for M1; Confluence URL is the required trigger per 11.2.)

## Saved Questions (resolved to defaults by Thuong — 2026-06-11)

1. **Project-key → multi-ticket search: OUT OF SCOPE for M1.** Epic AC1 lists "project key" as a possible input and AC2 says "matching tickets" (plural), but 11.1 built only single-ticket `read_issue` and 11.2 validates only a single issue key / URL. **Confirmed default: M1 retrieves the single referenced ticket.** Multi-ticket search (a new `JiraReader.search_issues` wrapping the declared `jira_search_issues` tool + a project-key validator) is a follow-up story, not 11.4 — do not build it here.

2. **Jira item HTML/source-view pane: NOT added.** Confluence items put raw HTML in `raw_html` for the SplitPanel "source" tab. Jira has no HTML page; **confirmed default: 11.4 sets `raw_html=""`.** A raw-field view, if ever wanted, is Story 11.6's concern — out of scope here.

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Syntax error in bob.py `_retrieve_jira_requirements` (missing `)` after send_message call) — fixed by linter auto-format.
- `JiraReader` was constructed with a `settings` param that it doesn't accept (`max_concurrent_requests: int = 10` at position 3 instead). Fixed: removed `settings` from both JiraReader call sites and from the `_retrieve_jira_requirements` signature.
- `handle_start` tests initially failed because `await client.connect()` on a plain `MagicMock` raises `TypeError`. Existing 11.2 tests already set `mock_mcp_client_class.return_value.connect = AsyncMock()` — no fix needed to test file; the syntax error had caused a stale `.pyc`. Tests all pass once the syntax error was resolved.
- Debug `print("RETURNING EARLY DUE TO …")` statements left in `handle_start` during 11.2 investigation — removed in 11.4 cleanup pass.

### Completion Notes List

- Signature deviation from story spec: `_retrieve_jira_requirements(client, jira_base_url)` — `settings` param dropped because `JiraReader.__init__` (Story 11.1) does not accept it. The story spec's Task 3.1 included `settings: AppSettings` as the third parameter based on an incorrect assumption about the 11.1 interface. Mypy caught the mismatch; corrected by removing `settings` from the call and signature, and updating the 5 test call sites accordingly.
- All 3 ACs implemented and covered: AC1 via `check_tool_availability` gate before `read_issue`; AC2 via `_format_jira_markdown` deterministic renderer + page append; AC3 via outer `try/except Exception` that never re-raises.
- `handle_start` capability check block (11.2 code) also gained a `JiraReader` tool check when `self._jira_ref` is set — this is the AC1 gate at the start level, complementing the `_retrieve_jira_requirements` gate at extraction time.

### File List

- `src/ai_qa/agents/bob.py` — added `JiraReader`/`JiraIssue` imports; `_format_jira_markdown()`; `_retrieve_jira_requirements()`; Jira step wired at `_extract_descendants` tail; debug prints removed from `handle_start`.
- `tests/test_agents/test_bob.py` — 11 new tests (5.2–5.9 from story + `test_bob_extract_descendants_with_jira_produces_two_pages`); `patch("ai_qa.agents.bob.JiraReader")` added to 3 existing `_extract_descendants` tests; unused `PageSummary` import removed.
- `tests/conftest.py` — unused `Project` import removed (ruff fix).
- `src/ai_qa/pipelines/jira_reader.py` — unused `AppSettings` and `MCPToolError` imports removed (ruff fix).

### Change Log

- Added `_format_jira_markdown(issue: JiraIssue) -> str` — deterministic Markdown renderer for Jira ticket fields.
- Added `_retrieve_jira_requirements(client, jira_base_url) -> list[str]` — best-effort Jira retrieval, appends to `self.pages`, returns warning strings, fully exception-wrapped.
- Wired Jira step at tail of `_extract_descendants` after Confluence `if not self.pages:` guard; merged `jira_warnings` into success `StageResult`.
- Captured `jira_base_url: str | None = None` alongside `confluence_base_url` in `_extract_descendants`; assigned from `project.jira_base_url` inside the `if project:` block.
- Added JiraReader tool availability check in `handle_start` capability block (when `self._jira_ref` is set).
- 11 new unit/integration tests covering all 3 ACs.
