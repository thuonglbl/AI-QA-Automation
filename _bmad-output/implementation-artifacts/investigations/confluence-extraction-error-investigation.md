# Investigation: Confluence Extraction Error via MCP

## Hand-off Brief

1. **What happened.** The application fails to extract Confluence pages and their children via MCP, with backend logs indicating `GET stream disconnected, reconnecting in 1000ms...` and the agent state changing to `error`.
2. **Where the case stands.** Initializing the case. Evidence suggests a disconnect between the backend MCP client and the MCP server during the extraction process.
3. **What's needed next.** Map the evidence perimeter to locate the exact code handling the `prefix_confluence_get_page` / `prefix_confluence_search` tool calls or MCP streaming connections.

## Case Info

| Field            | Value                                                                      |
| ---------------- | -------------------------------------------------------------------------- |
| Ticket           | N/A                                                       |
| Date opened      | 2026-05-29                                                                     |
| Status           | Active                                                                     |
| System           | Windows 10, ai-qa-automation project, Agent Bob                                |
| Evidence sources | User provided screenshots: Frontend chat & console, Backend terminal logs, MCP Session & Audit logs |

## Problem Statement

Connect MCP OK rồi, nhưng không thể extract nội dung confluence được. Mình có attach thêm log backend, session và log trên MCP.
Expect: trích xuất được page mà user confirm và toàn bộ page con của page đó.

## Evidence Inventory

| Source   | Status                          | Notes     |
| -------- | ------------------------------- | --------- |
| Frontend Screenshot | Available | Shows error "All pages failed to extract or convert" and "message channel closed" |
| Backend Terminal Logs | Available | Shows "GET stream disconnected" for mcp.client.streamable_http |
| MCP Session UI | Available | Session shows as Offline |
| MCP Audit Logs | Available | Shows tool calls for `prefix_confluence_get_page` and `prefix_confluence_search` |

## Investigation Backlog

| # | Path to Explore | Priority              | Status                                | Notes     |
| - | --------------- | --------------------- | ------------------------------------- | --------- |
| 1 | Locate MCP client code | High | Open | Need to see how `streamable_http` is implemented and why it disconnects |
| 2 | Locate Bob's agent code | High | Open | Find where Confluence extraction is initiated |

## Timeline of Events

| Time        | Event               | Source                | Confidence            |
| ----------- | ------------------- | --------------------- | --------------------- |

## Confirmed Findings

### Finding 1: MCP Stream Disconnects

**Evidence:** Backend terminal screenshot

**Detail:** The log shows `[mcp.client.streamable_http] GET stream disconnected, reconnecting in 1000ms...` right after receiving a session ID and negotiating protocol version. Shortly after, Agent Bob transitions from `processing -> error`.

## Deduced Conclusions

## Hypothesized Paths

### Hypothesis 1: Streamable HTTP Client Timeout or Network Issue

**Status:** Open

**Theory:** The MCP client implementation (`mcp.client.streamable_http`) drops the connection before the Confluence extraction can complete, possibly due to a timeout or an unhandled exception during stream processing.

**Supporting indicators:** Log says "GET stream disconnected" while processing a request.

**Would confirm:** Logs or exceptions from the stream reading loop.

**Would refute:** The server explicitly terminating the connection because of an invalid payload.

**Resolution:** 

## Missing Evidence

| Gap              | Impact                               | How to Obtain   |
| ---------------- | ------------------------------------ | --------------- |
| Code implementation | Needed to trace the error origin | Use file search to locate `streamable_http` and Bob's agent code |

## Source Code Trace

| Element       | Detail                                      |
| ------------- | ------------------------------------------- |
| Error origin  |  |
| Trigger       |  |
| Condition     |  |
| Related files |  |

## Conclusion

**Confidence:** Low

Initial investigation phase. The failure occurs because the MCP client stream disconnects.

## Recommended Next Steps

### Fix direction

### Diagnostic

Scan the codebase to find where `mcp.client.streamable_http` is used and where Agent Bob (`ai_qa.agents.bob` or similar) is implemented.

## Reproduction Plan

## Side Findings

- Unchecked runtime.lastError in frontend console might be unrelated (often a browser extension issue), but worth noting.

## Follow-up: 2026-05-29

### New Evidence

### Additional Findings

### Updated Hypotheses

### Backlog Changes

### Updated Conclusion
