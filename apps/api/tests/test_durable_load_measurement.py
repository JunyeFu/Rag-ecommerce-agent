"""Latency oracle: SSE starts at the 202 response, not request submission."""

import asyncio
import runpy
from pathlib import Path

import httpx
import pytest
from ragcommerce_api.app import create_app
from ragcommerce_api.demo import create_demo_app


def test_measurement_mission_uses_production_installation_identity():
    root = Path(__file__).resolve().parents[3]
    mission = runpy.run_path(str(root / "scripts/run_v3_durable_load.py"))["mission"]
    fixture = create_demo_app(root / "data/demo/catalog.v3.jsonl")
    app = create_app(
        fixture.state.turn_service,
        fixture.state.media_store,
        commerce=fixture.state.commerce,
        installation_store=fixture.state.installations,
    )

    async def execute():
        async with httpx.AsyncClient(
            base_url="https://test.invalid", transport=httpx.ASGITransport(app=app)
        ) as client:
            return await mission(client)

    result = asyncio.run(execute())
    assert result["terminal"] == ["completed"]
    assert result["snapshot_status"] == "COMPLETED"
    assert "token" not in result


def test_first_public_state_excludes_turn_acceptance_time():
    harness = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "scripts/run_v3_durable_load.py")
    )
    mission = harness["mission"]
    clock = iter([0.0, 0.15, 0.4, 0.5])
    mission.__globals__["perf_counter"] = lambda: next(clock)

    def respond(request):
        if request.url.path == "/v1/installations":
            return httpx.Response(201, json={"owner_id": "owner", "token": "test-only"})
        assert request.headers["Authorization"] == "Bearer test-only"
        assert "X-User-ID" not in request.headers
        if request.url.path == "/v1/threads":
            return httpx.Response(201, json={"thread_id": "thread"})
        if request.url.path.endswith("/turns"):
            return httpx.Response(202, json={"run_id": "run"})
        if request.url.path.endswith("/events"):
            return httpx.Response(
                200,
                text='event: progress\ndata: {"stage":"run_started"}\n\nevent: completed\ndata: {}\n\n',
            )
        return httpx.Response(200, json={"status": "COMPLETED"})

    async def execute():
        async with httpx.AsyncClient(
            base_url="https://test.invalid", transport=httpx.MockTransport(respond)
        ) as client:
            return await mission(client)

    result = asyncio.run(execute())
    assert result["accepted_ms"] == pytest.approx(150)
    assert result["first_state_ms"] == pytest.approx(250)
    assert result["worker_started_ms"] == pytest.approx(500)
