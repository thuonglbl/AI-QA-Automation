---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-04-06'
inputDocuments:
  - prd.md
  - product-brief-browser-use-custom.md
  - product-brief-browser-use-custom-distillate.md
  - secret-brief-internal.md
workflowType: 'architecture'
project_name: 'AI QA Automation'
user_name: 'Thuong'
date: '2026-04-03'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
67 functional requirements across 12 categories:

- **Confluence Integration (FR1-4):** MCP-based connectivity to on-prem Confluence, SSO authentication, content parsing including embedded macros (M1)
- **Test Script Generation (FR5-9):** NL interpretation → Playwright Python scripts with stable selectors and mapped assertions. One file per test case
- **Pipeline Execution (FR10-13):** Single entry point (Confluence URL → Playwright files), end-to-end without manual intervention, browser-use controls local Chrome via SSO
- **Secure Configuration (FR14-15b):** System-level base URLs in environment settings; per-user AI provider and MCP keys stored only in encrypted PostgreSQL fields; Alice validates provider connectivity, dynamically discovers available models, and persists only verified model assignments with non-secret rationale
- **Administration (FR16):** Admin CRUD for users/projects and project memberships; admins route only to the admin dashboard
- **Backlog / Removed Scope (FR17-18):** Provider comparison tests are backlog; centralized prompt-template tuning is removed from MVP
- **Human-in-the-Loop Review (FR19-22):** Side-by-side source/script comparison, approve/reject/edit workflow, low-confidence flagging
- **Jira Integration (FR23-24, M1):** On-prem Jira Data Center access via MCP for test-related requirements
- **Quality, Observability, and Reporting (FR25-29):** Audit logging, success rate reporting, input quality detection, metrics dashboard, LLM cost tracking
- **Collaborative Project Threads and Agent Runs (FR30-41):** Per-user private conversation threads, immutable thread-to-project binding, append-only messages, thread-scoped agent runs, and access denial when project membership is removed
- **Output and Shared Artifact Storage (FR42-46):** Project-level shared SeaweedFS artifact tree with required logical folders, metadata ownership/version fields, and cross-user project-member artifact access
- **Collaborative Workspace UX and Realtime Sync (FR47-67):** Workspace shell, conversation history, selected-project artifact sidebar, secret status/rotation UX, and WebSocket artifact change events with non-disruptive refresh behavior

**Non-Functional Requirements:**

- **Performance:** <5 min per test case generation, <30s per browser action, standard Playwright timeouts
- **Security (critical):** All data on-premises, no external transmission. User secrets must never appear in `.env`, plaintext JSON columns, logs, WebSocket payload history, conversation history, artifacts, or generated files. Per-user AI provider and MCP keys are encrypted with `USER_SECRETS_ENCRYPTION_KEY`; passwords are one-way hashes; browser agent remains read-only
- **Integration Resilience:** Graceful MCP failure handling, LLM retry logic (max 3), browser crash recovery, valid standalone Playwright output, startup validation for system-level environment configuration and encryption key presence

**Scale & Complexity:**

- Primary domain: Collaborative AI-powered developer tool with FastAPI backend, React workspace, PostgreSQL state, SeaweedFS artifact storage, and WebSocket realtime updates
- Complexity level: Medium-high — AI/LLM integration, on-prem enterprise constraints, secure per-user secrets, project-scoped collaboration, thread persistence, and realtime artifact synchronization
- Estimated architectural components: 10-12 core components (auth/RBAC, project membership, thread/message store, agent runs, MCP client, LLM abstraction, browser-use orchestrator, artifact service, SeaweedFS storage, secret encryption, WebSocket hub, admin UI)

### Technical Constraints & Dependencies

- **On-premises only:** Non-negotiable for Swiss banking/pharma/government clients — shapes every integration decision
- **MCP Server dependency:** Single integration point for Confluence (and Jira in M1) — already deployed and stable
- **browser-use framework:** Open-source dependency (>=0.12.5), still maturing — architecture should allow fallback to Playwright native AI ecosystem
- **Claude Enterprise license:** PoC LLM, already approved — M1 migrates to on-prem DeepSeek/Qwen
- **Python 3.12+ / uv:** Runtime and package manager — aligns with browser-use ecosystem
- **Existing SSO infrastructure:** Browser sessions reuse active SSO login — no additional auth system needed
- **Gatling coexistence:** Playwright scripts must coexist with existing Gatling suites, no migration required

### Cross-Cutting Concerns Identified

- **Data sovereignty:** Affects every component — no data leaves company infrastructure at any phase
- **Secret containment:** Per-user MCP and AI provider keys must remain encrypted at rest, masked in UI, absent from logs/messages/artifacts, and resolved only at execution time
- **Thread/project scoping:** Conversation threads are private to the creating user, bind immutably to one project, and derive agent-run scope from `thread_id`; project artifacts are shared across assigned project members
- **LLM abstraction:** Must support provider switching without pipeline changes, with Alice using runtime provider validation and model discovery rather than static mappings
- **Error handling & resilience:** MCP failures, LLM timeouts/rate limits, browser crashes, secret expiry, provider model discovery failures, and artifact update conflicts — graceful degradation throughout
- **Audit & observability:** Who read what, who generated what, who changed artifacts, when, for which project/thread/agent run — required across execution and collaboration surfaces
- **Configuration management:** Environment configuration is for system-level non-secret settings and encryption keys only; user secrets and provider model selections live in PostgreSQL through secure domain services
- **Realtime collaboration:** Artifact changes must be emitted through WebSocket to all assigned users without disrupting active chat/input/scroll state
- **Script quality assurance:** Hallucination mitigation is architectural — human-in-the-loop review, confidence scoring, input quality detection

## Starter Template Evaluation

### Primary Technology Domain

Python CLI Pipeline Tool — backend automation pipeline for AI-powered QA test generation. Not a web application.

### Starter Options Considered

| Starter | Description | Verdict |
| --- | --- | --- |
| `uv init --package` | Native uv scaffolding, minimal | Project already exists — cannot re-init |
| cookiecutter-uv (fpgmaas) | Batteries-included: CI, docs, Docker, pre-commit | Overkill for PoC stage |
| simple-modern-uv (jlevy) | Balanced modern template via Copier | Project already exists — template conflicts |
| Manual restructure | Reorganize existing project to `src/` layout | **Selected** — preserves existing work |

### Selected Approach: Manual Restructure (No Template)

**Rationale for Selection:**

- Project already has `pyproject.toml`, `uv.lock`, `.venv`, and working `ai_connection/` module
- Template generators create from scratch and would conflict with existing files
- The restructure is straightforward enough to do manually
- Avoids inheriting unnecessary opinions (MkDocs, Docker, GitHub Actions) not needed for PoC

**Architectural Decisions Established:**

**Language & Runtime:**

- Backend: Python 3.12+ with uv package manager, type hints throughout, verified by mypy
- Frontend: TypeScript + React 18+ with Vite build tool

**Project Layout:**

- `src/ai_qa/` — Python backend (PEP 621 compliant, src layout)
- `frontend/` — React frontend (Vite + Shadcn/ui + Tailwind CSS)
- Editable install via `uv sync` for development

**API Framework:**

- FastAPI — async Python web framework serving REST API + static frontend files
- Replaces Click CLI as primary user interface (CLI retained for developer/admin use)

**Frontend Framework:**

- React 18+ with TypeScript — conversational chat UI
- Shadcn/ui — copy-paste component library (Radix UI primitives + Tailwind CSS)
- Vite — fast build tool, minimal config
- react-markdown + react-syntax-highlighter + mermaid — rich content rendering in chat bubbles (mermaid required for UX-DR5 diagram support)

**CLI Framework (secondary, developer/admin only):**

- Click — retained for admin tasks, debugging, direct pipeline execution without UI

**Build System:**

- Hatchling — modern, lightweight, native uv compatibility

**Testing Framework:**

- pytest + pytest-asyncio (async browser-use code) + pytest-cov
- Tests in top-level `tests/` directory

**Linting & Formatting:**

- Ruff — replaces black, isort, flake8 in a single fast tool
- Target: Python 3.12, line-length 100

**Type Checking:**

- mypy for static type analysis

**Target Project Structure:**

```text
ai-qa-automation/
  pyproject.toml
  uv.lock
  .python-version
  .env                    (gitignored)
  config.yaml             (gitignored)
  config.example.yaml
  src/
    ai_qa/
      __init__.py
      __main__.py          # CLI entry point
      cli.py               # Click command definitions (admin/developer)
      config.py            # Pydantic Settings
      api/                 # FastAPI web server
        __init__.py
        server.py          # FastAPI app + routes
        websocket.py       # WebSocket for real-time chat updates
      agents/              # Named AI agent orchestrators
        __init__.py
        alice.py           # Step 1: Configuration & AI provider selection
        bob.py             # Step 2: Extract Requirements
        mary.py            # Step 3: Create Test Cases
        sarah.py           # Step 4: Create Test Scripts
        jack.py            # Step 5: Run Test Scripts
      ai_connection/       # LLM server connectivity
        __init__.py
        client.py
        config.py
        exceptions.py
      browser/             # browser-use + Playwright orchestration
        __init__.py
        agent.py
      pipelines/           # Pipeline stages (used by agents)
        __init__.py
  frontend/                # React conversational UI
    package.json
    vite.config.ts
    tsconfig.json
    tailwind.config.ts
    src/
      App.tsx
      components/
        AgentTopBar.tsx
        ChatMessage.tsx
        ChatInputArea.tsx
        ReviewContent.tsx
        StepDots.tsx
        ProcessingIndicator.tsx
      hooks/
        useWebSocket.ts    # Real-time connection to backend
        usePipelineState.ts
  tests/
    conftest.py            # Shared fixtures
    test_ai_connection.py
    test_browser.py
```

**Dev Dependencies:**

```text
Backend: pytest, pytest-asyncio, pytest-cov, ruff, mypy, pre-commit
Frontend: npm (managed separately from uv)
```

**CI/CD:**

- Deferred to post-PoC milestone (Bitbucket on-premises)

**Note:** Project restructure from flat layout to `src/` layout should be the first implementation story.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**

- LLM Abstraction: LangChain ChatModel interface qua LiteLLM proxy
- MCP Integration: Official MCP Python SDK client
- Pipeline Architecture: Sequential pipeline với clean stage interfaces

**Important Decisions (Shape Architecture):**

- Error Handling: tenacity retry + custom exception hierarchy
- Configuration: Pydantic Settings for system-level non-secret settings and encryption key validation
- Secret Storage: per-user encrypted PostgreSQL secret fields with rotation UX and no secret echoing in API/WebSocket responses
- Collaboration State: PostgreSQL-backed projects, memberships, private conversation threads, append-only messages, and thread-scoped agent runs
- Output Strategy: PostgreSQL artifact metadata + project-level shared SeaweedFS objects with required logical folders
- Realtime Sync: WebSocket artifact-change events scoped by project membership
- Security: Data boundary enforcement + audit trail + RBAC authorization checks on all project/thread/artifact/secret operations

**Deferred Decisions (Post-MVP):**

- CI/CD pipeline (Bitbucket on-prem, milestone sau)
- Multi-environment config beyond current deployment settings
- Provider comparison tests
- Direct external SeaweedFS event subscriptions
- Artifact version rollback
- Centralized admin prompt-template tuning

### Frontend & API Layer

- **Decision:** Conversational chat UI (React) + FastAPI REST/WebSocket backend
- **UI Pattern:** Direction D from UX spec — chat-style interaction with named AI agents
- **Frontend stack:** React 18+ / TypeScript / Shadcn/ui / Tailwind CSS / Vite
- **Backend API:** FastAPI with WebSocket for real-time chat message streaming
- **Communication:** WebSocket for live agent messages (Processing updates, Review presentations), REST for actions (Start, Approve, Reject, Continue)
- **Rationale:** Manual QA testers cannot use CLI. Conversational UI is the most natural pattern for non-technical users (Teams-like). FastAPI is Python-native, async, and integrates seamlessly with existing pipeline code
- **Frontend routes:**
  - `/` — Collaborative workspace shell for standard users. Includes collapsible sidebar, New Conversation, Conversation History, and Project / Artifacts section for the active thread's bound project.
  - `/admin` — Admin Dashboard for authenticated admin users. Admin users route only here and do not enter the standard project/thread workspace flow.
  - `/dashboard` — Metrics dashboard for leadership (Epic 10)
  - Use React Router v6 for client-side routing
- **Workspace behavior:** Before Alice binds a project, Project / Artifacts is empty. After binding, the sidebar shows only the selected project for the active thread and project selection is locked for that thread. Conversation History shows only the current user's threads.
- **Artifact UX:** Project members can browse/open/edit/delete shared artifacts for assigned projects regardless of creator. Empty required folders are shown even when SeaweedFS has no objects for a PostgreSQL project.
- **Secret UX:** UI shows provider/MCP secret status and replacement actions, but never displays stored secret values.
- **Realtime UX:** WebSocket artifact-change events trigger targeted artifact-tree refresh when the visible project changed. Refresh must not reset chat, current input, current step, or scroll position. If the opened artifact changes or is deleted, show a non-disruptive reload/close notice.
- **Accessibility:** WCAG 2.1 AA required (per UX-DR15). Establish focus ring styles (`ring-2 ring-blue-500 ring-offset-2`), aria attributes, and 44px minimum click targets from Story 2.2 (React scaffold). All subsequent UI stories must maintain these standards. Consult UX-DR15 for full requirements.

### Agent Orchestration Layer

- **Decision:** 5 named AI agents, each owning one pipeline step
- **Agents:** Alice (Configuration) → Bob (Extract Requirements) → Mary (Create Test Cases) → Sarah (Create Test Scripts) → Jack (Run Test Scripts)
- **Pattern:** Each agent follows the same lifecycle: Start → Processing → Review Request → (Approve/Reject+feedback) → Done
- **Human-in-the-loop:** Mandatory review gate at every step — no output advances without explicit user approval
- **Reject flow:** User provides feedback → agent self-corrects → re-presents for review
- **Alice (Step 1):** At the beginning of a new thread, asks the user to select one accessible project, binds that project immutably to the thread, then guides AI provider/MCP secret status and provider configuration. Provider choice determines which dynamically discovered and verified LLM models downstream agents use.
- **Alice project resolution:** For standard users, Alice loads accessible projects through the project list API before provider options are shown. Zero projects shows a no-access message and blocks provider selection. One project is auto-selected with a confirmation message. Multiple projects render a selectable list; choosing one adds a right-aligned user message with the selected project name. Admin routing remains dashboard-first and unchanged.
- **Thread binding:** Once Alice binds `project_id` to `conversation_threads.project_id`, that project cannot be changed within the thread. If user membership is later removed, the thread is hidden from Conversation History and API access is denied.
- **Configuration output:** Alice persists non-secret provider selection, verified model assignments, non-secret runtime settings, and selection rationale to PostgreSQL user configuration fields. User secrets are stored separately in encrypted per-user secret fields. No API/WebSocket response may return secret values.
- **Provider/model assignment:** Alice validates provider connection, discovers available models where supported, scores discovered models against Bob/Mary/Sarah/Jack needs, and persists only selected model IDs verified from discovery. Static model names are ranking hints only.
- **Agent execution scope:** Every agent run is stored as an `agent_runs` record scoped only by `thread_id`; user and project scope are derived from the referenced thread. Agent runs update only `conversation_threads.current_step` and `conversation_threads.status`.
- **Artifact pipeline:** Required logical SeaweedFS folders are project-scoped: `projects/{project_id}/requirements/`, `projects/{project_id}/test_cases/`, and `projects/{project_id}/test_scripts/`. Artifact metadata links optional originating `thread_id` and `agent_run_id`.
- **Location:** `src/ai_qa/agents/`

### LLM Abstraction Layer

- **Decision:** LangChain ChatModel interface
- **Backend:** On-prem LiteLLM proxy (`on_premises_ai_server_url`)
- **Rationale:** browser-use already uses LangChain internally — unified ecosystem
- **Provider switching:** Change model name in config, no code changes required
- **Affects:** All pipeline stages using LLM

### MCP Integration

- **Decision:** Official `mcp` Python SDK
- **Rationale:** Standard protocol, type-safe, automatic tool discovery
- **Scope:** Confluence (PoC), Jira (M1)
- **Separation:** Decoupled from LLM layer — independent evolution

### Pipeline Architecture

- **Decision:** 5-agent pipeline with human-in-the-loop review at each step
- **Flow:** `Alice (Config) → Bob (Extract) → Mary (Test Cases) → Sarah (Scripts) → Jack (Run)`
- **Internal stages:** Each agent composes pipeline stages internally (e.g., Bob uses `confluence_reader` + `content_parser`). Alice handles configuration only (no pipeline stages)
- **Rationale:** Agent-per-step enables mandatory human review gates and conversational feedback loops
- **Evolution path:** Pipeline stages remain independently testable; agents add orchestration + review on top
- **Location:** Agents in `src/ai_qa/agents/`, pipeline stages in `src/ai_qa/pipelines/`

### Error Handling & Resilience

- **Retry:** tenacity library with `@retry` decorator, exponential backoff
- **LLM retries:** max 3 attempts (per PRD)
- **MCP retries:** max 3 attempts with graceful failure messages
- **Browser recovery:** browser-use built-in crash recovery + Playwright timeouts
- **Exception hierarchy:** Custom exceptions in `ai_qa/exceptions.py`
- **Logging:** Python `logging` module, structured output
- **Stage results:** Result objects with status + errors, no direct raises from pipeline

### Configuration & Environment

- **Decision:** Pydantic Settings (BaseSettings) for system-level configuration only
- **Environment sources:** `.env` file + `config.yaml` + env var overrides for non-secret deployment settings and infrastructure secrets required by the application process, including provider base URLs, MCP server URL, database URL, SeaweedFS settings, and `USER_SECRETS_ENCRYPTION_KEY`
- **Not environment-owned:** Per-user AI provider API keys, MCP API key, selected provider, selected model assignments, and user runtime choices must not be stored in `.env`
- **Database-owned configuration:** PostgreSQL stores selected provider, selected verified model IDs, non-secret runtime settings, secret status metadata, and non-secret model-selection rationale
- **Validation:** At startup — fail fast if system-level config or encryption key is missing/invalid. At execution — fail fast with actionable user messages if required user secrets are absent, expired, or provider/model validation fails
- **Rationale:** browser-use/LangChain ecosystem already uses Pydantic, while secure multi-user operation requires separating deployment configuration from per-user secrets and runtime choices

### Output & Storage

- **Decision:** PostgreSQL state + S3-compatible Object Storage (SeaweedFS)
- **Database:** PostgreSQL stores users, password hashes, projects, memberships, conversation threads, append-only messages, agent runs, non-secret user provider configuration, encrypted user secrets, artifact metadata, artifact version metadata, and audit metadata.
- **File Storage:** SeaweedFS (or any S3-compatible service) stores actual file bytes (Markdown, JSON, Python scripts, images) via `S3ArtifactStorage`. PostgreSQL stores the S3 URI (`storage_path`) and access/ownership metadata.
- **Artifact sharing:** Artifacts are project-level shared resources. Any assigned project member can list, read, edit, and delete artifacts from other users in that project, subject to role/assignment checks.
- **Required folders:** UI and API must surface required logical folders even if no SeaweedFS objects exist yet.
- **Audit trail:** Audit events can be persisted in PostgreSQL and/or append-only JSONL in SeaweedFS; all events must include actor, project/thread/agent-run context where available, target resource, timestamp, and action.
- **Rationale:** Separating durable collaboration state, artifact bytes, and non-secret/secret configuration supports stateless web servers, project-level collaboration, access control, and artifact sync.

**Output Structure (SeaweedFS bucket `ai-qa-artifacts`):**

```text
ai-qa-artifacts/
  projects/
    {project_id}/
      requirements/
        extracted_requirements.md
      test_cases/
        generated_test_cases.json
      test_scripts/
        test_login_flow.py
```

**Artifact Metadata (PostgreSQL):**

- artifact identifier
- `project_id`
- `kind`
- `storage_path`
- owner/creator/updater user IDs
- optional version history
- optional originating `thread_id`
- optional originating `agent_run_id`
- timestamps and non-secret execution metadata

### Security Architecture

- **System secrets:** Application infrastructure secrets such as `USER_SECRETS_ENCRYPTION_KEY` are loaded from environment configuration and must not be stored in PostgreSQL.
- **User secrets:** AI provider API keys and MCP API key are per-user encrypted PostgreSQL fields. Stored values are never returned through API/WebSocket, never logged, and never written to messages/artifacts/generated files.
- **Secret rotation:** UI and API support replacement/update of user secrets without revealing existing values. Rotated secrets apply to future runs while existing thread/message history remains unchanged.
- **Password storage:** Passwords are stored as one-way password hashes, not plaintext or reversible encryption.
- **Data sovereignty:** All processing local; on-prem providers eliminate external API transfer when selected.
- **Browser scope:** Read-only — no form submissions, no data modifications
- **Transport:** HTTPS + certificate validation (httpx verify=True)
- **Authorization:** Every project, thread, message, agent run, artifact, and secret operation enforces user identity, role, and project membership. Thread access requires thread creator ownership plus current membership in the bound project.
- **Audit:** Append-only audit trail across pipeline, admin, secret rotation, artifact changes, and membership changes
- **Leakage prevention:** Ruff rules + strict `.gitignore` + secret redaction middleware/log filters + response schema tests that assert no secret values are serialized

### Realtime Synchronization Architecture

- **Decision:** Backend emits application-managed artifact change events through the existing WebSocket channel after artifact create, update, delete, or metadata-change operations.
- **Event payload:** `project_id`, artifact identifier, change type, timestamp, and non-secret summary metadata.
- **Delivery scope:** All connected clients for users assigned to the changed project receive the event, even when that project is not attached to their active thread.
- **Frontend behavior:** If the changed project is currently visible, refetch the Project / Artifacts tree without resetting chat, current input, current step, or scroll position. If an opened artifact changes or is deleted, show a non-disruptive notice with reload/close options.
- **Out of MVP:** Direct external SeaweedFS notifications and artifact version rollback.

### Decision Impact Analysis

**Implementation Sequence:**

1. Configuration (Pydantic Settings) — system-level settings, database URL, SeaweedFS settings, encryption key validation
2. Exception hierarchy — needed before building any component
3. Database models and migrations — users, projects, memberships, conversation threads, messages, agent runs, user secrets, artifact metadata
4. Secret encryption service — per-user provider/MCP key encryption, masking, replacement, and execution-time resolution
5. Auth/RBAC/project membership services — authorization foundation for admin, workspace, thread, artifact, and secret operations
6. LLM abstraction and provider adapters — LangChain/LiteLLM-compatible calls plus provider validation and model discovery contracts
7. MCP client (Confluence reader) — data source using execution-time current-user MCP secret
8. Artifact service — PostgreSQL metadata + SeaweedFS object storage + required logical folders + application-managed change events
9. Conversation/thread/message services — private user threads, immutable project binding, append-only messages, restored state
10. Agent run orchestration — thread-scoped runs, current-step/status updates, artifact origin metadata
11. Pipeline stages (sequential) — orchestration and generation
12. WebSocket hub — chat updates and project-scoped artifact change delivery
13. Frontend workspace/admin/artifact/secret UX — collaborative shell, admin dashboard, secret rotation, artifact browsing/editing
14. Audit logging — cross-cutting across pipeline, admin, secret, artifact, and membership events

**Cross-Component Dependencies:**

- Pydantic Settings → infrastructure services read system config only
- Exception hierarchy → all components throw/catch
- Auth/RBAC → API, WebSocket connection registration, projects, threads, artifacts, secrets, admin
- Secret service → provider adapters, MCP client, Alice configuration, downstream agents
- LLM provider adapters → Alice model discovery and pipeline LLM calls
- MCP client → Pipeline stages (ConfluenceReader)
- Thread/message service → agents, API, Conversation History
- Agent run service → agents, WebSocket updates, artifact origin metadata
- Artifact service → Pipeline stages (OutputWriter), frontend Project / Artifacts tree, WebSocket artifact events, audit logging

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**Critical Conflict Points Identified:** 7 areas where AI agents could make different choices — naming, structure, data formats, stage interfaces, error handling, imports, and enforcement.

### Naming Patterns

| Area | Convention | Example |
| --- | --- | --- |
| Modules/packages | snake_case | `ai_connection`, `test_case_extractor` |
| Classes | PascalCase | `ScriptGenerator`, `PipelineResult` |
| Functions/methods | snake_case | `extract_test_cases()`, `generate_script()` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRIES = 3`, `DEFAULT_TIMEOUT` |
| Private members | Leading underscore | `_parse_content()`, `_validate_input()` |
| Config keys (.env) | UPPER_SNAKE_CASE | `AI_API_KEY`, `MCP_SERVER_URL` |
| Config keys (YAML) | snake_case | `llm_model`, `max_retries` |
| Output folders | kebab-case | `test-login-flow/`, `test-search/` |
| Test files | `test_` prefix | `test_confluence_reader.py` |

### Structure Patterns

**Project Organization:**

- Tests in top-level `tests/` directory, mirroring `src/ai_qa/` structure
- Each pipeline stage in its own file within `pipelines/`
- Shared types/models in `src/ai_qa/models.py` (Pydantic models)
- All custom exceptions in `src/ai_qa/exceptions.py` (single hierarchy)
- Project-wide constants in `src/ai_qa/constants.py`
- Database persistence models live under `src/ai_qa/db/` with Alembic migrations in `alembic/versions/`
- Domain services live in focused packages: `auth/`, `projects/`, `threads/`, `secrets/`, `artifacts/`, and `realtime/`
- Provider-specific validation/model discovery lives behind adapter interfaces in `ai_connection/providers/`
- UI workspace concerns are separated into frontend feature areas: conversation history, project artifacts, admin dashboard, secret status/rotation, and shared WebSocket state

### Data Format Patterns

- **Internal data exchange:** Pydantic models between stages (never raw dicts)
- **JSON output keys:** snake_case
- **Datetime format:** ISO 8601 strings (`2026-04-06T10:30:00Z`)
- **Database IDs:** Use UUIDs for users, projects, threads, messages, agent runs, and artifacts unless an existing model already establishes a stricter convention
- **Thread messages:** Append-only records with `thread_id`, `sender`, `content`, non-secret metadata, and timestamp. Messages must never store raw secret values
- **Agent runs:** Records contain `thread_id`, status, timestamps, summary, and non-secret execution metadata only. User/project scope is derived from the thread
- **Artifact events:** WebSocket payloads include `project_id`, artifact identifier, change type, timestamp, and non-secret summary metadata
- **JSONL audit log:** Each line is a JSON object with `timestamp`, `actor_id`, `event`, `resource_type`, `resource_id`, `project_id`, optional `thread_id`, optional `agent_run_id`, and non-secret `details` fields

### Pipeline Stage Interface Pattern

Every pipeline stage MUST follow this standard interface:

```python
class StageResult(BaseModel):
    success: bool
    data: Any | None = None
    errors: list[str] = []
    warnings: list[str] = []
    confidence: float | None = None  # 0.0-1.0, used for human-in-the-loop review

async def process(input: InputModel, config: AppSettings) -> StageResult:
    """Every pipeline stage follows this signature pattern."""
```

### Error Handling Patterns

- **User-facing errors:** Clear English log message with suggested action
- **Internal errors:** Custom exceptions from `exceptions.py` only — never raise generic `Exception`
- **Logging levels:**
  - `ERROR` = requires action
  - `WARNING` = degraded but continuing
  - `INFO` = pipeline progress milestones
  - `DEBUG` = technical details
- **Retry:** Always use tenacity decorators — never hand-written retry loops

### Import Order Pattern

```python
# Standard library
import logging
from pathlib import Path

# Third-party
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt

# Local
from ai_qa.config import AppSettings
from ai_qa.exceptions import LLMError
```

### Enforcement Guidelines

**All AI Agents MUST:**

- Use Pydantic models for data exchange between stages (no raw dicts)
- Follow StageResult pattern for every pipeline stage
- Use custom exceptions — never raise generic Exception
- Use tenacity for retry logic — never hand-written retry loops
- Type hint all function signatures
- Ruff + mypy must pass before considering work done

**All AI Agents MUST ALSO:**

- Resolve user secrets only through the secret service at execution time
- Treat provider model names as valid only after provider discovery/verification
- Scope agent runs by `thread_id` and derive user/project scope from the thread
- Write artifacts through the artifact service so metadata, SeaweedFS object storage, authorization, audit, and realtime events stay consistent
- Preserve append-only message history; never mutate historical messages to reflect rotated secrets or changed artifacts

**Anti-Patterns (FORBIDDEN):**

- `dict` instead of Pydantic model between stages
- `print()` instead of `logging`
- Bare `except:` or `except Exception:`
- Hardcoded config values in code
- `import *` from any module
- Storing user API keys or MCP keys in `.env`, plaintext JSON columns, messages, WebSocket payloads, logs, artifacts, or generated files
- Returning stored secret values to the frontend
- Assigning a model not returned or verified by provider model discovery
- Reassigning an existing `agent_run` to another thread
- Changing `conversation_threads.project_id` after initial Alice binding
- Reading/writing SeaweedFS directly from agents or UI code without the artifact service

## Project Structure & Boundaries

### Complete Project Directory Structure

```text
ai-qa-automation/
├── pyproject.toml                  # Project metadata, dependencies, tool configs
├── uv.lock                         # Dependency lockfile
├── .python-version                 # Python 3.12+
├── .env                            # Secrets (gitignored)
├── .env.example                    # Template for .env
├── config.yaml                     # Runtime config (gitignored)
├── config.example.yaml             # Template for config.yaml
├── .gitignore
├── .pre-commit-config.yaml         # Ruff + mypy hooks
├── README.md
│
├── src/
│   └── ai_qa/
│       ├── __init__.py             # Package version
│       ├── __main__.py             # python -m ai_qa entry point
│       ├── cli.py                  # Click commands (admin/developer)
│       ├── config.py               # System-level Pydantic Settings only
│       ├── constants.py            # Project-wide constants
│       ├── exceptions.py           # Custom exception hierarchy
│       ├── models.py               # Shared Pydantic models
│       │
│       ├── db/                     # SQLAlchemy models, sessions, repositories
│       ├── auth/                   # Authentication, password hashing, current user
│       ├── projects/               # Projects, memberships, admin authorization
│       ├── threads/                # Conversation threads, messages, agent runs
│       ├── secrets/                # Encrypted per-user secrets and rotation metadata
│       ├── artifacts/              # PostgreSQL metadata + SeaweedFS object service + events
│       ├── realtime/               # WebSocket connection registry and project broadcasts
│       │
│       ├── api/                    # FastAPI web server
│       │   ├── __init__.py
│       │   ├── server.py           # FastAPI app, CORS, static files
│       │   ├── schemas.py          # API request/response schemas with secret redaction
│       │   ├── websocket.py        # Agent updates + artifact change events
│       │   └── routes/             # auth, admin, projects, threads, secrets, artifacts, agents
│       │
│       ├── agents/                 # Named AI agent orchestrators
│       │   ├── __init__.py
│       │   ├── base.py             # BaseAgent lifecycle + thread/agent_run integration
│       │   ├── alice.py            # Project binding, provider validation, model discovery
│       │   ├── bob.py              # Extract Requirements from Confluence
│       │   ├── mary.py             # Create Test Cases from requirements
│       │   ├── sarah.py            # Create Test Scripts from test cases
│       │   └── jack.py             # Run Test Scripts across browsers
│       │
│       ├── ai_connection/          # LLM abstraction layer
│       │   ├── __init__.py
│       │   ├── client.py           # LangChain ChatModel wrapper
│       │   ├── config.py           # Non-secret LLM runtime config models
│       │   ├── exceptions.py       # LLM-specific exceptions
│       │   └── providers/          # Provider validation/model discovery adapters
│       │
│       ├── mcp/                    # MCP integration using current-user MCP secret
│       ├── browser/                # browser-use + Playwright
│       ├── prompts/                # LLM prompt templates
│       ├── pipelines/              # Pipeline stages (used internally by agents)
│       └── audit/                  # Non-secret audit trail
│
├── frontend/                       # React collaborative workspace
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── components.json             # Shadcn/ui config
│   ├── public/
│   ├── src/
│   │   ├── App.tsx                 # Router + workspace/admin shells
│   │   ├── main.tsx                # React entry point
│   │   ├── index.css               # Tailwind directives
│   │   ├── components/ui/          # Shadcn/ui primitives
│   │   ├── features/
│   │   │   ├── workspace/          # Sidebar, project lock, zero-project state
│   │   │   ├── conversations/      # New Conversation, private history, active thread
│   │   │   ├── artifacts/          # Project / Artifacts tree, editor, preview notices
│   │   │   ├── secrets/            # Secret status + replacement UI, no value display
│   │   │   ├── admin/              # User/project/membership CRUD
│   │   │   └── agents/             # Agent messages, review content, input area
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts     # Shared WebSocket connection
│   │   │   ├── usePipelineState.ts # Agent workflow state
│   │   │   └── useArtifactSync.ts  # Non-disruptive artifact change handling
│   │   └── types/                  # TypeScript API schemas
│   └── dist/                       # Built static files (gitignored, served by FastAPI)
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Shared fixtures (config, mock LLM, etc.)
│   ├── test_config.py              # Config loading & validation tests
│   ├── test_exceptions.py          # Exception hierarchy tests
│   ├── test_api/
│   │   ├── __init__.py
│   │   ├── test_routes.py          # REST API endpoint tests
│   │   └── test_websocket.py       # WebSocket communication tests
│   ├── test_agents/
│   │   ├── __init__.py
│   │   ├── test_base.py            # BaseAgent lifecycle tests
│   │   ├── test_alice.py           # Alice agent tests (config, provider selection)
│   │   ├── test_bob.py             # Bob agent tests
│   │   ├── test_mary.py            # Mary agent tests
│   │   ├── test_sarah.py           # Sarah agent tests
│   │   └── test_jack.py            # Jack agent tests
│   ├── test_ai_connection/
│   │   ├── __init__.py
│   │   └── test_client.py          # LLM client tests
│   ├── test_mcp/
│   │   ├── __init__.py
│   │   └── test_confluence.py      # MCP Confluence tests
│   ├── test_browser/
│   │   ├── __init__.py
│   │   └── test_agent.py           # browser-use agent tests
│   └── test_pipelines/
│       ├── __init__.py
│       ├── test_confluence_reader.py
│       ├── test_content_parser.py
│       ├── test_test_case_extractor.py
│       ├── test_script_generator.py
│       ├── test_script_runner.py
│       └── test_output_writer.py
│
├── alembic/                        # Database migrations
├── docker-compose.yml              # Local PostgreSQL/SeaweedFS support
└── _bmad-output/                   # Planning artifacts (not runtime)

Runtime artifact bytes are stored in SeaweedFS under `projects/{project_id}/...`; runtime state and metadata are stored in PostgreSQL.
```

### Architectural Boundaries

**Module Boundaries:**

| Module | Responsibility | Depends On | Does NOT depend on |
| --- | --- | --- | --- |
| `config` | System-level app settings, validation, encryption key presence | pydantic-settings | user secret values, domain services |
| `exceptions` | Exception hierarchy | nothing | anything else |
| `models` | Shared Pydantic models | pydantic | persistence internals |
| `db` | SQLAlchemy models, sessions, repositories | config, sqlalchemy | frontend, agent logic |
| `auth` | authentication, password hashing, current user context | db, exceptions | pipeline internals |
| `projects` | projects, memberships, admin CRUD authorization | db, auth | ai_connection, mcp, browser |
| `threads` | private conversation threads, append-only messages, agent run state | db, auth, projects | artifact bytes, provider SDKs |
| `secrets` | per-user encrypted provider/MCP secrets and rotation metadata | db, auth, config crypto key | API response schemas exposing values |
| `ai_connection` | provider adapters, validation, model discovery, LLM calls | config, secrets, langchain | mcp, browser, agents |
| `mcp` | MCP server communication using current-user MCP secret | config, secrets, exceptions, mcp-sdk | ai_connection, browser, agents |
| `browser` | Browser automation | config, exceptions, browser-use | mcp, ai_connection directly, agents |
| `artifacts` | metadata, SeaweedFS object I/O, required folders, artifact events | db, projects, realtime, audit | direct UI/agent SeaweedFS bypass |
| `pipelines` | Reusable pipeline stages | config, models, ai_connection, mcp, browser, artifacts | api, frontend |
| `agents` | Named agent orchestrators and thread-scoped agent runs | threads, secrets, models, pipelines, audit | api internals |
| `audit` | Append-only non-secret audit trail | db/config/models | raw secret values |
| `realtime` | WebSocket connection registry and project-scoped event delivery | auth, projects | business logic mutation |
| `api` | FastAPI REST + WebSocket | auth, projects, threads, secrets, artifacts, agents, models | direct storage bypass |
| `cli` | Admin/developer CLI | config, agents/services | frontend |
| `frontend/` | React collaborative workspace | api (via HTTP/WebSocket) | all Python modules |

**Dependency Rule:** Frontend communicates with backend only via API/WebSocket. API coordinates domain services; agents coordinate thread-scoped workflows; pipelines call integration/storage services. No component may bypass auth/project membership checks, secret service, or artifact service.

### Requirements to Structure Mapping

**FR1-4 (Confluence Integration):**

- `src/ai_qa/mcp/client.py` — MCP SDK connection
- `src/ai_qa/mcp/confluence.py` — Confluence page reading
- `src/ai_qa/pipelines/confluence_reader.py` — Pipeline stage

**FR5-9 (Test Script Generation):**

- `src/ai_qa/pipelines/test_case_extractor.py` — NL → test case extraction
- `src/ai_qa/pipelines/script_generator.py` — Test case → Playwright script
- `src/ai_qa/ai_connection/client.py` — LLM calls for generation

**FR10-13 (Pipeline Execution):**

- `src/ai_qa/agents/` — Agent orchestrators (Bob, Mary, Sarah, Jack)
- `src/ai_qa/api/server.py` — FastAPI web entry point
- `src/ai_qa/cli.py` — CLI entry point (admin/developer)
- `src/ai_qa/browser/agent.py` — browser-use agent

**FR14-15b (Secure Configuration and Dynamic Model Discovery):**

- `src/ai_qa/config.py` — system-level Pydantic Settings and encryption key validation
- `src/ai_qa/secrets/` — per-user encrypted AI provider and MCP key storage, rotation, masking, execution-time resolution
- `src/ai_qa/ai_connection/providers/` — provider validation and model discovery adapters
- `src/ai_qa/agents/alice.py` — provider/model review, discovered-model scoring, actionable recovery messages

**FR16 (Administration):**

- `src/ai_qa/projects/` — user/project/membership domain services
- `src/ai_qa/api/routes/admin.py` — admin-only CRUD endpoints
- `frontend/src/features/admin/` — admin dashboard

**FR17-18 (Backlog/Removed Scope):**

- Provider comparison test hooks can be added later under `ai_connection/evaluation/`
- Centralized prompt-template tuning is intentionally not an MVP architecture surface

**FR19-22 (Human-in-the-Loop):

- `src/ai_qa/agents/base.py` — BaseAgent review gate lifecycle (Start→Process→Review→Approve/Reject→Done)
- `src/ai_qa/api/websocket.py` — Real-time review presentation via WebSocket
- `src/ai_qa/api/routes.py` — Approve/Reject REST endpoints
- `frontend/src/components/ChatInputArea.tsx` — Approve/Reject/Feedback UI

**FR23-24 (Jira Integration, M1):**

- `src/ai_qa/mcp/jira.py` — Placeholder for M1

**FR25-29 (Quality, Observability, and Reporting):**

- `src/ai_qa/audit/logger.py` — non-secret audit trail
- Future: `src/ai_qa/metrics/` module for success rates, effort reduction, and LLM cost tracking

**FR30-41 (Collaborative Project Threads and Agent Runs):**

- `src/ai_qa/threads/` — conversation thread, message, and agent-run services
- `src/ai_qa/api/routes/threads.py` — New Conversation, Conversation History, restore thread state
- `frontend/src/features/conversations/` — conversation history and active-thread state

**FR42-46 (Shared Artifact Storage):**

- `src/ai_qa/artifacts/service.py` — metadata + SeaweedFS operations + required folder projection
- `src/ai_qa/artifacts/storage.py` — S3/SeaweedFS adapter
- `src/ai_qa/api/routes/artifacts.py` — project-member artifact list/read/edit/delete endpoints
- `frontend/src/features/artifacts/` — Project / Artifacts tree and editor/preview

**FR47-53 (Collaborative Workspace UX):**

- `frontend/src/features/workspace/` — shell, sidebar, project lock display, empty pre-selection state, zero-project message
- `frontend/src/features/conversations/` — New Conversation and private Conversation History

**FR54-60 (Secure User Secret Storage and Rotation):**

- `src/ai_qa/secrets/` — encrypted secret persistence, status metadata, replacement flows
- `src/ai_qa/api/routes/secrets.py` — secret status and replacement endpoints that never return values
- `frontend/src/features/secrets/` — secret status and replacement UI

**FR61-67 (Project Artifact Realtime Sync):**

- `src/ai_qa/realtime/` — WebSocket connection registry and project-scoped artifact event broadcast
- `src/ai_qa/artifacts/events.py` — application-managed artifact change events
- `frontend/src/hooks/useArtifactSync.ts` — non-disruptive artifact tree refresh and opened-artifact notices

### Data Flow

```text
[React Collaborative Workspace]
       │
       ├── REST: auth, admin, projects, threads, secrets, artifacts, agent actions
       ├── WebSocket: agent messages, processing updates, review content, artifact events
       │
       ▼
  api/server.py (FastAPI)
       │
       ├── auth/projects services ──→ [PostgreSQL: users, password_hashes, projects, memberships]
       ├── threads service ────────→ [PostgreSQL: conversation_threads, append-only messages, agent_runs]
       ├── secrets service ────────→ [PostgreSQL encrypted user secrets]
       │                               ▲
       │                               └── encryption key from AppSettings.USER_SECRETS_ENCRYPTION_KEY
       ├── artifacts service ──────→ [PostgreSQL artifact metadata] + [SeaweedFS ai-qa-artifacts]
       │                               └── emits artifact change event ─→ realtime hub ─→ authorized project clients
       │
       ▼
  agents/ (thread-scoped named orchestrators)
       │
       ├── alice.py
       │     ├── list accessible projects for current user
       │     ├── bind selected project to new thread immutably
       │     ├── read secret status / request replacement if missing or expired
       │     ├── resolve current-user provider secret through secrets service
       │     ├── validate provider connection and discover models through provider adapter
       │     ├── persist non-secret selected provider/model assignments and rationale
       │     └── append messages + update thread current_step/status
       │
       ├── bob.py
       │     ├── derive user/project from thread_id
       │     ├── resolve current-user MCP secret and selected model
       │     ├── confluence_reader.py ──→ mcp/confluence.py ──→ [MCP Server]
       │     ├── content_parser.py
       │     └── artifacts/service.py ──→ projects/{project_id}/requirements/
       │
       ├── mary.py
       │     ├── derive user/project from thread_id
       │     ├── read requirements via artifact service
       │     ├── test_case_extractor.py ──→ ai_connection provider adapter
       │     └── artifacts/service.py ──→ projects/{project_id}/test_cases/
       │
       ├── sarah.py
       │     ├── derive user/project from thread_id
       │     ├── read test cases via artifact service
       │     ├── script_generator.py ──→ ai_connection provider adapter + browser/agent.py
       │     └── artifacts/service.py ──→ projects/{project_id}/test_scripts/
       │
       └── jack.py
             ├── derive user/project from thread_id
             ├── read scripts via artifact service
             ├── script_runner.py ──→ [Chrome/Firefox/Edge]
             └── append execution report + artifact metadata

  audit/logger.py ──→ [PostgreSQL / SeaweedFS] (non-secret cross-cutting audit)
```

### Development Workflow

**Backend Setup:**

```bash
uv sync                    # Install all deps + editable install
cp .env.example .env       # Configure secrets
cp config.example.yaml config.yaml
pre-commit install         # Setup git hooks
```

**Frontend Setup:**

```bash
cd frontend
npm install                # Install frontend deps
cd ..
```

**Run (development — two terminals):**

```bash
# Terminal 1: Backend API
uv run python -m ai_qa     # Starts FastAPI on localhost:8000

# Terminal 2: Frontend dev server
cd frontend && npm run dev  # Starts Vite on localhost:5173 (proxies API to :8000)
```

**Run (production — single process):**

```bash
cd frontend && npm run build  # Build static files to frontend/dist/
uv run python -m ai_qa       # FastAPI serves both API and static frontend
```

**Run (CLI — admin/developer only):**

```bash
uv run ai-qa generate --url "https://confluence.example.com/page/123"
```

**Test:**

```bash
uv run pytest                      # All backend tests
uv run pytest tests/test_agents/   # Agent tests only
uv run pytest tests/test_api/      # API tests only
cd frontend && npm run test        # Frontend tests (if added)
```

**Lint:**

```bash
uv run ruff check src/ tests/
uv run mypy src/
cd frontend && npm run lint        # ESLint + TypeScript check
```

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**

- Python 3.12 + uv + Hatchling + src layout — fully compatible
- LangChain + browser-use + LiteLLM proxy — browser-use uses LangChain natively, no conflicts
- MCP SDK + Pydantic Settings + tenacity — independent, no version conflicts
- FastAPI + async agents — native async support, WebSocket for real-time chat
- React + Shadcn/ui + Tailwind — well-documented, AI-friendly code generation
- Click CLI retained for admin — bridge via `asyncio.run()` in CLI entry point

**Pattern Consistency:**

- snake_case naming throughout (Python convention) — consistent
- Pydantic models between all stages — enforced by StageResult pattern
- tenacity retry consistent for LLM + MCP — same decorator pattern
- Import order pattern clearly defined — enforceable by Ruff isort rules

**Structure Alignment:**

- Module boundaries respect downward-only dependency rule
- Every FR category maps clearly to directories
- Test structure mirrors source structure

### Requirements Coverage Validation ✅

**Functional Requirements Coverage:**

| FR Category | Architectural Support | Status |
| --- | --- | --- |
| FR1-4 Confluence Integration | `mcp/confluence.py` + `pipelines/confluence_reader.py` | ✅ Covered |
| FR5-9 Test Script Generation | `pipelines/test_case_extractor.py` + `script_generator.py` | ✅ Covered |
| FR10-13 Pipeline Execution | `agents/` + `threads/agent_runs` + `api/server.py` + `browser/agent.py` | ✅ Covered |
| FR14-15b Secure Configuration | `config.py` + `secrets/` + provider adapters + Alice discovery/review | ✅ Covered |
| FR16 Administration | `projects/`, `auth/`, admin API routes, admin frontend feature | ✅ Covered |
| FR17-18 Backlog/Removed | Provider comparisons deferred; admin prompt tuning excluded | ✅ Reflected |
| FR19-22 Human-in-the-Loop | `agents/base.py` review lifecycle + `api/websocket.py` + workspace agent UI | ✅ Covered |
| FR23-24 Jira Integration | `mcp/jira.py` placeholder | ⏳ M1 |
| FR25-29 Quality/Observability/Reporting | `audit/logger.py`, future `metrics/` | ✅ Partial |
| FR30-41 Threads/Agent Runs | `threads/` services, append-only messages, thread-scoped agent runs | ✅ Covered |
| FR42-46 Shared Artifacts | `artifacts/` service, PostgreSQL metadata, SeaweedFS project folders | ✅ Covered |
| FR47-53 Workspace UX | `frontend/src/features/workspace/` and conversations/artifacts features | ✅ Covered |
| FR54-60 Secret Storage/Rotation | `secrets/` service and secret status/replacement API/UI | ✅ Covered |
| FR61-67 Artifact Realtime Sync | `realtime/`, artifact events, `useArtifactSync` | ✅ Covered |

**Non-Functional Requirements Coverage:**

| NFR | Architectural Support | Status |
| --- | --- | --- |
| <5 min per test case | Sequential async pipeline with persisted run state | ✅ |
| <30s per browser action | Playwright timeout config | ✅ |
| On-premises data only | Environment-controlled endpoints, on-prem provider option, no secret/log leakage | ✅ |
| User secrets never exposed | Encrypted PostgreSQL fields, secret service, response redaction, no message/artifact/log serialization | ✅ |
| Encryption key handling | `USER_SECRETS_ENCRYPTION_KEY` from environment, startup validation, not stored in PostgreSQL | ✅ |
| Browser read-only | browser-use config enforcement | ✅ |
| LLM retry max 3 | tenacity `stop_after_attempt(3)` | ✅ |
| MCP failure handling | tenacity retry + custom exceptions + actionable user recovery | ✅ |
| Browser crash recovery | browser-use built-in + Playwright timeouts | ✅ |
| Startup validation | Pydantic Settings fail-fast for infrastructure settings and encryption key | ✅ |
| Project/thread authorization | RBAC and membership checks on all APIs/WebSocket events | ✅ |

### Implementation Readiness Validation ✅

**Decision Completeness:**

- All critical decisions documented with library choices ✅
- Implementation patterns comprehensive with code examples ✅
- Consistency rules clear with anti-patterns listed ✅
- StageResult interface pattern provides concrete template ✅

**Structure Completeness:**

- All files and directories defined with purpose comments ✅
- Module boundaries table with explicit dependency rules ✅
- Integration points mapped in data flow diagram ✅
- Development workflow commands provided ✅

**Pattern Completeness:**

- Naming conventions cover all areas (code, config, output) ✅
- Error handling pattern with logging levels defined ✅
- Import order pattern enforceable by tooling ✅
- Pipeline stage interface standardized ✅

### Gaps Identified and Resolved

| Gap | Resolution | Impact |
| --- | --- | --- |
| No prompt template location | Added `src/ai_qa/prompts/` directory | Prompt reuse remains possible without MVP admin tuning |
| No confidence scoring in StageResult | Added `confidence: float \| None` field | FR21 low-confidence flagging ready |
| Hardcoded output directory | Replaced with project-level SeaweedFS folders and PostgreSQL artifact metadata | FR42-46 shared artifacts supported |
| No web UI for non-technical users | Added React frontend + FastAPI API layer | FR19-22 human-in-the-loop enabled |
| No agent orchestration layer | Added `agents/` module with BaseAgent lifecycle | Named agent pipeline enabled |
| CLI-only interface excluded manual testers | FastAPI + WebSocket + React collaborative workspace | Zero-code barrier removed |
| Secret storage ambiguous | Added encrypted per-user secret service and rotation UX | FR54-60 and security NFRs covered |
| Conversation state ambiguous | Added private threads, append-only messages, and thread-scoped agent runs | FR30-41 covered |
| Artifact collaboration missing | Added project-level artifact metadata, required folders, and role-checked cross-user access | FR42-46 covered |
| Artifact realtime sync missing | Added application-managed artifact change events over WebSocket | FR61-67 covered |

### Architecture Completeness Checklist

#### ✅ Requirements Analysis

- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints identified
- [x] Cross-cutting concerns mapped

#### ✅ Architectural Decisions

- [x] Critical decisions documented (LLM, MCP, Pipeline, Config)
- [x] Technology stack fully specified (Python 3.12+, uv, LangChain, etc.)
- [x] Integration patterns defined (MCP SDK, LangChain ChatModel)
- [x] Performance considerations addressed (async, retry, timeouts)

#### ✅ Implementation Patterns

- [x] Naming conventions established (snake_case, PascalCase, etc.)
- [x] Structure patterns defined (module boundaries, dependency rules)
- [x] Communication patterns specified (Pydantic models, StageResult)
- [x] Process patterns documented (error handling, retry, logging)

#### ✅ Project Structure

- [x] Complete directory structure defined with all files
- [x] Component boundaries established with dependency table
- [x] Integration points mapped in data flow diagram
- [x] Requirements to structure mapping complete for all FRs

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** High — all critical decisions made, patterns defined, structure complete

**Key Strengths:**

- Clean sequential pipeline — easy to debug, test, and evolve
- Consistent Pydantic-based data flow — type-safe across all stages
- On-prem constraint enforced at architecture level — no accidental data leakage
- Clear module boundaries prevent circular dependencies
- M1 features have placeholders ready in structure (review/, jira.py, metrics/)
- Standard Python tooling (pytest, ruff, mypy) — well-supported ecosystem

**Areas for Future Enhancement (Post-MVP):**

- Event-driven or parallelized pipeline if throughput becomes a bottleneck
- CI/CD pipeline (Bitbucket on-premises)
- Provider comparison test harness
- Direct external SeaweedFS notifications if application-managed events are insufficient
- Artifact version rollback
- Metrics dashboard depth (`src/ai_qa/metrics/` + frontend dashboard page)
- Multi-environment configuration management beyond current deployment settings
- Dark mode frontend theme

### Implementation Handoff

**AI Agent Guidelines:**

- Follow all architectural decisions exactly as documented
- Use implementation patterns consistently across all components
- Respect module boundaries — no circular dependencies
- Use StageResult for every pipeline stage output
- Refer to this document for all architectural questions

**First Implementation Priority:**

1. `config.py` with Pydantic Settings for system-level settings and `USER_SECRETS_ENCRYPTION_KEY` validation
2. `exceptions.py` with custom exception hierarchy
3. Database models/migrations for users, projects, memberships, conversation threads, messages, agent runs, user secrets, and artifact metadata
4. Secret encryption service with status, replacement, redaction, and execution-time resolution
5. Auth/RBAC/project membership enforcement across API and WebSocket connection registration
6. Artifact service with PostgreSQL metadata, SeaweedFS storage, required folder projection, and artifact change events
7. Thread/message/agent-run services with immutable project binding and append-only message persistence
8. Provider adapter interfaces for validation and dynamic model discovery
9. Alice end-to-end: project binding → secret status → provider validation/model discovery → review → persisted non-secret configuration
10. Bob end-to-end: thread-scoped run → current-user MCP secret → Confluence extraction → project artifact write → realtime artifact event

## Corrective Addendum: Alice Provider Configuration and Dynamic Model Discovery

### Alice Provider Configuration and Dynamic Model Discovery

Alice owns the provider configuration flow for each authenticated user.

The system must not rely on static provider-to-model mappings for downstream agents. Instead, Alice performs a runtime model-selection pipeline:

1. Load provider base URL from environment configuration.
2. Collect provider API key from the authenticated user.
3. Validate provider connection using the selected provider credentials.
4. Discover available models from the selected provider/server where supported.
5. Normalize discovered model identifiers into a provider-neutral structure.
6. Score available models against downstream agent needs.
7. Select one valid discovered model for each downstream agent.
8. Emit a user-reviewable reasoning trace.
9. Persist only validated selected model IDs for the authenticated user/account.

If connection validation fails, model discovery fails, or no usable models are returned, Alice must not create a successful model assignment review and must not persist agent model configuration.

### Configuration Ownership Boundary

System-level URLs and base endpoints are deployment configuration and must be loaded from `.env` or equivalent environment settings:

- Browser Use Cloud base URL
- Claude API base URL
- Gemini API base URL
- ChatGPT/OpenAI API base URL
- On-Premises API base URL
- MCP server URL

User-specific secrets must not be stored in `.env`. They must be collected from user input and stored securely per authenticated user/account:

- Browser Use Cloud API key
- Claude API key
- Gemini API key
- OpenAI API key
- On-Premises API key
- MCP API key

Workflow-specific targets must remain runtime user inputs:

- target page URL
- SSO options
- project-specific login/runtime parameters

### Provider Model Discovery Contract

Each provider adapter should expose a model discovery capability:

- `validate_connection(credentials, base_url) -> ConnectionResult`
- `list_models(credentials, base_url) -> list[DiscoveredModel]`

`DiscoveredModel` should include at minimum:

- `id`
- `display_name`
- `provider`
- optional `capability_hints`
- optional `context_window`
- optional `supports_tools`
- optional `supports_vision`
- optional `cost_tier`
- optional `latency_tier`

For OpenAI-compatible providers, including On-Premises deployments, model discovery should use the configured base URL and the provider's model listing endpoint where available.

Alice must treat static model names only as ranking hints after verifying availability. Static names must never be persisted unless returned by discovery.

### Agent Model Selection Heuristics

Alice scores discovered models against each downstream agent's needs:

- Bob:
  - strong reasoning
  - long-context extraction
  - structured requirement extraction
  - tool-compatible responses where available

- Mary:
  - strong instruction following
  - structured output
  - test design reasoning
  - consistency across many test cases

- Sarah:
  - code generation strength
  - browser automation/tool-use compatibility
  - framework-aware output
  - optional vision/multimodal capability if available

- Jack:
  - execution analysis
  - concise summarization
  - speed and cost efficiency
  - reliable structured reporting

If capability metadata is unavailable, Alice may infer capability hints from model IDs, but must document uncertainty in the reasoning trace.
