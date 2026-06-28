"""Tests for build_browser_use_llm — provider id → browser_use.llm wrapper.

Verifies every Alice provider option maps to the right browser-use chat model
(reusing the thread's credential/base_url/model) so the live exploration can be
driven by whatever the thread configured. Construction is lazy (no network: the
wrappers build their HTTP/genai clients only on first call), so these tests stay
offline.
"""

import pytest

from ai_qa.browser.llm_factory import build_browser_use_llm
from ai_qa.exceptions import ConfigError


def test_claude_maps_to_anthropic() -> None:
    llm = build_browser_use_llm(
        "claude",
        api_key="sk-ant-test-123",
        model="claude-sonnet-4-6",
        base_url="https://api.anthropic.com",
    )
    assert type(llm).__name__ == "ChatAnthropic"
    assert llm.api_key == "sk-ant-test-123"
    assert llm.model == "claude-sonnet-4-6"


def test_claude_sso_also_maps_to_anthropic_with_default_base_url() -> None:
    # claude-sso authenticates via x-api-key too; the stored secret is the real
    # enterprise key behind SSO.
    llm = build_browser_use_llm("claude-sso", api_key="sk-ant-ent-456", model="claude-opus-4-8")
    assert type(llm).__name__ == "ChatAnthropic"
    assert llm.api_key == "sk-ant-ent-456"
    assert "anthropic" in str(llm.base_url)


def test_on_premises_maps_to_openai_with_insecure_client() -> None:
    llm = build_browser_use_llm(
        "on-premises",
        api_key="sk-onprem-789",
        model="deepseek-chat",
        base_url="https://ai.svc.corp.ch/api",
    )
    assert type(llm).__name__ == "ChatOpenAI"
    assert str(llm.base_url) == "https://ai.svc.corp.ch/api"
    # Self-signed cert tolerance for on-prem (mirrors client.py verify_ssl rule).
    assert llm.http_client is not None


def test_openai_maps_to_openai_without_custom_http_client() -> None:
    llm = build_browser_use_llm("openai", api_key="sk-openai-abc", model="gpt-5")
    assert type(llm).__name__ == "ChatOpenAI"
    assert llm.http_client is None


def test_gemini_maps_to_google() -> None:
    llm = build_browser_use_llm("gemini", api_key="g-key-xyz", model="gemini-2.5-pro")
    assert type(llm).__name__ == "ChatGoogle"
    assert llm.model == "gemini-2.5-pro"


def test_browser_use_cloud_maps_to_chatbrowseruse() -> None:
    llm = build_browser_use_llm("browser-use-cloud", api_key="bu_key_1", model="bu-2-0")
    assert type(llm).__name__ == "ChatBrowserUse"
    assert llm.model == "bu-2-0"


def test_browser_use_cloud_normalizes_non_bu_model() -> None:
    # A claude-* discovery placeholder is NOT a valid BU model → default to bu-2-0
    # instead of raising.
    llm = build_browser_use_llm("browser-use-cloud", api_key="bu_key_2", model="claude-sonnet-4.6")
    assert type(llm).__name__ == "ChatBrowserUse"
    assert llm.model == "bu-2-0"


def test_unknown_provider_raises() -> None:
    with pytest.raises(ConfigError, match="unknown provider"):
        build_browser_use_llm("not-a-provider", api_key="x-key-123", model="m")


def test_blank_api_key_raises() -> None:
    with pytest.raises(ConfigError, match="No credential"):
        build_browser_use_llm("claude", api_key="   ", model="claude-sonnet-4-6")
