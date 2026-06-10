---
story_key: 10-7-realtime-artifact-refresh-ux
epic: 10
status: done
baseline_commit: ca2a203e7cfb44fa2972a774ed353333d3131755
---

# Story 10.7: Realtime Artifact Refresh UX

## Story

As a project member,
I want the visible artifact tree to refresh when relevant artifact events occur,
So that I can see updates without losing my current chat context.

## Acceptance Criteria

**Given** a connected user is assigned to the changed project
**When** an artifact change event is broadcast
**Then** the user receives the event even if the changed project is not attached to the currently active thread

**Given** the changed project is currently displayed in the Project / Artifacts section
**When** the frontend receives the event
**Then** it refetches the visible artifact tree
**And** it does not reset chat messages, current input, current step, or scroll position

**Given** the changed project is not currently displayed
**When** the frontend receives the event
**Then** the active chat state remains unchanged
**And** the UI may update non-disruptive project artifact indicators only

## Tasks

- [ ] **Task 1: Add artifact DELETE endpoint with storage cleanup**
  - [ ] Add `delete_artifact()` method to `ArtifactService`
  - [ ] Add `DELETE /projects/{project_id}/artifacts/{artifact_id}` endpoint
  - [ ] Delete all version storage objects before DB delete
  - [ ] Add unit tests for artifact deletion

- [ ] **Task 2: Add S3 prefix-based delete for project cleanup**
  - [ ] Add `delete_prefix(prefix)` method to `S3ArtifactStorage`
  - [ ] Add `delete_prefix(prefix)` to `ArtifactStorage` protocol
  - [ ] Implement in `LocalArtifactStorage` as well

- [ ] **Task 3: Add S3 cleanup to admin project delete**
  - [ ] Modify `admin.py:delete_project()` to clean up S3 storage before DB delete
  - [ ] List and delete all objects under `projects/{project_id}/` prefix
  - [ ] Add unit tests for project deletion with storage cleanup

- [ ] **Task 4: Add artifact change WebSocket broadcast**
  - [ ] Create `broadcast_artifact_change()` function in websocket module
  - [ ] Define artifact change event payload (project_id, artifact_id, change_type, timestamp)
  - [ ] Call broadcast after `create_artifact`, `create_artifact_version`, and delete operations
  - [ ] Add unit tests for artifact change broadcast

- [ ] **Task 5: Frontend artifact tree refresh on WebSocket event**
  - [ ] Listen for `artifact_change` events in WebSocket message handler
  - [ ] Trigger artifact list refetch when event matches displayed project
  - [ ] Preserve chat state, input, scroll position during refresh
  - [ ] Handle non-active project events without disrupting chat

- [ ] **Task 6: E2E test cleanup for storage**
  - [ ] Verify project delete cleans S3 storage
  - [ ] Verify artifact delete cleans S3 storage
  - [ ] Update E2E afterEach to rely on backend cascade cleanup

## Dev Notes

### Architecture

- Backend: FastAPI, SQLAlchemy, S3/SeaweedFS artifact storage
- Frontend: React 18, TypeScript, Vite, WebSocket via `useWebSocket` hook
- Artifact storage: `S3ArtifactStorage` with `projects/{project_id}/` prefix structure
- WebSocket: `active_connections` dict maps connection_id → (ws, user, project_id, thread_id)

### Key Files

- `src/ai_qa/artifacts/service.py` — ArtifactService (save_artifact, create_version, list_artifacts)
- `src/ai_qa/artifacts/storage.py` — ArtifactStorage protocol, S3ArtifactStorage, LocalArtifactStorage
- `src/ai_qa/api/artifacts.py` — REST endpoints for artifacts
- `src/ai_qa/api/admin.py` — Admin project delete (no S3 cleanup currently)
- `src/ai_qa/api/websocket.py` — WebSocket hub with broadcast_message()
- `src/ai_qa/models.py` — AgentMessage model
- `frontend/src/hooks/useWebSocket.ts` — Frontend WebSocket hook
- `frontend/src/components/conversations/ProjectSidebar.tsx` — Artifact tree display
- `frontend/src/App.tsx` — Main app with WebSocket integration

### S3 Object Key Structure

- Requirements: `projects/{project_id}/requirements/{safe_name}`
- Raw HTML: `projects/{project_id}/requirements/mcp/confluence/{safe_name}`
- Versioned artifacts: `projects/{project_id}/artifacts/{artifact_id}/v{version}/{safe_name}`

### Current Gaps

- No DELETE endpoint for artifacts (only storage.delete for failed writes)
- No delete_artifact() in ArtifactService
- Project delete in admin.py only deletes DB records, no S3 cleanup
- No artifact change event type in WebSocket (only AgentMessage)
- Frontend sidebar fetches artifacts once on project open, never re-fetches

## File List

- `src/ai_qa/artifacts/service.py` — Modified: add delete_artifact()
- `src/ai_qa/artifacts/storage.py` — Modified: add delete_prefix() to protocol + implementations
- `src/ai_qa/api/artifacts.py` — Modified: add DELETE endpoint
- `src/ai_qa/api/admin.py` — Modified: add S3 cleanup to delete_project
- `src/ai_qa/api/websocket.py` — Modified: add broadcast_artifact_change()
- `src/ai_qa/models.py` — Modified: add ArtifactChangeEvent model
- `frontend/src/hooks/useWebSocket.ts` — Modified: handle artifact_change events
- `frontend/src/components/conversations/ProjectSidebar.tsx` — Modified: add refresh callback
- `frontend/src/App.tsx` — Modified: wire artifact refresh
- `tests/test_artifacts/test_service.py` — Modified: add delete tests
- `tests/api/test_artifacts_api.py` — Modified: add DELETE endpoint tests
- `tests/api/test_admin_api.py` — Modified: add project delete S3 cleanup tests

## Change Log

- 2026-06-09: Initial story creation and implementation
