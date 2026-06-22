"""Capture a Playwright ``storageState`` from a user-launched debug browser over CDP.

The user launches Chrome/Edge with ``--remote-debugging-port=<port>`` and logs in
(including corporate SSO — done by hand, never automated). This connects to that running
browser via CDP and exports its session (cookies + localStorage). Integration-only: it
requires a live debug browser, so it is not exercised by unit tests — the underlying
``connectOverCDP().storageState()`` flow was hand-validated on a real managed machine.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CDP_URL = "http://localhost:9222"


class SessionCaptureError(RuntimeError):
    """Raised when capturing a storageState over CDP fails (browser not reachable, etc.)."""


async def capture_storage_state_over_cdp(cdp_url: str = DEFAULT_CDP_URL) -> dict[str, Any]:
    """Connect to a debug browser at ``cdp_url`` and return its Playwright storageState.

    Uses the async Playwright API (FastAPI runs in an event loop, so the sync API would
    raise). Does NOT close the user's browser — only drops the CDP connection.

    Raises:
        SessionCaptureError: the browser is unreachable or exposes no context.
    """
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(cdp_url)
            contexts = browser.contexts
            if not contexts:
                raise SessionCaptureError(
                    "Connected to the debug browser but it has no open page/context — "
                    "open the app and log in first, then capture."
                )
            # storage_state() returns a StorageState TypedDict; normalize to a plain dict.
            return dict(await contexts[0].storage_state())
    except SessionCaptureError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface a clean message; browser/CDP failures vary
        logger.warning("Session capture over CDP (%s) failed: %s", cdp_url, exc)
        raise SessionCaptureError(
            f"Could not reach a debug browser at {cdp_url}. Launch Chrome/Edge with "
            "--remote-debugging-port=9222, log in, then try again."
        ) from exc
