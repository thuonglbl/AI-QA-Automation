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

    uvicorn.run(
        app,
        host=settings.server_host,
        port=settings.server_port,
        log_level="info",
    )


if __name__ == "__main__":
    run()
