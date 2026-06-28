"""Application-level request body-size guard (pure ASGI middleware).

Rejects requests whose body exceeds a configurable maximum with
``413 Request Entity Too Large`` *before* the body is buffered and parsed into
memory. This is the hardening that endpoint-level checks (e.g. the
session-import ``storageState`` cap in :mod:`ai_qa.api.sessions`) cannot provide
on their own, because those run only after Starlette/Pydantic has already read
the whole body.

Two layers of defence:

1. **Fast path** — a ``Content-Length`` header that already exceeds the cap is
   rejected without reading a single body byte.
2. **Streaming guard** — for chunked uploads (no, or an under-reported,
   ``Content-Length``) the body bytes are counted as they arrive and the request
   is aborted with 413 the moment the cap is crossed.

WebSocket and lifespan scopes pass straight through untouched (they carry no
buffered HTTP body). The middleware is registered inside CORS but outside auth so
the 413 still carries CORS headers while oversized bodies never reach — nor are
buffered by — the protected routes.
"""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_TOO_LARGE_BODY = b'{"detail":"Request body too large."}'


class _BodyTooLargeError(Exception):
    """Internal signal raised from the wrapped ``receive`` once the cap is crossed."""


async def _send_413(send: Send) -> None:
    """Emit a minimal JSON 413 response over the ASGI ``send`` channel."""
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_TOO_LARGE_BODY)).encode("latin-1")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _TOO_LARGE_BODY})


class BodySizeLimitMiddleware:
    """Reject requests whose body exceeds ``max_body_bytes`` with HTTP 413."""

    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            # WebSocket upgrades, lifespan events, etc. carry no buffered HTTP body.
            await self.app(scope, receive, send)
            return

        # Fast path: a declared Content-Length over the cap is rejected up front,
        # before a single body byte is read into memory.
        declared = Headers(scope=scope).get("content-length")
        if declared is not None:
            try:
                if int(declared) > self.max_body_bytes:
                    await _send_413(send)
                    return
            except ValueError:
                # Malformed header — fall through to the streaming guard.
                pass

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise _BodyTooLargeError()
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _BodyTooLargeError:
            # Only safe to emit our own response if the app has not started one;
            # otherwise the partial response is already on the wire — re-raise so
            # the server tears the connection down rather than corrupting it.
            if response_started:
                raise
            await _send_413(send)
