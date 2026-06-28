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


# --- Tier-1 server-side session-launch mode -------------------------------------------------


async def test_explore_storage_state_mode_injects_session_via_temp_file(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """storage_state alone is a valid browser source: launch with the session injected via
    a temp JSON file (path passed to BrowserProfile), user_data_dir None, headless True,
    executable_path None (managed Chromium). The temp file is written then removed."""
    import json
    import os

    import browser_use

    captured_path_content: dict[str, object] = {}

    class _ProfileCapturingFile:
        last_kwargs: dict[str, object] = {}

        def __init__(self, **kwargs: object) -> None:
            _ProfileCapturingFile.last_kwargs = kwargs
            # The temp file must EXIST and hold the blob at profile-build time.
            ss_path = kwargs.get("storage_state")
            assert isinstance(ss_path, str)
            assert os.path.exists(ss_path)
            with open(ss_path, encoding="utf-8") as fh:
                captured_path_content["path"] = ss_path
                captured_path_content["data"] = json.load(fh)

    monkeypatch.setattr(browser_use, "Agent", _FakeAgent, raising=False)
    monkeypatch.setattr(browser_use, "BrowserProfile", _ProfileCapturingFile, raising=False)

    blob = {"cookies": [{"name": "sid", "value": "abc"}], "origins": []}
    result = await explore_test_case(
        _test_case(), "https://app.test", llm=object(), storage_state=blob
    )

    assert result == "HISTORY"
    kwargs = _ProfileCapturingFile.last_kwargs
    # storage_state passed as a temp PATH (string), not the dict.
    assert isinstance(kwargs.get("storage_state"), str)
    assert kwargs.get("user_data_dir") is None
    assert kwargs.get("headless") is True
    # No chrome_path supplied -> executable_path None lets browser-use use managed Chromium.
    assert kwargs.get("executable_path") is None
    # The temp file held the exact blob...
    assert captured_path_content["data"] == blob
    # ...and is deleted afterwards (no credential left on disk).
    # captured_path_content is dict[str, object] (mixed path + blob), so narrow the path to
    # str before os.path.exists (Pyrefly bad-argument-type otherwise).
    captured_path = captured_path_content["path"]
    assert isinstance(captured_path, str)
    assert not os.path.exists(captured_path)


async def test_explore_cdp_url_takes_precedence_over_storage_state(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """When both cdp_url and storage_state are given, CDP connect wins (no session file)."""
    import browser_use

    monkeypatch.setattr(browser_use, "Agent", _FakeAgent, raising=False)
    monkeypatch.setattr(browser_use, "BrowserProfile", _FakeProfile, raising=False)

    result = await explore_test_case(
        _test_case(),
        "https://app.test",
        llm=object(),
        cdp_url="http://localhost:9222",
        storage_state={"cookies": []},
    )
    assert result == "HISTORY"
    assert _FakeProfile.last_kwargs == {"cdp_url": "http://localhost:9222"}


async def test_explore_storage_state_temp_file_removed_on_agent_failure(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Even when the agent run raises, the temp session file is removed (finally cleanup)."""
    import os

    import browser_use

    seen: dict[str, str] = {}

    class _ProfileRecordPath:
        def __init__(self, **kwargs: object) -> None:
            ss = kwargs.get("storage_state")
            assert isinstance(ss, str)
            seen["path"] = ss

    class _RaisingAgent:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def run(self, max_steps: int) -> str:
            raise RuntimeError("browser launch failed")

    monkeypatch.setattr(browser_use, "Agent", _RaisingAgent, raising=False)
    monkeypatch.setattr(browser_use, "BrowserProfile", _ProfileRecordPath, raising=False)

    result = await explore_test_case(
        _test_case(), "https://app.test", llm=object(), storage_state={"cookies": []}
    )
    # Any failure degrades to None (fallback) — and the temp file is gone.
    assert result is None
    assert not os.path.exists(seen["path"])
