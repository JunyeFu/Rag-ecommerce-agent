"""Deterministic, project-authored local composition for the V3 golden flow."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

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
from ragcommerce_contracts import (
    CartItemView,
    CartMutation,
    CartView,
    CreateListRequest,
    OfferCollection,
    OfferView,
    PatchListRequest,
    ProductView,
    ResolvedOffer,
    ResolveOfferRequest,
    ShoppingListsResponse,
    ShoppingListView,
)
from ragcommerce_retrieval import (
    DeterministicEmbeddingProvider,
    HybridSemanticIndex,
    load_demo_documents,
)

from .app import create_app
from .media import InMemoryMediaStore
from .ops import InMemoryOpsStore
from .service import TurnService


class DemoProvider:
    """Iterative fake provider that exercises the same typed tool loop as a real model."""

    async def plan(self, command: TurnCommand, prior_results: tuple[ToolResult, ...], replan: int):
        if not prior_results:
            if "演示" not in command.text and not any(
                character.isdigit() for character in command.text
            ):
                return ()
            return (ToolCall("catalog.search", {"query": command.text}),)
        keys = {key for result in prior_results for key in result.public_data}
        products = next(
            (
                result.public_data["products"]
                for result in prior_results
                if "products" in result.public_data
            ),
            [],
        )
        ids = [str(item["product_id"]) for item in products[:3]]
        if "product_facts" not in keys:
            return (ToolCall("catalog.get_product_facts", {"ids": ids}),)
        if "offers" not in keys:
            return (ToolCall("offer.find", {"ids": ids}),)
        if "comparison" not in keys:
            return (ToolCall("comparison.build", {"ids": ids}),)
        return ()

    async def respond(self, command: TurnCommand, results: tuple[ToolResult, ...]) -> str:
        if not results:
            return "请补充预算上限, 方便我在同一 Mission 中继续检索。"
        return "已按硬约束完成检索、报价核验和比较; 演示报价均标记为 DEMO_FIXTURE。"

    def usage(self):
        return {
            "provider": "deterministic_demo",
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }


class DemoCommerce:
    def __init__(self, catalog_path: Path) -> None:
        rows = [json.loads(line) for line in catalog_path.read_text(encoding="utf-8").splitlines()]
        self.rows = {UUID(row["product_id"]): row for row in rows}
        self.offers = {UUID(row["offer"]["offer_id"]): row for row in rows}
        self.embedding = DeterministicEmbeddingProvider()
        documents = load_demo_documents(catalog_path)
        self.hybrid = HybridSemanticIndex(
            documents,
            {item.seed_id: self.embedding.vector(item.searchable_text) for item in documents},
            self.embedding,
        )
        self.lists: dict[UUID, dict[UUID, ShoppingListView]] = {}
        self.carts: dict[UUID, CartView] = {}
        self.default_list_ids: dict[UUID, UUID] = {}

    def get_product(self, user_id: UUID, product_id: UUID) -> ProductView:
        row = self.rows[product_id]
        return ProductView(
            product_id=product_id,
            variant_id=UUID(row["variant_id"]),
            title=row["title"],
            category=row["category"],
            brand=row["brand"],
            attributes=row["attributes"],
            image_ref=row["image_ref"],
            evidence_refs=row["evidence_refs"],
        )

    def get_offers(self, user_id: UUID, product_id: UUID, fresh: bool) -> OfferCollection:
        row = self.rows[product_id]
        return OfferCollection(product_id=product_id, offers=[self._offer_view(row)])

    def resolve_offer(
        self, user_id: UUID, offer_id: UUID, request: ResolveOfferRequest
    ) -> ResolvedOffer:
        row = self.offers[offer_id]
        return ResolvedOffer(
            offer_id=offer_id,
            link_url=row["offer"]["link_url"],
            disclosure="项目自有演示报价; 外跳仅用于验证安全边界, 不代表联盟授权。",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
            quote_changed=False,
            requires_confirmation=False,
        )

    def get_lists(self, user_id: UUID) -> ShoppingListsResponse:
        return ShoppingListsResponse(lists=list(self.lists.get(user_id, {}).values()))

    def create_list(self, user_id: UUID, request: CreateListRequest) -> ShoppingListView:
        value = ShoppingListView(list_id=uuid4(), name=request.name, variant_ids=[])
        self.lists.setdefault(user_id, {})[value.list_id] = value
        self.default_list_ids.setdefault(user_id, value.list_id)
        return value

    def patch_list(
        self, user_id: UUID, list_id: UUID, request: PatchListRequest
    ) -> ShoppingListView:
        current = self.lists[user_id][list_id]
        values = list(current.variant_ids)
        if request.add_variant_id is not None and request.add_variant_id not in values:
            values.append(request.add_variant_id)
        if request.remove_variant_id is not None:
            values = [value for value in values if value != request.remove_variant_id]
        updated = ShoppingListView(
            list_id=list_id,
            name=request.name or current.name,
            variant_ids=values,
        )
        self.lists[user_id][list_id] = updated
        return updated

    def get_cart(self, user_id: UUID) -> CartView:
        return self.carts.get(user_id, CartView(items=[]))

    def mutate_cart(self, user_id: UUID, request: CartMutation) -> CartView:
        items = {item.offer_id: item.quantity for item in self.get_cart(user_id).items}
        if request.operation == "remove":
            items.pop(request.offer_id, None)
        else:
            items[request.offer_id] = request.quantity
        value = CartView(
            items=[
                CartItemView(offer_id=offer_id, quantity=quantity)
                for offer_id, quantity in sorted(items.items(), key=lambda item: str(item[0]))
            ]
        )
        self.carts[user_id] = value
        return value

    def tool_handlers(self):
        def execute(name: str, context: ToolExecutionContext, args: BaseModel) -> ToolResult:
            values = args.model_dump()
            if name == "catalog.search":
                return self._search(str(values["query"]))
            if name == "catalog.get_product_facts":
                rows = [self.rows[UUID(value)] for value in values["ids"]]
                return self._result(
                    "product_facts", [self._product_payload(row) for row in rows], rows
                )
            if name in {"offer.find", "offer.requote"}:
                rows = (
                    [self.rows[UUID(value)] for value in values["ids"]]
                    if "ids" in values
                    else [self.offers[UUID(values["offer_id"])]]
                )
                return self._result("offers", [self._offer_payload(row) for row in rows], rows)
            if name == "comparison.build":
                rows = [self.rows[UUID(value)] for value in values["ids"]]
                comparison = {
                    "items": [str(row["product_id"]) for row in rows],
                    "dimensions": sorted({key for row in rows for key in row["attributes"]}),
                    "missing_fields": [],
                    "evidence_refs": [ref for row in rows for ref in row["evidence_refs"]],
                }
                return self._result("comparison", comparison, rows)
            if name == "list.update":
                return ToolResult({"list_updated": True, "item_id": values["item_id"]})
            if name == "cart.update":
                return ToolResult({"cart_updated": True, "item_id": values["item_id"]})
            if name == "link.resolve":
                row = self.offers[UUID(values["offer_id"])]
                return self._result("link", row["offer"]["link_url"], [row])
            if name == "vision.identify":
                return ToolResult({"identified_query": "图片中的 3C 商品"})
            return ToolResult({"merchant_policy": "演示商家不托管支付、订单、退款或履约"})

        def bind(name: str):
            def handler(context: ToolExecutionContext, args: BaseModel) -> ToolResult:
                return execute(name, context, args)

            return handler

        return {name: bind(name) for name in FROZEN_TOOL_TYPES}

    def _search(self, query: str) -> ToolResult:
        categories = [
            category for category in ("手机", "电脑", "耳机", "相机") if category in query
        ]
        budget = self._budget_minor(query)
        constraints: dict[str, object] = {}
        if len(categories) == 1:
            constraints["category"] = categories[0]
        if budget is not None:
            constraints["price_max"] = budget
        hits = self.hybrid.search_with_vector(
            query,
            self.embedding.vector(query),
            5,
            constraints,
        )
        rows = [self.rows[UUID(hit.document.seed_id)] for hit in hits]
        return self._result("products", [self._candidate_payload(row) for row in rows], rows)

    @staticmethod
    def _budget_minor(query: str) -> int | None:
        import re

        match = re.search(r"(\d{2,6})\s*元", query)
        return int(match.group(1)) * 100 if match else None

    @staticmethod
    def _candidate_payload(row):
        return {
            "product_id": row["product_id"],
            "variant_id": row["variant_id"],
            "title": row["title"],
            "fit_summary": "符合演示目录中的品类、预算和场景约束",
            "matched_constraints": row["fit_tags"],
            "unmet_constraints": [],
            "risks": ["演示商品与报价, 不代表真实市场供应"],
            "evidence_refs": row["evidence_refs"],
        }

    @staticmethod
    def _product_payload(row):
        return {
            "product_id": row["product_id"],
            "variant_id": row["variant_id"],
            "title": row["title"],
            "brand": row["brand"],
            "category": row["category"],
            "attributes": row["attributes"],
            "evidence_refs": row["evidence_refs"],
        }

    def _offer_payload(self, row):
        payload = self._offer_view(row).model_dump(mode="json")
        payload["product_id"] = row["product_id"]
        payload["variant_id"] = row["variant_id"]
        return payload

    @staticmethod
    def _evidence(row):
        payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return ToolEvidence(
            row["evidence_refs"][0],
            hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            ("title", "brand", "category", "attributes"),
        )

    def _result(self, key, value, rows):
        return ToolResult(
            {key: value},
            tuple(self._evidence(row) for row in rows),
            frozenset({"title", "brand", "category", "attributes"}),
        )

    @staticmethod
    def _offer_view(row):
        now = datetime.now(UTC)
        offer = row["offer"]
        return OfferView(
            offer_id=UUID(offer["offer_id"]),
            merchant_name=offer["merchant_name"],
            verification="DEMO_FIXTURE",
            availability=offer["availability"],
            price_minor=offer["price_minor"],
            shipping_minor=offer["shipping_minor"],
            currency=offer["currency"],
            collected_at=now,
            expires_at=now + timedelta(minutes=15),
            source_ref=offer["source_ref"],
        )


def create_demo_app(catalog_path: Path):
    commerce = DemoCommerce(catalog_path)
    media = InMemoryMediaStore()
    agent = ShoppingAgent(
        DemoProvider(),
        ToolRegistry(commerce.tool_handlers()),
        InMemoryCheckpointStore(),
        RuntimeIdentity(
            "shopping-agent-v3-demo",
            "deterministic-demo",
            "agent-first-v3",
            "commercial-truth-v3",
            "0.2.0",
        ),
    )
    return create_app(
        TurnService(agent, media), media, commerce=commerce, ops_store=InMemoryOpsStore()
    )
