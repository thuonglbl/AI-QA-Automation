"""Tests for Alice Agent — AI Provider Selection & Configuration."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_qa.agents.alice import AliceAgent
from ai_qa.agents.base import AgentState
from ai_qa.ai_connection.providers import ConnectionResult
from ai_qa.db.models import User
from ai_qa.exceptions import PipelineError
from ai_qa.models import (
    AgentModelConfig,
    AgentsConfig,
    AliceConfiguration,
    ProviderConfig,
    StageResult,
)


def _ok_connection(
    provider: str = "claude", provider_name: str = "Claude (Anthropic)"
) -> ConnectionResult:
    """Successful ConnectionResult for patching _test_connection in process() tests."""
    return ConnectionResult(
        success=True,
        provider=provider,
        provider_name=provider_name,
        status="success",
        message=f"Successfully connected to {provider_name}.",
        error_category="none",
    )


def _failed_connection(
    message: str = "Authentication failed — the API key was rejected by Claude (Anthropic). Replace the key and try again.",
) -> ConnectionResult:
    """Failed ConnectionResult carrying an actionable, secret-free message."""
    return ConnectionResult(
        success=False,
        provider="claude",
        provider_name="Claude (Anthropic)",
        status="failed",
        message=message,
        error_category="auth",
    )


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = 1
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_thread():
    from ai_qa.threads.models import Thread

    thread = MagicMock(spec=Thread)
    thread.id = "thread-1"
    thread.provider_name = None
    thread.provider_base_url = None
    thread.agent_config = None
    return thread


@pytest.fixture
def alice(mock_db, mock_user, mock_thread):
    agent = AliceAgent()
    agent.project_context = MagicMock()
    agent.project_context.artifact_service.db = mock_db
    agent.project_context.user_id = 1
    agent.project_context.thread_id = "thread-1"

    def mock_get(model, id):
        if model.__name__ == "User" and id == 1:
            return mock_user
        if model.__name__ == "Thread" and id == "thread-1":
            return mock_thread
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
        assert len(options) == 5
        provider_ids = [p["id"] for p in options]
        assert "browser-use-cloud" in provider_ids
        assert "claude" in provider_ids
        assert "openai" in provider_ids
        assert "gemini" in provider_ids
        assert "on-premises" in provider_ids
        assert "gemini-chatgpt" not in provider_ids

    def test_provider_quality_ranks(self, alice: AliceAgent) -> None:
        options = alice.get_provider_options()
        by_id = {p["id"]: p for p in options}
        assert by_id["browser-use-cloud"]["quality_rank"] == 1
        assert by_id["claude"]["quality_rank"] == 2
        assert by_id["gemini"]["quality_rank"] == 3
        assert by_id["openai"]["quality_rank"] == 4
        assert by_id["on-premises"]["quality_rank"] == 5

    def test_provider_security_levels(self, alice: AliceAgent) -> None:
        options = alice.get_provider_options()
        by_id = {p["id"]: p for p in options}
        assert by_id["browser-use-cloud"]["security_level"] == "cloud"
        assert by_id["claude"]["security_level"] == "enterprise"
        assert by_id["openai"]["security_level"] == "good"
        assert by_id["gemini"]["security_level"] == "good"
        assert by_id["on-premises"]["security_level"] == "highest"

    def test_credential_fields(self, alice: AliceAgent) -> None:
        options = alice.get_provider_options()
        by_id = {p["id"]: p for p in options}
        for provider_id in ["browser-use-cloud", "claude", "openai", "gemini", "on-premises"]:
            fields = by_id[provider_id]["credential_fields"]
            assert len(fields) >= 1
            assert fields[0]["name"] == "api_key"


class TestOnPremDefaults:
    def test_get_on_prem_defaults_empty(self, alice: AliceAgent) -> None:
        with patch("ai_qa.secrets.service.get_user_secret", return_value=None):
            defaults = alice.get_on_prem_defaults()
        assert defaults["server_url"] == ""
        assert defaults["api_key_configured"] is False

    def test_get_on_prem_defaults_from_user(
        self, alice: AliceAgent, mock_user, mock_thread
    ) -> None:
        mock_thread.provider_base_url = "http://test"
        with patch("ai_qa.secrets.service.get_user_secret", return_value="key123"):
            defaults = alice.get_on_prem_defaults()
        assert defaults["server_url"] == "http://test"
        assert defaults["api_key_configured"] is True

    def test_get_on_prem_defaults_no_api_key_in_return(self, alice: AliceAgent) -> None:
        """Task 10: on_prem_defaults must NEVER include a plaintext api_key."""
        with patch("ai_qa.secrets.service.get_user_secret", return_value="secret-on-prem-key"):
            defaults = alice.get_on_prem_defaults()
        assert "api_key" not in defaults


class TestProcessWorkflow:
    @pytest.mark.asyncio
    @patch.object(AliceAgent, "_test_connection", return_value=_ok_connection())
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

        with patch("ai_qa.secrets.service.set_user_secret") as mock_set:
            result = await alice.process(input_data, feedback=None)

        assert result.success is True
        assert result.data is not None
        assert result.data["configuration"] == {"dump": "data"}
        mock_set.assert_called_once_with(mock_db, 1, "claude", "test-api-key-12345")
        # process() commits once for provider info and once for secret persistence
        assert mock_db.commit.call_count == 2

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "_test_connection", return_value=_ok_connection())
    @patch.object(AliceAgent, "_generate_configuration")
    async def test_process_valid_credentials_other_providers(
        self, mock_generate, mock_test, alice: AliceAgent, mock_user, mock_db
    ) -> None:
        mock_config = MagicMock()
        mock_config.model_dump.return_value = {"dump": "data"}
        mock_config.provider.endpoint = "http://test"
        mock_generate.return_value = mock_config

        for provider, secret_type in [
            ("openai", "openai"),
            ("gemini", "gemini"),
            ("browser-use-cloud", "browser_use"),
            ("on-premises", "on_premises"),
        ]:
            input_data = {
                "provider": provider,
                "credentials": {"api_key": "test-api-key-12345"},
            }
            with patch("ai_qa.secrets.service.set_user_secret") as mock_set:
                await alice.process(input_data, feedback=None)
                mock_set.assert_called_once_with(mock_db, 1, secret_type, "test-api-key-12345")

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "_test_connection", return_value=_ok_connection())
    @patch.object(AliceAgent, "_generate_configuration")
    async def test_process_does_not_leak_api_key_into_messages(
        self, mock_generate, mock_test, alice: AliceAgent, mock_user, mock_db
    ) -> None:
        """AC1.4 (message/WebSocket vector): the plaintext api_key must never
        appear in any broadcast message payload or the returned StageResult."""
        sentinel = "SENTINEL-SECRET-KEY-9173"
        mock_config = MagicMock()
        mock_config.model_dump.return_value = {"provider": {"credential_reference": "ref"}}
        mock_config.provider.endpoint = "http://test"
        mock_generate.return_value = mock_config

        input_data = {"provider": "claude", "credentials": {"api_key": sentinel}}

        with (
            patch("ai_qa.api.websocket.broadcast_message", new_callable=AsyncMock) as mock_bcast,
            patch("ai_qa.secrets.service.set_user_secret"),
        ):
            result = await alice.process(input_data, feedback=None)

        # Every broadcast message (the WebSocket payload history) must be key-free.
        for call in mock_bcast.call_args_list:
            message = call[0][0]
            assert sentinel not in (message.content or "")
            assert sentinel not in json.dumps(message.metadata or {}, default=str)

        # The returned result payload must also be key-free.
        assert sentinel not in json.dumps(result.data or {}, default=str)

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
    @patch.object(AliceAgent, "_test_connection", return_value=_failed_connection())
    async def test_process_connection_failed(self, mock_test, alice: AliceAgent) -> None:
        input_data = {"provider": "claude", "credentials": {"api_key": "short"}}
        # process() surfaces the adapter's actionable, secret-free message (AC2).
        with pytest.raises(PipelineError, match="Authentication failed"):
            await alice.process(input_data, feedback=None)

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "_test_connection", side_effect=Exception("API Error"))
    async def test_process_connection_exception(self, mock_test, alice: AliceAgent) -> None:
        input_data = {"provider": "claude", "credentials": {"api_key": "validkey123"}}
        # Unexpected adapter errors degrade to a curated message, never the raw exception.
        with pytest.raises(PipelineError, match="Could not validate the connection") as exc_info:
            await alice.process(input_data, feedback=None)
        assert "API Error" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_with_feedback(self, alice: AliceAgent) -> None:
        result = await alice.process(input_data={}, feedback="Change provider")
        assert result.success is True
        assert result.data is not None
        assert result.data["action"] == "restart_selection"


class TestConnectionAndFetch:
    @pytest.mark.asyncio
    async def test_test_connection_invalid_url(self, alice: AliceAgent) -> None:
        # On-prem with a non-http endpoint short-circuits to a config failure via the adapter.
        provider_info = {"id": "on-premises", "name": "On Prem", "endpoint": "not-http"}
        result = await alice._test_connection(provider_info, {"api_key": "long-enough-key"})
        assert result.success is False
        assert result.error_category == "config"

    @pytest.mark.asyncio
    async def test_test_connection_short_key(self, alice: AliceAgent) -> None:
        # Format floor in the adapter rejects sub-8-char keys without a network call.
        provider_info = {"id": "claude", "name": "Claude", "endpoint": "https://api.anthropic.com"}
        result = await alice._test_connection(provider_info, {"api_key": "short"})
        assert result.success is False
        assert result.error_category == "auth"

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_test_connection_auth_failure(self, mock_get, alice: AliceAgent) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response
        provider_info = {"id": "claude", "name": "Claude", "endpoint": "https://api.anthropic.com"}
        result = await alice._test_connection(provider_info, {"api_key": "validkey123"})
        assert result.success is False
        assert result.error_category == "auth"

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_test_connection_success(self, mock_get, alice: AliceAgent) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "gpt-4"}]}
        mock_get.return_value = mock_response
        provider_info = {"id": "claude", "name": "Claude", "endpoint": "https://api.anthropic.com"}
        result = await alice._test_connection(provider_info, {"api_key": "validkey123"})
        assert result.success is True
        assert result.error_category == "none"


class TestBootstrapAndLLM:
    def test_bootstrap_alice_model(self, alice: AliceAgent) -> None:
        available = [{"id": "gpt-4o", "name": "GPT-4o"}, {"id": "random", "name": "Random"}]
        model, rationale = alice._bootstrap_alice_model(available)
        assert model == "gpt-4o"
        assert rationale != ""

        available = [{"id": "random", "name": "Random"}]
        model, rationale = alice._bootstrap_alice_model(available)
        assert model == "random"

        assert alice._bootstrap_alice_model([]) == ("", "")

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
                "openai", "http://valid.url", "key", "gpt-4o", available
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
                "openai", "http://valid.url", "key", "gpt-4o", available
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
                "openai", "http://valid.url", "key", "gpt-4o", available
            )
            assert assignments["bob"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_assign_models_via_llm_fallback(self, alice: AliceAgent) -> None:
        with patch("ai_qa.ai_connection.client.LLMClient", autospec=True) as mock_client_class:
            mock_instance = mock_client_class.return_value
            mock_instance.invoke.side_effect = Exception("API error")
            available = [{"id": "gpt-4o", "name": "GPT-4o"}]
            assignments, reasoning = await alice._assign_models_via_llm(
                "openai", "http://valid.url", "key", "gpt-4o", available
            )
            assert assignments["bob"] == "gpt-4o"
            assert assignments["jack"] == "gpt-4o"
            # The raw exception text must NOT leak into the user-facing rationale.
            assert "API error" not in reasoning[0]["rationale"]
            assert "Exception" not in reasoning[0]["rationale"]

    @pytest.mark.asyncio
    async def test_assign_models_via_llm_no_json(self, alice: AliceAgent) -> None:
        mock_response = MagicMock()
        mock_response.content = "Hello I am an AI, I failed to generate JSON."
        with patch("ai_qa.ai_connection.client.LLMClient", autospec=True) as mock_client_class:
            mock_instance = mock_client_class.return_value
            mock_instance.invoke.return_value = mock_response
            available = [{"id": "gpt-4o", "name": "GPT-4o"}]
            assignments, reasoning = await alice._assign_models_via_llm(
                "openai", "http://valid.url", "key", "gpt-4o", available
            )
            assert assignments["bob"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_assign_models_via_llm_rate_limit_surfaces_to_user(
        self, alice: AliceAgent
    ) -> None:
        """A provider rate-limit / quota / billing error is surfaced verbatim
        (PipelineError), not swallowed by the heuristic fallback."""
        from ai_qa.exceptions import LLMRateLimitError

        provider_msg = (
            "LLM rate limit error: Error code: 400 - "
            "Your credit balance is too low to access the Anthropic API."
        )
        with patch("ai_qa.ai_connection.client.LLMClient", autospec=True) as mock_client_class:
            mock_instance = mock_client_class.return_value
            mock_instance.invoke.side_effect = LLMRateLimitError(provider_msg)
            available = [{"id": "claude-sonnet-4-5", "name": "Claude Sonnet"}]
            with pytest.raises(PipelineError, match="credit balance is too low"):
                await alice._assign_models_via_llm(
                    "claude", "https://api.anthropic.com", "key", "claude-sonnet-4-5", available
                )


class TestConfigurationAndPersistence:
    @pytest.mark.asyncio
    @patch("ai_qa.agents.alice.get_provider_adapter")
    @patch.object(AliceAgent, "_assign_models_via_llm")
    async def test_generate_configuration(
        self, mock_assign, mock_get_adapter, alice: AliceAgent
    ) -> None:
        from ai_qa.ai_connection.providers import DiscoveredModel

        mock_adapter = MagicMock()
        mock_adapter.list_models = AsyncMock(
            return_value=[DiscoveredModel(id="gpt-4o", display_name="GPT-4o", provider="openai")]
        )
        mock_get_adapter.return_value = mock_adapter
        mock_assign.return_value = (
            {"bob": "gpt-4o", "mary": "gpt-4o", "sarah": "gpt-4o", "jack": "gpt-4o"},
            [],
        )

        provider_info = {
            "id": "openai",
            "name": "OpenAI / ChatGPT",
            "endpoint": "http://endpoint",
            "env_key": "OPENAI_API_KEY",
        }
        config = await alice._generate_configuration(provider_info, {"api_key": "key12345"})

        assert config.provider.provider == "openai"
        assert config.agents.agents["bob"].model == "gpt-4o"
        mock_adapter.list_models.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("ai_qa.agents.alice.get_provider_adapter")
    async def test_generate_configuration_no_models(
        self, mock_get_adapter, alice: AliceAgent
    ) -> None:
        mock_adapter = MagicMock()
        mock_adapter.list_models = AsyncMock(return_value=[])
        mock_get_adapter.return_value = mock_adapter
        provider_info = {
            "id": "openai",
            "name": "OpenAI / ChatGPT",
            "endpoint": "",
            "env_key": "OPENAI_API_KEY",
        }
        with pytest.raises(PipelineError, match="Pipeline silently aborted"):
            await alice._generate_configuration(provider_info, {"api_key": "key12345"})

    @pytest.mark.asyncio
    @patch("ai_qa.agents.alice.get_provider_adapter")
    async def test_generate_configuration_no_models_message_is_secret_free(
        self, mock_get_adapter, alice: AliceAgent
    ) -> None:
        """AC2: the no-models failure message must carry no api_key / traceback."""
        sentinel = "sk-secret-LEAK-CANARY-123"
        mock_adapter = MagicMock()
        mock_adapter.list_models = AsyncMock(return_value=[])
        mock_get_adapter.return_value = mock_adapter
        provider_info = {
            "id": "openai",
            "name": "OpenAI / ChatGPT",
            "endpoint": "https://api.openai.com",
            "env_key": "OPENAI_API_KEY",
        }
        with pytest.raises(PipelineError) as exc_info:
            await alice._generate_configuration(provider_info, {"api_key": sentinel})
        message = str(exc_info.value)
        assert sentinel not in message
        assert "Traceback" not in message

    @pytest.mark.asyncio
    @patch("ai_qa.agents.alice.get_provider_adapter")
    async def test_generate_configuration_never_assigns_undiscovered_static_hint(
        self, mock_get_adapter, alice: AliceAgent
    ) -> None:
        """AC3 (verify-before-assign, end-to-end): a static ranking-hint name that
        the provider did NOT advertise must never be assigned.

        Discovery deliberately EXCLUDES ``claude-opus-4-6`` (a real
        ``_STATIC_MODEL_HINTS["claude"]`` entry). Even when the LLM tries to
        assign that undiscovered hint to Bob, the real verify-before-assign guard
        in ``_assign_models_via_llm`` (``valid_ids`` membership) falls back to a
        discovered id — proving static hints never bypass discovery through the
        full ``_generate_configuration`` path.
        """
        from ai_qa.ai_connection.providers import DiscoveredModel

        discovered_ids = {"claude-sonnet-4-6", "claude-3-5-haiku-latest"}
        mock_adapter = MagicMock()
        mock_adapter.list_models = AsyncMock(
            return_value=[
                DiscoveredModel(id="claude-sonnet-4-6", display_name="Sonnet", provider="claude"),
                DiscoveredModel(
                    id="claude-3-5-haiku-latest", display_name="Haiku", provider="claude"
                ),
            ]
        )
        mock_get_adapter.return_value = mock_adapter

        # The LLM (incorrectly) tries to assign the undiscovered static hint to Bob.
        llm_response = MagicMock()
        llm_response.content = (
            '{"assignments": {"bob": "claude-opus-4-6", "mary": "claude-sonnet-4-6", '
            '"sarah": "claude-sonnet-4-6", "jack": "claude-3-5-haiku-latest"}, '
            '"reasoning": [{"agent": "bob", "rationale": "x"}]}'
        )
        provider_info = {
            "id": "claude",
            "name": "Claude (Anthropic)",
            "endpoint": "https://api.anthropic.com",
            "env_key": "ANTHROPIC_API_KEY",
        }
        with patch("ai_qa.ai_connection.client.LLMClient", autospec=True) as mock_client_class:
            mock_client_class.return_value.invoke.return_value = llm_response
            config = await alice._generate_configuration(provider_info, {"api_key": "key12345"})

        assigned = {agent.model for agent in config.agents.agents.values()}
        # The undiscovered static hint is never assigned to ANY agent...
        assert "claude-opus-4-6" not in assigned
        # ...and every assigned model (alice + bob/mary/sarah/jack) is a discovered id.
        assert assigned <= discovered_ids
        # Bob specifically fell back to a discovered id rather than the bad hint.
        assert config.agents.agents["bob"].model in discovered_ids

    @pytest.mark.asyncio
    @patch("ai_qa.agents.alice.get_provider_adapter")
    async def test_generate_configuration_bootstrap_prefers_ranked_discovered_id(
        self, mock_get_adapter, alice: AliceAgent
    ) -> None:
        """AC3 (ranking hint, positive): among discovered ids, the static priority
        keywords only *prefer* one discovered id over another — Alice's bootstrap
        model is the discovered id matching a priority keyword (``sonnet``), never
        an undiscovered name.
        """
        from ai_qa.ai_connection.providers import DiscoveredModel

        mock_adapter = MagicMock()
        mock_adapter.list_models = AsyncMock(
            return_value=[
                DiscoveredModel(id="random-small", display_name="Random", provider="claude"),
                DiscoveredModel(id="my-sonnet-x", display_name="Sonnet X", provider="claude"),
            ]
        )
        mock_get_adapter.return_value = mock_adapter

        # LLM fails to produce JSON -> every agent falls back to the bootstrap model.
        llm_response = MagicMock()
        llm_response.content = "no json here"
        provider_info = {
            "id": "claude",
            "name": "Claude (Anthropic)",
            "endpoint": "https://api.anthropic.com",
            "env_key": "ANTHROPIC_API_KEY",
        }
        with patch("ai_qa.ai_connection.client.LLMClient", autospec=True) as mock_client_class:
            mock_client_class.return_value.invoke.return_value = llm_response
            config = await alice._generate_configuration(provider_info, {"api_key": "key12345"})

        # 'sonnet' priority keyword wins over the non-matching discovered id.
        assert config.agents.agents["alice"].model == "my-sonnet-x"

    def test_save_configuration(self, alice: AliceAgent, mock_thread, mock_db) -> None:
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
        assert mock_thread.provider_name == "claude"
        assert len(mock_thread.agent_configs) == 0
        mock_db.commit.assert_called_once()

    def test_save_configuration_no_thread(self, alice: AliceAgent, mock_db) -> None:
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
        with pytest.raises(OSError, match="Thread not found"):
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
        with pytest.raises(OSError, match="No thread_id available"):
            alice._save_configuration(config)


class TestExistingConfiguration:
    @pytest.mark.asyncio
    async def test_check_existing_valid(self, alice: AliceAgent, mock_thread) -> None:
        mock_thread.provider_name = "claude"
        mock_thread.provider_base_url = ""
        mock_thread.agent_configs = []

        existing = await alice.check_existing_configuration()
        assert existing is not None
        assert existing.provider.provider == "claude"

    @pytest.mark.asyncio
    async def test_check_existing_expired(self, alice: AliceAgent, mock_thread) -> None:
        # Since we removed tested_at expiration logic from check_existing_configuration
        # we can just test that if provider_name is missing, it returns None
        mock_thread.provider_name = None
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

        with patch("ai_qa.userconfig.service.get_provider_config", return_value=None):
            await alice.handle_start({"force_reconfigure": True})
        # Should bypass existing and show greeting
        assert alice.state == AgentState.START

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "check_existing_configuration", return_value=None)
    async def test_handle_start_no_provider(
        self, mock_check, alice: AliceAgent, mock_broadcast
    ) -> None:
        with patch("ai_qa.userconfig.service.get_provider_config", return_value=None):
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
        with patch("ai_qa.userconfig.service.save_provider_config"):
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
        with patch("ai_qa.userconfig.service.save_provider_config"):
            await alice.handle_approve()
        assert alice.state == AgentState.ERROR


class TestSavedConfigRoundTrip:
    """Story 9.7 — Task 3/4/8: save→load round-trip, explicit prompt, validity gating."""

    def test_save_configuration_writes_structured_format(
        self, alice: AliceAgent, mock_thread, mock_db
    ) -> None:
        """_save_configuration writes structured {model, temperature, rationale} per agent."""
        alice._model_reasoning = [
            {"agent": "bob", "model": "gpt-4o", "rationale": "best for vision"}
        ]
        config = AliceConfiguration(
            provider=ProviderConfig(
                provider="openai",
                provider_name="OpenAI",
                endpoint="https://api.openai.com",
                credential_reference="",
                tested_at="",
                test_result="success",
            ),
            agents=AgentsConfig(
                updated_at="",
                agents={
                    "bob": AgentModelConfig(
                        model="gpt-4o", temperature=0.5, prompt_template="p", tools=[]
                    ),
                },
            ),
        )
        alice._save_configuration(config)
        saved = mock_thread.agent_configs
        assert isinstance(saved["bob"], dict)
        assert saved["bob"]["model"] == "gpt-4o"
        assert saved["bob"]["temperature"] == 0.5
        assert saved["bob"]["rationale"] == "best for vision"

    @pytest.mark.asyncio
    async def test_check_existing_reads_structured_shape(
        self, alice: AliceAgent, mock_thread
    ) -> None:
        """check_existing_configuration reads structured {model, temperature, rationale}."""
        mock_thread.provider_name = "openai"
        mock_thread.provider_base_url = "https://api.openai.com"
        mock_thread.agent_configs = {
            "bob": {"model": "gpt-4o", "temperature": 0.7, "rationale": "vision capable"}
        }
        config = await alice.check_existing_configuration()
        assert config is not None
        assert config.agents.agents["bob"].model == "gpt-4o"
        assert config.agents.agents["bob"].temperature == 0.7

    @pytest.mark.asyncio
    async def test_check_existing_reads_legacy_flat_string(
        self, alice: AliceAgent, mock_thread
    ) -> None:
        """check_existing_configuration tolerates legacy flat-string thread snapshot."""
        mock_thread.provider_name = "claude"
        mock_thread.provider_base_url = ""
        mock_thread.agent_configs = {"bob": "claude-3-5-sonnet-20241022"}
        config = await alice.check_existing_configuration()
        assert config is not None
        assert config.agents.agents["bob"].model == "claude-3-5-sonnet-20241022"

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "check_existing_configuration", return_value=None)
    async def test_handle_start_emits_saved_config_prompt_when_valid(
        self, mock_check, alice: AliceAgent, mock_broadcast
    ) -> None:
        """Task 4: valid saved config → explicit saved_config_prompt, NOT auto-apply."""
        saved = {
            "provider": {
                "provider": "claude",
                "provider_name": "Claude",
                "endpoint": "https://api.anthropic.com",
            },
            "agents": {
                "agents": {"bob": {"model": "gpt-4o", "temperature": 0.0, "rationale": "r"}}
            },
        }
        mock_project = MagicMock()
        mock_project.enabled_providers = []  # empty = all allowed
        alice.project_context.artifact_service.db.get.return_value = mock_project

        with (
            patch("ai_qa.userconfig.service.get_provider_config", return_value=saved),
            patch("ai_qa.secrets.service.get_user_secret", return_value="key-abc"),
        ):
            await alice.handle_start({})

        # Must emit a saved_config_prompt message
        prompt_found = False
        for call in mock_broadcast.call_args_list:
            msg = call[0][0]
            if msg.metadata and msg.metadata.get("type") == "saved_config_prompt":
                prompt_found = True
                # Must NOT contain the api_key
                assert "key-abc" not in json.dumps(msg.metadata)
        assert prompt_found, "saved_config_prompt message not broadcast"
        # Must NOT auto-transition to DONE
        assert alice.state != AgentState.DONE

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "check_existing_configuration", return_value=None)
    @patch.object(AliceAgent, "_save_configuration")
    async def test_handle_start_use_saved_config_transitions_to_done(
        self, mock_save, mock_check, alice: AliceAgent, mock_broadcast
    ) -> None:
        """Task 4: use_saved_config=true writes snapshot and transitions to DONE."""
        saved = {
            "provider": {
                "provider": "claude",
                "provider_name": "Claude",
                "endpoint": "https://api.anthropic.com",
            },
            "agents": {
                "agents": {"alice": {"model": "claude-sonnet", "temperature": 0.0, "rationale": ""}}
            },
        }
        with patch("ai_qa.userconfig.service.get_provider_config", return_value=saved):
            await alice.handle_start({"use_saved_config": True})
        assert alice.state == AgentState.DONE
        mock_save.assert_called_once()

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "check_existing_configuration", return_value=None)
    async def test_handle_start_invalid_saved_config_falls_through(
        self, mock_check, alice: AliceAgent, mock_thread, mock_broadcast
    ) -> None:
        """Task 4: saved config whose provider is not in enabled_providers → fall through."""
        saved = {
            "provider": {"provider": "claude", "provider_name": "Claude", "endpoint": ""},
            "agents": {},
        }
        mock_project = MagicMock()
        mock_project.enabled_providers = ["openai"]  # claude NOT allowed

        def mock_get_with_project(model: type, id: object) -> object:
            from ai_qa.db.models import Project

            if model is Project:
                return mock_project
            if hasattr(model, "__name__") and model.__name__ == "Thread":
                return mock_thread
            return None

        alice.project_context.artifact_service.db.get.side_effect = mock_get_with_project

        with (
            patch("ai_qa.userconfig.service.get_provider_config", return_value=saved),
            patch("ai_qa.secrets.service.get_user_secret", return_value="key-abc"),
        ):
            await alice.handle_start({})

        # Should NOT emit saved_config_prompt when provider is disabled
        for call in mock_broadcast.call_args_list:
            msg = call[0][0]
            if msg.metadata:
                assert msg.metadata.get("type") != "saved_config_prompt"

    @pytest.mark.asyncio
    @patch.object(AliceAgent, "check_existing_configuration", return_value=None)
    async def test_handle_start_force_reconfigure_bypasses_saved_config(
        self, mock_check, alice: AliceAgent, mock_broadcast
    ) -> None:
        """Task 4: force_reconfigure=True skips saved config and runs provider-selection flow."""
        saved = {
            "provider": {
                "provider": "claude",
                "provider_name": "Claude",
                "endpoint": "https://api.anthropic.com",
            },
            "agents": {
                "agents": {"alice": {"model": "claude-sonnet", "temperature": 0.0, "rationale": ""}}
            },
        }
        mock_project = MagicMock()
        mock_project.enabled_providers = []
        alice.project_context.artifact_service.db.get.return_value = mock_project

        with (
            patch("ai_qa.userconfig.service.get_provider_config", return_value=saved),
            patch("ai_qa.secrets.service.get_user_secret", return_value="key-abc"),
        ):
            await alice.handle_start({"force_reconfigure": True})

        # Must NOT emit saved_config_prompt
        for call in mock_broadcast.call_args_list:
            msg = call[0][0]
            if msg.metadata:
                assert msg.metadata.get("type") != "saved_config_prompt", (
                    "force_reconfigure=True must not show saved_config_prompt"
                )

        # Must emit provider_options (normal provider-selection flow)
        provider_options_found = any(
            call[0][0].metadata and call[0][0].metadata.get("type") == "provider_options"
            for call in mock_broadcast.call_args_list
        )
        assert provider_options_found, "provider_options not shown after force_reconfigure=True"


class TestMaskEndpoint:
    def test_mask_endpoint(self, alice: AliceAgent) -> None:
        assert alice._mask_endpoint("https://api.test.com/v1?key=secret") == "https://api.test.com"
        assert alice._mask_endpoint("") == "N/A"
        # Invalid URL fallback, urlparse just leaves netloc empty and scheme as the text
        assert alice._mask_endpoint("not-a-valid-url-at-all-and-very-long-indeed-wow") == "://"


class TestHandleReject:
    """Story 9.5 — reject configuration review returns to provider selection."""

    @pytest.mark.asyncio
    async def test_handle_reject_resets_configuration(
        self, alice: AliceAgent, mock_broadcast
    ) -> None:
        """Reject must clear the generated configuration without persisting."""
        alice._configuration = MagicMock()
        alice._model_reasoning = [{"agent": "bob", "rationale": "test"}]

        await alice.handle_reject("Change provider")

        assert alice._configuration is None
        assert alice._model_reasoning == []

    @pytest.mark.asyncio
    async def test_handle_reject_returns_to_start_state(
        self, alice: AliceAgent, mock_broadcast
    ) -> None:
        """Reject must transition the agent back to START state."""
        alice._configuration = MagicMock()
        await alice.handle_reject("Wrong models")

        assert alice.state == AgentState.START

    @pytest.mark.asyncio
    async def test_handle_reject_sends_acknowledgment_message(
        self, alice: AliceAgent, mock_broadcast
    ) -> None:
        """Reject must broadcast a conversational acknowledgment (no secrets)."""
        sentinel = "SECRET-KEY-REJECT-456"
        alice._configuration = MagicMock()
        alice._provider_credentials = {"api_key": sentinel}

        await alice.handle_reject("Change provider")

        # Find the acknowledgment message (first broadcast call)
        calls = mock_broadcast.call_args_list
        ack_message = calls[0][0][0]
        assert "adjust" in ack_message.content.lower()
        assert sentinel not in ack_message.content

    @pytest.mark.asyncio
    async def test_handle_reject_sends_provider_options(
        self, alice: AliceAgent, mock_broadcast
    ) -> None:
        """Reject must re-show provider options for reconfiguration."""
        alice._configuration = MagicMock()
        await alice.handle_reject("Change provider")

        calls = mock_broadcast.call_args_list
        # Find the broadcast with provider_options metadata
        options_found = False
        for call in calls:
            msg = call[0][0]
            if msg.metadata and msg.metadata.get("type") == "provider_options":
                options_found = True
                break
        assert options_found, "provider_options message not found in broadcasts"

    @pytest.mark.asyncio
    async def test_handle_reject_does_not_persist_configuration(
        self, alice: AliceAgent, mock_db, mock_thread, mock_broadcast
    ) -> None:
        """Reject must NOT write to user_provider_config, AgentModelConfig, or any config tables."""
        alice._configuration = MagicMock()
        # Track all db.commit calls
        initial_commit_count = mock_db.commit.call_count

        await alice.handle_reject("Change provider")

        # No additional commits should have been made for configuration persistence
        assert mock_db.commit.call_count == initial_commit_count


class TestModelAssignmentsDisplay:
    """Story 9.5 — rationale is threaded into display output."""

    def test_display_includes_rationale(self, alice: AliceAgent, mock_thread, mock_db) -> None:
        """_get_model_assignments_display should include rationale from _model_reasoning."""
        alice._configuration = AliceConfiguration(
            provider=ProviderConfig(
                provider="claude",
                provider_name="Claude",
                endpoint="",
                credential_reference="",
                tested_at="",
                test_result="success",
            ),
            agents=AgentsConfig(
                updated_at="",
                agents={
                    "bob": AgentModelConfig(
                        model="claude-sonnet", temperature=0, prompt_template="p", tools=[]
                    ),
                },
            ),
        )
        alice._model_reasoning = [
            {"agent": "bob", "model": "claude-sonnet", "rationale": "Best for reasoning."}
        ]

        display = alice._get_model_assignments_display()
        assert len(display) == 1
        assert display[0]["rationale"] == "Best for reasoning."

    def test_display_empty_rationale_when_no_reasoning(
        self, alice: AliceAgent, mock_thread, mock_db
    ) -> None:
        """When _model_reasoning is empty, rationale should be empty string."""
        alice._configuration = AliceConfiguration(
            provider=ProviderConfig(
                provider="claude",
                provider_name="Claude",
                endpoint="",
                credential_reference="",
                tested_at="",
                test_result="success",
            ),
            agents=AgentsConfig(
                updated_at="",
                agents={
                    "bob": AgentModelConfig(
                        model="claude-sonnet", temperature=0, prompt_template="p", tools=[]
                    ),
                },
            ),
        )
        alice._model_reasoning = []

        display = alice._get_model_assignments_display()
        assert display[0]["rationale"] == ""

    def test_format_review_content_includes_rationale(
        self, alice: AliceAgent, mock_thread, mock_db
    ) -> None:
        """_format_review_content should include rationale column in the table."""
        alice._selected_provider = "claude"
        result = StageResult(
            success=True,
            data={
                "model_assignments": [
                    {
                        "agent": "Bob",
                        "model": "claude-sonnet",
                        "purpose": "Requirements",
                        "rationale": "Chosen for reasoning.",
                    }
                ],
                "provider_endpoint": "https://api.anthropic.com",
            },
        )
        content = alice._format_review_content(result)
        assert "Rationale" in content
        assert "Chosen for reasoning." in content
