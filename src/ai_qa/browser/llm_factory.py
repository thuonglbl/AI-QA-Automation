"""Build a browser-use LLM from the thread's configured provider.

browser-use's ``Agent`` is driven by ANY chat model implementing its
``browser_use.llm.BaseChatModel`` protocol — it does NOT require the paid
Browser Use Cloud key. To make EVERY provider option Alice can configure
(On-Premises, Claude, Claude SSO, Gemini, OpenAI, Browser Use Cloud) able to
drive the live exploration, we map the canonical provider id to the matching
``browser_use.llm`` wrapper and reuse the SAME resolved credential / base URL /
model the rest of the pipeline already uses (see ``agents.base.get_llm_config``
and ``ai_connection.client._build_chat_model`` — this is their browser-use
analog).

Credential reality (see design doc): Claude / Claude SSO require a real
``sk-ant-api…`` key (the SSO login alone never yields one); On-Premises is free
via the company gateway. Vision is left to the model — browser-use auto-disables
it only for DeepSeek.
"""

import logging
from typing import Any

import httpx

from ai_qa.exceptions import ConfigError

logger = logging.getLogger(__name__)

# Default Anthropic base URL when none is configured for a Claude provider.
_DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"


def build_browser_use_llm(
    provider_id: str,
    *,
    api_key: str,
    model: str,
    base_url: str = "",
    temperature: float = 0.0,
) -> Any:
    """Return a ``browser_use.llm`` chat model for a canonical provider id.

    Args:
        provider_id: Canonical Alice provider id (``on-premises``, ``claude``,
            ``claude-sso``, ``gemini``, ``openai``, ``browser-use-cloud``).
        api_key: The credential resolved for the thread (per-user secret or
            server-side enterprise key). Required.
        model: Model id the thread/Alice assigned to drive the browser.
        base_url: Config-owned base URL (empty = provider default).
        temperature: Sampling temperature (low for stable automation).

    Returns:
        A ``browser_use.llm.BaseChatModel`` instance (untyped — browser-use ships
        no stubs).

    Raises:
        ConfigError: Unknown provider id, or a missing credential (secret-free
            message).
    """
    if not isinstance(api_key, str) or not api_key.strip():
        raise ConfigError(
            f"No credential available to drive browser-use for provider {provider_id!r}."
        )
    key = api_key.strip()
    pid = provider_id.strip().lower()

    # Anthropic (Claude API key + Claude SSO both authenticate via x-api-key).
    if pid in ("claude", "claude-sso"):
        from browser_use.llm import ChatAnthropic

        return ChatAnthropic(
            model=model,
            api_key=key,
            base_url=base_url or _DEFAULT_ANTHROPIC_BASE_URL,
            temperature=temperature,
        )

    # Google Gemini (native genai client — api_key only, no base_url).
    if pid == "gemini":
        from browser_use.llm import ChatGoogle

        return ChatGoogle(model=model, api_key=key, temperature=temperature)

    # Browser Use Cloud (optional paid/free-tier proprietary inference). Its
    # model ids are BU-specific (bu-2-0, browser-use/…); the thread's assigned
    # model is often a discovery placeholder (e.g. claude-*), so fall back to the
    # default BU model when it isn't a valid BU id.
    if pid == "browser-use-cloud":
        from browser_use.llm import ChatBrowserUse

        bu_model = (
            model
            if (model in ("bu-latest", "bu-1-0", "bu-2-0") or model.startswith("browser-use/"))
            else "bu-2-0"
        )
        return ChatBrowserUse(model=bu_model, api_key=key)

    # OpenAI + On-Premises (OpenAI-compatible). On-prem tolerates self-signed
    # certs (mirrors ai_connection.client.verify_ssl rule).
    if pid in ("openai", "on-premises"):
        from browser_use.llm import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": model,
            "api_key": key,
            "temperature": temperature,
        }
        if base_url:
            kwargs["base_url"] = base_url
        if pid == "on-premises":
            kwargs["http_client"] = httpx.AsyncClient(verify=False, follow_redirects=True)
        return ChatOpenAI(**kwargs)

    raise ConfigError(f"Cannot drive browser-use for unknown provider id: {provider_id!r}")


__all__ = ["build_browser_use_llm"]
