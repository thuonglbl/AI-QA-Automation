"""Tests for the browser-use explorer (browser/explorer.py).

Covers the testable parts: the natural-language task builder and the guard paths
that return ``None`` (so generation falls back to LLM-only). The live agent run
is integration-only (needs Chrome + a reachable app + SSO) and is not exercised
here — same policy as the existing vision path.
"""

from ai_qa.browser.explorer import build_exploration_task, explore_test_case
from ai_qa.models import TestCase, TestCaseStep


def _test_case() -> TestCase:
    return TestCase(
        title="Search flow",
        objective="Search for a product and verify results",
        steps=[
            TestCaseStep(number=1, action="Type query", target="search box", data="laptop"),
            TestCaseStep(number=2, action="Click search button", target="search button"),
        ],
        expected_results=["Results list shows laptop items"],
    )


def test_build_exploration_task_includes_steps_objective_and_no_login() -> None:
    task = build_exploration_task(_test_case(), "https://app.test")
    assert "https://app.test" in task
    assert "do not log in" in task.lower()
    assert "Search for a product and verify results" in task
    assert "1. Type query" in task
    assert "search box" in task
    assert "laptop" in task
    assert "Results list shows laptop items" in task


async def test_explore_returns_none_without_chrome_path() -> None:
    result = await explore_test_case(_test_case(), "https://app.test", llm=object(), chrome_path="")
    assert result is None


async def test_explore_returns_none_without_target_url() -> None:
    result = await explore_test_case(_test_case(), "", llm=object(), chrome_path="/path/to/chrome")
    assert result is None


async def test_explore_returns_none_without_llm() -> None:
    result = await explore_test_case(
        _test_case(), "https://app.test", llm=None, chrome_path="/path/to/chrome"
    )
    assert result is None


async def test_explore_returns_none_without_any_browser_source() -> None:
    # Neither a Chrome path (launch) nor a CDP URL (connect) -> cannot explore.
    result = await explore_test_case(_test_case(), "https://app.test", llm=object())
    assert result is None


class _FakeAgent:
    last_kwargs: dict[str, object] = {}

    def __init__(self, **kwargs: object) -> None:
        _FakeAgent.last_kwargs = kwargs

    async def run(self, max_steps: int) -> str:
        return "HISTORY"


class _FakeProfile:
    last_kwargs: dict[str, object] = {}

    def __init__(self, **kwargs: object) -> None:
        _FakeProfile.last_kwargs = kwargs


async def test_explore_connect_mode_builds_profile_with_cdp_url(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import browser_use

    monkeypatch.setattr(browser_use, "Agent", _FakeAgent, raising=False)
    monkeypatch.setattr(browser_use, "BrowserProfile", _FakeProfile, raising=False)

    # CDP URL alone (no chrome path) is a valid browser source -> connect mode.
    result = await explore_test_case(
        _test_case(), "https://app.test", llm=object(), cdp_url="http://localhost:9222"
    )
    assert result == "HISTORY"
    assert _FakeProfile.last_kwargs == {"cdp_url": "http://localhost:9222"}


async def test_explore_launch_mode_builds_profile_with_executable_path(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import browser_use

    monkeypatch.setattr(browser_use, "Agent", _FakeAgent, raising=False)
    monkeypatch.setattr(browser_use, "BrowserProfile", _FakeProfile, raising=False)

    result = await explore_test_case(
        _test_case(), "https://app.test", llm=object(), chrome_path="/path/to/chrome"
    )
    assert result == "HISTORY"
    assert _FakeProfile.last_kwargs.get("executable_path") == "/path/to/chrome"
    assert "cdp_url" not in _FakeProfile.last_kwargs
