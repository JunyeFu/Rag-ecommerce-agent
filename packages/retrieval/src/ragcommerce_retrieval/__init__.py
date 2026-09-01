"""Rebuildable, evidence-carrying product retrieval."""

from .dataset import load_demo_documents, load_seed_documents
from .entity import EntityCandidate, EntityDecision, EntityResolver
from .metrics import RetrievalMetrics, ndcg, recall
from .normalization import normalize_brand
from .outbox import InMemoryProjection, OutboxEvent, OutboxProjector, ProjectionOperation
from .qdrant_projection import QdrantProjection, fixture_vector
from .search import (
    EvidenceBundle,
    HybridIndex,
    RetrievedEvidence,
    SearchDocument,
    SearchHit,
    TrustLevel,
    assemble_evidence,
)
from .semantic import (
    DeterministicEmbeddingProvider,
    EmbeddingProvider,
    EmbeddingProviderError,
    HybridSemanticIndex,
    OpenAICompatibleEmbeddingProvider,
)

__all__ = [
    "DeterministicEmbeddingProvider",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "EntityCandidate",
    "EntityDecision",
    "EntityResolver",
    "EvidenceBundle",
    "HybridIndex",
    "HybridSemanticIndex",
    "InMemoryProjection",
    "OpenAICompatibleEmbeddingProvider",
    "OutboxEvent",
    "OutboxProjector",
    "ProjectionOperation",
    "QdrantProjection",
    "RetrievalMetrics",
    "RetrievedEvidence",
    "SearchDocument",
    "SearchHit",
    "TrustLevel",
    "assemble_evidence",
    "fixture_vector",
    "load_demo_documents",
    "load_seed_documents",
    "ndcg",
    "normalize_brand",
    "recall",
]
