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

    def test_init_creates_output_writer(self, temp_workspace: Path) -> None:
        """Test that OutputWriter is created on initialization."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        assert generator._output_writer is not None


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
        assert "file_path" in result.data[0]

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
        """Test header contains required metadata."""
        generator = ScriptGenerator(output_base_dir=temp_workspace)
        test_case = TestCase(title="My Test Case")

        header = generator._generate_script_header(test_case)

        assert "Generated Playwright test script for: My Test Case" in header
        assert "Source: workspace/testcases/" in header
        assert "Generated:" in header
        assert "Model:" in header
        assert "import pytest" in header
        assert "from playwright.sync_api import Page, expect" in header


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
