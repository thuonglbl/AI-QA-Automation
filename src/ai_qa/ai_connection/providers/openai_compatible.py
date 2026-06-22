"""Concrete provider adapters with real connection validation (Story 9.3).

All adapters perform a lightweight, real auth+reachability probe via httpx and
normalize the outcome into a secret-free :class:`ConnectionResult`. They never
read secrets or decrypt anything — credentials are passed in by the caller
(Alice), and base URLs are config-owned (from ``AppSettings``).

Message hygiene (AC2): every returned ``message`` is curated and human-friendly.
Raw provider responses, api keys, and exception/stack-trace text are logged at
debug/warning level only and never placed into ``ConnectionResult.message``.
"""

import logging
from collections.abc import Mapping
from typing import Any, ClassVar

import httpx

from ai_qa.ai_connection.providers.base import (
    ConnectionResult,
    DiscoveredModel,
    ProviderAdapter,
)

logger = logging.getLogger(__name__)

# Minimum api key length before any network call (mirrors alice._test_connection
# and Story 9.2's validate_secret_format >= 8 rule).
_MIN_API_KEY_LENGTH = 8
_HTTP_TIMEOUT_SECONDS = 10.0

# Static model names used as RANKING HINTS / discovery bootstrap only (Story 9.4,
# AC3). These are NEVER returned from ``list_models`` as if discovered for a
# provider that exposes a real listing endpoint — a hint id is only honored when
# discovery confirms it. They serve as the curated fallback for a provider that
# has no model-listing endpoint, gated behind a successful ``validate_connection``
# (the "verified availability" bar). Keep conservative and minimal — prefer
# discovery over a long, fast-rotting hardcoded catalog.
_STATIC_MODEL_HINTS: dict[str, list[str]] = {
    # Anthropic exposes /v1/models (real discovery); these are ranking hints only.
    "claude": [
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-3-5-haiku-latest",
    ],
    # Browser Use Cloud documents its own models. ``/me`` is the 9.3 validation
    # probe, NOT a model list, so these curated hints are the discovery source,
    # gated behind a successful connection validation. (default: claude-sonnet-4.6;
    # most capable: claude-opus-4.6 — see Story 9.4 References.)
    "browser-use-cloud": [
        "claude-sonnet-4.6",
        "claude-opus-4.6",
    ],
}

# Non-secret provider benchmark ranking hints (Story 9.4, Task 2c). Seeded from
# OnlineMind2Web (March 2026). Used to rank among discovered/validated models and
# surfaced (secret-free) to the configuration-review UI. NEVER used to assign an
# undiscovered model (AC3).
_BENCHMARK_SOURCE_URL = "https://browser-use.com/benchmarks"
_PROVIDER_BENCHMARK_HINTS: dict[str, dict[str, Any]] = {
    "browser-use-cloud": {
        "accuracy_percent": 97,
        "benchmark": "OnlineMind2Web (March 2026)",
        "source_url": _BENCHMARK_SOURCE_URL,
        "note": "Highest accuracy provider.",
    },
    "claude": {
        "accuracy_percent": 62,
        "benchmark": "OnlineMind2Web (March 2026)",
        "source_url": _BENCHMARK_SOURCE_URL,
    },
    "openai": {
        "benchmark": "OnlineMind2Web (March 2026)",
        "source_url": _BENCHMARK_SOURCE_URL,
    },
    "gemini": {
        "benchmark": "OnlineMind2Web (March 2026)",
        "source_url": _BENCHMARK_SOURCE_URL,
    },
}


def get_provider_benchmark(provider_id: str) -> dict[str, Any] | None:
    """Return non-secret benchmark ranking-hint metadata for a provider, if any."""
    hint = _PROVIDER_BENCHMARK_HINTS.get(provider_id)
    return dict(hint) if hint is not None else None


class OpenAICompatibleAdapter(ProviderAdapter):
    """Adapter for OpenAI-compatible providers (model-listing via Bearer auth).

    Reused by Gemini/ChatGPT and On-Premises (both OpenAI-compatible). Subclasses
    override identity and, where needed, the auth header / candidate endpoints.
    """

    provider_id: ClassVar[str] = "openai-compatible"
    provider_name: ClassVar[str] = "OpenAI-Compatible Provider"

    def _build_headers(self, api_key: str) -> dict[str, str]:
        """Auth headers for the probe. Override per provider as needed."""
        return {"Authorization": f"Bearer {api_key}"}

    def _build_query_params(self, api_key: str) -> dict[str, str]:
        """Query params for the probe/discovery request. Override per provider.

        Default is no query auth. Native Gemini overrides this to append the api
        key as a ``?key=`` query parameter (its Generative Language API does not
        use a Bearer/x-api-key header).
        """
        return {}

    def _clean_model_id(self, raw_id: str) -> str:
        """Normalize a raw provider model id. Override per provider as needed.

        Default is identity. Native Gemini overrides this to strip the
        ``models/`` prefix (e.g. ``models/gemini-1.5-pro`` -> ``gemini-1.5-pro``).
        """
        return raw_id

    def _candidate_endpoints(self, base_url: str) -> list[str]:
        """Endpoints to probe, in order (validation + discovery share these)."""
        root = base_url.rstrip("/")
        return [
            f"{root}/v1/models",
            f"{root}/models",
            f"{root}/api/tags",  # Ollama
            f"{root}/api/models",
        ]

    @property
    def _verify_ssl(self) -> bool:
        # Self-signed certs are common on-prem (mirrors client.py SSL rule).
        return self.provider_id != "on-premises"

    async def validate_connection(
        self, credentials: Mapping[str, str], base_url: str
    ) -> ConnectionResult:
        # Format floor: reject empty/short/non-string keys before any network call.
        raw_key = credentials.get("api_key")
        if not isinstance(raw_key, str) or len(raw_key.strip()) < _MIN_API_KEY_LENGTH:
            return self._result(
                success=False,
                message=(
                    f"The {self.provider_name} API key looks invalid (empty or too short). "
                    "Enter a valid API key and try again."
                ),
                error_category="auth",
            )
        api_key = raw_key.strip()
        # Config floor: a missing/invalid base URL is a deployment-config issue, not
        # a network failure. On-premises overrides validate_connection to guard this
        # earlier; this catches the same case for every other provider.
        if not isinstance(base_url, str) or not base_url.startswith("http"):
            return self._result(
                success=False,
                message=(
                    f"The {self.provider_name} endpoint is not configured correctly. "
                    "Set a valid http(s) base URL in the deployment configuration and try again."
                ),
                error_category="config",
            )
        return await self._probe(api_key, base_url)

    @staticmethod
    def _is_valid_api_body(response: httpx.Response) -> bool:
        """A real AI endpoint answers with parseable JSON (object or array).

        A 200 alone is not proof of a valid connection — captive portals, proxy
        login pages, and generic landing pages also return 200 with HTML. Requiring
        a JSON object/array body screens those false positives out.
        """
        try:
            body = response.json()
        except ValueError:
            return False
        return isinstance(body, dict | list)

    async def _probe(self, api_key: str, base_url: str) -> ConnectionResult:
        headers = self._build_headers(api_key)
        params = self._build_query_params(api_key)
        endpoints = self._candidate_endpoints(base_url)
        saw_provider_error = False
        saw_auth_failure = False

        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT_SECONDS, verify=self._verify_ssl, follow_redirects=False
        ) as async_client:
            for endpoint in endpoints:
                try:
                    response = await async_client.get(endpoint, headers=headers, params=params)
                except (httpx.HTTPError, httpx.InvalidURL, httpx.CookieConflict) as exc:
                    # Network/URL family (connect/timeout/DNS/bad-url). Log type only —
                    # never the key — and fall through to the next candidate endpoint.
                    logger.warning(
                        "Connection probe to %s failed: %s",
                        self.provider_name,
                        type(exc).__name__,
                    )
                    continue

                status_code = response.status_code
                if status_code == 200 and self._is_valid_api_body(response):
                    return self._result(
                        success=True,
                        message=f"Successfully connected to {self.provider_name}.",
                        error_category="none",
                    )
                if status_code in (401, 403):
                    # Record auth failure but keep probing — a later candidate path on a
                    # mixed-auth gateway may still authenticate. Only conclude "auth" if
                    # no endpoint succeeds.
                    saw_auth_failure = True
                    logger.warning(
                        "%s rejected authentication during validation (status %s).",
                        self.provider_name,
                        status_code,
                    )
                    continue
                # A 200 with an unrecognized body, or any other non-2xx response, is a
                # provider-side error. Keep probing the remaining candidate endpoints.
                saw_provider_error = True
                logger.warning(
                    "%s returned unexpected status %s during validation.",
                    self.provider_name,
                    status_code,
                )

        # Failure priority (most actionable first): auth > provider_error > unreachable.
        if saw_auth_failure:
            return self._result(
                success=False,
                message=(
                    f"Authentication failed — the API key was rejected by "
                    f"{self.provider_name}. Replace the key and try again."
                ),
                error_category="auth",
            )
        if saw_provider_error:
            return self._result(
                success=False,
                message=(
                    f"{self.provider_name} returned an unexpected error during validation. "
                    "Try again later or contact your administrator."
                ),
                error_category="provider_error",
            )
        return self._result(
            success=False,
            message=(
                f"Could not reach {self.provider_name} at the configured endpoint. "
                "Check the deployment base URL and network access."
            ),
            error_category="unreachable",
        )

    # -- model discovery (Story 9.4) --------------------------------------
    async def list_models(
        self, credentials: Mapping[str, str], base_url: str
    ) -> list[DiscoveredModel]:
        """Discover available models from the provider (Story 9.4).

        Mirrors the validation probe: same candidate endpoints, headers, query
        params, SSL rule, and timeout. Returns the RAW discovered set normalized
        into :class:`DiscoveredModel` values — no scoring, assignment, or
        persistence (Alice owns those). Returns an empty list (never raises) on a
        sub-floor key or when no endpoint yields a usable model list, so Alice
        owns the "no models -> block review" decision (AC2).
        """
        raw_key = credentials.get("api_key")
        if not isinstance(raw_key, str) or len(raw_key.strip()) < _MIN_API_KEY_LENGTH:
            # Discovery cannot run without a usable key; the connection-test step
            # already surfaced the auth error. No network call.
            return []
        api_key = raw_key.strip()
        if not isinstance(base_url, str) or not base_url.startswith("http"):
            return []
        return await self._discover(api_key, base_url)

    async def _discover(self, api_key: str, base_url: str) -> list[DiscoveredModel]:
        """Probe candidate endpoints and return the first usable normalized set."""
        headers = self._build_headers(api_key)
        params = self._build_query_params(api_key)
        endpoints = self._candidate_endpoints(base_url)
        saw_auth_failure = False

        # NOTE: A new httpx.AsyncClient is created per call (no connection pooling).
        # This mirrors the existing _probe pattern. Consider a shared client with
        # proper lifecycle management if concurrent discovery throughput becomes
        # a bottleneck.
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT_SECONDS, verify=self._verify_ssl, follow_redirects=False
        ) as async_client:
            for endpoint in endpoints:
                try:
                    response = await async_client.get(endpoint, headers=headers, params=params)
                except (httpx.HTTPError, httpx.InvalidURL, httpx.CookieConflict) as exc:
                    # Network/URL family. Log type only — never the key — and try next.
                    logger.warning(
                        "Model discovery probe to %s failed: %s",
                        self.provider_name,
                        type(exc).__name__,
                    )
                    continue

                if response.status_code in (401, 403):
                    saw_auth_failure = True
                    logger.warning(
                        "Model discovery: %s rejected authentication (status %s).",
                        self.provider_name,
                        response.status_code,
                    )
                    continue

                if response.status_code == 200:
                    try:
                        if self._is_valid_api_body(response):
                            models = self._normalize_models(response.json())
                            if models:
                                return models
                            # Valid JSON but no usable models on this endpoint — keep probing.
                            continue
                    except ValueError:
                        # JSON decode error — not a valid API response, try next endpoint
                        logger.warning(
                            "%s returned invalid JSON during model discovery.",
                            self.provider_name,
                        )
                        continue
                logger.warning(
                    "%s returned status %s during model discovery.",
                    self.provider_name,
                    response.status_code,
                )
        if saw_auth_failure:
            logger.warning(
                "Model discovery for %s: all endpoints rejected authentication. "
                "The API key may be invalid or lack model-listing permissions.",
                self.provider_name,
            )
        return []

    def _normalize_models(self, body: object) -> list[DiscoveredModel]:
        """Normalize an OpenAI-compatible/Ollama response into DiscoveredModel values.

        Handles the three shapes the legacy discovery handled: a top-level list,
        ``{"data": [...]}`` (OpenAI), and ``{"models": [...]}`` (Ollama). Skips
        non-dict entries and entries with no usable id. Optional capability fields
        are left at their ``None`` defaults — capability metadata is never
        fabricated.
        """
        entries = self._extract_entries(body)
        models: list[DiscoveredModel] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            model = self._normalize_entry(entry)
            if model is not None:
                models.append(model)
        return models

    @staticmethod
    def _extract_entries(body: object) -> list[Any]:
        """Pull the list of model entries out of any supported response shape."""
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, list):
                return data
            ollama_models = body.get("models")
            if isinstance(ollama_models, list):
                return ollama_models
        return []

    def _normalize_entry(self, entry: dict[str, Any]) -> DiscoveredModel | None:
        """Normalize a single provider model entry; return None to skip it."""
        raw_id = entry.get("id") or entry.get("name")
        if raw_id is None:
            return None
        # Handle numeric IDs by converting to string
        raw_id_str = str(raw_id).strip()
        if not raw_id_str:
            return None
        model_id = self._clean_model_id(raw_id_str)
        raw_display = entry.get("name") or entry.get("id")
        if raw_display is not None:
            raw_display_str = str(raw_display).strip()
            if raw_display_str:
                display_name = self._clean_model_id(raw_display_str)
            else:
                display_name = model_id
        else:
            display_name = model_id
        caps = self._extract_capabilities(entry)
        return DiscoveredModel(
            id=model_id,
            display_name=display_name,
            provider=self.provider_id,
            supports_vision=self._cap_bool(caps, "vision"),
            supports_tools=self._cap_bool(caps, "function_calling", "tools"),
            context_window=self._cap_int(entry, caps),
        )

    @staticmethod
    def _extract_capabilities(entry: dict[str, Any]) -> dict[str, Any]:
        """Pull the capability map from either the top-level or OpenWebUI nested shape.

        OpenAI returns nothing here; the on-prem OpenWebUI gateway nests it at
        ``info.meta.capabilities``. Returns ``{}`` when absent so callers default
        the capability fields to ``None`` (never fabricated).
        """
        caps = entry.get("capabilities")
        if not isinstance(caps, dict):
            info = entry.get("info")
            meta = info.get("meta") if isinstance(info, dict) else None
            caps = meta.get("capabilities") if isinstance(meta, dict) else None
        return caps if isinstance(caps, dict) else {}

    @staticmethod
    def _cap_bool(caps: dict[str, Any], *keys: str) -> bool | None:
        """Return the first boolean capability flag found, else None (absent)."""
        for key in keys:
            val = caps.get(key)
            if isinstance(val, bool):
                return val
        return None

    @staticmethod
    def _cap_int(entry: dict[str, Any], caps: dict[str, Any]) -> int | None:
        """Best-effort context-window read; None when the gateway does not advertise it."""
        for source, key in (
            (entry, "context_length"),
            (caps, "context_length"),
            (caps, "max_tokens"),
        ):
            val = source.get(key)
            if isinstance(val, int) and not isinstance(val, bool):
                return val
        return None


def _static_hint_models(provider_id: str) -> list[DiscoveredModel]:
    """Build DiscoveredModel values from the curated static hints for a provider.

    Used only as the gated fallback for a provider with no model-listing endpoint
    (the hints are returned only after a successful ``validate_connection``).
    """
    hints = _STATIC_MODEL_HINTS.get(provider_id, [])
    return [DiscoveredModel(id=name, display_name=name, provider=provider_id) for name in hints]


class OpenAIAdapter(OpenAICompatibleAdapter):
    """OpenAI / ChatGPT adapter (Bearer auth, ``/v1/models`` discovery).

    Inherits the OpenAI-compatible defaults (Bearer header + ``/v1/models`` as the
    first candidate endpoint), so both validation and discovery work unchanged.
    """

    provider_id: ClassVar[str] = "openai"
    provider_name: ClassVar[str] = "OpenAI / ChatGPT"


class GeminiAdapter(OpenAICompatibleAdapter):
    """Native Google Gemini adapter (Generative Language API).

    Gemini authenticates with a ``?key=<api_key>`` query parameter (NOT a Bearer
    or ``x-api-key`` header) and lists models at ``GET {base_url}/v1beta/models``,
    returning ``{"models": [{"name": "models/gemini-1.5-pro", ...}]}``. The
    ``models/`` prefix is stripped when normalizing the id/display_name. All
    Gemini-specific auth/endpoint detail stays inside this adapter, never in Alice.
    """

    provider_id: ClassVar[str] = "gemini"
    provider_name: ClassVar[str] = "Google Gemini"
    _MODELS_PREFIX: ClassVar[str] = "models/"

    def _build_headers(self, api_key: str) -> dict[str, str]:
        # Gemini uses query-param auth; no auth header.
        return {}

    def _build_query_params(self, api_key: str) -> dict[str, str]:
        # WARNING: Gemini authenticates via query param — the API key is visible
        # in HTTP access logs, proxy logs, and monitoring systems. This is an
        # inherent limitation of the Gemini Generative Language API design.
        # Never log the full URL at or above WARNING level.
        return {"key": api_key}

    def _candidate_endpoints(self, base_url: str) -> list[str]:
        root = base_url.rstrip("/")
        return [
            f"{root}/v1beta/models",
            f"{root}/v1/models",  # Fallback for OpenAI-compatible gateways
        ]

    def _clean_model_id(self, raw_id: str) -> str:
        if not isinstance(raw_id, str):
            raw_id = str(raw_id)
        if raw_id.startswith(self._MODELS_PREFIX):
            return raw_id[len(self._MODELS_PREFIX) :]
        return raw_id


class OnPremisesAdapter(OpenAICompatibleAdapter):
    """On-premises OpenAI-compatible adapter (self-signed certs tolerated).

    Adds a fail-fast config guard for a missing/invalid base URL, preserving the
    current on-prem behavior in ``alice._test_connection``.
    """

    provider_id: ClassVar[str] = "on-premises"
    provider_name: ClassVar[str] = "On-Premises"

    async def validate_connection(
        self, credentials: Mapping[str, str], base_url: str
    ) -> ConnectionResult:
        if not base_url or not base_url.startswith("http"):
            return self._result(
                success=False,
                message=(
                    "The on-premises endpoint is not configured. Set a valid http(s) "
                    "base URL in the deployment configuration and try again."
                ),
                error_category="config",
            )
        return await super().validate_connection(credentials, base_url)

    async def list_models(
        self, credentials: Mapping[str, str], base_url: str
    ) -> list[DiscoveredModel]:
        return await super().list_models(credentials, base_url)


class AnthropicAdapter(OpenAICompatibleAdapter):
    """Claude (Anthropic) adapter.

    Anthropic uses ``x-api-key`` + ``anthropic-version`` headers (no Bearer auth).
    These provider-specific details stay inside the adapter, never in Alice.
    """

    provider_id: ClassVar[str] = "claude"
    provider_name: ClassVar[str] = "Claude (Anthropic)"
    _ANTHROPIC_VERSION: ClassVar[str] = "2023-06-01"

    def _build_headers(self, api_key: str) -> dict[str, str]:
        return {"x-api-key": api_key, "anthropic-version": self._ANTHROPIC_VERSION}

    def _candidate_endpoints(self, base_url: str) -> list[str]:
        root = base_url.rstrip("/")
        return [f"{root}/v1/models"]


class ClaudeSSOAdapter(AnthropicAdapter):
    """Claude via enterprise SSO login.

    Behaves like :class:`AnthropicAdapter` (Anthropic Messages API, ``/v1/models``
    discovery) but is reached after the OAuth/SSO browser login rather than a
    manually entered api key. The credential passed in is the token obtained from
    the SSO flow (an OAuth bearer token in real-OAuth mode, or the server-side
    enterprise key in mock/demo mode); both authenticate the ``/v1/models`` probe
    via the same header path as the api-key adapter.
    """

    provider_id: ClassVar[str] = "claude-sso"
    provider_name: ClassVar[str] = "Claude (Anthropic) — SSO"


class BrowserUseAdapter(OpenAICompatibleAdapter):
    """Browser Use Cloud adapter — authenticated reachability check + model hints.

    BU Cloud is the highest-accuracy provider (97% OnlineMind2Web, March 2026) and
    documents its own models. It authenticates with the ``X-Browser-Use-API-Key``
    header (keys start with ``bu_``) against the v2 REST API, validated via the
    ``/billing/account`` endpoint. The v2 API exposes no public model-listing
    route, so model discovery returns BU's curated documented models
    (``_STATIC_MODEL_HINTS["browser-use-cloud"]``) gated behind a successful
    ``validate_connection`` (the "verified availability" bar). It never returns an
    empty list purely because there is no model-listing endpoint.
    """

    provider_id: ClassVar[str] = "browser-use-cloud"
    provider_name: ClassVar[str] = "Browser Use Cloud"
    _API_KEY_HEADER: ClassVar[str] = "X-Browser-Use-API-Key"

    def _build_headers(self, api_key: str) -> dict[str, str]:
        # BU uses a custom API-key header, not Bearer/x-api-key.
        return {self._API_KEY_HEADER: api_key}

    def _candidate_endpoints(self, base_url: str) -> list[str]:
        root = base_url.rstrip("/")
        # /billing/account is a lightweight authenticated GET that returns a JSON
        # object — a reliable auth+reachability probe for the v2 API.
        return [f"{root}/billing/account", root]

    async def list_models(
        self, credentials: Mapping[str, str], base_url: str
    ) -> list[DiscoveredModel]:
        raw_key = credentials.get("api_key")
        if not isinstance(raw_key, str) or len(raw_key.strip()) < _MIN_API_KEY_LENGTH:
            return []
        if not isinstance(base_url, str) or not base_url.startswith("http"):
            return []
        # BU's v2 API has no model-listing route. Gate the curated documented
        # models behind a successful connection validation.
        # Note: validate_connection was already called successfully in the Alice flow
        # before calling list_models, so we trust the connection is valid here.
        return _static_hint_models(self.provider_id)
