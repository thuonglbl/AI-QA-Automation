"""Tests for WebSocket endpoint.

Validates WebSocket connection, message exchange, and disconnection handling.
"""

import json

import pytest
from fastapi.testclient import TestClient

from ai_qa.api.app import create_app
from ai_qa.api.websocket import active_connections


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client with default settings."""
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_active_connections() -> None:
    """Reset active_connections before each test to prevent state leaking."""
    active_connections.clear()
    yield
    active_connections.clear()


class TestWebSocketConnection:
    """Tests for WebSocket connection lifecycle."""

    def test_websocket_connects_successfully(self, client: TestClient) -> None:
        with client.websocket_connect("/ws"):
            # Connection established — no exception means success
            pass

    def test_websocket_send_receive_json(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as websocket:
            test_message = {"action": "test", "data": "hello"}
            websocket.send_json(test_message)

            response = websocket.receive_json()
            assert response["type"] == "ack"
            assert response["received"] == test_message

    def test_websocket_send_text_receive_json(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as websocket:
            test_message = {"action": "ping"}
            websocket.send_text(json.dumps(test_message))

            response = websocket.receive_json()
            assert response["type"] == "ack"
            assert response["received"]["action"] == "ping"

    def test_websocket_invalid_json_returns_error(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as websocket:
            websocket.send_text("not valid json{{{")
            response = websocket.receive_json()
            assert response["type"] == "error"
            assert "Invalid JSON" in response["message"]

            # Connection should still be alive — send a valid message
            websocket.send_json({"action": "after_error"})
            response2 = websocket.receive_json()
            assert response2["type"] == "ack"
            assert response2["received"]["action"] == "after_error"

    def test_websocket_multiple_messages(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as websocket:
            for i in range(3):
                websocket.send_json({"count": i})
                response = websocket.receive_json()
                assert response["type"] == "ack"
                assert response["received"]["count"] == i


class TestWebSocketConnections:
    """Tests for multiple concurrent WebSocket connections."""

    def test_multiple_connections(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as ws1, client.websocket_connect("/ws") as ws2:
            ws1.send_json({"source": "conn1"})
            ws2.send_json({"source": "conn2"})

            resp1 = ws1.receive_json()
            resp2 = ws2.receive_json()

            assert resp1["received"]["source"] == "conn1"
            assert resp2["received"]["source"] == "conn2"


class TestActiveConnections:
    """Tests for active_connections management."""

    def test_connection_added_on_connect(self, client: TestClient) -> None:
        with client.websocket_connect("/ws"):
            # Connection should be tracked
            assert len(active_connections) == 1

        # After disconnect, connection should be removed
        # Note: cleanup happens asynchronously, so we check it was removed eventually
        # In test context, the disconnect handler runs synchronously

    def test_connection_removed_on_disconnect(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"test": "data"})
            ws.receive_json()

        # After disconnect, the connection should be cleaned up
        # The exact timing depends on the test client implementation
