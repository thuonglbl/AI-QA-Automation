# Story 4.2: Test Case Extractor Pipeline Stage

**Epic:** 4  
**Status:** ready-for-dev

## Story

As a R&D engineer,  
I want a test case extractor that uses LLM to generate structured test cases from requirements,  
So that Mary can produce browser-use-optimized test cases from extracted content.

## Acceptance Criteria

**Given** markdown requirement files exist in `workspace/requirements/`  
**When** the test case extractor processes them  
**Then** it sends requirements to the LLM with a prompt template from `src/ai_qa/prompts/test_extraction.py`  
**And** generates structured test cases with: title, preconditions, numbered steps, and expected results  
**And** test cases are optimized for browser-use execution (actionable browser steps)  
**And** interprets natural-language test case steps into browser automation intent (FR5)  
**And** returns `StageResult` with generated test cases and confidence score  
**And** generation completes within 5 minutes per test case (NFR1)

## Tasks / Subtasks

- [ ] Create `src/ai_qa/prompts/__init__.py` with prompt template exports
- [ ] Create `src/ai_qa/prompts/test_extraction.py` with structured test case extraction prompt
- [ ] Create `src/ai_qa/pipelines/test_case_extractor.py` with TestCaseExtractor stage
- [ ] Create `src/ai_qa/models.py` updates for TestCase Pydantic model (if not exists)
- [ ] Create `tests/test_pipelines/test_test_case_extractor.py` with unit tests
- [ ] Implement confidence scoring algorithm based on LLM response quality
- [ ] Add retry logic with tenacity for LLM failures

## Dev Notes

### Epic Context

Epic 4 focuses on **Agent Mary (Test Case Generation)**. Story 4.1 (LLM Abstraction Layer) is **DONE** and provides the foundation. Story 4.2 is the core pipeline stage that converts Bob's extracted requirements into structured test cases suitable for browser automation.

**Key Dependencies:**
- Story 4.1 (LLM Abstraction Layer) - DONE - Provides `LLMClient` and `LLMConfig`
- Story 3.4 (Output Writer Pipeline Stage) - DONE - Can reuse patterns for file output
- Story 3.5 (Bob Agent) - DONE - Produces input requirements in `workspace/requirements/`

### Architecture Compliance

**MUST FOLLOW - Critical Patterns:**

1. **StageResult Pattern** [Source: architecture.md#Pipeline Stage Interface Pattern]
   ```python
   class StageResult(BaseModel):
       success: bool
       data: Any | None = None
       errors: list[str] = []
       warnings: list[str] = []
       confidence: float | None = None  # 0.0-1.0
   ```
   Every pipeline stage MUST return a `StageResult`. No exceptions.

2. **Pydantic Models for Data Exchange** [Source: architecture.md#Data Format Patterns]
   - Never use raw dicts between stages
   - Define a `TestCase` Pydantic model with: title, preconditions, steps (list), expected_results
   - All JSON keys must be snake_case
   - Datetime fields use ISO 8601 format

3. **Custom Exceptions Only** [Source: architecture.md#Error Handling Patterns]
   - Import from `ai_qa.exceptions` - use `LLMError`, `PipelineError`
   - Never raise generic `Exception` or bare `except:`

4. **Tenacity Retry Logic** [Source: architecture.md#Error Handling & Resilience]
   - Use `@retry` decorator, NOT hand-written retry loops
   - Max 3 attempts for LLM calls
   - Exponential backoff

5. **Module Boundaries** [Source: architecture.md#Architectural Boundaries]
   - `pipelines/` depends on: `ai_connection`, `models`, `exceptions`, `config`
   - `pipelines/` does NOT depend on: `agents`, `api`

### Technical & Library Requirements

**Core Libraries:**
- `langchain` - Already used by Story 4.1's `LLMClient`
- `pydantic` - For all data models
- `tenacity` - For retry decorators

**LLM Integration:**
- Use `ai_connection/client.py:LLMClient` (from Story 4.1)
- Read model config from `workspace/configuration/agents.json` (Alice writes this in Step 1)
- Default temperature: 0.0 for deterministic test case generation

**Prompt Templates:**
- Location: `src/ai_qa/prompts/test_extraction.py`
- Must instruct LLM to generate browser-use-optimized test cases
- Include examples of good vs. poor test case steps
- Prompt should request structured output (JSON) with clear schema

### File Structure Requirements

```
src/ai_qa/
├── prompts/
│   ├── __init__.py              # Export prompt templates
│   └── test_extraction.py       # Test case extraction prompt
├── pipelines/
│   ├── __init__.py              # Export pipeline stages
│   └── test_case_extractor.py   # TestCaseExtractor stage
└── models.py                    # Add TestCase model if not exists

tests/test_pipelines/
├── __init__.py
└── test_test_case_extractor.py  # Unit tests for extractor
```

### Input/Output Specifications

**Input:**
- Files from `workspace/requirements/` (written by Bob Agent in Step 2)
- Each file contains markdown requirements from Confluence
- Files have associated `metadata.json` with source URL

**Output:**
- Structured test cases saved to `workspace/testcases/`
- Each test case as separate file with kebab-case naming from title
- Format: JSON with test case structure
- Each output includes `metadata.json` with: source URL, timestamp, model used, confidence score

**Test Case Structure:**
```json
{
  "title": "User Login Flow",
  "preconditions": ["User has valid credentials", "Login page is accessible"],
  "steps": [
    {"number": 1, "action": "Navigate to /login", "target": "login page"},
    {"number": 2, "action": "Enter username in #username field", "target": "username input"},
    {"number": 3, "action": "Enter password in #password field", "target": "password input"},
    {"number": 4, "action": "Click Login button", "target": "login button"}
  ],
  "expected_results": ["Dashboard page loads", "Welcome message displayed"],
  "automation_hints": ["Use data-testid=login-btn for selector"]
}
```

### Testing Requirements

**Unit Tests Required:**
1. Test `TestCaseExtractor.process()` with mock LLM response
2. Test prompt template renders correctly with requirements input
3. Test confidence scoring calculation
4. Test retry logic on simulated LLM timeout
5. Test error handling when LLM returns malformed JSON
6. Test file output to correct `workspace/testcases/` location

**Mock Strategy:**
- Mock `LLMClient` to avoid real LLM calls in tests
- Use sample requirements as test fixtures
- Assert on `StageResult.success`, `StageResult.confidence`, and output file existence

### Previous Story Intelligence

**From Story 4.1 (LLM Abstraction Layer) - [Source: 4-1-llm-abstraction-layer-langchain-litellm.md]:**

- `LLMClient` class is in `src/ai_qa/ai_connection/client.py`
- `LLMConfig.from_agents_json()` loads config from `workspace/configuration/agents.json`
- Retry logic is already implemented in `LLMClient` with tenacity (max 3 attempts)
- Custom exceptions: `LLMError`, `LLMTimeoutError`, `LLMAuthenticationError`

**Key Code Patterns from 4.1:**
```python
# From client.py - how to instantiate LLMClient
config = LLMConfig.from_agents_json(agent_name="mary")
client = LLMClient(config)
response = await client.generate(prompt)
```

**Git Intelligence Summary:**
- Recent commits show pattern: `feat: Story X.X: [Story Title]`
- Story 4.1 touched: `ai_connection/config.py`, `ai_connection/client.py`
- All tests must pass (9/9 pattern established in 4.1)

### References

- [Source: epics.md#Story 4.2: Test Case Extractor Pipeline Stage] - Story requirements
- [Source: architecture.md#Pipeline Stage Interface Pattern] - StageResult pattern
- [Source: architecture.md#Requirements to Structure Mapping] - File location mappings
- [Source: architecture.md#FR5-9 (Test Script Generation)] - Architecture support for test case generation
- [Source: 4-1-llm-abstraction-layer-langchain-litellm.md] - Previous story implementation

## Dev Agent Record

### Agent Model Used

<!-- To be filled by dev agent -->

### Debug Log References

<!-- To be filled by dev agent -->

### Completion Notes List

<!-- To be filled by dev agent -->

### File List

<!-- To be filled by dev agent -->

## Story Completion Status

*Ultimate context engine analysis completed - comprehensive developer guide created*
