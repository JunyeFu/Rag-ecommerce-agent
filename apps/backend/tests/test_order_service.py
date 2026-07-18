"""订单状态机 + 库存校验 + 原子事务 单元测试"""
import pytest
import uuid as _uuid
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.order_service import (
    ORDER_TRANSITIONS,
    CANCELLABLE_STATES,
    _validate_state_transition,
    _generate_order_no,
    _validate_stock,
    cancel_order,
    update_order_status,
)
from app.core.exceptions import BadRequestError, NotFoundError, ValidationError

VALID_UUID = str(_uuid.uuid4())


@pytest.mark.unit
class TestOrderStateMachine:
    """订单状态机转换规则测试"""

    def test_transitions_pending_payment_can_cancel(self):
        assert "cancelled" in ORDER_TRANSITIONS["pending_payment"]

    def test_transitions_pending_payment_can_ship(self):
        assert "pending_shipping" in ORDER_TRANSITIONS["pending_payment"]

    def test_transitions_completed_is_terminal(self):
        assert ORDER_TRANSITIONS["completed"] == set()

    def test_transitions_cancelled_is_terminal(self):
        assert ORDER_TRANSITIONS["cancelled"] == set()

    def test_cancellable_states_excludes_completed(self):
        assert "completed" not in CANCELLABLE_STATES

    def test_cancellable_states_excludes_cancelled(self):
        assert "cancelled" not in CANCELLABLE_STATES

    def test_validate_transition_valid(self):
        _validate_state_transition("pending_payment", "pending_shipping")

    def test_validate_transition_invalid_completed_to_cancel(self):
        with pytest.raises(ValidationError):
            _validate_state_transition("completed", "cancelled")

    def test_validate_transition_invalid_cancelled_to_anything(self):
        with pytest.raises(ValidationError):
            _validate_state_transition("cancelled", "pending_shipping")

    def test_validate_transition_unknown_state(self):
        with pytest.raises(ValidationError):
            _validate_state_transition("unknown_state", "completed")


@pytest.mark.unit
class TestGenerateOrderNo:
    """订单号生成测试"""

    def test_order_no_format(self):
        no = _generate_order_no("test-session")
        assert no.startswith("ORD")
        assert len(no) == 3 + 6 + 8

    def test_order_no_unique_for_different_sessions(self):
        no1 = _generate_order_no("session1")
        no2 = _generate_order_no("session2")
        assert no1 != no2

    def test_order_no_contains_only_alnum(self):
        import re
        no = _generate_order_no("test")
        assert re.match(r"^ORD[A-Z0-9]+$", no)


@pytest.mark.unit
class TestValidateStock:
    """库存校验测试"""

    @pytest.mark.asyncio
    async def test_stock_sufficient(self):
        db = MagicMock()
        product = MagicMock()
        product.stock = 10
        item = MagicMock()
        item.product_id = "prod-1"
        item.quantity = 5
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = product
        db.execute = AsyncMock(return_value=result_mock)
        await _validate_stock(db, [item])

    @pytest.mark.asyncio
    async def test_stock_insufficient_raises(self):
        db = MagicMock()
        product = MagicMock()
        product.stock = 3
        item = MagicMock()
        item.product_id = "prod-1"
        item.quantity = 5
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = product
        db.execute = AsyncMock(return_value=result_mock)
        with pytest.raises(BadRequestError, match="stock|库存"):
            await _validate_stock(db, [item])

    @pytest.mark.asyncio
    async def test_stock_exact_match_passes(self):
        db = MagicMock()
        product = MagicMock()
        product.stock = 5
        item = MagicMock()
        item.product_id = "prod-1"
        item.quantity = 5
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = product
        db.execute = AsyncMock(return_value=result_mock)
        await _validate_stock(db, [item])

    @pytest.mark.asyncio
    async def test_stock_product_not_found_raises(self):
        db = MagicMock()
        item = MagicMock()
        item.product_id = "missing"
        item.quantity = 1
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        with pytest.raises(NotFoundError):
            await _validate_stock(db, [item])


@pytest.mark.unit
class TestCancelOrder:
    """取消订单测试 - 直接 mock get_order"""

    @pytest.mark.asyncio
    async def test_cancel_pending_payment_succeeds(self):
        order = MagicMock()
        order.status = "pending_payment"
        order.order_no = "ORD123"
        with patch("app.services.order_service.get_order", AsyncMock(return_value=order)):
            db = MagicMock()
            db.flush = AsyncMock()
            ok = await cancel_order(db, VALID_UUID)
            assert ok is True
            assert order.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_pending_shipping_succeeds(self):
        order = MagicMock()
        order.status = "pending_shipping"
        with patch("app.services.order_service.get_order", AsyncMock(return_value=order)):
            db = MagicMock()
            db.flush = AsyncMock()
            ok = await cancel_order(db, VALID_UUID)
            assert ok is True

    @pytest.mark.asyncio
    async def test_cancel_completed_raises(self):
        order = MagicMock()
        order.status = "completed"
        with patch("app.services.order_service.get_order", AsyncMock(return_value=order)):
            db = MagicMock()
            with pytest.raises(ValidationError):
                await cancel_order(db, VALID_UUID)

    @pytest.mark.asyncio
    async def test_cancel_cancelled_raises(self):
        order = MagicMock()
        order.status = "cancelled"
        with patch("app.services.order_service.get_order", AsyncMock(return_value=order)):
            db = MagicMock()
            with pytest.raises(ValidationError):
                await cancel_order(db, VALID_UUID)

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_returns_false(self):
        with patch("app.services.order_service.get_order", AsyncMock(return_value=None)):
            db = MagicMock()
            ok = await cancel_order(db, VALID_UUID)
            assert ok is False


@pytest.mark.unit
class TestUpdateOrderStatus:
    """订单状态更新测试"""

    @pytest.mark.asyncio
    async def test_update_valid_transition(self):
        order = MagicMock()
        order.status = "pending_payment"
        order.order_no = "ORD123"
        with patch("app.services.order_service.get_order", AsyncMock(return_value=order)):
            db = MagicMock()
            db.flush = AsyncMock()
            updated = await update_order_status(db, VALID_UUID, "pending_shipping")
            assert updated.status == "pending_shipping"

    @pytest.mark.asyncio
    async def test_update_invalid_transition_raises(self):
        order = MagicMock()
        order.status = "completed"
        with patch("app.services.order_service.get_order", AsyncMock(return_value=order)):
            db = MagicMock()
            with pytest.raises(ValidationError):
                await update_order_status(db, VALID_UUID, "pending_shipping")

    @pytest.mark.asyncio
    async def test_update_nonexistent_raises_not_found(self):
        with patch("app.services.order_service.get_order", AsyncMock(return_value=None)):
            db = MagicMock()
            with pytest.raises(NotFoundError):
                await update_order_status(db, VALID_UUID, "completed")
