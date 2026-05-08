# Story 5.3: Vision-Assisted Locator Identification

**Epic:** 5
**Status:** ready-for-dev

## Story

As a R&D engineer,
I want Sarah to use a vision model to identify accurate locators on the target application,
So that generated scripts use reliable selectors based on actual page state.

## Acceptance Criteria

**Given** a test case references UI elements on the target application
**When** Sarah generates the script
**Then** browser-use navigates to the target page and captures visual state
**And** vision model identifies UI elements matching test case steps (FR5)
**And** locators are validated against the actual DOM
**And** fallback to LLM-only generation if browser-use is unavailable
**And** generation completes within 5 minutes per test case (NFR1)

## Tasks / Subtasks

- [ ] Create `src/ai_qa/pipelines/vision_locator.py`
  - [ ] Implement VisionLocator class that uses browser-use vision model
  - [ ] Integrate with existing BrowserAgent from Story 5.1
  - [ ] Capture page screenshots for vision analysis
  - [ ] Extract UI element coordinates and properties from vision model
  - [ ] Convert visual elements to stable Playwright selectors
  - [ ] Validate identified locators against actual DOM
- [ ] Extend ScriptGenerator with vision integration
  - [ ] Add vision-assisted generation mode to ScriptGenerator
  - [ ] Modify prompt templates to include visual context
  - [ ] Implement fallback logic when browser/vision unavailable
  - [ ] Update confidence scoring to include vision accuracy
- [ ] Update prompt templates
  - [ ] Create vision-assisted script generation prompts in `src/ai_qa/prompts/script_generation.py`
  - [ ] Include visual element descriptions in prompts
  - [ ] Add selector strategy guidance based on visual analysis
- [ ] Add configuration options
  - [ ] Add `vision_enabled`, `vision_model`, `vision_timeout` to config.py
  - [ ] Update .env.example with vision configuration
- [ ] Create unit tests
  - [ ] Test VisionLocator initialization and configuration
  - [ ] Test screenshot capture and vision model integration
  - [ ] Test selector extraction from visual analysis
  - [ ] Test DOM validation of identified locators
  - [ ] Test fallback to LLM-only when vision unavailable
  - [ ] Test confidence scoring with vision accuracy
- [ ] Create integration tests
  - [ ] Test end-to-end vision-assisted script generation
  - [ ] Test browser navigation and screenshot capture
  - [ ] Test vision model element identification accuracy

## Dev Notes

### Epic Context

Epic 5 focuses on **Agent Sarah (Test Script Generation)**. Story 5.3 adds **vision-assisted locator identification** to improve script accuracy by analyzing the actual target application UI.

**Key Dependencies:**
- Story 3.4 (Output Writer Pipeline Stage) - DONE - Provides file output patterns
- Story 4.1 (LLM Abstraction Layer) - DONE - Provides LLM integration patterns
- Story 4.3 (Mary Agent) - DONE - Provides test case input format
- Story 5.1 (Browser-Use Agent Configuration) - DONE - Provides browser foundation with `use_vision=True`
- Story 5.2 (Script Generator Pipeline Stage) - DONE - Provides base script generation to extend

**Story Flow in Epic 5:**
- Story 5.1: Browser-use foundation (agent.py, session.py) - DONE
- Story 5.2: Script Generator Pipeline Stage (LLM → Playwright scripts) - DONE
- Story 5.3 (this story): Vision-Assisted Locator Identification (browser-use vision model → accurate selectors)
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
   class BrowserError(AIQAError):
       """Browser automation errors."""
       pass

   class VisionError(BrowserError):
       """Vision model analysis errors."""
       pass

   class LocatorValidationError(BrowserError):
       """DOM locator validation errors."""
       pass
   ```

5. **Retry Logic with Tenacity** [Source: architecture.md#Error Handling & Resilience]
   ```python
   from tenacity import retry, stop_after_attempt, wait_exponential

   @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
   async def analyze_with_vision(screenshot: bytes) -> VisionResult:
       pass
   ```

### Technical & Library Requirements

**Core Libraries:**
- `browser-use` - Vision model and browser automation (>=0.12.5, already has `use_vision=True`)
- `pydantic` - Data models and validation
- `pillow` - Image processing for screenshots (if needed)
- Custom exceptions from `src/ai_qa/exceptions.py` (Story 1.3)
- StageResult from `src/ai_qa/models.py` (Story 1.4)
- BrowserAgent from `src/ai_qa/browser/agent.py` (Story 5.1)
- ScriptGenerator from `src/ai_qa/pipelines/script_generator.py` (Story 5.2)

**Browser-Use Vision Integration Pattern:**
```python
# From browser-use documentation and Story 5.1 pattern
from browser_use import Agent

# Vision is already enabled in Story 5.1 BrowserAgent
agent = Agent(
    task="Identify UI elements for test automation",
    browser_config={
        "chrome_path": chrome_path,
        "headless": False,
    },
    use_vision=True,  # Already enabled in Story 5.1
)

# Vision model can analyze page state and identify elements
# Results include element coordinates, text, and suggested selectors
```

**VisionLocator Class Design:**
```python
class VisionLocator:
    """Identifies UI element locators using vision model analysis.
    
    Uses browser-use vision capabilities to:
    1. Navigate to target pages
    2. Capture visual state
    3. Identify UI elements matching test case steps
    4. Extract stable selectors (data-testid, role-based)
    5. Validate locators against actual DOM
    """
    
    def __init__(
        self,
        browser_agent: BrowserAgent,
        config: AppSettings,
    ) -> None:
        self.browser = browser_agent
        self.config = config
    
    async def identify_locators(
        self,
        test_case: TestCase,
        target_url: str,
    ) -> LocatorResult:
        """Identify locators for test case steps using vision analysis."""
        # Navigate to target URL
        # Capture screenshot
        # Use vision model to identify elements
        # Extract and validate selectors
        # Return structured locator information
```

**Locator Extraction Strategy:**

The vision model should extract elements in priority order:
1. `data-testid` attributes (most stable - if visible)
2. `role` attributes (ARIA roles)
3. Accessible text labels
4. Visual position + semantic context
5. CSS selectors (derived from vision analysis)

**Validation Approach:**
```python
async def validate_locator(
    self,
    selector: str,
    selector_type: str,  # "data-testid", "role", "text", "css"
) -> bool:
    """Validate that a selector matches exactly one element in DOM."""
    # Use Playwright to query the selector
    # Return True if unique match, False otherwise
    # Log warnings for ambiguous or missing selectors
```

**Integration with ScriptGenerator:**

Extend the existing ScriptGenerator from Story 5.2:

```python
class ScriptGenerator:
    def __init__(
        self,
        output_base_dir: Path,
        llm_config: LLMConfig | None = None,
        config: AppSettings | None = None,
        vision_locator: VisionLocator | None = None,  # NEW
    ) -> None:
        # ... existing init ...
        self._vision_locator = vision_locator
        self._vision_enabled = (
            vision_locator is not None and 
            getattr(config, "vision_enabled", True)
        )
    
    async def _generate_single_script(
        self, 
        test_case: TestCase,
        target_url: str | None = None,  # NEW: for vision analysis
    ) -> dict[str, Any]:
        """Generate script with optional vision assistance."""
        
        # If vision enabled and target URL provided, identify locators first
        if self._vision_enabled and target_url:
            try:
                locator_result = await self._vision_locator.identify_locators(
                    test_case, target_url
                )
                # Include locator info in LLM prompt
                enhanced_prompt = self._build_vision_prompt(
                    test_case, locator_result
                )
            except VisionError:
                # Fallback to LLM-only
                logger.warning("Vision analysis failed, falling back to LLM-only")
                self._vision_enabled = False
        
        # Continue with existing LLM generation...
```

**Enhanced Prompt with Vision Context:**
```python
VISION_SCRIPT_GENERATION_PROMPT = """
You are an expert Playwright test automation engineer. 

Test Case: {test_case}

{vision_context}

Visual Analysis Results:
{locator_info}

Generate a complete, runnable Playwright Python script using the identified locators.
Prefer stable selectors verified by vision analysis.
"""
```

### File Structure Requirements

```
src/ai_qa/
├── pipelines/
│   ├── __init__.py              # Add VisionLocator export
│   ├── script_generator.py    # MODIFY: Add vision integration
│   └── vision_locator.py        # NEW: Vision-assisted locator identification
├── browser/
│   ├── agent.py                 # USE: Existing BrowserAgent
│   └── session.py               # USE: Existing SessionManager
├── prompts/
│   └── script_generation.py     # MODIFY: Add vision-assisted prompts
├── config.py                    # MODIFY: Add vision configuration
└── exceptions.py                # MODIFY: Add VisionError, LocatorValidationError

tests/test_pipelines/
├── __init__.py
├── test_script_generator.py     # MODIFY: Add vision integration tests
└── test_vision_locator.py     # NEW: VisionLocator unit tests

.env.example                     # MODIFY: Add vision configuration options
```

### Input/Output Specifications

**Input:**
- Test case from Mary's output (Story 4.3) - same as Story 5.2
- Target application URL (for browser navigation)
- Optional: Existing browser session from Story 5.1

**Output:**
- Enhanced script generation with vision-verified selectors
- Locator metadata (selector type, confidence, validation status)
- StageResult with vision accuracy metrics
- Fallback indication if LLM-only mode used

**LocatorResult Structure:**
```python
class LocatorResult(BaseModel):
    step_number: int
    element_description: str
    selectors: list[SelectorInfo]  # Priority ordered
    screenshot_region: tuple[int, int, int, int]  # x, y, w, h
    confidence: float
    validation_status: str  # "valid", "ambiguous", "not_found"

class SelectorInfo(BaseModel):
    type: str  # "data-testid", "role", "text", "css"
    value: str
    confidence: float
    validated: bool
```

### Testing Requirements

**Unit Tests Required:**
1. Test VisionLocator initialization with BrowserAgent
2. Test screenshot capture and encoding
3. Test vision model element identification
4. Test selector extraction from vision results
5. Test DOM validation with Playwright
6. Test fallback when vision unavailable
7. Test confidence scoring with vision accuracy
8. Test integration with ScriptGenerator
9. Test error handling for browser crashes
10. Test timeout handling for vision analysis

**Mock Strategy:**
- Mock BrowserAgent for isolated VisionLocator tests
- Mock vision model responses with sample element data
- Mock Playwright page for DOM validation tests
- Use sample screenshots for vision analysis tests

**Integration Tests:**
- Test end-to-end vision-assisted generation
- Test with real Chrome instance (if available)
- Test fallback behavior with simulated failures

### Previous Story Intelligence

**From Story 5.2 (Script Generator Pipeline Stage) - [Source: 5-2-script-generator-pipeline-stage.md]:**

- ScriptGenerator class pattern with LLM integration via LLMClient
- Retry logic with tenacity (3 attempts, exponential backoff)
- Prompt templates in `src/ai_qa/prompts/script_generation.py`
- Confidence scoring algorithm based on script quality indicators
- File naming and OutputWriter patterns
- StageResult return structure

**Key Code Patterns from Story 5.2:**
```python
# ScriptGenerator pattern to extend
class ScriptGenerator:
    def __init__(self, output_base_dir, llm_config=None, config=None):
        self.output_base_dir = output_base_dir
        self._llm_config = llm_config
        self._config = config or AppSettings()
        self._output_writer = OutputWriter(output_base_dir)
    
    async def generate(self, test_cases: list[TestCase]) -> StageResult:
        # Process test cases, return StageResult
        pass

# Retry pattern
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _call_llm(self, test_case: TestCase) -> str:
    pass
```

**From Story 5.1 (Browser-Use Agent Configuration) - [Source: 5-1-browser-use-agent-configuration-and-session-management.md]:**

- BrowserAgent with `use_vision=True` already configured
- Chrome path configuration via SessionManager
- Read-only browser operations (no form submissions)
- Error handling for browser crashes

**BrowserAgent Integration:**
```python
# From Story 5.1 - use existing BrowserAgent
from ai_qa.browser.agent import BrowserAgent

# Vision is already enabled in BrowserAgent initialization
# Access via: browser_agent.agent (the underlying browser-use Agent)
```

**Git Intelligence Summary:**
- Story 5.2 touched: pipelines/script_generator.py, prompts/script_generation.py
- Story 5.1 touched: browser/agent.py, browser/session.py
- Pattern: Extend existing classes rather than creating new ones
- All tests must pass (242+ tests currently)
- Ruff + mypy must pass

### Security Requirements

**From PRD.md#Security:**

1. **Browser Read-Only Mode (NFR8):**
   - Vision analysis must not submit forms or modify data
   - Only navigate, screenshot, and analyze page state
   - No clicking or typing during locator identification

2. **Data Sovereignty (NFR5):**
   - Screenshots processed locally via on-prem browser-use
   - No visual data transmitted to external services
   - Vision model runs via on-prem LiteLLM proxy

3. **SSO Session Protection (NFR7):**
   - Reuse existing Chrome SSO session
   - Do not store or cache credentials
   - Browser session managed by Story 5.1 SessionManager

### Performance Requirements

**From PRD.md#Performance:**

1. **Vision Analysis Time:**
   - Screenshot capture: <5 seconds
   - Vision model analysis: <30 seconds per page
   - Total per-test-case: <2 minutes (within 5 min NFR1)

2. **Timeout Handling:**
   - Vision timeout: configurable (default 60s)
   - Browser action timeout: 30s (from Story 5.1)
   - Graceful fallback on timeout

### Configuration Requirements

**Add to AppSettings in config.py:**
```python
class AppSettings(BaseSettings):
    # Existing fields from Story 5.2...
    
    # Vision-assisted locator identification
    vision_enabled: bool = True  # Enable vision analysis
    vision_model: str = "sonnet"  # Vision model for analysis
    vision_timeout: int = 60  # Seconds for vision analysis
    vision_screenshot_quality: int = 85  # JPEG quality (1-100)
    locator_validation_enabled: bool = True  # Validate against DOM
    vision_fallback_on_error: bool = True  # Fallback to LLM-only
```

**Update .env.example:**
```bash
# Vision-assisted locator identification
VISION_ENABLED=true
VISION_MODEL=sonnet
VISION_TIMEOUT=60
VISION_SCREENSHOT_QUALITY=85
LOCATOR_VALIDATION_ENABLED=true
VISION_FALLBACK_ON_ERROR=true
```

### References

- [Source: epics.md#Story 5.3: Vision-Assisted Locator Identification] - Story requirements
- [Source: architecture.md#Pipeline Architecture] - Pipeline stage patterns
- [Source: architecture.md#Implementation Patterns & Consistency Rules] - Code patterns
- [Source: architecture.md#Module Boundaries] - browser/ module dependencies
- [Source: prd.md#Functional Requirements] - FR5 vision model requirements
- [Source: prd.md#Non-Functional Requirements] - NFR1, NFR5, NFR7, NFR8 performance/security
- [Source: 5-2-script-generator-pipeline-stage.md] - ScriptGenerator to extend
- [Source: 5-1-browser-use-agent-configuration-and-session-management.md] - BrowserAgent foundation
- browser-use documentation: https://docs.browser-use.com - Vision model capabilities

## Dev Agent Record

### Agent Model Used

*(To be filled during development)*

### Debug Log References

*(To be filled during development)*

### Completion Notes List

*(To be filled during development)*

### File List

- `src/ai_qa/pipelines/vision_locator.py` - New: Vision-assisted locator identification
- `src/ai_qa/pipelines/script_generator.py` - Modify: Add vision integration
- `src/ai_qa/prompts/script_generation.py` - Modify: Add vision-assisted prompts
- `src/ai_qa/config.py` - Modify: Add vision configuration fields
- `src/ai_qa/exceptions.py` - Modify: Add VisionError, LocatorValidationError
- `src/ai_qa/pipelines/__init__.py` - Modify: Add VisionLocator export
- `.env.example` - Modify: Add vision configuration environment variables
- `tests/pipelines/test_vision_locator.py` - New: VisionLocator unit tests
- `tests/pipelines/test_script_generator.py` - Modify: Add vision integration tests

## Story Completion Status

*Ultimate context engine analysis completed - comprehensive developer guide created*
