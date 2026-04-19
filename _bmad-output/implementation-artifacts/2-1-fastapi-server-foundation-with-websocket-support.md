# Story 2.1: FastAPI Server Foundation with WebSocket Support

**Story ID:** 2.1
**Story Key:** 2-1-fastapi-server-foundation-with-websocket-support
**Epic:** 2 — AI Provider Configuration & Connection (Agent Alice)
**Status:** done
**Date Created:** 2026-04-10
**Dependencies:** Story 1.5 (Dev Tooling Setup) - Done

---

## User Story

**As a** R&D engineer,
**I want** a FastAPI server with REST endpoints and WebSocket support,
**So that** the React frontend can communicate with the pipeline backend in real-time.

---

## Acceptance Criteria

**Given** the FastAPI server module is created at `src/ai_qa/api/`
**When** the server starts via `python -m ai_qa`
**Then** FastAPI app runs on `localhost:8000` with CORS configured for frontend dev server
**And** WebSocket endpoint at `/ws` accepts connections and can send/receive JSON messages
**And** REST endpoints exist for pipeline actions: `/api/start`, `/api/approve`, `/api/reject`, `/api/continue`
**And** API request/response models are defined in `api/schemas.py` as Pydantic models
**And** server serves static files from `frontend/dist/` in production mode
**And** `__main__.py` starts the FastAPI server as the default entry point

---

## Developer Context

### Current State (from Epic 1)

Epic 1 (Project Foundation) is complete with:
- `src/ai_qa/` package structure with src layout
- `AppSettings` (Pydantic Settings v2) for configuration
- Custom exception hierarchy (`ai_qa/exceptions.py`)
- `StageResult` and `AgentMessage` models (`ai_qa/models.py`)
- Project-wide constants (`ai_qa/constants.py`)
- Dev tooling (ruff, mypy, pytest, pre-commit) configured

**What's missing (this story must add):**
- No FastAPI server infrastructure
- No WebSocket support for real-time communication
- No REST API endpoints for pipeline actions
- No API schemas for request/response validation
- `__main__.py` currently runs a CLI script instead of starting a server

### What This Story Establishes

This story creates the **backend foundation** for the conversational chat UI:
1. FastAPI app with CORS for frontend communication
2. WebSocket endpoint for real-time agent-to-frontend messages
3. REST endpoints for pipeline control (start, approve, reject, continue)
4. Pydantic schemas for API request/response validation
5. Static file serving for production (frontend/dist/)
6. Server entry point via `python -m ai_qa`

This enables Epic 2 stories (2.2-2.8) to build the frontend and agent interactions on top of a solid API foundation.

---

## Technical Requirements

### 1. Create `src/ai_qa/api/` Module Structure

```
src/ai_qa/
├── api/
│   ├── __init__.py      # Package exports
│   ├── app.py           # FastAPI app factory
│   ├── websocket.py     # WebSocket endpoint handler
│   ├── routes.py        # REST API endpoints
│   └── schemas.py       # Pydantic request/response models
├── __main__.py          # Updated to start FastAPI server
└── ... (existing modules)
```

### 2. Create `src/ai_qa/api/app.py`

**FastAPI app factory with CORS configuration:**

```python
"""FastAPI application factory for AI QA Automation API.

Provides REST endpoints for pipeline control and WebSocket for real-time
communication between agents and the frontend.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ai_qa.api.routes import router as api_router
from ai_qa.api.websocket import websocket_endpoint
from ai_qa.config import AppSettings


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Create and configure FastAPI application.
    
    Args:
        settings: AppSettings instance. If None, loads from environment.
        
    Returns:
        Configured FastAPI application instance.
    """
    if settings is None:
        settings = AppSettings()
    
    app = FastAPI(
        title="AI QA Automation API",
        description="Backend API for AI-powered QA test automation pipeline",
        version="0.1.0",
    )
    
    # CORS for frontend dev server (Vite on localhost:5173)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # REST API routes
    app.include_router(api_router, prefix="/api")
    
    # WebSocket endpoint
    app.add_api_websocket_route("/ws", websocket_endpoint)
    
    # Static files for production (frontend/dist/)
    # Note: Only mounted if the directory exists
    import os
    dist_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "dist")
    if os.path.exists(dist_path):
        app.mount("/", StaticFiles(directory=dist_path, html=True), name="static")
    
    return app
```

### 3. Create `src/ai_qa/api/schemas.py`

**Pydantic models for API request/response validation:**

```python
"""Pydantic schemas for API request/response validation.

These models define the structure of data exchanged between frontend and backend.
"""

from pydantic import BaseModel, Field


class StartRequest(BaseModel):
    """Request body for /api/start endpoint."""
    
    step: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Pipeline step to start (1-5)",
    )
    input_data: dict = Field(
        default_factory=dict,
        description="Step-specific input data (e.g., Confluence URL for step 2)",
    )


class ActionResponse(BaseModel):
    """Response for pipeline action endpoints."""
    
    success: bool = Field(description="Whether the action was accepted")
    message: str = Field(description="Human-readable status message")
    current_step: int = Field(description="Current pipeline step after action")
    status: str = Field(description="Agent status (start/processing/review/done)")


class ApproveRequest(BaseModel):
    """Request body for /api/approve endpoint."""
    
    step: int = Field(description="Step being approved")
    item_index: int | None = Field(
        default=None,
        description="Index of specific item being approved (for paginated review)",
    )


class RejectRequest(BaseModel):
    """Request body for /api/reject endpoint."""
    
    step: int = Field(description="Step being rejected")
    feedback: str = Field(
        min_length=1,
        max_length=2000,
        description="User feedback explaining why output is rejected",
    )
    item_index: int | None = Field(
        default=None,
        description="Index of specific item being rejected (for paginated review)",
    )


class ContinueRequest(BaseModel):
    """Request body for /api/continue endpoint."""
    
    from_step: int = Field(description="Step that was just completed")
```

### 4. Create `src/ai_qa/api/routes.py`

**REST API endpoints for pipeline control:**

```python
"""REST API endpoints for pipeline control.

These endpoints allow the frontend to:
- Start a pipeline step
- Approve agent output and continue
- Reject with feedback for correction
- Continue to next step after approval
"""

from fastapi import APIRouter, HTTPException

from ai_qa.api.schemas import (
    ActionResponse,
    ApproveRequest,
    ContinueRequest,
    RejectRequest,
    StartRequest,
)
from ai_qa.exceptions import PipelineError

router = APIRouter()


@router.post("/start", response_model=ActionResponse)
async def start_step(request: StartRequest) -> ActionResponse:
    """Start a pipeline step.
    
    Triggers the specified agent to begin processing.
    Returns immediately; use WebSocket for real-time updates.
    """
    # TODO: Implement actual pipeline start logic in future stories
    # For now, return mock response to enable frontend development
    return ActionResponse(
        success=True,
        message=f"Step {request.step} started",
        current_step=request.step,
        status="processing",
    )


@router.post("/approve", response_model=ActionResponse)
async def approve_step(request: ApproveRequest) -> ActionResponse:
    """Approve agent output and continue.
    
    User approves the current output and wants to proceed.
    """
    return ActionResponse(
        success=True,
        message=f"Step {request.step} approved",
        current_step=request.step,
        status="done",
    )


@router.post("/reject", response_model=ActionResponse)
async def reject_step(request: RejectRequest) -> ActionResponse:
    """Reject agent output with feedback.
    
    User rejects the output and provides feedback for correction.
    Agent will re-process with the feedback context.
    """
    return ActionResponse(
        success=True,
        message=f"Step {request.step} rejected with feedback",
        current_step=request.step,
        status="processing",  # Returns to processing for correction
    )


@router.post("/continue", response_model=ActionResponse)
async def continue_pipeline(request: ContinueRequest) -> ActionResponse:
    """Continue to next step after approval.
    
    User clicks Continue after a step is marked Done.
    Advances to the next step or completes if step 5.
    """
    next_step = request.from_step + 1
    if next_step > 5:
        return ActionResponse(
            success=True,
            message="Pipeline completed",
            current_step=5,
            status="completed",
        )
    return ActionResponse(
        success=True,
        message=f"Continuing to step {next_step}",
        current_step=next_step,
        status="start",
    )


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}
```

### 5. Create `src/ai_qa/api/websocket.py`

**WebSocket endpoint for real-time communication:**

```python
"""WebSocket endpoint for real-time agent-to-frontend communication.

The frontend connects to /ws and receives AgentMessage updates in real-time.
This enables the conversational chat UI pattern where agents report progress,
request review, and receive user feedback.
"""

import json
from typing import Dict

from fastapi import WebSocket, WebSocketDisconnect

from ai_qa.models import AgentMessage

# Active connections storage (in-memory for now, consider Redis for multi-instance)
# Key: connection_id (can be enhanced with session management later)
active_connections: Dict[str, WebSocket] = {}


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
            message = json.loads(data)
            
            # Echo back for now (actual message handling in future stories)
            # This establishes the connection protocol
            await websocket.send_json({
                "type": "ack",
                "received": message,
            })
            
    except WebSocketDisconnect:
        del active_connections[connection_id]
    except json.JSONDecodeError:
        await websocket.send_json({
            "type": "error",
            "message": "Invalid JSON format",
        })


async def broadcast_message(message: AgentMessage) -> None:
    """Broadcast an AgentMessage to all connected WebSocket clients.
    
    Called by agents to send updates to the frontend in real-time.
    
    Args:
        message: AgentMessage to broadcast to all connected clients.
    """
    json_message = message.model_dump_json()
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
```

### 6. Create `src/ai_qa/api/__init__.py`

```python
"""AI QA Automation API package.

Provides FastAPI application and WebSocket support for the
conversational chat UI pipeline.
"""

from ai_qa.api.app import create_app

__all__ = ["create_app"]
```

### 7. Update `src/ai_qa/__main__.py`

**Replace CLI entry point with FastAPI server:**

```python
"""Entry point for AI QA Automation.

Starts the FastAPI server with WebSocket support for the
conversational chat UI pipeline.
"""

import uvicorn

from ai_qa.api import create_app
from ai_qa.config import AppSettings


def run() -> None:
    """Start the FastAPI server."""
    settings = AppSettings()
    app = create_app(settings)
    
    # Run uvicorn server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    run()
```

### 8. Add Dependencies to `pyproject.toml`

Add FastAPI and uvicorn to project dependencies:

```toml
[project]
dependencies = [
    "browser-use>=0.12.5",
    "fastapi>=0.115.0",
    "langchain-anthropic>=1.3.1",
    "pydantic-settings>=2.4.0",
    "pyyaml>=6.0",
    "uvicorn[standard]>=0.32.0",
    "websockets>=13.0",
]
```

Then run `uv sync` to install.

---

## Architecture Compliance

### Pattern Alignment

- **FastAPI + WebSocket** — Architecture specifies FastAPI for REST + WebSocket for real-time communication
- **Pydantic models for API schemas** — Architecture specifies Pydantic models everywhere, never raw dicts
- **CORS for frontend dev server** — Architecture specifies frontend on Vite dev server (localhost:5173)
- **Static files for production** — Architecture specifies serving frontend/dist/ in production
- **Modular API structure** — `api/` package with separate modules for routes, schemas, websocket

### Dependencies Added

| Package | Purpose | Version |
|---------|---------|---------|
| fastapi | Web framework | >=0.115.0 |
| uvicorn[standard] | ASGI server | >=0.32.0 |
| websockets | WebSocket support | >=13.0 |

---

## File Structure

```
ai-qa-automation/
├── src/ai_qa/
│   ├── api/                    # NEW — FastAPI API module
│   │   ├── __init__.py         # Package exports
│   │   ├── app.py              # FastAPI app factory with CORS
│   │   ├── routes.py           # REST endpoints
│   │   ├── schemas.py          # Pydantic request/response models
│   │   └── websocket.py        # WebSocket endpoint handler
│   ├── __main__.py             # MODIFY — Start FastAPI server
│   └── ... (existing modules)
├── pyproject.toml              # MODIFY — Add fastapi, uvicorn, websockets
└── tests/                      # ADD tests for API endpoints
    ├── test_api.py             # Tests for REST endpoints
    └── test_websocket.py       # Tests for WebSocket
```

---

## Testing Strategy

### What to Test

1. **FastAPI app creation:** `create_app()` returns valid FastAPI instance
2. **CORS configuration:** Frontend origins (localhost:5173) are allowed
3. **REST endpoints:** `/api/start`, `/api/approve`, `/api/reject`, `/api/continue` respond correctly
4. **WebSocket:** `/ws` accepts connections and can send/receive messages
5. **API schemas:** Request/response validation works with Pydantic
6. **Health endpoint:** `/api/health` returns expected response

### Test Commands

```bash
# Run tests
uv run pytest tests/test_api.py tests/test_websocket.py -v

# Start server manually for testing
uv run python -m ai_qa

# Test API with curl
curl http://localhost:8000/api/health

# Test WebSocket (using wscat or similar)
# Connect to ws://localhost:8000/ws
```

---

## Definition of Done

✅ **Story 2.1 is done when:**

1. `src/ai_qa/api/` module created with `app.py`, `routes.py`, `schemas.py`, `websocket.py`
2. FastAPI app runs on `localhost:8000` with CORS configured for frontend (localhost:5173)
3. WebSocket endpoint at `/ws` accepts connections and can send/receive JSON
4. REST endpoints exist: `/api/start`, `/api/approve`, `/api/reject`, `/api/continue`
5. Pydantic schemas defined in `api/schemas.py` for all request/response models
6. `__main__.py` updated to start FastAPI server via `uvicorn`
7. Dependencies added: fastapi, uvicorn, websockets
8. Tests created for API endpoints and WebSocket
9. `uv run ruff check src/ tests/` passes
10. `uv run mypy src/` passes
11. `uv run pytest tests/` passes
12. `git commit` created: `feat: Story 2.1: FastAPI Server Foundation with WebSocket Support`

---

## Tasks/Subtasks

- [ ] **Task 1: Add FastAPI dependencies to pyproject.toml**
  - [ ] 1a. Add `fastapi>=0.115.0` to `[project]` dependencies
  - [ ] 1b. Add `uvicorn[standard]>=0.32.0` to `[project]` dependencies
  - [ ] 1c. Add `websockets>=13.0` to `[project]` dependencies
  - [ ] 1d. Run `uv sync` to install

- [ ] **Task 2: Create api module structure**
  - [ ] 2a. Create `src/ai_qa/api/__init__.py`
  - [ ] 2b. Create `src/ai_qa/api/app.py` with FastAPI factory and CORS
  - [ ] 2c. Create `src/ai_qa/api/schemas.py` with Pydantic models
  - [ ] 2d. Create `src/ai_qa/api/routes.py` with REST endpoints
  - [ ] 2e. Create `src/ai_qa/api/websocket.py` with WebSocket handler

- [ ] **Task 3: Update entry point**
  - [ ] 3a. Update `src/ai_qa/__main__.py` to start FastAPI server
  - [ ] 3b. Verify `python -m ai_qa` starts server on port 8000

- [ ] **Task 4: Create API tests**
  - [ ] 4a. Create `tests/test_api.py` with REST endpoint tests
  - [ ] 4b. Create `tests/test_websocket.py` with WebSocket tests
  - [ ] 4c. Run tests and verify all pass

- [ ] **Task 5: Run validation suite**
  - [ ] 5a. `uv run ruff check src/ tests/` → exit 0
  - [ ] 5b. `uv run mypy src/` → exit 0
  - [ ] 5c. `uv run pytest tests/` → all tests pass
  - [ ] 5d. Manual test: `uv run python -m ai_qa` and verify server starts

- [ ] **Task 6: Commit**
  - [ ] 6a. `git add` all new/modified files
  - [ ] 6b. `git commit -m "feat: Story 2.1: FastAPI Server Foundation with WebSocket Support"`

---

## Dev Agent Record

### Implementation Plan

1. Add FastAPI dependencies (fastapi, uvicorn, websockets, httpx) to pyproject.toml
2. Create `src/ai_qa/api/` module with app factory, routes, schemas, and websocket handler
3. Update `__main__.py` to start FastAPI server via uvicorn instead of CLI
4. Create comprehensive tests for REST endpoints and WebSocket
5. Run validation suite (ruff, mypy, pytest)

### Debug Log

_To be filled if issues are encountered_

### Completion Notes

- ✅ Created `src/ai_qa/api/__init__.py` — package exports `create_app`
- ✅ Created `src/ai_qa/api/app.py` — FastAPI factory with CORS, routes, WebSocket, static files
- ✅ Created `src/ai_qa/api/schemas.py` — StartRequest, ActionResponse, ApproveRequest, RejectRequest, ContinueRequest
- ✅ Created `src/ai_qa/api/routes.py` — /api/start, /approve, /reject, /continue, /health endpoints
- ✅ Created `src/ai_qa/api/websocket.py` — /ws endpoint with active_connections dict and broadcast_message
- ✅ Updated `src/ai_qa/__main__.py` — replaced CLI with uvicorn server startup
- ✅ Added fastapi, uvicorn, websockets to pyproject.toml dependencies
- ✅ Added httpx to dev dependencies for TestClient
- ✅ Created `tests/test_api.py` — 20 tests covering all endpoints, validation, CORS, app factory
- ✅ Created `tests/test_websocket.py` — 8 tests covering connection, messaging, multiple connections
- ✅ All 86 tests pass (73% coverage)
- ✅ `ruff check src/ tests/` — All checks passed
- ✅ `mypy src/` — Success: no issues found in 11 source files

---

## File List

_To be filled by dev agent upon completion_

- `pyproject.toml` — modified (add fastapi, uvicorn, websockets dependencies)
- `src/ai_qa/__main__.py` — modified (start FastAPI server)
- `src/ai_qa/api/__init__.py` — created
- `src/ai_qa/api/app.py` — created (FastAPI app factory with CORS)
- `src/ai_qa/api/schemas.py` — created (Pydantic API schemas)
- `src/ai_qa/api/routes.py` — created (REST endpoints)
- `src/ai_qa/api/websocket.py` — created (WebSocket handler)
- `tests/test_api.py` — created (API endpoint tests)
- `tests/test_websocket.py` — created (WebSocket tests)

---

## Change Log

- 2026-04-10: Implemented Story 2.1 — FastAPI server foundation with WebSocket support. Created api/ module (app.py, routes.py, schemas.py, websocket.py), updated __main__.py to start uvicorn server, added 28 tests (all passing).
