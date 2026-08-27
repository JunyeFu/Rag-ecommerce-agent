"""Generated file; do not edit. generator=2 source_sha256=267cb76a25754c1b81655dbd96c725e46520db160c05a6aea5febff81997350d"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "0.1.0"
CONTRACT_SOURCE_SHA256 = "267cb76a25754c1b81655dbd96c725e46520db160c05a6aea5febff81997350d"


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
    verification: Literal["LIVE_AUTHORIZED", "FEED_VERIFIED", "DISCOVERY_ONLY"]
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
    "ResolveOfferRequest",
    "ResolvedOffer",
    "ShoppingListView",
    "ShoppingListsResponse",
    "ThreadCreated",
    "TurnAccepted",
    "TurnRequest",
]
