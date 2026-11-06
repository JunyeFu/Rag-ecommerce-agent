"""Forward HTTP metadata directly, including streaming response bodies."""

import json
import logging
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

LOGGER = logging.getLogger("ragcommerce.api")
LOGGER.setLevel(logging.INFO)
LOGGER.addHandler(logging.StreamHandler())


class DevelopmentAuthHeader:
    def __init__(self, app: ASGIApp, mode: str = "development-header") -> None:
        self.app = app
        self.mode = mode

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Auth-Mode"] = self.mode
            await send(message)

        await self.app(scope, receive, send_with_header)


class StructuredRequestLog:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        trace_id = Headers(scope=scope).get("X-Trace-ID", "").strip() or uuid4().hex

        async def send_with_log(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Trace-ID"] = trace_id
                LOGGER.info(
                    json.dumps(
                        {
                            "event": "http_request",
                            "trace_id": trace_id,
                            "method": scope["method"],
                            "path": scope["path"],
                            "status": message["status"],
                            "duration_ms": round((perf_counter() - started) * 1000, 3),
                        },
                        separators=(",", ":"),
                    )
                )
            await send(message)

        await self.app(scope, receive, send_with_log)
