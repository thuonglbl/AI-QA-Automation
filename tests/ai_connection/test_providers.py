"""Tests for the provider adapter interface and connection validation (Story 9.3).

Covers AC1 (normalized success result), AC2 (secret-free / stack-trace-free
failure messages incl. leak guardrails + format floor), and AC3 (config-owned
base URL resolution vs caller-supplied credentials), plus the Story 9.4
``list_models`` NotImplementedError extension point.

httpx is mocked via ``@patch("httpx.AsyncClient.get")`` (the established repo
pattern); no respx/pytest-httpx dependency is used.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from ai_qa.ai_connection.providers import (
    ConnectionResult,
    DiscoveredModel,
    ProviderAdapter,
    get_provider_adapter,
    resolve_base_url,
)
from ai_qa.ai_connection.providers.openai_compatible import (
    AnthropicAdapter,
    BrowserUseAdapter,
    GeminiAdapter,
    OnPremisesAdapter,
    OpenAIAdapter,
)
from ai_qa.config import AppSettings
from ai_qa.exceptions import ConfigError

# A sentinel api key used to prove it never leaks into ConnectionResult.message.
LEAK_CANARY = "sk-secret-LEAK-CANARY-123"

# Every supported provider id and its adapter type / config base-url setting.
ALL_PROVIDER_IDS = ["claude", "openai", "gemini", "on-premises", "browser-use-cloud"]


def _mock_response(status_code: int, json_body: object | None = None) -> MagicMock:
    """Build a MagicMock httpx response with status_code and .json()."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body if json_body is not None else {"data": []}
    response.text = "RAW-PROVIDER-BODY-SHOULD-NOT-LEAK"
    return response


def _base_url_for(provider_id: str) -> str:
    # On-premises requires a real http(s) base URL; others have config defaults.
    return "https://on-prem.example.com" if provider_id == "on-premises" else "https://api.test"


# ---------------------------------------------------------------------------
# AC1 — success path produces a normalized ConnectionResult
# ---------------------------------------------------------------------------
class TestValidateConnectionSuccess:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider_id", ALL_PROVIDER_IDS)
    @patch("httpx.AsyncClient.get")
    async def test_success_normalized_result(self, mock_get, provider_id: str) -> None:
        mock_get.return_value = _mock_response(200, {"data": [{"id": "m1"}]})
        adapter = get_provider_adapter(provider_id)

        result = await adapter.validate_connection(
            {"api_key": "valid-key-123"}, _base_url_for(provider_id)
        )

        assert isinstance(result, ConnectionResult)
        assert result.success is True
        assert result.status == "success"
        assert result.error_category == "none"
        assert result.provider == provider_id
        assert result.provider_name == adapter.provider_name


# ---------------------------------------------------------------------------
# AC2 — failures are secret-free and stack-trace-free
# ---------------------------------------------------------------------------
class TestValidateConnectionFailures:
    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_auth_401(self, mock_get) -> None:
        mock_get.return_value = _mock_response(401)
        adapter = OpenAIAdapter()

        result = await adapter.validate_connection({"api_key": LEAK_CANARY}, "https://api.test")

        assert result.success is False
        assert result.status == "failed"
        assert result.error_category == "auth"
        self._assert_no_leak(result)

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_unreachable_connect_error(self, mock_get) -> None:
        mock_get.side_effect = httpx.ConnectError("connection refused")
        adapter = OpenAIAdapter()

        result = await adapter.validate_connection({"api_key": LEAK_CANARY}, "https://api.test")

        assert result.success is False
        assert result.status == "failed"
        assert result.error_category == "unreachable"
        self._assert_no_leak(result)

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_unreachable_timeout(self, mock_get) -> None:
        mock_get.side_effect = httpx.ReadTimeout("timed out")
        adapter = OpenAIAdapter()

        result = await adapter.validate_connection({"api_key": LEAK_CANARY}, "https://api.test")

        assert result.error_category == "unreachable"
        self._assert_no_leak(result)

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_provider_error_500(self, mock_get) -> None:
        mock_get.return_value = _mock_response(500)
        adapter = OpenAIAdapter()

        result = await adapter.validate_connection({"api_key": LEAK_CANARY}, "https://api.test")

        assert result.success is False
        assert result.error_category == "provider_error"
        self._assert_no_leak(result)

    @staticmethod
    def _assert_no_leak(result: ConnectionResult) -> None:
        """The core AC2 guardrail: no api_key, raw body, or traceback in the message."""
        assert LEAK_CANARY not in result.message
        assert "RAW-PROVIDER-BODY-SHOULD-NOT-LEAK" not in result.message
        assert "Traceback" not in result.message
        for exc_name in ("ConnectError", "ReadTimeout", "HTTPError", "Exception"):
            assert exc_name not in result.message


# ---------------------------------------------------------------------------
# AC2 — format floor: short/empty keys never trigger a network call
# ---------------------------------------------------------------------------
class TestFormatFloor:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("api_key", ["", "   ", "short", "1234567"])
    @patch("httpx.AsyncClient.get")
    async def test_short_or_empty_key_no_network(self, mock_get, api_key: str) -> None:
        adapter = OpenAIAdapter()

        result = await adapter.validate_connection({"api_key": api_key}, "https://api.test")

        assert result.success is False
        assert result.error_category == "auth"
        mock_get.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_key_is_stripped_before_floor(self, mock_get) -> None:
        # 7 visible chars + surrounding whitespace -> still under the floor.
        adapter = OpenAIAdapter()

        result = await adapter.validate_connection({"api_key": "  1234567  "}, "https://api.test")

        assert result.success is False
        assert result.error_category == "auth"
        mock_get.assert_not_awaited()


# ---------------------------------------------------------------------------
# AC3 — config-owned base URL resolution; on-prem config guard
# ---------------------------------------------------------------------------
class TestBaseUrlResolutionAndConfigGuard:
    def _settings(self) -> AppSettings:
        # The repo .env supplies a valid user_secrets_encryption_key; base-URL
        # resolution only needs the config-owned URL fields.
        return AppSettings()

    @pytest.mark.parametrize(
        ("provider_id", "attr"),
        [
            ("claude", "claude_api_base_url"),
            ("openai", "openai_api_base_url"),
            ("gemini", "gemini_api_base_url"),
            ("on-premises", "on_premises_api_base_url"),
            ("browser-use-cloud", "browser_use_cloud_url"),
        ],
    )
    def test_resolve_base_url_from_settings(self, provider_id: str, attr: str) -> None:
        settings = self._settings()
        assert resolve_base_url(settings, provider_id) == getattr(settings, attr)

    def test_resolve_base_url_unknown_provider(self) -> None:
        with pytest.raises(ConfigError, match="Unknown provider id"):
            resolve_base_url(self._settings(), "no-such-provider")

    def test_get_provider_adapter_unknown(self) -> None:
        with pytest.raises(ConfigError, match="Unknown provider id"):
            get_provider_adapter("no-such-provider")

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_on_prem_empty_base_url_is_config_error(self, mock_get) -> None:
        adapter = OnPremisesAdapter()

        result = await adapter.validate_connection({"api_key": "valid-key-123"}, "")

        assert result.success is False
        assert result.error_category == "config"
        mock_get.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_on_prem_non_http_base_url_is_config_error(self, mock_get) -> None:
        adapter = OnPremisesAdapter()

        result = await adapter.validate_connection({"api_key": "valid-key-123"}, "ftp://server")

        assert result.success is False
        assert result.error_category == "config"
        mock_get.assert_not_awaited()


# ---------------------------------------------------------------------------
# Provider-specific header wiring (kept inside adapters, never in Alice)
# ---------------------------------------------------------------------------
class TestProviderSpecificHeaders:
    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_anthropic_uses_x_api_key_headers(self, mock_get) -> None:
        mock_get.return_value = _mock_response(200, {"data": []})
        adapter = AnthropicAdapter()

        await adapter.validate_connection({"api_key": "valid-key-123"}, "https://api.anthropic.com")

        _, kwargs = mock_get.call_args
        headers = kwargs["headers"]
        assert headers["x-api-key"] == "valid-key-123"
        assert "anthropic-version" in headers
        assert "Authorization" not in headers

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_openai_compatible_uses_bearer(self, mock_get) -> None:
        mock_get.return_value = _mock_response(200, {"data": []})
        adapter = OpenAIAdapter()

        await adapter.validate_connection({"api_key": "valid-key-123"}, "https://api.openai.com")

        _, kwargs = mock_get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer valid-key-123"

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_browser_use_uses_custom_api_key_header(self, mock_get) -> None:
        mock_get.return_value = _mock_response(200, {"ok": True})
        adapter = BrowserUseAdapter()

        await adapter.validate_connection(
            {"api_key": "valid-key-123"}, "https://api.browser-use.com/api/v2"
        )

        _, kwargs = mock_get.call_args
        headers = kwargs["headers"]
        assert headers["X-Browser-Use-API-Key"] == "valid-key-123"
        assert "Authorization" not in headers


# ---------------------------------------------------------------------------
# Story 9.4 — real model discovery (list_models)
# ---------------------------------------------------------------------------
# Provider ids that perform REAL endpoint discovery (vs the gated-static BU path).
DISCOVERY_PROVIDER_IDS = ["claude", "openai", "gemini", "on-premises"]


class TestListModelsAdapterContract:
    def test_adapters_are_provider_adapter_instances(self) -> None:
        for provider_id in ALL_PROVIDER_IDS:
            assert isinstance(get_provider_adapter(provider_id), ProviderAdapter)

    def test_discovered_model_is_constructible(self) -> None:
        model = DiscoveredModel(id="m1", display_name="Model 1", provider="claude")
        assert model.capability_hints is None
        assert model.context_window is None

    def test_base_stub_still_raises_not_implemented(self) -> None:
        """A bare ProviderAdapter that does not override discovery fails loudly."""

        class _BareAdapter(ProviderAdapter):
            provider_id = "bare"
            provider_name = "Bare"

            async def validate_connection(self, credentials, base_url):  # type: ignore[no-untyped-def]
                return self._result(success=True, message="ok", error_category="none")

        import asyncio

        with pytest.raises(NotImplementedError, match="does not implement model discovery"):
            asyncio.run(_BareAdapter().list_models({"api_key": "valid-key-123"}, "https://x"))


class TestListModelsDiscoverySuccess:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider_id", DISCOVERY_PROVIDER_IDS)
    @pytest.mark.parametrize(
        "json_body",
        [
            [{"id": "model-x"}],  # top-level list
            {"data": [{"id": "model-x"}]},  # OpenAI shape
            {"models": [{"name": "model-x"}]},  # Ollama shape
        ],
    )
    @patch("httpx.AsyncClient.get")
    async def test_discovery_normalizes_each_shape(
        self, mock_get, provider_id: str, json_body: object
    ) -> None:
        mock_get.return_value = _mock_response(200, json_body)
        adapter = get_provider_adapter(provider_id)

        models = await adapter.list_models({"api_key": "valid-key-123"}, _base_url_for(provider_id))

        assert len(models) == 1
        assert isinstance(models[0], DiscoveredModel)
        assert models[0].id == "model-x"
        assert models[0].display_name == "model-x"
        assert models[0].provider == provider_id
        # Capability fields are never fabricated.
        assert models[0].capability_hints is None
        assert models[0].context_window is None
        assert models[0].supports_tools is None

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_gemini_strips_models_prefix(self, mock_get) -> None:
        mock_get.return_value = _mock_response(200, {"models": [{"name": "models/gemini-1.5-pro"}]})
        adapter = GeminiAdapter()

        models = await adapter.list_models({"api_key": "valid-key-123"}, "https://api.test")

        assert models[0].id == "gemini-1.5-pro"
        assert models[0].display_name == "gemini-1.5-pro"

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_gemini_uses_query_key_no_auth_header(self, mock_get) -> None:
        mock_get.return_value = _mock_response(200, {"models": [{"name": "models/gemini-pro"}]})
        adapter = GeminiAdapter()

        await adapter.list_models({"api_key": "valid-key-123"}, "https://api.test")

        _, kwargs = mock_get.call_args
        assert kwargs["params"] == {"key": "valid-key-123"}
        assert kwargs["headers"] == {}


class TestListModelsNormalizationEdges:
    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_name_falls_back_to_id_and_vice_versa(self, mock_get) -> None:
        mock_get.return_value = _mock_response(
            200, {"data": [{"id": "only-id"}, {"name": "only-name"}]}
        )
        adapter = OpenAIAdapter()

        models = await adapter.list_models({"api_key": "valid-key-123"}, "https://api.test")

        by_id = {m.id: m for m in models}
        assert by_id["only-id"].display_name == "only-id"
        assert by_id["only-name"].display_name == "only-name"

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_non_dict_and_idless_entries_skipped(self, mock_get) -> None:
        mock_get.return_value = _mock_response(
            200, {"data": [{"id": "good"}, "not-a-dict", {"foo": "bar"}, {"id": ""}]}
        )
        adapter = OpenAIAdapter()

        models = await adapter.list_models({"api_key": "valid-key-123"}, "https://api.test")

        assert [m.id for m in models] == ["good"]

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_empty_data_yields_empty_list(self, mock_get) -> None:
        mock_get.return_value = _mock_response(200, {"data": []})
        adapter = OpenAIAdapter()

        models = await adapter.list_models({"api_key": "valid-key-123"}, "https://api.test")

        assert models == []


class TestListModelsDiscoveryFailure:
    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_all_endpoints_error_status_returns_empty(self, mock_get) -> None:
        mock_get.return_value = _mock_response(500, {"data": [{"id": "x"}]})
        adapter = OpenAIAdapter()

        models = await adapter.list_models({"api_key": "valid-key-123"}, "https://api.test")

        assert models == []

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_network_errors_return_empty(self, mock_get) -> None:
        mock_get.side_effect = httpx.ConnectError("connection refused")
        adapter = OpenAIAdapter()

        models = await adapter.list_models({"api_key": LEAK_CANARY}, "https://api.test")

        assert models == []

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_non_json_body_returns_empty(self, mock_get) -> None:
        bad = MagicMock()
        bad.status_code = 200
        bad.json.side_effect = ValueError("not json")
        bad.text = "<html>login</html>"
        mock_get.return_value = bad
        adapter = OpenAIAdapter()

        models = await adapter.list_models({"api_key": "valid-key-123"}, "https://api.test")

        assert models == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("api_key", ["", "   ", "short", "1234567", "  1234567  "])
    @patch("httpx.AsyncClient.get")
    async def test_format_floor_makes_no_network_call(self, mock_get, api_key: str) -> None:
        adapter = OpenAIAdapter()

        models = await adapter.list_models({"api_key": api_key}, "https://api.test")

        assert models == []
        mock_get.assert_not_awaited()


class TestBrowserUseDiscovery:
    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_returns_static_hints_when_connection_valid(self, mock_get) -> None:
        # /billing/account validates (200 + JSON object) -> BU returns its documented models.
        mock_get.return_value = _mock_response(200, {"ok": True})
        adapter = BrowserUseAdapter()

        models = await adapter.list_models(
            {"api_key": "valid-key-123"}, "https://api.browser-use.com/api/v2"
        )

        assert len(models) >= 1
        assert all(m.provider == "browser-use-cloud" for m in models)

    @pytest.mark.asyncio
    async def test_returns_static_hints_without_network_call(self) -> None:
        """BU list_models returns curated models without network call (validation
        happens separately in the Alice flow before calling list_models)."""
        adapter = BrowserUseAdapter()
        # No httpx mock - list_models should not make any network calls
        models = await adapter.list_models(
            {"api_key": "valid-key-123"}, "https://api.browser-use.com/api/v2"
        )

        assert len(models) >= 1
        assert all(m.provider == "browser-use-cloud" for m in models)


class TestDiscoverySecretHygiene:
    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_api_key_never_appears_in_discovered_models(self, mock_get) -> None:
        mock_get.return_value = _mock_response(200, {"data": [{"id": "model-x"}]})
        adapter = OpenAIAdapter()

        models = await adapter.list_models({"api_key": LEAK_CANARY}, "https://api.test")

        serialized = " ".join(m.model_dump_json() for m in models)
        assert LEAK_CANARY not in serialized
