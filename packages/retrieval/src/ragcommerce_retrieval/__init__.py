"""Rebuildable, evidence-carrying product retrieval."""

from .dataset import load_seed_documents
from .entity import EntityCandidate, EntityDecision, EntityResolver
from .metrics import RetrievalMetrics, ndcg, recall
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

__all__ = [
    "EntityCandidate",
    "EntityDecision",
    "EntityResolver",
    "EvidenceBundle",
    "HybridIndex",
    "InMemoryProjection",
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
    "load_seed_documents",
    "ndcg",
    "recall",
]
