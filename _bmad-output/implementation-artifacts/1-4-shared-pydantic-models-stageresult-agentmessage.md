# Story 1.4: Shared Pydantic Models (StageResult, AgentMessage)

**Story ID:** 1.4
**Story Key:** 1-4-shared-pydantic-models-stageresult-agentmessage
**Epic:** 1 — Project Foundation & Infrastructure Setup
**Status:** done
**Date Created:** 2026-04-08

---

## User Story

**As a** R&D engineer,
**I want** shared Pydantic models in `src/ai_qa/models.py`,
**So that** all pipeline stages and agents exchange data through typed, validated models — never raw dicts.

---

## Acceptance Criteria

**Given** the models module is created
**When** any pipeline stage completes processing
**Then** it returns a `StageResult` model with fields: `success: bool`, `data: Any | None`, `errors: list[str]`, `warnings: list[str]`, `confidence: float | None`
**And** `AgentMessage` model supports agent-to-frontend communication (sender, content, timestamp, message type)
**And** all JSON output uses snake_case keys
**And** datetime fields use ISO 8601 format
**And** project-wide constants are defined in `src/ai_qa/constants.py`

---

## Developer Context

### Current State (from Stories 1.1, 1.2, and 1.3)

The project has a fully functional foundation:
- `src/ai_qa/` — PEP 621 compliant src layout (Story 1-1)
- `src/ai_qa/config.py` — `AppSettings` with Pydantic v2.4.0+ (Story 1-2)
- `src/ai_qa/exceptions.py` — structured exception hierarchy (Story 1-3)
- `src/ai_qa/__main__.py` — CLI entry point
- `tests/test_config.py` and `tests/test_exceptions.py` — integration-style test patterns

**Next step:** Create models.py and constants.py to enable type-safe data exchange across the pipeline.

### What Models are for

From the architecture document, the pipeline has 6 distinct stages:
1. **Configuration** (read env/YAML, validate settings)
2. **Requirements** (Bob agent: parse Confluence via MCP, extract test requirements)
3. **TestCases** (Mary agent: generate test cases from requirements)
4. **TestScripts** (Sarah agent: generate Playwright scripts from test cases)
5. **Execution** (Jack agent: run scripts in browser-use, collect results)
6. **Report** (Generate metrics, audit trail, dashboard data)

Each stage produces a `StageResult` — a validated envelope with `success`, `data`, `errors`, `warnings`, and `confidence`. Each agent talks to the frontend via `AgentMessage` — typed messages with sender, content, timestamp, and type.

---

## Technical Requirements

### 1. Dependencies Already Available

This story uses **Pydantic v2.4.0+** (already in `pyproject.toml` via `pydantic-settings>=2.4.0`). No new packages needed.

**Key Pydantic v2 features used:**
- `BaseModel` for data validation and serialization
- `Field()` descriptors with descriptions and constraints
- `ConfigDict` for validation and serialization config
- `model_dump_json()` for ISO 8601 datetime serialization (automatic)
- Type hints required (mypy strict mode enforced)

### 2. Create `src/ai_qa/models.py`

**File location:** `src/ai_qa/models.py`

```python
"""Shared Pydantic models for the AI QA automation pipeline.

All pipeline stages exchange data through typed models, never raw dicts.
This ensures type safety, validation, and proper JSON serialization.

Models:
  - StageResult: Wrapper for pipeline stage output (success, data, errors, warnings, confidence)
  - AgentMessage: Agent-to-frontend communication (sender, content, timestamp, message_type)
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StageResult(BaseModel):
    """Validated output from any pipeline stage.

    This model wraps the result of processing through a stage (e.g., Requirements extraction,
    Test Case generation, Script generation). Stages MUST return StageResult, not raw dicts.

    Attributes:
        success: True if stage completed without fatal errors.
        data: The stage's output payload (test requirements, test cases, scripts, execution results, etc.).
              Specific type depends on stage. Can be None if stage failed or produced no data.
        errors: List of fatal errors that prevented successful processing (empty if success=True).
        warnings: List of non-fatal warnings (low confidence, missing fields, retries needed, etc.).
        confidence: Overall confidence in the result (0.0 to 1.0), or None if not applicable.
                   Used by downstream stages to decide whether to proceed or flag for review.
    """

    success: bool = Field(description="Stage succeeded without fatal errors")
    data: Any | None = Field(default=None, description="Stage output payload (type depends on stage)")
    errors: list[str] = Field(default_factory=list, description="Fatal errors that blocked processing")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings")
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence in result (0.0-1.0), None if not applicable",
    )

    class Config:
        """Pydantic v2 serialization config."""
        # Validate field assignments to catch mutations early
        validate_assignment = True
        # JSON will use snake_case (all fields are already snake_case, but set this as convention)
        alias_generator = None  # Our fields are already snake_case


class AgentMessage(BaseModel):
    """Typed message from an agent to the frontend UI.

    Each agent (Alice, Bob, Mary, Sarah, Jack) sends progress updates, results, and user feedback
    through AgentMessage. The frontend subscribes to these messages via WebSocket and updates the UI.

    Attributes:
        sender: Name of the sending agent (e.g., 'alice', 'bob', 'mary', 'sarah', 'jack').
        content: Message text or structured data (markdown, error trace, approval prompt, etc.).
        timestamp: When the message was generated (ISO 8601 format, auto-set from datetime).
        message_type: Classification of message type for UI rendering:
                     'status' (progress update), 'result' (stage complete), 'error' (failure),
                     'review' (awaiting user action), 'info' (FYI message).
    """

    sender: str = Field(description="Name of the sending agent (e.g., 'alice', 'bob', 'mary')")
    content: str = Field(description="Message text or structured data (markdown, JSON, etc.)")
    timestamp: datetime = Field(description="When the message was generated (ISO 8601 format)")
    message_type: str = Field(
        description="Message classification: 'status', 'result', 'error', 'review', 'info'"
    )

    class Config:
        """Pydantic v2 serialization config."""
        validate_assignment = True
        # Datetime fields automatically serialize to ISO 8601 in model_dump_json()
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }
```

**Design decisions:**
- `StageResult.data` is `Any | None` because different stages produce different types (list[str] for requirements, list[TestCase] for test cases, etc.).
- `confidence` is `float | None` (with `ge=0.0, le=1.0` validation) because not all stages produce confidence scores.
- `AgentMessage.timestamp` is a `datetime` object, NOT a string. Pydantic automatically serializes to ISO 8601 in `model_dump_json()`.
- `Config` class sets `validate_assignment=True` to catch mutations early (e.g., if code tries to set `stageresult.success = None`, Pydantic will validate and reject).
- `alias_generator = None` — not needed because our fields are already snake_case. Set this as convention for clarity.

### 3. Create `src/ai_qa/constants.py`

**File location:** `src/ai_qa/constants.py`

```python
"""Project-wide constants for the AI QA automation pipeline.

Define all constants here for consistency and to avoid magic strings/numbers scattered
throughout the codebase. Configuration values (e.g., LLM temperature, timeouts) belong
in config.py; runtime constants (agent names, stage names, etc.) belong here.
"""

# --- Agent Names ---
AGENT_ALICE = "alice"  # Configuration & orchestration agent
AGENT_BOB = "bob"  # Requirements extraction (Confluence reader)
AGENT_MARY = "mary"  # Test case generation
AGENT_SARAH = "sarah"  # Test script generation (Playwright)
AGENT_JACK = "jack"  # Test execution & reporting

ALL_AGENTS = [AGENT_ALICE, AGENT_BOB, AGENT_MARY, AGENT_SARAH, AGENT_JACK]

# --- Pipeline Stage Names ---
STAGE_CONFIGURATION = "configuration"
STAGE_REQUIREMENTS = "requirements"
STAGE_TEST_CASES = "test_cases"
STAGE_TEST_SCRIPTS = "test_scripts"
STAGE_EXECUTION = "execution"
STAGE_REPORT = "report"

ALL_STAGES = [
    STAGE_CONFIGURATION,
    STAGE_REQUIREMENTS,
    STAGE_TEST_CASES,
    STAGE_TEST_SCRIPTS,
    STAGE_EXECUTION,
    STAGE_REPORT,
]

# --- AgentMessage Types ---
MESSAGE_TYPE_STATUS = "status"  # Progress update (e.g., "Parsing Confluence page 2/5")
MESSAGE_TYPE_RESULT = "result"  # Stage complete with output
MESSAGE_TYPE_ERROR = "error"  # Fatal error occurred
MESSAGE_TYPE_REVIEW = "review"  # Awaiting user approval/rejection
MESSAGE_TYPE_INFO = "info"  # FYI message (no action needed)

ALL_MESSAGE_TYPES = [
    MESSAGE_TYPE_STATUS,
    MESSAGE_TYPE_RESULT,
    MESSAGE_TYPE_ERROR,
    MESSAGE_TYPE_REVIEW,
    MESSAGE_TYPE_INFO,
]

# --- Confidence Thresholds ---
CONFIDENCE_THRESHOLD_HIGH = 0.8  # >= 0.8: High confidence, proceed without review
CONFIDENCE_THRESHOLD_MEDIUM = 0.5  # 0.5-0.79: Medium confidence, optional review
CONFIDENCE_THRESHOLD_LOW = 0.0  # < 0.5: Low confidence, MUST review before proceeding

# --- LLM Model Names ---
LLM_CLAUDE_SONNET = "claude-sonnet-4-6"  # PoC LLM (Anthropic Claude)
LLM_DEEPSEEK = "deepseek-chat"  # M1 on-premise LLM
LLM_QWEN = "qwen-max"  # M1 on-premise LLM (backup)

ALL_LLMS = [LLM_CLAUDE_SONNET, LLM_DEEPSEEK, LLM_QWEN]

# --- Default Timeouts (in seconds) ---
TIMEOUT_MCP_REQUEST = 30  # MCP server call timeout
TIMEOUT_LLM_REQUEST = 60  # LLM API call timeout (may exceed for large generation)
TIMEOUT_BROWSER_ACTION = 30  # Playwright action timeout
TIMEOUT_BROWSER_LOAD = 60  # Page load timeout

# --- Pagination & Limits ---
DEFAULT_CONFLUENCE_PAGE_SIZE = 25  # Results per MCP query
MAX_CONFLUENCE_PAGES = 10  # Maximum pages to fetch before truncating (prevent infinite loops)
MAX_RETRIES_LLM = 3  # Retry failed LLM calls up to N times
MAX_RETRIES_MCP = 2  # Retry failed MCP calls up to N times

# --- HTTP Endpoints (for future API server in Epic 2) ---
API_ENDPOINT_METRICS = "/api/metrics"
API_ENDPOINT_AUDIT = "/api/audit"
API_ENDPOINT_CONFIG = "/api/config"
API_ENDPOINT_RESULTS = "/api/results"

# --- File Naming Conventions ---
OUTPUT_FILE_EXTENSION = ".py"  # Generated scripts are Python files
OUTPUT_DIR_SCRIPTS = "generated_scripts"  # Directory for generated Playwright scripts
OUTPUT_DIR_REPORTS = "reports"  # Directory for execution reports

# --- Database & Persistence (for M1) ---
DB_TABLE_AUDIT = "audit_log"
DB_TABLE_METRICS = "metrics"
DB_TABLE_CACHE = "generation_cache"
```

**Design decisions:**
- **Grouped by category** (Agent Names, Pipeline Stages, Message Types, etc.) for readability.
- **SCREAMING_SNAKE_CASE** for all constants (Python convention for module-level constants).
- **Descriptive names** — `AGENT_BOB = "bob"` makes code readable (`if sender == AGENT_BOB:` vs. `if sender == "bob"`).
- **List groupings** (e.g., `ALL_AGENTS`, `ALL_STAGES`) enable iteration and validation (e.g., `if message_type not in ALL_MESSAGE_TYPES: raise ValueError`).
- **Thresholds as constants** — `CONFIDENCE_THRESHOLD_HIGH = 0.8` is easier to tune than hardcoded `0.8` scattered in code.
- **Comments explain purpose** — e.g., why `TIMEOUT_LLM_REQUEST > TIMEOUT_BROWSER_ACTION` (LLM can take longer).

### 4. Create `tests/test_models.py`

```python
"""Tests for shared Pydantic models (StageResult, AgentMessage)."""
import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from ai_qa.models import AgentMessage, StageResult


# --- StageResult Tests ---


def test_stage_result_success_with_data() -> None:
    """StageResult with success=True and data."""
    result = StageResult(
        success=True,
        data={"test": "output"},
        errors=[],
        warnings=["unused_field"],
        confidence=0.95,
    )
    assert result.success is True
    assert result.data == {"test": "output"}
    assert result.errors == []
    assert result.warnings == ["unused_field"]
    assert result.confidence == 0.95


def test_stage_result_failure_with_errors() -> None:
    """StageResult with success=False and errors."""
    result = StageResult(
        success=False,
        data=None,
        errors=["MCP timeout", "Retry limit exceeded"],
        warnings=[],
        confidence=None,
    )
    assert result.success is False
    assert result.data is None
    assert len(result.errors) == 2
    assert result.confidence is None


def test_stage_result_defaults() -> None:
    """StageResult fields have sensible defaults."""
    result = StageResult(success=True)
    assert result.success is True
    assert result.data is None
    assert result.errors == []
    assert result.warnings == []
    assert result.confidence is None


def test_stage_result_confidence_validation() -> None:
    """Confidence must be 0.0-1.0 or None."""
    # Valid: 0.0
    result = StageResult(success=True, confidence=0.0)
    assert result.confidence == 0.0

    # Valid: 1.0
    result = StageResult(success=True, confidence=1.0)
    assert result.confidence == 1.0

    # Valid: None
    result = StageResult(success=True, confidence=None)
    assert result.confidence is None

    # Invalid: > 1.0
    with pytest.raises(ValidationError):
        StageResult(success=True, confidence=1.5)

    # Invalid: < 0.0
    with pytest.raises(ValidationError):
        StageResult(success=True, confidence=-0.1)


def test_stage_result_json_serialization() -> None:
    """StageResult serializes to JSON with snake_case keys."""
    result = StageResult(
        success=True,
        data={"inner_key": "value"},
        errors=[],
        warnings=[],
        confidence=0.85,
    )
    json_str = result.model_dump_json()
    data = json.loads(json_str)

    # Verify snake_case in JSON
    assert "success" in data
    assert "data" in data
    assert "errors" in data
    assert "warnings" in data
    assert "confidence" in data
    assert data["success"] is True
    assert data["confidence"] == 0.85


def test_stage_result_json_deserialization() -> None:
    """StageResult can be reconstructed from JSON."""
    original = StageResult(
        success=True,
        data=["item1", "item2"],
        errors=[],
        warnings=["warning1"],
        confidence=0.72,
    )
    json_str = original.model_dump_json()
    reconstructed = StageResult.model_validate_json(json_str)

    assert reconstructed.success == original.success
    assert reconstructed.data == original.data
    assert reconstructed.warnings == original.warnings
    assert reconstructed.confidence == original.confidence


# --- AgentMessage Tests ---


def test_agent_message_creation() -> None:
    """AgentMessage with all fields."""
    now = datetime(2026, 4, 8, 10, 30, 45, 123456)
    msg = AgentMessage(
        sender="bob",
        content="Parsed 5 requirements from Confluence",
        timestamp=now,
        message_type="status",
    )
    assert msg.sender == "bob"
    assert msg.content == "Parsed 5 requirements from Confluence"
    assert msg.timestamp == now
    assert msg.message_type == "status"


def test_agent_message_timestamp_auto_set_with_datetime() -> None:
    """AgentMessage timestamp can be a datetime object."""
    msg = AgentMessage(
        sender="mary",
        content="Generated 3 test cases",
        timestamp=datetime.now(),
        message_type="result",
    )
    assert isinstance(msg.timestamp, datetime)


def test_agent_message_json_serialization_iso8601() -> None:
    """AgentMessage timestamp serializes to ISO 8601 in JSON."""
    msg = AgentMessage(
        sender="sarah",
        content="Script generation complete",
        timestamp=datetime(2026, 4, 8, 10, 30, 45, 123456),
        message_type="result",
    )
    json_str = msg.model_dump_json()
    data = json.loads(json_str)

    # Timestamp must be ISO 8601 string in JSON
    assert isinstance(data["timestamp"], str)
    assert data["timestamp"] == "2026-04-08T10:30:45.123456"
    assert "T" in data["timestamp"]  # ISO 8601 format


def test_agent_message_json_deserialization() -> None:
    """AgentMessage can be reconstructed from JSON (string timestamp)."""
    json_str = (
        '{"sender": "jack", "content": "3/5 scripts passed", '
        '"timestamp": "2026-04-08T14:22:30.000000", "message_type": "status"}'
    )
    msg = AgentMessage.model_validate_json(json_str)

    assert msg.sender == "jack"
    assert msg.content == "3/5 scripts passed"
    assert isinstance(msg.timestamp, datetime)
    assert msg.timestamp.year == 2026
    assert msg.message_type == "status"


def test_agent_message_validation_sender() -> None:
    """AgentMessage sender must be a string."""
    with pytest.raises(ValidationError):
        AgentMessage(
            sender=123,  # Invalid: not a string
            content="test",
            timestamp=datetime.now(),
            message_type="status",
        )


def test_agent_message_validation_message_type() -> None:
    """AgentMessage message_type must be a string."""
    with pytest.raises(ValidationError):
        AgentMessage(
            sender="bob",
            content="test",
            timestamp=datetime.now(),
            message_type=42,  # Invalid: not a string
        )


# --- Cross-Model Tests ---


def test_stage_result_with_agent_message_in_data() -> None:
    """Verify StageResult can hold AgentMessage in data field."""
    msg = AgentMessage(
        sender="bob",
        content="Processing complete",
        timestamp=datetime.now(),
        message_type="result",
    )
    result = StageResult(
        success=True,
        data={"message": msg.model_dump()},  # Can serialize message to dict
        confidence=0.9,
    )
    assert result.success is True
    assert result.data["message"]["sender"] == "bob"
```

**Testing patterns:**
- Test valid cases first (happy path).
- Test field defaults and optional fields (None, empty lists).
- Test validation constraints (confidence 0.0-1.0, correct types).
- Test JSON serialization/deserialization (round-trip).
- Test cross-model composition (StageResult containing AgentMessage).
- Use `pytest.raises(ValidationError)` for invalid input.

### 5. Update Imports in `src/ai_qa/__init__.py`

Add public API exports:

```python
"""AI QA Automation pipeline — intelligent test generation from Confluence."""

from ai_qa.exceptions import (
    AIQAError,
    BrowserError,
    ConfigError,
    LLMError,
    MCPError,
    PipelineError,
)
from ai_qa.models import AgentMessage, StageResult

__all__ = [
    # Exceptions
    "AIQAError",
    "ConfigError",
    "LLMError",
    "MCPError",
    "BrowserError",
    "PipelineError",
    # Models
    "StageResult",
    "AgentMessage",
]
```

This allows downstream code to import cleanly:
```python
from ai_qa import StageResult, AgentMessage, ConfigError
```

---

## Architecture Compliance

### Design Patterns from Story 1.3 Continued

- **Docstrings with hierarchy diagrams** — models.py module docstring explains StageResult and AgentMessage relationships.
- **Field descriptions via Pydantic Field()** — each field has a description for self-documentation (and OpenAPI schema generation in Epic 2).
- **Config class for Pydantic settings** — `validate_assignment=True` mirrors the rigor from config.py's custom validators.
- **Type hints mandatory** — all fields fully type-hinted (mypy strict mode compliance).

### Technical Stack Alignment

- **Pydantic v2.4.0+** — leverages v2 features (ConfigDict, field validation, ISO 8601 datetime handling).
- **datetime for timestamps** — not strings. Pydantic serializes to ISO 8601 automatically in `model_dump_json()`.
- **snake_case in JSON** — all field names already snake_case, enforced as convention (no `alias_generator` needed).
- **Validation constraints** — confidence uses `ge=0.0, le=1.0` (same pattern as config.py's `ge`, `le` for temperature).

---

## File Structure Requirements

```
src/ai_qa/
├── __init__.py          ← UPDATE (add model exports)
├── __main__.py          (no change from Story 1.3)
├── config.py            (no change from Story 1.2)
├── exceptions.py        (no change from Story 1.3)
├── models.py            ← CREATE (this story)
└── constants.py         ← CREATE (this story)

tests/
├── __init__.py          (no change)
├── test_config.py       (no change)
├── test_exceptions.py   (no change)
└── test_models.py       ← CREATE (test models.py)
```

---

## Testing Strategy

### Unit Tests (tests/test_models.py)

**StageResult tests:**
- ✓ Constructor with all fields
- ✓ Constructor with success=False and errors
- ✓ Field defaults (data=None, errors=[], etc.)
- ✓ Confidence validation (0.0-1.0 range, rejection of invalid values)
- ✓ JSON serialization (snake_case keys)
- ✓ JSON deserialization (round-trip)

**AgentMessage tests:**
- ✓ Constructor with all fields
- ✓ Timestamp as datetime object
- ✓ JSON serialization (ISO 8601 timestamp)
- ✓ JSON deserialization (ISO 8601 string → datetime)
- ✓ Validation (sender, message_type required and type-checked)

**Cross-model tests:**
- ✓ StageResult can hold AgentMessage in data field

### Integration Tests (to verify with rest of project)

After implementation, verify:
- Models can be imported from `ai_qa` package (`from ai_qa import StageResult, AgentMessage`)
- Tests pass with `pytest` (should succeed without errors)
- mypy strict mode passes (`mypy src/ai_qa` should report no errors)
- `uv sync` still succeeds (no dependency conflicts)

---

## Previous Story Intelligence (Story 1.3)

### Learnings from Exception Hierarchy Implementation

1. **Module-level docstring as specification** — Story 1.3's docstring with ASCII hierarchy diagram was read by the developer and helped implementation. Apply this pattern to models.py.

2. **Custom `__repr__()` helpful for debugging** — Story 1.3's `AIQAError.__repr__()` makes exception traces readable. Consider if `StageResult.__repr__()` would be useful (likely not needed since Pydantic provides good defaults).

3. **Inheritance pattern worked well** — Story 1.3's approach of having child exceptions inherit `__init__` cleanly works. Apply same philosophy to models (inherit BaseModel, override only where needed).

4. **Field-level details optional** — Story 1.3's `details` parameter (optional technical context) was useful. Apply to models: `AgentMessage.content` can hold markdown, JSON, or plain text (flexible).

5. **Configuration class for validation** — Story 1.3 used class-level patterns. In models, use Pydantic's Config class for consistency (validate_assignment, json_encoders).

### Testing Patterns from Story 1.3

- **Test inheritance hierarchy first** (ensure all exceptions inherit from AIQAError).
- **Test constructor variations** (with/without optional fields).
- **Test type validation** (ensure wrong types are rejected).
- **Test repr and str** (verify debugging output is useful).

Apply to models:
- Test all model fields validate correctly.
- Test JSON serialization round-trips.
- Test datetime serialization (ISO 8601 format).

---

## Git Context

**Recent commits** (from Story 1.3 and earlier):
- `51e4361 feat: Story 1.3: Custom Exception Hierarchy` — implemented exceptions.py, updated __main__.py, added tests
- `95aef72 feat: Story 1.2: Configuration System with Pydantic Settings` — implemented config.py with BaseSettings
- `e319756 feat: Story 1.1: Project Restructure to src Layout` — restructured to src/ai_qa/, updated pyproject.toml

**Commit message pattern:** `feat: Story X.Y: Title` (follow this pattern for this story).

**Pre-commit hooks:** Story 1.5 will add (ruff, mypy, pytest), so ensure code is clean now.

---

## Implementation Checklist

- [ ] Create `src/ai_qa/models.py` with `StageResult` and `AgentMessage`
- [ ] Create `src/ai_qa/constants.py` with all project constants
- [ ] Create `tests/test_models.py` with comprehensive tests
- [ ] Update `src/ai_qa/__init__.py` to export models
- [ ] Run tests: `pytest tests/test_models.py` (all pass)
- [ ] Run mypy: `mypy src/ai_qa` (no errors)
- [ ] Run ruff (if available): `ruff check src/` (no issues)
- [ ] Commit: `git commit -m "feat: Story 1.4: Shared Pydantic Models (StageResult, AgentMessage)"`

---

## Definition of Done

✅ **Story 1.4 is done when:**

1. ✓ `src/ai_qa/models.py` created with `StageResult` and `AgentMessage` per AC
2. ✓ `src/ai_qa/constants.py` created with all project-wide constants
3. ✓ All tests pass: `pytest tests/test_models.py -v` (at least 15+ test cases)
4. ✓ Type checking passes: `mypy src/ai_qa --strict` (no errors or warnings)
5. ✓ Models properly exported from `src/ai_qa/__init__.py`
6. ✓ All AC verified:
   - `StageResult` has required fields with correct types and defaults
   - `AgentMessage` supports agent-to-frontend communication
   - JSON serialization uses snake_case (automatic, verified in tests)
   - Datetimes serialize to ISO 8601 (automatic, verified in tests)
   - Constants defined and used in doc examples
7. ✓ Commit created with clear message

---

## Helpful Commands

```bash
# Run specific test file
pytest tests/test_models.py -v

# Run all tests
pytest -v

# Type check with mypy strict mode
mypy src/ai_qa --strict

# Format code (if installed)
ruff format src/ai_qa

# Lint code (if installed)
ruff check src/ai_qa --fix
```

---

## Next Steps After Done

Once Story 1.4 is complete:

1. **Story 1.5:** Dev Tooling Setup (ruff, mypy, pytest, pre-commit) — will enforce these patterns project-wide
2. **Epic 2:** Begin FastAPI server and React frontend with WebSocket support for `AgentMessage` streams
3. Models will be reused by every subsequent epic (pipeline orchestration, agents, API contracts)

---

## Questions During Development?

Refer back to:
- **Pydantic v2 docs:** [pydantic.dev](https://docs.pydantic.dev/latest/)
- **Story 1.3 (exceptions.py):** Similar docstring structure and patterns
- **Story 1.2 (config.py):** Field validation patterns and BaseSettings structure
- **Architecture document:** Pipeline stage names and agent lifecycle

Good luck! 🚀

---

## Dev Agent Record

### Implementation Plan

**Approach:** Red-Green-Refactor cycle with Pydantic v2 best practices

1. **RED:** Write comprehensive tests for StageResult and AgentMessage (26 test cases covering validation, serialization, deserialization, edge cases)
2. **GREEN:** Implement models.py with ConfigDict for validation and custom field serializers, constants.py with project-wide constants
3. **REFACTOR:** Migrate from deprecated class-based Config to modern ConfigDict and field_serializer decorators

**Technical Decisions:**

- **Pydantic v2:** Used modern ConfigDict and field_serializer (not deprecated Config class or json_encoders)
- **Datetime handling:** datetime objects (not strings), Pydantic automatically serializes to ISO 8601 in JSON
- **Validation:** Confidence field constrained to 0.0-1.0 range, all required fields enforced by Pydantic
- **JSON serialization:** All fields automatically serialize to snake_case (they were already snake_case)
- **Constants:** Organized by category (Agent Names, Stages, Message Types, Thresholds, Timeouts, etc.) for maintainability

### Completion Notes

**All acceptance criteria satisfied:**

- ✓ **AC1:** StageResult created with fields: success, data, errors, warnings, confidence
- ✓ **AC2:** AgentMessage created for agent-to-frontend communication: sender, content, timestamp, message_type
- ✓ **AC3:** JSON output uses snake_case keys (verified with model_dump_json())
- ✓ **AC4:** Datetime fields use ISO 8601 format (automatic Pydantic serialization: "2026-04-08T10:00:00")
- ✓ **AC5:** Project-wide constants defined in constants.py (50+ constants across 6 categories)

**Test Results:**

- 26 new tests for models: 100% pass rate
- 16 existing tests (config + exceptions): 100% pass rate
- 0 regressions introduced
- 0 Pydantic deprecation warnings

**Code Quality:**

- All imports work correctly (verified via Python import test)
- Models properly exported from ai_qa package
- Follows established patterns from Stories 1.2 and 1.3
- Type hints complete (Pydantic validation ensures correctness)

---

## File List

**New files created:**
- `src/ai_qa/models.py` (81 lines) — StageResult and AgentMessage models with Pydantic v2
- `src/ai_qa/constants.py` (75 lines) — project-wide constants (agents, stages, message types, thresholds, timeouts)
- `tests/test_models.py` (283 lines) — 26 comprehensive test cases for both models

**Modified files:**
- `src/ai_qa/__init__.py` — added exports for StageResult, AgentMessage, and exceptions

---

## Review Findings

Reviewed on 2026-04-09 via adversarial code review (Blind Hunter + Edge Case Hunter + Acceptance Auditor).

**6 issues fixed during review** (committed in `8f03b80`):

- Literal types for `sender` and `message_type` fields
- `@model_validator` for success/errors consistency
- `@field_validator` for timezone-aware timestamp
- `max_length=100` on errors/warnings lists
- field_serializer cleaned up (removed silent None)

**Remaining findings:**

- [x] \[Review]\[Patch] CONFIDENCE_THRESHOLD_LOW = 0.0 misleading — removed constant; "< CONFIDENCE_THRESHOLD_MEDIUM" is the low-confidence boundary. `src/ai_qa/constants.py`

- [x] \[Review]\[Defer] `StageResult.data: Any|None` defeats type safety `src/ai_qa/models.py` — deferred, intentional design per story spec; different stages return different types
- [x] \[Review]\[Defer] `success=False` but `data` populated: no validation `src/ai_qa/models.py` — deferred, intentional; partial results on failure are valid
- [x] \[Review]\[Defer] errors/warnings as plain strings, no structured error codes `src/ai_qa/models.py` — deferred, future enhancement
- [x] \[Review]\[Defer] `ALL_AGENTS`/`ALL_STAGES` constants not enforced as validation `src/ai_qa/constants.py` — deferred, future stories will add validation
- [x] \[Review]\[Defer] Circular import risk if models.py imports exceptions in future `src/ai_qa/__init__.py` — deferred, pre-existing concern, not yet realized

---

## Change Log

- **2026-04-09:** Code review complete — 6 issues fixed, 1 patch pending, 5 deferred
  - Added Literal types for sender and message_type
  - Added model_validator for success/errors consistency
  - Added field_validator for timezone-aware timestamps
  - Added max_length=100 on errors/warnings lists
  - Tests updated to use timezone.utc, 32 tests pass
- **2026-04-08:** Story 1.4 implementation complete - created models.py, constants.py, test_models.py
  - StageResult: validation pipeline stage output wrapper
  - AgentMessage: typed agent-to-frontend communication
  - Constants: 50+ project-wide constants organized by category
  - Tests: 26 test cases, 100% pass rate, no regressions
  - Status: ready-for-dev → review
