"""Tests for VisionLocator pipeline stage.

Tests the VisionLocator class with mocked BrowserAgent.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_qa.config import AppSettings
from ai_qa.exceptions import NavigationError, VisionError
from ai_qa.models import TestCase, TestCaseStep
from ai_qa.pipelines.vision_locator import (
    SelectorInfo,
    VisionLocator,
)


@pytest.fixture
def mock_browser_agent() -> MagicMock:
    """Create a mock BrowserAgent."""
    agent = MagicMock()
    agent.agent = MagicMock()
    agent.agent.page = MagicMock()
    agent.navigate = AsyncMock()
    return agent


@pytest.fixture
def vision_config() -> AppSettings:
    """Create AppSettings with vision enabled."""
    return AppSettings(
        vision_enabled=True,
        vision_model="sonnet",
        vision_timeout=60,
        vision_screenshot_quality=85,
        locator_validation_enabled=True,
        vision_fallback_on_error=True,
    )


@pytest.fixture
def vision_locator(mock_browser_agent: MagicMock, vision_config: AppSettings) -> VisionLocator:
    """Create a VisionLocator with mocked dependencies."""
    return VisionLocator(
        browser_agent=mock_browser_agent,
        config=vision_config,
    )


@pytest.fixture
def sample_test_case() -> TestCase:
    """Create a sample test case for testing."""
    return TestCase(
        title="Test User Login",
        preconditions=["User is on login page"],
        steps=[
            TestCaseStep(
                number=1,
                action="Enter username in username field",
                target="username input field",
                data="testuser123",
            ),
            TestCaseStep(
                number=2,
                action="Enter password in password field",
                target="password input field",
                data="securepass456",
            ),
            TestCaseStep(
                number=3,
                action="Click login button",
                target="login button",
            ),
        ],
        expected_results=["User is logged in successfully", "Dashboard is displayed"],
    )


class TestVisionLocatorInitialization:
    """Test suite for VisionLocator initialization."""

    def test_initialization_with_browser_agent(
        self, mock_browser_agent: MagicMock, vision_config: AppSettings
    ) -> None:
        """Test that VisionLocator initializes correctly with BrowserAgent."""
        locator = VisionLocator(
            browser_agent=mock_browser_agent,
            config=vision_config,
        )

        assert locator.browser_agent == mock_browser_agent
        assert locator.config == vision_config
        assert locator._vision_enabled is True
        assert locator._validation_enabled is True

    def test_initialization_vision_disabled(self, mock_browser_agent: MagicMock) -> None:
        """Test that VisionLocator respects disabled vision config."""
        config = AppSettings(vision_enabled=False)
        locator = VisionLocator(
            browser_agent=mock_browser_agent,
            config=config,
        )

        assert locator._vision_enabled is False


class TestVisionLocatorIdentifyLocators:
    """Test suite for identify_locators method."""

    async def test_identify_locators_success(
        self,
        vision_locator: VisionLocator,
        mock_browser_agent: MagicMock,
        sample_test_case: TestCase,
    ) -> None:
        """Test successful locator identification."""
        # Mock screenshot
        mock_page = mock_browser_agent.agent.page
        mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot_data")

        # Mock vision analysis response
        mock_llm = MagicMock()
        mock_browser_agent.agent.llm = mock_llm
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content='{"element_found": true, "element_type": "input", "attributes": {"data-testid": "username-field"}, "confidence": 0.9}'
            )
        )

        # Mock DOM validation
        mock_page.query_selector_all = AsyncMock(return_value=[MagicMock()])

        result = await vision_locator.identify_locators(
            sample_test_case, "https://example.com/login"
        )

        assert result.success is True
        assert result.data is not None
        assert len(result.data) == 3  # One result per step
        mock_browser_agent.navigate.assert_called_once_with("https://example.com/login")

    async def test_identify_locators_navigation_failure(
        self,
        vision_locator: VisionLocator,
        mock_browser_agent: MagicMock,
        sample_test_case: TestCase,
    ) -> None:
        """Test handling of navigation failure."""
        mock_browser_agent.navigate.side_effect = NavigationError(
            "Failed to navigate",
            details="Timeout",
        )

        result = await vision_locator.identify_locators(
            sample_test_case, "https://example.com/login"
        )

        assert result.success is False
        assert result.data is None
        assert len(result.errors) > 0
        assert "Navigation failed" in result.errors[0]

    async def test_identify_locators_vision_disabled(
        self,
        mock_browser_agent: MagicMock,
        sample_test_case: TestCase,
    ) -> None:
        """Test that vision-disabled config returns appropriate result."""
        config = AppSettings(vision_enabled=False)
        locator = VisionLocator(
            browser_agent=mock_browser_agent,
            config=config,
        )

        result = await locator.identify_locators(sample_test_case, "https://example.com/login")

        assert result.success is True
        assert result.data is None
        assert len(result.warnings) > 0
        assert "Vision analysis disabled" in result.warnings[0]
        # Navigation should not be attempted when vision is disabled
        mock_browser_agent.navigate.assert_not_called()

    async def test_identify_locators_empty_steps(
        self,
        vision_locator: VisionLocator,
        sample_test_case: TestCase,
    ) -> None:
        """Test handling of test case with no steps."""
        sample_test_case.steps = []

        result = await vision_locator.identify_locators(
            sample_test_case, "https://example.com/login"
        )

        assert result.success is True
        assert result.data == []
        assert "No test steps provided" in result.warnings[0]


class TestVisionLocatorScreenshotCapture:
    """Test suite for screenshot capture."""

    async def test_capture_screenshot_success(
        self,
        vision_locator: VisionLocator,
        mock_browser_agent: MagicMock,
    ) -> None:
        """Test successful screenshot capture."""
        mock_page = mock_browser_agent.agent.page
        mock_page.screenshot = AsyncMock(return_value=b"fake_screenshot_data")

        result = await vision_locator._capture_screenshot()

        assert result == b"fake_screenshot_data"
        mock_page.screenshot.assert_called_once_with(
            type="jpeg",
            quality=85,
            full_page=False,
        )

    async def test_capture_screenshot_no_page(
        self,
        vision_locator: VisionLocator,
        mock_browser_agent: MagicMock,
    ) -> None:
        """Test screenshot capture when page is not available."""
        mock_browser_agent.agent.page = None

        with pytest.raises(VisionError) as exc_info:
            await vision_locator._capture_screenshot()

        assert "Browser page not available" in str(exc_info.value)

    async def test_capture_screenshot_empty_data(
        self,
        vision_locator: VisionLocator,
        mock_browser_agent: MagicMock,
    ) -> None:
        """Test screenshot capture returns empty data."""
        mock_page = mock_browser_agent.agent.page
        mock_page.screenshot = AsyncMock(return_value=None)

        with pytest.raises(VisionError) as exc_info:
            await vision_locator._capture_screenshot()

        assert "Screenshot capture returned empty data" in str(exc_info.value)


class TestVisionLocatorVisionAnalysis:
    """Test suite for vision model analysis."""

    async def test_analyze_with_vision_success(
        self,
        vision_locator: VisionLocator,
        mock_browser_agent: MagicMock,
    ) -> None:
        """Test successful vision analysis."""
        mock_llm = MagicMock()
        mock_browser_agent.agent.llm = mock_llm
        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(
                content='{"element_found": true, "element_type": "button", "attributes": {"data-testid": "submit-btn"}, "confidence": 0.95}'
            )
        )

        step = TestCaseStep(number=1, action="Click submit", target="submit button")
        result = await vision_locator._analyze_with_vision(b"fake_image", step)

        assert result["element_found"] is True
        assert result["element_type"] == "button"
        assert result["attributes"]["data-testid"] == "submit-btn"
        assert result["confidence"] == 0.95

    async def test_analyze_with_vision_no_llm(
        self,
        vision_locator: VisionLocator,
        mock_browser_agent: MagicMock,
    ) -> None:
        """Test vision analysis when LLM is not available."""
        mock_browser_agent.agent.llm = None

        step = TestCaseStep(number=1, action="Click submit", target="submit button")

        with pytest.raises(VisionError) as exc_info:
            await vision_locator._analyze_with_vision(b"fake_image", step)

        # Error should mention vision model or LLM not being available
        error_str = str(exc_info.value)
        assert (
            "Vision model" in error_str or "not available" in error_str or "'NoneType'" in error_str
        )


class TestVisionLocatorSelectorExtraction:
    """Test suite for selector extraction."""

    def test_extract_selectors_with_data_testid(
        self,
        vision_locator: VisionLocator,
    ) -> None:
        """Test selector extraction with data-testid attribute."""
        vision_analysis = {
            "element_found": True,
            "element_type": "input",
            "text_content": "Username",
            "attributes": {
                "data-testid": "username-input",
                "role": "textbox",
            },
        }
        step = TestCaseStep(number=1, action="Enter username", target="username field")

        selectors = vision_locator._extract_selectors(vision_analysis, step)

        assert len(selectors) > 0
        assert selectors[0].type == "data-testid"
        assert selectors[0].value == "username-input"
        assert selectors[0].confidence == 0.95

    def test_extract_selectors_without_attributes(
        self,
        vision_locator: VisionLocator,
    ) -> None:
        """Test selector extraction with minimal vision data."""
        vision_analysis = {
            "element_found": True,
            "element_type": "button",
            "text_content": "Submit",
        }
        step = TestCaseStep(number=1, action="Click submit", target="submit button")

        selectors = vision_locator._extract_selectors(vision_analysis, step)

        # Should have at least text-based selector
        assert len(selectors) > 0
        text_selectors = [s for s in selectors if s.type == "text"]
        assert len(text_selectors) > 0
        assert text_selectors[0].value == "Submit"


class TestVisionLocatorDOMValidation:
    """Test suite for DOM validation."""

    async def test_validate_selectors_unique_match(
        self,
        vision_locator: VisionLocator,
        mock_browser_agent: MagicMock,
    ) -> None:
        """Test validation with unique selector match."""
        mock_page = mock_browser_agent.agent.page
        mock_page.query_selector_all = AsyncMock(return_value=[MagicMock()])

        selectors = [
            SelectorInfo(type="data-testid", value="unique-id", confidence=0.9, validated=False),
        ]

        validated = await vision_locator._validate_selectors(selectors)

        assert len(validated) == 1
        assert validated[0].validated is True
        assert validated[0].confidence > selectors[0].confidence  # Should increase

    async def test_validate_selectors_ambiguous(
        self,
        vision_locator: VisionLocator,
        mock_browser_agent: MagicMock,
    ) -> None:
        """Test validation with ambiguous (multiple) matches."""
        mock_page = mock_browser_agent.agent.page
        mock_page.query_selector_all = AsyncMock(return_value=[MagicMock(), MagicMock()])

        selectors = [
            SelectorInfo(type="css", value=".common-class", confidence=0.7, validated=False),
        ]

        validated = await vision_locator._validate_selectors(selectors)

        assert len(validated) == 1
        assert validated[0].validated is False
        assert validated[0].confidence < selectors[0].confidence  # Should decrease

    async def test_validate_selectors_not_found(
        self,
        vision_locator: VisionLocator,
        mock_browser_agent: MagicMock,
    ) -> None:
        """Test validation when selector matches no elements."""
        mock_page = mock_browser_agent.agent.page
        mock_page.query_selector_all = AsyncMock(return_value=[])

        selectors = [
            SelectorInfo(type="data-testid", value="missing-id", confidence=0.8, validated=False),
        ]

        validated = await vision_locator._validate_selectors(selectors)

        assert len(validated) == 1
        assert validated[0].validated is False
        assert validated[0].confidence < selectors[0].confidence


class TestVisionLocatorConfidenceCalculation:
    """Test suite for confidence calculation."""

    def test_calculate_locator_confidence_with_validated_selectors(
        self,
        vision_locator: VisionLocator,
    ) -> None:
        """Test confidence calculation with validated selectors."""
        selectors = [
            SelectorInfo(type="data-testid", value="id1", confidence=0.9, validated=True),
            SelectorInfo(type="role", value="button", confidence=0.8, validated=True),
        ]

        confidence = vision_locator._calculate_locator_confidence(selectors, "valid")

        # Valid status gives good confidence
        assert confidence > 0.5

    def test_calculate_locator_confidence_not_found(
        self,
        vision_locator: VisionLocator,
    ) -> None:
        """Test confidence calculation when elements not found."""
        selectors = [
            SelectorInfo(type="css", value=".missing", confidence=0.5, validated=False),
        ]

        confidence = vision_locator._calculate_locator_confidence(selectors, "not_found")

        # Not found gives lower confidence
        assert confidence < 0.6

    def test_determine_validation_status_valid(
        self,
        vision_locator: VisionLocator,
    ) -> None:
        """Test validation status determination - valid case."""
        selectors = [
            SelectorInfo(type="data-testid", value="id1", confidence=0.9, validated=True),
        ]

        status = vision_locator._determine_validation_status(selectors)

        assert status == "valid"

    def test_determine_validation_status_ambiguous(
        self,
        vision_locator: VisionLocator,
    ) -> None:
        """Test validation status determination - ambiguous case."""
        selectors = [
            SelectorInfo(type="css", value=".class1", confidence=0.7, validated=True),
            SelectorInfo(type="css", value=".class2", confidence=0.6, validated=True),
        ]

        status = vision_locator._determine_validation_status(selectors)

        assert status == "ambiguous"

    def test_determine_validation_status_not_found(
        self,
        vision_locator: VisionLocator,
    ) -> None:
        """Test validation status determination - not found case."""
        selectors = [
            SelectorInfo(type="css", value=".missing", confidence=0.3, validated=False),
        ]

        status = vision_locator._determine_validation_status(selectors)

        assert status == "not_found"


class TestVisionLocatorHelperMethods:
    """Test suite for helper methods."""

    def test_convert_to_playwright_selector_data_testid(
        self,
        vision_locator: VisionLocator,
    ) -> None:
        """Test conversion of data-testid selector."""
        selector = SelectorInfo(type="data-testid", value="my-id", confidence=0.9)

        result = vision_locator._convert_to_playwright_selector(selector)

        assert result == "[data-testid='my-id']"

    def test_convert_to_playwright_selector_role(
        self,
        vision_locator: VisionLocator,
    ) -> None:
        """Test conversion of role selector."""
        selector = SelectorInfo(type="role", value="button", confidence=0.8)

        result = vision_locator._convert_to_playwright_selector(selector)

        assert result == "role=button"

    def test_convert_to_playwright_selector_text(
        self,
        vision_locator: VisionLocator,
    ) -> None:
        """Test conversion of text selector."""
        selector = SelectorInfo(type="text", value="Click me", confidence=0.7)

        result = vision_locator._convert_to_playwright_selector(selector)

        assert result == "text=Click me"

    def test_build_vision_prompt(self, vision_locator: VisionLocator) -> None:
        """Test vision prompt building."""
        step = TestCaseStep(
            number=1,
            action="Enter username",
            target="username field",
            data="testuser",
        )

        prompt = vision_locator._build_vision_prompt(step)

        assert "Enter username" in prompt
        assert "username field" in prompt
        assert "testuser" in prompt
        assert "JSON format" in prompt

    def test_parse_vision_response_with_json(self, vision_locator: VisionLocator) -> None:
        """Test parsing vision response with JSON content."""
        response = '{"element_found": true, "element_type": "button"}'

        result = vision_locator._parse_vision_response(response)

        assert result["element_found"] is True
        assert result["element_type"] == "button"

    def test_parse_vision_response_with_markdown(self, vision_locator: VisionLocator) -> None:
        """Test parsing vision response with markdown JSON block."""
        response = '```json\n{"element_found": true, "confidence": 0.9}\n```'

        result = vision_locator._parse_vision_response(response)

        assert result["element_found"] is True
        assert result["confidence"] == 0.9

    def test_parse_vision_response_invalid_json(self, vision_locator: VisionLocator) -> None:
        """Test parsing vision response with invalid JSON."""
        response = "The element is a button with data-testid='submit'"

        result = vision_locator._parse_vision_response(response)

        # Should return fallback structure
        assert "element_found" in result
        assert "element_type" in result

    def test_infer_element_type_button(self, vision_locator: VisionLocator) -> None:
        """Test element type inference - button."""
        result = vision_locator._infer_element_type("This is a clickable button element")
        assert result == "button"

    def test_infer_element_type_input(self, vision_locator: VisionLocator) -> None:
        """Test element type inference - input."""
        result = vision_locator._infer_element_type("Text input field for username")
        assert result == "input"

    def test_infer_element_type_unknown(self, vision_locator: VisionLocator) -> None:
        """Test element type inference - unknown."""
        result = vision_locator._infer_element_type("Some generic element")
        assert result == "unknown"


class TestVisionLocatorProcessFunction:
    """Test suite for the module-level process function."""

    @patch("ai_qa.pipelines.vision_locator.VisionLocator")
    async def test_process_function(
        self,
        mock_vision_locator_class: MagicMock,
        mock_browser_agent: MagicMock,
        sample_test_case: TestCase,
    ) -> None:
        """Test the process function entry point."""
        mock_instance = MagicMock()
        mock_instance.identify_locators = AsyncMock(
            return_value=MagicMock(success=True, data=[], errors=[], warnings=[])
        )
        mock_vision_locator_class.return_value = mock_instance

        from ai_qa.pipelines.vision_locator import process

        config = AppSettings(vision_enabled=True)
        _ = await process(
            sample_test_case,
            "https://example.com",
            mock_browser_agent,
            config,
        )

        mock_vision_locator_class.assert_called_once_with(mock_browser_agent, config)
        mock_instance.identify_locators.assert_called_once_with(
            sample_test_case, "https://example.com"
        )
