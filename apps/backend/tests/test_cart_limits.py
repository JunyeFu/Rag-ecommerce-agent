"""购物车数量上限单元测试"""
import pytest
import uuid as _uuid
from unittest.mock import AsyncMock, MagicMock
from app.services.cart_service import (
    MAX_SINGLE_ITEM_QTY,
    MAX_CART_TOTAL_ITEMS,
    add_to_cart,
    update_quantity,
)
from app.core.exceptions import BadRequestError

VALID_SESSION = str(_uuid.uuid4())


@pytest.mark.unit
class TestCartLimits:
    """购物车数量上限测试"""

    def test_max_single_item_qty_is_99(self):
        assert MAX_SINGLE_ITEM_QTY == 99

    def test_max_cart_total_items_is_50(self):
        assert MAX_CART_TOTAL_ITEMS == 50

    @pytest.mark.asyncio
    async def test_add_exceeds_single_item_limit_raises(self):
        """单品数量超过上限时抛 BadRequestError"""
        db = MagicMock()
        existing = MagicMock()
        existing.quantity = MAX_SINGLE_ITEM_QTY
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(BadRequestError, match="单品数量"):
            await add_to_cart(db, VALID_SESSION, "prod-1", "Test", 10.0)

    @pytest.mark.asyncio
    async def test_add_at_limit_raises(self):
        """恰好达到上限时再加也抛异常"""
        db = MagicMock()
        existing = MagicMock()
        existing.quantity = MAX_SINGLE_ITEM_QTY
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(BadRequestError, match="单品数量"):
            await add_to_cart(db, VALID_SESSION, "prod-1", "Test", 10.0)

    @pytest.mark.asyncio
    async def test_add_below_limit_succeeds(self):
        """未达上限时正常加购"""
        db = MagicMock()
        existing = MagicMock()
        existing.quantity = 10
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=result_mock)
        db.flush = AsyncMock()

        item = await add_to_cart(db, VALID_SESSION, "prod-1", "Test", 10.0)
        assert item is existing
        assert existing.quantity == 11

    @pytest.mark.asyncio
    async def test_update_exceeds_limit_raises(self):
        """update_quantity 超过上限时抛异常"""
        db = MagicMock()
        item = MagicMock()
        item.quantity = 5
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = item
        db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(BadRequestError, match="单品数量不能超过"):
            await update_quantity(db, VALID_SESSION, "prod-1", MAX_SINGLE_ITEM_QTY + 1)

    @pytest.mark.asyncio
    async def test_update_to_zero_allowed(self):
        """update_quantity 设为 0 允许（自动移除）"""
        db = MagicMock()
        item = MagicMock()
        item.quantity = 5
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = item
        db.execute = AsyncMock(return_value=result_mock)
        db.flush = AsyncMock()

        ok = await update_quantity(db, VALID_SESSION, "prod-1", 0)
        assert ok is True
        assert item.quantity == 0
