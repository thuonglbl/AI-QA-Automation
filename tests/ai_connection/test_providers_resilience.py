"""Resilience / branch-coverage expansion for provider adapters (Story 9.3).

The base suite (``test_providers.py``) reaches 100% line coverage of the
providers package, but several *behavioral* branches remain unexercised. This
module fills those gaps:

  - Endpoint **fallback** resilience: a network failure on the first candidate
    endpoint must not abort the probe — a later endpoint that answers ``200``
    still yields success.
  - ``verify_ssl`` **wiring**: on-premises tolerates self-signed certs
    (``verify=False``); every other provider verifies TLS (``verify=True``).
    Asserted both on the property and on the real ``httpx.AsyncClient`` kwargs.
  - Result-priority ordering: a ``provider_error`` (non-2xx) seen on any
    endpoint must win over a later ``unreachable`` network failure.
  - The ``403`` auth branch (the base suite only covers ``401``).
  - Base-URL **trailing-slash normalization** (``rstrip('/')`` — no double slash).

httpx is mocked via ``@patch("httpx.AsyncClient.get")`` (the established repo
pattern); no respx/pytest-httpx dependency is introduced.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from ai_qa.ai_connection.providers import ConnectionResult
from ai_qa.ai_connection.providers.openai_compatible import (
    AnthropicAdapter,
    BrowserUseAdapter,
    OnPremisesAdapter,
    OpenAIAdapter,
)

# Sentinel api key — must never leak into a ConnectionResult.message.
LEAK_CANARY = "sk-secret-LEAK-CANARY-123"
VALID_KEY = "valid-key-123"


def _mock_response(status_code: int, json_body: object | None = None) -> MagicMock:
    """Build a MagicMock httpx response with status_code/.json()/.text.

    ``json_body`` defaults to an empty OpenAI-shape ``{"data": []}`` so existing
    validation tests (which only care about status_code) keep working; discovery
    tests pass a populated body to exercise normalization/fallback branches.
    """
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = {"data": []} if json_body is None else json_body
    response.text = "RAW-PROVIDER-BODY-SHOULD-NOT-LEAK"
    return response


# ---------------------------------------------------------------------------
# Endpoint fallback resilience (the multi-endpoint `continue` loop)
# ---------------------------------------------------------------------------
class TestEndpointFallback:
    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_first_endpoint_network_fails_second_succeeds(self, mock_get) -> None:
        """[P1] A connect error on the first candidate must fall through to the
        next endpoint; a subsequent 200 still yields success."""
        mock_get.side_effect = [httpx.ConnectError("refused"), _mock_response(200)]
        adapter = OpenAIAdapter()

        result = await adapter.validate_connection({"api_key": VALID_KEY}, "https://api.test")

        assert result.success is True
        assert result.status == "success"
        assert result.error_category == "none"
        # Exactly two endpoints were probed before success.
        assert mock_get.await_count == 2

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_first_endpoint_404_second_succeeds(self, mock_get) -> None:
        """[P2] A non-auth, non-2xx response (404) on the first candidate flags a
        provider error but must not stop the probe; a later 200 wins."""
        mock_get.side_effect = [_mock_response(404), _mock_response(200)]
        adapter = OpenAIAdapter()

        result = await adapter.validate_connection({"api_key": VALID_KEY}, "https://api.test")

        assert result.success is True
        assert result.error_category == "none"
        assert mock_get.await_count == 2


# ---------------------------------------------------------------------------
# Result-priority ordering: provider_error wins over unreachable
# ---------------------------------------------------------------------------
class TestFailurePriority:
    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_provider_error_wins_over_later_unreachable(self, mock_get) -> None:
        """[P2] A 500 on an early endpoint followed by network failures on the
        rest must surface as ``provider_error`` (a real server error is more
        actionable than 'unreachable')."""
        # GeminiChatGPT probes 4 candidate endpoints.
        mock_get.side_effect = [
            _mock_response(500),
            httpx.ConnectError("refused"),
            httpx.ConnectError("refused"),
            httpx.ConnectError("refused"),
        ]
        adapter = OpenAIAdapter()

        result = await adapter.validate_connection({"api_key": LEAK_CANARY}, "https://api.test")

        assert result.success is False
        assert result.error_category == "provider_error"
        assert LEAK_CANARY not in result.message
        assert "RAW-PROVIDER-BODY-SHOULD-NOT-LEAK" not in result.message

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_all_endpoints_unreachable_yields_unreachable(self, mock_get) -> None:
        """[P2] When every candidate endpoint raises a network error (and no
        non-2xx was ever seen), the result is ``unreachable``."""
        mock_get.side_effect = httpx.ConnectTimeout("timed out")
        adapter = OpenAIAdapter()

        result = await adapter.validate_connection({"api_key": VALID_KEY}, "https://api.test")

        assert result.success is False
        assert result.error_category == "unreachable"


# ---------------------------------------------------------------------------
# 403 auth branch (base suite covers only 401)
# ---------------------------------------------------------------------------
class TestAuthForbidden:
    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_403_is_auth_failure(self, mock_get) -> None:
        """[P2] A 403 (forbidden) is normalized to ``auth`` just like 401."""
        mock_get.return_value = _mock_response(403)
        adapter = OpenAIAdapter()

        result = await adapter.validate_connection({"api_key": LEAK_CANARY}, "https://api.test")

        assert result.success is False
        assert result.error_category == "auth"
        assert LEAK_CANARY not in result.message


# ---------------------------------------------------------------------------
# verify_ssl rule (self-signed on-prem) — property + real AsyncClient wiring
# ---------------------------------------------------------------------------
class TestSslVerification:
    def test_on_premises_disables_ssl_verification(self) -> None:
        """[P1] On-premises tolerates self-signed certs (verify=False)."""
        assert OnPremisesAdapter()._verify_ssl is False

    @pytest.mark.parametrize("adapter", [OpenAIAdapter(), AnthropicAdapter()])
    def test_public_providers_enforce_ssl_verification(self, adapter) -> None:
        """[P1] Public providers must verify TLS (verify=True)."""
        assert adapter._verify_ssl is True

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_verify_flag_is_wired_into_async_client(self, mock_get) -> None:
        """[P1] Prove the ``_verify_ssl`` value actually reaches the real
        ``httpx.AsyncClient(verify=...)`` constructor for both on-prem (False)
        and a public provider (True)."""
        mock_get.return_value = _mock_response(200)
        captured: list[object] = []
        original_init = httpx.AsyncClient.__init__

        def capturing_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            captured.append(kwargs.get("verify"))
            original_init(self, *args, **kwargs)

        with patch.object(httpx.AsyncClient, "__init__", capturing_init):
            await OnPremisesAdapter().validate_connection(
                {"api_key": VALID_KEY}, "https://on-prem.example.com"
            )
            await OpenAIAdapter().validate_connection({"api_key": VALID_KEY}, "https://api.test")

        assert captured == [False, True]


# ---------------------------------------------------------------------------
# Base-URL trailing-slash normalization (rstrip('/'))
# ---------------------------------------------------------------------------
class TestBaseUrlNormalization:
    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_trailing_slash_does_not_double_up(self, mock_get) -> None:
        """[P2] A base URL with a trailing slash must not produce ``//v1/models``."""
        mock_get.return_value = _mock_response(200)
        adapter = OpenAIAdapter()

        await adapter.validate_connection({"api_key": VALID_KEY}, "https://api.test/")

        first_call_url = mock_get.call_args_list[0].args[0]
        assert first_call_url == "https://api.test/v1/models"
        assert "//v1" not in first_call_url

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_anthropic_probes_single_versioned_endpoint(self, mock_get) -> None:
        """[P2] Anthropic exposes only ``/v1/models`` — confirm it is the sole probe."""
        mock_get.return_value = _mock_response(200)
        adapter = AnthropicAdapter()

        result = await adapter.validate_connection(
            {"api_key": VALID_KEY}, "https://api.anthropic.com/"
        )

        assert isinstance(result, ConnectionResult)
        assert mock_get.await_count == 1
        assert mock_get.call_args_list[0].args[0] == "https://api.anthropic.com/v1/models"


# ---------------------------------------------------------------------------
# Story 9.4 — list_models / _discover endpoint-fallback resilience
# ---------------------------------------------------------------------------
# The base discovery suite (test_providers.py) covers single-endpoint success
# and "all endpoints fail -> []". These exercise the multi-endpoint *fallback*
# loop inside ``_discover`` (the per-endpoint ``continue`` branches), mirroring
# the validation-fallback coverage above but for discovery.
class TestDiscoveryEndpointFallback:
    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_empty_first_endpoint_then_models_on_second(self, mock_get) -> None:
        """[P1] A first candidate that answers 200 with a VALID-but-EMPTY body
        ({"data": []}) must not end discovery — _discover keeps probing and a
        later endpoint that returns models wins (the ``if models: return /
        continue`` branch)."""
        mock_get.side_effect = [
            _mock_response(200, {"data": []}),  # valid JSON, zero models -> continue
            _mock_response(200, {"data": [{"id": "model-x"}]}),  # real models -> return
        ]
        adapter = OpenAIAdapter()

        models = await adapter.list_models({"api_key": VALID_KEY}, "https://api.test")

        assert [m.id for m in models] == ["model-x"]
        assert all(m.provider == "openai" for m in models)
        assert mock_get.await_count == 2

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_network_error_first_endpoint_then_models_on_second(self, mock_get) -> None:
        """[P1] A network failure on the first candidate must fall through to the
        next endpoint during discovery (the network ``continue`` branch in
        _discover); a subsequent 200 with models still yields the models."""
        mock_get.side_effect = [
            httpx.ConnectError("refused"),
            _mock_response(200, {"data": [{"id": "model-x"}]}),
        ]
        adapter = OpenAIAdapter()

        models = await adapter.list_models({"api_key": LEAK_CANARY}, "https://api.test")

        assert [m.id for m in models] == ["model-x"]
        assert mock_get.await_count == 2
        # The key must never surface in the discovered models.
        assert LEAK_CANARY not in " ".join(m.model_dump_json() for m in models)

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_non_2xx_first_endpoint_then_models_on_second(self, mock_get) -> None:
        """[P2] A 404 on the first candidate (logged, not fatal) must not stop
        discovery; a later 200 with models still wins."""
        mock_get.side_effect = [
            _mock_response(404),
            _mock_response(200, {"data": [{"id": "model-x"}]}),
        ]
        adapter = OpenAIAdapter()

        models = await adapter.list_models({"api_key": VALID_KEY}, "https://api.test")

        assert [m.id for m in models] == ["model-x"]
        assert mock_get.await_count == 2


# ---------------------------------------------------------------------------
# Story 9.4 — BrowserUseAdapter.list_models own format/config floor
# ---------------------------------------------------------------------------
# BU overrides list_models with its OWN sub-floor key + base-URL guards (it
# gates curated static hints behind validate_connection). The generic floor
# test in test_providers.py uses OpenAIAdapter, so BU's duplicated guards are
# otherwise unexercised. These prove BU short-circuits with NO network call.
class TestBrowserUseDiscoveryFloor:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("api_key", ["", "   ", "short", "1234567", "  1234567  "])
    @patch("httpx.AsyncClient.get")
    async def test_short_or_empty_key_returns_empty_no_network(self, mock_get, api_key) -> None:
        """[P1] A sub-floor key (after strip) returns [] without any network
        call — BU's discovery never reaches validate_connection."""
        adapter = BrowserUseAdapter()

        models = await adapter.list_models(
            {"api_key": api_key}, "https://api.browser-use.com/api/v3"
        )

        assert models == []
        mock_get.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("base_url", ["", "ftp://server", "not-a-url"])
    @patch("httpx.AsyncClient.get")
    async def test_non_http_base_url_returns_empty_no_network(self, mock_get, base_url) -> None:
        """[P2] A missing/non-http base URL returns [] without a network call."""
        adapter = BrowserUseAdapter()

        models = await adapter.list_models({"api_key": VALID_KEY}, base_url)

        assert models == []
        mock_get.assert_not_awaited()
