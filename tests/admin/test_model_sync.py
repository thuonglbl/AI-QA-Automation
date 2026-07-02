"""Unit tests for the admin "Sync models and benchmarks" orchestrator."""

from collections.abc import Generator
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.admin import model_sync
from ai_qa.admin.model_sync import sync_models_and_benchmarks
from ai_qa.benchmarks import BenchmarkResult
from ai_qa.db.base import Base
from ai_qa.db.models import DiscoveredModelSnapshot, ModelBenchmarkScore


@pytest.fixture
def db_session() -> Generator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _model(
    model_id: str, *, vision: bool | None = None, name: str | None = None
) -> SimpleNamespace:
    return SimpleNamespace(id=model_id, display_name=name or model_id, supports_vision=vision)


class _FakeAdapter:
    def __init__(
        self, *, success: bool = True, message: str = "ok", models: list[Any] | None = None
    ) -> None:
        self._success = success
        self._message = message
        self._models = models or []

    async def validate_connection(self, creds: Any, base_url: str) -> SimpleNamespace:
        return SimpleNamespace(success=self._success, message=self._message)

    async def list_models(self, creds: Any, base_url: str) -> list[Any]:
        return list(self._models)


def _settings(**overrides: Any) -> SimpleNamespace:
    base: dict[str, Any] = dict(
        test_on_premises_key="",
        test_claude_key="",
        test_gemini_key="",
        test_openai_key="",
        test_browser_use_key="",
        on_premises_api_base_url="https://onprem.example/api",
        claude_api_base_url="https://api.anthropic.com",
        gemini_api_base_url="https://gemini.example",
        openai_api_base_url="https://api.openai.com",
        browser_use_cloud_url="https://browseruse.example",
        llm_stats_api_key="",
        llm_stats_api_base_url="https://api.llm-stats.com/stats/v1",
        sync_target_databases=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _patch(
    monkeypatch: pytest.MonkeyPatch, adapters: dict[str, Any], bench: BenchmarkResult
) -> None:
    monkeypatch.setattr(model_sync, "get_provider_adapter", lambda pid: adapters[pid])

    async def fake_fetch(_ids: Any, _settings: Any) -> BenchmarkResult:
        return bench

    monkeypatch.setattr(model_sync, "fetch_benchmark_scores", fake_fetch)


@pytest.mark.asyncio
async def test_sync_discovers_filters_and_benchmarks(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapters = {
        "on-premises": _FakeAdapter(
            models=[
                _model("glm-6", vision=False),
                _model("qwen3.5"),
                _model("inference-bge-m3"),  # embedding -> filtered out
            ]
        ),
        "claude": _FakeAdapter(models=[_model("claude-sonnet-4-6", vision=True)]),
    }
    bench = BenchmarkResult(
        source_available=True,
        scores_by_model={
            "glm-6": {"global": 80.0, "coding": 75.0},
            "claude-sonnet-4-6": {"global": 90.0, "vision": 85.0},
            # qwen3.5 intentionally absent -> unbenchmarked
        },
    )
    _patch(monkeypatch, adapters, bench)

    settings = _settings(test_on_premises_key="op-key", test_claude_key="cl-key")
    result = await sync_models_and_benchmarks(db_session, settings, triggered_by_user_id=None)  # type: ignore[arg-type]

    # Totals: bge embedding filtered; glm-6 + claude benchmarked, qwen3.5 not.
    assert result.models_discovered == 3
    assert result.models_benchmarked == 2
    assert result.models_unbenchmarked == 1
    assert result.scores_written == 4
    assert result.benchmark_source_available is True
    assert result.warnings == []

    by_provider = {p.provider_id: p for p in result.providers}
    assert by_provider["on-premises"].connected is True
    assert by_provider["on-premises"].models_found == 2  # bge dropped
    assert by_provider["claude"].connected is True
    assert by_provider["claude"].models_found == 1
    # Providers without a server key are skipped (not failed).
    for pid in ("gemini", "openai", "browser-use-cloud"):
        assert by_provider[pid].skipped is True
        assert by_provider[pid].connected is False

    # discovered_models holds the chat models only (embedding excluded).
    discovered = {
        row.model_id: row for row in db_session.execute(select(DiscoveredModelSnapshot)).scalars()
    }
    assert set(discovered) == {"glm-6", "qwen3.5", "claude-sonnet-4-6"}
    assert discovered["claude-sonnet-4-6"].supports_vision is True

    # model_benchmark_scores reflect the synced scores.
    scores = list(db_session.execute(select(ModelBenchmarkScore)).scalars())
    glm_caps = {s.capability: s.score for s in scores if s.model_id == "glm-6"}
    assert glm_caps == {"global": 80.0, "coding": 75.0}
    assert all("llm-stats" in (s.note or "") for s in scores)


@pytest.mark.asyncio
async def test_sync_drops_vision_for_non_vision_models(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A text-only model (supports_vision None/False) must not carry a vision score,
    # even if the benchmark source returned one; a vision-capable model keeps it.
    # Vision is decided by the UNION (advertised flag OR vision name signal), so a
    # name-obvious vision model (e.g. gemma) keeps its score even with the flag off.
    adapters = {
        "on-premises": _FakeAdapter(
            models=[
                _model("glm-6", vision=None),
                _model("pixel-vlm", vision=True),
                _model("inference-gemma4-31b", vision=False),
            ]
        )
    }
    bench = BenchmarkResult(
        source_available=True,
        scores_by_model={
            "glm-6": {"global": 80.0, "vision": 40.0},
            "pixel-vlm": {"global": 70.0, "vision": 60.0},
            "inference-gemma4-31b": {"global": 29.4, "vision": 80.0},
        },
    )
    _patch(monkeypatch, adapters, bench)

    settings = _settings(test_on_premises_key="op-key")
    await sync_models_and_benchmarks(db_session, settings, triggered_by_user_id=None)  # type: ignore[arg-type]

    by_model: dict[str, dict[str, float]] = {}
    for row in db_session.execute(select(ModelBenchmarkScore)).scalars():
        by_model.setdefault(row.model_id, {})[row.capability] = row.score
    assert "vision" not in by_model["glm-6"]  # text-only -> vision dropped
    assert by_model["glm-6"]["global"] == 80.0
    assert by_model["pixel-vlm"]["vision"] == 60.0  # advertised vision -> kept
    # gemma's flag is off, but the name signal keeps its vision score (the dashboard bug).
    assert by_model["inference-gemma4-31b"]["vision"] == 80.0


@pytest.mark.asyncio
async def test_sync_overwrites_existing_scores(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A prior manual score must be replaced ("overwrite all" policy).
    db_session.add(
        ModelBenchmarkScore(
            model_id="glm-6", capability="global", score=10.0, note="manual override"
        )
    )
    db_session.commit()

    adapters = {"on-premises": _FakeAdapter(models=[_model("glm-6")])}
    bench = BenchmarkResult(source_available=True, scores_by_model={"glm-6": {"global": 80.0}})
    _patch(monkeypatch, adapters, bench)

    settings = _settings(test_on_premises_key="op-key")
    await sync_models_and_benchmarks(db_session, settings, triggered_by_user_id=None)  # type: ignore[arg-type]

    rows = [s for s in db_session.execute(select(ModelBenchmarkScore)).scalars()]
    assert len(rows) == 1
    assert rows[0].score == 80.0
    assert "manual override" not in (rows[0].note or "")


@pytest.mark.asyncio
async def test_sync_records_connection_failure(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapters = {"on-premises": _FakeAdapter(success=False, message="Invalid credentials.")}
    _patch(monkeypatch, adapters, BenchmarkResult())

    settings = _settings(test_on_premises_key="bad-key")
    result = await sync_models_and_benchmarks(db_session, settings, triggered_by_user_id=None)  # type: ignore[arg-type]

    op = next(p for p in result.providers if p.provider_id == "on-premises")
    assert op.connected is False
    assert op.skipped is False
    assert op.error == "Invalid credentials."
    assert result.models_discovered == 0
    assert db_session.execute(select(DiscoveredModelSnapshot)).first() is None


@pytest.mark.asyncio
async def test_sync_skips_on_premises_without_base_url(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, {}, BenchmarkResult())
    settings = _settings(test_on_premises_key="op-key", on_premises_api_base_url="")

    result = await sync_models_and_benchmarks(db_session, settings, triggered_by_user_id=None)  # type: ignore[arg-type]

    op = next(p for p in result.providers if p.provider_id == "on-premises")
    assert op.skipped is True
    assert op.connected is False


@pytest.mark.asyncio
async def test_sync_without_benchmark_source(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapters = {"on-premises": _FakeAdapter(models=[_model("glm-6")])}
    _patch(monkeypatch, adapters, BenchmarkResult())  # source unavailable

    settings = _settings(test_on_premises_key="op-key")
    result = await sync_models_and_benchmarks(db_session, settings, triggered_by_user_id=None)  # type: ignore[arg-type]

    assert result.models_discovered == 1
    assert result.models_benchmarked == 0
    assert result.models_unbenchmarked == 1
    assert result.benchmark_source_available is False
    assert any("Benchmark source unavailable" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_sync_to_remote_databases(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    remote1_path = tmp_path / "remote1.db"
    remote_engine_1 = create_engine(f"sqlite+pysqlite:///{remote1_path}")
    Base.metadata.create_all(remote_engine_1)

    remote2_path = tmp_path / "remote2.db"
    remote_engine_2 = create_engine(f"sqlite+pysqlite:///{remote2_path}")
    Base.metadata.create_all(remote_engine_2)

    def fake_create_engine(url: str, **kwargs: Any) -> Any:
        if "remote1" in url:
            return create_engine(f"sqlite+pysqlite:///{remote1_path}", **kwargs)
        elif "remote2" in url:
            return create_engine(f"sqlite+pysqlite:///{remote2_path}", **kwargs)
        # A failing engine to test fault tolerance
        raise ValueError("Simulated connection failure")

    monkeypatch.setattr(model_sync, "create_engine", fake_create_engine)

    settings = _settings(
        test_on_premises_key="op-key",
        sync_target_databases=[
            {"name": "remote1", "url": "sqlite+pysqlite:///remote1"},
            {"name": "failing_remote", "url": "sqlite+pysqlite:///failing"},
            {"name": "remote2", "url": "sqlite+pysqlite:///remote2"},
        ],
    )

    adapters = {"on-premises": _FakeAdapter(models=[_model("glm-6")])}
    bench = BenchmarkResult(source_available=True, scores_by_model={"glm-6": {"global": 80.0}})
    _patch(monkeypatch, adapters, bench)

    result = await sync_models_and_benchmarks(db_session, settings, triggered_by_user_id=None)  # type: ignore[arg-type]

    # Verify primary DB got updated
    assert result.models_discovered == 1

    # Check that warning was recorded for failing_remote
    assert any("failing_remote" in w for w in result.warnings)

    # Verify remote DBs
    remote_session_1 = sessionmaker(bind=remote_engine_1)
    with remote_session_1() as rs1:
        remote1_models = [m for m in rs1.execute(select(DiscoveredModelSnapshot)).scalars()]
        assert len(remote1_models) == 1
        remote1_scores = [s for s in rs1.execute(select(ModelBenchmarkScore)).scalars()]
        assert len(remote1_scores) == 1

    remote_session_2 = sessionmaker(bind=remote_engine_2)
    with remote_session_2() as rs2:
        remote2_models = [m for m in rs2.execute(select(DiscoveredModelSnapshot)).scalars()]
        assert len(remote2_models) == 1
        remote2_scores = [s for s in rs2.execute(select(ModelBenchmarkScore)).scalars()]
        assert len(remote2_scores) == 1
