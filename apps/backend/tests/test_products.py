import pytest
pytestmark = pytest.mark.unit

"""
Products schema tests
"""
import pytest
from app.schemas.product import ProductCard, ProductRecord


def test_product_card_fields():
    p = ProductCard(
        product_id="550e8400-e29b-41d4-a716-446655440000",
        title="Test Product",
        price=99.0,
        category="Test",
        brand="TestBrand",
        rating=4.5,
    )
    data = p.model_dump()
    assert data["product_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert data["title"] == "Test Product"
    assert data["price"] == 99.0
    assert data.get("match_score") is None

def test_product_record_coerces_id():
    p = ProductRecord(
        id="550e8400-e29b-41d4-a716-446655440000",
        title="Test",
        category="Test",
        price=99.0,
    )
    assert p.product_id == "550e8400-e29b-41d4-a716-446655440000"

def test_product_filter_page_bounds():
    from app.schemas.product import ProductFilter
    f = ProductFilter(page=1, size=20)
    assert f.page == 1
    assert f.size == 20
