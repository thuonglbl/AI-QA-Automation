"""Tests for ScriptGenerator pipeline stage.

Tests the ScriptGenerator class with mocked LLM client.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_qa.config import AppSettings
from ai_qa.exceptions import ScriptGenerationError
from ai_qa.models import StageResult, TestCase, TestCaseStep
from ai_qa.pipelines.script_generator import ScriptGenerator, process


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace directory."""
    workspace = tmp_path / "workspace" / "testscripts"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


@pytest.fixture
def sample_test_case() -> TestCase:
    """Create a sample test case for testing."""
    return TestCase(
        title="User Login Flow",
        preconditions=["User is on login page", "User has valid credentials"],
        steps=[
            TestCaseStep(
                number=1,
                action="Enter username in username field",
                target="username input",
                data="testuser123",
            ),
            TestCaseStep(
                number=2,
                action="Enter password in password field",
                target="password input",
                data="securepassword",
            ),
            TestCaseStep(
                number=3,
                action="Click login button",
                target="login button",
            ),
        ],
        expected_results=[
            "User is redirected to dashboard",
            "Welcome message is displayed",
        ],
        automation_hints=["username field has data-testid='username'"],
        tags=["smoke", "authentication"],
    )


@pytest.fixture
def mock_llm_response() -> str:
    """Sample LLM-generated script content."""
    return '''
def test_user_login_flow(page: Page):
    """Test user login with valid credentials."""
    # Navigate to login page
    page.goto("https://example.com/login")

    # Enter username
    page.get_by_test_id("username").fill("testuser123")

    # Enter password
    page.get_by_label("Password").fill("securepassword")

    # Click login button
    page.get_by_role("button", name="Login").click()

    # Verify dashboard redirect
    expect(page).to_have_url("https://example.com/dashboard")

    # Verify welcome message
    expect(page.get_by_text("Welcome")).to_be_visible()
'''


@pytest.fixture
def mock_llm_client(mock_llm_response: str) -> MagicMock:
    """Create a mock LLM client."""
    client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = mock_llm_response
    client.invoke = MagicMock(return_value=mock_response)
    return client


class TestScriptGeneratorInitialization:
    """Test suite for ScriptGenerator initialization."""

    def test_init_with_valid_config(self, temp_workspace: Path) -> None:
        """Test initialization with valid configuration."""
        config = AppSettings()
        generator = ScriptGenerator(
            output_base_dir=temp_workspace,
            config=config,
        )
        assert generator.output_base_dir == temp_workspace
        assert generator._config == config

    def test_init_with_default_config(self, temp_workspace: Path) -> None:
        """Test initialization without explicit config."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        assert generator.output_base_dir == temp_workspace
        assert isinstance(generator._config, AppSettings)


class TestScriptGeneratorGenerate:
    """Test suite for ScriptGenerator.generate method."""

    async def test_generate_single_test_case(
        self,
        temp_workspace: Path,
        sample_test_case: TestCase,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test generating script for a single test case."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)

        with patch.object(generator, "_get_llm_client", return_value=mock_llm_client):
            result = await generator.generate([sample_test_case])

        assert isinstance(result, StageResult)
        assert result.success is True
        assert result.data is not None
        assert len(result.data) == 1
        assert result.data[0]["test_case_title"] == "User Login Flow"
        assert "script_content" in result.data[0]

    async def test_generate_empty_test_cases(self, temp_workspace: Path) -> None:
        """Test generating with empty test cases list."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        result = await generator.generate([])

        assert isinstance(result, StageResult)
        assert result.success is True
        assert result.data == []
        assert len(result.warnings) == 1
        assert "No test cases provided" in result.warnings[0]
        assert result.confidence == 1.0

    async def test_generate_multiple_test_cases(
        self,
        temp_workspace: Path,
        sample_test_case: TestCase,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test generating scripts for multiple test cases."""
        test_case_2 = TestCase(
            title="Search Functionality",
            steps=[
                TestCaseStep(number=1, action="Type query in search box", target="search input"),
                TestCaseStep(number=2, action="Press Enter", target="search input"),
            ],
            expected_results=["Search results are displayed"],
        )

        generator = ScriptGenerator(output_base_dir=temp_workspace)

        with patch.object(generator, "_get_llm_client", return_value=mock_llm_client):
            result = await generator.generate([sample_test_case, test_case_2])

        assert result.success is True
        assert result.data is not None
        assert len(result.data) == 2

    async def test_generate_with_llm_error(
        self,
        temp_workspace: Path,
        sample_test_case: TestCase,
    ) -> None:
        """Test handling LLM errors during generation."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)

        mock_client = MagicMock()
        mock_client.invoke = MagicMock(side_effect=ScriptGenerationError("LLM error"))

        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            result = await generator.generate([sample_test_case])

        assert result.success is False
        assert len(result.errors) == 1
        assert "Failed to generate script" in result.errors[0]

    async def test_call_llm_with_trace_feeds_real_selectors(
        self,
        temp_workspace: Path,
        sample_test_case: TestCase,
        mock_llm_client: MagicMock,
    ) -> None:
        """Trace translation feeds the REAL recorded selectors to the LLM and
        returns the translated script."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        trace = [
            {"action": "go_to_url", "params": {"url": "https://app.test/login"}, "element": None},
            {
                "action": "click_element_by_index",
                "params": {"index": 5},
                "element": {"tag": "button", "attributes": {"data-testid": "login-submit"}},
            },
        ]

        with patch.object(generator, "_get_llm_client", return_value=mock_llm_client):
            script = await generator._call_llm_with_trace(sample_test_case, trace)

        assert "def test_user_login_flow" in script
        # The real selector from the trace must reach the LLM prompt (proves the
        # verified trace — not invention — drives generation).
        messages = mock_llm_client.invoke.call_args[0][0]
        human_content = messages[1].content
        assert "login-submit" in human_content
        assert "https://app.test/login" in human_content

    async def test_call_llm_with_trace_raises_on_empty(
        self,
        temp_workspace: Path,
        sample_test_case: TestCase,
    ) -> None:
        """Empty LLM output raises ScriptGenerationError (so the caller falls back)."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        mock_client = MagicMock()
        empty = MagicMock()
        empty.content = "   "
        mock_client.invoke = MagicMock(return_value=empty)

        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            with pytest.raises(ScriptGenerationError):
                await generator._call_llm_with_trace(sample_test_case, [])

    async def test_generate_low_confidence_warning(
        self,
        temp_workspace: Path,
        sample_test_case: TestCase,
    ) -> None:
        """Test low confidence warning generation."""
        # Create config with high threshold
        config = AppSettings(confidence_threshold=0.9)
        generator = ScriptGenerator(output_base_dir=temp_workspace, config=config)

        # Mock to return script with low confidence indicators
        low_confidence_script = "page.locator('.btn').click()"  # Uses CSS, no assertions
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = low_confidence_script
        mock_client.invoke = MagicMock(return_value=mock_response)

        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            result = await generator.generate([sample_test_case])

        assert result.success is True
        # Should have warning about low confidence
        assert any("Low confidence" in w for w in result.warnings)


class TestScriptGeneratorFilenameGeneration:
    """Test suite for filename generation."""

    def test_generate_filename_simple_title(self, temp_workspace: Path) -> None:
        """Test filename generation from simple title."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        filename = generator._generate_filename("User Login Flow")
        assert filename == "test_user_login_flow.py"

    def test_generate_filename_with_special_chars(self, temp_workspace: Path) -> None:
        """Test filename generation with special characters."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        filename = generator._generate_filename("Search & Filter: User's Test!!!")
        assert filename == "test_search_filter_user_s_test.py"

    def test_generate_filename_long_title(self, temp_workspace: Path) -> None:
        """Test filename generation truncates long titles."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        long_title = "A" * 200
        filename = generator._generate_filename(long_title)
        assert len(filename) <= 80
        assert filename.startswith("test_")
        assert filename.endswith(".py")

    def test_generate_filename_snake_case(self, temp_workspace: Path) -> None:
        """Test filename is in snake_case."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        filename = generator._generate_filename("Test Case With Multiple Words")
        assert filename == "test_test_case_with_multiple_words.py"
        # "test_case_with_multiple_words" has 4 words connected by 3 underscores
        assert filename.replace("test_", "").replace(".py", "").count("_") == 3

    def test_generate_filename_unicode(self, temp_workspace: Path) -> None:
        """Test Unicode transliteration in filenames."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        # Chinese characters should be transliterated or result in fallback
        filename = generator._generate_filename("测试案例 Login Test")
        assert filename.startswith("test_")
        assert filename.endswith(".py")
        # Should either have transliterated content or fallback name
        name_part = filename.replace("test_", "").replace(".py", "")
        assert len(name_part) > 0 or "unnamed" in filename

    def test_generate_filename_empty_title(self, temp_workspace: Path) -> None:
        """Test empty title produces valid fallback filename."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        filename = generator._generate_filename("")
        assert filename == "test_unnamed_case.py"

    def test_generate_filename_whitespace_only(self, temp_workspace: Path) -> None:
        """Test whitespace-only title produces fallback filename."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        filename = generator._generate_filename("   ")
        assert filename == "test_unnamed_case.py"


class TestScriptGeneratorConfidenceCalculation:
    """Test suite for confidence score calculation."""

    def test_confidence_with_stable_selectors(self, temp_workspace: Path) -> None:
        """Test high confidence with stable selectors."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(title="Test", expected_results=["result"])

        script = """
page.get_by_test_id("button").click()
page.get_by_role("button", name="Submit").click()
expect(page.get_by_text("Success")).to_be_visible()
"""
        confidence = generator._calculate_confidence(script, test_case)
        assert confidence > 0.6

    def test_confidence_with_xpath_penalty(self, temp_workspace: Path) -> None:
        """Test confidence penalty for XPath usage."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(title="Test", expected_results=["result"])

        script = """
page.locator("xpath=//div[@class='btn']").click()
page.locator("xpath=//input[@id='name']").fill("test")
page.locator("xpath=//button").click()
"""
        confidence = generator._calculate_confidence(script, test_case)
        # Should be penalized for excessive XPath
        assert confidence < 0.5

    def test_confidence_with_assertions(self, temp_workspace: Path) -> None:
        """Test confidence boost for proper assertions."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(
            title="Test",
            expected_results=["result1", "result2", "result3"],
        )

        script = """
expect(page.get_by_test_id("msg")).to_have_text("result1")
expect(page.get_by_test_id("msg2")).to_be_visible()
expect(page).to_have_url("/success")
"""
        confidence = generator._calculate_confidence(script, test_case)
        # Should have higher confidence with assertions
        assert confidence > 0.5

    def test_confidence_base_score(self, temp_workspace: Path) -> None:
        """Test base confidence score."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(title="Test", expected_results=[])

        script = "pass"  # Minimal script
        confidence = generator._calculate_confidence(script, test_case)
        # Base score is 0.5
        assert confidence == 0.5


class TestScriptGeneratorScriptHeader:
    """Test suite for script header generation."""

    def test_header_contains_metadata(self, temp_workspace: Path) -> None:
        """Test header contains durable source traceability, not a stale workspace path."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(title="My Test Case")

        header = generator._generate_script_header(test_case)

        assert "Generated Playwright test script for: My Test Case" in header
        # AC2: durable header — no stale workspace path
        assert "workspace/testcases/" not in header
        assert "Generated:" in header
        assert "Model:" in header
        assert "import pytest" in header
        assert "from playwright.sync_api import Page, expect" in header

    def test_header_includes_source_requirement_when_present(self, temp_workspace: Path) -> None:
        """Test header includes source requirement name and URL when available (12.2 fields)."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(
            title="Login Test",
            source_requirement_name="FR-001 User Authentication",
            source_url="https://confluence.example.com/FR-001",
        )

        header = generator._generate_script_header(test_case)

        assert "Source requirement: FR-001 User Authentication" in header
        assert "Source URL: https://confluence.example.com/FR-001" in header
        assert "workspace/testcases/" not in header

    def test_header_omits_source_lines_when_fields_absent(self, temp_workspace: Path) -> None:
        """Test header degrades gracefully when 12.2 source fields are absent."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(title="Simple Test")

        header = generator._generate_script_header(test_case)

        assert "Source requirement:" not in header
        assert "Source URL:" not in header
        assert "Generated Playwright test script for: Simple Test" in header

    def test_header_omits_empty_source_url(self, temp_workspace: Path) -> None:
        """Test header omits source URL line when URL is empty string (Confluence stores '')."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(
            title="Confluence Test",
            source_requirement_name="Some Requirement",
            source_url="",
        )

        header = generator._generate_script_header(test_case)

        assert "Source requirement: Some Requirement" in header
        assert "Source URL:" not in header


class TestScriptGeneratorLLMIntegration:
    """Test suite for LLM integration."""

    async def test_llm_client_creation(self, temp_workspace: Path) -> None:
        """Test LLM client is created correctly."""
        config = AppSettings(
            script_generation_model="claude-3-opus",
            script_generation_temperature=0.5,
        )
        generator = ScriptGenerator(output_base_dir=temp_workspace, config=config)

        with patch("ai_qa.pipelines.script_generator.LLMClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            _ = generator._get_llm_client()

            mock_client_class.assert_called_once()
            call_args = mock_client_class.call_args[0][0]
            assert call_args.model_name == "claude-3-opus"
            assert call_args.temperature == 0.5

    async def test_llm_call_with_retry(
        self, temp_workspace: Path, sample_test_case: TestCase
    ) -> None:
        """Test LLM call uses retry logic."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "def test(): pass"
        mock_client.invoke = MagicMock(return_value=mock_response)

        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            script = await generator._call_llm(sample_test_case)

            assert script == "def test(): pass"
            mock_client.invoke.assert_called_once()


class TestScriptGeneratorValidation:
    """Test suite for script validation."""

    async def test_empty_script_content(
        self, temp_workspace: Path, sample_test_case: TestCase
    ) -> None:
        """Test handling of empty script content from LLM."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "   "  # Empty/whitespace only
        mock_client.invoke = MagicMock(return_value=mock_response)

        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            result = await generator._generate_single_script(sample_test_case)

            assert result["success"] is False
            assert "empty" in result["error"].lower()

    async def test_script_length_limit(
        self, temp_workspace: Path, sample_test_case: TestCase
    ) -> None:
        """Test script length validation."""
        config = AppSettings(max_script_length=2000)
        generator = ScriptGenerator(output_base_dir=temp_workspace, config=config)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "x" * 2500  # Exceeds limit of 2000
        mock_client.invoke = MagicMock(return_value=mock_response)

        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            result = await generator._generate_single_script(sample_test_case)

            assert result["success"] is False
            assert "max length" in result["error"].lower()


class TestProcessFunction:
    """Test suite for the process entry point function."""

    async def test_process_entry_point(
        self,
        temp_workspace: Path,
        sample_test_case: TestCase,
    ) -> None:
        """Test the process function as pipeline entry point."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "def test_example(page): pass"
        mock_client.invoke = MagicMock(return_value=mock_response)

        config = AppSettings()

        with patch("ai_qa.pipelines.script_generator.LLMClient") as mock_client_class:
            mock_client_class.return_value = mock_client
            result = await process(
                test_cases=[sample_test_case],
                output_base_dir=temp_workspace,
                config=config,
            )

        assert isinstance(result, StageResult)
        assert result.data is not None or result.errors

    async def test_process_without_config(
        self, temp_workspace: Path, sample_test_case: TestCase
    ) -> None:
        """Test process function with default config."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "def test_example(page): pass"
        mock_client.invoke = MagicMock(return_value=mock_response)

        with patch("ai_qa.pipelines.script_generator.LLMClient") as mock_client_class:
            mock_client_class.return_value = mock_client
            result = await process(
                test_cases=[sample_test_case],
                output_base_dir=temp_workspace,
            )

        assert isinstance(result, StageResult)


# ---------------------------------------------------------------------------
# Story 13.2 — AC3 prompt guard tests
# ---------------------------------------------------------------------------


class TestScriptGenerationPromptAC3:
    """Test that generation prompts enforce the no-unsafe-inference rule (AC3)."""

    def test_system_prompt_contains_no_unsafe_inference_rule(self) -> None:
        """SCRIPT_GENERATION_SYSTEM_PROMPT must instruct the model not to invent details."""
        from ai_qa.prompts.script_generation import SCRIPT_GENERATION_SYSTEM_PROMPT

        lowered = SCRIPT_GENERATION_SYSTEM_PROMPT.lower()
        assert "never invent" in lowered or "do not invent" in lowered or "not invent" in lowered

    def test_system_prompt_allows_todo_markers(self) -> None:
        """System prompt must explicitly allow # TODO: and # REVIEW: markers."""
        from ai_qa.prompts.script_generation import SCRIPT_GENERATION_SYSTEM_PROMPT

        assert (
            "# TODO:" in SCRIPT_GENERATION_SYSTEM_PROMPT
            or "TODO" in SCRIPT_GENERATION_SYSTEM_PROMPT
        )
        assert (
            "# REVIEW:" in SCRIPT_GENERATION_SYSTEM_PROMPT
            or "REVIEW" in SCRIPT_GENERATION_SYSTEM_PROMPT
        )

    def test_main_prompt_contains_no_unsafe_inference_rule(self) -> None:
        """SCRIPT_GENERATION_PROMPT must include the do-not-invent instruction."""
        from ai_qa.prompts.script_generation import SCRIPT_GENERATION_PROMPT

        lowered = SCRIPT_GENERATION_PROMPT.lower()
        assert "do not" in lowered or "never" in lowered or "must not" in lowered

    def test_main_prompt_contains_step_number_format(self) -> None:
        """SCRIPT_GENERATION_PROMPT must require Step N: format in comments."""
        from ai_qa.prompts.script_generation import SCRIPT_GENERATION_PROMPT

        assert "Step N:" in SCRIPT_GENERATION_PROMPT or "# Step" in SCRIPT_GENERATION_PROMPT

    def test_vision_system_prompt_contains_no_unsafe_inference_rule(self) -> None:
        """Vision system prompt must also enforce no-invent rule."""
        from ai_qa.prompts.script_generation import VISION_SCRIPT_GENERATION_SYSTEM_PROMPT

        lowered = VISION_SCRIPT_GENERATION_SYSTEM_PROMPT.lower()
        assert "never invent" in lowered or "do not invent" in lowered or "not invent" in lowered


# ---------------------------------------------------------------------------
# Story 13.2 — Marker detection tests (AC3 engine)
# ---------------------------------------------------------------------------


class TestExtractReviewWarnings:
    """Test _extract_review_warnings helper for TODO/REVIEW marker detection."""

    def test_detects_todo_marker(self, temp_workspace: Path) -> None:
        """A TODO marker line is extracted as a warning."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = "page.goto('/')\n    # TODO: exact submit control not specified\nexpect(page).to_be_visible()"

        warnings = generator._extract_review_warnings(script)

        assert len(warnings) == 1
        assert "TODO" in warnings[0]
        assert "exact submit control not specified" in warnings[0]

    def test_detects_review_marker(self, temp_workspace: Path) -> None:
        """A REVIEW marker line is extracted as a warning."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = "# REVIEW: expected result is ambiguous — multiple valid states"

        warnings = generator._extract_review_warnings(script)

        assert len(warnings) == 1
        assert "REVIEW" in warnings[0]
        assert "ambiguous" in warnings[0]

    def test_detects_multiple_markers(self, temp_workspace: Path) -> None:
        """Multiple TODO/REVIEW markers are all extracted."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = (
            "page.goto('/')\n"
            "    # TODO: missing input selector\n"
            "    # REVIEW: unclear whether to click or submit\n"
            "    # TODO: credential value not specified\n"
        )

        warnings = generator._extract_review_warnings(script)

        assert len(warnings) == 3

    def test_case_insensitive_detection(self, temp_workspace: Path) -> None:
        """Marker detection is case-insensitive."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = "# todo: lower case marker\n# Review: mixed case"

        warnings = generator._extract_review_warnings(script)

        assert len(warnings) == 2

    def test_no_markers_returns_empty_list(self, temp_workspace: Path) -> None:
        """Script with no markers yields empty warning list (back-compat)."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = (
            "def test_login(page: Page):\n"
            "    page.goto('https://app.example.com')\n"
            "    page.get_by_test_id('username').fill('user')\n"
            "    expect(page).to_have_url('/dashboard')\n"
        )

        warnings = generator._extract_review_warnings(script)

        assert warnings == []

    def test_regular_comment_not_detected(self, temp_workspace: Path) -> None:
        """Regular comments that don't start with TODO/REVIEW are not extracted."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = "# Step 1: navigate to login\n# This is a normal comment"

        warnings = generator._extract_review_warnings(script)

        assert warnings == []

    async def test_generate_single_script_populates_warnings(
        self, temp_workspace: Path, sample_test_case: TestCase
    ) -> None:
        """Warnings from marker detection flow from _generate_single_script into result dict."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)

        todo_script = (
            "def test_login(page: Page):\n"
            "    # TODO: exact submit control not specified\n"
            "    page.goto('/')\n"
        )
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = todo_script
        mock_client.invoke = MagicMock(return_value=mock_response)

        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            result = await generator._generate_single_script(sample_test_case)

        assert result["success"] is True
        # 13.3 adds assertion-gap warnings on top; check the TODO marker is present
        todo_warnings = [w for w in result["warnings"] if "TODO" in w]
        assert len(todo_warnings) >= 1
        assert "exact submit control not specified" in todo_warnings[0]

    async def test_generate_propagates_warnings_to_stage_result(
        self, temp_workspace: Path, sample_test_case: TestCase
    ) -> None:
        """Warnings from per-script detection aggregate into StageResult.warnings."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)

        todo_script = "def test_x(page):\n    # TODO: missing URL\n    pass\n"
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = todo_script
        mock_client.invoke = MagicMock(return_value=mock_response)

        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            result = await generator.generate([sample_test_case])

        assert result.success is True
        assert any("TODO" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Story 13.3 — Prompt guard tests (AC1/AC2 prompt rules)
# ---------------------------------------------------------------------------


class TestScriptGenerationPromptAC133:
    """13.3: Prompt rules for brittle-selector flagging + ambiguous-assertion warnings."""

    def test_main_prompt_contains_brittle_fallback_rule(self) -> None:
        """SCRIPT_GENERATION_PROMPT must instruct the LLM to flag brittle-selector fallbacks."""
        from ai_qa.prompts.script_generation import SCRIPT_GENERATION_PROMPT

        lowered = SCRIPT_GENERATION_PROMPT.lower()
        assert "brittle" in lowered
        assert "# review:" in lowered or "# review:" in SCRIPT_GENERATION_PROMPT.lower()

    def test_main_prompt_contains_assertion_warning_rule(self) -> None:
        """SCRIPT_GENERATION_PROMPT must instruct the LLM to flag ambiguous/unsupported assertions."""
        from ai_qa.prompts.script_generation import SCRIPT_GENERATION_PROMPT

        lowered = SCRIPT_GENERATION_PROMPT.lower()
        assert "ambiguous" in lowered or "unsupported" in lowered

    def test_main_prompt_still_has_step_comment_instruction(self) -> None:
        """SCRIPT_GENERATION_PROMPT must still include # Step N: format instruction."""
        from ai_qa.prompts.script_generation import SCRIPT_GENERATION_PROMPT

        assert "# Step N:" in SCRIPT_GENERATION_PROMPT or "Step N" in SCRIPT_GENERATION_PROMPT

    def test_main_prompt_still_forbids_inventing(self) -> None:
        """SCRIPT_GENERATION_PROMPT must still forbid inventing selectors/assertions."""
        from ai_qa.prompts.script_generation import SCRIPT_GENERATION_PROMPT

        lowered = SCRIPT_GENERATION_PROMPT.lower()
        assert "do not" in lowered or "never" in lowered or "must not" in lowered

    def test_vision_prompt_contains_brittle_fallback_rule(self) -> None:
        """VISION_ASSISTED_SCRIPT_GENERATION_PROMPT must also flag brittle-selector fallbacks."""
        from ai_qa.prompts.script_generation import VISION_ASSISTED_SCRIPT_GENERATION_PROMPT

        lowered = VISION_ASSISTED_SCRIPT_GENERATION_PROMPT.lower()
        assert "brittle" in lowered

    def test_vision_prompt_contains_assertion_warning_rule(self) -> None:
        """VISION_ASSISTED_SCRIPT_GENERATION_PROMPT must also flag ambiguous assertions."""
        from ai_qa.prompts.script_generation import VISION_ASSISTED_SCRIPT_GENERATION_PROMPT

        lowered = VISION_ASSISTED_SCRIPT_GENERATION_PROMPT.lower()
        assert "ambiguous" in lowered or "unsupported" in lowered


# ---------------------------------------------------------------------------
# Story 13.3 — Brittle-selector detector tests (AC1, AC3)
# ---------------------------------------------------------------------------


class TestBrittleSelectorDetector:
    """Tests for ScriptGenerator._detect_brittle_selectors (13.3 AC1/AC3)."""

    def test_xpath_locator_flagged(self, temp_workspace: Path) -> None:
        """An XPath locator is flagged as a brittle selector."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = "    page.locator(\"xpath=//button[@type='submit']\").click()"

        warnings = generator._detect_brittle_selectors(script)

        assert len(warnings) == 1
        assert "Brittle selector" in warnings[0]
        assert "xpath=" in warnings[0]

    def test_css_locator_flagged(self, temp_workspace: Path) -> None:
        """A raw CSS locator is flagged as a brittle selector."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = '    page.locator(".submit-btn").click()'

        warnings = generator._detect_brittle_selectors(script)

        assert len(warnings) == 1
        assert "Brittle selector" in warnings[0]
        assert ".submit-btn" in warnings[0]

    def test_step_attribution_included(self, temp_workspace: Path) -> None:
        """Brittle selector warning includes Step N ref from nearest # Step N: comment."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = '# Step 2: click the submit button\n    page.locator("xpath=//button").click()\n'

        warnings = generator._detect_brittle_selectors(script)

        assert len(warnings) == 1
        assert "(Step 2)" in warnings[0]

    def test_both_xpath_and_css_flagged_independently(self, temp_workspace: Path) -> None:
        """XPath and CSS locators on separate lines each produce one warning."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = (
            "# Step 2: navigate\n"
            '    page.locator("xpath=//button").click()\n'
            '    page.locator(".submit-btn").click()\n'
        )

        warnings = generator._detect_brittle_selectors(script)

        assert len(warnings) == 2
        xpath_warnings = [w for w in warnings if "xpath=" in w]
        css_warnings = [w for w in warnings if ".submit-btn" in w]
        assert len(xpath_warnings) == 1
        assert len(css_warnings) == 1
        # Both should carry the step attribution from the nearest # Step 2:
        assert all("(Step 2)" in w for w in warnings)

    def test_stable_selectors_produce_no_warnings(self, temp_workspace: Path) -> None:
        """Lines using only get_by_* stable selectors produce zero brittle warnings."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = (
            "# Step 1: login\n"
            '    page.get_by_test_id("username").fill("user")\n'
            '    page.get_by_role("button", name="Login").click()\n'
            '    page.get_by_label("Password").fill("pass")\n'
            '    page.get_by_text("Welcome").is_visible()\n'
            '    page.get_by_placeholder("Email").fill("x@y.com")\n'
            '    page.get_by_alt_text("logo").is_visible()\n'
            '    page.get_by_title("Submit").click()\n'
        )

        warnings = generator._detect_brittle_selectors(script)

        assert warnings == []

    def test_brittle_without_step_comment_omits_step_ref(self, temp_workspace: Path) -> None:
        """Brittle selector before any # Step N: comment is still flagged but without step ref."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = '    page.locator("#main-btn").click()\n'

        warnings = generator._detect_brittle_selectors(script)

        assert len(warnings) == 1
        assert "Brittle selector:" in warnings[0]  # no "(Step N)" segment
        assert "Step" not in warnings[0]

    def test_chained_stable_plus_brittle_flagged(self, temp_workspace: Path) -> None:
        """Chained stable+brittle (get_by_test_id(...).locator('.btn')) → flag brittle part."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = '    page.get_by_test_id("form").locator(".btn").click()\n'

        warnings = generator._detect_brittle_selectors(script)

        assert len(warnings) == 1
        assert ".btn" in warnings[0]

    def test_warning_includes_prefer_guidance(self, temp_workspace: Path) -> None:
        """Each brittle warning ends with the prefer-stable guidance."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = '    page.locator(".cls").click()\n'

        warnings = generator._detect_brittle_selectors(script)

        assert len(warnings) == 1
        assert "prefer" in warnings[0].lower()
        assert "get_by_test_id" in warnings[0]


# ---------------------------------------------------------------------------
# Story 13.3 — Assertion-gap detector tests (AC2, AC3)
# ---------------------------------------------------------------------------


class TestAssertionGapDetector:
    """Tests for ScriptGenerator._detect_assertion_gaps (13.3 AC2/AC3)."""

    def test_gap_detected_when_fewer_assertions_than_expected(self, temp_workspace: Path) -> None:
        """1 expect() for 3 expected_results → one gap warning."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(
            title="T",
            expected_results=["result 1", "result 2", "result 3"],
        )
        script = "expect(page).to_have_url('/done')\n"

        warnings = generator._detect_assertion_gaps(script, test_case)

        assert len(warnings) == 1
        assert "only 1 of 3" in warnings[0]
        assert "Assertion gap" in warnings[0]

    def test_no_gap_when_assertion_count_equals_expected(self, temp_workspace: Path) -> None:
        """expect() count == expected_results count → no gap warning."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(
            title="T",
            expected_results=["r1", "r2"],
        )
        script = "expect(a).to_be_visible()\nexpect(b).to_have_text('x')\n"

        warnings = generator._detect_assertion_gaps(script, test_case)

        assert warnings == []

    def test_no_gap_when_more_assertions_than_expected(self, temp_workspace: Path) -> None:
        """expect() count > expected_results count → no gap warning."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(title="T", expected_results=["r1"])
        script = "expect(a).to_be_visible()\nexpect(b).to_be_visible()\n"

        warnings = generator._detect_assertion_gaps(script, test_case)

        assert warnings == []

    def test_no_gap_when_no_expected_results(self, temp_workspace: Path) -> None:
        """empty expected_results → no gap warning (nothing to compare)."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(title="T", expected_results=[])
        script = "pass\n"

        warnings = generator._detect_assertion_gaps(script, test_case)

        assert warnings == []

    def test_gap_message_includes_counts(self, temp_workspace: Path) -> None:
        """Gap warning message includes the actual counts for human readability."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(
            title="T",
            expected_results=["r1", "r2", "r3", "r4"],
        )
        script = "expect(page).to_have_url('/x')\nexpect(el).to_be_visible()\n"

        warnings = generator._detect_assertion_gaps(script, test_case)

        assert len(warnings) == 1
        assert "2 of 4" in warnings[0]


# ---------------------------------------------------------------------------
# Story 13.3 — End-to-end engine tests (AC1/AC2 wired through generate)
# ---------------------------------------------------------------------------


class TestStory133EndToEnd:
    """End-to-end tests: detectors wired into generate() → StageResult.warnings."""

    async def test_brittle_and_gap_warnings_in_stage_result(self, temp_workspace: Path) -> None:
        """LLM returns a brittle-XPath script with fewer assertions → warnings in StageResult."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(
            title="Login",
            steps=[TestCaseStep(number=1, action="click", target="btn")],
            expected_results=["user is redirected", "welcome message shown"],
        )
        brittle_script = (
            "# Step 1: click login\n"
            "    page.locator(\"xpath=//button[@id='login']\").click()\n"
            "    expect(page).to_have_url('/dashboard')\n"
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = brittle_script
        mock_client.invoke = MagicMock(return_value=mock_response)

        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            result = await generator.generate([test_case])

        assert result.success is True
        brittle = [w for w in result.warnings if "Brittle selector" in w]
        gap = [w for w in result.warnings if "Assertion gap" in w]
        assert len(brittle) >= 1, "Expected at least one brittle-selector warning"
        assert len(gap) == 1, "Expected exactly one assertion-gap warning"
        assert "(Step 1)" in brittle[0]
        assert "1 of 2" in gap[0]

    async def test_per_case_warnings_in_generate_result_dict(self, temp_workspace: Path) -> None:
        """Per-case result dict includes brittle + gap warnings (populates GeneratedScript.warnings)."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(
            title="T",
            expected_results=["visible", "enabled"],
        )
        script = '    page.locator(".btn").click()\n    expect(page).to_be_visible()\n'

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = script
        mock_client.invoke = MagicMock(return_value=mock_response)

        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            single = await generator._generate_single_script(test_case)

        assert single["success"] is True
        assert any("Brittle selector" in w for w in single["warnings"])
        assert any("Assertion gap" in w for w in single["warnings"])

    async def test_clean_script_yields_no_detector_warnings(
        self, temp_workspace: Path, sample_test_case: TestCase
    ) -> None:
        """A clean script (stable selectors, full coverage) yields no brittle/gap warnings."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        clean_script = (
            "# Step 1: enter username\n"
            '    page.get_by_test_id("username").fill("user")\n'
            "# Step 2: click login\n"
            '    page.get_by_role("button", name="Login").click()\n'
            "    expect(page).to_have_url('/dashboard')\n"
            "    expect(page.get_by_text('Welcome')).to_be_visible()\n"
        )
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = clean_script
        mock_client.invoke = MagicMock(return_value=mock_response)

        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            result = await generator.generate([sample_test_case])

        brittle = [w for w in result.warnings if "Brittle selector" in w]
        gap = [w for w in result.warnings if "Assertion gap" in w]
        assert brittle == [], "Clean script should have no brittle-selector warnings"
        assert gap == [], "Clean script with full assertion coverage should have no gap warning"

    def test_confidence_unchanged_by_13_3_detectors(self, temp_workspace: Path) -> None:
        """13.3 detectors are an independent advisory surface and must not feed confidence.

        Non-tautological: confidence is computed for a clean script, then the SAME script is
        re-scored after brittle-selector and assertion-gap patterns are added. The detectors
        flag those patterns, but the confidence delta must come solely from _calculate_confidence's
        own heuristics — running the detectors must not alter the score for an identical script.
        """
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(title="T", expected_results=["r1", "r2"])
        clean_script = (
            "page.get_by_test_id('btn').click()\n"
            "page.get_by_role('button', name='X').click()\n"
            "expect(page).to_have_url('/ok')\n"
            "expect(page.get_by_text('Done')).to_be_visible()\n"
        )

        # Baseline confidence for the clean script, with the detectors NOT run.
        baseline = generator._calculate_confidence(clean_script, test_case)
        assert generator._detect_brittle_selectors(clean_script) == []
        assert generator._detect_assertion_gaps(clean_script, test_case) == []

        # Add brittle-selector + assertion-gap patterns that the 13.3 detectors DO flag.
        flagged_script = clean_script + 'page.locator("xpath=//button").click()\n'
        gap_tc = TestCase(title="T", expected_results=["r1", "r2", "r3", "r4", "r5"])
        assert generator._detect_brittle_selectors(flagged_script) != []
        assert generator._detect_assertion_gaps(flagged_script, gap_tc) != []

        # Confidence for the flagged script must be reproducible AND must equal the value
        # _calculate_confidence yields independently of whether the detectors were invoked —
        # proving the detectors do not write into the confidence path.
        before_detectors = generator._calculate_confidence(flagged_script, gap_tc)
        _ = generator._detect_brittle_selectors(flagged_script)
        _ = generator._detect_assertion_gaps(flagged_script, gap_tc)
        after_detectors = generator._calculate_confidence(flagged_script, gap_tc)
        assert before_detectors == after_detectors
        # And the clean-script baseline is untouched by the detector run on the flagged script.
        assert generator._calculate_confidence(clean_script, test_case) == baseline


# ---------------------------------------------------------------------------
# Story 13.4 — Prompt guard tests (session-reuse, no-hardcode-credentials, SSO-setup)
# ---------------------------------------------------------------------------


class TestScriptGenerationPromptAC134:
    """13.4: Prompt rules for session reuse, no hardcoded credentials, SSO-setup warning."""

    def test_main_prompt_contains_session_reuse_rule(self) -> None:
        """SCRIPT_GENERATION_PROMPT must instruct the LLM to assume a pre-authenticated session."""
        from ai_qa.prompts.script_generation import SCRIPT_GENERATION_PROMPT

        lowered = SCRIPT_GENERATION_PROMPT.lower()
        assert "sso" in lowered or ("session" in lowered and "authenticated" in lowered)
        assert "do not automate" in lowered or "not automate" in lowered or "skip" in lowered

    def test_main_prompt_contains_no_hardcode_credentials_rule(self) -> None:
        """SCRIPT_GENERATION_PROMPT must forbid hardcoding credentials."""
        from ai_qa.prompts.script_generation import SCRIPT_GENERATION_PROMPT

        lowered = SCRIPT_GENERATION_PROMPT.lower()
        assert "never" in lowered or "must not" in lowered
        assert "credential" in lowered or "password" in lowered or "secret" in lowered

    def test_main_prompt_contains_sso_setup_warning_rule(self) -> None:
        """SCRIPT_GENERATION_PROMPT must instruct the LLM to emit a # REVIEW: SSO-setup marker."""
        from ai_qa.prompts.script_generation import SCRIPT_GENERATION_PROMPT

        assert "# REVIEW:" in SCRIPT_GENERATION_PROMPT
        lowered = SCRIPT_GENERATION_PROMPT.lower()
        assert "sso" in lowered or "session setup" in lowered

    def test_main_prompt_still_forbids_inventing(self) -> None:
        """SCRIPT_GENERATION_PROMPT still forbids inventing selectors/credentials (regression)."""
        from ai_qa.prompts.script_generation import SCRIPT_GENERATION_PROMPT

        lowered = SCRIPT_GENERATION_PROMPT.lower()
        assert "do not" in lowered or "never" in lowered

    def test_vision_prompt_contains_session_reuse_rule(self) -> None:
        """VISION_ASSISTED_SCRIPT_GENERATION_PROMPT must also include session-reuse rule."""
        from ai_qa.prompts.script_generation import VISION_ASSISTED_SCRIPT_GENERATION_PROMPT

        lowered = VISION_ASSISTED_SCRIPT_GENERATION_PROMPT.lower()
        assert "sso" in lowered or ("session" in lowered and "authenticated" in lowered)

    def test_vision_prompt_contains_no_hardcode_credentials_rule(self) -> None:
        """VISION_ASSISTED_SCRIPT_GENERATION_PROMPT must forbid hardcoding credentials."""
        from ai_qa.prompts.script_generation import VISION_ASSISTED_SCRIPT_GENERATION_PROMPT

        lowered = VISION_ASSISTED_SCRIPT_GENERATION_PROMPT.lower()
        assert "credential" in lowered or "password" in lowered or "secret" in lowered

    def test_system_prompt_contains_no_credentials_principle(self) -> None:
        """SCRIPT_GENERATION_SYSTEM_PROMPT must include the never-emit-credentials principle."""
        from ai_qa.prompts.script_generation import SCRIPT_GENERATION_SYSTEM_PROMPT

        lowered = SCRIPT_GENERATION_SYSTEM_PROMPT.lower()
        assert "credential" in lowered or "session" in lowered

    def test_vision_system_prompt_contains_no_credentials_principle(self) -> None:
        """VISION_SCRIPT_GENERATION_SYSTEM_PROMPT must include the never-emit-credentials principle."""
        from ai_qa.prompts.script_generation import VISION_SCRIPT_GENERATION_SYSTEM_PROMPT

        lowered = VISION_SCRIPT_GENERATION_SYSTEM_PROMPT.lower()
        assert "credential" in lowered or "session" in lowered


# ---------------------------------------------------------------------------
# Story 13.4 — Hardcoded-secret detector tests (AC1, AC3)
# ---------------------------------------------------------------------------


class TestHardcodedSecretDetector:
    """Tests for ScriptGenerator._detect_hardcoded_secrets (13.4 AC1/AC3)."""

    def test_fill_password_locator_flagged_with_step_ref(self, temp_workspace: Path) -> None:
        """A .fill literal on a password-named locator with step attribution → warning with (Step N)."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = '# Step 1: enter password\n    page.get_by_label("Password").fill("hunter2")\n'

        warnings = generator._detect_hardcoded_secrets(script)

        assert len(warnings) == 1
        assert "Credential/secret literal" in warnings[0]
        assert "(Step 1)" in warnings[0]
        # Literal value must be redacted
        assert "hunter2" not in warnings[0]

    def test_fill_username_locator_flagged(self, temp_workspace: Path) -> None:
        """C44/AC1: a literal filled into a username-named locator is flagged (one warning).

        AC1/AC3 enumerate "usernames" alongside passwords/tokens, so a hardcoded username
        literal must be flagged for review just like a password literal.
        """
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = '# Step 1: enter username\n    page.get_by_label("Username").fill("admin-user")\n'

        warnings = generator._detect_hardcoded_secrets(script)

        assert len(warnings) == 1
        assert "Credential/secret literal" in warnings[0]
        assert "(Step 1)" in warnings[0]
        # Literal value must be redacted
        assert "admin-user" not in warnings[0]

    def test_fill_password_no_step_ref_when_no_preceding_step(self, temp_workspace: Path) -> None:
        """Credential fill before any # Step N: comment is still flagged without step ref."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = '    page.get_by_placeholder("Password").fill("s3cr3t")\n'

        warnings = generator._detect_hardcoded_secrets(script)

        assert len(warnings) == 1
        assert "Credential/secret literal:" in warnings[0]
        assert "Step" not in warnings[0]
        assert "s3cr3t" not in warnings[0]

    def test_token_variable_assignment_flagged(self, temp_workspace: Path) -> None:
        """A token = 'literal' assignment is flagged as a hardcoded secret."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = '    token = "abc123"\n'

        warnings = generator._detect_hardcoded_secrets(script)

        assert len(warnings) == 1
        assert "Credential/secret literal" in warnings[0]
        assert "abc123" not in warnings[0]

    def test_api_key_variable_assignment_flagged(self, temp_workspace: Path) -> None:
        """An api_key = 'literal' assignment is flagged."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = '    api_key = "sk-superSECRET"\n'

        warnings = generator._detect_hardcoded_secrets(script)

        assert any("Credential/secret literal" in w for w in warnings)
        assert all("superSECRET" not in w for w in warnings)

    def test_add_cookies_flagged(self, temp_workspace: Path) -> None:
        """An add_cookies() call is flagged as a credential-injection risk."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = (
            "# Step 2: inject session\n"
            "    context.add_cookies([{'name': 'session', 'value': 'abc', 'domain': 'app'}])\n"
        )

        warnings = generator._detect_hardcoded_secrets(script)

        assert any("add_cookies" in w for w in warnings)

    def test_inline_storage_state_dict_flagged(self, temp_workspace: Path) -> None:
        """An inline storage_state={...} dict is flagged."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = '    context = browser.new_context(storage_state={"cookies": []})\n'

        warnings = generator._detect_hardcoded_secrets(script)

        assert any("storage_state" in w for w in warnings)

    def test_url_with_embedded_creds_flagged(self, temp_workspace: Path) -> None:
        """A URL with embedded user:pass@host credentials is flagged."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = '    page.goto("https://admin:s3cr3t@app.example.com/dashboard")\n'

        warnings = generator._detect_hardcoded_secrets(script)

        assert any("embedded credentials" in w for w in warnings)
        # Actual password must be redacted
        assert all("s3cr3t" not in w for w in warnings)

    def test_clean_script_env_vars_no_warnings(self, temp_workspace: Path) -> None:
        """A clean script using env vars and a path-based storage_state yields zero warnings."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        clean_script = (
            "import os\n"
            "# Step 1: navigate\n"
            '    page.goto("https://app.example.com")\n'
            "# Step 2: use pre-authenticated session\n"
            "    # REVIEW: SSO/session setup required before execution\n"
            '    username = os.environ["APP_USERNAME"]\n'
            '    browser.new_context(storage_state="state.json")\n'
        )

        warnings = generator._detect_hardcoded_secrets(clean_script)

        assert warnings == [], f"Expected zero warnings for clean script, got: {warnings}"

    def test_storage_state_string_path_not_flagged(self, temp_workspace: Path) -> None:
        """storage_state='path/to/file.json' (string path) is allowed and must not be flagged."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        script = '    context = browser.new_context(storage_state="auth_state.json")\n'

        warnings = generator._detect_hardcoded_secrets(script)

        # Only the inline dict is forbidden; a string path is the approved pattern
        storage_warnings = [w for w in warnings if "storage_state" in w]
        assert storage_warnings == [], (
            f"String path storage_state must not be flagged: {storage_warnings}"
        )


# ---------------------------------------------------------------------------
# Story 13.4 — Auth-setup detector tests (AC2)
# ---------------------------------------------------------------------------


class TestAuthSetupDetector:
    """Tests for ScriptGenerator._detect_auth_setup_needed (13.4 AC2)."""

    def test_login_step_no_sso_marker_emits_warning(self, temp_workspace: Path) -> None:
        """A test case with a login step and no SSO marker → one SSO-setup warning."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(
            title="User Login Flow",
            steps=[TestCaseStep(number=1, action="Login with credentials", target="login button")],
            expected_results=["dashboard is visible"],
        )
        script = (
            "def test_user_login_flow(page):\n"
            '    page.goto("https://app.example.com")\n'
            '    page.get_by_role("button", name="Login").click()\n'
        )

        warnings = generator._detect_auth_setup_needed(script, test_case)

        assert len(warnings) == 1
        assert "SSO/session setup required" in warnings[0]

    def test_logged_in_precondition_no_sso_marker_emits_warning(self, temp_workspace: Path) -> None:
        """A precondition stating 'User is logged in' with no SSO marker → one SSO-setup warning."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(
            title="View dashboard",
            preconditions=["User is logged in"],
            steps=[TestCaseStep(number=1, action="Navigate to dashboard", target="dashboard link")],
        )
        script = (
            'def test_view_dashboard(page):\n    page.goto("https://app.example.com/dashboard")\n'
        )

        warnings = generator._detect_auth_setup_needed(script, test_case)

        assert len(warnings) == 1
        assert "SSO/session setup required" in warnings[0]

    def test_sso_marker_in_script_suppresses_warning(self, temp_workspace: Path) -> None:
        """When the LLM already emits a # REVIEW: SSO marker, the deterministic warning is suppressed."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(
            title="Login Flow",
            steps=[TestCaseStep(number=1, action="Sign in to the app", target="sign-in button")],
        )
        script = (
            "def test_login_flow(page):\n"
            "    # REVIEW: SSO/session setup required before execution\n"
            '    page.goto("https://app.example.com")\n'
        )

        warnings = generator._detect_auth_setup_needed(script, test_case)

        assert warnings == [], "LLM SSO marker already present — no duplicate warning expected"

    def test_non_auth_test_case_no_warning(self, temp_workspace: Path) -> None:
        """A non-auth test case (public search) produces no auth-setup warning."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(
            title="Search functionality",
            preconditions=["User is on the search page"],
            steps=[
                TestCaseStep(number=1, action="Type query in search box", target="search input"),
                TestCaseStep(number=2, action="Press Enter", target="search input"),
            ],
            expected_results=["Search results are displayed"],
        )
        script = (
            "def test_search(page):\n"
            '    page.goto("https://app.example.com/search")\n'
            '    page.get_by_placeholder("Search...").fill("test query")\n'
            '    page.keyboard.press("Enter")\n'
            '    expect(page.get_by_text("Results")).to_be_visible()\n'
        )

        warnings = generator._detect_auth_setup_needed(script, test_case)

        assert warnings == [], f"Non-auth test case must produce no auth-setup warning: {warnings}"


# ---------------------------------------------------------------------------
# Story 13.4 — End-to-end engine tests (wired through generate → StageResult)
# ---------------------------------------------------------------------------


class TestStory134EndToEnd:
    """End-to-end: 13.4 detectors wired into generate() → StageResult.warnings."""

    async def test_credential_and_auth_warnings_in_stage_result(self, temp_workspace: Path) -> None:
        """LLM returns a script with a hardcoded password + login flow → warnings in StageResult."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(
            title="Login with credentials",
            steps=[
                TestCaseStep(number=1, action="Enter password", target="password input"),
                TestCaseStep(number=2, action="Click login", target="login button"),
            ],
            expected_results=["dashboard is visible"],
        )
        # Mocked LLM "forgot" the session-reuse rule and emitted a hardcoded password
        bad_script = (
            "def test_login_with_credentials(page):\n"
            "    # Step 1: enter password\n"
            '    page.get_by_label("Password").fill("hunter2")\n'
            "    # Step 2: click login\n"
            '    page.get_by_role("button", name="Login").click()\n'
            '    expect(page).to_have_url("/dashboard")\n'
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = bad_script
        mock_client.invoke = MagicMock(return_value=mock_response)

        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            result = await generator.generate([test_case])

        assert result.success is True
        secret_warnings = [w for w in result.warnings if "Credential/secret literal" in w]
        # 13.4 auth-setup warning starts with "SSO/session setup required:" (not "REVIEW: SSO…")
        auth_warnings = [w for w in result.warnings if w.startswith("SSO/session setup required:")]
        assert len(secret_warnings) >= 1, "Expected credential literal warning"
        assert len(auth_warnings) >= 1, "Expected SSO/session setup warning"
        # Literal value must NOT appear in any warning
        assert all("hunter2" not in w for w in result.warnings)

    async def test_clean_sso_script_no_13_4_warnings(
        self, temp_workspace: Path, sample_test_case: TestCase
    ) -> None:
        """A clean session-reuse script with SSO marker yields no 13.4 auth-setup detector warning."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        clean_script = (
            "def test_user_login_flow(page):\n"
            "    # REVIEW: SSO/session setup required before execution\n"
            '    page.goto("https://app.example.com/dashboard")\n'
            '    expect(page.get_by_test_id("welcome-banner")).to_be_visible()\n'
            '    expect(page.get_by_test_id("user-menu")).to_be_visible()\n'
        )
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = clean_script
        mock_client.invoke = MagicMock(return_value=mock_response)

        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            result = await generator.generate([sample_test_case])

        secret_warnings = [w for w in result.warnings if "Credential/secret literal" in w]
        # 13.4 auth-setup detector warning starts with "SSO/session setup required:"
        # (distinct from 13.2's "REVIEW: SSO/session setup required …" which is the LLM's inline marker)
        sso_auth_warnings = [
            w for w in result.warnings if w.startswith("SSO/session setup required:")
        ]
        assert secret_warnings == [], "Clean script must have no credential warnings"
        assert sso_auth_warnings == [], (
            "Script with SSO marker must suppress the auth-setup detector warning"
        )

    def test_confidence_unchanged_by_13_4_detectors(self, temp_workspace: Path) -> None:
        """13.4 detectors are an independent advisory surface and must not feed confidence.

        Non-tautological: confidence is computed for a credential-bearing script BEFORE the
        secret/auth detectors run, then again AFTER they run. The detectors flag the hardcoded
        credential and the missing SSO setup, but the confidence score must be identical — proving
        the credential/auth flags never write into the _calculate_confidence path.
        """
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        # A script with stable selectors plus a hardcoded credential and a login flow:
        # the 13.4 detectors flag the credential + SSO setup, but confidence sees only selectors.
        cred_script = (
            "# Step 1: enter password\n"
            "page.get_by_test_id('btn').click()\n"
            "page.get_by_role('button', name='Login').click()\n"
            "page.get_by_label('Password').fill('hunter2')\n"
            "expect(page).to_have_url('/ok')\n"
        )
        cred_tc = TestCase(
            title="Login flow",
            steps=[TestCaseStep(number=1, action="Login", target="login button")],
            expected_results=["r"],
        )

        # Confidence computed WITHOUT invoking the 13.4 detectors.
        before_detectors = generator._calculate_confidence(cred_script, cred_tc)

        # The 13.4 detectors actively flag this script (so the comparison is meaningful).
        assert generator._detect_hardcoded_secrets(cred_script) != []
        assert generator._detect_auth_setup_needed(cred_script, cred_tc) != []

        # Confidence computed AFTER the detectors ran must be identical — the flags do not
        # participate in the score (no double-counting, per the 13.2/13.3/13.4 fence).
        after_detectors = generator._calculate_confidence(cred_script, cred_tc)
        assert before_detectors == after_detectors


# -----------------------------------------------------------------------------
# 13.7 — Feedback-into-regeneration (AC2)
# -----------------------------------------------------------------------------


class TestScriptGeneratorFeedback:
    """Story 13.7: generate(feedback=...) injects feedback into the prompt."""

    @pytest.mark.asyncio
    async def test_generate_with_feedback_injects_into_prompt(
        self,
        temp_workspace: Path,
        sample_test_case: TestCase,
    ) -> None:
        """AC2: when feedback is provided, the LLM is called with a prompt containing it."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "def test_example(page):\n    page.goto('https://example.com')\n"
        mock_client.invoke = MagicMock(return_value=mock_response)

        captured_prompts: list[str] = []

        def capture_invoke(messages, timeout=None):
            for msg in messages:
                if hasattr(msg, "content"):
                    captured_prompts.append(msg.content)
            return mock_response

        mock_client.invoke = MagicMock(side_effect=capture_invoke)

        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            result = await generator.generate(
                [sample_test_case], feedback="add an assertion for the welcome message"
            )

        assert result.success is True
        # At least one prompt must contain the feedback text
        assert any("add an assertion for the welcome message" in p for p in captured_prompts), (
            f"Feedback not found in prompts: {captured_prompts}"
        )
        # The feedback section marker must also be present
        assert any("Reviewer feedback to address" in p for p in captured_prompts)

    @pytest.mark.asyncio
    async def test_generate_without_feedback_behaves_identically(
        self,
        temp_workspace: Path,
        sample_test_case: TestCase,
    ) -> None:
        """AC2 back-compat: generate(...) with no feedback produces the same prompt as before."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "def test_example(page):\n    page.goto('https://example.com')\n"
        mock_client.invoke = MagicMock(return_value=mock_response)

        captured_prompts: list[str] = []

        def capture_invoke(messages, timeout=None):
            for msg in messages:
                if hasattr(msg, "content"):
                    captured_prompts.append(msg.content)
            return mock_response

        mock_client.invoke = MagicMock(side_effect=capture_invoke)

        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            result = await generator.generate([sample_test_case])

        assert result.success is True
        # No feedback section when no feedback provided
        assert not any("Reviewer feedback to address" in p for p in captured_prompts)

    @pytest.mark.asyncio
    async def test_generate_with_empty_feedback_behaves_identically(
        self,
        temp_workspace: Path,
        sample_test_case: TestCase,
    ) -> None:
        """AC2: empty string feedback is not injected (same as no feedback)."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "def test_example(page):\n    page.goto('https://example.com')\n"

        captured_prompts: list[str] = []

        def capture_invoke(messages, timeout=None):
            for msg in messages:
                if hasattr(msg, "content"):
                    captured_prompts.append(msg.content)
            return mock_response

        mock_client.invoke = MagicMock(side_effect=capture_invoke)

        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            result = await generator.generate([sample_test_case], feedback="  ")

        assert result.success is True
        assert not any("Reviewer feedback to address" in p for p in captured_prompts)

    @pytest.mark.asyncio
    async def test_generate_feedback_truncated_at_2000_chars(
        self,
        temp_workspace: Path,
        sample_test_case: TestCase,
    ) -> None:
        """AC2: feedback longer than 2000 chars is capped at 2000 in the prompt."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "def test_example(page):\n    pass\n"

        captured_prompts: list[str] = []

        def capture_invoke(messages, timeout=None):
            for msg in messages:
                if hasattr(msg, "content"):
                    captured_prompts.append(msg.content)
            return mock_response

        mock_client.invoke = MagicMock(side_effect=capture_invoke)

        long_feedback = "x" * 3000
        with patch.object(generator, "_get_llm_client", return_value=mock_client):
            result = await generator.generate([sample_test_case], feedback=long_feedback)

        assert result.success is True
        feedback_prompts = [p for p in captured_prompts if "Reviewer feedback to address" in p]
        assert feedback_prompts, "Expected feedback injection in prompt"
        # The injected portion must not exceed 2000 chars of the original feedback
        assert "x" * 2001 not in feedback_prompts[0], "Feedback must be capped at 2000 chars"
        assert "x" * 2000 in feedback_prompts[0], "2000 chars of feedback must be included"
