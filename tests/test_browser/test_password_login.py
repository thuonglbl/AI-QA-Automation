"""Unit tests for the scripted PASSWORD login heuristic + scripted→LLM fallback control flow.

The real browser launch (``login_and_capture_storage_state``) is integration-only and not
exercised here (mirrors ``session_capture``). These tests cover the pure pieces: the
deterministic form-filling heuristic and the decision to fall back to the LLM driver.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import ai_qa.browser.password_login as pl
from ai_qa.browser.password_login import (
    PasswordLoginError,
    _ensure_authenticated,
    _read_devtools_cdp_url,
    _validate_browser_path,
    perform_scripted_login,
)


class _FakeLocator:
    """A locator whose visibility is read LIVE from the page (so reveal-after-submit works)."""

    def __init__(self, page: _FakePage, selector: str) -> None:
        self.page = page
        self.selector = selector
        self.filled: str | None = None
        self.clicks = 0
        self.presses: list[str] = []

    @property
    def first(self) -> _FakeLocator:
        return self

    async def wait_for(self, state: str = "visible", timeout: float = 0) -> None:
        if self.selector not in self.page.visible:
            raise TimeoutError(self.selector)

    async def fill(self, value: str) -> None:
        self.filled = value

    async def click(self) -> None:
        self.clicks += 1
        self.page.reveal_now()

    async def press(self, key: str) -> None:
        self.presses.append(key)
        self.page.reveal_now()


class _FakePage:
    """Minimal Playwright Page double for the scripted-login heuristic."""

    def __init__(self, visible: set[str], reveal_after_action: set[str] | None = None) -> None:
        self.visible = set(visible)
        self._reveal = set(reveal_after_action or set())
        self._locators: dict[str, _FakeLocator] = {}
        self.load_states: list[str] = []

    def locator(self, selector: str) -> _FakeLocator:
        loc = self._locators.get(selector)
        if loc is None:
            loc = _FakeLocator(self, selector)
            self._locators[selector] = loc
        return loc

    async def wait_for_load_state(self, state: str = "networkidle", timeout: float = 0) -> None:
        self.load_states.append(state)

    def reveal_now(self) -> None:
        self.visible |= self._reveal
        self._reveal = set()


class TestScriptedLogin:
    async def test_single_step_form_fills_and_submits(self) -> None:
        page = _FakePage(
            visible={"input[type=email]", "input[type=password]", "button[type=submit]"}
        )
        await perform_scripted_login(page, username="admin@x.com", password="pw", timeout_ms=900)

        assert page.locator("input[type=email]").filled == "admin@x.com"
        assert page.locator("input[type=password]").filled == "pw"
        assert page.locator("button[type=submit]").clicks >= 1
        assert page.load_states  # settled at least once

    async def test_two_step_form_reveals_password_after_username_submit(self) -> None:
        page = _FakePage(
            visible={"input[type=email]", "button[type=submit]"},
            reveal_after_action={"input[type=password]"},
        )
        await perform_scripted_login(page, username="u", password="pw", timeout_ms=900)

        assert page.locator("input[type=email]").filled == "u"
        assert page.locator("input[type=password]").filled == "pw"

    async def test_falls_back_to_enter_when_no_submit_button(self) -> None:
        page = _FakePage(visible={"input[type=text]", "input[type=password]"})
        await perform_scripted_login(page, username="u", password="pw", timeout_ms=600)

        # No submit button visible → Enter pressed in the password field.
        assert page.locator("input[type=password]").presses == ["Enter"]

    async def test_missing_username_field_raises(self) -> None:
        page = _FakePage(visible=set())
        with pytest.raises(PasswordLoginError, match="username"):
            await perform_scripted_login(page, username="u", password="pw", timeout_ms=400)

    async def test_missing_password_field_raises(self) -> None:
        page = _FakePage(visible={"input[type=text]"})  # username only, never a password field
        with pytest.raises(PasswordLoginError, match="password"):
            await perform_scripted_login(page, username="u", password="pw", timeout_ms=400)

    async def test_error_message_is_credential_free(self) -> None:
        page = _FakePage(visible=set())
        with pytest.raises(PasswordLoginError) as ei:
            await perform_scripted_login(
                page, username="secretuser", password="topsecret", timeout_ms=300
            )
        assert "secretuser" not in str(ei.value)
        assert "topsecret" not in str(ei.value)


class TestFallbackControlFlow:
    async def test_no_fallback_on_scripted_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        async def ok(page: Any, **_: Any) -> None:
            calls.append("scripted")

        async def bu(cdp_url: str, **_: Any) -> None:
            calls.append("browser_use")

        monkeypatch.setattr(pl, "perform_scripted_login", ok)
        monkeypatch.setattr(pl, "perform_browser_use_login", bu)
        await pl._drive_login_with_fallback(
            object(),
            "http://localhost:9223",
            login_url="u",
            username="a",
            password="b",
            llm=object(),
            timeout_ms=10,
        )
        assert calls == ["scripted"]

    async def test_scripted_failure_without_llm_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(page: Any, **_: Any) -> None:
            raise PasswordLoginError("Could not find a password field on the login page.")

        monkeypatch.setattr(pl, "perform_scripted_login", boom)
        with pytest.raises(PasswordLoginError):
            await pl._drive_login_with_fallback(
                object(),
                "http://localhost:9223",
                login_url="u",
                username="a",
                password="b",
                llm=None,
                timeout_ms=10,
            )

    async def test_scripted_failure_with_llm_triggers_browser_use(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        async def boom(page: Any, **_: Any) -> None:
            calls.append("scripted")
            raise PasswordLoginError("Could not find a password field on the login page.")

        async def bu(cdp_url: str, **_: Any) -> None:
            calls.append("browser_use")

        monkeypatch.setattr(pl, "perform_scripted_login", boom)
        monkeypatch.setattr(pl, "perform_browser_use_login", bu)
        await pl._drive_login_with_fallback(
            object(),
            "http://localhost:9223",
            login_url="u",
            username="a",
            password="b",
            llm=object(),
            timeout_ms=10,
        )
        assert calls == ["scripted", "browser_use"]


class TestBrowserUseCredentialWiring:
    """Exercise the REAL perform_browser_use_login (fake Agent) — the highest-risk channel."""

    async def test_password_only_via_domain_scoped_sensitive_data(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import browser_use

        captured: dict[str, Any] = {}

        class _FakeProfile:
            def __init__(self, **kwargs: Any) -> None:
                captured["profile"] = kwargs

        class _DoneHistory:
            def is_done(self) -> bool:
                return True

        class _FakeAgent:
            def __init__(self, **kwargs: Any) -> None:
                captured["agent"] = kwargs

            async def run(self, **_: Any) -> _DoneHistory:
                return _DoneHistory()

        monkeypatch.setattr(browser_use, "Agent", _FakeAgent, raising=False)
        monkeypatch.setattr(browser_use, "BrowserProfile", _FakeProfile, raising=False)

        await pl.perform_browser_use_login(
            "http://localhost:9223",
            login_url="https://app.example.com/login",
            username="secretuser",
            password="topsecret",
            llm=object(),
        )

        agent_kwargs = captured["agent"]
        # The password is NEVER interpolated into the task string — only the placeholder key is.
        assert "topsecret" not in agent_kwargs["task"]
        assert pl._PASSWORD_PLACEHOLDER in agent_kwargs["task"]
        # Domain-scoped sensitive_data: the password is bound to the login host only.
        assert agent_kwargs["sensitive_data"] == {
            "app.example.com": {pl._PASSWORD_PLACEHOLDER: "topsecret"}
        }
        # Vision is off (no login-page screenshots shipped to the LLM provider).
        assert agent_kwargs["use_vision"] is False
        # The browser profile is locked to the login host.
        assert captured["profile"]["allowed_domains"] == ["app.example.com"]

    async def test_not_done_history_raises_credential_free(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import browser_use

        class _FakeProfile:
            def __init__(self, **kwargs: Any) -> None:
                pass

        class _NotDoneHistory:
            def is_done(self) -> bool:
                return False

        class _FakeAgent:
            def __init__(self, **kwargs: Any) -> None:
                pass

            async def run(self, **_: Any) -> _NotDoneHistory:
                return _NotDoneHistory()

        monkeypatch.setattr(browser_use, "Agent", _FakeAgent, raising=False)
        monkeypatch.setattr(browser_use, "BrowserProfile", _FakeProfile, raising=False)

        with pytest.raises(PasswordLoginError) as ei:
            await pl.perform_browser_use_login(
                "http://localhost:9223",
                login_url="https://app.example.com/login",
                username="secretuser",
                password="topsecret",
                llm=object(),
            )
        assert "secretuser" not in str(ei.value)
        assert "topsecret" not in str(ei.value)


class TestLauncherGuards:
    """Pure guards used by the integration-only launcher."""

    def test_validate_browser_path_accepts_real_chrome(self, tmp_path: Path) -> None:
        exe = tmp_path / "chrome.exe"
        exe.write_text("binary")
        _validate_browser_path(str(exe))  # no raise

    def test_validate_browser_path_rejects_missing(self, tmp_path: Path) -> None:
        with pytest.raises(PasswordLoginError, match="does not exist"):
            _validate_browser_path(str(tmp_path / "chrome.exe"))

    def test_validate_browser_path_rejects_non_browser_binary(self, tmp_path: Path) -> None:
        evil = tmp_path / "calc.exe"
        evil.write_text("binary")
        with pytest.raises(PasswordLoginError, match="not a recognised"):
            _validate_browser_path(str(evil))

    def test_ensure_authenticated_accepts_cookies_or_origins(self) -> None:
        _ensure_authenticated({"cookies": [{"name": "sid"}], "origins": []})
        _ensure_authenticated({"cookies": [], "origins": [{"origin": "https://x"}]})

    def test_ensure_authenticated_rejects_empty_state(self) -> None:
        with pytest.raises(PasswordLoginError, match="did not appear to succeed"):
            _ensure_authenticated({"cookies": [], "origins": []})
        with pytest.raises(PasswordLoginError):
            _ensure_authenticated({})

    async def test_read_devtools_cdp_url_reads_assigned_port(self, tmp_path: Path) -> None:
        (tmp_path / "DevToolsActivePort").write_text("51234\n/devtools/browser/abc\n")
        assert await _read_devtools_cdp_url(tmp_path, timeout_ms=1000) == "http://localhost:51234"

    async def test_read_devtools_cdp_url_times_out_without_file(self, tmp_path: Path) -> None:
        with pytest.raises(PasswordLoginError, match="debugging endpoint"):
            await _read_devtools_cdp_url(tmp_path, timeout_ms=0)
