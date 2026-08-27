"""Framework-free domain types for commercial facts and Agent evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from urllib.parse import urlparse
from uuid import UUID


def _required(value: str, label: str, maximum: int = 256) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{label} must contain 1..{maximum} characters")
    return normalized


def _aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: str = "CNY"

    def __post_init__(self) -> None:
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise TypeError("amount_minor must be an integer, never float")
        if not -(2**63) <= self.amount_minor < 2**63:
            raise ValueError("amount_minor exceeds signed 64-bit range")
        if self.currency != "CNY":
            raise ValueError("V2 baseline supports CNY only")

    def __add__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError("currency mismatch")
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError("currency mismatch")
        return Money(self.amount_minor - other.amount_minor, self.currency)


class VerificationLevel(StrEnum):
    LIVE_AUTHORIZED = "LIVE_AUTHORIZED"
    FEED_VERIFIED = "FEED_VERIFIED"
    DISCOVERY_ONLY = "DISCOVERY_ONLY"


class QuoteAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class QuoteState(StrEnum):
    FRESH = "FRESH"
    EXPIRED = "EXPIRED"
    UNAVAILABLE = "UNAVAILABLE"
    DISCOVERY_ONLY = "DISCOVERY_ONLY"


@dataclass(frozen=True, slots=True)
class Product:
    id: UUID
    canonical_name: str
    category_key: str
    brand_key: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "canonical_name", _required(self.canonical_name, "canonical_name"))
        object.__setattr__(self, "category_key", _required(self.category_key, "category_key", 96))
        if self.brand_key is not None:
            object.__setattr__(self, "brand_key", _required(self.brand_key, "brand_key", 96))


@dataclass(frozen=True, slots=True)
class ProductVariant:
    id: UUID
    product_id: UUID
    variant_key: str
    attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "variant_key", _required(self.variant_key, "variant_key", 160))
        normalized = {
            str(key).strip(): str(value).strip() for key, value in self.attributes.items()
        }
        if any(not key or not value for key, value in normalized.items()):
            raise ValueError("variant attributes require non-empty keys and values")
        object.__setattr__(self, "attributes", MappingProxyType(dict(sorted(normalized.items()))))


@dataclass(frozen=True, slots=True)
class Marketplace:
    id: UUID
    code: str
    display_name: str
    allowed_hosts: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _required(self.code, "marketplace code", 32).lower())
        object.__setattr__(self, "display_name", _required(self.display_name, "display_name"))
        hosts = tuple(sorted({host.strip().lower().rstrip(".") for host in self.allowed_hosts}))
        if not hosts or any(not host or "/" in host for host in hosts):
            raise ValueError("marketplace requires valid allowed hosts")
        object.__setattr__(self, "allowed_hosts", hosts)


@dataclass(frozen=True, slots=True)
class Merchant:
    id: UUID
    marketplace_id: UUID
    external_key: str
    display_name: str
    verified: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "external_key", _required(self.external_key, "external_key", 160))
        object.__setattr__(self, "display_name", _required(self.display_name, "display_name"))


@dataclass(frozen=True, slots=True)
class Offer:
    id: UUID
    variant_id: UUID
    merchant_id: UUID
    external_key: str
    active: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "external_key", _required(self.external_key, "external_key", 200))


@dataclass(frozen=True, slots=True)
class OfferQuote:
    id: UUID
    offer_id: UUID
    verification: VerificationLevel
    availability: QuoteAvailability
    collected_at: datetime
    expires_at: datetime
    source_ref: str
    price: Money | None = None
    shipping: Money | None = None

    def __post_init__(self) -> None:
        collected = _aware(self.collected_at, "collected_at")
        expires = _aware(self.expires_at, "expires_at")
        if expires <= collected:
            raise ValueError("expires_at must be later than collected_at")
        if (
            self.verification is VerificationLevel.LIVE_AUTHORIZED
            and expires - collected > timedelta(minutes=5)
        ):
            raise ValueError("live quote TTL may not exceed five minutes")
        if self.verification is VerificationLevel.DISCOVERY_ONLY and (self.price or self.shipping):
            raise ValueError("discovery-only quote cannot contain monetary facts")
        if self.availability is QuoteAvailability.UNAVAILABLE and self.price is not None:
            raise ValueError("unavailable quote cannot contain a current price")
        if self.price and self.shipping and self.price.currency != self.shipping.currency:
            raise ValueError("price and shipping currency mismatch")
        object.__setattr__(self, "source_ref", _required(self.source_ref, "source_ref", 512))

    def state_at(self, now: datetime) -> QuoteState:
        current = _aware(now, "now")
        if self.verification is VerificationLevel.DISCOVERY_ONLY:
            return QuoteState.DISCOVERY_ONLY
        if self.availability is QuoteAvailability.UNAVAILABLE:
            return QuoteState.UNAVAILABLE
        return QuoteState.EXPIRED if current >= self.expires_at else QuoteState.FRESH

    @property
    def total(self) -> Money | None:
        if self.price is None:
            return None
        return self.price if self.shipping is None else self.price + self.shipping

    def commercial_facts_changed_from(self, previous: OfferQuote) -> bool:
        if self.offer_id != previous.offer_id:
            raise ValueError("quotes belong to different offers")
        return (self.total, self.availability, self.verification) != (
            previous.total,
            previous.availability,
            previous.verification,
        )


@dataclass(frozen=True, slots=True)
class DeepLink:
    id: UUID
    offer_id: UUID
    url: str
    marketplace_host_allowlist: tuple[str, ...]
    disclosure: str
    expires_at: datetime

    def __post_init__(self) -> None:
        parsed = urlparse(self.url)
        host = (parsed.hostname or "").lower().rstrip(".")
        allowed = tuple(item.lower().rstrip(".") for item in self.marketplace_host_allowlist)
        if parsed.scheme != "https" or host not in allowed or parsed.username or parsed.password:
            raise ValueError("deep link must be credential-free HTTPS on an allowed host")
        _aware(self.expires_at, "expires_at")
        object.__setattr__(self, "disclosure", _required(self.disclosure, "disclosure", 300))

    def is_valid_at(self, now: datetime) -> bool:
        return _aware(now, "now") < self.expires_at


@dataclass(frozen=True, slots=True)
class ShoppingMission:
    id: UUID
    user_ref: str
    goal: str
    budget: Money | None
    hard_constraints: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    consented_preferences: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "user_ref", _required(self.user_ref, "user_ref", 128))
        object.__setattr__(self, "goal", _required(self.goal, "goal", 500))
        if self.budget is not None and self.budget.amount_minor < 0:
            raise ValueError("budget cannot be negative")


@dataclass(frozen=True, slots=True)
class ShoppingList:
    id: UUID
    mission_id: UUID
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required(self.name, "list name", 120))


@dataclass(frozen=True, slots=True)
class CartItem:
    offer_id: UUID
    quantity: int

    def __post_init__(self) -> None:
        if isinstance(self.quantity, bool) or not 1 <= self.quantity <= 99:
            raise ValueError("cart quantity must be in 1..99")


@dataclass(frozen=True, slots=True)
class Cart:
    id: UUID
    mission_id: UUID
    items: tuple[CartItem, ...] = ()

    def __post_init__(self) -> None:
        ids = [item.offer_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("cart has duplicate offers")


@dataclass(frozen=True, slots=True)
class Conversation:
    id: UUID
    mission_id: UUID
    created_at: datetime

    def __post_init__(self) -> None:
        _aware(self.created_at, "created_at")


class AgentRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentStepKind(StrEnum):
    GUARDRAIL = "GUARDRAIL"
    PLAN = "PLAN"
    TOOL = "TOOL"
    EVIDENCE = "EVIDENCE"
    RESPONSE = "RESPONSE"


class ToolInvocationStatus(StrEnum):
    REQUESTED = "REQUESTED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DENIED = "DENIED"


@dataclass(frozen=True, slots=True)
class AgentRun:
    id: UUID
    conversation_id: UUID
    idempotency_key: str
    status: AgentRunStatus
    model_version: str
    prompt_version: str
    policy_version: str
    contract_version: str
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "idempotency_key", _required(self.idempotency_key, "idempotency_key", 128)
        )
        for name in ("model_version", "prompt_version", "policy_version", "contract_version"):
            object.__setattr__(self, name, _required(getattr(self, name), name, 128))
        _aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class AgentStep:
    id: UUID
    run_id: UUID
    sequence: int
    kind: AgentStepKind
    created_at: datetime

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("step sequence cannot be negative")
        _aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    id: UUID
    step_id: UUID
    tool_name: str
    idempotency_key: str
    status: ToolInvocationStatus
    arguments_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_name", _required(self.tool_name, "tool_name", 100))
        object.__setattr__(
            self, "idempotency_key", _required(self.idempotency_key, "idempotency_key", 128)
        )
        object.__setattr__(
            self, "arguments_sha256", _digest(self.arguments_sha256, "arguments_sha256")
        )


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    id: UUID
    run_id: UUID
    step_id: UUID
    evidence_type: str
    source_ref: str
    content_sha256: str
    observed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "evidence_type", _required(self.evidence_type, "evidence_type", 64)
        )
        object.__setattr__(self, "source_ref", _required(self.source_ref, "source_ref", 512))
        object.__setattr__(self, "content_sha256", _digest(self.content_sha256, "content_sha256"))
        _aware(self.observed_at, "observed_at")


def _digest(value: str, label: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{label} must be a SHA-256 hex digest")
    return normalized
