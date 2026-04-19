# Story 5.2: Script Generator Pipeline Stage

**Epic:** 5
**Status:** done

## Story

As a R&D engineer,
I want a script generator that converts test cases into Playwright Python scripts via LLM,
So that Sarah can produce executable, well-structured test files.

## Acceptance Criteria

**Given** structured test cases exist in `workspace/testcases/`
**When** the script generator processes them
**Then** it generates executable Python Playwright test scripts (FR6)
**And** one test file is produced per test case with naming derived from test case title (FR7)
**And** selectors prefer stable strategies: data-testid, role-based over CSS path/XPath (FR8)
**And** expected results from test cases are mapped into Playwright assertions (FR9)
**And** generated scripts are valid standalone Python files executable with only Playwright as dependency (NFR14)
**And** prompt templates are loaded from `src/ai_qa/prompts/script_generation.py`
**And** returns `StageResult` with generated scripts and confidence score

## Tasks / Subtasks

- [x] Create `src/ai_qa/pipelines/script_generator.py`
  - [x] Implement ScriptGenerator class with LLM integration
  - [x] Load prompt templates from `src/ai_qa/prompts/script_generation.py`
  - [x] Process structured test cases from workspace/testcases/
  - [x] Generate Playwright Python scripts per test case
  - [x] Implement stable selector preference (data-testid, role-based)
  - [x] Map expected results to Playwright assertions
  - [x] Return StageResult with confidence scoring
- [x] Create prompt templates
  - [x] Create `src/ai_qa/prompts/__init__.py`
  - [x] Create `src/ai_qa/prompts/script_generation.py`
  - [x] Design prompts for NL → Playwright conversion
  - [x] Include selector stability guidance in prompts
  - [x] Include assertion mapping guidance in prompts
- [x] Add script generator to AppSettings
  - [x] Add script generation configuration fields to config.py
  - [x] Update .env.example with script generation options
- [x] Create unit tests
  - [x] Test script generation with sample test cases
  - [x] Test stable selector preference
  - [x] Test assertion mapping
  - [x] Test file naming from test case titles
  - [x] Test StageResult with confidence scoring
  - [x] Test prompt template loading
- [x] Integration tests
  - [x] Test end-to-end script generation pipeline
  - [x] Test generated script validity (Python syntax)
  - [x] Test generated script Playwright compatibility

## Dev Notes

### Epic Context

Epic 5 focuses on **Agent Sarah (Test Script Generation)**. Story 5.2 creates the core pipeline stage that converts Mary's test cases into executable Playwright scripts.

**Key Dependencies:**
- Story 3.4 (Output Writer Pipeline Stage) - DONE - Provides file output patterns
- Story 4.1 (LLM Abstraction Layer) - DONE - Provides LLM integration patterns
- Story 4.3 (Mary Agent) - DONE - Provides test case input format
- Story 5.1 (Browser-Use Agent Configuration) - DONE - Provides browser foundation

**Story Flow in Epic 5:**
- Story 5.1: Browser-use foundation (agent.py, session.py) - DONE
- Story 5.2 (this story): Script Generator Pipeline Stage (LLM → Playwright scripts)
- Story 5.3: Vision-Assisted Locator Identification (browser-use vision model)
- Story 5.4: Sarah Agent (orchestrator wrapping Stories 5.1-5.3)

### Architecture Compliance

**MUST FOLLOW - Critical Patterns:**

1. **Pipeline Stage Interface Pattern** [Source: architecture.md#Pipeline Stage Interface Pattern]
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

2. **Module Boundaries** [Source: architecture.md#Architectural Boundaries]
   ```
   pipelines/ depends on: config, models, ai_connection, mcp, browser
   pipelines/ does NOT depend on: agents, api
   ```
   This is a pipeline stage — pure processing logic, no orchestration.

3. **Pydantic Models for Data Exchange** [Source: architecture.md#Data Format Patterns]
   - Never use raw dicts between stages
   - Use existing models from `src/ai_qa/models.py`
   - JSON output keys must be snake_case

4. **Custom Exception Hierarchy** [Source: architecture.md#Error Handling & Resilience]
   ```python
   class LLMError(AIQAError):
       """LLM processing errors."""
       pass

   class ScriptGenerationError(LLMError):
       """Script generation specific errors."""
       pass
   ```

5. **Retry Logic with Tenacity** [Source: architecture.md#Error Handling & Resilience]
   ```python
   from tenacity import retry, stop_after_attempt, wait_exponential

   @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
   async def generate_script_with_retry(test_case: TestCase) -> str:
       pass
   ```

### Technical & Library Requirements

**Core Libraries:**
- `langchain` - LLM abstraction (from Story 4.1)
- `pydantic` - Data models and validation
- Custom exceptions from `src/ai_qa/exceptions.py` (Story 1.3)
- StageResult from `src/ai_qa/models.py` (Story 1.4)

**LLM Integration Pattern:**
```python
# From Story 4.1 pattern
from ai_qa.ai_connection.client import LLMClient
from ai_qa.config import AppSettings

class ScriptGenerator:
    def __init__(self, config: AppSettings):
        self.llm_client = LLMClient(config)
        self.prompts = self._load_prompts()
    
    async def process(self, test_cases: list[TestCase]) -> StageResult:
        # Process each test case through LLM
        pass
```

**Prompt Template Strategy:**
```python
# In src/ai_qa/prompts/script_generation.py
SCRIPT_GENERATION_PROMPT = """
You are an expert Playwright test automation engineer. Convert the following natural language test case into a Python Playwright script.

Test Case: {test_case}

Requirements:
1. Generate a complete, runnable Playwright Python script
2. Use stable selectors: prefer data-testid, role-based selectors over CSS/XPath
3. Include proper assertions for expected results
4. Add appropriate waits and error handling
5. Follow Playwright best practices

Output only the Python script code.
"""
```

**Stable Selector Preference Order:**
1. `data-testid` attributes (most stable)
2. Role-based selectors (`get_by_role`, `get_by_text`)
3. Accessibility attributes (`get_by_label`, `get_by_placeholder`)
4. CSS selectors (only if necessary)
5. XPath (last resort)

**Assertion Mapping Strategy:**
- "Verify X is visible" → `expect(element).to_be_visible()`
- "Check Y equals Z" → `expect(element).to_have_text("Z")`
- "Confirm button is disabled" → `expect(button).to_be_disabled()`
- "Validate URL contains X" → `expect(page).to_have_url(X)`

### File Structure Requirements

```
src/ai_qa/
├── pipelines/
│   ├── __init__.py
│   └── script_generator.py    # New: Script generation pipeline stage
├── prompts/
│   ├── __init__.py           # New: Package initialization
│   └── script_generation.py  # New: Prompt templates
├── config.py                 # Add script generation config
├── models.py                 # Use existing models
└── exceptions.py             # Use existing exceptions

tests/test_pipelines/
├── __init__.py
└── test_script_generator.py  # New: Script generator tests

.env.example                  # Add script generation options
```

### Input/Output Specifications

**Input:**
- List of structured test cases from `workspace/testcases/`
- Test case format from Mary's output (Story 4.3)
- LLM configuration from `workspace/configuration/agents.json`

**Output:**
- Generated Playwright Python scripts (one per test case)
- Files saved to `workspace/testscripts/` (via OutputWriter from Story 3.4)
- StageResult with confidence scores and any warnings
- Metadata per script (source test case, generation timestamp, model used)

**File Naming Pattern:**
- Input test case: "User Login Flow" → Output script: `test_user_login_flow.py`
- Input test case: "Search Functionality Test" → Output script: `test_search_functionality_test.py`
- Use kebab-case, prefix with `test_`, limit to 80 characters

**Generated Script Structure:**
```python
"""
Generated Playwright test script for: {test_case_title}
Source: {workspace/testcases/original_file.json}
Generated: {timestamp}
Model: {llm_model_used}
Confidence: {confidence_score}
"""

import pytest
from playwright.sync_api import Page, expect

def test_{normalized_test_case_name}(page: Page):
    # Test steps generated from natural language
    pass
```

### Testing Requirements

**Unit Tests Required:**
1. Test ScriptGenerator initialization with valid config
2. Test prompt template loading from file
3. Test script generation with sample test case
4. Test stable selector preference in generated scripts
5. Test assertion mapping in generated scripts
6. Test file naming from test case titles
7. Test StageResult with confidence scoring
8. Test error handling for LLM failures
9. Test retry logic with tenacity
10. Test configuration loading from AppSettings

**Mock Strategy:**
- Mock LLMClient to avoid real LLM calls
- Use sample test cases as fixtures
- Mock file system for workspace operations
- Assert on generated script structure and content
- Verify selector preference order in output

**Integration Tests:**
- Test end-to-end script generation pipeline
- Test generated script validity (Python syntax check)
- Test generated script Playwright compatibility
- Test workspace folder structure creation

### Previous Story Intelligence

**From Story 4.3 (Mary Agent) - [Source: 4-3-mary-agent-create-test-cases-with-per-item-review.md]:**

- Test case output format: JSON files in workspace/testcases/
- Test case structure: title, steps, expected_results, priority
- Per-item review pattern (Sarah will use similar in Story 5.4)
- Integration with pipeline stages

**From Story 4.1 (LLM Abstraction Layer) - [Source: 4-1-llm-abstraction-layer-langchain-litellm.md]:**

- LLMClient pattern for provider abstraction
- Configuration from workspace/configuration/agents.json
- Retry logic with tenacity (max 3 attempts)
- Temperature configuration (default 0.0 for deterministic output)

**From Story 3.4 (Output Writer Pipeline Stage) - [Source: 3-4-output-writer-pipeline-stage.md]:**

- OutputWriter pattern for file saving
- Metadata.json structure (source URL, timestamp, model, confidence)
- File naming derived from content titles
- Workspace folder organization

**From Story 5.1 (Browser-Use Agent Configuration) - [Source: 5-1-browser-use-agent-configuration-and-session-management.md]:**

- Browser module foundation (for Story 5.3 vision assistance)
- Configuration patterns for browser-specific settings
- Error handling patterns for browser operations

**Key Code Patterns from Previous Stories:**
```python
# From Story 4.1 - LLM integration pattern
from ai_qa.ai_connection.client import LLMClient
from ai_qa.config import AppSettings

class ScriptGenerator:
    def __init__(self, config: AppSettings):
        self.llm_client = LLMClient(config)
        self.config = config

# From Story 3.4 - Output pattern
from ai_qa.pipelines.output_writer import OutputWriter

async def save_script(self, script: str, test_case: TestCase) -> str:
    output_writer = OutputWriter(self.config)
    return await output_writer.save_file(
        content=script,
        folder="testscripts",
        filename=self._generate_filename(test_case.title),
        metadata={
            "source_test_case": test_case.title,
            "generated_at": datetime.now().isoformat(),
            "model": self.llm_client.model_name,
            "confidence": confidence_score
        }
    )

# From Story 4.1 - Retry pattern
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generate_script_with_llm(self, test_case: TestCase) -> str:
    prompt = self.prompts["script_generation"].format(
        test_case=test_case.model_dump_json(indent=2)
    )
    return await self.llm_client.generate(prompt)
```

**Git Intelligence Summary:**
- Recent commits show pattern: `feat: Story X.X: [Story Title]`
- Story 5.1 touched: browser/, config.py, exceptions.py, test_browser/
- Story 4.3 touched: agents/mary.py, test_cases/ output format
- Story 4.1 touched: ai_connection/client.py, LLM integration patterns
- All tests must pass (pattern established in previous stories)
- Ruff + mypy must pass before considering work done

### Security Requirements

**From PRD.md#Security:**

1. **Data Sovereignty (NFR5):**
   - All LLM processing via on-prem LiteLLM proxy
   - No test case data transmitted externally
   - Generated scripts stored locally only

2. **Output Validation (NFR14):**
   - Generated scripts must be valid standalone Python files
   - Scripts executable with only Playwright as dependency
   - No malicious code injection in generated scripts

### Performance Requirements

**From PRD.md#Performance:**

1. **Generation Time (NFR1):**
   - Pipeline end-to-end generation within 5 minutes per test case
   - Script generation stage should complete within 2-3 minutes per test case

2. **LLM Latency:**
   - Dependent on on-prem LLM performance
   - Retry logic handles transient failures

### Configuration Requirements

**Add to AppSettings in config.py:**
```python
class AppSettings(BaseSettings):
    # Existing fields...
    
    # Script generation configuration
    script_generation_model: str = "sonnet"  # Override per-agent config
    script_generation_temperature: float = 0.0  # Deterministic output
    script_generation_timeout: int = 120  # Seconds per script
    max_script_length: int = 10000  # Characters
    confidence_threshold: float = 0.7  # Flag low confidence generations
```

**Update .env.example:**
```bash
# Script generation configuration
SCRIPT_GENERATION_MODEL=sonnet
SCRIPT_GENERATION_TEMPERATURE=0.0
SCRIPT_GENERATION_TIMEOUT=120
MAX_SCRIPT_LENGTH=10000
CONFIDENCE_THRESHOLD=0.7
```

### References

- [Source: epics.md#Story 5.2: Script Generator Pipeline Stage] - Story requirements
- [Source: architecture.md#Pipeline Architecture] - Pipeline stage patterns
- [Source: architecture.md#Implementation Patterns & Consistency Rules] - Code patterns
- [Source: prd.md#Functional Requirements] - FR6-9 script generation requirements
- [Source: prd.md#Non-Functional Requirements] - NFR1, NFR14 performance/output requirements
- [Source: 4-3-mary-agent-create-test-cases-with-per-item-review.md] - Test case input format
- [Source: 4-1-llm-abstraction-layer-langchain-litellm.md] - LLM integration pattern
- [Source: 3-4-output-writer-pipeline-stage.md] - File output patterns
- [Source: 5-1-browser-use-agent-configuration-and-session-management.md] - Browser foundation

## Dev Agent Record

### Agent Model Used

Claude (AI Dev Agent)

### Debug Log References

- Fixed mypy type errors for response.content handling (list vs str)
- Fixed LLMConfig base_url type (ensure str not None)
- Added ScriptGenerationError to exceptions hierarchy
- Fixed confidence variable scope in _write_script method

### Completion Notes List

- ✅ Implemented ScriptGenerator class with LLM integration via LLMClient
- ✅ Added retry logic with tenacity (3 attempts, exponential backoff)
- ✅ Created comprehensive prompt templates for NL → Playwright conversion
- ✅ Implemented stable selector preference scoring (data-testid > role > text > CSS > XPath)
- ✅ Implemented confidence scoring algorithm based on script quality indicators
- ✅ Added script length validation and empty response handling
- ✅ Generated scripts include proper headers with metadata (source, timestamp, model)
- ✅ File naming follows kebab-case convention with test_ prefix
- ✅ All 23 unit tests pass covering initialization, generation, validation, confidence calculation
- ✅ Full test suite passes (242 tests) - no regressions introduced
- ✅ Ruff linting passes - code follows project style standards
- ✅ Mypy type checking passes - all type annotations correct

### File List

- `src/ai_qa/pipelines/script_generator.py` - New: Script generation pipeline stage
- `src/ai_qa/prompts/script_generation.py` - New: Prompt templates for script generation
- `src/ai_qa/prompts/__init__.py` - Modified: Added script generation exports
- `src/ai_qa/exceptions.py` - Modified: Added ScriptGenerationError class
- `src/ai_qa/config.py` - Modified: Added script generation configuration fields
- `.env.example` - Modified: Added script generation environment variables
- `tests/pipelines/test_script_generator.py` - New: Comprehensive unit tests

### Review Findings

- [x] [Review][Decision] Unicode test name handling — Chose transliteration to ASCII (Option A) for cross-platform compatibility
- [x] [Review][Decision] File naming convention — Chose snake_case per spec example & Python convention (Option A)
- [x] [Review][Patch] Empty test case title produces invalid filename `test_.py` — Fixed: Added guard with fallback to `test_unnamed_case.py`
- [x] [Review][Patch] KeyError risk in file path retrieval — Fixed: Changed `result.data["file_path"]` to `result.data.get("file_path")`
- [x] [Review][Patch] Fragile list content handling — Fixed: Added type-safe handling for list items with proper dict/str checking
- [x] [Review][Patch] Missing `test_case.filename` guard — Fixed: Added `getattr(test_case, "filename", None) or "unknown"` guards
- [x] [Review][Patch] Regex pattern escaping issue — Fixed: Corrected regex pattern for CSS selector detection
- [x] [Review][Defer] No parallelism for large test suites — deferred, pre-existing architecture pattern

## Story Completion Status

*Ultimate context engine analysis completed - comprehensive developer guide created*
