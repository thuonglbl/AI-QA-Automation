"""Tests for the application-level request body-size guard.

Two layers are covered:

* Unit tests drive :class:`BodySizeLimitMiddleware` directly over crafted ASGI
  scopes/messages — deterministic proof of the Content-Length fast path, the
  streaming guard, pass-through under the cap, and websocket bypass.
* Integration tests drive the real app built by ``create_app`` to prove the
  middleware is wired in (oversized → 413) and does not interfere with normal,
  under-cap traffic (still routed through to auth).
"""

import uuid
from collections.abc import Generator
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from starlette.types import Message, Receive, Scope, Send

from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.body_size_limit import BodySizeLimitMiddleware
from ai_qa.config import AppSettings


class _SendRecorder:
    """Collects ASGI response messages so a test can assert on status/body."""

    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def __call__(self, message: Message) -> None:
        self.messages.append(message)

    @property
    def status(self) -> int | None:
        for message in self.messages:
            if message["type"] == "http.response.start":
                status: int = message["status"]
                return status
        return None

    @property
    def body(self) -> bytes:
        return b"".join(
            m.get("body", b"") for m in self.messages if m["type"] == "http.response.body"
        )


def _receive_from(messages: list[Message]) -> Receive:
    queue = list(messages)

    async def receive() -> Message:
        return queue.pop(0)

    return receive


def _http_scope(headers: list[tuple[bytes, bytes]] | None = None) -> Scope:
    return {
        "type": "http",
        "method": "POST",
        "path": "/whatever",
        "headers": headers or [],
    }


async def _draining_app(scope: Scope, receive: Receive, send: Send) -> None:
    """Inner app that fully drains the request body, then returns 200.

    Draining is what exercises the streaming guard: each ``receive()`` runs
    through the middleware's wrapper, which raises once the cap is crossed.
    """
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return
        if message["type"] == "http.request" and not message.get("more_body", False):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


class TestBodySizeLimitMiddlewareUnit:
    async def test_content_length_over_cap_rejected_without_reading_body(self) -> None:
        called: bool = False

        async def inner(scope: Scope, receive: Receive, send: Send) -> None:
            nonlocal called
            called = True

        mw = BodySizeLimitMiddleware(inner, max_body_bytes=100)
        recorder = _SendRecorder()
        scope = _http_scope([(b"content-length", b"101")])
        await mw(scope, _receive_from([]), recorder)

        assert recorder.status == 413
        assert b"too large" in recorder.body.lower()
        # The inner app must never run for an over-declared body.
        assert not called

    async def test_streaming_body_over_cap_rejected(self) -> None:
        mw = BodySizeLimitMiddleware(_draining_app, max_body_bytes=10)
        recorder = _SendRecorder()
        # No Content-Length header → fast path is skipped; chunks total 12 > 10.
        messages: list[Message] = [
            {"type": "http.request", "body": b"123456", "more_body": True},
            {"type": "http.request", "body": b"789012", "more_body": False},
        ]
        await mw(_http_scope(), _receive_from(messages), recorder)

        assert recorder.status == 413
        assert b"too large" in recorder.body.lower()

    async def test_body_under_cap_passes_through(self) -> None:
        mw = BodySizeLimitMiddleware(_draining_app, max_body_bytes=100)
        recorder = _SendRecorder()
        messages: list[Message] = [
            {"type": "http.request", "body": b"small", "more_body": False},
        ]
        await mw(_http_scope([(b"content-length", b"5")]), _receive_from(messages), recorder)

        assert recorder.status == 200
        assert recorder.body == b"ok"

    async def test_malformed_content_length_falls_back_to_streaming_guard(self) -> None:
        mw = BodySizeLimitMiddleware(_draining_app, max_body_bytes=10)
        recorder = _SendRecorder()
        messages: list[Message] = [
            {"type": "http.request", "body": b"x" * 50, "more_body": False},
        ]
        # Bogus header must not crash the fast path; the streaming guard still fires.
        await mw(
            _http_scope([(b"content-length", b"not-a-number")]), _receive_from(messages), recorder
        )

        assert recorder.status == 413

    async def test_websocket_scope_passes_through_untouched(self) -> None:
        seen: dict[str, Any] = {}

        async def inner(scope: Scope, receive: Receive, send: Send) -> None:
            seen["scope"] = scope

        mw = BodySizeLimitMiddleware(inner, max_body_bytes=1)
        scope: Scope = {"type": "websocket", "path": "/ws"}
        await mw(scope, _receive_from([]), _SendRecorder())

        assert seen["scope"]["type"] == "websocket"


def _app_with_limit(session_factory: sessionmaker[Session], limit: int) -> FastAPI:
    """Build the real app with a small body cap and the test DB dependency wired in."""
    settings = AppSettings().model_copy(update={"max_request_body_bytes": limit})
    app: FastAPI = create_app(settings)

    def override_get_db_session() -> Generator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session_dependency] = override_get_db_session
    return app


class TestBodySizeLimitMiddlewareIntegration:
    def test_oversized_request_rejected_with_413(
        self, _session_factory: sessionmaker[Session]
    ) -> None:
        app = _app_with_limit(_session_factory, 2048)
        with TestClient(app) as client:
            payload = {
                "environment": "e",
                "role": "r",
                "storage_state": {"cookies": [{"name": "big", "value": "x" * 5000}]},
            }
            # No token: the guard fires before auth, so an oversized body is 413
            # regardless of authentication.
            resp = client.post(f"/api/projects/{uuid.uuid4()}/sessions/import", json=payload)
        assert resp.status_code == 413
        assert resp.json()["detail"] == "Request body too large."

    def test_small_request_passes_through_to_app(
        self, _session_factory: sessionmaker[Session]
    ) -> None:
        app = _app_with_limit(_session_factory, 8 * 1024 * 1024)
        with TestClient(app) as client:
            resp = client.get(f"/api/projects/{uuid.uuid4()}/sessions")
        # The middleware let the (bodyless) request through; auth then rejected it.
        assert resp.status_code != 413
        assert resp.status_code == 401
