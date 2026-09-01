"""Project-authored catalog with PostgreSQL-backed user list and cart state."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from ragcommerce_contracts import (
    CartItemView,
    CartMutation,
    CartView,
    CreateListRequest,
    PatchListRequest,
    ShoppingListsResponse,
    ShoppingListView,
)

from .demo import DemoCommerce


class PostgresDemoCommerce(DemoCommerce):
    def __init__(self, catalog_path: Path, dsn: str) -> None:
        super().__init__(catalog_path)
        self.dsn = dsn

    def get_lists(self, user_id: UUID) -> ShoppingListsResponse:
        with psycopg.connect(self.dsn) as connection:
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
        with psycopg.connect(self.dsn) as connection:
            connection.execute(
                "INSERT INTO v3_lists(list_id,owner_id,name,created_at) VALUES (%s,%s,%s,%s)",
                (value.list_id, user_id, value.name, datetime.now(UTC)),
            )
        return value

    def patch_list(
        self, user_id: UUID, list_id: UUID, request: PatchListRequest
    ) -> ShoppingListView:
        with psycopg.connect(self.dsn) as connection:
            owned = connection.execute(
                "SELECT name FROM v3_lists WHERE list_id=%s AND owner_id=%s", (list_id, user_id)
            ).fetchone()
            if owned is None:
                raise KeyError(list_id)
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
        with psycopg.connect(self.dsn) as connection:
            rows = connection.execute(
                "SELECT offer_id,quantity FROM v3_cart_items WHERE owner_id=%s ORDER BY offer_id",
                (user_id,),
            ).fetchall()
        return CartView(items=[CartItemView(offer_id=row[0], quantity=row[1]) for row in rows])

    def mutate_cart(self, user_id: UUID, request: CartMutation) -> CartView:
        with psycopg.connect(self.dsn) as connection:
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


__all__ = ["PostgresDemoCommerce"]
