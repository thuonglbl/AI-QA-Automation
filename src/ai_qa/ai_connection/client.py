import logging
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ai_qa.ai_connection.config import LLMConfig
from ai_qa.exceptions import LLMAuthenticationError, LLMError, LLMTimeoutError

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Abstraction layer for LLMs using LangChain ChatModel and LiteLLM proxy.
    """

    def __init__(self, config: LLMConfig):
        self._config = config

        # Configure ChatOpenAI to talk to LiteLLM Proxy or direct provider
        # Uses max_retries=0 internally as we handle retries via tenacity.
        self._chat_model = ChatOpenAI(
            model=self._config.model_name,
            temperature=self._config.temperature,
            api_key=SecretStr(self._config.api_key or "sk-dummy"),  # Some proxies need a dummy key
            base_url=self._config.base_url if self._config.base_url else None,
            max_retries=0,
        )

    @retry(  # type: ignore
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(LLMError),
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
