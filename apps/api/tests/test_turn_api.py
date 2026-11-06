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
PRODUCT_ID = UUID("00000000-0000-5000-8000-000000000204")


class RecordingPlanner:
    def __init__(self, call: ToolCall, clarify_first: bool = False) -> None:
        self.call = call
        self.clarify_first = clarify_first
        self.commands: list[TurnCommand] = []

    async def plan(
        self, command: TurnCommand, prior_results: tuple[ToolResult, ...], replan: int
    ) -> tuple[ToolCall, ...]:
        if prior_results:
            return ()
        self.commands.append(command)
        if self.clarify_first and len(self.commands) == 1:
            return ()
        return (self.call,)

    async def respond(self, command: TurnCommand, results: tuple[ToolResult, ...]) -> str:
        return "请补充预算。" if not results else "fixture response"

    def usage(self) -> dict[str, int | str]:
        return {"provider": "deterministic_fake", "cost_minor": 0, "currency": "CNY"}


def build_client(
    call: ToolCall | None = None,
    override: Callable[[ToolExecutionContext, BaseModel], ToolResult] | None = None,
    limiter: SlidingWindowLimiter | None = None,
    commerce: Any | None = None,
    clarify_first: bool = False,
) -> tuple[TestClient, RecordingPlanner, InMemoryMediaStore]:
    planner = RecordingPlanner(
        call or ToolCall("catalog.search", {"query": "fixture"}),
        clarify_first,
    )

    def read(_: ToolExecutionContext, __: BaseModel) -> ToolResult:
        return ToolResult(
            {
                "products": [
                    {
                        "product_id": str(PRODUCT_ID),
                        "variant_id": "00000000-0000-5000-8000-000000000203",
                        "title": "Fixture Product",
                    }
                ]
            },
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
    return (
        TestClient(create_app(service, media, limiter, commerce, development_identity=True)),
        planner,
        media,
    )


def headers(user: UUID = USER_A, **values: str) -> dict[str, str]:
    return {"X-User-ID": str(user), **values}


def create_thread(client: TestClient, user: UUID = USER_A) -> str:
    response = client.post("/v1/threads", json={"goal": "fixture shopping"}, headers=headers(user))
    assert response.status_code == 201
    return response.json()["thread_id"]


def event_ids(payload: str) -> list[int]:
    return [int(value) for value in re.findall(r"^id: (\d+)$", payload, re.MULTILINE)]


def test_mission_edit_http_conflict_preserves_goal_until_approval_lock_released() -> None:
    client, _, _ = build_client()
    thread_id = create_thread(client)
    path = f"/v1/threads/{thread_id}"
    service = client.app.state.turn_service
    before = client.get(path, headers=headers()).json()
    with service.index.mission_guard(UUID(thread_id)):
        conflict = client.patch(path + "/constraints", json={"goal": "new goal"}, headers=headers())
        assert conflict.status_code == 409
        assert client.get(path, headers=headers()).json() == before
    edited = client.patch(path + "/constraints", json={"goal": "new goal"}, headers=headers())
    assert edited.status_code == 200
    assert edited.json()["version"] == 2


def test_snapshot_pairs_cursor_with_its_run_and_clears_it_after_mission_edit() -> None:
    client, _, _ = build_client()
    thread_id = create_thread(client)
    path = f"/v1/threads/{thread_id}"
    empty = client.get(path, headers=headers()).json()
    assert empty["active_run_id"] is None
    assert empty["last_event_id"] == 0
    run_ids = []
    for key in ("cursor-first", "cursor-second"):
        turn = client.post(
            path + "/turns",
            json={"text": "fixture", "media_ids": []},
            headers=headers(**{"Idempotency-Key": key}),
        )
        assert turn.status_code == 202
        run_ids.append(turn.json()["run_id"])
        snapshot = client.get(path, headers=headers()).json()
        events = client.get(f"/v1/agent-runs/{run_ids[-1]}/events", headers=headers()).text
        assert snapshot["active_run_id"] == run_ids[-1]
        assert snapshot["last_event_id"] == max(event_ids(events))
    assert run_ids[0] != run_ids[1]
    assert (
        client.patch(
            path + "/constraints",
            json={"goal": "new goal"},
            headers=headers(),
        ).status_code
        == 200
    )
    edited = client.get(path, headers=headers()).json()
    assert edited["active_run_id"] is None
    assert edited["last_event_id"] == 0


def test_snapshot_keeps_mission_candidates_during_followup_approval() -> None:
    client, planner, _ = build_client()
    thread_id = create_thread(client)
    path = f"/v1/threads/{thread_id}"
    first = client.post(
        path + "/turns",
        json={"text": "fixture", "media_ids": []},
        headers=headers(**{"Idempotency-Key": "recommendation"}),
    )
    assert first.status_code == 202
    candidates = client.get(path, headers=headers()).json()["candidates"]
    assert len(candidates) == 1
    planner.call = ToolCall(
        "cart.update", {"operation": "add", "offer_id": "00000000-0000-5000-8000-000000000202"}
    )
    second = client.post(
        path + "/turns",
        json={"text": "add the recommended offer", "media_ids": []},
        headers=headers(**{"Idempotency-Key": "proposal"}),
    )
    assert second.status_code == 202
    run_id = second.json()["run_id"]
    snapshot = client.get(path, headers=headers()).json()
    assert snapshot["candidates"] == candidates
    assert snapshot["status"] == "WAITING_APPROVAL"
    assert snapshot["pending_action"] == "cart.update"
    assert snapshot["active_run_id"] == run_id
    assert snapshot["last_event_id"] == max(
        event_ids(client.get(f"/v1/agent-runs/{run_id}/events", headers=headers()).text)
    )
    assert client.get(path, headers=headers(USER_B)).status_code == 404
    assert (
        client.post(
            f"/v1/agent-runs/{run_id}/decisions",
            json={"tool_name": "cart.update", "approved": False},
            headers=headers(),
        ).status_code
        == 200
    )
    assert client.get(path, headers=headers()).json()["candidates"] == candidates
    assert (
        client.patch(
            path + "/constraints", json={"goal": "a different Mission"}, headers=headers()
        ).status_code
        == 200
    )
    assert client.get(path, headers=headers()).json()["candidates"] == []


def test_explicit_empty_product_result_does_not_restore_previous_candidates() -> None:
    values = [
        {
            "product_id": str(PRODUCT_ID),
            "variant_id": "00000000-0000-5000-8000-000000000203",
            "title": "Fixture Product",
        }
    ]

    def read(_context, _args):
        return ToolResult(
            {"products": list(values)},
            (ToolEvidence("seed:fixture", "0" * 64, ("title",)),),
            frozenset({"title"}),
        )

    client, _, _ = build_client(override=read)
    path = f"/v1/threads/{create_thread(client)}"
    for index in range(2):
        assert (
            client.post(
                path + "/turns",
                json={"text": "fixture", "media_ids": []},
                headers=headers(**{"Idempotency-Key": f"search-{index}"}),
            ).status_code
            == 202
        )
        assert len(client.get(path, headers=headers()).json()["candidates"]) == (
            1 if index == 0 else 0
        )
        values.clear()


def test_parse_mission_returns_typed_multi_item_constraints() -> None:
    client, _, _ = build_client()

    response = client.post(
        "/v1/missions/parse",
        json={"goal": "预算 5000 元以内, 显示器必须 4K, 耳机优先降噪, 周五前送达。"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "goal": "预算 5000 元以内, 显示器必须 4K, 耳机优先降噪, 周五前送达。",
        "version": 1,
        "items": [
            {"category": "显示器", "quantity": 1},
            {"category": "耳机", "quantity": 1},
        ],
        "hard_constraints": ["预算 5000 元以内", "显示器必须 4K", "周五前送达"],
        "soft_preferences": ["耳机优先降噪"],
        "unknowns": ["各品类预算分配"],
        "budget_total_minor": 500000,
        "currency": "CNY",
    }


def test_thread_snapshot_keeps_the_structured_mission_from_the_event_log() -> None:
    client, _, _ = build_client()
    created = client.post(
        "/v1/threads",
        json={"goal": "预算 3000 元, 笔记本必须 16GB, 外观可以妥协。"},
        headers=headers(),
    )
    thread_id = created.json()["thread_id"]

    before_turn = client.get(f"/v1/threads/{thread_id}", headers=headers()).json()
    assert before_turn["mission"]["items"] == [{"category": "笔记本", "quantity": 1}]

    accepted = client.post(
        f"/v1/threads/{thread_id}/turns",
        json={"text": "预算 3000 元, 笔记本必须 16GB, 外观可以妥协。"},
        headers=headers(**{"Idempotency-Key": "mission-structure-1"}),
    )
    assert accepted.status_code == 202
    snapshot = client.get(f"/v1/threads/{thread_id}", headers=headers()).json()
    assert snapshot["mission"]["hard_constraints"] == ["笔记本必须 16GB"]
    assert snapshot["mission"]["soft_preferences"] == ["外观可以妥协"]


def test_constraint_edit_creates_a_new_mission_version_before_recalculation() -> None:
    client, _, _ = build_client()
    thread_id = create_thread(client)
    accepted = client.post(
        f"/v1/threads/{thread_id}/turns",
        json={"text": "fixture shopping"},
        headers=headers(**{"Idempotency-Key": "mission-before-edit"}),
    )
    assert accepted.status_code == 202

    edited = client.patch(
        f"/v1/threads/{thread_id}/constraints",
        json={"goal": "预算 1200 元, 耳机必须降噪, 外观可以妥协。"},
        headers=headers(),
    )

    assert edited.status_code == 200
    assert edited.json()["version"] == 2
    assert edited.json()["hard_constraints"] == ["耳机必须降噪"]
    assert edited.json()["soft_preferences"] == ["外观可以妥协"]
    snapshot = client.get(f"/v1/threads/{thread_id}", headers=headers()).json()
    assert snapshot["goal"] == edited.json()["goal"]
    assert snapshot["mission"]["version"] == 2


def test_user_comparison_selection_is_persisted_and_rejects_foreign_products() -> None:
    client, _, _ = build_client()
    thread_id = create_thread(client)
    accepted = client.post(
        f"/v1/threads/{thread_id}/turns",
        json={"text": "headphones"},
        headers=headers(**{"Idempotency-Key": "comparison-selection-1"}),
    )
    assert accepted.status_code == 202

    selected = client.put(
        f"/v1/threads/{thread_id}/comparison",
        json={"product_ids": [str(PRODUCT_ID)]},
        headers=headers(),
    )
    replayed = client.put(
        f"/v1/threads/{thread_id}/comparison",
        json={"product_ids": [str(PRODUCT_ID)]},
        headers=headers(),
    )
    restored = client.get(
        f"/v1/threads/{thread_id}/comparison",
        headers=headers(),
    )
    snapshot = client.get(f"/v1/threads/{thread_id}", headers=headers())

    assert selected.status_code == replayed.status_code == restored.status_code == 200
    assert restored.json() == {"product_ids": [str(PRODUCT_ID)]}
    assert snapshot.json()["selected_product_ids"] == [str(PRODUCT_ID)]

    foreign = client.put(
        f"/v1/threads/{thread_id}/comparison",
        json={"product_ids": ["00000000-0000-5000-8000-000000000999"]},
        headers=headers(),
    )
    assert foreign.status_code == 422


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
    assert "event: mission_updated" in complete.text
    assert "event: products" in complete.text
    assert f'"product_id":"{PRODUCT_ID}"' in complete.text


def test_clarification_answer_updates_mission_before_retrieval() -> None:
    client, planner, _ = build_client(clarify_first=True)
    thread_id = create_thread(client)
    first = client.post(
        f"/v1/threads/{thread_id}/turns",
        json={"text": "通勤降噪耳机", "media_ids": []},
        headers=headers(**{"Idempotency-Key": "clarification-1"}),
    )
    first_events = client.get(
        f"/v1/agent-runs/{first.json()['run_id']}/events",
        headers=headers(),
    )
    waiting = client.get(f"/v1/threads/{thread_id}", headers=headers())
    assert "event: clarification_required" in first_events.text
    assert waiting.json()["status"] == "WAITING_CLARIFICATION"

    second = client.post(
        f"/v1/threads/{thread_id}/turns",
        json={"text": "预算 1000 元", "media_ids": []},
        headers=headers(**{"Idempotency-Key": "clarification-2"}),
    )
    second_events = client.get(
        f"/v1/agent-runs/{second.json()['run_id']}/events",
        headers=headers(),
    )
    completed = client.get(f"/v1/threads/{thread_id}", headers=headers())
    assert "event: completed" in second_events.text
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["goal"] == "fixture shopping; 预算 1000 元"
    assert planner.commands[-1].text == "fixture shopping; 预算 1000 元"


def test_text_image_and_audio_use_the_same_turn_command_and_runtime() -> None:
    client, planner, _ = build_client()
    thread_id = create_thread(client)
    image = client.post(
        "/v1/media",
        content=b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82",
        headers=headers(**{"Content-Type": "image/png"}),
    )
    audio = client.post(
        "/v1/media",
        content=b"RIFFd\x01\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data@\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00",
        headers=headers(**{"Content-Type": "audio/wav"}),
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

    # Media now takes the typed consent/understanding stage before model planning.
    assert len(planner.commands) == 1
    assert planner.commands[0].text == "text turn"


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
    media.IMAGE_LIMIT = InMemoryMediaStore.IMAGE_LIMIT
    valid = client.post(
        "/v1/media",
        content=b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82",
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
        ToolCall(
            "cart.update",
            {"operation": "add", "offer_id": "00000000-0000-5000-8000-000000000202"},
        ),
        update,
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

    repeated = client.post(
        f"/v1/agent-runs/{run_id}/decisions",
        json={"tool_name": "cart.update", "approved": True},
        headers=headers(),
    )
    assert repeated.status_code == 200
    assert calls == 1


def test_cancelled_decision_has_no_tool_side_effect() -> None:
    calls = 0

    def update(_: ToolExecutionContext, __: BaseModel) -> ToolResult:
        nonlocal calls
        calls += 1
        return ToolResult()

    client, _, _ = build_client(
        ToolCall(
            "cart.update",
            {"operation": "add", "offer_id": "00000000-0000-5000-8000-000000000202"},
        ),
        update,
    )
    thread_id = create_thread(client)
    turn = client.post(
        f"/v1/threads/{thread_id}/turns",
        json={"text": "add fixture", "media_ids": []},
        headers=headers(**{"Idempotency-Key": "decision-cancel-1"}),
    )
    cancelled = client.post(
        f"/v1/agent-runs/{turn.json()['run_id']}/decisions",
        json={"tool_name": "cart.update", "approved": False},
        headers=headers(),
    )
    assert cancelled.status_code == 200
    assert calls == 0

    # Rebuild the service/runtime over the same stores: recovery must use saved events.
    service = client.app.state.turn_service
    agent = service.agent
    client = TestClient(
        create_app(
            service=TurnService(
                ShoppingAgent(agent.planner, agent.tools, agent.store, agent.identity),
                service.media,
                service.index,
            ),
            development_identity=True,
        )
    )
    run_id = turn.json()["run_id"]
    snapshot = client.get(f"/v1/threads/{thread_id}", headers=headers()).json()
    assert snapshot["status"] == "COMPLETED"
    assert snapshot["pending_action"] is None
    events = client.get(f"/v1/agent-runs/{run_id}/events", headers=headers()).text
    assert '"reason":"approval_rejected"' in events
    repeated = client.post(
        f"/v1/agent-runs/{run_id}/decisions",
        json={"tool_name": "cart.update", "approved": False},
        headers=headers(),
    )
    assert repeated.status_code == 200
    assert repeated.json()["event_count"] == cancelled.json()["event_count"]
    contradictory = client.post(
        f"/v1/agent-runs/{run_id}/decisions",
        json={"tool_name": "cart.update", "approved": True},
        headers=headers(),
    )
    assert contradictory.status_code == 409
    assert calls == 0


def test_unconfigured_business_api_is_explicitly_unavailable() -> None:
    client = TestClient(create_app(development_identity=True))
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

    def get_product(self, user_id: UUID, product_id: UUID) -> dict[str, object]:
        return {
            "product_id": str(product_id),
            "variant_id": str(self.variant_id),
            "title": "Fixture Product",
            "category": "耳机",
            "brand": "Demo Audio",
            "attributes": {"降噪": "支持"},
            "image_ref": None,
            "evidence_refs": ["fixture:catalog-product-1"],
        }

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
        product = self.get_product(user_id, PRODUCT_ID)
        value = CartView(
            items=[
                CartItemView(
                    offer_id=request.offer_id,
                    quantity=request.quantity,
                    product=product,
                    quote=self.get_offers(user_id, PRODUCT_ID, False).offers[0],
                )
            ]
        )
        self.carts[user_id] = value
        return value


def test_commerce_routes_delegate_grounded_facts_lists_and_cart() -> None:
    commerce = FixtureCommerce()
    client, _, _ = build_client(commerce=commerce)
    product_id = PRODUCT_ID
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
    assert len(cart.json()["items"]) == 1
    assert cart.json()["items"][0]["offer_id"] == str(commerce.offer_id)
    assert cart.json()["items"][0]["quantity"] == 2
    assert cart.json()["items"][0]["product"]["title"] == "Fixture Product"
    assert cart.json()["items"][0]["quote"]["offer_id"] == str(commerce.offer_id)
    assert client.get("/v1/cart", headers=headers()).json() == cart.json()


def test_thread_snapshot_and_product_fact_are_hydratable() -> None:
    commerce = FixtureCommerce()
    client, _, _ = build_client(commerce=commerce)
    thread_id = create_thread(client)

    empty = client.get(f"/v1/threads/{thread_id}", headers=headers())
    assert empty.status_code == 200
    assert empty.json()["status"] == "IDLE"
    assert empty.json()["candidates"] == []

    accepted = client.post(
        f"/v1/threads/{thread_id}/turns",
        json={"text": "通勤降噪耳机", "media_ids": []},
        headers=headers(**{"Idempotency-Key": "snapshot-1"}),
    )
    assert accepted.status_code == 202
    snapshot = client.get(f"/v1/threads/{thread_id}", headers=headers())
    assert snapshot.status_code == 200
    assert snapshot.json()["status"] == "COMPLETED"
    assert snapshot.json()["candidates"][0]["title"] == "Fixture Product"
    assert snapshot.json()["last_event_id"] > 0

    product_id = PRODUCT_ID
    product = client.get(f"/v1/products/{product_id}", headers=headers())
    assert product.status_code == 200
    assert product.json()["evidence_refs"] == ["fixture:catalog-product-1"]
