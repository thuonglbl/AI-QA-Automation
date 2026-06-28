"""Interactive MFA manager for pausing and resuming browser logins.

This module provides an in-memory dictionary of asyncio Futures. When the headless
browser hits an MFA screen, it can wait on a Future. The frontend can then submit
the MFA code via a REST endpoint to resolve the Future and unblock the browser.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

# In-memory store of pending MFA requests.
# Key: session_id (e.g. project_id + "_" + environment + "_" + role or a UUID)
# Value: Future that will resolve to the 6-digit MFA code
_pending_mfas: dict[str, asyncio.Future[str]] = {}


async def wait_for_mfa(session_id: str, timeout_seconds: int = 120) -> str:
    """Wait for the user to submit an MFA code for the given session_id.

    Raises asyncio.TimeoutError if the user doesn't submit a code in time.
    """
    loop = asyncio.get_running_loop()
    future: asyncio.Future[str] = loop.create_future()
    _pending_mfas[session_id] = future

    logger.info(
        "Waiting for Interactive MFA code for session '%s' (timeout=%ds)...",
        session_id,
        timeout_seconds,
    )
    try:
        code = await asyncio.wait_for(future, timeout=timeout_seconds)
        logger.info("Received Interactive MFA code for session '%s'", session_id)
        return code
    finally:
        _pending_mfas.pop(session_id, None)


def submit_mfa(session_id: str, code: str) -> bool:
    """Submit the MFA code to unblock a waiting browser session.

    Returns True if the session was found and unblocked, False otherwise.
    """
    future = _pending_mfas.get(session_id)
    if not future:
        logger.warning("No pending MFA request found for session '%s'", session_id)
        return False

    if not future.done():
        future.set_result(code)
        return True

    return False
