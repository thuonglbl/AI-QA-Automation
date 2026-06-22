---
baseline_commit: 9d878c5
---

# Story 11.1: MCP Client Foundation for Confluence and Jira

Status: done

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

- [x] `JiraIssue` Pydantic model added to `src/ai_qa/pipelines/models.py` with all required fields.
- [x] `JiraReader` class created at `src/ai_qa/pipelines/jira_reader.py` with `JIRA_TOOLS`, `_parse_issue_ref()`, `read_issue()`, and `check_tool_availability()`.
- [x] `MCPClient.check_required_tools()` added; `ConfluenceReader.check_tool_availability()` added.
- [x] Unit tests pass: `tests/pipelines/test_jira_reader.py` and `tests/unit/test_mcp_client_capabilities.py`.
- [x] `uv run ruff check .` and `uv run mypy src` — clean.
- [x] `uv run alembic upgrade head` is a no-op (confirmed no schema changes).

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

## Code Review Findings

### 1. Missing Capability Check Invocation (Decision Needed)
- **Source**: Acceptance Auditor
- **Issue**: The spec requires `check_tool_availability()` to be used on connect, but the methods are implemented without being invoked anywhere in `MCPClient.connect()` or `BobAgent` initialization flow. Where should this check be hooked up?

### 2. Uncaught MCP Errors in `read_issue()` (Patch)
- **Source**: Acceptance Auditor & Edge Case Hunter
- **Issue**: `read_issue()` only catches `MCPToolError`, allowing `MCPConnectionError` and `MCPTimeoutError` to crash the pipeline instead of gracefully returning a failed `StageResult` like `ConfluenceReader` does.

### 3. Mismatched Constructor Shape & Encapsulation Violation (Patch)
- **Source**: Acceptance Auditor & Blind Hunter
- **Issue**: `JiraReader.__init__` takes a `settings` parameter instead of `max_concurrent_requests` (violating "same constructor shape as ConfluenceReader" constraint), and directly accesses `mcp_client._settings` to find `mcp_tool_prefix`.

### 4. Flawed URL Parsing for scheme-less URLs (Patch)
- **Source**: Blind Hunter
- **Issue**: `_validate_confluence_url` and `_validate_jira_ref` use `urlparse(url).netloc` which evaluates to an empty string if a user inputs a scheme-less URL (e.g., `jira.company.com/browse/PROJ-1`), causing legitimate inputs to be falsely rejected.

### 5. Brittle Regex Case Sensitivity (Patch)
- **Source**: Blind Hunter
- **Issue**: The `_ISSUE_KEY_RE` regex `[A-Z][A-Z0-9_]+-\d+` strictly enforces uppercase, which fails if a user pastes a lowercase or mixed-case string (e.g., `proj-123`).

### 6. Hardcoded Garbage Tool Arguments (Patch)
- **Source**: Blind Hunter
- **Issue**: The `call_tool` method passes literal `"..."` strings for `userPrompt` and `llmReasoning`, which could break tools expecting meaningful data.

### 7. Masking Real Exceptions (Patch)
- **Source**: Blind Hunter
- **Issue**: The exception handler for `MCPToolError` in `read_issue()` hardcodes `"Jira tool not available..."` rather than exposing the actual exception message, masking the root cause of the error.

### 8. Worthless Test Mocking in `conftest.py` (Patch)
- **Source**: Blind Hunter
- **Issue**: The DB mock for SecretStatus sets `status="configured"` instead of `configured=True`, making `get_secret_status(db).configured` accidentally truthy (it returns a `MagicMock`) rather than correctly simulating a boolean.

### 9. Bypassing Pydantic Defaults (Patch)
- **Source**: Blind Hunter
- **Issue**: `_get_nested_name` forces missing keys to return an empty string `""` instead of `None`, which bypasses the `str | None` type hints and pollutes the JiraIssue model.

### 10. Overly Strict Type Checking on Labels (Patch)
- **Source**: Blind Hunter
- **Issue**: `isinstance(labels_val, list)` silently drops data and returns an empty list if the API happens to return labels as a tuple or set.

### 11. Invalid URL Fallback (Patch)
- **Source**: Blind Hunter
- **Issue**: If `_jira_base_url` is missing, `url` defaults to `""`. Pydantic expects a valid direct URL, which may break frontend links.

### 12. Input Data Type Safety (Patch)
- **Source**: Edge Case Hunter
- **Issue**: `confluence_url = (input_data.get("confluence_url") or "").strip()` could throw `AttributeError` if `input_data` contains a truthy non-string value (like an integer or dictionary).

### 13. Jira Ref Validation Allows Keyless URLs (Patch)
- **Source**: Edge Case Hunter
- **Issue**: `_validate_jira_ref` passes validation if `jira_ref` is a valid base URL even without an issue key, causing the downstream pipeline extraction to fail ungracefully.
