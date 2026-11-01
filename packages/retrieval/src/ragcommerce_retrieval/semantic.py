"""Provider-backed hybrid retrieval that never embeds untrusted descriptions."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path
from typing import Protocol
from uuid import NAMESPACE_URL, uuid4, uuid5

import numpy as np
import onnxruntime as ort
from qdrant_client import QdrantClient, models
from tokenizers import Tokenizer

from .normalization import normalize_brand
from .search import HybridIndex, SearchDocument, SearchHit, tokenize


class EmbeddingProvider(Protocol):
    async def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class EmbeddingTransport(Protocol):
    async def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> tuple[int, dict[str, object]]: ...


class EmbeddingProviderError(RuntimeError):
    pass


class DeterministicEmbeddingProvider:
    """Stable development-only embedding used by CI and the local demo."""

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    def vector(self, text: str) -> tuple[float, ...]:
        values = [0.0] * self.dimensions
        for token in tokenize(text):
            digest = hashlib.sha256(token.encode()).digest()
            values[int.from_bytes(digest[:2], "big") % self.dimensions] += 1.0
        return tuple(values)

    async def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("embedding input must be non-empty")
        return tuple(self.vector(text) for text in texts)


class LocalOnnxEmbeddingProvider:
    """CPU-only local BGE embeddings loaded from a pinned Hugging Face snapshot."""

    QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："  # noqa: RUF001

    def __init__(self, model_dir: Path, *, max_length: int = 512) -> None:
        self.model_dir = model_dir
        self.tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=max_length)
        self.tokenizer.enable_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(model_dir / "model_optimized.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )

    async def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("embedding input must be non-empty")
        return await asyncio.to_thread(self._embed_sync, texts)

    async def embed_query(self, text: str) -> tuple[float, ...]:
        return (await self.embed((f"{self.QUERY_INSTRUCTION}{text}",)))[0]

    def _embed_sync(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        encoded = self.tokenizer.encode_batch(list(texts))
        inputs = {
            "input_ids": np.asarray([item.ids for item in encoded], dtype=np.int64),
            "attention_mask": np.asarray([item.attention_mask for item in encoded], dtype=np.int64),
            "token_type_ids": np.asarray([item.type_ids for item in encoded], dtype=np.int64),
        }
        hidden = self.session.run(["last_hidden_state"], inputs)[0][:, 0, :]
        norms = np.linalg.norm(hidden, axis=1, keepdims=True)
        normalized = hidden / np.maximum(norms, np.finfo(hidden.dtype).eps)
        return tuple(tuple(float(value) for value in row) for row in normalized)


class _UrllibEmbeddingTransport:
    async def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> tuple[int, dict[str, object]]:
        return await asyncio.to_thread(self._post, url, headers, payload, timeout_seconds)

    @staticmethod
    def _post(url, headers, payload, timeout_seconds):
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, {}
        except (urllib.error.URLError, TimeoutError) as exc:
            raise EmbeddingProviderError(type(exc).__name__) from exc


class OpenAICompatibleEmbeddingProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout_seconds: float = 30.0,
        transport: EmbeddingTransport | None = None,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("embedding base_url must use HTTPS")
        if not api_key or not model:
            raise ValueError("embedding api_key and model are required")
        self.url = f"{base_url.rstrip('/')}/embeddings"
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport or _UrllibEmbeddingTransport()

    async def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("embedding input must be non-empty")
        status, response = await self.transport.post_json(
            self.url,
            {"Authorization": f"Bearer {self.api_key}"},
            {"model": self.model, "input": list(texts)},
            self.timeout_seconds,
        )
        if status < 200 or status >= 300:
            raise EmbeddingProviderError(f"embedding provider returned HTTP {status}")
        try:
            rows = sorted(response["data"], key=lambda item: item["index"])  # type: ignore[arg-type,index]
            vectors = tuple(tuple(float(value) for value in row["embedding"]) for row in rows)
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingProviderError("embedding provider returned an invalid payload") from exc
        if (
            len(vectors) != len(texts)
            or not vectors
            or any(len(value) != len(vectors[0]) for value in vectors)
        ):
            raise EmbeddingProviderError("embedding provider returned invalid dimensions")
        return vectors


async def _embed_query(provider: EmbeddingProvider, query: str) -> tuple[float, ...]:
    query_method = getattr(provider, "embed_query", None)
    if query_method is not None:
        return await query_method(query)
    return (await provider.embed((query,)))[0]


def _semantic_text(document: SearchDocument) -> str:
    values = [
        document.title,
        document.category or "",
        normalize_brand(document.brand or ""),
        *[str(value) for _, value in sorted(document.attributes.items())],
        *document.scenarios,
        *document.highlights,
    ]
    return " ".join(value for value in values if value)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("embedding dimensions must be equal and non-empty")
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    return (
        0.0
        if denominator == 0
        else sum(a * b for a, b in zip(left, right, strict=True)) / denominator
    )


class HybridSemanticIndex:
    def __init__(
        self,
        documents: tuple[SearchDocument, ...],
        vectors: dict[str, tuple[float, ...]],
        provider: EmbeddingProvider,
    ) -> None:
        self.documents = documents
        self.by_id = {document.seed_id: document for document in documents}
        self.lexical = HybridIndex(documents)
        self.vectors = vectors
        self.provider = provider

    @classmethod
    async def build(
        cls, documents: tuple[SearchDocument, ...], provider: EmbeddingProvider
    ) -> HybridSemanticIndex:
        normalized = tuple(
            replace(document, brand=normalize_brand(document.brand or "") or None)
            for document in documents
        )
        embedded = await provider.embed(tuple(_semantic_text(document) for document in normalized))
        if len(embedded) != len(normalized):
            raise ValueError("embedding provider returned the wrong vector count")
        return cls(
            normalized,
            {
                document.seed_id: vector
                for document, vector in zip(normalized, embedded, strict=True)
            },
            provider,
        )

    async def search(
        self,
        query: str,
        limit: int = 10,
        constraints: dict[str, object] | None = None,
    ) -> tuple[SearchHit, ...]:
        query_vector = await _embed_query(self.provider, query)
        return self.search_with_vector(query, query_vector, limit, constraints)

    def search_with_vector(
        self,
        query: str,
        query_vector: tuple[float, ...],
        limit: int = 10,
        constraints: dict[str, object] | None = None,
    ) -> tuple[SearchHit, ...]:
        normalized_constraints = dict(constraints or {})
        if "brand_candidates" in normalized_constraints:
            normalized_constraints["brand_candidates"] = [
                normalize_brand(str(value))
                for value in normalized_constraints["brand_candidates"]  # type: ignore[union-attr]
            ]
        lexical = self.lexical.search(query, len(self.documents), normalized_constraints)
        allowed = {hit.document.seed_id for hit in lexical}
        if not normalized_constraints:
            allowed = set(self.by_id)
        vector_rank = sorted(
            allowed,
            key=lambda seed_id: (-_cosine(query_vector, self.vectors[seed_id]), seed_id),
        )
        lexical_rank = [hit.document.seed_id for hit in lexical]
        scores: dict[str, float] = {seed_id: 0.0 for seed_id in allowed}
        for rank, seed_id in enumerate(lexical_rank, 1):
            scores[seed_id] += 1.0 / (60 + rank)
        for rank, seed_id in enumerate(vector_rank, 1):
            scores[seed_id] += 1.0 / (60 + rank)
        query_tokens = set(tokenize(query))
        ranked = sorted(scores, key=lambda seed_id: (-scores[seed_id], seed_id))[:limit]
        return tuple(
            SearchHit(
                self.by_id[seed_id],
                scores[seed_id],
                tuple(sorted(query_tokens & set(tokenize(self.by_id[seed_id].searchable_text)))),
            )
            for seed_id in ranked
        )


class QdrantHybridSemanticIndex:
    """Real embedding + Qdrant vector rank fused with the local BM25 rank."""

    def __init__(
        self,
        documents: tuple[SearchDocument, ...],
        provider: EmbeddingProvider,
        client: QdrantClient,
        collection: str,
    ) -> None:
        self.documents = tuple(
            replace(document, brand=normalize_brand(document.brand or "") or None)
            for document in documents
        )
        self.by_id = {document.seed_id: document for document in self.documents}
        self.lexical = HybridIndex(self.documents)
        self.provider = provider
        self.client = client
        self.collection = collection
        self._ready = False
        self._build_lock = asyncio.Lock()

    async def _ensure_index(self) -> None:
        if self._ready:
            return
        async with self._build_lock:
            if self._ready:
                return
            exists = await asyncio.to_thread(self.client.collection_exists, self.collection)
            if not exists:
                raise RuntimeError(
                    "retrieval index is missing; run scripts/build_retrieval_index.py"
                )
            self._ready = True

    async def build_index(self) -> str:
        """Build a new collection, then atomically point the read alias at it."""
        vectors = await self.provider.embed(
            tuple(_semantic_text(document) for document in self.documents)
        )
        target = f"{self.collection}--{uuid4().hex}"

        def build() -> None:
            aliases = {item.alias_name for item in self.client.get_aliases().aliases}
            if self.client.collection_exists(self.collection) and self.collection not in aliases:
                raise RuntimeError(
                    "index name is an existing physical collection; choose a new alias"
                )
            self.client.create_collection(
                target,
                vectors_config=models.VectorParams(
                    size=len(vectors[0]), distance=models.Distance.COSINE
                ),
            )
            try:
                self.client.upsert(
                    target,
                    [
                        models.PointStruct(
                            id=str(uuid5(NAMESPACE_URL, document.seed_id)),
                            vector=list(vector),
                            payload={
                                "seed_id": document.seed_id,
                                "source_path": document.evidence.source_path,
                                "source_sha256": document.evidence.source_sha256,
                            },
                        )
                        for document, vector in zip(self.documents, vectors, strict=True)
                    ],
                    wait=True,
                )
                operations = []
                if self.collection in aliases:
                    operations.append(
                        models.DeleteAliasOperation(
                            delete_alias=models.DeleteAlias(alias_name=self.collection)
                        )
                    )
                operations.append(
                    models.CreateAliasOperation(
                        create_alias=models.CreateAlias(
                            collection_name=target, alias_name=self.collection
                        )
                    )
                )
                self.client.update_collection_aliases(change_aliases_operations=operations)
            except Exception:
                self.client.delete_collection(target)
                raise

        await asyncio.to_thread(build)
        self._ready = True
        return target

    async def search(
        self,
        query: str,
        limit: int = 10,
        constraints: dict[str, object] | None = None,
    ) -> tuple[SearchHit, ...]:
        await self._ensure_index()
        query_vector = await _embed_query(self.provider, query)
        normalized_constraints = dict(constraints or {})
        if "brand_candidates" in normalized_constraints:
            normalized_constraints["brand_candidates"] = [
                normalize_brand(str(value))
                for value in normalized_constraints["brand_candidates"]  # type: ignore[union-attr]
            ]
        lexical = self.lexical.search(query, len(self.documents), normalized_constraints)
        allowed = {hit.document.seed_id for hit in lexical}
        if not normalized_constraints:
            allowed = set(self.by_id)

        def vector_ids() -> list[str]:
            response = self.client.query_points(
                self.collection,
                query=list(query_vector),
                limit=len(self.documents),
                with_payload=True,
            )
            return [
                str(point.payload["seed_id"])
                for point in response.points
                if point.payload and str(point.payload.get("seed_id")) in allowed
            ]

        vector_rank = await asyncio.to_thread(vector_ids)
        lexical_rank = [hit.document.seed_id for hit in lexical]
        scores: dict[str, float] = {seed_id: 0.0 for seed_id in allowed}
        for rank, seed_id in enumerate(lexical_rank, 1):
            scores[seed_id] += 1.0 / (60 + rank)
        for rank, seed_id in enumerate(vector_rank, 1):
            scores[seed_id] += 1.0 / (60 + rank)
        query_tokens = set(tokenize(query))
        ranked = sorted(scores, key=lambda seed_id: (-scores[seed_id], seed_id))[:limit]
        return tuple(
            SearchHit(
                self.by_id[seed_id],
                scores[seed_id],
                tuple(sorted(query_tokens & set(tokenize(self.by_id[seed_id].searchable_text)))),
            )
            for seed_id in ranked
        )
