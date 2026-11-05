"""Interview-driven audit probes; failures expose gaps, not repaired regressions.

Run explicitly with pytest. All runtime state is in memory and every model response
uses an injected transport. No live model, credential, database or network is used.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from ragcommerce_agent_runtime import (
    FROZEN_TOOL_TYPES,
    EventType,
    InMemoryCheckpointStore,
    OpenAICompatibleProvider,
    ProviderBudgetExceeded,
    ProviderInvalidResponse,
    RuntimeIdentity,
    ScriptedPlanner,
    ShoppingAgent,
    StopReason,
    ToolCall,
    ToolRegistry,
    ToolResult,
    TurnCommand,
)
from ragcommerce_api.demo import create_demo_app
from ragcommerce_retrieval import HybridIndex, load_demo_documents

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "data/demo/catalog.v3.jsonl"
IDENTITY = RuntimeIdentity("interview-audit", "injected-fake", "audit", "audit", "0.2.0")


def turn(text: str = "推荐手机") -> TurnCommand:
    return TurnCommand(uuid4(), uuid4(), uuid4(), "interview-audit", text)


def make_agent(planner, overrides=None) -> ShoppingAgent:
    def read(context, arguments):
        return ToolResult({"audit_read": True})

    return ShoppingAgent(
        planner,
        ToolRegistry({**dict.fromkeys(FROZEN_TOOL_TYPES, read), **(overrides or {})}),
        InMemoryCheckpointStore(),
        IDENTITY,
    )


def collect(agent: ShoppingAgent, command: TurnCommand) -> list:
    async def run():
        return [event async for event in agent.handle(command)]

    return asyncio.run(run())


class InjectedResponse:
    def __init__(self, text: str, usage: int | None = 1):
        self.text = text
        self.tokens = usage
        self.calls = 0

    async def post_json(self, url, headers, payload, timeout_seconds):
        self.calls += 1
        result = {"choices": [{"message": {"content": self.text}}]}
        if self.tokens is not None:
            result["usage"] = {"total_tokens": self.tokens}
        return 200, result


def provider(text: str, **kwargs) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        "https://audit.invalid/v1",
        "test-only",
        "injected-fake",
        transport=InjectedResponse(text),
        **kwargs,
    )


def test_q1_empty_plan_is_clarification_not_completion():
    events = collect(make_agent(ScriptedPlanner(())), turn())
    assert any(event.type is EventType.CLARIFICATION_REQUIRED for event in events)
    assert not any(event.type is EventType.COMPLETED for event in events)


def test_q1_repeated_completed_tool_stops():
    class RepeatingPlanner(ScriptedPlanner):
        async def plan(self, command, prior_results, replan):
            return self.calls

    events = collect(
        make_agent(RepeatingPlanner((ToolCall("catalog.search", {"query": "手机"}),))), turn()
    )
    assert events[-1].type is EventType.FAILED
    assert events[-1].data["reason"] == StopReason.REPLAN_LIMIT


def test_q1_tool_failure_then_abandoned_plan_cannot_report_completed():
    class AbandoningPlanner(ScriptedPlanner):
        async def plan(self, command, prior_results, replan):
            return self.calls if replan == 0 else ()

    def broken_search(context, arguments):
        raise RuntimeError("injected catalog unavailable")

    events = collect(
        make_agent(
            AbandoningPlanner((ToolCall("catalog.search", {"query": "手机"}),)),
            {"catalog.search": broken_search},
        ),
        turn(),
    )
    assert any(event.type is EventType.TOOL_FAILED for event in events)
    assert not any(event.type is EventType.COMPLETED for event in events), [
        event.type for event in events
    ]
    assert events[-1].type is EventType.FAILED


def test_q1_nine_tool_plan_is_rejected_before_execution():
    calls = tuple(ToolCall("catalog.search", {"query": str(i)}) for i in range(9))
    events = collect(make_agent(ScriptedPlanner(calls)), turn())
    assert events[-1].data["reason"] == StopReason.TOOL_LIMIT
    assert not any(event.type is EventType.TOOL_STARTED for event in events)


def test_q2_structured_category_and_budget_filter():
    index = HybridIndex(load_demo_documents(CATALOG))
    hits = index.search("手机", constraints={"category": "手机", "price_max": 2000})
    assert hits
    assert all(hit.document.category == "手机" for hit in hits)
    assert all(hit.document.historical_price_minor <= 200000 for hit in hits)


def test_q2_impossible_budget_produces_no_match():
    index = HybridIndex(load_demo_documents(CATALOG))
    assert not index.search("手机", constraints={"category": "手机", "price_max": 1})


def test_q2_missing_attribute_does_not_satisfy_explicit_filter():
    docs = tuple(
        replace(document, attributes={})
        for document in load_demo_documents(CATALOG)
        if document.category == "手机"
    )
    hits = HybridIndex(docs).search("手机", constraints={"category": "手机", "防水": "IP68"})
    assert not hits, "missing 防水 evidence was silently treated as satisfying IP68"


def test_q2_exact_sku_query_is_not_overruled_by_development_prior():
    docs = load_demo_documents(CATALOG)
    target = next(
        document for document in docs if document.title == "Nova Mobile Pulse 02 演示手机"
    )
    hits = HybridIndex(docs).search(target.title, constraints={"category": "手机"})
    assert hits[0].document.seed_id == target.seed_id, {
        "query": target.title,
        "top_title": hits[0].document.title,
        "top_prior": hits[0].document.development_rank_prior,
        "requested_prior": target.development_rank_prior,
    }


def test_q2_api_does_not_claim_a_strict_match_for_missing_ip68():
    client = TestClient(create_demo_app(CATALOG))
    headers = {"X-User-ID": str(uuid4()), "Idempotency-Key": "audit-hard-constraint"}
    goal = "预算2000元,必须IP68防水的手机"
    thread = client.post("/v1/threads", json={"goal": goal}, headers=headers).json()
    path = f"/v1/threads/{thread['thread_id']}"
    assert (
        client.post(
            path + "/turns", json={"text": goal, "media_ids": []}, headers=headers
        ).status_code
        == 202
    )
    snapshot = client.get(path, headers=headers).json()
    strict = [
        route for route in snapshot["recommendation_routes"] if route["route_type"] == "STRICT"
    ]
    assert strict and not strict[0]["product_ids"]


def test_q3_unsupported_ascii_price_is_blocked_control():
    with pytest.raises(ProviderInvalidResponse):
        asyncio.run(provider("该商品售价3999元。").respond(turn("预算500元"), ()))


def test_q3_user_budget_is_not_source_for_a_product_price():
    with pytest.raises(ProviderInvalidResponse):
        asyncio.run(
            provider("这款商品的实际售价为1000元。").respond(
                turn("预算1000元"),
                (ToolResult({"offers": [{"price_minor": 159900, "shipping_minor": 0}]}),),
            )
        )


@pytest.mark.parametrize("text", ["售价$999.00。", "实际售价3999块。", "价格为三千九百九十九元。"])
def test_q3_unsupported_price_forms_are_blocked(text):
    with pytest.raises(ProviderInvalidResponse):
        asyncio.run(provider(text).respond(turn("预算500元"), ()))


@pytest.mark.parametrize(
    "text",
    ["这家商店是品牌官方旗舰店,提供全国联保。", "该商品库存9999件,明日送达,已经售出十万件。"],
)
def test_q3_unsupported_non_price_commercial_claim_is_blocked(text):
    with pytest.raises(ProviderInvalidResponse):
        asyncio.run(provider(text).respond(turn(), (ToolResult({"audit_read": True}),)))


def test_q3_unapproved_write_is_never_executed():
    writes = []

    def write(context, arguments):
        writes.append(arguments)
        return ToolResult({"audit_write": True})

    call = ToolCall("cart.update", {"operation": "add", "offer_id": str(uuid4()), "quantity": 2})
    events = collect(make_agent(ScriptedPlanner((call,)), {"cart.update": write}), turn())
    assert any(event.type is EventType.APPROVAL_REQUIRED for event in events)
    assert writes == []


@pytest.mark.parametrize("text", ["这款商品的实际售价为1000元。", "该商家是品牌官方旗舰店。"])
def test_q3_unsupported_claim_does_not_reach_public_sse(text):
    client = TestClient(create_demo_app(CATALOG))
    service = client.app.state.turn_service
    original = service.agent.planner
    injected_model = provider(text)

    class InjectedSummary:
        async def plan(self, command, prior_results, replan):
            return await original.plan(command, prior_results, replan)

        async def respond(self, command, results):
            return await injected_model.respond(command, results)

        def usage(self):
            return injected_model.usage()

    service.agent.planner = InjectedSummary()
    headers = {"X-User-ID": str(uuid4()), "Idempotency-Key": "audit-injected-summary"}
    goal = "Nova Mobile Pulse 01 演示手机,预算1000元"
    thread = client.post("/v1/threads", json={"goal": goal}, headers=headers).json()
    accepted = client.post(
        f"/v1/threads/{thread['thread_id']}/turns",
        json={"text": goal, "media_ids": []},
        headers=headers,
    )
    assert accepted.status_code == 202
    run_id = accepted.json()["run_id"]
    transcript = client.get(f"/v1/agent-runs/{run_id}/events", headers=headers).text
    assert text not in transcript, "unsupported model claim reached public MESSAGE/SSE"


def test_q4_foreign_identity_is_denied_control():
    client = TestClient(create_demo_app(CATALOG))
    owner = {"X-User-ID": str(uuid4())}
    thread = client.post("/v1/threads", json={"goal": "private audit task"}, headers=owner).json()
    response = client.get(f"/v1/threads/{thread['thread_id']}", headers={"X-User-ID": str(uuid4())})
    assert response.status_code == 404


def test_q4_client_cannot_impersonate_owner_with_only_a_header():
    client = TestClient(create_demo_app(CATALOG))
    owner = {"X-User-ID": str(uuid4())}
    thread = client.post("/v1/threads", json={"goal": "private audit task"}, headers=owner).json()
    attacker_supplied_headers = dict(owner)
    response = client.get(f"/v1/threads/{thread['thread_id']}", headers=attacker_supplied_headers)
    assert response.status_code in {401, 403}, "a self-asserted owner UUID is accepted as identity"


def test_q4_preference_memory_requires_consent():
    agent = make_agent(ScriptedPlanner(()))
    command = turn()
    assert not agent.remember_preferences(command, {"brand": "audit"})
    assert agent.load_preferences(command.user_id) == {}


def test_q4_turn_replay_with_different_payload_is_rejected():
    client = TestClient(create_demo_app(CATALOG))
    headers = {"X-User-ID": str(uuid4()), "Idempotency-Key": "audit-replay"}
    thread = client.post("/v1/threads", json={"goal": "通勤耳机"}, headers=headers).json()
    path = f"/v1/threads/{thread['thread_id']}/turns"
    assert (
        client.post(path, json={"text": "通勤耳机", "media_ids": []}, headers=headers).status_code
        == 202
    )
    response = client.post(path, json={"text": "换成手机", "media_ids": []}, headers=headers)
    assert response.status_code == 409


def test_q5_over_budget_response_is_not_reported_as_success():
    transport = InjectedResponse("请补充用途", usage=100)
    model = OpenAICompatibleProvider(
        "https://audit.invalid/v1", "test-only", "fake", max_total_tokens=10, transport=transport
    )
    with pytest.raises(ProviderBudgetExceeded):
        asyncio.run(model.respond(turn(), ()))
    assert transport.calls == 1


def test_q5_constructed_reference_is_not_real_model_quality():
    reference = json.loads(
        (ROOT / "evals/v2/results/deterministic-reference-summary.json").read_text(encoding="utf-8")
    )
    assert reference["real_provider_calls"] == 0
    assert reference["claims"]["model_quality_measured"] is False


def test_q5_security_snapshot_matches_git_checkout_bytes():
    report = json.loads(
        (ROOT / "docs/security/evidence/security-gate.json").read_text(encoding="utf-8")
    )
    committed = subprocess.run(
        ["git", "show", "HEAD:package-lock.json"], cwd=ROOT, check=True, capture_output=True
    ).stdout
    expected = report["checks"]["locked_inputs"]["npm_lock_sha256"]
    assert hashlib.sha256(committed).hexdigest() == expected, (
        "frozen security report matches CRLF worktree rather than Git LF checkout"
    )
