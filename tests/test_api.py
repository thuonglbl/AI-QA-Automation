"""Tests for FastAPI REST endpoints.

Validates that all pipeline action endpoints return correct responses
and that request validation works properly.
"""

import pytest
from fastapi.testclient import TestClient

from ai_qa.api.app import create_app


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client with default settings."""
    app = create_app()
    return TestClient(app)


# --- Health Check ---


class TestHealthCheck:
    """Tests for /api/health endpoint."""

    def test_health_check_returns_healthy(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"


# --- Start Endpoint ---


class TestStartEndpoint:
    """Tests for /api/start endpoint."""

    def test_start_default_step(self, client: TestClient) -> None:
        response = client.post("/api/start", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["current_step"] == 1
        assert data["status"] == "processing"

    def test_start_specific_step(self, client: TestClient) -> None:
        response = client.post(
            "/api/start", json={"step": 3, "input_data": {"url": "https://example.com"}}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["current_step"] == 3
        assert data["status"] == "processing"

    def test_start_invalid_step_too_low(self, client: TestClient) -> None:
        response = client.post("/api/start", json={"step": 0})
        assert response.status_code == 422  # Validation error

    def test_start_invalid_step_too_high(self, client: TestClient) -> None:
        response = client.post("/api/start", json={"step": 6})
        assert response.status_code == 422  # Validation error


# --- Approve Endpoint ---


class TestApproveEndpoint:
    """Tests for /api/approve endpoint."""

    def test_approve_step(self, client: TestClient) -> None:
        response = client.post("/api/approve", json={"step": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["current_step"] == 2
        assert data["status"] == "done"

    def test_approve_with_item_index(self, client: TestClient) -> None:
        response = client.post("/api/approve", json={"step": 2, "item_index": 1})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_approve_missing_step(self, client: TestClient) -> None:
        response = client.post("/api/approve", json={})
        assert response.status_code == 422  # Validation error

    def test_approve_invalid_step_too_low(self, client: TestClient) -> None:
        response = client.post("/api/approve", json={"step": 0})
        assert response.status_code == 422  # Validation error

    def test_approve_invalid_step_too_high(self, client: TestClient) -> None:
        response = client.post("/api/approve", json={"step": 6})
        assert response.status_code == 422  # Validation error


# --- Reject Endpoint ---


class TestRejectEndpoint:
    """Tests for /api/reject endpoint."""

    def test_reject_step(self, client: TestClient) -> None:
        response = client.post(
            "/api/reject",
            json={"step": 2, "feedback": "The extraction missed page 3"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "processing"  # Returns to processing

    def test_reject_with_item_index(self, client: TestClient) -> None:
        response = client.post(
            "/api/reject",
            json={"step": 2, "feedback": "Fix this item", "item_index": 0},
        )
        assert response.status_code == 200

    def test_reject_empty_feedback_fails(self, client: TestClient) -> None:
        response = client.post("/api/reject", json={"step": 2, "feedback": ""})
        assert response.status_code == 422  # Validation error

    def test_reject_missing_feedback_fails(self, client: TestClient) -> None:
        response = client.post("/api/reject", json={"step": 2})
        assert response.status_code == 422  # Validation error

    def test_reject_feedback_too_long(self, client: TestClient) -> None:
        response = client.post("/api/reject", json={"step": 2, "feedback": "x" * 2001})
        assert response.status_code == 422  # Validation error

    def test_reject_invalid_step_too_low(self, client: TestClient) -> None:
        response = client.post("/api/reject", json={"step": 0, "feedback": "bad"})
        assert response.status_code == 422  # Validation error

    def test_reject_invalid_step_too_high(self, client: TestClient) -> None:
        response = client.post("/api/reject", json={"step": 6, "feedback": "bad"})
        assert response.status_code == 422  # Validation error


# --- Continue Endpoint ---


class TestContinueEndpoint:
    """Tests for /api/continue endpoint."""

    def test_continue_to_next_step(self, client: TestClient) -> None:
        response = client.post("/api/continue", json={"from_step": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["current_step"] == 3
        assert data["status"] == "start"

    def test_continue_from_step_4_to_5(self, client: TestClient) -> None:
        response = client.post("/api/continue", json={"from_step": 4})
        assert response.status_code == 200
        data = response.json()
        assert data["current_step"] == 5
        assert data["status"] == "start"

    def test_continue_from_step_5_completes(self, client: TestClient) -> None:
        response = client.post("/api/continue", json={"from_step": 5})
        assert response.status_code == 200
        data = response.json()
        assert data["current_step"] == 5
        assert data["status"] == "completed"

    def test_continue_missing_from_step(self, client: TestClient) -> None:
        response = client.post("/api/continue", json={})
        assert response.status_code == 422  # Validation error

    def test_continue_invalid_from_step_too_low(self, client: TestClient) -> None:
        response = client.post("/api/continue", json={"from_step": 0})
        assert response.status_code == 422  # Validation error

    def test_continue_invalid_from_step_too_high(self, client: TestClient) -> None:
        response = client.post("/api/continue", json={"from_step": 6})
        assert response.status_code == 422  # Validation error


# --- CORS Configuration ---


class TestCORSConfiguration:
    """Tests for CORS middleware configuration."""

    def test_cors_allows_frontend_origin(self, client: TestClient) -> None:
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_cors_allows_127_origin(self, client: TestClient) -> None:
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200


# --- App Factory ---


class TestAppFactory:
    """Tests for FastAPI app factory."""

    def test_create_app_returns_fastapi_instance(self) -> None:
        from fastapi import FastAPI

        app = create_app()
        assert isinstance(app, FastAPI)

    def test_create_app_with_custom_settings(self) -> None:
        from ai_qa.config import AppSettings

        settings = AppSettings()
        app = create_app(settings=settings)
        assert app is not None

    def test_app_has_api_routes(self) -> None:
        app = create_app()
        routes = [route.path for route in app.routes]
        assert "/api/start" in routes
        assert "/api/approve" in routes
        assert "/api/reject" in routes
        assert "/api/continue" in routes
        assert "/api/health" in routes

    def test_app_has_websocket_route(self) -> None:
        app = create_app()
        routes = [route.path for route in app.routes]
        assert "/ws" in routes
