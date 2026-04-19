# Story 2.8: Alice Agent — AI Provider Selection & Configuration

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want Alice to guide me through selecting an AI provider and configuring credentials,
so that I can connect to an AI service and all subsequent agents know which models to use.

## Acceptance Criteria

1. **Given** the user opens the app for the first time
   **When** Alice's step begins
   **Then** Alice greets with introduction: "Hi! I'm Alice. Let's set up your AI provider..." (UX-DR19, pink avatar)

2. **Given** Alice is presenting provider options
   **When** the user views the selection UI
   **Then** Alice presents 4 provider options with quality rank and security level:
     - Browser Use Cloud (1st/cloud)
     - Claude (2nd/enterprise)
     - Gemini/ChatGPT (3rd/cloud)
     - On-Premises (4th/highest security) (UX-DR17)

3. **Given** a provider is selected
   **When** the user makes a selection
   **Then** appropriate credential fields appear (API key, or server URL + API key for On-Premises)

4. **Given** credentials are entered
   **When** the user clicks Start
   **Then** Alice tests the connection and shows Processing state during verification

5. **Given** connection test succeeds
   **When** Review Request is presented
   **Then** it shows a model assignment table per agent (e.g., Bob→Opus, Mary→Sonnet) (UX-DR17)

6. **Given** the review screen is displayed
   **When** the user takes action
   **Then** user can Approve to confirm or Reject to change provider

7. **Given** configuration is approved
   **When** Alice completes the step
   **Then** configuration saved to `workspace/configuration/provider.json` and `agents.json` (UX-DR17)

8. **Given** configuration is saved
   **When** the user returns to the app
   **Then** configuration is remembered for future sessions — subsequent runs skip Step 1 unless user reconfigures (UX-DR20)

9. **Given** on-premises provider is selected
   **When** credential fields are displayed
   **Then** fields pre-fill from `.env` values if available

## Tasks / Subtasks

- [ ] Task 1: Create Alice agent backend module (AC: 1, 4, 5, 7)
  - [ ] 1.1 Create `src/ai_qa/agents/alice.py` with Alice agent class
  - [ ] 1.2 Implement Alice greeting message with pink avatar (A/pink per UX-DR19)
  - [ ] 1.3 Implement provider selection workflow (Start state with 4 options)
  - [ ] 1.4 Add connection testing logic with Processing state handling
  - [ ] 1.5 Implement Review Request with model assignment table
  - [ ] 1.6 Write configuration to `workspace/configuration/provider.json` and `agents.json`

- [ ] Task 2: Define configuration schemas (AC: 7, 9)
  - [ ] 2.1 Define `ProviderConfig` Pydantic model in `src/ai_qa/models.py`
  - [ ] 2.2 Define `AgentConfig` Pydantic model for per-agent settings
  - [ ] 2.3 Define `AliceConfiguration` model for complete Alice step output
  - [ ] 2.4 Create default model mappings (Claude: Bob→Opus, others→Sonnet; On-Prem: Bob→DeepSeek, others→Qwen)

- [ ] Task 3: Create provider selection UI components (AC: 2, 3)
  - [ ] 3.1 Create `frontend/src/components/ProviderSelector.tsx`
  - [ ] 3.2 Implement 4 provider cards with quality rank and security level badges
  - [ ] 3.3 Add credential input forms (API key, server URL) with validation
  - [ ] 3.4 Style with "Professional Calm" color system (UX-DR9)
  - [ ] 3.5 Add responsive layout for provider cards

- [ ] Task 4: Create model assignment review component (AC: 5, 6)
  - [ ] 4.1 Create `frontend/src/components/ModelAssignmentReview.tsx`
  - [ ] 4.2 Implement model assignment table (Agent name → Model name)
  - [ ] 4.3 Integrate with ChatInputArea for Approve/Reject actions
  - [ ] 4.4 Show provider endpoint (masked credentials) in review panel

- [ ] Task 5: Implement configuration persistence (AC: 8, 9)
  - [ ] 5.1 Add `load_existing_configuration()` method in Alice agent
  - [ ] 5.2 Check for existing `provider.json` on app startup
  - [ ] 5.3 If valid config exists, skip to Review or auto-advance to Bob
  - [ ] 5.4 Pre-fill On-Premises credentials from `.env` (ON_PREM_AI_SERVER_URL, ON_PREM_API_KEY)

- [ ] Task 6: Integrate with WebSocket and state management (AC: 1, 4, 5)
  - [ ] 6.1 Add Alice-specific WebSocket message types
  - [ ] 6.2 Send provider options list from backend to frontend
  - [ ] 6.3 Send connection test progress updates
  - [ ] 6.4 Send model assignment table for review
  - [ ] 6.5 Handle Approve/Reject actions from frontend

- [ ] Task 7: Create workspace directory structure (AC: 7)
  - [ ] 7.1 Ensure `workspace/configuration/` directory exists
  - [ ] 7.2 Write `provider.json` with provider, endpoint, credential reference
  - [ ] 7.3 Write `agents.json` with per-agent model, prompt template, tools

- [ ] Task 8: Write backend tests (AC: 1-9)
  - [ ] 8.1 Test Alice agent initialization and greeting
  - [ ] 8.2 Test provider selection workflow
  - [ ] 8.3 Test connection testing with mocked LLM client
  - [ ] 8.4 Test configuration file writing
  - [ ] 8.5 Test existing configuration loading
  - [ ] 8.6 Test model assignment generation

- [ ] Task 9: Write frontend tests (AC: 2, 3, 5, 6)
  - [ ] 9.1 Test ProviderSelector renders 4 options with correct rankings
  - [ ] 9.2 Test credential fields appear based on provider selection
  - [ ] 9.3 Test ModelAssignmentReview renders table correctly
  - [ ] 9.4 Test Approve/Reject button actions
  - [ ] 9.5 Test configuration persistence in localStorage

- [ ] Task 10: Integration and validation (AC: 1-9)
  - [ ] 10.1 Integrate Alice with BaseAgent lifecycle from Story 2.3
  - [ ] 10.2 Run `ruff check src/ tests/` and `mypy src/`
  - [ ] 10.3 Run `npm run lint`, `npm run typecheck`, `npm run test` in frontend
  - [ ] 10.4 Manual test: Full Alice workflow from greeting to configuration saved
  - [ ] 10.5 Verify configuration files written correctly

## Dev Notes

### Alice Agent Architecture

**Alice follows the BaseAgent lifecycle (Story 2.3):**
```
Start → Processing (connection test) → Review Request → Done
                ↓
         (Reject + feedback)
                ↓
         Back to Start
```

**Alice-specific behavior:**
- Start state: Present provider selector UI (not text input)
- Processing: Test connection to selected provider
- Review: Show model assignment table (not raw output)
- On approve: Save configuration, clear chat, advance to Bob

### Provider Options Structure

```typescript
// frontend/src/types/provider.ts
export interface ProviderOption {
  id: 'browser-use-cloud' | 'claude' | 'gemini-chatgpt' | 'on-premises';
  name: string;
  qualityRank: number;  // 1-4, lower is better
  securityLevel: 'cloud' | 'enterprise' | 'highest';
  credentialFields: CredentialField[];
}

export interface CredentialField {
  name: string;
  label: string;
  type: 'text' | 'password' | 'url';
  required: boolean;
  placeholder?: string;
}

export const PROVIDER_OPTIONS: ProviderOption[] = [
  {
    id: 'browser-use-cloud',
    name: 'Browser Use Cloud',
    qualityRank: 1,
    securityLevel: 'cloud',
    credentialFields: [{ name: 'api_key', label: 'API Key', type: 'password', required: true }]
  },
  {
    id: 'claude',
    name: 'Claude (Anthropic)',
    qualityRank: 2,
    securityLevel: 'enterprise',
    credentialFields: [{ name: 'api_key', label: 'API Key', type: 'password', required: true }]
  },
  {
    id: 'gemini-chatgpt',
    name: 'Gemini / ChatGPT',
    qualityRank: 3,
    securityLevel: 'cloud',
    credentialFields: [{ name: 'api_key', label: 'API Key', type: 'password', required: true }]
  },
  {
    id: 'on-premises',
    name: 'On-Premises LLM',
    qualityRank: 4,
    securityLevel: 'highest',
    credentialFields: [
      { name: 'server_url', label: 'Server URL', type: 'url', required: true, placeholder: 'https://ai-server.company.com' },
      { name: 'api_key', label: 'API Key', type: 'password', required: true }
    ]
  }
];
```

### Model Assignment Default Mappings

```python
# src/ai_qa/agents/alice.py
DEFAULT_MODEL_MAPPINGS = {
    'claude': {
        'bob': 'claude-3-opus-20240229',      # Most capable for extraction
        'mary': 'claude-3-sonnet-20240229',   # Balanced for test case generation
        'sarah': 'claude-3-sonnet-20240229',  # Balanced for script generation
        'jack': 'claude-3-haiku-20240307'     # Fast for execution analysis
    },
    'on-premises': {
        'bob': 'deepseek-coder-33b',          # Strong coding model
        'mary': 'qwen-72b-chat',              # Good instruction following
        'sarah': 'qwen-72b-chat',             # Good instruction following
        'jack': 'qwen-7b-chat'                # Lightweight for analysis
    },
    'browser-use-cloud': {
        'bob': 'gpt-4',
        'mary': 'gpt-4',
        'sarah': 'gpt-4',
        'jack': 'gpt-3.5-turbo'
    },
    'gemini-chatgpt': {
        'bob': 'gemini-pro',
        'mary': 'gemini-pro',
        'sarah': 'gemini-pro',
        'jack': 'gemini-flash'
    }
}
```

### Configuration File Schemas

**provider.json:**
```json
{
  "provider": "claude",
  "provider_name": "Claude (Anthropic)",
  "endpoint": "https://api.anthropic.com",
  "credential_reference": "env://ANTHROPIC_API_KEY",
  "tested_at": "2026-04-17T10:30:00Z",
  "test_result": "success"
}
```

**agents.json:**
```json
{
  "version": "1.0",
  "updated_at": "2026-04-17T10:30:00Z",
  "agents": {
    "bob": {
      "model": "claude-3-opus-20240229",
      "temperature": 0.0,
      "prompt_template": "test_extraction_v1",
      "tools": ["confluence_reader", "content_parser"]
    },
    "mary": {
      "model": "claude-3-sonnet-20240229",
      "temperature": 0.0,
      "prompt_template": "test_case_generation_v1",
      "tools": ["test_case_extractor"]
    },
    "sarah": {
      "model": "claude-3-sonnet-20240229",
      "temperature": 0.0,
      "prompt_template": "script_generation_v1",
      "tools": ["script_generator", "browser_agent"]
    },
    "jack": {
      "model": "claude-3-haiku-20240307",
      "temperature": 0.0,
      "prompt_template": "execution_analysis_v1",
      "tools": ["script_runner"]
    }
  }
}
```

### UI Component Hierarchy

```
Alice Step UI:
├── AgentTopBar (Alice, Step 1, Processing/Review)
├── ChatArea
│   ├── ChatMessage (Alice greeting + introduction)
│   └── ChatMessage (ProviderSelector component in bubble)
│       └── ProviderSelector
│           ├── ProviderCard (Browser Use Cloud - rank 1)
│           ├── ProviderCard (Claude - rank 2)
│           ├── ProviderCard (Gemini/ChatGPT - rank 3)
│           └── ProviderCard (On-Premises - rank 4, highest security)
│   └── ChatMessage (ProcessingIndicator during connection test)
│   └── ChatMessage (ModelAssignmentReview in bubble)
│       └── ModelAssignmentReview
│           ├── ModelTable (agent → model assignments)
│           └── ProviderEndpoint (masked)
└── ChatInputArea
    ├── Start state: disabled (selection made in chat)
    ├── Processing: "Testing connection..."
    └── Review: [Reject (outline)] [Approve (solid)]
```

### WebSocket Message Types

```typescript
// Provider options message (backend → frontend)
interface ProviderOptionsMessage {
  type: 'provider_options';
  agent: 'alice';
  options: ProviderOption[];
}

// Provider selected (frontend → backend)
interface ProviderSelectedMessage {
  type: 'provider_selected';
  agent: 'alice';
  provider_id: string;
  credentials: Record<string, string>;
}

// Connection test progress (backend → frontend)
interface ConnectionTestMessage {
  type: 'connection_test';
  agent: 'alice';
  status: 'testing' | 'success' | 'failed';
  message: string;
}

// Model assignment review (backend → frontend)
interface ModelAssignmentMessage {
  type: 'model_assignment';
  agent: 'alice';
  provider: string;
  assignments: Array<{ agent: string; model: string; purpose: string }>;
  endpoint: string;
}
```

### Integration with Previous Stories

**From Story 2.3 (BaseAgent):**
- Alice extends BaseAgent class
- Uses shared lifecycle methods: `on_start()`, `on_processing()`, `on_review_request()`, `on_done()`
- Emits messages via `send_message()` for WebSocket delivery
- Reads/updates state via `self.state`

**From Story 2.4 (AgentTopBar):**
- Alice has pink avatar (A/pink per UX-DR19)
- Status badge shows: Start → Processing → Review Request → Done
- Step counter shows "Step 1 of 5"

**From Story 2.5 (ChatMessage):**
- Alice messages render with white bubble, left-aligned
- Rich content in review: model table renders as formatted markdown/HTML
- Avatar shows "A" with pink background

**From Story 2.6 (ChatInputArea):**
- Start: ProviderSelector component embedded in chat (not standard input)
- Processing: Disabled with ProcessingIndicator
- Review: Approve/Reject buttons visible

**From Story 2.7 (ProcessingIndicator):**
- Used during connection testing: "Testing connection to Claude..."
- ErrorFeedback used if connection fails

### Configuration Loading Precedence

```python
# On app startup, Alice checks for existing configuration:
async def check_existing_config(self) -> bool:
    provider_path = Path("workspace/configuration/provider.json")
    agents_path = Path("workspace/configuration/agents.json")
    
    if provider_path.exists() and agents_path.exists():
        provider_config = json.loads(provider_path.read_text())
        agents_config = json.loads(agents_path.read_text())
        
        # Validate configs are not expired (e.g., 30 days)
        if self._is_config_valid(provider_config, agents_config):
            self.send_message(
                type="info",
                content=f"Welcome back! Using saved {provider_config['provider_name']} configuration."
            )
            return True
    
    return False
```

### On-Premises Pre-fill from .env

```python
# When user selects On-Premises provider:
def get_on_prem_defaults(self) -> dict:
    from ai_qa.config import settings
    
    return {
        'server_url': settings.on_premises_ai_server_url or '',
        'api_key': settings.on_prem_api_key or ''  # Note: only pre-fill if exists
    }
```

### Project Structure Notes

**New Backend Files:**
- `src/ai_qa/agents/alice.py` — Alice agent implementation
- `src/ai_qa/models.py` updates — Add ProviderConfig, AgentConfig, AliceConfiguration models

**New Frontend Files:**
- `frontend/src/components/ProviderSelector.tsx` — Provider selection UI
- `frontend/src/components/ModelAssignmentReview.tsx` — Model assignment table
- `frontend/src/types/provider.ts` — Provider-related TypeScript types

**Modified Files:**
- `frontend/src/App.tsx` — Integrate Alice step into pipeline flow
- `frontend/src/hooks/usePipelineState.ts` — Add Alice-specific state handling

**Integration Points:**
- Uses `BaseAgent` from `src/ai_qa/agents/base.py` (Story 2.3)
- Integrates with WebSocket from `src/ai_qa/api/websocket.py` (Story 2.1)
- Uses `AppSettings` from `src/ai_qa/config.py` (Story 1.2)
- Uses `AgentMessage` model from `src/ai_qa/models.py` (Story 1.4)
- Uses `ProcessingIndicator` and `ErrorFeedback` from Story 2.7

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.8]
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR17 (AI Provider Selection UI)]
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR19 (Agent Personalities)]
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR20 (One-time Setup Inputs)]
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR9 (Color System)]
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR11 (Button Hierarchy)]
- [Source: _bmad-output/planning-artifacts/architecture.md#Agent Orchestration Layer]
- [Source: _bmad-output/planning-artifacts/architecture.md#Configuration & Environment]
- [Source: _bmad-output/planning-artifacts/architecture.md#Project Structure & Boundaries]
- [Source: 2-3-baseagent-lifecycle-start-processing-review-done.md#Dev Notes]
- [Source: 2-4-agenttopbar-and-stepdots-components.md#Dev Notes]
- [Source: 2-5-chatmessage-component-with-rich-content.md#Dev Notes]
- [Source: 2-6-chatinputarea-component-state-dependent-actions.md#Dev Notes]
- [Source: 2-7-processingindicator-and-error-feedback.md#Dev Notes]

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

