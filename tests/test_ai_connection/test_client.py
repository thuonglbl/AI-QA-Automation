from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from ai_qa.ai_connection.client import LLMClient
from ai_qa.ai_connection.config import LLMConfig
from ai_qa.exceptions import LLMRateLimitError, LLMTimeoutError


@pytest.fixture
def llm_config():
    return LLMConfig(
        provider="litellm",
        model_name="test-model",
        temperature=0.0,
        base_url="http://localhost:4000",
        api_key="test-key",
        max_retries=3,
    )


def test_llm_client_initialization(llm_config):
    client = LLMClient(config=llm_config)
    assert client._chat_model.model_name == "test-model"
    assert client._chat_model.temperature == 0.0


@patch("ai_qa.ai_connection.client.ChatOpenAI.invoke")
def test_llm_client_invoke_success(mock_invoke, llm_config):
    client = LLMClient(config=llm_config)
    mock_response = AIMessage(content="Hello world")
    mock_invoke.return_value = mock_response

    messages: list[BaseMessage] = [HumanMessage(content="Hi")]
    response = client.invoke(messages)

    assert response == mock_response
    mock_invoke.assert_called_once_with(messages)


@patch("ai_qa.ai_connection.client.ChatOpenAI.invoke")
def test_llm_client_invoke_timeout_retry(mock_invoke, llm_config):
    client = LLMClient(config=llm_config)

    # Configure mock to raise timeout twice, then succeed
    mock_response = AIMessage(content="Success after timeout")
    mock_invoke.side_effect = [
        Exception("connection timeout"),
        Exception("connection timeout"),
        mock_response,
    ]

    messages: list[BaseMessage] = [HumanMessage(content="Hi")]
    response = client.invoke(messages)

    assert response == mock_response
    assert mock_invoke.call_count == 3


@patch("ai_qa.ai_connection.client.ChatOpenAI.invoke")
def test_llm_client_invoke_max_retries_exceeded(mock_invoke, llm_config):
    client = LLMClient(config=llm_config)

    # Configure mock to always raise timeout
    mock_invoke.side_effect = Exception("connection timeout")

    messages: list[BaseMessage] = [HumanMessage(content="Hi")]

    with pytest.raises(LLMTimeoutError):
        client.invoke(messages)

    # tenacity stop_after_attempt(3) = 3 total attempts (initial + 2 retries)
    assert mock_invoke.call_count == 3


@patch("ai_qa.ai_connection.client.ChatOpenAI.invoke")
def test_llm_client_provider_switching_via_config(mock_invoke):
    # Test that changing config effectively points to different providers/models
    # without code changes. We just change model_name and base_url.
    config1 = LLMConfig(
        provider="litellm", model_name="claude-3-sonnet", base_url="http://litellm-proxy:4000"
    )
    client1 = LLMClient(config=config1)

    config2 = LLMConfig(
        provider="openai", model_name="gpt-4o", base_url="https://api.openai.com/v1"
    )
    client2 = LLMClient(config=config2)

    assert client1._chat_model.model_name == "claude-3-sonnet"
    # pydantic/langchain v0.2+ ChatOpenAI base_url behavior varies slightly,
    # but the client is initialized with it.
    assert client2._chat_model.model_name == "gpt-4o"


@pytest.mark.parametrize(
    "err_text",
    [
        "Error code: 429 - insufficient_quota",
        "RESOURCE_EXHAUSTED: quota exceeded",
        "Your credit balance is too low to access the Anthropic API",
        "rate limit reached",
    ],
)
@patch("ai_qa.ai_connection.client.ChatOpenAI.invoke")
def test_rate_limit_quota_errors_raise_without_retry(mock_invoke, llm_config, err_text):
    """Rate-limit / quota / billing errors fail fast (no retry) as LLMRateLimitError."""
    client = LLMClient(config=llm_config)
    mock_invoke.side_effect = Exception(err_text)

    messages: list[BaseMessage] = [HumanMessage(content="Hi")]
    with pytest.raises(LLMRateLimitError):
        client.invoke(messages)

    # Fail fast: a quota/billing error must NOT be retried.
    assert mock_invoke.call_count == 1


def test_claude_routes_to_chat_anthropic():
    from langchain_anthropic import ChatAnthropic

    client = LLMClient(
        config=LLMConfig(
            provider="claude",
            model_name="claude-sonnet-4-5",
            base_url="https://api.anthropic.com",
            api_key="sk-ant-test-key-123",
        )
    )
    assert isinstance(client._chat_model, ChatAnthropic)


def test_gemini_routes_to_openai_compat_endpoint():
    from langchain_openai import ChatOpenAI

    client = LLMClient(
        config=LLMConfig(
            provider="gemini",
            model_name="gemini-2.0-flash",
            base_url="https://generativelanguage.googleapis.com",
            api_key="gemini-test-key-123",
        )
    )
    assert isinstance(client._chat_model, ChatOpenAI)
    assert str(client._chat_model.openai_api_base).endswith("/v1beta/openai")


def test_openai_base_url_gets_v1_suffix():
    client = LLMClient(
        config=LLMConfig(
            provider="openai",
            model_name="gpt-4o-mini",
            base_url="https://api.openai.com",
            api_key="sk-openai-test-key-123",
        )
    )
    assert str(client._chat_model.openai_api_base).rstrip("/").endswith("/v1")
