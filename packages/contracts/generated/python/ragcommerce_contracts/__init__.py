"""Generated file; do not edit. generator=4 source_sha256=54898f9e23ab4e93df3ebeb00b7d52ec82e9d6a55d37250ce999ed000cf39d6f"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "0.2.0"
CONTRACT_SOURCE_SHA256 = "54898f9e23ab4e93df3ebeb00b7d52ec82e9d6a55d37250ce999ed000cf39d6f"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictModel):
    status: Literal["ok"]
    contract_version: str


class CreateThreadRequest(StrictModel):
    goal: str = Field(min_length=1, max_length=500)


class ThreadCreated(StrictModel):
    thread_id: UUID
    mission_id: UUID


class MissionItemView(StrictModel):
    category: str
    quantity: int = Field(ge=1, le=99)


class ShoppingMissionView(StrictModel):
    goal: str
    version: int = Field(ge=1)
    items: list[MissionItemView] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    soft_preferences: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    budget_total_minor: int | None = Field(default=None, ge=0)
    currency: Literal["CNY"] = "CNY"


class ProductCandidateView(StrictModel):
    product_id: UUID
    variant_id: UUID
    title: str
    fit_summary: str = ""
    matched_constraints: list[str] = Field(default_factory=list)
    unmet_constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    recommendation_type: Literal["STRICT", "BUDGET", "ALTERNATIVE"] = "STRICT"
    relaxed_constraints: list[str] = Field(default_factory=list)


class RecommendationRouteView(StrictModel):
    route_type: Literal["STRICT", "BUDGET", "ALTERNATIVE"]
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    summary: str
    relaxed_constraints: list[str] = Field(default_factory=list)
    product_ids: list[UUID] = Field(default_factory=list)


class ComparisonSelection(StrictModel):
    product_ids: list[UUID] = Field(default_factory=list, max_length=4)


class ExplorationDirection(StrictModel):
    direction_id: str
    title: str
    category: str
    experience_tags: list[str]
    evidence_refs: list[str]
    supporting_product_ids: list[UUID]
    scenario_hint: str = ""
    try_first: str = ""
    to_confirm: str = ""


class ExplorationState(StrictModel):
    directions: list[ExplorationDirection] = Field(default_factory=list)
    feedback: dict[str, Literal["interested", "not_interested"]] = Field(default_factory=dict)
    shown_direction_ids: list[str] = Field(default_factory=list)
    shown_product_ids: list[UUID] = Field(default_factory=list)
    experience_tags: list[str] = Field(default_factory=list)
    selected_direction_id: str | None = None
    exhausted: bool = False
    ended: bool = False
    outcome: Literal["UNDECIDED", "USE_EXISTING", "NOT_BUYING"] | None = None


class MediaInterpretation(StrictModel):
    media_id: UUID
    kind: Literal["image", "audio"]
    recognized_text: str = Field(max_length=2000)
    category: Literal["手机", "电脑", "耳机", "相机"] | None = None
    visible_attributes: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    supported: bool


class MediaConfirmation(StrictModel):
    source_run_id: UUID
    text: str = Field(min_length=1, max_length=500)


class ThreadExperience(StrictModel):
    title: str | None = None
    archived: bool = False
    feedback: dict[str, str] = Field(default_factory=dict)


class CandidateFeedback(StrictModel):
    product_id: UUID
    expected_mission_version: int = Field(ge=1)
    scope: Literal["PRODUCT", "CATEGORY"] = "PRODUCT"
    reason: str = Field(min_length=1, max_length=200)
    undo: bool = False


class ThreadHistoryPatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=80)
    archived: bool | None = None


class ThreadHistoryEntry(StrictModel):
    thread_id: UUID
    goal: str
    experience: ThreadExperience
    mode: Literal["PURCHASE", "DISCOVERY"]


class ConversationMessage(StrictModel):
    run_id: UUID
    role: Literal["user", "assistant", "system"]
    text: str


class ThreadSnapshot(StrictModel):
    experience: ThreadExperience = Field(default_factory=ThreadExperience)
    mode: Literal["PURCHASE", "DISCOVERY"] = "PURCHASE"
    exploration: ExplorationState | None = None
    pending_media_interpretations: list[MediaInterpretation] = Field(default_factory=list)
    thread_id: UUID
    mission_id: UUID
    goal: str
    status: Literal[
        "IDLE", "RUNNING", "WAITING_APPROVAL", "WAITING_CLARIFICATION", "COMPLETED", "FAILED"
    ]
    last_event_id: int = Field(ge=0)
    pending_action: str | None = None
    pending_action_arguments: dict[str, str | int] = Field(default_factory=dict)
    active_run_id: UUID | None = None
    candidates: list[ProductCandidateView] = Field(default_factory=list)
    recommendation_routes: list[RecommendationRouteView] = Field(default_factory=list)
    mission: ShoppingMissionView
    selected_product_ids: list[UUID] = Field(default_factory=list, max_length=4)


class ProductView(StrictModel):
    product_id: UUID
    variant_id: UUID
    title: str
    category: str
    brand: str
    attributes: dict[str, str]
    image_ref: str | None = None
    evidence_refs: list[str]


class MediaCreated(StrictModel):
    media_id: UUID
    kind: Literal["image", "audio"]
    content_type: str
    size_bytes: int
    sha256: str
    expires_at: datetime


class ExplorationAction(StrictModel):
    kind: Literal["start", "feedback", "next", "select_for_purchase", "end"]
    experience_tags: list[Literal["life_improvement", "novelty"]] = Field(
        default_factory=list, max_length=2
    )
    direction_id: str | None = Field(default=None, min_length=1, max_length=100)
    value: Literal["interested", "not_interested", "neutral"] | None = None
    outcome: Literal["UNDECIDED", "USE_EXISTING", "NOT_BUYING"] | None = None


class TurnRequest(StrictModel):
    text: str = Field(default="", max_length=10000)
    media_ids: tuple[UUID, ...] = Field(default=(), max_length=8)
    exploration_action: ExplorationAction | None = None
    expected_mission_version: int | None = Field(default=None, ge=1)
    media_confirmation: MediaConfirmation | None = None


class TurnAccepted(StrictModel):
    run_id: UUID
    replayed: bool
    event_count: int


class AgentDecision(StrictModel):
    tool_name: str = Field(min_length=1, max_length=100)
    approved: bool


class DecisionAccepted(StrictModel):
    run_id: UUID
    approved: bool
    event_count: int


class DeletionResult(StrictModel):
    deleted: bool


class BusinessFactView(StrictModel):
    fact_type: Literal["price", "inventory", "delivery", "merchant", "after_sales"]
    summary: str
    verification_level: Literal[
        "LIVE_AUTHORIZED", "FEED_VERIFIED", "DISCOVERY_ONLY", "DEMO_FIXTURE"
    ]
    observed_at: datetime
    expires_at: datetime | None = None
    evidence_ref: str


class OfferView(StrictModel):
    offer_id: UUID
    merchant_name: str
    verification: Literal["LIVE_AUTHORIZED", "FEED_VERIFIED", "DISCOVERY_ONLY", "DEMO_FIXTURE"]
    availability: Literal["AVAILABLE", "UNAVAILABLE", "UNKNOWN"]
    price_minor: int | None = None
    shipping_minor: int | None = None
    currency: Literal["CNY"] | None = None
    collected_at: datetime
    expires_at: datetime
    source_ref: str
    business_facts: list[BusinessFactView] = Field(default_factory=list)


class OfferCollection(StrictModel):
    product_id: UUID
    offers: list[OfferView]


class ResolveOfferRequest(StrictModel):
    quote_id: UUID | None = None
    confirmed_quote_change: bool = False


class ResolvedOffer(StrictModel):
    offer_id: UUID
    link_url: str | None = None
    disclosure: str
    expires_at: datetime | None = None
    quote_changed: bool
    requires_confirmation: bool


class ShoppingListView(StrictModel):
    list_id: UUID
    name: str
    variant_ids: list[UUID]


class ShoppingListsResponse(StrictModel):
    lists: list[ShoppingListView]


class CreateListRequest(StrictModel):
    name: str = Field(min_length=1, max_length=120)


class PatchListRequest(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    add_variant_id: UUID | None = None
    remove_variant_id: UUID | None = None


class CartItemView(StrictModel):
    offer_id: UUID
    quantity: int = Field(ge=1, le=99)
    product: ProductView
    quote: OfferView


class CartView(StrictModel):
    items: list[CartItemView]


class CartMutation(StrictModel):
    operation: Literal["add", "set", "remove"]
    offer_id: UUID
    quantity: int = Field(default=1, ge=1, le=99)


class CreateWatcherRequest(StrictModel):
    kind: Literal["PRICE_BELOW", "RESTOCK"]
    offer_id: UUID
    threshold_minor: int | None = Field(default=None, ge=0)


class WatcherView(StrictModel):
    watcher_id: UUID
    thread_id: UUID
    offer_id: UUID
    kind: Literal["PRICE_BELOW", "RESTOCK"]
    threshold_minor: int | None = Field(default=None, ge=0)
    status: Literal["DEMO_DRAFT"] = "DEMO_DRAFT"
    scheduler_active: Literal[False] = False
    disclosure: str
    created_at: datetime


class WatcherCollection(StrictModel):
    watchers: list[WatcherView]


__all__ = [
    "CONTRACT_SOURCE_SHA256",
    "CONTRACT_VERSION",
    "AgentDecision",
    "BusinessFactView",
    "CartItemView",
    "CartMutation",
    "CartView",
    "ComparisonSelection",
    "CreateListRequest",
    "CreateThreadRequest",
    "CreateWatcherRequest",
    "DecisionAccepted",
    "DeletionResult",
    "HealthResponse",
    "MediaCreated",
    "MissionItemView",
    "OfferCollection",
    "OfferView",
    "PatchListRequest",
    "ProductCandidateView",
    "ProductView",
    "RecommendationRouteView",
    "ResolveOfferRequest",
    "ResolvedOffer",
    "ShoppingListView",
    "ShoppingListsResponse",
    "ShoppingMissionView",
    "ThreadCreated",
    "ThreadSnapshot",
    "TurnAccepted",
    "TurnRequest",
    "WatcherCollection",
    "WatcherView",
]
