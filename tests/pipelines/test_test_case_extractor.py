"""Tests for the TestCaseExtractor pipeline stage."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_qa.ai_connection.config import LLMConfig
from ai_qa.exceptions import LLMError
from ai_qa.models import TestCase, TestCaseStep
from ai_qa.pipelines.test_case_extractor import TestCaseExtractor


@pytest.fixture
def output_base_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for output."""
    return tmp_path / "workspace" / "testcases"


@pytest.fixture
def llm_config() -> LLMConfig:
    """Provide a test LLM configuration."""
    return LLMConfig(
        provider="litellm",
        model_name="gpt-4",
        temperature=0.0,
        base_url="http://localhost:4000",
        api_key="test-key",
    )


@pytest.fixture
def extractor(llm_config: LLMConfig) -> TestCaseExtractor:
    """Provide a TestCaseExtractor instance."""
    return TestCaseExtractor(llm_config=llm_config)


@pytest.fixture
def sample_requirements() -> str:
    """Provide sample requirements markdown."""
    return """# User Authentication Requirements

## Requirement 1: Login Functionality
Users must be able to log in with valid credentials.

- Navigate to login page
- Enter username and password
- Click login button
- Should redirect to dashboard

## Requirement 2: Logout Functionality
Users must be able to log out.

- Click logout button
- Should redirect to login page
- Session should be cleared
"""


@pytest.fixture
def sample_llm_response() -> str:
    """Provide a sample valid LLM response."""
    return json.dumps(
        {
            "test_cases": [
                {
                    "title": "User Login with Valid Credentials",
                    "preconditions": ["User has valid credentials"],
                    "steps": [
                        {"number": 1, "action": "Navigate to /login", "target": "login page"},
                        {
                            "number": 2,
                            "action": "Enter username",
                            "target": "username field",
                            "data": "testuser",
                        },
                        {"number": 3, "action": "Click login", "target": "login button"},
                    ],
                    "expected_results": ["Dashboard loads"],
                    "automation_hints": ["Use #username selector"],
                    "tags": ["smoke"],
                }
            ]
        }
    )


class TestPromptTemplate:
    """Tests for prompt template formatting."""

    def test_prompt_template_renders_correctly(self, sample_requirements: str) -> None:
        """Test that prompt template formats with requirements."""
        from ai_qa.prompts.test_extraction import format_test_extraction_prompt

        prompt = format_test_extraction_prompt(sample_requirements)

        assert "User Authentication Requirements" in prompt
        assert "## Requirements Document" in prompt
        assert "## Output Format" in prompt
        assert "test_cases" in prompt


class TestLLMResponseParsing:
    """Tests for parsing LLM responses."""

    def test_extract_json_from_markdown_code_block(self, extractor: TestCaseExtractor) -> None:
        """Test JSON extraction from markdown code blocks."""
        content = '```json\n{"test_cases": []}\n```'
        result = extractor._extract_json(content)
        assert result == '{"test_cases": []}'

    def test_extract_json_from_plain_text(self, extractor: TestCaseExtractor) -> None:
        """Test JSON extraction from plain text without code blocks."""
        content = '{"test_cases": [{"title": "Test"}]}'
        result = extractor._extract_json(content)
        assert result == content

    def test_extract_json_with_extra_text(self, extractor: TestCaseExtractor) -> None:
        """Test JSON extraction when wrapped in extra text."""
        content = 'Some explanation text\n```json\n{"test_cases": []}\n```\nMore text'
        result = extractor._extract_json(content)
        assert result == '{"test_cases": []}'

    def test_parse_single_test_case(self, extractor: TestCaseExtractor) -> None:
        """Test parsing a single test case from JSON."""
        data = {
            "title": "Login Test",
            "preconditions": ["User exists"],
            "steps": [
                {"number": 1, "action": "Navigate", "target": "page", "data": None},
            ],
            "expected_results": ["Success"],
            "automation_hints": ["Use #id"],
            "tags": ["regression"],
        }

        test_case = extractor._parse_single_test_case(data)

        assert test_case.title == "Login Test"
        assert test_case.preconditions == ["User exists"]
        assert len(test_case.steps) == 1
        assert test_case.steps[0].action == "Navigate"
        assert test_case.steps[0].target == "page"
        assert test_case.expected_results == ["Success"]
        assert test_case.automation_hints == ["Use #id"]
        assert test_case.tags == ["regression"]

    def test_parse_llm_response_valid_json(
        self, extractor: TestCaseExtractor, sample_llm_response: str
    ) -> None:
        """Test parsing valid LLM response."""
        test_cases = extractor._parse_llm_response(sample_llm_response)

        assert len(test_cases) == 1
        assert test_cases[0].title == "User Login with Valid Credentials"
        assert len(test_cases[0].steps) == 3

    def test_parse_llm_response_invalid_json(self, extractor: TestCaseExtractor) -> None:
        """Test parsing invalid JSON raises PipelineError."""
        from ai_qa.exceptions import PipelineError

        with pytest.raises(PipelineError, match="invalid JSON"):
            extractor._parse_llm_response("not valid json")

    def test_parse_llm_response_missing_test_cases_key(self, extractor: TestCaseExtractor) -> None:
        """Test parsing JSON without test_cases key raises PipelineError."""
        from ai_qa.exceptions import PipelineError

        with pytest.raises(PipelineError, match="test_cases"):
            extractor._parse_llm_response('{"other": []}')


class TestConfidenceScoring:
    """Tests for confidence scoring algorithms."""

    def test_compute_single_confidence_complete_test_case(
        self, extractor: TestCaseExtractor
    ) -> None:
        """Test confidence for complete test case."""
        test_case = TestCase(
            title="Complete Test",
            preconditions=["Condition 1"],
            steps=[TestCaseStep(number=1, action="Click", target="button")],
            expected_results=["Result 1"],
            automation_hints=["Hint 1"],
        )

        confidence = extractor._compute_single_confidence(test_case)
        assert confidence == 1.0

    def test_compute_single_confidence_minimal_test_case(
        self, extractor: TestCaseExtractor
    ) -> None:
        """Test confidence for minimal test case."""
        test_case = TestCase(
            title="Minimal",
            steps=[TestCaseStep(number=1, action="Click", target="button")],
        )

        confidence = extractor._compute_single_confidence(test_case)
        # Title (0.2) + steps with valid actions (0.3 + 0.1 bonus) = 0.6
        assert confidence == 0.6

    def test_compute_single_confidence_empty_test_case(self, extractor: TestCaseExtractor) -> None:
        """Test confidence for empty test case."""
        test_case = TestCase(title="Untitled Test Case")

        confidence = extractor._compute_single_confidence(test_case)
        assert confidence == 0.0

    def test_compute_overall_confidence(self, extractor: TestCaseExtractor) -> None:
        """Test overall confidence computation."""
        test_cases = [
            TestCase(title="TC1", steps=[TestCaseStep(number=1, action="A", target="T")]),
            TestCase(title="TC2", steps=[TestCaseStep(number=1, action="B", target="U")]),
        ]

        confidence = extractor._compute_confidence(test_cases)
        assert 0.5 < confidence <= 1.0


class TestFilenameGeneration:
    """Tests for filename generation from test case title."""

    def test_filename_simple_title(self) -> None:
        """Test filename from simple title."""
        test_case = TestCase(title="User Login Flow")
        assert test_case.filename == "user-login-flow"

    def test_filename_special_characters(self) -> None:
        """Test filename with special characters."""
        test_case = TestCase(title="Test: User Login (Valid Credentials!)")
        assert test_case.filename == "test-user-login-valid-credentials"

    def test_filename_multiple_spaces(self) -> None:
        """Test filename with multiple spaces."""
        test_case = TestCase(title="Multiple   Spaces   Here")
        assert test_case.filename == "multiple-spaces-here"


class TestTestCaseExtractorExtract:
    """Tests for TestCaseExtractor.extract method."""

    @pytest.mark.asyncio
    async def test_extract_missing_file(self, extractor: TestCaseExtractor) -> None:
        """Test extraction with non-existent file."""
        result = await extractor.extract(Path("/nonexistent/file.md"))

        assert result.success is False
        assert result.confidence == 0.0
        assert len(result.errors) == 1
        assert "not found" in result.errors[0]

    @pytest.mark.asyncio
    async def test_extract_empty_file(
        self, extractor: TestCaseExtractor, output_base_dir: Path
    ) -> None:
        """Test extraction with empty requirements file."""
        req_file = output_base_dir.parent / "requirements" / "empty.md"
        req_file.parent.mkdir(parents=True, exist_ok=True)
        req_file.write_text("")

        result = await extractor.extract(req_file)

        assert result.success is True
        assert result.data == []
        assert len(result.warnings) == 1
        assert "Empty" in result.warnings[0]

    @pytest.mark.asyncio
    @patch("ai_qa.pipelines.test_case_extractor.LLMClient")
    async def test_extract_success(
        self,
        mock_client_class,
        extractor: TestCaseExtractor,
        output_base_dir: Path,
        sample_llm_response: str,
    ) -> None:
        """Test successful extraction with mocked LLM."""
        # Setup mock
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = sample_llm_response
        mock_client.invoke.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Create requirements file
        req_file = output_base_dir.parent / "requirements" / "test.md"
        req_file.parent.mkdir(parents=True, exist_ok=True)
        req_file.write_text("# Requirements\n\nLogin feature")

        result = await extractor.extract(req_file, source_url="https://example.com/page")

        assert result.success is True
        assert result.data is not None
        assert len(result.data) == 1
        assert result.data[0].title == "User Login with Valid Credentials"

    @pytest.mark.asyncio
    @patch("ai_qa.pipelines.test_case_extractor.LLMClient")
    async def test_extract_llm_error(
        self, mock_client_class, extractor: TestCaseExtractor, output_base_dir: Path
    ) -> None:
        """Test extraction when LLM raises error."""
        # Setup mock to raise exception
        mock_client = MagicMock()
        mock_client.invoke.side_effect = LLMError("API timeout")
        mock_client_class.return_value = mock_client

        # Create requirements file
        req_file = output_base_dir.parent / "requirements" / "test.md"
        req_file.parent.mkdir(parents=True, exist_ok=True)
        req_file.write_text("# Requirements\n\nLogin feature")

        result = await extractor.extract(req_file)

        assert result.success is False
        assert len(result.errors) == 1


class TestTestCaseExtractorBatch:
    """Tests for TestCaseExtractor.extract_batch method."""

    @pytest.mark.asyncio
    @patch("ai_qa.pipelines.test_case_extractor.LLMClient")
    async def test_extract_batch_multiple_files(
        self,
        mock_client_class,
        extractor: TestCaseExtractor,
        output_base_dir: Path,
        sample_llm_response: str,
    ) -> None:
        """Test batch extraction with multiple files."""
        # Setup mock
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = sample_llm_response
        mock_client.invoke.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Create requirements files
        req_dir = output_base_dir.parent / "requirements"
        req_dir.mkdir(parents=True, exist_ok=True)

        req_file1 = req_dir / "req1.md"
        req_file2 = req_dir / "req2.md"
        req_file1.write_text("# Req 1")
        req_file2.write_text("# Req 2")

        result = await extractor.extract_batch(
            [req_file1, req_file2], source_urls=["https://example.com/1", "https://example.com/2"]
        )

        assert result.success is True
        assert result.data is not None
        assert len(result.data) == 2  # 2 files x 1 test case each

    @pytest.mark.asyncio
    async def test_extract_batch_mismatched_urls(
        self, extractor: TestCaseExtractor, output_base_dir: Path
    ) -> None:
        """Test batch extraction with mismatched URL list raises error."""
        from ai_qa.exceptions import PipelineError

        req_file = output_base_dir.parent / "requirements" / "test.md"
        req_file.parent.mkdir(parents=True, exist_ok=True)
        req_file.write_text("# Test")

        with pytest.raises(PipelineError, match="source_urls length"):
            await extractor.extract_batch([req_file], source_urls=["url1", "url2"])
