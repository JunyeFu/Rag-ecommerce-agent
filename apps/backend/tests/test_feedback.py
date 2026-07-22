import pytest
pytestmark = pytest.mark.unit

"""
Feedback schema tests
"""
import pytest
from app.schemas.feedback import FeedbackCreate


def test_feedback_create_with_rating():
    fb = FeedbackCreate(
        session_id="550e8400-e29b-41d4-a716-446655440000",
        rating=1,
        reason="准确",
    )
    assert fb.rating == 1
    assert fb.reason == "准确"
    assert fb.product_id is None

def test_feedback_create_dislike():
    fb = FeedbackCreate(
        session_id="550e8400-e29b-41d4-a716-446655440000",
        product_id="550e8400-e29b-41d4-a716-446655440001",
        rating=-1,
        reason="不准确",
    )
    assert fb.rating == -1
    assert fb.product_id is not None
    assert fb.reason == "不准确"

def test_feedback_reason_optional():
    fb = FeedbackCreate(
        session_id="550e8400-e29b-41d4-a716-446655440000",
        rating=1,
    )
    assert fb.reason is None
