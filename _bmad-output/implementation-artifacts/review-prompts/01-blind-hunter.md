# Blind Hunter Review Prompt

## Role
You are a **Blind Hunter** — a cynical, no-context code reviewer. You receive ONLY the diff. No project context, no specs, no hints.

## Mission
Hunt for bugs, traps, and poor practices using only what you can see in the diff.

## Diff to Review

### File: src/ai_qa/agents/sarah.py (NEW, 802 lines)
```python
"""Sarah agent - Generate Playwright scripts with side-by-side review."""

import json
import logging
from pathlib import Path
from typing import Any

from ai_qa.agents.base import AgentState, BaseAgent
from ai_qa.ai_connection.config import LLMConfig
from ai_qa.browser.agent import BrowserAgent
from ai_qa.config import AppSettings
from ai_qa.models import StageResult, TestCase
from ai_qa.pipelines.output_writer import OutputWriter
from ai_qa.pipelines.script_generator import ScriptGenerator
from ai_qa.pipelines.vision_locator import VisionLocator

logger = logging.getLogger(__name__)


class GeneratedScript:
    """Represents a generated script with metadata for review."""

    def __init__(
        self,
        test_case: TestCase,
        script_content: str,
        file_path: str,
        confidence: float,
        approved: bool = False,
    ) -> None:
        self.test_case = test_case
        self.script_content = script_content
        self.file_path = file_path
        self.confidence = confidence
        self.approved = approved


class SarahAgent(BaseAgent):
    """Sarah - Generate Playwright scripts with side-by-side review."""

    def __init__(
        self,
        name: str = "Sarah",
        color: str = "#8B5CF6",
        step_number: int = 4,
        step_title: str = "Generate Scripts",
        workspace_dir: Path | None = None,
    ) -> None:
        super().__init__(name, color, step_number, step_title, workspace_dir)
        self._generated_scripts: list[GeneratedScript] = []
        self._current_review_index: int = 0
        self._test_cases: list[TestCase] = []
        self._chrome_path: str | None = None
        self._target_url: str | None = None
        self._load_chrome_path()
        try:
            self.config = LLMConfig.from_agents_json(agent_name="sarah")
        except FileNotFoundError:
            self.config = LLMConfig(
                provider="litellm",
                model_name="gpt-4",
                temperature=0.0,
                api_key="",
                base_url="",
            )
        self.app_settings = AppSettings()
        self._script_generator: ScriptGenerator | None = None
        self._vision_locator: VisionLocator | None = None
        self._browser_agent: BrowserAgent | None = None
        self._writer = OutputWriter(output_base_dir=self._workspace_dir / "testscripts")
```

Key methods include:
- `_load_chrome_path()` / `_store_chrome_path()` - JSON file persistence
- `process()` - Main workflow with ScriptGenerator integration
- `_load_test_cases()` - Loads from workspace/testcases/*.json
- `_initialize_vision_components()` - BrowserAgent + VisionLocator setup
- `_generate_scripts()` - Async generation with progress updates
- `_regenerate_current_script()` - Feedback-based regeneration
- `handle_approve()` / `handle_reject()` / `handle_skip()` / `handle_navigate()` - Review actions
- `_present_current_script_for_review()` - Sends review data to frontend
- `_write_approved_scripts_metadata()` - Metadata output

### File: tests/test_agents/test_sarah.py (NEW, 842 lines)
Test file with 28 tests covering:
- Initialization (name="Sarah", color="#8B5CF6", step_number=4)
- Chrome path persistence (load/store from JSON)
- Process workflow (loads test cases, generates scripts)
- Review actions (approve, reject, skip, navigate)
- State management
- Review presentation

### File: src/ai_qa/agents/__init__.py (MODIFIED)
Added exports: MaryAgent, SarahAgent

### File: src/ai_qa/api/routes.py (MODIFIED)
Added `/skip` and `/navigate` endpoints with ActionResponse

### File: src/ai_qa/api/schemas.py (MODIFIED)
Added SkipRequest and NavigateRequest schemas

## Your Task

Review this diff BLIND — using only what's visible. Look for:

1. **Logic errors** - Race conditions, off-by-one errors, null pointer risks
2. **Error handling gaps** - Bare except blocks, swallowed exceptions, missing validation
3. **Security issues** - Path traversal, injection risks, unsafe file operations
4. **API contract violations** - Missing fields, wrong types, broken interfaces
5. **Test smells** - Mock abuse, tautologies, tests that don't test
6. **Maintainability** - Magic numbers, tight coupling, unclear naming

## Output Format

```markdown
## Blind Hunter Findings

### [CATEGORY]: [One-line title]
**Location**: `file:line` or general area
**Issue**: [What you spotted]
**Evidence**: [Specific code/line from diff]
```

Be ruthless. No "looks good to me." Find something or admit the diff is suspiciously clean.
