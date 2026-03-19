class AIConnectionError(Exception):
    """Cannot reach the AI server."""


class AITimeoutError(AIConnectionError):
    """Server did not respond in time."""


class AIAuthError(Exception):
    """Authentication failed (401/403)."""


class AIRequestError(Exception):
    """Server returned an HTTP error."""
