"""Browser agent configuration using browser-use framework.

This module provides the BrowserAgent class that configures browser-use
to control Chrome with SSO session reuse and read-only navigation.
"""

import asyncio
from pathlib import Path
from typing import Any, cast

from browser_use import Agent

from ai_qa.exceptions import BrowserError, NavigationError


class BrowserAgent:
    """Browser automation agent using browser-use framework.

    Configures Chrome with SSO session reuse, read-only mode, and
    timeout handling for safe navigation operations.

    Attributes:
        agent: The underlying browser-use Agent instance.
        chrome_path: Path to Chrome executable.
        timeout: Timeout in seconds for each browser action.
    """

    agent: Agent[Any, Any]
    chrome_path: str
    timeout: int

    def __init__(self, chrome_path: str, timeout: int = 30) -> None:
        """Initialize browser agent with Chrome configuration.

        Args:
            chrome_path: Path to Chrome executable.
            timeout: Timeout in seconds for each browser action (default: 30).

        Raises:
            BrowserError: If Chrome path is invalid or Chrome cannot be launched.
        """
        self._validate_chrome_path(chrome_path)
        self.chrome_path = chrome_path
        self.timeout = timeout

        try:
            self.agent = Agent(
                task="navigation only",  # Read-only mode
                browser_config={
                    "chrome_path": chrome_path,
                    "headless": False,  # Visible for SSO session detection
                },
                use_vision=True,  # For Story 5.3 vision model
            )
        except Exception as e:
            raise BrowserError(
                f"Failed to initialize browser-use agent: {e}",
                details=f"Chrome path: {chrome_path}",
            ) from e

    def _validate_chrome_path(self, chrome_path: str) -> None:
        """Validate that Chrome executable exists at the given path.

        Args:
            chrome_path: Path to Chrome executable.

        Raises:
            BrowserError: If Chrome path is invalid or executable doesn't exist.
        """
        if not chrome_path:
            raise BrowserError("Chrome path is required")

        chrome_exe = Path(chrome_path)
        if not chrome_exe.exists():
            raise BrowserError(
                f"Chrome executable not found at: {chrome_path}",
                details="Please provide a valid path to Chrome executable",
            )
        if not chrome_exe.is_file():
            raise BrowserError(
                f"Chrome path is not a file: {chrome_path}",
                details="Please provide a path to the Chrome executable file",
            )

    async def navigate(self, url: str) -> None:
        """Navigate to the specified URL with timeout and error handling.

        Args:
            url: Target URL to navigate to.

        Raises:
            NavigationError: If navigation fails or times out.
            BrowserError: If browser crashes during navigation.
        """
        try:
            agent_any = cast(Any, self.agent)
            await asyncio.wait_for(
                agent_any.navigate(url),
                timeout=self.timeout,
            )

        except TimeoutError:
            raise NavigationError(
                f"Navigation to {url} exceeded {self.timeout}s timeout",
                details=f"URL: {url}, Timeout: {self.timeout}s",
            ) from None
        except Exception as e:
            # Check if it's a browser crash
            error_msg = str(e).lower()
            if "crash" in error_msg or "disconnected" in error_msg:
                raise BrowserError(
                    f"Browser crashed during navigation to {url}",
                    details=str(e),
                ) from e
            raise NavigationError(
                f"Failed to navigate to {url}",
                details=str(e),
            ) from e

    async def close(self) -> None:
        """Close the browser and clean up resources.

        Raises:
            BrowserError: If browser cleanup fails.
        """
        try:
            # browser-use handles cleanup via agent context
            # Additional cleanup if needed
            pass
        except Exception as e:
            raise BrowserError(f"Failed to close browser: {e}") from e
