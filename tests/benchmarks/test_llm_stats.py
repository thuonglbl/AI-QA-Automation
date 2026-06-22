"""Unit tests for the llm-stats.com client (catalog → match → detail scores + speed)."""

from types import SimpleNamespace
from typing import Any

import pytest

from ai_qa.benchmarks import llm_stats
from ai_qa.benchmarks.llm_stats import (
    aggregate_scores,
    build_name_index,
    fetch_benchmark_scores,
    match_llm_stats_id,
    normalize_model_name,
)

_CATALOG_IDS = [
    "glm-5",
    "glm-5.1",
    "glm-5.2",
    "claude-opus-4-8",
    "claude-haiku-4-5",
    "gpt-5-2025-08-07",
    "gpt-5.1-2025-11-13",
    "gpt-5.1-codex",
]


def test_normalize_model_name_strips_prefixes_and_separators() -> None:
    assert normalize_model_name("claude-sonnet-4-6") == "claudesonnet46"
    assert normalize_model_name("inference-glm-51-754b") == "glm51754b"
    assert normalize_model_name("GLM 5.1") == "glm51"
    assert normalize_model_name("models/gemini-2.5-pro") == "gemini25pro"


def test_match_resolves_onprem_size_suffix_to_base_version() -> None:
    index = build_name_index([{"id": mid} for mid in _CATALOG_IDS])
    assert match_llm_stats_id("inference-glm-51-754b", index) == "glm-5.1"
    assert match_llm_stats_id("glm-5", index) == "glm-5"
    assert match_llm_stats_id("claude-haiku-4-5-20251001", index) == "claude-haiku-4-5"
    assert match_llm_stats_id("claude-opus-4-8", index) == "claude-opus-4-8"
    assert match_llm_stats_id("gpt-5.1", index) == "gpt-5.1-2025-11-13"
    assert match_llm_stats_id("gpt-5", index) == "gpt-5-2025-08-07"
    assert match_llm_stats_id("totally-unknown-model", index) is None


def test_aggregate_scores_maps_categories_and_scales() -> None:
    entries = [
        {"category": "reasoning", "normalized_score": 0.8},
        {"category": "math", "normalized_score": 0.6},  # reasoning bucket
        {"category": "code", "normalized_score": 0.5},
        {"category": "code", "score": 30, "max_score": 100},  # -> 0.3, coding bucket
        {"category": "vision", "normalized_score": 0.9},
        {"category": "instruction_following", "normalized_score": 0.4},
        {"category": "creativity", "normalized_score": 0.2},  # unmapped: global only
    ]
    out = aggregate_scores(entries)
    assert out["reasoning"] == 70.0
    assert out["coding"] == 40.0
    assert out["vision"] == 90.0
    assert out["instruction"] == 40.0
    assert out["global"] == 52.9
    assert "fast" not in out


def test_aggregate_classifies_coding_by_name_even_under_agents_category() -> None:
    # GLM-5.1's coding benchmarks live under "agents" on llm-stats; name keyword wins.
    entries = [
        {"category": "agents", "benchmark_name": "SWE-Bench Pro", "normalized_score": 0.6},
        {"category": "agents", "benchmark_name": "FrontierSWE", "normalized_score": 0.4},
        {"category": "agents", "benchmark_name": "BrowseComp", "normalized_score": 0.8},
        {"category": "math", "benchmark_name": "AIME 2026", "normalized_score": 0.9},
    ]
    out = aggregate_scores(entries)
    assert out["coding"] == 50.0  # mean(0.6, 0.4)
    assert out["reasoning"] == 90.0
    assert out["global"] == 67.5


def test_aggregate_uses_rank_percentile_when_model_counts_given() -> None:
    # A top-3 finish on a hard benchmark (low raw score) must beat a rank-140 finish
    # on an easy one (high raw score). model_counts turn rank into a relative percentile.
    entries = [
        {
            "category": "agents",
            "benchmark_id": "swe-bench-pro",
            "benchmark_name": "SWE-Bench Pro",
            "rank": 2,
            "normalized_score": 0.30,  # low raw, but rank 2 of 10
        },
        {
            "category": "math",
            "benchmark_id": "aime-2026",
            "benchmark_name": "AIME 2026",
            "rank": 3,
            "normalized_score": 0.95,
        },
    ]
    counts = {"swebenchpro": 10, "aime2026": 17}
    out = aggregate_scores(entries, counts)
    assert out["coding"] == 90.0  # (10-2+1)/10
    assert out["reasoning"] == 88.2  # (17-3+1)/17
    assert out["global"] == 89.1  # mean of the two percentiles


@pytest.mark.asyncio
async def test_fetch_skipped_without_key() -> None:
    settings = SimpleNamespace(
        llm_stats_api_key="",
        llm_stats_api_base_url="https://api.llm-stats.com/stats/v1",
    )
    result = await fetch_benchmark_scores(["glm-5.1"], settings)  # type: ignore[arg-type]
    assert result.source_available is False
    assert result.scores_by_model == {}


# Leaderboard rankings: glm-5.1 + opus ranked (authoritative conservative_rating);
# glm-5.1 is NOT in "agents", and "weak-model" is in no ranking (forces the fallback).
_RANKINGS: dict[str, list[dict[str, Any]]] = {
    "general": [
        {"model_id": "glm-5.1", "conservative_rating": 43.7},
        {"model_id": "claude-opus-4-8", "conservative_rating": 61.3},
    ],
    "reasoning": [
        {"model_id": "glm-5.1", "conservative_rating": 50.4},
        {"model_id": "claude-opus-4-8", "conservative_rating": 63.1},
    ],
    "code": [
        {"model_id": "glm-5.1", "conservative_rating": 41.5},
        {"model_id": "claude-opus-4-8", "conservative_rating": 52.5},
    ],
    "agents": [{"model_id": "claude-opus-4-8", "conservative_rating": 44.1}],
    "vision": [{"model_id": "claude-opus-4-8", "conservative_rating": 47.1}],
}
_BENCHMARKS: dict[str, Any] = {
    "benchmarks": [
        {"id": "mcp-atlas", "model_count": 10},
        {"id": "gpqa", "model_count": 100},
    ]
}
_DETAIL: dict[str, dict[str, Any]] = {
    "glm-5.1": {
        "scores": [
            # agents->instruction by name; glm-5.1 is unranked in "agents" -> fallback.
            {
                "category": "agents",
                "benchmark_id": "mcp-atlas",
                "benchmark_name": "MCP Atlas",
                "rank": 3,
                "normalized_score": 0.7,
            }
        ],
        "providers": [{"throughput_tps": 30.0}],
    },
    "claude-opus-4-8": {
        "model": {"scores": [], "providers": [{"throughput_tps": 42.0}, {"throughput_tps": 48.0}]}
    },
    "weak-model": {
        "scores": [
            {"category": "reasoning", "benchmark_id": "gpqa", "rank": 5, "normalized_score": 0.8}
        ],
        "providers": [],
    },
}


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _RoutingClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> _RoutingClient:
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> _FakeResponse:
        assert headers and headers["Authorization"].startswith("Bearer ")
        if url.endswith("/rankings"):
            assert params is not None
            return _FakeResponse({"models": _RANKINGS.get(params["category"], [])})
        if url.endswith("/benchmarks"):
            return _FakeResponse(_BENCHMARKS)
        if url.endswith("/models"):  # catalog
            return _FakeResponse(
                {
                    "models": [{"id": "glm-5.1"}, {"id": "claude-opus-4-8"}, {"id": "weak-model"}],
                    "next_cursor": None,
                }
            )
        prefix = "/models/"
        model_id = url[url.index(prefix) + len(prefix) :]
        return _FakeResponse(_DETAIL.get(model_id, {"scores": []}))


@pytest.mark.asyncio
async def test_fetch_hybrid_leaderboard_then_scaled_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_stats.httpx, "AsyncClient", _RoutingClient)
    settings = SimpleNamespace(
        llm_stats_api_key="ze_test",
        llm_stats_api_base_url="https://api.llm-stats.com/stats/v1",
    )
    discovered = ["inference-glm-51-754b", "claude-opus-4-8", "weak-model"]
    result = await fetch_benchmark_scores(discovered, settings)  # type: ignore[arg-type]
    assert result.source_available is True

    glm = result.scores_by_model["inference-glm-51-754b"]
    # Ranked capabilities use the authoritative leaderboard conservative_rating.
    assert glm["global"] == 43.7
    assert glm["reasoning"] == 50.4
    assert glm["coding"] == 41.5
    # Unranked in "agents": MCP Atlas rank 3/10 -> pct 0.8, scaled by agents floor (44.1).
    assert glm["instruction"] == 35.3  # round(44.1 * 0.8, 1)
    assert glm["fast"] == 30.0

    opus = result.scores_by_model["claude-opus-4-8"]
    assert opus["global"] == 61.3
    assert opus["vision"] == 47.1
    assert opus["instruction"] == 44.1
    assert opus["fast"] == 48.0

    # weak-model is leaderboard-unranked everywhere -> scaled fallback, strictly below
    # the ranked glm-5.1 in the same capability.
    weak = result.scores_by_model["weak-model"]
    assert weak["reasoning"] == 48.4  # round(50.4 floor * 0.96, 1)
    assert weak["reasoning"] < glm["reasoning"]
    assert weak["global"] < glm["global"]


@pytest.mark.asyncio
async def test_fetch_returns_unavailable_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BoomClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _BoomClient:
            return self

        async def __aexit__(self, *args: Any) -> bool:
            return False

        async def get(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("network down")

    monkeypatch.setattr(llm_stats.httpx, "AsyncClient", _BoomClient)
    settings = SimpleNamespace(
        llm_stats_api_key="ze_test",
        llm_stats_api_base_url="https://api.llm-stats.com/stats/v1",
    )
    result = await fetch_benchmark_scores(["glm-5.1"], settings)  # type: ignore[arg-type]
    assert result.source_available is False
