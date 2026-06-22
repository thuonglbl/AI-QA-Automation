---
baseline_commit: "9b2de24"
---
# Story 7.5: Conversation History and Thread Resume

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a standard user,
I want a centralized Project Explorer in my sidebar,
So that I can browse all my projects, view their artifacts and threads categorically, and quickly resume or create new conversations within a specific project.

## Acceptance Criteria

1. **Given** an authenticated user is logged in
   **When** they view the sidebar
   **Then** they see a "Projects" list replacing the old conversation history
   **And** the list operates as an accordion, where only one project folder is open at a time to prevent UI clutter.
2. **Given** a user expands a project folder
   **When** the project data loads
   **Then** it displays categorized sub-folders (`Conversations`, `Requirements`, `Test Cases`, `Scripts`, `Reports`) containing the project's artifacts and threads
   **And** each sub-folder displays a maximum of 5 items per page with clear pagination controls.
3. **Given** the user selects a previous thread from the "Conversations" folder
   **When** the thread is reopened
   **Then** the backend returns the persisted messages, current step, status, and latest agent run summary
   **And** the frontend restores the conversation without creating a duplicate thread.
4. **Given** the user hovers over a project row
   **When** they click the `+` button
   **Then** a new conversation is immediately created and bound to that project, bypassing the standard project selection step.
5. **Given** another user belongs to the same project
   **When** that other user opens the Project Explorer
   **Then** they cannot see or continue the first user's private threads, even within the same shared project.

## Tasks / Subtasks

- [x] Task 1: Backend - Thread Service queries (AC: 1, 2)
  - [x] Implement query in `ThreadService` to list threads for `current_user.id`, including metadata (project_id, current_step, status, last activity).
  - [x] Implement query in `ThreadService` to get full thread details (messages, agent run summary, status) ensuring it belongs to `current_user.id`.
- [x] Task 2: Backend - API Endpoints (AC: 1, 2)
  - [x] Implement `GET /api/threads` route to list conversation history for the authenticated user.
  - [x] Implement `GET /api/threads/{thread_id}` route to retrieve thread state and messages for resuming. Ensure proper authorization checking so only the thread owner can access.
- [x] Task 3: Frontend - Conversation History UI (AC: 1, 3)
  - [x] Create a `ProjectSidebar` component replacing the simple Conversation History.
  - [x] Implement a collapsible accordion grouped by project.
  - [x] Implement categorized sub-folders (conversations, requirements, testcases, scripts, reports) fetched from `/api/projects/{id}/artifacts` and `/api/threads`.
  - [x] Implement pagination (5 items per page) within each folder, sorted by `created_at`.
  - [x] Add a quick `+` button to create a new conversation natively bound to the selected project.
- [x] Task 4: Frontend - Thread Resume (AC: 2)
  - [x] Update frontend to fetch full state via `GET /api/threads/{thread_id}` when a thread is selected.
  - [x] Restore conversation state (messages, current step, status, latest agent run) without creating a new duplicate thread.
- [x] Task 5: Testing and Validation (AC: 1, 2, 3)
  - [x] Write backend unit tests verifying that only the user's own threads are returned and accessible (enforce private threads per user).
  - [x] Write backend unit tests verifying another user in the same project cannot retrieve the first user's thread (AC 3).

## Dev Notes

- **Architecture Patterns and Constraints**:
  - API responses must use Pydantic models with snake_case keys. No secrets returned. Use `current_user` from the auth dependency.
  - Ensure strict data boundary enforcement on all thread operations (only thread creator can access).
  - Once a project is bound to a thread by Alice, it remains immutable.
- **Source Tree Components to Touch**:
  - `src/ai_qa/threads/service.py` (Domain service: queries for conversation history and thread retrieval)
  - `src/ai_qa/api/routes/threads.py` (FastAPI router for threads history)
  - `frontend/src/features/conversations/` (Conversation history UI and active-thread state restoration)
- **Testing Standards**:
  - Backend tests must enforce RBAC: ensure user B cannot view user A's threads, even if in the same project.

### Project Structure Notes

- Keep `ai_qa/threads/service.py` focused on business logic, keeping `api/routes/threads.py` thin and focused on HTTP transport.

### Previous Story Intelligence

From Story 7.4 (Thread-Scoped Messages and Agent Run Records):
- Ensure proper use of `thread_id` to get messages and latest agent runs.
- Messages are append-only.
- The `AgentRun` keeps `thread_id`, `status`, `summary`, `execution_metadata`. Restore latest agent run summary when resuming.

### Git Intelligence

Recent commits focus on 8-6 (Admin E2E test execution) and 7-4 (Thread-scoped messages). The models for threads and messages are in place, so 7.5 only requires querying and frontend integration.

### Latest Tech Information

- Python 3.14+, FastAPI, SQLAlchemy/Alembic, PostgreSQL
- React 18+, TypeScript, Vite, Shadcn/ui

### References

- [Epic 7: Secure Multi-User Workspace Foundation](file:///_bmad-output/planning-artifacts/epics.md#L238)
- [Architecture: Thread/project scoping](file:///_bmad-output/planning-artifacts/architecture.md#L67)
- [Architecture: Thread/message service](file:///_bmad-output/planning-artifacts/architecture.md#L395)

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro (High)

### Debug Log References

- Generated via bmad-create-story workflow.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created

### File List

- `_bmad-output/implementation-artifacts/7-5-conversation-history-and-thread-resume.md` (NEW)

### UI Redesign Notes (Added June 5th)

- Replaced the simple list of recent conversations with a full Project Explorer accordion sidebar.
- Only one project is open at a time; fetching artifacts (`requirements`, `testcases`, `scripts`, `reports`) on demand alongside `conversations`.
- Quick-create `+` button binds Alice directly to the selected project.
- Pagination is enforced inside sub-folders natively to limit noise (5 items per page).
