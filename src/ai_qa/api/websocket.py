"""WebSocket endpoint for real-time agent-to-frontend communication.

The frontend connects to /ws and receives AgentMessage updates in real-time.
This enables the conversational chat UI pattern where agents report progress,
request review, and receive user feedback.
"""

import json
import logging
from collections.abc import Generator
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.session import SessionManager, UserSession
from ai_qa.config import AppSettings
from ai_qa.models import AgentMessage
from ai_qa.pipelines.context import PipelineContext

logger = logging.getLogger(__name__)

# Active connections storage with user context
# Key: connection_id, Value: (websocket, user_session)
active_connections: dict[str, tuple[WebSocket, UserSession | None]] = {}


def _get_user_from_websocket(websocket: WebSocket, settings: AppSettings) -> UserSession | None:
    """Extract and validate user session from WebSocket connection.

    Auth resolution order:
    1. ?token= query param (JWT sent by frontend that cannot set WS headers)
    2. Session cookie (set by /auth/login for same-origin requests)

    Args:
        websocket: WebSocket connection.
        settings: Application settings.

    Returns:
        UserSession if authenticated and not expired, None otherwise.
    """
    session_manager = SessionManager(settings)
    cookie_name = settings.session_cookie_name

    # 1. Try Bearer token from query param (frontend passes ?token=<jwt>)
    token = websocket.query_params.get("token")

    # 2. Fallback to session cookie
    if not token:
        token = websocket.cookies.get(cookie_name)

    if not token:
        return None

    user = session_manager.decode_session(token)
    # Treat expired sessions the same as no session
    if user and user.is_expired:
        return None
    return user


async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time communication.

    Accepts connections from frontend and handles bidirectional messaging.
    Frontend receives AgentMessage JSON objects as agents progress.

    Authentication is checked via ?token= query param or session cookie.
    Unauthenticated / expired-session connections are closed immediately with
    WS close code 4401 so the frontend knows to redirect to login.
    """
    # Get settings from app state
    settings = (
        websocket.app.state.settings if hasattr(websocket.app.state, "settings") else AppSettings()
    )

    # Authenticate user from query param or cookie
    user = _get_user_from_websocket(websocket, settings)

    await websocket.accept()

    if user is None:
        # Reject unauthenticated connections with a clear close code.
        # 4401 is a custom application-level code meaning "Unauthorized".
        # The frontend should redirect to login on receiving this.
        logger.warning("WebSocket connection rejected: no valid session")
        await websocket.close(code=4401, reason="Unauthorized")
        return

    connection_id = str(id(websocket))
    active_connections[connection_id] = (websocket, user)
    query_project_id = _parse_project_id(websocket.query_params.get("projectId"))

    # Notify frontend that auth succeeded
    await websocket.send_json(
        {
            "type": "auth_status",
            "authenticated": True,
            "user": {"email": user.email, "name": user.name},
        }
    )

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

            # Process action messages
            msg_type = message.get("type")
            step = message.get("step")

            if msg_type in ("start", "approve", "reject") and step:
                # Handle pipeline actions
                try:
                    await _handle_action(message, user, websocket, query_project_id)
                except Exception as e:
                    logger.error("Error handling action %s: %s", msg_type, e)
                    await websocket.send_json(
                        {"type": "error", "message": f"Failed to process {msg_type}: {str(e)}"}
                    )
            elif msg_type == "navigate" and step:
                # Handle navigation to different step
                try:
                    await _handle_navigate(message, user, websocket, query_project_id)
                except Exception as e:
                    logger.error("Error handling navigate: %s", e)
                    await websocket.send_json(
                        {"type": "error", "message": f"Failed to navigate: {str(e)}"}
                    )
            else:
                # Echo back unknown messages
                await websocket.send_json(
                    {
                        "type": "ack",
                        "received": message,
                        "user": user.email if user else None,
                    }
                )

    except WebSocketDisconnect:
        active_connections.pop(connection_id, None)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        active_connections.pop(connection_id, None)


def _parse_project_id(value: object) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid projectId") from exc


def _db_session_from_websocket(websocket: WebSocket) -> Session:
    dependency = websocket.app.dependency_overrides.get(get_db_session_dependency)
    if dependency is not None:
        session_gen = cast(Generator[Session], dependency())
        try:
            return next(session_gen)
        except StopIteration as exc:
            raise RuntimeError("DB session dependency did not yield a session") from exc

    from ai_qa.db.session import create_session_factory

    settings = (
        websocket.app.state.settings if hasattr(websocket.app.state, "settings") else AppSettings()
    )
    session_factory = create_session_factory(settings)
    return session_factory()


async def _context_from_websocket(
    message: dict[str, Any],
    user: UserSession | None,
    websocket: WebSocket,
    query_project_id: UUID | None,
    *,
    create_run: bool = False,
) -> PipelineContext | None:
    from ai_qa.api.artifacts import get_artifact_storage
    from ai_qa.api.routes import _build_pipeline_context

    project_id = _parse_project_id(message.get("projectId") or message.get("project_id"))
    if project_id is None:
        project_id = query_project_id

    scope_state = getattr(websocket, "state", None)
    if scope_state is not None:
        websocket.state.user = user

    session = _db_session_from_websocket(websocket)
    try:
        storage = get_artifact_storage()
        return await _build_pipeline_context(
            project_id=project_id,
            http_request=websocket,  # type: ignore[arg-type]
            db=session,
            storage=storage,
            create_run=create_run,
        )
    finally:
        session.close()


async def _handle_action(
    message: dict[str, Any],
    user: UserSession | None,
    websocket: WebSocket,
    query_project_id: UUID | None,
) -> None:
    """Handle pipeline action messages from WebSocket.

    Routes start, approve, reject messages to the appropriate agent.
    """
    msg_type = message.get("type")
    step = message.get("step")

    if not isinstance(step, int):
        logger.warning("Invalid step value: %s", step)
        return

    # Lazy import to avoid circular imports
    from ai_qa.api.routes import _agent_for_context

    context = await _context_from_websocket(
        message,
        user,
        websocket,
        query_project_id,
        create_run=msg_type == "start",
    )
    user_email = user.email if user else None
    agent = _agent_for_context(step, context, user_email)

    if agent is None:
        logger.warning("No agent registered for step %d", step)
        return

    try:
        if msg_type == "start":
            input_data = message.get("inputData", {})
            await agent.handle_start(input_data)
        elif msg_type == "approve":
            data = message.get("data", {})
            await agent.handle_approve(data)
        elif msg_type == "reject":
            feedback = message.get("feedback", "")
            await agent.handle_reject(feedback)
    except Exception as e:
        logger.error("Error handling %s for step %d: %s", msg_type, step, e, exc_info=True)
        error_msg = AgentMessage(
            sender="system",
            agentName=None,
            content=f"An unexpected error occurred: {str(e)}",
            messageType="error",
        )
        await broadcast_message(error_msg)
        # Don't raise here, let the connection stay open so the user can see the error and retry.


async def _handle_navigate(
    message: dict[str, Any],
    user: UserSession | None,
    websocket: WebSocket,
    query_project_id: UUID | None,
) -> None:
    """Handle navigation to a different pipeline step.

    Broadcasts a navigation message to all clients to update the current step.
    """
    step = message.get("step")
    direction = message.get("direction", "next")

    await _context_from_websocket(message, user, websocket, query_project_id)

    if not isinstance(step, int):
        logger.warning("Invalid step value for navigate: %s", step)
        return

    # Map step numbers to agent names
    step_agents: dict[int, str] = {
        1: "Alice",
        2: "Bob",
        3: "Mary",
        4: "Sarah",
        5: "Jack",
    }

    agent_name = step_agents.get(step, "Unknown")

    # Broadcast navigation message
    from ai_qa.models import AgentMessage

    navigate_message = AgentMessage(
        sender="system",
        agentName=agent_name,  # type: ignore[arg-type]
        content=f"Navigating to {agent_name} (Step {step})",
        messageType="info",
        metadata={
            "type": "navigation",
            "step": step,
            "direction": direction,
            "state": "start",
        },
    )

    await broadcast_message(navigate_message)
    logger.info(
        "Navigation to step %d (%s) triggered by %s",
        step,
        agent_name,
        user.email if user else "anonymous",
    )


async def broadcast_message(message: AgentMessage) -> None:
    """Broadcast an AgentMessage to all connected WebSocket clients.

    Called by agents to send updates to the frontend in real-time.

    Args:
        message: AgentMessage to broadcast to all connected clients.
    """
    json_message = message.model_dump_json(by_alias=True)
    disconnected = []

    for conn_id, (connection, _user) in active_connections.items():
        try:
            await connection.send_text(json_message)
        except Exception:
            # Connection likely closed, mark for cleanup
            disconnected.append(conn_id)

    # Clean up disconnected clients
    for conn_id in disconnected:
        active_connections.pop(conn_id, None)
