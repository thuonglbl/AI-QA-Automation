"""Tests for automated login routines."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_qa.browser.login import _classify_browser_failure, generate_session_storage_state
from ai_qa.db.models import TestAccountCredential
from ai_qa.exceptions import BrowserError


@pytest.fixture
def mock_credential():
    """Return a mock TestAccountCredential."""
    cred = MagicMock(spec=TestAccountCredential)
    cred.username = "testuser"
    cred.password = "testpass"
    cred.totp_secret = None
    return cred


@pytest.mark.asyncio
@patch("ai_qa.browser.login._login_with_playwright")
@patch("ai_qa.browser.login._login_with_browser_use")
async def test_generate_session_chooses_playwright(
    mock_browser_use: AsyncMock,
    mock_playwright: AsyncMock,
    mock_credential: MagicMock,
) -> None:
    """Test it uses Playwright when no LLM is provided."""
    mock_playwright.return_value = {"cookies": []}

    result = await generate_session_storage_state(
        credential=mock_credential,
        login_url="http://example.com/login",
        chrome_path="/usr/bin/google-chrome",
        llm=None,
    )

    assert result == {"cookies": []}
    mock_playwright.assert_called_once()
    mock_browser_use.assert_not_called()


@pytest.mark.asyncio
@patch("ai_qa.browser.login._login_with_playwright")
@patch("ai_qa.browser.login._login_with_browser_use")
async def test_generate_session_chooses_browser_use(
    mock_browser_use: AsyncMock,
    mock_playwright: AsyncMock,
    mock_credential: MagicMock,
) -> None:
    """Test it uses browser-use when LLM is provided."""
    mock_browser_use.return_value = {"cookies": ["bu"]}

    result = await generate_session_storage_state(
        credential=mock_credential,
        login_url="http://example.com/login",
        chrome_path="/usr/bin/google-chrome",
        llm=MagicMock(),
    )

    assert result == {"cookies": ["bu"]}
    mock_browser_use.assert_called_once()
    mock_playwright.assert_not_called()


@pytest.mark.asyncio
@patch("ai_qa.browser.login.Agent")
@patch("ai_qa.browser.login.Browser")
async def test_login_with_browser_use_success(
    mock_browser_class: MagicMock,
    mock_agent_class: MagicMock,
    mock_credential: MagicMock,
) -> None:
    """Test browser-use login flow."""
    mock_browser = MagicMock()
    mock_browser_class.return_value = mock_browser
    mock_browser.export_storage_state = AsyncMock(return_value={"state": "ok"})
    mock_browser.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent_class.return_value = mock_agent
    mock_agent.run = AsyncMock()

    from ai_qa.browser.login import _login_with_browser_use

    result = await _login_with_browser_use(
        credential=mock_credential,
        login_url="http://example.com",
        chrome_path="/bin/chrome",
        llm=MagicMock(),
        totp_code="123456",
        timeout=10,
    )

    assert result == {"state": "ok"}
    mock_agent_class.assert_called_once()
    mock_agent.run.assert_called_once()
    mock_browser.export_storage_state.assert_called_once()
    mock_browser.close.assert_called_once()


@pytest.mark.asyncio
@patch("ai_qa.browser.login.Agent")
@patch("ai_qa.browser.login.Browser")
async def test_login_with_browser_use_timeout(
    mock_browser_class: MagicMock,
    mock_agent_class: MagicMock,
    mock_credential: MagicMock,
) -> None:
    """Test browser-use timeout handling."""
    mock_browser = MagicMock()
    mock_browser_class.return_value = mock_browser
    mock_browser.close = AsyncMock()

    mock_agent = MagicMock()
    mock_agent_class.return_value = mock_agent

    async def mock_run_timeout():
        await asyncio.sleep(2)

    mock_agent.run = mock_run_timeout

    from ai_qa.browser.login import _login_with_browser_use

    with pytest.raises(BrowserError, match="timed out"):
        await _login_with_browser_use(
            credential=mock_credential,
            login_url="http://example.com",
            chrome_path="/bin/chrome",
            llm=MagicMock(),
            totp_code=None,
            timeout=0.1,  # Short timeout to force failure
        )

    mock_browser.close.assert_called_once()


@pytest.mark.asyncio
@patch("ai_qa.browser.login.async_playwright")
async def test_login_with_playwright_success(
    mock_async_playwright: MagicMock,
    mock_credential: MagicMock,
) -> None:
    """Test raw playwright fallback."""
    mock_playwright = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    # Setup the mock chain
    mock_async_playwright.return_value.__aenter__.return_value = mock_playwright
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.storage_state = AsyncMock(return_value={"state": "playwright"})

    # Success is now detected by landing back on the target app's own host.
    mock_page.url = "http://example.com/home"

    mock_page.locator = MagicMock(return_value=AsyncMock())

    from ai_qa.browser.login import _login_with_playwright

    result = await _login_with_playwright(
        credential=mock_credential,
        login_url="http://example.com",
        chrome_path="/bin/chrome",
        totp_code="123456",
        timeout=10,
    )

    assert result == {"state": "playwright"}
    mock_page.goto.assert_called_once_with("http://example.com", timeout=10000)
    mock_context.storage_state.assert_called_once()
    mock_browser.close.assert_called_once()


@pytest.mark.asyncio
@patch("ai_qa.browser.login._login_with_playwright")
async def test_generate_session_maps_notimplemented_to_event_loop_hint(
    mock_playwright: AsyncMock,
    mock_credential: MagicMock,
) -> None:
    """A subprocess NotImplementedError (Win SelectorEventLoop) becomes a clear message."""
    mock_playwright.side_effect = NotImplementedError()

    with pytest.raises(BrowserError, match="WITHOUT `uvicorn --reload`"):
        await generate_session_storage_state(
            credential=mock_credential,
            login_url="https://app.example.com/",
            chrome_path="",
            llm=None,
        )


@pytest.mark.parametrize(
    ("raw", "expected_fragment"),
    [
        ("Page.goto: net::ERR_NAME_NOT_RESOLVED at https://x", "corporate network/VPN"),
        ("net::ERR_CONNECTION_TIMED_OUT", "Could not reach the target application"),
        ("net::ERR_INTERNET_DISCONNECTED", "Could not reach the target application"),
        ("Timeout 30000ms exceeded", "Timed out reaching the target application"),
        ("something weird happened", "See the server logs"),
    ],
)
def test_classify_browser_failure(raw: str, expected_fragment: str) -> None:
    """Network/DNS/timeout errors map to clear user messages; raw text kept as details."""
    msg, details = _classify_browser_failure(Exception(raw))
    assert expected_fragment in msg
    assert details == raw  # technical text preserved for logs, not the user message


@pytest.mark.asyncio
@patch("ai_qa.browser.login.async_playwright")
async def test_login_with_playwright_raises_if_never_authenticated(
    mock_async_playwright: MagicMock,
    mock_credential: MagicMock,
) -> None:
    """Never landing on the target host must FAIL, not return an empty session."""
    mock_playwright = AsyncMock()
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()

    mock_async_playwright.return_value.__aenter__.return_value = mock_playwright
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.storage_state = AsyncMock(return_value={"state": "should-not-be-used"})

    # Stuck on the IdP host; no screen element ever matches.
    mock_page.url = "https://login.microsoftonline.com/common/oauth2"
    stuck = MagicMock()
    stuck_first = AsyncMock()
    stuck_first.is_visible = AsyncMock(return_value=False)
    stuck.first = stuck_first
    stuck.or_ = MagicMock(return_value=stuck)
    mock_page.locator = MagicMock(return_value=stuck)
    mock_page.get_by_text = MagicMock(return_value=stuck)

    from ai_qa.browser.login import _login_with_playwright

    with pytest.raises(BrowserError, match="did not reach the authenticated app"):
        await _login_with_playwright(
            credential=mock_credential,
            login_url="https://app.example.com/",
            chrome_path="",
            totp_code=None,
            timeout=0.05,  # short budget -> loop exits unauthenticated
        )

    mock_context.storage_state.assert_not_called()
    mock_browser.close.assert_called_once()
