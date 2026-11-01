"""Real database quote persistence and owner erasure."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from ragcommerce_api import demo
from ragcommerce_api.erasure import PostgresUserDataEraser
from ragcommerce_api.postgres_demo import PostgresDemoCommerce
from ragcommerce_contracts import ResolveOfferRequest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3]


def test_quote_survives_adapter_restart_and_owner_erasure(monkeypatch):
    dsn = os.environ.get("API_DATABASE_URL")
    if not dsn:
        pytest.skip("API_DATABASE_URL required")
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    clock = datetime(2026, 10, 13, 8, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock

    monkeypatch.setattr(demo, "datetime", Clock)
    first = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn)
    second = PostgresDemoCommerce(ROOT / "data/demo/catalog.v3.jsonl", dsn)
    alice, bob = uuid4(), uuid4()
    product = next(iter(first.rows))
    quote = first.get_offers(alice, product, False).offers[0]
    bob_quote = first.get_offers(bob, product, False)
    clock += timedelta(minutes=16)
    assert second.get_offers(alice, product, False).offers[0] == quote
    assert second.resolve_offer(alice, quote.offer_id, ResolveOfferRequest()).link_url is None
    renewed = second.get_offers(alice, product, True)
    assert first.get_offers(alice, product, False) == renewed
    assert first.get_offers(bob, product, False) == bob_quote
    assert PostgresUserDataEraser(dsn).delete_user(alice) == 1
    clock += timedelta(minutes=1)
    assert first.get_offers(alice, product, False).offers[0].collected_at == clock
    assert second.get_offers(bob, product, False) == bob_quote
