from pathlib import Path

from ragcommerce_retrieval import (
    HybridIndex,
    TrustLevel,
    assemble_evidence,
    load_seed_documents,
    ndcg,
    recall,
)

ROOT = Path(__file__).resolve().parents[3]


def test_every_hit_carries_seed_provenance_and_not_price() -> None:
    index = HybridIndex(load_seed_documents(ROOT / "data/seed/catalog.v1.jsonl"))
    hits = index.search("降噪耳机", constraints={"category": "耳机"})
    assert hits
    for hit in hits:
        assert len(hit.document.evidence.source_sha256) == 64
        assert "price" not in hit.document.evidence.fields


def test_binary_metrics() -> None:
    relevant = {"a", "b"}
    assert recall(["a", "c", "b"], relevant) == 1.0
    assert 0.9 < ndcg(["a", "b", "c"], relevant) <= 1.0


def test_external_prompt_text_remains_untrusted_content_not_instructions() -> None:
    document = load_seed_documents(ROOT / "data/seed/catalog.v1.jsonl")[0]
    evidence = assemble_evidence(HybridIndex((document,)).search(document.title, 1))[0]
    assert evidence.evidence.trust is TrustLevel.DEVELOPMENT_SEED_UNTRUSTED
    assert "instructions" not in evidence.cited_facts
    assert evidence.untrusted_content == document.untrusted_description
