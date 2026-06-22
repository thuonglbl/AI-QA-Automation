"""API tests for admin model benchmark-score + discovered-model endpoints."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ai_qa.db.models import DiscoveredModelSnapshot


class TestModelScores:
    def test_non_admin_forbidden(self, client: TestClient, user_token: str) -> None:
        response = client.get(
            "/api/admin/model-scores",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403

    def test_upsert_then_list(self, client: TestClient, admin_token: str) -> None:
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = client.put(
            "/api/admin/model-scores",
            json={
                "model_id": "inference-newmodel-9-700b",
                "capability": "coding",
                "score": 95,
                "note": "new SOTA",
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["model_id"] == "inference-newmodel-9-700b"
        assert data["capability"] == "coding"
        assert data["score"] == 95

        listed = client.get("/api/admin/model-scores", headers=headers).json()
        assert any(
            row["model_id"] == "inference-newmodel-9-700b" and row["score"] == 95 for row in listed
        )

    def test_upsert_replaces_not_duplicates(self, client: TestClient, admin_token: str) -> None:
        headers = {"Authorization": f"Bearer {admin_token}"}
        client.put(
            "/api/admin/model-scores",
            json={"model_id": "m1", "capability": "global", "score": 50},
            headers=headers,
        )
        client.put(
            "/api/admin/model-scores",
            json={"model_id": "m1", "capability": "global", "score": 80},
            headers=headers,
        )
        rows = [
            r
            for r in client.get("/api/admin/model-scores", headers=headers).json()
            if r["model_id"] == "m1"
        ]
        assert len(rows) == 1
        assert rows[0]["score"] == 80

    def test_float_score_round_trips(self, client: TestClient, admin_token: str) -> None:
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = client.put(
            "/api/admin/model-scores",
            json={"model_id": "inference-glm-51-754b", "capability": "coding", "score": 58.4},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["score"] == 58.4
        listed = client.get("/api/admin/model-scores", headers=headers).json()
        assert any(
            row["model_id"] == "inference-glm-51-754b" and row["score"] == 58.4 for row in listed
        )

    def test_score_out_of_range_rejected(self, client: TestClient, admin_token: str) -> None:
        response = client.put(
            "/api/admin/model-scores",
            json={"model_id": "m2", "score": 150},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422

    def test_delete_then_404(self, client: TestClient, admin_token: str) -> None:
        headers = {"Authorization": f"Bearer {admin_token}"}
        client.put(
            "/api/admin/model-scores",
            json={"model_id": "m3", "capability": "global", "score": 10},
            headers=headers,
        )
        first = client.request(
            "DELETE",
            "/api/admin/model-scores",
            json={"model_id": "m3", "capability": "global"},
            headers=headers,
        )
        assert first.status_code == 204
        second = client.request(
            "DELETE",
            "/api/admin/model-scores",
            json={"model_id": "m3", "capability": "global"},
            headers=headers,
        )
        assert second.status_code == 404


class TestDiscoveredModels:
    def test_lists_snapshots_with_provenance(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        now = datetime.now(UTC)
        db_session.add(
            DiscoveredModelSnapshot(
                model_id="inference-glm-51-754b",
                display_name="GLM 5.1",
                supports_vision=False,
                last_seen_at=now,
            )
        )
        db_session.add(
            DiscoveredModelSnapshot(
                model_id="inference-mysteryco-9-700b",
                display_name="Mystery",
                supports_vision=False,
                last_seen_at=now,
            )
        )
        db_session.commit()

        rows = client.get(
            "/api/admin/discovered-models",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        by_id = {row["model_id"]: row for row in rows}
        # A curated model is benchmarked; an unknown one is flagged.
        assert by_id["inference-glm-51-754b"]["tier_source"] == "curated"
        assert by_id["inference-glm-51-754b"]["unbenchmarked"] is False
        assert by_id["inference-mysteryco-9-700b"]["tier_source"] == "parsed"
        assert by_id["inference-mysteryco-9-700b"]["unbenchmarked"] is True

    def test_admin_score_marks_model_benchmarked(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        db_session.add(
            DiscoveredModelSnapshot(
                model_id="inference-mysteryco-9-700b",
                display_name="Mystery",
                supports_vision=False,
                last_seen_at=datetime.now(UTC),
            )
        )
        db_session.commit()
        headers = {"Authorization": f"Bearer {admin_token}"}
        client.put(
            "/api/admin/model-scores",
            json={"model_id": "inference-mysteryco-9-700b", "capability": "coding", "score": 90},
            headers=headers,
        )
        rows = client.get("/api/admin/discovered-models", headers=headers).json()
        row = next(r for r in rows if r["model_id"] == "inference-mysteryco-9-700b")
        assert row["tier_source"] == "admin"
        assert row["unbenchmarked"] is False
        assert len(row["scores"]) == 1
        assert row["scores"][0]["score"] == 90
