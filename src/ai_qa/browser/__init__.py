"""Browser automation module using browser-use framework.

This module provides browser agent configuration and SSO session management
for read-only navigation and vision-assisted locator identification.
"""

from ai_qa.browser.agent import BrowserAgent
from ai_qa.browser.session import SessionManager

__all__ = ["BrowserAgent", "SessionManager"]
