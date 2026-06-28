"""FastAPI application factory for AI QA Automation API.

Provides REST endpoints for pipeline control and WebSocket for real-time
communication between agents and the frontend.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from ai_qa.agents import AliceAgent
from ai_qa.api.admin import router as admin_router
from ai_qa.api.artifacts import router as artifacts_router
from ai_qa.api.auth import AuthMiddleware, get_auth_router
from ai_qa.api.auth.sso import router as sso_router
from ai_qa.api.body_size_limit import BodySizeLimitMiddleware
from ai_qa.api.claude_sso import router as claude_sso_router
from ai_qa.api.executions import router as executions_router
from ai_qa.api.projects import router as projects_router
from ai_qa.api.projects_admin import router as projects_admin_router
from ai_qa.api.routes import register_agent
from ai_qa.api.routes import router as api_router
from ai_qa.api.secrets import router as secrets_router
from ai_qa.api.sessions import router as sessions_router
from ai_qa.api.test_credentials import router as test_credentials_router
from ai_qa.api.test_login import router as test_login_router
from ai_qa.api.threads import router as threads_router
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

    @asynccontextmanager
    async def lifespan(app_inst: FastAPI) -> AsyncGenerator[None]:
        # Ensure SeaweedFS bucket exists
        try:
            import boto3
            from botocore.config import Config
            from botocore.exceptions import ClientError

            s3 = boto3.client(
                "s3",
                endpoint_url=f"{'https' if settings.seaweedfs_secure else 'http'}://{settings.seaweedfs_endpoint}",
                aws_access_key_id=settings.seaweedfs_access_key,
                aws_secret_access_key=settings.seaweedfs_secret_key,
                config=Config(
                    signature_version="s3v4",
                    connect_timeout=settings.s3_connect_timeout,
                    read_timeout=settings.s3_read_timeout,
                    retries={"max_attempts": 0},
                ),
            )
            bucket = settings.seaweedfs_bucket
            try:
                s3.head_bucket(Bucket=bucket)
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") == "404":
                    s3.create_bucket(Bucket=bucket)
        except Exception as e:
            import logging

            logging.warning(f"Failed to initialize SeaweedFS bucket on startup: {e}")

        # Recover work orphaned by a previous process that died mid-run (uvicorn
        # --reload restart, crash, OOM, kill): in-flight pipeline tasks are killed by
        # process death with no exception, leaving threads stuck "processing" (endless
        # UI spinner) and agent_runs "running". Reset them so the UI can recover.
        # Resilient like the SeaweedFS init above — a failure must never block startup.
        try:
            import logging

            from ai_qa.db.session import create_session_factory
            from ai_qa.threads.service import ThreadService

            session = create_session_factory(settings)()
            try:
                threads_reset, runs_reset = ThreadService(session).reconcile_interrupted_work()
                if threads_reset or runs_reset:
                    logging.getLogger(__name__).info(
                        "Startup reconciliation: reset %d interrupted thread(s) and %d run(s)",
                        threads_reset,
                        runs_reset,
                    )
            finally:
                session.close()
        except Exception as e:
            import logging

            logging.warning(f"Failed to reconcile interrupted runs on startup: {e}")

        # Warn early if browser automation cannot work under the current event loop.
        # On Windows, `uvicorn --reload` runs a SelectorEventLoop that cannot spawn the
        # Playwright browser subprocess (Test Login / Sarah explore fail with
        # NotImplementedError). Without --reload, uvicorn uses the ProactorEventLoop.
        try:
            import asyncio
            import logging
            import sys

            running_loop = asyncio.get_running_loop()
            if sys.platform == "win32" and isinstance(running_loop, asyncio.SelectorEventLoop):
                logging.getLogger(__name__).warning(
                    "Event loop is SelectorEventLoop on Windows (likely `uvicorn --reload`): "
                    "browser automation (Test Login, Sarah explore) WILL fail to launch the "
                    "browser. Restart the backend WITHOUT --reload to use the ProactorEventLoop."
                )
        except Exception:  # pragma: no cover - diagnostic only, never blocks startup
            pass
        yield

        # Shutdown: dispose the process-wide pooled DB engines so their connections are
        # returned/closed cleanly (see db/session.py engine cache).
        try:
            from ai_qa.db.session import dispose_all_engines

            dispose_all_engines()
        except Exception as e:  # pragma: no cover - shutdown best-effort
            import logging

            logging.warning(f"Failed to dispose DB engines on shutdown: {e}")

    app = FastAPI(
        title="AI QA Automation API",
        description="Backend API for AI-powered QA test automation pipeline",
        version=settings.docker_image_version,
        lifespan=lifespan,
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

    # Request body-size guard: reject oversized bodies with 413 before they are
    # buffered/parsed into memory. Registered inside CORS but outside auth so the
    # 413 still carries CORS headers and oversized bodies never reach the routes.
    app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=settings.max_request_body_bytes)

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
    # Azure SSO user-login router (Epic 23) — root-level like the local auth router
    # so the FE navigates the browser straight to /auth/sso/login.
    app.include_router(sso_router)

    # REST API routes (protected by auth middleware)
    app.include_router(api_router, prefix="/api")
    app.include_router(projects_router, prefix="/api")
    app.include_router(projects_admin_router, prefix="/api")
    app.include_router(sessions_router, prefix="/api")
    app.include_router(test_credentials_router, prefix="/api")
    app.include_router(test_login_router, prefix="/api")
    app.include_router(executions_router, prefix="/api")
    app.include_router(artifacts_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")
    app.include_router(threads_router, prefix="/api")
    app.include_router(secrets_router, prefix="/api")
    app.include_router(claude_sso_router, prefix="/api")

    # WebSocket endpoint (protected by auth middleware)
    app.add_api_websocket_route("/ws", websocket_endpoint)

    # Static files for production (frontend/dist/)
    # Only mounted if the directory exists
    if _DIST_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(_DIST_DIR), html=True), name="static")

    # Register agents as templates
    # Per-user instances are created on-demand in routes.py via _get_agent_for_user
    from ai_qa.agents import BobAgent, JackAgent, MaryAgent, SarahAgent

    register_agent(AliceAgent())
    register_agent(BobAgent())
    register_agent(MaryAgent())
    register_agent(SarahAgent())
    register_agent(JackAgent())

    return app
