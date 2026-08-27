"""Deterministic local API composition for Android integration tests only."""

from pydantic import BaseModel
from ragcommerce_agent_runtime import (
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
)
from ragcommerce_api.app import create_app
from ragcommerce_api.media import InMemoryMediaStore
from ragcommerce_api.service import TurnService


def grounded_fixture(_: ToolExecutionContext, __: BaseModel) -> ToolResult:
    return ToolResult(
        public_data={"product_id": "fixture-product-1", "title": "Fixture Headphones"},
        evidence=(
            ToolEvidence(
                "fixture:catalog-product-1",
                "0" * 64,
                ("product_id", "title"),
            ),
        ),
        commercial_fact_fields=frozenset({"product_id", "title"}),
    )


media = InMemoryMediaStore()
planner = ScriptedPlanner(
    (ToolCall("catalog.search", {"query": "fixture"}),),
    message="fixture response",
)
agent = ShoppingAgent(
    planner,
    ToolRegistry({name: grounded_fixture for name in FROZEN_TOOL_TYPES}),
    InMemoryCheckpointStore(),
    RuntimeIdentity(
        "android-fixture-agent",
        "deterministic-fixture",
        "fixture-prompt",
        "fixture-policy",
        "0.1.0",
    ),
)
app = create_app(TurnService(agent, media), media)
