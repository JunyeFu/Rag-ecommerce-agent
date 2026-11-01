"""Read-only Gowu sandbox prices with an explicit weak-authority evidence level."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx

from .spi import ConnectorError, ConnectorErrorKind


@dataclass(frozen=True, slots=True)
class ThirdPartyDemoPrice:
    external_product_id: str
    title: str
    category: str | None
    brand: str | None
    price_minor: int
    market_price_minor: int | None
    availability: str
    collected_at: datetime
    expires_at: datetime
    source_ref: str
    verification: str = "THIRD_PARTY_DEMO"


class GowuDemoPriceClient:
    """Small, read-only client for the public Gowu sandbox catalog."""

    BASE_URL = "https://api.gowu-ai.com"

    def __init__(self, app_key: str, *, client: httpx.Client | None = None) -> None:
        normalized = app_key.strip()
        if not normalized:
            raise ValueError("GOWU_DEMO_APP_KEY is required")
        self._app_key = normalized
        self._client = client or httpx.Client(base_url=self.BASE_URL, timeout=5.0)

    def search(self, keyword: str, *, limit: int = 3) -> tuple[ThirdPartyDemoPrice, ...]:
        query = keyword.strip()
        if not query or not 1 <= limit <= 10:
            raise ValueError("keyword is required and limit must be in 1..10")
        try:
            response = self._client.get(
                f"{self.BASE_URL}/open/lm/products",
                params={"keyword": query, "page": 1, "pageSize": limit},
                headers={"x-app-key": self._app_key, "x-open-user": "rag-commerce-demo"},
            )
        except httpx.TimeoutException as exc:
            raise ConnectorError(
                ConnectorErrorKind.TIMEOUT,
                "Gowu demo price request timed out",
                retryable=False,
            ) from exc
        except httpx.HTTPError as exc:
            raise ConnectorError(
                ConnectorErrorKind.UPSTREAM_UNAVAILABLE,
                "Gowu demo price request failed",
                retryable=False,
            ) from exc
        if response.status_code == 429:
            raise ConnectorError(
                ConnectorErrorKind.RATE_LIMITED,
                "Gowu demo price quota is unavailable",
                retryable=False,
            )
        if response.status_code in {401, 403}:
            raise ConnectorError(
                ConnectorErrorKind.AUTHORIZATION_REQUIRED,
                "Gowu demo price authorization was rejected",
                retryable=False,
            )
        if not response.is_success:
            raise ConnectorError(
                ConnectorErrorKind.UPSTREAM_UNAVAILABLE,
                f"Gowu demo price request returned HTTP {response.status_code}",
                retryable=False,
            )
        try:
            payload = response.json()
            items = payload["items"]
            if not isinstance(items, list):
                raise TypeError("items must be a list")
            now = datetime.now(UTC)
            return tuple(self._parse_item(item, now) for item in items)
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise ConnectorError(
                ConnectorErrorKind.INVALID_RESPONSE,
                "Gowu demo price response is invalid",
                retryable=False,
            ) from exc

    @staticmethod
    def _parse_item(item: object, collected_at: datetime) -> ThirdPartyDemoPrice:
        if not isinstance(item, dict):
            raise TypeError("item must be an object")
        external_id = str(item["id"]).strip()
        title = str(item["title"]).strip()
        if not external_id or not title:
            raise ValueError("id and title are required")
        return ThirdPartyDemoPrice(
            external_product_id=external_id,
            title=title,
            category=_optional_text(item.get("category")),
            brand=_optional_text(item.get("brand")),
            price_minor=_minor_units(item["price"]),
            market_price_minor=(
                _minor_units(item["marketPrice"]) if item.get("marketPrice") is not None else None
            ),
            availability=str(item.get("availability", "unknown")),
            collected_at=collected_at,
            expires_at=collected_at + timedelta(minutes=5),
            source_ref=f"gowu-sandbox:{external_id}",
        )


def _minor_units(value: object) -> int:
    if isinstance(value, bool):
        raise TypeError("price must be numeric")
    amount = Decimal(str(value)) * 100
    if amount != amount.to_integral_value() or amount < 0:
        raise ValueError("price must be a non-negative CNY amount with at most two decimals")
    return int(amount)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
