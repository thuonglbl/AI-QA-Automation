"""AI QA Automation pipeline — intelligent test generation from Confluence."""

import warnings

# Suppress LangChain Pydantic V1 compatibility warning for Python 3.14
warnings.filterwarnings(
    "ignore",
    message=".*Core Pydantic V1 functionality isn't compatible with Python 3.14.*",
    category=UserWarning,
)
from ai_qa.exceptions import (  # noqa: E402
    AIQAError,
    BrowserError,
    ConfigError,
    LLMError,
    MCPAuthenticationError,
    MCPConnectionError,
    MCPError,
    MCPTimeoutError,
    MCPToolError,
    PipelineError,
)
from ai_qa.models import AgentMessage, StageResult  # noqa: E402

__all__ = [
    # Exceptions
    "AIQAError",
    "ConfigError",
    "LLMError",
    "MCPError",
    "MCPConnectionError",
    "MCPAuthenticationError",
    "MCPToolError",
    "MCPTimeoutError",
    "BrowserError",
    "PipelineError",
    # Models
    "StageResult",
    "AgentMessage",
]
