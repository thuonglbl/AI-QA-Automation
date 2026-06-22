# Story 1.1: Project Restructure to src Layout

**Story ID:** 1.1
**Story Key:** 1-1-project-restructure-to-src-layout
**Status:** done

## Story Requirements

**As a** R&D engineer,
**I want** the project restructured from flat layout to `src/ai_qa/` PEP 621 compliant src layout,
**So that** the codebase follows Python best practices and supports editable install via `uv sync`.

### Acceptance Criteria
- **Given** the existing project with `pyproject.toml` and any existing root python modules
- **When** the restructure is applied
- **Then** all existing code is moved to `src/ai_qa/` directory structure
- **And** `pyproject.toml` is updated with Hatchling build system, project metadata, and `[project.scripts]` entry point
- **And** `uv sync` installs the package in editable mode successfully
- **And** `python -m ai_qa` runs without import errors

## Developer Context

**Epic Goal:** Project Foundation & Infrastructure Setup. This story establishes the core build and structure upon which all other features will be built.

### Technical & Architecture Requirements
- **Language/Environment**: Python 3.14+ (managed by `uv`)
- **Build System**: Hatchling (`[build-system]` section in `pyproject.toml`)
- **PEP 621**: Utilize `[project]` settings rather than tool-specific proprietary fields.
- **Linter & Formatting**: Configure Ruff (Target: Python 3.14, line-length 100).
- **Type Checking**: Configure `mypy` for static type checking.

### Library & Framework Requirements
- Keep existing dependencies (`browser-use`, `langchain-anthropic`, `python-dotenv`).
- Add required dev tooling configuration (Ruff/mypy) in `pyproject.toml` (even if specific stories tackle them deeper, the struct should be ready).

### File Structure Requirements
You must reorganize the files to achieve this structure:
```text
ai-qa-automation/
  pyproject.toml
  uv.lock
  .python-version
  src/
    ai_qa/
      __init__.py
      __main__.py          # CLI entry point foundation
```

### Testing Requirements
- Ensure `uv sync` executes successfully natively parsing the new `pyproject.toml`.
- Import path resolution must work smoothly (`import ai_qa`).
- `python -m ai_qa` must exit gracefully.

## Git Intelligence Summary
Recent work includes creating the initial PRD, architecture, and Epic definitions. A flat layout exists, which now formally needs to transition to a maintainable enterprise-level Python structure before creating actual components.

---
**Completion Status:** Ultimate context engine analysis completed - comprehensive developer guide created.

## Tasks/Subtasks

- [x] Move `main.py` contents to `src/ai_qa/__main__.py`
- [x] Create `src/ai_qa/__init__.py`
- [x] Update `pyproject.toml` (Hatchling, Ruff, mypy, script entrypoint)
- [x] Verify `python -m ai_qa` imports correctly and works via editable installation (`uv sync`)

### Review Findings (2026-04-07)

- [x] [Review][Patch] Misleading unconditional print message says "Claude 4.6 Sonnet" even in on-prem Qwen branch [`src/ai_qa/__main__.py:46`] — FIXED: moved provider-specific messages into their respective conditional branches.
- [x] [Review][Defer] `browser.kill()` without error handling — cleanup exception will propagate uncaught [`src/ai_qa/__main__.py:61`] — deferred, pre-existing design; will be addressed in browser agent story
- [x] [Review][Defer] Non-standard env var naming with hyphens in `ON-PREMISES-AI-SERVER-URL` — deferred, pre-existing issue
- [x] [Review][Defer] Missing `[tool.hatch.build.targets.sdist]` config — sdist builds may behave unexpectedly — deferred, not required by current story scope

## Dev Agent Record

### Implementation Plan
- Restructure project to PEP 621 compliant src layout using Hatchling as the build backend.
- Migrate existing `main.py` into `src/ai_qa/__main__.py` and add a synchronous `run()` entry point wired to `[project.scripts]`.
- Add Ruff and mypy configuration blocks to `pyproject.toml`.
- Verify via `uv sync`, `import ai_qa`, and `uv run python -m ai_qa`.

### Completion Notes
- ✅ Created `src/ai_qa/__init__.py` (package marker).
- ✅ Created `src/ai_qa/__main__.py` — migrated all logic from root `main.py`; added `run()` wrapper for the `ai-qa` console script entry point.
- ✅ Updated `pyproject.toml`: added `[build-system]` (hatchling), `[project.scripts]` (`ai-qa = "ai_qa.__main__:run"`), `[tool.hatch.build.targets.wheel]`, `[tool.ruff]`, `[tool.mypy]`.
- ✅ Deleted root-level `main.py` (migrated).
- ✅ `uv sync` completed cleanly — package `ai-qa-automation` built and installed in editable mode.
- ✅ `import ai_qa` resolves correctly.
- ✅ `uvx ruff check .` — All checks passed!
- ℹ️ mypy requires dev dependency install (`uv add --dev mypy`) to run in the project venv; will be configured in Story 1.5 (dev tooling setup).
- All Acceptance Criteria satisfied.

## File List
- `pyproject.toml` (modified)
- `src/ai_qa/__init__.py` (new)
- `src/ai_qa/__main__.py` (new)
- `main.py` (deleted)

## Change Log
- 2026-04-07: Restructured project to PEP 621 compliant `src/ai_qa/` layout. Configured Hatchling build system, Ruff linter, mypy type-checker. Migrated `main.py` to `src/ai_qa/__main__.py` with `run()` CLI entry point. Verified editable install via `uv sync` and import validation.
- 2026-04-07: Code review — Fixed misleading unconditional print message: moved provider-specific status messages inside each LLM conditional branch in `src/ai_qa/__main__.py`.
