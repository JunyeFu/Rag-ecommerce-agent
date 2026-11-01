from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import psycopg
import pytest
from pydantic import BaseModel
from ragcommerce_agent_runtime import (
    FROZEN_TOOL_TYPES,
    PostgresCheckpointStore,
    RuntimeIdentity,
    ScriptedPlanner,
    ShoppingAgent,
    ToolCall,
    ToolExecutionContext,
    ToolRegistry,
    ToolResult,
)
from ragcommerce_api.media import InMemoryMediaStore
from ragcommerce_api.postgres_demo import PostgresDemoCommerce
from ragcommerce_api.postgres_index import PostgresTurnIndex
from ragcommerce_api.service import DecisionConflict, TurnService
from ragcommerce_contracts import (
    CartMutation,
    CreateListRequest,
    CreateWatcherRequest,
    PatchListRequest,
)
from ragcommerce_worker import TurnWorker

pytestmark = pytest.mark.integration
IDENTITY = RuntimeIdentity("shopping-agent-v1", "fake-api-v1", "p1", "policy1", "0.2.0")
ROOT = Path(__file__).resolve().parents[3]


def test_approval_is_durable_and_returns_before_worker_executes():
    dsn = database_url()
    commerce = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn)
    owner = uuid4()
    offer = UUID(next(iter(commerce.rows.values()))["offer"]["offer_id"])

    def service(quantity=2):
        index = PostgresTurnIndex(dsn)
        return TurnService(
            ShoppingAgent(
                ScriptedPlanner(
                    (
                        ToolCall(
                            "cart.update",
                            {"operation": "add", "offer_id": str(offer), "quantity": quantity},
                        ),
                    )
                ),
                ToolRegistry(commerce.tool_handlers()),
                PostgresCheckpointStore(dsn),
                IDENTITY,
            ),
            InMemoryMediaStore(),
            index,
        )

    first = service()
    thread = first.create_thread(owner, "durable approval")
    record, _ = submit(first, owner, thread.id)
    accepted = asyncio.run(first.decide(owner, record.run_id, "cart.update", True))
    assert accepted.execution_status == "PENDING"
    assert not commerce.get_cart(owner).items
    # Changed planner after process recreation cannot change the approved quantity.
    restarted = service(99)
    assert restarted.snapshot(owner, thread.id).status == "RUNNING"
    assert restarted.snapshot(owner, thread.id).pending_action is None
    assert (
        asyncio.run(restarted.decide(owner, record.run_id, "cart.update", True)).execution_status
        == "PENDING"
    )
    with pytest.raises(DecisionConflict):
        asyncio.run(restarted.decide(owner, record.run_id, "cart.update", False))
    with pytest.raises(DecisionConflict):
        restarted.update_mission(owner, thread.id, "another mission goal")
    worker = TurnWorker(restarted.index, restarted)
    assert asyncio.run(worker.run_once())
    assert restarted.snapshot(owner, thread.id).status == "COMPLETED"
    assert commerce.get_cart(owner).items[0].quantity == 2
    replay = asyncio.run(restarted.decide(owner, record.run_id, "cart.update", True))
    assert replay.execution_status == "COMPLETED"
    assert not asyncio.run(worker.run_once())
    with psycopg.connect(dsn) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM v3_tool_receipts WHERE owner_id=%s", (owner,)
            ).fetchone()[0]
            == 1
        )


def test_approval_does_not_authorize_a_second_call_with_different_arguments():
    dsn = database_url()
    commerce = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn)
    owner = uuid4()
    offer = UUID(next(iter(commerce.rows.values()))["offer"]["offer_id"])
    calls = tuple(
        ToolCall("cart.update", {"operation": "set", "offer_id": str(offer), "quantity": q})
        for q in (2, 99)
    )
    service = TurnService(
        ShoppingAgent(
            ScriptedPlanner(calls),
            ToolRegistry(commerce.tool_handlers()),
            PostgresCheckpointStore(dsn),
            IDENTITY,
        ),
        InMemoryMediaStore(),
        PostgresTurnIndex(dsn),
    )
    thread = service.create_thread(owner, "scope one confirmation")
    record, _ = submit(service, owner, thread.id)
    asyncio.run(service.decide(owner, record.run_id, "cart.update", True))
    completed = asyncio.run(service.execute(record.run_id))
    assert completed.execution_status == "FAILED"
    assert commerce.get_cart(owner).items[0].quantity == 2
    with pytest.raises(DecisionConflict):
        asyncio.run(service.decide(owner, record.run_id, "cart.update", True))
    with psycopg.connect(dsn) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM v3_tool_receipts WHERE owner_id=%s", (owner,)
            ).fetchone()[0]
            == 1
        )


def test_exploration_pg_transaction_replay_recovery_and_conversion() -> None:
    from ragcommerce_api.demo import DemoProvider
    from ragcommerce_api.service import IdempotencyConflict
    from ragcommerce_contracts import ExplorationAction

    dsn = database_url()
    commerce = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn)

    def service():
        return TurnService(
            ShoppingAgent(
                DemoProvider(),
                ToolRegistry(commerce.tool_handlers()),
                PostgresCheckpointStore(dsn),
                IDENTITY,
            ),
            InMemoryMediaStore(),
            PostgresTurnIndex(dsn),
        )

    first = service()
    user = uuid4()
    thread = first.create_thread(user, "随便看看")
    directions = commerce.exploration_directions()

    def submit(app, action, version, key):
        return asyncio.run(
            app.submit(
                user, thread.id, key, "", (), ExplorationAction(**action), version, directions
            )
        )

    run, replayed = submit(first, {"kind": "start"}, 1, "start")
    assert not replayed
    # Reconstruct before execution: state and durable job both survived.
    restored = service()
    assert restored.snapshot(user, thread.id).mode == "DISCOVERY"
    claimed = restored.index.claim(run.run_id)
    assert claimed is not None
    asyncio.run(restored.execute_claimed(claimed))
    snap = restored.snapshot(user, thread.id)
    assert snap.status == "COMPLETED" and snap.mission.version == 2
    assert submit(restored, {"kind": "start"}, 1, "start")[1]
    with pytest.raises(IdempotencyConflict):
        submit(restored, {"kind": "next"}, 1, "start")
    direction = snap.exploration.directions[0].direction_id
    feedback, _ = submit(
        restored,
        {"kind": "feedback", "direction_id": direction, "value": "not_interested"},
        2,
        "feedback",
    )
    asyncio.run(restored.execute(feedback.run_id))
    assert service().snapshot(user, thread.id).exploration.feedback[direction] == "not_interested"
    # Invalid transition rolls back both state and turn reservation.
    with pytest.raises(ValueError):
        submit(restored, {"kind": "select_for_purchase", "direction_id": direction}, 3, "invalid")
    assert service().snapshot(user, thread.id).mission.version == 3
    with restored.index.mission_guard(thread.id), pytest.raises(DecisionConflict):
        submit(restored, {"kind": "next"}, 3, "locked")
    undo, _ = submit(
        restored, {"kind": "feedback", "direction_id": direction, "value": "neutral"}, 3, "undo"
    )
    asyncio.run(restored.execute(undo.run_id))
    selected, _ = submit(
        restored, {"kind": "select_for_purchase", "direction_id": direction}, 4, "select"
    )
    asyncio.run(restored.execute(selected.run_id))
    final = service().snapshot(user, thread.id)
    assert final.mode == "PURCHASE" and final.status == "WAITING_CLARIFICATION"
    assert commerce.get_cart(user).items == []
    with psycopg.connect(dsn) as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM api_turns WHERE thread_id=%s", (thread.id,)
            ).fetchone()[0]
            == 4
        )


def test_clarification_reservation_is_atomic_under_duplicate_submissions() -> None:
    from ragcommerce_agent_runtime import TurnCommand
    from ragcommerce_api.service import ThreadRecord, TurnRecord

    index = PostgresTurnIndex(database_url())
    owner, thread_id = uuid4(), uuid4()
    index.create_thread(ThreadRecord(thread_id, uuid4(), owner, "headphones"))

    def candidate(key, text):
        run = uuid4()
        return TurnRecord(
            owner, thread_id, run, key, text, TurnCommand(owner, thread_id, run, key, text)
        )

    first, _ = index.reserve(candidate("initial", "headphones"))
    index.update_status(first.run_id, "WAITING_CLARIFICATION")
    before = index.get_thread(thread_id)
    replay, created = index.reserve(candidate("initial", "different body"))
    assert not created and replay.fingerprint == "headphones"
    assert index.get_thread(thread_id) == before
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: index.reserve(candidate("answer", "budget 1000")), range(2))
        )
    assert sum(created for _, created in results) == 1
    assert len({record.run_id for record, _ in results}) == 1
    updated = index.get_thread(thread_id)
    assert updated.mission_version == 2
    assert updated.goal == "headphones; budget 1000"
    assert all(record.command.mission_version == 2 for record, _ in results)
    index.update_status(results[0][0].run_id, "COMPLETED")
    index.update_comparison(owner, thread_id, (uuid4(),))
    edited = index.update_goal(owner, thread_id, "new goal")
    assert edited.selected_product_ids == ()


def test_postgres_invalid_catalog_writes_leave_state_unchanged() -> None:
    commerce = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", database_url())
    user, unknown = uuid4(), uuid4()
    original = commerce.create_list(user, CreateListRequest(name="original"))
    with pytest.raises(KeyError):
        commerce.patch_list(
            user, original.list_id, PatchListRequest(name="changed", add_variant_id=unknown)
        )
    with pytest.raises(KeyError):
        commerce.mutate_cart(user, CartMutation(operation="add", offer_id=unknown, quantity=1))
    assert commerce.get_lists(user).lists == [original]
    assert commerce.get_cart(user).items == []


def test_global_cart_survives_service_recreation_without_renewing_expired_quote():
    from datetime import UTC, datetime, timedelta

    from psycopg.types.json import Jsonb

    dsn = database_url()
    commerce = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn)
    owner, other = uuid4(), uuid4()
    product_id = next(iter(commerce.rows))
    quote = commerce.get_offers(owner, product_id, False).offers[0]
    expired = quote.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(minutes=1)})
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "UPDATE v3_demo_quotes SET quote=%s WHERE owner_id=%s AND product_id=%s",
            (Jsonb(expired.model_dump(mode="json")), owner, product_id),
        )
    commerce.mutate_cart(owner, CartMutation(operation="set", offer_id=quote.offer_id, quantity=2))
    restarted = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn)
    item = restarted.get_cart(owner).items[0]
    assert item.product.product_id == product_id
    assert item.product.title == commerce.rows[product_id]["title"]
    assert item.quote == expired and item.quantity == 2
    assert restarted.get_cart(other).items == []
    removed = restarted.mutate_cart(
        owner, CartMutation(operation="remove", offer_id=quote.offer_id)
    )
    assert removed.items == []
    assert restarted.get_offers(owner, product_id, False).offers == [expired]


def test_postgres_watcher_threshold_edit_preserves_identity() -> None:
    from ragcommerce_api.service import ThreadRecord

    commerce = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", database_url())
    user, thread = uuid4(), uuid4()
    PostgresTurnIndex(database_url()).create_thread(ThreadRecord(thread, uuid4(), user, "watch"))
    request = CreateWatcherRequest(
        kind="PRICE_BELOW", offer_id=next(iter(commerce.offers)), threshold_minor=50000
    )
    first = commerce.create_watcher(user, thread, request)
    updated = commerce.create_watcher(
        user, thread, request.model_copy(update={"threshold_minor": 40000})
    )
    assert updated.watcher_id == first.watcher_id and updated.created_at == first.created_at
    assert updated.threshold_minor == 40000
    assert commerce.get_watchers(user, thread).watchers == [updated]


def database_url() -> str:
    value = os.environ.get("API_DATABASE_URL")
    if not value:
        pytest.skip("API_DATABASE_URL is required for API integration")
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def test_postgres_decision_history_feedback_and_messages_survive_recreation():
    from ragcommerce_api.demo import DemoProvider
    from ragcommerce_api.service import OwnershipError
    from ragcommerce_contracts import CandidateFeedback, ThreadHistoryPatch

    dsn = database_url()
    commerce = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn)
    owner, other = uuid4(), uuid4()

    def service():
        return TurnService(
            ShoppingAgent(
                DemoProvider(),
                ToolRegistry(commerce.tool_handlers()),
                PostgresCheckpointStore(dsn),
                IDENTITY,
            ),
            InMemoryMediaStore(),
            PostgresTurnIndex(dsn),
        )

    original = service()
    thread = original.create_thread(owner, "预算1000元通勤耳机")

    async def run():
        record, _ = await original.submit(owner, thread.id, "ux-first", "预算1000元通勤耳机", ())
        await original.execute(record.run_id)
        return record

    asyncio.run(run())
    first = original.snapshot(owner, thread.id)
    product = first.candidates[0]
    original.organize(owner, thread.id, ThreadHistoryPatch(title="通勤备选", archived=True))
    original.feedback(
        owner,
        thread.id,
        CandidateFeedback(
            product_id=product.product_id,
            expected_mission_version=first.mission.version,
            reason="这一款不适合",
        ),
        "耳机",
    )
    restored = service()
    snapshot = restored.snapshot(owner, thread.id)
    assert snapshot.experience.title == "通勤备选"
    assert snapshot.experience.archived is True
    key = f"PRODUCT:{product.product_id}"
    assert snapshot.experience.feedback == {key: "这一款不适合"}
    assert restored.history(owner)[0].thread_id == thread.id
    assert restored.history(other) == []
    assert any(
        m.role == "user" and m.text == "预算1000元通勤耳机"
        for m in restored.messages(owner, thread.id)
    )
    with pytest.raises(OwnershipError):
        restored.undo_feedback(other, thread.id, key, snapshot.mission.version)
    restored.undo_feedback(owner, thread.id, key, snapshot.mission.version)
    assert service().snapshot(owner, thread.id).experience.feedback == {}


def test_candidate_feedback_reason_is_part_of_durable_model_context():
    from ragcommerce_agent_runtime import TurnCommand
    from ragcommerce_api.postgres_index import command_json, parse_command

    command = TurnCommand(
        uuid4(),
        uuid4(),
        uuid4(),
        "feedback-context",
        mission_goal="预算1000元,续航重要",
        excluded_product_ids=("p",),
        recommendation_feedback={"PRODUCT:p": "太重,但保留续航要求"},
    )
    restored = parse_command(command_json(command))
    assert restored.mission_goal == command.mission_goal
    assert restored.excluded_product_ids == ("p",)
    assert restored.recommendation_feedback == {"PRODUCT:p": "太重,但保留续航要求"}


def test_new_search_gets_current_quote_without_silently_refreshing_restored_quote():
    from datetime import UTC, datetime, timedelta

    from ragcommerce_api.demo import DemoProvider

    dsn = database_url()
    commerce = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn)
    owner = uuid4()
    for row in commerce.rows.values():
        quote = commerce.get_offers(owner, UUID(row["product_id"]), True).offers[0]
        expired = quote.model_copy(
            update={
                "collected_at": datetime.now(UTC) - timedelta(hours=2),
                "expires_at": datetime.now(UTC) - timedelta(hours=1),
            }
        )
        with psycopg.connect(dsn) as connection:
            from psycopg.types.json import Jsonb

            connection.execute(
                "UPDATE v3_demo_quotes SET quote=%s WHERE owner_id=%s AND product_id=%s",
                (Jsonb(expired.model_dump(mode="json")), owner, UUID(row["product_id"])),
            )
    product_id = UUID(next(iter(commerce.rows.values()))["product_id"])
    assert commerce.get_offers(owner, product_id, False).offers[0].expires_at < datetime.now(UTC)
    app = TurnService(
        ShoppingAgent(
            DemoProvider(),
            ToolRegistry(commerce.tool_handlers()),
            PostgresCheckpointStore(dsn),
            IDENTITY,
        ),
        InMemoryMediaStore(),
        PostgresTurnIndex(dsn),
    )
    thread = app.create_thread(owner, "预算5000元办公电脑")

    async def run():
        record, _ = await app.submit(
            owner, thread.id, "fresh-search-after-expiry", "预算5000元办公电脑", ()
        )
        return await app.execute(record.run_id)

    result = asyncio.run(run())
    assert result.execution_status == "COMPLETED", [
        event.data for event in result.events if event.type.value == "failed"
    ]
    assert any(event.type.value == "offers" for event in result.events)
    # Ordinary cached reads still retain old expiry, requiring explicit requote.
    assert commerce.get_offers(owner, product_id, False).offers[0].expires_at < datetime.now(UTC)


def test_postgres_snapshot_preserves_candidates_across_approval_and_process_recreation() -> None:
    from ragcommerce_api.demo import DemoProvider
    from ragcommerce_api.service import OwnershipError

    dsn = database_url()
    commerce = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn)

    def service(planner):
        return TurnService(
            ShoppingAgent(
                planner,
                ToolRegistry(commerce.tool_handlers()),
                PostgresCheckpointStore(dsn),
                IDENTITY,
            ),
            InMemoryMediaStore(),
            PostgresTurnIndex(dsn),
        )

    owner = uuid4()
    first = service(DemoProvider())
    thread = first.create_thread(owner, "预算2000元的通勤手机")

    async def execute(app, key, text):
        record, _ = await app.submit(owner, thread.id, key, text, ())
        return await app.execute(record.run_id)

    asyncio.run(execute(first, "recommendation", thread.goal))
    original = first.snapshot(owner, thread.id).candidates
    assert original
    offer = commerce.rows[original[0].product_id]["offer"]["offer_id"]
    planner = ScriptedPlanner((ToolCall("cart.update", {"operation": "add", "offer_id": offer}),))
    followup = service(planner)
    proposal = asyncio.run(execute(followup, "proposal", "加入已推荐商品"))
    restored = service(planner)
    snapshot = restored.snapshot(owner, thread.id)
    assert snapshot.mission.goal == thread.goal
    assert snapshot.mission.budget_total_minor == 200000
    assert snapshot.mission.unknowns == []
    assert restored.require_run(owner, proposal.run_id).command.mission_goal == thread.goal
    assert snapshot.candidates == original
    assert snapshot.status == "WAITING_APPROVAL" and snapshot.pending_action == "cart.update"
    assert snapshot.active_run_id == proposal.run_id
    assert snapshot.last_event_id == restored.agent.replay(proposal.run_id)[-1].id
    with pytest.raises(OwnershipError):
        restored.snapshot(uuid4(), thread.id)
    asyncio.run(restored.decide(owner, proposal.run_id, "cart.update", False))
    assert service(planner).snapshot(owner, thread.id).candidates == original
    restored.update_mission(owner, thread.id, "预算1000元的耳机")
    assert service(planner).snapshot(owner, thread.id).candidates == []


@pytest.mark.parametrize("tool", ["cart.update", "list.update"])
def test_committed_tool_recovery_does_not_overwrite_later_user_change(tool) -> None:
    class Interrupted(BaseException):
        pass

    class InterruptedStore(PostgresCheckpointStore):
        def save(self, checkpoint):
            if checkpoint.completed_tools:
                raise Interrupted()
            super().save(checkpoint)

    dsn = database_url()
    commerce = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn)
    owner = uuid4()
    row = next(iter(commerce.rows.values()))
    offer_id, variant_id = UUID(row["offer"]["offer_id"]), UUID(row["variant_id"])
    shopping_list = commerce.create_list(owner, CreateListRequest(name="recovery"))
    args = (
        {"operation": "add", "offer_id": str(offer_id), "quantity": 1}
        if tool == "cart.update"
        else {
            "operation": "add",
            "list_id": str(shopping_list.list_id),
            "variant_id": str(variant_id),
        }
    )

    def service(store):
        return TurnService(
            ShoppingAgent(
                ScriptedPlanner((ToolCall(tool, args),)),
                ToolRegistry(
                    PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn).tool_handlers()
                ),
                store,
                IDENTITY,
            ),
            InMemoryMediaStore(),
            PostgresTurnIndex(dsn),
        )

    first = service(InterruptedStore(dsn))
    thread = first.create_thread(owner, "recover committed write")
    record, _ = submit(first, owner, thread.id)
    assert asyncio.run(first.decide(owner, record.run_id, tool, True)).execution_status == "PENDING"
    with pytest.raises(Interrupted):
        asyncio.run(first.execute(record.run_id))
    if tool == "cart.update":
        assert commerce.get_cart(owner).items[0].quantity == 1
        commerce.mutate_cart(owner, CartMutation(operation="set", offer_id=offer_id, quantity=3))
    else:
        assert commerce.get_lists(owner).lists[0].variant_ids == [variant_id]
        commerce.patch_list(
            owner, shopping_list.list_id, PatchListRequest(remove_variant_id=variant_id)
        )
    restarted = service(PostgresCheckpointStore(dsn))
    # Integration fault fixture only: expire this exact interrupted claim;
    # the separate real process acceptance never modifies the lease clock.
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "UPDATE api_turns SET claimed_at=NOW()-INTERVAL '6 minutes' WHERE run_id=%s",
            (record.run_id,),
        )
    reclaimed = restarted.index.claim_next()
    assert reclaimed is not None and reclaimed.run_id == record.run_id
    completed = asyncio.run(restarted.execute_claimed(reclaimed))
    assert completed.execution_status == "COMPLETED"
    if tool == "cart.update":
        assert commerce.get_cart(owner).items[0].quantity == 3
    else:
        assert commerce.get_lists(owner).lists[0].variant_ids == []


def test_receipt_failure_rolls_back_cart_and_receipts_are_owner_scoped() -> None:
    from psycopg import sql
    from ragcommerce_agent_runtime import TurnCommand
    from ragcommerce_api.erasure import PostgresUserDataEraser

    dsn = database_url()
    commerce = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn)
    owner, other, invocation = uuid4(), uuid4(), uuid4()
    offer_id = next(iter(commerce.offers))
    registry = ToolRegistry(commerce.tool_handlers())

    def execute(user, quantity=1):
        command = TurnCommand(
            user,
            uuid4(),
            uuid4(),
            "receipt-test",
            "fixture",
            approved_tools=frozenset({"cart.update"}),
            allow_reversible_writes=True,
        )
        context = ToolExecutionContext(
            user, command.thread_id, command.run_id, invocation, "receipt-test"
        )
        return registry.execute(
            command,
            ToolCall(
                "cart.update",
                {
                    "operation": "add",
                    "offer_id": str(offer_id),
                    "quantity": quantity,
                },
            ),
            context,
        )

    constraint = sql.Identifier("receipt_fault_" + owner.hex)
    with psycopg.connect(dsn) as connection:
        connection.execute(
            sql.SQL("ALTER TABLE v3_tool_receipts ADD CONSTRAINT {} CHECK (owner_id <> {})").format(
                constraint, sql.Literal(owner)
            )
        )
    try:
        with pytest.raises(psycopg.errors.CheckViolation):
            execute(owner)
        assert commerce.get_cart(owner).items == []
    finally:
        with psycopg.connect(dsn) as connection:
            connection.execute(
                sql.SQL("ALTER TABLE v3_tool_receipts DROP CONSTRAINT {}").format(constraint)
            )
    original = execute(owner)
    assert execute(owner) == original
    with pytest.raises(ValueError, match="different arguments"):
        execute(owner, 2)
    execute(other, 3)
    assert commerce.get_cart(owner).items[0].quantity == 1
    assert commerce.get_cart(other).items[0].quantity == 3
    PostgresUserDataEraser(dsn).delete_user(owner)
    # Deleted receipt must not replay the old response without restoring a new write.
    execute(owner)
    assert commerce.get_cart(owner).items[0].quantity == 1
    assert commerce.get_cart(other).items[0].quantity == 3


@pytest.mark.parametrize("second_decision", [False, True, "edit"])
def test_concurrent_contradictory_approval_is_rejected_and_terminal_is_unique(
    second_decision,
) -> None:
    entered, release = Event(), Event()
    call = ToolCall(
        "cart.update",
        {
            "operation": "add",
            "offer_id": "00000000-0000-5000-8000-000000000202",
        },
    )

    async def paused_tool(_context, _args):
        entered.set()
        assert await asyncio.to_thread(release.wait, 10)
        return ToolResult()

    def service():
        return TurnService(
            ShoppingAgent(
                ScriptedPlanner((call,)),
                ToolRegistry({name: paused_tool for name in FROZEN_TOOL_TYPES}),
                PostgresCheckpointStore(database_url()),
                IDENTITY,
            ),
            InMemoryMediaStore(),
            PostgresTurnIndex(database_url()),
        )

    first, second = service(), service()
    owner = uuid4()
    thread = first.create_thread(owner, "approval race")
    record, _ = submit(first, owner, thread.id)
    assert (
        asyncio.run(first.decide(owner, record.run_id, "cart.update", True)).execution_status
        == "PENDING"
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lambda: asyncio.run(first.execute(record.run_id)))
        try:
            assert entered.wait(5)
            if second_decision is True:
                replay = asyncio.run(second.decide(owner, record.run_id, "cart.update", True))
                assert replay.execution_status == "RUNNING"
            else:
                with pytest.raises(DecisionConflict):
                    if second_decision == "edit":
                        second.update_mission(owner, thread.id, "changed goal")
                    else:
                        asyncio.run(second.decide(owner, record.run_id, "cart.update", False))
            assert second.require_thread(owner, thread.id).mission_version == 1
        finally:
            release.set()
        future.result(timeout=10)
    restored = service().require_run(owner, record.run_id)
    terminals = [event for event in restored.events if event.type.value in {"completed", "failed"}]
    assert len(terminals) == 1
    assert terminals[0].data["reason"] == "COMPLETED"
    replay = asyncio.run(second.decide(owner, record.run_id, "cart.update", True))
    assert replay.events == restored.events


def test_rejected_approval_survives_postgres_service_recreation() -> None:
    def service():
        return TurnService(
            ShoppingAgent(
                ScriptedPlanner(
                    (
                        ToolCall(
                            "cart.update",
                            {
                                "operation": "add",
                                "offer_id": "00000000-0000-5000-8000-000000000202",
                            },
                        ),
                    )
                ),
                ToolRegistry(
                    {name: lambda _context, _args: ToolResult() for name in FROZEN_TOOL_TYPES}
                ),
                PostgresCheckpointStore(database_url()),
                IDENTITY,
            ),
            InMemoryMediaStore(),
            PostgresTurnIndex(database_url()),
        )

    first = service()
    owner = uuid4()
    thread = first.create_thread(owner, "reject and restart")
    record, _ = submit(first, owner, thread.id)
    rejected = asyncio.run(first.decide(owner, record.run_id, "cart.update", False))
    restored = service()
    snapshot = restored.snapshot(owner, thread.id)
    assert snapshot.status == "COMPLETED" and snapshot.pending_action is None
    assert snapshot.active_run_id == record.run_id
    replay = asyncio.run(restored.decide(owner, record.run_id, "cart.update", False))
    assert replay.events == rejected.events
    with pytest.raises(DecisionConflict):
        asyncio.run(restored.decide(owner, record.run_id, "cart.update", True))


def test_mission_edit_first_blocks_stale_approval_without_cart_write() -> None:
    dsn = database_url()
    commerce = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn)
    offer_id = next(iter(commerce.offers))
    service = TurnService(
        ShoppingAgent(
            ScriptedPlanner(
                (
                    ToolCall(
                        "cart.update",
                        {
                            "operation": "add",
                            "offer_id": str(offer_id),
                        },
                    ),
                )
            ),
            ToolRegistry(commerce.tool_handlers()),
            PostgresCheckpointStore(dsn),
            IDENTITY,
        ),
        InMemoryMediaStore(),
        PostgresTurnIndex(dsn),
    )
    owner = uuid4()
    thread = service.create_thread(owner, "headphones")
    record, _ = submit(service, owner, thread.id)
    assert record.execution_status == "WAITING_APPROVAL"
    assert service.update_mission(owner, thread.id, "camera").version == 2
    with pytest.raises(DecisionConflict, match="earlier Mission version"):
        asyncio.run(service.decide(owner, record.run_id, "cart.update", True))
    assert commerce.get_cart(owner).items == []
    assert service.snapshot(owner, thread.id).active_run_id is None
    # The rejected stale request must release the Mission lock.
    assert service.update_mission(owner, thread.id, "laptop").version == 3


def submit(service: TurnService, owner_id: UUID, thread_id: UUID):
    async def submit_and_execute():
        record, replayed = await service.submit(owner_id, thread_id, "api-restart-1", "fixture", ())
        if not replayed:
            record = await service.execute(record.run_id)
        return record, replayed

    return asyncio.run(submit_and_execute())


def test_postgres_index_and_agent_events_survive_api_process_recreation() -> None:
    calls = 0

    def counted(_: ToolExecutionContext, __: BaseModel) -> ToolResult:
        nonlocal calls
        calls += 1
        return ToolResult()

    handlers: dict[str, Callable[[ToolExecutionContext, BaseModel], ToolResult]] = {
        name: counted for name in FROZEN_TOOL_TYPES
    }
    planner = ScriptedPlanner((ToolCall("catalog.search", {"query": "fixture"}),))
    first_agent = ShoppingAgent(
        planner,
        ToolRegistry(handlers),
        PostgresCheckpointStore(database_url()),
        IDENTITY,
    )
    first = TurnService(first_agent, InMemoryMediaStore(), PostgresTurnIndex(database_url()))
    owner_id = uuid4()
    thread = first.create_thread(owner_id, "restart fixture")
    selected_product_id = uuid4()
    first.index.update_comparison(owner_id, thread.id, (selected_product_id,))
    initial, replayed = submit(first, owner_id, thread.id)
    assert replayed is False
    assert calls == 1

    recreated_agent = ShoppingAgent(
        planner,
        ToolRegistry(handlers),
        PostgresCheckpointStore(database_url()),
        IDENTITY,
    )
    recreated = TurnService(
        recreated_agent, InMemoryMediaStore(), PostgresTurnIndex(database_url())
    )
    replay, replayed = submit(recreated, owner_id, thread.id)
    loaded = recreated.require_run(owner_id, initial.run_id)
    restored_thread = recreated.require_thread(owner_id, thread.id)

    assert replayed is True
    assert calls == 1
    assert [event.id for event in replay.events] == [event.id for event in initial.events]
    assert [event.id for event in loaded.events] == [event.id for event in initial.events]
    assert loaded.events[-1].type.value == "completed"
    assert restored_thread.selected_product_ids == (selected_product_id,)


def test_concurrent_workers_claim_once_and_emit_one_terminal_event() -> None:
    def search(_: ToolExecutionContext, __: BaseModel) -> ToolResult:
        return ToolResult()

    planner = ScriptedPlanner((ToolCall("catalog.search", {"query": "fixture"}),))
    index = PostgresTurnIndex(database_url())
    service = TurnService(
        ShoppingAgent(
            planner,
            ToolRegistry({name: search for name in FROZEN_TOOL_TYPES}),
            PostgresCheckpointStore(database_url()),
            IDENTITY,
        ),
        InMemoryMediaStore(),
        index,
    )
    owner_id = uuid4()
    thread = service.create_thread(owner_id, "concurrent claim fixture")

    async def reserve():
        return await service.submit(owner_id, thread.id, "claim-once-1", "fixture", ())

    pending, replayed = asyncio.run(reserve())
    assert replayed is False
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = tuple(pool.map(lambda _: index.claim_next(), range(2)))
    claimed = [record for record in claims if record is not None]

    assert [record.run_id for record in claimed] == [pending.run_id]
    asyncio.run(service.execute_claimed(claimed[0]))
    loaded = service.require_run(owner_id, pending.run_id)
    terminal = [
        event.type.value for event in loaded.events if event.type.value in {"completed", "failed"}
    ]

    assert terminal == ["completed"]


def test_stale_worker_claim_is_recovered_after_restart() -> None:
    def search(_: ToolExecutionContext, __: BaseModel) -> ToolResult:
        return ToolResult()

    dsn = database_url()
    planner = ScriptedPlanner((ToolCall("catalog.search", {"query": "fixture"}),))
    index = PostgresTurnIndex(dsn)
    service = TurnService(
        ShoppingAgent(
            planner,
            ToolRegistry({name: search for name in FROZEN_TOOL_TYPES}),
            PostgresCheckpointStore(dsn),
            IDENTITY,
        ),
        InMemoryMediaStore(),
        index,
    )
    owner_id = uuid4()
    thread = service.create_thread(owner_id, "worker restart fixture")

    async def reserve():
        return await service.submit(owner_id, thread.id, "worker-restart-1", "fixture", ())

    pending, replayed = asyncio.run(reserve())
    assert replayed is False
    abandoned = index.claim_next()
    assert abandoned is not None and abandoned.run_id == pending.run_id
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "UPDATE api_turns SET claimed_at=NOW() - INTERVAL '6 minutes' WHERE run_id=%s",
            (pending.run_id,),
        )

    restarted_index = PostgresTurnIndex(dsn)
    restarted_service = TurnService(
        ShoppingAgent(
            planner,
            ToolRegistry({name: search for name in FROZEN_TOOL_TYPES}),
            PostgresCheckpointStore(dsn),
            IDENTITY,
        ),
        InMemoryMediaStore(),
        restarted_index,
    )
    assert asyncio.run(TurnWorker(restarted_index, restarted_service).run_once()) is True
    assert asyncio.run(TurnWorker(restarted_index, restarted_service).run_once()) is False
    loaded = restarted_service.require_run(owner_id, pending.run_id)
    terminal = [
        event.type.value for event in loaded.events if event.type.value in {"completed", "failed"}
    ]
    assert terminal == ["completed"]


def test_postgres_agent_approved_writes_are_durable_idempotent_and_user_scoped() -> None:
    dsn = database_url()
    commerce = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn)
    owner_id, other_id = uuid4(), uuid4()
    shopping_list = commerce.create_list(owner_id, CreateListRequest(name="Agent durable list"))
    row = next(iter(commerce.rows.values()))
    planner = ScriptedPlanner(
        (
            ToolCall(
                "list.update",
                {
                    "operation": "add",
                    "list_id": str(shopping_list.list_id),
                    "variant_id": row["variant_id"],
                },
            ),
            ToolCall(
                "cart.update",
                {
                    "operation": "set",
                    "offer_id": row["offer"]["offer_id"],
                    "quantity": 2,
                },
            ),
        )
    )
    service = TurnService(
        ShoppingAgent(
            planner,
            ToolRegistry(commerce.tool_handlers()),
            PostgresCheckpointStore(dsn),
            IDENTITY,
        ),
        InMemoryMediaStore(),
        PostgresTurnIndex(dsn),
    )
    thread = service.create_thread(owner_id, "durable Agent write")

    async def run():
        record, replayed = await service.submit(
            owner_id, thread.id, "durable-agent-write-1", "保存并加入待购", ()
        )
        assert replayed is False
        await service.execute(record.run_id)
        await service.decide(owner_id, record.run_id, "list.update", True)
        await service.execute(record.run_id)
        await service.decide(owner_id, record.run_id, "cart.update", True)
        completed = await service.execute(record.run_id)
        replay = await service.decide(owner_id, record.run_id, "cart.update", True)
        return completed, replay

    completed, replay = asyncio.run(run())

    saved = commerce.get_lists(owner_id).lists[0]
    cart = commerce.get_cart(owner_id)
    assert saved.variant_ids == [UUID(row["variant_id"])]
    assert [(item.offer_id, item.quantity) for item in cart.items] == [
        (UUID(row["offer"]["offer_id"]), 2)
    ]
    assert commerce.get_lists(other_id).lists == []
    assert commerce.get_cart(other_id).items == []
    assert replay.events == completed.events

    watcher = commerce.create_watcher(
        owner_id,
        thread.id,
        CreateWatcherRequest(
            kind="PRICE_BELOW",
            offer_id=UUID(row["offer"]["offer_id"]),
            threshold_minor=35000,
        ),
    )
    recreated_commerce = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn)
    restored_watchers = recreated_commerce.get_watchers(owner_id, thread.id).watchers
    assert [value.watcher_id for value in restored_watchers] == [watcher.watcher_id]
    assert restored_watchers[0].scheduler_active is False
    assert recreated_commerce.get_watchers(other_id, thread.id).watchers == []
