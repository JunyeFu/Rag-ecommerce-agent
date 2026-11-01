import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from ragcommerce_connectors import (
    ConnectorError,
    ConnectorErrorKind,
    DiscoveryConnector,
    FixtureConnector,
    GowuDemoPriceClient,
    RequoteOutcome,
    SafeLinkPolicy,
    load_fixture_connectors,
)
from ragcommerce_domain import Money, Offer, VerificationLevel

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_three_platform_contract_fixtures_are_fail_closed() -> None:
    connectors = load_fixture_connectors(FIXTURES)
    assert {connector.capability.platform for connector in connectors} == {
        "jd",
        "taobao_tmall",
        "pdd",
    }
    for connector in connectors:
        assert connector.capability.live_enabled is False
        offer = connector.offers()[0]
        quote = connector.quote(offer.id)
        assert quote.verification is VerificationLevel.FEED_VERIFIED
        assert connector.resolve_link(offer.id).url.startswith("https://")
        assert connector.requote(quote).outcome is RequoteOutcome.UNCHANGED


def test_fixture_manifest_hashes_are_frozen() -> None:
    package = FIXTURES.parent
    manifest = json.loads((package / "fixtures-manifest.json").read_text(encoding="utf-8"))
    repository = package.parents[1]
    for item in manifest["files"]:
        path = repository / item["path"]
        content = path.read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(content).hexdigest() == item["sha256"]
        assert len(content) == item["bytes"]


def test_requote_blocks_link_when_commercial_facts_changed() -> None:
    connector = load_fixture_connectors(FIXTURES)[0]
    current = connector.quote(connector.offers()[0].id)
    previous = replace(current, id=uuid4(), price=Money(current.price.amount_minor + 1))  # type: ignore[union-attr]
    result = connector.requote(previous)
    assert result.outcome is RequoteOutcome.CHANGED
    assert result.deep_link_allowed is False


def test_requote_reports_unavailable_without_last_known_price() -> None:
    raw = json.loads((FIXTURES / "jd.json").read_text(encoding="utf-8"))
    original = FixtureConnector(raw).quote(UUID(raw["offers"][0]["offer_id"]))
    raw["offers"][0].update(
        availability="UNAVAILABLE",
        price_minor=None,
        shipping_minor=None,
        quote_id="40000000-0000-4000-8000-000000000099",
    )
    result = FixtureConnector(raw).requote(original)
    assert result.outcome is RequoteOutcome.UNAVAILABLE
    assert result.current_quote.price is None
    assert result.deep_link_allowed is False


@pytest.mark.parametrize(
    "chain",
    [
        ("http://item.example/p/1",),
        ("https://127.0.0.1/p/1",),
        ("https://item.example@evil.invalid/p/1",),
        ("https://item.example:8443/p/1",),
        ("https://item.example/p/1", "https://evil.invalid/p/1"),
    ],
)
def test_link_policy_denies_ssrf_authority_and_redirect_bypass(chain: tuple[str, ...]) -> None:
    with pytest.raises(ConnectorError):
        SafeLinkPolicy(frozenset({"item.example"})).validate_chain(chain)


def test_live_link_policy_denies_dns_rebinding_to_private_address() -> None:
    policy = SafeLinkPolicy(frozenset({"item.example"}))
    with pytest.raises(ConnectorError):
        policy.validate_chain(
            ("https://item.example/p/1",),
            {"item.example": ("10.0.0.5",)},
        )
    assert (
        policy.validate_chain(
            ("https://item.example/p/1",),
            {"item.example": ("8.8.8.8",)},
        )
        == "https://item.example/p/1"
    )


def test_unicode_homograph_is_not_promoted_to_an_allowed_host() -> None:
    with pytest.raises(ConnectorError):
        SafeLinkPolicy(frozenset({"item.example"})).validate_chain(
            ("https://\u0456tem.example/p/1",)
        )


def test_unknown_offer_returns_error_not_a_synthetic_price() -> None:
    connector: FixtureConnector = load_fixture_connectors(FIXTURES)[0]
    with pytest.raises(ConnectorError):
        connector.quote(uuid4())


def test_gowu_sandbox_prices_are_explicitly_weak_demo_evidence() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.gowu-ai.com"
        assert request.headers["x-app-key"] == "sandbox-key"
        assert request.headers["x-open-user"] == "rag-commerce-demo"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "external-1",
                        "title": "演示降噪耳机",
                        "category": "耳机",
                        "brand": "演示品牌",
                        "price": 399.90,
                        "marketPrice": 599,
                        "availability": "in_stock",
                    }
                ],
                "page": 1,
                "pageSize": 1,
                "total": 1,
            },
        )

    client = GowuDemoPriceClient(
        "sandbox-key",
        client=httpx.Client(transport=httpx.MockTransport(respond)),
    )

    result = client.search("降噪耳机", limit=1)

    assert result[0].price_minor == 39990
    assert result[0].verification == "THIRD_PARTY_DEMO"
    assert result[0].source_ref == "gowu-sandbox:external-1"


def test_gowu_sandbox_invalid_payload_fails_without_fixture_fallback() -> None:
    client = GowuDemoPriceClient(
        "sandbox-key",
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"items": [{}]}))
        ),
    )

    with pytest.raises(ConnectorError) as error:
        client.search("降噪耳机")

    assert error.value.kind is ConnectorErrorKind.INVALID_RESPONSE
    assert "sandbox-key" not in str(error.value)


def test_discovery_adapter_cannot_promote_price_or_link_without_requote() -> None:
    now = datetime(2026, 8, 26, tzinfo=UTC)
    offer = Offer(uuid4(), uuid4(), uuid4(), "discovery-1")
    connector = DiscoveryConnector(
        "search",
        offer,
        "https://item.example/p/1",
        frozenset({"item.example"}),
        now,
        now + timedelta(hours=1),
    )
    quote = connector.quote(offer.id)
    assert quote.price is None
    assert quote.verification is VerificationLevel.DISCOVERY_ONLY
    assert connector.requote(quote).outcome is RequoteOutcome.UNVERIFIED
    assert connector.requote(quote).deep_link_allowed is False
