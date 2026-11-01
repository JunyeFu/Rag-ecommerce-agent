"""Fail-closed marketplace connector contracts and deterministic fixtures."""

from .discovery import DiscoveryConnector
from .fixture import FixtureConnector, load_fixture_connectors
from .gowu_demo import GowuDemoPriceClient, ThirdPartyDemoPrice
from .security import SafeLinkPolicy
from .spi import (
    AuthorizationRequired,
    ConnectorCapability,
    ConnectorError,
    ConnectorErrorKind,
    OfferConnector,
    RequoteOutcome,
    RequoteResult,
)

__all__ = [
    "AuthorizationRequired",
    "ConnectorCapability",
    "ConnectorError",
    "ConnectorErrorKind",
    "DiscoveryConnector",
    "FixtureConnector",
    "GowuDemoPriceClient",
    "OfferConnector",
    "RequoteOutcome",
    "RequoteResult",
    "SafeLinkPolicy",
    "ThirdPartyDemoPrice",
    "load_fixture_connectors",
]
