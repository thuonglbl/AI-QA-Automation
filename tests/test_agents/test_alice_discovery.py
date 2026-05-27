from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_qa.agents.alice import AliceAgent
from ai_qa.config import AppSettings


@pytest.fixture
def mock_settings():
    settings = AppSettings()
    settings.claude_api_base_url = "https://mock-claude.com"
    return settings


@pytest.fixture
def alice(mock_settings, tmp_path):
    agent = AliceAgent(workspace_dir=tmp_path)
    agent._settings = mock_settings
    return agent


@pytest.mark.asyncio
async def test_fetch_available_models_success(alice):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "model-1"}, {"id": "model-2"}]}
        mock_get.return_value = mock_response

        models = await alice._fetch_available_models("https://test.com", "key")
        assert len(models) == 2
        assert models[0]["id"] == "model-1"


@pytest.mark.asyncio
async def test_assign_models_via_llm_fallback(alice):
    # Test fallback when LLM fails
    available_models = [{"id": "model-1"}, {"id": "opus"}]
    with patch("ai_qa.ai_connection.client.LLMClient.invoke", side_effect=Exception("LLM error")):
        mappings, reasoning = await alice._assign_models_via_llm(
            "claude", "https://test.com", "key", "opus", available_models
        )
        assert mappings["bob"] == "opus"
        assert reasoning[0]["agent"] == "bob"
        assert "Fallback heuristic" in reasoning[0]["rationale"]


def test_bootstrap_alice_model(alice):
    available_models = [
        {"id": "model-1"},
        {"id": "claude-3-opus-20240229"},
        {"id": "claude-3-sonnet"},
    ]
    model = alice._bootstrap_alice_model(available_models)
    assert model == "claude-3-opus-20240229"


@pytest.mark.asyncio
async def test_fetch_available_models_list_strings(alice):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = ["model-1", "model-2"]
        mock_get.return_value = mock_response

        models = await alice._fetch_available_models("https://test.com", "key")
        assert len(models) == 2
        assert models[0]["id"] == "model-1"
        assert models[0]["name"] == "model-1"


@pytest.mark.asyncio
async def test_assign_models_via_llm_invalid_assignment(alice):
    # Test when LLM assigns an invalid model not in available_models
    available_models = [{"id": "model-1"}]
    mock_response = MagicMock()
    mock_response.content = '{"assignments": {"bob": "fake-model"}, "reasoning": []}'

    with patch("ai_qa.ai_connection.client.LLMClient.invoke", return_value=mock_response):
        mappings, reasoning = await alice._assign_models_via_llm(
            "claude", "https://test.com", "key", "model-1", available_models
        )
        assert mappings["bob"] == "model-1"  # fallback to alice_model
        assert reasoning[0]["model"] == "model-1"
        assert "invalid model" in reasoning[0]["rationale"]


def test_bootstrap_alice_model_empty(alice):
    assert alice._bootstrap_alice_model([]) == ""
