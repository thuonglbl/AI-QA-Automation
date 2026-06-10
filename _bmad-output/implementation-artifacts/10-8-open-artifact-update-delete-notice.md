---
story_key: 10-8-open-artifact-update-delete-notice
epic: 10
status: done
baseline_commit: ca2a203e7cfb44fa2972a774ed353333d3131755
---

# Story 10.8: Open Artifact Update/Delete Notice

## Story

As a project member viewing an artifact,
I want to see a non-disruptive notice when the artifact is updated or deleted by someone else,
So that I know the content has changed without losing my chat context.

## Acceptance Criteria

**Given** a user is viewing an artifact in the preview panel
**When** the artifact is updated externally (another user or process)
**Then** a non-disruptive notice appears indicating a newer version is available
**And** the chat messages, input, current step, and scroll position remain unchanged

**Given** a user is viewing an artifact in the preview panel
**When** the artifact is deleted externally
**Then** a non-disruptive notice appears indicating the artifact was deleted
**And** the chat messages, input, current step, and scroll position remain unchanged

**Given** a notice is displayed about an artifact change
**When** the user ignores the notice (does not interact with it)
**Then** all chat state remains preserved

## Tasks

- [ ] **Task 1: Create ArtifactNotice component**
  - [ ] Create `frontend/src/components/artifacts/ArtifactNotice.tsx`
  - [ ] Support `update` and `delete` notice types
  - [ ] Auto-dismiss after timeout (optional)
  - [ ] Non-disruptive styling (toast/banner at top of artifact panel)

- [ ] **Task 2: Wire artifact change events to notice**
  - [ ] Track currently viewed artifact ID in App.tsx
  - [ ] Listen for `artifact_change` events matching viewed artifact
  - [ ] Show notice when viewed artifact is updated or deleted
  - [ ] Preserve all chat state when notice appears

- [ ] **Task 3: Verify E2E tests pass**
  - [ ] Run `story-10-8-artifact-notice.spec.ts`
  - [ ] Verify notice appears on artifact update
  - [ ] Verify notice appears on artifact deletion
  - [ ] Verify chat state preserved when notice ignored

## Dev Notes

### Architecture

- Backend already broadcasts `artifact_change` events via WebSocket (Story 10.7)
- Frontend `useWebSocket` hook already handles raw events via `onRawEvent` callback
- Currently only triggers sidebar refresh; need to also show notice for viewed artifact

### Key Files

- `frontend/src/App.tsx` — Main app with WebSocket, artifact refresh trigger
- `frontend/src/hooks/useWebSocket.ts` — WebSocket hook with `onRawEvent`
- `frontend/src/components/conversations/ProjectSidebar.tsx` — Artifact tree display
- `frontend/e2e/story-10-8-artifact-notice.spec.ts` — E2E tests

### E2E Test Expectations

- Update notice text: matches `/newer version|updated|reload|stale/i`
- Delete notice text: matches `/deleted|removed|no longer available|close/i`
- Tests use try/catch — notice is optional if sidebar refresh works
- Chat state must remain unchanged after notice

### Current Gaps

- No ArtifactNotice component exists
- App.tsx only triggers sidebar refresh, no notice for viewed artifact
- No tracking of currently viewed artifact ID

## File List

- `frontend/src/components/artifacts/ArtifactNotice.tsx` — New: notice component
- `frontend/src/App.tsx` — Modified: track viewed artifact, show notice
- `frontend/src/components/conversations/ArtifactPreview.tsx` — Modified: report viewed artifact ID

## Change Log

- 2026-06-09: Initial story creation
