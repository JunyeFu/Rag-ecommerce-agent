import json
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from ragcommerce_agent_runtime import (
    InMemoryCheckpointStore,
    RuntimeIdentity,
    ScriptedPlanner,
    ShoppingAgent,
    ToolCall,
    ToolRegistry,
)
from ragcommerce_api.app import create_app
from ragcommerce_api.demo import DemoCommerce, create_demo_app
from ragcommerce_api.media import InMemoryMediaStore
from ragcommerce_api.ops import InMemoryOpsStore
from ragcommerce_api.service import TurnService

ROOT = Path(__file__).resolve().parents[3]
USER = "00000000-0000-5000-8000-000000000301"


def test_all_v3_golden_queries_retrieve_the_expected_product_first() -> None:
    commerce = DemoCommerce(ROOT / "data/demo/catalog.v3.jsonl")
    scenarios = json.loads((ROOT / "evals/v3/golden-scenarios.json").read_text(encoding="utf-8"))[
        "scenarios"
    ]

    for scenario in scenarios:
        result = commerce._search(scenario["query"])
        assert result.public_data["products"][0]["product_id"] == scenario["expected_product_id"]


def test_recommendation_routes_separate_strict_budget_and_alternative_products() -> None:
    commerce = DemoCommerce(ROOT / "data/demo/catalog.v3.jsonl")
    result = commerce._search("预算 450 元, 耳机必须轻量")
    routes = {item["route_type"]: item for item in result.public_data["recommendation_routes"]}

    assert routes["STRICT"]["status"] == "AVAILABLE"
    assert routes["BUDGET"]["status"] == "AVAILABLE"
    assert routes["ALTERNATIVE"]["status"] == "AVAILABLE"
    assert routes["ALTERNATIVE"]["relaxed_constraints"] == ["耳机必须轻量"]
    assert routes["STRICT"]["product_ids"][0] != routes["ALTERNATIVE"]["product_ids"][0]
    candidates = result.public_data["products"]
    alternative = next(item for item in candidates if item["recommendation_type"] == "ALTERNATIVE")
    assert alternative["relaxed_constraints"] == ["耳机必须轻量"]
    assert "不同商品或规格" in alternative["fit_summary"]


def test_impossible_hard_constraint_does_not_masquerade_as_budget_solution() -> None:
    commerce = DemoCommerce(ROOT / "data/demo/catalog.v3.jsonl")
    result = commerce._search("预算 450 元, 耳机必须支持卫星通信")
    routes = {item["route_type"]: item for item in result.public_data["recommendation_routes"]}

    assert routes["STRICT"]["status"] == "UNAVAILABLE"
    assert routes["BUDGET"]["status"] == "UNAVAILABLE"
    assert routes["ALTERNATIVE"]["status"] == "AVAILABLE"
    assert routes["ALTERNATIVE"]["relaxed_constraints"] == ["耳机必须支持卫星通信"]


def headers(**values: str) -> dict[str, str]:
    return {"X-User-ID": USER, **values}


def test_global_cart_has_facts_and_original_quote_after_starting_another_task():
    client = TestClient(create_demo_app(ROOT / "data/demo/catalog.v3.jsonl"))
    commerce = DemoCommerce(ROOT / "data/demo/catalog.v3.jsonl")
    product = next(iter(commerce.rows.values()))
    quote = client.get(f"/v1/products/{product['product_id']}/offers", headers=headers()).json()[
        "offers"
    ][0]
    added = client.patch(
        "/v1/cart",
        headers=headers(),
        json={
            "operation": "set",
            "offer_id": quote["offer_id"],
            "quantity": 2,
        },
    )
    assert added.status_code == 200
    client.post(
        "/v1/threads", json={"goal": "另一个独立购买任务"}, headers=headers()
    ).raise_for_status()
    item = client.get("/v1/cart", headers=headers()).json()["items"][0]
    assert item["product"]["title"] == product["title"]
    assert item["product"]["variant_id"] == product["variant_id"]
    assert item["quote"] == quote
    assert item["quantity"] == 2
    assert client.get(
        "/v1/cart", headers={"X-User-ID": "00000000-0000-5000-8000-000000000302"}
    ).json() == {"items": []}


def test_demo_user_completes_grounded_agent_to_cart_flow_through_public_api() -> None:
    client = TestClient(create_demo_app(ROOT / "data/demo/catalog.v3.jsonl"))
    thread = client.post(
        "/v1/threads", json={"goal": "预算 1000 元的通勤降噪耳机"}, headers=headers()
    ).json()
    accepted = client.post(
        f"/v1/threads/{thread['thread_id']}/turns",
        json={"text": "预算 1000 元的通勤降噪耳机", "media_ids": []},
        headers=headers(**{"Idempotency-Key": "golden-demo-1"}),
    )
    assert accepted.status_code == 202

    events = client.get(
        f"/v1/agent-runs/{accepted.json()['run_id']}/events", headers=headers()
    ).text
    assert "event: products" in events
    assert "event: offers" in events
    assert "event: comparison" in events
    assert "event: completed" in events
    assert "DEMO_FIXTURE" in events

    snapshot = client.get(f"/v1/threads/{thread['thread_id']}", headers=headers()).json()
    assert snapshot["status"] == "COMPLETED"
    assert len(snapshot["candidates"]) >= 3
    assert all(candidate["evidence_refs"] for candidate in snapshot["candidates"])
    assert [item["route_type"] for item in snapshot["recommendation_routes"]] == [
        "STRICT",
        "BUDGET",
        "ALTERNATIVE",
    ]

    product_id = UUID(snapshot["candidates"][0]["product_id"])
    product = client.get(f"/v1/products/{product_id}", headers=headers())
    offers = client.get(f"/v1/products/{product_id}/offers?fresh=true", headers=headers())
    assert product.status_code == offers.status_code == 200
    offer = offers.json()["offers"][0]
    assert offer["verification"] == "DEMO_FIXTURE"
    assert {fact["fact_type"] for fact in offer["business_facts"]} == {
        "price",
        "inventory",
        "delivery",
        "merchant",
        "after_sales",
    }
    assert all(fact["verification_level"] == "DEMO_FIXTURE" for fact in offer["business_facts"])
    assert all(fact["evidence_ref"] for fact in offer["business_facts"])

    shopping_list = client.post("/v1/lists", json={"name": "通勤方案"}, headers=headers())
    saved = client.patch(
        f"/v1/lists/{shopping_list.json()['list_id']}",
        json={"add_variant_id": product.json()["variant_id"]},
        headers=headers(),
    )
    offer_id = offers.json()["offers"][0]["offer_id"]
    cart = client.post(
        "/v1/cart",
        json={"operation": "add", "offer_id": offer_id, "quantity": 1},
        headers=headers(),
    )
    resolved = client.post(
        f"/v1/offers/{offer_id}/resolve",
        json={"confirmed_quote_change": False},
        headers=headers(),
    )
    assert saved.status_code == cart.status_code == resolved.status_code == 200
    assert resolved.json()["link_url"].startswith("https://example.com/")


def test_watcher_is_persisted_only_as_a_non_scheduled_demo_draft() -> None:
    client = TestClient(create_demo_app(ROOT / "data/demo/catalog.v3.jsonl"))
    thread = client.post("/v1/threads", json={"goal": "观察耳机价格"}, headers=headers()).json()
    commerce = DemoCommerce(ROOT / "data/demo/catalog.v3.jsonl")
    offer_id = next(iter(commerce.offers))
    path = f"/v1/threads/{thread['thread_id']}/watchers"

    missing_threshold = client.post(
        path,
        json={"kind": "PRICE_BELOW", "offer_id": str(offer_id)},
        headers=headers(),
    )
    assert missing_threshold.status_code == 400
    created = client.post(
        path,
        json={"kind": "PRICE_BELOW", "offer_id": str(offer_id), "threshold_minor": 35000},
        headers=headers(),
    )
    assert created.status_code == 201
    assert created.json()["status"] == "DEMO_DRAFT"
    assert created.json()["scheduler_active"] is False
    assert "不会后台提醒" in created.json()["disclosure"]
    repeated = client.post(
        path,
        json={"kind": "PRICE_BELOW", "offer_id": str(offer_id), "threshold_minor": 35000},
        headers=headers(),
    )
    assert repeated.json()["watcher_id"] == created.json()["watcher_id"]
    assert len(client.get(path, headers=headers()).json()["watchers"]) == 1
    assert (
        client.get(
            path,
            headers={"X-User-ID": "00000000-0000-5000-8000-000000000302"},
        ).status_code
        == 404
    )


def test_approved_agent_writes_are_visible_through_public_state_apis() -> None:
    commerce = DemoCommerce(ROOT / "data/demo/catalog.v3.jsonl")
    row = next(iter(commerce.rows.values()))
    media = InMemoryMediaStore()
    planner = ScriptedPlanner(())
    agent = ShoppingAgent(
        planner,
        ToolRegistry(commerce.tool_handlers()),
        InMemoryCheckpointStore(),
        RuntimeIdentity("shopping-agent-v3-test", "fake", "p1", "policy1", "0.2.0"),
    )
    client = TestClient(
        create_app(
            TurnService(agent, media),
            media,
            commerce=commerce,
            ops_store=InMemoryOpsStore(),
            development_identity=True,
        )
    )
    list_id = client.post("/v1/lists", json={"name": "Agent 方案"}, headers=headers()).json()[
        "list_id"
    ]
    planner.calls = (
        ToolCall(
            "list.update",
            {"operation": "add", "list_id": list_id, "variant_id": row["variant_id"]},
        ),
        ToolCall(
            "cart.update",
            {"operation": "add", "offer_id": row["offer"]["offer_id"], "quantity": 2},
        ),
    )
    thread = client.post("/v1/threads", json={"goal": "保存方案"}, headers=headers()).json()
    turn = client.post(
        f"/v1/threads/{thread['thread_id']}/turns",
        json={"text": "保存并加入待购", "media_ids": []},
        headers=headers(**{"Idempotency-Key": "agent-write-1"}),
    ).json()

    before = client.get("/v1/cart", headers=headers()).json()
    assert before["items"] == []
    assert (
        client.post(
            f"/v1/agent-runs/{turn['run_id']}/decisions",
            json={"tool_name": "list.update", "approved": True},
            headers=headers(),
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/v1/agent-runs/{turn['run_id']}/decisions",
            json={"tool_name": "cart.update", "approved": True},
            headers=headers(),
        ).status_code
        == 200
    )

    saved = client.get("/v1/lists", headers=headers()).json()["lists"][0]
    cart = client.get("/v1/cart", headers=headers()).json()
    assert saved["variant_ids"] == [row["variant_id"]]
    assert len(cart["items"]) == 1
    assert cart["items"][0]["offer_id"] == row["offer"]["offer_id"]
    assert cart["items"][0]["quantity"] == 2
    assert cart["items"][0]["product"]["title"] == row["title"]
    assert cart["items"][0]["quote"]["offer_id"] == row["offer"]["offer_id"]
    other_headers = {"X-User-ID": "00000000-0000-5000-8000-000000000302"}
    assert client.get("/v1/lists", headers=other_headers).json()["lists"] == []
    assert client.get("/v1/cart", headers=other_headers).json()["items"] == []

    repeated = client.post(
        f"/v1/agent-runs/{turn['run_id']}/decisions",
        json={"tool_name": "cart.update", "approved": True},
        headers=headers(),
    )
    assert repeated.status_code == 200
    assert client.get("/v1/cart", headers=headers()).json() == cart


def test_demo_clarifies_a_vague_mission_then_merges_the_answer() -> None:
    client = TestClient(create_demo_app(ROOT / "data/demo/catalog.v3.jsonl"))
    thread = client.post("/v1/threads", json={"goal": "通勤降噪耳机"}, headers=headers()).json()
    first = client.post(
        f"/v1/threads/{thread['thread_id']}/turns",
        json={"text": "通勤降噪耳机", "media_ids": []},
        headers=headers(**{"Idempotency-Key": "clarify-demo-1"}),
    )
    first_events = client.get(
        f"/v1/agent-runs/{first.json()['run_id']}/events", headers=headers()
    ).text
    waiting = client.get(f"/v1/threads/{thread['thread_id']}", headers=headers()).json()

    assert "event: clarification_required" in first_events
    assert waiting["status"] == "WAITING_CLARIFICATION"

    second = client.post(
        f"/v1/threads/{thread['thread_id']}/turns",
        json={"text": "预算上限 1500 元", "media_ids": []},
        headers=headers(**{"Idempotency-Key": "clarify-demo-2"}),
    )
    second_events = client.get(
        f"/v1/agent-runs/{second.json()['run_id']}/events", headers=headers()
    ).text
    completed = client.get(f"/v1/threads/{thread['thread_id']}", headers=headers()).json()

    assert "event: completed" in second_events
    assert completed["status"] == "COMPLETED"
    assert completed["goal"] == "通勤降噪耳机; 预算上限 1500 元"
