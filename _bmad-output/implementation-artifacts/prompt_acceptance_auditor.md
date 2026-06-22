You are an Acceptance Auditor. Review this diff against the spec and context docs. Check for: violations of acceptance criteria, deviations from spec intent, missing implementation of specified behavior, contradictions between spec constraints and actual code. Output findings as a Markdown list. Each finding: one-line title, which AC/constraint it violates, and evidence from the diff.

SPEC:
```markdown
---
baseline_commit: 9d878c5
---

# Story 11.1: MCP Client Foundation for Confluence and Jira

Status: review

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a system developer,
I want a shared MCP client for Confluence and Jira access,
so that Bob can retrieve source requirements through the approved on-premises MCP server.

## Acceptance Criteria

### AC1 — MCP client resolves the current user's encrypted MCP key at execution time

**Given** Bob needs to access Confluence or Jira
**When** the MCP client initializes
**Then** it uses the current user's encrypted MCP key resolved at execution time
**And** it connects to the configured on-premises MCP server URL from system configuration.

### AC2 — Client discovers available Confluence and Jira tools on connect

**Given** the MCP server is reachable
**When** the client connects
**Then** it discovers available Confluence and Jira tools where supported
**And** unavailable tools are reported as actionable capability errors.

### AC3 — Retry logic covers MCP connection and transient failures

**Given** MCP connection, authentication, or transient errors occur
**When** Bob attempts MCP access
**Then** retry logic uses max 3 attempts with safe backoff
**And** failures raise custom MCP errors with user-safe messages and no secret leakage.

---

## ⚠️ CRITICAL: This is an EXTEND story — NOT a greenfield MCP build

The MCP client, Confluence reader, retry logic, and per-user secret infrastructure were **already built** across Epics 3 and 9. Story 11-1 exists to **extend the existing foundation** with:

1. **Jira capability** — `JiraReader` pipeline stage (parallel to `ConfluenceReader`) so Bob can retrieve Jira issues via the same MCP server.
2. **Formal capability detection** — `MCPClient.check_required_tools()` that returns a list of missing tools, enabling ConfluenceReader and JiraReader to report actionable errors rather than silently failing when a tool is absent.
3. **`JiraIssue` model** — structured data model for Jira issue content (parallel to `ConfluencePage`).

**Do NOT:**
- Rebuild `MCPClient` (already at `src/ai_qa/mcp/client.py`) — extend only
- Rebuild `ConfluenceReader` (already at `src/ai_qa/pipelines/confluence_reader.py`) — do not touch unless adding capability-check call
- Rebuild `SECRET_TYPE_MCP` or the secret-resolution pattern — already in `src/ai_qa/secrets/__init__.py` and Bob agent
- Add a new transport or auth mechanism — Bearer token via `Authorization` header is the only supported transport
- Add async patterns to pipeline stage models — `ConfluencePage`, `JiraIssue` are pure Pydantic (sync)

### What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status |
| --- | --- | --- |
| `MCPClient` with retry + tool cache | [src/ai_qa/mcp/client.py](src/ai_qa/mcp/client.py) — `__init__(server_url, auth_token, settings)`, `connect()`, `list_tools()`, `call_tool()`, `discover_capabilities()` | ✅ done |
| `ConnectionManager` + `MCPConnection` | [src/ai_qa/mcp/connection.py](src/ai_qa/mcp/connection.py) — pooled by URL+token key, Streamable HTTP + SSE fallback | ✅ done |
| `Tool`, `ToolCache`, `ToolResult` | [src/ai_qa/mcp/tools.py](src/ai_qa/mcp/tools.py) — TTL-based tool caching (5 min default) | ✅ done |
| `MCPError` hierarchy | [src/ai_qa/exceptions.py](src/ai_qa/exceptions.py) — `MCPConnectionError`, `MCPAuthenticationError`, `MCPToolError`, `MCPTimeoutError` | ✅ done |
| `SECRET_TYPE_MCP = "mcp"` | [src/ai_qa/secrets/__init__.py](src/ai_qa/secrets/__init__.py) — canonical secret type for MCP PAT | ✅ done |
| Per-user secret resolution | `get_user_secret(db, user_id, SECRET_TYPE_MCP)` in [src/ai_qa/secrets/service.py](src/ai_qa/secrets/service.py) — used by Bob agent | ✅ done |
| `mcp_server_url`, `mcp_tool_prefix`, `mcp_max_retries`, `mcp_retry_backoff` | [src/ai_qa/config.py](src/ai_qa/config.py) — AppSettings fields | ✅ done |
| `ConfluenceReader` + `CONFLUENCE_TOOLS` | [src/ai_qa/pipelines/confluence_reader.py](src/ai_qa/pipelines/confluence_reader.py) — full MCP-backed reader | ✅ done |
| `ConfluencePage` model | [src/ai_qa/pipelines/models.py](src/ai_qa/pipelines/models.py) — `page_id`, `title`, `content`, `space_key`, `url`, `retrieved_at`, etc. | ✅ done |
| `Project.jira_base_url` DB field | [src/ai_qa/db/models.py](src/ai_qa/db/models.py) — stored, not yet used by any reader | ✅ exists (to be consumed) |
| `StageResult` | [src/ai_qa/pipelines/models.py](src/ai_qa/pipelines/models.py) — all pipeline stages return this | ✅ done |

---

## Tasks / Subtasks

- [x] **Task 1 — Add `JiraIssue` model to pipeline models (AC1/AC2)**
  - [x] 1.1 Open [src/ai_qa/pipelines/models.py](src/ai_qa/pipelines/models.py). After the `ConfluencePage` class, add `JiraIssue(BaseModel)` with fields: `issue_key: str` (e.g., `"PROJ-123"`), `summary: str`, `description: str | None`, `acceptance_criteria: str | None`, `status: str | None`, `labels: list[str] = []`, `project_key: str`, `url: str`, `retrieved_at: datetime`, `issue_type: str | None = None`, `reporter: str | None = None`, `assignee: str | None = None`. Add a `tz_aware` validator on `retrieved_at` matching the same pattern as `ConfluencePage`.
  - [x] 1.2 Export `JiraIssue` from `src/ai_qa/pipelines/__init__.py` (or wherever `ConfluencePage` is exported — match the same export location).

- [x] **Task 2 — Create `JiraReader` pipeline stage (AC1/AC2/AC3)**
  - [x] 2.1 Create `src/ai_qa/pipelines/jira_reader.py`. Model the class structure on `ConfluenceReader` — same `__init__(mcp_client, jira_base_url, settings)` signature shape.
  - [x] 2.2 Declare `JIRA_TOOLS: list[str] = ["jira_get_issue", "jira_search_issues", "jira_get_project"]` as a class constant. Respect `mcp_tool_prefix` from `AppSettings` (same `_get_tool_name()` helper pattern as `ConfluenceReader`).
  - [x] 2.3 Implement `_parse_issue_ref(ref: str) -> str` — a private static/class method that extracts a Jira issue key from:
    - Plain issue key: `"PROJ-123"` → `"PROJ-123"`
    - Jira Cloud URL: `https://company.atlassian.net/browse/PROJ-123` → `"PROJ-123"`
    - Jira Data Center URL: `https://jira.company.com/browse/PROJ-123` → `"PROJ-123"`
    - Invalid input → raise `ValueError` with a clear message
  - [x] 2.4 Implement `async read_issue(issue_ref: str) -> StageResult` — parses the ref via `_parse_issue_ref()`, calls `self._mcp_client.call_tool(self._get_tool_name("jira_get_issue"), {"issue_key": issue_key, "userPrompt": "...", "llmReasoning": "..."})`, maps the tool result to `JiraIssue`, returns `StageResult(success=True, data=issue, metadata={...})`. On `MCPToolError` or non-success `ToolResult`: return `StageResult(success=False, error=err_msg, metadata={...})` — do NOT re-raise; let callers decide.
  - [x] 2.5 Implement `async check_tool_availability() -> list[str]` — calls `self._mcp_client.list_tools()`, returns the names in `JIRA_TOOLS` that are absent from the discovered tool list. Returns empty list when all tools are present. Raises `MCPConnectionError` if `list_tools()` raises. This method is called by the caller (Bob) before the first read to surface actionable "Jira not available" errors — not called automatically inside `read_issue`.
  - [x] 2.6 Map tool result fields defensively: Jira MCP tool responses may nest content in `"fields"`, `"body"`, or flat keys depending on the server version — use `result.data.get("fields", result.data)` or similar and guard all optional field accesses. Acceptance criteria text lives in `fields.description` or `fields.customfield_XXXXX` — extract whatever is present; fall back to `None` gracefully.

- [x] **Task 3 — Add `check_required_tools()` to `MCPClient` (AC2)**
  - [x] 3.1 Open [src/ai_qa/mcp/client.py](src/ai_qa/mcp/client.py). Add method `async check_required_tools(required_tools: list[str]) -> list[str]` — calls `self.list_tools()`, returns names from `required_tools` not found in the discovered tool names. Returns empty list when all present. Raises whatever `list_tools()` raises (caller handles). No caching bypass — relies on the existing `ToolCache` TTL.
  - [x] 3.2 Update `ConfluenceReader` to expose a parallel `check_tool_availability() -> list[str]` method that delegates to `self._mcp_client.check_required_tools(CONFLUENCE_TOOLS)`. Keep the `CONFLUENCE_TOOLS` list as-is — do NOT change existing Confluence logic beyond adding this one method.

- [x] **Task 4 — Unit tests (AC1/AC2/AC3)**
  - [x] 4.1 Create `tests/pipelines/test_jira_reader.py`. Use `unittest.mock.AsyncMock` + `MagicMock` to mock `MCPClient`. Do NOT instantiate a real MCPClient or open a network connection.
  - [x] 4.2 Test `_parse_issue_ref()`:
    - `"PROJ-123"` → `"PROJ-123"`
    - `"https://company.atlassian.net/browse/PROJ-123"` → `"PROJ-123"`
    - `"https://jira.company.com/browse/PROJ-123"` → `"PROJ-123"`
    - Empty string → `ValueError` with `match=`
    - Garbage input (no issue key pattern) → `ValueError` with `match=`
  - [x] 4.3 Test `read_issue()` happy path: mock `call_tool` to return `ToolResult.from_data({...})` with a realistic Jira payload; assert returned `StageResult.success is True` and `StageResult.data` is a `JiraIssue` with correct fields.
  - [x] 4.4 Test `read_issue()` error path: mock `call_tool` to raise `MCPToolError("tool not found")`; assert returned `StageResult.success is False` and error message is non-empty.
  - [x] 4.5 Test `check_tool_availability()`: mock `list_tools()` to return a tool list missing `"jira_search_issues"`; assert the return value is `["jira_search_issues"]` (the missing one). Then mock it to return all `JIRA_TOOLS` present; assert return is `[]`.
  - [x] 4.6 Add unit test for `MCPClient.check_required_tools()` in `tests/unit/test_mcp_client_capabilities.py` (new file). Mock `list_tools()` to return a subset; assert the missing names are returned. Test with empty `required_tools` → always returns `[]`.
  - [x] 4.7 Add unit test for `ConfluenceReader.check_tool_availability()` in `tests/pipelines/test_jira_reader.py` (same file is fine, or extract) — delegate asserts that `check_required_tools(CONFLUENCE_TOOLS)` is called.

- [x] **Task 5 — Full gate + DoD**
  - [x] 5.1 Run `uv run ruff check .` and `uv run mypy src` — clean.
  - [x] 5.2 Run `uv run pytest tests/pipelines/test_jira_reader.py tests/unit/test_mcp_client_capabilities.py -v` — all green.
  - [x] 5.3 **No DB migration required** — `Project.jira_base_url` already exists in schema. Confirm `uv run alembic upgrade head` is a no-op.
  - [x] 5.4 **Frontend not touched** — no `frontend/` changes expected; skip `npm run typecheck` unless a type was incidentally affected.
  - [x] 5.5 Update Dev Agent Record with file list, commands run, and outputs.

---

## Dev Notes

### What this story is actually building

The existing Epic 3 work built a generic `MCPClient` and a `ConfluenceReader`. Epic 9 added per-user MCP secret storage. This story's job is:

1. **`JiraReader`** — a Jira-specific pipeline stage that wraps `MCPClient.call_tool()` for `jira_get_issue` and friends, same as `ConfluenceReader` wraps Confluence tools. It must handle Jira's nested `fields` response structure and extract `summary`, `description`, `acceptance_criteria`, `labels`, `status`.
2. **`check_required_tools()`** on `MCPClient` — a first-class API for callers to ask "is Jira/Confluence available?" before attempting reads. Returns a list of missing tool names so the caller can surface user-friendly errors.
3. **`JiraIssue` model** — Pydantic model for Jira issue data, consumed by Task 4 of Epic 11 (JiraReader output) and later by Bob agent.

### MCPClient instantiation pattern (DO NOT change)

Bob agent already resolves the MCP PAT at runtime and passes it to `MCPClient`:

```python
# From src/ai_qa/agents/bob.py — existing pattern, do not copy-paste into JiraReader
mcp_pat = get_user_secret(db, user_id, SECRET_TYPE_MCP)  # decrypted at runtime
settings = AppSettings()
client = MCPClient(auth_token=mcp_pat, settings=settings)
await client.connect()
reader = ConfluenceReader(client, confluence_base_url=project.confluence_base_url)
```

`JiraReader` follows the same constructor shape: `JiraReader(mcp_client, jira_base_url, settings)`. Secret resolution is the **caller's** responsibility (Bob agent), not the reader's. The reader never touches `UserSecret` or `get_user_secret`.

### `check_required_tools()` sketch

```python
# In src/ai_qa/mcp/client.py — add to MCPClient class
async def check_required_tools(self, required_tools: list[str]) -> list[str]:
    """Return names from required_tools that are absent on the MCP server.
    
    Empty list means all required tools are present.
    Raises MCPConnectionError / MCPAuthenticationError if list_tools() fails.
    """
    if not required_tools:
        return []
    available = {t.name for t in await self.list_tools()}
    return [name for name in required_tools if name not in available]
```

Respects `mcp_tool_prefix` because `list_tools()` returns the server's actual tool names (already prefixed), and `_get_tool_name()` in the readers adds the prefix when calling. The comparison should be against **prefixed** names when a prefix is configured. Readers should pass prefixed names to `check_required_tools()`:

```python
# In JiraReader.check_tool_availability()
prefixed = [self._get_tool_name(t) for t in JIRA_TOOLS]
return await self._mcp_client.check_required_tools(prefixed)
```

### `JiraIssue` model sketch

```python
# In src/ai_qa/pipelines/models.py — add after ConfluencePage
class JiraIssue(BaseModel):
    issue_key: str          # e.g. "PROJ-123"
    summary: str
    description: str | None = None
    acceptance_criteria: str | None = None  # from fields.description or custom field
    status: str | None = None
    labels: list[str] = []
    project_key: str
    url: str
    retrieved_at: datetime
    issue_type: str | None = None
    reporter: str | None = None
    assignee: str | None = None
```

### `JiraReader` response mapping — defensive field access

Jira MCP tool responses vary by server type (Cloud vs Data Center) and MCP server implementation. Map defensively:

```python
# After call_tool returns ToolResult with .data = dict
raw = tool_result.data or {}
fields = raw.get("fields", raw)  # DC wraps in "fields"; Cloud may be flat
return JiraIssue(
    issue_key=raw.get("key", "") or issue_key,
    summary=fields.get("summary", ""),
    description=fields.get("description") or None,
    acceptance_criteria=fields.get("acceptance_criteria") or None,
    status=(fields.get("status") or {}).get("name") if isinstance(fields.get("status"), dict) else fields.get("status"),
    labels=fields.get("labels") or [],
    project_key=(fields.get("project") or {}).get("key", "") if isinstance(fields.get("project"), dict) else fields.get("project", ""),
    url=self._jira_base_url.rstrip("/") + "/browse/" + issue_key,
    retrieved_at=datetime.now(tz=timezone.utc),
    issue_type=(fields.get("issuetype") or {}).get("name") if isinstance(fields.get("issuetype"), dict) else None,
    reporter=(fields.get("reporter") or {}).get("displayName") if isinstance(fields.get("reporter"), dict) else None,
    assignee=(fields.get("assignee") or {}).get("displayName") if isinstance(fields.get("assignee"), dict) else None,
)
```

### `_parse_issue_ref()` sketch

```python
import re

_ISSUE_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9_]+-\d+)\b")

@classmethod
def _parse_issue_ref(cls, ref: str) -> str:
    """Extract Jira issue key from a URL or bare key string."""
    stripped = ref.strip()
    if not stripped:
        raise ValueError("Issue reference must not be empty")
    match = _ISSUE_KEY_RE.search(stripped)
    if not match:
        raise ValueError(f"No Jira issue key found in: {stripped!r}")
    return match.group(1)
```

This handles Cloud URLs, DC URLs, and plain issue keys. The regex requires uppercase project key + dash + digits (standard Jira format).

### Error handling contract

`read_issue()` must NOT re-raise MCP errors — it returns `StageResult(success=False, error=...)`. This is consistent with `ConfluenceReader.read_page()` behavior. The Bob agent is responsible for surfacing errors to the user.

`check_tool_availability()` MAY raise `MCPConnectionError` / `MCPAuthenticationError` because being unable to list tools is a hard infrastructure failure, not a soft "tool not present" signal.

Never include raw exception messages, stack traces, or auth token fragments in `StageResult.error` — always use sanitized user-safe wording:
- `MCPToolError` → "Jira tool not available on the MCP server"  
- `MCPConnectionError` → "Could not connect to MCP server"
- `MCPAuthenticationError` → "MCP authentication failed — check your MCP credential configuration"

### Retry coverage

`MCPClient.call_tool()` and `MCPClient.list_tools()` already implement retry (max 3, exponential backoff via tenacity in `src/ai_qa/mcp/client.py`). `JiraReader` does NOT add its own retry layer — the client handles it. Do NOT add `@retry` decorators in the reader.

### Anti-patterns to avoid (FORBIDDEN)

- Re-implementing connection pooling, auth, or retry in `JiraReader` — these live in `MCPClient`
- Calling `get_user_secret()` inside `JiraReader` — secret resolution belongs in the agent layer (Bob)
- Silently swallowing `MCPConnectionError` / `MCPAuthenticationError` in `read_issue()` — only catch `MCPToolError` and non-success `ToolResult` for soft failure
- Mutating `ConfluenceReader` logic (other than adding `check_tool_availability()`)
- `# type: ignore` / global lint disables
- Bare `except Exception:` — use specific MCP error types
- `asyncio.run()` inside JiraReader — it's an async class; `await` is correct

### Testing approach

Use `unittest.mock.AsyncMock` for `MCPClient` methods that are `async def`. Example:

```python
from unittest.mock import AsyncMock, MagicMock, patch
from ai_qa.mcp.tools import ToolResult, Tool

mock_client = MagicMock()
mock_client.call_tool = AsyncMock(return_value=ToolResult.from_data({
    "key": "PROJ-123",
    "fields": {"summary": "Login fails", "description": "Steps: ...", ...}
}))
mock_client.list_tools = AsyncMock(return_value=[
    Tool(name="jira_get_issue", description="", parameters=[], returns=""),
    Tool(name="jira_search_issues", description="", parameters=[], returns=""),
    # "jira_get_project" intentionally absent to test missing-tool detection
])
```

No `@pytest.mark.asyncio` required if using `anyio` or the project's existing pytest-asyncio config — check `tests/conftest.py` for the existing marker setup and match it exactly.

### Project Structure Notes

**New files:**
- `src/ai_qa/pipelines/jira_reader.py` — new pipeline stage
- `tests/pipelines/test_jira_reader.py` — new unit test file
- `tests/unit/test_mcp_client_capabilities.py` — new unit test file

**Modified files:**
- `src/ai_qa/pipelines/models.py` — add `JiraIssue` model
- `src/ai_qa/pipelines/__init__.py` — export `JiraIssue` (if `ConfluencePage` is exported there)
- `src/ai_qa/mcp/client.py` — add `check_required_tools()` method
- `src/ai_qa/pipelines/confluence_reader.py` — add `check_tool_availability()` method (one method, no other changes)

No new packages required. No DB migration. No frontend changes.

### Previous-story intelligence

No prior Epic 11 story exists. Relevant brownfield context:
- **Epic 3** (done): Built the original MCP client + Confluence reader. These files are production code — do not refactor them beyond the targeted additions described above.
- **Epic 9** (done): Added `SECRET_TYPE_MCP`, `get_user_secret()`, and runtime secret resolution in Bob agent. The per-user MCP PAT flow is complete — this story only extends it to also support Jira reads.
- **Epic 10** (in-progress): Unrelated to MCP; no conflicts expected.

### Full gate notes

Full `uv run pytest` produces ~17 failures in orphaned legacy tests (pre-existing — see [backend-test-suite-orphaned-legacy-tests.md](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/backend-test-suite-orphaned-legacy-tests.md)). Only verify the 11-1-touched test files are clean, not the full suite baseline.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-11.1] — full ACs
- [Source: _bmad-output/planning-artifacts/architecture.md#MCP-Integration] — MCP SDK decision, `src/ai_qa/mcp/` location, Jira M1 scope
- [Source: src/ai_qa/mcp/client.py] — `MCPClient.__init__`, `connect()`, `list_tools()`, `call_tool()`, `discover_capabilities()`
- [Source: src/ai_qa/mcp/connection.py] — `ConnectionManager`, Bearer token auth pattern
- [Source: src/ai_qa/mcp/tools.py] — `Tool`, `ToolResult`, `ToolCache`
- [Source: src/ai_qa/pipelines/confluence_reader.py] — `ConfluenceReader` structure, `CONFLUENCE_TOOLS`, `_get_tool_name()`, `StageResult` usage pattern
- [Source: src/ai_qa/pipelines/models.py] — `ConfluencePage` (reference model), `StageResult`
- [Source: src/ai_qa/secrets/__init__.py] — `SECRET_TYPE_MCP`
- [Source: src/ai_qa/secrets/service.py] — `get_user_secret()` API
- [Source: src/ai_qa/exceptions.py] — `MCPError` hierarchy
- [Source: src/ai_qa/config.py] — `mcp_server_url`, `mcp_tool_prefix`, `mcp_max_retries`, `mcp_retry_backoff`
- [Source: src/ai_qa/db/models.py] — `Project.jira_base_url` (already in schema)
- [Source: project-context.md] — `uv` only; Ruff + Mypy strict; no global lint disables; no bare `except`; never `python3`

### Definition of Done

- [ ] `JiraIssue` Pydantic model added to `src/ai_qa/pipelines/models.py` with all required fields.
- [ ] `JiraReader` class created at `src/ai_qa/pipelines/jira_reader.py` with `JIRA_TOOLS`, `_parse_issue_ref()`, `read_issue()`, and `check_tool_availability()`.
- [ ] `MCPClient.check_required_tools()` added; `ConfluenceReader.check_tool_availability()` added.
- [ ] Unit tests pass: `tests/pipelines/test_jira_reader.py` and `tests/unit/test_mcp_client_capabilities.py`.
- [ ] `uv run ruff check .` and `uv run mypy src` — clean.
- [ ] `uv run alembic upgrade head` is a no-op (confirmed no schema changes).

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created.
- Added `JiraIssue` Pydantic model to `src/ai_qa/pipelines/models.py` with all required fields and tz-aware validator matching `ConfluencePage` pattern.
- Exported `JiraIssue` from `src/ai_qa/pipelines/__init__.py`.
- Created `src/ai_qa/pipelines/jira_reader.py` with `JiraReader` class: `JIRA_TOOLS`, `_parse_issue_ref()`, `read_issue()`, `check_tool_availability()`, and defensive `_map_issue_data()` for Cloud/DC response shape variation.
- Added `MCPClient.check_required_tools()` to `src/ai_qa/mcp/client.py` — delegates to `list_tools()`, returns missing names.
- Added `ConfluenceReader.check_tool_availability()` to `src/ai_qa/pipelines/confluence_reader.py` — one method, no other changes.
- 25 unit tests, all green: `tests/pipelines/test_jira_reader.py` (19 tests) + `tests/unit/test_mcp_client_capabilities.py` (6 tests).
- `uv run ruff check .` → clean. `uv run mypy src` → clean (80 files).
- `uv run alembic upgrade head` → no-op (no schema changes).

### File List

- `src/ai_qa/pipelines/models.py` — added `JiraIssue` model
- `src/ai_qa/pipelines/__init__.py` — exported `JiraIssue`
- `src/ai_qa/pipelines/jira_reader.py` — new file: `JiraReader` pipeline stage
- `src/ai_qa/mcp/client.py` — added `check_required_tools()` method
- `src/ai_qa/pipelines/confluence_reader.py` — added `check_tool_availability()` method
- `tests/pipelines/test_jira_reader.py` — new file: 19 unit tests
- `tests/unit/test_mcp_client_capabilities.py` — new file: 6 unit tests
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status updated

### Change Log

- 2026-06-11: Story 11-1 implemented — JiraIssue model, JiraReader pipeline stage, MCPClient.check_required_tools(), ConfluenceReader.check_tool_availability(), 25 unit tests. All gates pass.

```


DIFF:
```diff
﻿diff --git a/_bmad-output/implementation-artifacts/11-1-mcp-client-foundation-for-confluence-and-jira.md b/_bmad-output/implementation-artifacts/11-1-mcp-client-foundation-for-confluence-and-jira.md
index 2490ccf..90cbcb7 100644
--- a/_bmad-output/implementation-artifacts/11-1-mcp-client-foundation-for-confluence-and-jira.md
+++ b/_bmad-output/implementation-artifacts/11-1-mcp-client-foundation-for-confluence-and-jira.md
@@ -4,7 +4,7 @@ baseline_commit: 9d878c5
 
 # Story 11.1: MCP Client Foundation for Confluence and Jira
 
-Status: ready-for-dev
+Status: review
 
 <!-- markdownlint-disable MD033 MD041 -->
 <!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
@@ -75,46 +75,46 @@ The MCP client, Confluence reader, retry logic, and per-user secret infrastructu
 
 ## Tasks / Subtasks
 
-- [ ] **Task 1 ΓÇö Add `JiraIssue` model to pipeline models (AC1/AC2)**
-  - [ ] 1.1 Open [src/ai_qa/pipelines/models.py](src/ai_qa/pipelines/models.py). After the `ConfluencePage` class, add `JiraIssue(BaseModel)` with fields: `issue_key: str` (e.g., `"PROJ-123"`), `summary: str`, `description: str | None`, `acceptance_criteria: str | None`, `status: str | None`, `labels: list[str] = []`, `project_key: str`, `url: str`, `retrieved_at: datetime`, `issue_type: str | None = None`, `reporter: str | None = None`, `assignee: str | None = None`. Add a `tz_aware` validator on `retrieved_at` matching the same pattern as `ConfluencePage`.
-  - [ ] 1.2 Export `JiraIssue` from `src/ai_qa/pipelines/__init__.py` (or wherever `ConfluencePage` is exported ΓÇö match the same export location).
+- [x] **Task 1 ΓÇö Add `JiraIssue` model to pipeline models (AC1/AC2)**
+  - [x] 1.1 Open [src/ai_qa/pipelines/models.py](src/ai_qa/pipelines/models.py). After the `ConfluencePage` class, add `JiraIssue(BaseModel)` with fields: `issue_key: str` (e.g., `"PROJ-123"`), `summary: str`, `description: str | None`, `acceptance_criteria: str | None`, `status: str | None`, `labels: list[str] = []`, `project_key: str`, `url: str`, `retrieved_at: datetime`, `issue_type: str | None = None`, `reporter: str | None = None`, `assignee: str | None = None`. Add a `tz_aware` validator on `retrieved_at` matching the same pattern as `ConfluencePage`.
+  - [x] 1.2 Export `JiraIssue` from `src/ai_qa/pipelines/__init__.py` (or wherever `ConfluencePage` is exported ΓÇö match the same export location).
 
-- [ ] **Task 2 ΓÇö Create `JiraReader` pipeline stage (AC1/AC2/AC3)**
-  - [ ] 2.1 Create `src/ai_qa/pipelines/jira_reader.py`. Model the class structure on `ConfluenceReader` ΓÇö same `__init__(mcp_client, jira_base_url, settings)` signature shape.
-  - [ ] 2.2 Declare `JIRA_TOOLS: list[str] = ["jira_get_issue", "jira_search_issues", "jira_get_project"]` as a class constant. Respect `mcp_tool_prefix` from `AppSettings` (same `_get_tool_name()` helper pattern as `ConfluenceReader`).
-  - [ ] 2.3 Implement `_parse_issue_ref(ref: str) -> str` ΓÇö a private static/class method that extracts a Jira issue key from:
+- [x] **Task 2 ΓÇö Create `JiraReader` pipeline stage (AC1/AC2/AC3)**
+  - [x] 2.1 Create `src/ai_qa/pipelines/jira_reader.py`. Model the class structure on `ConfluenceReader` ΓÇö same `__init__(mcp_client, jira_base_url, settings)` signature shape.
+  - [x] 2.2 Declare `JIRA_TOOLS: list[str] = ["jira_get_issue", "jira_search_issues", "jira_get_project"]` as a class constant. Respect `mcp_tool_prefix` from `AppSettings` (same `_get_tool_name()` helper pattern as `ConfluenceReader`).
+  - [x] 2.3 Implement `_parse_issue_ref(ref: str) -> str` ΓÇö a private static/class method that extracts a Jira issue key from:
     - Plain issue key: `"PROJ-123"` ΓåÆ `"PROJ-123"`
     - Jira Cloud URL: `https://company.atlassian.net/browse/PROJ-123` ΓåÆ `"PROJ-123"`
     - Jira Data Center URL: `https://jira.company.com/browse/PROJ-123` ΓåÆ `"PROJ-123"`
     - Invalid input ΓåÆ raise `ValueError` with a clear message
-  - [ ] 2.4 Implement `async read_issue(issue_ref: str) -> StageResult` ΓÇö parses the ref via `_parse_issue_ref()`, calls `self._mcp_client.call_tool(self._get_tool_name("jira_get_issue"), {"issue_key": issue_key, "userPrompt": "...", "llmReasoning": "..."})`, maps the tool result to `JiraIssue`, returns `StageResult(success=True, data=issue, metadata={...})`. On `MCPToolError` or non-success `ToolResult`: return `StageResult(success=False, error=err_msg, metadata={...})` ΓÇö do NOT re-raise; let callers decide.
-  - [ ] 2.5 Implement `async check_tool_availability() -> list[str]` ΓÇö calls `self._mcp_client.list_tools()`, returns the names in `JIRA_TOOLS` that are absent from the discovered tool list. Returns empty list when all tools are present. Raises `MCPConnectionError` if `list_tools()` raises. This method is called by the caller (Bob) before the first read to surface actionable "Jira not available" errors ΓÇö not called automatically inside `read_issue`.
-  - [ ] 2.6 Map tool result fields defensively: Jira MCP tool responses may nest content in `"fields"`, `"body"`, or flat keys depending on the server version ΓÇö use `result.data.get("fields", result.data)` or similar and guard all optional field accesses. Acceptance criteria text lives in `fields.description` or `fields.customfield_XXXXX` ΓÇö extract whatever is present; fall back to `None` gracefully.
+  - [x] 2.4 Implement `async read_issue(issue_ref: str) -> StageResult` ΓÇö parses the ref via `_parse_issue_ref()`, calls `self._mcp_client.call_tool(self._get_tool_name("jira_get_issue"), {"issue_key": issue_key, "userPrompt": "...", "llmReasoning": "..."})`, maps the tool result to `JiraIssue`, returns `StageResult(success=True, data=issue, metadata={...})`. On `MCPToolError` or non-success `ToolResult`: return `StageResult(success=False, error=err_msg, metadata={...})` ΓÇö do NOT re-raise; let callers decide.
+  - [x] 2.5 Implement `async check_tool_availability() -> list[str]` ΓÇö calls `self._mcp_client.list_tools()`, returns the names in `JIRA_TOOLS` that are absent from the discovered tool list. Returns empty list when all tools are present. Raises `MCPConnectionError` if `list_tools()` raises. This method is called by the caller (Bob) before the first read to surface actionable "Jira not available" errors ΓÇö not called automatically inside `read_issue`.
+  - [x] 2.6 Map tool result fields defensively: Jira MCP tool responses may nest content in `"fields"`, `"body"`, or flat keys depending on the server version ΓÇö use `result.data.get("fields", result.data)` or similar and guard all optional field accesses. Acceptance criteria text lives in `fields.description` or `fields.customfield_XXXXX` ΓÇö extract whatever is present; fall back to `None` gracefully.
 
-- [ ] **Task 3 ΓÇö Add `check_required_tools()` to `MCPClient` (AC2)**
-  - [ ] 3.1 Open [src/ai_qa/mcp/client.py](src/ai_qa/mcp/client.py). Add method `async check_required_tools(required_tools: list[str]) -> list[str]` ΓÇö calls `self.list_tools()`, returns names from `required_tools` not found in the discovered tool names. Returns empty list when all present. Raises whatever `list_tools()` raises (caller handles). No caching bypass ΓÇö relies on the existing `ToolCache` TTL.
-  - [ ] 3.2 Update `ConfluenceReader` to expose a parallel `check_tool_availability() -> list[str]` method that delegates to `self._mcp_client.check_required_tools(CONFLUENCE_TOOLS)`. Keep the `CONFLUENCE_TOOLS` list as-is ΓÇö do NOT change existing Confluence logic beyond adding this one method.
+- [x] **Task 3 ΓÇö Add `check_required_tools()` to `MCPClient` (AC2)**
+  - [x] 3.1 Open [src/ai_qa/mcp/client.py](src/ai_qa/mcp/client.py). Add method `async check_required_tools(required_tools: list[str]) -> list[str]` ΓÇö calls `self.list_tools()`, returns names from `required_tools` not found in the discovered tool names. Returns empty list when all present. Raises whatever `list_tools()` raises (caller handles). No caching bypass ΓÇö relies on the existing `ToolCache` TTL.
+  - [x] 3.2 Update `ConfluenceReader` to expose a parallel `check_tool_availability() -> list[str]` method that delegates to `self._mcp_client.check_required_tools(CONFLUENCE_TOOLS)`. Keep the `CONFLUENCE_TOOLS` list as-is ΓÇö do NOT change existing Confluence logic beyond adding this one method.
 
-- [ ] **Task 4 ΓÇö Unit tests (AC1/AC2/AC3)**
-  - [ ] 4.1 Create `tests/pipelines/test_jira_reader.py`. Use `unittest.mock.AsyncMock` + `MagicMock` to mock `MCPClient`. Do NOT instantiate a real MCPClient or open a network connection.
-  - [ ] 4.2 Test `_parse_issue_ref()`:
+- [x] **Task 4 ΓÇö Unit tests (AC1/AC2/AC3)**
+  - [x] 4.1 Create `tests/pipelines/test_jira_reader.py`. Use `unittest.mock.AsyncMock` + `MagicMock` to mock `MCPClient`. Do NOT instantiate a real MCPClient or open a network connection.
+  - [x] 4.2 Test `_parse_issue_ref()`:
     - `"PROJ-123"` ΓåÆ `"PROJ-123"`
     - `"https://company.atlassian.net/browse/PROJ-123"` ΓåÆ `"PROJ-123"`
     - `"https://jira.company.com/browse/PROJ-123"` ΓåÆ `"PROJ-123"`
     - Empty string ΓåÆ `ValueError` with `match=`
     - Garbage input (no issue key pattern) ΓåÆ `ValueError` with `match=`
-  - [ ] 4.3 Test `read_issue()` happy path: mock `call_tool` to return `ToolResult.from_data({...})` with a realistic Jira payload; assert returned `StageResult.success is True` and `StageResult.data` is a `JiraIssue` with correct fields.
-  - [ ] 4.4 Test `read_issue()` error path: mock `call_tool` to raise `MCPToolError("tool not found")`; assert returned `StageResult.success is False` and error message is non-empty.
-  - [ ] 4.5 Test `check_tool_availability()`: mock `list_tools()` to return a tool list missing `"jira_search_issues"`; assert the return value is `["jira_search_issues"]` (the missing one). Then mock it to return all `JIRA_TOOLS` present; assert return is `[]`.
-  - [ ] 4.6 Add unit test for `MCPClient.check_required_tools()` in `tests/unit/test_mcp_client_capabilities.py` (new file). Mock `list_tools()` to return a subset; assert the missing names are returned. Test with empty `required_tools` ΓåÆ always returns `[]`.
-  - [ ] 4.7 Add unit test for `ConfluenceReader.check_tool_availability()` in `tests/pipelines/test_jira_reader.py` (same file is fine, or extract) ΓÇö delegate asserts that `check_required_tools(CONFLUENCE_TOOLS)` is called.
-
-- [ ] **Task 5 ΓÇö Full gate + DoD**
-  - [ ] 5.1 Run `uv run ruff check .` and `uv run mypy src` ΓÇö clean.
-  - [ ] 5.2 Run `uv run pytest tests/pipelines/test_jira_reader.py tests/unit/test_mcp_client_capabilities.py -v` ΓÇö all green.
-  - [ ] 5.3 **No DB migration required** ΓÇö `Project.jira_base_url` already exists in schema. Confirm `uv run alembic upgrade head` is a no-op.
-  - [ ] 5.4 **Frontend not touched** ΓÇö no `frontend/` changes expected; skip `npm run typecheck` unless a type was incidentally affected.
-  - [ ] 5.5 Update Dev Agent Record with file list, commands run, and outputs.
+  - [x] 4.3 Test `read_issue()` happy path: mock `call_tool` to return `ToolResult.from_data({...})` with a realistic Jira payload; assert returned `StageResult.success is True` and `StageResult.data` is a `JiraIssue` with correct fields.
+  - [x] 4.4 Test `read_issue()` error path: mock `call_tool` to raise `MCPToolError("tool not found")`; assert returned `StageResult.success is False` and error message is non-empty.
+  - [x] 4.5 Test `check_tool_availability()`: mock `list_tools()` to return a tool list missing `"jira_search_issues"`; assert the return value is `["jira_search_issues"]` (the missing one). Then mock it to return all `JIRA_TOOLS` present; assert return is `[]`.
+  - [x] 4.6 Add unit test for `MCPClient.check_required_tools()` in `tests/unit/test_mcp_client_capabilities.py` (new file). Mock `list_tools()` to return a subset; assert the missing names are returned. Test with empty `required_tools` ΓåÆ always returns `[]`.
+  - [x] 4.7 Add unit test for `ConfluenceReader.check_tool_availability()` in `tests/pipelines/test_jira_reader.py` (same file is fine, or extract) ΓÇö delegate asserts that `check_required_tools(CONFLUENCE_TOOLS)` is called.
+
+- [x] **Task 5 ΓÇö Full gate + DoD**
+  - [x] 5.1 Run `uv run ruff check .` and `uv run mypy src` ΓÇö clean.
+  - [x] 5.2 Run `uv run pytest tests/pipelines/test_jira_reader.py tests/unit/test_mcp_client_capabilities.py -v` ΓÇö all green.
+  - [x] 5.3 **No DB migration required** ΓÇö `Project.jira_base_url` already exists in schema. Confirm `uv run alembic upgrade head` is a no-op.
+  - [x] 5.4 **Frontend not touched** ΓÇö no `frontend/` changes expected; skip `npm run typecheck` unless a type was incidentally affected.
+  - [x] 5.5 Update Dev Agent Record with file list, commands run, and outputs.
 
 ---
 
@@ -335,14 +335,33 @@ Full `uv run pytest` produces ~17 failures in orphaned legacy tests (pre-existin
 
 ### Agent Model Used
 
-{{agent_model_name_version}}
+claude-sonnet-4-6
 
 ### Debug Log References
 
 ### Completion Notes List
 
 - Ultimate context engine analysis completed ΓÇö comprehensive developer guide created.
+- Added `JiraIssue` Pydantic model to `src/ai_qa/pipelines/models.py` with all required fields and tz-aware validator matching `ConfluencePage` pattern.
+- Exported `JiraIssue` from `src/ai_qa/pipelines/__init__.py`.
+- Created `src/ai_qa/pipelines/jira_reader.py` with `JiraReader` class: `JIRA_TOOLS`, `_parse_issue_ref()`, `read_issue()`, `check_tool_availability()`, and defensive `_map_issue_data()` for Cloud/DC response shape variation.
+- Added `MCPClient.check_required_tools()` to `src/ai_qa/mcp/client.py` ΓÇö delegates to `list_tools()`, returns missing names.
+- Added `ConfluenceReader.check_tool_availability()` to `src/ai_qa/pipelines/confluence_reader.py` ΓÇö one method, no other changes.
+- 25 unit tests, all green: `tests/pipelines/test_jira_reader.py` (19 tests) + `tests/unit/test_mcp_client_capabilities.py` (6 tests).
+- `uv run ruff check .` ΓåÆ clean. `uv run mypy src` ΓåÆ clean (80 files).
+- `uv run alembic upgrade head` ΓåÆ no-op (no schema changes).
 
 ### File List
 
+- `src/ai_qa/pipelines/models.py` ΓÇö added `JiraIssue` model
+- `src/ai_qa/pipelines/__init__.py` ΓÇö exported `JiraIssue`
+- `src/ai_qa/pipelines/jira_reader.py` ΓÇö new file: `JiraReader` pipeline stage
+- `src/ai_qa/mcp/client.py` ΓÇö added `check_required_tools()` method
+- `src/ai_qa/pipelines/confluence_reader.py` ΓÇö added `check_tool_availability()` method
+- `tests/pipelines/test_jira_reader.py` ΓÇö new file: 19 unit tests
+- `tests/unit/test_mcp_client_capabilities.py` ΓÇö new file: 6 unit tests
+- `_bmad-output/implementation-artifacts/sprint-status.yaml` ΓÇö status updated
+
 ### Change Log
+
+- 2026-06-11: Story 11-1 implemented ΓÇö JiraIssue model, JiraReader pipeline stage, MCPClient.check_required_tools(), ConfluenceReader.check_tool_availability(), 25 unit tests. All gates pass.
diff --git a/_bmad-output/implementation-artifacts/11-8-technical-debt-sweep-and-hardening.md b/_bmad-output/implementation-artifacts/11-8-technical-debt-sweep-and-hardening.md
new file mode 100644
index 0000000..05a031c
--- /dev/null
+++ b/_bmad-output/implementation-artifacts/11-8-technical-debt-sweep-and-hardening.md
@@ -0,0 +1,369 @@
+---
+baseline_commit: 8cf53eb
+---
+
+# Story 11.8: Technical Debt Sweep and Hardening
+
+Status: ready-for-dev
+
+<!-- markdownlint-disable MD033 MD041 -->
+<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->
+
+## Story
+
+As a system developer,
+I want to resolve accumulated test-suite technical debt and harden a few in-flight cleanups before adding new complex layers,
+so that the test suite is stable, CI runs cleanly end-to-end, and old stubs no longer provide a false sense of security.
+
+## Acceptance Criteria
+
+### AC1 ΓÇö AdminDashboard timeout + unstable tests resolved; CI runs cleanly end-to-end
+
+**Given** the suite carries the pre-existing `AdminDashboard` timeout and other unstable/red tests
+**When** the technical-debt sweep is executed
+**Then** the slow/fragile `AdminDashboard` real-timer test is made deterministic (no multi-second real-time wait)
+**And** all currently-red backend tests are resolved (the suite is green)
+**And** the CI workflow (`.github/workflows/test.yml`) is fixed to run on Python 3.14, via `uv`, with a working E2E job that boots the backend (migrated + admin-bootstrapped) and frontend so Playwright can run ΓÇö not a job that can never pass.
+
+### AC2 ΓÇö Stale stub tests are either fully implemented or explicitly skipped with a TODO reason
+
+**Given** the codebase contains pre-existing stub tests (e.g. tests that assert the exact opposite of current reality, or never call the actual mutation, or assert a placeholder like `assert True`)
+**When** the sweep is performed
+**Then** each stale stub is **either** fully implemented to assert the correct behaviour **or** explicitly marked `@pytest.mark.skip(reason="TODO: <why>")`
+**And** no two test files make contradictory assertions about the same production symbol.
+
+### AC3 ΓÇö The sweep is bounded and evidence-based; the only production changes are the four approved, behaviour-preserving cleanups
+
+**Given** this is a hardening pass, not a feature
+**When** changes are made
+**Then** every change is justified by a concrete failing/slow/contradictory test (enumerated live, not guessed)
+**And** the **only** production-code changes are the four approved by Thuong (2026-06-11): (1) completing the dead-code `OutputWriter` deletion, (2) requirement draft-dedupe + idempotent approved-save *(depends on 11.7 merged)*, (3) a `ToolCache` clock seam for deterministic TTL testing, (4) the CI workflow fix ΓÇö each bounded and behaviour-preserving by default
+**And** `uv run pytest` (with its default `--cov-fail-under=80` gate) and `npm run lint`/`typecheck`/`test` are green at the end.
+
+---
+
+## ΓÜá∩╕Å CRITICAL: This is a SWEEP ΓÇö enumerate the LIVE debt first, then fix-or-skip. Do NOT chase a fabricated list.
+
+This story exists because the **Epic 10 retrospective** (2026-06-11) explicitly requested a dedicated debt sweep in Epic 11 ([epic-10-retrospective-2026-06-11.md:26-34](_bmad-output/implementation-artifacts/epic-10-retrospective-2026-06-11.md)). It named two debts: the **`AdminDashboard` timeout** ("causing CI noise and reviewer fatigue") and **stub tests for artifact deletion that never actually called DELETE** ("providing a false sense of security"). The retro's rule (Action Item 3, Murat): *"all test stubs must actually assert the core mutation/behaviour they claim to test, or be marked explicitly `@pytest.mark.skip(reason="TODO")`."*
+
+**11.8 is the LAST story in Epic 11.** By the time it runs, 11.1ΓÇô11.7 (MCP/Confluence/Jira/quality/review/save) are expected to be merged and will have **added new tests**, so the exact debt set is a **moving target**. The dev's **first task is to re-measure the live suite** and enumerate the actual offenders, using the verified baseline below (measured on `8cf53eb`, before any 11.x merge) as the known starting set.
+
+> **Honesty note (verified, not assumed).** As of the `8cf53eb` baseline:
+>
+> - **Frontend suite is GREEN** ΓÇö `npm run test` ΓåÆ **153 passed / 19 files** (~35 s). The AdminDashboard tests **pass**; they are *slow/fragile*, not failing.
+> - **Backend suite is 2 RED / 1098 passed** ΓÇö `uv run pytest --no-cov` ΓåÆ **2 failed, 1098 passed** in ~175 s. The 2 failures are the OutputWriter guard tests (Debt A1.1).
+> - The retro's "5 artifact-deletion stubs" were **largely fixed during Epic 10** ΓÇö `test_artifact_change_event_emitted_on_delete` ([tests/api/test_artifact_events.py:285](tests/api/test_artifact_events.py)) now really creates ΓåÆ DELETEs ΓåÆ asserts the `deleted` broadcast + a 404; the `delete_artifact` unit/scoped tests ([tests/unit/test_artifact_service.py:342,388](tests/unit/test_artifact_service.py)) are real. **Do not re-create or hunt a phantom "5 stubs."** The actual surviving "false sense of security" is the OutputWriter contradiction (A1.1).
+> - The memory note that the backend suite was "~17 failed / ~32 errors from orphaned legacy tests" is **STALE** ΓÇö that instability was resolved during Epic 10. Trust the live run.
+
+### The four expansions Thuong approved (2026-06-11) ΓÇö all IN SCOPE
+
+Thuong confirmed all four follow-ups are part of this story (not deferred): **(Q1)** fix CI fully ΓÇö Python + `uv` + a working E2E job; **(Q2)** make the mislabeled `story-10-7` non-active test correct; **(Q3)** pull in 11.7's two requirement-dedupe follow-ups; **(Q4)** harden the flaky cache-TTL test. Each was designed and adversarially verified against the real code during story creation; the verified designs are below.
+
+---
+
+## VERIFIED DEBT INVENTORY (the known starting set ΓÇö confirm still-live, then fix-or-skip)
+
+Every item was confirmed against real code on `8cf53eb`. Re-run the suites first (Task 0) to confirm each is still live after 11.1ΓÇô11.7 merge, then add any new offenders the live run surfaces.
+
+### AC1 group ΓÇö red / slow / unstable, and CI cleanliness
+
+**A1.1 ΓÇö Backend RED: OutputWriter deletion is incomplete, and two test files contradict each other.** *(the only currently-red backend tests)*
+
+- `tests/integration/test_artifact_service_integration.py::test_output_writer_is_not_importable` ([:196-210](tests/integration/test_artifact_service_integration.py)) **FAILS** ΓÇö asserts `importlib.util.find_spec("ai_qa.pipelines.output_writer") is None`, but the module still exists.
+- `::test_output_writer_not_in_pipelines_namespace` ([:213-222](tests/integration/test_artifact_service_integration.py)) **FAILS** (`assert not True`) ΓÇö `OutputWriter` is still in `ai_qa.pipelines.__all__`.
+- Live remnants of an unfinished Epic-10 migration: `src/ai_qa/pipelines/output_writer.py:17` (class), `src/ai_qa/pipelines/__init__.py:11,22` (import + `__all__`), stale comment `src/ai_qa/agents/sarah.py:45`.
+- **Direct contradiction:** `tests/pipelines/test_output_writer.py` ([:10](tests/pipelines/test_output_writer.py)) imports and tests `OutputWriter` as live code (8+ passing tests). One file demands deletion, the other demands it work ΓÇö the "false sense of security" knot.
+- **No runtime caller** exists (grep `src/` ΓåÆ only the dead `__init__` export + the comment). Production write path is `PipelineArtifactAdapter` ΓåÆ `ArtifactService`.
+- **Fix (D1):** complete the deletion (module + `__init__` import/`__all__` + `tests/pipelines/test_output_writer.py` + fix `sarah.py:45`). Both guards then pass.
+
+**A1.2 ΓÇö CI workflow is broken: pins Python 3.12, and the E2E job can never pass.** *(Q1 ΓÇö "fix everything", IN SCOPE)*
+
+- `.github/workflows/test.yml:21` pins `python-version: '3.12'` while the project `requires-python>=3.14` ΓåÆ `uv pip install` fails. Bump to `3.14`.
+- The frontend job runs `npm run test:e2e` ([:58-59](.github/workflows/test.yml)) with **no backend running and no DB** ΓåÆ every E2E spec that needs the stack fails.
+- **Good news (verified):** `frontend/playwright.config.ts:67-86` already defines a `webServer` array that boots **both** the backend (`uv run ai-qa` ΓåÆ waits on `http://127.0.0.1:8000/auth/status`) and the frontend (`npm run dev` ΓåÆ `:5173`), with `reuseExistingServer: !process.env.CI` ([:72,81](frontend/playwright.config.ts)) ΓÇö so **in CI it starts a fresh pair automatically** when `CI=true`. `workers: 1` ([:38](frontend/playwright.config.ts)) and `retries: 2` are already CI-correct (Argon2 serial requirement, Epic 8 retro).
+- **What CI must add for the webServer-launched backend to actually start** (verified gaps): `USER_SECRETS_ENCRYPTION_KEY` is required at startup (Fernet ΓÇö `config.py`); a Postgres service + `DATABASE_*` env (the `config.py` default user is `ai_qa`, so CI must set `DATABASE_USER=postgres` to match the service); **`uv run alembic upgrade head` BEFORE the run** ΓÇö `create_app()` does **not** run migrations, so without this the bootstrap/queries hit "relation does not exist"; an admin bootstrap (`uv run python -m ai_qa.auth.bootstrap_admin` with `AI_QA_BOOTSTRAP_ADMIN_PASSWORD`); and the e2e env (`ADMIN_PASSWORD`/`E2E_ADMIN_PASSWORD`, `API_URL`, `BASE_URL`). Use `uv sync` (not `uv pip install --system`) so the webServer's `uv run ai-qa` resolves the project entry point.
+- **Provider-key reality:** specs gated on `TEST_*_KEY` (e.g. `story-9-7-saved-config.spec.ts:25-36`) **skip** when the key is a placeholder ΓÇö so CI stays green without real provider secrets; document that those live-provider specs are skipped in CI.
+- **Fix (D6):** see Task 5 ΓÇö backend job (3.14 + `uv run pytest`) + a new combined `e2e` job (Postgres service ΓåÆ `uv sync` ΓåÆ migrate ΓåÆ bootstrap ΓåÆ `CI=true npx playwright test`). Required GitHub Secrets: `USER_SECRETS_ENCRYPTION_KEY`, `ADMIN_PASSWORD`.
+
+**A1.3 ΓÇö Frontend: the `AdminDashboard` real-timer test (the named "AdminDashboard timeout").**
+
+- `frontend/src/components/admin/AdminDashboard.test.tsx:174-180` uses `await waitFor(() => ΓÇªnot.toBeInTheDocument(), { timeout: 3500 })` to wait for the status banner to auto-dismiss.
+- The dismiss is a **real 3-second timer**: `AdminDashboard.tsx:106-110` ΓåÆ `window.setTimeout(() => setStatus(null), 3000)`. So that assertion burns ~3.5 s and flakes under CI load.
+- **Fix (D2):** scope Vitest fake timers to that assertion ΓÇö `vi.useFakeTimers()`, then `await vi.advanceTimersByTimeAsync(3000)`, assert gone; drop the `{ timeout: 3500 }`. `afterEach` already calls `vi.useRealTimers()` ([:91-93](frontend/src/components/admin/AdminDashboard.test.tsx)). Do **not** change `AdminDashboard.tsx`. Use the **async** advance API (RTL Γåö fake-timer deadlock ΓÇö see Latest tech).
+
+**A1.4 ΓÇö `story-10-7` "non-active-thread" test: the behavioural fix is ALREADY in the working tree; finish + correct the comments.** *(Q2 ΓÇö "sß╗¡a test", IN SCOPE)*
+
+- The investigation ([investigations/e2e-artifact-tree-failures-investigation.md](_bmad-output/implementation-artifacts/investigations/e2e-artifact-tree-failures-investigation.md)) flagged this test as mislabeled. **Verified current state:** the unstaged working-tree version of `frontend/e2e/story-10-7-artifact-refresh.spec.ts` **already creates the artifact in `projectOne`** (the non-active project, [:343-350](frontend/e2e/story-10-7-artifact-refresh.spec.ts)) and **already has** the deterministic `projectTwo`ΓåÆ`projectOne` click sequence ([:381-382](frontend/e2e/story-10-7-artifact-refresh.spec.ts)). So it now correctly exercises the non-active path (event for a non-active project must **not** auto-refresh; the report appears only after a manual open).
+- **Residual work (D7):** (a) **commit** the unstaged `story-10-2`/`story-10-7` fixes; (b) fix two **misleading comments** in `story-10-7`: line ~339-340 says "projects are ordered by name" ΓÇö wrong, threads sort by **recency** (`App.tsx:330-334`); names are incidental. Line ~352-353 cites the guard as `App.tsx:437 ΓÇö eventProjectId === activeProjectId` ΓÇö the real guard is `if (!eventProjectId || eventProjectId === activeProjectId)` (it also refreshes on a missing project id). (c) Optionally fix the investigation doc's follow-up note ([:164](_bmad-output/implementation-artifacts/investigations/e2e-artifact-tree-failures-investigation.md)) which states the applied click order as "projectOne then projectTwo" ΓÇö the actual (correct) code is the reverse.
+- **Not** a behavioural rework ΓÇö the non-active behaviour is already proven; this is commit + comment accuracy.
+
+**A1.5 ΓÇö `testpaths` duplication in `pyproject.toml`.**
+
+- `testpaths = ["tests/unit", "tests/integration", "tests/api", "tests"]` lists three subdirs **and** the parent `tests`. **Fix (D4):** `testpaths = ["tests"]`; verify the collected count is unchanged.
+
+### AC2 group ΓÇö stub / placeholder tests
+
+**A2.1 ΓÇö `assert True` placeholder tests.**
+
+- `tests/unit/test_infrastructure.py:60-67` `test_async_test_support` (`await asyncio.sleep(0)` then `assert True`); `:73-77` `test_coverage_tracking_active` (docstring literally says **"Placeholder"**; `assert True`).
+- **Fix:** real assertions or skip-with-TODO. Suggested: async ΓåÆ `assert asyncio.get_running_loop().is_running()`; coverage ΓåÆ take `pytestconfig` and `assert pytestconfig.pluginmanager.hasplugin("pytest_cov")`.
+
+**A2.2 ΓÇö Re-verify the retro's "artifact-deletion stubs" against the LIVE suite (likely already green).** Confirm they still pass after 11.x merge; do **not** re-implement. If a *new* 11.x delete/save/approve test only checks "the mock was constructed" without asserting the mutation's effect, fix it under AC2.
+
+**A2.3 ΓÇö Flaky cache-TTL test using a real `time.sleep`.** *(Q4 ΓÇö "harden", IN SCOPE)*
+
+- `tests/mcp/test_connection.py:215-228` `test_cache_ttl_expiration` uses `ToolCache(ttl_seconds=0.001)` then `time.sleep(0.002)` ΓÇö a wall-clock race.
+- **Verified gotcha (why the obvious fix fails):** `ToolCache.CachedTool.cached_at: float = field(default_factory=time.time)` ([src/ai_qa/mcp/tools.py:102](src/ai_qa/mcp/tools.py)) captures the **original** `time.time` at class-definition time. `set()` stamps `cached_at` via that captured factory; only `get()`/`invalidate_expired()` look up `time.time()` at call time ([:133,162](src/ai_qa/mcp/tools.py)). So **monkeypatching `time.time` after import mocks the get-side but NOT the set-side** ΓåÆ the delta is garbage and the test breaks. A pure-monkeypatch fix is unsound here.
+- **Fix (D9):** add a **clock seam** to `ToolCache` ΓÇö `__init__(self, ttl_seconds=300.0, clock: Callable[[], float] = time.time)`, store `self._clock`, stamp `cached_at` via `self._clock()` in `set()` (pass it into `CachedTool`, don't rely on the field default), and use `self._clock()` in `get()`/`invalidate_expired()`. The test injects a controllable fake clock ΓÇö fully deterministic, no sleep. This is **additive and behaviour-preserving** (default `time.time`). *(Alternative, zero production change: in the test set `cache._cache[name].cached_at = 0.0` directly and monkeypatch `ai_qa.mcp.tools.time.time` for the get-side ΓÇö but it pokes private state; the clock seam is the proper fix.)*
+
+### AC3 group ΓÇö requirement-artifact dedupe (the two 11.7 follow-ups) *(Q3 ΓÇö "sß╗¡a lu├┤n", IN SCOPE; depends on 11.7 merged)*
+
+**A3.1 ΓÇö A page can end up with multiple `kind="requirements"` artifacts.** Story 11.7 (Saved Questions 1 & 2) flagged two follow-ups for 11.8:
+
+- **(a) Draft not deduped:** 11.7 keeps the pre-approval draft save (`{page_id}.md`, no provenance) **and** writes the approved copy (`{page_id}/requirement.md`, with provenance) ΓÇö two artifacts per page.
+- **(b) Retry duplicates:** **Verified** ΓÇö `ArtifactService.save_artifact` **always creates a new `Artifact` row** (no dedupe by `(project, kind, name)` ΓÇö [service.py:90-101](src/ai_qa/artifacts/service.py)). So an AC3 re-approval after a transient save failure yields a **second** approved row.
+- **Verified building blocks:** `ArtifactService.delete_artifact(*, project_id, artifact_id) -> bool` exists (cascades versions + best-effort storage cleanup ΓÇö [service.py:202-225](src/ai_qa/artifacts/service.py)); `list_artifacts(*, project_id, kind=None)` exists ([service.py:185-192](src/ai_qa/artifacts/service.py)); `storage.build_artifact_key` nests by `artifact_id/v{version}` so distinct rows never overwrite each other in storage.
+- **Fix (D8) ΓÇö single artifact per page:**
+  1. **Draft dedupe:** add `PipelineArtifactAdapter.delete_draft_requirement(page_id)` (list `kind="requirements"` ΓåÆ find `name == f"{page_id}.md"` ΓåÆ `delete_artifact`; safe-fail with a **module-level** logger ΓÇö never fail the approval). Call it in `handle_approve`'s approved branch **after** a successful `save_requirement(...)`, before the side-car.
+  2. **Retry dedupe:** make `save_requirement(...)` idempotent-by-name ΓÇö if an approved `{page_id}/requirement.md` already exists for the project, **replace** it (delete the prior approved row, then save fresh with current provenance) instead of creating a duplicate. *(Default: delete-then-save for fresh provenance; version history for requirements is not a stated need. Re-decide to `create_version` if Thuong wants history.)*
+- **Downstream:** keeps the draft-vs-approved discriminator meaningful and means 12.1's Mary input filter sees exactly one approved requirement per page (still filter `source_type IS NOT NULL` / the `{page_id}/requirement.md` name as belt-and-suspenders).
+- **Sequencing:** this touches 11.7's `save_requirement` + `handle_approve` approved branch ΓÇö **implement only after 11.7 is merged.** Line anchors below are post-11.7.
+
+---
+
+## What ALREADY EXISTS (reuse / respect ΓÇö do not recreate)
+
+| Capability | Where | Note for the sweep |
+| --- | --- | --- |
+| Production write path (replaces OutputWriter) | `PipelineArtifactAdapter` ΓåÆ `ArtifactService` ([artifact_adapter.py](src/ai_qa/pipelines/artifact_adapter.py), [service.py](src/ai_qa/artifacts/service.py)) | OutputWriter is dead; this is the live path. |
+| OutputWriter guard tests (desired end-state) | [test_artifact_service_integration.py:196-222](tests/integration/test_artifact_service_integration.py) | Keep; pass once deletion completes. |
+| Contradicting OutputWriter unit tests | [tests/pipelines/test_output_writer.py](tests/pipelines/test_output_writer.py) | Delete with the module (D1). |
+| AdminDashboard status auto-dismiss timer | [AdminDashboard.tsx:106-110](frontend/src/components/admin/AdminDashboard.tsx) | **Do not change** ΓÇö fix the test with fake timers. |
+| Playwright `webServer` (boots backend + frontend; CI-fresh) | [playwright.config.ts:67-86](frontend/playwright.config.ts) | The CI E2E job just sets `CI=true` + env; Playwright starts both. |
+| Admin bootstrap CLI | `python -m ai_qa.auth.bootstrap_admin` (`AI_QA_BOOTSTRAP_ADMIN_PASSWORD`) | Use in the CI e2e job. |
+| `ArtifactService.delete_artifact` / `list_artifacts` | [service.py:185-225](src/ai_qa/artifacts/service.py) | Reuse for the draft-dedupe adapter method (D8). |
+| `save_artifact` (always new row, no dedupe) | [service.py:71-131](src/ai_qa/artifacts/service.py) | Why the retry-dup exists; D8 dedupes at the `save_requirement` seam, not here. |
+| `ToolCache` | [tools.py:97-168](src/ai_qa/mcp/tools.py) | Add a `clock` seam (D9); `cached_at` default_factory captures `time.time` at class-def. |
+| E2E artifact-tree fixes (working tree, unstaged) | [story-10-2-ΓÇªspec.ts](frontend/e2e/story-10-2-artifact-tree-browsing.spec.ts), [story-10-7-ΓÇªspec.ts](frontend/e2e/story-10-7-artifact-refresh.spec.ts) | Commit; the non-active fix is already present (D7). |
+| `deferred-work.md` | [deferred-work.md](_bmad-output/implementation-artifacts/deferred-work.md) | Other deferred items are mostly production refactors ΓÇö out of scope. |
+
+---
+
+## Tasks / Subtasks
+
+- [ ] **Task 0 ΓÇö Re-measure the live suite FIRST (AC3)**
+  - [ ] 0.1 `uv run pytest -p no:cacheprovider --no-cov -q --tb=line` ΓåÆ capture the live failed/error list (baseline: **2 failed, 1098 passed** ΓÇö OutputWriter guards). Record any *new* reds from 11.1ΓÇô11.7.
+  - [ ] 0.2 `cd frontend && npm run test` ΓåÆ confirm green (baseline 153 passed); note the slow AdminDashboard real-timer test.
+  - [ ] 0.3 Confirm 11.7 is merged (Task 7 depends on it). Build the live fix list = (VERIFIED DEBT still present) + (new offenders). Every change must trace to it (AC3).
+
+- [ ] **Task 1 ΓÇö Complete the OutputWriter deletion (AC1/AC2; D1)**
+  - [ ] 1.1 `grep -rn "OutputWriter\|output_writer" src tests` ΓåÆ confirm only: `output_writer.py`, `__init__.py` import/`__all__`, `sarah.py:45` comment, `tests/pipelines/test_output_writer.py`, the integration guards. If a real caller exists, STOP and flag.
+  - [ ] 1.2 Delete `src/ai_qa/pipelines/output_writer.py`.
+  - [ ] 1.3 In `src/ai_qa/pipelines/__init__.py`: remove the import ([:11](src/ai_qa/pipelines/__init__.py)) and the `"OutputWriter"` `__all__` entry ([:22](src/ai_qa/pipelines/__init__.py)).
+  - [ ] 1.4 Delete `tests/pipelines/test_output_writer.py`.
+  - [ ] 1.5 Fix the stale comment `src/ai_qa/agents/sarah.py:45`.
+  - [ ] 1.6 Verify: the two integration guard tests pass; `python -c "import ai_qa.pipelines"` clean; `uv run ruff check .` has no `F822`/unused-import fallout.
+
+- [ ] **Task 2 ΓÇö Deterministic AdminDashboard timer test (AC1; D2)**
+  - [ ] 2.1 In `AdminDashboard.test.tsx`, scope `vi.useFakeTimers()` to the status-dismiss assertion ([:174-180](frontend/src/components/admin/AdminDashboard.test.tsx)); after asserting the banner shows, `await vi.advanceTimersByTimeAsync(3000)` and assert it's gone; delete `{ timeout: 3500 }`.
+  - [ ] 2.2 Use the **async** advance API (RTL deadlock). Keep the global fetch-spy pattern; do **not** make the whole file fake-timered. `afterEach` already restores real timers.
+  - [ ] 2.3 Do **not** change `AdminDashboard.tsx`.
+  - [ ] 2.4 Verify the file is green and no longer spends ~3.5 s on that assertion.
+
+- [ ] **Task 3 ΓÇö Implement or skip the placeholder infra tests (AC2)**
+  - [ ] 3.1 `test_async_test_support` ΓåÆ real assertion (e.g. `assert asyncio.get_running_loop().is_running()`).
+  - [ ] 3.2 `test_coverage_tracking_active` ΓåÆ `assert pytestconfig.pluginmanager.hasplugin("pytest_cov")` (or skip-with-TODO).
+  - [ ] 3.3 Verify `tests/unit/test_infrastructure.py` green.
+
+- [ ] **Task 4 ΓÇö Commit the E2E artifact-tree fixes + correct the `story-10-7` comments (AC1; D7)**
+  - [ ] 4.1 Review the unstaged diffs in `story-10-2`/`story-10-7` against the investigation's "Fix applied + verified"; confirm test-side only; stage them.
+  - [ ] 4.2 Fix the two misleading comments in `story-10-7` ([~:339-340](frontend/e2e/story-10-7-artifact-refresh.spec.ts) "ordered by name" ΓåÆ threads sort by recency; [~:352-353](frontend/e2e/story-10-7-artifact-refresh.spec.ts) guard ΓåÆ `if (!eventProjectId || eventProjectId === activeProjectId)`). The artifact is already created in `projectOne` and the click sequence is already correct ΓÇö **no behavioural change**.
+  - [ ] 4.3 (Optional) correct the investigation doc's backwards click-order note ([:164](_bmad-output/implementation-artifacts/investigations/e2e-artifact-tree-failures-investigation.md)).
+  - [ ] 4.4 E2E re-run is optional/manual (needs the live stack). If you have the 3-terminal stack (or CI from Task 5), run the two specs to reconfirm green; else rely on the investigation's verification + note it.
+
+- [ ] **Task 5 ΓÇö Fix CI end-to-end (AC1; D6)**
+  - [ ] 5.1 Backend job: `python-version: '3.14'` ([:21](.github/workflows/test.yml)); keep `uv pip install --system -e ".[dev]"`; run `uv run pytest` (coverage gate applies via `addopts`).
+  - [ ] 5.2 Replace the broken `frontend` job with a combined **`e2e`** job: a `postgres` service; checkout; Python 3.14 + Node (`.nvmrc`) + uv + Playwright browsers; `npm ci`; **`uv sync`** (so the webServer's `uv run ai-qa` resolves); **`uv run alembic upgrade head`**; `uv run python -m ai_qa.auth.bootstrap_admin --email admin@example.com --name "CI Admin"`; then `npx playwright test` with `CI=true` + env (`DATABASE_*` matching the service incl. `DATABASE_USER=postgres`; `USER_SECRETS_ENCRYPTION_KEY` + `AI_QA_BOOTSTRAP_ADMIN_PASSWORD`/`ADMIN_PASSWORD`/`E2E_ADMIN_PASSWORD` from GitHub Secrets; `API_URL=http://127.0.0.1:8000`; `BASE_URL=http://localhost:5173`; placeholder `TEST_*_KEY`). Playwright's `webServer` (CI mode) starts backend+frontend; `workers:1` is already enforced. Keep both `upload-artifact` steps.
+  - [ ] 5.3 Document required GitHub Secrets (`USER_SECRETS_ENCRYPTION_KEY`, `ADMIN_PASSWORD`) and that live-provider specs (gated on `TEST_*_KEY`) **skip** in CI. Validate the workflow YAML (e.g. `actionlint` or a draft PR run).
+
+- [ ] **Task 6 ΓÇö `testpaths` dedup (AC1; D4)**
+  - [ ] 6.1 `pyproject.toml` ΓåÆ `testpaths = ["tests"]`; verify `uv run pytest --collect-only -q | tail -1` count is unchanged.
+
+- [ ] **Task 7 ΓÇö Requirement draft-dedupe + idempotent approved-save (AC3; D8) ΓÇö REQUIRES 11.7 MERGED**
+  - [ ] 7.1 In `src/ai_qa/pipelines/artifact_adapter.py`, add `delete_draft_requirement(self, page_id: str) -> bool` (module-level `logger`): `list_artifacts(project_id=self.project_id, kind="requirements")` ΓåÆ if any `artifact.name == f"{page_id}.md"`, `delete_artifact(...)` and return its bool; else `False`. Wrap in `try/except Exception` ΓåÆ `logger.warning(...)`, return `False` (never raise ΓÇö deletion is advisory).
+  - [ ] 7.2 Make `save_requirement(...)` idempotent-by-name: before saving, find an existing approved `name == f"{page_id}/requirement.md"` for the project; if present, `delete_artifact` it (default: delete-then-save for fresh provenance), then proceed with the normal `save_artifact`. (Keep the change inside the adapter; do **not** change `ArtifactService.save_artifact`'s general contract.)
+  - [ ] 7.3 In `BobAgent.handle_approve`'s approved branch, **after** a successful `adapter.save_requirement(...)` and **before** the side-car `save_metadata`, call `adapter.delete_draft_requirement(page["page_id"])`. On AC3 save failure the early `return` runs first, so the draft is **not** deleted (page stays reviewable). Preserve 11.6/11.7's resolved-id model exactly (see snippet-fidelity note in 11.7 Task 4.1).
+  - [ ] 7.4 Tests (`tests/test_agents/test_bob.py` + adapter/service tests): (a) adapter unit ΓÇö draft `{page_id}.md` found + deleted; missing draft ΓåÆ `False`, no raise; (b) happy approve ΓÇö `save_requirement` called, then `delete_draft_requirement(page_id)` called, page resolved; (c) deletion-advisory ΓÇö `delete_draft_requirement` returns `False`/raises internally ΓåÆ approval still succeeds; (d) AC3 ΓÇö `save_requirement` raises ΓåÆ page un-resolved, no DONE, `delete_draft_requirement` **never** called, no duplicate; (e) idempotent save ΓÇö saving twice for the same `page_id` leaves exactly one approved row.
+
+- [ ] **Task 8 ΓÇö Harden the cache-TTL test with a clock seam (AC2/AC3; D9)**
+  - [ ] 8.1 In `src/ai_qa/mcp/tools.py`, add `clock: Callable[[], float] = time.time` to `ToolCache.__init__`; store `self._clock`. Stamp `cached_at` via `self._clock()` in `set()` (construct `CachedTool(tool=tool, cached_at=self._clock())` ΓÇö do **not** rely on the field default). Use `self._clock()` in `get()` and `invalidate_expired()`.
+  - [ ] 8.2 Rewrite `test_cache_ttl_expiration` ([tests/mcp/test_connection.py:215-228](tests/mcp/test_connection.py)) to inject a controllable fake clock (a mutable holder), `set()`, advance the clock past the TTL, assert `get()` is `None` ΓÇö **no `time.sleep`**. Add a "before-expiry returns the tool" assertion.
+  - [ ] 8.3 Verify `uv run mypy src` clean (`Callable[[], float]` typed; `from collections.abc import Callable`); no behaviour change (default clock = `time.time`).
+
+- [ ] **Task 9 ΓÇö Full gate + DoD (AC3)**
+  - [ ] 9.1 `uv run pytest` (default `--cov-fail-under=80`) ΓåÆ green, coverage ΓëÑ 80%. Deleting `output_writer.py` + its tests is roughly coverage-neutral; if the % dips, note it (OutputWriter coverage was propping the number ΓÇö itself debt).
+  - [ ] 9.2 `uv run ruff check .` + `uv run mypy src` clean.
+  - [ ] 9.3 `cd frontend && npm run lint && npm run typecheck && npm run test` green.
+  - [ ] 9.4 Update the Dev Agent Record: the live debt list (Task 0), every file touched, before/after suite numbers, and which items were fixed vs already-resolved vs skipped-with-TODO (and why).
+
+---
+
+## Dev Notes
+
+### Build-order reality ΓÇö what's on disk vs. what this story assumes
+
+On `8cf53eb`, none of 11.1ΓÇô11.7 are merged (baseline: 2 backend reds, green frontend). 11.8 is the **last** story, so implement in order; by then:
+
+- 11.6 reshapes `handle_approve` to the resolved-id model; 11.7 adds `PipelineArtifactAdapter.save_requirement` + provenance columns. **Task 7 (Q3 dedupe) depends on 11.7** ΓÇö its line anchors are post-11.7. If 11.7 isn't merged when you reach Task 7, STOP and sequence it after.
+- The OutputWriter reds (Task 1), the AdminDashboard slow test (Task 2), the CI pins (Task 5), the cache test (Task 8), and `testpaths` (Task 6) are **pre-existing** and present regardless of 11.x.
+- Treat any divergence between this inventory and the live suite as a **flag-during-dev** item, not a guess (see [verify-subagent-claims](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/verify-subagent-claims.md), [create-story-snippet-hazards](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/create-story-snippet-hazards.md)).
+
+### Why these specific approaches (verified during story creation)
+
+- **OutputWriter ΓåÆ complete the deletion** (not delete the guards): no runtime caller; the guards encode the intended end-state; removes dead code AND the contradiction.
+- **Cache ΓåÆ clock seam** (not monkeypatch): `cached_at = field(default_factory=time.time)` ([tools.py:102](src/ai_qa/mcp/tools.py)) captures the original `time.time` at class-definition, so monkeypatching only affects the get-side ΓÇö a pure monkeypatch fix is unsound. A constructor `clock` (default `time.time`) is behaviour-preserving and properly testable.
+- **CI E2E ΓåÆ Playwright `webServer`** (not hand-rolled background steps): the config already boots both servers and respects `CI` for fresh start + `workers:1`; CI only needs to provide DB + migrations + admin bootstrap + env. *Mandatory:* `uv run alembic upgrade head` before the run (`create_app` does not migrate) and `uv sync` so `uv run ai-qa` resolves.
+- **Requirement dedupe ΓåÆ delete draft on approve + idempotent `save_requirement`** (Option A + name-idempotency): bounded to the adapter seam; doesn't widen `save_artifact`'s general contract; keeps Thuong's draft-cache decision; yields exactly one approved artifact per page even across AC3 retries.
+- **story-10-7 ΓåÆ already correct**: the non-active behaviour is already proven by the working-tree change; only comments + a doc note need fixing.
+
+### Project-context rules that bite here
+
+- **`uv` only, never `python3`**; `PYTHONUTF8=1` for emoji scripts.
+- **Imports at module top (E402):** the new `logger` in `artifact_adapter.py` and `from collections.abc import Callable` in `tools.py` go at the top ΓÇö not inside functions.
+- **Type checks after deletions:** removing the `OutputWriter` import must not leave a dangling `__all__` name (Ruff `F822`) or unused import. `ToolCache.clock` typed `Callable[[], float]`. No `# type: ignore` / `@ts-ignore`.
+- **No bare `except`:** `delete_draft_requirement` uses `except Exception as exc: logger.warning(...)` (recovery, no re-raise) ΓÇö test with a specific `side_effect`.
+- **Vitest 4 fake timers:** scope to one test; use the **async** advance API; keep the fetch-spy pattern; `vi.mock` is hoisted file-wide (don't introduce a file-wide timer default).
+- **Atomic commits:** keep the OutputWriter deletion, the e2e-spec commit, the CI change, and the Q3 dedupe as separate, readable commits; stage formatter auto-fixes, never `git commit -a`.
+- **Coverage gate** `--cov-fail-under=80` enforced by `addopts`; confirm ΓëÑ80% after deletions (Task 9.1).
+- **Security:** never put secrets in logs/messages. CI secrets are GitHub-Secrets-injected and masked; never `echo` them.
+
+### Do NOT do (scope discipline ΓÇö AC3)
+
+- **No production behaviour changes beyond the four approved** (OutputWriter deletion, Q3 dedupe, Q4 clock seam, CI). Do not touch agent logic beyond the Q3 `handle_approve` draft-delete call, the artifact service's general contract, the DB schema, or `AdminDashboard.tsx`.
+- **No broad test refactor** (don't consolidate the per-file `db_session`/`client` fixtures, don't rename passing tests). Only touch red/slow/contradictory/stub tests.
+- **No new deps, no migration, no new package.** (Q3 adds no column; Q4 adds a constructor param with a default.)
+- **Do not** delete/weaken real guard tests, the leak-canary suite, or the single-MCP-client/disconnect Bob tests.
+- **Do not** touch the `test_requirement_formatter.py` `pass` lines ΓÇö they're mock method bodies, not empty tests.
+
+### Testing approach (house style)
+
+- **Backend:** `uv run pytest`; specific `pytest.raises(..., match=...)`; `Generator[T, None, None]` yield fixtures; SQLite `engine.dispose()`; patch `ai_qa.agents.bob.PipelineArtifactAdapter` at the class boundary for Bob tests; real `ArtifactService` over in-memory SQLite for adapter/service tests.
+- **Frontend (Vitest 4):** global-fetch-spy + `AuthProvider`/`ProjectProvider`; fake timers scoped + async-advanced; `npm run typecheck` after TS edits.
+- **E2E (Playwright):** no `page.route` / `waitForTimeout`; `getByRole`/network-first; `--workers=1`.
+
+### Latest tech / external context
+
+No new library/version. The one externally-informed technique is **Vitest 4 fake timers + React Testing Library**: with `vi.useFakeTimers()`, RTL `waitFor`/`findBy` polls but time doesn't advance on its own ΓåÆ deadlock. Use the **async** advance API (`await vi.advanceTimersByTimeAsync(3000)`) to flush microtasks between ticks so the pending `setState` resolves.
+Sources: [Vitest ΓÇö Timers](https://vitest.dev/guide/mocking/timers), [Vitest ΓÇö vi API](https://vitest.dev/api/vi.html), [RTL #1198](https://github.com/testing-library/react-testing-library/issues/1198), [Vitest #3117](https://github.com/vitest-dev/vitest/issues/3117).
+
+### Git intelligence (recent work patterns)
+
+`8cf53eb epic 10 all code done`, `9d878c5 (10.6 events)`, `1852886 (10-3)`, `39db313 (3.12ΓåÆ3.14)`. The OutputWriter reds + CI 3.12 pin are fallout from those two: the artifact migration left OutputWriter half-deleted; the 3.14 upgrade wasn't propagated into CI. The unstaged `story-10-2`/`story-10-7` edits are the in-flight E2E fix. This story closes those loose ends + the four approved hardenings.
+
+### Project Structure Notes
+
+**Backend files touched:**
+
+- `src/ai_qa/pipelines/output_writer.py` ΓÇö **deleted** (D1).
+- `src/ai_qa/pipelines/__init__.py` ΓÇö remove `OutputWriter` import + `__all__` entry.
+- `src/ai_qa/agents/sarah.py` ΓÇö fix stale comment (:45).
+- `src/ai_qa/pipelines/artifact_adapter.py` ΓÇö add `delete_draft_requirement(...)`; make `save_requirement(...)` idempotent-by-name (D8; post-11.7).
+- `src/ai_qa/agents/bob.py` ΓÇö `handle_approve` approved branch calls `delete_draft_requirement` after a successful save (D8; post-11.7).
+- `src/ai_qa/mcp/tools.py` ΓÇö `ToolCache` clock seam (D9).
+- `tests/pipelines/test_output_writer.py` ΓÇö **deleted**.
+- `tests/unit/test_infrastructure.py` ΓÇö real assertions / skip-with-TODO.
+- `tests/mcp/test_connection.py` ΓÇö deterministic cache-TTL test.
+- `tests/test_agents/test_bob.py` (+ adapter/service tests) ΓÇö Q3 dedupe tests.
+- `pyproject.toml` ΓÇö `testpaths = ["tests"]`.
+
+**Frontend files touched:**
+
+- `frontend/src/components/admin/AdminDashboard.test.tsx` ΓÇö fake-timer the status-dismiss assertion.
+- `frontend/e2e/story-10-2-artifact-tree-browsing.spec.ts`, `frontend/e2e/story-10-7-artifact-refresh.spec.ts` ΓÇö commit the verified fixes; correct the `story-10-7` comments.
+
+**Infra:**
+
+- `.github/workflows/test.yml` ΓÇö Python 3.14, `uv run pytest`, combined `e2e` job (Postgres + migrate + bootstrap + Playwright webServer).
+
+**New files:** none. **No migration, no new package.**
+
+### Previous-story intelligence
+
+- **Epic 10 retro** ΓÇö origin (named the AdminDashboard timeout + deletion stubs; set the fix-or-skip rule). [epic-10-retrospective-2026-06-11.md:26-34](_bmad-output/implementation-artifacts/epic-10-retrospective-2026-06-11.md).
+- **Story 11.7** ΓÇö Saved Questions 1 & 2 are now Q3 here (draft dedupe + single-artifact-per-page); Task 7 modifies 11.7's `save_requirement` + approved branch (post-11.7). [11-7](_bmad-output/implementation-artifacts/11-7-requirements-artifact-save.md).
+- **Story 10.4** ΓÇö flagged then reconciled the delete-event stub. [10-4](_bmad-output/implementation-artifacts/10-4-artifact-edit-delete-and-version-metadata.md).
+- **Epic 8 retro** ΓÇö Argon2 ΓåÆ e2e `--workers=1`; honor in CI (already set in `playwright.config.ts:38`). [epic-8-retro:28](_bmad-output/implementation-artifacts/epic-8-retrospective-2026-06-09.md).
+- Memory: [backend-test-suite-orphaned-legacy-tests](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/backend-test-suite-orphaned-legacy-tests.md) is updated (live = 2 reds). [epic-10-artifact-ui-gotchas](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/epic-10-artifact-ui-gotchas.md) ΓÇö don't disturb artifact-tree behaviour while committing the e2e fix.
+
+### References
+
+- [Source: epics.md:1120-1135] ΓÇö Story 11.8 ACs.
+- [Source: epic-10-retrospective-2026-06-11.md:26-34] ΓÇö origin + fix-or-skip rule.
+- [Source: tests/integration/test_artifact_service_integration.py:196-222] ΓÇö OutputWriter guards (RED).
+- [Source: tests/pipelines/test_output_writer.py] ΓÇö contradicting unit tests (delete).
+- [Source: src/ai_qa/pipelines/output_writer.py:17; __init__.py:11,22; agents/sarah.py:45] ΓÇö remnants.
+- [Source: frontend/src/components/admin/AdminDashboard.test.tsx:91-93,174-180; AdminDashboard.tsx:106-110] ΓÇö timer test + product timer.
+- [Source: tests/unit/test_infrastructure.py:60-77] ΓÇö `assert True` canaries.
+- [Source: frontend/playwright.config.ts:38,67-86] ΓÇö webServer (both servers), workers:1, CI-fresh.
+- [Source: .github/workflows/test.yml:21,30,58-59] ΓÇö Python pin + broken e2e job.
+- [Source: frontend/e2e/story-10-7-artifact-refresh.spec.ts:343-385] ΓÇö already creates artifact in projectOne + click sequence; comments to fix.
+- [Source: src/ai_qa/artifacts/service.py:71-131,185-225] ΓÇö `save_artifact` (no dedupe), `list_artifacts`, `delete_artifact`.
+- [Source: src/ai_qa/mcp/tools.py:97-168] ΓÇö `ToolCache` + `cached_at` default_factory.
+- [Source: tests/mcp/test_connection.py:215-228] ΓÇö cache-TTL `time.sleep`.
+- [Source: pyproject.toml:68-71] ΓÇö `testpaths` dup + `--cov-fail-under=80`.
+- [Source: 11-7-requirements-artifact-save.md (Saved Questions 1-2, draft-vs-approved discriminator)] ΓÇö Q3 origin.
+- [Source: project-context.md] ΓÇö `uv`/`npm` only; Ruff + mypy(src) strict; no `# type: ignore`/`@ts-ignore`; Vitest-4; atomic commits; security.
+
+### Definition of Done
+
+- [ ] Task 0 live re-measure done; every change traces to a live debt item (AC3).
+- [ ] OutputWriter fully removed (module + `__init__` export + contradicting unit test + stale comment); the two integration guards pass; `import ai_qa.pipelines` clean (AC1/AC2).
+- [ ] AdminDashboard status-dismiss assertion deterministic via scoped fake timers; `AdminDashboard.tsx` unchanged (AC1).
+- [ ] The two `assert True` canaries assert something real or are skip-with-TODO (AC2).
+- [ ] E2E artifact-tree fixes committed; `story-10-7` comments corrected (recency + full guard condition); behaviour unchanged (AC1).
+- [ ] CI: Python 3.14 + `uv run pytest`; a working `e2e` job (Postgres + `uv sync` + `alembic upgrade head` + admin bootstrap + `CI=true` Playwright) that can actually run; required Secrets documented; live-provider specs skip cleanly (AC1).
+- [ ] `testpaths = ["tests"]` (collected count unchanged) (AC1).
+- [ ] Requirement dedupe (post-11.7): `delete_draft_requirement` + idempotent `save_requirement`; one approved artifact per page across approve + AC3 retry; draft deleted only on success; tests cover happy/advisory/AC3/idempotent (AC3).
+- [ ] `ToolCache` clock seam; cache-TTL test deterministic (no `time.sleep`); default behaviour unchanged (AC2/AC3).
+- [ ] `uv run pytest` green, coverage ΓëÑ 80%; `uv run ruff check .` + `uv run mypy src` clean; `npm run lint`/`typecheck`/`test` green.
+- [ ] No production change beyond the four approved; Dev Record lists fixed vs already-resolved vs skipped-with-TODO.
+
+---
+
+## Resolved Decisions (confirmed by Thuong ΓÇö do NOT revisit)
+
+Confirmed 2026-06-11. D1ΓÇôD5 set at story creation; D6ΓÇôD9 confirmed when Thuong answered the four Saved Questions ("sß╗¡a hß║┐t / sß╗¡a test / sß╗¡a lu├┤n / harden").
+
+1. **D1 ΓÇö Complete the OutputWriter deletion** (module + `__init__` export + `tests/pipelines/test_output_writer.py` + `sarah.py:45` comment), not delete the guards. No runtime caller.
+2. **D2 ΓÇö Fix the AdminDashboard slow test with scoped Vitest fake timers**, not by changing the 3 s product timer.
+3. **D3 ΓÇö Bump CI to Python 3.14.** (Superseded/expanded by D6 ΓÇö full CI fix.)
+4. **D4 ΓÇö `testpaths = ["tests"]`** (dedup, collection-neutral).
+5. **D5 ΓÇö Re-enumerate live before fixing.**
+6. **D6 ΓÇö Fix CI fully (Q1):** Python 3.14 + `uv run pytest`; replace the broken e2e job with one that boots a migrated, admin-bootstrapped backend + frontend via Playwright's `webServer` (CI mode). Provider-key specs skip; required Secrets documented. *(Mandatory details: `uv sync`, `alembic upgrade head`, Postgres service, `DATABASE_USER=postgres`, `USER_SECRETS_ENCRYPTION_KEY`.)*
+7. **D7 ΓÇö Fix the `story-10-7` test (Q2):** the non-active behaviour is already correct in the working tree (commit it); fix the two misleading comments (recency not alphabetical; full guard condition). No behavioural rework.
+8. **D8 ΓÇö Pull in 11.7's dedupe follow-ups (Q3):** delete the draft on approval + make `save_requirement` idempotent-by-name ΓåÆ one approved artifact per page (incl. AC3 retry). Depends on 11.7 merged. Default: delete-then-save (fresh provenance) over `create_version`.
+9. **D9 ΓÇö Harden the cache-TTL test (Q4) via a `ToolCache` clock seam** (additive, default `time.time`), because `default_factory=time.time` defeats pure monkeypatching.
+
+## Saved Questions (residual ΓÇö defaults applied; flag only if a test forces the issue)
+
+1. **Mary's draft-vs-approved filter (Story 12.1, not 11.8).** Even with D8, 12.1 should filter approved requirements (`source_type IS NOT NULL` / the `{page_id}/requirement.md` name) for belt-and-suspenders. Flagged for 12.1.
+2. **D8 retry: delete-then-save vs `create_version`.** Default = delete-then-save (fresh provenance; requirements version-history not a stated need). Re-decide to `create_version` only if history is wanted.
+3. **CI Secrets must be configured in the repo** (`USER_SECRETS_ENCRYPTION_KEY`, `ADMIN_PASSWORD`) or the e2e job fails fast ΓÇö operational prerequisite, document in README.
+
+---
+
+## Dev Agent Record
+
+### Agent Model Used
+
+{{agent_model_name_version}}
+
+### Debug Log References
+
+### Completion Notes List
+
+- Ultimate context engine analysis completed ΓÇö comprehensive developer guide created. Verified against the live suite (backend 2 failed/1098 passed, frontend 153 passed on `8cf53eb`) and against the four scope expansions Thuong approved (each design adversarially verified against real code via a fan-out workflow during story creation).
+
+### File List
+
+### Change Log
diff --git a/_bmad-output/implementation-artifacts/sprint-status.yaml b/_bmad-output/implementation-artifacts/sprint-status.yaml
index ae1d149..289382f 100644
--- a/_bmad-output/implementation-artifacts/sprint-status.yaml
+++ b/_bmad-output/implementation-artifacts/sprint-status.yaml
@@ -36,7 +36,7 @@
 # - Dev moves story to 'review', then runs code-review (fresh context, different LLM recommended)
 
 generated: 2026-05-29T00:14:09.493182
-last_updated: 2026-06-12T01:00:00.000000
+last_updated: 2026-06-11T22:30:00.000000
 project: ai qa automation
 project_key: NOKEY
 tracking_system: file-system
@@ -148,14 +148,14 @@ development_status:
   10-8-open-artifact-update-delete-notice: done
   epic-10-retrospective: done
   epic-11: in-progress
-  11-1-mcp-client-foundation-for-confluence-and-jira: ready-for-dev
+  11-1-mcp-client-foundation-for-confluence-and-jira: review
   11-2-bob-confluence-url-intake-and-pipeline-trigger: ready-for-dev
   11-3-confluence-content-retrieval-and-parsing: ready-for-dev
   11-4-jira-requirements-retrieval: ready-for-dev
   11-5-input-quality-detection-before-generation: ready-for-dev
   11-6-bob-reviewable-extraction-output: ready-for-dev
   11-7-requirements-artifact-save: ready-for-dev
-  11-8-technical-debt-sweep-and-hardening: backlog
+  11-8-technical-debt-sweep-and-hardening: ready-for-dev
   epic-11-retrospective: optional
   epic-12: backlog
   12-1-test-case-generation-input-selection: backlog
diff --git a/src/ai_qa/mcp/client.py b/src/ai_qa/mcp/client.py
index ba075f9..52d0c75 100644
--- a/src/ai_qa/mcp/client.py
+++ b/src/ai_qa/mcp/client.py
@@ -260,6 +260,24 @@ class MCPClient:
                 raise MCPToolError(f"Tool '{name}' not found on server") from e
             raise
 
+    async def check_required_tools(self, required_tools: list[str]) -> list[str]:
+        """Return names from required_tools that are absent on the MCP server.
+
+        Args:
+            required_tools: Tool names to check for (use prefixed names when applicable).
+
+        Returns:
+            List of missing tool names; empty list means all required tools are present.
+
+        Raises:
+            MCPConnectionError: If list_tools() fails due to connectivity.
+            MCPAuthenticationError: If authentication fails.
+        """
+        if not required_tools:
+            return []
+        available = {t.name for t in await self.list_tools()}
+        return [name for name in required_tools if name not in available]
+
     async def discover_capabilities(self) -> ServerCapabilities:
         """Discover server capabilities.
 
diff --git a/src/ai_qa/pipelines/__init__.py b/src/ai_qa/pipelines/__init__.py
index 93c9b41..01cbe00 100644
--- a/src/ai_qa/pipelines/__init__.py
+++ b/src/ai_qa/pipelines/__init__.py
@@ -7,7 +7,13 @@ the AI QA workflow. Each stage follows the StageResult contract.
 from ai_qa.models import TestCase, TestCaseStep
 from ai_qa.pipelines.confluence_reader import ConfluenceReader
 from ai_qa.pipelines.content_parser import ContentParser
-from ai_qa.pipelines.models import ConfluencePage, OutputMetadata, PageSummary, ParsedContent
+from ai_qa.pipelines.models import (
+    ConfluencePage,
+    JiraIssue,
+    OutputMetadata,
+    PageSummary,
+    ParsedContent,
+)
 from ai_qa.pipelines.output_writer import OutputWriter
 from ai_qa.pipelines.test_case_extractor import TestCaseExtractor
 from ai_qa.pipelines.vision_locator import LocatorResult, SelectorInfo, VisionLocator
@@ -15,6 +21,7 @@ from ai_qa.pipelines.vision_locator import LocatorResult, SelectorInfo, VisionLo
 __all__ = [
     "ConfluenceReader",
     "ConfluencePage",
+    "JiraIssue",
     "PageSummary",
     "ContentParser",
     "ParsedContent",
diff --git a/src/ai_qa/pipelines/confluence_reader.py b/src/ai_qa/pipelines/confluence_reader.py
index 962cb18..d6a079a 100644
--- a/src/ai_qa/pipelines/confluence_reader.py
+++ b/src/ai_qa/pipelines/confluence_reader.py
@@ -280,6 +280,19 @@ class ConfluenceReader:
         """Get the full tool name including any configured prefix."""
         return f"{self._tool_prefix}{base_name}"
 
+    async def check_tool_availability(self) -> list[str]:
+        """Return names of required Confluence tools absent from the MCP server.
+
+        Returns:
+            List of missing tool names; empty list means all tools are present.
+
+        Raises:
+            MCPConnectionError: If list_tools() cannot reach the MCP server.
+            MCPAuthenticationError: If authentication with the MCP server fails.
+        """
+        prefixed = [self._get_tool_name(t) for t in self.CONFLUENCE_TOOLS]
+        return await self._mcp_client.check_required_tools(prefixed)
+
     async def read_page(self, page_url: str) -> StageResult:
         """Read a single Confluence page.
 
diff --git a/src/ai_qa/pipelines/jira_reader.py b/src/ai_qa/pipelines/jira_reader.py
new file mode 100644
index 0000000..d816f19
--- /dev/null
+++ b/src/ai_qa/pipelines/jira_reader.py
@@ -0,0 +1,229 @@
+"""Jira Reader Pipeline Stage.
+
+This module provides the JiraReader pipeline stage for retrieving
+issue content from Jira via MCP server.
+"""
+
+from __future__ import annotations
+
+import re
+from datetime import UTC, datetime
+from typing import Any
+
+from ai_qa.config import AppSettings
+from ai_qa.exceptions import MCPToolError
+from ai_qa.mcp.client import MCPClient
+from ai_qa.models import StageResult
+from ai_qa.pipelines.models import JiraIssue
+
+_ISSUE_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9_]+-\d+)\b")
+
+
+class JiraReader:
+    """Pipeline stage for reading Jira issues via MCP.
+
+    Retrieves Jira issue content through the MCP server and returns
+    structured JiraIssue data for downstream processing.
+
+    Example:
+        >>> reader = JiraReader(mcp_client, jira_base_url="https://jira.company.com")
+        >>> result = await reader.read_issue("PROJ-123")
+        >>> if result.success:
+        ...     issue = result.data
+        ...     print(issue.summary)
+    """
+
+    JIRA_TOOLS: list[str] = [
+        "jira_get_issue",
+        "jira_search_issues",
+        "jira_get_project",
+    ]
+
+    def __init__(
+        self,
+        mcp_client: MCPClient,
+        jira_base_url: str | None = None,
+        settings: AppSettings | None = None,
+    ) -> None:
+        """Initialize Jira reader.
+
+        Args:
+            mcp_client: Configured MCPClient instance
+            jira_base_url: Base URL for the Jira instance
+            settings: Optional AppSettings (uses mcp_tool_prefix if provided)
+
+        Raises:
+            ValueError: If mcp_client is None
+        """
+        if mcp_client is None:
+            raise ValueError("MCP client is required")
+        self._mcp_client = mcp_client
+        self._jira_base_url = (jira_base_url or "").rstrip("/")
+        _settings = settings or (
+            mcp_client._settings if hasattr(mcp_client, "_settings") else None
+        )
+        self._tool_prefix = (
+            getattr(_settings, "mcp_tool_prefix", "") if _settings is not None else ""
+        )
+
+    def _get_tool_name(self, base_name: str) -> str:
+        """Get the full tool name including any configured prefix."""
+        return f"{self._tool_prefix}{base_name}"
+
+    @classmethod
+    def _parse_issue_ref(cls, ref: str) -> str:
+        """Extract Jira issue key from a URL or bare key string.
+
+        Args:
+            ref: Issue key (e.g. "PROJ-123") or Jira browse URL
+
+        Returns:
+            Extracted issue key
+
+        Raises:
+            ValueError: If ref is empty or contains no valid issue key
+        """
+        stripped = ref.strip()
+        if not stripped:
+            raise ValueError("Issue reference must not be empty")
+        match = _ISSUE_KEY_RE.search(stripped)
+        if not match:
+            raise ValueError(f"No Jira issue key found in: {stripped!r}")
+        return match.group(1)
+
+    def _map_issue_data(self, raw: Any, issue_key: str) -> JiraIssue:
+        """Map raw MCP tool response to JiraIssue model.
+
+        Handles both Jira Cloud (flat) and Data Center (fields-nested) response shapes.
+        """
+        if not isinstance(raw, dict):
+            raw = {}
+        # Data Center wraps everything under "fields"; Cloud may be flat
+        fields: Any = raw.get("fields", raw)
+        if not isinstance(fields, dict):
+            fields = raw
+
+        resolved_key: str = str(raw.get("key", "") or issue_key)
+
+        def _get_str(d: Any, key: str) -> str | None:
+            val = d.get(key) if isinstance(d, dict) else None
+            return str(val) if val is not None else None
+
+        def _get_name(d: Any, key: str) -> str | None:
+            obj = d.get(key) if isinstance(d, dict) else None
+            if isinstance(obj, dict):
+                return str(obj.get("displayName") or obj.get("name") or "")
+            return None
+
+        def _get_nested_name(d: Any, key: str) -> str | None:
+            obj = d.get(key) if isinstance(d, dict) else None
+            if isinstance(obj, dict):
+                return str(obj.get("name") or "")
+            return None
+
+        status_val = fields.get("status") if isinstance(fields, dict) else None
+        status: str | None
+        if isinstance(status_val, dict):
+            status = str(status_val.get("name") or "")
+        else:
+            status = str(status_val) if status_val is not None else None
+
+        project_val = fields.get("project") if isinstance(fields, dict) else None
+        project_key: str
+        if isinstance(project_val, dict):
+            project_key = str(project_val.get("key") or "")
+        elif project_val is not None:
+            project_key = str(project_val)
+        else:
+            project_key = ""
+
+        labels_val = fields.get("labels") if isinstance(fields, dict) else None
+        labels: list[str] = list(labels_val) if isinstance(labels_val, list) else []
+
+        url = f"{self._jira_base_url}/browse/{resolved_key}" if self._jira_base_url else ""
+
+        return JiraIssue(
+            issue_key=resolved_key,
+            summary=str(fields.get("summary", "") if isinstance(fields, dict) else ""),
+            description=_get_str(fields, "description"),
+            acceptance_criteria=_get_str(fields, "acceptance_criteria"),
+            status=status,
+            labels=labels,
+            project_key=project_key,
+            url=url,
+            retrieved_at=datetime.now(tz=UTC),
+            issue_type=_get_nested_name(fields, "issuetype"),
+            reporter=_get_name(fields, "reporter"),
+            assignee=_get_name(fields, "assignee"),
+        )
+
+    async def read_issue(self, issue_ref: str) -> StageResult:
+        """Read a single Jira issue.
+
+        Args:
+            issue_ref: Issue key (e.g. "PROJ-123") or Jira browse URL
+
+        Returns:
+            StageResult with JiraIssue data on success, or error details on failure.
+            Never re-raises MCP errors ΓÇö soft failures are returned as StageResult.
+        """
+        try:
+            issue_key = self._parse_issue_ref(issue_ref)
+        except ValueError as e:
+            return StageResult(
+                success=False,
+                data=None,
+                errors=[str(e)],
+                warnings=[],
+                confidence=0.0,
+            )
+
+        try:
+            tool_result = await self._mcp_client.call_tool(
+                self._get_tool_name("jira_get_issue"),
+                {
+                    "issue_key": issue_key,
+                    "userPrompt": "User initiated a requirements extraction workflow from a Jira issue.",
+                    "llmReasoning": "Need to retrieve the Jira issue content to fulfill the user's request.",
+                },
+            )
+        except MCPToolError:
+            return StageResult(
+                success=False,
+                data=None,
+                errors=["Jira tool not available on the MCP server"],
+                warnings=[],
+                confidence=0.0,
+            )
+
+        if not tool_result.success:
+            return StageResult(
+                success=False,
+                data=None,
+                errors=[tool_result.error or "Failed to retrieve Jira issue"],
+                warnings=[],
+                confidence=0.0,
+            )
+
+        issue = self._map_issue_data(tool_result.data, issue_key)
+
+        return StageResult(
+            success=True,
+            data=issue,
+            errors=[],
+            warnings=[],
+            confidence=1.0,
+        )
+
+    async def check_tool_availability(self) -> list[str]:
+        """Return names of required Jira tools absent from the MCP server.
+
+        Returns:
+            List of missing tool names; empty list means all tools are present.
+
+        Raises:
+            MCPConnectionError: If list_tools() cannot reach the MCP server.
+            MCPAuthenticationError: If authentication with the MCP server fails.
+        """
+        prefixed = [self._get_tool_name(t) for t in self.JIRA_TOOLS]
+        return await self._mcp_client.check_required_tools(prefixed)
diff --git a/src/ai_qa/pipelines/models.py b/src/ai_qa/pipelines/models.py
index e30ce0a..461a7e0 100644
--- a/src/ai_qa/pipelines/models.py
+++ b/src/ai_qa/pipelines/models.py
@@ -54,6 +54,57 @@ class ConfluencePage(BaseModel):
         return self.model_dump(mode="json")
 
 
+class JiraIssue(BaseModel):
+    """Represents a retrieved Jira issue.
+
+    Attributes:
+        issue_key: Issue key (e.g. "PROJ-123")
+        summary: Issue summary/title
+        description: Issue description body
+        acceptance_criteria: Acceptance criteria text (from description or custom field)
+        status: Issue status name
+        labels: List of issue labels
+        project_key: Jira project key
+        url: Direct URL to the issue in Jira
+        retrieved_at: ISO 8601 timestamp when issue was retrieved
+        issue_type: Issue type name (e.g. "Story", "Bug")
+        reporter: Display name of reporter
+        assignee: Display name of assignee
+    """
+
+    issue_key: str = Field(description="Jira issue key (e.g. 'PROJ-123')")
+    summary: str = Field(description="Issue summary/title")
+    description: str | None = Field(default=None, description="Issue description body")
+    acceptance_criteria: str | None = Field(
+        default=None, description="Acceptance criteria text"
+    )
+    status: str | None = Field(default=None, description="Issue status name")
+    labels: list[str] = Field(default_factory=list, description="List of issue labels")
+    project_key: str = Field(description="Jira project key")
+    url: str = Field(description="Direct URL to the issue in Jira")
+    retrieved_at: datetime = Field(
+        default_factory=lambda: datetime.now(UTC),
+        description="ISO 8601 timestamp when issue was retrieved",
+    )
+    issue_type: str | None = Field(default=None, description="Issue type name")
+    reporter: str | None = Field(default=None, description="Display name of reporter")
+    assignee: str | None = Field(default=None, description="Display name of assignee")
+
+    model_config = ConfigDict(validate_assignment=True)
+
+    @field_validator("retrieved_at")
+    @classmethod
+    def validate_retrieved_at_timezone(cls, v: datetime) -> datetime:
+        """Ensure retrieved_at is timezone-aware."""
+        if v.tzinfo is None:
+            raise ValueError("retrieved_at must be timezone-aware")
+        return v
+
+    def to_dict(self) -> dict[str, Any]:
+        """Convert to dictionary for serialization."""
+        return self.model_dump(mode="json")
+
+
 class ParsedContent(BaseModel):
     """Represents LLM-optimized content parsed from a Confluence page."""
 
diff --git a/tests/pipelines/test_jira_reader.py b/tests/pipelines/test_jira_reader.py
new file mode 100644
index 0000000..48c25c0
--- /dev/null
+++ b/tests/pipelines/test_jira_reader.py
@@ -0,0 +1,235 @@
+"""Tests for JiraReader pipeline stage and related capability helpers."""
+
+from unittest.mock import AsyncMock, MagicMock
+
+import pytest
+
+from ai_qa.exceptions import MCPConnectionError, MCPToolError  # noqa: F401 (used in pytest.raises)
+from ai_qa.mcp.tools import ToolResult
+from ai_qa.pipelines.jira_reader import JiraReader
+
+# ---------------------------------------------------------------------------
+# Fixtures
+# ---------------------------------------------------------------------------
+
+
+@pytest.fixture
+def mock_mcp_client() -> MagicMock:
+    client = MagicMock()
+    client.is_connected = True
+    client.server_url = "http://localhost:3000/sse"
+    client._settings = MagicMock()
+    client._settings.mcp_tool_prefix = ""
+    client.call_tool = AsyncMock()
+    client.list_tools = AsyncMock()
+    client.check_required_tools = AsyncMock()
+    return client
+
+
+@pytest.fixture
+def jira_reader(mock_mcp_client: MagicMock) -> JiraReader:
+    return JiraReader(
+        mcp_client=mock_mcp_client,
+        jira_base_url="https://jira.company.com",
+    )
+
+
+_REALISTIC_PAYLOAD = {
+    "key": "PROJ-123",
+    "fields": {
+        "summary": "Login fails for SSO users",
+        "description": "Steps to reproduce: ...",
+        "acceptance_criteria": "Given SSO is configured, user can log in",
+        "status": {"name": "In Progress"},
+        "labels": ["auth", "sso"],
+        "project": {"key": "PROJ"},
+        "issuetype": {"name": "Story"},
+        "reporter": {"displayName": "Alice Smith"},
+        "assignee": {"displayName": "Bob Jones"},
+    },
+}
+
+
+# ---------------------------------------------------------------------------
+# _parse_issue_ref tests
+# ---------------------------------------------------------------------------
+
+
+class TestParseIssueRef:
+    def test_plain_key(self) -> None:
+        assert JiraReader._parse_issue_ref("PROJ-123") == "PROJ-123"
+
+    def test_cloud_url(self) -> None:
+        url = "https://company.atlassian.net/browse/PROJ-123"
+        assert JiraReader._parse_issue_ref(url) == "PROJ-123"
+
+    def test_datacenter_url(self) -> None:
+        url = "https://jira.company.com/browse/PROJ-123"
+        assert JiraReader._parse_issue_ref(url) == "PROJ-123"
+
+    def test_empty_string_raises(self) -> None:
+        with pytest.raises(ValueError, match="must not be empty"):
+            JiraReader._parse_issue_ref("")
+
+    def test_whitespace_only_raises(self) -> None:
+        with pytest.raises(ValueError, match="must not be empty"):
+            JiraReader._parse_issue_ref("   ")
+
+    def test_garbage_input_raises(self) -> None:
+        with pytest.raises(ValueError, match="No Jira issue key found"):
+            JiraReader._parse_issue_ref("https://example.com/not-a-jira-url")
+
+    def test_lowercase_key_raises(self) -> None:
+        with pytest.raises(ValueError, match="No Jira issue key found"):
+            JiraReader._parse_issue_ref("proj-123")
+
+
+# ---------------------------------------------------------------------------
+# read_issue happy path
+# ---------------------------------------------------------------------------
+
+
+class TestReadIssueHappyPath:
+    async def test_returns_jira_issue(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client.call_tool.return_value = ToolResult.from_data(_REALISTIC_PAYLOAD)
+
+        result = await jira_reader.read_issue("PROJ-123")
+
+        assert result.success is True
+        assert result.data is not None
+        issue = result.data
+        assert issue.issue_key == "PROJ-123"
+        assert issue.summary == "Login fails for SSO users"
+        assert issue.description == "Steps to reproduce: ..."
+        assert issue.acceptance_criteria == "Given SSO is configured, user can log in"
+        assert issue.status == "In Progress"
+        assert issue.labels == ["auth", "sso"]
+        assert issue.project_key == "PROJ"
+        assert issue.issue_type == "Story"
+        assert issue.reporter == "Alice Smith"
+        assert issue.assignee == "Bob Jones"
+        assert "PROJ-123" in issue.url
+
+    async def test_url_contains_browse(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client.call_tool.return_value = ToolResult.from_data(_REALISTIC_PAYLOAD)
+        result = await jira_reader.read_issue("PROJ-123")
+        assert result.success is True
+        assert result.data is not None
+        assert "/browse/PROJ-123" in result.data.url
+
+    async def test_accepts_browse_url(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client.call_tool.return_value = ToolResult.from_data(_REALISTIC_PAYLOAD)
+        result = await jira_reader.read_issue("https://jira.company.com/browse/PROJ-123")
+        assert result.success is True
+        assert result.data is not None
+        assert result.data.issue_key == "PROJ-123"
+
+
+# ---------------------------------------------------------------------------
+# read_issue error paths
+# ---------------------------------------------------------------------------
+
+
+class TestReadIssueErrors:
+    async def test_mcp_tool_error_returns_failure(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client.call_tool.side_effect = MCPToolError("tool not found")
+        result = await jira_reader.read_issue("PROJ-123")
+        assert result.success is False
+        assert result.data is None
+        assert result.errors
+        assert "Jira tool not available" in result.errors[0]
+
+    async def test_unsuccessful_tool_result_returns_failure(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client.call_tool.return_value = ToolResult.from_error("issue not found")
+        result = await jira_reader.read_issue("PROJ-123")
+        assert result.success is False
+        assert result.data is None
+        assert result.errors
+
+    async def test_invalid_issue_ref_returns_failure(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        result = await jira_reader.read_issue("not-a-jira-key")
+        assert result.success is False
+        assert result.data is None
+        mock_mcp_client.call_tool.assert_not_called()
+
+
+# ---------------------------------------------------------------------------
+# check_tool_availability tests
+# ---------------------------------------------------------------------------
+
+
+class TestCheckToolAvailability:
+    async def test_returns_missing_tool(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client.check_required_tools.return_value = ["jira_search_issues"]
+        missing = await jira_reader.check_tool_availability()
+        assert missing == ["jira_search_issues"]
+
+    async def test_returns_empty_when_all_present(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client.check_required_tools.return_value = []
+        missing = await jira_reader.check_tool_availability()
+        assert missing == []
+
+    async def test_propagates_mcp_connection_error(
+        self, jira_reader: JiraReader, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client.check_required_tools.side_effect = MCPConnectionError(
+            "cannot reach server"
+        )
+        with pytest.raises(MCPConnectionError):
+            await jira_reader.check_tool_availability()
+
+    async def test_passes_prefixed_names(
+        self, mock_mcp_client: MagicMock
+    ) -> None:
+        mock_mcp_client._settings.mcp_tool_prefix = "myprefix_"
+        reader = JiraReader(mock_mcp_client, jira_base_url="https://jira.company.com")
+        mock_mcp_client.check_required_tools.return_value = []
+        await reader.check_tool_availability()
+        called_with = mock_mcp_client.check_required_tools.call_args[0][0]
+        assert all(name.startswith("myprefix_") for name in called_with)
+
+
+# ---------------------------------------------------------------------------
+# ConfluenceReader.check_tool_availability delegation
+# ---------------------------------------------------------------------------
+
+
+class TestConfluenceReaderCheckToolAvailability:
+    async def test_delegates_to_check_required_tools(
+        self, mock_mcp_client: MagicMock
+    ) -> None:
+        from ai_qa.pipelines.confluence_reader import ConfluenceReader
+
+        mock_mcp_client.check_required_tools.return_value = []
+        reader = ConfluenceReader(mcp_client=mock_mcp_client)
+        await reader.check_tool_availability()
+
+        mock_mcp_client.check_required_tools.assert_called_once()
+        called_tools: list[str] = mock_mcp_client.check_required_tools.call_args[0][0]
+        assert len(called_tools) == len(ConfluenceReader.CONFLUENCE_TOOLS)
+
+    async def test_returns_missing_confluence_tools(
+        self, mock_mcp_client: MagicMock
+    ) -> None:
+        from ai_qa.pipelines.confluence_reader import ConfluenceReader
+
+        mock_mcp_client.check_required_tools.return_value = ["confluence_get_page"]
+        reader = ConfluenceReader(mcp_client=mock_mcp_client)
+        missing = await reader.check_tool_availability()
+        assert missing == ["confluence_get_page"]
diff --git a/tests/unit/test_mcp_client_capabilities.py b/tests/unit/test_mcp_client_capabilities.py
new file mode 100644
index 0000000..e78ed8b
--- /dev/null
+++ b/tests/unit/test_mcp_client_capabilities.py
@@ -0,0 +1,63 @@
+"""Tests for MCPClient.check_required_tools capability checking."""
+
+from unittest.mock import AsyncMock, MagicMock, patch
+
+import pytest
+
+from ai_qa.exceptions import MCPConnectionError
+from ai_qa.mcp.client import MCPClient
+from ai_qa.mcp.tools import Tool
+
+
+def _make_tool(name: str) -> Tool:
+    return Tool(name=name, description="", parameters=[], returns="")
+
+
+@pytest.fixture
+def mock_mcp_client() -> MCPClient:
+    with patch("ai_qa.mcp.client.ConnectionManager"):
+        client = MCPClient(server_url="http://localhost:3000/sse")
+    client._connection = MagicMock()
+    client._connection.is_connected = True
+    return client
+
+
+class TestCheckRequiredTools:
+    async def test_empty_required_returns_empty(self, mock_mcp_client: MCPClient) -> None:
+        missing = await mock_mcp_client.check_required_tools([])
+        assert missing == []
+
+    async def test_all_present_returns_empty(self, mock_mcp_client: MCPClient) -> None:
+        mock_mcp_client.list_tools = AsyncMock(
+            return_value=[
+                _make_tool("tool_a"),
+                _make_tool("tool_b"),
+            ]
+        )
+        missing = await mock_mcp_client.check_required_tools(["tool_a", "tool_b"])
+        assert missing == []
+
+    async def test_missing_tool_returned(self, mock_mcp_client: MCPClient) -> None:
+        mock_mcp_client.list_tools = AsyncMock(
+            return_value=[_make_tool("tool_a")]
+        )
+        missing = await mock_mcp_client.check_required_tools(["tool_a", "tool_b"])
+        assert missing == ["tool_b"]
+
+    async def test_all_missing(self, mock_mcp_client: MCPClient) -> None:
+        mock_mcp_client.list_tools = AsyncMock(return_value=[])
+        missing = await mock_mcp_client.check_required_tools(["tool_a", "tool_b"])
+        assert set(missing) == {"tool_a", "tool_b"}
+
+    async def test_propagates_connection_error(self, mock_mcp_client: MCPClient) -> None:
+        mock_mcp_client.list_tools = AsyncMock(
+            side_effect=MCPConnectionError("cannot connect")
+        )
+        with pytest.raises(MCPConnectionError):
+            await mock_mcp_client.check_required_tools(["tool_a"])
+
+    async def test_does_not_bypass_cache(self, mock_mcp_client: MCPClient) -> None:
+        mock_mcp_client.list_tools = AsyncMock(return_value=[_make_tool("tool_a")])
+        await mock_mcp_client.check_required_tools(["tool_a"])
+        # list_tools is delegated with default args (uses_cache=True by default)
+        mock_mcp_client.list_tools.assert_called_once()

```
