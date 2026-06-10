---
baseline_commit: "5eace1c755396aa98ff3b07922de58a3aeb85a21"
---
# Story 7.3: New Conversation Thread Creation with Alice Project Selection

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a standard user,
I want Alice to select and bind a project at the start of a new thread,
So that every workflow run is scoped to the correct project.

## Acceptance Criteria

1. **Given** an authenticated standard user starts a new conversation
   **When** the thread is created
   **Then** the thread is private to that user
   **And** the thread remains unbound until Alice resolves project selection
2. **Given** the user has exactly one accessible project
   **When** Alice starts project selection
   **Then** Alice automatically binds that project to the thread
   **And** the project cannot be changed afterward
3. **Given** the user has multiple accessible projects
   **When** Alice asks the user to select one project
   **Then** the selected project is bound to the thread
   **And** the project cannot be changed afterward
4. **Given** the user has zero accessible projects
   **When** Alice starts project selection
   **Then** Alice shows the no-access message
   **And** no provider setup or pipeline action is shown

## Tasks/Subtasks

- [x] Task 1: Update Thread domain models and service (`src/ai_qa/threads/`)
  - [x] Add `project_id` field to thread schema, allowing it to be initially unbound but immutable once set.
  - [x] Update `ThreadService.create_thread` to enforce RBAC (users can only create threads for themselves).
  - [x] Add `ThreadService.bind_project(thread_id, project_id)` method which raises an error if already bound.
- [x] Task 2: Update API router (`src/ai_qa/api/routes/threads.py`)
  - [x] Modify thread creation endpoint to use `current_user` from auth dependency.
  - [x] Add API endpoint for binding a project to a thread (if needed by Alice agent).
- [x] Task 3: Update Alice agent flow logic (`src/ai_qa/agents/alice/`)
  - [x] Fetch user's accessible projects when processing a new, unbound thread.
  - [x] If 0 projects: emit "no access" message and stop.
  - [x] If 1 project: automatically call bind_project API/service, then proceed.
  - [x] If >1 projects: ask user to select a project.
  - [x] Handle user's project selection response and bind it.
- [x] Task 4: Update Frontend components (`frontend/src/features/conversations/`)
  - [x] Handle Alice's project selection request in the chat UI.
  - [x] Add UI to display the no-access message.
- [x] Task 5: Tests and Validation
  - [x] Write unit tests for `ThreadService` thread creation and project binding.
  - [x] Write tests for Alice's 0, 1, and >1 project scenarios.
  - [x] Ensure all tests pass.

### Review Findings

- [x] [Review][Patch] Allow PipelineRun to have project_id as NULL to support unbound threads (Resolved from Decision 1B)
- [x] [Review][Patch] Update database schema and API to scope conversation history by thread_id instead of project_id (Resolved from Decision 2A)
- [x] [Review][Patch] Thread ID stored in localStorage is not cleared on logout/user switch [frontend/src/App.tsx:162-174]
- [x] [Review][Patch] Race conditions in thread creation during render/mount cycle [frontend/src/App.tsx:162-174]
- [x] [Review][Patch] WebSocket attempts connection with stored threadId when user is not authenticated [frontend/src/App.tsx:178-181]
- [x] [Review][Patch] hasSentStartRef reference is never reset, preventing start message on new threads [frontend/src/App.tsx:189-201]
- [x] [Review][Patch] Auto-bound project by Alice does not update frontend state via WebSocket metadata [src/ai_qa/agents/alice.py:450-453]
- [x] [Review][Patch] Pointless dynamic import of createThread inside useEffect [frontend/src/App.tsx:167]
- [x] [Review][Patch] Lack of user-facing error handling/retry for thread creation [frontend/src/App.tsx:162-174]
- [x] [Review][Patch] Missing project membership check in thread binding endpoint and service [src/ai_qa/threads/service.py:1105]
- [x] [Review][Patch] Authentication bypass and architectural coupling in Alice Agent via dummy UserSession [src/ai_qa/agents/alice.py:407-411]
- [x] [Review][Patch] Malformed UUID in project_id input can raise unhandled ValueError in Alice agent [src/ai_qa/agents/alice.py:401]
- [x] [Review][Patch] Pipeline context builder silently ignores missing threads [src/ai_qa/api/routes.py:548-556]
- [x] [Review][Patch] WebSocket broadcast leaks private agent updates to other users [src/ai_qa/api/websocket.py:345-365]
- [x] [Review][Patch] IntegrityError on invalid foreign key project_id causes 500 error instead of 400 [src/ai_qa/api/threads.py:756-777]
- [x] [Review][Patch] UUID parsing raises HTTPException inside WebSocket loop before connection cleanup is ensured [src/ai_qa/api/websocket.py:91-96]
- [x] [Review][Patch] Inconsistent HTTP Status Codes for thread errors and test assertion validation [src/ai_qa/api/threads.py:756-777]

## Dev Notes

- **Architecture Patterns and Constraints**:
  - Thread creation must immutably bind to `project_id`. Once bound, it cannot change.
  - Enforce RBAC/authorization on thread creation. `thread_id` becomes the scope for agent runs.
  - Project selection must handle 0, 1, and many accessible projects for the standard user.
  - Alice is the first agent involved in the pipeline, operating immediately after thread creation.
- **Source Tree Components to Touch**:
  - `src/ai_qa/threads/` (Domain service: models and service for threads)
  - `src/ai_qa/api/routes/threads.py` (FastAPI router for threads)
  - `src/ai_qa/agents/alice/` (Alice agent flow logic for project selection)
  - `frontend/src/features/conversations/` (React components for New Conversation logic)
- **Testing Standards**:
  - Write tests for thread creation and project binding in `tests/`.
  - Verify that a standard user can only create threads for themselves.
  - Verify Alice's zero, single, and multiple project handling logic.

### Previous Story Intelligence

From Story 7.2 (Project Membership Access):
- **Architecture Patterns**: API responses must use Pydantic models with snake_case keys. No secrets returned. Use `current_user` from the auth dependency.
- **UI**: Use Professional Calm color system, display empty states gracefully, and adhere to WCAG 2.1 AA standards.
- **Project Structure Notes**: Keep `ai_qa/threads/service.py` focused on business logic, keeping `api/routes/threads.py` thin and focused on HTTP transport.

### References

- [Epic 7: Secure Multi-User Workspace Foundation](file:///_bmad-output/planning-artifacts/epics.md#L238)
- [Story 7.3: New Conversation Thread Creation with Alice Project Selection](file:///_bmad-output/planning-artifacts/epics.md#L289)
- [Architecture: Thread/project scoping](file:///_bmad-output/planning-artifacts/architecture.md#L67)

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro (High)

### Debug Log References

- Created by bmad-create-story workflow.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created

### File List

- `_bmad-output/implementation-artifacts/7-3-new-conversation-thread-creation-with-alice-project-selection.md` (NEW)
