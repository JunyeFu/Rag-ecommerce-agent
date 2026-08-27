"""Discovery-only boundary: links are allowed, monetary facts are impossible."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid5

from ragcommerce_domain import DeepLink, Offer, OfferQuote, QuoteAvailability, VerificationLevel

from .security import SafeLinkPolicy
from .spi import ConnectorCapability, RequoteOutcome, RequoteResult


class DiscoveryConnector:
    def __init__(
        self,
        platform: str,
        offer: Offer,
        url: str,
        allowed_hosts: frozenset[str],
        observed_at: datetime,
        expires_at: datetime,
    ) -> None:
        self.capability = ConnectorCapability(platform, ("DISCOVERY_ONLY",), False, True)
        self._offer, self._url, self._observed_at, self._expires_at = (
            offer,
            url,
            observed_at,
            expires_at,
        )
        self._policy = SafeLinkPolicy(allowed_hosts)

    def offers(self) -> tuple[Offer, ...]:
        return (self._offer,)

    def quote(self, offer_id: UUID) -> OfferQuote:
        if offer_id != self._offer.id:
            raise KeyError("unknown discovery offer")
        return OfferQuote(
            uuid5(offer_id, "discovery-quote"),
            offer_id,
            VerificationLevel.DISCOVERY_ONLY,
            QuoteAvailability.UNKNOWN,
            self._observed_at,
            self._expires_at,
            f"discovery:{self.capability.platform}:{self._offer.external_key}",
        )

    def requote(self, previous: OfferQuote) -> RequoteResult:
        return RequoteResult(
            RequoteOutcome.UNVERIFIED, previous.id, self.quote(previous.offer_id), False
        )

    def resolve_link(self, offer_id: UUID) -> DeepLink:
        validated = self._policy.validate_chain((self._url,))
        return DeepLink(
            uuid5(offer_id, "discovery-link"),
            offer_id,
            validated,
            tuple(self._policy.allowed_hosts),
            "发现链接; 价格与成交条件待商家确认",
            self._expires_at,
        )
