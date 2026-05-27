---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
inputDocuments:
  - prd.md
  - architecture.md
  - ux-design-specification.md
---

# browser-use-custom - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for browser-use-custom, decomposing the requirements from the PRD, UX Design if it exists, and Architecture requirements into implementable stories.

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
FR14: Engineer can configure the pipeline via a `.env` file (API keys, MCP server URL, target page URL, SSO options)
FR15: Engineer can set LLM parameters including model selection and temperature
FR16: Admin can switch between LLM providers (Claude, DeepSeek, Qwen) via configuration (Milestone 1)
FR17: Admin can run comparison tests between LLM providers to evaluate script quality (Milestone 1)
FR18: Admin can tune prompt templates to optimize generation quality per LLM (Milestone 1)
FR19: Reviewer can view generated scripts alongside their source Confluence test cases for side-by-side comparison (Milestone 1)
FR20: Reviewer can approve or reject individual generated scripts (Milestone 1)
FR21: Reviewer can edit generated scripts before approval (Milestone 1)
FR22: Pipeline can flag low-confidence generations for mandatory review (Milestone 1)
FR23: Pipeline can connect to on-premises Jira Data Center via MCP server (Milestone 1)
FR24: Pipeline can retrieve test-related requirements from Jira tickets (Milestone 1)
FR25: Pipeline can log which Confluence pages were read, which scripts were generated, and by whom (Milestone 1)
FR26: Pipeline can report script execution success rate (Milestone 1)
FR27: Pipeline can detect insufficient input quality and warn before generation (Milestone 1)
FR28: Leadership can view metrics dashboard showing scripts generated, success rates, and effort reduction (Milestone 1)
FR29: Leadership can view LLM cost tracking and comparison data (Milestone 1)

### NonFunctional Requirements

NFR1: Pipeline end-to-end generation within 5 minutes per test case (PoC)
NFR2: Individual browser actions complete within 30 seconds to avoid timeout cascading
NFR3: Generated Playwright scripts execute within standard Playwright timeout defaults (30 seconds per action)
NFR4: LLM API latency dependent on provider SLA; Claude Enterprise typical latency acceptable for batch processing
NFR5: No data transmitted outside company infrastructure — on-prem constraint enforced at all phases
NFR6: API keys and credentials in `.env` only — never committed to version control, never logged
NFR7: Browser sessions reuse existing SSO — pipeline must not store, cache, or log credentials
NFR8: AI browser agent restricted to read-only navigation — no form submissions, data modifications, or write operations during generation
NFR9: Milestone 1: audit logging of all pipeline executions (who, when, which page, which scripts)
NFR10: Milestone 1: on-premises LLMs eliminate external API data transfer entirely
NFR11: MCP server unavailability: fail gracefully with clear error messages
NFR12: LLM API: handle rate limits, timeouts, and transient errors with retry logic (max 3 retries)
NFR13: browser-use: handle browser crashes or navigation failures without corrupting partial output
NFR14: Playwright output: valid standalone Python files — executable with only Playwright as dependency
NFR15: `.env` validation: check all required values at startup, fail fast with actionable error messages

### Additional Requirements

- **Project restructure:** Migrate from flat layout to `src/ai_qa/` with PEP 621 compliant src layout — first implementation story per Architecture
- **Starter template:** Manual restructure selected (no template generator) — project already has existing `ai_connection/` module, `pyproject.toml`, `uv.lock`
- **FastAPI + React frontend:** Conversational chat UI (React 18+ / TypeScript / Shadcn/ui / Tailwind CSS / Vite) with FastAPI REST/WebSocket backend — replaces CLI as primary user interface
- **5 named AI agents:** Alice (Configuration), Bob (Extract Requirements), Mary (Create Test Cases), Sarah (Create Test Scripts), Jack (Run Test Scripts) — each follows Start→Processing→Review→Done lifecycle via BaseAgent
- **LLM abstraction:** LangChain ChatModel interface via on-prem LiteLLM proxy — browser-use already uses LangChain natively
- **MCP integration:** Official `mcp` Python SDK client — standard protocol, type-safe, automatic tool discovery
- **Pipeline architecture:** 5-agent pipeline with mandatory human-in-the-loop review at each step. File pipeline: `configuration/` → `requirements/` → `testcases/` → `testscripts/` → `report/`
- **Configuration:** Pydantic Settings (BaseSettings) with `.env` + `config.yaml` + env var overrides. Fail fast at startup
- **Error handling:** tenacity library with `@retry` decorator, exponential backoff. Custom exception hierarchy in `ai_qa/exceptions.py`. Max 3 retries for LLM and MCP
- **Output strategy:** Hybrid file-based output + JSON metadata per test case (source URL, timestamp, model, confidence). Audit trail as `audit_log.jsonl` (JSONL append-only)
- **Testing:** pytest + pytest-asyncio + pytest-cov. Tests in top-level `tests/` mirroring `src/ai_qa/` structure
- **Linting:** Ruff (replaces black, isort, flake8). Target Python 3.12, line-length 100. mypy for static type checking
- **Build system:** Hatchling — modern, lightweight, native uv compatibility
- **CLI (secondary):** Click framework for admin/developer tasks, debugging, direct pipeline execution without UI
- **Implementation patterns:** Pydantic models between all stages (never raw dicts), StageResult pattern for every pipeline stage, snake_case naming throughout, structured logging (no print())
- **Workspace folder:** `workspace/` directory (gitignored) for per-run pipeline output with per-step subfolders
- **Alice configuration output:** `provider.json` (selected provider, credentials, endpoint) and `agents.json` (per-agent config: model, prompt template, tools/capabilities)
- **Pre-commit hooks:** Ruff + mypy hooks via `.pre-commit-config.yaml`

### UX Design Requirements

UX-DR1: Conversational chat UI (Direction D) — chat-style interaction with named AI agents as chat participants. Agent messages left-aligned (white), user messages right-aligned (blue). Based on Microsoft Teams familiarity
UX-DR2: AgentTopBar component — persistent header with agent avatar (initial letter + color), agent name, step title, step counter (X of 5), status badge. Supports Start/Processing/Review/Done/Completed states
UX-DR3: ChatMessage component — agent and user message bubbles with rich content support (rendered markdown, tables, code blocks, images). Agent bubbles: white with left border-radius flat. User bubbles: blue with right border-radius flat. Accessible with `role="listitem"`
UX-DR4: ChatInputArea component — context-dependent input area that changes based on pipeline state: Start (input field + Start button), Processing (disabled), Review (Approve + Reject buttons), Reject-feedback (textarea + Submit), Done (Continue button), Completed (Completed button for Step 5)
UX-DR5: ReviewContent component — renders rich AI output within chat bubbles: react-markdown with GFM for requirements/test cases, react-syntax-highlighter for Playwright Python scripts, mermaid.js for diagrams, images with alt text. Max-height 400px with internal ScrollArea
UX-DR6: StepDots component — minimal 5-dot progress indicator (completed=green, active=blue, pending=grey). 8px dots. `role="progressbar"` with aria attributes
UX-DR7: ProcessingIndicator component — animated typing dots (3 dots with staggered bounce, 1.4s cycle) plus status message text. `aria-live="polite"` and `role="status"`
UX-DR8: Status Badge System — Start (grey outline), Processing (amber pulsing), Review Request (blue solid), Done (green + checkmark), Completed (green + checkmark, Step 5 only). Color + text + icon (colorblind-safe)
UX-DR9: Color System "Professional Calm" — primary Slate Blue (#3B82F6/blue-500), background white, surface slate-50, borders slate-200, text primary slate-900, text secondary slate-500. Semantic: success green-500, warning amber-500, error red-500, info blue-500 with light tint backgrounds
UX-DR10: Typography System — system font stack only (no custom fonts). Type scale: Step Title text-xl/semibold, Agent Name text-lg/medium, Body text-base/normal, Code text-sm/font-mono, Status Badge text-xs/medium. Monospace for code display
UX-DR11: Button Hierarchy — max 2 buttons visible at a time. Primary (solid): Start/Approve/Continue/Completed/Submit. Secondary (outline): Reject (red outline, never solid). Primary always on right. No confirmation dialogs. Disabled buttons show why via tooltip
UX-DR12: Feedback Patterns — all feedback conversational through agent messages. Success: green checkmark + summary + next action hint. Error: 3-part structure (what happened/why/what to do) + Retry button. Warning: yellow icon per issue, specific guidance. Rejection ack: agent paraphrases feedback + begins re-processing
UX-DR13: State Transition Machine — universal for every step: Start→Processing→ReviewRequest→Done. With Error (from Processing, retry returns to Processing) and RejectFeedback (from ReviewRequest, submit returns to Processing). Transition animations: badge fade 150ms, input slide-up 200ms, messages fade-in 150ms
UX-DR14: Navigation — forward-only during pipeline execution (no skip ahead). StepDots informational only (not clickable). Item-level pagination: Next/Previous buttons during multi-item review. Approve applies to current item only, auto-advance to next
UX-DR15: Accessibility WCAG 2.1 AA — visible focus rings (`ring-2 ring-blue-500 ring-offset-2`), form inputs with associated labels (not placeholder-only), min 44px click targets, `aria-describedby` for error messages, keyboard Tab navigation, `aria-live="polite"` for status changes, screen reader support
UX-DR16: Split Panel Layout for review states — 50/50 grid (`grid grid-cols-2`), 16px gap, independent scroll per panel, min-height 400px. Left panel: source content (Confluence iframe or rendered view). Right panel: extracted/generated content
UX-DR17: Alice (Step 1) AI Provider Selection UI — 4 provider options (Browser Use Cloud / Claude / Gemini-ChatGPT / On-Premises) with quality rank, security level, credential type. Connection testing. Review shows model assignment table per agent. Configuration saved to `configuration/` folder, remembered for future sessions
UX-DR18: Chat scroll behavior — auto-scroll to bottom on new messages. User can scroll up to review history. "↓ New message" indicator if scrolled up. Chat history clears on step transition (new agent = fresh chat)
UX-DR19: Agent personalities — Alice (A/pink), Bob (B/blue), Mary (M/green), Sarah (S/purple), Jack (J/orange). Each has greeting message introducing themselves and their role
UX-DR20: One-time setup inputs remembered across sessions — AI provider + credentials (Step 1), MCP PAT (Step 2), Chrome path (Step 4), browser paths (Step 5). Subsequent runs skip or pre-fill these inputs

### FR Coverage Map

| FR | Epic | Description |
| --- | --- | --- |
| FR1 | Epic 3 | Confluence MCP connection + SSO |
| FR2 | Epic 3 | Retrieve Confluence page content |
| FR3 | Epic 3 | Parse natural-language test cases |
| FR4 | Epic 7 | Confluence content variations (M1) |
| FR5 | Epic 4, 5 | Interpret NL test steps → browser actions |
| FR6 | Epic 5 | Generate Playwright Python scripts |
| FR7 | Epic 5 | One test file per test case |
| FR8 | Epic 5 | Stable selectors (data-testid, role) |
| FR9 | Epic 5 | Map expected results → assertions |
| FR10 | Epic 3, 6 | Trigger pipeline via Confluence URL |
| FR11 | Epic 6 | End-to-end pipeline execution |
| FR12 | Epic 5 | browser-use controls Chrome via SSO |
| FR13 | Epic 5, 6 | Configurable output directory |
| FR14 | Epic 1 | .env configuration |
| FR15 | Epic 1, 2 | LLM parameters config |
| FR16 | Epic 2, 8 | LLM provider switching (M1) |
| FR17 | Epic 8 | LLM comparison tests (M1) |
| FR18 | Epic 8 | Prompt template tuning (M1) |
| FR19 | Epic 8 | Side-by-side review (M1) |
| FR20 | Epic 8 | Approve/reject scripts (M1) |
| FR21 | Epic 8 | Edit scripts before approval (M1) |
| FR22 | Epic 7 | Low-confidence flagging (M1) |
| FR23 | Epic 9 | Jira MCP connection (M1) — Story 9.1a |
| FR24 | Epic 9 | Jira test requirements (M1) — Story 9.1a |
| FR25 | Epic 9 | Audit logging (M1) — Stories 9.1b, 9.2, 9.3 |
| FR26 | Epic 10 | Script success rate reporting (M1) |
| FR27 | Epic 7 | Input quality detection (M1) |
| FR28 | Epic 10 | Metrics dashboard (M1) |
| FR29 | Epic 10 | LLM cost tracking (M1) |

## Epic List

### Epic 3 Overview: Requirements Extraction from Confluence (Agent Bob)

User pastes a Confluence URL, Bob connects via MCP server, extracts content, and converts to markdown/images. User reviews side-by-side with original Confluence, approves/rejects per page. Output saved to `requirements/` folder.
**FRs covered:** FR1, FR2, FR3, FR10 (partial)

### Epic 4 Overview: Test Case Generation (Agent Mary)

Mary reads extracted requirements from Bob, generates natural-language test cases optimized for browser-use execution. User reviews each test case, approves/rejects with feedback. Output saved to `testcases/` folder.
**FRs covered:** FR5 (partial)

### Epic 6 Overview: Test Execution & Reporting (Agent Jack)

Jack runs test scripts across Chrome/Firefox/Edge, generates execution reports with pass/fail per test per browser. Pipeline completes end-to-end. User sees final results.
**FRs covered:** FR10, FR11, FR13

### Epic 7 Overview: Input Quality Detection & Confidence Scoring (Milestone 1)

Pipeline automatically detects low-quality test cases, flags low-confidence generations. Users are warned before generation, reviewers see confidence scores per script.
**FRs covered:** FR4, FR22, FR27

### Epic 8 Overview: Advanced Review & LLM Management (Milestone 1)

Reviewer can edit scripts before approval. Admin can switch between LLM providers, run comparison tests, and tune prompt templates for quality optimization.
**FRs covered:** FR16, FR17, FR18, FR19, FR20, FR21

### Epic 9 Overview: Jira Integration & Audit Trail (Milestone 1)

Pipeline connects to Jira Data Center via MCP for test-related requirements. Full audit logging records all pipeline activity (who read what, generated what, when).
**FRs covered:** FR23, FR24, FR25

## Epic 1: Project Foundation & Infrastructure Setup

R&D engineer (Duc) has a properly structured project with config system, exception handling, shared models, and dev tooling — the foundation for all pipeline development.

### Story 1.1: Project Restructure to src Layout

As a R&D engineer,
I want the project restructured from flat layout to `src/ai_qa/` PEP 621 compliant src layout,
So that the codebase follows Python best practices and supports editable install via `uv sync`.

**Acceptance Criteria:**

**Given** the existing project with `ai_connection/` module and `pyproject.toml`
**When** the restructure is applied
**Then** all existing code is moved to `src/ai_qa/` directory structure
**And** `pyproject.toml` is updated with Hatchling build system, project metadata, and `[project.scripts]` entry point
**And** `uv sync` installs the package in editable mode successfully
**And** `python -m ai_qa` runs without import errors
**And** existing `ai_connection/` module is relocated to `src/ai_qa/ai_connection/`

### Story 1.2: Configuration System with Pydantic Settings

As a R&D engineer,
I want a centralized configuration system using Pydantic Settings,
So that all pipeline components read validated config from `.env` + `config.yaml` with env var overrides.

**Acceptance Criteria:**

**Given** a fresh project setup
**When** the engineer creates `.env` and `config.yaml` files from example templates
**Then** `AppSettings` class loads and validates all config values at startup
**And** missing required values cause immediate failure with actionable error messages (NFR15)
**And** `.env.example` and `config.example.yaml` templates are committed to version control
**And** `.env` and `config.yaml` are gitignored (NFR6)
**And** environment variable overrides take precedence over file values
**And** LLM parameters (model selection, temperature) are configurable (FR15)
**And** API keys and MCP server URL are configurable via `.env` (FR14)

### Story 1.3: Custom Exception Hierarchy

As a R&D engineer,
I want a structured exception hierarchy in `src/ai_qa/exceptions.py`,
So that all pipeline components use consistent, meaningful error types instead of generic exceptions.

**Acceptance Criteria:**

**Given** the exception module is created
**When** any pipeline component encounters an error
**Then** it raises a custom exception from the hierarchy (e.g., `LLMError`, `MCPError`, `BrowserError`, `ConfigError`, `PipelineError`)
**And** all custom exceptions inherit from a base `AIQAError`
**And** each exception includes a user-friendly message and optional technical details
**And** generic `Exception` or bare `except:` are forbidden (enforced by code convention)

### Story 1.4: Shared Pydantic Models (StageResult, AgentMessage)

As a R&D engineer,
I want shared Pydantic models in `src/ai_qa/models.py`,
So that all pipeline stages and agents exchange data through typed, validated models — never raw dicts.

**Acceptance Criteria:**

**Given** the models module is created
**When** any pipeline stage completes processing
**Then** it returns a `StageResult` model with fields: `success: bool`, `data: Any | None`, `errors: list[str]`, `warnings: list[str]`, `confidence: float | None`
**And** `AgentMessage` model supports agent-to-frontend communication (sender, content, timestamp, message type)
**And** all JSON output uses snake_case keys
**And** datetime fields use ISO 8601 format
**And** project-wide constants are defined in `src/ai_qa/constants.py`

### Story 1.5: Dev Tooling Setup (Ruff, mypy, pytest, pre-commit)

As a R&D engineer,
I want linting, type checking, testing, and pre-commit hooks configured,
So that code quality is enforced automatically from the start.

**Acceptance Criteria:**

**Given** the project structure is in place
**When** the engineer runs dev tools
**Then** `ruff check src/ tests/` passes with Python 3.12 target and line-length 100
**And** `mypy src/` passes with type hints validated
**And** `pytest` runs with pytest-asyncio and pytest-cov configured
**And** `tests/` directory mirrors `src/ai_qa/` structure with `conftest.py`
**And** `.pre-commit-config.yaml` runs Ruff + mypy on every commit
**And** `pre-commit install` sets up git hooks successfully
**And** at least one basic test exists to verify the test infrastructure works

## Epic 2: AI Provider Configuration & Connection (Agent Alice)

User opens the app, Alice guides them to select an AI provider (Claude/On-Prem/Gemini/ChatGPT/Browser Use Cloud), enter credentials, and test the connection. Configuration is saved and remembered for future sessions. Full conversational chat UI established.

### Story 2.1: FastAPI Server Foundation with WebSocket Support

As a R&D engineer,
I want a FastAPI server with REST endpoints and WebSocket support,
So that the React frontend can communicate with the pipeline backend in real-time.

**Acceptance Criteria:**

**Given** the FastAPI server module is created at `src/ai_qa/api/`
**When** the server starts via `python -m ai_qa`
**Then** FastAPI app runs on `localhost:8000` with CORS configured for frontend dev server
**And** WebSocket endpoint at `/ws` accepts connections and can send/receive JSON messages
**And** REST endpoints exist for pipeline actions: `/api/start`, `/api/approve`, `/api/reject`, `/api/continue`
**And** API request/response models are defined in `api/schemas.py` as Pydantic models
**And** server serves static files from `frontend/dist/` in production mode
**And** `__main__.py` starts the FastAPI server as the default entry point

### Story 2.2: React Frontend Scaffold with Shadcn/ui

As a R&D engineer,
I want a React 18+ frontend scaffolded with Vite, TypeScript, Tailwind CSS, and Shadcn/ui,
So that the conversational chat UI has a solid foundation with the correct design system.

**Acceptance Criteria:**

**Given** the `frontend/` directory is initialized
**When** `npm install && npm run dev` is executed
**Then** Vite dev server starts on `localhost:5173` with proxy to backend `:8000`
**And** Tailwind CSS is configured with the "Professional Calm" color system (UX-DR9): primary blue-500, surface slate-50, borders slate-200, semantic success/warning/error/info colors
**And** Shadcn/ui is initialized with required primitive components: Button, Card, Input, Textarea, Label, Badge, ScrollArea, Alert, Progress, Avatar, Checkbox, Separator
**And** System font stack is configured (no custom fonts) (UX-DR10)
**And** TypeScript types for pipeline state are defined in `types/pipeline.ts`
**And** `useWebSocket` hook connects to backend WebSocket and handles reconnection

### Story 2.3: BaseAgent Lifecycle (Start → Processing → Review → Done)

As a R&D engineer,
I want a BaseAgent class that implements the shared agent lifecycle,
So that all 5 agents (Alice/Bob/Mary/Sarah/Jack) follow the same Start→Processing→Review→Done pattern.

**Acceptance Criteria:**

**Given** the `agents/base.py` module is created
**When** an agent processes a request
**Then** it transitions through states: Start → Processing → ReviewRequest → (Approve/Reject+feedback) → Done
**And** reject with feedback triggers re-processing using the feedback context
**And** agent sends messages to frontend via WebSocket using `AgentMessage` model
**And** each agent has configurable properties: name, color, step number, step title
**And** the agent reads its config from `configuration/agents.json` if available
**And** the `workspace/` directory structure is created per run with subfolders: `configuration/`, `requirements/`, `testcases/`, `testscripts/`, `report/`

### Story 2.4: AgentTopBar and StepDots Components

As a manual QA tester (Linh),
I want to see which AI agent is active, what step I'm on, and the current status,
So that I always know where I am in the pipeline.

**Acceptance Criteria:**

**Given** the chat UI is open
**When** an agent is active
**Then** AgentTopBar shows agent avatar (initial letter with color), agent name, step title, and step counter "Step X of 5" (UX-DR2)
**And** status badge displays correct state with colors: Start (grey), Processing (amber pulsing), Review Request (blue), Done (green + checkmark) (UX-DR8)
**And** StepDots show 5 dots: completed (green), active (blue), pending (grey) (UX-DR6)
**And** status badge uses color + text + icon (colorblind-safe) (UX-DR8)
**And** AgentTopBar has `role="banner"` and status changes announced via `aria-live="polite"` (UX-DR15)

### Story 2.5: ChatMessage Component with Rich Content

As a manual QA tester (Linh),
I want to see agent messages and my own messages in a familiar chat layout,
So that interacting with the AI pipeline feels like chatting with a colleague.

**Acceptance Criteria:**

**Given** the conversational chat UI is rendered
**When** messages are exchanged
**Then** agent messages display left-aligned with white background and flat bottom-left radius (UX-DR3)
**And** user messages display right-aligned with blue background and flat bottom-right radius (UX-DR3)
**And** agent messages show avatar, name, and timestamp
**And** rich content within bubbles supports rendered markdown via react-markdown with GFM (UX-DR5)
**And** code blocks display with syntax highlighting via react-syntax-highlighter (UX-DR5)
**And** content exceeding 400px height shows internal ScrollArea (UX-DR5)
**And** chat area auto-scrolls to bottom on new messages, with "↓ New message" indicator when scrolled up (UX-DR18)
**And** chat messages have `role="listitem"` within chat area `role="list"` (UX-DR15)

### Story 2.6: ChatInputArea Component (State-Dependent Actions)

As a manual QA tester (Linh),
I want the input area to show the right buttons based on what's happening,
So that I always know what action to take next.

**Acceptance Criteria:**

**Given** the pipeline is in a specific state
**When** the state changes
**Then** Start state shows input field(s) + Start button (UX-DR4)
**And** Processing state shows disabled area with "Agent is working..." text (UX-DR4)
**And** Review state shows Approve (green solid) + Reject (red outline) buttons (UX-DR4, UX-DR11)
**And** Reject-feedback state shows textarea + Submit button (UX-DR4)
**And** Done state shows Continue button (blue solid) (UX-DR4)
**And** max 2 buttons visible at a time, primary action on the right (UX-DR11)
**And** disabled Start button shows tooltip explaining why (e.g., "Enter Confluence URL to start") (UX-DR11)
**And** no confirmation dialogs — Reject opens feedback inline (UX-DR11)
**And** focus automatically moves to primary action on state change (UX-DR15)
**And** state transitions animate: badge fade 150ms, input slide-up 200ms, messages fade-in 150ms (UX-DR13)

### Story 2.7: ProcessingIndicator and Error Feedback

As a manual QA tester (Linh),
I want to see what the agent is doing during processing and get clear guidance when errors occur,
So that I never feel lost or anxious about what's happening.

**Acceptance Criteria:**

**Given** an agent is in Processing state
**When** work is in progress
**Then** ProcessingIndicator shows 3 animated dots (staggered bounce, 1.4s cycle) + status message (UX-DR7)
**And** status message updates in-place with progress (e.g., "Reading page 3 of 5...")
**And** ProcessingIndicator has `aria-live="polite"` and `role="status"` (UX-DR7)
**Given** a pipeline error occurs (MCP timeout, LLM failure)
**When** the error is displayed
**Then** agent message uses 3-part structure: what happened / why / what to do (UX-DR12)
**And** error message includes a Retry button inside the message bubble (UX-DR12)
**And** no technical jargon, stack traces, or HTTP status codes in error messages (UX-DR12)

### Story 2.8: Alice Agent — AI Provider Selection & Configuration

As a user,
I want Alice to guide me through selecting an AI provider and configuring credentials,
So that I can connect to an AI service and all subsequent agents know which models to use.

**Acceptance Criteria:**

**Given** the user opens the app for the first time
**When** Alice's step begins
**Then** Alice greets with introduction: "Hi! I'm Alice. Let's set up your AI provider..." (UX-DR19, pink avatar)
**And** Alice presents 4 provider options with quality rank and security level: Browser Use Cloud (1st/cloud), Claude (2nd/enterprise), Gemini/ChatGPT (3rd/cloud), On-Premises (4th/highest security) (UX-DR17)
**And** based on selection, appropriate credential fields appear (API key, or server URL + API key for On-Premises)
**And** Alice tests the connection and shows Processing state during verification
**And** on success, Review Request shows model assignment table per agent (e.g., Bob→Opus, Mary→Sonnet) (UX-DR17)
**And** user can Approve to confirm or Reject to change provider
**And** configuration saved to `workspace/configuration/provider.json` and `agents.json` (UX-DR17)
**And** configuration remembered for future sessions — subsequent runs skip Step 1 unless user reconfigures (UX-DR20)
**And** on-premises provider pre-fills from `.env` values if available

## Epic 3: Requirements Extraction from Confluence (Agent Bob)

User pastes a Confluence URL, Bob connects via MCP server, extracts content, and converts to markdown/images. User reviews side-by-side with original Confluence, approves/rejects per page. Output saved to `requirements/` folder.

### Story 3.1: MCP Client Foundation

As a R&D engineer,
I want an MCP client using the official `mcp` Python SDK,
So that the pipeline can connect to the on-premises MCP server for Confluence access.

**Acceptance Criteria:**

**Given** the `src/ai_qa/mcp/` module is created
**When** the MCP client initializes with server URL from config
**Then** it connects to the MCP server and discovers available tools automatically
**And** connection failures raise `MCPError` with clear error message (NFR11)
**And** retry logic uses tenacity with max 3 attempts and exponential backoff (NFR12)
**And** all data stays on-premises — no external transmission (NFR5)
**And** SSO authentication is reused from existing browser session (FR1)

### Story 3.2: Confluence Reader Pipeline Stage

As a R&D engineer,
I want a Confluence reader pipeline stage that retrieves page content via MCP,
So that Bob can extract test case content from any Confluence page URL.

**Acceptance Criteria:**

**Given** a valid Confluence page URL is provided
**When** the confluence reader executes
**Then** it retrieves the full page content via MCP `confluence.py` tools (FR2)
**And** returns a `StageResult` with page title, content body, and metadata
**And** handles MCP server unavailability with graceful failure and clear error message (NFR11)
**And** multiple pages from a Confluence space can be discovered and listed
**And** the stage works with the Confluence page URL as the pipeline trigger (FR10)

### Story 3.3: Content Parser — Markdown, Mermaid, and Images

As a R&D engineer,
I want a content parser that converts Confluence content to LLM-friendly formats,
So that extracted requirements are clean markdown suitable for subsequent pipeline stages.

**Acceptance Criteria:**

**Given** raw Confluence page content is retrieved
**When** the content parser processes it
**Then** text content is converted to clean Markdown with proper headings, lists, and tables (FR3)
**And** diagrams are converted to Mermaid format where possible
**And** images are preserved and saved to the output folder
**And** the parser handles natural-language test cases and extracts their structure
**And** returns a `StageResult` with parsed content and any warnings about content issues

### Story 3.4: Output Writer Pipeline Stage

As a R&D engineer,
I want a reusable output writer that saves pipeline results to organized folders,
So that all agents use consistent file output with metadata.

**Acceptance Criteria:**

**Given** a pipeline stage produces output
**When** the output writer saves results
**Then** files are written to the correct workspace subfolder (e.g., `workspace/requirements/`)
**And** each output includes a `metadata.json` with source URL, timestamp, model used, and confidence score
**And** file naming is derived from source content titles using kebab-case
**And** the output directory is configurable (FR13)
**And** partial output from failed stages is not corrupted (NFR13)

### Story 3.5: Bob Agent — Extract Requirements with Paginated Review

As a manual QA tester (Linh),
I want Bob to extract my Confluence pages and let me review each one side-by-side with the original,
So that I can verify the extraction is accurate before proceeding.

**Acceptance Criteria:**

**Given** Bob's step begins after Alice completes
**When** Bob greets the user
**Then** Bob introduces himself: "Hi! I'm Bob, and I'll help you extract requirements from Confluence." (UX-DR19, blue avatar)
**And** guidance text explains MCP PAT setup if first time (UX-DR20)
**And** user enters Confluence project URL (required) and Jira URL (optional)
**Given** user clicks Start
**When** Bob processes the request
**Then** Bob connects to MCP, navigates Confluence space, extracts pages
**And** Processing indicator shows progress per page (e.g., "Reading page 3 of 5...")
**Given** extraction completes
**When** Review Request is presented
**Then** split panel shows: left = link to open original Confluence page in new tab, right = rendered markdown (not raw) (UX-DR16)
**And** Next/Previous buttons navigate between pages (UX-DR14)
**And** Approve applies to current page only, auto-advances to next (UX-DR14)
**And** Reject opens feedback textarea, Bob re-processes that single page with feedback context
**And** after all pages approved, status changes to Done with summary: "X files saved to requirements/"
**And** output saved to `workspace/requirements/` folder
**And** chat history clears when transitioning to next agent (UX-DR18)

## Epic 4: Test Case Generation (Agent Mary)

Mary reads extracted requirements from Bob, generates natural-language test cases optimized for browser-use execution. User reviews each test case, approves/rejects with feedback. Output saved to `testcases/` folder.

> **Dependencies:** Requires Story 3.4 (Output Writer Pipeline Stage) complete.
> **Cross-epic note:** Story 4.1 (LLM Abstraction Layer) created in this epic is a shared dependency for Epics 5, 6, and 8. Story 4.1 must be marked Done before starting any of those epics.

### Story 4.1: LLM Abstraction Layer (LangChain + LiteLLM)

As a R&D engineer,
I want an LLM abstraction layer using LangChain ChatModel interface,
So that all agents can call LLMs through a unified interface regardless of provider.

**Acceptance Criteria:**

**Given** the `src/ai_qa/ai_connection/` module is refactored
**When** an agent needs to call an LLM
**Then** it uses a LangChain ChatModel wrapper that routes through the on-prem LiteLLM proxy
**And** the model name is read from `configuration/agents.json` (set by Alice in Step 1)
**And** provider switching requires only a config change, no code changes
**And** LLM errors raise `LLMError` with retry logic (tenacity, max 3 attempts, exponential backoff) (NFR12)
**And** temperature is configurable per agent (default 0.0 for deterministic output)
**And** no data is transmitted outside company infrastructure (NFR5)

### Story 4.2: Test Case Extractor Pipeline Stage

As a R&D engineer,
I want a test case extractor that uses LLM to generate structured test cases from requirements,
So that Mary can produce browser-use-optimized test cases from extracted content.

**Acceptance Criteria:**

**Given** markdown requirement files exist in `workspace/requirements/`
**When** the test case extractor processes them
**Then** it sends requirements to the LLM with a prompt template from `src/ai_qa/prompts/test_extraction.py`
**And** generates structured test cases with: title, preconditions, numbered steps, and expected results
**And** test cases are optimized for browser-use execution (actionable browser steps)
**And** interprets natural-language test case steps into browser automation intent (FR5)
**And** returns `StageResult` with generated test cases and confidence score
**And** generation completes within 5 minutes per test case (NFR1)

### Story 4.3: Mary Agent — Create Test Cases with Per-Item Review

As a manual QA tester (Linh),
I want Mary to generate test cases from my requirements and let me review each one,
So that I can verify the AI understood my intent before scripts are generated.

**Acceptance Criteria:**

**Given** Mary's step begins after Bob completes
**When** Mary greets the user
**Then** Mary introduces herself: "Hi! I'm Mary. I'll create test cases from the requirements Bob extracted." (UX-DR19, green avatar)
**And** no user input needed — Mary reads from `workspace/requirements/`
**Given** user clicks Start
**When** Mary processes the requirements
**Then** Processing indicator shows progress per test case (e.g., "Generating test case 3 of 12...")
**Given** generation completes
**When** Review Request is presented
**Then** each test case is displayed with clear structure: title, preconditions, steps, expected results
**And** Next/Previous buttons navigate between test cases (UX-DR14)
**And** Approve applies to current test case only, auto-advances to next
**And** Reject with feedback triggers Mary to self-correct and re-present that test case
**And** Mary paraphrases feedback in acknowledgment before re-processing (UX-DR12)
**And** after all test cases approved, status Done with summary: "X test cases saved to testcases/"
**And** output saved to `workspace/testcases/`

## Epic 5: Test Script Generation (Agent Sarah)

Sarah reads test cases, uses vision model + LLM to generate Playwright Python scripts with stable selectors. User or automation engineer reviews side-by-side test case vs script. Output saved to `testscripts/` folder.

> **Dependencies:** Requires Story 3.4 (Output Writer) and Story 4.1 (LLM Abstraction Layer) complete before starting this epic.

### Story 5.1: Browser-Use Agent Configuration and Session Management

As a R&D engineer,
I want browser-use framework integrated with Chrome via SSO session,
So that Sarah can use vision model to identify locators on the target application.

**Acceptance Criteria:**

**Given** the `src/ai_qa/browser/` module is created
**When** the browser agent initializes
**Then** it configures browser-use to control a local Chrome instance (FR12)
**And** reuses the active SSO login session — no additional credential storage (NFR7)
**And** browser agent operates in read-only mode — no form submissions, data modifications, or write operations (NFR8)
**And** browser crashes or navigation failures are handled without corrupting partial output (NFR13)
**And** individual browser actions complete within 30 seconds (NFR2)
**And** Chrome path is configurable and remembered after first input (UX-DR20)

### Story 5.2: Script Generator Pipeline Stage

As a R&D engineer,
I want a script generator that converts test cases into Playwright Python scripts via LLM,
So that Sarah can produce executable, well-structured test files.

**Acceptance Criteria:**

**Given** structured test cases exist in `workspace/testcases/`
**When** the script generator processes them
**Then** it generates executable Python Playwright test scripts (FR6)
**And** one test file is produced per test case with naming derived from test case title (FR7)
**And** selectors prefer stable strategies: data-testid, role-based over CSS path/XPath (FR8)
**And** expected results from test cases are mapped into Playwright assertions (FR9)
**And** generated scripts are valid standalone Python files executable with only Playwright as dependency (NFR14)
**And** prompt templates are loaded from `src/ai_qa/prompts/script_generation.py`
**And** returns `StageResult` with generated scripts and confidence score

### Story 5.3: Vision-Assisted Locator Identification

As a R&D engineer,
I want Sarah to use a vision model to identify accurate locators on the target application,
So that generated scripts use reliable selectors based on actual page state.

**Acceptance Criteria:**

**Given** a test case references UI elements on the target application
**When** Sarah generates the script
**Then** browser-use navigates to the target page and captures visual state
**And** vision model identifies UI elements matching test case steps (FR5)
**And** locators are validated against the actual DOM
**And** fallback to LLM-only generation if browser-use is unavailable
**And** generation completes within 5 minutes per test case (NFR1)

### Story 5.4: Sarah Agent — Generate Scripts with Side-by-Side Review

As a manual QA tester (Linh) or QA automation engineer (Minh),
I want Sarah to generate Playwright scripts and let me review each one alongside its source test case,
So that I can verify the script correctly implements the test case.

**Acceptance Criteria:**

**Given** Sarah's step begins after Mary completes
**When** Sarah greets the user
**Then** Sarah introduces herself: "Hi! I'm Sarah. I'll generate Playwright test scripts from Mary's test cases." (UX-DR19, purple avatar)
**And** user inputs local Chrome path (remembered after first time) (UX-DR20)
**Given** user clicks Start
**When** Sarah processes test cases
**Then** Processing indicator shows progress per script (e.g., "Generating script 2 of 12...")
**Given** generation completes
**When** Review Request is presented
**Then** split panel shows: left = natural-language test case, right = Playwright Python script with syntax highlighting (UX-DR16, UX-DR5)
**And** Next/Previous buttons navigate between test case + script pairs (UX-DR14)
**And** Approve applies to current script only, auto-advances to next
**And** Reject with feedback triggers Sarah to self-correct that script
**And** Linh can skip review and ask Minh (automation engineer) to review instead
**And** after all scripts approved, status Done: "X scripts saved to testscripts/"
**And** output saved to `workspace/testscripts/` with metadata per script (FR13)
**Note (FR19 scope boundary):** This story delivers the base split-panel layout only — no selector highlighting, no assertion linking, no confidence score overlay. Those enhancements are deferred to Epic 8 Story 8.2. Do not over-engineer the panel here.

## Epic 12: Decoupled Backend, Database, Auth, and Project Foundation

This epic pivots the product from a single-user file-based workspace into a decoupled multi-user system. React remains the frontend, FastAPI remains the backend, PostgreSQL becomes the source of truth, and generated Markdown/Mermaid/script files are managed as project-scoped artifacts. This epic must be completed before resuming Epic 6+ execution, metrics, audit, or enterprise integrations.

> **Dependencies:** Builds on Epic 1 (project structure), Epic 2 (FastAPI/React foundation), and the completed agent pipeline foundations from Epics 3–5.
> **Course correction:** Azure Entra ID SSO is deferred to a later enterprise backlog item. R&D authentication uses local email/password accounts, with initial admin accounts seeded manually or via CLI.

### Story 12.1: PostgreSQL Persistence Foundation with SQLAlchemy and Alembic

As a R&D engineer,
I want PostgreSQL persistence configured with SQLAlchemy models and Alembic migrations,
So that backend data has a versioned, scalable source of truth instead of ad-hoc workspace files.

**Acceptance Criteria:**

**Given** the backend starts in development mode
**When** database configuration is loaded
**Then** the application connects to PostgreSQL using environment-driven settings
**And** SQLAlchemy 2.x models are defined for `users`, `projects`, `project_memberships`, `pipeline_runs`, `artifacts`, `artifact_versions`, and `audit_events`
**And** Alembic is configured with an initial migration for the core schema
**And** `alembic upgrade head` creates or updates the schema successfully
**And** database health is exposed through a backend health check endpoint
**And** tests can run against an isolated test database or transaction-scoped test session

### Story 12.2: Local Authentication and Admin Bootstrap

As a project user,
I want to log in with local email/password credentials during R&D,
So that the system can support multiple users before enterprise SSO is approved.

**Acceptance Criteria:**

**Given** the backend auth module is available
**When** an admin creates a user account
**Then** the password is stored only as a secure hash
**And** duplicate email creation is rejected
**And** login returns an authenticated session or token suitable for protected API calls
**And** current-user endpoint returns the authenticated user profile and role
**And** an admin account can be seeded manually or via CLI (no self-service registration allowed)
**And** Azure Entra ID SSO remains documented as a deferred production/enterprise backlog item

### Story 12.3: Role-Based Access Control for Admin and Standard Users

As an admin,
I want role-based permissions enforced by the backend,
So that only authorized users can manage users and projects.

**Acceptance Criteria:**

**Given** authenticated users have roles
**When** an admin accesses admin APIs
**Then** they can view the user list, create projects, and assign users to projects
**And** standard users cannot access admin-only endpoints
**And** all protected endpoints reject unauthenticated requests
**And** authorization failures return consistent error responses without leaking sensitive details
**And** RBAC checks are covered by API tests

### Story 12.4: Project and Membership Management API

As an admin,
I want to create projects and assign users to them,
So that project teams can share the same QA automation workspace and results.

**Acceptance Criteria:**

**Given** users and projects exist
**When** an admin assigns users to a project
**Then** `project_memberships` stores the many-to-many relationship between users and projects
**And** assigned users can see the project in their project list after login
**And** users only see projects where they are members unless they are admin
**And** project-scoped endpoints validate membership before returning data
**And** API schemas are documented automatically in OpenAPI/Swagger under `/docs`

### Story 12.5: Project-Scoped Artifact Service

As a project member,
I want generated Markdown, Mermaid, and script files to be linked to a project,
So that everyone in the same project can review and edit shared AI outputs.

**Acceptance Criteria:**

**Given** a pipeline stage produces Markdown, Mermaid, Playwright scripts, screenshots, or reports
**When** the artifact service saves the output
**Then** artifact metadata is stored in PostgreSQL with `project_id`, artifact type, owner, timestamps, and current version
**And** large file content is stored through a local artifact storage abstraction rather than directly by agents
**And** artifact versions preserve edit history for user-modified outputs
**And** agents read and write artifacts through the artifact service, not by hard-coded `workspace/` paths
**And** the storage abstraction can later be replaced by MinIO/S3-compatible object storage without rewriting agent logic

### Story 12.6: Frontend Login, Project Selection, and API Client Foundation

As a project member,
I want to log in and select a project before running the agent pipeline,
So that all generated results are scoped to the correct shared project.

**Acceptance Criteria:**

**Given** the React frontend starts
**When** an unauthenticated user opens the app
**Then** they see a login flow (without self-registration) instead of the pipeline workspace
**And** authenticated users see a project picker containing only accessible projects
**And** the selected project ID is included in project-scoped API calls and WebSocket connections
**And** admin users can access basic user/project management screens
**And** API client code targets `/api/v1` endpoints and handles authentication errors consistently

### Story 12.7: Refactor Existing Pipeline from Workspace Paths to Project Context

As a R&D engineer,
I want existing agents and stages to operate on project context instead of global local workspace folders,
So that multi-user project collaboration works without breaking the current agent workflow.

**Acceptance Criteria:**

**Given** Bob, Mary, Sarah, and Jack run in sequence
**When** they need previous-stage inputs or need to save new outputs
**Then** they resolve inputs through project-scoped artifact queries
**And** generated outputs are saved via the artifact service with versions and metadata
**And** pipeline runs are recorded in `pipeline_runs` with project, triggering user, status, timestamps, and summary
**And** legacy `workspace/` assumptions are isolated behind compatibility adapters or removed where safe
**And** existing completed functionality from Epics 3–5 remains operational after the refactor

### Story 12.8: Bugfix - Admin Routing and Dashboard Enhancements

As an admin,
I want to be routed directly to an administrative dashboard when logging in,
So that I can bypass project selection and manage users and projects effectively.

**Acceptance Criteria:**

**Given** an authenticated user with the 'admin' role logs in
**When** the frontend routes the user
**Then** the admin bypasses the Project Picker and goes straight to the Admin Dashboard
**Given** the admin is on the Admin Dashboard
**When** they view the interface
**Then** there is a functional "Logout" button
**And** the admin's email, display name, and role are displayed next to the "Logout" button
**And** there is a vertical list on the left showing projects with create, edit name, and delete buttons
**And** there is a vertical list on the right showing users and the projects they belong to
**And** there are buttons to assign projects to members and remove users from projects

### Story 12.9: Admin Dashboard Refinement and Fixes

As an admin,
I want the dashboard UI and APIs to be fully functional and streamlined,
So that I can effectively manage users and projects.

**Acceptance Criteria:**

- **Given** an admin is on the dashboard, **when** they click Edit or Delete on a project, **then** the action calls the implemented backend API (`PUT /projects/{id}`, `DELETE /projects/{id}`) and updates the UI successfully.
- **Given** a success notification appears, **then** it automatically hides after 3 seconds.
- **Given** the user management area, **then** the "Manage Membership" section is replaced by a "Create User" form (with Email, Display Name, Initial Password fields).
- **Given** the "Create User" form, **then** there is a disabled button "Sync existing company's users" that displays "This feature is not available at the moment, please add manually." on hover.
- **Given** the user list, **then** the UI is restructured so each user card has a "Projects" section with a "+" button to assign a project and an "x" button on assigned projects to unassign them.
- **Given** the login screen, **then** the "Need an account? Create one" link is removed, enforcing that only admins can create new accounts.

### Story 12.10: User Project Selection in Alice Configuration Flow

As a project member,
I want project selection to happen inside Alice's configuration chat flow,
So that I can start the pipeline directly after login without a separate Project Workspace screen.

**Acceptance Criteria:**

- **Given** a standard user logs in successfully, **when** routing completes, **then** the frontend bypasses the Project Workspace screen and opens the Home pipeline UI at Alice — Config.
- **Given** Alice starts for an authenticated standard user, **when** the user's accessible projects are loaded, **then** Alice determines whether the user has zero, one, or multiple projects.
- **Given** the user has zero accessible projects, **then** Alice shows: "You do not have access to any project yet. Please contact an administrator to assign you to a project." and does not show AI provider selection.
- **Given** the user has exactly one accessible project, **then** Alice shows: "You have only one project called <project name>. Auto proceed with this project.", automatically selects that project, and then shows the AI provider selection message.
- **Given** the user has two or more accessible projects, **then** Alice shows: "Please select one project to proceed" and renders a selectable list of project names.
- **Given** the user clicks one project from the list, **then** the chat adds a right-aligned user message containing the selected project name.
- **Given** a project has been selected manually or automatically, **then** all subsequent project-scoped API calls and WebSocket connections use the selected project ID.
- **Given** Alice has not resolved a selected project yet, **then** Alice does not show "Which AI provider would you like to use?..." or provider options.
- **Given** an admin logs in, **then** the existing admin dashboard routing remains unchanged.

## Epic 6: Test Execution & Reporting (Agent Jack)

Jack runs test scripts across Chrome/Firefox/Edge, generates execution reports with pass/fail per test per browser. Pipeline completes end-to-end. User sees final results.

> **Dependencies:** Requires Story 3.4 (Output Writer) and Story 4.1 (LLM Abstraction Layer) complete before starting this epic.

### Story 6.1: Script Runner Pipeline Stage

As a R&D engineer,
I want a script runner that executes Playwright test scripts across multiple browsers,
So that Jack can run tests and collect execution results.

**Acceptance Criteria:**

**Given** Playwright test scripts exist in `workspace/testscripts/`
**When** the script runner executes them
**Then** scripts run against selected browsers (Chrome required, Firefox/Edge/Safari optional)
**And** each script executes within standard Playwright timeout defaults (30 seconds per action) (NFR3)
**And** execution results capture: pass/fail status, error details, screenshots on failure
**And** browser crashes during execution are handled gracefully without corrupting other results (NFR13)
**And** returns `StageResult` with per-script, per-browser execution results
**And** the pipeline completes end-to-end without manual intervention (FR11)

### Story 6.2: Execution Report Generation

As a R&D engineer,
I want execution reports generated from test run results,
So that users can see clear pass/fail outcomes per test case per browser.

**Acceptance Criteria:**

**Given** test scripts have been executed across browsers
**When** the report is generated
**Then** report shows pass/fail per test case per browser in a clear format
**And** failure details include error message, step that failed, and screenshot if available
**And** report summary includes total tests, pass count, fail count per browser
**And** report is saved to `workspace/report/` folder (FR13)
**And** report format preserves browser-use execution output as-is (no custom reformatting)

### Story 6.3: Jack Agent — Run Tests and Present Final Report

As a manual QA tester (Linh),
I want Jack to run my test scripts across browsers and show me the results,
So that I can see which tests pass and which fail across different browsers.

**Acceptance Criteria:**

**Given** Jack's step begins after Sarah completes
**When** Jack greets the user
**Then** Jack introduces himself: "Hi! I'm Jack. I'll run the test scripts across your selected browsers." (UX-DR19, orange avatar)
**And** user inputs browser paths for Edge/Firefox/Safari (optional, remembered after first time) (UX-DR20)
**And** user selects which browsers to run via checkboxes (Chrome default)
**Given** user clicks Start
**When** Jack executes tests
**Then** Processing indicator shows per-script, per-browser progress (e.g., "Running test 3 of 12 on Chrome...")
**Given** execution completes
**When** Review Request is presented
**Then** execution report is displayed as-is from browser-use output
**And** user clicks Approve to accept report, or Reject to re-run with feedback
**And** final button shows "Completed" (not Continue — last step of 5) (UX-DR4)
**And** status changes to Completed with green badge (UX-DR8)
**And** StepDots show all 5 dots green (UX-DR6)
**And** output saved to `workspace/report/`
**And** pipeline trigger initiated from Confluence URL completes full cycle (FR10)

## Epic 7: Input Quality Detection & Confidence Scoring (Milestone 1 — Step 2 Enhancement)

Pipeline automatically detects low-quality test cases, flags low-confidence generations. Users are warned before generation, reviewers see confidence scores per script.

> **Dependencies:** Requires Story 3.4 (Output Writer), Story 4.1 (LLM Abstraction), and Epics 3–5 complete before starting this epic.

### Story 7.1: Confluence Content Variation Handling

As a R&D engineer,
I want the pipeline to handle Confluence content variations including embedded macros and non-standard formatting,
So that Bob can extract content reliably from diverse Confluence pages.

**Acceptance Criteria:**

**Given** a Confluence page contains embedded macros, attachments, or non-standard formatting
**When** the content parser processes it
**Then** embedded macros are handled gracefully (extracted if possible, flagged with warning if not) (FR4)
**And** non-standard formatting is normalized to clean markdown
**And** attachments are listed with references even if not directly embeddable
**And** parser returns warnings in `StageResult.warnings` for any content that couldn't be fully parsed
**And** Bob presents these warnings to the user during review

### Story 7.2: Input Quality Detection and Pre-Generation Warning

As a manual QA tester (Linh),
I want the pipeline to detect insufficient input quality and warn me before generating scripts,
So that I can fix my Confluence documentation before wasting processing time on poor input.

**Acceptance Criteria:**

**Given** extracted requirements contain quality issues (vague steps, missing expected results, ambiguous language)
**When** Mary begins test case generation
**Then** the pipeline analyzes input quality before full generation (FR27)
**And** low-quality inputs are flagged with specific issues: "Step 3 is too vague", "Expected result missing for TC-005"
**And** warning is presented as an agent message with yellow warning icons (UX-DR12)
**And** user can choose to proceed anyway or go back to fix the source documentation
**And** quality assessment does not block generation — it informs the user's decision

### Story 7.3: Low-Confidence Generation Flagging

As a QA automation engineer (Minh),
I want low-confidence generations flagged for mandatory review,
So that I can prioritize reviewing scripts where the AI is least certain.

**Acceptance Criteria:**

**Given** the LLM generates a test case or script with low confidence
**When** the output is presented for review
**Then** confidence score (0.0-1.0) is visible per item in the review UI (FR22)
**And** items with confidence below a configurable threshold are flagged visually (amber/red indicator)
**And** flagged items are presented first during review to prioritize expert attention
**And** confidence score is stored in `metadata.json` alongside each output
**And** the scoring considers: input clarity, LLM response quality indicators, selector reliability

## Epic 8: Advanced Review & LLM Management (Milestone 1)

Reviewer can edit scripts before approval. Admin can switch between LLM providers, run comparison tests, and tune prompt templates for quality optimization.

> **Dependencies:** Requires Story 4.1 (LLM Abstraction Layer) and Story 5.4 (Sarah agent) complete before starting this epic. Story 8.2 (enhanced side-by-side review) builds on the base split-panel layout from Story 5.4 — do not re-implement the panel; enhance it.

### Story 8.1: Script Editing Before Approval

As a QA automation engineer (Minh),
I want to edit generated Playwright scripts directly in the review UI before approving them,
So that I can fix minor issues (fragile selectors, missing waits) without rejecting and re-generating.

**Acceptance Criteria:**

**Given** a script is presented for review in Step 4 (Sarah)
**When** the reviewer wants to make changes
**Then** an Edit button is available alongside Approve/Reject (FR21)
**And** clicking Edit opens an inline code editor within the review panel with syntax highlighting
**And** edited scripts can be saved and then approved
**And** the original and edited versions are both preserved in metadata for audit
**And** editing is optional — Approve and Reject still work as before (FR20)

### Story 8.2: Side-by-Side Source and Script Review Enhancement

As a QA automation engineer (Minh),
I want an enhanced side-by-side view showing source test case alongside generated script with technical detail,
So that I can efficiently validate script quality at scale.

**Acceptance Criteria:**

**Given** scripts are presented for review
**When** the reviewer examines them
**Then** left panel shows the source Confluence test case content (FR19)
**And** right panel shows the generated Playwright script with full syntax highlighting
**And** selectors used in the script are highlighted for quick validation
**And** assertion mappings are visually linked to expected results in the source
**And** batch navigation (Next/Previous) allows efficient review of multiple scripts (FR20)
**And** reviewer can approve or reject each script individually

### Story 8.3: Multi-Provider LLM Switching

As an admin (Duc),
I want to switch between LLM providers (Claude, DeepSeek, Qwen, Gemini, ChatGPT) via configuration,
So that I can optimize for quality, cost, or data sovereignty requirements.

**Acceptance Criteria:**

**Given** the admin accesses provider configuration
**When** the provider is changed
**Then** switching requires only a config change through Alice's Step 1 reconfiguration (FR16)
**And** all subsequent agents automatically use the new provider's model assignments
**And** provider-specific prompt templates can be configured per agent (FR18)
**And** prompt templates are stored in `src/ai_qa/prompts/` and selectable per provider
**And** switching does not require code changes or server restart

### Story 8.4: LLM Comparison Testing

As an admin (Duc),
I want to run comparison tests between LLM providers using the same input,
So that I can evaluate script quality differences and make informed provider decisions.

**Acceptance Criteria:**

**Given** the admin wants to compare LLM providers
**When** a comparison test is initiated via CLI
**Then** the same test case input is processed by multiple providers in sequence (FR17)
**And** results are saved side-by-side with provider name, model, generation time, and output
**And** comparison report highlights differences in: script structure, selector strategies, assertion accuracy
**And** comparison results are saved to a dedicated `workspace/comparisons/` folder
**And** CLI command: `uv run ai-qa compare --providers claude,deepseek --input <testcase>`

## Epic 9: Jira Integration & Audit Trail (Milestone 1)

Pipeline connects to on-premises Jira Data Center via MCP server for test-related requirements. Full audit logging records all pipeline activity (who read what, generated what, when) for compliance and troubleshooting.

> **Dependencies:** Requires Story 3.1 (MCP Client Foundation), Story 3.4 (Output Writer), and Epics 1–6 complete before starting this epic.
> **Story order:** 9.1a → 9.1b → 9.2 → 9.3 (9.1b must precede 9.2)

### Story 9.1a: Jira MCP Integration

As a R&D engineer,
I want the pipeline to connect to on-premises Jira Data Center via the MCP server,
So that Bob can also extract test-related requirements from Jira tickets.

**Acceptance Criteria:**

**Given** the `src/ai_qa/mcp/jira.py` module is created
**When** the user provides a Jira project URL in Bob's Step 2 (optional input)
**Then** the MCP client connects to Jira Data Center via existing MCP server (FR23)
**And** test-related requirements are retrieved from Jira tickets (FR24)
**And** extracted Jira content is converted to markdown and saved alongside Confluence requirements in `workspace/requirements/`
**And** Jira connection failures are handled gracefully with clear error message
**And** retry logic uses tenacity with max 3 attempts (NFR12)
**And** all data stays on-premises (NFR5)

### Story 9.1b: Audit Logger Foundation

As a R&D engineer,
I want a foundational audit logger module established,
So that Stories 9.2 and 9.3 can build audit trail integration on a stable base.

**Acceptance Criteria:**

**Given** the `src/ai_qa/audit/` package is created
**When** the audit logger is initialized
**Then** `audit/logger.py` provides a `log_event(event: str, details: dict)` function
**And** events are written to `workspace/audit/audit_log.jsonl` in JSONL format (one JSON object per line)
**And** each entry includes: `timestamp` (ISO 8601), `event` type, `details` object
**And** the log file is append-only — never truncated or overwritten
**And** the logger is importable by BaseAgent without circular imports
**And** the module has at least one unit test confirming JSONL output format

### Story 9.2: Audit Trail Logger — Extended Event Types

As an admin (Duc),
I want the audit logger (from Story 9.1b) extended with all required pipeline event types,
So that I can track who read what, generated what, and when — for compliance and troubleshooting.

**Acceptance Criteria:**

**Given** the `src/ai_qa/audit/logger.py` foundation from Story 9.1b is in place
**When** any pipeline activity occurs
**Then** an event is appended to `workspace/audit/audit_log.jsonl` in JSONL format (FR25)
**And** each log entry includes: `timestamp` (ISO 8601), `event` type, `details` object
**And** events logged include: Confluence pages read, scripts generated, approvals/rejections, provider changes
**And** user identity (who triggered the action) is recorded per event
**And** audit log is append-only — never modified or truncated
**And** logging is cross-cutting — integrated into all agents via BaseAgent

### Story 9.3: Audit Integration Across All Agents

As an admin (Duc),
I want audit logging woven into every agent's lifecycle,
So that the audit trail is comprehensive without requiring each agent to implement logging separately.

**Acceptance Criteria:**

**Given** the audit logger is available
**When** any agent transitions state (Start, Processing, Review, Approve, Reject, Done)
**Then** BaseAgent automatically logs the transition with agent name, step number, and timestamp
**And** Bob logs: which Confluence/Jira pages were read, content size, extraction warnings
**And** Mary logs: which test cases were generated, confidence scores
**And** Sarah logs: which scripts were generated, selectors used, confidence scores
**And** Jack logs: which scripts were executed, pass/fail results per browser
**And** all approval and rejection events include the reviewer's feedback text

## Epic 10: Metrics Dashboard & Reporting (Milestone 1)

Leadership views dashboard showing scripts generated, success rates, effort reduction, and LLM cost tracking for data-driven decision making.

> **Dependencies:** Requires Story 3.4 (Output Writer) and Epics 1–6 complete before starting this epic.
> **Story order:** 10.1 → 10.3 → 10.2 (REST API must be complete before Dashboard Frontend can consume it)

### Story 10.1: Metrics Collection Service

As a R&D engineer,
I want a metrics collection service that gathers pipeline statistics,
So that the dashboard has accurate data about script generation and execution.

**Acceptance Criteria:**

**Given** the pipeline runs end-to-end
**When** metrics are collected
**Then** the service tracks: total scripts generated, pass/fail counts, generation time per script (FR26)
**And** LLM cost data is calculated per run: tokens used, model, estimated cost per provider (FR29)
**And** metrics are aggregated per run, per day, and per week
**And** metrics data is stored in a structured format (JSON files in `workspace/metrics/`)
**And** collection is automatic — integrated into BaseAgent lifecycle, no manual instrumentation needed

### Story 10.3: REST API for Metrics Data

As a R&D engineer,
I want REST API endpoints serving metrics data,
So that the dashboard frontend can retrieve and display pipeline statistics.

**Acceptance Criteria:**

**Given** the metrics collection service has data
**When** the dashboard frontend requests metrics
**Then** `/api/metrics/summary` returns overall totals: scripts generated, success rate, effort reduction
**And** `/api/metrics/runs` returns per-run history with date, script count, pass/fail, cost
**And** `/api/metrics/costs` returns LLM cost breakdown by provider and time period
**And** API responses use Pydantic models for consistent schema
**And** endpoints handle empty data gracefully (new installation with no runs yet)

### Story 10.2: Metrics Dashboard Frontend

As engineering leadership (Trang),
I want a dashboard page showing pipeline metrics at a glance,
So that I can track ROI, adoption, and make data-driven decisions about the tool.

**Acceptance Criteria:**

**Given** the REST API endpoints from Story 10.3 are available
**When** the user navigates to the dashboard view
**Then** it shows total scripts generated, overall success rate, and effort reduction estimate (FR28)
**And** LLM cost tracking displays cost per provider, cost per run, and cost trend over time (FR29)
**And** script execution success rate is shown per run and as a trend chart (FR26)
**And** data is presented with clear, at-a-glance summary cards and simple trend visualizations
**And** dashboard data can be exported for reporting (CSV or JSON)
**And** dashboard is accessible via the `/dashboard` route in the web UI

## Epic 11: Azure Entra ID SSO Integration

QA engineers authenticate using their existing Azure Entra ID (Azure AD) credentials through the company's SSO infrastructure. This replaces the insecure shared `.env` approach with proper per-user authentication and authorization.

**FRs covered:** FR14 (security fix), NFR6 (credential isolation)

### Story 11.1: Azure Entra ID SSO Authentication Foundation

As a QA engineer (Minh),
I want to authenticate via Azure Entra ID SSO instead of shared `.env` credentials,
So that my API keys and access are isolated and secure per my corporate identity.

**Acceptance Criteria:**

**Given** the FastAPI server is running
**When** an unauthenticated user accesses any protected endpoint
**Then** they are redirected to Azure Entra ID login page

**Given** a user completes Azure Entra ID authentication
**When** the auth callback is processed
**Then** a JWT session token is issued with user identity (email, name, groups)
**And** the token expires after configurable duration (default: 8 hours)

**Given** an authenticated user
**When** they access protected API endpoints
**Then** their identity is available to the pipeline via `request.state.user`
**And** audit logs capture "who" performed each action (NFR9)

**Given** the current `.env` configuration system
**When** SSO is enabled
**Then** per-user configuration is stored in isolated location: `workspace/users/{user_email}/`
**And** API keys are no longer read from shared `.env` but from user-specific config

**Given** the React frontend
**When** SSO is integrated
**Then** login page shows "Sign in with Microsoft" button
**And** post-login, Agent Alice recognizes the user by name

**Security Requirements:**
- Use `fastapi-azure-auth` or `msal` library for Azure Entra ID integration
- Token validation against Azure JWKS endpoint
- No shared credentials in `.env` for user-isolated data
- Session middleware with HttpOnly cookies
- CSRF protection for authentication endpoints

### Story 11.2: Sync Company Users via Oracle sharedERP

As an admin,
I want to synchronize the company's user list from Oracle sharedERP,
So that I don't have to manually create every user account for production use.

**Acceptance Criteria:**

- System connects to Oracle sharedERP to fetch the active user list.
- Users are automatically provisioned in the AI QA Automation database.
- Admin can trigger the sync manually from the Admin Dashboard via the "Sync existing company's users" button.
