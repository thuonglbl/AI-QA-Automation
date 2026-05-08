"""Prompt templates for Playwright script generation.

This module contains prompt templates used by the ScriptGenerator to convert
test cases into executable Playwright Python scripts.
"""

SCRIPT_GENERATION_SYSTEM_PROMPT = """You are an expert Playwright test automation engineer specializing in Python.

Your task is to convert structured test cases into complete, executable Playwright Python test scripts.

Key principles:
1. Generate clean, maintainable Python code following pytest conventions
2. Prefer stable selectors: data-testid > role-based > accessibility > CSS > XPath
3. Include proper assertions that match expected results from the test case
4. Add appropriate waits using Playwright's auto-waiting mechanisms
5. Follow Playwright best practices for reliability and maintainability

Output only valid Python code without markdown formatting or explanations."""

SCRIPT_GENERATION_PROMPT = """Convert the following structured test case into a complete Playwright Python test script.

Test Case (JSON format):
{test_case}

Requirements for the generated script:

1. **Function Definition**: Create a pytest test function with signature:
   ```python
   def test_<descriptive_name>(page: Page):
   ```

2. **Stable Selectors** (use in this priority order):
   - `page.get_by_test_id("...")` - Most stable, preferred when available
   - `page.get_by_role("button", name="...")` - Role-based selectors
   - `page.get_by_text("...")` - Text-based selectors
   - `page.get_by_label("...")` - Label-based selectors
   - `page.get_by_placeholder("...")` - Placeholder-based selectors
   - `page.locator("...")` - CSS selectors (use only when necessary)
   - `page.locator("xpath=...")` - XPath (last resort, avoid if possible)

3. **Actions**: Convert each test step to appropriate Playwright actions:
   - Navigation: `page.goto(url)`
   - Clicking: `element.click()`
   - Typing: `element.fill(text)` or `element.press_sequentially(text, delay=50)`
   - Selecting: `element.select_option(value)`
   - Waiting: Use implicit waits or `element.wait_for()`

4. **Assertions**: Map expected results to Playwright assertions:
   - "Verify X is visible" → `expect(element).to_be_visible()`
   - "Check Y equals Z" → `expect(element).to_have_text("Z")`
   - "Confirm button is disabled" → `expect(button).to_be_disabled()`
   - "Validate URL contains X" → `expect(page).to_have_url(re.compile(".*X.*"))`
   - "Verify element exists" → `expect(element).to_be_attached()`
   - "Check element count" → `expect(elements).to_have_count(n)`

5. **Structure**:
   - Include docstring describing what the test verifies
   - Add comments for each major step referencing the original test step number
   - Use descriptive variable names
   - Handle preconditions at the start of the test

6. **Error Handling**:
   - Use Playwright's built-in auto-waiting and retry mechanisms
   - Add explicit waits only when necessary for timing issues
   - Use `expect(...).to_be_visible(timeout=10000)` for custom timeouts

7. **Best Practices**:
   - One action per line for clarity
   - Chain locators for specificity: `page.get_by_test_id("form").get_by_role("button")`
   - Use `expect()` for all assertions (not `assert`)
   - Prefer user-visible selectors (text, role) over implementation details

Output ONLY the Python test function code. Do not include markdown code blocks or explanations. The code should be ready to run with pytest and Playwright."""

# Additional specialized prompts for specific scenarios
SCRIPT_GENERATION_WITH_HINTS_PROMPT = """Convert the following structured test case into a complete Playwright Python test script.

Test Case (JSON format):
{test_case}

This test case includes automation hints - USE THESE HINTS for selector strategies:
- If data-testid hints are provided, prioritize using `get_by_test_id()`
- If role-based hints are provided, use `get_by_role()` with the specified roles
- If accessibility hints are provided, use accessibility selectors

Requirements for the generated script:

1. **Function Definition**: Create a pytest test function with signature:
   ```python
   def test_<descriptive_name>(page: Page):
   ```

2. **Selector Strategy** (follow this priority):
   - Use hints from automation_hints field when available
   - `page.get_by_test_id("...")` - Most stable, preferred
   - `page.get_by_role("...", name="...")` - Role-based
   - `page.get_by_text("...")` - Text-based
   - `page.get_by_label("...")` - Label-based
   - `page.locator("...")` - CSS selectors (when necessary)
   - `page.locator("xpath=...")` - XPath (last resort)

3. **Actions**: Convert each test step to Playwright actions with appropriate waits

4. **Assertions**: Map all expected_results to corresponding expect() assertions

5. **Structure**: Include docstring, step comments, descriptive variable names

6. **Error Handling**: Use Playwright's auto-waiting, add explicit waits only when needed

Output ONLY the Python test function code, ready to run with pytest and Playwright."""

SELECTOR_GUIDANCE_PROMPT = """When selecting elements in Playwright, follow this stability hierarchy:

MOST STABLE (use first if available):
1. `page.get_by_test_id("unique-id")` - data-testid attributes
2. `page.get_by_role("button", name="Submit")` - ARIA roles with names
3. `page.get_by_text("Visible Text")` - Visible text content

MODERATELY STABLE:
4. `page.get_by_label("Field Label")` - Associated label text
5. `page.get_by_placeholder("Enter name...")` - Placeholder text
6. `page.get_by_title("Tooltip text")` - Title attributes

LESS STABLE (avoid if possible):
7. `page.locator("#css-id")` - CSS ID selectors
8. `page.locator(".css-class")` - CSS class selectors
9. `page.locator("div > button:nth-child(2)")` - Structural CSS

LEAST STABLE (last resort):
10. `page.locator("xpath=//div[@class='btn']")` - XPath expressions

When generating scripts, always try the most stable options first before falling back to less stable selectors."""

VISION_ASSISTED_SCRIPT_GENERATION_PROMPT = """Convert the following structured test case into a complete Playwright Python test script.

Test Case (JSON format):
{test_case}

Visual Analysis Results:
{vision_context}

The vision model has analyzed the target application and identified the following UI elements:

{locator_info}

When generating the script:
1. **PRIORITIZE** the vision-identified selectors - they have been verified against the actual DOM
2. Use selectors in this order of preference:
   - `data-testid` (most stable, if confidence > 0.8)
   - `get_by_role()` with name (ARIA roles verified by vision)
   - `get_by_text()` for elements with clear text labels
   - CSS selectors only as fallback

3. **Confidence-based decisions**:
   - High confidence (>0.8): Use directly, add assertion
   - Medium confidence (0.5-0.8): Use with wait or retry
   - Low confidence (<0.5): Add comment, use alternative selector

4. Include comments referencing the vision analysis for each element used.

Generate complete, runnable Playwright Python code following standard patterns."""

VISION_SCRIPT_GENERATION_SYSTEM_PROMPT = """You are an expert Playwright test automation engineer with access to visual analysis results.

Your task is to convert test cases into executable Playwright Python scripts using vision-verified selectors.

Key principles:
1. Trust vision analysis results for accurate element identification
2. Use the most stable selector with highest confidence from vision results
3. Add appropriate waits for elements identified as potentially dynamic
4. Include assertions that verify expected outcomes
5. Comment each selector with its confidence score and source

Output only valid Python code without markdown formatting."""

ASSERTION_MAPPING_GUIDE = """Map expected results from test cases to Playwright assertions:

Visibility and Display:
- "X should be visible" → `expect(element).to_be_visible()`
- "X should be hidden" → `expect(element).to_be_hidden()`
- "X should exist" → `expect(element).to_be_attached()`

Text Content:
- "X displays 'text'" → `expect(element).to_have_text("text")`
- "X contains 'text'" → `expect(element).to_contain_text("text")`
- "X has value 'val'" → `expect(element).to_have_value("val")`

State:
- "button should be enabled" → `expect(button).to_be_enabled()`
- "button should be disabled" → `expect(button).to_be_disabled()`
- "checkbox should be checked" → `expect(checkbox).to_be_checked()`
- "element should be focused" → `expect(element).to_be_focused()`

URL and Navigation:
- "URL should be X" → `expect(page).to_have_url("X")`
- "URL should contain X" → `expect(page).to_have_url(re.compile(".*X.*"))`
- "page title should be X" → `expect(page).to_have_title("X")`

Count and Lists:
- "list should have N items" → `expect(list_items).to_have_count(N)`

Custom Attributes:
- "element has attribute X=Y" → `expect(element).to_have_attribute("X", "Y")`

CSS:
- "element has CSS property X=Y" → `expect(element).to_have_css("X", "Y")`

Use `expect()` for all assertions - it provides auto-retrying, configurable timeouts, and clear error messages."""

__all__ = [
    "SCRIPT_GENERATION_PROMPT",
    "SCRIPT_GENERATION_SYSTEM_PROMPT",
    "SCRIPT_GENERATION_WITH_HINTS_PROMPT",
    "SELECTOR_GUIDANCE_PROMPT",
    "ASSERTION_MAPPING_GUIDE",
    "VISION_ASSISTED_SCRIPT_GENERATION_PROMPT",
    "VISION_SCRIPT_GENERATION_SYSTEM_PROMPT",
]
