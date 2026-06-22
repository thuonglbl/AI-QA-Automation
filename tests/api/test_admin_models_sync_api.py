"""API tests for the admin "Sync models and benchmarks" endpoint."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

import ai_qa.api.admin as admin_module
from ai_qa.admin.model_sync import ModelSyncResult, ProviderSyncResult


def _canned_result() -> ModelSyncResult:
    return ModelSyncResult(
        providers=[
            ProviderSyncResult(
                provider_id="on-premises",
                connected=True,
                skipped=False,
                models_found=2,
                error=None,
            ),
            ProviderSyncResult(
                provider_id="claude",
                connected=False,
                skipped=True,
                models_found=0,
                error="No server key configured.",
            ),
        ],
        models_discovered=2,
        models_benchmarked=1,
        models_unbenchmarked=1,
        scores_written=3,
        benchmark_source_available=True,
        warnings=[],
    )


def test_sync_requires_admin(client: TestClient, user_token: str) -> None:
    resp = client.post(
        "/api/admin/models/sync",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403


def test_sync_rejects_anonymous(client: TestClient) -> None:
    resp = client.post("/api/admin/models/sync")
    assert resp.status_code in (401, 403)


def test_sync_returns_summary(
    client: TestClient, admin_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_sync(db: Any, settings: Any, *, triggered_by_user_id: Any) -> ModelSyncResult:
        return _canned_result()

    # The endpoint calls the symbol bound in the ai_qa.api.admin namespace.
    monkeypatch.setattr(admin_module, "sync_models_and_benchmarks", fake_sync)

    resp = client.post(
        "/api/admin/models/sync",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["models_discovered"] == 2
    assert data["models_benchmarked"] == 1
    assert data["models_unbenchmarked"] == 1
    assert data["scores_written"] == 3
    assert data["benchmark_source_available"] is True

    providers = {p["provider_id"]: p for p in data["providers"]}
    assert providers["on-premises"]["connected"] is True
    assert providers["on-premises"]["models_found"] == 2
    assert providers["claude"]["skipped"] is True
