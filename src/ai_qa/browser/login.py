"""Automated login routines for target applications.

Provides functionality to automatically log in to a target application using
stored TestAccountCredential and export the resulting Playwright storageState,
using either browser-use (for dynamic forms) or Playwright (for simple forms).
"""

import asyncio
import logging
import time
from typing import Any, cast
from urllib.parse import urlparse

from browser_use import Agent, Browser
from playwright.async_api import Locator, Page, async_playwright

from ai_qa.db.models import TestAccountCredential
from ai_qa.exceptions import BrowserError

logger = logging.getLogger(__name__)

# Raised on Windows when the asyncio event loop is a SelectorEventLoop (which cannot
# spawn subprocesses) — e.g. when the backend runs under `uvicorn --reload`. Playwright
# needs the ProactorEventLoop, which uvicorn uses only WITHOUT --reload on Windows.
_EVENT_LOOP_HINT = (
    "Browser automation could not start under the server's event loop. On Windows, run "
    "the backend WITHOUT `uvicorn --reload` (reload forces a SelectorEventLoop that "
    "cannot launch the browser subprocess)."
)


async def generate_session_storage_state(
    credential: TestAccountCredential,
    login_url: str,
    chrome_path: str,
    llm: Any = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Automate login and capture storageState.

    Args:
        credential: The TestAccountCredential to use.
        login_url: The URL to start the login process.
        chrome_path: Path to the Chrome executable.
        llm: A browser_use.llm.BaseChatModel instance to drive browser-use.
             If None, falls back to a simple raw Playwright heuristic.
        timeout: Timeout in seconds for the entire routine.

    Returns:
        A dict representing the Playwright storageState.

    Raises:
        BrowserError: If login fails or state cannot be captured.
    """
    totp_code = None
    if credential.totp_secret:
        try:
            import pyotp

            totp = pyotp.TOTP(credential.totp_secret)
            totp_code = totp.now()
        except ImportError:
            logger.warning("pyotp not installed, cannot generate TOTP code.")

    try:
        if llm:
            return await _login_with_browser_use(
                credential, login_url, chrome_path, llm, totp_code, timeout
            )
        return await _login_with_playwright(credential, login_url, chrome_path, totp_code, timeout)
    except NotImplementedError as e:
        # Playwright's driver subprocess can't start on a SelectorEventLoop (Windows
        # + `uvicorn --reload`). Surface a clear, actionable message instead of a
        # cryptic NotImplementedError bubbling up as an "unexpected" error.
        raise BrowserError(_EVENT_LOOP_HINT, details=str(e)) from e


async def _login_with_browser_use(
    credential: TestAccountCredential,
    login_url: str,
    chrome_path: str,
    llm: Any,
    totp_code: str | None,
    timeout: float,
) -> dict[str, Any]:
    """Login using the browser-use Agent for dynamic UI navigation."""

    prompt = (
        f"Navigate to {login_url}.\n"
        f"Log in using the username '{credential.username}' and password '{credential.password}'.\n"
        "If the site requires a third-party login (like 'Sign in with Google' or 'Apple'), select that option and complete the authentication flow.\n"
    )
    if totp_code:
        prompt += f"If prompted for a two-factor (TOTP/Authenticator) code, enter '{totp_code}'.\n"

    prompt += (
        "Once you have successfully logged in and reached the authenticated area, stop the task."
    )

    # Need to run browser in headless mode to capture state in background.
    # An empty chrome_path falls back to Playwright's bundled Chromium (passing
    # "" raises "Failed to launch: spawn . ENOENT"); None selects the bundle.
    # We disable security to allow self-signed certificates on internal UAT/Dev domains.
    browser = Browser(executable_path=chrome_path or None, headless=True, disable_security=True)

    try:
        agent: Any = Agent(task=prompt, llm=llm, browser=browser, use_vision=True)

        # Run agent with timeout
        await asyncio.wait_for(agent.run(), timeout=timeout)

        # Capture state
        state: dict[str, Any] = await browser.export_storage_state()
        return state
    except TimeoutError as e:
        raise BrowserError(f"Login via browser-use timed out after {timeout} seconds.") from e
    except Exception as e:
        raise BrowserError(f"Login via browser-use failed: {e}") from e
    finally:
        await browser.close()


async def _prompt_interactive_mfa(
    page: Page, totp_input: Locator, credential: TestAccountCredential
) -> None:
    """Pause the login, ask the frontend for a 6-digit MFA code, and submit it.

    Broadcasts an ``MFA_REQUIRED`` system message (carrying a fresh session id +
    project/env/role) so the frontend can render the code prompt, then blocks on
    the in-memory MFA future until the user submits a code. The wait is bounded by
    its own timeout, independent of the caller's automation budget.
    """
    import uuid

    from ai_qa.api.websocket import broadcast_message
    from ai_qa.models import AgentMessage
    from ai_qa.sessions.mfa_manager import wait_for_mfa

    session_id = str(uuid.uuid4())
    await broadcast_message(
        AgentMessage(
            sender="system",
            content="The login flow is waiting for a 6-digit MFA code.",
            messageType="info",
            metadata={
                "action": "MFA_REQUIRED",
                "session_id": session_id,
                "environment": credential.environment,
                "role": credential.role,
                "project_id": str(credential.project_id),
            },
        )
    )

    # Human-in-the-loop: allow generous time, independent of the automation budget.
    code = await wait_for_mfa(session_id, timeout_seconds=180)
    await totp_input.fill(code)
    await totp_input.press("Enter")
    await page.wait_for_timeout(1000)


def _classify_browser_failure(exc: Exception) -> tuple[str, str]:
    """Map a raw Playwright/browser error to a (user_message, technical_details) pair.

    Keeps the technical string in ``details`` (logged, never shown to the user) and
    returns a clear, actionable message so a network/VPN problem is not reported as a
    credentials problem.
    """
    raw = str(exc)
    lowered = raw.lower()
    if "err_name_not_resolved" in lowered:
        msg = (
            "Could not resolve the target host — the application's hostname is internal. "
            "Connect to the corporate network/VPN and try again."
        )
    elif any(
        token in lowered
        for token in (
            "err_connection_refused",
            "err_connection_timed_out",
            "err_connection_reset",
            "err_address_unreachable",
            "err_timed_out",
            "err_internet_disconnected",
            "err_proxy",
        )
    ):
        msg = (
            "Could not reach the target application. Check the network/VPN and the "
            "environment URL, then try again."
        )
    elif "timeout" in lowered or "exceeded" in lowered:
        msg = "Timed out reaching the target application. Check the network/VPN and the URL."
    else:
        msg = "Browser login failed. See the server logs for the underlying error."
    return msg, raw


async def _login_with_playwright(
    credential: TestAccountCredential,
    login_url: str,
    chrome_path: str,
    totp_code: str | None,
    timeout: float,
) -> dict[str, Any]:
    """Basic raw Playwright fallback for standard forms."""

    async with async_playwright() as p:
        try:
            # Empty chrome_path falls back to Playwright's bundled Chromium;
            # passing "" raises "Failed to launch: spawn . ENOENT". None = bundle.
            browser = await p.chromium.launch(executable_path=chrome_path or None, headless=True)
            context = await browser.new_context(ignore_https_errors=True)

            # Disable WebAuthn/Passkeys to force Microsoft Entra to ask for a Password
            await context.add_init_script(
                "Object.defineProperty(window, 'PublicKeyCredential', { get: () => undefined, configurable: true });"
            )

            page = await context.new_page()

            await page.goto(login_url, timeout=timeout * 1000)

            # The authenticated app's own host. Landing back here (after the IdP
            # round-trip) is the positive, unambiguous success signal — far more
            # reliable than substring-matching the URL for "login"/"auth".
            target_host = urlparse(login_url).netloc.lower()
            authenticated = False
            start_time = time.time()

            # State machine loop for complex SSO flows (e.g. Microsoft Entra).
            # Each iteration identifies the current screen and advances one step.
            while time.time() - start_time < timeout:
                await page.wait_for_timeout(1500)

                # 0. Success: we are back on the target app's host (OIDC/SAML
                #    round-trip complete). Checked first so a transient IdP screen
                #    is never misread as success.
                if urlparse(page.url).netloc.lower() == target_host:
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:  # noqa: BLE001 - settle only; auth already proven by host
                        pass
                    authenticated = True
                    break

                # 1. Email / username input (two-step IdP first screen)
                email_input = page.locator(
                    "input[type='email'], input[name*='user'], input[name*='email']"
                ).first
                if await email_input.is_visible():
                    if not await email_input.input_value():
                        await email_input.fill(credential.username)
                        await email_input.press("Enter")
                        await page.wait_for_timeout(1000)
                    continue

                # 2. Account picker (Microsoft caches sessions)
                account_picker = page.locator(f"text='{credential.username}'").first
                if (
                    await account_picker.is_visible()
                    and await page.locator("text='Pick an account'").is_visible()
                ):
                    await account_picker.click()
                    continue

                # 3. Passwordless / "Approve a request" push screen -> switch to
                #    password. Match the stable element id first, then fall back to
                #    visible text (which varies by Entra UI revision and locale).
                use_password = (
                    page.locator("#idA_PWD_SwitchToPassword")
                    .or_(page.get_by_text("Use your password instead", exact=False))
                    .first
                )
                if await use_password.is_visible():
                    await use_password.click(timeout=5000)
                    continue

                # 4. Password input
                pass_input = page.locator("input[type='password'], input[name*='pass']").first
                if await pass_input.is_visible():
                    if not await pass_input.input_value():
                        await pass_input.fill(credential.password)
                        await pass_input.press("Enter")
                        await page.wait_for_timeout(1000)
                    continue

                # 5. Number-matching / push screen with no input box -> switch to a
                #    typed verification code so a TOTP or interactive code can be used.
                switch_to_code = (
                    page.locator("#idA_PWD_SwitchToCredPicker, [data-value='PhoneAppOTP']")
                    .or_(
                        page.get_by_text("I can't use my Microsoft Authenticator app", exact=False)
                    )
                    .or_(page.get_by_text("Sign in with an authenticator app", exact=False))
                    .or_(page.get_by_text("Use a verification code", exact=False))
                    .first
                )
                if await switch_to_code.is_visible():
                    await switch_to_code.click(timeout=3000)
                    continue

                # 6. One-time-code input. Microsoft's field is name='otc'
                #    (id idTxtBx_SAOTCC_OTC) — it does NOT match name*='code', so it
                #    must be listed explicitly or the code screen is never detected.
                totp_input = page.locator(
                    "input[name='otc'], #idTxtBx_SAOTCC_OTC, "
                    "input[autocomplete='one-time-code'], "
                    "input[name*='code'], input[name*='token'], input[name*='totp']"
                ).first
                if await totp_input.is_visible():
                    if totp_code:
                        await totp_input.fill(totp_code)
                        await totp_input.press("Enter")
                        await page.wait_for_timeout(1000)
                    else:
                        await _prompt_interactive_mfa(page, totp_input, credential)
                        # The human wait can far exceed the automation budget; give
                        # the post-submit navigation a fresh time window.
                        start_time = time.time()
                    continue

                # 7. "Stay signed in?" (Microsoft KMSI)
                stay_signed_in = page.locator("text='Stay signed in?'").first
                if await stay_signed_in.is_visible():
                    await page.click(
                        "input[type='submit'], button[type='submit'], button:has-text('Yes')",
                        timeout=5000,
                    )
                    continue

            if not authenticated:
                raise BrowserError(
                    f"Login did not reach the authenticated app '{target_host}' within "
                    f"{timeout:.0f}s (still at '{urlparse(page.url).netloc}'). Credentials, "
                    "MFA, or a Conditional Access policy may have blocked sign-in."
                )

            state = await context.storage_state()
            return cast(dict[str, Any], state)
        except BrowserError:
            raise  # already a clear, intentional failure — don't re-wrap
        except Exception as e:
            msg, details = _classify_browser_failure(e)
            raise BrowserError(msg, details=details) from e
        finally:
            if "browser" in locals():
                await browser.close()
