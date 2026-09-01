import json
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from ragcommerce_api.demo import DemoCommerce, create_demo_app

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


def headers(**values: str) -> dict[str, str]:
    return {"X-User-ID": USER, **values}


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

    product_id = UUID(snapshot["candidates"][0]["product_id"])
    product = client.get(f"/v1/products/{product_id}", headers=headers())
    offers = client.get(f"/v1/products/{product_id}/offers?fresh=true", headers=headers())
    assert product.status_code == offers.status_code == 200
    assert offers.json()["offers"][0]["verification"] == "DEMO_FIXTURE"

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
