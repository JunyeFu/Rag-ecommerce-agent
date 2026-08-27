"""Development identity and bounded process-local rate policy."""

from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic
from uuid import UUID


class RateLimitExceeded(RuntimeError):
    pass


def parse_development_user(value: str | None) -> UUID:
    if value is None:
        raise ValueError("X-User-ID is required")
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError("X-User-ID must be a UUID") from exc


class SlidingWindowLimiter:
    def __init__(self, limit: int = 60, window_seconds: float = 60.0) -> None:
        if limit < 1 or window_seconds <= 0:
            raise ValueError("rate limit settings must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self.history: dict[UUID, deque[float]] = defaultdict(deque)

    def check(self, user_id: UUID) -> None:
        now = monotonic()
        entries = self.history[user_id]
        while entries and entries[0] <= now - self.window_seconds:
            entries.popleft()
        if len(entries) >= self.limit:
            raise RateLimitExceeded("request rate exceeded")
        entries.append(now)
