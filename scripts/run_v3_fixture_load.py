#!/usr/bin/env python3
"""Measure the V3 fixture API under concurrent, isolated shopping missions."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from math import ceil
from pathlib import Path
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

import httpx

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data/demo/catalog.v3.jsonl"
QUERY = "预算 1000 元的通勤降噪耳机"
for source_root in (
    "apps/api/src",
    "packages/agent-runtime/src",
    "packages/contracts/generated/python",
    "packages/domain/src",
    "packages/retrieval/src",
):
    sys.path.insert(0, str(ROOT / source_root))

from ragcommerce_api.demo import create_demo_app  # noqa: E402


def percentile(values: list[float], percentile_value: float) -> float:
    return sorted(values)[ceil(len(values) * percentile_value) - 1]


async def mission(client: httpx.AsyncClient, index: int) -> tuple[float, float]:
    user_id = str(uuid5(NAMESPACE_URL, f"ragcommerce-v3-load-{index}"))
    headers = {"X-User-ID": user_id}
    created = await client.post("/v1/threads", headers=headers, json={"goal": QUERY})
    assert created.status_code == 201, created.text
    thread_id = created.json()["thread_id"]

    started = perf_counter()
    accepted = await client.post(
        f"/v1/threads/{thread_id}/turns",
        headers={**headers, "Idempotency-Key": f"fixture-load-{index}"},
        json={"text": QUERY, "media_ids": []},
    )
    turn_ms = (perf_counter() - started) * 1000
    assert accepted.status_code == 202, accepted.text
    run_id = accepted.json()["run_id"]

    sse_started = perf_counter()
    events = await client.get(f"/v1/agent-runs/{run_id}/events", headers=headers)
    sse_ms = (perf_counter() - sse_started) * 1000
    assert events.status_code == 200, events.text
    assert events.text.count("event: completed") == 1
    assert "event: products" in events.text

    snapshot = await client.get(f"/v1/threads/{thread_id}", headers=headers)
    assert snapshot.status_code == 200, snapshot.text
    body = snapshot.json()
    assert body["status"] == "COMPLETED"
    assert len(body["candidates"]) >= 3
    assert all(candidate["evidence_refs"] for candidate in body["candidates"])
    return turn_ms, sse_ms


async def measure() -> dict[str, object]:
    app = create_demo_app(CATALOG)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://fixture") as client:
        results = await asyncio.gather(*(mission(client, index) for index in range(30)))
    turn_values = [value[0] for value in results]
    sse_values = [value[1] for value in results]
    return {
        "schema_version": 1,
        "evidence_level": "fixture_load_only",
        "provider": "deterministic_demo",
        "missions": 30,
        "terminal_events": 30,
        "duplicate_terminal_events": 0,
        "lost_missions": 0,
        "turn_accept_p95_ms": round(percentile(turn_values, 0.95), 3),
        "first_sse_response_p95_ms": round(percentile(sse_values, 0.95), 3),
        "thresholds": {
            "turn_accept_p95_lt_ms": 200,
            "first_sse_response_p95_lt_ms": 1000,
        },
        "claims": {
            "fixture_concurrency_verified": True,
            "real_model_quality_measured": False,
            "live_commerce_quality_measured": False,
            "human_quality_measured": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = asyncio.run(measure())
    if report["turn_accept_p95_ms"] >= 200 or report["first_sse_response_p95_ms"] >= 1000:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
