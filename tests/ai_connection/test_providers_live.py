"""Opt-in real-key provider model-discovery integration tests (Story 9.4, Task 4b).

These exercise ``list_models`` against the REAL providers using the ``TEST_*_KEY``
values in ``.env``. They are marker-gated (``live_provider``) and SKIP whenever a
given key is missing or still a ``replace-with-...`` placeholder, so the default
``uv run pytest`` stays green on machines without keys.

Run explicitly to debug real discovery for every provider::

    uv run pytest -m live_provider

Secret hygiene: keys come from ``.env`` only — never hardcode and never log a
key. On failure we capture the provider id / endpoint, never the key. Discovery
is read-only, so no cleanup is required.
"""

from pathlib import Path

import pytest

from ai_qa.ai_connection.providers import get_provider_adapter, resolve_base_url
from ai_qa.config import AppSettings

pytestmark = pytest.mark.live_provider

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PROJECT_ROOT / ".env"
_PLACEHOLDER_PREFIX = "replace-with"

# provider id -> the .env variable holding its real test key.
_PROVIDER_TEST_KEYS = {
    "browser-use-cloud": "TEST_BROWSER_USE_KEY",
    "claude": "TEST_CLAUDE_KEY",
    "gemini": "TEST_GEMINI_KEY",
    "openai": "TEST_OPENAI_KEY",
    "on-premises": "TEST_ON_PREMISES_KEY",
}


def _load_env_file() -> dict[str, str]:
    """Parse simple ``KEY=value`` lines from ``.env`` (no shell expansion)."""
    values: dict[str, str] = {}
    if not _ENV_FILE.exists():
        return values
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


_ENV = _load_env_file()


def _resolve_test_key(provider_id: str) -> str | None:
    """Return a usable real key for a provider, or None when unset/placeholder."""
    raw = _ENV.get(_PROVIDER_TEST_KEYS[provider_id], "")
    if not raw or raw.startswith(_PLACEHOLDER_PREFIX):
        return None
    return raw


class TestRealProviderDiscovery:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider_id", sorted(_PROVIDER_TEST_KEYS))
    async def test_list_models_against_real_provider(self, provider_id: str) -> None:
        api_key = _resolve_test_key(provider_id)
        if api_key is None:
            pytest.skip(f"No real key for {provider_id} ({_PROVIDER_TEST_KEYS[provider_id]})")

        base_url = resolve_base_url(AppSettings(), provider_id)
        if not base_url.startswith("http"):
            pytest.skip(f"No base URL configured for {provider_id}")

        adapter = get_provider_adapter(provider_id)
        models = await adapter.list_models({"api_key": api_key}, base_url)

        # Diagnose without leaking the key: report only provider id + endpoint.
        assert models, f"{provider_id} discovery returned no models (endpoint={base_url})"
        for model in models:
            assert model.provider == provider_id
            assert model.id and model.display_name
            assert api_key not in model.model_dump_json()
