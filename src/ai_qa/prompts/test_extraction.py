"""Test case extraction prompt template.

Prompt for LLM to generate structured, browser-use-optimized test cases from requirements.
"""

TEST_CASE_EXTRACTION_PROMPT = """You are a test automation expert. Your task is to analyze the provided requirements and generate structured test cases optimized for browser automation.

## Requirements Document
{requirements}

## Instructions

Generate test cases that are:
1. **Actionable**: Each step must be a concrete browser action
2. **Atomic**: One discrete action per step
3. **Locatable**: Include hints for finding elements (selectors, test IDs)
4. **Verifiable**: Each step leads to a verifiable state

## Output Format

Return a JSON object with this structure:

```json
{{
  "test_cases": [
    {{
      "title": "User Login with Valid Credentials",
      "preconditions": [
        "User has valid credentials",
        "Login page is accessible"
      ],
      "steps": [
        {{
          "number": 1,
          "action": "Navigate to /login",
          "target": "login page",
          "data": null
        }},
        {{
          "number": 2,
          "action": "Enter username in #username field",
          "target": "username input",
          "data": "testuser123"
        }},
        {{
          "number": 3,
          "action": "Enter password in #password field",
          "target": "password input",
          "data": "TestPass123!"
        }},
        {{
          "number": 4,
          "action": "Click Login button",
          "target": "login button",
          "data": null
        }}
      ],
      "expected_results": [
        "Dashboard page loads successfully",
        "Welcome message is displayed"
      ],
      "automation_hints": [
        "Use data-testid=login-btn for login button selector",
        "Add explicit wait for dashboard to load"
      ],
      "tags": ["smoke", "login"]
    }}
  ]
}}

## Rules for Good Test Cases

### DO:
- Use CSS selectors or test IDs when available (e.g., `#username`, `[data-testid="login-btn"]`)
- Make each step a single, unambiguous action
- Include input data in the "data" field when applicable
- Provide clear expected results that can be asserted
- Add automation hints for complex selectors or timing issues

### DON'T:
- Combine multiple actions into one step
- Use vague descriptions like "fill in the form"
- Assume implicit knowledge (always specify targets)
- Skip preconditions even if they seem obvious

## Examples of Good vs Poor Steps

**Poor**: "Log in to the system"
**Good**: "Click the Login button"

**Poor**: "Fill out the registration form"
**Good**: "Enter 'john@example.com' in the #email input field"

**Poor**: "Complete the checkout process"
**Good**: "Click the Checkout button with data-testid='checkout-btn'"

## Response

Generate as many test cases as needed to thoroughly cover the requirements. Each requirement should map to at least one test case. Return ONLY the JSON response, no additional commentary.
"""


def format_test_extraction_prompt(requirements: str) -> str:
    """Format the test extraction prompt with requirements.

    Args:
        requirements: Markdown requirements text from Bob agent.

    Returns:
        Formatted prompt ready for LLM invocation.
    """
    return TEST_CASE_EXTRACTION_PROMPT.replace("{requirements}", requirements)
