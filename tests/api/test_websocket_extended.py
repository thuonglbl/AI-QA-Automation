"""Extended tests for WebSocket endpoint covering broadcasting and context extraction."""

import json
import uuid
from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from ai_qa.api.app import create_app
from ai_qa.api.auth.session import SessionManager
from ai_qa.api.websocket import active_connections, broadcast_artifact_change, broadcast_message
from ai_qa.models import AgentMessage


@pytest.fixture
def extended_client() -> TestClient:
    app = create_app()
    client = TestClient(app)

    settings = app.state.settings
    session_manager = SessionManager(settings)
    session = session_manager.create_session(
        {
            "email": "test@example.com",
            "name": "Test User",
            "user_id": "00000000-0000-0000-0000-000000000000",
        }
    )
    token = session_manager.encode_session(session)

    client.cookies.set(settings.session_cookie_name, token)
    return client


@pytest.fixture(autouse=True)
def _reset_active_connections() -> Generator[None]:
    active_connections.clear()
    yield
    active_connections.clear()


@pytest.mark.asyncio
async def test_broadcast_message_filtered_by_thread() -> None:
    """Test that broadcast_message filters connections by threadId if provided."""
    mock_ws1 = AsyncMock()
    mock_ws2 = AsyncMock()

    # Connection 1 is on thread 1
    active_connections["conn1"] = (
        mock_ws1,
        None,
        None,
        uuid.UUID("11111111-1111-1111-1111-111111111111"),
        frozenset(),
    )
    # Connection 2 is on thread 2
    active_connections["conn2"] = (
        mock_ws2,
        None,
        None,
        uuid.UUID("22222222-2222-2222-2222-222222222222"),
        frozenset(),
    )

    message = AgentMessage(
        sender="agent",
        agentName="Bob",
        content="Hello",
        messageType="info",
        metadata={"threadId": "11111111-1111-1111-1111-111111111111"},
    )

    await broadcast_message(message)

    mock_ws1.send_text.assert_called_once()
    mock_ws2.send_text.assert_not_called()


@pytest.mark.asyncio
async def test_broadcast_artifact_change_filtered_by_project() -> None:
    """Test that broadcast_artifact_change filters connections by project membership."""
    mock_ws1 = AsyncMock()
    mock_ws2 = AsyncMock()

    # Connection 1 is a member of project 1
    active_connections["conn1"] = (
        mock_ws1,
        None,
        None,
        None,
        frozenset(["11111111-1111-1111-1111-111111111111"]),
    )
    # Connection 2 is a member of project 2
    active_connections["conn2"] = (
        mock_ws2,
        None,
        None,
        None,
        frozenset(["22222222-2222-2222-2222-222222222222"]),
    )

    await broadcast_artifact_change(
        project_id="11111111-1111-1111-1111-111111111111",
        artifact_id="some-artifact",
        change_type="created",
    )

    mock_ws1.send_text.assert_called_once()
    mock_ws2.send_text.assert_not_called()

    # Verify JSON structure
    call_arg = mock_ws1.send_text.call_args[0][0]
    payload = json.loads(call_arg)
    assert payload["project_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["artifact_id"] == "some-artifact"
    assert payload["change_type"] == "created"


def test_websocket_connection_with_params(extended_client: TestClient) -> None:
    """Test websocket connections with projectId and threadId parameters."""
    with extended_client.websocket_connect(
        "/ws?projectId=11111111-1111-1111-1111-111111111111&threadId=22222222-2222-2222-2222-222222222222"
    ) as ws:
        # Drain auth_status
        response = ws.receive_json()
        assert response["type"] == "auth_status"

        # Verify active_connections is populated correctly
        assert len(active_connections) == 1
        conn_tuple = list(active_connections.values())[0]
        assert str(conn_tuple[2]) == "11111111-1111-1111-1111-111111111111"  # project_id
        assert str(conn_tuple[3]) == "22222222-2222-2222-2222-222222222222"  # thread_id


def test_websocket_connection_invalid_uuid(extended_client: TestClient) -> None:
    """Test websocket connections with invalid UUIDs get rejected."""
    # It sends an error JSON and closes connection
    with extended_client.websocket_connect("/ws?projectId=invalid-uuid") as ws:
        err_resp = ws.receive_json()
        assert err_resp["type"] == "error"
        assert "Invalid projectId" in err_resp["message"]
