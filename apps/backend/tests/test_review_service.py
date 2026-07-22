"""评价服务单元测试 - CRUD + 平均评分 + 匿名评价"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.review_service import (
    create_review,
    get_reviews_by_product,
    get_reviews_by_user,
    get_review,
)


def _make_result(scalars=None, scalar=None, scalar_one_or_none=None, rowcount=0):
    result = MagicMock()
    result.scalars.return_value.all.return_value = scalars or []
    result.scalar.return_value = scalar
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.rowcount = rowcount
    return result



@pytest.mark.unit
class TestCreateReview:
    """create_review - 创建评价"""

    @pytest.mark.asyncio
    async def test_create_normal_review(self, mock_db):
        result = await create_review(
            mock_db, product_id="p1", user_id="u1", nickname="张三", rating=5, content="很好用"
        )
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()
        assert result.nickname == "张三"

    @pytest.mark.asyncio
    async def test_create_anonymous_review(self, mock_db):
        result = await create_review(
            mock_db, product_id="p1", user_id="u1", nickname="张三", rating=4,
            content="一般", is_anonymous=True,
        )
        assert result.nickname == "匿名用户"

    @pytest.mark.asyncio
    async def test_create_with_default_rating(self, mock_db):
        result = await create_review(mock_db, product_id="p1", user_id="u1", nickname="李四")
        assert result.rating == 5

    @pytest.mark.asyncio
    async def test_create_with_media(self, mock_db):
        result = await create_review(
            mock_db, product_id="p1", user_id="u1", nickname="王五", rating=5,
            media=b"fake_image_data",
        )
        assert result.media == b"fake_image_data"


@pytest.mark.unit
class TestGetReviewsByProduct:
    """get_reviews_by_product - 商品评价列表 + 总数 + 平均分"""

    @pytest.mark.asyncio
    async def test_returns_reviews_total_avg(self, mock_db):
        reviews = [MagicMock(rating=5), MagicMock(rating=4)]
        mock_db.execute.side_effect = [
            _make_result(scalar=2),
            _make_result(scalar=4.5),
            _make_result(scalars=reviews),
        ]
        result, total, avg = await get_reviews_by_product(mock_db, product_id="p1")
        assert result == reviews
        assert total == 2
        assert avg == 4.5

    @pytest.mark.asyncio
    async def test_empty_reviews(self, mock_db):
        mock_db.execute.side_effect = [
            _make_result(scalar=0),
            _make_result(scalar=None),
            _make_result(scalars=[]),
        ]
        result, total, avg = await get_reviews_by_product(mock_db, product_id="p1")
        assert result == []
        assert total == 0
        assert avg == 0.0

    @pytest.mark.asyncio
    async def test_avg_rounded_to_one_decimal(self, mock_db):
        mock_db.execute.side_effect = [
            _make_result(scalar=3),
            _make_result(scalar=4.333333),
            _make_result(scalars=[]),
        ]
        _, _, avg = await get_reviews_by_product(mock_db, product_id="p1")
        assert avg == 4.3

    @pytest.mark.asyncio
    async def test_pagination_applied(self, mock_db):
        mock_db.execute.side_effect = [
            _make_result(scalar=0),
            _make_result(scalar=None),
            _make_result(scalars=[]),
        ]
        await get_reviews_by_product(mock_db, product_id="p1", limit=10, offset=20)
        assert mock_db.execute.call_count == 3


@pytest.mark.unit
class TestGetReviewsByUser:
    """get_reviews_by_user - 用户评价列表"""

    @pytest.mark.asyncio
    async def test_returns_user_reviews(self, mock_db):
        reviews = [MagicMock(rating=5), MagicMock(rating=3)]
        mock_db.execute.return_value = _make_result(scalars=reviews)
        result = await get_reviews_by_user(mock_db, user_id="u1")
        assert result == reviews
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_list(self, mock_db):
        mock_db.execute.return_value = _make_result(scalars=[])
        result = await get_reviews_by_user(mock_db, user_id="u1")
        assert result == []

    @pytest.mark.asyncio
    async def test_pagination(self, mock_db):
        mock_db.execute.return_value = _make_result(scalars=[])
        await get_reviews_by_user(mock_db, user_id="u1", limit=5, offset=10)
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestGetReview:
    """get_review - 按 ID 查询评价"""

    @pytest.mark.asyncio
    async def test_valid_uuid_found(self, mock_db):
        review = MagicMock(rating=5, content="Good")
        mock_db.execute.return_value = _make_result(scalar_one_or_none=review)
        result = await get_review(mock_db, str(uuid.uuid4()))
        assert result == review

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_none(self, mock_db):
        result = await get_review(mock_db, "not-a-uuid")
        assert result is None
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self, mock_db):
        mock_db.execute.return_value = _make_result(scalar_one_or_none=None)
        result = await get_review(mock_db, str(uuid.uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_none_input_returns_none(self, mock_db):
        result = await get_review(mock_db, None)
        assert result is None
        mock_db.execute.assert_not_called()
