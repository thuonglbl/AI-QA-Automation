"""AI QA Automation API package.

Provides FastAPI application and WebSocket support for the
conversational chat UI pipeline.
"""

from ai_qa.api.app import create_app

__all__ = ["create_app"]
