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
> **REVISED 2026-06-25 (Epic 25, see `sprint-change-proposal-2026-06-25-no-session-capture.md` / `sprint-change-proposal-2026-06-27-test-credentials.md`):** target-app auth no longer reuses the end user's active SSO session — it authenticates via an automated login with a DEDICATED TEST ACCOUNT in the tool's own isolated browser. Users must provide their own test account credentials (stored as user secrets), preventing central storage of passwords by Project Admins. Project Admins only configure the `login_type` (e.g. sso vs standard). Group Security prohibits capturing the employee's session. Final FR text reconciled in Story 25-7.
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
> **REVISED 2026-06-25 (Epic 25, see `sprint-change-proposal-2026-06-25-no-session-capture.md` / `sprint-change-proposal-2026-06-27-test-credentials.md`):** the pipeline must NEVER read, store, or replay an END USER's browser session or corporate credentials. Target-app auth uses DEDICATED TEST ACCOUNTS whose credentials are stored encrypted as per-user secrets, resolved only at runtime, and never logged/echoed (leak-canary enforced). Storing dedicated test-account credentials as user secrets is the security-accepted replacement for the now-prohibited session capture. (Also revises Story 13.4 + Story 14.4 "existing authenticated session / without storing credentials" framing — login now happens in setup/harness; the generated script body still hardcodes no credentials.) Final text reconciled in Story 25-7.
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
- Backend uses Python 3.14+, `uv`, Hatchling, FastAPI, SQLAlchemy/Alembic, PostgreSQL, SeaweedFS, Pydantic Settings, Ruff, mypy, pytest, and pytest-asyncio.
- Frontend uses React 19+, TypeScript, Vite, Shadcn/ui, Tailwind CSS, React Router v6, react-markdown, react-syntax-highlighter, and Mermaid rendering.
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
FR11: Epic 14 - Complete end-to-end pipeline execution
FR12: Epic 13 - Use browser-use with local Chrome and SSO session
FR13: Epic 13 / Epic 14 - Save generated scripts and execution reports
FR14: Epic 9 - Encrypted per-user AI/MCP secret storage
FR14a: Epic 9 - User-driven secret replacement
FR14b: Epic 9 - Non-secret provider/model configuration separation
FR15: Epic 9 - Dynamic provider validation and model discovery
FR15a: Epic 9 - Assign only discovered available models
FR15b: Epic 9 - User-reviewable provider/model review
FR16: Epic 8 - Admin CRUD for users, projects, and memberships
FR16a: Epic 8 - Admin E2E test execution and report download
FR17: Epic 21 - Provider comparison backlog support
FR18: Not implemented - removed from MVP
FR19: Epic 13 - Side-by-side script/source review
FR20: Epic 13 - Approve or reject generated scripts
FR21: Epic 13 - Edit scripts before approval
FR22: Epic 12 / Epic 13 - Low-confidence review flagging
FR23: Epic 11 - Jira MCP connection
FR24: Epic 11 - Retrieve Jira test-related requirements
FR25: Epic 21 - Audit logging
FR26: Epic 14 - Script execution success-rate reporting
FR27: Epic 11 / Epic 12 - Input quality detection and warnings
FR28: Epic 21 - Leadership metrics dashboard
FR29: Epic 21 - LLM cost tracking and comparison data
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

### Story 11.8: Technical Debt Sweep and Hardening

As a system developer,
I want to resolve accumulated technical debt before adding new complex layers,
So that the test suite is stable and old stubs do not provide a false sense of security.

**Acceptance Criteria:**

**Given** the test suite contains pre-existing `AdminDashboard` timeouts and unstable tests
**When** the technical debt sweep is executed
**Then** the timeouts and flaky tests are resolved
**And** CI execution runs cleanly

**Given** the codebase contains pre-existing stub tests (e.g. tests that assert exact opposites or never call the actual mutation)
**When** the sweep is performed
**Then** stale stubs are either fully implemented to assert correct behavior or explicitly marked with `@pytest.mark.skip(reason="TODO")`

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

### Epic 14: Test Execution and Reporting with Jack

Users can run generated Playwright scripts, collect execution results, and view success/failure reporting across supported browsers.

**FRs covered:** FR11, FR13, FR26

**Note:** Promoted to highest priority (2026-06-20) — highest business value; completes the end-to-end pipeline. Script editing-before-approval and side-by-side source/script review (formerly proposed as a separate enhancement epic) are already delivered under Epic 13 (Stories 13.5 / 13.6) and are not re-scoped here.

### Story 14.1: Approved Script Execution Input Selection

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

### Story 14.2: Playwright Execution Runner

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

### Story 14.3: Configurable Execution Output Path

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

### Story 14.4: Multi-Browser Execution Support

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

### Story 14.5: Execution Result Report Generation

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

### Story 14.6: Execution Report Review UX

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

### Epic 15: Admin Dashboard — Project-Admin RBAC and User/Project Management

Repair and complete the platform-admin Dashboard for project and user management: fix project creation, finish the project_admin role wiring (project picker + membership on user-create), and add user-list sorting and per-user Edit/Delete. Realizes Slices 1-2 of the project-admin RBAC re-architecture (design-projectadmin-rbac-redesign-2026-06-21.md) for the Admin Dashboard surface. Source: investigation admin-dashboard-project-user-mgmt-investigation.md and sprint-change-proposal-2026-06-21.md.

**FRs covered:** FR16/FR16a (admin CRUD for users/projects and project memberships); extends Epic 6 RBAC (6-2/6-3) and the signed-off project-admin RBAC design.

**Status:** Active. Decisions (2026-06-21): the platform `admin` account is immutable (cannot be edited or deleted; only the platform admin may edit/delete project_admin and standard users); project_admin↔project linkage is many-to-many (no 1:1 uniqueness); demoting a project_admin to standard deletes the project_admin membership. App UI English-only.

### Story 15.1: Fix Project Creation Regression

As a platform admin,
I want to create a project with only a name (and optional description),
So that project creation succeeds without requiring Confluence/Jira config up front.

**Acceptance Criteria:**

**Given** the live database constraint on `projects.confluence_base_url`
**When** the schema is migrated
**Then** the column is nullable (an Alembic migration reverses the prior NOT NULL; downgrade backfills NULL→'' before re-adding NOT NULL)

**Given** an admin submits the Create Project form with a non-blank name and no Confluence/Jira config
**When** the request is processed
**Then** the project is created (HTTP 2xx) with confluence_base_url NULL and appears in the project list

**Given** an admin submits a blank project name
**When** the request is validated
**Then** creation is rejected with a clear "Project name is required" message (description remains optional)

**Given** a duplicate project name OR another integrity violation occurs
**When** the error is returned
**Then** the message distinguishes a genuine duplicate-name conflict from other failures (the NOT-NULL violation no longer masquerades as "Project name already exists")

### Story 15.2: Trim Obsolete Admin Dashboard Helper Copy

As a platform admin,
I want the Admin Dashboard to omit instructions about config it no longer owns,
So that the UI reflects that Confluence/Jira, providers, environments, roles, and membership are managed by the project admin.

**Acceptance Criteria:**

**Given** the Create Project and Edit Project forms
**When** they render
**Then** the helper sentences about config being "configured/managed by the project admin after creation" are removed

**Given** the Users Management list
**When** a non-admin user row renders
**Then** the "Project membership is managed by the project admin." note is removed (the whole conditional block, leaving no empty element)

**Given** the removed copy
**When** the dashboard is tested
**Then** no test depends on the removed strings (optionally a negative assertion confirms their absence)

### Story 15.3: Project-Admin Project Picker and Membership on User Create

As a platform admin,
I want to assign a project when creating a project_admin user,
So that the new project_admin is linked to a project via a project_admin membership.

**Acceptance Criteria:**

**Given** the Create User form
**When** the role is set to Project Admin
**Then** a required project picker is shown; for the Standard role no project picker is shown

**Given** an admin submits a project_admin user with a selected project
**When** the request is processed
**Then** the User (role=project_admin) and a ProjectMembership(role="project_admin") for that project are created atomically

**Given** an admin submits a project_admin user without a project, or a standard user with a project
**When** the request is validated
**Then** the request is rejected (422) with a clear message

**Given** the project_admin↔project linkage
**When** memberships are created
**Then** no 1:1 uniqueness is enforced — a project may have multiple project_admins and a user may admin multiple projects (additional assignments happen via existing membership flows)

**Given** no projects exist yet
**When** the admin selects the Project Admin role
**Then** the form prevents submission and explains that a project must exist first

### Story 15.4: Sort Users Management and Show Project-Admin's Project

As a platform admin,
I want the Users Management list sorted and annotated,
So that I can scan users by role, status, timezone, and name.

**Acceptance Criteria:**

**Given** the Users Management list
**When** it renders
**Then** users are sorted by role (admin → project_admin → standard → other), then status (active before inactive), then timezone (A→Z), then display name (A→Z)

**Given** a project_admin user
**When** the row renders
**Then** the administered project name(s) appear near the role badge (multiple names if the user admins multiple projects)

**Given** the active/inactive status
**When** it renders
**Then** status is conveyed with text + icon, not color alone, per the design system

### Story 15.5: User Edit and Delete with Platform-Admin Immutability

As a platform admin,
I want to edit and delete project_admin and standard users,
So that I can manage the user directory while the platform admin account stays protected.

**Acceptance Criteria:**

**Given** a project_admin or standard user
**When** the admin edits it
**Then** a new update-user endpoint updates display name, role (project_admin↔standard only), timezone, active status, and optional password reset, returning a secret-free response

**Given** a role change between project_admin and standard
**When** the update is applied
**Then** standard→project_admin requires a project and creates the project_admin membership; project_admin→standard deletes the user's project_admin membership(s)

**Given** the platform admin account (role=admin)
**When** any actor attempts to edit or delete it
**Then** the action is rejected (403); promoting any user to admin is also rejected

**Given** the current admin
**When** they attempt to deactivate or delete their own account
**Then** the action is rejected to prevent lockout

**Given** a non-admin caller
**When** they call the update or delete user endpoints
**Then** access is denied (403)

**Given** the Users Management list
**When** rows render
**Then** Edit and Delete controls appear for project_admin and standard users but NOT for the platform admin row, with distinct accessible labels

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

### Story 16.8: Hierarchical Requirements Tree Mirroring Source Structure

As a QA user,
I want the Requirements artifact tree to mirror the multi-level Confluence page hierarchy,
So that I can navigate generated requirements with the same parent/child structure as the source space.

**Acceptance Criteria:**

**Given** a Confluence space whose pages form a multi-level tree (parent pages with nested child pages across several depths)
**When** Bob saves the extracted requirements artifacts
**Then** each requirements artifact records its full ancestor chain, not only its immediate parent, so the complete source hierarchy is reconstructable

**Given** the Requirements sidebar renders the saved requirements
**When** the result tree is built
**Then** it displays the same nested levels as the source space — parent nodes contain their child pages at the correct depth — instead of a single flat list

**Given** a page has no resolvable parent or an incomplete ancestor chain
**When** the tree is rendered
**Then** the node falls back to the root level (or nearest known ancestor) and remains visible and distinct rather than being dropped or duplicated

**Given** a parent node has child requirements
**When** the user expands, collapses, or selects nodes
**Then** expand/collapse state and selection behave predictably and do not reset chat input or scroll position

### Story 16.9: Multilingual Agent Conversation with English Specifications

As a QA user who prefers a non-English language,
I want each agent to converse with me in my configured language while all generated specifications stay in English,
So that I can collaborate naturally without changing the language of the artifacts the team relies on.

**Acceptance Criteria:**

**Given** an administrator opens the Admin Dashboard user management
**When** they create or edit a user
**Then** they can set that user's preferred conversation language, which is persisted on the user record

**Given** a user has a preferred conversation language configured
**When** Alice, Bob, Mary, Sarah, or Jack send conversational messages to that user
**Then** the agent's chat-facing prose is written in the user's preferred language

**Given** the user replies in their preferred language
**When** the agent processes the reply (including feedback, clarifications, and approvals)
**Then** the agent understands the input regardless of its language and continues the workflow correctly

**Given** the workflow produces persisted specifications (requirements, test cases, scripts, execution reports, and any other saved artifacts)
**When** those artifacts are generated and saved
**Then** their content remains in English regardless of the user's conversation language

**Given** the existing App-UI-English-only convention
**When** static UI chrome (labels, buttons, placeholders, menus) is rendered
**Then** it stays in English; only dynamic agent conversation content is localized to the user's preferred language

### Story 16.10: Flat Test-Case and Script Storage (Remove Per-Role Sub-Folders)

As a QA user,
I want generated test cases and test scripts to be saved at the root of their artifact folder instead of inside a per-role sub-folder,
So that a test case that applies to more than one role is not forced under a single role folder, while the role it belongs to is still visible from the artifact's own content.

**Acceptance Criteria:**

**Given** Mary saves a test case (draft during streaming or approved on confirmation)
**When** the artifact name and storage key are derived
**Then** the test case is stored directly in the Test Cases folder root (e.g. `<case>.md`) with no `<role>/` sub-folder segment
**And** the role remains recorded in the Markdown body header (the `Role` section) so role information is not lost

**Given** Sarah saves an approved test script
**When** the script artifact name and storage key are derived
**Then** the script is stored directly in the Test Scripts folder root (e.g. `<script>.py`) with no `<role>/` sub-folder segment
**And** the script's sidecar metadata file is stored alongside it at the same root level

**Given** two test cases — or two scripts — normalise to the same base name
**When** their storage names are computed without a role folder to keep them apart
**Then** name-uniqueness is resolved across the whole flat folder (not per-role), so each artifact maps to a distinct file and none is silently overwritten

**Given** the role→folder mechanism is no longer used for storage
**When** the test-case and script save paths are updated
**Then** per-role sub-foldering is removed from both save paths, and any downstream consumer that previously grouped by folder path (e.g. role-aware execution grouping in Jack) reads the role from the artifact content/metadata instead of the folder path

**Given** artifacts already saved under a `<role>/` sub-folder before this change
**When** the new flat layout is in effect
**Then** the change applies to newly generated artifacts and pre-existing role-foldered artifacts remain readable; regenerating a test case or script saves it at the flat root (no data migration is required)

### Story 16.11: Display Current Frontend Version in UI

As a QA user or administrator,
I want the current frontend version to be visible somewhere in the UI,
So that I can tell which build I am using when reporting issues or confirming a deployment.

**Acceptance Criteria:**

**Given** the frontend is built
**When** the application bundle is produced
**Then** the version is sourced from a single authoritative place (the frontend `package.json` version, optionally with short build/commit metadata) and injected at build time, so no extra runtime request is needed to read it

**Given** an authenticated user is in the application shell
**When** any primary screen is rendered
**Then** the current frontend version is displayed in a consistent, unobtrusive location (e.g. a footer, the user/account menu, or an "About" area) using the App-UI-English-only convention

**Given** the version label is shown
**When** the user reads it
**Then** it is clearly identifiable as the frontend version (e.g. `v1.4.0`), does not overlap or obstruct interactive controls, and meets the project accessibility/contrast baseline

**Given** the build has no resolvable version or metadata
**When** the version label would render
**Then** it falls back to a safe placeholder (e.g. `dev` / `unknown`) rather than showing an empty, broken, or error state, and never exposes secrets or internal build paths

### Story 16.12: Fix Sarah Browser-Use Chrome-Driven Script Generation

**Priority: P0 — highest in Epic 16. This bug blocks the Sarah → Jack pipeline (no scripts are produced), so it must be worked before all other Epic 16 stories.**

As a QA user,
I want Sarah to reliably drive Chrome via browser-use and produce Playwright scripts from approved test cases,
So that script generation succeeds instead of failing with an LLM authentication error and leaving the Scripts folder empty.

**Observed bug:** When Sarah reaches "Generating script N of M", generation fails with `LLM Authentication failed: "Could not resolve authentication method. Expected either api_key or auth_token to be set. Or for one of the X-Api-Key or Authorization headers to be explicitly omitted"`. This message comes from the browser-use driving model (`browser_use.llm.ChatAnthropic` for the `claude` / `claude-sso` providers), so Sarah never actually drives Chrome; and because the failure is not absorbed into the fallback path it aborts the whole batch — the Scripts folder stays at 0 even though all 8 "Generating script…" messages appear.

**Likely areas to investigate (not prescriptive):** `agents/sarah.py::_build_explore_llm`, `browser/llm_factory.py::build_browser_use_llm`, `pipelines/script_generator.py` (explore gating + the vision/LLM-only fallback), and `agents/base.py::get_llm_config` (how the per-user secret / base URL is resolved for the driving and fallback models).

**Acceptance Criteria:**

**Given** approved test cases and a configured provider whose credential resolves successfully
**When** Sarah generates scripts
**Then** the resolved credential authenticates correctly for both the browser-use driving model and the deterministic script-generation model, and no "Could not resolve authentication method" error occurs

**Given** a Chrome path (or CDP URL) and a target application URL are available
**When** Sarah generates a script for a test case
**Then** the browser-use exploration path actually drives Chrome against the real app (real app → verified trace → deterministic Playwright) for that test case

**Given** the browser-use driving credential is genuinely unavailable (for example Claude / Claude-SSO without a real Anthropic key)
**When** the live exploration cannot run
**Then** Sarah falls back cleanly to vision / LLM-only generation and still produces a script per test case, rather than hard-failing the entire batch

**Given** generation completes for a batch of approved test cases
**When** the results are saved
**Then** the Scripts folder is populated with the generated scripts (not left empty) and each script is reviewable

**Given** any generation or authentication failure
**When** the error is surfaced in the conversation
**Then** the message is actionable and secret-safe — it never exposes api_key, auth_token, or Authorization/X-Api-Key header values

### Story 16.13: Fix Project Selection When Editing a Project-Admin User

**Priority: low — work at the end of Epic 16 (after 16-1..16-11). Bug found 2026-06-22 on the Admin Dashboard.**

As a platform administrator,
I want to choose a project for a user whose role is already Project Admin when I edit them in Users Management,
So that I can assign or change which project that project admin manages, not only at creation or while promoting a standard user.

**Observed bug:** In the Admin Dashboard → Users Management → Edit form, selecting the role "Project Admin" shows no project selector when the user is *already* a Project Admin, so there is no way to assign/change their managed project on edit. The project selector only appears when promoting a standard user (`u.role === "standard" && editUserRole === "project_admin"`); the create-user form has its own picker. As a result an existing project admin's project assignment cannot be viewed or changed through the edit form.

**Likely areas to investigate (not prescriptive):** frontend `components/admin/AdminDashboard.tsx` (the edit-form picker gate around `u.role === "standard" && editUserRole === "project_admin"` and the `promoting` logic in `handleEditUser`); backend `api/admin.py::update_user` + `AdminUserUpdateRequest` (today `project_id` is only consumed on the standard→project_admin transition — there is no branch to add/update a project membership for a user who is already a project_admin). Keep the many-to-many project_admin↔project model and platform-admin immutability from Epic 15, and the App-UI-English-only convention.

**Acceptance Criteria:**

**Given** I edit a user whose current role is Project Admin
**When** the edit form is shown
**Then** a project selector is present and reflects the project(s) the user currently administers, so I can assign or change the managed project

**Given** I change the selected project for an existing Project Admin and save
**When** the update is persisted
**Then** the user's `project_admin` project membership is updated accordingly, consistent with the many-to-many project_admin↔project model, and the change is reflected in the Users Management list

**Given** I promote a standard user to Project Admin (the existing flow)
**When** I edit and save
**Then** behavior is preserved — a project is still required and the membership is created as before

**Given** the immutable platform admin account
**When** it is viewed in Users Management
**Then** it remains non-editable (no project selector, no role change) per the Epic 15 immutability decision

**Given** an invalid or missing project selection on save
**When** the request is submitted
**Then** the form/API rejects it with a clear, actionable message and no partial/inconsistent membership state is left behind

### Epic 17: Document Attachment Reading

Today Bob extracts requirements only from the body of a Confluence page or Jira issue; attached documents (Excel, Word, PDF, etc.) are ignored, so requirements captured in spreadsheets and specs are lost. This epic lets Bob discover, download, and parse file attachments via the existing MCP retrieval path and fold their content into requirement extraction, so the resulting requirements cover both the page/issue body and its attachments.

**FRs covered:** new (extends Epic 11: FR23/FR24 Confluence+Jira MCP retrieval, FR27 input-quality detection; feeds requirements-artifact-save 11-7)

**Status:** Provisional — single product-owner one-liner, no PRD yet; acceptance criteria to be elaborated via a full PRD before development. Open questions: which MCP tools expose attachment lists/downloads (current readers use confluence_get_page / jira_get_issue only), supported file types + size caps, how parsed attachment text is merged with body content for the LLM, and whether attachment bytes are persisted as artifacts. Per-user encrypted-secret + no-secret-leak conventions apply to any new download path.

### Story 17.1: Discover and Download Attachments via MCP

As Bob, I want to discover and download files attached to a Confluence page or Jira issue through the existing MCP retrieval path, so that attachment bytes are available for parsing alongside the body.

_Provisional — acceptance criteria TBD via PRD._

### Story 17.2: Parse Excel, Word, and PDF Documents

As the content pipeline, I want to convert downloaded xlsx/docx/pdf attachments into clean LLM-friendly text, so that their content can feed requirement extraction the same way body content does.

_Provisional — acceptance criteria TBD via PRD._

### Story 17.3: Feed Parsed Attachments into Bob Extraction

As Bob, I want parsed attachment content merged into the requirement-extraction input, so that generated requirements reflect attachments, not just the page/issue body.

_Provisional — acceptance criteria TBD via PRD._

### Story 17.4: Surface Which Attachments Were Read

As a user, I want to see which attachments Bob read (and which were skipped or unsupported), so that I can trust and verify the source coverage of the extracted requirements.

_Provisional — acceptance criteria TBD via PRD._

### Epic 18: Source Change Detection and Downstream Cascade Update

Detect when the Confluence/Jira sources behind a project's artifacts have changed since the last run, and offer a guided, user-confirmed re-run of the affected downstream chain (requirements -> test cases -> test scripts -> execution runs). A versioned snapshot of each source is persisted per run so the next run can diff against it and surface exactly what changed and which generated artifacts are now potentially stale.

**FRs covered:** new (extends FR1-FR4, FR23-FR24 source ingestion and FR45 artifact lineage; relates to FR25 audit and FR61-FR63 realtime events). Suggest reserving FR68+ for this epic.

**Status:** Provisional — acceptance criteria TBD via PRD. Grounding: ConfluencePage.version and JiraIssue status/fields are cheap-to-hash change indicators; ArtifactVersion.content_hash + Artifact.source_url/source_type + agent_run_id give the lineage to walk source -> requirement -> test case -> script (DiscoveredModelSnapshot is an existing "last-seen snapshot" precedent). Needs a new snapshot table + Alembic migration and a backfill story for pre-existing artifacts (treat as "never-checked", not "changed"). The execution-run leg depends on Jack (Epic 14), which now ships first. Open questions: on-demand vs scheduled detection (no scheduler today), and cascade granularity (project vs page vs single test case).

### Story 18.1: Per-Run Source Snapshot Persistence

As the system, I want each run to persist a versioned snapshot/hash of every Confluence page and Jira issue it consumed, so that a later run has a baseline to diff against.

_Provisional — acceptance criteria TBD via PRD._

### Story 18.2: Source Change Detection vs Last Run

As a QA user, I want Bob to detect whether the bound Confluence/Jira sources changed since the last snapshot, so that I am told what changed before regenerating anything.

_Provisional — acceptance criteria TBD via PRD._

### Story 18.3: Downstream Staleness Impact Mapping

As a QA user, I want changed sources mapped to the affected requirements, test cases, scripts, and execution runs via artifact lineage, so that I can see exactly which generated assets are now potentially stale.

_Provisional — acceptance criteria TBD via PRD._

### Story 18.4: Guided Cascade Re-Run with Confirmation

As a QA user, I want to confirm whether to cascade an update through requirements -> test cases -> scripts -> execution, so that downstream regeneration only happens with my explicit approval and at the scope I choose.

_Provisional — acceptance criteria TBD via PRD._

### Story 18.5: Change Notice, Realtime Signal, and Audit Trail

As a project member, I want detected source changes and cascade decisions surfaced as a notice/realtime event and recorded in the audit trail, so that the team knows when sources drifted and what was regenerated.

_Provisional — acceptance criteria TBD via PRD._

### Epic 19: Frontend UX Enhancement via ui-ux-pro-max Design Conventions

Adopt the design-system and UI-quality conventions from the external "ui-ux-pro-max" skill (https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) to raise the visual and interaction quality of the existing React frontend, without changing pipeline behavior or backend contracts. The work is a polish pass over already-shipped screens — chat workspace, agent review panels, admin dashboard, and shared ui/ primitives.

**FRs covered:** new (presentation-layer quality; refines the UX surface of FR15b/FR19-FR22 review panels, FR16/FR16a admin dashboard, and the Epic 16 conversational-UX stories)

**Status:** Provisional, LOW priority, internal-only (no external/runtime dependency — the skill provides conventions applied during development; nothing from the repo ships in the bundle). Must be reconciled with Epic 16 (Conversational UX) to avoid scope overlap: treat Epic 16 as the functional baseline and this epic as the quality/polish layer on top. Keep the App UI English-only per project convention.

### Story 19.1: Audit Current UI Against Skill Conventions

As a frontend developer, I want to audit the existing React screens and shared ui/ primitives against the ui-ux-pro-max conventions, so that we have a prioritized gap list before making changes.

_Provisional — acceptance criteria TBD via PRD._

### Story 19.2: Adopt Design-System Conventions

As a frontend developer, I want to align our Tailwind v4 tokens, spacing, typography, and shared ui/ primitives with the skill's design-system conventions, so that the app has a consistent visual foundation.

_Provisional — acceptance criteria TBD via PRD._

### Story 19.3: Polish Key Workflow Screens

As a QA user, I want the chat workspace and agent review panels (Bob/Mary/Sarah) refined to the new conventions, so that the core pipeline flow looks and feels polished and coherent.

_Provisional — acceptance criteria TBD via PRD._

### Story 19.4: Polish Admin and Navigation Surfaces

As an admin, I want the admin dashboard and project navigation/sidebar refined to match the new conventions, so that management screens are visually consistent with the workspace.

_Provisional — acceptance criteria TBD via PRD._

### Story 19.5: Visual-Regression and Conventions Guardrail

As a frontend developer, I want lightweight checks and documented conventions that catch UI drift, so that future changes stay aligned with the adopted design system.

_Provisional — acceptance criteria TBD via PRD._

### Epic 20: Retrieval-Augmented Requirements for Context-Bounded Generation (RAG)

Today Mary loads every requirement Bob extracted (effectively the whole Confluence space) plus the Jira ticket before reasoning, so even a modest project already consumes 100k+ tokens of context and a larger space would overflow the model outright. This epic adds a retrieval layer so the pipeline reads only the requirement pages relevant to the current test target, the way a developer opens just the few Confluence pages that matter rather than the entire space. Each requirement page is indexed by its title plus an LLM-enriched description (built from the page's own content and rolled-up summaries of its child pages, so terse or unclear titles still retrieve well), and the relevant pages are selected by semantic similarity over the existing page hierarchy. Below a configurable size threshold the pipeline keeps the current full-load behavior, so small projects are unaffected.

**FRs covered:** new (extends Epic 11 FR23/FR24 source retrieval and FR45 artifact lineage; directly serves Epic 12 Mary test-case generation; relates to the Story 16-8 hierarchical requirements tree and Epic 18 source-change re-index). New FR numbers to be allocated during the PRD.

**Status:** Provisional — single product-owner one-liner, no PRD yet; acceptance criteria to be elaborated via a PRD before development. RECOMMENDED APPROACH (to be confirmed): hierarchy-aware semantic retrieval over LLM-enriched page-level descriptions — NOT full Graph RAG (overkill at current scale; the parent/child tree is already captured via Artifact.parent_source_id and the Story 16-8 ancestor chain) and NOT plain keyword/JSON matching (brittle when titles are terse, which is the core complaint). Page-level retrieval (read whole relevant pages), not chunk-level. DECISION GATES: (1) the embedding model MUST be reachable on the air-gapped on-premises host (LiteLLM proxy at https://ai.svc.corp.ch/api) — confirm an embedding endpoint exists, with a lexical/BM25 index or a small bundled local embedder as fallback if none; (2) vector storage — pgvector (a Postgres-only optimization) versus an embedding column stored as JSON/array with cosine computed in Python (a cross-dialect default that also works in the SQLite test suite), defaulting to the JSON+Python path at project scale (hundreds of pages); (3) retrieval tuning — top-K, similarity threshold, and whether to expand along the hierarchy to include parent pages for context. Conventions: persisted descriptions and index data stay English (App-UI-English-only); embedding API calls follow the per-user-secret and no-secret-leak rules; the index must work under both Postgres (prod) and SQLite (tests). Graph RAG (entity/relationship extraction) is explicitly deferred as a future enhancement.

### Story 20.1: Page Retrieval Index Foundation

As the system, I want a persisted per-page retrieval record (source id, title, hierarchy path, enriched description, and embedding vector) with an Alembic migration, so that requirement pages can be searched without loading them all.

_Provisional — acceptance criteria TBD via PRD._

### Story 20.2: LLM-Enriched Page Descriptions with Hierarchy Roll-Up

As the indexer, I want each page description generated from its own content plus bottom-up summaries of its child pages, so that pages with terse or unclear titles are still described richly enough to retrieve accurately.

_Provisional — acceptance criteria TBD via PRD._

### Story 20.3: Embedding Generation via On-Prem-Compatible Provider

As the indexer, I want title and description embeddings produced through an embedding model reachable on the air-gapped on-premises deployment (with a lexical fallback when none is available), so that retrieval works in the UAT and production environments, not only where cloud egress exists.

_Provisional — acceptance criteria TBD via PRD._

### Story 20.4: Semantic Retrieval of Relevant Pages

As Mary, I want to retrieve the top-K requirement pages most relevant to the current test target (optionally expanded along the page hierarchy for parent context), so that I reason over the pages that matter instead of the whole space.

_Provisional — acceptance criteria TBD via PRD._

### Story 20.5: Mary Context-Bounded Retrieval Integration

As Mary, I want to load only the retrieved relevant pages (with a full-load fallback below a configurable size threshold and a token-budget guard), so that test-case generation no longer overflows context on large requirement sets while small projects behave exactly as before.

_Provisional — acceptance criteria TBD via PRD._

### Story 20.6: Incremental Index Maintenance and Re-Index on Source Change

As the system, I want the retrieval index updated incrementally when pages are added, changed, or removed (reusing Epic 18 source-change detection so only deltas are re-embedded), so that retrieval stays accurate without rebuilding the whole index every run.

_Provisional — acceptance criteria TBD via PRD._

### Story 20.7: Retrieval Transparency and Tuning

As a QA user, I want to see which pages were retrieved and why, and to adjust top-K and the similarity threshold, so that I can trust the source coverage of generated test cases and tune recall against context size, mirroring the attachment-coverage transparency from Epic 17.

_Provisional — acceptance criteria TBD via PRD._

### Epic 21: Audit, Metrics, and Leadership Visibility

Admins and leadership can see audit trail, execution metrics, success rates, effort reduction, LLM cost tracking, and provider comparison backlog support.

**FRs covered:** FR17, FR25, FR28, FR29

**Note:** Lower business value (2026-06-20 reprioritization) — sequenced after the core pipeline, UX, and new-feature epics but ahead of the externally-blocked SSO epics. Absorbs the former standalone audit-logger backlog (foundation + extended event types).

### Story 21.1: Audit Event Model and Persistence

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

### Story 21.2: Pipeline Audit Logging

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

### Story 21.3: Admin Audit Trail View

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

### Story 21.4: Execution Metrics Aggregation

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

### Story 21.5: Leadership Metrics Dashboard

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

### Story 21.6: LLM Cost Tracking

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

### Story 21.7: Provider Comparison Backlog Support

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

### Epic 22: Company-Provided Claude API Key (separate from personal keys)

Let users drive Claude inference (Sarah's browser-use exploration, and any Claude provider use) with a **company-issued Anthropic API key** obtained through the company Anthropic workspace, kept strictly separate from a user's personal Claude key because the two carry different security and governance levels. Company IT confirmed the credential mechanism: each employee logs in to `platform.claude.com` with their `@corp.ch` identity, IT grants workspace access via a Change Request, and the employee creates their own API key (credits requested via Manager/CR). This is a real `sk-ant-api...` key — NOT an OAuth/SSO token — so it slots into the existing `claude` provider path; the work is the separation, selection, and validation around it.

This RESOLVES the previously-provisional credential unknown: the mechanism is a real per-user API key (option a), not an OAuth-token-accepting API (b). The existing SSO login flow (OAuth+PKCE mock IdP, the `claude_sso` secret, `ClaudeSSOAdapter`, `build_browser_use_llm` claude mapping) stays for login UX, but the **inference credential is now a company API key stored in its own secret slot** (`claude_company`) alongside the personal `claude` key.

**FRs covered:** FR14, FR36, FR54 (existing per-user encrypted secrets), NFR7 (secrets never leak); new — "a company-scoped Claude API key is stored and used separately from a personal Claude key, selectable per run, with a gateway/MCP fallback where direct egress is unavailable."

**Status:** Planning, IT-gated. The API key is **requested from IT but not yet provisioned** — plan now, implement when it arrives. Decisions (Thuong, 2026-06-23): (1) **separation = per-user dedicated secret slot** `claude_company` alongside personal `claude`; each user pastes their own company key, encrypted per-user, tagged company-scope with stricter handling/audit (the headline security concern); (2) **selection = user chooses per provider-config / per-thread** which Claude credential to use (company vs personal); (3) **scope = simplify but keep the gateway fallback** — dropped the OAuth-token story, kept the internal gateway/MCP story for air-gapped hosts. ⚠️ **Air-gapped caveat:** a company Claude key still needs egress to `api.anthropic.com`; the no-internet/no-proxy UAT host cannot use it without an IT egress proxy, so UAT keeps falling back to on-prem models and Story 22.5 (gateway/MCP) remains the air-gapped Claude path. Honor conventions: secrets never in messages/logs/artifacts; leak-canary coverage; deterministic model selection.

### Story 22.1: Company Claude API Key Secret Slot Separate From Personal

As a QA user, I want to store my company-issued Claude API key in a dedicated secret slot separate from my personal Claude key, so that the company credential is governed and handled independently (different security level) and the two are never conflated.

_Provisional — acceptance criteria TBD via PRD / bmad-create-story._

### Story 22.2: Per-Thread Company vs Personal Claude Credential Selection

As a QA user, I want to choose whether a given configuration/thread uses my company Claude key or my personal Claude key, so that I control which credential each run consumes (company credits vs personal account).

_Provisional — acceptance criteria TBD via PRD / bmad-create-story._

### Story 22.3: Drive Browser-Use With the Selected Company Claude Key

As a QA user, I want Sarah's browser-use exploration to authenticate to Claude using the selected company API key, so that script generation runs end-to-end on the company-approved credential, falling back gracefully when it is unavailable.

_Provisional — acceptance criteria TBD via PRD / bmad-create-story._

### Story 22.4: Validate Company Claude Connection and Discover Models

As a user, I want Alice to validate the company Claude key and discover available Claude models through it, so that configuration review reflects real reachability (including the air-gapped no-egress case) and never silently assumes a working credential.

_Provisional — acceptance criteria TBD via PRD / bmad-create-story._

### Story 22.5: Claude via Internal Company Gateway/MCP Fallback

As an enterprise deployment, I want Claude inference to optionally route through a Claude-capable internal gateway/MCP endpoint, so that browser-use can use Claude on air-gapped hosts (e.g. UAT with no direct egress to api.anthropic.com), reusing the on-premises/OpenAI-compatible adapter pattern.

_Provisional — acceptance criteria TBD via PRD / bmad-create-story._

### Epic 23: SSO-First Authentication, Azure App-Role Mapping, and Auto-Provisioning

Let the company identity provider be the **only** front door. The login screen collapses to a **single "Sign in with SSO" button** — there is no email/password field and no second login surface. Every user (standard, project-admin, platform-admin) signs in through Azure Entra ID; the platform **auto-provisions** their User record on first login and **derives their platform role(s) from Azure App Roles** (`admin`, `project-admin`, `user`). A user may hold **multiple** app roles at once; multi-role users land on the standard user workspace by default and get header links to the Project Admin Dashboard and/or Admin Dashboard for the roles they hold. The app header shows the user's name, role(s), and an **avatar synced from Azure**. The `admin` role carries **implicit project-admin authority over every project** and the power to **assign project-admin users to one or more projects**. Local email/password login is **removed** and the redundant credential column (`users.password_hash`) is **dropped**. Both **local and UAT** environments must be able to complete SSO. Pre-provisioning needs no bulk directory sync: an admin **creates a user by email** (identity-only, no password) and a project admin assigns them to projects, so a user lands on their projects on first login.

This **RESHAPES** the earlier two-origin plan (SSO at `/` + local `/admin` login). Thuong's 2026-06-25 direction supersedes it: one SSO button, no local passwords, Azure-app-role-driven RBAC. Per-user encrypted secrets and project-scoped RBAC mechanics stay; only the identity, role-source, and account-provisioning layers change.

**FRs covered:** reuses/extends Epic 6 auth + RBAC (6-2, 6-3), admin user management (2-2, Epic 15), and the project-admin↔project many-to-many (Epic 15, story 16-13); revives the deferred Azure Entra SSO foundation (prior art in reverted commit `73980bf` — `api/auth/azure.py`, `MicrosoftLoginButton.tsx`, config). New: single-SSO login, Azure-app-role→platform-role mapping, multi-role users, role-aware in-app navigation, Azure avatar sync, and removal of local password auth (no existing FR; final FR text deferred to a PRD pass, consistent with Epics 14–24).

**Decisions (sprint planning 2026-06-25, Thuong — supersede the 2026-06-24 two-origin decisions):** (1) **Spike first** — the topology + air-gapped UAT egress are genuinely unknown, so 23-1 is a feasibility investigation before production code; the spike must confirm a path that works on **both** local and UAT. (2) **Single SSO front door** — one "Sign in with SSO" button, no password field, no `/admin` local login; all roles authenticate via SSO. (3) **Roles from Azure App Roles** — the app registration exposes `admin` / `project-admin` / `user`; one user may hold several; the platform maps the token `roles` claim → its platform roles on every login. (4) **Multi-role UX** — default to the user workspace; surface header links to the dashboards the user is entitled to. (5) **Avatar from Azure** — show the synced photo (initials fallback). (6) **Admin = global project-admin** + can assign project-admin users to 1..n projects (preserve many-to-many + platform-admin immutability from Epic 15). **A `project_admin` membership CONFERS the project-admin role** (Thuong 2026-06-25): an admin can create a user and assign them as project-admin of a project **entirely in-app, before that person ever logs in** — no Azure `project-admin` app-role grant needed; the membership confers `project_admin` on first SSO login. Only the platform **`admin`** role is Azure-only. (7) **Remove local password auth and drop `users.password_hash`.** (8) **No bulk directory sync** — the earlier SharedERP/Graph user-sync (was story 23.7) is **DROPPED** (Thuong 2026-06-25): admin **Create-User** (identity-only after 23.6) + the **existing project-admin member assignment** already let an admin pre-provision a user by email and assign them to projects before first login, so no automated user pull is needed.

**Status:** Provisional, gated on company IT/security policy approval; 23-1 (spike) can start now. Azure inputs are **already provisioned** (Thuong has an app registration with tenant id / app (client) id / client secret + the 3 app roles; on the Enterprise Application a user can be assigned multiple app roles). The `msal>=1.28` + `python-jose[cryptography]>=3.3` deps are already in `pyproject.toml` (leftover from the reverted SSO foundation). Grounding (verified in code 2026-06-25): login today is local email/password only (`api/auth/local.py` → `/auth/login`, JWT cookie via `SessionManager` at `api/auth/session.py:78`); the FE has a single password `LoginPage.tsx` (`frontend/src/components/auth/LoginPage.tsx`) and `App.tsx` renders by auth state (1702-1711) with **no URL routing / no router dep**; `UserSession` (`api/auth/session.py:17-76`) already exposes `given_name`/`family_name`/`groups`, so Azure claims slot into the existing session layer; `User.role` is a **single** `String(50)` (`db/models.py:38`); the only credential column left after migration `c7e3a9f04b21` (which already dropped `login_type`/`project_accounts`/`users.chrome_path`) is **`users.password_hash`** (`db/models.py:37`) — there is **no `account` column**; `claude_sso.py` is provider auth for browser-use, NOT user login. **Air-gap reality:** app-level OIDC needs backend egress to `login.microsoftonline.com` (token + JWKS) and `graph.microsoft.com` (avatar), which the **air-gapped UAT host blocks** without an IT proxy (see memory `uat-airgapped-egress-model-transfer.md`); the spike weighs **(A) app-level OIDC + IT egress proxy** vs **(B) SPA/MSAL.js browser-side code exchange + cached/bundled JWKS** (browser has the corporate session and internet; backend only validates the ID token) vs **(C) reverse-proxy header SSO**. Decision gates (topology, multi-role persistence, avatar storage, break-glass, in-app navigation) are baked into the individual stories.

### Story 23.1: SSO Feasibility Spike — Topology, UAT Egress, App-Roles, and Avatar

As an operator, I want a time-boxed feasibility investigation of how to reuse corporate Azure SSO on **both** local and air-gapped UAT, so that we commit to the right topology and know the exact app-registration / IT asks (egress proxy or reverse proxy), the app-role claim shape, and the avatar path before building.

_Provisional — investigation/spike; acceptance criteria TBD. Output = recommended topology + UAT egress verdict + app-role→platform-role mapping spec + avatar plan + concrete IT asks._

### Story 23.2: SSO Login Foundation and Single SSO-Only Login Screen

As an employee, I want the login screen to offer a single "Sign in with SSO" button that authenticates me with my corporate Azure identity (no password field), so that I sign in with my existing company account and the platform no longer manages local passwords.

_Provisional — acceptance criteria TBD; mechanism follows the 23.1 topology decision. Establishes the OIDC round-trip + session for an existing user; first-login provisioning + role mapping is 23.3._

### Story 23.3: Auto-Provision on First Login and Azure App-Role → Platform-Role Mapping

As a first-time or returning SSO user, I want the platform to auto-create my User record on first login and derive my platform role(s) from my Azure App Roles (supporting multiple roles), so that I can use the platform immediately without an admin adding me, and an Azure `admin` app-role bootstraps platform-admin access.

_Provisional — acceptance criteria TBD. Decision gate: persist a multi-role set (new `User.roles`) vs derive each login + keep `User.role` as the derived primary._

### Story 23.4: Role-Aware Navigation and Header Identity with Azure Avatar

As a multi-role user, I want to land on the user workspace by default with header links to the Project Admin Dashboard and/or Admin Dashboard for the roles I hold, and to see my name, role(s), and Azure-synced avatar in the header, so that I can move between the surfaces I'm entitled to.

_Provisional — acceptance criteria TBD. Decision gates: in-app navigation (state-based vs add a router) and avatar storage (blob vs URL vs data-URI)._

### Story 23.5: Admin Global Project-Admin Authority and Project-Admin Assignment

As a platform admin, I want implicit project-admin rights over every project plus the ability to assign project-admin users to one or more projects, so that I can delegate project administration without hand-managing each membership row.

_Provisional — acceptance criteria TBD. Largely audit-and-confirm of the existing admin backdoor (`rbac.py:68-69`, `projects_admin.py:125-127`) + new multi-project assignment UI/API; preserve many-to-many + platform-admin immutability (Epic 15)._

### Story 23.6: Remove Local Password Auth and Drop Redundant Credential Columns

As an operator, I want local email/password login removed and the redundant `users.password_hash` column dropped, so that SSO is the single source of authentication and no stale credential surface remains.

_Provisional — acceptance criteria TBD. Sequenced LAST among the auth stories (after SSO is proven). Decision gate: break-glass = none (rely on Azure `admin` app role) vs an env-based emergency token._

### Story 23.7: ~~Directory Sync~~ — DROPPED (2026-06-25)

**Dropped (Thuong 2026-06-25).** The bulk directory sync (originally Oracle SharedERP, then reshaped to Azure Microsoft Graph `appRoleAssignedTo`) is **not needed**. The goal — assign a user to a project **before their first login** — is already met by the existing platform:

- **Admin creates the user by email** — `POST /admin/users` (`create_user`), identity-only (no password) after story 23.6.
- **Project admin assigns them to a project** — `POST /projects/{id}/members` (`add_project_member`); the assignable-user picker `GET /projects/{id}/users` (`list_assignable_users`) returns **all active users**, so a never-logged-in user is selectable.

So Epic 23 ships as **6 stories (23.1–23.6)**; no automated user pull, no `Application.Read.All` Graph consent, no scheduler, no new migration.

### Epic 24: DOM Snapshot Caching and Site Map for Faster Script Generation

Speed up Sarah's Playwright script generation by capturing and caching the target web app's DOM ahead of time, versioned per environment and page, with change detection so a re-run only re-reads pages that changed. A project admin triggers a session-authenticated background crawl ("Get DOM") of an environment URL (or schedules it daily/weekly); the crawl stores only the important elements (button, text, label, input, selector, url, breadcrumb) plus a content hash and version per page. When any project user generates a script for a page that has a fresh cached DOM, Sarah reuses the cache and skips live exploration; on a miss or stale page it explores live and persists the result for the whole project to reuse. Admins can download the cached DOM to monitor the site.

**FRs covered:** new (performance enhancement; relates to FR45 artifact lineage, FR61–FR63 realtime events, and the session/credentials work). Reserve FR90+ (final TBD via PRD; no `prd.md` FR-list edit now, consistent with Epics 14–23 which defer FR text to a PRD pass).

**Status:** Provisional — acceptance criteria TBD via PRD/design doc (same convention as Epic 18). Grounding (verified in code 2026-06-23): `Project.environments` (`db/models.py:76`, migration `d4e7a1c93f20`), `CapturedSession` + encrypted `storageState` (`db/models.py:137`, `browser/session_capture.py`, `sessions/auto_capture.py`), browser-use + Playwright async (`browser/`, `playwright>=1.60`), snapshot+hash pattern (`DiscoveredModelSnapshot` `db/models.py:395`, `ArtifactVersion.content_hash`), Sarah explore hook (`pipelines/script_generator.py:208`). New work: full-site crawler (none today — only single-flow `explore_test_case`), DOM-snapshot table + Alembic migration, scheduler (no APScheduler/Celery/cron today), Sarah cache integration, FE "Get DOM" button/progress/schedule/download. Independent of Epic 18 but SHARES its snapshot/hash/versioning design (Epic 18 = Confluence/Jira source drift; Epic 24 = live DOM drift). Decision gates DG1–DG5 in `sprint-change-proposal-2026-06-23-epic24-dom-cache.md`.

### Story 24.1: DOM Snapshot Schema and Storage

As the system, I want a versioned per-(project, environment, page) DOM snapshot table that stores only key elements (button/text/label/input/selector/url/breadcrumb) plus a normalized content hash and version, so that DOM can be cached, diffed, and reused.

_Provisional — acceptance criteria TBD via PRD/design (DG1, DG5)._

### Story 24.2: "Get DOM" Trigger with Session-Authenticated Background Crawl

As a project admin, I want a "Get DOM" button on each environment URL that kicks off a session-authenticated background crawl, so that I can populate the DOM cache without blocking the UI.

> **REVISED 2026-06-25 (depends on Epic 25):** the crawl authenticates via the Epic 25 dedicated test-account auto-login (not a captured session — capture is prohibited). Epic 24 stays after Epic 25 in the dev order.

_Provisional — acceptance criteria TBD via PRD/design._

### Story 24.3: Bounded Full-Site Crawler and Element Extraction

As the system, I want a bounded, same-origin crawler (driven by Playwright async + the captured session) that visits the site's pages and extracts only the important elements per page, so that a full DOM map is captured safely without runaway crawling.

_Provisional — acceptance criteria TBD via PRD/design (DG2, DG5)._

### Story 24.4: Incremental Re-Crawl via Change Detection

As a project admin, I want a re-run of "Get DOM" to re-crawl only pages whose DOM changed since the last snapshot (diff by content hash) and bump their version, so that refreshes are cheap.

_Provisional — acceptance criteria TBD via PRD/design (DG4)._

### Story 24.5: Scheduled Crawl (Daily / Weekly)

As a project admin, I want to schedule the crawl daily or weekly per environment, so that the DOM cache stays fresh automatically.

_Provisional — acceptance criteria TBD via PRD/design (DG3; single-worker assumption)._

### Story 24.6: Sarah Cache-Aware Script Generation

As a project user, I want Sarah to reuse a fresh cached DOM for a page and skip live exploration, and on a miss/stale page to explore live and persist the result for project-wide reuse, so that script generation is fast and self-improving.

_Provisional — acceptance criteria TBD via PRD/design (DG4). This is the payoff story; can be pulled forward once 24.1 + 24.3 land._

### Story 24.7: Crawl Progress and DOM Download / Monitor

As a project admin, I want to see background-crawl progress and download the cached DOM (key elements per page), so that I can monitor what the site exposes.

_Provisional — acceptance criteria TBD via PRD/design._

### Epic 25: Security-Compliant Target-App Authentication (Dedicated Test-Account Auto-Login)

> **NEW 2026-06-25 (correct-course).** Source: `sprint-change-proposal-2026-06-25-no-session-capture.md` and `sprint-change-proposal-2026-06-27-test-credentials.md`. **MAJOR** change forced by Group Security: capturing the employee's browser session (cookies / `storageState` via CDP pull or the `capture-session.mjs`/`.cmd` client capture) is prohibited. This epic replaces session capture with an automated login with a DEDICATED TEST ACCOUNT, in its own isolated browser. Users store their test account credentials as user secrets. Project Admins only configure the `login_type` (SSO vs standard). The employee's actual session is never touched.

Replace the now-prohibited capture mechanism (Stories 16-19 / 16-21 capture surface, `design-test-login-credentials-and-sessions-2026-06-20.md`) with dedicated test-account auto-login. Store per-(project, environment, role) test-account credentials encrypted (reusing the Fernet per-user-secret machinery); run a browser-use/Playwright login routine to produce a session; reuse the **existing** Tier-1 server-side injection (`browser/explorer.py`) and Jack conftest injection (`pipelines/script_runner.py`) — only the SOURCE of the session changes. Keep the `check-connections` reachability probe and the `c7e3a9f04b21` cleanup; remove `browser/session_capture.py`, the 4 capture/import routes in `api/sessions.py`, `frontend/public/capture-session.{mjs,cmd}`, and `ImportSessionForm.tsx`.

**FRs covered:** revises FR12 + NFR10 (+ Story 13.4 / 14.4 framing); new TBD FR for test-account credential storage (reconciled via PRD pass in 25-7, same defer convention as Epics 14–24).

**Status:** Provisional — acceptance criteria + design TBD via Story 25-1 (spike + IT asks). **High priority** — the capture path is dead, so Sarah/Jack are currently blocked against any authenticated corporate target app; sequence Epic 25 BEFORE Epic 24 (24 depends on it) and alongside Epic 23's live-validation window (both are auth work needing the real environment).

**Load-bearing risk (like Epic 23's egress):** MFA / Conditional Access on internal Azure-SSO apps — a scripted login cannot pass push-MFA/biometrics. Mitigation is the §6 IT ask: a dedicated QA test account that is MFA-exempt OR provides a TOTP seed.

**Grounding (verified in code 2026-06-25):** capture surface = `browser/session_capture.py` (CDP pull), `api/sessions.py` capture/import routes, `frontend/public/capture-session.{mjs,cmd}`, `ImportSessionForm.tsx`. Reusable seams = `browser/explorer.py:120` (Tier-1 `storage_state` temp-file injection), `pipelines/script_runner.py:574` (conftest injection), `ScriptGenerator(role_sessions=…)` (`pipelines/script_generator.py:105`), `sarah._resolve_role_sessions`, `api/sessions.py::check_environment_connections`. Credential storage = Fernet (`db/types.py`), same as provider keys. `CapturedSession` table repurposed as the (optional) cache of the TOOL-generated session.

### Story 25.1: Auto-Login Design Note, Feasibility Spike, and IT Asks

As the architect, I want a design note + feasibility spike that picks the login-automation mechanism (browser-use-driven vs scripted), the credential-storage model, and the per-app login-hint shape — plus the verbatim IT asks (dedicated test accounts; MFA-exempt or TOTP; security sign-off on storing test-account credentials) — so that production stories 25-2…25-7 build on a confirmed approach. *Load-bearing gate, like Story 23-1.*

_Provisional — acceptance criteria TBD via design note._

### Story 25.2: Remove the Prohibited Session-Capture Surface

As the system, I want the session-capture/import surface removed (`browser/session_capture.py`; the `capture`/`import`/`import-token`/`import-with-token` routes in `api/sessions.py`; `frontend/public/capture-session.{mjs,cmd}`; `ImportSessionForm.tsx`) while keeping the consumption seams and `check-connections`, so that the behaviour Group Security flagged no longer exists in the product.

_Provisional — acceptance criteria TBD via PRD/design._

### Story 25.3: Dedicated Test-Account Credential Store

As a user, I want to store my dedicated test-account credentials (username/password + optional TOTP secret) per (project, environment, role) as encrypted **user-scoped secrets**, so that the tool can log in to the target app securely without exposing my passwords to Project Admins. This includes:
- User UI to input test accounts.
- Encrypted CRUD (reusing Fernet per-user-secret machinery).
- **CRITICAL**: A DB migration to drop the old project-level `test_account_credentials` table.
- Project Admin dashboard UI update to only configure `login_type` (`standard`, `sso_microsoft`, `sso_google`, etc.) and `login_hint` for the environment.

_Provisional — acceptance criteria TBD via PRD/design._

### Story 25.4: Automated Login to Generate a Session

As the system, I want an automated login routine (browser-use/Playwright) that, given a target-app login URL + stored test-account credentials (+ TOTP when configured), authenticates in a clean isolated browser and exports the resulting `storageState`, so that a session is produced without reading any employee browser.

_Provisional — acceptance criteria TBD via PRD/design._

### Story 25.5: Wire Auto-Login into Sarah Explore and Jack Run

As a project user, I want Sarah's exploration and Jack's runs to dynamically parse the selected test cases to extract ONLY the specific roles actually required, and to resolve their session via auto-login (using my secure user-scoped test credentials). The FE `SarahInputsForm` should prompt me to enter credentials only for those missing test roles, so that script generation and execution authenticate securely and efficiently without over-asking for unused roles.

_Provisional — acceptance criteria TBD via PRD/design._

### Story 25.6: External-App Authentication (Username/Password and Third-Party OAuth)

As a project user, I want external (non-Azure) apps supported — direct username/password login, and third-party OAuth (Google/Apple) via dedicated test accounts or the app's own test login — with hard limits documented where automation is genuinely blocked, so that the pipeline covers external as well as internal apps.

_Provisional — acceptance criteria TBD via PRD/design._

### Story 25.7: Docs, FR/NFR Reconciliation, and Live Validation

As the team, I want FR12 / NFR10 / Story 13.4 / Story 14.4 reconciled to the new model, `project-context.md` updated, the `2026-06-20` design doc superseded, and a live validation on local + UAT against a real authenticated app, so that the change is complete, discoverable, and proven end-to-end.

_Provisional — acceptance criteria TBD via PRD/design._
