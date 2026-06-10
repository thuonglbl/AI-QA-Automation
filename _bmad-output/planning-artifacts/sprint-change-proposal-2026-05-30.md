# Sprint Change Proposal: Collaborative Project Threads, Shared Artifacts, and Secure Secrets

Date: 2026-05-30  
Project: ai qa automation  
Workflow: BMad Correct Course  
Mode: Incremental  
Status: Approved

## 1. Issue Summary

The current product direction and implementation model assume that each project has a single agent workflow conversation state. This is no longer sufficient for the desired collaborative workflow.

The required change is:

- A user can work on multiple projects over time.
- Each conversation thread is bound to exactly one project after Alice asks the user to select a project at thread start.
- A project can have one or more conversation threads.
- Multiple users on the same project can view and continue work using shared generated artifacts stored in MinIO.
- Generated artifacts are project-scoped, not user-private.
- API keys and MCP keys must not be stored in plaintext user settings.
- The UI needs an Antigravity-inspired collaborative workspace with New Conversation, Conversation History, a collapsible sidebar, and a singular Project / Artifacts area for the active thread's bound project.

The current design creates the following blockers:

1. `current_step`, `status`, and `conversation_data` are stored on the project, so one project can effectively have only one active lifecycle state.
2. Other users on the same project cannot safely reuse or continue work because the project row contains a singleton conversation state.
3. There is no thread/message model; conversation data is stored as JSON that is hard to read, query, and process.
4. The UI does not support creating a new thread, reopening old threads, or browsing already generated MinIO artifacts for the active project.
5. `User.settings` stores keys in plaintext JSON, and the UI does not provide safe key rotation.
6. `ai_provider_config` duplicates values that may belong in environment configuration or secret storage.
7. `ai_agents_config` stores runtime parameters such as temperature without clear rationale.
8. Artifact views need realtime reload when another user changes artifacts in the same project.

## 2. Impact Analysis

### Scope Classification

This is a major product architecture correction within Epic 12. It should be handled as a backlog and architecture update before continuing deeper implementation of the multi-user workflow.

### Affected Planning Artifacts

- PRD: functional requirements and security NFRs need updates for thread persistence, shared artifacts, and secret storage.
- Epics: Epic 12 needs expanded stories for conversation threads, messages, secure secret storage, sidebar UX, and project artifact sharing.
- Architecture: data model, API contracts, WebSocket scoping, storage structure, and secret handling need updates.
- UX specification: main workspace layout and sidebar behavior need updates.

### Affected Runtime Areas

- Backend database schema and migrations.
- Conversation persistence APIs.
- WebSocket connection model and event payloads.
- Agent orchestration, especially Alice project selection and downstream thread-bound execution.
- Artifact service and MinIO object-key conventions.
- Secret storage and key rotation.
- Frontend application shell, sidebar, thread history, Project / Artifacts tree, and credential settings UI.
- Tests for RBAC, conversations, artifacts, agent runs, and frontend workspace behavior.

### Current State Evidence

Code review confirmed the reported issues:

- `Project` currently owns `current_step`, `status`, and `conversation_data`.
- The existing run model is project-scoped and does not include `thread_id`.
- `Artifact` is project-scoped and does not include `thread_id`.
- The frontend workflow hook persists conversation state through project-level conversation APIs.
- Alice writes provider credentials into user settings.
- Artifact storage currently maps requirements specially but does not fully implement the required `requirements`, `test_cases`, and `test_scripts` shared project tree.

## 3. Recommended Approach

Use a hybrid approach:

1. Directly adjust the planning artifacts and Epic 12 backlog.
2. Treat the change as an MVP architecture correction before implementing additional workflow stories.
3. Do not roll back the multi-user/project-scoped direction; instead, refine it into a thread-based collaborative model.
4. Preserve Alice's responsibility for project selection at the start of a new thread.
5. Lock each thread to one project after Alice project selection.
6. Keep MinIO artifacts project-scoped and visible to authorized members of that project.
7. Store user secrets in encrypted PostgreSQL fields, not plaintext user settings.
8. Keep conversation threads private to the creating user, even when multiple users are assigned to the same project.

## 4. Detailed Change Proposals

### 4.1 PRD Changes

Update the PRD to clarify secure per-user credential handling and collaborative thread behavior.

#### Replace FR14

Provider API keys and MCP API keys must not be stored in `.env` or plaintext JSON columns. They must be collected from the user and stored in encrypted PostgreSQL fields, with only non-secret metadata persisted separately from encrypted secret material.

#### Add FR14a

Users can update or replace expired MCP and AI provider API keys from the UI without admin support. The UI must never display stored secret values.

#### Add FR14b

`ai_provider_config` and `ai_agents_config` must not duplicate system-level environment settings. PostgreSQL may store selected provider, selected model assignments, non-secret model-selection rationale, and non-secret runtime settings. Secrets remain in secret storage.

#### Update FR15b

Alice's provider/model review must include selected model, selected temperature or other non-secret runtime parameters, and rationale for each downstream agent.

#### Add Agent Run Execution Requirements

- Each project can have one or more conversation threads.
- A user can create a new thread, return to previous threads, and continue from saved thread state.
- Conversation threads are private to the user who created them; other users assigned to the same project cannot view or continue those threads.
- At the beginning of a new thread, Alice asks the user to select one accessible project.
- Once Alice binds a project to the thread, the project cannot be changed within that thread.
- Users on the same project can view project-level generated artifacts from other users, subject to project assignment and role.
- User secrets are per-user. AI provider API keys and MCP keys belong to the user, not the project.
- Agent workflow executions are stored as `agent_runs`, scoped only by `thread_id`; user and project scope are derived from the referenced thread.

#### Add Output and Storage Requirements

- The MinIO artifact tree is shared at project level.
- Required logical tree:

```text
projects/{project_id}/requirements/
projects/{project_id}/test_cases/
projects/{project_id}/test_scripts/
```

- If a PostgreSQL project exists but MinIO has no objects for it, the UI still shows the required empty folders for the selected project.
- Artifact metadata preserves ownership, kind, storage path, creator, updater, optional version history, optional originating thread, and optional originating agent run.

#### Replace Security NFR

System-level non-secret service URLs may be stored in environment configuration. User-provided MCP keys and AI provider API keys must be stored only in encrypted PostgreSQL fields and must never appear in `.env`, plaintext JSON columns, logs, WebSocket payload history, conversation history, artifacts, or generated files. Following the repo's settings convention, the encryption key should be configured as `USER_SECRETS_ENCRYPTION_KEY` in the environment and exposed in `AppSettings` as `user_secrets_encryption_key`; it must not be stored in PostgreSQL.

### 4.2 Epics and Story Backlog Changes

Update Epic 12 from a broad multi-user persistence epic into a collaborative project/thread/artifact epic.

#### Update Epic 12 Summary

Epic 12 should define a decoupled multi-user collaborative system where PostgreSQL is the source of truth for metadata, users, projects, threads, messages, agent runs, artifact metadata, encrypted per-user secrets, and non-secret configuration metadata. MinIO/S3-compatible object storage is the shared project-level artifact tree for generated requirements, test cases, and test scripts.

#### Update Story 12.1

Add database models and migrations for:

- `conversation_threads`
- `messages`
- `user_secrets` or equivalent secret reference metadata

Also clarify:

- `projects` no longer owns singleton `current_step`, `status`, or `conversation_data`.
- No automated legacy conversation-data migration is required for the current development environment. Existing developer-only data may be fixed manually in the database if needed.
- Alembic migration scripts must still update the database schema for the new models and columns.

#### Update Story 12.5

Artifact metadata must include:

- `project_id`
- optional `thread_id`
- optional `agent_run_id`
- kind
- `created_by_user_id`
- `updated_by_user_id`
- timestamps
- storage path
- current version when version history is used

MinIO tree:

```text
projects/{project_id}/requirements/
projects/{project_id}/test_cases/
projects/{project_id}/test_scripts/
```

Project members can list, read, edit, and delete artifacts from other users in the same project, subject to project assignment and role. This intentionally allows a user to remove outdated artifacts created by another user assigned to the same project.

#### Update Story 12.6

Replace the project-only frontend foundation with a collaborative workspace shell:

- Collapsible left sidebar.
- New Conversation.
- Conversation History.
- Project / Artifacts section for the active thread's bound project.
- Empty Project / Artifacts section before Alice project selection.
- Empty required folders after a project is selected but before artifacts exist.
- REST and WebSocket calls include thread scope.

#### Update Story 12.7

Agent run execution should be bound through exactly one conversation thread:

- Rename or replace the existing `pipeline_runs` schema with `agent_runs` for clearer domain meaning.
- `agent_runs` records `thread_id`, status, timestamps, and summary.
- An `agent_run` derives its owning user from `conversation_threads.created_by_user_id`.
- An `agent_run` derives its project from `conversation_threads.project_id` after Alice project selection.
- An `agent_run` cannot be reassigned to another thread after creation.
- Agent run execution updates only the referenced `conversation_threads.current_step` and `conversation_threads.status`.
- User and agent messages are persisted as append-only `messages` for the referenced thread.

#### Replace Story 12.10

New title: Collaborative Workspace Sidebar, Threads, and Project Artifact Tree.

Acceptance criteria:

- Login opens collaborative workspace shell for standard users.
- Admin users are routed only to the admin dashboard and do not enter the standard user workspace flow.
- Zero-project user gets a no-access message.
- New Conversation starts a new thread flow.
- Alice asks the user to select one accessible project.
- Before project selection, the Project / Artifacts section is empty.
- After project selection, sidebar shows only the selected project for the active thread.
- The selected project is locked for that thread.
- Conversation History reopens only the current user's existing threads with bound project, messages, current step, status, and latest agent run restored.
- If a user is removed from a project, threads bound to that project are hidden from that user's Conversation History and API access is denied.
- Authorized project users can browse, open, edit, and delete shared artifacts for assigned projects regardless of creator.
- Admin dashboard behavior remains unchanged.

#### Add Story 12.14: Thread and Message Persistence API

Acceptance criteria:

- Create conversation threads with project binding behavior that supports Alice project selection at thread start.
- Persist messages with `thread_id`, sender type/name, content, message type, metadata, and timestamp.
- List only the current user's threads ordered by last activity.
- Hide threads bound to projects that the user is no longer assigned to.
- Open thread returns ordered messages and state without project-level `conversation_data`.
- Users cannot list, open, or continue another user's threads, even if both users are assigned to the same project.
- Users removed from a project receive authorization errors if they try to open or continue a thread bound to that project.
- Non-members receive authorization errors without resource-existence leakage.
- No automated legacy project-level conversation-data migration is required; the schema migration is required and developer-only legacy data may be handled manually.

#### Add Story 12.15: Secure User Secret Storage and Rotation

Acceptance criteria:

- Store user password using one-way password hashing, not reversible encryption.
- Store AI provider API keys as per-user encrypted PostgreSQL fields; a user may store one or more provider keys for Browser Use, Claude, Gemini, ChatGPT, and on-premises providers.
- Store one MCP key as a per-user encrypted PostgreSQL field.
- PostgreSQL separates encrypted secret values from non-secret status and metadata.
- Secret encryption uses the environment-provided `USER_SECRETS_ENCRYPTION_KEY`, mapped to `AppSettings.user_secrets_encryption_key`.
- API and WebSocket responses never return secrets.
- UI shows secret status and allows replacement without revealing existing values.
- Alice and downstream agents resolve the current user's secrets at execution time.
- Secrets are never written to `users.settings`, conversation history, artifact metadata, logs, or generated files.
- `ai_provider_config` and `ai_agents_config` contain only non-secret provider selection, discovered model metadata, model assignments, runtime parameters, and rationale.
- Rotated secrets apply to future runs while existing thread/message history remains unchanged.

#### Add Story 12.16: Project Artifact Realtime Sync

Acceptance criteria:

- Backend emits artifact change events after application-managed artifact create, update, delete, or metadata-change operations.
- Event payload includes `project_id`, artifact identifier, change type, and timestamp.
- WebSocket clients for users assigned to the changed project receive the event, even if the changed project is not attached to the currently active thread.
- Frontend refetches the visible Project / Artifacts tree when the changed project is currently displayed.
- Refresh does not reset chat, current input, current step, or scroll position.
- If the currently opened artifact is updated or deleted, the UI shows a non-disruptive notice and offers to reload or close the preview.
- Direct external MinIO notifications are out of MVP scope; realtime sync only needs application-managed artifact events.
- Artifact version rollback is out of scope.

### 4.3 Architecture Changes

#### Frontend and API Layer

Replace the current project workspace assumption with a collaborative workspace shell.

New behavior:

- `/` routes standard users to the collaborative agent workspace.
- Admin users are routed only to the admin dashboard. Admins do not have projects and do not enter the standard project/thread workspace flow.
- The workspace contains chat, collapsible sidebar, current user's thread history, and Project / Artifacts area.
- Standard users start a new thread from the workspace shell.
- At the beginning of a new thread, Alice asks the user to select one accessible project.
- Once selected, the thread is bound to that `project_id`.
- Existing threads restore their bound project automatically.
- REST and WebSocket calls validate thread ownership and project assignment.

#### Agent Orchestration Layer

Alice remains responsible for project selection at thread start.

New behavior:

- Alice resolves standard-user project context before provider options are shown.
- Zero projects shows a no-access message and blocks provider selection.
- One project may be auto-selected with a confirmation message.
- Multiple projects render a selectable list.
- Choosing a project updates the thread with the selected `project_id`.
- The selected project is immutable for the lifetime of that thread.
- Opening an existing thread restores the bound project and must not ask the user to change project.
- Alice persists only non-secret provider/model configuration metadata and secret references.
- Downstream agents resolve secrets through backend secret services at execution time.

#### Output and Storage

New storage ownership:

- PostgreSQL stores users, projects, memberships, conversation threads, messages, agent runs, artifact metadata, optional artifact versions, non-secret config metadata, encrypted per-user MCP keys, encrypted per-user AI provider API keys, password hashes, and audit events.
- MinIO stores actual artifact bytes.
- No project-level secrets are required in the current scope.

Project state ownership:

- `projects` must not own singleton execution state.
- `conversation_threads` owns `project_id`, `created_by_user_id`, `current_step`, `status`, optional active agent run, and last activity.
- `messages` owns ordered chat history for one thread.
- `agent_runs` owns execution history for one thread and derives user/project scope from that thread.

Required MinIO bucket structure:

```text
ai-qa-artifacts/
  projects/
    {project_id}/
      requirements/
      test_cases/
      test_scripts/
      reports/
```

`reports/` may remain for execution outputs, but the required collaboration folders are `requirements`, `test_cases`, and `test_scripts`.

#### Core Data Model Changes

Add or update:

- `conversation_threads`: `id`, nullable or deferred `project_id` until Alice selection, `created_by_user_id`, title, `current_step`, status, optional `active_agent_run_id`, `last_activity_at`, timestamps.
- `messages`: `id`, `thread_id`, sender type, sender name, content, message type, metadata, created timestamp.
- `agent_runs`: `id`, `thread_id`, status, timestamps, summary, and any non-secret execution metadata; represents execution attempts or long-running agent work associated with exactly one thread.
- `artifacts`: add optional `thread_id`, optional `agent_run_id`, `created_by_user_id`, `updated_by_user_id`, and keep project-level visibility.
- `artifact_versions`: optional immutable version records for history only; rollback is out of scope.
- `user_secrets`: store per-user encrypted AI provider keys and one per-user encrypted MCP key plus non-secret status metadata, not plaintext keys.
- `users`: store password hashes, not encrypted or plaintext passwords.
- `audit_events`: optionally add `thread_id`.

Agent run binding rule:

- An `agent_run` is created only from an authenticated user action inside a thread owned by that user.
- The `agent_runs.thread_id` is the only required scope reference for an agent run.
- User scope is derived from `conversation_threads.created_by_user_id`.
- Project scope is derived from `conversation_threads.project_id`.
- An `agent_run` cannot be moved to another thread.
- Agent work inside the run uses encrypted secrets belonging to the thread owner.

Thread title rule:

- New thread titles default to `{project_name} - {timestamp}` after Alice binds the project.
- Users can rename their own thread titles later.

Thread binding rule:

- A new thread starts without a fixed project, or persistence may be deferred until Alice project selection.
- Once selected, the project is locked for that thread.
- Requests for an existing thread must validate that the requested project matches the thread-bound project.
- Requests for an existing thread must validate that the authenticated user owns the thread.
- If the thread owner is removed from the bound project, the thread is hidden from Conversation History and API access is denied.

RBAC rule:

- `admin` can create, read, update, and delete users and projects, and can assign or remove users from projects.
- `admin` does not participate in the standard project/thread workspace flow.
- `user` can create personal threads, append messages to their own threads, and view, create, edit, or delete artifacts for assigned projects.
- `user` can edit or delete artifacts created by another user assigned to the same project when those artifacts are outdated or no longer needed.
- `user` cannot access another user's threads.

#### API and WebSocket Contracts

Add or update API capability for:

- Create/list/open conversation threads owned by the authenticated user.
- Hide threads bound to projects the authenticated user is no longer assigned to.
- Persist and retrieve ordered messages for the authenticated user's threads.
- Bind a project to a new thread during Alice project selection.
- Validate immutable thread-project binding.
- Create/list/read agent runs only through `thread_id` and only when the authenticated user owns the referenced thread and remains assigned to the bound project.
- Derive agent run user/project authorization from the referenced thread instead of duplicating user/project columns on `agent_runs`.
- List Project / Artifacts tree for assigned projects.
- Read, create, edit, and delete artifact content and metadata for assigned projects.
- Upsert/rotate per-user encrypted secrets without returning secret values.
- Emit artifact change events to WebSocket clients whose authenticated users are assigned to the changed project.

Artifact change event payload should include:

- `project_id`
- artifact identifier
- change type
- timestamp

Direct external MinIO notifications are out of MVP scope. Artifact realtime sync is required only for application-managed artifact events. Artifact rollback is out of scope.

### 4.4 UX Changes

#### Main Workspace

The main UI becomes a collaborative workspace shell with:

- Collapsible left sidebar.
- Main chat/thread area.
- Agent progress/review area.
- Artifact preview panel when a generated file is opened.

The chat remains the primary interaction model.

#### New Conversation

- Starts a new thread flow.
- Opens a clean chat state.
- Alice asks the user to select one accessible project.
- Before project selection, the Project / Artifacts section is empty.
- If the user has no projects, show a no-access message.

#### Conversation History

- Lists only the current user's previous threads ordered by latest activity.
- Hides threads whose bound project is no longer assigned to the current user.
- Each thread displays title, bound project name, current agent/step, and status.
- Default thread titles use `{project_name} - {timestamp}` after project binding.
- Users can rename their own threads later.
- Selecting a thread restores the bound project, ordered messages, current step, status, and latest agent run.
- The bound project cannot be changed from inside the reopened thread.

#### Project / Artifacts

- UI label is singular: Project.
- Shows only the one project bound to the active thread.
- Before Alice project selection completes, this section is empty.
- After project selection, show the selected project node and its artifact folders:
  - `requirements`
  - `test_cases`
  - `test_scripts`
- If the selected project exists in PostgreSQL but has no MinIO objects yet, show those folders as empty.
- Generated files are visible to all authorized users in the bound project, regardless of creator.
- Authorized project users can edit or delete artifacts regardless of creator.
- Opening a file shows preview and metadata: artifact kind, creator, last updater, version when available, originating thread/agent run if available, and timestamp.

#### Artifact Realtime Sync

- Project / Artifacts auto-refreshes when artifacts change in any project assigned to the current user.
- Artifact changes include file created, updated, deleted, or metadata changed.
- Artifact version rollback is not required.
- When artifacts change through the application, assigned users receive a realtime notification.
- Direct external MinIO changes do not need realtime sync in the MVP.
- If the changed project is currently displayed, the frontend reloads the Project / Artifacts tree.
- Users not assigned to the changed project are not affected.
- Users in a new thread before project selection may receive project artifact notifications for assigned projects, but no Project / Artifacts tree is shown until a project is selected.
- Refresh updates the sidebar tree without resetting chat, current input, current step, or scroll position.
- If a currently opened artifact is updated or deleted, show a non-disruptive notice and offer to reload or close the preview.

#### Credential Management UX

- Provide a user settings or credential panel for AI provider keys and MCP keys.
- Never display stored secret values.
- Show only non-secret status such as configured, missing, expired/invalid, or last updated.
- Allow the user to replace an expired or invalid key.
- Support one or more AI provider keys per user for Browser Use, Claude, Gemini, ChatGPT, and on-premises providers.
- Support one MCP key per user.
- After replacement, future agent runs use the new secret.
- Existing thread/message history and artifact metadata remain unchanged.
- If a provider or MCP call fails due to credential expiration, show a clear recoverable action that routes the user to replace the key.

## 5. Implementation Handoff

### Recommended Implementation Order

1. Database migration foundation
   - Add conversation thread, message, encrypted user secret, `agent_runs`, and updated artifact fields.
   - Rename or replace `pipeline_runs` with `agent_runs` and update related columns such as `active_pipeline_run_id` to `active_agent_run_id` and `pipeline_run_id` to `agent_run_id`.
   - Add Alembic migration scripts for schema changes.
   - Do not implement automated legacy conversation-data migration; developer-only legacy data can be handled manually if needed.
   - Remove or deprecate project-level singleton state usage.

2. Backend thread/message APIs
   - Create/list/open only the authenticated user's threads.
   - Persist ordered messages.
   - Bind project to a new thread during Alice selection.
   - Enforce immutable thread-project binding.
   - Enforce private thread ownership even when artifacts remain project-shared.

3. Secret storage abstraction
   - Introduce a `SecretStore` interface backed by per-user encrypted PostgreSQL fields.
   - Use `USER_SECRETS_ENCRYPTION_KEY`, mapped to `AppSettings.user_secrets_encryption_key`, as the encryption key source.
   - Store passwords as password hashes, not encrypted plaintext.
   - Move provider/MCP keys out of `User.settings`.
   - Support multiple AI provider keys per user and one MCP key per user.
   - Update Alice and downstream agents to resolve the current user's secrets at execution time.
   - Add key rotation APIs.

4. Agent run and WebSocket thread scoping
   - Include only `thread_id` as the scope reference in `agent_runs`.
   - Derive agent run user scope from `conversation_threads.created_by_user_id`.
   - Derive agent run project scope from `conversation_threads.project_id`.
   - Persist step/status on `conversation_threads`.
   - Persist chat output as `messages`.
   - Validate project/thread/run access through the referenced thread on every request.
   - Deny access to threads, messages, and agent runs when the user is removed from the bound project.

5. Artifact service and MinIO tree
   - Align artifact object keys with `requirements`, `test_cases`, and `test_scripts`.
   - Add Project / Artifacts tree API for the active bound project.
   - Add artifact creator/updater metadata.
   - Ensure project members can read, create, edit, and delete shared artifacts subject to RBAC, regardless of artifact creator.

6. Artifact realtime sync
   - Emit artifact change events after application-managed artifact mutations.
   - Do not require external MinIO notification integration for MVP.
   - Broadcast to clients whose authenticated users are assigned to the changed project, regardless of which thread is currently active.
   - Frontend refetches Project / Artifacts without disrupting chat state.

7. Frontend workspace shell
   - Add collapsible sidebar.
   - Add New Conversation.
   - Add Conversation History.
   - Add singular Project / Artifacts section.
   - Keep Project empty before Alice project selection.
   - Show only the bound project after selection.
   - Add artifact preview behavior.

8. Credential management UI
   - Add secure key status and replacement UX.
   - Never reveal existing key values.
   - Surface recoverable credential-expiration errors.

9. Tests and validation
   - Unit tests for new models and migrations.
   - API tests for threads, messages, RBAC, artifacts, and secrets.
   - WebSocket tests for thread-scoped state and artifact change broadcasts.
   - Frontend tests for New Conversation, Conversation History, Project / Artifacts empty/bound states, and realtime reload.
   - Regression tests proving one project can have multiple threads and multiple users can share project artifacts.

### Acceptance Criteria for the Corrected Epic

- A user can create multiple private threads over time.
- Each thread is bound to exactly one project after Alice project selection.
- The bound project cannot be changed inside the same thread.
- One project can have multiple threads across one or more users, but each thread remains visible only to its creator.
- If a user is removed from a project, threads bound to that project are hidden from history and API access is denied.
- Each agent run stores only `thread_id` for scope.
- Each agent run's user and project are derived from the referenced thread.
- Users on the same assigned project can see shared generated artifacts in MinIO.
- Users assigned to a project can view, create, edit, and delete artifacts for that project regardless of creator.
- Artifact metadata records creator and last updater.
- Before project selection, the UI Project section is empty.
- After project selection, the UI shows only the bound project and its required folders.
- Application-managed artifact changes trigger realtime Project / Artifacts reload for assigned users when the changed project is currently displayed, regardless of which thread is active.
- External MinIO notification integration is not required for MVP realtime sync.
- Passwords are stored as password hashes.
- AI provider API keys and MCP keys are stored as per-user encrypted PostgreSQL fields and are not stored in plaintext JSON columns, logs, messages, artifacts, or WebSocket history.
- Secret encryption uses `USER_SECRETS_ENCRYPTION_KEY`, mapped to `AppSettings.user_secrets_encryption_key`.
- Users can store one or more AI provider keys and one MCP key.
- Expired or invalid keys can be replaced from the UI without revealing stored secret values.
- Admin users remain limited to the admin dashboard and do not enter the standard user project/thread workspace.

## 6. Decision

This Sprint Change Proposal is approved as the source of truth for updating the PRD, Epic 12 backlog, Architecture document, and UX specification before implementation continues.

## 7. Resolved Decisions

- Approval status is approved.
- Secret storage uses per-user encrypted PostgreSQL fields for AI provider API keys and MCP keys.
- Passwords are stored as password hashes, not encrypted plaintext.
- Secret encryption key comes from `USER_SECRETS_ENCRYPTION_KEY`, mapped to `AppSettings.user_secrets_encryption_key`.
- Users can store one or more AI provider API keys for Browser Use, Claude, Gemini, ChatGPT, and on-premises providers.
- Users can store one MCP key.
- Project-level secrets are out of scope.
- Automated legacy conversation-data migration is not required; schema migration scripts are required, and developer-only legacy data may be fixed manually.
- Conversation threads are private to the creating user and are not shared with other users assigned to the same project.
- If a user is removed from a project, threads bound to that project are hidden from Conversation History and API access is denied.
- Artifacts are project-shared for assigned users.
- Artifact metadata must include creator metadata and last-updater metadata.
- Assigned users may edit or delete artifacts created by other users when those artifacts are outdated or no longer needed.
- Roles are limited to `admin` and `user`.
- `admin` can CRUD users/projects and assign or remove users from projects, but does not enter the standard user workspace.
- `user` can create personal threads, append messages to their own threads, and view, create, edit, or delete artifacts for assigned projects.
- Thread titles default to `{project_name} - {timestamp}` after project binding and can be renamed later by the owning user.
- Rename the run table/concept from `pipeline_runs` to `agent_runs` for clearer meaning.
- Agent runs store only `thread_id` for scope.
- Agent run user scope is derived from the referenced thread's `created_by_user_id`.
- Agent run project scope is derived from the referenced thread's `project_id`.
- Artifact version rollback is out of scope.
- Artifact realtime updates are project-assignment scoped, not active-thread scoped. Assigned users may receive artifact update events even if the changed project is not attached to their currently active thread.
- Realtime artifact updates only need application-managed events for MVP; external MinIO notification integration is out of scope.
