import httpx

from .config import AIServerConfig
from .exceptions import AIAuthError, AIConnectionError, AIRequestError, AITimeoutError


class AIClient:
    """HTTP/2 client for OpenAI-compatible LLM API (LiteLLM proxy)."""

    def __init__(self, config: AIServerConfig):
        self.config = config
        verify = config.ca_bundle if config.ca_bundle else config.verify_ssl
        self._client = httpx.Client(
            http1=not config.http2,
            http2=config.http2,
            verify=verify,
            timeout=httpx.Timeout(connect=10, read=config.timeout, write=30, pool=10),
            headers={
                "Authorization": f"Bearer {config.api_key}",
            },
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self._client.close()

    def health_check(self) -> bool:
        """GET /health — returns True if server responds with 2xx/3xx."""
        try:
            r = self._client.get(f"{self.config.base_url}/health")
            return r.status_code < 500
        except httpx.TransportError:
            return False

    def list_models(self) -> list[str]:
        """GET /v1/models — returns list of model ID strings."""
        r = self._request("GET", "/v1/models")
        data = self._parse_json(r)
        # Handle OpenAI format {"data": [{"id": ...}]} and flat list
        if isinstance(data, dict) and "data" in data:
            return [m["id"] for m in data["data"]]
        if isinstance(data, list):
            return [str(m) for m in data]
        return []

    def chat(self, messages: list[dict], **kwargs) -> dict:
        """POST /v1/chat/completions — returns parsed response dict.

        Extra kwargs (temperature, max_tokens, etc.) are passed to the API.
        """
        payload = {"model": self.config.model, "messages": messages, **kwargs}
        r = self._request("POST", "/v1/chat/completions", json=payload)
        return self._parse_json(r)

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self.config.base_url}{path}"
        try:
            r = self._client.request(method, url, **kwargs)
        except httpx.TimeoutException as e:
            raise AITimeoutError(
                f"Server did not respond within {self.config.timeout}s"
            ) from e
        except httpx.TransportError as e:
            raise AIConnectionError(
                f"Cannot reach server at {self.config.base_url}"
            ) from e

        if r.status_code in (401, 403):
            raise AIAuthError("Authentication failed — check API key")
        if r.status_code >= 400:
            raise AIRequestError(
                f"HTTP {r.status_code}: {r.text[:500]}"
            )
        return r

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict | list:
        try:
            return response.json()
        except (ValueError, UnicodeDecodeError) as e:
            raise AIRequestError(
                f"Invalid JSON response: {response.text[:200]}"
            ) from e
