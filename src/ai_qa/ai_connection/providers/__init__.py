"""Provider adapter package: validation/model-discovery seam (Story 9.3).

Public surface:
  - ``ConnectionResult`` / ``DiscoveredModel`` — normalized, non-secret models.
  - ``ProviderAdapter`` — the adapter contract.
  - ``get_provider_adapter(provider_id)`` — factory for a provider adapter.
  - ``resolve_base_url(settings, provider_id)`` — config-owned base URL resolver.

This registry is pure: no DB, no secrets service. Base URLs come only from
``AppSettings``; credentials are passed in by the caller (Alice). Provider ids
match ``alice.PROVIDER_OPTIONS`` exactly. OpenAI and Gemini are distinct provider
ids (``openai`` and ``gemini``); the combined ``gemini-chatgpt`` id was removed in
Story 9.4.
"""

from ai_qa.ai_connection.providers.base import (
    ConnectionResult,
    DiscoveredModel,
    ProviderAdapter,
)
from ai_qa.ai_connection.providers.openai_compatible import (
    AnthropicAdapter,
    BrowserUseAdapter,
    GeminiAdapter,
    OnPremisesAdapter,
    OpenAIAdapter,
    get_provider_benchmark,
)
from ai_qa.config import AppSettings
from ai_qa.exceptions import ConfigError

# Canonical provider id -> adapter instance. Adapters are stateless, so a single
# shared instance per provider is safe.
_PROVIDER_ADAPTERS: dict[str, ProviderAdapter] = {
    "claude": AnthropicAdapter(),
    "openai": OpenAIAdapter(),
    "gemini": GeminiAdapter(),
    "on-premises": OnPremisesAdapter(),
    "browser-use-cloud": BrowserUseAdapter(),
}

# Canonical provider id -> AppSettings attribute holding the config-owned base URL.
# Uses the exact AppSettings attribute names from config.py. OpenAI and Gemini are
# distinct providers with independent base URLs.
_PROVIDER_BASE_URL_SETTINGS: dict[str, str] = {
    "claude": "claude_api_base_url",
    "openai": "openai_api_base_url",
    "gemini": "gemini_api_base_url",
    "on-premises": "on_premises_api_base_url",
    "browser-use-cloud": "browser_use_cloud_url",
}


def get_provider_adapter(provider_id: str) -> ProviderAdapter:
    """Return the adapter for a canonical provider id.

    Raises:
        ConfigError: If the provider id is unknown (message is secret-free).
    """
    adapter = _PROVIDER_ADAPTERS.get(provider_id)
    if adapter is None:
        raise ConfigError(f"Unknown provider id: {provider_id!r}")
    return adapter


def resolve_base_url(settings: AppSettings, provider_id: str) -> str:
    """Resolve the config-owned base URL for a provider from ``AppSettings``.

    The adapter layer never reads secrets — only base URLs come from here.

    Raises:
        ConfigError: If the provider id is unknown (message is secret-free).
    """
    attr = _PROVIDER_BASE_URL_SETTINGS.get(provider_id)
    if attr is None:
        raise ConfigError(f"Unknown provider id: {provider_id!r}")
    return getattr(settings, attr, "") or ""


__all__ = [
    "ConnectionResult",
    "DiscoveredModel",
    "ProviderAdapter",
    "get_provider_adapter",
    "get_provider_benchmark",
    "resolve_base_url",
]
