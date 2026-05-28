# Story 12.13: Fix MCP extraction failure and implement proactive session cleanup

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want the MCP extraction to use correct parameters, reuse connections, and proactively cleanup sessions,
So that Confluence extraction is reliable and complies with IT policy on session lifecycle management.

## Acceptance Criteria

1. Given Bob attempts to extract children via MCP, when `confluence_get_page` or `confluence_search` is called, then the correct parameter format (`page_id` vs `pageId` based on MCP server spec) is used.
2. Given Bob confirms a parent page and moves to descendant extraction, then the same MCP connection session is reused rather than opening a new one.
3. Given an MCP session is no longer needed, then the application actively signals termination/cleanup to the MCP server (via explicit API or graceful transport close) so sessions do not accumulate offline.

## Tasks / Subtasks

- [ ] Fix parameter naming inconsistencies in `ConfluenceReader` (`pageId` vs `page_id`).
- [ ] Refactor `BobAgent` to reuse the MCP connection across the parent confirmation and child extraction phases instead of instantiating new clients.
- [ ] Ensure `MCPConnection` / `ClientSession` properly signals termination to the MCP server (e.g., closing the transport gracefully or calling a delete endpoint if exposed).

## Dev Notes

- Bob agent extraction failed with "GET stream disconnected".
- Need to prevent leaving offline sessions behind.
- Ensure parameters match the exact schema of the MCP server tool (`confluence_get_page` / `confluence_search`).

### Project Structure Notes

- `src/ai_qa/mcp/confluence.py` and Bob agent implementation in `src/ai_qa/agents/`.

### References

- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-05-29.md#Story 12.13]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 12.13: Fix MCP extraction failure and implement proactive session cleanup]

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro (High)

### Debug Log References

### Completion Notes List

### File List
