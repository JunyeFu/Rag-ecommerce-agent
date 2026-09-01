#!/usr/bin/env python3
"""Run the ten V3 golden scenarios once against the fixed MiMo provider."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
for source in (
    "apps/api/src",
    "packages/agent-runtime/src",
    "packages/contracts/generated/python",
    "packages/retrieval/src",
):
    sys.path.insert(0, str(ROOT / source))

from ragcommerce_agent_runtime import (  # noqa: E402
    EventType,
    InMemoryCheckpointStore,
    OpenAICompatibleProvider,
    RuntimeIdentity,
    ShoppingAgent,
    ToolRegistry,
    TurnCommand,
)
from ragcommerce_api.demo import DemoCommerce  # noqa: E402

BASE_URL = "https://api.xiaomimimo.com/v1"
MODEL = "mimo-v2.5"
TIMEOUT_SECONDS = 180
MAX_TOTAL_TOKENS = 48_000
PRICE_PATTERN = re.compile(
    r"(?:¥|￥|人民币)\s*([0-9]+(?:\.[0-9]{1,2})?)|([0-9]+(?:\.[0-9]{1,2})?)\s*元"
)


def _money_values(text: str) -> set[int]:
    values = set()
    for left, right in PRICE_PATTERN.findall(text):
        values.add(round(float(left or right) * 100))
    return values


async def run_case(case: dict[str, object], credential: str) -> dict[str, object]:
    provider = OpenAICompatibleProvider(
        BASE_URL,
        credential,
        MODEL,
        timeout_seconds=TIMEOUT_SECONDS,
        max_total_tokens=MAX_TOTAL_TOKENS,
    )
    commerce = DemoCommerce(ROOT / "data/demo/catalog.v3.jsonl")
    agent = ShoppingAgent(
        provider,
        ToolRegistry(commerce.tool_handlers()),
        InMemoryCheckpointStore(),
        RuntimeIdentity("0.3.0", MODEL, "agent-first-v3", "commercial-truth-v3", "0.2.0"),
    )
    case_id = str(case["id"])
    command = TurnCommand(
        user_id=uuid5(NAMESPACE_URL, f"mimo-eval:user:{case_id}"),
        thread_id=uuid5(NAMESPACE_URL, f"mimo-eval:thread:{case_id}"),
        run_id=uuid5(NAMESPACE_URL, f"mimo-eval:run:{case_id}"),
        idempotency_key=f"mimo-v2.5-{case_id}",
        text=str(case["query"]),
    )
    started = perf_counter()
    events = [event async for event in agent.handle(command)]
    latency_ms = round((perf_counter() - started) * 1000, 3)
    event_types = [event.type.value for event in events]
    tools = [str(event.data["tool"]) for event in events if event.type is EventType.TOOL_STARTED]
    products = [
        product
        for event in events
        if event.type is EventType.PRODUCTS
        for product in event.data.get("products", [])
    ]
    evidence_refs = [ref for product in products for ref in product.get("evidence_refs", [])]
    messages = [str(event.data["text"]) for event in events if event.type is EventType.MESSAGE]
    supported_commercial_amounts = {
        value
        for event in events
        if event.type is EventType.OFFERS
        for offer in event.data.get("offers", [])
        for value in (
            offer.get("price_minor"),
            offer.get("shipping_minor"),
            (
                offer.get("price_minor") + offer.get("shipping_minor")
                if isinstance(offer.get("price_minor"), int)
                and isinstance(offer.get("shipping_minor"), int)
                else None
            ),
        )
        if isinstance(value, int)
    }
    supported_commercial_amounts.update(_money_values(command.text))
    mentioned_prices = {value for message in messages for value in _money_values(message)}
    unsupported_prices = mentioned_prices - supported_commercial_amounts
    failed = next((event for event in events if event.type is EventType.FAILED), None)
    expected_product = str(case["expected_product_id"])
    unauthorized_execution = any(
        event.type is EventType.TOOL_COMPLETED
        and event.data.get("tool")
        in {"list.update", "cart.update", "link.resolve", "vision.identify"}
        for event in events
    )
    expected_read_tools = {
        "search": "catalog.search",
        "facts": "catalog.get_product_facts",
        "offers": "offer.find",
        "comparison": "comparison.build",
        "requote": "offer.requote",
        "resolve": "link.resolve",
    }
    required = {
        expected_read_tools[value]
        for value in case["flow"]
        if value in expected_read_tools and expected_read_tools[value] not in {"link.resolve"}
    }
    return {
        "id": case_id,
        "latency_ms": latency_ms,
        "terminal": event_types[-1] if event_types else "missing",
        "parseable": bool(events) and failed is None,
        "failure_type": str(failed.data.get("summary")) if failed else None,
        "tools": tools,
        "tool_schema_valid": not any(event.type is EventType.TOOL_FAILED for event in events),
        "expected_flow_complete": required <= set(tools),
        "expected_product_found": any(
            product.get("product_id") == expected_product for product in products
        ),
        "recommendations": len(products),
        "evidence_coverage": 1.0 if products and len(evidence_refs) >= len(products) else 0.0,
        "unauthorized_write_or_navigation": unauthorized_execution,
        "fabricated_commercial_fact": bool(unsupported_prices),
        "mentioned_amounts_minor": sorted(mentioned_prices),
        "supported_amounts_minor": sorted(supported_commercial_amounts),
        "unsupported_amounts_minor": sorted(unsupported_prices),
        "usage": provider.usage(),
    }


async def evaluate(credential: str) -> dict[str, object]:
    scenarios = json.loads((ROOT / "evals/v3/golden-scenarios.json").read_text(encoding="utf-8"))[
        "scenarios"
    ]
    results = []
    for case in scenarios:
        try:
            results.append(await run_case(case, credential))
        except Exception as exc:
            results.append(
                {
                    "id": case["id"],
                    "parseable": False,
                    "failure_type": type(exc).__name__,
                    "tools": [],
                    "tool_schema_valid": False,
                    "expected_flow_complete": False,
                    "expected_product_found": False,
                    "recommendations": 0,
                    "evidence_coverage": 0.0,
                    "unauthorized_write_or_navigation": False,
                    "fabricated_commercial_fact": False,
                    "usage": {},
                }
            )
    summary = {
        "parseable": sum(bool(item["parseable"]) for item in results),
        "schema_valid": sum(bool(item["tool_schema_valid"]) for item in results),
        "expected_flows": sum(bool(item["expected_flow_complete"]) for item in results),
        "evidence_coverage": min(float(item["evidence_coverage"]) for item in results),
        "unauthorized_write_or_navigation": sum(
            bool(item["unauthorized_write_or_navigation"]) for item in results
        ),
        "fabricated_commercial_facts": sum(
            bool(item["fabricated_commercial_fact"]) for item in results
        ),
    }
    passed = (
        summary["parseable"] == 10
        and summary["schema_valid"] == 10
        and summary["expected_flows"] >= 8
        and summary["evidence_coverage"] == 1.0
        and summary["unauthorized_write_or_navigation"] == 0
        and summary["fabricated_commercial_facts"] == 0
    )
    return {
        "schema_version": 1,
        "evidence_level": "REAL_PROVIDER_PUBLIC_GOLDEN",
        "created_at": datetime.now(UTC).isoformat(),
        "provider": {
            "endpoint_host": urlparse(BASE_URL).hostname,
            "model": MODEL,
            "api_style": "chat_completions",
            "cost": "NOT_AVAILABLE_FROM_PROVIDER",
        },
        "git_sha": os.environ.get("GITHUB_SHA") or _git_sha(),
        "single_attempt_per_scenario": True,
        "provider_limits": {
            "timeout_seconds": TIMEOUT_SECONDS,
            "max_total_tokens_per_scenario": MAX_TOTAL_TOKENS,
        },
        "summary": summary,
        "passed": passed,
        "scenarios": results,
    }


def _git_sha() -> str:
    import subprocess

    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    credential = os.environ.get("OPENAI_COMPATIBLE_API_KEY")
    if not credential:
        print("OPENAI_COMPATIBLE_API_KEY is required", file=sys.stderr)
        return 2
    report = asyncio.run(evaluate(credential))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"mimo_evaluation={'pass' if report['passed'] else 'fail'} scenarios=10")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
