# mypy: disable-error-code="misc"
"""Vision-assisted locator identification pipeline stage.

Uses browser-use vision model to identify UI element locators by analyzing
screenshots of the target application, then validates them against the DOM.
"""

import base64
import logging
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from ai_qa.browser.agent import BrowserAgent
from ai_qa.config import AppSettings
from ai_qa.exceptions import NavigationError, VisionError
from ai_qa.models import StageResult, TestCase, TestCaseStep

logger = logging.getLogger(__name__)


class SelectorInfo(BaseModel):
    """Information about a single selector.

    Attributes:
        type: Selector type (data-testid, role, text, css).
        value: The selector value/pattern.
        confidence: Confidence score for this selector (0.0-1.0).
        validated: Whether the selector was validated against DOM.
    """

    type: str = Field(description="Selector type: data-testid, role, text, css")
    value: str = Field(description="The selector value/pattern")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score for this selector")
    validated: bool = Field(default=False, description="Whether validated against DOM")

    model_config = ConfigDict(validate_assignment=True)


class LocatorResult(BaseModel):
    """Result of vision-assisted locator identification for a test step.

    Attributes:
        step_number: Step sequence number (1-indexed).
        element_description: Description of the UI element.
        selectors: Priority-ordered list of selector options.
        screenshot_region: Optional region coordinates (x, y, w, h) on screenshot.
        confidence: Overall confidence for this locator (0.0-1.0).
        validation_status: Validation status: valid, ambiguous, not_found.
    """

    step_number: int = Field(ge=1, description="Step sequence number")
    element_description: str = Field(description="Description of the UI element")
    selectors: list[SelectorInfo] = Field(
        default_factory=list, description="Priority-ordered selector options"
    )
    screenshot_region: tuple[int, int, int, int] | None = Field(
        default=None, description="Region on screenshot (x, y, w, h)"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Overall confidence for this locator")
    validation_status: str = Field(
        default="unknown",
        description="Validation status: valid, ambiguous, not_found, unknown",
    )

    model_config = ConfigDict(validate_assignment=True)


class VisionLocator:
    """Identifies UI element locators using vision model analysis.

    Uses browser-use vision capabilities to:
    1. Navigate to target pages
    2. Capture visual state (screenshots)
    3. Identify UI elements matching test case steps
    4. Extract stable selectors (data-testid, role-based)
    5. Validate locators against actual DOM

    Attributes:
        browser_agent: BrowserAgent instance for navigation and DOM access.
        config: AppSettings for vision configuration.
        _vision_enabled: Whether vision analysis is enabled.
    """

    def __init__(
        self,
        browser_agent: BrowserAgent,
        config: AppSettings,
    ) -> None:
        """Initialize the vision locator.

        Args:
            browser_agent: BrowserAgent for browser automation.
            config: AppSettings with vision configuration.
        """
        self.browser_agent = browser_agent
        self.config = config
        self._vision_enabled = getattr(config, "vision_enabled", True)
        self._validation_enabled = getattr(config, "locator_validation_enabled", True)

    async def identify_locators(
        self,
        test_case: TestCase,
        target_url: str,
    ) -> StageResult:
        """Identify locators for test case steps using vision analysis.

        Args:
            test_case: The test case containing steps to identify locators for.
            target_url: URL of the target application to analyze.

        Returns:
            StageResult with list of LocatorResult objects on success.
        """
        if not self._vision_enabled:
            return StageResult(
                success=True,
                data=None,
                errors=[],
                warnings=["Vision analysis disabled - skipping locator identification"],
                confidence=0.0,
            )

        if not test_case.steps:
            return StageResult(
                success=True,
                data=[],
                errors=[],
                warnings=["No test steps provided - no locators to identify"],
                confidence=1.0,
            )

        locator_results: list[LocatorResult] = []
        errors: list[str] = []
        warnings: list[str] = []
        total_confidence = 0.0

        try:
            # Navigate to target URL
            await self._navigate_to_url(target_url)
        except NavigationError as e:
            logger.error(f"Failed to navigate to {target_url}: {e}")
            return StageResult(
                success=False,
                data=None,
                errors=[f"Navigation failed: {e.message}"],
                warnings=[],
                confidence=0.0,
            )

        # Process each test step
        for step in test_case.steps:
            try:
                locator_result = await self._identify_step_locator(step)
                locator_results.append(locator_result)
                total_confidence += locator_result.confidence

                if locator_result.validation_status == "not_found":
                    warnings.append(
                        f"Step {step.number}: No valid locator found for '{step.target}'"
                    )
                elif locator_result.validation_status == "ambiguous":
                    warnings.append(f"Step {step.number}: Ambiguous selector for '{step.target}'")

            except VisionError as e:
                error_msg = f"Vision analysis failed for step {step.number}: {e.message}"
                logger.error(error_msg)
                errors.append(error_msg)
                if e.details:
                    logger.debug(f"Vision error details: {e.details}")
            except Exception as e:
                error_msg = f"Unexpected error analyzing step {step.number}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Calculate overall confidence
        if locator_results:
            avg_confidence = total_confidence / len(locator_results)
        else:
            avg_confidence = 0.0

        success = len(locator_results) > 0 and len(errors) < len(test_case.steps)

        return StageResult(
            success=success,
            data=locator_results if locator_results else None,
            errors=errors,
            warnings=warnings,
            confidence=avg_confidence,
        )

    async def _navigate_to_url(self, url: str) -> None:
        """Navigate to target URL with timeout handling.

        Args:
            url: Target URL to navigate to.

        Raises:
            NavigationError: If navigation fails.
        """
        try:
            await self.browser_agent.navigate(url)
            logger.info(f"Successfully navigated to {url}")
        except NavigationError:
            raise
        except Exception as e:
            raise NavigationError(
                f"Failed to navigate to {url}",
                details=str(e),
            ) from e

    async def _identify_step_locator(self, step: TestCaseStep) -> LocatorResult:
        """Identify locator for a single test step.

        Args:
            step: The test case step to identify locator for.

        Returns:
            LocatorResult with identified selectors.

        Raises:
            VisionError: If vision analysis fails.
        """
        # Capture screenshot for vision analysis
        screenshot = await self._capture_screenshot()

        # Analyze with vision model
        vision_analysis = await self._analyze_with_vision(screenshot, step)

        # Extract selectors from vision analysis
        selectors = self._extract_selectors(vision_analysis, step)

        # Validate selectors if enabled
        if self._validation_enabled and selectors:
            validated_selectors = await self._validate_selectors(selectors)
        else:
            validated_selectors = selectors

        # Determine validation status
        validation_status = self._determine_validation_status(validated_selectors)

        # Calculate confidence based on selector quality
        confidence = self._calculate_locator_confidence(validated_selectors, validation_status)

        return LocatorResult(
            step_number=step.number,
            element_description=step.target,
            selectors=validated_selectors,
            confidence=confidence,
            validation_status=validation_status,
        )

    async def _capture_screenshot(self) -> bytes:
        """Capture screenshot of current page.

        Returns:
            Screenshot image as bytes.

        Raises:
            VisionError: If screenshot capture fails.
        """
        try:
            # Access browser-use agent's page for screenshot
            agent = self.browser_agent.agent
            if not agent or not hasattr(agent, "page") or not agent.page:
                raise VisionError(
                    "Browser page not available for screenshot",
                    details="Browser agent page is None or not initialized",
                )

            page = agent.page
            screenshot = await page.screenshot(
                type="jpeg",
                quality=getattr(self.config, "vision_screenshot_quality", 85),
                full_page=False,  # Viewport only for performance
            )

            if not screenshot:
                raise VisionError("Screenshot capture returned empty data")

            logger.debug(f"Screenshot captured: {len(screenshot)} bytes")
            return screenshot  # type: ignore[no-any-return]

        except VisionError:
            raise
        except Exception as e:
            raise VisionError(
                "Failed to capture screenshot",
                details=str(e),
            ) from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _analyze_with_vision(
        self,
        screenshot: bytes,
        step: TestCaseStep,
    ) -> dict[str, Any]:
        """Analyze screenshot with vision model to identify UI elements.

        Args:
            screenshot: Screenshot image as bytes.
            step: Test case step to find elements for.

        Returns:
            Vision analysis result with identified elements.

        Raises:
            VisionError: If vision analysis fails.
        """
        try:
            # Encode screenshot for vision model
            image_b64 = base64.b64encode(screenshot).decode("utf-8")

            # Build vision prompt for element identification
            vision_prompt = self._build_vision_prompt(step)

            # Use browser-use agent's LLM for vision analysis
            agent = self.browser_agent.agent
            if not agent or not hasattr(agent, "llm"):
                raise VisionError(
                    "Vision model not available",
                    details="Browser agent LLM is not configured",
                )

            # Call vision model with image
            # Note: This uses the browser-use agent's built-in vision capabilities
            timeout = getattr(self.config, "vision_timeout", 60)

            # Format message with image for vision model
            from langchain_core.messages import BaseMessage, HumanMessage

            messages: list[BaseMessage] = [
                HumanMessage(
                    content=[
                        {"type": "text", "text": vision_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ]
                )
            ]

            # Use typed invoke method with timeout
            llm_any = cast(Any, agent.llm)
            response = await llm_any.ainvoke(messages, timeout=timeout)

            # Parse vision analysis response
            analysis = self._parse_vision_response(getattr(response, "content", str(response)))
            logger.debug(f"Vision analysis completed for step {step.number}")
            return analysis

        except VisionError:
            raise
        except Exception as e:
            raise VisionError(
                f"Vision model analysis failed: {e}",
                details=f"Step: {step.number}, Target: {step.target}",
            ) from e

    def _build_vision_prompt(self, step: TestCaseStep) -> str:
        """Build vision prompt for element identification.

        Args:
            step: Test case step to build prompt for.

        Returns:
            Vision prompt string.
        """
        return f"""Analyze this screenshot and identify the UI element for this test step:

Action: {step.action}
Target: {step.target}
{"Data: " + step.data if step.data else ""}

Identify and return the following information in JSON format:
{{
    "element_found": true/false,
    "element_type": "button|input|link|text|etc",
    "text_content": "visible text if any",
    "attributes": {{
        "data-testid": "value if present",
        "role": "ARIA role if present",
        "id": "id if present",
        "class": "CSS classes"
    }},
    "location": {{
        "x": pixel x coordinate,
        "y": pixel y coordinate,
        "width": element width,
        "height": element height
    }},
    "confidence": 0.0-1.0
}}

Focus on finding stable, testable selectors. Prioritize data-testid attributes,
then ARIA roles, then semantic HTML elements."""

    def _parse_vision_response(self, response: str | list[Any]) -> dict[str, Any]:
        """Parse vision model response into structured format.

        Args:
            response: Raw response from vision model.

        Returns:
            Parsed analysis result.
        """
        import json
        import re

        # Handle list response format
        if isinstance(response, list):
            content_parts = []
            for item in response:
                if isinstance(item, str):
                    content_parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text", "")
                    if text:
                        content_parts.append(text)
            content = "\n".join(content_parts)
        else:
            content = response

        # Try to extract JSON from response
        # Look for JSON block in markdown code blocks first
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                pass

        # Try to find raw JSON object
        json_match = re.search(r"(\{[\s\S]*\})", content)
        if json_match:
            try:
                return json.loads(json_match.group(1))  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                pass

        # Fallback: return structured info from text analysis
        return {
            "element_found": "not found" not in content.lower(),
            "element_type": self._infer_element_type(content),
            "text_content": content[:200],  # Truncate for summary
            "attributes": {},
            "confidence": 0.5,
        }

    def _infer_element_type(self, content: str) -> str:
        """Infer element type from response content.

        Args:
            content: Response content to analyze.

        Returns:
            Inferred element type.
        """
        content_lower = content.lower()
        if "button" in content_lower:
            return "button"
        if "input" in content_lower or "field" in content_lower:
            return "input"
        if "link" in content_lower or "anchor" in content_lower:
            return "link"
        if "text" in content_lower:
            return "text"
        return "unknown"

    def _extract_selectors(
        self,
        vision_analysis: dict[str, Any],
        step: TestCaseStep,
    ) -> list[SelectorInfo]:
        """Extract selector options from vision analysis.

        Args:
            vision_analysis: Parsed vision analysis result.
            step: Test case step for context.

        Returns:
            Priority-ordered list of selector options.
        """
        selectors: list[SelectorInfo] = []
        attributes = vision_analysis.get("attributes", {})
        _ = vision_analysis.get("element_type", "unknown")  # Available for future use
        text_content = vision_analysis.get("text_content", "")

        # Priority 1: data-testid (most stable)
        test_id = attributes.get("data-testid")
        if test_id:
            selectors.append(
                SelectorInfo(
                    type="data-testid",
                    value=test_id,
                    confidence=0.95,
                    validated=False,
                )
            )

        # Priority 2: ARIA role
        role = attributes.get("role")
        if role:
            # Role-based selector with name if available
            if text_content:
                selectors.append(
                    SelectorInfo(
                        type="role",
                        value=f'{role}[name="{text_content}"]',
                        confidence=0.85,
                        validated=False,
                    )
                )
            else:
                selectors.append(
                    SelectorInfo(
                        type="role",
                        value=role,
                        confidence=0.75,
                        validated=False,
                    )
                )

        # Priority 3: Text content
        if text_content and len(text_content) < 100:  # Avoid long text
            selectors.append(
                SelectorInfo(
                    type="text",
                    value=text_content,
                    confidence=0.7,
                    validated=False,
                )
            )

        # Priority 4: Element type with attributes
        element_id = attributes.get("id")
        if element_id:
            selectors.append(
                SelectorInfo(
                    type="css",
                    value=f"#{element_id}",
                    confidence=0.6,
                    validated=False,
                )
            )

        # Priority 5: CSS class if unique enough
        css_class = attributes.get("class")
        if css_class:
            # Use first class if multiple
            first_class = css_class.split()[0] if " " in css_class else css_class
            selectors.append(
                SelectorInfo(
                    type="css",
                    value=f".{first_class}",
                    confidence=0.4,
                    validated=False,
                )
            )

        # If no selectors found, create fallback based on step target
        if not selectors:
            selectors.append(
                SelectorInfo(
                    type="css",
                    value=f"[placeholder*='{step.target}']",
                    confidence=0.3,
                    validated=False,
                )
            )

        return selectors

    async def _validate_selectors(
        self,
        selectors: list[SelectorInfo],
    ) -> list[SelectorInfo]:
        """Validate selectors against actual DOM.

        Args:
            selectors: List of selectors to validate.

        Returns:
            Validated selectors with updated status.
        """
        validated: list[SelectorInfo] = []

        try:
            agent = self.browser_agent.agent
            if not agent or not hasattr(agent, "page") or not agent.page:
                # Cannot validate, return as-is
                return selectors

            page = agent.page

            for selector in selectors:
                try:
                    # Convert selector info to Playwright selector
                    pw_selector = self._convert_to_playwright_selector(selector)

                    # Query the DOM
                    elements = await page.query_selector_all(pw_selector)
                    count = len(elements)

                    if count == 1:
                        # Unique match - valid
                        validated.append(
                            SelectorInfo(
                                type=selector.type,
                                value=selector.value,
                                confidence=min(selector.confidence + 0.1, 1.0),
                                validated=True,
                            )
                        )
                    elif count > 1:
                        # Ambiguous - still usable but lower confidence
                        validated.append(
                            SelectorInfo(
                                type=selector.type,
                                value=selector.value,
                                confidence=selector.confidence * 0.7,
                                validated=False,
                            )
                        )
                    else:
                        # Not found - keep but mark invalid
                        validated.append(
                            SelectorInfo(
                                type=selector.type,
                                value=selector.value,
                                confidence=selector.confidence * 0.3,
                                validated=False,
                            )
                        )

                except Exception as e:
                    logger.debug(f"Validation error for selector {selector.value}: {e}")
                    # Keep original selector with lower confidence
                    validated.append(
                        SelectorInfo(
                            type=selector.type,
                            value=selector.value,
                            confidence=selector.confidence * 0.5,
                            validated=False,
                        )
                    )

        except Exception as e:
            logger.warning(f"DOM validation failed: {e}")
            # Return original selectors if validation fails
            return selectors

        return validated

    def _convert_to_playwright_selector(self, selector: SelectorInfo) -> str:
        """Convert SelectorInfo to Playwright selector string.

        Args:
            selector: SelectorInfo to convert.

        Returns:
            Playwright selector string.
        """
        selector_type = selector.type
        value = selector.value

        if selector_type == "data-testid":
            return f"[data-testid='{value}']"
        elif selector_type == "role":
            # Handle role with name
            if "[name=" in value:
                return f"role={value}"
            return f"role={value}"
        elif selector_type == "text":
            return f"text={value}"
        elif selector_type == "css":
            return value
        else:
            return value

    def _determine_validation_status(self, selectors: list[SelectorInfo]) -> str:
        """Determine overall validation status from selectors.

        Args:
            selectors: Validated selectors.

        Returns:
            Validation status string.
        """
        if not selectors:
            return "not_found"

        validated_count = sum(1 for s in selectors if s.validated)

        if validated_count == 0:
            return "not_found"
        elif validated_count == 1:
            return "valid"
        else:
            return "ambiguous"

    def _calculate_locator_confidence(
        self,
        selectors: list[SelectorInfo],
        validation_status: str,
    ) -> float:
        """Calculate overall confidence for locator.

        Args:
            selectors: Validated selectors.
            validation_status: Validation status.

        Returns:
            Confidence score (0.0-1.0).
        """
        if not selectors:
            return 0.0

        # Base confidence from highest-confidence selector
        best_confidence = max(s.confidence for s in selectors)

        # Adjust based on validation status
        if validation_status == "valid":
            return min(best_confidence + 0.1, 1.0)
        elif validation_status == "ambiguous":
            return best_confidence * 0.7
        else:  # not_found
            return best_confidence * 0.3


async def process(
    test_case: TestCase,
    target_url: str,
    browser_agent: BrowserAgent,
    config: AppSettings,
) -> StageResult:
    """Pipeline stage entry point for vision-assisted locator identification.

    Args:
        test_case: Test case to identify locators for.
        target_url: Target application URL.
        browser_agent: BrowserAgent for browser automation.
        config: AppSettings with vision configuration.

    Returns:
        StageResult with identified locators.
    """
    vision_locator = VisionLocator(browser_agent, config)
    return await vision_locator.identify_locators(test_case, target_url)
