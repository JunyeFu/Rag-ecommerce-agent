"""Deterministic, project-authored local composition for the V3 golden flow."""

from __future__ import annotations

import hashlib
import json
import re
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
    parse_shopping_mission,
)
from ragcommerce_contracts import (
    BusinessFactView,
    CartItemView,
    CartMutation,
    CartView,
    CreateListRequest,
    CreateWatcherRequest,
    OfferCollection,
    OfferView,
    PatchListRequest,
    ProductView,
    ResolvedOffer,
    ResolveOfferRequest,
    ShoppingListsResponse,
    ShoppingListView,
    WatcherCollection,
    WatcherView,
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

    async def interpret_media(self, context, kind, content_type, content):
        return {
            "recognized_text": "通勤使用的耳机,预算800元",
            "category": "耳机",
            "visible_attributes": ["耳机"],
            "uncertainties": ["显式fake媒体测试结果"],
            "supported": True,
        }


class DemoCommerce:
    def exploration_directions(self):
        from .exploration import catalog_directions

        return catalog_directions(self.rows.values())

    def __init__(self, catalog_path: Path, *, real_hybrid=None) -> None:
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
        self.real_hybrid = real_hybrid
        self.lists: dict[UUID, dict[UUID, ShoppingListView]] = {}
        self.carts: dict[UUID, CartView] = {}
        self.quotes: dict[tuple[UUID, UUID], OfferView] = {}
        self.default_list_ids: dict[UUID, UUID] = {}
        self.watchers: dict[tuple[UUID, UUID, str, UUID], WatcherView] = {}

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

    def get_variant(self, user_id: UUID, variant_id: UUID) -> ProductView:
        product_id = next(
            (key for key, row in self.rows.items() if row["variant_id"] == str(variant_id)), None
        )
        if product_id is None:
            raise KeyError(variant_id)
        return self.get_product(user_id, product_id)

    def get_offers(self, user_id: UUID, product_id: UUID, fresh: bool) -> OfferCollection:
        key = (user_id, product_id)
        if fresh or key not in self.quotes:
            self.quotes[key] = self._offer_view(self.rows[product_id])
        return OfferCollection(product_id=product_id, offers=[self.quotes[key]])

    def resolve_offer(
        self, user_id: UUID, offer_id: UUID, request: ResolveOfferRequest
    ) -> ResolvedOffer:
        row = self.offers[offer_id]
        quote = self.get_offers(user_id, UUID(row["product_id"]), False).offers[0]
        expired = quote.expires_at <= datetime.now(UTC)
        return ResolvedOffer(
            offer_id=offer_id,
            link_url=None if expired else row["offer"]["link_url"],
            disclosure="报价已过期, 请重新询价"
            if expired
            else "项目自有演示报价; 外跳仅用于验证安全边界, 不代表联盟授权。",
            expires_at=quote.expires_at,
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
        self.require_catalog_variant(request.add_variant_id)
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
        return CartView(
            items=[
                self._cart_item(user_id, item.offer_id, item.quantity)
                for item in self.carts.get(user_id, CartView(items=[])).items
            ]
        )

    def _cart_item(self, user_id: UUID, offer_id: UUID, quantity: int) -> CartItemView:
        product_id = UUID(self.offers[offer_id]["product_id"])
        return CartItemView(
            offer_id=offer_id,
            quantity=quantity,
            product=self.get_product(user_id, product_id),
            quote=self.get_offers(user_id, product_id, False).offers[0],
        )

    def mutate_cart(self, user_id: UUID, request: CartMutation) -> CartView:
        if request.operation != "remove" and request.offer_id not in self.offers:
            raise KeyError(request.offer_id)
        items = {item.offer_id: item.quantity for item in self.get_cart(user_id).items}
        if request.operation == "remove":
            items.pop(request.offer_id, None)
        else:
            items[request.offer_id] = request.quantity
        value = CartView(
            items=[
                self._cart_item(user_id, offer_id, quantity)
                for offer_id, quantity in sorted(items.items(), key=lambda item: str(item[0]))
            ]
        )
        self.carts[user_id] = value
        return value

    def get_watchers(self, user_id: UUID, thread_id: UUID) -> WatcherCollection:
        return WatcherCollection(
            watchers=[
                value
                for (owner_id, owner_thread_id, _, _), value in self.watchers.items()
                if owner_id == user_id and owner_thread_id == thread_id
            ]
        )

    def create_watcher(
        self, user_id: UUID, thread_id: UUID, request: CreateWatcherRequest
    ) -> WatcherView:
        if request.offer_id not in self.offers:
            raise KeyError(request.offer_id)
        if request.kind == "PRICE_BELOW" and request.threshold_minor is None:
            raise ValueError("PRICE_BELOW requires threshold_minor")
        key = (user_id, thread_id, request.kind, request.offer_id)
        existing = self.watchers.get(key)
        if existing is not None:
            updated = existing.model_copy(update={"threshold_minor": request.threshold_minor})
            self.watchers[key] = updated
            return updated
        value = WatcherView(
            watcher_id=uuid4(),
            thread_id=thread_id,
            offer_id=request.offer_id,
            kind=request.kind,
            threshold_minor=request.threshold_minor,
            disclosure="演示观察草稿; 当前没有调度器或通知渠道, 不会后台提醒。",
            created_at=datetime.now(UTC),
        )
        self.watchers[key] = value
        return value

    def require_catalog_variant(self, variant_id: UUID | None) -> None:
        if variant_id is not None and not any(
            row["variant_id"] == str(variant_id) for row in self.rows.values()
        ):
            raise KeyError(variant_id)

    def tool_handlers(self):
        def execute(name: str, context: ToolExecutionContext, args: BaseModel) -> ToolResult:
            values = args.model_dump()
            if name == "catalog.search":
                return self._search_tool(
                    str(values["query"]), context.excluded_product_ids, context.excluded_categories
                )
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
                return self._result(
                    "offers",
                    [self._offer_payload(row, context.user_id, fresh=True) for row in rows],
                    rows,
                )
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
                request = PatchListRequest(
                    **{
                        (
                            "add_variant_id"
                            if values["operation"] == "add"
                            else "remove_variant_id"
                        ): values["variant_id"]
                    }
                )
                updated = self.patch_list(context.user_id, values["list_id"], request)
                return ToolResult({"shopping_list": updated.model_dump(mode="json")})
            if name == "cart.update":
                updated = self.mutate_cart(
                    context.user_id,
                    CartMutation(
                        operation=values["operation"],
                        offer_id=values["offer_id"],
                        quantity=values["quantity"],
                    ),
                )
                return ToolResult({"cart": updated.model_dump(mode="json")})
            if name == "link.resolve":
                row = self.offers[UUID(values["offer_id"])]
                resolved = self.resolve_offer(
                    context.user_id, UUID(values["offer_id"]), ResolveOfferRequest()
                )
                if resolved.link_url is None:
                    return ToolResult({"link": None, "disclosure": resolved.disclosure})
                return self._result("link", resolved.link_url, [row])
            if name in {"vision.identify", "audio.transcribe"}:
                raise RuntimeError("media tools require the shared owner-bound media adapter")
            return ToolResult({"merchant_policy": "演示商家不托管支付、订单、退款或履约"})

        def bind(name: str):
            def handler(context: ToolExecutionContext, args: BaseModel) -> ToolResult:
                return execute(name, context, args)

            return handler

        return {name: bind(name) for name in FROZEN_TOOL_TYPES}

    async def _search_tool(
        self, query: str, excluded_products=(), excluded_categories=()
    ) -> ToolResult:
        if self.real_hybrid is None:
            return self._search(query, excluded_products, excluded_categories)
        categories = [
            category for category in ("手机", "电脑", "耳机", "相机") if category in query
        ]
        constraints: dict[str, object] = {}
        if len(categories) == 1:
            constraints["category"] = categories[0]
        hits = await self.real_hybrid.search(query, 15, constraints)
        rows = [self.rows[UUID(hit.document.seed_id)] for hit in hits]
        return self._strategy_result(
            query,
            [
                row
                for row in rows
                if row["product_id"] not in excluded_products
                and row["category"] not in excluded_categories
            ],
        )

    def _search(self, query: str, excluded_products=(), excluded_categories=()) -> ToolResult:
        categories = [
            category for category in ("手机", "电脑", "耳机", "相机") if category in query
        ]
        constraints: dict[str, object] = {}
        if len(categories) == 1:
            constraints["category"] = categories[0]
        hits = self.hybrid.search_with_vector(
            query,
            self.embedding.vector(query),
            15,
            constraints,
        )
        rows = [self.rows[UUID(hit.document.seed_id)] for hit in hits]
        return self._strategy_result(
            query,
            [
                row
                for row in rows
                if row["product_id"] not in excluded_products
                and row["category"] not in excluded_categories
            ],
        )

    @staticmethod
    def _budget_minor(query: str) -> int | None:
        import re

        match = re.search(r"(\d{2,6})\s*元", query)
        return int(match.group(1)) * 100 if match else None

    def _strategy_result(self, query: str, rows: list[dict]) -> ToolResult:
        mission = parse_shopping_mission(query)
        hard_constraints = [
            value
            for value in mission["hard_constraints"]
            if not re.search(r"(?:预算|不超过|以内).*\d+\s*元", value)
        ]
        soft_preferences = list(mission["soft_preferences"])
        budget = mission["budget_total_minor"] or self._budget_minor(query)
        evaluated = [
            (
                row,
                [value for value in hard_constraints if not self._matches_constraint(row, value)],
                [value for value in soft_preferences if not self._matches_constraint(row, value)],
            )
            for row in rows
        ]
        strict = [item for item in evaluated if not item[1]]
        within_budget = [
            item
            for item in strict
            if budget is not None and item[0]["offer"]["price_minor"] <= budget
        ]
        alternatives = [item for item in evaluated if item[1]]

        strict_pick = strict[0] if strict else None
        budget_pick = within_budget[0] if within_budget else None
        alternative_pick = alternatives[0] if alternatives else None
        routes = [
            self._route(
                "STRICT",
                strict_pick,
                self._strict_summary(strict_pick, budget),
                [],
            ),
            self._route(
                "BUDGET",
                budget_pick,
                (
                    "满足硬约束和预算上限"
                    + (
                        f"; 放宽软偏好: {'、'.join(budget_pick[2])}"
                        if budget_pick and budget_pick[2]
                        else ""
                    )
                    if budget_pick is not None
                    else (
                        "未提供预算上限, 无法形成预算方案"
                        if budget is None
                        else "演示目录中没有同时满足硬约束和预算上限的商品"
                    )
                ),
                budget_pick[2] if budget_pick else [],
            ),
            self._route(
                "ALTERNATIVE",
                alternative_pick,
                (
                    f"替代商品; 明确放宽硬约束: {'、'.join(alternative_pick[1])}"
                    if alternative_pick
                    else "没有需要放宽的硬约束"
                ),
                alternative_pick[1] if alternative_pick else [],
            ),
        ]

        primary: list[tuple[dict, list[str], list[str], str]] = []
        for item, route_type in (
            (strict_pick, "STRICT"),
            (budget_pick, "BUDGET"),
            (alternative_pick, "ALTERNATIVE"),
        ):
            if item is not None and all(
                existing[0]["product_id"] != item[0]["product_id"] for existing in primary
            ):
                primary.append((*item, route_type))
        for item in evaluated:
            if len(primary) >= 5:
                break
            if all(existing[0]["product_id"] != item[0]["product_id"] for existing in primary):
                primary.append((*item, "ALTERNATIVE" if item[1] else "STRICT"))

        products = [
            self._candidate_payload(
                row,
                route_type=route_type,
                hard_constraints=hard_constraints,
                soft_preferences=soft_preferences,
                unmet_hard=unmet_hard,
                unmet_soft=unmet_soft,
                budget=budget,
            )
            for row, unmet_hard, unmet_soft, route_type in primary
        ]
        selected_rows = [item[0] for item in primary]
        result = self._result("products", products, selected_rows)
        return ToolResult(
            {"products": products, "recommendation_routes": routes},
            result.evidence,
            result.commercial_fact_fields,
        )

    @staticmethod
    def _route(route_type: str, item, summary: str, relaxed: list[str]) -> dict:
        return {
            "route_type": route_type,
            "status": "AVAILABLE" if item is not None else "UNAVAILABLE",
            "summary": summary,
            "relaxed_constraints": relaxed,
            "product_ids": [item[0]["product_id"]] if item is not None else [],
        }

    @staticmethod
    def _strict_summary(item, budget: int | None) -> str:
        if item is None:
            return "演示目录中没有满足全部硬约束的商品"
        price = item[0]["offer"]["price_minor"]
        if budget is not None and price > budget:
            return f"满足硬约束; 超出预算 ¥{(price - budget) / 100:.2f}"
        return "满足全部可验证硬约束"

    @staticmethod
    def _matches_constraint(row: dict, constraint: str) -> bool:
        if "续航" in constraint:
            value = row["attributes"].get("续航", "")
            actual = re.search(r"(\d+(?:\.\d+)?)\s*小时", value)
            minimum = re.search(r"(?:至少|不低于)[^\d]*(\d+(?:\.\d+)?)\s*小时", constraint)
            maximum = re.search(r"(?:至多|不超过)[^\d]*(\d+(?:\.\d+)?)\s*小时", constraint)
            if actual and minimum:
                return float(actual.group(1)) >= float(minimum.group(1))
            if actual and maximum:
                return float(actual.group(1)) <= float(maximum.group(1))
        searchable = " ".join(
            [
                row["category"],
                row["title"],
                *row["fit_tags"],
                *row["attributes"].keys(),
                *row["attributes"].values(),
            ]
        )
        if "不要" in constraint:
            forbidden = constraint.split("不要", 1)[1].strip()
            return bool(forbidden) and forbidden not in searchable
        terms = [
            *row["fit_tags"],
            *row["attributes"].keys(),
            *row["attributes"].values(),
        ]
        return any(len(term) >= 2 and term in constraint for term in terms)

    @staticmethod
    def _candidate_payload(
        row,
        *,
        route_type: str,
        hard_constraints: list[str],
        soft_preferences: list[str],
        unmet_hard: list[str],
        unmet_soft: list[str],
        budget: int | None,
    ):
        over_budget = budget is not None and row["offer"]["price_minor"] > budget
        matched = [value for value in hard_constraints if value not in unmet_hard]
        matched += [value for value in soft_preferences if value not in unmet_soft]
        unmet = list(unmet_hard)
        if over_budget:
            unmet.append("预算上限")
        relaxed = (
            unmet_hard
            if route_type == "ALTERNATIVE"
            else unmet_soft
            if route_type == "BUDGET"
            else []
        )
        return {
            "product_id": row["product_id"],
            "variant_id": row["variant_id"],
            "title": row["title"],
            "fit_summary": {
                "STRICT": "严格方案: 优先保持硬约束",
                "BUDGET": "预算方案: 预算内并显式列出放宽偏好",
                "ALTERNATIVE": "替代方案: 不同商品或规格, 并显式列出改变项",
            }[route_type],
            "matched_constraints": matched or row["fit_tags"],
            "unmet_constraints": unmet,
            "risks": ["演示商品与报价, 不代表真实市场供应"],
            "evidence_refs": row["evidence_refs"],
            "recommendation_type": route_type,
            "relaxed_constraints": relaxed,
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

    def _offer_payload(self, row, user_id, fresh=False):
        payload = (
            self.get_offers(user_id, UUID(row["product_id"]), fresh)
            .offers[0]
            .model_dump(mode="json")
        )
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

    @staticmethod
    def _offer_evidence(row):
        offer = row["offer"]
        payload = json.dumps(offer, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return ToolEvidence(
            offer["source_ref"],
            hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            (
                "price_minor",
                "shipping_minor",
                "availability",
                "merchant_name",
                "source_ref",
                "verification",
            ),
        )

    def _result(self, key, value, rows):
        if key == "offers":
            fields = frozenset(
                {
                    "price_minor",
                    "shipping_minor",
                    "availability",
                    "merchant_name",
                    "source_ref",
                    "verification",
                }
            )
            return ToolResult(
                {key: value},
                tuple(self._offer_evidence(row) for row in rows),
                fields,
            )
        return ToolResult(
            {key: value},
            tuple(self._evidence(row) for row in rows),
            frozenset({"title", "brand", "category", "attributes"}),
        )

    @staticmethod
    def _offer_view(row):
        now = datetime.now(UTC)
        offer = row["offer"]
        evidence_ref = offer["source_ref"]
        expires_at = now + timedelta(minutes=15)
        return OfferView(
            offer_id=UUID(offer["offer_id"]),
            merchant_name=offer["merchant_name"],
            verification="DEMO_FIXTURE",
            availability=offer["availability"],
            price_minor=offer["price_minor"],
            shipping_minor=offer["shipping_minor"],
            currency=offer["currency"],
            collected_at=now,
            expires_at=expires_at,
            source_ref=evidence_ref,
            business_facts=[
                BusinessFactView(
                    fact_type="price",
                    summary=f"演示报价 ¥{offer['price_minor'] / 100:.2f}; 不可作为成交价",
                    verification_level="DEMO_FIXTURE",
                    observed_at=now,
                    expires_at=expires_at,
                    evidence_ref=evidence_ref,
                ),
                BusinessFactView(
                    fact_type="inventory",
                    summary="演示目录包含此报价; 不代表真实库存",
                    verification_level="DEMO_FIXTURE",
                    observed_at=now,
                    expires_at=expires_at,
                    evidence_ref=evidence_ref,
                ),
                BusinessFactView(
                    fact_type="delivery",
                    summary="未接入真实地址、仓库或配送承诺",
                    verification_level="DEMO_FIXTURE",
                    observed_at=now,
                    evidence_ref=evidence_ref,
                ),
                BusinessFactView(
                    fact_type="merchant",
                    summary="演示商家; 不代表官方旗舰店或平台自营",
                    verification_level="DEMO_FIXTURE",
                    observed_at=now,
                    evidence_ref=evidence_ref,
                ),
                BusinessFactView(
                    fact_type="after_sales",
                    summary="未接入真实退换货、发票或联保条款",
                    verification_level="DEMO_FIXTURE",
                    observed_at=now,
                    evidence_ref=evidence_ref,
                ),
            ],
        )


def create_demo_app(catalog_path: Path, *, ops_credentials=None):
    from .media_tools import media_tool_handlers

    commerce = DemoCommerce(catalog_path)
    media = InMemoryMediaStore()
    provider = DemoProvider()
    agent = ShoppingAgent(
        provider,
        ToolRegistry(media_tool_handlers(commerce.tool_handlers(), media, provider)),
        InMemoryCheckpointStore(),
        RuntimeIdentity(
            "shopping-agent-v3-demo",
            "deterministic-demo",
            "agent-first-v3",
            "commercial-truth-v3",
            "0.2.0",
        ),
    )
    from .installation_auth import InMemoryInstallations

    return create_app(
        TurnService(agent, media),
        media,
        commerce=commerce,
        ops_store=InMemoryOpsStore(),
        development_identity=True,
        installation_store=InMemoryInstallations(),
        ops_credentials=ops_credentials,
    )
