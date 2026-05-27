# Story 2.9: Dynamic Provider Model Discovery and Alice Reasoning Transparency

Status: ready-for-dev

## Story

As a user,
I want Alice to validate my selected AI provider and choose models from the provider's actual available model list,
so that downstream agents never use nonexistent or hardcoded models.

## Acceptance Criteria

1. Given the user selects an AI provider and enters required credentials,
   when Alice starts the connection test,
   then Alice connects to the selected provider/server using those credentials and reports success or failure based on the real provider response.

2. Given the provider connection succeeds,
   when the provider supports model listing,
   then Alice fetches the available model list from the provider/server before assigning models to agents.

3. Given available models are returned,
   when Alice assigns models to Bob, Mary, Sarah, and Jack,
   then each assigned model must come from the discovered available model list.

3b. Given Alice needs to use an LLM to reason about model assignments,
    when the available models are discovered,
    then Alice must first bootstrap her own model selection using basic keyword heuristics (e.g., looking for high-quality, advanced reasoning models like "opus", "gpt-4", "pro") so she can run the LLM selection process with maximum accuracy.

4. Given no available models are returned or model discovery fails,
   when Alice cannot verify valid model availability,
   then Alice must not display a successful model assignment table and must show a clear error or recovery path.

5. Given Alice is selecting models,
   when reasoning information is shown in chat,
   then Alice displays a collapsible/expandable thinking bubble containing:
   - provider connection status;
   - available model list;
   - Alice's own bootstrap model selection;
   - each agent's model needs;
   - selected model per agent;
   - rationale for each selection.

6. Given the final Review Request message is displayed,
   when connection and model assignment succeed,
   then the message says "Connected successfully to [provider]" and displays only the selected valid model assignments.

7. Given the final Review Request message is displayed,
   when model assignment is rendered,
   then it must not include the hardcoded explanation:
   "Bob uses Opus (highest quality) for requirement extraction. Other agents use Sonnet for speed and cost efficiency."

8. Given a saved provider configuration exists,
   when the user returns to the app,
   then Alice must not emit the extra welcome-back chat message:
   "Welcome back! I'm Alice. Using your saved..."
   unless the user explicitly opens or changes provider configuration.

9. Given Alice writes `agents.json`,
   when the configuration is saved,
   then each saved agent model (including Alice herself) must match the model selected from the discovered provider model list.

10. Given regression tests run,
    when provider discovery and review rendering are tested,
    then tests cover:
    - connection success with model discovery;
    - connection failure;
    - empty model list;
    - prevention of nonexistent/hardcoded model assignment;
    - removed hardcoded Opus/Sonnet copy;
    - removed saved-config welcome-back message.

11. Given the user selects Claude,
    when Alice asks for credentials,
    then the input placeholder must remain Claude-specific, e.g. "Enter your Claude API key..."

12. Given the user selects Gemini / ChatGPT,
    when Alice asks for credentials,
    then Alice must show a single API key input with placeholder: "Enter your Gemini or OpenAI API key..."

13. Given the user selects On-Premises,
    when Alice asks for credentials,
    then Alice must not show a Server URL input field and must show a single API key input with placeholder: "Enter your on-premises API key..."

14. Given provider URLs are needed for Browser Use Cloud, Claude, Gemini, ChatGPT, On-Premises API, or MCP,
    when the system connects to these services,
    then base URLs must be loaded from environment configuration, not entered in the Alice provider credential form.

15. Given provider API keys and MCP API keys differ per user,
    when a user enters these keys,
    then the system must persist them securely per user account rather than storing them in `.env`.

16. Given target page URL and SSO options are project/user workflow inputs,
    when the user runs the QA automation flow,
    then those values must be collected from user input and must not be stored in `.env`.

## Tasks / Subtasks

- [ ] Task 1: Add provider model discovery contract
  - [ ] 1.1 Add backend provider abstraction for listing available models.
  - [ ] 1.2 For On-Premises/OpenAI-compatible servers, call the provider's model listing endpoint.
  - [ ] 1.3 Normalize discovered model IDs into a provider-neutral structure.
  - [ ] 1.4 Ensure secrets are never logged or displayed.

- [ ] Task 2: Replace static model assignment with discovered-model selection
  - [ ] 2.1 Define model capability heuristics for Alice (Bootstrap), Bob, Mary, Sarah, and Jack.
  - [ ] 2.2 Implement a basic string-matching heuristic to bootstrap Alice's own model from the discovered list.
  - [ ] 2.3 Use Alice's selected model to score the remaining discovered models against Bob, Mary, Sarah, and Jack's needs via an LLM call.
  - [ ] 2.4 Select only from discovered model IDs for all agents.
  - [ ] 2.5 Block review if no valid discovered model can be selected.

- [ ] Task 3: Add Alice thinking trace payload
  - [ ] 3.1 Emit provider connection result.
  - [ ] 3.2 Emit discovered model list.
  - [ ] 3.3 Emit per-agent needs and selected-model rationale.
  - [ ] 3.4 Ensure the trace is user-readable and does not expose secrets.

- [ ] Task 4: Add collapsible thinking bubble UI
  - [ ] 4.1 Render Alice thinking trace as an expandable/collapsible chat bubble.
  - [ ] 4.2 Default the bubble to collapsed after completion.
  - [ ] 4.3 Allow user to expand it to inspect reasoning.
  - [ ] 4.4 Keep accessibility support for keyboard and screen readers.

- [ ] Task 5: Clean review and saved-config copy
  - [ ] 5.1 Remove hardcoded Opus/Sonnet explanation from `ModelAssignmentReview`.
  - [ ] 5.2 Ensure final success message only lists selected valid models.
  - [ ] 5.3 Remove or suppress Alice saved-config welcome-back message.

- [ ] Task 6: Persist validated configuration only
  - [ ] 6.1 Save discovered provider metadata in `provider.json` where useful.
  - [ ] 6.2 Save only selected discovered model IDs in `agents.json`.
  - [ ] 6.3 Reject persistence when discovery or selection failed.

- [ ] Task 7: Add backend tests
  - [ ] 7.1 Test successful provider connection and model discovery.
  - [ ] 7.2 Test connection failure.
  - [ ] 7.3 Test empty model list blocks assignment.
  - [ ] 7.4 Test nonexistent/static models are not assigned.
  - [ ] 7.5 Test saved config does not emit welcome-back chat message.

- [ ] Task 8: Add frontend tests
  - [ ] 8.1 Test thinking bubble renders collapsed/expanded states.
  - [ ] 8.2 Test model assignment review renders actual assigned models.
  - [ ] 8.3 Test hardcoded Opus/Sonnet explanation is absent.
  - [ ] 8.4 Test final review message is concise.

- [ ] Task 9: Refine Alice provider credential form
  - [ ] 9.1 Use Claude as the form-copy baseline.
  - [ ] 9.2 For Gemini / ChatGPT, show one API key input with placeholder: "Enter your Gemini or OpenAI API key..."
  - [ ] 9.3 For On-Premises, remove Server URL input entirely.
  - [ ] 9.4 For On-Premises, use placeholder: "Enter your on-premises API key..."
  - [ ] 9.5 Remove UI copy that says "Server URL + API key".

- [ ] Task 10: Align environment configuration ownership
  - [ ] 10.1 Add Browser Use Cloud, Claude, Gemini, OpenAI/ChatGPT, On-Premises, and MCP base URLs to `.env.example`.
  - [ ] 10.2 Remove user-specific API key examples from `.env.example`.
  - [ ] 10.3 Ensure provider API keys and MCP API keys are collected from user input.
  - [ ] 10.4 Persist user-specific keys separately per authenticated user.
  - [ ] 10.5 Ensure target page URL and SSO options remain user workflow inputs, not environment variables.

## Dev Notes

### Expected Alice Flow

1. User selects provider and enters credentials.
2. Alice loads the selected provider base URL from environment configuration.
3. Alice shows Processing state.
4. Alice emits a thinking trace:
   - "Connecting to provider..."
   - "Connection successful" or "Connection failed"
   - "Fetching available models..."
   - "Available models: ..."
   - "Bootstrapping Alice's reasoning model: Selected `<model>` for myself based on keyword heuristics..."
   - "Bob needs strong reasoning, long-context extraction, and tool-compatible output..."
   - "Selected `<model>` for Bob because ..."
5. If success, Alice presents Review Request with selected model assignment table (now including Alice).
6. If failure, Alice shows an actionable error and does not proceed to review.

### Model Selection Rules

- Never assign a model that was not returned by provider discovery.
- **Alice (Bootstrap):** Use basic string matching on the discovered list to find the highest-quality, most capable reasoning model (e.g., "opus", "gpt-4", "pro") for Alice to use. Quality and accuracy are prioritized over speed for this assignment step.
- Prefer strongest reasoning model for Bob.
- Prefer structured-output/instruction-following model for Mary.
- Prefer coding/tool-capable model for Sarah.
- Prefer fast, lower-cost summarization/execution-analysis model for Jack.
- If capabilities are unknown, use safe heuristic ranking based on discovered model names and document uncertainty in the thinking trace.

### Configuration Ownership Rules

- Store service base URLs in environment configuration.
- Do not store provider API keys or MCP API keys in `.env`.
- Collect API keys from the authenticated user and persist them securely per account.
- Keep target page URL and SSO options as runtime workflow inputs.

### Explicitly Removed Behavior

- Do not show:
  "Bob uses Opus (highest quality) for requirement extraction. Other agents use Sonnet for speed and cost efficiency."

- Do not show automatic saved-config welcome-back message:
  "Welcome back! I'm Alice. Using your saved..."

## üõ°Ô∏è ULTIMATE DEVELOPER GUARDRAILS & ARCHITECTURE CONTEXT

### 1. Existing Backend State (What you are modifying)
- **`src/ai_qa/agents/alice.py`**: Currently contains hardcoded `DEFAULT_MODEL_MAPPINGS` and a simulated `_test_connection()` using `asyncio.sleep(1.0)`. You must replace these with real provider discovery.
- **Provider Adapters**: You will need to implement `validate_connection()` and `list_models()` contracts. Note that `ai_qa/ai_connection/client.py` exists and has LLM integration logic via Langchain/LiteLLM.
- **Jack Agent**: Note that `jack.py` does NOT exist yet in `src/ai_qa/agents/`, but the `agents.json` schema still requires configuration for the Jack agent. Ensure Alice still discovers and assigns a model for Jack.
- **API Boundaries**: Remember that API keys are user-specific and MUST NOT be stored in `.env`. Base URLs (e.g., `BROWSER_USE_CLOUD_URL`, `CLAUDE_API_BASE_URL`) live in `.env` or `AppSettings`.

### 2. Existing Frontend State (What you are modifying)
- **`frontend/src/App.tsx`**: The conversational UI for Alice is currently implemented inline here (lines 520-589). Alice does NOT use the standard `ChatMessage.tsx` component like other agents.
- **`frontend/src/components/ProviderSelector.tsx`**: Contains the credential input form. You need to update this to remove the Server URL input for On-Premises and adjust placeholders.
- **`frontend/src/components/ModelAssignmentReview.tsx`**: Contains the hardcoded Opus/Sonnet message. You must remove this and ensure the table only shows the dynamic selections.
- **Thinking Bubble**: There is currently NO `ThinkingBubble` component in the frontend. You must build it. The only existing processing component is `ProcessingIndicator` (bouncing dots). The thinking bubble should be an expandable/collapsible component (defaulting to collapsed on completion) that does NOT expose secrets.

### 3. Required WebSocket Updates
- Ensure Alice's backend sends the reasoning trace payload to the frontend.
- Update `frontend/src/types/provider.ts` and `pipeline.ts` to support the new reasoning trace payload within the connection test or review messages.

### 4. Git & Previous Intelligence
- Recent commits (e.g., `d529171`, `24b552e`, `2e181d1`) show heavy work on Epic 12 (Admin Dashboard & Project Selection). Alice's step was recently modified to include Project Selection (Story 12.10). Ensure your changes to Alice do not break the new project resolution flow.

---
*Generated by BMad Story Automator*

### Review Findings
- [ ] [Review][Patch] Thi?u import json - G‚y l?i NameError khi parse ph?n h?i LLM.
- [ ] [Review][Patch] L?i trÌch xu?t JSON b?ng Regex - C?n Regex an to‡n hon d? x? l˝ JSON, tr·nh b?t tham lam.
- [ ] [Review][Patch] Thi?u x·c th?c ch?t ch? k?t qu? LLM - C?n ki?m tra model ID cÛ n?m trong vailable_models hay khÙng.
- [ ] [Review][Patch] KhÙng b?t l?i Fallback khi Regex th?t b?i - Code roi v‡o kho?ng tr?ng n?u khÙng tÏm th?y chu?i JSON.
- [ ] [Review][Patch] Logic fallback y?u - NÍn s? d?ng DEFAULT_MODEL_MAPPINGS thay vÏ g·n d?ng lo?t alice_model.
- [ ] [Review][Patch] Kh?i Exception b?t l?i qu· r?ng - B?t Exception chung che gi?u l?i h? th?ng (nhu NameError).
- [ ] [Review][Patch] X? l˝ sai d?nh d?ng t? Provider - C?n phÚng h? tru?ng h?p Provider tr? v? chu?i ho?c s? thay vÏ dict.
- [ ] [Review][Patch] Thi?u model du?c ch?n trong Thinking Trace payload - KhÙng cÛ tÍn model trong k?t qu? tr? v? UI.
- [ ] [Review][Patch] Thi?u component ThinkingBubble - Chua tri?n khai giao di?n theo Task 4.
- [ ] [Review][Patch] Thi?u thÙng b·o Connected successfully - C‚u van hi?n th? chua d˙ng AC6.
- [ ] [Review][Patch] Thi?u b‡i test regression backend - Chua cÛ b‡i ki?m th? theo yÍu c?u Task 7.
- [ ] [Review][Patch] Thi?u co ch? luu API key an to‡n - API key chua du?c luu d?c l?p theo user (Task 10.4).
- [ ] [Review][Patch] Thi?u placeholder riÍng cho Claude - Giao di?n chua d·p ?ng AC11.
- [x] [Review][Defer] Lu?c b? metadata c?a model khi g?i LLM - deferred, pre-existing
- [x] [Review][Defer] Import b? ph‚n t·n trong code - deferred, pre-existing
- [x] [Review][Defer] Hardcode tÍn c·c agent (bob, mary...) - deferred, pre-existing
