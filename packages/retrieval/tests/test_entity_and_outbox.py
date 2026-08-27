from ragcommerce_retrieval import (
    EntityCandidate,
    EntityDecision,
    EntityResolver,
    EvidenceBundle,
    InMemoryProjection,
    OutboxEvent,
    OutboxProjector,
    ProjectionOperation,
    SearchDocument,
)


def document(seed_id: str, title: str) -> SearchDocument:
    return SearchDocument(
        seed_id,
        title,
        None,
        "耳机",
        {},
        (),
        EvidenceBundle("fixture", "0" * 64, seed_id, ("title",)),
    )


def test_projection_update_delete_replay_is_idempotent_and_rebuildable() -> None:
    events = (
        OutboxEvent(1, "e1", "p1", ProjectionOperation.UPSERT, document("p1", "old")),
        OutboxEvent(2, "e2", "p1", ProjectionOperation.UPSERT, document("p1", "new")),
        OutboxEvent(3, "e3", "p1", ProjectionOperation.DELETE, None),
        OutboxEvent(4, "e4", "p2", ProjectionOperation.UPSERT, document("p2", "kept")),
    )
    projection = InMemoryProjection()
    projector = OutboxProjector(projection)
    projector.rebuild(events)
    assert list(projection.documents) == ["p2"]
    assert projector.apply(events[-1]) is False
    projector.rebuild(events)
    assert projection.documents["p2"].title == "kept"


def test_identifier_conflicts_never_merge_on_semantic_similarity() -> None:
    resolver = EntityResolver()
    left = EntityCandidate("a", "6900000000001", None, "Phone X", {"storage": "128GB"})
    right = EntityCandidate("b", "6900000000002", None, "Phone X", {"storage": "128GB"})
    assert resolver.compare(left, right)[0] is EntityDecision.DISTINCT
    missing = EntityCandidate("c", None, None, "Phone X", {"storage": "256GB"})
    assert resolver.compare(left, missing)[0] is not EntityDecision.MATCH
