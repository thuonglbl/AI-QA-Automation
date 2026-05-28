# Sprint Change Proposal: Fix MCP Extraction & Frontend Auth
**Date**: 2026-05-29
**Trigger**: Bob agent extraction failed with "GET stream disconnected" and 401 Unauthorized errors in the frontend during user testing. Also, IT policy requires proactive cleanup of MCP sessions to avoid accumulating offline sessions.

## Executive Summary
During testing of Bob's requirement extraction (Epic 3), the application encountered two distinct bugs:
1. **MCP Stream Disconnect**: Fetching child pages fails due to connection issues (potentially creating multiple sessions) and parameter inconsistency (`page_id` vs `pageId`). IT also noted that the app leaves offline sessions behind, requiring proactive cleanup.
2. **Frontend Authentication**: `GET /api/projects/...` requests return 401 Unauthorized, indicating that the frontend API client is not properly attaching auth tokens for project-scoped calls, which is a regression from recent Epic 12 work.

This proposal introduces two new bugfix stories to Epic 12 to address these issues and ensure the foundation is stable before proceeding to Epic 6 (Test Execution).

## Impact Analysis
- **Epic Impact**: Epic 12 (Platform Foundation) will receive two new bugfix stories. Epic 6 (Jack) remains blocked until extraction is functional.
- **Architectural Impact**: MCP client connections need to be reused across phases in the same agent step, and we must implement proper connection termination/cleanup to comply with IT's session management policy.
- **UX Impact**: None. The error handling UX remains the same, but the extraction process will succeed.

## Proposed Changes

### Epic 12: Platform Foundation (Status: In-Progress)

- **[NEW] Story 12.12: Fix frontend 401 Unauthorized API calls**
  - **Details**: Investigate and fix the frontend API client configuration so that it correctly includes the authentication token (and project context if needed) for all project-scoped API endpoints.

- **[NEW] Story 12.13: Fix MCP extraction failure and implement proactive session cleanup**
  - **Details**: 
    - Fix parameter naming inconsistencies in `ConfluenceReader` (`pageId` vs `page_id`).
    - Reuse the MCP connection in `BobAgent` across the parent confirmation and child extraction phases instead of instantiating new clients.
    - Ensure `MCPConnection` / `ClientSession` properly signals termination to the MCP server (e.g., closing the transport gracefully or calling a delete endpoint if exposed) so that sessions do not accumulate in an "Offline" state.

## Next Steps
1. User approves this proposal.
2. We update the Epic definitions and `sprint-status.yaml` (automatically via the workflow).
3. We implement the bugfix stories.
