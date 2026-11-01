"""Shared retrieval composition for the durable API and worker processes."""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path
from threading import Lock

from huggingface_hub import snapshot_download
from qdrant_client import QdrantClient
from ragcommerce_retrieval import (
    LocalOnnxEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    QdrantHybridSemanticIndex,
    load_demo_documents,
)

_local_model_lock = Lock()


@cache
def _local_model(model_path: str) -> LocalOnnxEmbeddingProvider:
    return LocalOnnxEmbeddingProvider(Path(model_path))


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def configured_retrieval(catalog_path: Path):
    mode = os.environ.get("RETRIEVAL_MODE", "fixture").strip().lower()
    if mode == "fixture":
        return None
    if mode == "local":
        model_path = snapshot_download(
            repo_id=os.environ.get("LOCAL_EMBEDDING_MODEL", "Qdrant/bge-small-zh-v1.5").strip(),
            revision=os.environ.get(
                "LOCAL_EMBEDDING_REVISION",
                "46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59",
            ).strip(),
            local_files_only=True,
        )
        # Worker lanes retain separate clients/indexes, not eight ONNX sessions.
        # Serialize initial construction: functools.cache alone is not single-flight.
        with _local_model_lock:
            provider = _local_model(model_path)
        default_collection = "rag-commerce-v3-local-bge-current"
    elif mode == "real":
        provider = OpenAICompatibleEmbeddingProvider(
            _required("EMBEDDING_BASE_URL"),
            _required("EMBEDDING_API_KEY"),
            _required("EMBEDDING_MODEL"),
        )
        default_collection = "rag-commerce-v3-real-current"
    else:
        raise RuntimeError("RETRIEVAL_MODE must be fixture, local, or real")
    return QdrantHybridSemanticIndex(
        load_demo_documents(catalog_path),
        provider,
        QdrantClient(url=_required("QDRANT_URL")),
        os.environ.get("QDRANT_COLLECTION", default_collection).strip(),
    )


__all__ = ["configured_retrieval"]
