"""Project-authored catalog with PostgreSQL-backed user list and cart state."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from ragcommerce_agent_runtime import ToolResult
from ragcommerce_agent_runtime.postgres_connection import connect
from ragcommerce_contracts import (
    CartMutation,
    CartView,
    CreateListRequest,
    CreateWatcherRequest,
    OfferCollection,
    OfferView,
    PatchListRequest,
    ShoppingListsResponse,
    ShoppingListView,
    WatcherCollection,
    WatcherView,
)

from .demo import DemoCommerce


class PostgresDemoCommerce(DemoCommerce):
    def __init__(self, catalog_path: Path, dsn: str, *, real_hybrid=None) -> None:
        super().__init__(catalog_path, real_hybrid=real_hybrid)
        self.dsn = dsn
        self._tool_connection = ContextVar("commerce_tool_connection", default=None)

    @contextmanager
    def _connection(self):
        current = self._tool_connection.get()
        if current is not None:
            yield current
        else:
            with connect(self.dsn) as connection:
                yield connection

    def get_offers(self, user_id: UUID, product_id: UUID, fresh: bool) -> OfferCollection:
        with self._connection() as connection:
            if not fresh:
                saved = connection.execute(
                    "SELECT quote FROM v3_demo_quotes WHERE owner_id=%s AND product_id=%s",
                    (user_id, product_id),
                ).fetchone()
                if saved is not None:
                    return OfferCollection(
                        product_id=product_id, offers=[OfferView.model_validate(saved[0])]
                    )
            quote = self._offer_view(self.rows[product_id])
            conflict = "DO UPDATE SET quote=EXCLUDED.quote" if fresh else "DO NOTHING"
            saved = connection.execute(
                "INSERT INTO v3_demo_quotes(owner_id,product_id,quote) VALUES (%s,%s,%s) "
                "ON CONFLICT(owner_id,product_id) " + conflict + " RETURNING quote",
                (user_id, product_id, Jsonb(quote.model_dump(mode="json"))),
            ).fetchone()
            if saved is None:
                saved = connection.execute(
                    "SELECT quote FROM v3_demo_quotes WHERE owner_id=%s AND product_id=%s",
                    (user_id, product_id),
                ).fetchone()
            return OfferCollection(
                product_id=product_id, offers=[OfferView.model_validate(saved[0])]
            )

    def tool_handlers(self):
        handlers = super().tool_handlers()

        def durable(name, handler):
            def execute(context, args):
                arguments = args.model_dump(mode="json")
                with connect(self.dsn) as connection:
                    connection.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (f"tool:{context.user_id}:{context.invocation_id}",),
                    )
                    receipt = connection.execute(
                        """SELECT tool_name,arguments,result FROM v3_tool_receipts
                        WHERE owner_id=%s AND invocation_id=%s""",
                        (context.user_id, context.invocation_id),
                    ).fetchone()
                    if receipt is not None:
                        if receipt[0] != name or receipt[1] != arguments:
                            raise ValueError(
                                "tool invocation is already bound to different arguments"
                            )
                        return ToolResult(receipt[2])
                    token = self._tool_connection.set(connection)
                    try:
                        result = handler(context, args)
                    finally:
                        self._tool_connection.reset(token)
                    connection.execute(
                        """INSERT INTO v3_tool_receipts
                        (owner_id,invocation_id,tool_name,arguments,result)
                        VALUES (%s,%s,%s,%s,%s)""",
                        (
                            context.user_id,
                            context.invocation_id,
                            name,
                            Jsonb(arguments),
                            Jsonb(dict(result.public_data)),
                        ),
                    )
                    return result

            return execute

        for name in ("cart.update", "list.update"):
            handlers[name] = durable(name, handlers[name])
        return handlers

    def get_lists(self, user_id: UUID) -> ShoppingListsResponse:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT value.list_id,value.name,item.variant_id FROM v3_lists value
                LEFT JOIN v3_list_items item ON item.list_id=value.list_id
                WHERE value.owner_id=%s ORDER BY value.created_at,item.created_at""",
                (user_id,),
            ).fetchall()
        values: dict[UUID, ShoppingListView] = {}
        for list_id, name, variant_id in rows:
            current = values.setdefault(
                list_id, ShoppingListView(list_id=list_id, name=name, variant_ids=[])
            )
            if variant_id is not None:
                current.variant_ids.append(variant_id)
        return ShoppingListsResponse(lists=list(values.values()))

    def create_list(self, user_id: UUID, request: CreateListRequest) -> ShoppingListView:
        value = ShoppingListView(list_id=uuid4(), name=request.name, variant_ids=[])
        with connect(self.dsn) as connection:
            connection.execute(
                "INSERT INTO v3_lists(list_id,owner_id,name,created_at) VALUES (%s,%s,%s,%s)",
                (value.list_id, user_id, value.name, datetime.now(UTC)),
            )
        return value

    def patch_list(
        self, user_id: UUID, list_id: UUID, request: PatchListRequest
    ) -> ShoppingListView:
        with self._connection() as connection:
            owned = connection.execute(
                "SELECT name FROM v3_lists WHERE list_id=%s AND owner_id=%s", (list_id, user_id)
            ).fetchone()
            if owned is None:
                raise KeyError(list_id)
            self.require_catalog_variant(request.add_variant_id)
            if request.name is not None:
                connection.execute(
                    "UPDATE v3_lists SET name=%s WHERE list_id=%s", (request.name, list_id)
                )
            if request.add_variant_id is not None:
                connection.execute(
                    """INSERT INTO v3_list_items(list_id,variant_id,created_at) VALUES (%s,%s,%s)
                    ON CONFLICT DO NOTHING""",
                    (list_id, request.add_variant_id, datetime.now(UTC)),
                )
            if request.remove_variant_id is not None:
                connection.execute(
                    "DELETE FROM v3_list_items WHERE list_id=%s AND variant_id=%s",
                    (list_id, request.remove_variant_id),
                )
        return next(value for value in self.get_lists(user_id).lists if value.list_id == list_id)

    def get_cart(self, user_id: UUID) -> CartView:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT offer_id,quantity FROM v3_cart_items WHERE owner_id=%s ORDER BY offer_id",
                (user_id,),
            ).fetchall()
            return CartView(items=[self._cart_item(user_id, row[0], row[1]) for row in rows])

    def mutate_cart(self, user_id: UUID, request: CartMutation) -> CartView:
        if request.operation != "remove" and request.offer_id not in self.offers:
            raise KeyError(request.offer_id)
        with self._connection() as connection:
            if request.operation == "remove":
                connection.execute(
                    "DELETE FROM v3_cart_items WHERE owner_id=%s AND offer_id=%s",
                    (user_id, request.offer_id),
                )
            else:
                connection.execute(
                    """INSERT INTO v3_cart_items(owner_id,offer_id,quantity,updated_at)
                    VALUES (%s,%s,%s,%s) ON CONFLICT(owner_id,offer_id) DO UPDATE SET
                    quantity=EXCLUDED.quantity,updated_at=EXCLUDED.updated_at""",
                    (user_id, request.offer_id, request.quantity, datetime.now(UTC)),
                )
        return self.get_cart(user_id)

    def get_watchers(self, user_id: UUID, thread_id: UUID) -> WatcherCollection:
        with connect(self.dsn) as connection:
            rows = connection.execute(
                """SELECT watcher_id,offer_id,kind,threshold_minor,created_at
                FROM v3_watchers WHERE owner_id=%s AND thread_id=%s ORDER BY created_at""",
                (user_id, thread_id),
            ).fetchall()
        return WatcherCollection(
            watchers=[
                WatcherView(
                    watcher_id=row[0],
                    thread_id=thread_id,
                    offer_id=row[1],
                    kind=row[2],
                    threshold_minor=row[3],
                    disclosure="演示观察草稿; 当前没有调度器或通知渠道, 不会后台提醒。",
                    created_at=row[4],
                )
                for row in rows
            ]
        )

    def create_watcher(
        self, user_id: UUID, thread_id: UUID, request: CreateWatcherRequest
    ) -> WatcherView:
        if request.offer_id not in self.offers:
            raise KeyError(request.offer_id)
        if request.kind == "PRICE_BELOW" and request.threshold_minor is None:
            raise ValueError("PRICE_BELOW requires threshold_minor")
        watcher_id = uuid4()
        created_at = datetime.now(UTC)
        with connect(self.dsn) as connection:
            row = connection.execute(
                """INSERT INTO v3_watchers(
                    watcher_id,owner_id,thread_id,offer_id,kind,threshold_minor,created_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(owner_id,thread_id,offer_id,kind) DO UPDATE SET
                    threshold_minor=EXCLUDED.threshold_minor
                RETURNING watcher_id,created_at""",
                (
                    watcher_id,
                    user_id,
                    thread_id,
                    request.offer_id,
                    request.kind,
                    request.threshold_minor,
                    created_at,
                ),
            ).fetchone()
        return WatcherView(
            watcher_id=row[0],
            thread_id=thread_id,
            offer_id=request.offer_id,
            kind=request.kind,
            threshold_minor=request.threshold_minor,
            disclosure="演示观察草稿; 当前没有调度器或通知渠道, 不会后台提醒。",
            created_at=row[1],
        )


__all__ = ["PostgresDemoCommerce"]
