"""Fail-closed marketplace connector contracts and deterministic fixtures."""

from .discovery import DiscoveryConnector
from .fixture import FixtureConnector, load_fixture_connectors
from .resilience import CircuitBreaker, CircuitState, RetryPolicy
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
    "CircuitBreaker",
    "CircuitState",
    "ConnectorCapability",
    "ConnectorError",
    "ConnectorErrorKind",
    "DiscoveryConnector",
    "FixtureConnector",
    "OfferConnector",
    "RequoteOutcome",
    "RequoteResult",
    "RetryPolicy",
    "SafeLinkPolicy",
    "load_fixture_connectors",
]
