"""Real child-process interruption after a committed tool, using an isolated DB.

Explicit fake planner; production TurnWorker/claim/checkpoint/commerce receipts.
The five-minute lease elapses naturally, never by changing its timestamp.
This is platform fault injection, not an Android or real-model acceptance slot.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import psycopg

ROOT = Path(__file__).resolve().parents[1]
for entry in (
    "apps/api/src",
    "apps/worker/src",
    "packages/agent-runtime/src",
    "packages/domain/src",
    "packages/retrieval/src",
    "packages/contracts/generated/python",
):
    sys.path.insert(0, str(ROOT / entry))

from ragcommerce_agent_runtime import (  # noqa: E402
    PostgresCheckpointStore,
    RuntimeIdentity,
    ScriptedPlanner,
    ShoppingAgent,
    ToolCall,
    ToolRegistry,
)
from ragcommerce_api.media import InMemoryMediaStore  # noqa: E402
from ragcommerce_api.postgres_demo import PostgresDemoCommerce  # noqa: E402
from ragcommerce_api.postgres_index import PostgresTurnIndex  # noqa: E402
from ragcommerce_api.service import TurnService  # noqa: E402
from ragcommerce_worker import TurnWorker  # noqa: E402


def service(dsn: str, interrupt: bool = False) -> TurnService:
    commerce = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn)
    handlers = commerce.tool_handlers()
    offer = next(iter(commerce.offers))
    durable_cart = handlers["cart.update"]

    def pause_after_commit(context, args):
        result = durable_cart(context, args)
        if interrupt:
            # Parent observes the committed receipt before terminating this child.
            time.sleep(600)
        return result

    handlers["cart.update"] = pause_after_commit
    agent = ShoppingAgent(
        ScriptedPlanner(
            (
                ToolCall(
                    "cart.update",
                    {
                        "operation": "add",
                        "offer_id": str(offer),
                        "quantity": 2,
                    },
                ),
            )
        ),
        ToolRegistry(handlers),
        PostgresCheckpointStore(dsn),
        RuntimeIdentity(
            "final-recovery-fixture", "explicit-fake", "fault-injection", "v3", "0.2.0"
        ),
    )
    return TurnService(agent, InMemoryMediaStore(), PostgresTurnIndex(dsn))


async def child(dsn: str, interrupt: bool, run_id: UUID) -> None:
    worker_service = service(dsn, interrupt)
    deadline = time.monotonic() + 345
    while time.monotonic() < deadline:
        if await TurnWorker(worker_service.index, worker_service).run_once():
            record = worker_service.index.get_run(run_id)
            if record.execution_status == "COMPLETED":
                return
        await asyncio.sleep(0.25)
    raise TimeoutError("production lease was not reclaimed within its observation window")


async def parent(dsn: str) -> dict:
    with psycopg.connect(dsn) as connection:
        # Keep this independent DB exclusive to the fault-injection exercise.
        if connection.execute(
            "SELECT count(*) FROM api_turns WHERE status IN ('PENDING','RETRY','RUNNING')"
        ).fetchone()[0]:
            raise RuntimeError("isolated recovery DB already has active work; preserve it")
    application = service(dsn)
    owner = uuid4()
    thread = application.create_thread(owner, "explicit platform recovery fixture")
    record, _ = await application.submit(owner, thread.id, str(uuid4()), thread.goal, ())
    # The production approval service binds the exact invocation and freezes its args.
    # This explicit fixture approval is separate from native user approval acceptance.
    assert await TurnWorker(application.index, application).run_once()
    assert application.index.get_run(record.run_id).execution_status == "WAITING_APPROVAL"
    accepted = await application.decide(owner, record.run_id, "cart.update", True)
    assert accepted.execution_status == "PENDING"
    started = time.monotonic()
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child",
        "--run",
        str(record.run_id),
    ]
    first = subprocess.Popen([*command, "--interrupt"], cwd=ROOT, env=os.environ.copy())
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            with psycopg.connect(dsn) as connection:
                receipts = connection.execute(
                    "SELECT count(*) FROM v3_tool_receipts WHERE owner_id=%s", (owner,)
                ).fetchone()[0]
                cursor = connection.execute(
                    "SELECT max(event_id) FROM agent_events WHERE run_id=%s", (record.run_id,)
                ).fetchone()[0]
            if receipts == 1:
                break
            if first.poll() is not None:
                raise RuntimeError("child exited before a committed business receipt")
            await asyncio.sleep(0.1)
        else:
            raise TimeoutError("committed tool receipt not observed")
        first.terminate()
        first.wait(timeout=10)
        with psycopg.connect(dsn) as connection:
            before = connection.execute(
                "SELECT quantity,updated_at FROM v3_cart_items WHERE owner_id=%s", (owner,)
            ).fetchone()
        second = subprocess.Popen(command, cwd=ROOT, env=os.environ.copy())
        try:
            while second.poll() is None:
                await asyncio.sleep(1)
            if second.returncode != 0:
                raise RuntimeError("replacement Worker failed")
        finally:
            if second.poll() is None:
                second.terminate()
                second.wait(timeout=10)
        with psycopg.connect(dsn) as connection:
            after = connection.execute(
                "SELECT quantity,updated_at FROM v3_cart_items WHERE owner_id=%s", (owner,)
            ).fetchone()
            rows = connection.execute(
                "SELECT event_id,event_type FROM agent_events WHERE run_id=%s ORDER BY event_id",
                (record.run_id,),
            ).fetchall()
            receipts = connection.execute(
                "SELECT count(*) FROM v3_tool_receipts WHERE owner_id=%s", (owner,)
            ).fetchone()[0]
            status = connection.execute(
                "SELECT status FROM api_turns WHERE run_id=%s", (record.run_id,)
            ).fetchone()[0]
        replay = application.agent.replay(record.run_id)
        tail = [event.id for event in replay if event.id > cursor]
        checks = {
            "committed_write_not_repeated": before == after and before[0] == 2,
            "one_tool_receipt": receipts == 1,
            "one_terminal_event": sum(kind == "completed" for _, kind in rows) == 1,
            "recovered_event_recorded": any(kind == "run_resumed" for _, kind in rows),
            "durable_status_completed": status == "COMPLETED",
            "cursor_replay_exact": tail == [event_id for event_id, _ in rows if event_id > cursor],
        }
        return {
            "created_at": datetime.now(UTC).isoformat(),
            "evidence_level": "REAL_POSTGRES_CHILD_PROCESS_FAILURE_EXPLICIT_FAKE",
            "database": dsn.rsplit("/", 1)[-1],
            "run_id": str(record.run_id),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "lease_seconds": 300,
            "lease_clock_modified": False,
            "first_child_terminated_after_committed_receipt": first.returncode is not None,
            "cursor_before_interruption": cursor,
            "checks": checks,
            "passed": all(checks.values()),
            "limitations": [
                "Cursor replay verified against persistent event log; this exercise is not an HTTP SSE reconnect test.",
                "Cart command is approved through the production service by an explicit fixture; native approval UI is accepted separately.",
            ],
        }
    finally:
        if first.poll() is None:
            first.terminate()
            first.wait(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--interrupt", action="store_true")
    parser.add_argument("--run", type=UUID)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    if args.child:
        asyncio.run(child(dsn, args.interrupt, args.run))
        return 0
    if not args.output or args.output.exists():
        parser.error("provide a new report path; existing evidence is preserved")
    report = asyncio.run(parent(dsn))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"recovery passed={report['passed']} elapsed={report['elapsed_seconds']}s")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
