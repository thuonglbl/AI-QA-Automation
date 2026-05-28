"""Tests for Alice Agent — AI Provider Selection & Configuration."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ai_qa.agents.alice import AliceAgent
from ai_qa.agents.base import AgentState
from ai_qa.db.models import User
from ai_qa.exceptions import PipelineError
from ai_qa.models import (
    AgentModelConfig,
    AgentsConfig,
    AliceConfiguration,
    ProviderConfig,
    StageResult,
)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = 1
    user.settings = {}
    user.ai_provider_config = None
    user.ai_agents_config = None
    user.email = "test@example.com"
    return user


@pytest.fixture
def alice(mock_db, mock_user):
    agent = AliceAgent()
    agent.project_context = MagicMock()
    agent.project_context.artifact_service.db = mock_db
    agent.project_context.user_id = 1

    def mock_get(model, id):
        if model.__name__ == "User" and id == 1:
            return mock_user
        return None

    mock_db.get.side_effect = mock_get

    # Disable broadcast to avoid errors if missing fixture
    agent.broadcast_message = AsyncMock()  # type: ignore

    return agent


@pytest.fixture
def mock_broadcast():
    with patch("ai_qa.api.websocket.broadcast_message", new_callable=AsyncMock) as mock:
        yield mock


class TestAliceInitialization:
    def test_agent_properties(self, alice: AliceAgent) -> None:
        assert alice.name == "Alice"
        assert alice.color == "#EC4899"
        assert alice.step_number == 1
        assert alice.step_title == "AI Provider Configuration"

    def test_initial_state(self, alice: AliceAgent) -> None:
        assert alice.state == AgentState.START


class TestProviderOptions:
    def test_get_provider_options_structure(self, alice: AliceAgent) -> None:
        options = alice.get_provider_options()
        assert len(options) == 4
        provider_ids = [p["id"] for p in options]
        assert "browser-use-cloud" in provider_ids
        assert "claude" in provider_ids
        assert "gemini-chatgpt" in provider_ids
        assert "on-premises" in provider_ids

    def test_provider_quality_ranks(self, alice: AliceAgent) -> None:
        options = alice.get_provider_options()
        by_id = {p["id"]: p for p in options}
        assert by_id["browser-use-cloud"]["quality_rank"] == 1
        assert by_id["claude"]["quality_rank"] == 2
        assert by_id["gemini-chatgpt"]["quality_rank"] == 3
        assert by_id["on-premises"]["quality_rank"] == 4

    def test_provider_security_levels(self, alice: AliceAgent) -> None:
        options = alice.get_provider_options()
        by_id = {p["id"]: p for p in options}
        assert by_id["browser-use-cloud"]["security_level"] == "cloud"
        assert by_id["claude"]["security_level"] == "enterprise"
        assert by_id["gemini-chatgpt"]["security_level"] == "cloud"
        assert by_id["on-premises"]["security_level"] == "highest"

    def test_credential_fields(self, alice: AliceAgent) -> None:
        options = alice.get_provider_options()
        by_id = {p["id"]: p for p in options}
        for provider_id in ["browser-use-cloud", "claude", "gemini-chatgpt", "on-premises"]:
            fields = by_id[provider_id]["credential_fields"]
            assert len(fields) >= 1
            if provider_id == "on-premises":
                assert fields[0]["name"] == "api_key"
            else:
                assert fields[0]["name"] == "api_key"


class TestOnPremDefaults:
    def test_get_on_prem_defaults_empty(self, alice: AliceAgent) -> None:
        defaults = alice.get_on_prem_defaults()
        assert defaults["server_url"] == ""
        assert defaults["api_key"] == ""

    def test_get_on_prem_defaults_from_user(self, alice: AliceAgent, mock_user) -> None:
        mock_user.settings = {
            "on_premises_ai_server_url": "http://test",
            "on_premises_ai_server_key": "key123",
        }
        defaults = alice.get_on_prem_defaults()
        assert defaults["server_url"] == "http://test"
        assert defaults["api_key"] == "key123"


class TestProcessWorkflow:
    @pytest.mark.asyncio
    @patch.object(AliceAgent, "_test_connection", return_value=True)
    @patch.object(AliceAgent, "_generate_configuration")
    async def test_process_valid_credentials(
        self, mock_generate, mock_test, alice: AliceAgent, mock_user, mock_db
    ) -> None:
        mock_config = MagicMock()
        mock_config.model_dump.return_value = {"dump": "data"}
        mock_config.provider.endpoint = "http://test"
        mock_generate.return_value = mock_config

        input_data = {
            "provider": "claude",
            "credentials": {"api_key": "test-api-key-12345"},
        }

        result = await alice.process(input_data, feedback=None)

        assert result.success is True
        assert result.data is not None
        assert result.data["configuration"] == {"dump": "data"}
        assert mock_user.settings["anthropic_api_key"] == "test-api-key-12345"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "_test_connection", return_value=True)
    @patch.object(AliceAgent, "_generate_configuration")
    async def test_process_valid_credentials_other_providers(
        self, mock_generate, mock_test, alice: AliceAgent, mock_user, mock_db
    ) -> None:
        mock_config = MagicMock()
        mock_config.model_dump.return_value = {"dump": "data"}
        mock_config.provider.endpoint = "http://test"
        mock_generate.return_value = mock_config

        for provider, key in [
            ("gemini-chatgpt", "openai_api_key"),
            ("browser-use-cloud", "browser_use_api_key"),
            ("on-premises", "on_premises_ai_server_key"),
        ]:
            mock_user.settings = {}
            input_data = {
                "provider": provider,
                "credentials": {"api_key": "test-api-key-12345"},
            }
            await alice.process(input_data, feedback=None)
            assert mock_user.settings[key] == "test-api-key-12345"

    @pytest.mark.asyncio
    async def test_process_missing_provider(self, alice: AliceAgent) -> None:
        input_data = {"credentials": {"api_key": "test"}}
        with pytest.raises(PipelineError, match="No provider selected"):
            await alice.process(input_data, feedback=None)

    @pytest.mark.asyncio
    async def test_process_invalid_provider(self, alice: AliceAgent) -> None:
        input_data = {"provider": "invalid-provider", "credentials": {"api_key": "test"}}
        with pytest.raises(PipelineError, match="Unknown provider"):
            await alice.process(input_data, feedback=None)

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "_test_connection", return_value=False)
    async def test_process_connection_failed(self, mock_test, alice: AliceAgent) -> None:
        input_data = {"provider": "claude", "credentials": {"api_key": "short"}}
        with pytest.raises(PipelineError, match="Failed to connect"):
            await alice.process(input_data, feedback=None)

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "_test_connection", side_effect=Exception("API Error"))
    async def test_process_connection_exception(self, mock_test, alice: AliceAgent) -> None:
        input_data = {"provider": "claude", "credentials": {"api_key": "validkey123"}}
        with pytest.raises(PipelineError, match="Failed to connect"):
            await alice.process(input_data, feedback=None)

    @pytest.mark.asyncio
    async def test_process_with_feedback(self, alice: AliceAgent) -> None:
        result = await alice.process(input_data={}, feedback="Change provider")
        assert result.success is True
        assert result.data is not None
        assert result.data["action"] == "restart_selection"


class TestConnectionAndFetch:
    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_fetch_available_models_on_prem(self, mock_get, alice: AliceAgent) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": "model-1", "name": "Model 1"}]
        mock_get.return_value = mock_response

        models = await alice._fetch_available_models("on-premises", "http://server", "key")
        assert len(models) == 1
        assert models[0]["id"] == "model-1"

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_fetch_available_models_on_prem_data_format(
        self, mock_get, alice: AliceAgent
    ) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "model-1", "name": "Model 1"}]}
        mock_get.return_value = mock_response

        models = await alice._fetch_available_models("on-premises", "http://server", "key")
        assert len(models) == 1
        assert models[0]["id"] == "model-1"

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_fetch_available_models_on_prem_models_format(
        self, mock_get, alice: AliceAgent
    ) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": [{"name": "model-1"}]}
        mock_get.return_value = mock_response

        models = await alice._fetch_available_models("on-premises", "http://server", "key")
        assert len(models) == 1
        assert models[0]["id"] == "model-1"

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_fetch_available_models_on_prem_exception(
        self, mock_get, alice: AliceAgent
    ) -> None:
        mock_get.side_effect = httpx.RequestError("Connection failed")
        models = await alice._fetch_available_models("on-premises", "http://server", "key")
        assert len(models) == 0

    @pytest.mark.asyncio
    async def test_fetch_available_models_claude(self, alice: AliceAgent) -> None:
        models = await alice._fetch_available_models("claude", "", "")
        assert any(m["id"] == "claude-3-5-sonnet-latest" for m in models)

    @pytest.mark.asyncio
    async def test_fetch_available_models_gemini(self, alice: AliceAgent) -> None:
        models = await alice._fetch_available_models("gemini-chatgpt", "", "")
        assert any(m["id"] == "gpt-4o" for m in models)

    @pytest.mark.asyncio
    async def test_fetch_available_models_browser_use(self, alice: AliceAgent) -> None:
        models = await alice._fetch_available_models("browser-use-cloud", "", "")
        assert any(m["id"] == "gpt-4o" for m in models)

    @pytest.mark.asyncio
    async def test_test_connection_invalid_url(self, alice: AliceAgent) -> None:
        provider_info = {"id": "on-premises", "name": "On Prem", "endpoint": "not-http"}
        assert await alice._test_connection(provider_info, {"api_key": "long-enough-key"}) is False

    @pytest.mark.asyncio
    async def test_test_connection_short_key(self, alice: AliceAgent) -> None:
        provider_info = {"id": "claude", "name": "Claude", "endpoint": ""}
        assert await alice._test_connection(provider_info, {"api_key": "short"}) is False

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "_fetch_available_models", return_value=[])
    async def test_test_connection_no_models(self, mock_fetch, alice: AliceAgent) -> None:
        provider_info = {"id": "claude", "name": "Claude", "endpoint": ""}
        assert await alice._test_connection(provider_info, {"api_key": "validkey123"}) is False

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "_fetch_available_models", return_value=[{"id": "gpt-4"}])
    async def test_test_connection_success(self, mock_fetch, alice: AliceAgent) -> None:
        provider_info = {"id": "claude", "name": "Claude", "endpoint": ""}
        assert await alice._test_connection(provider_info, {"api_key": "validkey123"}) is True


class TestBootstrapAndLLM:
    def test_bootstrap_alice_model(self, alice: AliceAgent) -> None:
        available = [{"id": "gpt-4o", "name": "GPT-4o"}, {"id": "random", "name": "Random"}]
        model = alice._bootstrap_alice_model(available)
        assert model == "gpt-4o"

        available = [{"id": "random", "name": "Random"}]
        model = alice._bootstrap_alice_model(available)
        assert model == "random"

        assert alice._bootstrap_alice_model([]) == ""

    @pytest.mark.asyncio
    async def test_assign_models_via_llm_success(self, alice: AliceAgent) -> None:
        mock_response = MagicMock()
        mock_response.content = '```json\n{"assignments": {"bob": "gpt-4o", "mary": "gpt-4o-mini", "sarah": "gpt-4o-mini", "jack": "gpt-4o-mini"}, "reasoning": []}\n```'

        with patch("ai_qa.ai_connection.client.LLMClient", autospec=True) as mock_client_class:
            mock_instance = mock_client_class.return_value
            mock_instance.invoke.return_value = mock_response
            available = [
                {"id": "gpt-4o", "name": "GPT-4o"},
                {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
            ]
            assignments, reasoning = await alice._assign_models_via_llm(
                "gemini-chatgpt", "http://valid.url", "key", "gpt-4o", available
            )
            assert assignments["bob"] == "gpt-4o"
            assert assignments["mary"] == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_assign_models_via_llm_no_markdown_block(self, alice: AliceAgent) -> None:
        mock_response = MagicMock()
        mock_response.content = (
            '{"assignments": {"bob": "gpt-4o"}, "reasoning": [{"agent": "bob", "rationale": "ok"}]}'
        )
        with patch("ai_qa.ai_connection.client.LLMClient", autospec=True) as mock_client_class:
            mock_instance = mock_client_class.return_value
            mock_instance.invoke.return_value = mock_response
            available = [{"id": "gpt-4o", "name": "GPT-4o"}]
            assignments, reasoning = await alice._assign_models_via_llm(
                "gemini-chatgpt", "http://valid.url", "key", "gpt-4o", available
            )
            assert assignments["bob"] == "gpt-4o"
            assert reasoning[0]["rationale"] == "ok"

    @pytest.mark.asyncio
    async def test_assign_models_via_llm_invalid_assignment(self, alice: AliceAgent) -> None:
        mock_response = MagicMock()
        mock_response.content = '{"assignments": {"bob": "not-exist"}, "reasoning": [{"agent": "bob", "rationale": "ok"}]}'
        with patch("ai_qa.ai_connection.client.LLMClient", autospec=True) as mock_client_class:
            mock_instance = mock_client_class.return_value
            mock_instance.invoke.return_value = mock_response
            available = [{"id": "gpt-4o", "name": "GPT-4o"}]
            assignments, reasoning = await alice._assign_models_via_llm(
                "gemini-chatgpt", "http://valid.url", "key", "gpt-4o", available
            )
            assert assignments["bob"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_assign_models_via_llm_fallback(self, alice: AliceAgent) -> None:
        with patch("ai_qa.ai_connection.client.LLMClient", autospec=True) as mock_client_class:
            mock_instance = mock_client_class.return_value
            mock_instance.invoke.side_effect = Exception("API error")
            available = [{"id": "gpt-4o", "name": "GPT-4o"}]
            assignments, reasoning = await alice._assign_models_via_llm(
                "gemini-chatgpt", "http://valid.url", "key", "gpt-4o", available
            )
            assert assignments["bob"] == "gpt-4o"
            assert assignments["jack"] == "gpt-4o"
            assert "API error" in reasoning[0]["rationale"]

    @pytest.mark.asyncio
    async def test_assign_models_via_llm_no_json(self, alice: AliceAgent) -> None:
        mock_response = MagicMock()
        mock_response.content = "Hello I am an AI, I failed to generate JSON."
        with patch("ai_qa.ai_connection.client.LLMClient", autospec=True) as mock_client_class:
            mock_instance = mock_client_class.return_value
            mock_instance.invoke.return_value = mock_response
            available = [{"id": "gpt-4o", "name": "GPT-4o"}]
            assignments, reasoning = await alice._assign_models_via_llm(
                "gemini-chatgpt", "http://valid.url", "key", "gpt-4o", available
            )
            assert assignments["bob"] == "gpt-4o"


class TestConfigurationAndPersistence:
    @pytest.mark.asyncio
    @patch.object(AliceAgent, "_fetch_available_models")
    @patch.object(AliceAgent, "_assign_models_via_llm")
    async def test_generate_configuration(self, mock_assign, mock_fetch, alice: AliceAgent) -> None:
        mock_fetch.return_value = [{"id": "gpt-4o"}]
        mock_assign.return_value = (
            {"bob": "gpt-4o", "mary": "gpt-4o", "sarah": "gpt-4o", "jack": "gpt-4o"},
            [],
        )

        provider_info = {
            "id": "gemini-chatgpt",
            "name": "Gemini",
            "endpoint": "http://endpoint",
            "env_key": "OPENAI_API_KEY",
        }
        config = await alice._generate_configuration(provider_info, {"api_key": "key12345"})

        assert config.provider.provider == "gemini-chatgpt"
        assert config.agents.agents["bob"].model == "gpt-4o"

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "_fetch_available_models")
    async def test_generate_configuration_no_models(self, mock_fetch, alice: AliceAgent) -> None:
        mock_fetch.return_value = []
        provider_info = {
            "id": "gemini-chatgpt",
            "name": "Gemini",
            "endpoint": "",
            "env_key": "OPENAI_API_KEY",
        }
        with pytest.raises(PipelineError, match="No models discovered"):
            await alice._generate_configuration(provider_info, {"api_key": "key12345"})

    def test_save_configuration(self, alice: AliceAgent, mock_user, mock_db) -> None:
        config = AliceConfiguration(
            provider=ProviderConfig(
                provider="claude",
                provider_name="Claude",
                endpoint="",
                credential_reference="",
                tested_at="",
                test_result="success",
            ),
            agents=AgentsConfig(updated_at="", agents={}),
        )
        alice._save_configuration(config)
        assert mock_user.ai_provider_config is not None
        mock_db.commit.assert_called_once()

    def test_save_configuration_no_user(self, alice: AliceAgent, mock_db) -> None:
        mock_db.get.side_effect = None
        mock_db.get.return_value = None
        config = AliceConfiguration(
            provider=ProviderConfig(
                provider="claude",
                provider_name="c",
                endpoint="",
                credential_reference="",
                tested_at="",
                test_result="success",
            ),
            agents=AgentsConfig(updated_at="", agents={}),
        )
        with pytest.raises(OSError, match="User not found"):
            alice._save_configuration(config)

    def test_save_configuration_no_context(self, alice: AliceAgent) -> None:
        alice.project_context = None
        config = AliceConfiguration(
            provider=ProviderConfig(
                provider="claude",
                provider_name="c",
                endpoint="",
                credential_reference="",
                tested_at="",
                test_result="success",
            ),
            agents=AgentsConfig(updated_at="", agents={}),
        )
        with pytest.raises(OSError, match="No project context"):
            alice._save_configuration(config)


class TestExistingConfiguration:
    @pytest.mark.asyncio
    async def test_check_existing_valid(self, alice: AliceAgent, mock_user) -> None:
        now = datetime.now(UTC).isoformat()
        mock_user.ai_provider_config = {
            "provider": "claude",
            "provider_name": "Claude",
            "endpoint": "",
            "credential_reference": "",
            "tested_at": now,
            "test_result": "success",
        }
        mock_user.ai_agents_config = {"updated_at": now, "agents": {}}

        existing = await alice.check_existing_configuration()
        assert existing is not None
        assert existing.provider.provider == "claude"

    @pytest.mark.asyncio
    async def test_check_existing_expired(self, alice: AliceAgent, mock_user) -> None:
        expired = (datetime.now(UTC) - timedelta(days=31)).isoformat()
        mock_user.ai_provider_config = {
            "provider": "claude",
            "provider_name": "Claude",
            "endpoint": "",
            "credential_reference": "",
            "tested_at": expired,
            "test_result": "success",
        }
        mock_user.ai_agents_config = {"updated_at": expired, "agents": {}}

        existing = await alice.check_existing_configuration()
        assert existing is None

    @pytest.mark.asyncio
    async def test_check_existing_missing(self, alice: AliceAgent) -> None:
        existing = await alice.check_existing_configuration()
        assert existing is None

    @pytest.mark.asyncio
    async def test_check_existing_no_context(self, alice: AliceAgent) -> None:
        alice.project_context = None
        existing = await alice.check_existing_configuration()
        assert existing is None


class TestHandleStartAndApprove:
    @pytest.mark.asyncio
    @patch.object(AliceAgent, "check_existing_configuration")
    async def test_handle_start_with_existing(
        self, mock_check, alice: AliceAgent, mock_broadcast
    ) -> None:
        mock_config = MagicMock()
        mock_config.provider.provider = "claude"
        mock_config.provider.endpoint = ""
        mock_config.agents.agents = {}
        mock_check.return_value = mock_config

        await alice.handle_start({})
        assert alice.state == AgentState.REVIEW_REQUEST

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "check_existing_configuration")
    async def test_handle_start_force_reconfigure(
        self, mock_check, alice: AliceAgent, mock_broadcast
    ) -> None:
        mock_config = MagicMock()
        mock_check.return_value = mock_config

        await alice.handle_start({"force_reconfigure": True})
        # Should bypass existing and show greeting
        assert alice.state == AgentState.START

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "check_existing_configuration", return_value=None)
    async def test_handle_start_no_provider(
        self, mock_check, alice: AliceAgent, mock_broadcast
    ) -> None:
        await alice.handle_start({})
        # Should stay in START state, not transition to REVIEW_REQUEST
        assert alice.state == AgentState.START

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "process")
    async def test_handle_start_with_provider_success(
        self, mock_process, alice: AliceAgent
    ) -> None:
        mock_process.return_value = StageResult(
            success=True,
            data={"model_assignments": [], "configuration": {}, "provider_endpoint": ""},
        )
        await alice.handle_start({"provider": "claude"})
        assert alice.state == AgentState.REVIEW_REQUEST

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "process")
    async def test_handle_start_with_provider_failure(
        self, mock_process, alice: AliceAgent
    ) -> None:
        mock_process.return_value = StageResult(success=False, errors=["Error"])
        await alice.handle_start({"provider": "claude"})
        assert alice.state == AgentState.ERROR

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "process")
    async def test_handle_start_pipeline_error(self, mock_process, alice: AliceAgent) -> None:
        mock_process.side_effect = PipelineError("Err")
        await alice.handle_start({"provider": "claude"})
        assert alice.state == AgentState.ERROR

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "_save_configuration")
    async def test_handle_approve_success(self, mock_save, alice: AliceAgent) -> None:
        alice._configuration = AliceConfiguration(
            provider=ProviderConfig(
                provider="c",
                provider_name="c",
                endpoint="e",
                credential_reference="c",
                tested_at="t",
                test_result="success",
            ),
            agents=AgentsConfig(
                updated_at="",
                agents={
                    "bob": AgentModelConfig(model="m", temperature=0, prompt_template="p", tools=[])
                },
            ),
        )
        await alice.handle_approve(data={"assignments": {"bob": "new-model"}})
        assert alice.state == AgentState.DONE
        assert alice._configuration.agents.agents["bob"].model == "new-model"

    @pytest.mark.asyncio
    async def test_handle_approve_no_config(self, alice: AliceAgent, mock_broadcast) -> None:
        alice._configuration = None
        await alice.handle_approve()
        assert alice.state == AgentState.START

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "_save_configuration")
    async def test_handle_approve_save_error(self, mock_save, alice: AliceAgent) -> None:
        mock_save.side_effect = OSError("DB Error")
        alice._configuration = MagicMock()
        await alice.handle_approve()
        assert alice.state == AgentState.ERROR


class TestMaskEndpoint:
    def test_mask_endpoint(self, alice: AliceAgent) -> None:
        assert alice._mask_endpoint("https://api.test.com/v1?key=secret") == "https://api.test.com"
        assert alice._mask_endpoint("") == "N/A"
        # Invalid URL fallback, urlparse just leaves netloc empty and scheme as the text
        assert alice._mask_endpoint("not-a-valid-url-at-all-and-very-long-indeed-wow") == "://"
