# mypy: disable-error-code="misc"
import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from tenacity import (
    retry,
    retry_if_exception_type,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ai_qa.ai_connection.config import LLMConfig
from ai_qa.exceptions import (
    LLMAuthenticationError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)

# Substrings that identify a rate-limit / quota / billing rejection. These do
# not recover on a short retry, so they fail fast and are surfaced verbatim.
_RATE_LIMIT_MARKERS = (
    "429",
    "rate limit",
    "rate_limit",
    "ratelimit",
    "quota",
    "insufficient_quota",
    "resource_exhausted",
    "resource exhausted",
    "credit balance",
    "billing",
    "too low",
)


def _is_rate_limit_or_quota(message: str) -> bool:
    """True when a provider error message indicates rate limit / quota / billing."""
    lowered = message.lower()
    return any(marker in lowered for marker in _RATE_LIMIT_MARKERS)


def _map_provider_exception(e: Exception) -> LLMError:
    """Translate a raw LangChain/provider exception into our typed LLMError family."""
    err_msg = str(e).lower()
    if _is_rate_limit_or_quota(err_msg):
        logger.error(f"LLM rate limit / quota error: {e}")
        return LLMRateLimitError(f"LLM rate limit error: {e}")
    if "timeout" in err_msg or "timed out" in err_msg:
        logger.error(f"LLM Timeout error: {e}")
        return LLMTimeoutError(f"LLM request timed out: {e}")
    if "401" in err_msg or "auth" in err_msg:
        logger.error(f"LLM Authentication error: {e}")
        return LLMAuthenticationError(f"LLM Authentication failed: {e}")
    logger.error(f"LLM Provider error: {e}")
    return LLMError(f"LLM provider error: {e}")


def _build_chat_model(config: LLMConfig) -> BaseChatModel:
    """Build the appropriate LangChain chat model based on the provider id.

    - ``claude`` → ``ChatAnthropic`` (native Anthropic Messages API).
    - ``gemini`` → ``ChatGoogleGenerativeAI`` (native Generative Language API).
    - Everything else → ``ChatOpenAI`` (OpenAI-compatible: openai, on-premises,
      browser-use-cloud, litellm proxies).
    """
    import httpx

    verify_ssl = config.provider != "on-premises"
    # Bound every request so a slow/stalled provider can never hang forever (a sync
    # invoke would otherwise freeze the event loop indefinitely). Generous read budget
    # for slow on-premises models; short connect budget to fail fast on a dead host.
    timeout = httpx.Timeout(config.timeout, connect=15.0)

    # ``claude-sso`` is Claude reached via the enterprise SSO login: the api_key
    # here is the token obtained from the OAuth flow (or the enterprise key in
    # mock/demo mode), and it authenticates the Anthropic Messages API exactly
    # like the api-key path.
    if config.provider in ("claude", "claude-sso"):
        from langchain_anthropic import ChatAnthropic

        kwargs: dict[str, Any] = {
            "model": config.model_name,
            "temperature": config.temperature,
            "api_key": SecretStr(config.api_key or ""),
            "base_url": config.base_url or "https://api.anthropic.com",
            "max_retries": 0,
            "timeout": config.timeout,
        }
        return ChatAnthropic(**kwargs)

    if config.provider == "gemini":
        # Use ChatOpenAI pointed at the Gemini OpenAI-compatible endpoint
        # which Google exposes at generativelanguage.googleapis.com/v1beta/openai
        base = (config.base_url or "https://generativelanguage.googleapis.com").rstrip("/")
        gemini_openai_url = f"{base}/v1beta/openai"
        return ChatOpenAI(
            model=config.model_name,
            temperature=config.temperature,
            api_key=SecretStr(config.api_key or ""),
            base_url=gemini_openai_url,
            max_retries=0,
            timeout=config.timeout,
            http_client=httpx.Client(verify=verify_ssl, follow_redirects=True, timeout=timeout),
            http_async_client=httpx.AsyncClient(
                verify=verify_ssl, follow_redirects=True, timeout=timeout
            ),
        )

    # Default: OpenAI-compatible (openai, on-premises, browser-use-cloud, etc.)
    base_url = config.base_url or None
    if config.provider == "openai" and base_url:
        # The OpenAI chat completions API lives under /v1; the configured base URL
        # (openai_api_base_url) is the bare host, so ensure the /v1 suffix is present
        # to avoid a 404 on POST {host}/chat/completions.
        normalized = base_url.rstrip("/")
        if not normalized.endswith("/v1") and "/v1/" not in normalized:
            normalized = f"{normalized}/v1"
        base_url = normalized
    return ChatOpenAI(
        model=config.model_name,
        temperature=config.temperature,
        api_key=SecretStr(config.api_key or "sk-dummy"),
        base_url=base_url,
        max_retries=0,
        timeout=config.timeout,
        http_client=httpx.Client(verify=verify_ssl, follow_redirects=True, timeout=timeout),
        http_async_client=httpx.AsyncClient(
            verify=verify_ssl, follow_redirects=True, timeout=timeout
        ),
    )


class LLMClient:
    """
    Abstraction layer for LLMs using LangChain ChatModel and LiteLLM proxy.
    """

    def __init__(self, config: LLMConfig):
        self._config = config
        self._chat_model = _build_chat_model(config)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        # Rate-limit/quota and auth errors are deterministic — they will not recover on a
        # short retry, so fail fast instead of burning backoff sleeps.
        retry=retry_if_exception_type(LLMError)
        & retry_if_not_exception_type((LLMRateLimitError, LLMAuthenticationError)),
        reraise=True,
    )
    def _invoke_with_retry(self, messages: list[BaseMessage], **kwargs: Any) -> BaseMessage:
        """Invoke the chat model with tenacity retry logic."""
        try:
            return self._chat_model.invoke(messages, **kwargs)
        except Exception as e:
            # Translate raw LangChain/provider errors into our typed LLMError family.
            raise _map_provider_exception(e) from e

    def invoke(self, messages: list[BaseMessage], **kwargs: Any) -> BaseMessage:
        """
        Call the configured LLM with the provided messages.

        Args:
            messages: List of LangChain messages.
            kwargs: Additional kwargs to pass to the ChatModel.

        Returns:
            A LangChain BaseMessage response.

        Raises:
            LLMError: If the call fails after maximum retries.
        """
        return self._invoke_with_retry(messages, **kwargs)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        # Do NOT retry timeouts (a slow provider that already burned the generous
        # per-request timeout won't recover on a short retry, and 3× a long timeout would
        # compound into minutes of dead air), nor rate-limit/auth errors (deterministic).
        retry=retry_if_exception_type(LLMError)
        & retry_if_not_exception_type((LLMRateLimitError, LLMTimeoutError, LLMAuthenticationError)),
        reraise=True,
    )
    async def _ainvoke_with_retry(self, messages: list[BaseMessage], **kwargs: Any) -> BaseMessage:
        """Async-invoke the chat model with tenacity retry logic."""
        try:
            return await self._chat_model.ainvoke(messages, **kwargs)
        except Exception as e:
            raise _map_provider_exception(e) from e

    async def ainvoke(self, messages: list[BaseMessage], **kwargs: Any) -> BaseMessage:
        """Async variant of :meth:`invoke`.

        Prefer this inside ``async`` code (e.g. pipeline agents): a synchronous
        ``invoke`` blocks the event loop for the whole call, which for a slow
        on-premises model (generation can take minutes) freezes WebSocket heartbeats
        and every other request. ``ainvoke`` yields during the network wait so the
        server stays responsive.
        """
        return await self._ainvoke_with_retry(messages, **kwargs)

    async def astream(
        self, messages: list[BaseMessage], **kwargs: Any
    ) -> AsyncIterator[BaseMessage]:
        """Stream the model response chunk-by-chunk (async, non-blocking).

        Used to deliver long generations incrementally — e.g. Mary surfaces and saves
        each test case the moment it finishes streaming, instead of waiting minutes for
        one opaque response. Not retried: a stream cannot be safely resumed mid-flight,
        so a connection/provider error is mapped to our typed family and raised; the
        caller decides whether to fall back to a non-streaming call.
        """
        try:
            async for chunk in self._chat_model.astream(messages, **kwargs):
                yield chunk
        except Exception as e:
            raise _map_provider_exception(e) from e

    async def invoke_vision(
        self, prompt: str, image_base64: str, mime_type: str = "image/png"
    ) -> str:
        """Send image + text prompt to a vision-capable LLM.

        Returns text response. Raises if model doesn't support vision.
        """
        from langchain_core.messages import HumanMessage

        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{image_base64}"},
                },
            ]
        )

        # Async invoke for vision, bounded by a hard wall-clock timeout so a hung/stalled
        # provider can't stall the caller indefinitely (the per-chunk httpx read timeout
        # may never fire). Mirrors the convert/clarify timeout guards.
        try:
            response = await asyncio.wait_for(
                self._chat_model.ainvoke([message]), timeout=self._config.timeout
            )
        except TimeoutError as exc:
            raise LLMTimeoutError("Vision request timed out") from exc
        return str(response.content)
