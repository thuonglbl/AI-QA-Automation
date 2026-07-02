"""Admin "Sync models and benchmarks" orchestrator.

Two steps, driven by the admin dashboard button:

1. **Discover** — connect to each provider in turn using its server-side
   ``TEST_<PROVIDER>_KEY``, list its LLM models, drop non-generative families
   (embeddings / tts / stt / …) via the shared classifier, detect vision support, and
   upsert the survivors into ``discovered_models``.
2. **Benchmark** — fetch the llm-stats.com catalog once and, for each discovered model,
   overwrite its ``model_benchmark_scores`` rows with the matched 6-capability scores.

The whole run is best-effort: a provider that is unconfigured/unreachable, or a
benchmark source that is down, is recorded in the returned summary but never aborts the
sync. Secrets (the keys) are resolved at runtime and never placed in the summary or logs.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_qa.ai_connection.model_filter import is_non_generative_model
from ai_qa.ai_connection.providers import (
    DiscoveredModel,
    get_provider_adapter,
    resolve_base_url,
)
from ai_qa.benchmarks import fetch_benchmark_scores
from ai_qa.db.models import DiscoveredModelSnapshot, ModelBenchmarkScore

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ai_qa.config import AppSettings

logger = logging.getLogger(__name__)

# Provider sync order (per the feature request) -> AppSettings attribute holding its
# server-side discovery key. on-premises first, then the hosted providers.
_PROVIDER_KEY_ATTRS: list[tuple[str, str]] = [
    ("on-premises", "test_on_premises_key"),
    ("claude", "test_claude_key"),
    ("gemini", "test_gemini_key"),
    ("openai", "test_openai_key"),
    ("browser-use-cloud", "test_browser_use_key"),
]


class ProviderSyncResult(BaseModel):
    """Per-provider outcome of the discovery step (display-safe, secret-free)."""

    provider_id: str
    connected: bool
    skipped: bool
    models_found: int
    error: str | None = None


class ModelSyncResult(BaseModel):
    """Summary returned to the admin dashboard after a sync."""

    providers: list[ProviderSyncResult]
    models_discovered: int
    models_benchmarked: int
    models_unbenchmarked: int
    scores_written: int
    benchmark_source_available: bool
    warnings: list[str]


async def sync_models_and_benchmarks(
    db: Session,
    settings: AppSettings,
    *,
    triggered_by_user_id: UUID | None,
) -> ModelSyncResult:
    """Run discovery + benchmark sync, persisting both tables. Never raises."""
    now = datetime.now(UTC)
    provider_results: list[ProviderSyncResult] = []
    warnings: list[str] = []
    # Deduplicate across providers by model id (discovered_models is unique on model_id).
    unique_models: dict[str, DiscoveredModel] = {}

    for provider_id, key_attr in _PROVIDER_KEY_ATTRS:
        result = await _discover_provider(db, settings, provider_id, key_attr, now, unique_models)
        provider_results.append(result)

    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001 - persist what we can; report the rest
        db.rollback()
        warnings.append(f"Failed to persist discovered models: {type(exc).__name__}")
        logger.warning("Discovered-model commit failed: %s", type(exc).__name__)

    # --- Benchmark step ---
    bench = await fetch_benchmark_scores(list(unique_models), settings)
    benchmark_available = bench.source_available
    if not benchmark_available:
        warnings.append(
            "Benchmark source unavailable (no llm-stats key or fetch failed) — "
            "models were discovered but not scored."
        )

    benchmarked = 0
    unbenchmarked = 0
    scores_written = 0
    if benchmark_available:
        note = f"Synced from llm-stats.com on {now:%Y-%m-%d}"
        from ai_qa.agents.alice import _has_vision_signal

        for model_id, model in unique_models.items():
            scores = bench.scores_by_model.get(model_id)
            # A vision score only makes sense for vision-capable models. Drop it for
            # genuinely text-only models (e.g. GLM-5.1) so the score stays consistent with
            # the dashboard's "vision" tag. Use the UNION signal (advertised flag OR a
            # vision name signal) — the gateway flag alone is unreliable: it misses name-
            # obvious vision families (e.g. gemma, qwen-*-vl) whose score would otherwise
            # be wrongly dropped here.
            is_vision = _has_vision_signal(
                {"id": model_id, "supports_vision": model.supports_vision}
            )
            if scores and not is_vision:
                scores = {cap: val for cap, val in scores.items() if cap != "vision"}
            written = _overwrite_scores(db, model_id, scores, triggered_by_user_id, note)
            if written > 0:
                benchmarked += 1
                scores_written += written
            else:
                unbenchmarked += 1
        try:
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            warnings.append(f"Failed to persist benchmark scores: {type(exc).__name__}")
            logger.warning("Benchmark-score commit failed: %s", type(exc).__name__)
    else:
        unbenchmarked = len(unique_models)

    # --- Multi-Environment Sync Step ---
    if settings.sync_target_databases:
        from ai_qa.config import mask_database_url

        for target in settings.sync_target_databases:
            db_name = target.get("name", "unknown")
            db_url = target.get("url")
            if not db_url:
                continue
            try:
                engine = create_engine(db_url, pool_pre_ping=True)
                remote_session_factory = sessionmaker(bind=engine)
                with remote_session_factory() as remote_db:
                    # Sync discovered models
                    for dm in unique_models.values():
                        _upsert_discovered_model(remote_db, dm, now)
                    remote_db.commit()

                    # Sync benchmark scores
                    if benchmark_available:
                        for model_id, model in unique_models.items():
                            scores = bench.scores_by_model.get(model_id)
                            is_vision = _has_vision_signal(
                                {"id": model_id, "supports_vision": model.supports_vision}
                            )
                            if scores and not is_vision:
                                scores = {
                                    cap: val for cap, val in scores.items() if cap != "vision"
                                }
                            _overwrite_scores(remote_db, model_id, scores, None, note)
                        remote_db.commit()
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Failed to sync remote DB {db_name}: {type(exc).__name__}")
                logger.error(
                    "Failed to sync remote DB %s (%s): %s", db_name, mask_database_url(db_url), exc
                )
            finally:
                if "engine" in locals():
                    engine.dispose()

    return ModelSyncResult(
        providers=provider_results,
        models_discovered=len(unique_models),
        models_benchmarked=benchmarked,
        models_unbenchmarked=unbenchmarked,
        scores_written=scores_written,
        benchmark_source_available=benchmark_available,
        warnings=warnings,
    )


async def _discover_provider(
    db: Session,
    settings: AppSettings,
    provider_id: str,
    key_attr: str,
    now: datetime,
    unique_models: dict[str, DiscoveredModel],
) -> ProviderSyncResult:
    """Connect to one provider, list + filter its models, and upsert snapshots."""
    key = (getattr(settings, key_attr, "") or "").strip()
    base_url = resolve_base_url(settings, provider_id)

    if not key:
        return ProviderSyncResult(
            provider_id=provider_id,
            connected=False,
            skipped=True,
            models_found=0,
            error="No server key configured.",
        )
    if provider_id == "on-premises" and not base_url:
        return ProviderSyncResult(
            provider_id=provider_id,
            connected=False,
            skipped=True,
            models_found=0,
            error="On-premises base URL not configured.",
        )

    adapter = get_provider_adapter(provider_id)
    try:
        connection = await adapter.validate_connection({"api_key": key}, base_url)
    except Exception as exc:  # noqa: BLE001 - never leak the key/stack
        return ProviderSyncResult(
            provider_id=provider_id,
            connected=False,
            skipped=False,
            models_found=0,
            error=f"Connection error ({type(exc).__name__}).",
        )
    if not connection.success:
        return ProviderSyncResult(
            provider_id=provider_id,
            connected=False,
            skipped=False,
            models_found=0,
            error=connection.message,  # adapter contract: secret-free, actionable
        )

    try:
        discovered = await adapter.list_models({"api_key": key}, base_url)
    except Exception as exc:  # noqa: BLE001
        return ProviderSyncResult(
            provider_id=provider_id,
            connected=True,
            skipped=False,
            models_found=0,
            error=f"Model listing failed ({type(exc).__name__}).",
        )

    kept = [dm for dm in discovered if not is_non_generative_model(dm.id)]
    for dm in kept:
        dm.provider = provider_id
        _upsert_discovered_model(db, dm, now)
        unique_models.setdefault(dm.id, dm)

    return ProviderSyncResult(
        provider_id=provider_id,
        connected=True,
        skipped=False,
        models_found=len(kept),
        error=None,
    )


def _upsert_discovered_model(db: Session, dm: DiscoveredModel, now: datetime) -> None:
    """Insert or update the ``discovered_models`` snapshot for a model (last-seen)."""
    from sqlalchemy import select

    row = db.execute(
        select(DiscoveredModelSnapshot).where(DiscoveredModelSnapshot.model_id == dm.id)
    ).scalar_one_or_none()
    display_name = dm.display_name or dm.id

    # Hardcode override: GLM 4.5 Air does not support vision natively
    if "glm45-air" in dm.id.lower():
        dm.supports_vision = False

    if row is None:
        db.add(
            DiscoveredModelSnapshot(
                model_id=dm.id,
                display_name=display_name,
                supports_vision=dm.supports_vision,
                provider=dm.provider,
                last_seen_at=now,
            )
        )
    else:
        row.display_name = display_name
        row.supports_vision = dm.supports_vision
        row.provider = dm.provider
        row.last_seen_at = now


def _overwrite_scores(
    db: Session,
    model_id: str,
    scores: dict[str, float] | None,
    user_id: UUID | None,
    note: str,
) -> int:
    """Replace all benchmark scores for a model with the freshly-synced set.

    Per the agreed "overwrite all" policy, the model's existing rows (including any
    historical manual entries) are dropped first. Returns the number of rows written.
    """
    db.query(ModelBenchmarkScore).filter(ModelBenchmarkScore.model_id == model_id).delete(
        synchronize_session=False
    )
    if not scores:
        return 0
    written = 0
    for capability, score in scores.items():
        db.add(
            ModelBenchmarkScore(
                model_id=model_id,
                capability=capability,
                score=score,
                note=note,
                updated_by_user_id=user_id,
            )
        )
        written += 1
    return written
