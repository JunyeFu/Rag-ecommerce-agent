"""Commercial read/write port; API routes do not derive marketplace facts."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from ragcommerce_contracts import (
    CartMutation,
    CartView,
    CreateListRequest,
    OfferCollection,
    PatchListRequest,
    ResolvedOffer,
    ResolveOfferRequest,
    ShoppingListsResponse,
    ShoppingListView,
)


class CommercePort(Protocol):
    def get_offers(self, user_id: UUID, product_id: UUID, fresh: bool) -> OfferCollection: ...

    def resolve_offer(
        self, user_id: UUID, offer_id: UUID, request: ResolveOfferRequest
    ) -> ResolvedOffer: ...

    def get_lists(self, user_id: UUID) -> ShoppingListsResponse: ...

    def create_list(self, user_id: UUID, request: CreateListRequest) -> ShoppingListView: ...

    def patch_list(
        self, user_id: UUID, list_id: UUID, request: PatchListRequest
    ) -> ShoppingListView: ...

    def get_cart(self, user_id: UUID) -> CartView: ...

    def mutate_cart(self, user_id: UUID, request: CartMutation) -> CartView: ...
