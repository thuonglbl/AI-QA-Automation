"""Tests for the static Playwright script validator (Story 13.6).

Security test: the validator must NEVER create or modify files on disk.
"""

from pathlib import Path

from ai_qa.pipelines.script_validator import (
    ScriptValidationResult,
    validate_script,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_PLAYWRIGHT_SCRIPT = """
import asyncio
from playwright.async_api import async_playwright


async def test_login():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://example.com/login")
        await page.fill("#username", "alice")
        await page.click("#submit")
        await page.wait_for_url("**/dashboard")
        assert await page.title() == "Dashboard"
        await browser.close()


asyncio.run(test_login())
""".strip()


# ---------------------------------------------------------------------------
# Valid script
# ---------------------------------------------------------------------------


class TestValidScript:
    def test_valid_playwright_script_is_valid(self) -> None:
        result = validate_script(VALID_PLAYWRIGHT_SCRIPT)
        assert isinstance(result, ScriptValidationResult)
        assert result.is_valid is True
        assert result.errors == []


# ---------------------------------------------------------------------------
# Syntax errors
# ---------------------------------------------------------------------------


class TestSyntaxErrors:
    def test_missing_colon_syntax_error(self) -> None:
        bad = "def test_foo()\n    pass\n"
        result = validate_script(bad)
        assert result.is_valid is False
        assert len(result.errors) == 1
        err = result.errors[0]
        assert err.code == "syntax"
        assert err.line is not None
        assert "syntax error" in err.message.lower()

    def test_unclosed_paren_syntax_error(self) -> None:
        bad = "x = (1 + 2\n"
        result = validate_script(bad)
        assert result.is_valid is False
        assert result.errors[0].code == "syntax"

    def test_syntax_error_stops_unsafe_scan(self) -> None:
        """Only syntax error returned — no unsafe-pattern scan on broken tree."""
        bad = "import subprocess\ndef bad(\n    pass\n"
        result = validate_script(bad)
        assert result.is_valid is False
        # Only the syntax error; subprocess not checked on unparseable tree
        assert all(e.code == "syntax" for e in result.errors)


# ---------------------------------------------------------------------------
# Unsafe pattern detection
# ---------------------------------------------------------------------------


class TestUnsafePatterns:
    def test_import_subprocess_flagged(self) -> None:
        script = f"{VALID_PLAYWRIGHT_SCRIPT}\nimport subprocess\n"
        result = validate_script(script)
        assert result.is_valid is False
        codes = [e.code for e in result.errors]
        assert "unsafe_pattern" in codes
        msgs = [e.message for e in result.errors]
        assert any("subprocess" in m for m in msgs)

    def test_import_subprocess_provides_line_number(self) -> None:
        lines = VALID_PLAYWRIGHT_SCRIPT.split("\n")
        content = "\n".join(lines) + "\nimport subprocess\n"
        result = validate_script(content)
        unsafe = [e for e in result.errors if e.code == "unsafe_pattern"]
        assert len(unsafe) == 1
        assert unsafe[0].line == len(lines) + 1

    def test_eval_call_flagged(self) -> None:
        script = f"{VALID_PLAYWRIGHT_SCRIPT}\nresult = eval('1+1')\n"
        result = validate_script(script)
        assert result.is_valid is False
        assert any("eval" in e.message for e in result.errors)

    def test_os_system_call_flagged(self) -> None:
        script = f"{VALID_PLAYWRIGHT_SCRIPT}\nimport os\nos.system('ls')\n"
        result = validate_script(script)
        assert result.is_valid is False
        # os.system is in the call denylist
        assert any("os.system" in e.message for e in result.errors)

    def test_requests_import_flagged(self) -> None:
        script = f"{VALID_PLAYWRIGHT_SCRIPT}\nimport requests\n"
        result = validate_script(script)
        assert result.is_valid is False
        assert any("requests" in e.message for e in result.errors)

    def test_from_import_flagged(self) -> None:
        script = f"{VALID_PLAYWRIGHT_SCRIPT}\nfrom urllib.request import urlopen\n"
        result = validate_script(script)
        assert result.is_valid is False
        assert any("urllib" in e.message for e in result.errors)

    def test_open_write_flagged(self) -> None:
        script = f"{VALID_PLAYWRIGHT_SCRIPT}\nopen('output.txt', 'w').write('hello')\n"
        result = validate_script(script)
        assert result.is_valid is False
        assert any("open" in e.message.lower() for e in result.errors)

    def test_open_read_not_flagged(self) -> None:
        script = f"{VALID_PLAYWRIGHT_SCRIPT}\nopen('data.txt', 'r')\n"
        result = validate_script(script)
        assert result.is_valid is True

    def test_unsafe_patterns_override_honored(self) -> None:
        """Providing an explicit unsafe_patterns list replaces the default."""
        # With no pattern override, subprocess is flagged
        bad = f"{VALID_PLAYWRIGHT_SCRIPT}\nimport subprocess\n"
        assert validate_script(bad).is_valid is False
        # With empty override, subprocess is NOT flagged (user cleared the list)
        result = validate_script(bad, unsafe_patterns=[])
        assert result.is_valid is True

    def test_custom_bare_call_name_override_enforced(self) -> None:
        """A custom bare call name in the override is enforced against calls.

        Regression test: a bare token (no dot) that is not in the built-in
        _UNSAFE_CALL_NAMES set must still be matched against ast.Call nodes
        when supplied via unsafe_patterns.
        """
        script = f"{VALID_PLAYWRIGHT_SCRIPT}\ndangerous_func()\n"
        # Default denylist does not include this name → script is valid.
        assert validate_script(script).is_valid is True
        # Custom override naming the bare call → the call is rejected.
        result = validate_script(script, unsafe_patterns=["dangerous_func"])
        assert result.is_valid is False
        assert any(
            e.code == "unsafe_pattern" and "dangerous_func" in e.message for e in result.errors
        )


# ---------------------------------------------------------------------------
# Blank / empty content
# ---------------------------------------------------------------------------


class TestBlankContent:
    def test_empty_string_is_invalid(self) -> None:
        result = validate_script("")
        assert result.is_valid is False
        assert result.errors[0].code == "syntax"

    def test_whitespace_only_is_invalid(self) -> None:
        result = validate_script("   \n\t\n  ")
        assert result.is_valid is False
        assert result.errors[0].code == "syntax"


# ---------------------------------------------------------------------------
# Security test: validator must NOT create or modify files
# ---------------------------------------------------------------------------


class TestSecurityNoExecution:
    def test_open_write_flagged_and_no_file_created(self, tmp_path: Path) -> None:
        """The validator must NEVER execute the script, only inspect its AST."""
        sentinel = tmp_path / "sentinel.txt"
        script = f"{VALID_PLAYWRIGHT_SCRIPT}\nopen(r'{sentinel}', 'w').write('pwned')\n"
        result = validate_script(script)
        # 1. The unsafe open() was flagged
        assert result.is_valid is False
        assert any("open" in e.message.lower() for e in result.errors)
        # 2. The sentinel file was NOT created (proof of no execution)
        assert not sentinel.exists(), (
            f"Security violation: the validator executed the script and created {sentinel}"
        )

    def test_eval_flagged_and_no_side_effect(self) -> None:
        """eval() in the script must not be evaluated during validation."""
        # If the validator ran eval(), this would raise a NameError for undefined_name
        script = f"{VALID_PLAYWRIGHT_SCRIPT}\neval('undefined_name')\n"
        # Should return an invalid result without raising
        result = validate_script(script)
        assert result.is_valid is False
        assert any("eval" in e.message for e in result.errors)

    def test_exec_flagged(self) -> None:
        script = f"{VALID_PLAYWRIGHT_SCRIPT}\nexec('x = 1')\n"
        result = validate_script(script)
        assert result.is_valid is False
        assert any("exec" in e.message for e in result.errors)
