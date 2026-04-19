# Story 1.2: Configuration System with Pydantic Settings

**Story ID:** 1.2
**Story Key:** 1-2-configuration-system-with-pydantic-settings
**Epic:** 1 — Project Foundation & Infrastructure Setup
**Status:** done
**Date Created:** 2026-04-08

---

## User Story

**As a** R&D engineer,
**I want** a centralized configuration system using Pydantic Settings,
**So that** all pipeline components read validated config from `.env` + `config.yaml` with env var overrides.

---

## Acceptance Criteria

**Given** a fresh project setup
**When** the engineer creates `.env` and `config.yaml` files from example templates
**Then** `AppSettings` class loads and validates all config values at startup
**And** missing required values cause immediate failure with actionable error messages (NFR15)
**And** `.env.example` and `config.example.yaml` templates are committed to version control
**And** `.env` and `config.yaml` are gitignored (NFR6)
**And** environment variable overrides take precedence over file values
**And** LLM parameters (model selection, temperature) are configurable (FR15)
**And** API keys and MCP server URL are configurable via `.env` (FR14)

---

## Developer Context

### Current State (from Story 1.1)

The project has a working `src/ai_qa/` layout with:
- `src/ai_qa/__init__.py` — package marker
- `src/ai_qa/__main__.py` — CLI entry point using raw `os.getenv()` + `python-dotenv`

**Critical: `__main__.py` currently uses these env vars directly:**
```python
load_dotenv()
anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
on_prem_url   = os.getenv("ON-PREMISES-AI-SERVER-URL", "").strip()  # ⚠️ non-standard (hyphens)
on_prem_key   = os.getenv("ON-PREMISES-AI-SERVER-KEY", "").strip()  # ⚠️ non-standard (hyphens)
```

This story creates `AppSettings` and updates `__main__.py` to use it. The non-standard hyphenated env var names are **standardized in this story** to UPPER_SNAKE_CASE (per architecture naming conventions).

---

## Technical Requirements

### 1. New Dependency: `pydantic-settings`

Add to `pyproject.toml` `[project.dependencies]`:
```toml
"pydantic-settings>=2.4.0",   # >=2.4.0 required for YamlConfigSettingsSource
"pyyaml>=6.0",                 # Required by YamlConfigSettingsSource
```

**Remove** `python-dotenv` from `[project.dependencies]` — pydantic-settings handles `.env` loading natively via `model_config = SettingsConfigDict(env_file=".env")`.

Run `uv sync` after modifying pyproject.toml.

### 2. Create `src/ai_qa/config.py`

**File location:** `src/ai_qa/config.py` (as specified in architecture)

```python
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource, PydanticBaseSettingsSource
from typing import Any, Type

_CONFIG_YAML = Path("config.yaml")

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- LLM Provider (FR14, FR15) ---
    anthropic_api_key: str = Field(default="", description="Claude API key (optional if using on-prem)")
    on_premises_ai_server_url: str = Field(default="", description="On-prem LiteLLM proxy base URL")
    on_premises_ai_server_key: str = Field(default="", description="On-prem AI server API key")

    # --- LLM Parameters (FR15) ---
    llm_model: str = Field(default="claude-sonnet-4-6", description="LLM model identifier")
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="LLM sampling temperature")

    # --- MCP (FR14) ---
    mcp_server_url: str = Field(default="", description="MCP server URL for Confluence/Jira integration")
    mcp_server_key: str = Field(default="", description="MCP server API key")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
            dotenv_settings,
        ]
        if _CONFIG_YAML.exists():
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=_CONFIG_YAML))
        return tuple(sources)
```

**Priority order (highest → lowest):** init_settings → env vars → .env file → config.yaml

This means env vars override .env which overrides config.yaml. This satisfies the AC "environment variable overrides take precedence over file values."

### 3. Update `src/ai_qa/__main__.py`

Replace all raw `os.getenv()` + `load_dotenv()` calls with `AppSettings`:

```python
# REMOVE these imports
import os
from dotenv import load_dotenv

# ADD this import
from ai_qa.config import AppSettings

# REPLACE in main():
# OLD:
#   load_dotenv()
#   anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
#   on_prem_url   = os.getenv("ON-PREMISES-AI-SERVER-URL", "").strip()
#   on_prem_key   = os.getenv("ON-PREMISES-AI-SERVER-KEY", "").strip()
#
# NEW:
settings = AppSettings()
anthropic_key = settings.anthropic_api_key
on_prem_url   = settings.on_premises_ai_server_url
on_prem_key   = settings.on_premises_ai_server_key
llm_model     = settings.llm_model
llm_temperature = settings.llm_temperature
```

Also replace hardcoded `model="claude-sonnet-4-6"` and `temperature=0.0` with `settings.llm_model` and `settings.llm_temperature`.

### 4. Create `.env.example` (project root)

```dotenv
# AI Provider (set ONE of these groups)

# Option A: Claude API
ANTHROPIC_API_KEY=sk-ant-...

# Option B: On-Premises LiteLLM Server
ON_PREMISES_AI_SERVER_URL=https://your-litellm-server.example.com
ON_PREMISES_AI_SERVER_KEY=your-api-key

# MCP Integration
MCP_SERVER_URL=https://your-mcp-server.example.com
MCP_SERVER_KEY=your-mcp-key
```

### 5. Create `config.example.yaml` (project root)

```yaml
# LLM parameters (can be overridden by env vars)
llm_model: "claude-sonnet-4-6"
llm_temperature: 0.0
```

### 6. Update `.gitignore`

Add `config.yaml` to `.gitignore`. Current `.gitignore` already includes `.env` but NOT `config.yaml`.

Append to `.gitignore`:
```
config.yaml
```

### 7. Create `tests/test_config.py`

**Note:** Full test infrastructure (`tests/conftest.py`, pytest-cov, pre-commit) is set up in Story 1.5. For now, create the `tests/` directory and `tests/test_config.py`. You do NOT need `conftest.py` for these tests (no shared fixtures needed yet).

Create `tests/__init__.py` (empty).

```python
# tests/test_config.py
from pathlib import Path
import pytest
from pydantic import ValidationError


def test_appsettings_loads_with_defaults(tmp_path, monkeypatch):
    """AppSettings initializes with defaults when no .env or config.yaml present."""
    monkeypatch.chdir(tmp_path)  # isolate from project .env/config.yaml
    from ai_qa.config import AppSettings
    settings = AppSettings()
    assert settings.llm_model == "claude-sonnet-4-6"
    assert settings.llm_temperature == 0.0


def test_appsettings_env_var_overrides_default(monkeypatch):
    """Env vars override default values."""
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.5")
    from importlib import reload
    import ai_qa.config as cfg
    reload(cfg)
    settings = cfg.AppSettings()
    assert settings.llm_model == "gpt-4o"
    assert settings.llm_temperature == 0.5


def test_appsettings_temperature_validation(monkeypatch):
    """Temperature outside [0.0, 2.0] raises ValidationError."""
    monkeypatch.setenv("LLM_TEMPERATURE", "3.0")
    from importlib import reload
    import ai_qa.config as cfg
    reload(cfg)
    with pytest.raises(ValidationError):
        cfg.AppSettings()


def test_appsettings_yaml_override(tmp_path, monkeypatch):
    """config.yaml values are loaded when file exists."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("llm_model: custom-model\n")
    from importlib import reload
    import ai_qa.config as cfg
    reload(cfg)
    settings = cfg.AppSettings()
    assert settings.llm_model == "custom-model"
```

Run tests with: `uv run pytest tests/test_config.py -v`

---

## Architecture Compliance

### File Locations (MUST follow exactly)

| File | Location | Status |
|------|----------|--------|
| `config.py` | `src/ai_qa/config.py` | **CREATE** |
| `.env.example` | `.env.example` (project root) | **CREATE** |
| `config.example.yaml` | `config.example.yaml` (project root) | **CREATE** |
| `config.yaml` | gitignored, NOT committed | **ENSURE in .gitignore** |
| `.env` | gitignored, already ignored | no change |
| `tests/test_config.py` | `tests/test_config.py` | **CREATE** |
| `tests/__init__.py` | `tests/__init__.py` | **CREATE** |

### Naming Conventions (MUST follow)

- Env var names: `UPPER_SNAKE_CASE` — use `ANTHROPIC_API_KEY`, `ON_PREMISES_AI_SERVER_URL`, `ON_PREMISES_AI_SERVER_KEY` (fix the non-standard hyphenated names from old code)
- YAML config keys: `snake_case` — `llm_model`, `llm_temperature`
- Class name: `AppSettings` (PascalCase)
- Module name: `config` (snake_case)

### Import Pattern (MUST use this order)

```python
# Standard library
from pathlib import Path
from typing import Any, Type

# Third-party
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource, PydanticBaseSettingsSource

# Local (if any)
```

### Anti-Patterns (FORBIDDEN)

- Do NOT use `python-dotenv` (`load_dotenv()`) anywhere after this story — pydantic-settings handles it
- Do NOT hardcode any API keys, URLs, or model names in source files
- Do NOT use `print()` — use `logging` (but for this story, the `__main__.py` print statements for provider selection UI are acceptable until agent refactor in Epic 2)
- Do NOT store secrets in `config.example.yaml` — only non-secret defaults

---

## Previous Story Intelligence (Story 1.1)

- **Deferred issue:** `ON-PREMISES-AI-SERVER-URL` and `ON-PREMISES-AI-SERVER-KEY` used hyphens in env var names — **FIX in this story** by standardizing to `ON_PREMISES_AI_SERVER_URL` / `ON_PREMISES_AI_SERVER_KEY` in `AppSettings` field definitions (pydantic-settings maps env var names to field names automatically via case-insensitive snake_case matching)
- **Deferred issue:** `browser.kill()` without error handling — NOT in scope for this story
- `uv sync` works correctly; use it after modifying `pyproject.toml`
- `uvx ruff check .` must pass after implementation — run before marking done
- mypy strict mode is configured but `uv add --dev mypy` not yet run (will be in Story 1.5)
- pyproject.toml uses Hatchling, Ruff (py312, line-length 100), mypy (strict)

---

## Git Intelligence (Recent Commits)

- `e319756` — created `src/ai_qa/__init__.py` + `__main__.py`, updated `pyproject.toml` with Hatchling
- Current `pyproject.toml` dependencies: `browser-use>=0.12.5`, `langchain-anthropic>=1.3.1`, `python-dotenv>=1.2.1`
- **This story removes `python-dotenv` and adds `pydantic-settings>=2.4.0` + `pyyaml>=6.0`**

---

## Tasks / Subtasks

- [x] Add `pydantic-settings>=2.4.0` and `pyyaml>=6.0` to `pyproject.toml`, remove `python-dotenv`
- [x] Run `uv sync` to install new dependencies
- [x] Create `src/ai_qa/config.py` with `AppSettings` class
- [x] Create `.env.example` at project root
- [x] Create `config.example.yaml` at project root
- [x] Add `config.yaml` to `.gitignore`
- [x] Update `src/ai_qa/__main__.py` to use `AppSettings` (remove `os.getenv` + `load_dotenv`)
- [x] Create `tests/__init__.py` and `tests/test_config.py`
- [x] Run `uv run pytest tests/test_config.py -v` — all tests pass
- [x] Run `uvx ruff check src/ tests/` — no issues
- [x] Verify `uv run python -m ai_qa` still works (does not crash on import)

### Review Findings

**Decision Needed:**
- [x] [Review][Decision] CWD-relative `Path("config.yaml")` — Fixed: anchored to `__file__` via `_PROJECT_ROOT = Path(__file__).parents[2]`. Decision: A (anchor to project root)
- [x] [Review][Decision] No startup validation for provider credentials — Decision: B (keep validation in `__main__.py` by design; AppSettings is a pure config loader)

**Patch:**
- [x] [Review][Patch] On-prem model hardcoded, ignores `settings.llm_model` — Fixed: `model=llm_model` [src/ai_qa/__main__.py:30]
- [x] [Review][Patch] `test_appsettings_env_var_overrides_default` lacks CWD isolation — Fixed: added `monkeypatch.chdir(tmp_path)` [tests/test_config.py:22]
- [x] [Review][Patch] Whitespace-only URL values pass truthiness check — Fixed: `str_strip_whitespace=True` in SettingsConfigDict + added test [src/ai_qa/config.py:22]
- [x] [Review][Patch] `MCP_SERVER_KEY` missing from `.env.example` — Dismissed: already present in file (false positive)
- [x] [Review][Patch] Error message references only `.env` file — Fixed: updated to mention all config sources [src/ai_qa/__main__.py:35]

**Deferred:**
- [x] [Review][Defer] `file_secret_settings` silently dropped from source chain — intentional per spec design, not a future concern yet [src/ai_qa/config.py:43] — deferred, pre-existing
- [x] [Review][Defer] Missing negative temperature boundary test (`-0.1`) — test coverage expansion deferred to Story 1.5 [tests/test_config.py] — deferred, pre-existing
- [x] [Review][Defer] URL format validation (`AnyHttpUrl`) not enforced — basic str field for now, schema validation deferred [src/ai_qa/config.py:28] — deferred, pre-existing
- [x] [Review][Defer] `reload(cfg)` module isolation between tests — proper conftest and fixture isolation deferred to Story 1.5 [tests/test_config.py] — deferred, pre-existing
- [x] [Review][Defer] Malformed YAML parse error untested — error handling test deferred to Story 1.5 [tests/test_config.py] — deferred, pre-existing

---

## Completion Status

**Status:** done
Ultimate context engine analysis completed — comprehensive developer guide created.

---

## Dev Agent Record

### Implementation Plan

Implemented centralized configuration system using `pydantic-settings>=2.4.0` with layered source priority: init_settings → env vars → .env file → config.yaml. Removed `python-dotenv` dependency as pydantic-settings handles `.env` loading natively.

### Completion Notes

- `src/ai_qa/config.py`: `AppSettings` class with `YamlConfigSettingsSource` for optional `config.yaml`, env vars mapped via UPPER_SNAKE_CASE automatically
- `src/ai_qa/__main__.py`: Replaced raw `os.getenv()` + `load_dotenv()` with `AppSettings()`; standardized env var names from hyphenated (`ON-PREMISES-AI-SERVER-URL`) to snake_case (`on_premises_ai_server_url`); `llm_model` and `llm_temperature` now configurable
- `pyproject.toml`: Added `pydantic-settings>=2.4.0`, `pyyaml>=6.0`, removed `python-dotenv`; added `pytest>=9.0.3` as dev dependency via `uv add --dev pytest`
- `tests/test_config.py`: 4 tests covering defaults, env var override, temperature validation, and YAML override — all pass
- ruff check: all checks passed

### File List

- `src/ai_qa/config.py` — CREATED
- `src/ai_qa/__main__.py` — MODIFIED
- `pyproject.toml` — MODIFIED
- `.env.example` — CREATED
- `config.example.yaml` — CREATED
- `.gitignore` — MODIFIED (added config.yaml)
- `tests/__init__.py` — CREATED
- `tests/test_config.py` — CREATED

### Change Log

- 2026-04-08: Story 1.2 implemented — centralized AppSettings config system with pydantic-settings, replaced python-dotenv, standardized env var naming, added 4 passing tests
