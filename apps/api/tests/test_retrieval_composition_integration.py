"""Worker lanes must not load eight copies of the same pinned BGE model."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from qdrant_client import QdrantClient
from ragcommerce_api.retrieval_config import configured_retrieval

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3]


def test_eight_lanes_share_local_model_but_read_index_independently(monkeypatch):
    url = os.environ.get("QDRANT_TEST_URL")
    collection = os.environ.get("LOCAL_EMBEDDING_TEST_COLLECTION")
    if not url or not collection:
        pytest.skip("QDRANT_TEST_URL and LOCAL_EMBEDDING_TEST_COLLECTION are required")
    monkeypatch.setenv("RETRIEVAL_MODE", "local")
    monkeypatch.setenv("QDRANT_URL", url)
    monkeypatch.setenv("QDRANT_COLLECTION", collection)
    client = QdrantClient(url=url)
    try:
        before = client.count(collection, exact=True).count
        with ThreadPoolExecutor(max_workers=8) as pool:
            indexes = list(
                pool.map(
                    lambda _: configured_retrieval(ROOT / "data/demo/catalog.v3.jsonl"), range(8)
                )
            )
            try:
                assert len({id(index.provider) for index in indexes}) == 1

                def search(index):
                    hits = asyncio.run(index.search("预算1000元的通勤降噪耳机"))
                    return [hit.document.seed_id for hit in hits]

                results = list(pool.map(search, indexes))
                assert results[0]
                assert all(result == results[0] for result in results)
            finally:
                for index in indexes:
                    index.client.close()
        assert client.count(collection, exact=True).count == before == 60
    finally:
        client.close()
