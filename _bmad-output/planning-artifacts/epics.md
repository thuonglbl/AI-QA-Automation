---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
inputDocuments:
  - prd.md
  - architecture.md
  - ux-design-specification.md
---

# AI QA Automation - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for AI QA Automation, decomposing the requirements from the PRD, UX Design if it exists, and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: Pipeline can connect to on-premises Confluence via MCP server and authenticate using existing SSO session
FR2: Pipeline can retrieve test case content from a specified Confluence page URL
FR3: Pipeline can parse natural-language test cases from Confluence page content
FR4: Pipeline can handle Confluence content variations including embedded macros and non-standard formatting (Milestone 1)
FR5: Pipeline can interpret natural-language test case steps and translate them into browser automation actions
FR6: Pipeline can generate executable Python Playwright test scripts from parsed test cases
FR7: Pipeline can produce one test file per Confluence test case with naming derived from test case title
FR8: Pipeline can generate stable selectors (data-testid, role-based) over fragile ones (CSS path, XPath)
FR9: Pipeline can map expected results from test case documentation into Playwright assertions
FR10: Engineer can trigger the pipeline by providing a Confluence page URL
FR11: Pipeline can execute end-to-end (MCP → LLM → browser-use → Playwright output) without manual intervention
FR12: Pipeline can control a local Chrome instance via browser-use framework using active SSO login session
FR13: Pipeline can output generated test files to a configurable output directory
FR14: Provider API keys and MCP API keys must not be stored in `.env` or plaintext JSON columns. They must be collected from the user and stored in encrypted PostgreSQL fields, with only non-secret metadata persisted separately from encrypted secret material.
FR14a: Users can update or replace expired MCP and AI provider API keys from the UI without admin support. The UI must never display stored secret values.
FR14b: `ai_provider_config` and `ai_agents_config` must not duplicate system-level environment settings. PostgreSQL may store selected provider, selected model assignments, non-secret model-selection rationale, and non-secret runtime settings. Secrets remain in secret storage.
FR15: Alice must dynamically validate the selected AI provider and discover available models from the selected provider/server where supported. Engineer-managed LLM parameter tuning is not part of the MVP because available models are dynamic and cannot be safely predetermined.
FR15a: Alice must only assign downstream agent models from the provider's discovered available model list. If model discovery fails, returns no models, or cannot verify a selected model exists, Alice must block successful configuration review and show an actionable recovery message.
FR15b: Alice must provide a user-reviewable provider/model review for each downstream agent, including provider connection status, discovered models, agent model needs, selected model, selected temperature or other non-secret runtime parameters, and selection rationale.
FR16: Admin can create, read, update, and delete users and projects, and can assign or remove users from projects. Admin users are routed only to the admin dashboard and do not enter the standard project/thread workspace flow.
FR16a: Admin can trigger an automated E2E test run directly from the dashboard. The tests run in headed mode with slow motion for visual monitoring, and the report is automatically downloaded to the admin's machine upon completion.
FR17: User can run comparison tests between LLM providers to evaluate output quality. This is deferred to backlog and is not required for the current MVP.
FR18: Admin prompt-template tuning is removed from the MVP because dynamic provider/model selection makes centralized prompt tuning too complex for this phase.
FR19: Reviewer can view generated scripts alongside their source Confluence test cases for side-by-side comparison
FR20: Reviewer can approve or reject individual generated scripts
FR21: Reviewer can edit generated scripts before approval
FR22: Pipeline can flag low-confidence generations for mandatory review
FR23: Pipeline can connect to on-premises Jira Data Center via MCP server
FR24: Pipeline can retrieve test-related requirements from Jira tickets
FR25: Pipeline can log which Confluence pages were read, which scripts were generated, and by whom
FR26: Pipeline can report script execution success rate
FR27: Pipeline can detect insufficient input quality and warn before generation
FR28: Leadership can view metrics dashboard showing scripts generated, success rates, and effort reduction
FR29: Leadership can view LLM cost tracking and comparison data
FR30: Each project can have one or more conversation threads.
FR31: A user can create a new thread, return to previous threads, and continue from saved thread state.
FR32: Conversation threads are private to the user who created them; other users assigned to the same project cannot view or continue those threads.
FR33: At the beginning of a new thread, Alice asks the user to select one accessible project.
FR34: Once Alice binds a project to the thread, the project cannot be changed within that thread.
FR35: Users on the same project can view project-level generated artifacts from other users, subject to project assignment and role.
FR36: User secrets are per-user. AI provider API keys and MCP keys belong to the user, not the project.
FR37: Agent workflow executions are stored as `agent_runs`, scoped only by `thread_id`; user and project scope are derived from the referenced thread.
FR38: `agent_runs` records `thread_id`, status, timestamps, summary, and non-secret execution metadata. An `agent_run` cannot be reassigned to another thread after creation.
FR39: Agent run execution updates only the referenced `conversation_threads.current_step` and `conversation_threads.status`.
FR40: User and agent messages are persisted as append-only `messages` for the referenced thread.
FR41: If a user is removed from a project, threads bound to that project are hidden from that user's Conversation History and API access is denied.
FR42: The SeaweedFS artifact tree is shared at project level.
FR43: Required logical artifact folders are `projects/{project_id}/requirements/`, `projects/{project_id}/test_cases/`, and `projects/{project_id}/test_scripts/`.
FR44: If a PostgreSQL project exists but SeaweedFS has no objects for it, the UI still shows the required empty folders for the selected project.
FR45: Artifact metadata preserves ownership, kind, storage path, creator, updater, optional version history, optional originating thread, and optional originating agent run.
FR46: Project members can list, read, edit, and delete artifacts from other users in the same project, subject to project assignment and role.
FR47: Login opens the collaborative workspace shell for standard users.
FR48: The workspace shell includes a collapsible left sidebar, New Conversation, Conversation History, and a singular Project / Artifacts section for the active thread's bound project.
FR49: Before Alice project selection, the Project / Artifacts section is empty.
FR50: After project selection, the sidebar shows only the selected project for the active thread and the selected project is locked for that thread.
FR51: Conversation History reopens only the current user's existing threads with bound project, messages, current step, status, and latest agent run restored.
FR52: Authorized project users can browse, open, edit, and delete shared artifacts for assigned projects regardless of creator.
FR53: Zero-project users receive a no-access message.
FR54: Store AI provider API keys as per-user encrypted PostgreSQL fields; a user may store one or more provider keys for Browser Use, Claude, Gemini, ChatGPT, and on-premises providers.
FR55: Store one MCP key as a per-user encrypted PostgreSQL field.
FR56: PostgreSQL separates encrypted secret values from non-secret status and metadata.
FR57: API and WebSocket responses never return secrets.
FR58: UI shows secret status and allows replacement without revealing existing values.
FR59: Alice and downstream agents resolve the current user's secrets at execution time.
FR60: Rotated secrets apply to future runs while existing thread/message history remains unchanged.
FR61: Backend emits artifact change events after application-managed artifact create, update, delete, or metadata-change operations.
FR62: Event payload includes `project_id`, artifact identifier, change type, and timestamp.
FR63: WebSocket clients for users assigned to the changed project receive the event, even if the changed project is not attached to the currently active thread.
FR64: Frontend refetches the visible Project / Artifacts tree when the changed project is currently displayed.
FR65: Artifact refresh does not reset chat, current input, current step, or scroll position.
FR66: If the currently opened artifact is updated or deleted, the UI shows a non-disruptive notice and offers to reload or close the preview.
FR67: Direct external SeaweedFS notifications and artifact version rollback are out of MVP scope.

### NonFunctional Requirements

NFR1: Pipeline end-to-end generation completes within 5 minutes per test case.
NFR2: Individual browser actions complete within 30 seconds to avoid timeout cascading.
NFR3: Generated Playwright scripts execute within standard Playwright timeout defaults.
NFR4: LLM API latency is provider-dependent; Claude Enterprise latency is acceptable for batch processing.
NFR5: No data is transmitted outside company infrastructure; on-prem constraint is enforced at all phases.
NFR6: System-level non-secret service URLs may be stored in environment configuration.
NFR7: User-provided MCP keys and AI provider API keys are stored only in encrypted PostgreSQL fields and never appear in `.env`, plaintext JSON columns, logs, WebSocket payload history, conversation history, artifacts, or generated files.
NFR8: Secret encryption uses `USER_SECRETS_ENCRYPTION_KEY`, mapped to `AppSettings.user_secrets_encryption_key`; the encryption key must not be stored in PostgreSQL.
NFR9: Passwords are stored as one-way password hashes, not reversible encryption or plaintext.
NFR10: Browser sessions reuse existing SSO and the pipeline must not store, cache, or log credentials.
NFR11: AI browser agent is restricted to read-only navigation with no form submissions, data modifications, or write operations during generation.
NFR12: Audit logging records all pipeline executions, including who, when, which page, and which scripts.
NFR13: On-premises LLMs eliminate external API data transfer entirely where selected.
NFR14: MCP server unavailability fails gracefully with clear error messages.
NFR15: LLM API rate limits, timeouts, and transient errors are handled with retry logic, max 3 retries.
NFR16: browser-use handles browser crashes or navigation failures without corrupting partial output.
NFR17: Playwright output is valid standalone Python executable with only Playwright as dependency.
NFR18: Startup validation checks all required system-level values and fails fast with actionable error messages.

### Additional Requirements

- Architecture selected manual restructure/no starter template because the project already exists; future implementation must preserve current work.
- Backend uses Python 3.12+, `uv`, Hatchling, FastAPI, SQLAlchemy/Alembic, PostgreSQL, SeaweedFS, Pydantic Settings, Ruff, mypy, pytest, and pytest-asyncio.
- Frontend uses React 18+, TypeScript, Vite, Shadcn/ui, Tailwind CSS, React Router v6, react-markdown, react-syntax-highlighter, and Mermaid rendering.
- Primary UX is a conversational React workspace with FastAPI REST and WebSocket backend, plus an admin dashboard route.
- Five named agents are required: Alice, Bob, Mary, Sarah, and Jack, each using Start → Processing → Review Request → Approve/Reject → Done lifecycle.
- Alice owns project selection, secret status, provider validation, runtime model discovery, discovered-model scoring, model assignment review, and persistence of only non-secret provider/model configuration.
- Agent runs are scoped by `thread_id`; user/project scope is derived from the immutable thread-project binding.
- PostgreSQL stores users, password hashes, projects, memberships, conversation threads, messages, agent runs, non-secret user provider configuration, encrypted user secrets, artifact metadata, artifact version metadata, and audit metadata.
- SeaweedFS stores project-level artifact bytes under `projects/{project_id}/requirements/`, `projects/{project_id}/test_cases/`, and `projects/{project_id}/test_scripts/`.
- Artifacts must be written through the artifact service so metadata, SeaweedFS storage, authorization, audit, and realtime events remain consistent.
- WebSocket realtime hub broadcasts project-scoped artifact change events to authorized connected clients without disrupting active chat state.
- Provider adapters expose `validate_connection(credentials, base_url)` and `list_models(credentials, base_url)` and normalize `DiscoveredModel` values.
- Static model names may only be ranking hints after provider discovery verifies availability.
- Pipeline stages must exchange Pydantic models and return the standard `StageResult` structure.
- Tenacity retry and custom exception hierarchy are mandatory for LLM, MCP, browser, configuration, and pipeline failures.
- Authorization must protect every project, thread, message, agent run, artifact, and secret operation.
- Response schemas, logs, messages, and artifacts must enforce secret redaction.
- Existing local auth/admin/project functionality remains part of the architecture; Azure Entra ID SSO is deferred.

### UX Design Requirements

UX-DR1: Conversational chat UI with named AI agents as chat participants; agent messages are left-aligned and user messages are right-aligned.
UX-DR2: AgentTopBar shows agent avatar, agent name, step title, step counter, status badge, and accessible status changes.
UX-DR3: ChatMessage supports rich rendered content, agent/user bubble variants, avatar/name/timestamp, and accessible list semantics.
UX-DR4: ChatInputArea changes by state: Start, Processing, Review, Reject-feedback, Done, and Completed.
UX-DR5: ReviewContent renders Markdown/GFM, syntax-highlighted Python, Mermaid diagrams, images, and scrollable rich content.
UX-DR6: StepDots show 5-dot progress with completed/active/pending states and progressbar accessibility.
UX-DR7: ProcessingIndicator shows animated dots, status message, `aria-live="polite"`, and `role="status"`.
UX-DR8: Status badges use Start, Processing, Review Request, Done, and Completed states with color + text + icon.
UX-DR9: Use the Professional Calm color system: blue primary, neutral slate surfaces/text, green success, amber warning, red error, and blue info.
UX-DR10: Use system font stack only with defined scale for titles, agent names, body text, labels, code, buttons, and badges.
UX-DR11: Button hierarchy allows at most two input-area buttons at once; primary actions are solid, Reject is red outline, primary action is right-aligned, and no confirmation dialogs are used.
UX-DR12: Feedback is delivered conversationally through agent messages with defined success, error, warning, progress, and rejection-acknowledgment patterns.
UX-DR13: Every step follows the universal state machine Start → Processing → ReviewRequest → Done, with Error and RejectFeedback branches and specified transition animations.
UX-DR14: Pipeline navigation is forward-only; StepDots are informational; multi-item review uses Next/Previous; approval applies to current item only.
UX-DR15: WCAG 2.1 AA is required: focus rings, labels, 44px click targets, `aria-describedby`, keyboard navigation, status live regions, and screen reader support.
UX-DR16: Review states use split-panel layout where appropriate with 50/50 grid, 16px gap, independent scroll, and minimum 400px height.
UX-DR17: Alice provider selection displays provider options, credential collection, connection/model-discovery review, and remembered configuration while excluding secret values.
UX-DR18: Chat scroll auto-scrolls to latest messages, supports reviewing history, and shows a new-message indicator when scrolled up.
UX-DR19: Agent personalities use Alice pink, Bob blue, Mary green, Sarah purple, and Jack orange avatars with role-specific greetings.
UX-DR20: One-time setup inputs and secret statuses are remembered where appropriate, but returning users should not receive automatic saved-config chat noise.
UX-DR21: Alice project selection handles zero, one, or multiple accessible projects before provider selection and locks selected project to the thread.
UX-DR22: Alice displays an expandable thinking bubble showing provider status, model discovery status, discovered model list, per-agent model needs, selected model, rationale, and failure/recovery guidance without secrets.
UX-DR23: Provider credential forms collect only user-specific API keys; provider base URLs are deployment-level environment configuration.
UX-DR24: On-Premises provider copy states: "Highest security • Private endpoint configured by deployment • Personal API key required".
UX-DR25: Alice success review says only "Connected successfully to [Provider]" plus selected provider, valid model per downstream agent, and optional compact status metadata; no hardcoded recommendations.
UX-DR26: Returning saved provider configuration may initialize silently; users inspect or change it through explicit UI action.

### FR Coverage Map

FR1: Epic 11 - Confluence MCP connection and SSO reuse
FR2: Epic 11 - Retrieve Confluence content
FR3: Epic 11 - Parse natural-language test cases
FR4: Epic 11 - Handle Confluence content variations
FR5: Epic 12 - Interpret natural-language test steps for browser automation
FR6: Epic 13 - Generate executable Python Playwright scripts
FR7: Epic 13 - Produce one script file per test case
FR8: Epic 13 - Prefer stable selectors
FR9: Epic 13 - Map expected results into assertions
FR10: Epic 11 - Trigger extraction from Confluence URL
FR11: Epic 15 - Complete end-to-end pipeline execution
FR12: Epic 13 - Use browser-use with local Chrome and SSO session
FR13: Epic 13 / Epic 15 - Save generated scripts and execution reports
FR14: Epic 9 - Encrypted per-user AI/MCP secret storage
FR14a: Epic 9 - User-driven secret replacement
FR14b: Epic 9 - Non-secret provider/model configuration separation
FR15: Epic 9 - Dynamic provider validation and model discovery
FR15a: Epic 9 - Assign only discovered available models
FR15b: Epic 9 - User-reviewable provider/model review
FR16: Epic 8 - Admin CRUD for users, projects, and memberships
FR16a: Epic 8 - Admin E2E test execution and report download
FR17: Epic 14 - Provider comparison backlog support
FR18: Not implemented - removed from MVP
FR19: Epic 13 - Side-by-side script/source review
FR20: Epic 13 - Approve or reject generated scripts
FR21: Epic 13 - Edit scripts before approval
FR22: Epic 12 / Epic 13 - Low-confidence review flagging
FR23: Epic 11 - Jira MCP connection
FR24: Epic 11 - Retrieve Jira test-related requirements
FR25: Epic 14 - Audit logging
FR26: Epic 15 - Script execution success-rate reporting
FR27: Epic 11 / Epic 12 - Input quality detection and warnings
FR28: Epic 14 - Leadership metrics dashboard
FR29: Epic 14 - LLM cost tracking and comparison data
FR30: Epic 7 - Project conversation threads
FR31: Epic 7 - Create and resume threads
FR32: Epic 7 - Private per-user conversation threads
FR33: Epic 7 / Epic 16 - Alice project selection at new thread start
FR34: Epic 7 - Immutable thread-project binding
FR35: Epic 10 - Project-level artifact visibility
FR36: Epic 9 - Per-user ownership of secrets
FR37: Epic 7 - Thread-scoped agent runs
FR38: Epic 7 - Immutable agent run thread association
FR39: Epic 7 - Agent run updates thread step/status
FR40: Epic 7 - Append-only thread messages
FR41: Epic 7 - Hide inaccessible project threads after membership removal
FR42: Epic 10 - Project-level SeaweedFS artifact tree
FR43: Epic 10 - Required project artifact folders
FR44: Epic 10 - Empty project folders shown in UI
FR45: Epic 10 - Artifact ownership, metadata, and version metadata
FR46: Epic 10 - Project-member artifact operations
FR47: Epic 7 / Epic 16 - Collaborative workspace after login
FR48: Epic 7 / Epic 16 - Workspace shell and sidebar
FR49: Epic 7 / Epic 16 - Empty artifacts section before project selection
FR50: Epic 7 / Epic 16 - Locked selected project in sidebar
FR51: Epic 7 - Restore conversation history
FR52: Epic 10 / Epic 16 - Shared artifact browse/open/edit/delete
FR53: Epic 7 / Epic 16 - Zero-project no-access message
FR54: Epic 9 - Encrypted AI provider API keys
FR55: Epic 9 - Encrypted MCP key
FR56: Epic 9 - Secret value and metadata separation
FR57: Epic 9 - No secrets in API/WebSocket responses
FR58: Epic 9 / Epic 16 - Secret status and replacement UI
FR59: Epic 9 - Runtime secret resolution
FR60: Epic 9 - Rotated secrets apply to future runs
FR61: Epic 10 - Artifact change events
FR62: Epic 10 - Artifact event payload fields
FR63: Epic 10 - Broadcast to authorized project users
FR64: Epic 10 / Epic 16 - Refetch visible artifact tree
FR65: Epic 10 / Epic 16 - Artifact refresh preserves chat/input/scroll state
FR66: Epic 10 / Epic 16 - Non-disruptive open-artifact update/delete notice
FR67: Epic 10 - External SeaweedFS notifications and rollback out of scope

## Epic List

### Epic 7: Secure Multi-User Workspace Foundation

Users can securely access the system, select and bind projects to threads, resume private conversation history, and operate inside a project-scoped collaborative workspace shell.

**FRs covered:** FR30, FR31, FR32, FR33, FR34, FR37, FR38, FR39, FR40, FR41, FR47, FR48, FR49, FR50, FR51, FR53

### Story 7.1: Local Login and Authenticated Session Foundation

As a project user,
I want to log in with local email/password credentials,
So that I can access the system securely before entering any workspace.

**Acceptance Criteria:**

**Given** a seeded user account exists with an email, display name, role, and password hash
**When** the user submits valid login credentials
**Then** the backend authenticates the user and returns a session/token suitable for protected API calls
**And** the frontend stores and applies the session/token through the API client

**Given** a user submits an invalid email or password
**When** login is attempted
**Then** authentication is rejected with a safe, consistent error message
**And** the response does not reveal whether the email exists

**Given** an authenticated user calls the current-user endpoint
**When** the session/token is valid
**Then** the backend returns the user's email, display name, and role
**And** no password hash or secret data is returned

### Story 7.2: Project Membership Access for Standard Users

As a standard user,
I want to see only projects assigned to me,
So that I can choose from authorized project workspaces only.

**Acceptance Criteria:**

**Given** an authenticated standard user belongs to one or more projects
**When** the frontend requests the user's accessible project list
**Then** the backend returns only projects where the user has active membership
**And** admin-only project records are not exposed beyond the user's authorization

**Given** an authenticated standard user belongs to zero projects
**When** the frontend requests accessible projects
**Then** the backend returns an empty project list
**And** the frontend can display the no-access state required by FR53

**Given** an unauthenticated request is made to the project list endpoint
**When** the backend evaluates the request
**Then** the request is rejected as unauthorized

### Story 7.3: New Conversation Thread Creation with Alice Project Selection

As a standard user,
I want Alice to select and bind a project at the start of a new thread,
So that every workflow run is scoped to the correct project.

**Acceptance Criteria:**

**Given** an authenticated standard user starts a new conversation
**When** the thread is created
**Then** the thread is private to that user
**And** the thread remains unbound until Alice resolves project selection

**Given** the user has exactly one accessible project
**When** Alice starts project selection
**Then** Alice automatically binds that project to the thread
**And** the project cannot be changed afterward

**Given** the user has multiple accessible projects
**When** Alice asks the user to select one project
**Then** the selected project is bound to the thread
**And** the project cannot be changed afterward

**Given** the user has zero accessible projects
**When** Alice starts project selection
**Then** Alice shows the no-access message
**And** no provider setup or pipeline action is shown

### Story 7.4: Thread-Scoped Messages and Agent Run Records

As a project user,
I want conversation messages and agent executions saved under my thread,
So that the workflow state can be audited and resumed accurately.

**Acceptance Criteria:**

**Given** a conversation thread exists
**When** the user or an agent sends a message
**Then** the message is persisted as append-only data linked to the thread
**And** messages cannot be reassigned to another thread

**Given** an agent workflow execution starts for a thread
**When** the backend creates an agent run
**Then** the agent run stores `thread_id`, status, timestamps, summary, and non-secret execution metadata
**And** user and project scope are derived from the thread rather than duplicated as mutable runtime authority

**Given** an agent run updates workflow progress
**When** the update is persisted
**Then** only the referenced thread's `current_step` and `status` are updated
**And** the agent run cannot be reassigned to another thread

### Story 7.5: Conversation History and Thread Resume

As a standard user,
I want to reopen my previous conversation threads,
So that I can continue work from saved state.

**Acceptance Criteria:**

**Given** an authenticated user has existing threads
**When** the user opens Conversation History
**Then** the frontend shows only threads created by that user
**And** each visible thread includes bound project, current step, status, and last activity metadata

**Given** the user selects a previous thread
**When** the thread is reopened
**Then** the backend returns the persisted messages, current step, status, and latest agent run summary
**And** the frontend restores the conversation without creating a duplicate thread

**Given** another user belongs to the same project
**When** that other user opens Conversation History
**Then** they cannot see or continue the first user's private threads

### Story 7.6: Membership Removal Access Enforcement

As an admin-managed system,
I want project membership removal to immediately affect thread visibility and access,
So that users cannot access project-bound work after losing membership.

**Acceptance Criteria:**

**Given** a user is removed from a project
**When** the user opens Conversation History
**Then** threads bound to that project are hidden from the user

**Given** a removed user attempts direct API access to a thread bound to the removed project
**When** the backend authorizes the request
**Then** access is denied
**And** the response does not expose thread, project, artifact, or agent-run details

**Given** a removed user has an active frontend session
**When** project-scoped access is next checked
**Then** the UI handles denial safely and prompts the user to choose an accessible workflow state or contact an administrator

### Story 7.7: Standard User Workspace Shell Routing

As a standard user,
I want to enter a collaborative workspace shell after login,
So that I can start or resume AI QA automation work from one consistent place.

**Acceptance Criteria:**

**Given** a standard user logs in successfully
**When** routing completes
**Then** the frontend opens the standard workspace shell rather than the admin dashboard
**And** the shell includes a collapsible sidebar with New Conversation, Conversation History, and Project / Artifacts sections

**Given** a new thread has not selected a project yet
**When** the workspace shell is displayed
**Then** the Project / Artifacts section is empty
**And** Alice project selection is the next required workflow action

**Given** a thread has a bound project
**When** the workspace shell is displayed
**Then** the sidebar shows only the selected project for that active thread
  **And** the selected project appears locked for that thread

### Story 7.8: Refactor Agent Runs and Pipeline Runs

As a developer,
I want to refactor and document the differences between agent_runs and pipeline_runs,
So that the transition from the old Pipeline architecture to the new Thread/Chat architecture is clear and artifacts/audits can be correctly migrated.

**Acceptance Criteria:**

**Given** the current transition from Pipeline to Thread/Chat architecture
**When** reviewing the schema and usage of agent_runs and pipeline_runs
**Then** the similarities (status tracking, timestamps, metadata) and differences (scope, relationships, audit integration) must be clearly documented

**Given** the new Chat interface is finalized
**When** artifacts and audit events are generated
**Then** their foreign keys (`pipeline_run_id`) must be updated to use `agent_run_id` (or `thread_id`)

**Given** the migration is complete
**When** the old pipeline components are no longer used
**Then** `pipeline_runs` should be marked as legacy and eventually removed

### Epic 8: Admin Dashboard and Project Membership Management

Admins can manage users, projects, memberships, and admin-only routing through a dedicated dashboard.

**FRs covered:** FR16, FR16a

### Story 8.1: Admin Dashboard Routing and Access Control

As an admin,
I want to be routed directly to the admin dashboard and protected from standard workspace flow,
So that I can manage users and projects without entering the pipeline workspace.

**Acceptance Criteria:**

**Given** an authenticated user has the admin role
**When** login routing completes
**Then** the frontend routes the user directly to the admin dashboard
**And** the admin does not enter Alice project selection or the standard workspace flow

**Given** an authenticated standard user attempts to access the admin dashboard route
**When** route authorization is evaluated
**Then** access is denied
**And** the user remains in or is redirected to the standard workspace flow

**Given** an unauthenticated request targets an admin API endpoint
**When** backend authorization is evaluated
**Then** the request is rejected as unauthorized

**Given** an authenticated non-admin request targets an admin API endpoint
**When** backend authorization is evaluated
**Then** the request is rejected as forbidden without exposing admin-only data

### Story 8.2: Admin User Management

As an admin,
I want to view and create local user accounts,
So that I can control who can access the AI QA Automation system.

**Acceptance Criteria:**

**Given** an authenticated admin opens user management
**When** the frontend requests the user list
**Then** the backend returns users with id, email, display name, role, status, and project memberships
**And** password hashes and secret values are never returned

**Given** an authenticated admin submits a new user with email, display name, role, and initial password
**When** the backend validates the request
**Then** a user is created with the password stored only as a secure hash
**And** duplicate emails are rejected with a safe validation message

**Given** the user management screen is displayed
**When** the admin views available actions
**Then** self-service registration is not shown
**And** user creation is available only to admins

### Story 8.3: Admin Project Management

As an admin,
I want to create, rename, delete, and list projects,
So that I can maintain the project workspace structure.

**Acceptance Criteria:**

**Given** an authenticated admin opens project management
**When** the frontend requests the project list
**Then** the backend returns all projects with id, name, timestamps, and membership summary

**Given** an authenticated admin creates a project
**When** the backend validates the project name and Confluence base URL
**Then** the project is created and appears in the admin project list
**And** duplicate or blank project names are rejected with a clear validation message
**And** a missing or blank Confluence base URL is rejected with a clear validation message

**Given** an authenticated admin renames a project
**When** the backend validates the update
**Then** the project name is updated consistently in subsequent project and membership views

**Given** an authenticated admin deletes a project
**When** the backend validates deletion
**Then** the project is removed from assignable project lists
**And** affected standard users no longer see the deleted project as accessible

### Story 8.4: Project Membership Assignment

As an admin,
I want to assign users to projects and remove users from projects,
So that each user can access only authorized project workspaces.

**Acceptance Criteria:**

**Given** users and projects exist
**When** an admin assigns a user to a project
**Then** the membership is stored in the project membership table
**And** the user can see the project in their accessible project list after login or refresh

**Given** a user is already assigned to a project
**When** an admin attempts to assign the same membership again
**Then** the system prevents duplicate membership records
**And** the UI remains consistent after refresh

**Given** an admin removes a user from a project
**When** the removal is saved
**Then** the user no longer sees that project in their accessible project list
**And** thread access enforcement from Epic 7 applies to project-bound conversations

**Given** a standard user attempts to assign or remove memberships
**When** backend authorization is evaluated
**Then** the request is rejected as forbidden

### Story 8.5: Admin Dashboard UI Layout

As an admin,
I want a clear dashboard for managing projects, users, and memberships,
So that I can perform administrative tasks efficiently.

**Acceptance Criteria:**

**Given** an authenticated admin is on the dashboard
**When** the dashboard loads
**Then** the admin's email, display name, and role are displayed near a functional Logout button
**And** logout clears the authenticated session and returns the user to login

**Given** the dashboard is displayed
**When** the admin reviews the layout
**Then** projects are shown in a left-side management area with create, rename, and delete actions
**And** users are shown in a right-side management area with project membership controls

**Given** the admin views a user card
**When** the user has assigned projects
**Then** the card shows a Projects section with assigned project chips
**And** each assigned project can be removed through an `x` action

**Given** assignable projects exist
**When** the admin clicks the add-project action for a user
**Then** the UI allows selecting an unassigned project and assigning it to the user

**Given** the user management area is displayed
**When** the admin needs to create a user
**Then** a Create User form is available with Email, Display Name, Role, and Initial Password fields
**And** a disabled "Sync existing company's users" button explains that the feature is not available yet

### Story 8.6: Admin E2E Test Execution

As an admin,
I want to trigger an automated E2E test run from the dashboard,
So that I can visually monitor the system's health in real-time and review the test reports.

**Acceptance Criteria:**

**Given** an authenticated admin is on the dashboard
**When** they click "Run E2E Tests"
**Then** the backend triggers the E2E test suite using Playwright in headed mode with slow motion
**And** the admin can observe the browser execution (via UI or visual streaming)

**Given** the E2E test run completes
**When** the report is generated
**Then** the report file is automatically downloaded to the admin's client machine

### Story 8.7: Lock Down Public Self-Service Registration Endpoint

As a security-conscious system,
I want the public `POST /auth/register` endpoint removed or gated to admins,
So that user accounts can only be created by admins, fully satisfying the admin-only user-management requirement (FR16, Story 8.2 AC3).

**Context:** Story 8.2 AC3 requires that "self-service registration is not shown" and "user creation is available only to admins." The authenticated UI satisfies this, but a public, unauthenticated `POST /auth/register` endpoint still exists (whitelisted in `PUBLIC_PATHS`) and creates standard users without admin authorization. This endpoint is currently relied upon by every Epic 7 E2E spec (`registerStandardUser`) to bootstrap test users, so removing it is a breaking change for the test suite that must be handled here.

**Acceptance Criteria:**

**Given** an unauthenticated client calls `POST /auth/register`
**When** backend authorization is evaluated
**Then** the request is rejected (endpoint removed, disabled, or admin-gated)
**And** no user account is created without admin authorization

**Given** the E2E test suite previously bootstrapped users via `POST /auth/register`
**When** the registration endpoint is locked down
**Then** the affected E2E specs are migrated to a replacement bootstrap path (e.g. seeding via an admin token calling `POST /api/admin/users`)
**And** the full E2E suite passes against the live stack

**Given** the registration endpoint is gated rather than removed
**When** a standard or unauthenticated caller attempts it
**Then** the request is rejected as forbidden/unauthorized without leaking whether an email exists
**And** only admins can create users through any path

### Epic 9: Per-User Secret Management and Dynamic AI Provider Setup

Users can securely provide AI/MCP credentials, rotate them, and let Alice validate provider connections, discover available models, and assign valid models to downstream agents.

**FRs covered:** FR14, FR14a, FR14b, FR15, FR15a, FR15b, FR36, FR54, FR55, FR56, FR57, FR58, FR59, FR60

### Story 9.1: Encrypted Per-User Secret Storage Foundation

As a project user,
I want my AI provider keys and MCP key stored securely under my own account,
So that my credentials are isolated from other users and never stored in plaintext configuration.

**Acceptance Criteria:**

**Given** a user submits an AI provider API key or MCP key
**When** the backend stores the value
**Then** the secret is encrypted using `AppSettings.user_secrets_encryption_key` before persistence
**And** the plaintext secret is not stored in `.env`, plaintext JSON columns, logs, messages, artifacts, or WebSocket payload history

**Given** the backend stores secret records
**When** secret metadata is queried
**Then** encrypted secret values are stored separately from non-secret metadata such as provider name, status, last updated timestamp, and owning user id

**Given** `USER_SECRETS_ENCRYPTION_KEY` is missing or invalid
**When** the application starts
**Then** startup validation fails fast with an actionable configuration error
**And** the encryption key is never stored in PostgreSQL

### Story 9.2: Secret Status and Replacement API

As a project user,
I want to see whether my credentials are configured and replace expired keys,
So that I can recover from provider/MCP authentication failures without admin support.

**Acceptance Criteria:**

**Given** a user has stored provider or MCP secrets
**When** the frontend requests secret status
**Then** the API returns only non-secret status fields such as configured/missing, provider name, last updated, and validation state
**And** no stored secret value or masked reversible token is returned

**Given** a user submits a replacement key
**When** the backend validates and stores it
**Then** the previous encrypted value is replaced or superseded securely
**And** future runs use the new value

**Given** a user attempts to view an existing key
**When** the UI renders credential status
**Then** the stored key is never displayed
**And** the UI provides replacement flow only

### Story 9.3: Provider Adapter Interface and Connection Validation

As a project user,
I want Alice to validate my selected AI provider connection,
So that I know the provider credentials and endpoint work before running the pipeline.

**Acceptance Criteria:**

**Given** a supported provider is selected
**When** Alice validates the connection
**Then** the provider adapter calls `validate_connection(credentials, base_url)`
**And** the result is normalized into success/failure status, provider name, and actionable non-secret error guidance

**Given** validation fails due to invalid credentials, unreachable endpoint, or provider error
**When** Alice presents the result
**Then** the user sees a recovery message without stack traces, raw provider responses, or secrets

**Given** provider base URLs are needed
**When** adapter configuration is loaded
**Then** deployment-level base URLs come from system environment/configuration
**And** user-specific secrets come only from encrypted per-user secret storage

### Story 9.4: Dynamic Model Discovery

As a project user,
I want Alice to discover available models from my selected provider,
So that downstream agents use models that actually exist for my credentials/server.

**Acceptance Criteria:**

**Given** provider validation succeeds
**When** Alice performs model discovery
**Then** the provider adapter calls `list_models(credentials, base_url)` where supported
**And** the response is normalized into `DiscoveredModel` values, categorized clearly into 'Available' and 'Unavailable' (quota exceeded, not supported, outdated)

**Given** model discovery returns 0 'Available' models (or fails entirely)
**When** Alice evaluates configuration readiness
**Then** Alice stops the thread
**And** Alice shows the message: "No available model to proceed. Please check your subscription then create a new thread to continue."

**Given** static model names are available as ranking hints
**When** Alice selects models
**Then** static names are used only after provider discovery verifies availability

### Story 9.5: Agent Model Assignment Review

As a project user,
I want to review which discovered model Alice assigns to each downstream agent,
So that I can approve or reject the configuration before generation begins.

**Acceptance Criteria:**

**Given** Alice has discovered available models
**When** model assignment runs
**Then** Alice assigns the most suitable models ONLY from the 'Available' group
**And** each assignment includes agent name, selected model, selected temperature or runtime parameters, and non-secret selection rationale

**Given** Alice presents the configuration review
**When** the review is displayed
**Then** the user sees provider connection status, discovered model summary, agent model needs, selected model per downstream agent, and rationale
**And** no provider key, MCP key, or secret material is displayed

**Given** the user rejects the review
**When** feedback is submitted
**Then** Alice returns to configuration adjustment without persisting an approved configuration as ready

### Story 9.6: Runtime Secret Resolution for Agent Runs

As a system operator,
I want agents to resolve user secrets only at execution time,
So that secrets are used securely without being exposed through application data.

**Acceptance Criteria:**

**Given** an agent run starts for a thread
**When** downstream agents need provider or MCP credentials
**Then** the backend derives the user from the thread owner and resolves that user's encrypted secrets at execution time
**And** secrets are decrypted only in memory for the minimum required operation

**Given** API responses, WebSocket messages, persisted messages, artifacts, generated files, audit logs, or execution metadata are produced
**When** they include provider or MCP information
**Then** all secret values are omitted or redacted
**And** secret leakage tests verify no plaintext secret appears in those outputs

**Given** a user's required secret is missing or invalid at execution time
**When** an agent attempts to run
**Then** execution is blocked with a user-actionable credential status message
**And** no partial output contains secret material

### Story 9.7: Saved Provider Configuration and Rotation Behavior

As a returning project user,
I want my non-secret provider/model configuration remembered while secret rotation applies only to future runs,
So that setup is convenient without rewriting conversation history.

**Acceptance Criteria:**

**Given** a user approves Alice provider/model configuration
**When** the configuration is saved
**Then** PostgreSQL stores selected provider, selected model assignments, non-secret runtime settings, and selection rationale
**And** encrypted secret values remain in separate per-user secret storage

**Given** a user starts a future thread
**When** saved provider configuration is valid
**Then** Alice may initialize configuration silently or expose it through explicit UI inspection/change action
**And** returning users are not shown noisy saved-config chat messages automatically

**Given** a user rotates an AI provider or MCP secret
**When** future runs execute
**Then** future runs use the rotated value
**And** existing thread messages, conversation history, and previous run metadata remain unchanged

### Epic 10: Project Artifact Collaboration and Realtime Sync

Project members can share, browse, edit, delete, and receive realtime updates for project-level artifacts stored in SeaweedFS and tracked in PostgreSQL.

**FRs covered:** FR35, FR42, FR43, FR44, FR45, FR46, FR52, FR61, FR62, FR63, FR64, FR65, FR66, FR67

### Story 10.1: Project Artifact Storage Foundation

As a project member,
I want project artifacts stored under a shared project-level structure,
So that generated files are available to authorized collaborators in the same project.

**Acceptance Criteria:**

**Given** a project exists in PostgreSQL
**When** artifact storage is initialized or queried for that project
**Then** the logical folders `projects/{project_id}/requirements/`, `projects/{project_id}/test_cases/`, and `projects/{project_id}/test_scripts/` are available
**And** artifact bytes are stored in SeaweedFS or the configured S3-compatible artifact backend

**Given** an artifact is created
**When** metadata is persisted
**Then** PostgreSQL stores project id, artifact kind, storage path, creator, updater, timestamps, optional originating thread, and optional originating agent run
**And** artifact metadata is separate from artifact bytes

**Given** a user is not assigned to a project
**When** they attempt to access that project's artifact storage
**Then** access is denied before reading or writing artifact metadata or bytes

### Story 10.2: Artifact List and Empty Folder Browsing

As a project member,
I want to browse project artifact folders even when they are empty,
So that I understand the expected artifact structure before outputs exist.

**Acceptance Criteria:**

**Given** a PostgreSQL project exists but SeaweedFS has no objects for it
**When** an authorized project member opens the Project / Artifacts section
**Then** the UI shows the required empty folders: `requirements`, `test_cases`, and `test_scripts`
**And** each folder is clearly marked as empty

**Given** artifacts exist under one or more required folders
**When** the artifact tree is loaded
**Then** the API returns folders and artifact entries with names, types, updated timestamps, and creator/updater metadata
**And** entries are scoped only to the selected project

**Given** a user is assigned to multiple projects
**When** a thread has a bound project
**Then** the artifact tree shows only artifacts for the thread's selected project

### Story 10.3: Artifact Read and Preview Access

As a project member,
I want to open and preview artifacts created by other members of the same project,
So that collaboration is possible across generated QA outputs.

**Acceptance Criteria:**

**Given** an artifact exists in a project
**When** an authorized project member opens it
**Then** the backend verifies project membership before returning metadata or bytes
**And** the frontend renders supported Markdown, Mermaid, image, and script previews where applicable

**Given** the artifact was created by another project member
**When** the authorized user opens it
**Then** access is allowed based on project membership rather than creator ownership
**And** creator/updater metadata remains visible

**Given** a user is not assigned to the artifact's project
**When** they attempt direct artifact access
**Then** access is denied without exposing artifact metadata or storage path details

### Story 10.4: Artifact Edit, Delete, and Version Metadata

As a project member,
I want to edit and delete shared project artifacts,
So that the team can refine generated outputs collaboratively.

**Acceptance Criteria:**

**Given** an authorized project member edits a supported artifact
**When** the edit is saved
**Then** artifact bytes are updated through the artifact service
**And** metadata records the updater and updated timestamp

**Given** version metadata is enabled for an artifact
**When** a user edits the artifact
**Then** the previous version metadata is preserved with timestamp, updater, and storage reference where supported
**And** rollback behavior is not implemented in MVP

**Given** an authorized project member deletes an artifact
**When** deletion is confirmed by the application action
**Then** the artifact is removed or marked deleted consistently in metadata and storage
**And** direct external SeaweedFS notifications are not required for MVP

### Story 10.5: Agent Artifact Service Integration

As a system developer,
I want all agents to read and write artifacts through the artifact service,
So that authorization, metadata, storage, audit, and realtime events stay consistent.

**Acceptance Criteria:**

**Given** Bob, Mary, Sarah, or Jack needs to save output
**When** the agent writes requirements, test cases, scripts, screenshots, or reports
**Then** the agent calls the artifact service rather than writing directly to local workspace paths or SeaweedFS clients
**And** artifact metadata includes originating thread and agent run where available

**Given** an agent needs input from a previous stage
**When** the agent reads requirements, test cases, or scripts
**Then** it queries project-scoped artifacts through the artifact service
**And** it only receives artifacts authorized for the thread's bound project

**Given** legacy workspace path assumptions still exist
**When** agent artifact integration is implemented
**Then** compatibility adapters are isolated behind the artifact service or removed where safe
**And** no new direct workspace-path dependency is introduced

### Story 10.6: Project-Scoped Artifact Change Events

As a project member,
I want artifact changes to emit realtime events,
So that collaborators can see project artifact updates without manual reload.

**Acceptance Criteria:**

**Given** an application-managed artifact create, update, delete, or metadata-change operation succeeds
**When** the transaction completes
**Then** the backend emits an artifact change event
**And** the event includes `project_id`, artifact identifier, change type, and timestamp

**Given** an artifact operation fails or is unauthorized
**When** no artifact state changes
**Then** no artifact change event is emitted

**Given** multiple users are connected through WebSocket
**When** an artifact event is emitted
**Then** only users assigned to the changed project are eligible to receive the event

### Story 10.7: Realtime Artifact Refresh UX

As a project member,
I want the visible artifact tree to refresh when relevant artifact events occur,
So that I can see updates without losing my current chat context.

**Acceptance Criteria:**

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

### Story 10.8: Open Artifact Update/Delete Notice

As a project member,
I want to be notified if the artifact I am viewing changes or is deleted,
So that I can avoid reviewing stale content.

**Acceptance Criteria:**

**Given** a user has an artifact preview open
**When** that artifact is updated by another application-managed operation
**Then** the UI shows a non-disruptive notice that a newer version is available
**And** the user can choose to reload the preview or keep viewing the current content

**Given** a user has an artifact preview open
**When** that artifact is deleted
**Then** the UI shows a non-disruptive notice that the artifact was deleted
**And** the user can close the preview without losing chat state

**Given** an artifact notice is shown
**When** the user ignores it
**Then** chat messages, input text, current step, and scroll position remain unchanged

### Epic 11: Confluence and Jira Requirements Extraction with Bob

Users can start from Confluence/Jira sources and have Bob extract readable requirements/test-case source content through MCP with reviewable output.

**FRs covered:** FR1, FR2, FR3, FR4, FR10, FR23, FR24, FR27

### Story 11.1: MCP Client Foundation for Confluence and Jira

As a system developer,
I want a shared MCP client for Confluence and Jira access,
So that Bob can retrieve source requirements through the approved on-premises MCP server.

**Acceptance Criteria:**

**Given** Bob needs to access Confluence or Jira
**When** the MCP client initializes
**Then** it uses the current user's encrypted MCP key resolved at execution time
**And** it connects to the configured on-premises MCP server URL from system configuration

**Given** the MCP server is reachable
**When** the client connects
**Then** it discovers available Confluence and Jira tools where supported
**And** unavailable tools are reported as actionable capability errors

**Given** MCP connection, authentication, or transient errors occur
**When** Bob attempts MCP access
**Then** retry logic uses max 3 attempts with safe backoff
**And** failures raise custom MCP errors with user-safe messages and no secret leakage

### Story 11.2: Bob Confluence URL Intake and Pipeline Trigger

As a QA user,
I want to start requirements extraction by giving Bob a Confluence page URL,
So that the QA automation pipeline begins from existing documented test cases.

**Acceptance Criteria:**

**Given** a thread is bound to a project and Alice configuration is ready
**When** Bob starts
**Then** Bob asks for a Confluence page URL as the required pipeline trigger
**And** Bob optionally allows a Jira URL or Jira ticket reference if Jira extraction is enabled

**Given** the user submits a Confluence URL
**When** Bob validates the input
**Then** the URL is accepted only if it matches configured Confluence URL rules
**And** invalid URLs produce a clear correction message without starting extraction

**Given** required project/thread context, provider configuration, or MCP credential status is missing
**When** the user attempts to start Bob extraction
**Then** Bob blocks extraction and explains the required recovery action

### Story 11.3: Confluence Content Retrieval and Parsing

As a QA user,
I want Bob to retrieve and parse Confluence content,
So that natural-language test cases become clean, reviewable requirement artifacts.

**Acceptance Criteria:**

**Given** a valid Confluence page URL is provided
**When** Bob calls MCP Confluence tools
**Then** the full page content and relevant metadata are retrieved
**And** page retrieval supports configured descendant/page discovery where available

**Given** Confluence content contains natural-language test cases
**When** the parser processes the content
**Then** it extracts readable requirements/test-case source content into clean Markdown
**And** headings, lists, and tables are preserved in a reviewable format

**Given** Confluence content includes embedded macros, attachments, images, or non-standard formatting
**When** parsing occurs
**Then** supported content is normalized or preserved by reference
**And** unsupported content is surfaced as warnings rather than silently dropped

### Story 11.4: Jira Requirements Retrieval

As a QA user,
I want Bob to retrieve test-related requirements from Jira,
So that Confluence source content can be supplemented with ticket-level context.

**Acceptance Criteria:**

**Given** the user provides a Jira URL, project key, or ticket reference
**When** Bob validates Jira input
**Then** Jira extraction starts only if Jira MCP tools are available and user MCP credentials are configured

**Given** Jira extraction starts
**When** Bob calls MCP Jira tools
**Then** test-related requirements are retrieved from matching Jira tickets
**And** retrieved ticket content includes relevant title, description, acceptance criteria, labels/status where available, and source reference

**Given** Jira input is optional or unavailable
**When** Confluence extraction can continue without Jira
**Then** Bob continues Confluence-only extraction and reports Jira as skipped or unavailable without failing the whole extraction

### Story 11.5: Input Quality Detection Before Generation

As a QA user,
I want vague or incomplete source requirements flagged before downstream generation,
So that I can decide whether to improve documentation before generating test cases and scripts.

**Acceptance Criteria:**

**Given** Bob has parsed Confluence/Jira source content
**When** quality detection runs
**Then** it flags issues such as vague steps, missing expected results, missing preconditions, ambiguous UI references, or unsupported content warnings

**Given** quality issues are detected
**When** Bob presents extraction results
**Then** the user sees specific warnings tied to source sections or test cases
**And** the warning explains the likely impact on downstream test case/script generation

**Given** quality issues exist
**When** the user reviews output
**Then** the user can still approve and proceed
**And** the approval records that warnings were acknowledged

### Story 11.6: Bob Reviewable Extraction Output

As a QA user,
I want to review Bob's extracted Confluence/Jira output before it is saved,
So that I can verify source requirements were captured correctly.

**Acceptance Criteria:**

**Given** Bob completes extraction and parsing
**When** review state is presented
**Then** the UI shows source reference links and rendered extracted Markdown content
**And** extraction warnings are visible in the review content

**Given** multiple pages or tickets are extracted
**When** the user reviews output
**Then** the user can navigate between extracted items with Next/Previous controls
**And** approval applies to the current item or clear batch scope shown by the UI

**Given** the user rejects an extracted item with feedback
**When** feedback is submitted
**Then** Bob reprocesses that item where possible
**And** Bob acknowledges the feedback conversationally before retrying

### Story 11.7: Requirements Artifact Save

As a project member,
I want approved extracted requirements saved as project artifacts,
So that Mary and other project members can use them as shared source inputs.

**Acceptance Criteria:**

**Given** an extracted item is approved
**When** Bob saves it
**Then** the artifact service stores it under `projects/{project_id}/requirements/`
**And** artifact metadata includes source type, source URL/reference, creator, updater, originating thread, originating agent run, timestamp, warnings, and artifact kind

**Given** saved requirement artifacts exist
**When** Mary or a project member requests requirements for the selected project
**Then** the artifacts are available through project-scoped artifact queries
**And** direct workspace path reads are not required

**Given** saving fails
**When** Bob reports the failure
**Then** partial output is not corrupted
**And** the user receives a clear retry or recovery message

### Epic 12: Test Case Generation with Mary

Users can transform extracted requirements into structured natural-language test cases optimized for browser automation, then review, approve, or reject them.

**FRs covered:** FR5, FR22, FR27

### Story 12.1: Test Case Generation Input Selection

As a QA user,
I want Mary to use approved extracted requirements for the current project/thread,
So that generated test cases are based only on reviewed source material.

**Acceptance Criteria:**

**Given** approved requirement artifacts exist for the selected project
**When** Mary starts test case generation
**Then** Mary loads only project-scoped approved requirements through the artifact service
**And** direct workspace path reads are not used

**Given** the current thread has source requirement artifacts
**When** Mary prepares generation input
**Then** artifacts from the originating thread are prioritized
**And** the user can confirm or adjust the selected requirement inputs before generation

**Given** no approved requirement artifact is available
**When** Mary is asked to generate test cases
**Then** Mary blocks generation and explains that Bob extraction and approval must happen first

### Story 12.2: Browser-Automation-Oriented Test Case Generation

As a QA user,
I want Mary to transform requirements into structured natural-language test cases,
So that Sarah can later convert them into browser automation scripts.

**Acceptance Criteria:**

**Given** approved requirement inputs are selected
**When** Mary generates test cases
**Then** each generated test case includes title, objective, preconditions, test data, steps, expected results, and source requirement references

**Given** a requirement describes browser behavior
**When** Mary creates test steps
**Then** user actions and expected UI outcomes are written clearly enough for Playwright automation
**And** ambiguous UI targets are preserved as warnings instead of invented selectors

**Given** multiple requirements are processed
**When** generation completes
**Then** Mary groups test cases by source requirement or feature area
**And** each test case remains independently reviewable

### Story 12.3: Confidence Scoring for Generated Test Cases

As a QA user,
I want Mary to score confidence for generated test cases,
So that low-confidence outputs receive explicit review before script generation.

**Acceptance Criteria:**

**Given** Mary generates a test case
**When** quality analysis runs
**Then** the test case receives a confidence score or confidence level
**And** confidence rationale is stored with the generated item

**Given** source content is incomplete, vague, contradictory, or includes unresolved Bob warnings
**When** Mary scores the generated test case
**Then** the test case is flagged as low confidence
**And** the specific causes are shown to the reviewer

**Given** low-confidence test cases exist
**When** the user attempts to proceed to Sarah
**Then** the workflow requires explicit approval or regeneration decision for those test cases

### Story 12.4: Mary Review Workflow

As a QA user,
I want to review, approve, reject, and give feedback on Mary’s generated test cases,
So that only validated natural-language test cases become script-generation inputs.

**Acceptance Criteria:**

**Given** Mary generated one or more test cases
**When** the review UI opens
**Then** the user can review each test case with source requirement references and confidence warnings visible

**Given** the user approves a generated test case
**When** approval is submitted
**Then** the test case becomes eligible for Sarah script generation
**And** the approval is recorded with user and timestamp metadata

**Given** the user rejects a generated test case with feedback
**When** feedback is submitted
**Then** Mary regenerates or revises the affected test case where possible
**And** prior rejected output is not treated as approved input

### Story 12.5: Test Case Artifact Save

As a project member,
I want approved generated test cases saved as project artifacts,
So that Sarah and other project members can use them as shared automation inputs.

**Acceptance Criteria:**

**Given** a generated test case is approved
**When** Mary saves it
**Then** the artifact service stores it under `projects/{project_id}/test_cases/`
**And** artifact metadata includes source requirement artifact IDs, confidence data, approval status, creator, updater, originating thread, originating agent run, and timestamp

**Given** saved test case artifacts exist
**When** Sarah requests approved test cases for the selected project
**Then** Sarah receives only project-scoped approved test case artifacts through artifact service queries

**Given** saving fails
**When** Mary reports the failure
**Then** partial output is not marked approved or available to Sarah
**And** the user receives a clear retry or recovery message

### Epic 13: Playwright Script Generation and Human Review with Sarah

Users can generate executable Python Playwright scripts from approved test cases, review them side-by-side with source, edit before approval, and enforce stable selectors/assertions.

**FRs covered:** FR6, FR7, FR8, FR9, FR12, FR13, FR19, FR20, FR21, FR22

### Story 13.1: Approved Test Case Input Selection

As a QA user,
I want Sarah to use only approved test cases for script generation,
So that generated Playwright scripts are based on validated test design.

**Acceptance Criteria:**

**Given** approved test case artifacts exist for the selected project
**When** Sarah starts script generation
**Then** Sarah loads only project-scoped approved test cases through the artifact service
**And** rejected or draft test cases are excluded

**Given** the current thread has approved test case artifacts
**When** Sarah prepares generation input
**Then** artifacts from the originating thread are prioritized
**And** the user can confirm or adjust selected test cases before generation

**Given** no approved test case artifact is available
**When** Sarah is asked to generate scripts
**Then** Sarah blocks generation and explains that Mary generation and approval must happen first

### Story 13.2: Python Playwright Script Generation

As a QA user,
I want Sarah to generate Python Playwright scripts from approved test cases,
So that each approved test case can become an executable browser automation file.

**Acceptance Criteria:**

**Given** approved test cases are selected
**When** Sarah generates scripts
**Then** one Python Playwright script is generated per approved test case
**And** generated scripts use project-standard Python and Playwright conventions

**Given** a generated script is created
**When** its content is inspected
**Then** it includes a clear test function, browser/page interactions, assertions, and comments or metadata linking back to the source test case

**Given** script generation encounters missing details
**When** Sarah cannot safely infer an action
**Then** Sarah inserts an explicit review warning or TODO marker rather than inventing unsafe behavior

### Story 13.3: Stable Selector and Assertion Mapping

As a QA user,
I want Sarah to prefer stable selectors and concrete assertions,
So that generated scripts are maintainable and reliable.

**Acceptance Criteria:**

**Given** a generated script needs to locate UI elements
**When** Sarah maps test steps to Playwright selectors
**Then** selectors prefer `data-testid`, role-based locators, accessible names, labels, and stable text in that priority order
**And** brittle selectors are flagged for review

**Given** a test case includes expected results
**When** Sarah generates script assertions
**Then** expected results are converted into concrete Playwright assertions where possible
**And** unsupported or ambiguous expected results remain visible as review warnings

**Given** generated scripts include warnings
**When** the user reviews them
**Then** warnings are tied to source test steps or expected results

### Story 13.4: Browser SSO Session Compatibility

As a QA user,
I want generated scripts to support browser execution with an existing authenticated session,
So that tests can run against on-prem applications using enterprise SSO without storing credentials.

**Acceptance Criteria:**

**Given** a test target requires authenticated browser access
**When** Sarah generates the script
**Then** the script supports configured browser context/session reuse
**And** it does not store, print, or hardcode usernames, passwords, tokens, cookies, or session secrets

**Given** browser session configuration is unavailable
**When** Sarah generates a script that likely requires authentication
**Then** the script or review warning identifies required SSO/session setup before execution

**Given** scripts are saved or displayed
**When** content is rendered in the UI or artifact store
**Then** no credential values or secret-like data are included

### Story 13.5: Sarah Side-by-Side Review UX

As a QA user,
I want to review generated scripts beside their source test cases,
So that I can verify traceability and correctness before approval.

**Acceptance Criteria:**

**Given** Sarah generated one or more scripts
**When** the review UI opens
**Then** the source test case is shown on one side and generated Python script on the other side
**And** generated script content has syntax highlighting

**Given** multiple generated scripts exist
**When** the user reviews them
**Then** the user can navigate between script/test-case pairs with Next/Previous controls
**And** review status is visible for each item

**Given** the generated script contains warnings or TODO markers
**When** the script is reviewed
**Then** warnings are visible without hiding the script content

### Story 13.6: Script Edit Before Approval

As a QA user,
I want to edit generated scripts before approval,
So that I can correct selectors, assertions, or implementation details before execution.

**Acceptance Criteria:**

**Given** a generated script is open for review
**When** the user edits the script content
**Then** the edited content is retained in review state
**And** unsaved changes are clearly indicated

**Given** edited script content is submitted for validation
**When** the validation runs
**Then** the system checks basic Python syntax and disallows known unsafe patterns configured for the project
**And** validation errors are shown with actionable messages

**Given** validation passes
**When** the user approves the edited script
**Then** the approved artifact uses the edited script content, not the original generated draft

### Story 13.7: Script Approval, Rejection, and Regeneration

As a QA user,
I want to approve, reject, or regenerate generated scripts with feedback,
So that only reviewed scripts become executable by Jack.

**Acceptance Criteria:**

**Given** a generated script is reviewed
**When** the user approves it
**Then** the script becomes eligible for Jack execution
**And** approval metadata records user and timestamp

**Given** the user rejects a script with feedback
**When** feedback is submitted
**Then** Sarah regenerates or revises the affected script where possible
**And** the rejected script is not available for Jack execution

**Given** a script remains unapproved
**When** Jack requests executable scripts
**Then** that script is excluded from execution input

### Story 13.8: Test Script Artifact Save

As a project member,
I want approved Playwright scripts saved as project artifacts,
So that Jack and other project members can run or inspect them later.

**Acceptance Criteria:**

**Given** a script is approved
**When** Sarah saves it
**Then** the artifact service stores it under `projects/{project_id}/test_scripts/`
**And** one approved script artifact is saved per source test case

**Given** script artifact metadata is saved
**When** it is inspected
**Then** it includes source test case artifact ID, output path or logical path, approval status, creator, updater, originating thread, originating agent run, validation status, and timestamp

**Given** Jack requests executable scripts for the selected project
**When** approved script artifacts exist
**Then** Jack receives only approved project-scoped script artifacts through artifact service queries

### Epic 14: Audit, Metrics, and Leadership Visibility

Admins and leadership can see audit trail, execution metrics, success rates, effort reduction, LLM cost tracking, and provider comparison backlog support.

**FRs covered:** FR17, FR25, FR28, FR29

### Story 14.1: Audit Event Model and Persistence

As an admin,
I want pipeline and security-relevant actions recorded as structured audit events,
So that activity can be reviewed consistently across projects and agents.

**Acceptance Criteria:**

**Given** a user, agent, or admin performs an auditable action
**When** the action completes or fails
**Then** an audit event is persisted with actor, project, thread, agent/run where applicable, action type, target type, target ID, timestamp, result, and safe metadata

**Given** audit metadata is persisted
**When** the event includes provider, model, artifact, execution, or admin context
**Then** only non-secret identifiers and safe summaries are stored
**And** API keys, tokens, cookies, passwords, and decrypted secret values are never stored

**Given** audit events are stored
**When** they are queried later
**Then** events retain immutable core fields needed for compliance and troubleshooting

### Story 14.2: Pipeline Audit Logging

As an admin,
I want all major pipeline actions logged,
So that I can trace who read, generated, reviewed, approved, edited, executed, or exported QA artifacts.

**Acceptance Criteria:**

**Given** Bob retrieves or saves requirement artifacts
**When** the operation occurs
**Then** audit logs record the user, project, thread, agent run, source reference, artifact ID where available, and result

**Given** Mary or Sarah generates, edits, approves, rejects, or saves outputs
**When** the operation occurs
**Then** audit logs record the action, affected artifact/test case/script, review decision, actor, timestamp, and result

**Given** Jack executes scripts or produces reports
**When** execution starts, completes, or fails
**Then** audit logs record execution scope, browser where applicable, result summary, report artifact ID, and duration

### Story 14.3: Admin Audit Trail View

As an admin,
I want to view and filter audit events,
So that I can investigate project activity and compliance questions.

**Acceptance Criteria:**

**Given** an authenticated admin opens the audit trail
**When** audit data loads
**Then** the UI shows events with timestamp, actor, project, action, target, result, and safe summary

**Given** many audit events exist
**When** the admin filters the view
**Then** filtering supports user, project, thread, agent, action type, artifact, result, and time range

**Given** a non-admin user attempts to access audit trail data
**When** the request is made
**Then** access is denied and no audit event details are returned

### Story 14.4: Execution Metrics Aggregation

As a QA lead,
I want script execution metrics aggregated over time,
So that I can understand automation reliability and coverage trends.

**Acceptance Criteria:**

**Given** Jack execution results exist
**When** metrics aggregation runs
**Then** pass/fail counts, success rate, duration, execution count, browser breakdown, and project/thread summaries are calculated

**Given** new execution results are saved
**When** metrics are requested
**Then** the dashboard reflects current results or clearly indicates last aggregation time

**Given** execution metrics are aggregated
**When** results include failed or skipped tests
**Then** failure and skip counts remain distinguishable from passed tests

### Story 14.5: Leadership Metrics Dashboard

As a leadership or admin user,
I want a metrics dashboard for QA automation impact,
So that I can understand success rate, usage, and effort reduction indicators.

**Acceptance Criteria:**

**Given** a leadership/admin user opens the metrics dashboard
**When** project metrics load
**Then** the UI shows execution volume, success rate, failure trends, generated artifact counts, approved artifact counts, and recent pipeline activity

**Given** effort reduction data is estimated
**When** it is shown in the dashboard
**Then** the calculation basis is visible as a safe explanatory summary
**And** values are labeled as estimates unless based on configured measured values

**Given** a user without required admin/leadership permission opens the dashboard
**When** the request is made
**Then** restricted metrics are denied or scoped according to their project permissions

### Story 14.6: LLM Cost Tracking

As an admin,
I want estimated LLM usage and costs tracked by provider and model,
So that I can monitor cost trends without exposing secrets.

**Acceptance Criteria:**

**Given** an agent run calls an LLM provider
**When** usage metadata is returned or estimated
**Then** token counts, provider name, model name, project, thread, agent, run, timestamp, and estimated cost are recorded where available

**Given** provider usage metadata is incomplete
**When** cost tracking records the run
**Then** the system stores available usage fields and marks missing estimates clearly

**Given** cost data is displayed
**When** admins view it
**Then** costs can be grouped by provider, model, project, agent, and time range
**And** no API key, endpoint secret, request payload secret, or decrypted credential is exposed

### Story 14.7: Provider Comparison Backlog Support

As an admin,
I want normalized provider/model metrics stored for future comparison,
So that the product can later support provider quality and cost comparison without redesigning telemetry.

**Acceptance Criteria:**

**Given** agent runs execute with different providers or models
**When** run metadata is persisted
**Then** normalized fields capture provider, model, run type, token usage, estimated cost, latency, success/failure, quality/confidence signals where available, and related artifact IDs

**Given** provider comparison UI is not fully implemented in MVP
**When** metrics are stored
**Then** the data model still supports later comparison by provider/model/project/agent/time range

**Given** stored provider comparison metrics are queried by admins
**When** the query is authorized
**Then** results return only safe metadata and aggregate summaries, not prompts containing secrets or confidential source content

### Epic 15: Test Execution and Reporting with Jack

Users can run generated Playwright scripts, collect execution results, and view success/failure reporting across supported browsers.

**FRs covered:** FR11, FR13, FR26

### Story 15.1: Approved Script Execution Input Selection

As a QA user,
I want Jack to execute only approved scripts for the selected project,
So that test runs use reviewed automation assets.

**Acceptance Criteria:**

**Given** approved script artifacts exist for the selected project
**When** Jack prepares an execution run
**Then** Jack loads only project-scoped approved script artifacts through the artifact service
**And** rejected, draft, or unapproved scripts are excluded

**Given** the current thread has approved script artifacts
**When** Jack prepares execution inputs
**Then** scripts from the originating thread are prioritized
**And** the user can confirm or adjust selected scripts before execution

**Given** no approved script artifacts are available
**When** Jack is asked to run tests
**Then** Jack blocks execution and explains that Sarah generation and approval must happen first

### Story 15.2: Playwright Execution Runner

As a QA user,
I want Jack to execute approved Python Playwright scripts,
So that I can validate generated tests against the target application.

**Acceptance Criteria:**

**Given** approved scripts are selected
**When** Jack starts execution
**Then** each selected Python Playwright script is executed in a controlled runner process
**And** the run captures pass/fail/error status, start time, end time, duration, and browser context

**Given** a script fails during execution
**When** the failure occurs
**Then** Jack captures the error message, stack trace where safe, and failure classification
**And** execution continues or stops according to configured run policy

**Given** execution completes
**When** results are persisted
**Then** each result is linked to its source script artifact, test case artifact where available, project, thread, and execution run ID

### Story 15.3: Configurable Execution Output Path

As a system administrator,
I want execution reports and run artifacts saved to configured project artifact locations,
So that outputs are organized consistently and do not rely on ad-hoc workspace writes.

**Acceptance Criteria:**

**Given** Jack produces execution outputs
**When** logs, reports, screenshots, traces, or result files are saved
**Then** they are written through the artifact service using configured project-scoped logical paths
**And** direct arbitrary filesystem writes are not required for application-managed outputs

**Given** output path configuration is missing or invalid
**When** Jack starts execution
**Then** startup/runtime validation reports a clear configuration error before output is lost

**Given** multiple execution runs exist
**When** outputs are saved
**Then** each run uses a unique logical run path and does not overwrite prior reports unless explicitly configured

### Story 15.4: Multi-Browser Execution Support

As a QA user,
I want Jack to run tests against configured browsers,
So that execution results reflect supported browser coverage.

**Acceptance Criteria:**

**Given** one or more browser targets are configured
**When** Jack runs selected scripts
**Then** execution can run against configured targets such as Chrome, Firefox, and Edge where available
**And** results are recorded separately by browser

**Given** a requested browser is unavailable in the runner environment
**When** execution starts
**Then** Jack reports that browser as unavailable with a clear reason
**And** other available configured browsers can still run if policy allows

**Given** browser execution requires an authenticated context
**When** a configured session is available
**Then** Jack uses the configured browser context/session without storing or logging credentials

### Story 15.5: Execution Result Report Generation

As a QA user,
I want Jack to generate structured execution reports,
So that I can understand test outcomes and diagnose failures.

**Acceptance Criteria:**

**Given** execution results exist
**When** Jack generates the report
**Then** the report includes run summary, per-test result, browser, duration, failure details, skipped/unavailable states, and linked source script/test case artifacts

**Given** screenshots, traces, logs, or attachments are available
**When** report artifacts are saved
**Then** they are linked from the execution report metadata
**And** unavailable attachments are represented as missing rather than breaking report generation

**Given** the report is saved
**When** project members retrieve it
**Then** it is accessible as a project-scoped artifact according to project membership permissions

### Story 15.6: Execution Report Review UX

As a QA user,
I want to view execution summaries and drill into details,
So that I can quickly understand pass/fail status and investigate failures.

**Acceptance Criteria:**

**Given** an execution report exists
**When** the user opens it
**Then** the UI shows overall pass/fail/error counts, success rate, duration, browser breakdown, and run metadata

**Given** individual test results exist
**When** the user selects a test result
**Then** the UI shows linked script, source test case, failure details, logs, screenshots/traces where available, and safe stack trace details

**Given** multiple reports exist for a project
**When** the user views execution history
**Then** reports are sorted by run time and filterable by project, thread, browser, result, and date range

### Epic 16: Conversational UX System and Accessibility

Users experience the workflow through the intended chat-based UI with named agents, stateful controls, rich review panels, progress, feedback, accessibility, and Alice-specific UX refinements.

**FRs covered:** Cross-cutting UX requirements supporting FR33, FR47-FR52, FR58, FR64-FR66

### Story 16.1: Agent-Based Conversational Shell

As a QA user,
I want the application to present the pipeline as a named-agent conversation,
So that I can understand which agent is guiding each step.

**Acceptance Criteria:**

**Given** the user opens a project thread
**When** the conversational UI loads
**Then** messages are displayed in a chat interface with agent names, avatars, timestamps, and role-appropriate message styling

**Given** the workflow reaches Alice, Bob, Mary, Sarah, or Jack
**When** the agent becomes active
**Then** the agent introduces or frames the current task in its expected role
**And** the UI preserves conversation history for the active thread

**Given** multiple agents contribute to a thread
**When** the user reviews prior messages
**Then** agent identity remains clear and distinguishable for each message

### Story 16.2: Stateful Workflow Controls

As a QA user,
I want the input area to change based on the current workflow state,
So that I see only relevant actions at each pipeline step.

**Acceptance Criteria:**

**Given** the workflow is waiting for source input
**When** Bob is active
**Then** the input area supports Confluence URL input and optional Jira input where enabled

**Given** the workflow is waiting for review
**When** requirements, test cases, scripts, or execution reports require a decision
**Then** the input area shows relevant approve, reject, feedback, regenerate, run, or export actions

**Given** an action is unavailable because required state is missing
**When** the control is shown
**Then** it is disabled with an explanatory reason rather than silently failing

### Story 16.3: Processing and Progress Indicators

As a QA user,
I want clear progress indicators during long-running agent work,
So that I know what is happening without losing context.

**Acceptance Criteria:**

**Given** an agent starts a long-running operation
**When** processing begins
**Then** the UI shows the active agent, current operation label, and non-blocking progress state

**Given** progress updates arrive over WebSocket
**When** the operation advances
**Then** step progress, status text, and current agent state update without resetting chat input or scroll position

**Given** an operation completes, fails, or is cancelled
**When** terminal status is received
**Then** the UI shows a clear completion, failure, or cancellation state with next available actions

### Story 16.4: Rich Review Panels

As a QA user,
I want rich review panels for generated outputs and artifacts,
So that I can evaluate requirements, test cases, scripts, and reports efficiently.

**Acceptance Criteria:**

**Given** reviewable content is available
**When** the user opens review mode
**Then** the UI can render Markdown, Mermaid diagrams, code with syntax highlighting, images, and structured execution report content

**Given** source and generated content are linked
**When** a side-by-side review is opened
**Then** the source content appears beside the generated output where applicable
**And** traceability metadata remains visible

**Given** multiple review items exist
**When** the user navigates review items
**Then** selection, review status, warnings, and scroll behavior remain predictable and non-destructive

### Story 16.5: Error, Empty, and Recovery States

As a QA user,
I want clear UX for missing data, errors, and recovery paths,
So that I can resolve issues without guessing.

**Acceptance Criteria:**

**Given** a required setup item is missing
**When** the user reaches a dependent workflow step
**Then** the UI explains the missing prerequisite and provides the next recovery action

**Given** an operation fails due to permission, missing credentials, unavailable MCP tools, provider/model failure, validation failure, or artifact save failure
**When** the error is shown
**Then** the message is actionable, user-safe, and does not expose secrets or internal stack traces

**Given** no project, thread, artifact, review item, or execution report exists
**When** the relevant panel is opened
**Then** an appropriate empty state explains what to do next

### Story 16.6: Keyboard and Accessibility Support

As a keyboard or assistive-technology user,
I want the conversational workflow and review panels to be accessible,
So that I can complete the QA automation workflow without relying only on a mouse.

**Acceptance Criteria:**

**Given** the user navigates the application with keyboard only
**When** they move through chat, controls, review panels, artifact tree, and dialogs
**Then** focus order is logical, visible, and does not trap the user unexpectedly

**Given** controls, status messages, errors, and dynamic updates are rendered
**When** assistive technology reads the UI
**Then** labels, roles, ARIA states, and live regions communicate meaning clearly

**Given** visual design tokens are applied
**When** text, icons, buttons, alerts, and review panels are displayed
**Then** contrast and focus states meet the project accessibility baseline

### Story 16.7: Alice Configuration Review UX Integration

As an admin or QA user,
I want Alice configuration decisions represented clearly in the conversational UI,
So that project/provider/model setup is reviewable, safe, and understandable.

**Acceptance Criteria:**

**Given** Alice performs project setup or provider/model configuration
**When** the review step is shown
**Then** the UI displays project scope, provider names, selected models, discovered-model scores, and assignment recommendations using secret-safe labels only

**Given** provider credentials are missing, invalid, or untested
**When** the user attempts to save or continue
**Then** save/continue controls are disabled with clear recovery guidance

**Given** Alice proposes per-agent model assignments
**When** the user reviews assignments
**Then** each assignment shows the agent, selected provider/model, scoring rationale, and editable selection controls where allowed
