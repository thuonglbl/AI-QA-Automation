"""Tests for the custom exception hierarchy in src/ai_qa/exceptions.py."""

import pytest

from ai_qa.exceptions import (
    AIQAError,
    BrowserError,
    ConfigError,
    LLMError,
    MCPError,
    PipelineError,
)

# --- Inheritance tests ---


def test_all_exceptions_inherit_from_aiqa_error() -> None:
    """All custom exceptions must inherit from AIQAError."""
    for exc_class in (ConfigError, LLMError, MCPError, BrowserError, PipelineError):
        assert issubclass(exc_class, AIQAError), f"{exc_class.__name__} must inherit AIQAError"


def test_aiqa_error_inherits_from_exception() -> None:
    """AIQAError must be catchable as a standard Exception."""
    assert issubclass(AIQAError, Exception)


# --- Constructor tests ---


def test_aiqa_error_message_only() -> None:
    """AIQAError stores message attribute; details defaults to None."""
    err = AIQAError("Something went wrong")
    assert err.message == "Something went wrong"
    assert err.details is None
    assert str(err) == "Something went wrong"


def test_aiqa_error_with_details() -> None:
    """AIQAError stores both message and details when provided."""
    err = AIQAError("Something went wrong", details="Technical context here")
    assert err.message == "Something went wrong"
    assert err.details == "Technical context here"


def test_child_exception_inherits_constructor() -> None:
    """Child exceptions support message + details via inherited constructor."""
    err = LLMError("LLM call failed", details="HTTP 429 rate limited")
    assert err.message == "LLM call failed"
    assert err.details == "HTTP 429 rate limited"
    assert str(err) == "LLM call failed"


# --- Raise and catch tests ---


def test_can_raise_and_catch_by_specific_type() -> None:
    """Each exception type can be raised and caught by its specific class."""
    with pytest.raises(ConfigError):
        raise ConfigError("Bad config")

    with pytest.raises(LLMError):
        raise LLMError("LLM failed")

    with pytest.raises(MCPError):
        raise MCPError("MCP failed")

    with pytest.raises(BrowserError):
        raise BrowserError("Browser crashed")

    with pytest.raises(PipelineError):
        raise PipelineError("Pipeline aborted")


def test_can_catch_specific_as_aiqa_error() -> None:
    """Specific exceptions can be caught by AIQAError base class."""
    with pytest.raises(AIQAError):
        raise LLMError("caught as base")

    with pytest.raises(AIQAError):
        raise ConfigError("caught as base")


def test_can_catch_specific_as_exception() -> None:
    """All custom exceptions are catchable as standard Exception via AIQAError."""
    with pytest.raises(AIQAError):
        raise PipelineError("caught as Exception")


# --- repr tests ---


def test_repr_without_details() -> None:
    """__repr__ shows class name and message when no details."""
    err = ConfigError("missing key")
    assert "ConfigError" in repr(err)
    assert "missing key" in repr(err)


def test_repr_with_details() -> None:
    """__repr__ includes details when provided."""
    err = MCPError("connection failed", details="refused on port 8080")
    r = repr(err)
    assert "MCPError" in r
    assert "connection failed" in r
    assert "refused on port 8080" in r


# --- Integration tests ---


def test_config_error_usage_pattern() -> None:
    """Test the usage pattern from __main__.py."""
    with pytest.raises(ConfigError) as exc_info:
        raise ConfigError(
            "No AI provider configured.",
            details=(
                "Set ANTHROPIC_API_KEY, or both ON_PREMISES_AI_SERVER_URL and "
                "ON_PREMISES_AI_SERVER_KEY in .env, config.yaml, or environment variables."
            ),
        )
    assert exc_info.value.message == "No AI provider configured."
    assert "ANTHROPIC_API_KEY" in exc_info.value.details
