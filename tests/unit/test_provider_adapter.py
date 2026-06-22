"""Unit tests for provider adapter (Story 9.3).

Validates that provider adapters implement the base interface correctly,
the adapter factory works, configuration is loaded per provider, and
fallback behavior works when a provider is unavailable.

Following project rules #19/#20/#21 for test patterns.
"""

from collections.abc import Generator
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

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
    get_provider_benchmark,
)
from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.config import AppSettings
from ai_qa.db.base import Base
from ai_qa.db.models import User
from ai_qa.exceptions import ConfigError
from ai_qa.secrets import CANONICAL_SECRET_TYPES, resolve_secret_type


@pytest.fixture
def adapter_client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=cast(list[Table], [User.__table__]),
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db_session() -> Generator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db_session_dependency] = override_get_db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    engine.dispose()


# --- Base Interface Compliance ---


def test_provider_adapter_is_abstract() -> None:
    """ProviderAdapter cannot be instantiated directly (abstract)."""
    with pytest.raises(TypeError):
        ProviderAdapter()  # type: ignore[abstract]


def test_provider_adapter_has_required_class_variables() -> None:
    """All concrete adapters declare provider_id and provider_name."""
    adapters = [
        AnthropicAdapter,
        OpenAIAdapter,
        GeminiAdapter,
        OnPremisesAdapter,
        BrowserUseAdapter,
    ]
    for adapter_cls in adapters:
        assert hasattr(adapter_cls, "provider_id")
        assert hasattr(adapter_cls, "provider_name")
        assert isinstance(adapter_cls.provider_id, str)
        assert isinstance(adapter_cls.provider_name, str)
        assert len(adapter_cls.provider_id) > 0
        assert len(adapter_cls.provider_name) > 0


def test_provider_adapter_implements_validate_connection() -> None:
    """All concrete adapters implement validate_connection."""
    adapters = [
        AnthropicAdapter(),
        OpenAIAdapter(),
        GeminiAdapter(),
        OnPremisesAdapter(),
        BrowserUseAdapter(),
    ]
    for adapter in adapters:
        assert hasattr(adapter, "validate_connection")
        assert callable(adapter.validate_connection)


def test_provider_adapter_has_list_models_method() -> None:
    """All concrete adapters have list_models (may raise NotImplementedError)."""
    adapters = [
        AnthropicAdapter(),
        OpenAIAdapter(),
        GeminiAdapter(),
        OnPremisesAdapter(),
        BrowserUseAdapter(),
    ]
    for adapter in adapters:
        assert hasattr(adapter, "list_models")
        assert callable(adapter.list_models)


def test_connection_result_is_secret_free() -> None:
    """ConnectionResult contains no secret fields."""
    result = ConnectionResult(
        success=True,
        provider="claude",
        provider_name="Claude (Anthropic)",
        status="success",
        message="Connected",
        error_category="none",
    )
    result_dict = result.model_dump()
    assert "api_key" not in result_dict
    assert "secret" not in result_dict
    assert "password" not in result_dict
    assert "token" not in result_dict


def test_connection_result_status_literal() -> None:
    """ConnectionResult.status is restricted to 'success' or 'failed'."""
    success = ConnectionResult(
        success=True, provider="test", provider_name="Test", status="success", message="ok"
    )
    failed = ConnectionResult(
        success=False, provider="test", provider_name="Test", status="failed", message="bad"
    )
    assert success.status == "success"
    assert failed.status == "failed"


def test_discovered_model_has_required_fields() -> None:
    """DiscoveredModel has all required fields."""
    model = DiscoveredModel(
        id="claude-sonnet-4-6",
        display_name="Claude Sonnet 4.6",
        provider="claude",
    )
    assert model.id == "claude-sonnet-4-6"
    assert model.display_name == "Claude Sonnet 4.6"
    assert model.provider == "claude"
    assert model.context_window is None
    assert model.supports_tools is None


# --- Adapter Factory ---


def test_get_provider_adapter_returns_known_providers() -> None:
    """Factory returns correct adapter for each known provider id."""
    known_ids = ["claude", "claude-sso", "openai", "gemini", "on-premises", "browser-use-cloud"]
    for provider_id in known_ids:
        adapter = get_provider_adapter(provider_id)
        assert isinstance(adapter, ProviderAdapter)
        assert adapter.provider_id == provider_id


def test_claude_sso_adapter_resolves_to_anthropic_base_url() -> None:
    """claude-sso reuses the Anthropic Messages API surface and base URL."""
    from ai_qa.config import AppSettings

    adapter = get_provider_adapter("claude-sso")
    assert adapter.provider_id == "claude-sso"
    settings = AppSettings()
    assert "anthropic" in resolve_base_url(settings, "claude-sso")


def test_get_provider_adapter_raises_for_unknown() -> None:
    """Factory raises ConfigError for unknown provider ids."""
    with pytest.raises(ConfigError, match="Unknown provider id"):
        get_provider_adapter("nonexistent_provider")


def test_get_provider_adapter_raises_for_empty_string() -> None:
    """Factory raises ConfigError for empty provider id."""
    with pytest.raises(ConfigError, match="Unknown provider id"):
        get_provider_adapter("")


def test_get_provider_adapter_returns_same_instance() -> None:
    """Factory returns the same adapter instance (stateless pattern)."""
    adapter1 = get_provider_adapter("claude")
    adapter2 = get_provider_adapter("claude")
    assert adapter1 is adapter2


# --- Base URL Resolution ---


def test_resolve_base_url_returns_configured_urls() -> None:
    """resolve_base_url returns the correct base URL per provider."""
    settings = AppSettings()
    claude_url = resolve_base_url(settings, "claude")
    openai_url = resolve_base_url(settings, "openai")
    gemini_url = resolve_base_url(settings, "gemini")

    assert "anthropic" in claude_url
    assert "openai" in openai_url
    assert "googleapis" in gemini_url


def test_resolve_base_url_raises_for_unknown_provider() -> None:
    """resolve_base_url raises ConfigError for unknown provider."""
    settings = AppSettings()
    with pytest.raises(ConfigError, match="Unknown provider id"):
        resolve_base_url(settings, "nonexistent")


def test_resolve_base_url_on_premises() -> None:
    """resolve_base_url returns empty string for unconfigured on-premises."""
    settings = AppSettings()
    url = resolve_base_url(settings, "on-premises")
    # On-premises URL defaults to empty string
    assert isinstance(url, str)


# --- Provider Name Normalization ---


def test_provider_adapter_normalizes_provider_names() -> None:
    """Provider alias normalization maps to canonical secret types."""
    assert resolve_secret_type("claude") == "claude"
    assert resolve_secret_type("anthropic") == "claude"
    assert resolve_secret_type("openai") == "openai"
    assert resolve_secret_type("gemini") == "gemini"
    assert resolve_secret_type("google") == "gemini"
    assert resolve_secret_type("on_premises") == "on_premises"
    assert resolve_secret_type("on-premises") == "on_premises"
    assert resolve_secret_type("browser_use") == "browser_use"
    assert resolve_secret_type("browser-use-cloud") == "browser_use"
    assert resolve_secret_type("mcp") == "mcp"

    with pytest.raises(KeyError):
        resolve_secret_type("unknown_provider")


# --- Secret Format Validation ---


def test_validate_secret_format_rejects_empty() -> None:
    """Empty secret fails format validation."""
    from ai_qa.secrets.service import validate_secret_format

    with pytest.raises(ValueError, match="must not be empty"):
        validate_secret_format("claude", "")


def test_validate_secret_format_rejects_whitespace_only() -> None:
    """Whitespace-only secret fails format validation."""
    from ai_qa.secrets.service import validate_secret_format

    with pytest.raises(ValueError, match="must not be empty"):
        validate_secret_format("claude", "   ")


def test_validate_secret_format_rejects_too_short() -> None:
    """Short secret fails format validation."""
    from ai_qa.secrets.service import validate_secret_format

    with pytest.raises(ValueError, match="too short"):
        validate_secret_format("claude", "short")


def test_validate_secret_format_accepts_valid_key() -> None:
    """Valid-length secret passes format validation."""
    from ai_qa.secrets.service import validate_secret_format

    validate_secret_format("claude", "valid-api-key-12345678")


def test_validate_secret_format_works_across_all_providers() -> None:
    """Format validation works for all canonical secret types."""
    from ai_qa.secrets.service import validate_secret_format

    for secret_type in CANONICAL_SECRET_TYPES:
        validate_secret_format(secret_type, "valid-api-key-12345678")


# --- Connection Validation Behavior ---


@pytest.mark.asyncio
async def test_anthropic_adapter_rejects_short_key() -> None:
    """Anthropic adapter rejects short/empty API keys before network call."""
    adapter = AnthropicAdapter()
    result = await adapter.validate_connection(
        credentials={"api_key": "short"},
        base_url="https://api.anthropic.com",
    )
    assert result.success is False
    assert result.error_category == "auth"
    assert result.provider == "claude"
    assert "API key looks invalid" in result.message


@pytest.mark.asyncio
async def test_anthropic_adapter_rejects_empty_key() -> None:
    """Anthropic adapter rejects empty API key."""
    adapter = AnthropicAdapter()
    result = await adapter.validate_connection(
        credentials={"api_key": ""},
        base_url="https://api.anthropic.com",
    )
    assert result.success is False
    assert result.error_category == "auth"


@pytest.mark.asyncio
async def test_anthropic_adapter_rejects_missing_key() -> None:
    """Anthropic adapter rejects missing api_key in credentials."""
    adapter = AnthropicAdapter()
    result = await adapter.validate_connection(
        credentials={},
        base_url="https://api.anthropic.com",
    )
    assert result.success is False
    assert result.error_category == "auth"


@pytest.mark.asyncio
async def test_openai_adapter_rejects_short_key() -> None:
    """OpenAI adapter rejects short API key."""
    adapter = OpenAIAdapter()
    result = await adapter.validate_connection(
        credentials={"api_key": "abc"},
        base_url="https://api.openai.com",
    )
    assert result.success is False
    assert result.error_category == "auth"


@pytest.mark.asyncio
async def test_gemini_adapter_rejects_short_key() -> None:
    """Gemini adapter rejects short API key."""
    adapter = GeminiAdapter()
    result = await adapter.validate_connection(
        credentials={"api_key": "short"},
        base_url="https://generativelanguage.googleapis.com",
    )
    assert result.success is False
    assert result.error_category == "auth"


@pytest.mark.asyncio
async def test_on_premises_adapter_rejects_invalid_base_url() -> None:
    """On-Premises adapter rejects missing/invalid base URL."""
    adapter = OnPremisesAdapter()
    result = await adapter.validate_connection(
        credentials={"api_key": "valid-api-key-12345678"},
        base_url="",
    )
    assert result.success is False
    assert result.error_category == "config"
    assert "on-premises endpoint" in result.message.lower()


@pytest.mark.asyncio
async def test_on_premises_adapter_rejects_non_http_url() -> None:
    """On-Premises adapter rejects non-HTTP base URLs."""
    adapter = OnPremisesAdapter()
    result = await adapter.validate_connection(
        credentials={"api_key": "valid-api-key-12345678"},
        base_url="ftp://server.local",
    )
    assert result.success is False
    assert result.error_category == "config"


@pytest.mark.asyncio
@patch("httpx.AsyncClient.get")
async def test_browser_use_adapter_rejects_short_key(mock_get: MagicMock) -> None:
    """Browser Use adapter rejects a short API key at the format floor — no network.

    The key must be shorter than the 8-char format floor (``_MIN_API_KEY_LENGTH``)
    so it is rejected *before* any network probe, exactly like the Anthropic/
    OpenAI/Gemini sibling tests above. The former value ``"bu_short"`` was exactly
    8 chars, so it slipped past the ``len < 8`` floor and triggered a real call to
    ``api.browser-use.com`` — an order-dependent flake under pytest-randomly, where
    the live call's outcome varied and surfaced as ``unreachable``/``provider_error``
    instead of ``auth``. The ``assert_not_awaited`` below pins the test hermetic.
    """
    adapter = BrowserUseAdapter()
    result = await adapter.validate_connection(
        credentials={"api_key": "bu_key"},
        base_url="https://api.browser-use.com/api/v2",
    )
    assert result.success is False
    assert result.error_category == "auth"
    mock_get.assert_not_awaited()  # rejected at the format floor, before any probe


@pytest.mark.asyncio
async def test_adapter_rejects_invalid_base_url() -> None:
    """All adapters reject non-HTTP base URLs as config errors."""
    adapters = [
        AnthropicAdapter(),
        OpenAIAdapter(),
        GeminiAdapter(),
    ]
    for adapter in adapters:
        result = await adapter.validate_connection(
            credentials={"api_key": "valid-api-key-12345678"},
            base_url="not-a-url",
        )
        assert result.success is False
        assert result.error_category == "config"


# --- Provider Benchmark Hints ---


def test_get_provider_benchmark_returns_data_for_known_providers() -> None:
    """Known providers have benchmark metadata."""
    claude_benchmark = get_provider_benchmark("claude")
    assert claude_benchmark is not None
    assert "benchmark" in claude_benchmark
    assert "source_url" in claude_benchmark


def test_get_provider_benchmark_returns_none_for_unknown() -> None:
    """Unknown providers return None for benchmark."""
    result = get_provider_benchmark("nonexistent")
    assert result is None


def test_browser_use_benchmark_has_highest_accuracy() -> None:
    """Browser Use Cloud has the highest accuracy benchmark."""
    bu_benchmark = get_provider_benchmark("browser-use-cloud")
    assert bu_benchmark is not None
    assert bu_benchmark["accuracy_percent"] == 97


# --- Model Normalization ---


def test_openai_compatible_normalize_models_with_data_key() -> None:
    """OpenAI-compatible adapter normalizes 'data' array response."""
    adapter = OpenAIAdapter()
    body = {
        "data": [
            {"id": "gpt-4o", "name": "GPT-4o"},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
        ]
    }
    models = adapter._normalize_models(body)
    assert len(models) == 2
    assert models[0].id == "gpt-4o"
    assert models[0].provider == "openai"
    assert models[1].id == "gpt-4o-mini"


def test_openai_compatible_normalize_models_with_list() -> None:
    """OpenAI-compatible adapter normalizes plain list response."""
    adapter = OpenAIAdapter()
    body = [{"id": "model-1", "name": "Model 1"}]
    models = adapter._normalize_models(body)
    assert len(models) == 1
    assert models[0].id == "model-1"


def test_openai_compatible_normalize_models_with_ollama_shape() -> None:
    """OpenAI-compatible adapter normalizes Ollama 'models' response."""
    adapter = OpenAIAdapter()
    body = {"models": [{"name": "llama3", "id": "llama3"}]}
    models = adapter._normalize_models(body)
    assert len(models) == 1
    assert models[0].id == "llama3"


def test_openai_compatible_normalize_models_skips_invalid_entries() -> None:
    """Adapter skips entries without usable id."""
    adapter = OpenAIAdapter()
    body = {"data": [{"name": "valid-model"}, {}, {"id": "", "name": ""}]}
    models = adapter._normalize_models(body)
    assert len(models) == 1
    assert models[0].id == "valid-model"


def test_gemini_adapter_strips_models_prefix() -> None:
    """Gemini adapter strips 'models/' prefix from model ids."""
    adapter = GeminiAdapter()
    assert adapter._clean_model_id("models/gemini-1.5-pro") == "gemini-1.5-pro"
    assert adapter._clean_model_id("gemini-1.5-flash") == "gemini-1.5-flash"


def test_gemini_adapter_query_params_auth() -> None:
    """Gemini uses query parameter authentication, not headers."""
    adapter = GeminiAdapter()
    headers = adapter._build_headers("test-key")
    params = adapter._build_query_params("test-key")
    assert headers == {}
    assert params == {"key": "test-key"}


def test_anthropic_adapter_x_api_key_header() -> None:
    """Anthropic uses x-api-key header, not Bearer."""
    adapter = AnthropicAdapter()
    headers = adapter._build_headers("test-key")
    assert "x-api-key" in headers
    assert headers["x-api-key"] == "test-key"
    assert "anthropic-version" in headers


def test_browser_use_adapter_custom_header() -> None:
    """Browser Use uses custom X-Browser-Use-API-Key header."""
    adapter = BrowserUseAdapter()
    headers = adapter._build_headers("bu_test-key-12345678")
    assert "X-Browser-Use-API-Key" in headers
    assert headers["X-Browser-Use-API-Key"] == "bu_test-key-12345678"


def test_openai_adapter_bearer_auth() -> None:
    """OpenAI uses standard Bearer authentication."""
    adapter = OpenAIAdapter()
    headers = adapter._build_headers("test-key")
    assert headers == {"Authorization": "Bearer test-key"}


# --- Adapter Identity ---


def test_adapter_provider_ids_are_unique() -> None:
    """Each adapter has a unique provider_id."""
    adapters = [
        AnthropicAdapter(),
        OpenAIAdapter(),
        GeminiAdapter(),
        OnPremisesAdapter(),
        BrowserUseAdapter(),
    ]
    ids = [a.provider_id for a in adapters]
    assert len(ids) == len(set(ids))


def test_adapter_provider_names_are_unique() -> None:
    """Each adapter has a unique provider_name."""
    adapters = [
        AnthropicAdapter(),
        OpenAIAdapter(),
        GeminiAdapter(),
        OnPremisesAdapter(),
        BrowserUseAdapter(),
    ]
    names = [a.provider_name for a in adapters]
    assert len(names) == len(set(names))


def test_result_helper_builds_correct_connection_result() -> None:
    """_result helper stamps adapter identity onto ConnectionResult."""
    adapter = AnthropicAdapter()
    result = adapter._result(
        success=True,
        message="Connected",
        error_category="none",
    )
    assert result.provider == "claude"
    assert result.provider_name == "Claude (Anthropic)"
    assert result.status == "success"
    assert result.success is True

    failed = adapter._result(
        success=False,
        message="Failed",
        error_category="auth",
    )
    assert failed.status == "failed"
    assert failed.success is False
