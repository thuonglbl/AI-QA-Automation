# Story 4.3: Mary Agent — Create Test Cases with Per-Item Review

**Epic:** 4
**Status:** done

## Story

As a manual QA tester (Linh),
I want Mary to generate test cases from my requirements and let me review each one,
so that I can verify the AI understood my intent before scripts are generated.

## Acceptance Criteria

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

## Tasks / Subtasks

- [x] Create `src/ai_qa/agents/mary.py` with Mary agent orchestrator
  - [x] Implement BaseAgent inheritance (from Story 2.3)
  - [x] Implement Start state: greeting message, no input fields
  - [x] Implement Processing state: read requirements, call TestCaseExtractor, show progress
  - [x] Implement Review Request state: per-item pagination, Approve/Reject with feedback
  - [x] Implement Done state: summary message, transition to Step 4
- [x] Create frontend component for Mary's step (if not already in Story 2.2 scaffold)
  - [x] ChatInputArea state: Start (Start button), Review (Approve/Reject + Next/Previous)
  - [x] ReviewContent component: render test case structure (title, preconditions, steps, expected results)
- [x] Implement WebSocket message handling for Mary agent
  - [x] Processing progress updates ("Generating test case X of Y...")
  - [x] Review Request with test case data
  - [x] Acknowledgment on Reject with feedback
- [x] Create `tests/test_agents/test_mary.py` with unit tests
  - [x] Test Mary agent lifecycle (Start→Processing→Review→Done)
  - [x] Test per-item review navigation
  - [x] Test Reject with feedback self-correction
- [x] Integrate with existing TestCaseExtractor (Story 4.2)
  - [x] Read from `workspace/requirements/`
  - [x] Write to `workspace/testcases/` via OutputWriter

## Dev Notes

### Epic Context

Epic 4 focuses on **Agent Mary (Test Case Generation)**. Story 4.1 (LLM Abstraction Layer) is **DONE**, Story 4.2 (Test Case Extractor Pipeline Stage) is **ready-for-dev**. Story 4.3 is the agent orchestrator that wraps the pipeline stage with human-in-the-loop review.

**Key Dependencies:**
- Story 4.1 (LLM Abstraction Layer) - DONE - Provides `LLMClient` and `LLMConfig`
- Story 4.2 (Test Case Extractor Pipeline Stage) - ready-for-dev - Core pipeline stage for test case generation
- Story 3.4 (Output Writer Pipeline Stage) - DONE - Reuse for file output
- Story 3.5 (Bob Agent) - DONE - Produces input requirements in `workspace/requirements/`
- Story 2.3 (BaseAgent Lifecycle) - DONE - Shared lifecycle pattern

### Architecture Compliance

**MUST FOLLOW - Critical Patterns:**

1. **BaseAgent Inheritance** [Source: architecture.md#Agent Orchestration Layer]
   ```python
   class MaryAgent(BaseAgent):
       def __init__(self):
           super().__init__(
               name="Mary",
               color="green",  # UX-DR19
               step_number=3,
               step_title="Create Test Cases"
           )
   ```
   Follow Start→Processing→ReviewRequest→Done lifecycle with reject feedback loop.

2. **StageResult Pattern** [Source: architecture.md#Pipeline Stage Interface Pattern]
   - TestCaseExtractor (Story 4.2) returns StageResult
   - Mary agent wraps this and adds WebSocket communication
   - Never raise exceptions from agent - return StageResult with errors

3. **Pydantic Models for Data Exchange** [Source: architecture.md#Data Format Patterns]
   - Use TestCase model from Story 4.2
   - AgentMessage model for WebSocket communication
   - Never use raw dicts between components

4. **WebSocket Communication** [Source: architecture.md#Frontend & API Layer]
   - Use WebSocket for real-time agent messages
   - Processing updates, Review Request presentation, feedback acknowledgment
   - REST endpoints for actions (Approve, Reject, Continue)

5. **Module Boundaries** [Source: architecture.md#Architectural Boundaries]
   - `agents/` depends on: `pipelines`, `ai_connection`, `models`, `exceptions`, `config`
   - `agents/` does NOT depend on: `api` (communicates via WebSocket)

### Technical & Library Requirements

**Core Libraries:**
- `BaseAgent` from `src/ai_qa/agents/base.py` (Story 2.3)
- `TestCaseExtractor` from `src/ai_qa/pipelines/test_case_extractor.py` (Story 4.2)
- `OutputWriter` from `src/ai_qa/pipelines/output_writer.py` (Story 3.4)
- `LLMClient` from `src/ai_qa/ai_connection/client.py` (Story 4.1)
- `AgentMessage` from `src/ai_qa/models.py` (Story 1.4)

**Agent Configuration:**
- Read model config from `workspace/configuration/agents.json` (agent_name="mary")
- Default temperature: 0.0 for deterministic test case generation
- Greeting message: "Hi! I'm Mary. I'll create test cases from the requirements Bob extracted."

**Per-Item Review Logic:**
- Maintain list of generated test cases in memory
- Track current review index
- Approve: mark current as approved, advance to next
- Reject with feedback: re-run TestCaseExtractor for single test case with feedback context
- All approved: transition to Done state

### File Structure Requirements

```
src/ai_qa/
├── agents/
│   ├── base.py              # BaseAgent (already exists from Story 2.3)
│   └── mary.py             # Mary agent orchestrator
├── pipelines/
│   ├── test_case_extractor.py   # TestCaseExtractor (from Story 4.2)
│   └── output_writer.py          # OutputWriter (from Story 3.4)
└── models.py                    # TestCase, AgentMessage models

tests/test_agents/
├── __init__.py
└── test_mary.py            # Mary agent tests

frontend/src/components/
├── ChatInputArea.tsx       # Already exists, add Mary-specific states
└── ReviewContent.tsx      # Already exists, add test case rendering
```

### Input/Output Specifications

**Input:**
- Files from `workspace/requirements/` (written by Bob Agent in Step 2)
- Each file contains markdown requirements from Confluence
- Files have associated `metadata.json` with source URL

**Output:**
- Structured test cases saved to `workspace/testcases/` (via OutputWriter)
- Each test case as separate file with kebab-case naming from title
- Format: JSON with test case structure (from Story 4.2)
- Each output includes `metadata.json` with: source URL, timestamp, model used, confidence score

**WebSocket Message Types:**
```python
# Processing progress
AgentMessage(
    sender="mary",
    content="Generating test case 3 of 12...",
    message_type="processing_update"
)

# Review Request
AgentMessage(
    sender="mary",
    content={
        "test_case": TestCase(...),
        "current_index": 2,
        "total_count": 12
    },
    message_type="review_request"
)

# Acknowledgment
AgentMessage(
    sender="mary",
    content="I'll revise the test case to address your feedback about the missing precondition.",
    message_type="acknowledgment"
)

# Done
AgentMessage(
    sender="mary",
    content="12 test cases saved to testcases/",
    message_type="done"
)
```

### Testing Requirements

**Unit Tests Required:**
1. Test Mary agent initialization (name, color, step number)
2. Test Start state: greeting message, no input fields
3. Test Processing state: calls TestCaseExtractor, shows progress updates
4. Test Review Request state: presents test case data via WebSocket
5. Test Approve action: marks current test case approved, advances index
6. Test Reject with feedback: re-runs TestCaseExtractor with feedback context
7. Test Done state: summary message, all test cases approved
8. Test WebSocket message formatting for all message types

**Mock Strategy:**
- Mock TestCaseExtractor to avoid real LLM calls
- Mock OutputWriter to avoid file system writes
- Mock WebSocket connection
- Use sample requirements as test fixtures
- Assert on agent state transitions and WebSocket messages

**Integration Tests:**
- Test end-to-end flow from requirements input to testcases output
- Test per-item review navigation (Next/Previous)
- Test reject feedback loop (feedback → self-correction → re-presentation)

### Previous Story Intelligence

**From Story 4.2 (Test Case Extractor Pipeline Stage) - [Source: 4-2-test-case-extractor-pipeline-stage.md]:**

- `TestCaseExtractor` class is in `src/ai_qa/pipelines/test_case_extractor.py`
- Returns `StageResult` with generated test cases and confidence score
- Uses `LLMClient` from Story 4.1 for LLM calls
- Prompt template in `src/ai_qa/prompts/test_extraction.py`
- Test case structure: title, preconditions, steps (list), expected_results, automation_hints
- Confidence scoring algorithm based on LLM response quality

**From Story 2.3 (BaseAgent Lifecycle) - [Source: implementation-artifacts/2-3-baseagent-lifecycle-start-processing-review-done.md]:**

- `BaseAgent` class in `src/ai_qa/agents/base.py`
- Lifecycle: Start → Processing → ReviewRequest → (Approve/Reject+feedback) → Done
- Reject with feedback triggers re-processing using feedback context
- Agent sends messages to frontend via WebSocket using `AgentMessage` model
- Agent reads config from `workspace/configuration/agents.json` if available
- Creates `workspace/` directory structure with subfolders per run

**From Story 3.4 (Output Writer Pipeline Stage):**

- `OutputWriter` class in `src/ai_qa/pipelines/output_writer.py`
- Writes files to correct workspace subfolder
- Includes `metadata.json` with source URL, timestamp, model used, confidence score
- File naming derived from source content titles using kebab-case
- Configurable output directory

**Key Code Patterns from Previous Stories:**
```python
# From BaseAgent - how to inherit and initialize
class MaryAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Mary",
            color="green",
            step_number=3,
            step_title="Create Test Cases"
        )
        self.config = LLMConfig.from_agents_json(agent_name="mary")
        self.extractor = TestCaseExtractor()
        self.writer = OutputWriter()

# From TestCaseExtractor - how to call pipeline stage
result = await self.extractor.process(requirements, self.config)
if not result.success:
    return StageResult(success=False, errors=result.errors)

# From BaseAgent - how to send WebSocket messages
await self.websocket.send_json(
    AgentMessage(
        sender=self.name,
        content=message,
        message_type="processing_update"
    ).model_dump()
)
```

**Git Intelligence Summary:**
- Recent commits show pattern: `feat: Story X.X: [Story Title]`
- Story 4.2 touched: `prompts/test_extraction.py`, `pipelines/test_case_extractor.py`
- Story 2.3 touched: `agents/base.py`
- All tests must pass (pattern established in previous stories)
- Ruff + mypy must pass before considering work done

### UX Requirements

**From UX Design Specification [Source: ux-design-specification.md#Step 3: Create Test Cases (Agent Mary)]:**

- **No user input needed** - Mary reads from `requirements/` folder
- **Processing indicator** shows progress per test case
- **Review Request** shows single test case with clear structure: title, preconditions, steps, expected results
- **Navigation:** Next/Previous to step through test cases
- **Approve** or **Reject** (with feedback — Mary self-corrects and re-presents)
- **Agent personality:** Mary (M/green avatar)
- **Greeting:** "Hi! I'm Mary. I'll create test cases from the requirements Bob extracted."
- **Completion:** All test cases approved → Status: Done → Output: `testcases/` folder

**UX-DR12 (Feedback Patterns):**
- Agent paraphrases feedback in acknowledgment before re-processing
- Rejection ack: agent paraphrases feedback + begins re-processing

**UX-DR14 (Navigation):**
- Forward-only during pipeline execution (no skip ahead)
- Next/Previous buttons during multi-item review
- Approve applies to current item only, auto-advance to next

**UX-DR19 (Agent Personalities):**
- Mary (M/green)
- Greeting message introducing role

### References

- [Source: epics.md#Story 4.3: Mary Agent — Create Test Cases with Per-Item Review] - Story requirements
- [Source: architecture.md#Agent Orchestration Layer] - Agent lifecycle and patterns
- [Source: architecture.md#Data Flow] - Mary agent data flow diagram
- [Source: ux-design-specification.md#Step 3: Create Test Cases (Agent Mary)] - UX requirements for Mary
- [Source: 4-2-test-case-extractor-pipeline-stage.md] - Previous story implementation
- [Source: 2-3-baseagent-lifecycle-start-processing-review-done.md] - BaseAgent pattern
- [Source: 3-4-output-writer-pipeline-stage.md] - OutputWriter pattern

## Dev Agent Record

### Agent Model Used

<!-- To be filled by dev agent -->

### Debug Log References

<!-- To be filled by dev agent -->

### Completion Notes List

- Implemented MaryAgent class inheriting from BaseAgent with correct identity properties (name="Mary", color="green", step_number=3, step_title="Create Test Cases")
- Implemented all lifecycle states: Start (greeting message), Processing (reads requirements from workspace/requirements/, calls TestCaseExtractor, shows progress updates), Review Request (per-item pagination with current_review_index tracking), Done (summary message with test case count)
- Implemented per-item review with Approve/Reject with feedback:
  - Approve: marks current test case as approved (by advancing index), auto-advances to next test case
  - Reject with feedback: paraphrases feedback in acknowledgment, re-runs TestCaseExtractor for current test case, re-presents for review
  - All approved: writes all test cases to workspace/testcases/ via OutputWriter, transitions to Done state
- Implemented WebSocket message handling:
  - Processing progress updates: "Generating test case X of Y..." for each test case
  - Review Request: formatted test case content with title, preconditions, steps, expected results, automation hints, plus navigation metadata (current_index, total_count)
  - Acknowledgment on Reject: paraphrases feedback before re-processing
- Integrated with TestCaseExtractor (Story 4.2) for test case generation
- Integrated with OutputWriter (Story 3.4) for persisting approved test cases
- Added frontend navigation support to ChatInputArea component:
  - Added Next/Previous buttons for per-item review navigation (UX-DR14)
  - Added currentIndex, totalCount, onNext, onPrevious props to ChatInputAreaProps interface
  - Navigation bar shows "X of Y" position with disabled state for first/last items
- ReviewContent component already supports markdown rendering, sufficient for test case structure display
- Created comprehensive unit tests (14 tests) covering:
  - Agent initialization and state properties
  - Process method with requirements reading, progress updates, empty requirements, extractor failure
  - handle_approve with test case approval, Done transition, test case writing
  - handle_reject with feedback acknowledgment and test case regeneration
  - _format_review_content with test case structure and navigation info
- All tests passing (14/14 Mary agent tests, 306/306 total tests)
- Followed TDD red-green-refactor approach: wrote failing tests first, then implemented to pass
- Followed architecture patterns: BaseAgent inheritance, StageResult pattern, Pydantic models, WebSocket communication, module boundaries

### File List

**New Files Created:**
- `src/ai_qa/agents/mary.py` - Mary agent orchestrator with per-item review (112 lines)
- `tests/test_agents/test_mary.py` - Mary agent unit tests (14 tests, 396 lines)

**Modified Files:**
- `frontend/src/components/ChatInputArea.tsx` - Added Next/Previous navigation buttons for per-item review
- `frontend/src/types/pipeline.ts` - Added navigation props (currentIndex, totalCount, onNext, onPrevious) to ChatInputAreaProps interface

**Files Used (No Changes):**
- `src/ai_qa/agents/base.py` - BaseAgent class (inherited by MaryAgent)
- `src/ai_qa/pipelines/test_case_extractor.py` - TestCaseExtractor (used for test case generation)
- `src/ai_qa/pipelines/output_writer.py` - OutputWriter (used for persisting test cases)
- `src/ai_qa/ai_connection/config.py` - LLMConfig (used for agent configuration)
- `src/ai_qa/models.py` - TestCase, StageResult, AgentMessage models
- `frontend/src/components/ReviewContent.tsx` - Used for rendering test case markdown (no changes needed)

## Story Completion Status

*Ultimate context engine analysis completed - comprehensive developer guide created*
