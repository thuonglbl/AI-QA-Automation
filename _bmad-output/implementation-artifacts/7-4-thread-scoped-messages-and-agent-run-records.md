---
baseline_commit: "9b2de24"
---
# Story 7.4: Thread-Scoped Messages and Agent Run Records

Status: in-progress

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a project user,
I want conversation messages and agent executions saved under my thread,
So that the workflow state can be audited and resumed accurately.

## Acceptance Criteria

1. **Given** a conversation thread exists
   **When** the user or an agent sends a message
   **Then** the message is persisted as append-only data linked to the thread
   **And** messages cannot be reassigned to another thread
2. **Given** an agent workflow execution starts for a thread
   **When** the backend creates an agent run
   **Then** the agent run stores `thread_id`, status, timestamps, summary, and non-secret execution metadata
   **And** user and project scope are derived from the thread rather than duplicated as mutable runtime authority
3. **Given** an agent run updates workflow progress
   **When** the update is persisted
   **Then** only the referenced thread's `current_step` and `status` are updated
   **And** the agent run cannot be reassigned to another thread

## Tasks/Subtasks

- [x] Task 1: Create ThreadMessage and AgentRun models (`src/ai_qa/threads/models.py`)
  - [x] Add `ThreadMessage` SQLAlchemy model (append-only, immutable `thread_id`).
  - [x] Add `AgentRun` SQLAlchemy model (stores `thread_id`, `status`, `summary`, `execution_metadata`).
  - [x] Generate Alembic migration for the new tables.
- [x] Task 2: Create schemas for Messages and Agent Runs (`src/ai_qa/threads/schemas.py`)
  - [x] Add `ThreadMessageCreate` and `ThreadMessageResponse` schemas.
  - [x] Add `AgentRunCreate`, `AgentRunUpdate`, and `AgentRunResponse` schemas.
- [x] Task 3: Update Thread Service for Messages (`src/ai_qa/threads/service.py`)
  - [x] Add `add_message` method to `ThreadService` to persist append-only messages.
  - [x] Add `get_thread_messages` method to retrieve messages for a thread.
- [x] Task 4: Update Thread Service for Agent Runs (`src/ai_qa/threads/service.py`)
  - [x] Add `create_agent_run` method ensuring `thread_id` is immutable.
  - [x] Add `update_agent_run` method that also updates the related thread's `current_step` and `status`.
- [x] Task 5: Expose API endpoints (`src/ai_qa/api/routes/threads.py`)
  - [x] Add endpoint to retrieve thread messages.
  - [x] Add endpoint to create thread messages (by user/agent).
  - [x] Add endpoints for retrieving/updating Agent Runs.
- [x] Task 6: Tests and Validation
  - [x] Write tests for thread messages (append-only, specific to thread).
  - [x] Write tests for agent runs (creation, update, thread status synchronization).
  - [x] Run full test suite to ensure no regressions.

## Dev Notes

- **Architecture Patterns and Constraints**:
  - Thread creation must immutably bind to `project_id`. Once bound, it cannot change.
  - Enforce RBAC/authorization on thread creation. `thread_id` becomes the scope for agent runs.
  - Messages are append-only.
  - Agent runs are scoped only by `thread_id`; user and project scope are derived from the referenced thread.
  - Updating agent run updates `conversation_threads.current_step` and `conversation_threads.status`.
- **Source Tree Components to Touch**:
  - `src/ai_qa/threads/` (Domain service: models and service for threads, messages, and agent runs)
  - `src/ai_qa/api/routes/threads.py` (FastAPI router for threads)
- **Testing Standards**:
  - Write tests for thread messages and agent runs.
  - Verify that agent runs correctly update the thread's step and status.

### Previous Story Intelligence

From Story 7.3 (New Conversation Thread Creation with Alice Project Selection):
- **Architecture Patterns**: API responses must use Pydantic models with snake_case keys. No secrets returned. Use `current_user` from the auth dependency.
- **Project Structure Notes**: Keep `ai_qa/threads/service.py` focused on business logic, keeping `api/routes/threads.py` thin and focused on HTTP transport.

### Git Intelligence
Recent commits show work on story 8-6 (Admin E2E test execution).

### Latest Tech Information
- Python 3.12+
- FastAPI, SQLAlchemy/Alembic, PostgreSQL

### References

- [Epic 7: Secure Multi-User Workspace Foundation](file:///_bmad-output/planning-artifacts/epics.md#L238)
- [Architecture: Thread/project scoping](file:///_bmad-output/planning-artifacts/architecture.md#L67)

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro (High)

### Debug Log References

- Created by bmad-create-story workflow.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created

### File List

- `_bmad-output/implementation-artifacts/7-4-thread-scoped-messages-and-agent-run-records.md` (NEW)
