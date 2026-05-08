# Acceptance Auditor Review Prompt

## Role
You are an **Acceptance Auditor** — you have the diff, the full story spec, and project context. Your job is to verify compliance with acceptance criteria.

## Story Spec

**Story 5.4: Sarah Agent — Generate Scripts with Side-by-Side Review**

### Acceptance Criteria (from spec)

**AC1**: Given Sarah's step begins after Mary completes
**When** Sarah greets the user
**Then** Sarah introduces herself: "Hi! I'm Sarah. I'll generate Playwright test scripts from Mary's test cases." (UX-DR19, purple avatar)
**And** user inputs local Chrome path (remembered after first time) (UX-DR20)

**AC2**: Given user clicks Start
**When** Sarah processes test cases
**Then** Processing indicator shows progress per script (e.g., "Generating script 2 of 12...")

**AC3**: Given generation completes
**When** Review Request is presented
**Then** split panel shows: left = natural-language test case, right = Playwright Python script with syntax highlighting (UX-DR16, UX-DR5)
**And** Next/Previous buttons navigate between test case + script pairs (UX-DR14)
**And** Approve applies to current script only, auto-advances to next
**And** Reject with feedback triggers Sarah to self-correct that script
**And** Linh can skip review and ask Minh (automation engineer) to review instead
**And** after all scripts approved, status Done: "X scripts saved to testscripts/"
**And** output saved to `workspace/testscripts/` with metadata per script (FR13)

### UX Requirements (from spec)

**UX-DR19**: Agent Personality
- Sarah: Purple color (#8B5CF6), "S" initial avatar
- Greeting: "Hi! I'm Sarah. I'll generate Playwright test scripts from Mary's test cases."

**UX-DR20**: Chrome Path Persistence
- Remember Chrome path after first input
- Store in local storage (not transmitted)

**UX-DR16**: Side-by-Side Review
- 50/50 grid layout (grid grid-cols-2)
- 16px gap, independent scroll per panel
- Left panel: natural-language test case
- Right panel: Playwright script with syntax highlighting

**UX-DR14**: Navigation
- Next/Previous buttons for multiple scripts
- Approve applies to current item only, auto-advance
- Max 2 buttons visible at a time (UX-DR11)

**UX-DR7**: Processing Indicator
- Show progress per script: "Generating script X of Y..."
- Animated typing dots + status message

**UX-DR13**: State Transitions
- Badge fade 150ms, input slide-up 200ms, messages fade-in 150ms
- Forward-only during generation, review allows navigation

### Technical Requirements (from spec)

**FR13**: Output saved to workspace/testscripts/ with metadata per script

**FR19 Scope Boundary**: This story delivers the base split-panel layout only — no selector highlighting, no assertion linking, no confidence score overlay. Those enhancements are deferred to Epic 8 Story 8.2.

**BaseAgent Lifecycle Pattern** [Required]:
```python
class SarahAgent(BaseAgent):
    def __init__(self, config: AppSettings) -> None:
        super().__init__(
            name="Sarah",
            color="purple",
            step_number=4,
            step_title="Generate Scripts",
            config=config
        )
```

**Review Data Structure** [Required]:
```python
class ReviewData(BaseModel):
    test_case: TestCase
    script_content: str
    script_language: str = "python"
    current_index: int
    total_count: int
    can_approve: bool = True
    can_reject: bool = True
    can_skip: bool = True
```

### Security Requirements

**NFR5**: Data Sovereignty
- All processing local via on-prem LLM and browser-use
- Chrome path stored locally, not transmitted

**NFR7**: SSO Session Protection
- Reuse existing Chrome SSO session
- Do not store or cache credentials in Sarah

## Diff to Audit

### src/ai_qa/agents/sarah.py (802 lines)

Key implementation areas:

```python
# Initialization - Lines 56-107
class SarahAgent(BaseAgent):
    def __init__(self, name="Sarah", color="#8B5CF6", step_number=4, ...):
        super().__init__(name, color, step_number, step_title, workspace_dir)
        # Chrome path loading from JSON file
        self._load_chrome_path()
```

```python
# Chrome persistence - Lines 112-139
def _load_chrome_path(self) -> None:
    chrome_path_file = self._workspace_dir / "configuration" / "chrome_path.json"
    if chrome_path_file.exists():
        data = json.loads(chrome_path_file.read_text())
        self._chrome_path = data.get("chrome_path")

async def _store_chrome_path(self, chrome_path: str) -> None:
    chrome_path_file.write_text(json.dumps({"chrome_path": chrome_path}))
```

```python
# Process with progress - Lines 145-205
async def process(self, input_data: dict, feedback: str | None = None) -> StageResult:
    # Sends progress messages via WebSocket
    # "Generating script X of Y..."
```

```python
# Review presentation - Lines 680-718
async def _present_current_script_for_review(self) -> None:
    review_data = {
        "test_case": script.test_case.model_dump(),
        "script_content": script.script_content,
        "script_language": "python",
        "current_index": current,  # 1-based for UI
        "total_count": total,
        "can_approve": True,
        "can_reject": True,
        "can_skip": True,
    }
```

```python
# Review actions - Lines 514-679
async def handle_approve(self) -> None:  # Auto-advances
async def handle_reject(self, feedback: str) -> None:  # Self-correct
async def handle_skip(self) -> None:  # Hand to Minh
async def handle_navigate(self, direction: str) -> None:  # Next/Previous
```

```python
# Metadata output - Lines 720-741
async def _write_approved_scripts_metadata(self) -> None:
    metadata = OutputMetadata(
        source_url=f"workspace/testcases/{script.test_case.filename}.json",
        model=self.config.model_name,
        confidence=script.confidence,
    )
    metadata_path = Path(script.file_path).with_suffix(".metadata.json")
```

### tests/test_agents/test_sarah.py (842 lines, 28 tests)

Test coverage includes:
- Initialization with correct identity (name="Sarah", color="#8B5CF6")
- Chrome path persistence (load/store from JSON)
- Process workflow with progress updates
- All review actions (approve, reject, skip, navigate)
- Review state management
- Review presentation with metadata

### API Changes

**routes.py**: Added `/skip` and `/navigate` endpoints
**schemas.py**: Added SkipRequest, NavigateRequest

## Your Task

Verify compliance with acceptance criteria. For each AC:

1. **Locate implementation** - Find where it's implemented
2. **Verify correctness** - Does it match the spec exactly?
3. **Identify gaps** - What's missing or deviating?

## Output Format

```markdown
## Acceptance Auditor Findings

### [AC#]: [Criteria being checked]
**Status**: ✅ PASS / ❌ FAIL / ⚠️ PARTIAL
**Spec Reference**: [Exact quote from AC]
**Implementation**: [Where it's implemented]
**Evidence**: [Code that implements it]
**Deviation**: [If any - what's wrong or missing]
```

Be specific. Quote the spec. Quote the code. Show the gap.
