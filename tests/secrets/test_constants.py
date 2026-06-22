"""Tests for canonical secret-type constants and provider-alias resolution.

``resolve_secret_type`` / ``PROVIDER_SECRET_TYPE_MAP`` are the normalization
contract that every secret consumer (``agents/base.py`` provider names,
``agents/alice.py`` provider ids) depends on. These pure-logic tests pin every
alias → canonical mapping, the case/whitespace handling, and the unknown-alias
failure mode (AC1/AC2 storage contract).
"""

import pytest

from ai_qa.secrets import (
    PROVIDER_SECRET_TYPE_MAP,
    SECRET_TYPE_BROWSER_USE,
    SECRET_TYPE_CLAUDE,
    SECRET_TYPE_CLAUDE_SSO,
    SECRET_TYPE_GEMINI,
    SECRET_TYPE_MCP,
    SECRET_TYPE_ON_PREMISES,
    SECRET_TYPE_OPENAI,
    resolve_secret_type,
)

# Every provider alias used by current consumers and its expected canonical type.
_ALIAS_EXPECTATIONS = [
    ("claude", SECRET_TYPE_CLAUDE),
    ("anthropic", SECRET_TYPE_CLAUDE),
    ("claude-sso", SECRET_TYPE_CLAUDE_SSO),
    ("claude_sso", SECRET_TYPE_CLAUDE_SSO),
    ("openai", SECRET_TYPE_OPENAI),
    ("gemini", SECRET_TYPE_GEMINI),
    ("google", SECRET_TYPE_GEMINI),
    ("on_premises", SECRET_TYPE_ON_PREMISES),
    ("on-premises", SECRET_TYPE_ON_PREMISES),
    ("browser_use", SECRET_TYPE_BROWSER_USE),
    ("browser-use-cloud", SECRET_TYPE_BROWSER_USE),
    ("mcp", SECRET_TYPE_MCP),
]


class TestCanonicalConstants:
    def test_constant_values_are_stable(self) -> None:
        """Canonical secret_type strings must not drift (stored as DB metadata)."""
        assert SECRET_TYPE_CLAUDE == "claude"
        assert SECRET_TYPE_OPENAI == "openai"
        assert SECRET_TYPE_GEMINI == "gemini"
        assert SECRET_TYPE_BROWSER_USE == "browser_use"
        assert SECRET_TYPE_ON_PREMISES == "on_premises"
        assert SECRET_TYPE_MCP == "mcp"

    def test_all_canonical_types_are_reachable_via_map(self) -> None:
        """Every canonical type must be the target of at least one alias."""
        canonical = {
            SECRET_TYPE_CLAUDE,
            SECRET_TYPE_CLAUDE_SSO,
            SECRET_TYPE_OPENAI,
            SECRET_TYPE_GEMINI,
            SECRET_TYPE_BROWSER_USE,
            SECRET_TYPE_ON_PREMISES,
            SECRET_TYPE_MCP,
        }
        assert set(PROVIDER_SECRET_TYPE_MAP.values()) == canonical


class TestResolveSecretType:
    @pytest.mark.parametrize("alias, expected", _ALIAS_EXPECTATIONS)
    def test_known_alias_maps_to_canonical(self, alias: str, expected: str) -> None:
        assert resolve_secret_type(alias) == expected

    @pytest.mark.parametrize("alias, expected", _ALIAS_EXPECTATIONS)
    def test_map_entry_matches_resolver(self, alias: str, expected: str) -> None:
        """The lookup map and the resolver must agree for every alias."""
        assert PROVIDER_SECRET_TYPE_MAP[alias] == expected

    def test_uppercase_alias_is_normalized(self) -> None:
        assert resolve_secret_type("ANTHROPIC") == SECRET_TYPE_CLAUDE

    def test_surrounding_whitespace_is_stripped(self) -> None:
        assert resolve_secret_type("  Gemini  ") == SECRET_TYPE_GEMINI

    def test_combined_gemini_chatgpt_alias_removed(self) -> None:
        """Story 9.4 dropped the combined ``gemini-chatgpt`` id."""
        assert "gemini-chatgpt" not in PROVIDER_SECRET_TYPE_MAP
        with pytest.raises(KeyError):
            resolve_secret_type("gemini-chatgpt")

    def test_unknown_alias_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            resolve_secret_type("not-a-real-provider")
