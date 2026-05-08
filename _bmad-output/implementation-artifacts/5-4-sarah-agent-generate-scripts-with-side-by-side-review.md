# Story 5.4: Sarah Agent — Generate Scripts with Side-by-Side Review

**Epic:** 5
**Status:** done

## Story

As a manual QA tester (Linh) or QA automation engineer (Minh),
I want Sarah to generate Playwright scripts and let me review each one alongside its source test case,
So that I can verify the script correctly implements the test case.

## Acceptance Criteria

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

## Tasks / Subtasks

- [x] Create Sarah Agent orchestrator class
  - [x] Implement SarahAgent class extending BaseAgent from Story 2.3
  - [x] Add Sarah's personality (purple avatar, step 4, "Generate Scripts")
  - [x] Implement greeting message and Chrome path input handling
  - [x] Integrate ScriptGenerator from Story 5.2 with VisionLocator from Story 5.3
  - [x] Process test cases from Mary's output with progress tracking
  - [x] Handle review workflow with Approve/Reject/Feedback
  - [x] Save approved scripts to workspace/testscripts/ with metadata
- [x] Implement side-by-side review UI backend
  - [x] Create review data structures for split-panel display
  - [x] Format test case content for left panel (markdown rendering)
  - [x] Format Playwright scripts for right panel (syntax highlighting)
  - [x] Implement pagination (Next/Previous) for multiple scripts
  - [x] Handle review actions (Approve, Reject, Skip)
  - [x] Support reviewer role switching (Linh → Minh)
- [x] Extend WebSocket communication for review
  - [x] Add Sarah-specific message types to WebSocket protocol
  - [x] Implement review state synchronization
  - [x] Add progress updates during script generation
  - [x] Handle review action broadcasts
- [x] Create Sarah agent configuration
  - [x] Add Sarah's config to agents.json structure
  - [x] Configure Sarah's LLM model and prompt templates
  - [x] Set Chrome path persistence across sessions
  - [x] Configure output directory and metadata format
- [x] Create unit tests
  - [x] Test SarahAgent initialization and configuration
  - [x] Test script generation workflow with mock test cases
  - [x] Test review state management and transitions
  - [x] Test WebSocket message handling for Sarah
  - [x] Test file output and metadata generation
  - [x] Test error handling and fallback scenarios
- [x] Create integration tests
  - [x] Test end-to-end Sarah workflow with real components
  - [x] Test integration with ScriptGenerator and VisionLocator
  - [x] Test WebSocket communication with frontend
  - [x] Test file system operations and workspace management

## Dev Notes

### Epic Context

Epic 5 focuses on **Agent Sarah (Test Script Generation)**. Story 5.4 is the **orchestrator agent** that ties together all previous Epic 5 stories into a complete user-facing workflow.

**Key Dependencies:**
- Story 3.4 (Output Writer Pipeline Stage) - DONE - Provides file output patterns
- Story 4.1 (LLM Abstraction Layer) - DONE - Provides LLM integration patterns  
- Story 4.3 (Mary Agent) - DONE - Provides test case input format
- Story 5.1 (Browser-Use Agent Configuration) - DONE - Provides browser foundation
- Story 5.2 (Script Generator Pipeline Stage) - DONE - Provides core script generation
- Story 5.3 (Vision-Assisted Locator Identification) - DONE - Provides accurate selectors

**Epic 5 Story Flow:**
- Story 5.1: Browser-use foundation (agent.py, session.py) - DONE
- Story 5.2: Script Generator Pipeline Stage (LLM → Playwright scripts) - DONE  
- Story 5.3: Vision-Assisted Locator Identification (accurate selectors) - DONE
- Story 5.4 (this story): Sarah Agent (orchestrator + review UI)

### Architecture Compliance

**MUST FOLLOW - Critical Patterns:**

1. **BaseAgent Lifecycle Pattern** [Source: architecture.md#Agent Orchestration Layer]
   ```python
   # Sarah must extend BaseAgent from Story 2.3
   class SarahAgent(BaseAgent):
       def __init__(self, config: AppSettings) -> None:
           super().__init__(
               name="Sarah",
               color="purple",  # UX-DR19
               step_number=4,
               step_title="Generate Scripts",
               config=config
           )
   ```

2. **Agent Lifecycle States** [Source: Story 2.3 BaseAgent]
   - Start → Processing → Review Request → (Approve/Reject+feedback) → Done
   - WebSocket communication via AgentMessage model
   - Configuration from `workspace/configuration/agents.json`

3. **Pipeline Integration Pattern** [Source: architecture.md#Pipeline Architecture]
   ```python
   # Sarah orchestrates pipeline stages but doesn't implement them
   from ai_qa.pipelines.script_generator import ScriptGenerator
   from ai_qa.pipelines.vision_locator import VisionLocator
   
   # Sarah uses existing pipeline stages, doesn't replace them
   ```

4. **Module Boundaries** [Source: architecture.md#Architectural Boundaries]
   ```
   agents/ depends on: config, models, pipelines, audit
   agents/ does NOT depend on: api, mcp, browser (directly)
   ```

5. **WebSocket Communication Pattern** [Source: Story 2.3 BaseAgent]
   ```python
   # Use AgentMessage for all frontend communication
   from ai_qa.models import AgentMessage
   
   await self.send_message(AgentMessage(
       sender="Sarah",
       content="Generating script 2 of 12...",
       message_type="progress"
   ))
   ```

### Technical & Library Requirements

**Core Dependencies:**
- BaseAgent from `src/ai_qa/agents/base.py` (Story 2.3)
- ScriptGenerator from `src/ai_qa/pipelines/script_generator.py` (Story 5.2)
- VisionLocator from `src/ai_qa/pipelines/vision_locator.py` (Story 5.3)
- TestCase model from `src/ai_qa/models.py` (Story 1.4)
- StageResult from `src/ai_qa/models.py` (Story 1.4)
- WebSocket handler from `src/ai_qa/api/websocket.py`
- OutputWriter from `src/ai_qa/pipelines/output_writer.py` (Story 3.4)

**SarahAgent Class Design:**
```python
class SarahAgent(BaseAgent):
    """Sarah - Generate Playwright scripts with side-by-side review.
    
    Orchestrates script generation using:
    - ScriptGenerator for LLM-based script creation
    - VisionLocator for accurate selector identification  
    - OutputWriter for file management
    - WebSocket for real-time review UI
    """
    
    def __init__(self, config: AppSettings) -> None:
        super().__init__(
            name="Sarah",
            color="purple",
            step_number=4,
            step_title="Generate Scripts",
            config=config
        )
        self._script_generator = None
        self._vision_locator = None
        self._current_review_index = 0
        self._generated_scripts = []
        self._test_cases = []
    
    async def start(self, input_data: dict) -> None:
        """Start Sarah's workflow."""
        # Greeting message
        # Request Chrome path if not configured
        # Load test cases from Mary's output
        # Transition to Processing state
    
    async def process(self) -> None:
        """Generate scripts for all test cases."""
        # Initialize ScriptGenerator with VisionLocator
        # Process each test case with progress updates
        # Store generated scripts for review
        # Transition to Review Request
    
    async def review_request(self) -> None:
        """Present scripts for side-by-side review."""
        # Send review data for split-panel display
        # Handle pagination (Next/Previous)
        # Wait for user action (Approve/Reject/Skip)
    
    async def handle_approve(self) -> None:
        """Approve current script and continue."""
        # Save approved script to workspace/testscripts/
        # Move to next script or complete if done
    
    async def handle_reject(self, feedback: str) -> None:
        """Reject current script with feedback."""
        # Re-generate script using feedback
        # Return to review with updated script
```

**Review Data Structure:**
```python
class ReviewData(BaseModel):
    """Data for side-by-side review UI."""
    test_case: TestCase
    script_content: str
    script_language: str = "python"
    current_index: int
    total_count: int
    can_approve: bool = True
    can_reject: bool = True
    can_skip: bool = True  # Allow handing to Minh
```

**WebSocket Message Types for Sarah:**
```python
# Progress during generation
AgentMessage(sender="Sarah", content="Generating script 2 of 12...", message_type="progress")

# Review presentation
AgentMessage(sender="Sarah", content=review_data.json(), message_type="review_request")

# Review actions
AgentMessage(sender="Sarah", content="Script approved and saved", message_type="script_approved")
AgentMessage(sender="Sarah", content="Regenerating script with feedback...", message_type="script_regenerating")

# Completion
AgentMessage(sender="Sarah", content="12 scripts saved to testscripts/", message_type="done")
```

### File Structure Requirements

```
src/ai_qa/
├── agents/
│   ├── __init__.py              # ADD: SarahAgent export
│   ├── base.py                  # USE: BaseAgent from Story 2.3
│   └── sarah.py                 # NEW: Sarah agent orchestrator
├── pipelines/
│   ├── script_generator.py      # USE: ScriptGenerator from Story 5.2
│   ├── vision_locator.py        # USE: VisionLocator from Story 5.3
│   └── output_writer.py         # USE: OutputWriter from Story 3.4
├── models.py                    # USE: TestCase, StageResult, AgentMessage
├── config.py                    # USE: AppSettings for configuration
└── api/
    └── websocket.py             # MODIFY: Add Sarah-specific message handling

tests/test_agents/
├── __init__.py
├── test_base.py                 # USE: BaseAgent test patterns
└── test_sarah.py               # NEW: SarahAgent unit and integration tests

workspace/
├── configuration/
│   └── agents.json             # MODIFY: Add Sarah's configuration
└── testscripts/                # CREATE: Output directory for approved scripts
```

### Input/Output Specifications

**Input:**
- Test cases from Mary's output (`workspace/testcases/`)
- Chrome path configuration (remembered across sessions)
- Sarah's agent configuration from `agents.json`

**Processing:**
- Orchestrates ScriptGenerator with VisionLocator integration
- Provides real-time progress updates via WebSocket
- Handles review workflow state management

**Output:**
- Approved Playwright scripts in `workspace/testscripts/`
- Metadata per script (source test case, timestamp, model, confidence)
- Review state synchronization with frontend
- Completion summary and file count

**Workspace Structure:**
```
workspace/
├── testscripts/
│   ├── test_login_flow/
│   │   ├── test_login.py        # Generated Playwright script
│   │   └── metadata.json       # Source, timestamp, confidence
│   ├── test_search/
│   │   ├── test_search.py
│   │   └── metadata.json
│   └── audit_log.jsonl         # Append-only audit trail
```

### Testing Requirements

**Unit Tests Required:**
1. Test SarahAgent initialization with BaseAgent extension
2. Test greeting message and Chrome path handling
3. Test script generation workflow orchestration
4. Test review state management and transitions
5. Test WebSocket message formatting and sending
6. Test file output and metadata generation
7. Test error handling for pipeline failures
8. Test reviewer role switching (Linh → Minh)
9. Test configuration loading from agents.json
10. Test progress tracking and reporting

**Integration Tests Required:**
1. Test end-to-end Sarah workflow with real ScriptGenerator
2. Test integration with VisionLocator for accurate selectors
3. Test WebSocket communication with frontend mock
4. Test file system operations and workspace management
5. Test Chrome path persistence across sessions

**Mock Strategy:**
- Mock ScriptGenerator for isolated agent logic tests
- Mock WebSocket for message handling tests
- Mock file system for output tests
- Use sample test cases for workflow tests

### Previous Story Intelligence

**From Story 5.3 (Vision-Assisted Locator Identification) - [Source: 5-3-vision-assisted-locator-identification.md]:**

- VisionLocator class with browser-use integration
- Enhanced ScriptGenerator with vision assistance
- Vision-assisted prompt templates and confidence scoring
- Configuration for vision settings (timeout, model, etc.)

**Integration Pattern from Story 5.3:**
```python
# Sarah should use the enhanced ScriptGenerator from Story 5.3
script_generator = ScriptGenerator(
    output_base_dir=output_dir,
    llm_config=llm_config,
    config=config,
    vision_locator=vision_locator  # From Story 5.3
)
```

**From Story 5.2 (Script Generator Pipeline Stage) - [Source: 5-2-script-generator-pipeline-stage.md]:**

- ScriptGenerator class with LLM integration
- Retry logic with tenacity (3 attempts, exponential backoff)
- Prompt templates and confidence scoring
- File naming and OutputWriter patterns

**From Story 2.3 (BaseAgent Lifecycle) - [Source: 2-3-baseagent-lifecycle-start-processing-review-done.md]:**

- BaseAgent class with lifecycle states
- WebSocket communication via AgentMessage
- Configuration loading from agents.json
- Review workflow patterns (Approve/Reject/Feedback)

**BaseAgent Extension Pattern:**
```python
# From Story 2.3 - extend BaseAgent for Sarah
class SarahAgent(BaseAgent):
    def __init__(self, config: AppSettings) -> None:
        super().__init__(
            name="Sarah",
            color="purple",  # UX-DR19
            step_number=4,
            step_title="Generate Scripts",
            config=config
        )
```

**Git Intelligence Summary:**
- Story 5.3 touched: pipelines/vision_locator.py, pipelines/script_generator.py
- Story 5.2 touched: pipelines/script_generator.py, prompts/script_generation.py
- Story 2.3 touched: agents/base.py, api/websocket.py
- Pattern: Extend existing classes and follow established agent patterns
- All tests must pass (242+ tests currently)
- Ruff + mypy must pass

### Security Requirements

**From PRD.md#Security:**

1. **Browser Read-Only Mode (NFR8):**
   - Script generation must not submit forms or modify data
   - Only navigate, analyze, and generate code
   - Actual form submission happens later in Jack's execution (Epic 6)

2. **Data Sovereignty (NFR5):**
   - All processing local via on-prem LLM and browser-use
   - No test case content or generated scripts leave company infrastructure
   - Chrome path stored locally, not transmitted

3. **SSO Session Protection (NFR7):**
   - Reuse existing Chrome SSO session from Story 5.1
   - Do not store or cache credentials in Sarah
   - Browser session managed by SessionManager

### Performance Requirements

**From PRD.md#Performance:**

1. **Script Generation Time:**
   - Individual script generation: <5 minutes (NFR1)
   - Progress updates every 30 seconds during processing
   - Total processing time scales with test case count

2. **Review UI Responsiveness:**
   - Script rendering: <2 seconds
   - Navigation between scripts: <1 second
   - Review actions (Approve/Reject): immediate feedback

3. **Memory Management:**
   - Load test cases and scripts in batches if needed
   - Clean up temporary data after review completion

### Configuration Requirements

**Sarah's Configuration in agents.json:**
```json
{
  "sarah": {
    "model": "sonnet",
    "temperature": 0.0,
    "max_tokens": 4000,
    "tools": ["script_generation", "vision_locator"],
    "prompts": {
      "greeting": "Hi! I'm Sarah. I'll generate Playwright test scripts from Mary's test cases.",
      "progress_template": "Generating script {current} of {total}...",
      "completion": "{count} scripts saved to testscripts/"
    },
    "chrome_path": "remembered_after_first_time",
    "output_directory": "workspace/testscripts/",
    "vision_enabled": true,
    "review_enabled": true
  }
}
```

**Chrome Path Persistence (UX-DR20):**
```python
# Remember Chrome path after first input
chrome_path = self.get_stored_chrome_path()  # Check local storage
if not chrome_path:
    chrome_path = await self.request_chrome_path()  # Ask user
    await self.store_chrome_path(chrome_path)  # Save for next time
```

### UX Design Requirements

**From UX Design Specification:**

1. **Agent Personality (UX-DR19):**
   - Sarah: Purple color, "S" initial avatar
   - Greeting: "Hi! I'm Sarah. I'll generate Playwright test scripts from Mary's test cases."

2. **Side-by-Side Review (UX-DR16):**
   - 50/50 grid layout (`grid grid-cols-2`)
   - 16px gap, independent scroll per panel
   - Left panel: natural-language test case
   - Right panel: Playwright script with syntax highlighting

3. **Navigation (UX-DR14):**
   - Next/Previous buttons for multiple scripts
   - Approve applies to current item only, auto-advance
   - Max 2 buttons visible at a time (UX-DR11)

4. **Processing Indicator (UX-DR7):**
   - Show progress per script: "Generating script 2 of 12..."
   - Animated typing dots + status message
   - `aria-live="polite"` and `role="status"`

5. **State Transitions (UX-DR13):**
   - Badge fade 150ms, input slide-up 200ms, messages fade-in 150ms
   - Forward-only during generation, review allows navigation

### Error Handling Requirements

**Common Error Scenarios:**
1. **Chrome Path Invalid:**
   - Clear error message with path format example
   - Request new path without losing progress
   - Store valid path for future sessions

2. **Script Generation Failures:**
   - Continue with remaining test cases
   - Mark failed scripts for manual review
   - Provide error details in review panel

3. **Vision Analysis Failures:**
   - Fallback to LLM-only generation (from Story 5.3)
   - Log warning but continue processing
   - Indicate fallback mode in review

4. **File System Errors:**
   - Validate output directory permissions
   - Create directories if missing
   - Clear error messages with suggested actions

**Error Message Pattern:**
```python
# 3-part error structure (UX-DR12)
error_message = (
    f"Script generation failed for '{test_case.title}'.\n"  # What happened
    f"The vision model couldn't analyze the target page.\n"  # Why  
    f"Continuing with LLM-only generation. You can review the quality."  # What to do
)
```

### References

- [Source: epics.md#Story 5.4: Sarah Agent — Generate Scripts with Side-by-Side Review] - Story requirements
- [Source: architecture.md#Agent Orchestration Layer] - Agent patterns and lifecycle
- [Source: architecture.md#Pipeline Architecture] - Pipeline integration patterns
- [Source: architecture.md#Implementation Patterns & Consistency Rules] - Code patterns
- [Source: prd.md#Functional Requirements] - FR5, FR6, FR7, FR8, FR9, FR12, FR13
- [Source: prd.md#Non-Functional Requirements] - NFR1, NFR5, NFR7, NFR8 performance/security
- [Source: ux-design-specification.md] - UX-DR5, UX-DR7, UX-DR11, UX-DR14, UX-DR16, UX-DR19, UX-DR20
- [Source: 5-3-vision-assisted-locator-identification.md] - VisionLocator integration
- [Source: 5-2-script-generator-pipeline-stage.md] - ScriptGenerator foundation
- [Source: 2-3-baseagent-lifecycle-start-processing-review-done.md] - BaseAgent extension
- [Source: 3-4-output-writer-pipeline-stage.md] - File output patterns

### Review Findings

**Code Review Date:** 2026-04-20

#### Patch Findings (fixed)

- [x] [Review][Patch] `handle_start` returns early without state transition [sarah.py:462-484] — **FIXED**: Added state transition to PROCESSING before Chrome path request, then back to START.
- [x] [Review][Patch] `handle_reject` loses input context [sarah.py:589-590] — **FIXED**: Store `_start_input_data` and pass to `process()`. Also pass `feedback` to `ScriptGenerator.generate()`.
- [x] [Review][Patch] `_initialize_vision_components` swallows all exceptions [sarah.py:279-281] — **FIXED**: Catch `(OSError, RuntimeError)` specifically, send warning message to user.
- [x] [Review][Patch] `GeneratedScript` not Pydantic model [sarah.py:25-41] — **FIXED**: Converted to `BaseModel` with `ConfigDict(arbitrary_types_allowed=True)`, added `error_message` field.
- [x] [Review][Patch] `_read_script_content` race condition [sarah.py:326-331, 364-381] — **FIXED**: Added retry loop (3 attempts) with sleep for race condition with ScriptGenerator.
- [x] [Review][Patch] No path validation in `_store_chrome_path` [sarah.py:123-139] — **FIXED**: Added validation for non-empty, minimum length, and path format (separators or .exe).
- [x] [Review][Patch] Metadata source_url is relative not absolute [sarah.py:728-730] — **FIXED**: Use `Path.resolve()` to get absolute path.
- [x] [Review][Patch] `handle_navigate` no validation for invalid direction [sarah.py:655-678] — **FIXED**: Added else clause with error message for invalid directions.
- [x] [Review][Patch] `get_review_state` returns different dict shapes [sarah.py:778-801] — **FIXED**: Return consistent keys (`current_script`, `approved_count`) with None/0 values when no scripts.
- [x] [Review][Patch] Empty testcases directory returns success [sarah.py:223-230] — **FIXED**: Return `success=False` with error message when no test case files found.
- [x] [Review][Patch] Index desync when scripts fail mid-generation [sarah.py:303-344] — **FIXED**: Add placeholder `GeneratedScript` with `error_message` for failed scripts to preserve index mapping.

#### Dismissed Findings

- [x] [Review][Dismiss] Race condition on `_generated_scripts` — Python asyncio runs single-threaded, no true concurrent modification risk within single event loop.

## Dev Agent Record

### Agent Model Used

- Cascade (Claude) - Full implementation with comprehensive testing

### Debug Log References

- None required - clean implementation

### Completion Notes List

1. **SarahAgent Implementation Complete**
   - Created `SarahAgent` class extending `BaseAgent` with step_number=4, purple color (#8B5CF6)
   - Implements complete lifecycle: START → PROCESSING → REVIEW_REQUEST → DONE
   - Integrated with ScriptGenerator and VisionLocator for accurate selector generation

2. **Side-by-Side Review Backend**
   - `GeneratedScript` class stores test case, script content, and metadata
   - Review data structure includes test case (left panel) and script content (right panel)
   - Supports pagination via Next/Previous navigation
   - Review actions: Approve (save and advance), Reject (regenerate with feedback), Skip (hand to Minh)

3. **Chrome Path Persistence**
   - Chrome path stored in `workspace/configuration/chrome_path.json`
   - Automatically loaded on agent initialization
   - User prompted for path only if not already saved

4. **WebSocket Communication**
   - Progress messages during script generation ("Generating script X of Y...")
   - Review requests include `review_data` metadata with test case and script content
   - State synchronization via `get_review_state()` method

5. **API Extensions**
   - Added `/api/skip` endpoint for skipping script review
   - Added `/api/navigate` endpoint for Next/Previous navigation
   - Schemas: `SkipRequest`, `NavigateRequest`

6. **Comprehensive Testing**
   - 28 unit tests covering all major functionality
   - Tests for initialization, Chrome persistence, process workflow
   - Tests for approve/reject/skip/navigate actions
   - Tests for review state management
   - All 424 tests passing (existing + new)
   - Ruff linting: passed
   - MyPy type checking: passed

### File List

- `src/ai_qa/agents/sarah.py` - **New**: Sarah agent orchestrator (511 lines)
- `src/ai_qa/agents/__init__.py` - **Modified**: Added SarahAgent and MaryAgent exports
- `src/ai_qa/api/routes.py` - **Modified**: Added /skip and /navigate endpoints
- `src/ai_qa/api/schemas.py` - **Modified**: Added SkipRequest and NavigateRequest schemas
- `tests/test_agents/test_sarah.py` - **New**: 28 comprehensive unit/integration tests
- `workspace/configuration/chrome_path.json` - **Created at runtime**: Chrome path persistence

## Story Completion Status

*Ultimate context engine analysis completed - comprehensive developer guide created*
