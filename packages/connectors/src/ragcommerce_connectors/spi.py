"""Small connector SPI; provider transports stay behind this boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from ragcommerce_domain import DeepLink, Offer, OfferQuote


class ConnectorErrorKind(StrEnum):
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    POLICY_DENIED = "POLICY_DENIED"


class ConnectorError(RuntimeError):
    def __init__(self, kind: ConnectorErrorKind, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable


class AuthorizationRequired(ConnectorError):
    def __init__(self, platform: str) -> None:
        super().__init__(
            ConnectorErrorKind.AUTHORIZATION_REQUIRED,
            f"{platform} live connector is disabled",
            retryable=False,
        )


@dataclass(frozen=True, slots=True)
class ConnectorCapability:
    platform: str
    modes: tuple[str, ...]
    can_quote: bool
    can_resolve_affiliate_link: bool
    live_enabled: bool = False

    def __post_init__(self) -> None:
        if self.live_enabled:
            raise ValueError("live capability cannot be enabled by static configuration")


class RequoteOutcome(StrEnum):
    UNCHANGED = "UNCHANGED"
    CHANGED = "CHANGED"
    UNAVAILABLE = "UNAVAILABLE"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True, slots=True)
class RequoteResult:
    outcome: RequoteOutcome
    previous_quote_id: UUID
    current_quote: OfferQuote
    deep_link_allowed: bool


class OfferConnector(Protocol):
    capability: ConnectorCapability

    def offers(self) -> tuple[Offer, ...]: ...
    def quote(self, offer_id: UUID) -> OfferQuote: ...
    def requote(self, previous: OfferQuote) -> RequoteResult: ...
    def resolve_link(self, offer_id: UUID) -> DeepLink: ...
