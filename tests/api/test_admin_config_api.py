from fastapi.testclient import TestClient


def test_admin_config_returns_feature_flags(
    client: TestClient,
    admin_token: str,
) -> None:
    settings = client.fastapi_app.state.settings  # type: ignore[attr-defined]
    settings.enable_model_benchmark_sync = True
    response = client.get(
        "/api/admin/config",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["enable_model_benchmark_sync"] is True

    settings.enable_model_benchmark_sync = False
    response = client.get(
        "/api/admin/config",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["enable_model_benchmark_sync"] is False


def test_admin_config_requires_admin(
    client: TestClient,
    user_token: str,
) -> None:
    response = client.get(
        "/api/admin/config",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 403
