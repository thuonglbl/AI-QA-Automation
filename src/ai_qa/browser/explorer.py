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

import logging
import os
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
    user_data_dir: str | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
    use_vision: bool = True,
) -> Any | None:
    """Run a browser-use agent through ``test_case``; return its history or ``None``.

    Two browser modes:
      * **CDP connect** (``cdp_url`` set) -- attach to an ALREADY-RUNNING Chrome
        started with ``--remote-debugging-port`` and reuse its live, authenticated
        SSO session (no profile lock, no re-login). Preferred for SSO apps.
      * **Launch** (``chrome_path`` set) -- launch a fresh Chrome (optionally with
        ``user_data_dir`` to reuse a logged-in profile; Chrome must be closed).

    Args:
        test_case: The approved test case to explore.
        target_url: The application URL to test against.
        llm: A ``browser_use.llm`` chat model (from ``build_browser_use_llm``).
        chrome_path: Path to the user's Chrome executable (launch mode).
        cdp_url: CDP URL of a running Chrome (connect mode, e.g. http://localhost:9222).
        user_data_dir: Optional Chrome profile dir for SSO reuse in launch mode.
        max_steps: Max agent steps before stopping.
        use_vision: Whether the agent may use screenshots (browser-use auto-disables
            for DeepSeek regardless).

    Returns:
        The browser-use ``AgentHistoryList`` on success, else ``None`` (caller
        falls back to LLM-only generation).
    """
    if not target_url or llm is None or (not chrome_path and not cdp_url):
        return None

    # Self-hosted: never phone home to Browser Use Cloud telemetry/sync.
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
    os.environ.setdefault("BROWSER_USE_CLOUD_SYNC", "false")

    try:
        from browser_use import Agent, BrowserProfile

        if cdp_url:
            # Connect to the running Chrome and reuse its live SSO session.
            profile = BrowserProfile(cdp_url=cdp_url)
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


__all__ = ["build_exploration_task", "explore_test_case", "DEFAULT_MAX_STEPS"]
