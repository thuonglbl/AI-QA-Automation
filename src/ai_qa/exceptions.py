"""Custom exception hierarchy for AI QA Automation.

All exceptions inherit from AIQAError. Pipeline components MUST raise
exceptions from this module — never generic Exception or bare except:.

Hierarchy:
    AIQAError (base)
    ├── ConfigError      — configuration invalid or missing
    ├── LLMError         — LLM call failure (timeout, API error, parsing)
    ├── MCPError         — MCP server call failure
    ├── BrowserError     — browser automation failure
    │   ├── SessionError          — SSO session management failure
    │   ├── NavigationError       — page navigation failure
    │   ├── VisionError           — vision model analysis failure
    │   └── LocatorValidationError — DOM locator validation failure
    └── PipelineError    — pipeline orchestration failure
"""


class AIQAError(Exception):
    """Base exception for all AI QA Automation errors.

    Args:
        message: User-friendly description of what went wrong.
        details: Optional technical details for debugging (not shown to end users).
    """

    def __init__(self, message: str, details: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message

    def __repr__(self) -> str:
        if self.details:
            return f"{type(self).__name__}(message={self.message!r}, details={self.details!r})"
        return f"{type(self).__name__}(message={self.message!r})"


class ConfigError(AIQAError):
    """Raised when configuration is invalid or required values are missing.

    Examples: missing API key, invalid URL format, conflicting settings.
    """


class LLMError(AIQAError):
    """Raised when an LLM call fails.

    Examples: API timeout, rate limit exceeded, malformed response, max retries exceeded.
    """


class LLMTimeoutError(LLMError):
    """Raised when an LLM call times out."""


class LLMAuthenticationError(LLMError):
    """Raised when an LLM call fails due to authentication issues."""


class LLMRateLimitError(LLMError):
    """Raised when an LLM provider rejects a call due to rate limit / quota / billing.

    Examples: HTTP 429 (rate limit / insufficient quota), free-plan quota
    exhausted, "credit balance too low" billing errors. These do not recover on
    a short retry and the provider's own message should be surfaced to the user.
    """


class LLMProviderError(LLMError):
    """Raised when an LLM provider returns an error (e.g. 5xx)."""


class ScriptGenerationError(LLMError):
    """Raised when script generation via LLM fails.

    Examples: empty response, invalid script content, generation timeout,
    malformed output that cannot be written to file.
    """


class MCPError(AIQAError):
    """Raised when an MCP server call fails.

    Examples: connection refused, tool call error, unexpected response schema.
    """


class MCPConnectionError(MCPError):
    """Raised when MCP server connection fails.

    Examples: connection refused, timeout, network unavailable.
    """


class MCPAuthenticationError(MCPError):
    """Raised when MCP server authentication fails.

    Examples: invalid token, expired credentials, SSO failure.
    """


class MCPToolError(MCPError):
    """Raised when MCP tool execution fails.

    Examples: tool not found, invalid parameters, execution timeout.
    """


class MCPTimeoutError(MCPError):
    """Raised when MCP operation times out."""


class BrowserError(AIQAError):
    """Raised when browser automation fails.

    Examples: page load timeout, element not found, browser crash.
    """


class SessionError(BrowserError):
    """Raised when SSO session management fails.

    Examples: unable to detect active session, session expired, cookie access denied.
    """


class NavigationError(BrowserError):
    """Raised when page navigation fails.

    Examples: invalid URL, network error, page load timeout.
    """


class VisionError(BrowserError):
    """Raised when vision model analysis fails.

    Examples: screenshot capture failure, vision model timeout,
    element identification error, invalid visual analysis response.
    """


class LocatorValidationError(BrowserError):
    """Raised when DOM locator validation fails.

    Examples: selector not found, ambiguous selector matches multiple elements,
    selector validation timeout, invalid selector syntax.
    """


class PipelineError(AIQAError):
    """Raised when pipeline orchestration fails.

    Examples: stage dependency missing, invalid stage result, pipeline aborted.
    """


class PipelineSilentAbortError(PipelineError):
    """Raised to abort pipeline processing without logging or error state.

    Signals that the error has already been surfaced via a thinking trace or
    connection-test status message, and no additional error handling should
    occur. Catch this specifically — never match on string content.
    """

    def __init__(self) -> None:
        super().__init__("Pipeline silently aborted")
