"""Tests for Alice Agent — AI Provider Selection & Configuration."""

import json
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_qa.agents.alice import _AGENT_RATIONALE, AliceAgent
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
        assert len(options) == 6
        provider_ids = [p["id"] for p in options]
        assert "browser-use-cloud" in provider_ids
        assert "claude" in provider_ids
        assert "claude-sso" in provider_ids
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
        # Personal Claude (API key) is "good" secure like Gemini/ChatGPT; only the
        # enterprise SSO option keeps "enterprise" (Strong secure).
        assert by_id["claude"]["security_level"] == "good"
        assert by_id["claude-sso"]["security_level"] == "enterprise"
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


class TestConfiguredProviders:
    def test_empty_without_context(self) -> None:
        """No DB/user context → no configured providers (and no crash)."""
        agent = AliceAgent()
        assert agent.get_configured_providers() == []

    def test_lists_only_providers_with_a_stored_secret(self, alice: AliceAgent) -> None:
        def fake_get(_db: object, _uid: object, secret_type: str) -> str | None:
            return "stored-value" if secret_type in {"claude", "on_premises"} else None

        with patch("ai_qa.secrets.service.get_user_secret", side_effect=fake_get):
            configured = alice.get_configured_providers()
        # secret_type "claude" → provider id "claude"; "on_premises" → "on-premises".
        assert set(configured) == {"claude", "on-premises"}


class TestStoredKeyReuse:
    @pytest.mark.asyncio
    @patch.object(AliceAgent, "_test_connection", return_value=_ok_connection())
    @patch.object(AliceAgent, "_generate_configuration")
    async def test_blank_key_reuses_stored_secret_without_rewrite(
        self, mock_generate, mock_test, alice: AliceAgent, mock_user, mock_db
    ) -> None:
        """A blank api_key resolves the stored secret for ANY provider (skip-prompt
        UX) and does NOT re-write it (reuse path)."""
        mock_config = MagicMock()
        mock_config.model_dump.return_value = {"dump": "data"}
        mock_config.provider.endpoint = "http://test"
        mock_generate.return_value = mock_config

        input_data = {"provider": "gemini", "credentials": {}}
        with (
            patch("ai_qa.secrets.service.get_user_secret", return_value="stored-gemini-key"),
            patch("ai_qa.secrets.service.set_user_secret") as mock_set,
        ):
            result = await alice.process(input_data, feedback=None)

        assert result.success is True
        # Reused key must not be persisted again.
        mock_set.assert_not_called()
        # The resolved stored key reached the connection test.
        resolved_credentials = mock_test.call_args.args[1]
        assert resolved_credentials.get("api_key") == "stored-gemini-key"


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


class TestBootstrapAndAssignment:
    def test_bootstrap_alice_model(self, alice: AliceAgent) -> None:
        # GLM-5.1 outranks DeepSeek-V3.2 for reasoning (the core selection fix).
        available = [
            {"id": "inference-deepseek-v32", "name": "DeepSeek V3.2"},
            {"id": "inference-glm-51-754b", "name": "GLM 5.1"},
        ]
        model, rationale = alice._bootstrap_alice_model(available)
        assert model == "inference-glm-51-754b"
        assert rationale != ""

        # No ranked match -> first discovered model, with a fallback rationale.
        available = [{"id": "random-model", "name": "Random"}]
        model, rationale = alice._bootstrap_alice_model(available)
        assert model == "random-model"

        assert alice._bootstrap_alice_model([]) == ("", "")

    def test_assign_models_picks_best_per_capability(self, alice: AliceAgent) -> None:
        available = [
            {"id": "inference-glm-51-754b", "name": "GLM 5.1"},
            {"id": "inference-qwen3-vl-235b", "name": "Qwen3 VL"},
            {"id": "inference-glm45-air-110b", "name": "GLM 4.5 Air"},
            {"id": "inference-deepseek-v32", "name": "DeepSeek V3.2"},
            {"id": "inference-mistral-v03-7b", "name": "Mistral"},
        ]
        mappings, reasoning = alice._assign_models("inference-glm-51-754b", available)
        assert mappings["sarah"] == "inference-glm-51-754b"  # coding flagship (script-gen)
        assert mappings["mary"] == "inference-glm-51-754b"  # instruction flagship
        assert mappings["bob"] == "inference-qwen3-vl-235b"  # best vision model
        # Sarah's SECOND model (browser explore) is the vision model, same as Bob — NOT the
        # coding flagship; a text-only model (deepseek/glm) must never win the vision role.
        assert mappings["sarah_explore"] == "inference-qwen3-vl-235b"
        assert mappings["jack"] == "inference-glm45-air-110b"  # fast tier
        assert {r["agent"] for r in reasoning} == {
            "bob",
            "mary",
            "sarah",
            "sarah_explore",
            "jack",
        }
        assert all(r["rationale"] for r in reasoning)

    def test_assign_models_bob_requires_vision_model(self, alice: AliceAgent) -> None:
        # GLM-5.1 is text-only: with NO vision model present, Bob falls back to
        # the alice_model rather than receive a text-only flagship.
        available = [{"id": "inference-glm-51-754b", "name": "GLM 5.1"}]
        mappings, _ = alice._assign_models("inference-glm-51-754b", available)
        assert mappings["bob"] == "inference-glm-51-754b"
        # When a vision model exists, Bob prefers it over the flagship.
        available.append({"id": "inference-qwen3-vl-235b", "name": "Qwen3 VL"})
        mappings, _ = alice._assign_models("inference-glm-51-754b", available)
        assert mappings["bob"] == "inference-qwen3-vl-235b"

    def test_assign_models_prefers_base_over_grc_variant(self, alice: AliceAgent) -> None:
        available = [
            {"id": "inference-qwen3-vl-235b-GRC", "name": "Qwen3 VL GRC"},
            {"id": "inference-qwen3-vl-235b", "name": "Qwen3 VL"},
        ]
        mappings, _ = alice._assign_models("inference-qwen3-vl-235b", available)
        assert mappings["bob"] == "inference-qwen3-vl-235b"

    def test_assign_models_falls_back_to_alice_model(self, alice: AliceAgent) -> None:
        # No ranked match for any capability -> every agent uses the (discovered)
        # alice_model; an undiscovered model is never introduced (Story 9.4 AC3).
        available = [{"id": "some-unknown-model", "name": "Unknown"}]
        mappings, reasoning = alice._assign_models("some-unknown-model", available)
        assert set(mappings.values()) == {"some-unknown-model"}
        assert all(r["model"] == "some-unknown-model" for r in reasoning)


class TestModelRankingHeuristic:
    """Tier-2 parsed heuristic that ranks UNLISTED / brand-new model ids."""

    @pytest.mark.parametrize(
        "model_id,family,version,total_b,tags",
        [
            ("inference-glm-51-754b", "glm", (5, 1), 754, set()),
            ("inference-qwen3-vl-235b", "qwen", (3,), 235, {"vl"}),
            ("inference-deepseek-v32", "deepseek", (3, 2), None, set()),
            ("inference-glm45-air-110b", "glm", (4, 5), 110, {"air"}),
            ("inference-mistral-v03-7b", "mistral", (0, 3), 7, set()),
            ("inference-glm-7-820b", "glm", (7,), 820, set()),  # hypothetical future id
        ],
    )
    def test_parse_model_id_golden_table(self, model_id, family, version, total_b, tags) -> None:
        from ai_qa.agents.alice import parse_model_id

        p = parse_model_id(model_id)
        assert p.family == family
        assert p.version == version
        assert p.total_b == total_b
        assert p.tags == frozenset(tags)

    def test_version_decimal_components_not_floats(self) -> None:
        from ai_qa.agents.alice import _version_from_token

        # 3.10 must sort ABOVE 3.5 as decimal components, not as a float (3.1 < 3.5).
        v310 = _version_from_token("3.10")
        v35 = _version_from_token("3.5")
        assert v310 == (3, 10)
        assert v35 == (3, 5)
        assert v310 is not None and v35 is not None
        assert v310 > v35  # ordering on the parsed tuples, not inline literals
        assert _version_from_token("v32") == (3, 2)
        assert _version_from_token("air") is None

    def test_parse_is_fail_soft(self) -> None:
        from ai_qa.agents.alice import parse_model_id

        p = parse_model_id("")
        assert p.family == "" and p.version == ()

    def test_new_version_in_known_family_wins_via_parsed_tier(self, alice: AliceAgent) -> None:
        # Neither id is in any curated list -> Tier 2 parses both. A glm model
        # (high family prior + version 7) beats a higher-versioned granite, with
        # ZERO code change to the curated lists.
        pool = [
            {"id": "inference-glm-7-820b", "name": "GLM 7"},
            {"id": "inference-granite-9-8b", "name": "Granite 9"},
        ]
        from ai_qa.agents.alice import _select_model_for

        pick = _select_model_for("sarah", pool)
        assert pick is not None
        assert pick["model"] == "inference-glm-7-820b"
        assert pick["source"] == "parsed"

    def test_curated_tier_is_version_aware(self) -> None:
        from ai_qa.agents.alice import _select_best_model

        # A single preference matching two siblings prefers the higher version.
        chosen = _select_best_model(["x-glm-51-y", "x-glm-52-y"], ["glm-5"])
        assert chosen == "x-glm-52-y"

    def test_bob_vision_gate_uses_advertised_flag_or_name(self, alice: AliceAgent) -> None:
        from ai_qa.agents.alice import _select_model_for

        # Advertised vision flag promotes an otherwise-unknown id for Bob.
        pick = _select_model_for(
            "bob",
            [{"id": "mystery-x", "supports_vision": True}, {"id": "plain-text-y"}],
        )
        assert pick is not None and pick["model"] == "mystery-x"

        # Name signal ("vl") works too, and a text-only flagship is NOT chosen for Bob.
        pick = _select_model_for(
            "bob",
            [{"id": "inference-glm-7-820b"}, {"id": "inference-newvendor-vl-99b"}],
        )
        assert pick is not None and "vl" in pick["model"]

    def test_has_vision_signal_detects_glm_v_variants_by_name(self) -> None:
        from ai_qa.agents.alice import _has_vision_signal

        # GLM vision variants append "v" to the version (in _VISION_RANK). Name-only
        # detection (no supports_vision flag, e.g. resolving from a stored id) must catch them.
        assert _has_vision_signal({"id": "inference-glm-5.1v-754b"})
        assert _has_vision_signal({"id": "glm-5v"})
        assert _has_vision_signal({"id": "glm-4.6v"})
        # Text-only GLM (no trailing-v version) is NOT a vision model.
        assert not _has_vision_signal({"id": "inference-glm-51-754b"})
        assert not _has_vision_signal({"id": "glm-5.1"})

    def test_has_vision_signal_rejects_text_only_flagships_even_when_flagged(self) -> None:
        from ai_qa.agents.alice import _has_vision_signal

        # The on-prem gateway false-flags these text-only models as vision; reject anyway.
        assert not _has_vision_signal({"id": "inference-deepseek-v32", "supports_vision": True})
        assert not _has_vision_signal({"id": "inference-gpt-oss-120b", "supports_vision": True})
        # A hosted vision model with the flag (no name signal) is still trusted.
        assert _has_vision_signal({"id": "claude-sonnet-4-6", "supports_vision": True})
        # A real vision name beats the denylist (a genuine multimodal deepseek-vl would count).
        assert _has_vision_signal({"id": "inference-deepseek-vl-7b"})

    def test_bob_never_selects_text_only_model_for_vision(self) -> None:
        from ai_qa.agents.alice import _select_model_for

        # deepseek has a HIGHER (false) vision score AND the gateway flag, but is text-only;
        # Bob must still pick the real vision model despite its lower score.
        pool = [
            {"id": "inference-deepseek-v32", "supports_vision": True},
            {"id": "inference-qwen3-vl-235b", "supports_vision": False},
        ]
        pick = _select_model_for(
            "bob",
            pool,
            {"inference-deepseek-v32": 28.7, "inference-qwen3-vl-235b": 17.9},
        )
        assert pick is not None and pick["model"] == "inference-qwen3-vl-235b"

    def test_admin_score_overrides_all_tiers(self, alice: AliceAgent) -> None:
        from ai_qa.agents.alice import _select_model_for

        # An admin score outranks even a curated flagship for that agent.
        pool = [
            {"id": "inference-glm-51-754b", "name": "GLM 5.1"},
            {"id": "inference-newcomer-9-700b", "name": "Newcomer"},
        ]
        pick = _select_model_for("sarah", pool, {"inference-newcomer-9-700b": 100.0})
        assert pick is not None
        assert pick["model"] == "inference-newcomer-9-700b"
        assert pick["source"] == "admin"

    def test_auto_promotes_to_newer_version_in_winning_family(self, alice: AliceAgent) -> None:
        from ai_qa.agents.alice import _select_model_for

        # glm-5.1 is the curated winner; a newer same-line glm-5.3 (in no list) is
        # auto-selected because it is a newer version of the winning family+variant.
        pool = [
            {"id": "inference-glm-51-754b", "name": "GLM 5.1"},
            {"id": "inference-glm-53-754b", "name": "GLM 5.3"},
        ]
        pick = _select_model_for("sarah", pool)
        assert pick is not None
        assert pick["model"] == "inference-glm-53-754b"

    def test_admin_scored_family_promotes_to_newer_version(self, alice: AliceAgent) -> None:
        from ai_qa.agents.alice import _select_model_for

        # The exact requested behavior: glm-5.1 has the top admin score; an
        # unbenchmarked newer glm-5.2 is auto-chosen as the newest of that family.
        pool = [
            {"id": "inference-glm-51-754b", "name": "GLM 5.1"},
            {"id": "inference-glm-52-754b", "name": "GLM 5.2"},
        ]
        pick = _select_model_for("sarah", pool, {"inference-glm-51-754b": 100})
        assert pick is not None
        assert pick["model"] == "inference-glm-52-754b"
        assert pick["source"] == "admin"

    def test_promotion_does_not_cross_variant(self, alice: AliceAgent) -> None:
        from ai_qa.agents.alice import _promote_to_newest_sibling

        # A newer but DIFFERENT variant (-air) is a separate product line and must
        # NOT replace the flagship winner...
        out = _promote_to_newest_sibling(
            "inference-glm-51-754b",
            ["inference-glm-51-754b", "inference-glm-6-air-110b"],
        )
        assert out == "inference-glm-51-754b"
        # ...but a newer SAME-variant sibling does.
        out2 = _promote_to_newest_sibling(
            "inference-glm-51-754b",
            ["inference-glm-51-754b", "inference-glm-53-754b"],
        )
        assert out2 == "inference-glm-53-754b"


class TestConfigurationAndPersistence:
    @pytest.mark.asyncio
    @patch("ai_qa.agents.alice.get_provider_adapter")
    @patch.object(AliceAgent, "_assign_models")
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
    async def test_generate_configuration_never_assigns_undiscovered_model(
        self, mock_get_adapter, alice: AliceAgent
    ) -> None:
        """AC3 (verify-before-assign, end-to-end): deterministic assignment only
        ever picks from the DISCOVERED pool — an undiscovered model can never be
        assigned to any agent. Here no discovered id matches any ranking keyword,
        so every agent falls back to the (discovered) bootstrap model.
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

        provider_info = {
            "id": "claude",
            "name": "Claude (Anthropic)",
            "endpoint": "https://api.anthropic.com",
            "env_key": "ANTHROPIC_API_KEY",
        }
        config = await alice._generate_configuration(provider_info, {"api_key": "key12345"})

        assigned = {agent.model for agent in config.agents.agents.values()}
        # Every assigned model (alice + bob/mary/sarah/jack) is a discovered id.
        assert assigned <= discovered_ids
        # Bob never receives an undiscovered id either.
        assert config.agents.agents["bob"].model in discovered_ids

    @pytest.mark.asyncio
    @patch("ai_qa.agents.alice.get_provider_adapter")
    async def test_generate_configuration_bootstrap_prefers_ranked_discovered_id(
        self, mock_get_adapter, alice: AliceAgent
    ) -> None:
        """The benchmark ranking only *prefers* one discovered id over another:
        Alice's bootstrap model is the discovered id matching the highest-ranked
        keyword (``glm-51`` -> GLM-5.1), never an undiscovered name.
        """
        from ai_qa.ai_connection.providers import DiscoveredModel

        mock_adapter = MagicMock()
        mock_adapter.list_models = AsyncMock(
            return_value=[
                DiscoveredModel(id="random-small", display_name="Random", provider="on-premises"),
                DiscoveredModel(
                    id="inference-glm-51-754b", display_name="GLM 5.1", provider="on-premises"
                ),
            ]
        )
        mock_get_adapter.return_value = mock_adapter

        provider_info = {
            "id": "on-premises",
            "name": "On-Premises",
            "endpoint": "https://ai.local",
            "env_key": "ON_PREMISES_AI_SERVER_KEY",
        }
        config = await alice._generate_configuration(provider_info, {"api_key": "key12345"})

        # GLM-5.1 (ranked) wins over the non-matching discovered id.
        assert config.agents.agents["alice"].model == "inference-glm-51-754b"

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
        # Should bypass existing config and stay in START for provider selection
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
        assert alice.project_context is not None
        cast(MagicMock, alice.project_context.artifact_service).db.get.return_value = mock_project

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

        assert alice.project_context is not None
        cast(
            MagicMock, alice.project_context.artifact_service
        ).db.get.side_effect = mock_get_with_project

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
        assert alice.project_context is not None
        cast(MagicMock, alice.project_context.artifact_service).db.get.return_value = mock_project

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

    def test_display_includes_alice_rationale(
        self, alice: AliceAgent, mock_thread, mock_db
    ) -> None:
        """Alice's own row in the confirm/review table must carry a rationale even
        though _assign_models never emits an 'alice' entry — it falls back to the
        canonical alice template so it matches the bootstrap card (the user-reported
        'rationale empty in confirm step' bug)."""
        alice._configuration = AliceConfiguration(
            provider=ProviderConfig(
                provider="on-premises",
                provider_name="On-Premises",
                endpoint="",
                credential_reference="",
                tested_at="",
                test_result="success",
            ),
            agents=AgentsConfig(
                updated_at="",
                agents={
                    "alice": AgentModelConfig(
                        model="inference-glm-51-754b",
                        temperature=0,
                        prompt_template="p",
                        tools=[],
                    ),
                    "bob": AgentModelConfig(
                        model="claude-sonnet", temperature=0, prompt_template="p", tools=[]
                    ),
                },
            ),
        )
        # Mirror _assign_models output: no 'alice' entry.
        alice._model_reasoning = [
            {"agent": "bob", "model": "claude-sonnet", "rationale": "Best for vision."}
        ]

        display = alice._get_model_assignments_display()
        alice_row = next(r for r in display if r["key"] == "alice")
        assert alice_row["rationale"] == _AGENT_RATIONALE["alice"].format(
            model="inference-glm-51-754b"
        )
        assert alice_row["rationale"] != ""

    def test_falls_back_to_template_when_no_reasoning(
        self, alice: AliceAgent, mock_thread, mock_db
    ) -> None:
        """When _model_reasoning is empty, rationale falls back to the canonical
        per-agent template (formatted with the chosen model) so the confirm/review
        table is never blank — matching what the bootstrap card shows."""
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
        assert display[0]["rationale"] == _AGENT_RATIONALE["bob"].format(model="claude-sonnet")
        assert display[0]["rationale"] != ""

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
