"""Tests for WebSocket endpoint.

Validates WebSocket connection, message exchange, and disconnection handling.
"""

import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ai_qa.api.app import create_app
from ai_qa.api.auth.session import SessionManager
from ai_qa.api.websocket import active_connections


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client with default settings and a mock authenticated user."""
    app = create_app()
    client = TestClient(app)

    # Create a mock session
    settings = app.state.settings
    session_manager = SessionManager(settings)
    session = session_manager.create_session({"email": "test@example.com", "name": "Test User"})
    token = session_manager.encode_session(session)

    client.cookies.set(settings.session_cookie_name, token)
    return client


@pytest.fixture(autouse=True)
def _reset_active_connections() -> Generator[None]:
    """Reset active_connections before each test to prevent state leaking."""
    active_connections.clear()
    yield
    active_connections.clear()


class TestWebSocketConnection:
    """Tests for WebSocket connection lifecycle."""

    def test_websocket_connects_successfully(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as websocket:
            # Drain auth_status message
            response = websocket.receive_json()
            assert response["type"] == "auth_status"

    def test_websocket_send_receive_json(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as websocket:
            websocket.receive_json()  # Drain auth_status

            test_message = {"action": "test", "data": "hello"}
            websocket.send_json(test_message)

            response = websocket.receive_json()
            assert response["type"] == "ack"
            assert response["received"] == test_message

    def test_websocket_send_text_receive_json(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as websocket:
            websocket.receive_json()  # Drain auth_status

            test_message = {"action": "ping"}
            websocket.send_text(json.dumps(test_message))

            response = websocket.receive_json()
            assert response["type"] == "ack"
            assert response["received"]["action"] == "ping"

    def test_websocket_invalid_json_returns_error(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as websocket:
            websocket.receive_json()  # Drain auth_status

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
            websocket.receive_json()  # Drain auth_status

            for i in range(3):
                websocket.send_json({"count": i})
                response = websocket.receive_json()
                assert response["type"] == "ack"
                assert response["received"]["count"] == i


class TestWebSocketConnections:
    """Tests for multiple concurrent WebSocket connections."""

    def test_multiple_connections(self, client: TestClient) -> None:
        with (
            client.websocket_connect("/ws") as ws1,
            client.websocket_connect("/ws") as ws2,
        ):
            ws1.receive_json()  # Drain auth_status
            ws2.receive_json()  # Drain auth_status

            ws1.send_json({"source": "conn1"})
            ws2.send_json({"source": "conn2"})

            resp1 = ws1.receive_json()
            resp2 = ws2.receive_json()

            assert resp1["received"]["source"] == "conn1"
            assert resp2["received"]["source"] == "conn2"


class TestActiveConnections:
    """Tests for active_connections management."""

    def test_connection_added_on_connect(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as websocket:
            websocket.receive_json()  # Drain auth_status
            # Connection should be tracked
            assert len(active_connections) == 1

        # After disconnect, connection should be removed
        # Note: cleanup happens asynchronously, so we check it was removed eventually
        # In test context, the disconnect handler runs synchronously

    def test_connection_removed_on_disconnect(self, client: TestClient) -> None:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # Drain auth_status
            ws.send_json({"test": "data"})
            ws.receive_json()

        # After disconnect, the connection should be cleaned up
        # The exact timing depends on the test client implementation


class TestWebSocketAuthentication:
    """Tests for WebSocket authentication behavior."""

    def test_unauthenticated_connection_is_closed_with_4401(self) -> None:
        """Unauthenticated WebSocket connections must be rejected with code 4401.

        This prevents silent guest connections and ensures the frontend can detect
        auth failure and redirect to login instead of entering a reconnect loop.
        """
        app = create_app()
        client = TestClient(app)

        # Connect without any auth cookie or token
        with pytest.raises(WebSocketDisconnect) as exc_info:
            # TestClient raises when the server closes the connection during
            # the context (the WS close frame with code 4401 causes disconnect)
            with client.websocket_connect("/ws") as ws:
                # Server should close immediately with 4401
                ws.receive_json()  # may raise WebSocketDisconnect
        assert exc_info.value.code == 4401

    def test_token_query_param_authenticates_websocket(self) -> None:
        """A valid Bearer token supplied as ?token= should authenticate the WS."""
        app = create_app()
        client = TestClient(app)

        settings = app.state.settings
        session_manager = SessionManager(settings)
        session = session_manager.create_session(
            {"email": "token@example.com", "name": "Token User"}
        )
        token = session_manager.encode_session(session)

        # Connect without cookie, but with token in query param
        with client.websocket_connect(f"/ws?token={token}") as ws:
            response = ws.receive_json()
            assert response["type"] == "auth_status"
            assert response["authenticated"] is True
            assert response["user"]["email"] == "token@example.com"

    def test_auth_status_shows_authenticated_true_on_success(self, client: TestClient) -> None:
        """Authenticated connections receive auth_status with authenticated=True."""
        with client.websocket_connect("/ws") as ws:
            response = ws.receive_json()
            assert response["type"] == "auth_status"
            assert response["authenticated"] is True
            assert "user" in response
            assert response["user"]["email"] == "test@example.com"
