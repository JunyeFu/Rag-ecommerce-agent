"""Recorded/synthetic contract fixtures that can never claim live authorization."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from ragcommerce_domain import (
    DeepLink,
    Money,
    Offer,
    OfferQuote,
    QuoteAvailability,
    VerificationLevel,
)

from .security import SafeLinkPolicy
from .spi import (
    ConnectorCapability,
    ConnectorError,
    ConnectorErrorKind,
    RequoteOutcome,
    RequoteResult,
)


class FixtureConnector:
    def __init__(self, fixture: dict[str, object]) -> None:
        self._fixture = fixture
        self.capability = ConnectorCapability(
            platform=str(fixture["platform"]),
            modes=("RECORDED_FIXTURE", "DISCOVERY_ONLY"),
            can_quote=True,
            can_resolve_affiliate_link=True,
        )
        self._records = {UUID(item["offer_id"]): item for item in fixture["offers"]}  # type: ignore[index]
        self._policy = SafeLinkPolicy(frozenset(str(host) for host in fixture["allowed_hosts"]))  # type: ignore[arg-type]

    def offers(self) -> tuple[Offer, ...]:
        return tuple(
            Offer(
                UUID(item["offer_id"]),
                UUID(item["variant_id"]),
                UUID(item["merchant_id"]),
                str(item["external_key"]),
            )
            for item in self._records.values()
        )

    def quote(self, offer_id: UUID) -> OfferQuote:
        try:
            item = self._records[offer_id]
        except KeyError as exc:
            raise ConnectorError(
                ConnectorErrorKind.INVALID_RESPONSE, "unknown fixture offer", retryable=False
            ) from exc
        verification = VerificationLevel(str(item["verification"]))
        price = item.get("price_minor")
        return OfferQuote(
            id=UUID(item["quote_id"]),
            offer_id=offer_id,
            verification=verification,
            availability=QuoteAvailability(str(item["availability"])),
            collected_at=datetime.fromisoformat(str(item["collected_at"]).replace("Z", "+00:00")),
            expires_at=datetime.fromisoformat(str(item["expires_at"]).replace("Z", "+00:00")),
            source_ref=f"fixture:{self.capability.platform}:{item['external_key']}",
            price=Money(int(price)) if price is not None else None,
            shipping=Money(int(item["shipping_minor"]))
            if item.get("shipping_minor") is not None
            else None,
        )

    def requote(self, previous: OfferQuote) -> RequoteResult:
        current = self.quote(previous.offer_id)
        if current.verification is VerificationLevel.DISCOVERY_ONLY:
            outcome = RequoteOutcome.UNVERIFIED
        elif current.availability is QuoteAvailability.UNAVAILABLE:
            outcome = RequoteOutcome.UNAVAILABLE
        elif current.commercial_facts_changed_from(previous):
            outcome = RequoteOutcome.CHANGED
        else:
            outcome = RequoteOutcome.UNCHANGED
        return RequoteResult(outcome, previous.id, current, outcome is RequoteOutcome.UNCHANGED)

    def resolve_link(self, offer_id: UUID) -> DeepLink:
        item = self._records[offer_id]
        url = self._policy.validate_chain(tuple(str(url) for url in item["redirect_chain"]))  # type: ignore[arg-type]
        return DeepLink(
            UUID(item["link_id"]),
            offer_id,
            url,
            tuple(self._policy.allowed_hosts),
            str(item["disclosure"]),
            datetime.fromisoformat(str(item["link_expires_at"]).replace("Z", "+00:00")),
        )


def load_fixture_connectors(directory: Path) -> tuple[FixtureConnector, ...]:
    return tuple(
        FixtureConnector(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(directory.glob("*.json"))
    )
