"""Isolated emulator fixture: real API/runtime/PostgreSQL, no paid model or media tests."""

import json
import os
from pathlib import Path

from fastapi.exception_handlers import http_exception_handler
from ragcommerce_agent_runtime import (
    PostgresCheckpointStore,
    RuntimeIdentity,
    ShoppingAgent,
    ToolCall,
    ToolRegistry,
)
from ragcommerce_api.app import create_app
from ragcommerce_api.demo import DemoProvider
from ragcommerce_api.media import InMemoryMediaStore
from ragcommerce_api.postgres_demo import PostgresDemoCommerce
from ragcommerce_api.postgres_index import PostgresTurnIndex
from ragcommerce_api.security import SlidingWindowLimiter
from ragcommerce_api.service import TurnService
from starlette.exceptions import HTTPException

dsn = os.environ["API_DATABASE_URL"]
commerce = PostgresDemoCommerce(
    Path(__file__).resolve().parents[1] / "data/demo/catalog.v3.jsonl", dsn
)


class ApprovalFixture(DemoProvider):
    async def plan(self, command, prior_results, replan):
        if command.text.startswith("recovery-"):
            return (
                ()
                if prior_results
                else (
                    ToolCall(
                        "cart.update",
                        {
                            "operation": "add",
                            "offer_id": str(next(iter(commerce.offers))),
                            "quantity": 1,
                        },
                    ),
                )
            )
        return await super().plan(command, prior_results, replan)


media = InMemoryMediaStore()
agent = ShoppingAgent(
    ApprovalFixture(),
    ToolRegistry(commerce.tool_handlers()),
    PostgresCheckpointStore(dsn),
    RuntimeIdentity("emulator-acceptance", "explicit-fake", "recovery", "v3", "0.2.0"),
)
app = create_app(
    TurnService(agent, media, PostgresTurnIndex(dsn)),
    media,
    commerce=commerce,
    limiter=SlidingWindowLimiter(limit=600),
)  # Fast native fixture only; production remains 60/minute.


@app.exception_handler(HTTPException)
async def qa_request_failure(request, error):
    # Isolated QA only: diagnose the observed native 4xx without credentials,
    # request bodies, private reasoning, or changing the production response.
    print(
        json.dumps(
            {
                "qa_failure": {
                    "path": request.url.path,
                    "method": request.method,
                    "status": error.status_code,
                    "detail": str(error.detail)[:240],
                }
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return await http_exception_handler(request, error)
