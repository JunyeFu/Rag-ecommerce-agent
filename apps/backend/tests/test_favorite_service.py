"""收藏服务单元测试 - CRUD + 幂等切换 + 批量删除"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.favorite_service import (
    get_favorites,
    get_favorite_count,
    is_favorited,
    toggle_favorite,
    remove_favorites,
)


def _make_result(scalars=None, scalar=None, scalar_one_or_none=None, rowcount=0):
    result = MagicMock()
    result.scalars.return_value.all.return_value = scalars or []
    result.scalar.return_value = scalar
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.rowcount = rowcount
    return result



@pytest.mark.unit
class TestGetFavorites:
    """get_favorites - 按用户查询收藏列表"""

    @pytest.mark.asyncio
    async def test_returns_favorites_list(self, mock_db):
        favs = [MagicMock(product_id="p1"), MagicMock(product_id="p2")]
        mock_db.execute.return_value = _make_result(scalars=favs)
        result = await get_favorites(mock_db, user_id="u1")
        assert result == favs
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_list_when_no_favorites(self, mock_db):
        mock_db.execute.return_value = _make_result(scalars=[])
        result = await get_favorites(mock_db, user_id="u1")
        assert result == []

    @pytest.mark.asyncio
    async def test_pagination_applied(self, mock_db):
        mock_db.execute.return_value = _make_result(scalars=[])
        await get_favorites(mock_db, user_id="u1", offset=10, limit=20)
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestGetFavoriteCount:
    """get_favorite_count - 收藏总数"""

    @pytest.mark.asyncio
    async def test_returns_count(self, mock_db):
        mock_db.execute.return_value = _make_result(scalar=5)
        result = await get_favorite_count(mock_db, user_id="u1")
        assert result == 5

    @pytest.mark.asyncio
    async def test_returns_zero_when_none(self, mock_db):
        mock_db.execute.return_value = _make_result(scalar=None)
        result = await get_favorite_count(mock_db, user_id="u1")
        assert result == 0


@pytest.mark.unit
class TestIsFavorited:
    """is_favorited - 检查是否已收藏"""

    @pytest.mark.asyncio
    async def test_already_favorited(self, mock_db):
        mock_db.execute.return_value = _make_result(scalar_one_or_none=MagicMock())
        result = await is_favorited(mock_db, user_id="u1", product_id="p1")
        assert result is True

    @pytest.mark.asyncio
    async def test_not_favorited(self, mock_db):
        mock_db.execute.return_value = _make_result(scalar_one_or_none=None)
        result = await is_favorited(mock_db, user_id="u1", product_id="p1")
        assert result is False


@pytest.mark.unit
class TestToggleFavorite:
    """toggle_favorite - 幂等切换收藏状态"""

    @pytest.mark.asyncio
    async def test_add_when_not_exists(self, mock_db):
        mock_db.execute.return_value = _make_result(scalar_one_or_none=None)
        result = await toggle_favorite(mock_db, user_id="u1", product_id="p1")
        assert result == {"action": "added", "favorited": True}
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_when_exists(self, mock_db):
        mock_db.execute.side_effect = [
            _make_result(scalar_one_or_none=MagicMock()),
            _make_result(rowcount=1),
        ]
        result = await toggle_favorite(mock_db, user_id="u1", product_id="p1")
        assert result == {"action": "removed", "favorited": False}
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_returns_correct_action(self, mock_db):
        mock_db.execute.return_value = _make_result(scalar_one_or_none=None)
        result = await toggle_favorite(mock_db, user_id="u1", product_id="p1")
        assert result["action"] == "added"
        assert result["favorited"] is True

    @pytest.mark.asyncio
    async def test_remove_returns_correct_action(self, mock_db):
        mock_db.execute.side_effect = [
            _make_result(scalar_one_or_none=MagicMock()),
            _make_result(rowcount=1),
        ]
        result = await toggle_favorite(mock_db, user_id="u1", product_id="p1")
        assert result["action"] == "removed"
        assert result["favorited"] is False


@pytest.mark.unit
class TestRemoveFavorites:
    """remove_favorites - 批量移除"""

    @pytest.mark.asyncio
    async def test_batch_remove(self, mock_db):
        mock_db.execute.return_value = _make_result(rowcount=3)
        result = await remove_favorites(mock_db, user_id="u1", product_ids=["p1", "p2", "p3"])
        assert result == 3
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_product_ids_returns_zero(self, mock_db):
        result = await remove_favorites(mock_db, user_id="u1", product_ids=[])
        assert result == 0
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_nonexistent_returns_zero(self, mock_db):
        mock_db.execute.return_value = _make_result(rowcount=0)
        result = await remove_favorites(mock_db, user_id="u1", product_ids=["p999"])
        assert result == 0
