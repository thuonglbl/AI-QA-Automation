# mypy: disable-error-code="misc"
import logging
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


def _build_chat_model(config: LLMConfig) -> BaseChatModel:
    """Build the appropriate LangChain chat model based on the provider id.

    - ``claude`` → ``ChatAnthropic`` (native Anthropic Messages API).
    - ``gemini`` → ``ChatGoogleGenerativeAI`` (native Generative Language API).
    - Everything else → ``ChatOpenAI`` (OpenAI-compatible: openai, on-premises,
      browser-use-cloud, litellm proxies).
    """
    import httpx

    verify_ssl = config.provider != "on-premises"

    if config.provider == "claude":
        from langchain_anthropic import ChatAnthropic

        kwargs: dict[str, Any] = {
            "model": config.model_name,
            "temperature": config.temperature,
            "api_key": SecretStr(config.api_key or ""),
            "base_url": config.base_url or "https://api.anthropic.com",
            "max_retries": 0,
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
            http_client=httpx.Client(verify=verify_ssl, follow_redirects=True),
            http_async_client=httpx.AsyncClient(verify=verify_ssl, follow_redirects=True),
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
        http_client=httpx.Client(verify=verify_ssl, follow_redirects=True),
        http_async_client=httpx.AsyncClient(verify=verify_ssl, follow_redirects=True),
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
        retry=retry_if_exception_type(LLMError) & retry_if_not_exception_type(LLMRateLimitError),
        reraise=True,
    )
    def _invoke_with_retry(self, messages: list[BaseMessage], **kwargs: Any) -> BaseMessage:
        """Invoke the chat model with tenacity retry logic."""
        try:
            return self._chat_model.invoke(messages, **kwargs)
        except Exception as e:
            # Catching generic Exception from LangChain and raising our custom exception.
            # E.g. langchain raise APITimeoutError -> we raise LLMTimeoutError
            err_msg = str(e).lower()
            if _is_rate_limit_or_quota(err_msg):
                # Rate limit / quota / billing — do NOT retry; surface verbatim.
                logger.error(f"LLM rate limit / quota error: {e}")
                raise LLMRateLimitError(f"LLM rate limit error: {e}") from e
            if "timeout" in err_msg:
                # Add a specific generic error type if needed
                logger.error(f"LLM Timeout error: {e}")
                raise LLMTimeoutError(f"LLM request timed out: {e}") from e
            elif "401" in err_msg or "auth" in err_msg:
                # Auth issues should not be retried - raise specific exception
                logger.error(f"LLM Authentication error: {e}")
                raise LLMAuthenticationError(f"LLM Authentication failed: {e}") from e
            else:
                logger.error(f"LLM Provider error: {e}")
                raise LLMError(f"LLM provider error: {e}") from e

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

        # We use aync invoke for vision
        response = await self._chat_model.ainvoke([message])
        return str(response.content)
