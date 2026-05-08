"""AI QA Automation API package.

Provides FastAPI application and WebSocket support for the
conversational chat UI pipeline.
"""

from ai_qa.api.app import create_app
from ai_qa.config import AppSettings

# Create default app instance for uvicorn
app = create_app(AppSettings())

__all__ = ["create_app", "app"]
