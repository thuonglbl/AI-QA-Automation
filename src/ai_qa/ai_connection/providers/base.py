"""Provider adapter interface and normalized result models (Story 9.3).

This module defines the seam between Alice (the caller) and the concrete
provider validation/model-discovery adapters that live alongside it in
``ai_connection/providers/``.

Scope (Story 9.3): the interface + a real ``validate_connection`` per provider.
``list_models`` is intentionally a ``NotImplementedError`` stub — Story 9.4 owns
dynamic model discovery and ``DiscoveredModel`` population/normalization.

Contract invariants:
  - ``ConnectionResult`` carries ONLY non-secret data: no api_key, no raw
    provider response body, no stack trace (AC2).
  - Base URLs are config-owned (passed in by the caller from ``AppSettings``);
    credentials are passed in by the caller (sourced from per-user encrypted
    secret storage). The adapter layer never reads secrets or decrypts (AC3).
"""

import abc
from collections.abc import Mapping
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

# error_category values:
#   "none"          -> success
#   "auth"          -> bad/short/rejected key (401/403)
#   "unreachable"   -> connect/timeout/DNS failure
#   "provider_error"-> other non-2xx / malformed response
#   "config"        -> missing/invalid base URL (e.g. empty on-prem URL)
ErrorCategory = Literal["auth", "unreachable", "provider_error", "config", "none"]

# Typed default so the Pydantic field default is an ``ErrorCategory`` (Literal),
# not a bare ``str`` — keeps both mypy (no redundant cast) and Pyrefly happy.
_DEFAULT_ERROR_CATEGORY: ErrorCategory = "none"


class ConnectionResult(BaseModel):
    """Normalized, non-secret result of a provider connection validation.

    Every field is safe to surface to the user / log. The ``message`` is the
    only user-facing text and MUST be actionable, secret-free, and
    stack-trace-free (AC2).
    """

    success: bool = Field(description="True if the connection validated successfully")
    provider: str = Field(description="Canonical provider id (e.g. 'claude')")
    provider_name: str = Field(description="Human-readable provider label")
    status: Literal["success", "failed"] = Field(description="Normalized status")
    message: str = Field(
        description="Actionable, secret-free, stack-trace-free guidance for the user"
    )
    error_category: ErrorCategory = Field(
        default=_DEFAULT_ERROR_CATEGORY, description="Machine-readable failure category"
    )

    model_config = ConfigDict(validate_assignment=True)


class DiscoveredModel(BaseModel):
    """A model advertised by a provider.

    Defined here because the ``ProviderAdapter.list_models`` signature
    references it. Story 9.4 owns populating and normalizing these fields from
    live provider responses; for Story 9.3 it is a contract placeholder only.
    """

    id: str = Field(description="Provider model id")
    display_name: str = Field(description="Human-readable model name")
    provider: str = Field(description="Canonical provider id")
    capability_hints: list[str] | None = Field(default=None)
    context_window: int | None = Field(default=None)
    supports_tools: bool | None = Field(default=None)
    supports_vision: bool | None = Field(default=None)
    cost_tier: str | None = Field(default=None)
    latency_tier: str | None = Field(default=None)
    quota_status: Literal["available", "exceeded", "unknown"] | None = Field(
        default="unknown", description="Status of the quota for this model."
    )

    model_config = ConfigDict(validate_assignment=True)


class ProviderAdapter(abc.ABC):
    """Contract every provider adapter implements.

    Subclasses declare their identity via the ``provider_id`` / ``provider_name``
    class variables and implement ``validate_connection``. ``list_models`` is a
    concrete stub that raises ``NotImplementedError`` — Story 9.4 plugs dynamic
    discovery in here (the single, intentional extension point).
    """

    provider_id: ClassVar[str]
    provider_name: ClassVar[str]

    @abc.abstractmethod
    async def validate_connection(
        self, credentials: Mapping[str, str], base_url: str
    ) -> ConnectionResult:
        """Validate auth + reachability for this provider.

        Args:
            credentials: Caller-supplied credentials (e.g. ``{"api_key": ...}``);
                sourced from per-user encrypted secret storage by the caller.
            base_url: Config-owned base URL from ``AppSettings``.

        Returns:
            A normalized, non-secret ``ConnectionResult``.
        """

    async def list_models(
        self, credentials: Mapping[str, str], base_url: str
    ) -> list[DiscoveredModel]:
        """Discover available models for this provider.

        Implemented by concrete adapters (Story 9.4). The default raises so a new
        adapter that forgets to implement discovery fails loudly rather than
        silently returning no models.
        """
        raise NotImplementedError(f"{type(self).__name__} does not implement model discovery")

    # -- helpers -----------------------------------------------------------
    def _result(
        self,
        *,
        success: bool,
        message: str,
        error_category: ErrorCategory,
    ) -> ConnectionResult:
        """Build a ``ConnectionResult`` stamped with this adapter's identity."""
        return ConnectionResult(
            success=success,
            provider=self.provider_id,
            provider_name=self.provider_name,
            status="success" if success else "failed",
            message=message,
            error_category=error_category,
        )
