"""Idempotent projection replay; PostgreSQL event persistence composes outside."""

from dataclasses import dataclass
from enum import StrEnum

from .search import SearchDocument


class ProjectionOperation(StrEnum):
    UPSERT = "UPSERT"
    DELETE = "DELETE"


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    sequence: int
    event_id: str
    aggregate_id: str
    operation: ProjectionOperation
    document: SearchDocument | None


class InMemoryProjection:
    def __init__(self) -> None:
        self.documents: dict[str, SearchDocument] = {}

    def clear(self) -> None:
        self.documents.clear()

    def apply(self, event: OutboxEvent) -> None:
        if event.operation is ProjectionOperation.DELETE:
            self.documents.pop(event.aggregate_id, None)
        elif event.document is None:
            raise ValueError("upsert requires document")
        else:
            self.documents[event.aggregate_id] = event.document


class OutboxProjector:
    def __init__(self, projection: InMemoryProjection) -> None:
        self.projection = projection
        self.applied_event_ids: set[str] = set()
        self.last_sequence = -1

    def apply(self, event: OutboxEvent) -> bool:
        if event.event_id in self.applied_event_ids:
            return False
        if event.sequence <= self.last_sequence:
            raise ValueError("outbox sequence regression")
        self.projection.apply(event)
        self.applied_event_ids.add(event.event_id)
        self.last_sequence = event.sequence
        return True

    def rebuild(self, events: tuple[OutboxEvent, ...]) -> None:
        self.projection.clear()
        self.applied_event_ids.clear()
        self.last_sequence = -1
        for event in sorted(events, key=lambda item: item.sequence):
            self.apply(event)
