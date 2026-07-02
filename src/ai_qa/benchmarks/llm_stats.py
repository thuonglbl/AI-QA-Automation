"""llm-stats.com Data API client — per-model benchmark scores for the admin model sync.

Goal: give EVERY discovered model a comparable score across the app's capabilities,
including on-prem models that are not in the site's top-50 leaderboard.

Source of truth = the per-model detail endpoint ``GET /v1/models/{id}`` → its ``scores[]``
array, where each entry has a ``category`` and a 0–1 ``normalized_score`` (the real
benchmark result). We aggregate those into the app capabilities and scale to 0–100, plus
read throughput for ``fast``. Flow:

1. **Catalog** — paginate ``GET /v1/models`` (``next_cursor``) for the full model id list.
2. **Match** — map each discovered id to an llm-stats id (version-aware, prefix-tolerant),
   so ``inference-glm-51-754b`` → ``glm-5.1`` and ``claude-haiku-4-5-20251001`` → the base.
3. **Detail** — for each matched id, aggregate ``scores[].normalized_score`` by capability
   and read ``providers[].throughput_tps`` for ``fast``.

Why NOT the site's leaderboard columns (``/v1/rankings`` ``conservative_rating``): that is
a relative trueskill rating capped at the top 50 per category with no paging, so it cannot
score the full fleet (e.g. Llama-4 / Qwen3-VL aren't in any top-50). ``normalized_score``
covers all 321 catalog models on one consistent scale.

Mapping notes: ``global`` = mean of all a model's normalized scores; ``coding`` is matched
by benchmark NAME first (SWE/LiveCodeBench/…) because llm-stats files coding benchmarks
under mixed categories (e.g. GLM-5.1's SWE-Bench Pro sits under ``agents``). ``fast`` is a
raw tokens/sec figure, not a 0–100 quality score. Network/auth failures NEVER raise.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from statistics import mean
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from ai_qa.config import AppSettings

logger = logging.getLogger(__name__)

# The app's 6 capability names (mirror ai_qa.api.admin.__SKIP_WORD_2_Modcorppability__).
APP_CAPABILITIES: tuple[str, ...] = (
    "global",
    "reasoning",
    "vision",
    "instruction",
    "coding",
    "fast",
)

# llm-stats leaderboard category -> app capability (authoritative trueskill rating).
RANKING_CATEGORY_TO_CAPABILITY: dict[str, str] = {
    "general": "global",
    "reasoning": "reasoning",
    "code": "coding",
    "agents": "instruction",
    "vision": "vision",
}
_QUALITY_CAPABILITIES: tuple[str, ...] = ("global", "reasoning", "coding", "instruction", "vision")

# Benchmark-NAME keywords -> capability, checked BEFORE the category fallback (llm-stats
# files coding/SWE benchmarks under inconsistent categories). First hit wins.
_NAME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "coding": (
        "swe",
        "code",
        "livecode",
        "humaneval",
        "mbpp",
        "codeforces",
        "codecontest",
        "aider",
        "polyglot",
        "lancer",
        "repo",
        "terminal-bench",
        "terminalbench",
        "kotlin",
    ),
    "vision": (
        "mmmu",
        "docvqa",
        "chartqa",
        "charxiv",
        "screenspot",
        "mathvista",
        "ai2d",
        "vqa",
        "mmbench",
        "blink",
        "realworldqa",
        "video",
        "ocr",
        "vision",
        "multimodal",
    ),
    "instruction": (
        "ifeval",
        "ifbench",
        "instruction",
        "collie",
        "function",
        "tool",
        "mcp atlas",
    ),
    "reasoning": (
        "gpqa",
        "supergpqa",
        "mmlu",
        "aime",
        "hmmt",
        "imo",
        "math",
        "humanity",
        "hle",
        "bbh",
        "gsm",
        "drop",
        "arc-",
        "scibench",
    ),
}

# llm-stats ``scores[].category`` -> capability (FALLBACK when no name keyword hits).
CATEGORY_TO_CAPABILITY: dict[str, str] = {
    "reasoning": "reasoning",
    "math": "reasoning",
    "physics": "reasoning",
    "chemistry": "reasoning",
    "biology": "reasoning",
    "spatial_reasoning": "reasoning",
    "spatial": "reasoning",
    "factuality": "reasoning",
    "code": "coding",
    "coding": "coding",
    "frontend_development": "coding",
    "instruction_following": "instruction",
    "tool_calling": "instruction",
    "structured_output": "instruction",
    "vision": "vision",
    "multimodal": "vision",
    "image_to_text": "vision",
    "document_understanding": "vision",
    "video": "vision",
}

_PAGE_LIMIT = 100
_MAX_PAGES = 20
_DETAIL_CONCURRENCY = 8
_HTTP_TIMEOUT = 30.0


def normalize_model_name(name: str) -> str:
    """Collapse a model id/name to a comparable key (lowercase, alphanumerics only)."""
    low = name.strip().lower()
    for prefix in ("inference-", "models/", "model-"):
        if low.startswith(prefix):
            low = low[len(prefix) :]
    return re.sub(r"[^a-z0-9]", "", low)


@dataclass
class BenchmarkResult:
    """Outcome of the benchmark step: per-discovered-model scores + source health."""

    source_available: bool = False
    scores_by_model: dict[str, dict[str, float]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pure helpers (no I/O) — unit tested directly.
# ---------------------------------------------------------------------------


def build_name_index(catalog: list[dict[str, Any]]) -> dict[str, str]:
    """Map ``normalized(model id) -> model id`` for matching."""
    index: dict[str, str] = {}
    for entry in catalog:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id") or entry.get("model_id")
        if isinstance(model_id, str) and model_id.strip():
            index.setdefault(normalize_model_name(model_id), model_id)
    return index


def match_llm_stats_id(discovered_id: str, name_index: dict[str, str]) -> str | None:
    """Resolve a discovered model id to an llm-stats id (exact, else version-aware prefix)."""
    norm = normalize_model_name(discovered_id)
    if not norm:
        return None
    exact = name_index.get(norm)
    if exact is not None:
        return exact
    best_id: str | None = None
    best_rank: tuple[int, int, int] | None = None
    for key, model_id in name_index.items():
        if len(key) < 4:
            continue
        if norm.startswith(key):
            lcp, longer = len(key), norm
        elif key.startswith(norm):
            lcp, longer = len(norm), key
        else:
            continue
        suffix = longer[lcp:]
        rank = (lcp, 1 if suffix.isdigit() else 0, -len(suffix))
        if best_rank is None or rank > best_rank:
            best_rank, best_id = rank, model_id
    return best_id


def _classify(entry: dict[str, Any]) -> str | None:
    """Map one benchmark entry to a capability (name keywords first, then category)."""
    name = str(entry.get("benchmark_name") or entry.get("benchmark_id") or "").lower()
    for capability, keywords in _NAME_KEYWORDS.items():
        if any(keyword in name for keyword in keywords):
            return capability
    return CATEGORY_TO_CAPABILITY.get(str(entry.get("category", "")).lower())


def _bench_key(value: Any) -> str:
    """Normalize a benchmark id/name for matching against the model-count map."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _raw_value(entry: dict[str, Any]) -> float | None:
    """A benchmark entry's RAW score on a 0–1 scale (prefer ``normalized_score``)."""
    value = entry.get("normalized_score")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raw = entry.get("score")
        ceiling = entry.get("max_score")
        if (
            isinstance(raw, (int, float))
            and not isinstance(raw, bool)
            and isinstance(ceiling, (int, float))
            and ceiling
        ):
            value = raw / ceiling
        else:
            return None
    return max(0.0, min(1.0, float(value)))


def _relative_value(entry: dict[str, Any], model_counts: dict[str, int]) -> float | None:
    """A benchmark entry's RELATIVE standing on a 0–1 scale.

    Uses the model's ``rank`` on that benchmark vs the benchmark's total ``model_count``:
    ``(model_count - rank + 1) / model_count`` (rank 1 → ~1.0). This is comparable across
    models even when they were evaluated on different/harder benchmark sets — a top-3 finish
    on a hard frontier benchmark beats a rank-140 finish on an easy one, which raw
    ``normalized_score`` averaging gets backwards. Falls back to the raw score when rank or
    model_count is unavailable.
    """
    rank = entry.get("rank")
    if isinstance(rank, int) and not isinstance(rank, bool) and rank >= 1:
        key = _bench_key(entry.get("benchmark_id") or entry.get("benchmark_name") or "")
        count = model_counts.get(key)
        if isinstance(count, int) and count > 0:
            return max(0.0, min(1.0, (count - rank + 1) / count))
    return _raw_value(entry)


def aggregate_scores(
    score_entries: list[dict[str, Any]], model_counts: dict[str, int] | None = None
) -> dict[str, float]:
    """Aggregate a model's ``scores[]`` into ``{capability: 0-100}`` (excludes ``fast``).

    Each benchmark contributes its rank-percentile (relative standing) when ``model_counts``
    is supplied, else its raw normalized score.
    """
    counts = model_counts or {}
    buckets: dict[str, list[float]] = {}
    everything: list[float] = []
    for entry in score_entries:
        if not isinstance(entry, dict):
            continue
        value = _relative_value(entry, counts)
        if value is None:
            continue
        everything.append(value)
        capability = _classify(entry)
        if capability:
            buckets.setdefault(capability, []).append(value)

    out: dict[str, float] = {}
    if everything:
        out["global"] = round(mean(everything) * 100, 1)
    for capability, values in buckets.items():
        out[capability] = round(mean(values) * 100, 1)
    return out


def _extract_throughput(detail: dict[str, Any]) -> float | None:
    """Max ``throughput_tps`` across a model's inference providers (tokens/sec), else None."""
    providers = detail.get("providers")
    if not isinstance(providers, list):
        return None
    values = [
        float(p["throughput_tps"])
        for p in providers
        if isinstance(p, dict)
        and isinstance(p.get("throughput_tps"), (int, float))
        and not isinstance(p.get("throughput_tps"), bool)
    ]
    return max(values) if values else None


def _extract_catalog(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
    """Unwrap the model list + next cursor from a ``/v1/models`` page."""
    if isinstance(payload, list):
        return [m for m in payload if isinstance(m, dict)], None
    if isinstance(payload, dict):
        for key in ("models", "data", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                cursor = payload.get("next_cursor")
                return (
                    [m for m in value if isinstance(m, dict)],
                    cursor if isinstance(cursor, str) and cursor else None,
                )
    return [], None


# ---------------------------------------------------------------------------
# Network — best-effort, never raises.
# ---------------------------------------------------------------------------


async def _fetch_catalog(
    client: httpx.AsyncClient, base_url: str, headers: dict[str, str]
) -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(_MAX_PAGES):
        params: dict[str, Any] = {"limit": _PAGE_LIMIT}
        if cursor:
            params["cursor"] = cursor
        response = await client.get(f"{base_url}/models", headers=headers, params=params)
        response.raise_for_status()
        batch, cursor = _extract_catalog(response.json())
        models.extend(batch)
        if not cursor or not batch:
            break
    return models


async def _fetch_benchmark_counts(
    client: httpx.AsyncClient, base_url: str, headers: dict[str, str]
) -> dict[str, int]:
    """Map ``benchmark key -> model_count`` from the paginated ``/v1/benchmarks`` list."""
    counts: dict[str, int] = {}
    cursor: str | None = None
    for _ in range(_MAX_PAGES):
        params: dict[str, Any] = {"limit": _PAGE_LIMIT}
        if cursor:
            params["cursor"] = cursor
        try:
            response = await client.get(f"{base_url}/benchmarks", headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - degrade to raw scores
            logger.warning("llm-stats benchmarks fetch failed: %s", type(exc).__name__)
            break
        batch = payload.get("benchmarks") if isinstance(payload, dict) else payload
        if not isinstance(batch, list):
            break
        for entry in batch:
            if isinstance(entry, dict):
                bid = entry.get("id")
                model_count = entry.get("model_count")
                if isinstance(bid, str) and isinstance(model_count, int):
                    counts[_bench_key(bid)] = model_count
        cursor = payload.get("next_cursor") if isinstance(payload, dict) else None
        if not cursor or not batch:
            break
    return counts


async def _fetch_ranking(
    client: httpx.AsyncClient, base_url: str, headers: dict[str, str], category: str
) -> list[dict[str, Any]]:
    try:
        response = await client.get(
            f"{base_url}/rankings", headers=headers, params={"category": category, "limit": 50}
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - skip this category
        logger.warning("llm-stats ranking fetch failed for %s: %s", category, type(exc).__name__)
        return []
    models = payload.get("models") if isinstance(payload, dict) else payload
    return [m for m in models if isinstance(m, dict)] if isinstance(models, list) else []


async def _fetch_model_detail(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict[str, str],
    model_id: str,
    semaphore: asyncio.Semaphore,
    model_counts: dict[str, int],
) -> tuple[str, dict[str, float], float | None]:
    """Return (model_id, rank-percentile quality caps, throughput_tps)."""
    async with semaphore:
        try:
            response = await client.get(f"{base_url}/models/{model_id}", headers=headers)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm-stats detail fetch failed for %s: %s", model_id, type(exc).__name__)
            return model_id, {}, None
    detail = payload.get("model", payload) if isinstance(payload, dict) else {}
    if not isinstance(detail, dict):
        return model_id, {}, None
    scores = detail.get("scores")
    caps = aggregate_scores(scores, model_counts) if isinstance(scores, list) else {}
    return model_id, caps, _extract_throughput(detail)


async def fetch_benchmark_scores(
    discovered_ids: list[str], settings: AppSettings
) -> BenchmarkResult:
    """Resolve per-capability benchmark scores for the given discovered ids. Never raises."""
    api_key = (settings.llm_stats_api_key or "").strip()
    base_url = (settings.llm_stats_api_base_url or "").strip().rstrip("/")
    if not api_key or not base_url:
        logger.info("llm-stats sync skipped: API key or base URL not configured.")
        return BenchmarkResult()

    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    categories = list(RANKING_CATEGORY_TO_CAPABILITY.items())
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            catalog = await _fetch_catalog(client, base_url, headers)
            if not catalog:
                return BenchmarkResult(source_available=False)
            name_index = build_name_index(catalog)
            matched: dict[str, str] = {}
            for discovered_id in discovered_ids:
                llm_id = match_llm_stats_id(discovered_id, name_index)
                if llm_id:
                    matched[discovered_id] = llm_id

            # AUTHORITATIVE: leaderboard conservative_rating per capability (trueskill,
            # top-50). cap_ratings[capability][llm_id] = rating; floor = lowest ranked.
            ranking_lists = await asyncio.gather(
                *(_fetch_ranking(client, base_url, headers, cat) for cat, _ in categories)
            )
            cap_ratings: dict[str, dict[str, float]] = {}
            for (_cat, capability), models in zip(categories, ranking_lists, strict=True):
                rated: dict[str, float] = {}
                for model in models:
                    mid = model.get("model_id")
                    rating = model.get("conservative_rating")
                    if (
                        isinstance(mid, str)
                        and isinstance(rating, (int, float))
                        and not isinstance(rating, bool)
                    ):
                        rated[mid] = round(float(rating), 1)
                cap_ratings[capability] = rated
            cap_floor = {cap: (min(r.values()) if r else 0.0) for cap, r in cap_ratings.items()}

            # FALLBACK: per-benchmark model counts -> rank-percentile from detail, used
            # only for models the leaderboard hasn't ranked in a capability.
            model_counts = await _fetch_benchmark_counts(client, base_url, headers)
            semaphore = asyncio.Semaphore(_DETAIL_CONCURRENCY)
            unique_ids = sorted(set(matched.values()))
            detail_triples = await asyncio.gather(
                *(
                    _fetch_model_detail(client, base_url, headers, llm_id, semaphore, model_counts)
                    for llm_id in unique_ids
                )
            )
    except Exception as exc:  # noqa: BLE001 - catalog/transport failure
        logger.warning("llm-stats fetch failed: %s", type(exc).__name__)
        return BenchmarkResult(source_available=False)

    detail_by_id = {llm_id: (caps, tps) for llm_id, caps, tps in detail_triples}
    scores_by_model: dict[str, dict[str, float]] = {}
    for discovered_id, llm_id in matched.items():
        detail_caps, tps = detail_by_id.get(llm_id, ({}, None))
        final: dict[str, float] = {}
        for capability in _QUALITY_CAPABILITIES:
            rating = cap_ratings.get(capability, {}).get(llm_id)
            if rating is not None:
                final[capability] = rating  # leaderboard-ranked: authoritative
            elif capability in detail_caps:
                # Unranked: scale rank-percentile below the ranked tier's floor so any
                # leaderboard model outranks any unranked one in this capability.
                final[capability] = round(
                    cap_floor.get(capability, 0.0) * detail_caps[capability] / 100, 1
                )
        if tps is not None:
            final["fast"] = round(tps, 1)
        if final:
            scores_by_model[discovered_id] = final

    logger.info(
        "llm-stats: %d catalog, %d matched, %d scored.",
        len(catalog),
        len(matched),
        len(scores_by_model),
    )
    return BenchmarkResult(source_available=True, scores_by_model=scores_by_model)
