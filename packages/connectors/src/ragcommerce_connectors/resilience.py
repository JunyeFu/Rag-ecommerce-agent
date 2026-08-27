"""Deterministic retry and circuit state; transports own actual waiting."""

from dataclasses import dataclass
from enum import StrEnum

from .spi import ConnectorErrorKind


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_ms: int = 100
    max_delay_ms: int = 1000

    def delays(self, kind: ConnectorErrorKind) -> tuple[int, ...]:
        if kind not in {
            ConnectorErrorKind.RATE_LIMITED,
            ConnectorErrorKind.TIMEOUT,
            ConnectorErrorKind.UPSTREAM_UNAVAILABLE,
        }:
            return ()
        return tuple(
            min(self.base_delay_ms * (2**attempt), self.max_delay_ms)
            for attempt in range(self.max_attempts - 1)
        )


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_ms: int = 30_000) -> None:
        self.failure_threshold, self.cooldown_ms = failure_threshold, cooldown_ms
        self.failures, self.opened_at_ms = 0, None

    def state_at(self, now_ms: int) -> CircuitState:
        if self.opened_at_ms is None:
            return CircuitState.CLOSED
        return (
            CircuitState.HALF_OPEN
            if now_ms - self.opened_at_ms >= self.cooldown_ms
            else CircuitState.OPEN
        )

    def record_failure(self, now_ms: int) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at_ms = now_ms

    def record_success(self) -> None:
        self.failures, self.opened_at_ms = 0, None
