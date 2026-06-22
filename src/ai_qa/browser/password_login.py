"""Auto-drive a username/password login and capture its Playwright ``storageState``.

For a PASSWORD project the backend logs in on the tester's behalf using the shared
:class:`~ai_qa.db.models.ProjectAccount` credential and exports the resulting session
blob (stored as that tester's per-user :class:`~ai_qa.db.models.CapturedSession`). Two
strategies are tried in order (the "hybrid" the project chose):

  1. **Scripted** (default): a deterministic Playwright heuristic finds the username and
     password fields, types the credentials directly into them, and submits. No LLM is
     involved and nothing leaves the machine — the password is only ever typed into the
     page's password field.
  2. **browser-use LLM fallback**: when the scripted heuristic cannot complete the login
     (non-standard, multi-step or unusual forms) AND an LLM is available, a browser-use
     ``Agent`` drives the SAME browser over CDP. The password is passed via browser-use's
     ``sensitive_data`` channel as a placeholder, so the secret is NEVER sent to the LLM
     provider — only the placeholder key is.

Integration-only: launching a real browser is NOT exercised by unit tests (mirrors
:mod:`ai_qa.browser.session_capture`). The pure pieces — the scripted heuristic and the
scripted→LLM fallback control flow — ARE unit-tested. The end-to-end launch needs live
validation on a real managed machine.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# The auto-login browser is launched with ``--remote-debugging-port=0`` so the OS assigns a
# free port (no fixed-port collision when captures run concurrently or a debug browser is
# already on 9222/9223). The actual port is read back from the profile's DevToolsActivePort
# file. ``chrome_path`` is client-provided, so it is launched via subprocess WITHOUT a shell
# and only after validating it points at a recognised browser binary that exists on disk —
# this bounds it to launching a real Chrome/Edge/Chromium rather than an arbitrary executable.
_ALLOWED_BROWSER_BINARIES = frozenset(
    {
        "chrome.exe",
        "chrome",
        "msedge.exe",
        "msedge",
        "chromium.exe",
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
        "brave.exe",
        "brave",
    }
)

# browser-use ``sensitive_data`` placeholder key. The LLM only ever sees this key; the
# real password is substituted by browser-use at fill time and is never sent to the model.
_PASSWORD_PLACEHOLDER = "account_password"  # noqa: S105 — placeholder KEY, not a secret

# Heuristic field locators, tried in order. Case-insensitive attribute matching uses
# Playwright's CSS ``[attr*=val i]`` flag. The plain ``input[type=text]`` fallback is last
# so a more specific username/email match wins first.
_USERNAME_SELECTORS: tuple[str, ...] = (
    "input[type=email]",
    "input[autocomplete=username]",
    "input[name*=user i]",
    "input[id*=user i]",
    "input[name*=email i]",
    "input[id*=email i]",
    "input[name*=login i]",
    "input[id*=login i]",
    "input[type=text]",
)
_PASSWORD_SELECTOR = "input[type=password]"  # noqa: S105 — CSS selector, not a secret
_SUBMIT_SELECTORS: tuple[str, ...] = (
    "button[type=submit]",
    "input[type=submit]",
    "button:has-text('Log in')",
    "button:has-text('Login')",
    "button:has-text('Sign in')",
    "button:has-text('Sign In')",
    "button:has-text('Continue')",
    "button:has-text('Next')",
)


class PasswordLoginError(RuntimeError):
    """Raised when an automated username/password login could not be completed.

    Its message is always credential-free (no username/password) so it is safe to surface
    to the API and logs.
    """


async def _first_visible(page: Any, selectors: tuple[str, ...], timeout_ms: int) -> Any | None:
    """Return the first locator from ``selectors`` that becomes visible, else ``None``.

    Splits ``timeout_ms`` across the candidates so the total wait is bounded regardless of
    how many selectors are tried.
    """
    per = max(250, timeout_ms // max(1, len(selectors)))
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(state="visible", timeout=per)
            return locator
        except Exception:  # noqa: BLE001 — locator/timeout failures vary; treat as "not here"
            continue
    return None


async def _settle(page: Any, timeout_ms: int) -> None:
    """Best-effort wait for the page to settle after a submit (never raises)."""
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:  # noqa: BLE001 — networkidle can legitimately never fire; ignore
        logger.debug("Auto-login: page did not reach networkidle within %dms", timeout_ms)


async def _submit(page: Any, fallback_field: Any, timeout_ms: int) -> None:
    """Click a submit/login button, falling back to pressing Enter in ``fallback_field``."""
    button = await _first_visible(page, _SUBMIT_SELECTORS, timeout_ms)
    if button is not None:
        await button.click()
    else:
        await fallback_field.press("Enter")


async def perform_scripted_login(
    page: Any, *, username: str, password: str, timeout_ms: int = 15000
) -> None:
    """Deterministically fill and submit a username/password form on ``page``.

    ``page`` must already be navigated to the login page. Handles both single-step forms
    and the common two-step pattern (username, submit, then a revealed password field).

    Raises:
        PasswordLoginError: a required field could not be located (the caller may then try
            the LLM fallback or surface a "capture manually" message).
    """
    username_field = await _first_visible(page, _USERNAME_SELECTORS, timeout_ms)
    if username_field is None:
        raise PasswordLoginError("Could not find a username/email field on the login page.")

    # Wrap the fill/submit actions: an unexpected Playwright error (detached element, strict
    # mode, navigation mid-fill) must become a credential-free PasswordLoginError so the
    # caller can engage the LLM fallback and the message stays controlled.
    try:
        await username_field.fill(username)

        # Single-step forms expose the password field immediately; two-step forms reveal it
        # only after the username is submitted.
        password_field = await _first_visible(page, (_PASSWORD_SELECTOR,), timeout_ms // 3)
        if password_field is None:
            await _submit(page, username_field, timeout_ms)
            await _settle(page, timeout_ms)
            password_field = await _first_visible(page, (_PASSWORD_SELECTOR,), timeout_ms)
        if password_field is None:
            raise PasswordLoginError("Could not find a password field on the login page.")

        await password_field.fill(password)
        await _submit(page, password_field, timeout_ms)
        await _settle(page, timeout_ms)
    except PasswordLoginError:
        raise
    except Exception as exc:  # noqa: BLE001 — Playwright errors vary; keep the message credential-free
        raise PasswordLoginError("Could not complete the login form.") from exc


def _history_succeeded(history: Any) -> bool:
    """Whether the browser-use agent reached a done/successful state (best-effort).

    ``Agent.run`` returns without raising even when it stops short of logging in, so we inspect
    the returned ``AgentHistoryList``. If the history shape is unknown we do NOT block — the
    downstream :func:`_ensure_authenticated` check still guards an empty session.
    """
    is_done = getattr(history, "is_done", None)
    if is_done is None:
        return True
    try:
        return bool(is_done() if callable(is_done) else is_done)
    except Exception:  # noqa: BLE001 — unknown history shape; defer to the storageState check
        return True


async def perform_browser_use_login(
    cdp_url: str, *, login_url: str, username: str, password: str, llm: Any
) -> None:
    """LLM fallback: a browser-use ``Agent`` logs in by driving the browser at ``cdp_url``.

    The password is passed via browser-use ``sensitive_data`` as a placeholder so it is
    never sent to the LLM provider. Integration-only (lazy import; not unit-tested).

    Raises:
        PasswordLoginError: the agent failed to drive the login.
    """
    try:
        from urllib.parse import urlsplit

        from browser_use import Agent, BrowserProfile

        host = urlsplit(login_url).hostname or ""
        # Lock the credential to the intended login host: allowed_domains stops the agent from
        # wandering off-origin, and the domain-scoped sensitive_data form means browser-use only
        # substitutes the real password on `host` — never on an SSO/redirect origin.
        profile = BrowserProfile(cdp_url=cdp_url, allowed_domains=[host] if host else [])
        task = (
            f"Go to {login_url} and log into the application. Enter the username "
            f"'{username}' in the username/email field, enter the value referenced as "
            f"'{_PASSWORD_PLACEHOLDER}' in the password field, then submit the login form. "
            "Stop as soon as the login has clearly succeeded (you are past the login page)."
        )
        sensitive_data: dict[str, Any] = (
            {host: {_PASSWORD_PLACEHOLDER: password}} if host else {_PASSWORD_PLACEHOLDER: password}
        )
        agent: Any = Agent(
            task=task,
            llm=llm,
            browser_profile=profile,
            sensitive_data=sensitive_data,
            # Vision off: a username/password fill needs no screenshots, and use_vision=True
            # would ship login-page pixels (incl. the plaintext username) to the LLM provider —
            # a channel the sensitive_data placeholder does not protect.
            use_vision=False,
        )
        history = await agent.run(max_steps=15)
        # Agent.run does NOT raise when it stops short of logging in; treat a not-done run as a
        # failure so a silently-failed login is never returned as a "successful" session.
        if not _history_succeeded(history):
            raise PasswordLoginError(
                "Automated login could not be completed (the assistant did not reach a "
                "logged-in state)."
            )
    except PasswordLoginError:
        raise
    except Exception as exc:  # noqa: BLE001 — browser-use failures vary; surface clean message
        logger.warning("Auto-login: browser-use fallback failed: %s", type(exc).__name__)
        raise PasswordLoginError(
            "Automated login could not be completed (LLM fallback failed)."
        ) from exc


async def _drive_login_with_fallback(
    page: Any,
    cdp_url: str,
    *,
    login_url: str,
    username: str,
    password: str,
    llm: Any | None,
    timeout_ms: int,
) -> None:
    """Run the scripted login; on failure, fall back to the browser-use LLM driver.

    With ``llm=None`` there is no fallback and the scripted error propagates. Both branches
    raise :class:`PasswordLoginError` on a credential-free message.
    """
    try:
        await perform_scripted_login(
            page, username=username, password=password, timeout_ms=timeout_ms
        )
    except PasswordLoginError:
        if llm is None:
            raise
        logger.info("Auto-login: scripted heuristic failed; trying browser-use LLM fallback.")
        await perform_browser_use_login(
            cdp_url, login_url=login_url, username=username, password=password, llm=llm
        )


def _validate_browser_path(chrome_path: str) -> None:
    """Reject anything that is not an existing, recognised browser binary.

    ``chrome_path`` is client-provided and the backend executes it, so this bounds the
    launch to a real Chrome/Edge/Chromium that exists on disk (a renamed executable still
    requires server-host filesystem access, outside this trust boundary).
    """
    from pathlib import Path

    path = Path(chrome_path)
    if not path.is_file():
        raise PasswordLoginError("The configured Chrome/Edge path does not exist.")
    if path.name.lower() not in _ALLOWED_BROWSER_BINARIES:
        raise PasswordLoginError(
            "The configured path is not a recognised Chrome/Edge/Chromium browser binary."
        )


async def _read_devtools_cdp_url(user_data_dir: Any, timeout_ms: int) -> str:
    """Read the OS-assigned debugging port from the profile's DevToolsActivePort file."""
    import asyncio

    port_file = user_data_dir / "DevToolsActivePort"
    waited = 0.0
    deadline = timeout_ms / 1000.0
    while True:
        if port_file.exists():
            try:
                first_line = port_file.read_text(encoding="utf-8").splitlines()[0].strip()
                if first_line.isdigit():
                    return f"http://localhost:{first_line}"
            except OSError, IndexError:
                pass  # file still being written; retry
        if waited >= deadline:
            raise PasswordLoginError(
                "Auto-login browser did not expose a debugging endpoint in time."
            )
        await asyncio.sleep(0.25)
        waited += 0.25


def _ensure_authenticated(storage_state: dict[str, Any]) -> None:
    """Guard against a silently-failed login producing an unauthenticated, useless blob.

    A successful login virtually always sets at least one cookie or a localStorage origin;
    an empty storageState means the credentials were rejected (and the app stayed on the
    login page) far more often than it means a genuinely cookieless authenticated app.
    """
    cookies = storage_state.get("cookies")
    origins = storage_state.get("origins")
    has_cookies = isinstance(cookies, list) and len(cookies) > 0
    has_origins = isinstance(origins, list) and len(origins) > 0
    if not has_cookies and not has_origins:
        raise PasswordLoginError(
            "Login did not appear to succeed — no session was established. Check the "
            "account credentials, or capture the session manually."
        )


def _terminate_and_reap(proc: Any) -> None:
    """Terminate a browser subprocess and reap it (blocking; call via ``asyncio.to_thread``)."""
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:  # noqa: BLE001 — escalate to kill, then reap
        proc.kill()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001 — best-effort reap
            logger.warning("Auto-login: browser process did not exit after kill.")


async def login_and_capture_storage_state(
    *,
    login_url: str,
    username: str,
    password: str,
    chrome_path: str,
    llm: Any | None = None,
    headless: bool = True,
    timeout_ms: int = 30000,
) -> dict[str, Any]:
    """Launch a debug browser, log in (scripted → LLM fallback), and return storageState.

    Integration-only (not unit-tested — mirrors :func:`session_capture.capture_storage_state_over_cdp`).
    Launches ``chrome_path`` with a throwaway profile and an OS-assigned remote-debugging port
    so BOTH Playwright (scripted fill + ``storage_state()``) and a browser-use fallback can
    drive the SAME browser over CDP. The browser process and temp profile are always torn down,
    and an empty (unauthenticated) result is rejected.

    Raises:
        PasswordLoginError: bad browser path, launch/connection failure, or a login that did
            not establish a session.
    """
    import asyncio
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    from playwright.async_api import async_playwright

    _validate_browser_path(chrome_path)

    user_data_dir = tempfile.mkdtemp(prefix="aiqa-autologin-")
    args = [
        chrome_path,
        "--remote-debugging-port=0",  # OS-assigned free port; avoids fixed-port collisions
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        args.append("--headless=new")

    proc: subprocess.Popen[bytes] | None = None
    try:
        try:
            proc = subprocess.Popen(args)  # noqa: S603 — path validated to a browser binary
        except OSError as exc:
            raise PasswordLoginError(
                "Could not launch the browser for auto-login. Check the Chrome/Edge path."
            ) from exc

        cdp_url = await _read_devtools_cdp_url(Path(user_data_dir), timeout_ms)
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(login_url, wait_until="domcontentloaded", timeout=timeout_ms)
            await _drive_login_with_fallback(
                page,
                cdp_url,
                login_url=login_url,
                username=username,
                password=password,
                llm=llm,
                timeout_ms=timeout_ms,
            )
            storage_state = dict(await context.storage_state())
        _ensure_authenticated(storage_state)
        return storage_state
    finally:
        if proc is not None:
            # Offload the blocking terminate/wait/kill off the event loop so a slow teardown
            # cannot freeze every other request on the worker (project async convention).
            await asyncio.to_thread(_terminate_and_reap, proc)
        # On Windows the browser may briefly hold handles to the profile dir after exit;
        # retry the removal a few times so temp profiles do not accumulate.
        for _ in range(3):
            shutil.rmtree(user_data_dir, ignore_errors=True)
            if not Path(user_data_dir).exists():
                break
            await asyncio.sleep(0.3)
