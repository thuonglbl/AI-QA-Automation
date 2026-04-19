"""WebSocket endpoint for real-time agent-to-frontend communication.

The frontend connects to /ws and receives AgentMessage updates in real-time.
This enables the conversational chat UI pattern where agents report progress,
request review, and receive user feedback.
"""

import json

from fastapi import WebSocket, WebSocketDisconnect

from ai_qa.models import AgentMessage

# Active connections storage (in-memory for now, consider Redis for multi-instance)
# Key: connection_id (can be enhanced with session management later)
active_connections: dict[str, WebSocket] = {}


async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time communication.

    Accepts connections from frontend and handles bidirectional messaging.
    Frontend receives AgentMessage JSON objects as agents progress.
    """
    await websocket.accept()
    connection_id = str(id(websocket))
    active_connections[connection_id] = websocket

    try:
        while True:
            # Receive message from frontend (JSON format)
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Invalid JSON format",
                    }
                )
                continue

            # Echo back for now (actual message handling in future stories)
            # This establishes the connection protocol
            await websocket.send_json(
                {
                    "type": "ack",
                    "received": message,
                }
            )

    except WebSocketDisconnect:
        active_connections.pop(connection_id, None)


async def broadcast_message(message: AgentMessage) -> None:
    """Broadcast an AgentMessage to all connected WebSocket clients.

    Called by agents to send updates to the frontend in real-time.

    Args:
        message: AgentMessage to broadcast to all connected clients.
    """
    json_message = message.model_dump_json(by_alias=True)
    disconnected = []

    for conn_id, connection in active_connections.items():
        try:
            await connection.send_text(json_message)
        except Exception:
            # Connection likely closed, mark for cleanup
            disconnected.append(conn_id)

    # Clean up disconnected clients
    for conn_id in disconnected:
        active_connections.pop(conn_id, None)
