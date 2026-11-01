"""Measure a running persistent API/Worker; never substitute an in-process fixture."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import httpx
import psycopg


def percentile(values: list[float], fraction: float) -> float:
    from math import ceil

    return sorted(values)[ceil(len(values) * fraction) - 1]


async def mission(client: httpx.AsyncClient) -> dict[str, object]:
    user_id = str(uuid4())
    headers = {"X-User-ID": user_id, "Idempotency-Key": str(uuid4())}
    response = await client.post(
        "/v1/threads", headers=headers, json={"goal": "预算1000元的通勤降噪耳机"}
    )
    response.raise_for_status()
    thread_id = response.json()["thread_id"]
    started = perf_counter()
    response = await client.post(
        f"/v1/threads/{thread_id}/turns",
        headers=headers,
        json={"text": "预算1000元的通勤降噪耳机", "media_ids": []},
    )
    assert response.status_code == 202, response.status_code
    accepted_at = perf_counter()
    accepted_ms = (accepted_at - started) * 1000
    run_id = response.json()["run_id"]
    first_ms = None
    worker_started_ms = None
    first_stage = None
    kind = None
    terminal = []
    async with client.stream("GET", f"/v1/agent-runs/{run_id}/events", headers=headers) as stream:
        stream.raise_for_status()
        async for line in stream.aiter_lines():
            if line.startswith("event:"):
                if first_ms is None:
                    first_ms = (perf_counter() - accepted_at) * 1000
                kind = line.split(":", 1)[1].strip()
                if kind in {"completed", "failed"}:
                    terminal.append(kind)
            elif line.startswith("data:"):
                payload = json.loads(line.split(":", 1)[1])
                if first_stage is None:
                    first_stage = payload.get("stage", kind)
                if kind == "progress" and payload.get("stage") == "run_started":
                    worker_started_ms = (perf_counter() - started) * 1000
    snapshot = await client.get(f"/v1/threads/{thread_id}", headers=headers)
    snapshot.raise_for_status()
    return {
        "run_id": run_id,
        "user_id": user_id,
        "thread_id": thread_id,
        "accepted_ms": accepted_ms,
        "first_state_ms": first_ms,
        "first_public_stage": first_stage,
        "worker_started_ms": worker_started_ms,
        "terminal": terminal,
        "snapshot_status": snapshot.json()["status"],
    }


async def measure(base_url: str, dsn: str) -> dict[str, object]:
    # This command is only for an isolated persistent fixture worker, not paid model load.
    async with httpx.AsyncClient(base_url=base_url, timeout=120) as client:
        results = await asyncio.gather(*(mission(client) for _ in range(30)))
    with psycopg.connect(dsn) as connection:
        rows = connection.execute(
            "SELECT id, model_version FROM agent_runs WHERE id = ANY(%s::uuid[])",
            ([row["run_id"] for row in results],),
        ).fetchall()
        terminal_rows = connection.execute(
            """SELECT run_id, count(*), bool_and(event_type = 'completed')
               FROM agent_events WHERE run_id = ANY(%s::uuid[])
               AND event_type IN ('completed', 'failed') GROUP BY run_id""",
            ([row["run_id"] for row in results],),
        ).fetchall()
    database_matches = len(rows) == 30
    fixture_only = all(row[1] == "deterministic-demo" for row in rows)
    persisted_terminal_once = len(terminal_rows) == 30 and all(
        count == 1 and succeeded for _, count, succeeded in terminal_rows
    )
    completed = sum(
        row["terminal"] == ["completed"] and row["snapshot_status"] == "COMPLETED"
        for row in results
    )
    accept_p95 = percentile([row["accepted_ms"] for row in results], 0.95)
    state_p95 = percentile([row["first_state_ms"] for row in results], 0.95)
    passed = (
        database_matches
        and fixture_only
        and persisted_terminal_once
        and completed == 30
        and accept_p95 < 200
        and state_p95 < 1000
    )
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_level": "durable_fixture_worker_load",
        "missions": 30,
        "completed": completed,
        "database_matches": database_matches,
        "fixture_only": fixture_only,
        "turn_accept_p95_ms": accept_p95,
        "persisted_terminal_once": persisted_terminal_once,
        "first_state_p95_ms": state_p95,
        "passed": passed,
        "results": results,
        "worker_started_p95_ms": percentile([row["worker_started_ms"] for row in results], 0.95),
        "first_state_definition": "Time from receipt of HTTP 202 to first public SSE state, including database-backed queued feedback without a cursor ID. Worker execution latency is measured from Turn submission and reported separately.",
        "limitations": [
            "Not real-provider capacity; no production throughput claim.",
            "Failure injection and restart acceptance are separate checks.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--batches", type=int, choices=[1, 10], default=1)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preserve previous results; choose a new report path")
    import os

    dsn = os.environ["API_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)

    async def execute():
        if args.batches == 1:
            return await measure(args.base_url, dsn)
        batches = []
        for batch in range(10):
            result = await measure(args.base_url, dsn)
            result["batch"] = batch + 1
            batches.append(result)
            print(f"batch={batch + 1} passed={result['passed']}", flush=True)
        results = [item for batch in batches for item in batch["results"]]
        return {
            "created_at": datetime.now(UTC).isoformat(),
            "evidence_level": "durable_fixture_worker_load_10_sequential_batches",
            "batch_count": 10,
            "concurrency_per_batch": 30,
            "missions": 300,
            "completed": sum(batch["completed"] for batch in batches),
            "passed": all(batch["passed"] for batch in batches),
            "turn_accept_p95_ms": percentile([r["accepted_ms"] for r in results], 0.95),
            "first_state_p95_ms": percentile([r["first_state_ms"] for r in results], 0.95),
            "worker_started_p95_ms": percentile([r["worker_started_ms"] for r in results], 0.95),
            "percentile_method": "Nearest rank ceil(n*p), all 300 samples; per-batch p95 retained",
            "first_state_definition": batches[0]["first_state_definition"],
            "batches": batches,
            "limitations": [
                "Explicit fake provider; not real-model or production capacity",
                "Each batch executes once; no failed-batch retry",
            ],
        }

    report = asyncio.run(execute())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"durable_load={'pass' if report['passed'] else 'fail'} missions={report['missions']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
