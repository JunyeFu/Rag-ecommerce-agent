"""HTTP metadata must not buffer SSE or turn contract failures into success."""

import asyncio
import json
import os
import subprocess
import sys
from uuid import UUID

import httpx
import pytest
from fastapi.responses import StreamingResponse
from ragcommerce_api.app import create_app
from ragcommerce_api.observability import configure_observability


def test_http_headers_and_structured_log_survive_validation_errors(caplog):
    app = create_app()
    configure_observability(app)

    async def execute():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post(
                "/v1/threads", json={"goal": "headphones"}, headers={"X-Trace-ID": "fixture-trace"}
            )

    with caplog.at_level("INFO", logger="ragcommerce.api"):
        response = asyncio.run(execute())
    assert response.status_code == 401
    assert response.headers["X-Auth-Mode"] == "development-header"
    assert response.headers["X-Trace-ID"] == "fixture-trace"
    record = json.loads(caplog.records[-1].message)
    assert (record["status"], record["trace_id"], record["path"]) == (
        401,
        "fixture-trace",
        "/v1/threads",
    )


def test_sse_first_chunk_is_delivered_before_stream_completion():
    app = create_app()
    configure_observability(app)

    async def execute():
        first_chunk = asyncio.Event()
        finish = asyncio.Event()
        messages = []

        @app.get("/stream-test")
        async def stream_test():
            async def stream():
                yield "event: progress\ndata: queued\n\n"
                await finish.wait()
                yield "event: completed\ndata: done\n\n"

            return StreamingResponse(stream(), media_type="text/event-stream")

        async def receive():
            await asyncio.Event().wait()

        async def send(message):
            messages.append(message)
            if message["type"] == "http.response.body" and message.get("body"):
                first_chunk.set()

        task = asyncio.create_task(
            app(
                {
                    "type": "http",
                    "asgi": {"spec_version": "2.4"},
                    "method": "GET",
                    "scheme": "http",
                    "path": "/stream-test",
                    "raw_path": b"/stream-test",
                    "query_string": b"",
                    "headers": [],
                    "server": ("test", 80),
                    "client": ("test", 1),
                    "http_version": "1.1",
                },
                receive,
                send,
            )
        )
        try:
            await asyncio.wait_for(first_chunk.wait(), 2)
            assert not task.done()
            headers = dict(messages[0]["headers"])
            assert headers[b"x-auth-mode"] == b"development-header"
            UUID(headers[b"x-trace-id"].decode())
        finally:
            finish.set()
            await task
        assert (
            b"".join(m.get("body", b"") for m in messages)
            == b"event: progress\ndata: queued\n\nevent: completed\ndata: done\n\n"
        )

    asyncio.run(execute())


def test_unknown_application_error_is_not_silently_recovered():
    app = create_app()
    configure_observability(app)

    @app.get("/broken-contract")
    async def broken_contract():
        raise ValueError("invalid internal contract")

    async def execute():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get("/broken-contract")

    with pytest.raises(ValueError, match="invalid internal contract"):
        asyncio.run(execute())


def test_request_log_is_emitted_without_collector_or_external_logging_config():
    script = """
import asyncio, httpx
from ragcommerce_api.app import create_app
from ragcommerce_api.observability import configure_observability
app = create_app()
configure_observability(app)
async def request():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/health')
        assert response.status_code == 200
asyncio.run(request())
"""
    process = subprocess.run(
        [sys.executable, "-c", script],
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(sys.path),
            "OTEL_EXPORTER_OTLP_ENDPOINT": "",
        },
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    lines = [json.loads(line) for line in process.stderr.splitlines() if line.startswith("{")]
    assert len(lines) == 1
    assert (lines[0]["event"], lines[0]["path"], lines[0]["status"]) == (
        "http_request",
        "/health",
        200,
    )
