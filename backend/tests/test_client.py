"""Small synchronous facade over httpx's supported ASGITransport test API."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx


class TestClient:
    __test__ = False

    def __init__(self, app: Any):
        self.app = app

    def __enter__(self) -> TestClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        content = kwargs.get("content")
        if isinstance(content, httpx.SyncByteStream):
            async def stream_body():
                for chunk in content:
                    yield chunk
            kwargs["content"] = stream_body()

        async def send() -> httpx.Response:
            async with self.app.router.lifespan_context(self.app):
                transport = httpx.ASGITransport(app=self.app)
                async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                    return await client.request(method, url, **kwargs)

        return asyncio.run(send())

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

