"""Citation field tests for ProductCardEvent and _assemble_cards."""
import pytest
from app.schemas.sse_events import ProductCardEvent
from app.services.product_assembly import _assemble_cards


@pytest.mark.unit
class TestProductCardEventCitation:
    def test_default_citation_empty(self):
        card = ProductCardEvent(product_id="p1", title="Test Product")
        assert card.citation == []

    def test_citation_field_serialized(self):
        card = ProductCardEvent(
            product_id="p1",
            title="Test",
            citation=[{"source_type": "semantic_retrieval", "description": "85% match"}],
        )
        data = card.model_dump()
        assert "citation" in data
        assert len(data["citation"]) == 1
        assert data["citation"][0]["source_type"] == "semantic_retrieval"

    def test_citation_in_sse(self):
        card = ProductCardEvent(
            product_id="p1",
            title="Test",
            citation=[{"source_type": "product_highlights", "description": "test"}],
        )
        sse = card.to_sse()
        assert "citation" in sse
        assert "product_highlights" in sse


@pytest.mark.unit
class TestAssembleCardsCitation:
    def test_citation_populated_with_semantic_score(self):
        ranked = [{
            "product_id": "p1",
            "title": "Test Product",
            "price": 99.0,
            "category": "耳机",
            "semantic_score": 0.85,
            "highlights": ["降噪"],
            "match_score": 0.85,
        }]
        cards = _assemble_cards(ranked)
        assert len(cards) == 1
        assert len(cards[0]["citation"]) >= 1
        assert cards[0]["citation"][0]["source_type"] == "semantic_retrieval"

    def test_citation_populated_with_highlights(self):
        ranked = [{
            "product_id": "p1",
            "title": "Test",
            "price": 50.0,
            "semantic_score": 0.7,
            "highlights": ["feature1", "feature2"],
            "match_score": 0.7,
        }]
        cards = _assemble_cards(ranked)
        types = [c["source_type"] for c in cards[0]["citation"]]
        assert "product_highlights" in types

    def test_no_semantic_score_no_citation(self):
        ranked = [{
            "product_id": "p1",
            "title": "Test",
            "price": 50.0,
            "highlights": [],
            "match_score": 0.5,
        }]
        cards = _assemble_cards(ranked)
        assert cards[0]["citation"] == []

    def test_multiple_cards_each_have_citation(self):
        ranked = [
            {"product_id": "p1", "title": "A", "price": 10, "semantic_score": 0.9, "highlights": ["h1"]},
            {"product_id": "p2", "title": "B", "price": 20, "semantic_score": 0.8, "highlights": ["h2"]},
            {"product_id": "p3", "title": "C", "price": 30, "semantic_score": 0.7, "highlights": ["h3"]},
        ]
        cards = _assemble_cards(ranked)
        assert len(cards) == 3
        for card in cards:
            assert len(card["citation"]) >= 1
