# Story 3.1: MCP Client Foundation

**Status:** ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a R&D engineer,
I want an MCP client using the official `mcp` Python SDK,
So that the pipeline can connect to the on-premises MCP server for Confluence access.

## Acceptance Criteria

**Given** the `src/ai_qa/mcp/` module is created
**When** the MCP client initializes with server URL from config
**Then** it connects to the MCP server and discovers available tools automatically
**And** connection failures raise `MCPError` with clear error message (NFR11)
**And** retry logic uses tenacity with max 3 attempts and exponential backoff (NFR12)
**And** all data stays on-premises — no external transmission (NFR5)
**And** SSO authentication is reused from existing browser session (FR1)

## Technical Requirements

### Core Functionality
- Implement MCP client using official `mcp` Python SDK (latest stable version)
- Support both stdio and HTTP transport modes
- Automatic tool discovery from MCP server
- Connection pooling for multiple MCP servers
- Graceful handling of connection failures with descriptive error messages

### Module Structure
```
src/ai_qa/mcp/
├── __init__.py           # Public exports
├── client.py             # MCPClient class
├── connection.py         # Connection management
├── errors.py             # MCPError hierarchy
├── tools.py              # Tool discovery and caching
└── config.py             # MCP-specific configuration
```

### Key Components

#### 1. MCPClient Class
```python
class MCPClient:
    """Client for MCP server communication."""
    
    def __init__(self, server_url: str, auth_token: str | None = None)
    async def connect() -> None
    async def disconnect() -> None
    async def list_tools() -> list[Tool]
    async def call_tool(name: str, params: dict) -> ToolResult
    async def discover_capabilities() -> ServerCapabilities
```

#### 2. Error Handling
- `MCPError` (base exception from `ai_qa.exceptions` hierarchy)
- `MCPConnectionError` - Connection failures
- `MCPAuthenticationError` - Auth failures
- `MCPToolError` - Tool execution failures

#### 3. Retry Configuration
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((MCPConnectionError, MCPTimeout))
)
async def connect_with_retry(...)
```

### Configuration

Pydantic Settings integration:
```python
class MCPSettings(BaseSettings):
    mcp_server_url: str = Field(..., description="MCP server endpoint")
    mcp_auth_token: str | None = Field(None, description="Optional auth token")
    mcp_timeout: int = Field(30, description="Connection timeout in seconds")
    mcp_max_retries: int = Field(3, description="Max retry attempts")
```

### Dependencies

Add to `pyproject.toml`:
```toml
dependencies = [
    "mcp>=1.0.0",  # Official MCP SDK
    "tenacity>=8.0.0",  # Retry logic
]
```

## Dev Notes

### Research Context

From technical research on skills.sh integration:

**MCP Protocol Basics:**
- Model Context Protocol announced by Anthropic Nov 2024
- 97M+ SDK downloads, enterprise adoption at Block, Bloomberg
- Universal standard: write once, use everywhere (Claude, ChatGPT, Cursor)

**Official MCP Servers:**
- `mcp-atlassian` (Python): Jira + Confluence Cloud/Server
- `playwright-mcp` (Microsoft): Browser automation
- Installation: `uvx mcp-atlassian` or npm package

**Security Patterns:**
- OAuth 2.0 + PKCE for production auth
- Static API tokens acceptable for on-premises development
- Token audience validation to prevent confused deputy attacks

**Integration Patterns:**
- Pattern 1: Direct MCP connection (chosen for MVP)
- Pattern 2: Unified gateway (future scaling)
- Pattern 3: Agent-specific bundles (security-focused)

### Implementation Guidelines

1. **Use official MCP SDK**: `pip install mcp` (Python SDK)
2. **Async-first design**: All operations async/await
3. **Type safety**: Full type hints, Pydantic models for all data
4. **Error hierarchy**: Extend from existing `ai_qa.exceptions` base
5. **Configuration**: Integrate with existing Pydantic Settings
6. **Testing**: pytest with async support, mock MCP server

### MCP SDK Resources

- GitHub: `github.com/modelcontextprotocol/python-sdk`
- Docs: `modelcontextprotocol.io/docs/concepts/architecture`
- PyPI: `pypi.org/project/mcp/`

### Related Stories

- Story 3.2: Confluence Reader Pipeline Stage (depends on this)
- Story 3.4: Output Writer Pipeline Stage (shared patterns)
- Story 9.1a: Jira MCP Integration (reuses this client)

### NFR Compliance

| NFR | Implementation |
|-----|---------------|
| NFR5 (On-premises) | No external API calls, local MCP server only |
| NFR11 (Graceful failure) | `MCPError` with descriptive messages |
| NFR12 (Retry logic) | tenacity with exponential backoff |
| NFR6 (No credential logging) | Secrets handled via Pydantic, never logged |

## Tasks

- [ ] Create `src/ai_qa/mcp/` module structure
- [ ] Implement `MCPError` exception hierarchy in `errors.py`
- [ ] Implement connection management in `connection.py`
- [ ] Implement `MCPClient` class in `client.py`
- [ ] Implement tool discovery and caching in `tools.py`
- [ ] Add MCP configuration to Pydantic Settings
- [ ] Add `mcp` SDK dependency to `pyproject.toml`
- [ ] Write unit tests with mocked MCP server
- [ ] Write integration test against local MCP server
- [ ] Update `__init__.py` with public exports
- [ ] Document usage in module docstrings
- [ ] Run linting (ruff) and type checking (mypy)
- [ ] Verify tests pass with `pytest`

## Completion Notes

### File List
- `[NEW] src/ai_qa/mcp/__init__.py`
- `[NEW] src/ai_qa/mcp/client.py`
- `[NEW] src/ai_qa/mcp/connection.py`
- `[NEW] src/ai_qa/mcp/errors.py`
- `[NEW] src/ai_qa/mcp/tools.py`
- `[NEW] src/ai_qa/mcp/config.py`
- `[NEW] tests/mcp/test_client.py`
- `[NEW] tests/mcp/test_connection.py`
- `[MODIFY] src/ai_qa/config/settings.py` (add MCP settings)
- `[MODIFY] pyproject.toml` (add MCP dependency)

### Definition of Done
- [ ] All acceptance criteria pass
- [ ] Unit tests achieve >80% coverage
- [ ] Integration test against MCP server passes
- [ ] Error handling verified with simulated failures
- [ ] Retry logic verified with flaky connection simulation
- [ ] Documentation complete with usage examples
- [ ] Code review passed (run `code-review` workflow)
- [ ] Linting and type checking pass

---

**Story ID:** 3.1
**Story Key:** 3-1-mcp-client-foundation
**Epic:** Epic 3 - Requirements Extraction from Confluence (Agent Bob)
**Created:** 2026-04-17
**Research Reference:** `technical-skills.sh-integration-research-2026-04-16.md`
