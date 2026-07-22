"""足迹服务单元测试 - 创建/更新 + 查询 + 批量删除"""
from datetime import date
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.footprint_service import (
    record_footprint,
    get_footprints,
    get_footprint_count,
    delete_footprints,
)


def _make_result(scalars=None, scalar=None, scalar_one_or_none=None, rowcount=0):
    result = MagicMock()
    result.scalars.return_value.all.return_value = scalars or []
    result.scalar.return_value = scalar
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.rowcount = rowcount
    return result



@pytest.mark.unit
class TestRecordFootprint:
    """record_footprint - 记录浏览足迹"""

    @pytest.mark.asyncio
    async def test_create_new_footprint(self, mock_db):
        mock_db.execute.return_value = _make_result(scalar_one_or_none=None)
        result = await record_footprint(mock_db, user_id="u1", product_id="p1")
        assert result["action"] == "created"
        assert "date" in result
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_existing_footprint_different_date(self, mock_db):
        existing = MagicMock()
        existing.browse_date = date(2025, 1, 1)
        mock_db.execute.return_value = _make_result(scalar_one_or_none=existing)
        result = await record_footprint(mock_db, user_id="u1", product_id="p1")
        assert result["action"] == "updated"
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_unchanged_when_same_date(self, mock_db):
        existing = MagicMock()
        existing.browse_date = date.today()
        mock_db.execute.return_value = _make_result(scalar_one_or_none=existing)
        result = await record_footprint(mock_db, user_id="u1", product_id="p1")
        assert result["action"] == "unchanged"
        mock_db.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_is_idempotent_same_day(self, mock_db):
        existing = MagicMock()
        existing.browse_date = date.today()
        mock_db.execute.return_value = _make_result(scalar_one_or_none=existing)
        result = await record_footprint(mock_db, user_id="u1", product_id="p1")
        assert result["action"] == "unchanged"
        mock_db.add.assert_not_called()


@pytest.mark.unit
class TestGetFootprints:
    """get_footprints - 查询足迹列表"""

    @pytest.mark.asyncio
    async def test_returns_footprints(self, mock_db):
        fps = [MagicMock(product_id="p1"), MagicMock(product_id="p2")]
        mock_db.execute.return_value = _make_result(scalars=fps)
        result = await get_footprints(mock_db, user_id="u1")
        assert result == fps
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_list(self, mock_db):
        mock_db.execute.return_value = _make_result(scalars=[])
        result = await get_footprints(mock_db, user_id="u1")
        assert result == []

    @pytest.mark.asyncio
    async def test_date_range_filter(self, mock_db):
        mock_db.execute.return_value = _make_result(scalars=[])
        await get_footprints(
            mock_db,
            user_id="u1",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        )
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_pagination(self, mock_db):
        mock_db.execute.return_value = _make_result(scalars=[])
        await get_footprints(mock_db, user_id="u1", offset=20, limit=10)
        mock_db.execute.assert_called_once()


@pytest.mark.unit
class TestGetFootprintCount:
    """get_footprint_count - 足迹总数"""

    @pytest.mark.asyncio
    async def test_returns_count(self, mock_db):
        mock_db.execute.return_value = _make_result(scalar=10)
        result = await get_footprint_count(mock_db, user_id="u1")
        assert result == 10

    @pytest.mark.asyncio
    async def test_returns_zero_when_none(self, mock_db):
        mock_db.execute.return_value = _make_result(scalar=None)
        result = await get_footprint_count(mock_db, user_id="u1")
        assert result == 0

    @pytest.mark.asyncio
    async def test_count_with_date_range(self, mock_db):
        mock_db.execute.return_value = _make_result(scalar=5)
        result = await get_footprint_count(mock_db, user_id="u1", start_date=date(2025, 1, 1))
        assert result == 5


@pytest.mark.unit
class TestDeleteFootprints:
    """delete_footprints - 批量删除"""

    @pytest.mark.asyncio
    async def test_batch_delete(self, mock_db):
        mock_db.execute.return_value = _make_result(rowcount=2)
        result = await delete_footprints(mock_db, user_id="u1", product_ids=["p1", "p2"])
        assert result == 2
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_product_ids_returns_zero(self, mock_db):
        result = await delete_footprints(mock_db, user_id="u1", product_ids=[])
        assert result == 0
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_zero(self, mock_db):
        mock_db.execute.return_value = _make_result(rowcount=0)
        result = await delete_footprints(mock_db, user_id="u1", product_ids=["p999"])
        assert result == 0
