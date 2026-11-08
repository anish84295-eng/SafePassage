"""Small in-memory request guards for the single-process API deployment."""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestGuardMiddleware:
    """Apply a per-peer request limit and cap streamed HTTP request bodies."""

    def __init__(self, app: ASGIApp, *, rate_enabled: bool, rate_limit: int,
                 window_seconds: int, max_body_bytes: int) -> None:
        self.app = app
        self.rate_enabled = rate_enabled
        self.rate_limit = rate_limit
        self.window_seconds = window_seconds
        self.max_body_bytes = max_body_bytes
        self.requests: dict[str, deque[float]] = defaultdict(deque)
        self.next_cleanup = 0.0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        peer = str(client[0]) if client else "unknown"
        now = time.monotonic()
        if self.rate_enabled:
            if now >= self.next_cleanup:
                cutoff = now - self.window_seconds
                for address, queue in list(self.requests.items()):
                    while queue and queue[0] <= cutoff:
                        queue.popleft()
                    if not queue:
                        del self.requests[address]
                self.next_cleanup = now + self.window_seconds
            recent = self.requests[peer]
            while recent and recent[0] <= now - self.window_seconds:
                recent.popleft()
            if len(recent) >= self.rate_limit:
                await self._error(scope, receive, send, 429, "rate_limited", "Too many requests; please wait before trying again.")
                return
            recent.append(now)

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_body_bytes:
                    await self._error(scope, receive, send, 413, "request_too_large", "Request body exceeds the configured size limit.")
                    return
            except ValueError:
                await self._error(scope, receive, send, 400, "invalid_content_length", "Content-Length must be a valid integer.")
                return

        buffered: deque[Message] = deque()
        consumed = 0
        while True:
            message = await receive()
            buffered.append(message)
            if message["type"] != "http.request":
                break
            consumed += len(message.get("body", b""))
            if consumed > self.max_body_bytes:
                await self._error(scope, receive, send, 413, "request_too_large", "Request body exceeds the configured size limit.")
                return
            if not message.get("more_body", False):
                break

        async def replay_receive() -> Message:
            return buffered.popleft() if buffered else await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _error(scope: Scope, receive: Receive, send: Send, status: int, code: str, message: str) -> None:
        body = json.dumps({"error": {"code": code, "message": message}}).encode("utf-8")
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode("ascii"))]})
        await send({"type": "http.response.body", "body": body})


