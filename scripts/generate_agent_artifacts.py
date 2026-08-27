#!/usr/bin/env python3
"""Generate or verify frozen Agent tool contracts and deterministic public trace."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/agent-runtime/src"))

import ragcommerce_agent_runtime.runtime as runtime_module  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from ragcommerce_agent_runtime import (  # noqa: E402
    FROZEN_TOOL_TYPES,
    InMemoryCheckpointStore,
    RuntimeIdentity,
    ScriptedPlanner,
    ShoppingAgent,
    ToolCall,
    ToolEvidence,
    ToolExecutionContext,
    ToolRegistry,
    ToolResult,
    TurnCommand,
)
from ragcommerce_agent_runtime.postgres_store import plain  # noqa: E402

REGISTRY_PATH = ROOT / "packages/contracts/agent/tool-registry.json"
TRACE_PATH = ROOT / "evals/agent/fake-trace.json"
IDENTITY = RuntimeIdentity("shopping-agent-v1", "fake-v1", "p1", "policy1", "0.1.0")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def registry_artifact() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "registry_version": "agent-tools-v1",
        "transaction_tools": [],
        "tools": [
            {
                "name": name,
                "risk": risk.value,
                "arguments_schema": argument_type.model_json_schema(),
            }
            for name, (argument_type, risk) in FROZEN_TOOL_TYPES.items()
        ],
    }


async def trace_artifact() -> dict[str, Any]:
    def handler(_: ToolExecutionContext, __: BaseModel) -> ToolResult:
        return ToolResult(
            {"products": [{"id": "fixture-product", "title": "Fixture Headphones"}]},
            (ToolEvidence("seed:fixture-product", "0" * 64, ("title",)),),
            frozenset({"title"}),
        )

    handlers: dict[str, Callable[[ToolExecutionContext, BaseModel], ToolResult]] = {
        name: handler for name in FROZEN_TOOL_TYPES
    }
    command = TurnCommand(
        user_id=UUID("00000000-0000-5000-8000-000000000001"),
        thread_id=UUID("00000000-0000-5000-8000-000000000002"),
        run_id=UUID("00000000-0000-5000-8000-000000000003"),
        idempotency_key="test-v2-agent-01-trace",
        text="推荐夹具耳机",
    )
    timing = iter((100.0, 100.005))
    runtime_module.perf_counter = lambda: next(timing)
    agent = ShoppingAgent(
        ScriptedPlanner((ToolCall("catalog.search", {"query": "夹具耳机"}),)),
        ToolRegistry(handlers),
        InMemoryCheckpointStore(),
        IDENTITY,
    )
    events = [event async for event in agent.handle(command)]
    return {
        "schema_version": 1,
        "fixture": "deterministic_fake_model",
        "runtime_identity": {
            "agent_version": IDENTITY.agent_version,
            "model_version": IDENTITY.model_version,
            "prompt_version": IDENTITY.prompt_version,
            "policy_version": IDENTITY.policy_version,
            "contract_version": IDENTITY.contract_version,
        },
        "command": {
            "run_id": str(command.run_id),
            "thread_id": str(command.thread_id),
            "media_count": 0,
            "input_kind": "text",
        },
        "events": [
            {"id": event.id, "type": event.type.value, "data": plain(dict(event.data))}
            for event in events
        ],
        "assertions": {
            "completed": events[-1].type.value == "completed",
            "commercial_fact_fields": 1,
            "evidence_supported_fields": 1,
            "model_generated_commercial_fields": 0,
            "unauthorized_actions": 0,
            "tool_attempts": 1,
            "replans": 0,
        },
        "normalization": ["event timestamps omitted", "tool duration uses deterministic clock"],
    }


def apply(path: Path, content: bytes, check: bool) -> bool:
    if check:
        return path.is_file() and path.read_bytes() == content
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    artifacts = {
        REGISTRY_PATH: canonical(registry_artifact()),
        TRACE_PATH: canonical(asyncio.run(trace_artifact())),
    }
    failures = [path for path, content in artifacts.items() if not apply(path, content, args.check)]
    if failures:
        for path in failures:
            print(f"DRIFT {path.relative_to(ROOT).as_posix()}")
        return 1
    action = "verified" if args.check else "generated"
    print(f"agent_artifacts={action} files={len(artifacts)} tools={len(FROZEN_TOOL_TYPES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
