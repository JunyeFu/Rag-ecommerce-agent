import asyncio
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from ragcommerce_api.demo import create_demo_app


def test_pending_job_feedback_never_advances_sse_cursor():
    app = create_demo_app(Path(__file__).resolve().parents[3] / "data/demo/catalog.v3.jsonl")
    app.state.execute_background = False
    headers = {"X-User-ID": str(uuid4()), "Idempotency-Key": "pending-progress"}
    with TestClient(app) as client:
        thread = client.post(
            "/v1/threads", headers=headers, json={"goal": "预算800元的耳机"}
        ).json()
        run = client.post(
            f"/v1/threads/{thread['thread_id']}/turns",
            headers=headers,
            json={"text": "预算800元的耳机", "media_ids": []},
        ).json()
    endpoint = next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", "") == "/v1/agent-runs/{run_id}/events"
    )

    async def first():
        response = await endpoint(UUID(run["run_id"]), "0", headers["X-User-ID"])
        block = await anext(response.body_iterator)
        await response.body_iterator.aclose()
        return block

    block = asyncio.run(first())
    assert '"stage":"queued"' in block
    assert "id:" not in block
