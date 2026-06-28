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
6. NEVER invent selectors, URLs, credentials, or assertions when the test case does not specify them.
   Instead, insert an inline Python comment marker at that point:
   - `# TODO: <description of what concrete detail is missing>` — when a step lacks a named control, value, or URL
   - `# REVIEW: <description of the ambiguity>` — when the expected result is unclear or has multiple valid interpretations
   These are valid Python comments and are explicitly REQUIRED when detail is missing. Keep surrounding code runnable where possible.
7. Never emit credentials; reuse the existing authenticated session supplied at execution time.
8. Parameterize the application URL for environment reuse: `import os`, define a module-level `BASE_URL = os.environ["APP_BASE_URL"]`, and build every `page.goto(...)` from it (e.g. `page.goto(f"{BASE_URL}/journeys")`). NEVER hardcode the scheme+host inline, so the same script runs unchanged against any environment (local/test/integrate/production) by setting `APP_BASE_URL`.
9. **English Language**: The generated Python code, including all docstrings, variable names, and comments, MUST be written in English, regardless of the language of the test case or context.

Output only valid Python code without markdown formatting or explanations.
Inline `# TODO:` and `# REVIEW:` comments are allowed and required when details are missing — they are not explanations."""

SCRIPT_GENERATION_PROMPT = """Convert the following structured test case into a complete Playwright Python test script.

Test Case (Markdown):
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
   - **Brittle-fallback rule**: If you must fall back to CSS or XPath, add an inline `# REVIEW: Step N brittle selector — needs data-testid/role/text/label` comment on that line (N = the step number from the nearest `# Step N:` comment). Never silently emit a brittle selector.

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
   - If an expected result is **ambiguous, unsupported, or has no observable outcome**, do NOT invent an assertion — add `# REVIEW: <expected result text> — ambiguous/unsupported assertion` instead.

5. **Structure**:
   - Include docstring describing what the test verifies
   - Precede each mapped step's actions with `# Step N: <action description>` (N = the original test case step number) so warnings can be traced back to the source step
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

8. **Missing details — DO NOT invent**:
   - If a step does not specify a concrete selector, URL, credential, input value, or assertion target, do NOT fabricate one.
   - Insert `# TODO: <what is missing>` (for missing action detail) or `# REVIEW: <the ambiguity>` (for unclear expected result).
   - These inline comments are valid Python and are REQUIRED when detail is missing.

9. **Authentication & session** (MANDATORY — these rules override any step instructions):
   - **Session reuse over login:** Assume the test runs in a browser context that already has an
     authenticated SSO session (supplied at execution time). Do NOT automate interactive login —
     do not generate steps that type a username/password or click a login button to authenticate.
     If the test case includes login/sign-in steps, replace them with a brief comment that the test
     assumes an existing authenticated session, and add an inline
     `# REVIEW: SSO/session setup required before execution` comment.
   - **Never hardcode credentials:** NEVER write a literal username, password, token, cookie,
     API key, bearer token, or session secret into the script — not in `.fill()`/`.type()`, not
     in a variable, not in a header, not in a URL (`user:pass@host`), and not in
     `add_cookies(...)` or an inline `storage_state` dict. If a value is genuinely needed and
     unspecified, use a clearly-named environment-variable reference (e.g.
     `os.environ["APP_PASSWORD"]`) and add a `# REVIEW:` comment — never invent a credential.
   - **Auth-setup visibility:** If the test target appears to require authentication (a protected
     area, an "authenticated"/"logged in" precondition, or any login interaction), add a
     `# REVIEW: SSO/session setup required — run against a pre-authenticated browser context`
     comment at the top of the test body, before the first navigation step.

Output ONLY the Python test function code. Do not include markdown code blocks or explanations.
Inline `# TODO:` and `# REVIEW:` comments are allowed and required when details are missing."""

# Additional specialized prompts for specific scenarios
SCRIPT_GENERATION_WITH_HINTS_PROMPT = """Convert the following structured test case into a complete Playwright Python test script.

Test Case (Markdown):
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

When generating scripts, always try the most stable options first before falling back to less stable selectors.
If you must fall back to CSS or XPath, flag it with `# REVIEW: Step N brittle selector — needs data-testid/role/text/label`."""

VISION_ASSISTED_SCRIPT_GENERATION_PROMPT = """Convert the following structured test case into a complete Playwright Python test script.

Test Case (Markdown):
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
   - Low confidence (<0.5): Insert `# REVIEW: low-confidence selector — <element description>`, use best available alternative
   - **CSS/XPath fallback** (any confidence): If you must use a CSS or XPath locator (no stable `get_by_*` form available), also add `# REVIEW: Step N brittle selector — needs data-testid/role/text/label` on that line.

4. Include comments referencing the vision analysis for each element used.

5. **Missing details — DO NOT invent**:
   - If a step has no concrete selector, URL, credential, or assertion target in the test case or vision results, do NOT fabricate one.
   - Insert `# TODO: <what is missing>` or `# REVIEW: <the ambiguity>` at that point.
   - These inline Python comments are required when detail is missing.
   - If an expected result is ambiguous, unsupported, or has no observable outcome, do NOT invent an assertion — add `# REVIEW: <expected result text> — ambiguous/unsupported assertion` instead.

6. **Authentication & session** (MANDATORY — these rules override any step instructions):
   - **Session reuse over login:** Assume the test runs in a browser context that already has an
     authenticated SSO session (supplied at execution time). Do NOT automate interactive login —
     do not generate steps that type a username/password or click a login button to authenticate.
     If the test case includes login/sign-in steps, replace them with a brief comment that the test
     assumes an existing authenticated session, and add an inline
     `# REVIEW: SSO/session setup required before execution` comment.
   - **Never hardcode credentials:** NEVER write a literal username, password, token, cookie,
     API key, bearer token, or session secret into the script — not in `.fill()`/`.type()`, not
     in a variable, not in a header, not in a URL (`user:pass@host`), and not in
     `add_cookies(...)` or an inline `storage_state` dict. If a value is genuinely needed and
     unspecified, use a clearly-named environment-variable reference (e.g.
     `os.environ["APP_PASSWORD"]`) and add a `# REVIEW:` comment — never invent a credential.
   - **Auth-setup visibility:** If the test target appears to require authentication (a protected
     area, an "authenticated"/"logged in" precondition, or any login interaction), add a
     `# REVIEW: SSO/session setup required — run against a pre-authenticated browser context`
     comment at the top of the test body, before the first navigation step.

Generate complete, runnable Playwright Python code following standard patterns.
Inline `# TODO:` and `# REVIEW:` comments are allowed and required when details are missing."""

VISION_SCRIPT_GENERATION_SYSTEM_PROMPT = """You are an expert Playwright test automation engineer with access to visual analysis results.

Your task is to convert test cases into executable Playwright Python scripts using vision-verified selectors.

Key principles:
1. Trust vision analysis results for accurate element identification
2. Use the most stable selector with highest confidence from vision results
3. Add appropriate waits for elements identified as potentially dynamic
4. Include assertions that verify expected outcomes
5. Comment each selector with its confidence score and source
6. NEVER invent selectors, URLs, credentials, or assertions when the test case does not specify them.
   Insert `# TODO: <what is missing>` or `# REVIEW: <the ambiguity>` at that point instead.
   These are valid Python comments and are explicitly REQUIRED when detail is missing.
7. Never emit credentials; reuse the existing authenticated session supplied at execution time.
8. Parameterize the application URL for environment reuse: `import os`, define a module-level `BASE_URL = os.environ["APP_BASE_URL"]`, and build every `page.goto(...)` from it. NEVER hardcode the scheme+host inline, so the same script runs unchanged against any environment by setting `APP_BASE_URL`.

Output only valid Python code without markdown formatting.
Inline `# TODO:` and `# REVIEW:` comments are allowed and required when details are missing."""

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

Use `expect()` for all assertions - it provides auto-retrying, configurable timeouts, and clear error messages.
If an expected result is ambiguous or has no observable outcome, add `# REVIEW: <expected result text> — ambiguous/unsupported assertion` instead of inventing one."""

TRACE_TO_PLAYWRIGHT_SYSTEM_PROMPT = """You are an expert Playwright test automation engineer specializing in Python.

A browser-use agent has ALREADY executed this test against the real application and recorded a verified action trace. Each trace step includes the action it performed AND the REAL DOM element it interacted with (its tag, attributes such as data-testid/id/role/aria-label/name/placeholder/text, and xpath).

Your task is to TRANSLATE that verified trace into a clean, deterministic Playwright pytest script. The flow already works — do not invent steps, selectors, or assertions that are not grounded in the trace or the test case.

Key principles:
1. Build every locator from the REAL element attributes in the trace, in this preference order: get_by_test_id (data-testid) > get_by_role(name=…) (role + aria-label/text) > get_by_text > get_by_label > get_by_placeholder > CSS id/name > locator("xpath=…") (last resort).
2. Map trace actions to Playwright: navigate/go_to_url → page.goto(url); click → .click(); input_text/type → .fill(text); select → .select_option(...). Skip browser-use bookkeeping actions (done, wait, scroll, extract) unless they carry a meaningful assertion.
3. Map the test case's expected_results to expect(...) assertions. If an expected result is ambiguous or has no observable outcome in the trace, add `# REVIEW: <expected result> — ambiguous/unsupported assertion` instead of inventing one.
4. The output is a DETERMINISTIC regression script — no browser_use import, no AI agent, just Playwright.
5. Never emit credentials; reuse the existing authenticated SSO session supplied at execution time. Do NOT automate interactive login; if the trace contains login typing, replace it with a `# REVIEW: SSO/session setup required before execution` comment.
6. Parameterize the application URL for environment reuse: `import os`, define a module-level `BASE_URL = os.environ["APP_BASE_URL"]`, and build every `page.goto(...)` from it (derive the path from the trace's navigate URL, not its host). NEVER hardcode the scheme+host inline, so the same script runs unchanged against any environment by setting `APP_BASE_URL`.

Output only valid Python code without markdown formatting or explanations.
Inline `# TODO:` and `# REVIEW:` comments are allowed and required when a detail is genuinely missing."""

TRACE_TO_PLAYWRIGHT_PROMPT = """Translate the following VERIFIED browser-use exploration trace into a complete, deterministic Playwright Python test script.

Test Case (Markdown):
{test_case}

Verified action trace (real actions + real DOM elements captured during a successful run):
{trace}

Requirements:

1. **Function**: `def test_<descriptive_name>(page: Page):` with a docstring describing what is verified.

2. **Real selectors only**: For each interacted element, choose the most stable locator from its REAL attributes, in order: `get_by_test_id` (data-testid) > `get_by_role("<role>", name="<aria-label/text>")` > `get_by_text` > `get_by_label` > `get_by_placeholder` > CSS (`#id`, `[name="…"]`) > `locator("xpath=…")`. Because these come from a real run, do NOT invent or guess — use what the trace recorded.
   - If you can only build a CSS/XPath locator, add `# REVIEW: Step N brittle selector — needs data-testid/role/text/label` on that line.

3. **Actions**: Convert trace steps in order. `go_to_url`/`navigate` → `page.goto("<url>")`; `click_element_by_index`/`click` → `<locator>.click()`; `input_text` → `<locator>.fill("<text>")`; `select_dropdown_option` → `<locator>.select_option(...)`. Precede each with `# Step N: <description>` mapped to the test case step where possible.

4. **Assertions**: Map every test-case expected_result to an `expect(...)` assertion (visibility/text/value/url/count). Use `expect()`, never bare `assert`.

5. **Auth & session** (MANDATORY — override any step): assume a pre-authenticated SSO session; never automate login; NEVER hardcode a username/password/token/cookie/secret (not in `.fill()`, a variable, a header, a URL, `add_cookies`, or `storage_state`). If a protected area is involved, add `# REVIEW: SSO/session setup required — run against a pre-authenticated browser context` before the first navigation.

6. **Missing detail — do NOT invent**: if the trace + test case lack a concrete selector/value/assertion, insert `# TODO:`/`# REVIEW:` instead of fabricating.

Output ONLY the Python test function code (imports + function). No markdown code fences, no explanations."""

__all__ = [
    "SCRIPT_GENERATION_PROMPT",
    "SCRIPT_GENERATION_SYSTEM_PROMPT",
    "SCRIPT_GENERATION_WITH_HINTS_PROMPT",
    "SELECTOR_GUIDANCE_PROMPT",
    "ASSERTION_MAPPING_GUIDE",
    "VISION_ASSISTED_SCRIPT_GENERATION_PROMPT",
    "VISION_SCRIPT_GENERATION_SYSTEM_PROMPT",
    "TRACE_TO_PLAYWRIGHT_PROMPT",
    "TRACE_TO_PLAYWRIGHT_SYSTEM_PROMPT",
]
