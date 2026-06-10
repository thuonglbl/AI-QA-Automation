"""Per-user encrypted secret storage (Epic 9 foundation).

This package owns the storage backing for per-user AI provider / MCP secrets:
a dedicated ``user_secrets`` table that separates encrypted secret values from
non-secret metadata, plus a thin accessor service.

Canonical ``secret_type`` constants and a provider-alias mapping live here so
every consumer normalizes to one key per provider regardless of the alias used
in ``agents/base.py`` (provider names) or ``agents/alice.py`` (provider ids).
"""

# Canonical secret type identifiers (one per provider / integration).
SECRET_TYPE_CLAUDE = "claude"
SECRET_TYPE_OPENAI = "openai"
SECRET_TYPE_GEMINI = "gemini"
SECRET_TYPE_BROWSER_USE = "browser_use"
SECRET_TYPE_ON_PREMISES = "on_premises"
SECRET_TYPE_MCP = "mcp"

# Ordered tuple of every canonical secret type. Consumers iterate this to
# represent "missing" providers too (e.g. the status endpoint in Story 9.2)
# and validate that an incoming ``secret_type`` is one of the canonical keys.
CANONICAL_SECRET_TYPES: tuple[str, ...] = (
    SECRET_TYPE_CLAUDE,
    SECRET_TYPE_OPENAI,
    SECRET_TYPE_GEMINI,
    SECRET_TYPE_BROWSER_USE,
    SECRET_TYPE_ON_PREMISES,
    SECRET_TYPE_MCP,
)

# Maps every provider alias used by current consumers to a canonical secret_type.
#   - base.py provider names: claude/anthropic, openai, gemini/google, on_premises
#   - alice.py provider ids:  claude, gemini, openai, on-premises, browser-use-cloud
PROVIDER_SECRET_TYPE_MAP: dict[str, str] = {
    # Claude / Anthropic
    "claude": SECRET_TYPE_CLAUDE,
    "anthropic": SECRET_TYPE_CLAUDE,
    # OpenAI
    "openai": SECRET_TYPE_OPENAI,
    # Gemini / Google
    "gemini": SECRET_TYPE_GEMINI,
    "google": SECRET_TYPE_GEMINI,
    # On-premises
    "on_premises": SECRET_TYPE_ON_PREMISES,
    "on-premises": SECRET_TYPE_ON_PREMISES,
    # Browser Use Cloud
    "browser_use": SECRET_TYPE_BROWSER_USE,
    "browser-use-cloud": SECRET_TYPE_BROWSER_USE,
    # MCP integration
    "mcp": SECRET_TYPE_MCP,
}


def resolve_secret_type(provider: str) -> str:
    """Normalize a provider name/id alias to its canonical ``secret_type``.

    Args:
        provider: Provider alias (e.g. ``"anthropic"``, ``"gemini"``).

    Returns:
        Canonical secret type (e.g. ``"claude"``, ``"gemini"``).

    Raises:
        KeyError: If the provider alias is unknown.
    """
    return PROVIDER_SECRET_TYPE_MAP[provider.strip().lower()]


__all__ = [
    "SECRET_TYPE_CLAUDE",
    "SECRET_TYPE_OPENAI",
    "SECRET_TYPE_GEMINI",
    "SECRET_TYPE_BROWSER_USE",
    "SECRET_TYPE_ON_PREMISES",
    "SECRET_TYPE_MCP",
    "CANONICAL_SECRET_TYPES",
    "PROVIDER_SECRET_TYPE_MAP",
    "resolve_secret_type",
]
