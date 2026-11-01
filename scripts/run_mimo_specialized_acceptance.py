#!/usr/bin/env python3
"""Run one-shot MiMo acceptance for clarification, requote, and approved writes."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
for relative in (
    "apps/api/src",
    "packages/agent-runtime/src",
    "packages/contracts/generated/python",
    "packages/retrieval/src",
):
    sys.path.insert(0, str(ROOT / relative))

from ragcommerce_agent_runtime import (  # noqa: E402
    OpenAICompatibleProvider,
    ToolCall,
    ToolDenied,
    ToolExecutionContext,
    ToolRegistry,
    ToolResult,
    TurnCommand,
)
from ragcommerce_api.demo import DemoCommerce  # noqa: E402
from ragcommerce_api.provider_config import (  # noqa: E402
    REAL_PROVIDER_MAX_TOTAL_TOKENS,
    REAL_PROVIDER_TIMEOUT_SECONDS,
)
from ragcommerce_contracts import CreateListRequest  # noqa: E402

BASE_URL = "https://api.xiaomimimo.com/v1"
MODEL = "mimo-v2.5"


def prior_results(commerce: DemoCommerce, *, expired: bool = False) -> tuple[ToolResult, ...]:
    row = next(iter(commerce.rows.values()))
    offer = commerce._offer_payload(row)
    if expired:
        offer["expires_at"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    product = commerce._candidate_payload(
        row,
        route_type="STRICT",
        hard_constraints=[],
        soft_preferences=[],
        unmet_hard=[],
        unmet_soft=[],
        budget=None,
    )
    return (
        ToolResult({"products": [product]}),
        ToolResult({"product_facts": [commerce._product_payload(row)]}),
        ToolResult({"offers": [offer]}),
        ToolResult(
            {
                "comparison": {
                    "items": [row["product_id"]],
                    "dimensions": sorted(row["attributes"]),
                    "missing_fields": [],
                    "evidence_refs": row["evidence_refs"],
                }
            }
        ),
    )


async def plan_once(
    credential: str, text: str, prior: tuple[ToolResult, ...], case_id: str
) -> tuple[tuple[ToolCall, ...], dict[str, int | str], float]:
    provider = OpenAICompatibleProvider(
        BASE_URL,
        credential,
        MODEL,
        timeout_seconds=REAL_PROVIDER_TIMEOUT_SECONDS,
        max_total_tokens=REAL_PROVIDER_MAX_TOTAL_TOKENS,
    )
    command = TurnCommand(
        uuid5(NAMESPACE_URL, f"mimo-specialized:user:{case_id}"),
        uuid5(NAMESPACE_URL, f"mimo-specialized:thread:{case_id}"),
        uuid5(NAMESPACE_URL, f"mimo-specialized:run:{case_id}"),
        f"mimo-specialized-{case_id}",
        text,
    )
    started = perf_counter()
    calls = await provider.plan(command, prior, 0)
    return calls, dict(provider.usage()), round((perf_counter() - started) * 1000, 3)


async def evaluate(credential: str) -> dict[str, object]:
    commerce = DemoCommerce(ROOT / "data/demo/catalog.v3.jsonl")
    registry = ToolRegistry(commerce.tool_handlers())
    row = next(iter(commerce.rows.values()))
    shopping_list = commerce.create_list(
        uuid5(NAMESPACE_URL, "mimo-specialized:owner"),
        CreateListRequest(name="MiMo 专项验收"),
    )
    owner_id = uuid5(NAMESPACE_URL, "mimo-specialized:owner")
    cases = (
        {
            "id": "clarification",
            "text": "帮我选一个合适的数码产品。",
            "prior": (),
            "expected_tool": None,
        },
        {
            "id": "requote",
            "text": (
                f"报价 {row['offer']['offer_id']} 已经过期, 请只重新询价, 不要修改清单或待购。"
            ),
            "prior": prior_results(commerce, expired=True),
            "expected_tool": "offer.requote",
        },
        {
            "id": "list_write",
            "text": (
                f"请把规格 {row['variant_id']} 加入清单 {shopping_list.list_id}, 等待我审批后执行。"
            ),
            "prior": prior_results(commerce),
            "expected_tool": "list.update",
        },
        {
            "id": "cart_write",
            "text": (f"请把报价 {row['offer']['offer_id']} 以数量 2 加入待购, 等待我审批后执行。"),
            "prior": prior_results(commerce),
            "expected_tool": "cart.update",
        },
    )
    results: list[dict[str, object]] = []
    for case in cases:
        record: dict[str, object] = {"id": case["id"], "expected_tool": case["expected_tool"]}
        try:
            calls, usage, latency_ms = await plan_once(
                credential,
                str(case["text"]),
                case["prior"],  # type: ignore[arg-type]
                str(case["id"]),
            )
            actual = calls[0].name if len(calls) == 1 else None
            record.update(
                {
                    "actual_tool": actual,
                    "call_count": len(calls),
                    "latency_ms": latency_ms,
                    "usage": usage,
                    "schema_valid": True,
                    "approval_blocked_before_decision": None,
                    "state_changed_after_approval": None,
                    "idempotent_replay": None,
                }
            )
            expected = case["expected_tool"]
            if expected is None:
                record["passed"] = not calls
                results.append(record)
                continue
            if actual != expected:
                record["passed"] = False
                results.append(record)
                continue
            call = calls[0]
            command = TurnCommand(
                owner_id,
                uuid5(NAMESPACE_URL, f"mimo-specialized:thread:{case['id']}"),
                uuid5(NAMESPACE_URL, f"mimo-specialized:run:{case['id']}"),
                f"mimo-specialized-{case['id']}",
                str(case["text"]),
            )
            context = ToolExecutionContext(
                owner_id,
                command.thread_id,
                command.run_id,
                uuid5(NAMESPACE_URL, f"mimo-specialized:invocation:{case['id']}"),
                f"mimo-specialized-{case['id']}",
            )
            if expected in {"list.update", "cart.update"}:
                before = (
                    commerce.get_lists(owner_id).model_dump(mode="json")
                    if expected == "list.update"
                    else commerce.get_cart(owner_id).model_dump(mode="json")
                )
                try:
                    await registry.execute_async(command, call, context)
                    blocked = False
                except ToolDenied:
                    blocked = True
                unchanged = before == (
                    commerce.get_lists(owner_id).model_dump(mode="json")
                    if expected == "list.update"
                    else commerce.get_cart(owner_id).model_dump(mode="json")
                )
                approved = TurnCommand(
                    command.user_id,
                    command.thread_id,
                    command.run_id,
                    command.idempotency_key,
                    command.text,
                    approved_tools=frozenset({expected}),
                    allow_reversible_writes=True,
                )
                first = await registry.execute_async(approved, call, context)
                first_state = dict(first.public_data)
                second = await registry.execute_async(approved, call, context)
                second_state = dict(second.public_data)
                record["approval_blocked_before_decision"] = blocked and unchanged
                record["state_changed_after_approval"] = first_state != before
                record["idempotent_replay"] = first_state == second_state
                record["passed"] = all(
                    (
                        record["approval_blocked_before_decision"],
                        record["state_changed_after_approval"],
                        record["idempotent_replay"],
                    )
                )
            else:
                result = await registry.execute_async(command, call, context)
                record["passed"] = bool(result.public_data.get("offers"))
        except Exception as exc:
            record.update(
                {
                    "passed": False,
                    "schema_valid": False,
                    "failure_type": type(exc).__name__,
                }
            )
        results.append(record)

    passed = sum(bool(item["passed"]) for item in results)
    return {
        "schema_version": 1,
        "evidence_level": "REAL_PROVIDER_SPECIALIZED_ACCEPTANCE",
        "created_at": datetime.now(UTC).isoformat(),
        "provider": {
            "endpoint_host": "api.xiaomimimo.com",
            "model": MODEL,
            "cost": "NOT_AVAILABLE_FROM_PROVIDER",
        },
        "single_attempt_per_scenario": True,
        "summary": {"passed": passed, "total": len(results)},
        "passed": passed == len(results),
        "scenarios": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.parse_args()
    print(
        "Historical evaluator retired: use scripts/run_final_media_acceptance.py or native Android acceptance with frozen slots and the shared PostgreSQL budget. No provider call performed.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
