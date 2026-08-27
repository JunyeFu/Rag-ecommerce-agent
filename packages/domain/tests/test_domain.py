from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st
from ragcommerce_domain import (
    AgentRun,
    AgentRunStatus,
    DeepLink,
    Money,
    OfferQuote,
    Product,
    ProductVariant,
    QuoteAvailability,
    QuoteState,
    VerificationLevel,
)
from ragcommerce_domain.persistence import FORBIDDEN_TRANSACTION_TABLES, metadata


@given(st.integers(-(2**62), 2**62 - 1), st.integers(-(2**62), 2**62 - 1))
def test_money_addition_is_exact(left: int, right: int) -> None:
    assert (Money(left) + Money(right)).amount_minor == left + right


def test_money_rejects_float_and_other_currency() -> None:
    with pytest.raises(TypeError):
        Money(19.99)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="CNY"):
        Money(100, "USD")


def quote(**overrides: object) -> OfferQuote:
    now = datetime(2026, 8, 26, tzinfo=UTC)
    values: dict[str, object] = {
        "id": uuid4(),
        "offer_id": uuid4(),
        "verification": VerificationLevel.LIVE_AUTHORIZED,
        "availability": QuoteAvailability.AVAILABLE,
        "collected_at": now,
        "expires_at": now + timedelta(minutes=5),
        "source_ref": "fixture:offer:1",
        "price": Money(129900),
        "shipping": Money(0),
    }
    values.update(overrides)
    return OfferQuote(**values)  # type: ignore[arg-type]


def test_quote_state_and_commercial_change_are_deterministic() -> None:
    current = quote()
    assert current.state_at(current.collected_at) is QuoteState.FRESH
    assert current.state_at(current.expires_at) is QuoteState.EXPIRED
    changed = quote(offer_id=current.offer_id, price=Money(130000))
    assert changed.commercial_facts_changed_from(current)


def test_discovery_and_live_ttl_cannot_claim_false_price() -> None:
    with pytest.raises(ValueError, match="discovery-only"):
        quote(verification=VerificationLevel.DISCOVERY_ONLY)
    with pytest.raises(ValueError, match="five minutes"):
        quote(expires_at=datetime(2026, 8, 26, tzinfo=UTC) + timedelta(minutes=6))


def test_product_variant_offer_boundaries_use_distinct_ids() -> None:
    product = Product(uuid4(), "Phone X", "phones")
    variant = ProductVariant(uuid4(), product.id, "phone-x-256-black", {"storage": "256GB"})
    assert isinstance(product.id, UUID)
    assert variant.id != product.id
    assert variant.product_id == product.id


def test_deep_link_requires_allowed_https_host() -> None:
    expires = datetime(2026, 8, 27, tzinfo=UTC)
    link = DeepLink(
        uuid4(), uuid4(), "https://item.example/p/1", ("item.example",), "推广链接", expires
    )
    assert link.is_valid_at(datetime(2026, 8, 26, tzinfo=UTC))
    with pytest.raises(ValueError, match="allowed host"):
        DeepLink(
            uuid4(), uuid4(), "http://evil.invalid/p/1", ("item.example",), "推广链接", expires
        )


def test_agent_run_requires_versions_and_idempotency() -> None:
    run = AgentRun(
        uuid4(),
        uuid4(),
        "turn-001",
        AgentRunStatus.PENDING,
        "fake-1",
        "p1",
        "policy1",
        "0.1.0",
        datetime.now(UTC),
    )
    assert run.idempotency_key == "turn-001"
    with pytest.raises(ValueError, match="idempotency_key"):
        AgentRun(
            uuid4(), uuid4(), " ", AgentRunStatus.PENDING, "m", "p", "g", "0.1.0", datetime.now(UTC)
        )


def test_persistence_has_expected_boundaries_and_no_transaction_ledger() -> None:
    required = {
        "products",
        "product_variants",
        "offers",
        "offer_quotes",
        "agent_runs",
        "tool_invocations",
        "evidence_refs",
    }
    assert required <= set(metadata.tables)
    assert FORBIDDEN_TRANSACTION_TABLES.isdisjoint(metadata.tables)
