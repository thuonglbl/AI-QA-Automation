# Story 3.4: Output Writer Pipeline Stage

**Status:** done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a R&D engineer,
I want a reusable output writer that saves pipeline results to organized folders,
So that all agents use consistent file output with metadata.

## Acceptance Criteria

**Given** a pipeline stage produces output
**When** the output writer saves results
**Then** files are written to the correct workspace subfolder (e.g., `workspace/requirements/`)
**And** each output includes a `metadata.json` with source URL, timestamp, model used, and confidence score
**And** file naming is derived from source content titles using kebab-case
**And** the output directory is configurable (FR13)
**And** partial output from failed stages is not corrupted (NFR13)

---

## Technical Requirements

### Core Functionality

Implement `OutputWriter` pipeline stage in `src/ai_qa/pipelines/output_writer.py`:

- Save string/text output to target files
- Generate and save `metadata.json` alongside each output
- Ensure output naming is safely derived from titles using kebab-case
- Group output logically in subdirectories if necessary
- Avoid corrupting partial output from failed stages (NFR13) (e.g., write to temporary paths first or ensure atomic writes)
- Configurable output directory (FR13) via `__init__` arguments

### Module Structure

```
src/ai_qa/pipelines/
├── __init__.py                 # Add OutputWriter to exports
├── output_writer.py            # NEW: main implementation
```

```
tests/pipelines/
├── __init__.py
├── test_output_writer.py       # NEW: tests for OutputWriter
```

### Key Classes and Interfaces

#### 1. OutputMetadata Pydantic Model (add to `src/ai_qa/pipelines/models.py`)

```python
class OutputMetadata(BaseModel):
    """Metadata accompanying generated files."""

    source_url: str = Field(description="Original source URL")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="ISO 8601 timestamp"
    )
    model: str | None = Field(default=None, description="Model used for generation")
    confidence: float | None = Field(default=None, description="Confidence score")

    model_config = ConfigDict(validate_assignment=True)
```

#### 2. OutputWriter Class

```python
class OutputWriter:
    """Pipeline stage for persisting output and its metadata.
    """

    def __init__(self, output_base_dir: Path) -> None:
        """Initialize writer.

        Args:
            output_base_dir: Base workspace directory (e.g., Path("workspace/requirements"))
        """

    async def write(self, file_name: str, content: str | bytes, metadata: OutputMetadata) -> StageResult:
        """Write a single file and its metadata.

        Args:
            file_name: Target filename (without path)
            content: Content to write
            metadata: Associated metadata

        Returns:
            StageResult with written file paths on success, errors on failure
        """

    def _to_kebab_case(self, text: str) -> str:
        """Convert text to safe kebab-case filename."""
```

### File Names and Path Generation

- Subfolder should be `{output_base_dir}/{kebab_case_title}/`
- Output text is placed in that subfolder.
- Metadata is written to `metadata.json` within the subfolder.
- Ensure safe file names (kebab-case): alphanumeric lowercase, replacing spaces/special characters with hyphens.

### StageResult Contract

```python
# Success
StageResult(
    success=True,
    data={"file_path": str, "metadata_path": str},
    errors=[],
    warnings=[],
    confidence=1.0,
)

# Failure
StageResult(
    success=False,
    data=None,
    errors=["Write failed: <reason>"],
    warnings=[],
    confidence=0.0,
)
```

### Error Handling

- File system write failure → catch `OSError`, return `StageResult(success=False, errors=["..."])`

**Follow project error handling rules:**
- Never raise `Exception` from pipeline stage — always return `StageResult`
- Use `logging` module with appropriate levels (not `print()`)
- Use `logger = logging.getLogger(__name__)` at module level

---

## Dev Agent Guardrails

### ⛔ FORBIDDEN — Anti-Patterns

| Forbidden | Correct Alternative |
|---|---|
| `open()` without `with` | `with open(...)` or `Path.write_text()` / `Path.write_bytes()` |
| `print(...)` anywhere | `logger.debug/info/warning/error(...)` |
| `raise Exception(...)` from stage | Return `StageResult(success=False, errors=[...])` |
| `dict` between stages | Pydantic model (`OutputMetadata`) |
| Modifying existing pipeline stages | Only add to `output_writer.py` and `models.py` |
| `import *` | Explicit named imports |
| Bare `except:` | `except OSError as e:` |

### ✅ REQUIRED — Architecture Compliance

**Import order pattern (enforced by Ruff):**
```python
# Standard library
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Third-party
from pydantic import BaseModel, ConfigDict, Field

# Local
from ai_qa.exceptions import PipelineError
from ai_qa.models import StageResult
from ai_qa.pipelines.models import OutputMetadata
```

**Logging setup (module-level):**
```python
logger = logging.getLogger(__name__)
```

**Atomic writes mechanism**:
To avoid partial output (NFR13), consider writing to temporary files next to the active files and atomic renaming. However, standard Python path operations are acceptable if the structure enforces writing complete contents at once.

---

## Previous Story Intelligence (Stories 3.2, 3.3)

### Established Patterns — Must Follow

- Pydantic models in `pipelines/models.py` use `model_config = ConfigDict(validate_assignment=True)`
- All models implement `to_dict()` → `return self.model_dump(mode="json")` if necessary.
- **Error constants pattern**: Extract repeated error strings to module-level constants.
- Input validation first in every public method.

---

## Project Context Reference

Conforms to general structure:
- Code in `src/ai_qa/pipelines/`.
- Fast validation with Ruff & mypy before pushing.
- Pydantic settings are correctly validated. 
- Ensure file writes respect NFR5 - no data outside the configured paths.

---

## Tasks

- [x] Add `OutputMetadata` Pydantic model to `src/ai_qa/pipelines/models.py`
- [x] Create `src/ai_qa/pipelines/output_writer.py`:
  - [x] Module-level logger
  - [x] `OutputWriter.__init__()` with `output_base_dir: Path`
  - [x] `OutputWriter.write(...) -> StageResult`
  - [x] Atomic internal writing implementations to avoid corruption
  - [x] Kebab case helper function
- [x] Update `src/ai_qa/pipelines/__init__.py` to export `OutputWriter`, `OutputMetadata`
- [x] Create `tests/pipelines/test_output_writer.py` with cases for successful writes, filesystem error handling, atomic write guarantees, and safe naming.
- [x] Run `uv run ruff check src/ tests/` — must pass clean
- [x] Run `uv run mypy src/` — must pass in strict mode
- [x] Run `uv run pytest tests/pipelines/test_output_writer.py -v` — all tests pass

## Dev Agent Record

### Implementation Plan
Followed red-green-refactor cycle.
Implemented `OutputMetadata` with simple timezone validation.
Created `OutputWriter` class with standard `logger`, directory creation, `_to_kebab_case` string normalization, and an atomic write operation sequence (`.tmp` write followed by `replace`) to satisfy NFR13.
Handled OS and unexpected exceptions cleanly by capturing them in the `StageResult` output.

### Completion Notes
✅ Successfully resolved all tasks.
Implemented the output writer pipeline stage using atomic writes to prevent data corruption. Handled timezone-aware metadata writing. Covered tests for string content, binary content, and comprehensive error handling.

## File List

- `src/ai_qa/pipelines/models.py` (Modified)
- `src/ai_qa/pipelines/output_writer.py` (New)
- `src/ai_qa/pipelines/__init__.py` (Modified)
- `tests/pipelines/test_output_writer.py` (New)

---

## Completion Status

Ultimate context engine analysis completed - comprehensive developer guide created.

---

**Story ID:** 3.4
**Story Key:** 3-4-output-writer-pipeline-stage
**Epic:** Epic 3 — Requirements Extraction from Confluence (Agent Bob)
**Depends On:** Story 3.2, 3.3
**Feeds Into:** Story 3.5 (Bob Agent), Epic 4
**Created:** {date}

### Review Findings

- [x] [Review][Patch] Cảnh báo Race Condition trên file tạm (`.tmp`) [src/ai_qa/pipelines/output_writer.py:54]
- [x] [Review][Patch] Nguy cơ lọt Path Traversal (Directory Traversal) từ tên file không qua kiểm duyệt [src/ai_qa/pipelines/output_writer.py:50]
- [x] [Review][Patch] Dọn dẹp (unlink) các file tạm nếu tiến trình Atomic Rename/Replace bị crash [src/ai_qa/pipelines/output_writer.py:65]
