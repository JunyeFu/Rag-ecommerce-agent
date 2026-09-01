"""Provider-backed hybrid retrieval that never embeds untrusted descriptions."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import urllib.error
import urllib.request
from dataclasses import replace
from typing import Protocol

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


def _semantic_text(document: SearchDocument) -> str:
    values = [
        document.title,
        document.category or "",
        normalize_brand(document.brand or ""),
        *[str(value) for _, value in sorted(document.attributes.items())],
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
        query_vector = (await self.provider.embed((query,)))[0]
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
