import json
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from ai_qa.ai_connection.client import LLMClient
from ai_qa.ai_connection.config import LLMConfig
from ai_qa.exceptions import LLMTimeoutError


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

    messages = [HumanMessage(content="Hi")]
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

    messages = [HumanMessage(content="Hi")]
    response = client.invoke(messages)

    assert response == mock_response
    assert mock_invoke.call_count == 3


@patch("ai_qa.ai_connection.client.ChatOpenAI.invoke")
def test_llm_client_invoke_max_retries_exceeded(mock_invoke, llm_config):
    client = LLMClient(config=llm_config)

    # Configure mock to always raise timeout
    mock_invoke.side_effect = Exception("connection timeout")

    messages = [HumanMessage(content="Hi")]

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


def test_llm_config_from_agents_json_success():
    """Test successful loading of configuration from agents.json."""
    import tempfile

    agents_config = {
        "version": "1.0",
        "updated_at": "2026-04-17T10:30:00Z",
        "agents": {
            "mary": {
                "model": "claude-3-sonnet-20240229",
                "temperature": 0.0,
                "prompt_template": "test_case_generation_v1",
                "tools": ["test_case_extractor"],
            }
        },
    }

    provider_config = {
        "provider": "claude",
        "provider_name": "Claude (Anthropic)",
        "endpoint": "https://api.anthropic.com",
        "credential_reference": "env://ANTHROPIC_API_KEY",
        "tested_at": "2026-04-17T10:30:00Z",
        "test_result": "success",
    }

    # Create temporary directory structure
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / "workspace" / "configuration"
        config_dir.mkdir(parents=True)

        agents_file = config_dir / "agents.json"
        provider_file = config_dir / "provider.json"

        # Write test configuration files
        agents_file.write_text(json.dumps(agents_config))
        provider_file.write_text(json.dumps(provider_config))

        # Test loading configuration
        config = LLMConfig.from_agents_json("mary", agents_file=agents_file)

        assert config.model_name == "claude-3-sonnet-20240229"
        assert config.temperature == 0.0
        assert config.provider == "claude"
        assert config.base_url == "https://api.anthropic.com"


def test_llm_config_from_agents_json_file_not_found():
    """Test error when agents.json file doesn't exist."""
    with patch("pathlib.Path.exists") as mock_exists:
        mock_exists.return_value = False

        with pytest.raises(FileNotFoundError, match="Agents configuration file not found"):
            LLMConfig.from_agents_json("mary")


def test_llm_config_from_agents_json_agent_not_found():
    """Test error when agent name is not in configuration."""
    agents_config = {"version": "1.0", "agents": {"bob": {"model": "claude-3-opus-20240229"}}}

    with patch("builtins.open", mock_open(read_data=json.dumps(agents_config))):
        with patch("pathlib.Path.exists") as mock_exists:
            mock_exists.return_value = True

            with pytest.raises(KeyError, match="Agent 'mary' not found in configuration"):
                LLMConfig.from_agents_json("mary")


def test_llm_client_with_agents_json_config():
    """Test LLMClient initialization using config loaded from agents.json."""
    import tempfile

    agents_config = {
        "version": "1.0",
        "agents": {
            "mary": {
                "model": "claude-3-sonnet-20240229",
                "temperature": 0.1,
                "prompt_template": "test_case_generation_v1",
                "tools": ["test_case_extractor"],
            }
        },
    }

    provider_config = {
        "provider": "litellm",
        "endpoint": "http://localhost:4000",
        "tested_at": "2026-04-17T10:30:00Z",
        "test_result": "success",
    }

    # Create temporary directory structure
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / "workspace" / "configuration"
        config_dir.mkdir(parents=True)

        agents_file = config_dir / "agents.json"
        provider_file = config_dir / "provider.json"

        # Write test configuration files
        agents_file.write_text(json.dumps(agents_config))
        provider_file.write_text(json.dumps(provider_config))

        # Test loading configuration and creating client
        config = LLMConfig.from_agents_json("mary", agents_file=agents_file)
        client = LLMClient(config=config)

        assert client._chat_model.model_name == "claude-3-sonnet-20240229"
        assert client._chat_model.temperature == 0.1
