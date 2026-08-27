from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from pydantic import BaseModel
from ragcommerce_agent_runtime import (
    FROZEN_TOOL_TYPES,
    InMemoryCheckpointStore,
    RuntimeIdentity,
    ShoppingAgent,
    ToolCall,
    ToolEvidence,
    ToolExecutionContext,
    ToolRegistry,
    ToolResult,
    TurnCommand,
)
from ragcommerce_api.app import create_app
from ragcommerce_api.media import InMemoryMediaStore
from ragcommerce_api.security import SlidingWindowLimiter
from ragcommerce_api.service import TurnService
from ragcommerce_contracts import (
    CartItemView,
    CartMutation,
    CartView,
    CreateListRequest,
    OfferCollection,
    OfferView,
    PatchListRequest,
    ResolvedOffer,
    ResolveOfferRequest,
    ShoppingListsResponse,
    ShoppingListView,
)

IDENTITY = RuntimeIdentity("shopping-agent-v1", "fake-api-v1", "p1", "policy1", "0.1.0")
USER_A = UUID("00000000-0000-5000-8000-000000000101")
USER_B = UUID("00000000-0000-5000-8000-000000000102")


class RecordingPlanner:
    def __init__(self, call: ToolCall) -> None:
        self.call = call
        self.commands: list[TurnCommand] = []

    def plan(
        self, command: TurnCommand, prior_results: tuple[ToolResult, ...], replan: int
    ) -> tuple[ToolCall, ...]:
        self.commands.append(command)
        return (self.call,)

    def respond(self, command: TurnCommand, results: tuple[ToolResult, ...]) -> str:
        return "fixture response"

    def usage(self) -> dict[str, int | str]:
        return {"provider": "deterministic_fake", "cost_minor": 0, "currency": "CNY"}


def build_client(
    call: ToolCall | None = None,
    override: Callable[[ToolExecutionContext, BaseModel], ToolResult] | None = None,
    limiter: SlidingWindowLimiter | None = None,
    commerce: Any | None = None,
) -> tuple[TestClient, RecordingPlanner, InMemoryMediaStore]:
    planner = RecordingPlanner(call or ToolCall("catalog.search", {"query": "fixture"}))

    def read(_: ToolExecutionContext, __: BaseModel) -> ToolResult:
        return ToolResult(
            {"title": "fixture"},
            (ToolEvidence("seed:fixture", "0" * 64, ("title",)),),
            frozenset({"title"}),
        )

    handlers = {name: read for name in FROZEN_TOOL_TYPES}
    if override is not None:
        handlers[planner.call.name] = override
    media = InMemoryMediaStore()
    agent = ShoppingAgent(
        planner,
        ToolRegistry(handlers),
        InMemoryCheckpointStore(),
        IDENTITY,
    )
    service = TurnService(agent, media)
    return TestClient(create_app(service, media, limiter, commerce)), planner, media


def headers(user: UUID = USER_A, **values: str) -> dict[str, str]:
    return {"X-User-ID": str(user), **values}


def create_thread(client: TestClient, user: UUID = USER_A) -> str:
    response = client.post("/v1/threads", json={"goal": "fixture shopping"}, headers=headers(user))
    assert response.status_code == 201
    return response.json()["thread_id"]


def event_ids(payload: str) -> list[int]:
    return [int(value) for value in re.findall(r"^id: (\d+)$", payload, re.MULTILINE)]


def test_turn_idempotency_and_lossless_sse_cursor_resume() -> None:
    client, _, _ = build_client()
    thread_id = create_thread(client)
    request_headers = headers(**{"Idempotency-Key": "api-turn-1"})
    first = client.post(
        f"/v1/threads/{thread_id}/turns",
        json={"text": "headphones", "media_ids": []},
        headers=request_headers,
    )
    replay = client.post(
        f"/v1/threads/{thread_id}/turns",
        json={"text": "headphones", "media_ids": []},
        headers=request_headers,
    )
    conflict = client.post(
        f"/v1/threads/{thread_id}/turns",
        json={"text": "different", "media_ids": []},
        headers=request_headers,
    )

    assert first.status_code == replay.status_code == 202
    assert first.json()["run_id"] == replay.json()["run_id"]
    assert first.json()["replayed"] is False
    assert replay.json()["replayed"] is True
    assert conflict.status_code == 409

    run_id = first.json()["run_id"]
    complete = client.get(f"/v1/agent-runs/{run_id}/events", headers=headers())
    ids = event_ids(complete.text)
    resumed = client.get(
        f"/v1/agent-runs/{run_id}/events",
        headers=headers(**{"Last-Event-ID": str(ids[2])}),
    )
    assert ids == list(range(1, len(ids) + 1))
    assert event_ids(resumed.text) == ids[3:]
    assert complete.text.count("event: completed") == 1
    assert resumed.text.count("event: completed") == 1
    assert "arguments_sha256" not in complete.text
    assert "idempotency_digest" not in complete.text
    assert "invocation_id" not in complete.text


def test_text_image_and_audio_use_the_same_turn_command_and_runtime() -> None:
    client, planner, _ = build_client()
    thread_id = create_thread(client)
    image = client.post(
        "/v1/media",
        content=b"\x89PNG\r\n\x1a\nfixture",
        headers=headers(**{"Content-Type": "image/png"}),
    )
    audio = client.post(
        "/v1/media",
        content=b"OggSfixture",
        headers=headers(**{"Content-Type": "audio/ogg"}),
    )
    assert image.status_code == audio.status_code == 201

    payloads = (
        ("text", {"text": "text turn", "media_ids": []}),
        ("image", {"text": "", "media_ids": [image.json()["media_id"]]}),
        ("audio", {"text": "", "media_ids": [audio.json()["media_id"]]}),
    )
    for key, payload in payloads:
        response = client.post(
            f"/v1/threads/{thread_id}/turns",
            json=payload,
            headers=headers(**{"Idempotency-Key": f"api-{key}-1"}),
        )
        assert response.status_code == 202

    assert len(planner.commands) == 3
    assert planner.commands[0].text == "text turn"
    assert planner.commands[1].media[0].kind == "image"
    assert planner.commands[2].media[0].kind == "audio"


def test_media_signature_size_owner_and_deletion_boundaries() -> None:
    client, _, media = build_client()
    media.IMAGE_LIMIT = 12
    forged = client.post(
        "/v1/media",
        content=b"not-a-png",
        headers=headers(**{"Content-Type": "image/png", "X-Filename": "../../secret"}),
    )
    oversized = client.post(
        "/v1/media",
        content=b"\x89PNG\r\n\x1a\n" + b"x" * 8,
        headers=headers(**{"Content-Type": "image/png"}),
    )
    valid = client.post(
        "/v1/media",
        content=b"\x89PNG\r\n\x1a\n",
        headers=headers(**{"Content-Type": "image/png", "X-Filename": "../../secret"}),
    )
    assert forged.status_code == 415
    assert oversized.status_code == 413
    assert valid.status_code == 201
    assert "secret" not in valid.text

    media_id = valid.json()["media_id"]
    assert client.delete(f"/v1/media/{media_id}", headers=headers(USER_B)).status_code == 404
    assert client.delete(f"/v1/media/{media_id}", headers=headers()).json() == {"deleted": True}
    assert client.delete(f"/v1/media/{media_id}", headers=headers()).status_code == 404


def test_owner_isolation_and_process_local_rate_limit_fail_closed() -> None:
    client, _, _ = build_client(limiter=SlidingWindowLimiter(limit=2, window_seconds=60))
    thread_id = create_thread(client)
    assert (
        client.post(
            f"/v1/threads/{thread_id}/turns",
            json={"text": "x", "media_ids": []},
            headers=headers(USER_B, **{"Idempotency-Key": "cross-user"}),
        ).status_code
        == 404
    )
    assert client.post("/v1/threads", json={"goal": "second"}, headers=headers()).status_code == 201
    assert (
        client.post("/v1/threads", json={"goal": "limited"}, headers=headers()).status_code == 429
    )


def test_explicit_decision_resumes_the_same_agent_run() -> None:
    calls = 0

    def update(_: ToolExecutionContext, __: BaseModel) -> ToolResult:
        nonlocal calls
        calls += 1
        return ToolResult()

    client, _, _ = build_client(
        ToolCall("cart.update", {"operation": "add", "item_id": "o1"}), update
    )
    thread_id = create_thread(client)
    turn = client.post(
        f"/v1/threads/{thread_id}/turns",
        json={"text": "add fixture", "media_ids": []},
        headers=headers(**{"Idempotency-Key": "decision-1"}),
    )
    run_id = turn.json()["run_id"]
    paused = client.get(f"/v1/agent-runs/{run_id}/events", headers=headers())
    assert "event: approval_required" in paused.text
    assert calls == 0

    decision = client.post(
        f"/v1/agent-runs/{run_id}/decisions",
        json={"tool_name": "cart.update", "approved": True},
        headers=headers(),
    )
    completed = client.get(f"/v1/agent-runs/{run_id}/events", headers=headers())
    assert decision.status_code == 200
    assert decision.json()["run_id"] == run_id
    assert calls == 1
    assert "event: completed" in completed.text


def test_unconfigured_business_api_is_explicitly_unavailable() -> None:
    client = TestClient(create_app())
    assert client.get("/health").status_code == 200
    assert client.post("/v1/threads", json={"goal": "x"}, headers=headers()).status_code == 503


class FixtureCommerce:
    def __init__(self) -> None:
        self.list_id = UUID("00000000-0000-5000-8000-000000000201")
        self.offer_id = UUID("00000000-0000-5000-8000-000000000202")
        self.variant_id = UUID("00000000-0000-5000-8000-000000000203")
        self.lists: dict[UUID, ShoppingListView] = {}
        self.carts: dict[UUID, CartView] = {}
        self.fresh_requests: list[bool] = []

    def get_offers(self, user_id: UUID, product_id: UUID, fresh: bool) -> OfferCollection:
        self.fresh_requests.append(fresh)
        now = datetime.now(UTC)
        return OfferCollection(
            product_id=product_id,
            offers=[
                OfferView(
                    offer_id=self.offer_id,
                    merchant_name="Fixture Merchant",
                    verification="FEED_VERIFIED",
                    availability="AVAILABLE",
                    price_minor=19900,
                    shipping_minor=0,
                    currency="CNY",
                    collected_at=now,
                    expires_at=now + timedelta(minutes=5),
                    source_ref="fixture:offer-1",
                )
            ],
        )

    def resolve_offer(
        self, user_id: UUID, offer_id: UUID, request: ResolveOfferRequest
    ) -> ResolvedOffer:
        return ResolvedOffer(
            offer_id=offer_id,
            link_url="https://fixture.invalid/item/1",
            disclosure="fixture affiliate disclosure",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            quote_changed=False,
            requires_confirmation=False,
        )

    def get_lists(self, user_id: UUID) -> ShoppingListsResponse:
        return ShoppingListsResponse(lists=list(self.lists.values()))

    def create_list(self, user_id: UUID, request: CreateListRequest) -> ShoppingListView:
        value = ShoppingListView(list_id=self.list_id, name=request.name, variant_ids=[])
        self.lists[value.list_id] = value
        return value

    def patch_list(
        self, user_id: UUID, list_id: UUID, request: PatchListRequest
    ) -> ShoppingListView:
        current = self.lists[list_id]
        variants = list(current.variant_ids)
        if request.add_variant_id is not None and request.add_variant_id not in variants:
            variants.append(request.add_variant_id)
        value = ShoppingListView(
            list_id=list_id, name=request.name or current.name, variant_ids=variants
        )
        self.lists[list_id] = value
        return value

    def get_cart(self, user_id: UUID) -> CartView:
        return self.carts.get(user_id, CartView(items=[]))

    def mutate_cart(self, user_id: UUID, request: CartMutation) -> CartView:
        value = CartView(items=[CartItemView(offer_id=request.offer_id, quantity=request.quantity)])
        self.carts[user_id] = value
        return value


def test_commerce_routes_delegate_grounded_facts_lists_and_cart() -> None:
    commerce = FixtureCommerce()
    client, _, _ = build_client(commerce=commerce)
    product_id = UUID("00000000-0000-5000-8000-000000000204")
    offers = client.get(f"/v1/products/{product_id}/offers?fresh=true", headers=headers())
    offer = offers.json()["offers"][0]
    assert offers.status_code == 200
    assert commerce.fresh_requests == [True]
    assert {
        "price_minor",
        "currency",
        "verification",
        "collected_at",
        "expires_at",
        "source_ref",
    } <= set(offer)

    resolved = client.post(f"/v1/offers/{commerce.offer_id}/resolve", json={}, headers=headers())
    assert resolved.status_code == 200
    assert resolved.json()["link_url"].startswith("https://")
    assert resolved.json()["disclosure"]

    created = client.post("/v1/lists", json={"name": "shortlist"}, headers=headers())
    patched = client.patch(
        f"/v1/lists/{created.json()['list_id']}",
        json={"add_variant_id": str(commerce.variant_id)},
        headers=headers(),
    )
    listed = client.get("/v1/lists", headers=headers())
    assert patched.json()["variant_ids"] == [str(commerce.variant_id)]
    assert len(listed.json()["lists"]) == 1

    cart = client.post(
        "/v1/cart",
        json={"operation": "add", "offer_id": str(commerce.offer_id), "quantity": 2},
        headers=headers(),
    )
    assert cart.json()["items"] == [{"offer_id": str(commerce.offer_id), "quantity": 2}]
    assert client.get("/v1/cart", headers=headers()).json() == cart.json()
