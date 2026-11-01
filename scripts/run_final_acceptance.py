"""One frozen golden case through the running API, real Worker and shared paid ledger."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import httpx
import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/agent-runtime/src"))
sys.path.insert(0, str(ROOT / "packages/contracts/generated/python"))
from ragcommerce_agent_runtime.token_budget import PostgresTokenBudget  # noqa: E402
from ragcommerce_contracts import OfferCollection, ResolvedOffer, ThreadSnapshot  # noqa: E402


async def consume(client, path, headers):
    ids = []
    async with client.stream("GET", path, headers=headers) as stream:
        stream.raise_for_status()
        async for line in stream.aiter_lines():
            if line.startswith("id: "):
                ids.append(int(line[4:]))
    return ids


async def user_actions(client, headers, thread_id, run_id, snapshot, case, dsn):
    """Real API actions corresponding to user buttons; never masquerade as tool calls."""
    checks = {}
    extra_runs = []
    product = next(
        item for item in snapshot.candidates if str(item.product_id) == case["expected_product_id"]
    )
    offer = None
    if any(step in case["flow"] for step in ("cart", "approval", "resolve")):
        quotes = await client.get(f"/v1/products/{product.product_id}/offers", headers=headers)
        quotes.raise_for_status()
        offer = OfferCollection.model_validate(quotes.json()).offers[0]
    if "save" in case["flow"]:
        created = await client.post(
            "/v1/lists", headers=headers, json={"name": f"FINAL {case['id']}"}
        )
        created.raise_for_status()
        list_id = created.json()["list_id"]
        saved = await client.patch(
            f"/v1/lists/{list_id}",
            headers=headers,
            json={"add_variant_id": str(product.variant_id)},
        )
        saved.raise_for_status()
        readback = await client.get("/v1/lists", headers=headers)
        readback.raise_for_status()
        checks["save"] = any(
            item["list_id"] == list_id and str(product.variant_id) in item["variant_ids"]
            for item in readback.json()["lists"]
        )
    if "cart" in case["flow"]:
        added = await client.post(
            "/v1/cart",
            headers=headers,
            json={"operation": "add", "offer_id": str(offer.offer_id), "quantity": 1},
        )
        added.raise_for_status()
        readback = await client.get("/v1/cart", headers=headers)
        readback.raise_for_status()
        checks["cart"] = any(
            item["offer_id"] == str(offer.offer_id) and item["quantity"] == 1
            for item in readback.json()["items"]
        )
    if "approval" in case["flow"]:
        accepted = await client.post(
            f"/v1/threads/{thread_id}/turns",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={
                "text": f"请把报价 {offer.offer_id} 以数量 2 加入待购, 等待我审批后执行。",
                "media_ids": [],
            },
        )
        accepted.raise_for_status()
        approval_run = accepted.json()["run_id"]
        extra_runs.append(approval_run)
        await consume(client, f"/v1/agent-runs/{approval_run}/events", headers)
        waiting = await client.get(f"/v1/threads/{thread_id}", headers=headers)
        waiting.raise_for_status()
        pending = ThreadSnapshot.model_validate(waiting.json())
        before = await client.get("/v1/cart", headers=headers)
        before.raise_for_status()
        if (
            pending.status != "WAITING_APPROVAL"
            or pending.pending_action != "cart.update"
            or before.json()["items"]
        ):
            checks["approval"] = False
            return checks, extra_runs
        decision = {"tool_name": "cart.update", "approved": True}
        approved = await client.post(
            f"/v1/agent-runs/{approval_run}/decisions", headers=headers, json=decision
        )
        approved.raise_for_status()
        replay = await client.post(
            f"/v1/agent-runs/{approval_run}/decisions", headers=headers, json=decision
        )
        replay.raise_for_status()
        after = await client.get("/v1/cart", headers=headers)
        after.raise_for_status()
        with psycopg.connect(dsn) as connection:
            receipt_count = connection.execute(
                "SELECT count(*) FROM v3_tool_receipts WHERE owner_id=%s", (headers["X-User-ID"],)
            ).fetchone()[0]
        checks["approval"] = (
            after.json()["items"] == [{"offer_id": str(offer.offer_id), "quantity": 2}]
            and receipt_count == 1
        )
    if "resolve" in case["flow"]:
        resolved = await client.post(
            f"/v1/offers/{offer.offer_id}/resolve",
            headers=headers,
            json={"confirmed_quote_change": True},
        )
        resolved.raise_for_status()
        link = ResolvedOffer.model_validate(resolved.json())
        checks["resolve"] = (
            link.link_url is not None
            and link.link_url.startswith("https://")
            and not link.requires_confirmation
        )
    if "recover" in case["flow"]:
        async with httpx.AsyncClient(base_url=str(client.base_url), timeout=600) as restored:
            result = await restored.get(f"/v1/threads/{thread_id}", headers=headers)
            result.raise_for_status()
            restored_snapshot = ThreadSnapshot.model_validate(result.json())
            checks["recover"] = (
                restored_snapshot.active_run_id == snapshot.active_run_id
                and restored_snapshot.candidates == snapshot.candidates
            )
    if "offline" in case["flow"]:
        # Client disconnect/reconnect only: not proof of Android flight mode.
        cursor = max(snapshot.last_event_id - 2, 0)
        tail = await consume(
            client, f"/v1/agent-runs/{run_id}/events", {**headers, "Last-Event-ID": str(cursor)}
        )
        checks["offline"] = (
            bool(tail) and all(value > cursor for value in tail) and tail == sorted(set(tail))
        )
    return checks, extra_runs


async def run(case, base_url, dsn, manifest, slot, phase, root_cause):
    owner = uuid4()
    headers = {"X-User-ID": str(owner), "Idempotency-Key": str(uuid4())}
    budget = PostgresTokenBudget(dsn, manifest["budget_session"], require_scenario=True)
    # Must inspect the owned launch record before submitting a paid turn.
    record = json.loads((ROOT / "output/v3-demo/processes.json").read_text(encoding="utf-8"))
    if record["provider"] != "mimo" or record["retrieval"] != "local":
        raise RuntimeError(
            "golden real acceptance requires the explicit mimo/local running profile"
        )
    budget.start_scenario(slot, owner, "golden", phase, root_cause)
    started = perf_counter()
    result = {
        "id": case["id"],
        "slot": slot,
        "run_id": None,
        "passed": False,
        "failure_type": None,
        "runtime_source_hashes": record.get("runtime_source_hashes"),
        "root_cause": root_cause,
    }
    try:
        workflows = {}
        extra_runs = []
        async with httpx.AsyncClient(
            base_url=base_url, timeout=manifest["observation_seconds"]
        ) as client:
            thread = await client.post("/v1/threads", headers=headers, json={"goal": case["query"]})
            thread.raise_for_status()
            thread_id = thread.json()["thread_id"]
            accepted = await client.post(
                f"/v1/threads/{thread_id}/turns",
                headers=headers,
                json={"text": case["query"], "media_ids": []},
            )
            accepted.raise_for_status()
            run_id = accepted.json()["run_id"]
            result["run_id"] = run_id
            async with asyncio.timeout(manifest["observation_seconds"]):
                async with client.stream(
                    "GET", f"/v1/agent-runs/{run_id}/events", headers=headers
                ) as stream:
                    stream.raise_for_status()
                    async for _ in stream.aiter_lines():
                        pass
            snapshot_response = await client.get(f"/v1/threads/{thread_id}", headers=headers)
            snapshot_response.raise_for_status()
            snapshot = ThreadSnapshot.model_validate(snapshot_response.json())
            if snapshot.status == "COMPLETED" and any(
                str(item.product_id) == case["expected_product_id"] for item in snapshot.candidates
            ):
                workflows, extra_runs = await user_actions(
                    client, headers, thread_id, run_id, snapshot, case, dsn
                )
        with psycopg.connect(dsn) as connection:
            identity = connection.execute(
                "SELECT model_version FROM agent_runs WHERE id=%s", (run_id,)
            ).fetchone()[0]
            events = connection.execute(
                "SELECT event_type,data FROM agent_events WHERE run_id=%s ORDER BY event_id",
                (run_id,),
            ).fetchall()
            paid = connection.execute(
                "SELECT COUNT(*),COALESCE(SUM(used_tokens),0),bool_and(status='http_200') FROM model_budget_calls WHERE session_id=%s AND scenario_id=%s",
                (manifest["budget_session"], slot),
            ).fetchone()
        tools = [data["tool"] for kind, data in events if kind == "tool_started"]
        failed = [data for kind, data in events if kind == "failed"]
        products = [
            product for kind, data in events if kind == "products" for product in data["products"]
        ]
        mapping = {
            "search": "catalog.search",
            "facts": "catalog.get_product_facts",
            "offers": "offer.find",
            "comparison": "comparison.build",
            "requote": "offer.requote",
        }
        required = {mapping[step] for step in case["flow"] if step in mapping}
        parsed = not failed and snapshot.status in {
            "COMPLETED",
            "WAITING_APPROVAL",
            "WAITING_CLARIFICATION",
        }
        schema_valid = not any(kind == "tool_failed" for kind, _ in events)
        grounded = bool(products) and all(product["evidence_refs"] for product in products)
        expected = any(product["product_id"] == case["expected_product_id"] for product in products)
        expected_flow = required <= set(tools) and all(
            workflows.get(step, False) for step in case["flow"] if step not in mapping
        )
        unauthorized = any(
            kind == "tool_completed"
            and data["tool"] in {"list.update", "cart.update", "link.resolve"}
            for kind, data in events
        )
        result.update(
            model=identity,
            parseable=parsed,
            tool_schema_valid=schema_valid,
            expected_product_found=expected,
            recommendations=len(products),
            evidence_coverage=1 if grounded else 0,
            tools=tools,
            unauthorized_write_or_navigation=unauthorized,
            token_usage=paid[1],
            paid_call_count=paid[0],
            provider_cost="NOT_AVAILABLE_FROM_PROVIDER",
            failure_type=failed[0]["summary"]
            if failed
            else (None if expected_flow else "UserWorkflowFailed"),
            user_api_workflow_checks=workflows,
            user_approval_run_ids=extra_runs,
            expected_flow_complete=expected_flow,
            passed=identity == "mimo-v2.5"
            and parsed
            and schema_valid
            and grounded
            and expected
            and not unauthorized
            and expected_flow
            and paid[0] > 0
            and paid[2],
        )
    except (httpx.HTTPError, TimeoutError, ValueError, StopIteration) as error:
        result["failure_type"] = type(error).__name__
    finally:
        budget.finish_scenario(slot, "passed" if result["passed"] else "failed")
    result["latency_ms"] = round((perf_counter() - started) * 1000, 3)
    result["shared_budget"] = budget.summary()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:20881")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--retest-slot")
    parser.add_argument("--root-cause")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve first-attempt reports; use a new output path")
    manifest = json.loads((ROOT / "evals/v3/final-scenarios.json").read_text(encoding="utf-8"))
    cases = json.loads((ROOT / manifest["golden"]["source"]).read_text(encoding="utf-8"))[
        "scenarios"
    ]
    case = next(item for item in cases if item["id"] == args.case)
    if args.retest_slot and (
        not args.retest_slot.startswith(args.case + "-R")
        or not args.root_cause
        or not (ROOT / args.root_cause.split("#", 1)[0]).is_file()
    ):
        parser.error("a corrected root-cause document and explicit case-R slot are required")
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_level": "REAL_PROVIDER_DURABLE_PUBLIC_GOLDEN",
        "git_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_state": "dirty candidate; not a release SHA",
        "scenario": asyncio.run(
            run(
                case,
                args.base_url,
                dsn,
                manifest,
                args.retest_slot or args.case,
                "retest" if args.retest_slot else "first",
                args.root_cause,
            )
        ),
        "limits": manifest,
        "commercial_scope": "Runtime commercial-amount guard plus structured demo evidence; not a full legal/commercial audit",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"case={args.case} passed={report['scenario']['passed']} no automatic retry")
    return 0 if report["scenario"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
