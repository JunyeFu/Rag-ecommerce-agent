"""Generated file; do not edit. generator=3 source_sha256=08fa7e7cb7446628bc1407cedc5bffb4a5bbfb0914ed1bca8c91216a5799d076"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "0.2.0"
CONTRACT_SOURCE_SHA256 = "08fa7e7cb7446628bc1407cedc5bffb4a5bbfb0914ed1bca8c91216a5799d076"


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


class ProductCandidateView(StrictModel):
    product_id: UUID
    variant_id: UUID
    title: str
    fit_summary: str = ""
    matched_constraints: list[str] = Field(default_factory=list)
    unmet_constraints: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class ThreadSnapshot(StrictModel):
    thread_id: UUID
    mission_id: UUID
    goal: str
    status: Literal[
        "IDLE", "RUNNING", "WAITING_APPROVAL", "WAITING_CLARIFICATION", "COMPLETED", "FAILED"
    ]
    last_event_id: int = Field(ge=0)
    pending_action: str | None = None
    candidates: list[ProductCandidateView] = Field(default_factory=list)


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


class TurnRequest(StrictModel):
    text: str = Field(default="", max_length=10000)
    media_ids: tuple[UUID, ...] = Field(default=(), max_length=8)


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


class CartView(StrictModel):
    items: list[CartItemView]


class CartMutation(StrictModel):
    operation: Literal["add", "set", "remove"]
    offer_id: UUID
    quantity: int = Field(default=1, ge=1, le=99)


__all__ = [
    "CONTRACT_SOURCE_SHA256",
    "CONTRACT_VERSION",
    "AgentDecision",
    "CartItemView",
    "CartMutation",
    "CartView",
    "CreateListRequest",
    "CreateThreadRequest",
    "DecisionAccepted",
    "DeletionResult",
    "HealthResponse",
    "MediaCreated",
    "OfferCollection",
    "OfferView",
    "PatchListRequest",
    "ProductCandidateView",
    "ProductView",
    "ResolveOfferRequest",
    "ResolvedOffer",
    "ShoppingListView",
    "ShoppingListsResponse",
    "ThreadCreated",
    "ThreadSnapshot",
    "TurnAccepted",
    "TurnRequest",
]
