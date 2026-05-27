"""FastAPI application factory for AI QA Automation API.

Provides REST endpoints for pipeline control and WebSocket for real-time
communication between agents and the frontend.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from ai_qa.agents import AliceAgent
from ai_qa.api.admin import router as admin_router
from ai_qa.api.artifacts import router as artifacts_router
from ai_qa.api.auth import AuthMiddleware, get_auth_router
from ai_qa.api.projects import router as projects_router
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

    # Store settings in app state for middleware and websocket access
    app.state.settings = settings

    # Session middleware for OAuth state (must be before auth middleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret_key,
        session_cookie="aiqa_oauth_session",
        max_age=600,  # 10 minutes for OAuth flow
        https_only=settings.session_cookie_secure,
        same_site="lax",
    )

    # Auth middleware to protect routes (after session middleware)
    app.add_middleware(AuthMiddleware, settings=settings)

    # CORS for frontend dev server (Vite on localhost:5173)
    # Note: Must be after auth middleware to allow credentials
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auth routes (public, handled by middleware)
    auth_router = get_auth_router(settings)
    app.include_router(auth_router)

    # REST API routes (protected by auth middleware)
    app.include_router(api_router, prefix="/api")
    app.include_router(projects_router, prefix="/api")
    app.include_router(artifacts_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")

    # WebSocket endpoint (protected by auth middleware)
    app.add_api_websocket_route("/ws", websocket_endpoint)

    # Static files for production (frontend/dist/)
    # Only mounted if the directory exists
    if _DIST_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(_DIST_DIR), html=True), name="static")

    # Register agents as templates
    # Per-user instances are created on-demand in routes.py via _get_agent_for_user
    from ai_qa.agents import BobAgent, MaryAgent, SarahAgent

    register_agent(AliceAgent())
    register_agent(BobAgent())
    register_agent(MaryAgent())
    register_agent(SarahAgent())

    return app
