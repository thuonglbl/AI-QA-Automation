"""Tests for the TestCaseExtractor pipeline stage."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_qa.ai_connection.config import LLMConfig
from ai_qa.exceptions import LLMError
from ai_qa.models import TestCase, TestCaseStep
from ai_qa.pipelines.test_case_extractor import (
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    RequirementSource,
    StreamingArrayObjects,
    TestCaseExtractor,
    _content_to_text,
)


def _astream_of(chunks: list[str], raise_at: int | None = None):
    """Build a fake LLMClient.astream that yields content chunks (optionally erroring)."""

    async def _astream(messages, **kwargs):  # noqa: ANN001, ANN003
        for i, piece in enumerate(chunks):
            if raise_at is not None and i == raise_at:
                raise LLMError("stream broke")
            yield SimpleNamespace(content=piece)

    return _astream


class TestStreamingArrayObjects:
    """The incremental JSON-array object parser used for streamed generation."""

    def test_extracts_objects_from_whole_buffer(self) -> None:
        parser = StreamingArrayObjects()
        out = parser.feed('{"test_cases": [{"title": "A"}, {"title": "B"}]}')
        assert [json.loads(o)["title"] for o in out] == ["A", "B"]

    def test_extracts_across_chunk_boundaries(self) -> None:
        parser = StreamingArrayObjects()
        collected: list[str] = []
        for piece in ['{"test_ca', 'ses": [{"ti', 'tle": "A"}, {"title"', ': "B"}]}']:
            collected.extend(parser.feed(piece))
        assert [json.loads(o)["title"] for o in collected] == ["A", "B"]

    def test_braces_inside_strings_do_not_break_parsing(self) -> None:
        parser = StreamingArrayObjects()
        out = parser.feed('{"test_cases": [{"title": "a}b{c", "x": "esc\\"}"}]}')
        assert len(out) == 1
        assert json.loads(out[0])["title"] == "a}b{c"

    def test_ignores_preamble_before_array(self) -> None:
        parser = StreamingArrayObjects()
        out = parser.feed('Here you go:\n```json\n{"test_cases": [{"title": "A"}]}\n```')
        assert [json.loads(o)["title"] for o in out] == ["A"]

    def test_prose_mention_of_test_cases_does_not_misalign(self) -> None:
        """A bare `"test_cases"` + `[` in prose must NOT anchor — only the real key does."""
        parser = StreamingArrayObjects()
        out = parser.feed(
            'I will write the "test_cases" [in a list]: {"test_cases": [{"title": "Real"}]}'
        )
        assert [json.loads(o)["title"] for o in out] == ["Real"]


class TestContentNormalization:
    """_content_to_text handles Anthropic list-of-blocks content (not just str)."""

    def test_str_passthrough(self) -> None:
        assert _content_to_text("hello") == "hello"

    def test_list_of_text_blocks_concatenated(self) -> None:
        content = [{"type": "text", "text": "abc"}, {"type": "text", "text": "def"}]
        assert _content_to_text(content) == "abcdef"

    def test_non_text_blocks_skipped(self) -> None:
        content = [
            {"type": "thinking", "thinking": "hmm"},
            {"type": "text", "text": "real"},
            {"type": "tool_use", "name": "x"},
        ]
        assert _content_to_text(content) == "real"


_TWO_CASES = json.dumps({"test_cases": [{"title": "Case One"}, {"title": "Case Two"}]})


class TestExtractStreaming:
    """extract_streaming surfaces each case via on_case and returns the full list."""

    @pytest.mark.asyncio
    @patch("ai_qa.pipelines.test_case_extractor.LLMClient")
    async def test_streams_each_case_to_callback(
        self, mock_client_class, extractor: TestCaseExtractor, output_base_dir: Path
    ) -> None:
        mock_client = MagicMock()
        # Stream the JSON in two chunks so objects complete mid-stream.
        split = _TWO_CASES.index("}, {") + 2
        mock_client.astream = _astream_of([_TWO_CASES[:split], _TWO_CASES[split:]])
        mock_client_class.return_value = mock_client

        req = output_base_dir.parent / "requirements" / "s.md"
        req.parent.mkdir(parents=True, exist_ok=True)
        req.write_text("# Req")

        seen: list[str] = []

        async def on_case(tc: TestCase) -> None:
            seen.append(tc.title)

        source = RequirementSource(id="r1", name="r1/requirement.md", url="https://x/1")
        result = await extractor.extract_streaming([req], sources=[source], on_case=on_case)

        assert result.success is True
        assert seen == ["Case One", "Case Two"]  # delivered incrementally, in order
        assert result.data is not None
        assert [tc.title for tc in result.data] == ["Case One", "Case Two"]
        # Source attribution + confidence are stamped on streamed cases.
        assert all(tc.source_requirement_id == "r1" for tc in result.data)
        assert all(tc.confidence_level in ("high", "medium", "low") for tc in result.data)

    @pytest.mark.asyncio
    @patch("ai_qa.pipelines.test_case_extractor.LLMClient")
    async def test_falls_back_to_non_streaming_when_stream_errors_early(
        self, mock_client_class, extractor: TestCaseExtractor, output_base_dir: Path
    ) -> None:
        """A stream that errors before any object falls back to a single non-stream call."""
        mock_client = MagicMock()
        # raise_at=0 fires before the first chunk is yielded → nothing streamed.
        mock_client.astream = _astream_of(["unused"], raise_at=0)
        mock_client.ainvoke = AsyncMock(return_value=SimpleNamespace(content=_TWO_CASES))
        mock_client_class.return_value = mock_client

        req = output_base_dir.parent / "requirements" / "s2.md"
        req.parent.mkdir(parents=True, exist_ok=True)
        req.write_text("# Req")

        seen: list[str] = []

        async def on_case(tc: TestCase) -> None:
            seen.append(tc.title)

        result = await extractor.extract_streaming([req], on_case=on_case)

        assert result.success is True
        assert result.data is not None
        assert [tc.title for tc in result.data] == ["Case One", "Case Two"]
        assert seen == ["Case One", "Case Two"]  # fallback still drives the callback

    @pytest.mark.asyncio
    @patch("ai_qa.pipelines.test_case_extractor.LLMClient")
    async def test_handles_anthropic_list_content_chunks(
        self, mock_client_class, extractor: TestCaseExtractor, output_base_dir: Path
    ) -> None:
        """Regression: Claude streams content as a LIST of blocks, not str — must parse."""

        async def _astream_list(messages, **kwargs):  # noqa: ANN001, ANN003
            split = _TWO_CASES.index("}, {") + 2
            for piece in [_TWO_CASES[:split], _TWO_CASES[split:]]:
                # Anthropic AIMessageChunk content shape:
                yield SimpleNamespace(content=[{"type": "text", "text": piece}])

        mock_client = MagicMock()
        mock_client.astream = _astream_list
        mock_client_class.return_value = mock_client

        req = output_base_dir.parent / "requirements" / "s3.md"
        req.parent.mkdir(parents=True, exist_ok=True)
        req.write_text("# Req")

        result = await extractor.extract_streaming([req])

        assert result.success is True
        assert result.data is not None
        assert [tc.title for tc in result.data] == ["Case One", "Case Two"]


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


def _make_full_tc(**kwargs: object) -> TestCase:
    """Build a structurally complete TestCase (all AC1 fields present)."""
    defaults: dict[str, object] = {
        "title": "Full Test Case",
        "objective": "Verify the login flow",
        "preconditions": ["User has valid credentials"],
        "test_data": ["user@example.com", "Password123"],
        "steps": [TestCaseStep(number=1, action="Navigate to login", target="the login page")],
        "expected_results": ["Dashboard is displayed"],
    }
    defaults.update(kwargs)
    return TestCase(**defaults)  # type: ignore[arg-type]


class TestConfidenceScoring:
    """Tests for the _assess_confidence deterministic engine (12.3 algorithm)."""

    def test_complete_case_scores_high(self, extractor: TestCaseExtractor) -> None:
        """A structurally complete, warning-free case scores >= HIGH_THRESHOLD and is 'high'."""
        tc = _make_full_tc()
        score, level, rationale = extractor._assess_confidence(tc, source_warnings=None)
        assert score >= CONFIDENCE_HIGH_THRESHOLD
        assert level == "high"
        # Positive note must be present
        assert any("All structural fields present" in r for r in rationale)

    def test_minimal_case_scores_lower_with_gap_rationale(
        self, extractor: TestCaseExtractor
    ) -> None:
        """A minimal case (title + steps only) produces a lower score with gap rationale."""
        tc = TestCase(
            title="Minimal",
            steps=[TestCaseStep(number=1, action="Click", target="the button")],
        )
        score, level, rationale = extractor._assess_confidence(tc, source_warnings=None)
        # Must be below HIGH (missing objective, expected_results, preconditions, test_data)
        assert score < CONFIDENCE_HIGH_THRESHOLD
        assert "No objective stated" in rationale
        assert "No expected results" in rationale[0] or any(
            "expected" in r.lower() for r in rationale
        )

    def test_per_case_warning_forces_low_regardless_of_structure(
        self, extractor: TestCaseExtractor
    ) -> None:
        """A case with per-case warnings is forced to 'low' even if structurally complete."""
        tc = _make_full_tc(warnings=["Ambiguous UI target in step 1: 'the form button'"])
        score, level, rationale = extractor._assess_confidence(tc, source_warnings=None)
        assert level == "low"
        # Rationale must explain the override (structural score is high)
        assert any("Flagged LOW" in r for r in rationale)
        # The warning itself must appear in rationale
        assert any("Ambiguous UI target" in r for r in rationale)

    def test_override_rationale_uses_post_penalty_score(self, extractor: TestCaseExtractor) -> None:
        """The 'Flagged LOW' override message must quote the POST-penalty score (== tc.confidence).

        A structurally complete case (structural_score 1.00) with two per-case warnings
        takes a 0.30 penalty, so the displayed/stored score is 0.70. The override rationale
        must read 0.70 (the value shown to the reviewer), NOT the pre-penalty 1.00 — otherwise
        the message contradicts the score stored on the test case.
        """
        tc = _make_full_tc(warnings=["Ambiguous target A", "Ambiguous target B"])
        score, level, rationale = extractor._assess_confidence(tc, source_warnings=None)
        assert level == "low"
        assert score == pytest.approx(0.70)
        # The override message must be present and must quote the post-penalty score.
        override = next((r for r in rationale if "Flagged LOW" in r), None)
        assert override is not None
        assert "0.70" in override
        assert "1.00" not in override

    def test_source_warning_forces_low(self, extractor: TestCaseExtractor) -> None:
        """A case with source/Bob warnings is forced to 'low' and carries the cause."""
        tc = _make_full_tc()
        source_warnings = [
            {
                "category": "vague_language",
                "message": "requirement uses vague terms",
                "location": "section 2",
                "impact": "low",
            }
        ]
        score, level, rationale = extractor._assess_confidence(tc, source_warnings=source_warnings)
        assert level == "low"
        assert any("Source requirement issue (vague_language)" in r for r in rationale)

    def test_high_threshold_boundary(self, extractor: TestCaseExtractor) -> None:
        """A case missing only preconditions lands above HIGH_THRESHOLD and maps to 'high'."""
        # title(0.15) + objective(0.15) + steps(0.20+0.10) + expected(0.20)
        #   + test_data(0.10, awarded because no step carries data) = 0.90.
        # Only preconditions(0.10) is missing, so the score sits at 0.90 (>= 0.80 HIGH).
        tc = TestCase(
            title="Boundary Test",
            objective="Check boundary",
            steps=[TestCaseStep(number=1, action="Click", target="the button")],
            expected_results=["Done"],
        )
        score, level, rationale = extractor._assess_confidence(tc, source_warnings=None)
        assert score == pytest.approx(0.90)
        assert score >= CONFIDENCE_HIGH_THRESHOLD
        assert level == "high"

    def test_medium_band(self, extractor: TestCaseExtractor) -> None:
        """Score between MEDIUM and HIGH thresholds maps to 'medium'."""
        # title(0.15) + steps(0.20+0.10) + expected(0.20)
        #   + test_data(0.10, awarded because no step carries data) = 0.75, no warnings.
        # Missing objective(0.15) and preconditions(0.10) keep it below 0.80 HIGH.
        tc = TestCase(
            title="Medium Case",
            steps=[TestCaseStep(number=1, action="Do it", target="the thing")],
            expected_results=["Result"],
        )
        score, level, rationale = extractor._assess_confidence(tc, source_warnings=None)
        assert score == pytest.approx(0.75)
        assert CONFIDENCE_MEDIUM_THRESHOLD <= score < CONFIDENCE_HIGH_THRESHOLD
        assert level == "medium"

    def test_compute_confidence_averages_stamped_scores(self, extractor: TestCaseExtractor) -> None:
        """_compute_confidence averages the already-stamped tc.confidence values."""
        tc1 = TestCase(title="TC1", confidence=0.9)
        tc2 = TestCase(title="TC2", confidence=0.5)
        avg = extractor._compute_confidence([tc1, tc2])
        assert abs(avg - 0.7) < 0.001

    def test_compute_confidence_none_treated_as_zero(self, extractor: TestCaseExtractor) -> None:
        """_compute_confidence treats None confidence as 0.0."""
        tc1 = TestCase(title="TC1", confidence=None)
        tc2 = TestCase(title="TC2", confidence=0.8)
        avg = extractor._compute_confidence([tc1, tc2])
        assert abs(avg - 0.4) < 0.001


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
        mock_client.ainvoke = AsyncMock(return_value=mock_response)
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
        mock_client.ainvoke = AsyncMock(side_effect=LLMError("API timeout"))
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
        mock_client.ainvoke = AsyncMock(return_value=mock_response)
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


class TestCaseModel:
    """Tests for the extended TestCase model (AC1/AC2/AC3 fields)."""

    def test_new_fields_have_defaults(self) -> None:
        """Existing constructors keep working with all-default new fields."""
        tc = TestCase(title="Minimal")
        assert tc.objective == ""
        assert tc.test_data == []
        assert tc.source_requirement_id is None
        assert tc.source_requirement_name is None
        assert tc.source_url is None
        assert tc.feature_area is None
        assert tc.warnings == []

    def test_new_fields_round_trip_model_dump(self) -> None:
        """All new fields survive model_dump() / model_dump_json() round-trip."""
        tc = TestCase(
            title="Login Flow",
            objective="Verify login with valid credentials",
            test_data=["user@example.com", "Password123!"],
            source_requirement_id="abc-uuid-123",
            source_requirement_name="login/requirement.md",
            source_url="https://confluence.example.com/page/123",
            feature_area="Authentication",
            warnings=["Ambiguous UI target in step 2: 'submit the form'"],
        )
        dumped = tc.model_dump()
        assert dumped["objective"] == "Verify login with valid credentials"
        assert dumped["test_data"] == ["user@example.com", "Password123!"]
        assert dumped["source_requirement_id"] == "abc-uuid-123"
        assert dumped["source_requirement_name"] == "login/requirement.md"
        assert dumped["source_url"] == "https://confluence.example.com/page/123"
        assert dumped["feature_area"] == "Authentication"
        assert dumped["warnings"] == ["Ambiguous UI target in step 2: 'submit the form'"]

    def test_new_fields_round_trip_model_dump_json(self) -> None:
        """New fields persist correctly when serialized to JSON (artifact save path)."""
        import json

        tc = TestCase(
            title="Search Feature",
            objective="Verify search returns relevant results",
            test_data=["laptop", "phone"],
            source_requirement_id="req-999",
            feature_area="Search",
            warnings=["Step 4: target 'the search box' is ambiguous"],
        )
        as_json = json.loads(tc.model_dump_json())
        assert as_json["objective"] == "Verify search returns relevant results"
        assert as_json["test_data"] == ["laptop", "phone"]
        assert as_json["source_requirement_id"] == "req-999"
        assert as_json["warnings"] == ["Step 4: target 'the search box' is ambiguous"]

    def test_existing_fixture_still_works(self) -> None:
        """Existing TestCase constructors (without new fields) still produce valid objects."""
        tc = TestCase(
            title="Existing Test",
            preconditions=["Precondition"],
            steps=[TestCaseStep(number=1, action="Click", target="button")],
            expected_results=["Result"],
            automation_hints=["Hint"],
            tags=["smoke"],
        )
        assert tc.title == "Existing Test"
        assert tc.objective == ""
        assert tc.test_data == []
        assert tc.warnings == []

    def test_confidence_fields_default_to_none(self) -> None:
        """Confidence fields are None/empty by default (backward-compat with pre-12.3)."""
        tc = TestCase(title="Existing")
        assert tc.confidence is None
        assert tc.confidence_level is None
        assert tc.confidence_rationale == []

    def test_confidence_fields_round_trip_model_dump(self) -> None:
        """Confidence triple round-trips through model_dump() / model_dump_json()."""
        import json

        tc = TestCase(
            title="Scored Case",
            confidence=0.75,
            confidence_level="medium",
            confidence_rationale=["No preconditions specified", "No objective stated"],
        )
        dumped = tc.model_dump()
        assert dumped["confidence"] == 0.75
        assert dumped["confidence_level"] == "medium"
        assert dumped["confidence_rationale"] == [
            "No preconditions specified",
            "No objective stated",
        ]

        as_json = json.loads(tc.model_dump_json())
        assert as_json["confidence"] == 0.75
        assert as_json["confidence_level"] == "medium"


class TestPromptTemplateNewFields:
    """Tests for the rewritten extraction prompt (AC2: no invented selectors)."""

    def test_prompt_contains_new_schema_fields(self, sample_requirements: str) -> None:
        """Prompt schema includes objective, test_data, feature_area, warnings."""
        from ai_qa.prompts.test_extraction import format_test_extraction_prompt

        prompt = format_test_extraction_prompt(sample_requirements)
        assert "objective" in prompt
        assert "test_data" in prompt
        assert "feature_area" in prompt
        assert "warnings" in prompt

    def test_prompt_forbids_invented_selectors(self, sample_requirements: str) -> None:
        """Prompt must NOT instruct using data-testid, CSS selectors, or XPaths as targets."""
        from ai_qa.prompts.test_extraction import format_test_extraction_prompt

        prompt = format_test_extraction_prompt(sample_requirements)
        # The old selector guidance must be gone
        assert "data-testid" not in prompt
        assert "#username" not in prompt
        assert "[data-testid" not in prompt
        assert "CSS selectors" not in prompt.lower()

    def test_prompt_instructs_plain_language_targets(self, sample_requirements: str) -> None:
        """Prompt must instruct plain-language UI descriptions, not selectors."""
        from ai_qa.prompts.test_extraction import format_test_extraction_prompt

        prompt = format_test_extraction_prompt(sample_requirements)
        assert "plain" in prompt.lower() or "plain-language" in prompt.lower()

    def test_prompt_instructs_ambiguity_warnings(self, sample_requirements: str) -> None:
        """Prompt must instruct model to emit warnings for ambiguous UI targets."""
        from ai_qa.prompts.test_extraction import format_test_extraction_prompt

        prompt = format_test_extraction_prompt(sample_requirements)
        # Must mention warnings for ambiguous targets
        assert "ambiguous" in prompt.lower() or "ambiguity" in prompt.lower()
        assert "warnings" in prompt.lower()


class TestParseNewFields:
    """Tests for _parse_single_test_case reading new LLM fields (AC1/AC2)."""

    def test_parse_new_fields_populated(self, extractor: TestCaseExtractor) -> None:
        """_parse_single_test_case reads objective, test_data, feature_area, warnings."""
        data = {
            "title": "Search Test",
            "objective": "Verify search returns results",
            "test_data": ["laptop", "phone"],
            "feature_area": "Search",
            "role": "Admin",
            "warnings": ["Step 2: 'the search box' is ambiguous"],
            "preconditions": [],
            "steps": [],
            "expected_results": [],
            "automation_hints": [],
            "tags": [],
        }
        tc = extractor._parse_single_test_case(data)
        assert tc.objective == "Verify search returns results"
        assert tc.test_data == ["laptop", "phone"]
        assert tc.feature_area == "Search"
        assert tc.role == "Admin"
        assert tc.warnings == ["Step 2: 'the search box' is ambiguous"]

    def test_parse_new_fields_default_when_absent(self, extractor: TestCaseExtractor) -> None:
        """New fields fall back to defaults when absent in LLM JSON."""
        data = {
            "title": "Minimal Test",
            "steps": [],
            "expected_results": [],
        }
        tc = extractor._parse_single_test_case(data)
        assert tc.objective == ""
        assert tc.test_data == []
        assert tc.feature_area is None
        assert tc.role is None
        assert tc.warnings == []

    def test_parse_role_blank_normalized_to_none(self, extractor: TestCaseExtractor) -> None:
        """A blank/whitespace role from the LLM becomes None (no empty sub-folder)."""
        data = {"title": "T", "role": "   ", "steps": [], "expected_results": []}
        tc = extractor._parse_single_test_case(data)
        assert tc.role is None

    def test_parse_warnings_entry_survives(self, extractor: TestCaseExtractor) -> None:
        """A warnings entry for an ambiguous target is preserved through parsing."""
        data = {
            "title": "Form Submission",
            "objective": "Test form submit",
            "warnings": [
                "Ambiguous UI target in step 3: 'submit the form' — exact control not specified"
            ],
            "steps": [
                {"number": 1, "action": "Fill in the name field", "target": "the name input field"},
                {
                    "number": 2,
                    "action": "Fill in the email field",
                    "target": "the email input field",
                },
                {"number": 3, "action": "Submit", "target": "the submit button"},
            ],
            "expected_results": ["Form submitted"],
        }
        tc = extractor._parse_single_test_case(data)
        assert len(tc.warnings) == 1
        assert "Ambiguous UI target" in tc.warnings[0]


class TestRequirementSourceStamping:
    """Tests for RequirementSource stamping in extract/extract_batch (AC1/AC3)."""

    @pytest.mark.asyncio
    @patch("ai_qa.pipelines.test_case_extractor.LLMClient")
    async def test_extract_stamps_source_on_test_cases(
        self,
        mock_client_class,
        extractor: TestCaseExtractor,
        output_base_dir: Path,
        sample_llm_response: str,
    ) -> None:
        """extract() with a RequirementSource stamps source_requirement_id/name/source_url."""
        from ai_qa.pipelines.test_case_extractor import RequirementSource

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = sample_llm_response
        mock_client.ainvoke = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        req_file = output_base_dir.parent / "requirements" / "req1.md"
        req_file.parent.mkdir(parents=True, exist_ok=True)
        req_file.write_text("# Login Requirements")

        source = RequirementSource(
            id="req-uuid-001",
            name="login/requirement.md",
            url="https://example.com/page/1",
        )
        result = await extractor.extract(req_file, source=source)

        assert result.success is True
        assert result.data is not None
        for tc in result.data:
            assert tc.source_requirement_id == "req-uuid-001"
            assert tc.source_requirement_name == "login/requirement.md"
            assert tc.source_url == "https://example.com/page/1"

    @pytest.mark.asyncio
    @patch("ai_qa.pipelines.test_case_extractor.LLMClient")
    async def test_extract_without_source_leaves_fields_none(
        self,
        mock_client_class,
        extractor: TestCaseExtractor,
        output_base_dir: Path,
        sample_llm_response: str,
    ) -> None:
        """extract() without source keeps source fields at None (backward-compat)."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = sample_llm_response
        mock_client.ainvoke = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        req_file = output_base_dir.parent / "requirements" / "req2.md"
        req_file.parent.mkdir(parents=True, exist_ok=True)
        req_file.write_text("# Requirements")

        result = await extractor.extract(req_file)
        assert result.success is True
        for tc in result.data or []:
            assert tc.source_requirement_id is None

    @pytest.mark.asyncio
    @patch("ai_qa.pipelines.test_case_extractor.LLMClient")
    async def test_extract_batch_with_sources_stamps_correctly(
        self,
        mock_client_class,
        extractor: TestCaseExtractor,
        output_base_dir: Path,
        sample_llm_response: str,
    ) -> None:
        """extract_batch() zips sources with paths and stamps each set of cases."""
        from ai_qa.pipelines.test_case_extractor import RequirementSource

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = sample_llm_response
        mock_client.ainvoke = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        req_dir = output_base_dir.parent / "requirements"
        req_dir.mkdir(parents=True, exist_ok=True)
        req1 = req_dir / "req1.md"
        req2 = req_dir / "req2.md"
        req1.write_text("# Req1")
        req2.write_text("# Req2")

        sources = [
            RequirementSource(id="id-001", name="req1/requirement.md", url="https://ex.com/1"),
            RequirementSource(id="id-002", name="req2/requirement.md", url="https://ex.com/2"),
        ]
        result = await extractor.extract_batch([req1, req2], sources=sources)

        assert result.success is True
        assert result.data is not None
        # Each file yields 1 test case (per sample_llm_response)
        assert len(result.data) == 2
        assert result.data[0].source_requirement_id == "id-001"
        assert result.data[1].source_requirement_id == "id-002"

    @pytest.mark.asyncio
    async def test_extract_batch_sources_length_mismatch_raises(
        self,
        extractor: TestCaseExtractor,
        output_base_dir: Path,
    ) -> None:
        """extract_batch() raises PipelineError when sources length mismatches paths."""
        from ai_qa.exceptions import PipelineError
        from ai_qa.pipelines.test_case_extractor import RequirementSource

        req_dir = output_base_dir.parent / "requirements"
        req_dir.mkdir(parents=True, exist_ok=True)
        req1 = req_dir / "r1.md"
        req1.write_text("# R1")

        sources = [
            RequirementSource(id="id-001", name="r1/requirement.md", url=""),
            RequirementSource(id="id-002", name="r2/requirement.md", url=""),
        ]
        with pytest.raises(PipelineError, match="sources length"):
            await extractor.extract_batch([req1], sources=sources)

    @pytest.mark.asyncio
    @patch("ai_qa.pipelines.test_case_extractor.LLMClient")
    async def test_extract_stamps_confidence_on_cases(
        self,
        mock_client_class,
        extractor: TestCaseExtractor,
        output_base_dir: Path,
        sample_llm_response: str,
    ) -> None:
        """extract() stamps confidence/level/rationale on every returned case."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = sample_llm_response
        mock_client.ainvoke = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        req_file = output_base_dir.parent / "requirements" / "stamping.md"
        req_file.parent.mkdir(parents=True, exist_ok=True)
        req_file.write_text("# Requirements")

        result = await extractor.extract(req_file)

        assert result.success is True
        for tc in result.data or []:
            assert tc.confidence is not None
            assert tc.confidence_level in ("high", "medium", "low")
            assert isinstance(tc.confidence_rationale, list)
            assert len(tc.confidence_rationale) > 0

    @pytest.mark.asyncio
    @patch("ai_qa.pipelines.test_case_extractor.LLMClient")
    async def test_extract_with_source_warnings_forces_low(
        self,
        mock_client_class,
        extractor: TestCaseExtractor,
        output_base_dir: Path,
        sample_llm_response: str,
    ) -> None:
        """extract() with source warnings forces level='low' on all cases."""
        from ai_qa.pipelines.test_case_extractor import RequirementSource

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = sample_llm_response
        mock_client.ainvoke = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        req_file = output_base_dir.parent / "requirements" / "warn.md"
        req_file.parent.mkdir(parents=True, exist_ok=True)
        req_file.write_text("# Requirements")

        source = RequirementSource(
            id="req-1",
            name="req/requirement.md",
            url="",
            warnings=[
                {
                    "category": "vague_language",
                    "message": "too vague",
                    "location": "body",
                    "impact": "medium",
                }
            ],
        )
        result = await extractor.extract(req_file, source=source)

        assert result.success is True
        for tc in result.data or []:
            assert tc.confidence_level == "low"
            assert any("Source requirement issue" in r for r in tc.confidence_rationale)
