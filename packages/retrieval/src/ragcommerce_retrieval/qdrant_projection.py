"""Qdrant projection adapter using a deterministic non-production test vector."""

import hashlib
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from .outbox import OutboxEvent, ProjectionOperation


def fixture_vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    values = [(digest[index] - 127.5) / 127.5 for index in range(8)]
    norm = sum(value * value for value in values) ** 0.5
    return [value / norm for value in values]


class QdrantProjection:
    def __init__(self, client: QdrantClient, collection: str, index_version: str) -> None:
        self.client, self.collection, self.index_version = client, collection, index_version

    def rebuild(self, events: tuple[OutboxEvent, ...]) -> None:
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            self.collection,
            vectors_config=models.VectorParams(size=8, distance=models.Distance.COSINE),
        )
        for event in sorted(events, key=lambda item: item.sequence):
            self.apply(event)

    def apply(self, event: OutboxEvent) -> None:
        point_id = str(uuid5(NAMESPACE_URL, event.aggregate_id))
        if event.operation is ProjectionOperation.DELETE:
            self.client.delete(self.collection, models.PointIdsList(points=[point_id]), wait=True)
            return
        if event.document is None:
            raise ValueError("upsert requires document")
        document = event.document
        self.client.upsert(
            self.collection,
            [
                models.PointStruct(
                    id=point_id,
                    vector=fixture_vector(document.searchable_text),
                    payload={
                        "seed_id": document.seed_id,
                        "title": document.title,
                        "category": document.category,
                        "brand": document.brand,
                        "index_version": self.index_version,
                        "source_path": document.evidence.source_path,
                        "source_sha256": document.evidence.source_sha256,
                    },
                )
            ],
            wait=True,
        )

    def seed_ids(self) -> tuple[str, ...]:
        values: list[str] = []
        offset = None
        while True:
            points, offset = self.client.scroll(
                self.collection, limit=128, offset=offset, with_payload=True, with_vectors=False
            )
            values.extend(str(point.payload["seed_id"]) for point in points)
            if offset is None:
                break
        return tuple(sorted(values))
