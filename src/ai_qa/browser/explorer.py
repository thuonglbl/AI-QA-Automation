"""Drive the real app with browser-use to capture a verified action trace.

This is the live, integration-only half of browser-use-driven script generation:
a ``browser_use.Agent`` (driven by the thread's configured LLM via
:func:`ai_qa.browser.llm_factory.build_browser_use_llm`) is run through a test
case against the target app in the user's local Chrome (reusing the active SSO
session), and its recorded ``AgentHistoryList`` is returned. The script generator
then translates that VERIFIED trace into a deterministic Playwright script.

Every failure is swallowed (returns ``None``) so the caller falls back to
LLM-only generation — the live browser / reachable-app / active-SSO prerequisites
are not always available (e.g. CI), exactly like the existing vision path.
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from ai_qa.models import TestCase

logger = logging.getLogger(__name__)

# Default ceiling on agent steps per test case (tunable knob from the design doc).
DEFAULT_MAX_STEPS = 25


def build_exploration_task(test_case: TestCase, target_url: str) -> str:
    """Compose the natural-language task that browser-use executes for a test case."""
    objective = getattr(test_case, "objective", "") or test_case.title
    lines = [
        f"You are QA-testing a web application at {target_url}.",
        "Assume you are ALREADY authenticated (an active SSO session) — do NOT log in "
        "or type any username/password/credentials.",
        f"Goal: {objective}",
        "Perform these steps in order, exactly as a tester would:",
    ]
    for step in test_case.steps:
        detail = step.action
        target = getattr(step, "target", None)
        data = getattr(step, "data", None)
        if target:
            detail += f" (target: {target})"
        if data:
            detail += f" (data: {data})"
        lines.append(f"{step.number}. {detail}")
    if test_case.expected_results:
        lines.append("The test succeeds when: " + "; ".join(test_case.expected_results))
    lines.append("Do not perform destructive actions beyond what the steps require.")
    return "\n".join(lines)


async def explore_test_case(
    test_case: TestCase,
    target_url: str,
    *,
    llm: Any,
    chrome_path: str = "",
    cdp_url: str = "",
    storage_state: dict[str, Any] | None = None,
    user_data_dir: str | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
    use_vision: bool = True,
    headless: bool = True,
) -> Any | None:
    """Run a browser-use agent through ``test_case``; return its history or ``None``.

    Three browser modes (precedence in this order):
      * **CDP connect** (``cdp_url`` set) -- attach to an ALREADY-RUNNING Chrome
        started with ``--remote-debugging-port`` and reuse its live, authenticated
        SSO session (no profile lock, no re-login). Preferred for a local QA Chrome.
      * **Session launch** (``storage_state`` set, no ``cdp_url``) -- the Tier-1
        SERVER-SIDE path: launch a browser with the user's captured Playwright
        ``storageState`` (cookies + localStorage) injected, so the run is
        authenticated without any local Chrome / live SSO. The blob is written to a
        secure temp JSON file (browser-use's ``storage_state`` accepts a path),
        which is ALWAYS deleted afterwards. ``executable_path`` defaults to None so
        browser-use uses its managed/bundled Chromium (the UAT container provides
        it); ``chrome_path`` overrides when set. ``user_data_dir`` MUST be None —
        a persistent profile conflicts with ``storage_state``.
      * **Launch** (``chrome_path`` set, no ``cdp_url``/``storage_state``) -- launch a
        fresh Chrome (optionally with ``user_data_dir`` to reuse a logged-in profile;
        Chrome must be closed).

    Args:
        test_case: The approved test case to explore.
        target_url: The application URL to test against.
        llm: A ``browser_use.llm`` chat model (from ``build_browser_use_llm``).
        chrome_path: Path to a Chrome executable (launch / session-launch override).
        cdp_url: CDP URL of a running Chrome (connect mode, e.g. http://localhost:9222).
        storage_state: Decrypted Playwright storageState dict (session-launch mode).
            NEVER logged.
        user_data_dir: Optional Chrome profile dir for SSO reuse in plain launch mode.
        max_steps: Max agent steps before stopping.
        use_vision: Whether the agent may use screenshots (browser-use auto-disables
            for DeepSeek regardless).
        headless: Whether the session-launch browser runs headless (True on the
            server; ignored for connect mode, which reuses the running Chrome).

    Returns:
        The browser-use ``AgentHistoryList`` on success, else ``None`` (caller
        falls back to LLM-only generation).
    """
    if not target_url or llm is None or (not chrome_path and not cdp_url and not storage_state):
        return None

    # Self-hosted: never phone home to Browser Use Cloud telemetry/sync.
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
    os.environ.setdefault("BROWSER_USE_CLOUD_SYNC", "false")

    storage_state_path: str | None = None
    try:
        from browser_use import Agent, BrowserProfile

        if cdp_url:
            # Connect to the running Chrome and reuse its live SSO session.
            profile = BrowserProfile(cdp_url=cdp_url)
        elif storage_state is not None:
            # Tier-1 server-side: inject the captured session via a secure temp file.
            # storage_state + user_data_dir conflict, so user_data_dir MUST be None.
            fd, storage_state_path = tempfile.mkstemp(suffix=".json", prefix="aiqa_ss_")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(storage_state, fh)
            profile = BrowserProfile(
                storage_state=storage_state_path,
                executable_path=chrome_path or None,
                headless=headless,
                user_data_dir=None,
            )
        else:
            profile = BrowserProfile(
                executable_path=chrome_path,
                headless=False,  # visible so an SSO login can complete if prompted
                user_data_dir=user_data_dir or None,
            )
        agent: Any = Agent(
            task=build_exploration_task(test_case, target_url),
            llm=llm,
            browser_profile=profile,
            use_vision=use_vision,
        )
        history = await agent.run(max_steps=max_steps)
        return history
    except Exception as exc:  # noqa: BLE001 — degrade to fallback on any browser/agent error
        logger.warning(
            "browser-use exploration failed for '%s' (%s) — falling back to LLM-only generation",
            test_case.title,
            type(exc).__name__,
        )
        return None
    finally:
        # ALWAYS remove the temp session file — it holds a live credential.
        if storage_state_path is not None:
            try:
                Path(storage_state_path).unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Could not delete temp session file (%s)", type(exc).__name__)


__all__ = ["build_exploration_task", "explore_test_case", "DEFAULT_MAX_STEPS"]
