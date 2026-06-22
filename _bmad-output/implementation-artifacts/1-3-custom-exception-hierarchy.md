# Story 1.3: Custom Exception Hierarchy

**Story ID:** 1.3
**Story Key:** 1-3-custom-exception-hierarchy
**Epic:** 1 — Project Foundation & Infrastructure Setup
**Status:** done
**Date Created:** 2026-04-08

---

## User Story

**As a** R&D engineer,
**I want** a structured exception hierarchy in `src/ai_qa/exceptions.py`,
**So that** all pipeline components use consistent, meaningful error types instead of generic exceptions.

---

## Acceptance Criteria

**Given** the exception module is created
**When** any pipeline component encounters an error
**Then** it raises a custom exception from the hierarchy (e.g., `LLMError`, `MCPError`, `BrowserError`, `ConfigError`, `PipelineError`)
**And** all custom exceptions inherit from a base `AIQAError`
**And** each exception includes a user-friendly message and optional technical details
**And** generic `Exception` or bare `except:` are forbidden (enforced by code convention)

---

## Developer Context

### Current State (from Stories 1.1 and 1.2)

The project has a working `src/ai_qa/` layout with:
- `src/ai_qa/__init__.py` — package marker
- `src/ai_qa/config.py` — `AppSettings` class with Pydantic Settings
- `src/ai_qa/__main__.py` — CLI entry point using `AppSettings`
- `tests/test_config.py` — 5 passing tests
- `tests/__init__.py` — package marker

**Critical: `__main__.py` currently raises raw `ValueError` for missing config:**
```python
raise ValueError(
    "No AI provider configured. Set ANTHROPIC_API_KEY, or both "
    "ON_PREMISES_AI_SERVER_URL and ON_PREMISES_AI_SERVER_KEY "
    "in .env, config.yaml, or environment variables."
)
```

This story creates `exceptions.py` and updates `__main__.py` to raise `ConfigError` instead.

---

## Technical Requirements

### 1. No New Dependencies

This story uses **pure Python stdlib only** — no new packages to add to `pyproject.toml`. No `uv sync` needed.

### 2. Create `src/ai_qa/exceptions.py`

**File location:** `src/ai_qa/exceptions.py` (as specified in architecture — single hierarchy file)

```python
"""Custom exception hierarchy for AI QA Automation.

All exceptions inherit from AIQAError. Pipeline components MUST raise
exceptions from this module — never generic Exception or bare except:.

Hierarchy:
    AIQAError (base)
    ├── ConfigError      — configuration invalid or missing
    ├── LLMError         — LLM call failure (timeout, API error, parsing)
    ├── MCPError         — MCP server call failure
    ├── BrowserError     — browser automation failure
    └── PipelineError    — pipeline orchestration failure
"""


class AIQAError(Exception):
    """Base exception for all AI QA Automation errors.

    Args:
        message: User-friendly description of what went wrong.
        details: Optional technical details for debugging (not shown to end users).
    """

    def __init__(self, message: str, details: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def __repr__(self) -> str:
        if self.details:
            return f"{type(self).__name__}(message={self.message!r}, details={self.details!r})"
        return f"{type(self).__name__}(message={self.message!r})"


class ConfigError(AIQAError):
    """Raised when configuration is invalid or required values are missing.

    Examples: missing API key, invalid URL format, conflicting settings.
    """


class LLMError(AIQAError):
    """Raised when an LLM call fails.

    Examples: API timeout, rate limit exceeded, malformed response, max retries exceeded.
    """


class MCPError(AIQAError):
    """Raised when an MCP server call fails.

    Examples: connection refused, tool call error, unexpected response schema.
    """


class BrowserError(AIQAError):
    """Raised when browser automation fails.

    Examples: page load timeout, element not found, browser crash.
    """


class PipelineError(AIQAError):
    """Raised when pipeline orchestration fails.

    Examples: stage dependency missing, invalid stage result, pipeline aborted.
    """
```

**Design decisions:**
- `AIQAError.__init__` stores `message` as attribute AND passes it to `Exception.__init__` (so `str(err)` and `err.message` both work)
- `details` is optional — for technical info never shown to end users
- Child classes have no `__init__` override — they inherit `AIQAError.__init__` cleanly
- Module docstring documents the hierarchy for LLM agents reading the file

### 3. Update `src/ai_qa/__main__.py`

Replace the raw `ValueError` with `ConfigError`:

```python
# ADD import at top (local section):
from ai_qa.exceptions import ConfigError

# REPLACE in main():
# OLD:
#     raise ValueError(
#         "No AI provider configured. Set ANTHROPIC_API_KEY, or both "
#         "ON_PREMISES_AI_SERVER_URL and ON_PREMISES_AI_SERVER_KEY "
#         "in .env, config.yaml, or environment variables."
#     )
#
# NEW:
raise ConfigError(
    "No AI provider configured.",
    details=(
        "Set ANTHROPIC_API_KEY, or both ON_PREMISES_AI_SERVER_URL and "
        "ON_PREMISES_AI_SERVER_KEY in .env, config.yaml, or environment variables."
    ),
)
```

**Note:** Keep the `print()` statements in `__main__.py` — they are acceptable per Story 1.2 anti-pattern note: "print() statements for provider selection UI are acceptable until agent refactor in Epic 2."

### 4. Create `tests/test_exceptions.py`

```python
"""Tests for the custom exception hierarchy in src/ai_qa/exceptions.py."""
import pytest

from ai_qa.exceptions import (
    AIQAError,
    BrowserError,
    ConfigError,
    LLMError,
    MCPError,
    PipelineError,
)

# --- Inheritance tests ---


def test_all_exceptions_inherit_from_aiqa_error() -> None:
    """All custom exceptions must inherit from AIQAError."""
    for exc_class in (ConfigError, LLMError, MCPError, BrowserError, PipelineError):
        assert issubclass(exc_class, AIQAError), f"{exc_class.__name__} must inherit AIQAError"


def test_aiqa_error_inherits_from_exception() -> None:
    """AIQAError must be catchable as a standard Exception."""
    assert issubclass(AIQAError, Exception)


# --- Constructor tests ---


def test_aiqa_error_message_only() -> None:
    """AIQAError stores message attribute; details defaults to None."""
    err = AIQAError("Something went wrong")
    assert err.message == "Something went wrong"
    assert err.details is None
    assert str(err) == "Something went wrong"


def test_aiqa_error_with_details() -> None:
    """AIQAError stores both message and details when provided."""
    err = AIQAError("Something went wrong", details="Technical context here")
    assert err.message == "Something went wrong"
    assert err.details == "Technical context here"


def test_child_exception_inherits_constructor() -> None:
    """Child exceptions support message + details via inherited constructor."""
    err = LLMError("LLM call failed", details="HTTP 429 rate limited")
    assert err.message == "LLM call failed"
    assert err.details == "HTTP 429 rate limited"
    assert str(err) == "LLM call failed"


# --- Raise and catch tests ---


def test_can_raise_and_catch_by_specific_type() -> None:
    """Each exception type can be raised and caught by its specific class."""
    with pytest.raises(ConfigError):
        raise ConfigError("Bad config")

    with pytest.raises(LLMError):
        raise LLMError("LLM failed")

    with pytest.raises(MCPError):
        raise MCPError("MCP failed")

    with pytest.raises(BrowserError):
        raise BrowserError("Browser crashed")

    with pytest.raises(PipelineError):
        raise PipelineError("Pipeline aborted")


def test_can_catch_specific_as_aiqa_error() -> None:
    """Specific exceptions can be caught by AIQAError base class."""
    with pytest.raises(AIQAError):
        raise LLMError("caught as base")

    with pytest.raises(AIQAError):
        raise ConfigError("caught as base")


def test_can_catch_specific_as_exception() -> None:
    """All custom exceptions are catchable as standard Exception."""
    with pytest.raises(Exception):
        raise PipelineError("caught as Exception")


# --- repr tests ---


def test_repr_without_details() -> None:
    """__repr__ shows class name and message when no details."""
    err = ConfigError("missing key")
    assert "ConfigError" in repr(err)
    assert "missing key" in repr(err)


def test_repr_with_details() -> None:
    """__repr__ includes details when provided."""
    err = MCPError("connection failed", details="refused on port 8080")
    r = repr(err)
    assert "MCPError" in r
    assert "connection failed" in r
    assert "refused on port 8080" in r
```

Run tests with: `uv run pytest tests/test_exceptions.py -v`

---

## Architecture Compliance

### File Locations (MUST follow exactly)

| File | Location | Action |
|------|----------|--------|
| `exceptions.py` | `src/ai_qa/exceptions.py` | **CREATE** |
| `test_exceptions.py` | `tests/test_exceptions.py` | **CREATE** |
| `__main__.py` | `src/ai_qa/__main__.py` | **MODIFY** (ConfigError import + raise) |

**Do NOT create** `src/ai_qa/ai_connection/exceptions.py` — that file belongs to the LLM abstraction layer in Epic 4 (Story 4.1). Story 1.3 scope is ONLY `src/ai_qa/exceptions.py`.

### Module Dependency Rule (MUST follow)

```
exceptions.py → depends on NOTHING (no local imports)
All other modules → may import from exceptions
```

The `exceptions.py` file must have **zero local imports** (`from ai_qa.*`). Only stdlib if needed (none needed for this story).

### Naming Conventions (MUST follow)

- Base class: `AIQAError` (PascalCase, `Error` suffix per Python convention)
- Child classes: `ConfigError`, `LLMError`, `MCPError`, `BrowserError`, `PipelineError`
- Module name: `exceptions` (snake_case)
- Attribute names: `message`, `details` (snake_case)

### Import Pattern in Other Modules (MUST use)

```python
# Standard library
# (nothing needed for exceptions module itself)

# Third-party
# (nothing)

# Local
from ai_qa.exceptions import ConfigError  # or whichever exception needed
```

### Anti-Patterns (FORBIDDEN — enforced in this story and all future stories)

- `raise Exception(...)` — use a specific subclass instead
- `raise ValueError(...)` for config issues — use `ConfigError`
- `except Exception:` without re-raise — forbidden by architecture
- `except:` (bare) — forbidden by architecture
- Importing `from ai_qa.config` or any other local module inside `exceptions.py` — circular dependency risk

---

## Previous Story Intelligence (Stories 1.1 and 1.2)

### Story 1.2 Learnings (directly applicable)

- **Dev tooling:** `uv run pytest tests/ -v` runs all tests; `uvx ruff check src/ tests/` for linting
- **Python 3.14 union syntax:** Use `str | None` not `Optional[str]` (per Ruff py314 target)
- **Import order enforced by Ruff:** stdlib → third-party → local (isort rules)
- **mypy strict mode:** All functions need type hints; `None` return must be explicit `-> None`
- **str_strip_whitespace:** Config has this enabled — relevant if you ever process config values, but not needed in exceptions.py
- **Project root:** `_PROJECT_ROOT = Path(__file__).parents[2]` pattern established — NOT needed in exceptions.py
- **`__main__.py` has `raise ValueError`** at line 36 — THIS IS THE TARGET for ConfigError replacement

### Story 1.1 Learnings

- `browser.kill()` deferred error handling — not in scope here but BrowserError is prepared for Epic 5
- Pre-existing hyphenated env vars standardized in 1.2 — fully resolved

### Deferred Items NOT in Scope for This Story

From `deferred-work.md`:
- `file_secret_settings` dropped from source chain — irrelevant to exceptions
- Missing negative temperature boundary test — deferred to Story 1.5
- URL format validation — deferred to Story 1.5
- `reload(cfg)` test isolation — deferred to Story 1.5
- Malformed YAML parse error untested — deferred to Story 1.5

---

## Git Intelligence (Recent Commits)

- `95aef72` — Story 1.2: Config system, `src/ai_qa/config.py` created, `tests/test_config.py` with 5 tests
- `e319756` — Story 1.1: `src/ai_qa/` layout, `__main__.py` with browser-use agent
- Current `pyproject.toml` dev deps: `pytest>=9.0.3` (sufficient for this story — no new dev deps needed)
- Test pattern established: `tests/test_config.py` uses `monkeypatch`, `tmp_path`, `reload` — follow same pattern for `tests/test_exceptions.py` (though simpler — no env/file isolation needed)

---

## Tasks / Subtasks

- [x] Create `src/ai_qa/exceptions.py` with `AIQAError` base class and 5 child exception classes (AC: 1, 2, 3, 4)
- [x] Update `src/ai_qa/__main__.py`: add `from ai_qa.exceptions import ConfigError` import and replace `raise ValueError(...)` with `raise ConfigError(...)` (AC: 1)
- [x] Create `tests/test_exceptions.py` with comprehensive tests (AC: 1, 2, 3, 4)
- [x] Run `uv run pytest tests/test_exceptions.py -v` — all tests pass
- [x] Run `uv run pytest -v` (full suite including test_config.py) — no regressions
- [x] Run `uvx ruff check src/ tests/` — no issues

### Review Findings

- [x] [Review][Patch] Test coverage: add test for ConfigError usage pattern from `__main__.py` [tests/test_exceptions.py] — RESOLVED
- [x] [Review][Defer] AppSettings validation error handling not caught as ConfigError [src/ai_qa/__main__.py:10] — deferred, pre-existing issue (AppSettings from Story 1.2, outside scope)

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

No issues encountered. Implementation straightforward per spec.

### Completion Notes List

- Created `src/ai_qa/exceptions.py` with `AIQAError` base class and 5 child classes (`ConfigError`, `LLMError`, `MCPError`, `BrowserError`, `PipelineError`)
- Updated `src/ai_qa/__main__.py`: replaced `raise ValueError(...)` with `raise ConfigError(...)` with split message/details
- Created `tests/test_exceptions.py` with 10 tests covering inheritance, constructor, raise/catch, and repr behavior
- All 10 new tests pass; all 5 existing `test_config.py` tests continue to pass (no regressions)
- `uvx ruff check src/ tests/` — no issues; Python 3.14 union syntax (`str | None`) used correctly
- `exceptions.py` has zero local imports, satisfying the module dependency rule
- Code review completed: Acceptance Auditor confirmed all 5 ACs met, all 8 technical requirements satisfied
- Review patch applied: added `test_config_error_usage_pattern()` to validate real-world usage from `__main__.py`
- Final test results: 16/16 pass (5 config + 11 exceptions) — no regressions

### File List

- `src/ai_qa/exceptions.py` (created)
- `src/ai_qa/__main__.py` (modified — ConfigError import + raise replacement)
- `tests/test_exceptions.py` (created)

### Change Log

- 2026-04-08: Story 1.3 implemented — created custom exception hierarchy (`AIQAError` + 5 subclasses), updated `__main__.py` to use `ConfigError`, added 10 comprehensive tests. All ACs satisfied.
