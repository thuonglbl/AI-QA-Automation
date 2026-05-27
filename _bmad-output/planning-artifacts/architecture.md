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
29 functional requirements across 7 categories:

- **Confluence Integration (FR1-4):** MCP-based connectivity to on-prem Confluence, SSO authentication, content parsing including embedded macros (M1)
- **Test Script Generation (FR5-9):** NL interpretation → Playwright Python scripts with stable selectors and mapped assertions. One file per test case
- **Pipeline Execution (FR10-13):** Single entry point (Confluence URL → Playwright files), end-to-end without manual intervention, browser-use controls local Chrome via SSO
- **Configuration (FR14-15):** .env-based config for API keys, MCP URL, target page, LLM parameters
- **LLM Management (FR16-18, M1):** Multi-provider switching (Claude/DeepSeek/Qwen), comparison testing, prompt template tuning
- **Human-in-the-Loop Review (FR19-22, M1):** Side-by-side source/script comparison, approve/reject/edit workflow, low-confidence flagging
- **Jira Integration (FR23-24, M1):** On-prem Jira Data Center access via MCP for test-related requirements
- **Quality & Observability (FR25-29, M1):** Audit logging, success rate reporting, input quality detection, metrics dashboard

**Non-Functional Requirements:**

- **Performance:** <5 min per test case generation, <30s per browser action, standard Playwright timeouts
- **Security (critical):** All data on-premises, no external transmission. .env-only secrets, never committed/logged. Browser agent read-only — no form submissions or data modifications. Audit logging from M1. On-prem LLMs eliminate external API transfer entirely
- **Integration Resilience:** Graceful MCP failure handling, LLM retry logic (max 3), browser crash recovery, valid standalone Playwright output, .env validation at startup

**Scale & Complexity:**

- Primary domain: Backend pipeline / Developer tool (CLI-first)
- Complexity level: Medium — AI/LLM integration with on-prem enterprise constraints, but linear pipeline architecture
- Estimated architectural components: 5-7 core components (MCP client, LLM abstraction, browser-use orchestrator, script generator, output manager, config manager, CLI interface)

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
- **LLM abstraction:** Must support provider switching without pipeline changes — Claude → DeepSeek/Qwen
- **Error handling & resilience:** MCP failures, LLM timeouts/rate limits, browser crashes — graceful degradation throughout
- **Audit & observability:** Who read what, who generated what, when — required from M1 across all pipeline stages
- **Configuration management:** .env for PoC, needs to scale to multi-environment support for M1+
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
- Configuration: Pydantic Settings (.env + config.yaml)
- Output Strategy: Hybrid files + JSON metadata
- Security: Data boundary enforcement + audit trail

**Deferred Decisions (Post-PoC):**

- CI/CD pipeline (Bitbucket on-prem, milestone sau)
- Multi-environment config (M1+)
- Database storage (nếu cần query audit data at scale)

### Frontend & API Layer

- **Decision:** Conversational chat UI (React) + FastAPI REST/WebSocket backend
- **UI Pattern:** Direction D from UX spec — chat-style interaction with named AI agents
- **Frontend stack:** React 18+ / TypeScript / Shadcn/ui / Tailwind CSS / Vite
- **Backend API:** FastAPI with WebSocket for real-time chat message streaming
- **Communication:** WebSocket for live agent messages (Processing updates, Review presentations), REST for actions (Start, Approve, Reject, Continue)
- **Rationale:** Manual QA testers cannot use CLI. Conversational UI is the most natural pattern for non-technical users (Teams-like). FastAPI is Python-native, async, and integrates seamlessly with existing pipeline code
- **Frontend routes:**
  - `/` — Main pipeline UI (5-step agent wizard, Alice → Jack). Standard users route here directly after login.
  - `/admin` — Admin Dashboard for authenticated admin users.
  - `/dashboard` — Metrics dashboard for leadership (Epic 10)
  - Use React Router v6 for client-side routing
  - Standard-user Project Workspace is removed from the happy path; project selection is handled inside Alice's configuration chat flow.
- **Accessibility:** WCAG 2.1 AA required (per UX-DR15). Establish focus ring styles (`ring-2 ring-blue-500 ring-offset-2`), aria attributes, and 44px minimum click targets from Story 2.2 (React scaffold). All subsequent UI stories must maintain these standards. Consult UX-DR15 for full requirements.

### Agent Orchestration Layer

- **Decision:** 5 named AI agents, each owning one pipeline step
- **Agents:** Alice (Configuration) → Bob (Extract Requirements) → Mary (Create Test Cases) → Sarah (Create Test Scripts) → Jack (Run Test Scripts)
- **Pattern:** Each agent follows the same lifecycle: Start → Processing → Review Request → (Approve/Reject+feedback) → Done
- **Human-in-the-loop:** Mandatory review gate at every step — no output advances without explicit user approval
- **Reject flow:** User provides feedback → agent self-corrects → re-presents for review
- **Alice (Step 1):** Resolves standard-user project context first, then guides AI provider selection (Browser Use Cloud / Claude / Gemini / ChatGPT / On-Premises). Provider choice determines which LLM models all subsequent agents use. Saves complete configuration to `configuration/` folder
- **Alice project resolution:** For standard users, Alice loads accessible projects through the project list API before provider options are shown. Zero projects shows a no-access message and blocks provider selection. One project is auto-selected with a confirmation message. Multiple projects render a selectable list; choosing one adds a right-aligned user message with the selected project name. Admin routing remains dashboard-first and unchanged.
- **Configuration output:** Alice writes `provider.json` (selected provider, credentials, endpoint) and `agents.json` (per-agent config: model, prompt template, tools/capabilities). All subsequent agents read their config from `configuration/agents.json` at startup
- **Provider → Model mapping:** Claude: Bob→Opus, others→Sonnet. On-Prem: Bob→DeepSeek, others→Qwen. See UX spec for full mapping table
- **File pipeline:** `configuration/` → `requirements/` → `testcases/` → `testscripts/` → `report/`
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

- **Decision:** Pydantic Settings (BaseSettings)
- **Sources:** `.env` file + `config.yaml` + env var overrides
- **Validation:** At startup — fail fast if config missing/invalid
- **Rationale:** browser-use/LangChain ecosystem already uses Pydantic — unified approach

### Output & Storage

- **Decision:** Database + S3-compatible Object Storage (MinIO)
- **Database:** PostgreSQL stores all project configurations (`User` settings), conversation states (`Project` state), and artifact metadata (`ArtifactVersion`).
- **File Storage:** MinIO (or any S3-compatible service) stores the actual file bytes (Markdown, JSON, Python scripts, images) via `S3ArtifactStorage`. The database only stores the S3 URI (`storage_path`).
- **Audit trail:** `audit_log.jsonl` append-only (JSONL format), can also be pushed to MinIO or logged directly.
- **Rationale:** Separating file storage from the application server ensures high availability, scalability, and allows the web server to remain stateless.

**Output Structure (MinIO bucket `ai-qa-artifacts`):**

```text
ai-qa-artifacts/
  projects/
    {project_id}/
      test_login_flow.py      # Playwright script
      metadata.json           # Source URL, timestamp, model, confidence
```

### Security Architecture

- **Secrets:** Pydantic Settings + `.env` (gitignored), validation at startup
- **Data sovereignty:** All processing local, LLM via on-prem proxy only
- **Browser scope:** Read-only — no form submissions, no data modifications
- **Transport:** HTTPS + certificate validation (httpx verify=True)
- **Audit:** JSONL append-only log across all pipeline stages
- **Leakage prevention:** Ruff rules + strict `.gitignore`

### Decision Impact Analysis

**Implementation Sequence:**

1. Configuration (Pydantic Settings) — foundation for all components
2. Exception hierarchy — needed before building any component
3. LLM abstraction (LangChain + LiteLLM) — core capability
4. MCP client (Confluence reader) — data source
5. Pipeline stages (sequential) — orchestration
6. Output manager (files + metadata) — results
7. CLI interface (Click) — user entry point
8. Audit logging — cross-cutting, weave in last

**Cross-Component Dependencies:**

- Pydantic Settings → all components read config
- Exception hierarchy → all components throw/catch
- LLM abstraction → Pipeline stages (TestCaseExtractor, ScriptGenerator)
- MCP client → Pipeline stages (ConfluenceReader)
- Output manager → Pipeline stages (OutputWriter) + Audit logging

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

### Data Format Patterns

- **Internal data exchange:** Pydantic models between stages (never raw dicts)
- **JSON output keys:** snake_case
- **Datetime format:** ISO 8601 strings (`2026-04-06T10:30:00Z`)
- **JSONL audit log:** Each line is a JSON object with `timestamp`, `event`, `details` fields

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

**Anti-Patterns (FORBIDDEN):**

- `dict` instead of Pydantic model between stages
- `print()` instead of `logging`
- Bare `except:` or `except Exception:`
- Hardcoded config values in code
- `import *` from any module

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
│       ├── cli.py                  # Click CLI commands (admin/developer)
│       ├── config.py               # Pydantic Settings (AppSettings)
│       ├── constants.py            # Project-wide constants
│       ├── exceptions.py           # Custom exception hierarchy
│       ├── models.py               # Shared Pydantic models (StageResult, AgentMessage, etc.)
│       │
│       ├── api/                    # FastAPI web server
│       │   ├── __init__.py
│       │   ├── server.py           # FastAPI app, CORS, static files
│       │   ├── routes.py           # REST endpoints (start, approve, reject, continue)
│       │   ├── websocket.py        # WebSocket for real-time chat messages
│       │   └── schemas.py          # API request/response Pydantic models
│       │
│       ├── agents/                 # Named AI agent orchestrators
│       │   ├── __init__.py
│       │   ├── base.py             # BaseAgent — shared lifecycle (Start→Process→Review→Done)
│       │   ├── alice.py            # Step 1: Configuration & AI provider selection
│       │   ├── bob.py              # Step 2: Extract Requirements from Confluence
│       │   ├── mary.py             # Step 3: Create Test Cases from requirements
│       │   ├── sarah.py            # Step 4: Create Test Scripts from test cases
│       │   └── jack.py             # Step 5: Run Test Scripts across browsers
│       │
│       ├── ai_connection/          # LLM abstraction layer
│       │   ├── __init__.py
│       │   ├── client.py           # LangChain ChatModel wrapper
│       │   ├── config.py           # LLM-specific config
│       │   └── exceptions.py       # LLM-specific exceptions
│       │
│       ├── mcp/                    # MCP integration
│       │   ├── __init__.py
│       │   ├── client.py           # MCP SDK client
│       │   ├── confluence.py       # Confluence-specific MCP tools
│       │   └── jira.py             # Jira MCP tools (M1)
│       │
│       ├── browser/                # browser-use + Playwright
│       │   ├── __init__.py
│       │   ├── agent.py            # browser-use agent configuration
│       │   └── session.py          # Browser session / SSO management
│       │
│       ├── prompts/                # LLM prompt templates
│       │   ├── __init__.py
│       │   ├── test_extraction.py  # Prompts for test case extraction
│       │   └── script_generation.py # Prompts for Playwright script generation
│       │
│       ├── pipelines/              # Pipeline stages (used internally by agents)
│       │   ├── __init__.py
│       │   ├── confluence_reader.py    # Read from Confluence via MCP
│       │   ├── content_parser.py       # Parse & structure content to MD/Mermaid/images
│       │   ├── test_case_extractor.py  # Extract test cases via LLM
│       │   ├── script_generator.py     # Generate Playwright scripts via LLM + vision
│       │   ├── script_runner.py        # Execute scripts across browsers
│       │   └── output_writer.py        # Write files + metadata to folders
│       │
│       └── audit/                  # Audit & observability
│           ├── __init__.py
│           └── logger.py           # JSONL audit trail writer
│
├── frontend/                       # React conversational UI
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── components.json             # Shadcn/ui config
│   ├── public/
│   ├── src/
│   │   ├── App.tsx                 # Main app — chat layout with AgentTopBar
│   │   ├── main.tsx                # React entry point
│   │   ├── index.css               # Tailwind directives
│   │   ├── lib/
│   │   │   └── utils.ts            # Shadcn/ui cn() utility
│   │   ├── components/
│   │   │   ├── ui/                 # Shadcn/ui primitives (Button, Card, Badge, etc.)
│   │   │   ├── AgentTopBar.tsx     # Agent avatar + name + step + status
│   │   │   ├── ChatMessage.tsx     # Agent/user message bubbles
│   │   │   ├── ChatInputArea.tsx   # Context-dependent input (Start/Review/Done)
│   │   │   ├── ReviewContent.tsx   # Rich content renderer (MD, code, report)
│   │   │   ├── StepDots.tsx        # Mini 4-dot progress indicator
│   │   │   └── ProcessingIndicator.tsx  # Animated typing dots
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts     # WebSocket connection to backend
│   │   │   └── usePipelineState.ts # Pipeline state management
│   │   └── types/
│   │       └── pipeline.ts         # TypeScript types matching backend schemas
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
├── workspace/                      # Per-run pipeline output (gitignored)
│   ├── configuration/              # Step 1 output: AI provider + agent configs
│   │   ├── provider.json           # Selected provider, endpoint, credential ref
│   │   └── agents.json             # Per-agent: model, prompt template, tools
│   ├── requirements/               # Step 2 output: MD, Mermaid, images
│   ├── testcases/                  # Step 3 output: structured test cases
│   ├── testscripts/                # Step 4 output: Playwright .py files
│   ├── report/                     # Step 5 output: execution reports
│   └── audit/
│       └── audit_log.jsonl
│
└── _bmad-output/                   # Planning artifacts (not runtime)
```

### Architectural Boundaries

**Module Boundaries:**

| Module | Responsibility | Depends On | Does NOT depend on |
| --- | --- | --- | --- |
| `config` | App settings, validation | pydantic-settings | anything else |
| `exceptions` | Exception hierarchy | nothing | anything else |
| `models` | Shared data models | pydantic | anything else |
| `ai_connection` | LLM calls | config, exceptions, langchain | mcp, browser, pipelines, agents |
| `mcp` | MCP server communication | config, exceptions, mcp-sdk | ai_connection, browser, agents |
| `browser` | Browser automation | config, exceptions, browser-use | mcp, ai_connection directly, agents |
| `pipelines` | Reusable pipeline stages | config, models, ai_connection, mcp, browser | agents, api |
| `agents` | Named agent orchestrators (Bob/Mary/Sarah/Jack) | config, models, pipelines, audit | api |
| `audit` | Logging trail | config, models | pipeline internals, agents |
| `api` | FastAPI REST + WebSocket | config, agents, models | pipeline internals |
| `cli` | Admin/developer CLI | config, agents | api, frontend |
| `frontend/` | React conversational UI | api (via HTTP/WebSocket) | all Python modules |

**Dependency Rule:** Modules depend downward only. `api/cli` → `agents` → `pipelines` → `ai_connection/mcp/browser` → `config/exceptions/models`. Frontend communicates with backend only via API. No circular dependencies.

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

**FR14-15 (Configuration):**

- `src/ai_qa/config.py` — Pydantic Settings
- `.env` / `config.yaml` — Runtime config files

**FR16-18 (LLM Management, M1):**

- `src/ai_qa/ai_connection/client.py` — Multi-provider switching
- `src/ai_qa/ai_connection/config.py` — LLM-specific settings

**FR19-22 (Human-in-the-Loop):**

- `src/ai_qa/agents/base.py` — BaseAgent review gate lifecycle (Start→Process→Review→Approve/Reject→Done)
- `src/ai_qa/api/websocket.py` — Real-time review presentation via WebSocket
- `src/ai_qa/api/routes.py` — Approve/Reject REST endpoints
- `frontend/src/components/ChatInputArea.tsx` — Approve/Reject/Feedback UI

**FR23-24 (Jira Integration, M1):**

- `src/ai_qa/mcp/jira.py` — Placeholder for M1

**FR25-29 (Quality & Observability, M1):**

- `src/ai_qa/audit/logger.py` — Audit trail
- Future: `src/ai_qa/metrics/` module (M1)

### Data Flow

```text
[React Frontend (localhost:5173)]
       │
       ├── REST API (actions: start, approve, reject, continue)
       ├── WebSocket (real-time: agent messages, processing updates, review content)
       │
       ▼
  api/server.py (FastAPI)
       │
       ▼
  agents/ (Named Agent Orchestrators)
       │
       ├── alice.py (Step 1: Configuration)
       │     ├──→ Present AI provider options (BU Cloud/Claude/Gemini/ChatGPT/On-Prem)
       │     ├──→ Collect credentials (API key or server URL)
       │     ├──→ Test connection to selected provider
       │     ├──→ WebSocket: present provider + model assignment for review ──→ [Frontend]
       │     │                 ← approve/reject ←
       │     └──→ Save config files ──→ [PostgreSQL `User` Table]
       │           ├── ai_provider_config   (provider, endpoint, credential ref)
       │           └── ai_agents_config     (per-agent: model, prompt, tools)
       │
       ├── bob.py (Step 2: Extract Requirements)
       │     ├──→ reads [PostgreSQL `User` Table] → loads model + prompt + tools
       │     ├──→ pipelines/confluence_reader.py ──→ mcp/confluence.py ──→ [MCP Server]
       │     ├──→ pipelines/content_parser.py (MD, Mermaid, images)
       │     ├──→ artifacts/service.py ──→ [MinIO `ai-qa-artifacts` bucket]
       │     └──→ WebSocket: present pages for review ──→ [Frontend]
       │                      ← approve/reject+feedback ←
       │
       ├── mary.py (Step 3: Create Test Cases)
       │     ├──→ reads [PostgreSQL `User` Table] → loads model + prompt + tools
       │     ├──→ reads requirements from [MinIO / PostgreSQL Metadata]
       │     ├──→ pipelines/test_case_extractor.py ──→ ai_connection/client.py ──→ [LiteLLM]
       │     ├──→ artifacts/service.py ──→ [MinIO `ai-qa-artifacts` bucket]
       │     └──→ WebSocket: present test cases for review ──→ [Frontend]
       │                      ← approve/reject+feedback ←
       │
       ├── sarah.py (Step 4: Create Test Scripts)
       │     ├──→ reads [PostgreSQL `User` Table] → loads model + prompt + tools
       │     ├──→ reads testcases from [MinIO / PostgreSQL Metadata]
       │     ├──→ pipelines/script_generator.py ──→ ai_connection/client.py ──→ [LiteLLM]
       │     │                                     browser/agent.py ──→ [Chrome via SSO]
       │     ├──→ artifacts/service.py ──→ [MinIO `ai-qa-artifacts` bucket]
       │     └──→ WebSocket: present TC+script pairs for review ──→ [Frontend]
       │                      ← approve/reject+feedback ←
       │
       └── jack.py (Step 5: Run Test Scripts)
             ├──→ reads [PostgreSQL `User` Table] → loads model + prompt + tools
             ├──→ reads testscripts from [MinIO / PostgreSQL Metadata]
             ├──→ pipelines/script_runner.py ──→ [Chrome/Firefox/Edge]
             ├──→ artifacts/service.py ──→ [MinIO `ai-qa-artifacts` bucket]
             └──→ WebSocket: present execution report ──→ [Frontend]
                              ← approve/reject+feedback ←

  audit/logger.py ──→ [PostgreSQL / MinIO] (cross-cutting, all agents)
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
| FR10-13 Pipeline Execution | `agents/` + `api/server.py` + `cli.py` + `browser/agent.py` | ✅ Covered |
| FR14-15 Configuration | `config.py` + `.env` + `config.yaml` | ✅ Covered |
| FR16-18 LLM Management (M1) | `ai_connection/client.py` — multi-provider ready | ✅ Covered |
| FR17 Prompt Tuning | `prompts/` directory — dedicated prompt templates | ✅ Covered |
| FR19-22 Human-in-the-Loop | `agents/base.py` review lifecycle + `api/websocket.py` + `frontend/` chat UI | ✅ Covered |
| FR23-24 Jira Integration (M1) | `mcp/jira.py` placeholder | ⏳ M1 |
| FR25-29 Quality & Observability (M1) | `audit/logger.py` — basic audit in PoC | ✅ Partial |

**Non-Functional Requirements Coverage:**

| NFR | Architectural Support | Status |
| --- | --- | --- |
| <5 min per test case | Sequential async pipeline | ✅ |
| <30s per browser action | Playwright timeout config | ✅ |
| On-premises data only | LiteLLM proxy, no external calls enforced | ✅ |
| .env-only secrets | Pydantic Settings, gitignored, validated at startup | ✅ |
| Browser read-only | browser-use config enforcement | ✅ |
| LLM retry max 3 | tenacity `stop_after_attempt(3)` | ✅ |
| MCP failure handling | tenacity retry + custom exceptions | ✅ |
| Browser crash recovery | browser-use built-in + Playwright timeouts | ✅ |
| Startup validation | Pydantic Settings fail-fast | ✅ |

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
| No prompt template location | Added `src/ai_qa/prompts/` directory | FR17 prompt tuning supported |
| No confidence scoring in StageResult | Added `confidence: float \| None` field | FR21 low-confidence flagging ready |
| Hardcoded output directory | `workspace/` directory with per-step subfolders | Transparent file pipeline |
| No web UI for non-technical users | Added React frontend + FastAPI API layer | FR19-22 human-in-the-loop enabled |
| No agent orchestration layer | Added `agents/` module with BaseAgent lifecycle | 4-step named agent pipeline |
| CLI-only interface excluded manual testers | FastAPI + WebSocket + React conversational UI | Zero-code barrier removed |

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

**Areas for Future Enhancement (M1+):**

- Event-driven pipeline if parallel processing needed
- Database storage for audit data at scale
- CI/CD pipeline (Bitbucket on-premises)
- Multi-user support with authentication (M2 server deployment)
- Metrics dashboard (`src/ai_qa/metrics/` + frontend dashboard page)
- Multi-environment configuration support
- Dark mode frontend theme

### Implementation Handoff

**AI Agent Guidelines:**

- Follow all architectural decisions exactly as documented
- Use implementation patterns consistently across all components
- Respect module boundaries — no circular dependencies
- Use StageResult for every pipeline stage output
- Refer to this document for all architectural questions

**First Implementation Priority:**

1. Project restructure: flat layout → `src/ai_qa/` with `pyproject.toml` updates
2. `config.py` with Pydantic Settings (AppSettings)
3. `exceptions.py` with custom exception hierarchy
4. `models.py` with StageResult, AgentMessage, and shared models
5. `agents/base.py` with BaseAgent lifecycle (Start→Process→Review→Done)
6. `api/server.py` + `api/websocket.py` with FastAPI + WebSocket foundation
7. `frontend/` scaffold with Vite + React + Shadcn/ui + core chat components
8. First agent (Alice) end-to-end: API → Agent → WebSocket → Frontend (config + provider selection)
9. Second agent (Bob) end-to-end: API → Agent → Pipeline → WebSocket → Frontend (extract requirements)

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
