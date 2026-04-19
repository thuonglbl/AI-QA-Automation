"""FastAPI application factory for AI QA Automation API.

Provides REST endpoints for pipeline control and WebSocket for real-time
communication between agents and the frontend.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ai_qa.agents import AliceAgent
from ai_qa.api.routes import register_agent
from ai_qa.api.routes import router as api_router
from ai_qa.api.websocket import websocket_endpoint
from ai_qa.config import AppSettings

# Frontend dist directory (relative to project root)
_DIST_DIR = Path(__file__).parents[3] / "frontend" / "dist"


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
    # Only mounted if the directory exists
    if _DIST_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(_DIST_DIR), html=True), name="static")

    # Register Alice agent (Step 1)
    alice = AliceAgent()
    register_agent(alice)

    return app
