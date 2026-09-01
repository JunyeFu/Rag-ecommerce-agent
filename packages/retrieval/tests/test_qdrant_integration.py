import os
from pathlib import Path

import pytest
from qdrant_client import QdrantClient
from ragcommerce_retrieval import (
    OutboxEvent,
    ProjectionOperation,
    QdrantProjection,
    load_demo_documents,
)

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3]


def test_qdrant_update_delete_and_full_rebuild() -> None:
    url = os.environ.get("QDRANT_TEST_URL")
    if not url:
        pytest.skip("QDRANT_TEST_URL is required")
    documents = load_demo_documents(ROOT / "data/demo/catalog.v3.jsonl")
    first, second = documents[:2]
    events = (
        OutboxEvent(1, "q1", first.seed_id, ProjectionOperation.UPSERT, first),
        OutboxEvent(2, "q2", second.seed_id, ProjectionOperation.UPSERT, second),
        OutboxEvent(3, "q3", first.seed_id, ProjectionOperation.DELETE, None),
    )
    client = QdrantClient(url=url, timeout=5)
    projection = QdrantProjection(client, "rag_v3_retrieval_test", "fixture-v3")
    try:
        projection.rebuild(events)
        assert projection.seed_ids() == (second.seed_id,)
        projection.rebuild(events[:2])
        assert projection.seed_ids() == tuple(sorted((first.seed_id, second.seed_id)))
    finally:
        if client.collection_exists("rag_v3_retrieval_test"):
            client.delete_collection("rag_v3_retrieval_test")
        client.close()
