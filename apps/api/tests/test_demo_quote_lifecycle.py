from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from ragcommerce_api import demo
from ragcommerce_contracts import ResolveOfferRequest

ROOT = Path(__file__).resolve().parents[3]


def test_reading_quote_does_not_renew_it_and_requote_is_explicit(monkeypatch):
    clock = datetime(2026, 10, 13, 8, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock

    monkeypatch.setattr(demo, "datetime", Clock)
    commerce = demo.DemoCommerce(ROOT / "data/demo/catalog.v3.jsonl")
    owner = uuid4()
    product = next(iter(commerce.rows))
    first = commerce.get_offers(owner, product, False).offers[0]
    clock += timedelta(minutes=16)
    expired = commerce.get_offers(owner, product, False).offers[0]
    assert expired == first
    assert expired.expires_at < clock
    blocked = commerce.resolve_offer(owner, first.offer_id, ResolveOfferRequest())
    assert blocked.link_url is None
    assert blocked.expires_at == first.expires_at
    fresh = commerce.get_offers(owner, product, True).offers[0]
    assert fresh.collected_at == clock
    assert fresh.expires_at == clock + timedelta(minutes=15)
    resolved = commerce.resolve_offer(owner, first.offer_id, ResolveOfferRequest())
    assert resolved.link_url.startswith("https://example.com/")
    assert resolved.expires_at == fresh.expires_at


def test_requote_is_scoped_to_the_owner(monkeypatch):
    clock = datetime(2026, 10, 13, 8, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock

    monkeypatch.setattr(demo, "datetime", Clock)
    commerce = demo.DemoCommerce(ROOT / "data/demo/catalog.v3.jsonl")
    alice, bob = uuid4(), uuid4()
    product = next(iter(commerce.rows))
    first = commerce.get_offers(alice, product, False)
    clock += timedelta(minutes=1)
    commerce.get_offers(bob, product, True)
    assert commerce.get_offers(alice, product, False) == first
