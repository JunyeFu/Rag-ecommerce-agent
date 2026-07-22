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
    create_order_atomic,
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


@pytest.mark.unit
class TestCreateOrderAtomic:
    """原子下单测试 - create_order_atomic

    覆盖：空购物车、库存校验、product_ids 过滤、正常下单、购物车清理
    """

    @pytest.mark.asyncio
    async def test_empty_cart_raises(self):
        """空购物车抛 BadRequestError"""
        db = MagicMock()
        with patch("app.services.order_service.cart_service.get_cart", AsyncMock(return_value=[])):
            with pytest.raises(BadRequestError, match="购物车为空"):
                await create_order_atomic(
                    db, VALID_UUID, [], 0.0,
                )

    @pytest.mark.asyncio
    async def test_empty_cart_after_product_ids_filter_raises(self):
        """product_ids 过滤后购物车为空也抛异常"""
        item = MagicMock()
        item.product_id = "prod-1"
        db = MagicMock()
        with patch("app.services.order_service.cart_service.get_cart", AsyncMock(return_value=[item])):
            with pytest.raises(BadRequestError, match="购物车为空"):
                await create_order_atomic(
                    db, VALID_UUID, [], 0.0, product_ids=["prod-nonexistent"],
                )

    @pytest.mark.asyncio
    async def test_stock_validation_failure_propagates(self):
        """库存不足时抛 BadRequestError"""
        item = MagicMock()
        item.product_id = "prod-1"
        item.quantity = 10
        db = MagicMock()
        with patch("app.services.order_service.cart_service.get_cart", AsyncMock(return_value=[item])):
            with patch("app.services.order_service._validate_stock", AsyncMock(side_effect=BadRequestError("库存不足"))):
                with pytest.raises(BadRequestError, match="库存不足"):
                    await create_order_atomic(
                        db, VALID_UUID, [{"product_id": "prod-1", "title": "T", "price": 10, "quantity": 10}], 100.0,
                    )

    @pytest.mark.asyncio
    async def test_successful_order_creation_without_product_ids(self):
        """正常下单 - 无 product_ids，清空整个购物车"""
        item = MagicMock()
        item.product_id = "prod-1"
        item.title = "Test Product"
        item.price = 9.9
        item.quantity = 2
        db = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        with patch("app.services.order_service.cart_service.get_cart", AsyncMock(return_value=[item])):
            with patch("app.services.order_service._validate_stock", AsyncMock()):
                with patch("app.services.order_service.cart_service.clear_cart", AsyncMock()) as mock_clear:
                    order = await create_order_atomic(
                        db, VALID_UUID,
                        [{"product_id": "prod-1", "title": "Test Product", "price": 9.9, "quantity": 2}],
                        19.8,
                        address="Test Address",
                        remark="Test Remark",
                    )

        assert order is not None
        assert order.status == "pending_shipping"
        assert order.total == 19.8
        assert order.address == "Test Address"
        assert order.remark == "Test Remark"
        db.add.assert_called_once()
        mock_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_order_creation_with_product_ids(self):
        """正常下单 - 有 product_ids，仅移除已下单商品"""
        item1 = MagicMock()
        item1.product_id = "prod-1"
        item1.title = "Product 1"
        item1.price = 10.0
        item1.quantity = 1

        item2 = MagicMock()
        item2.product_id = "prod-2"
        item2.title = "Product 2"
        item2.price = 20.0
        item2.quantity = 1

        db = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        items_snapshot = [
            {"product_id": "prod-1", "title": "Product 1", "price": 10.0, "quantity": 1},
        ]

        with patch("app.services.order_service.cart_service.get_cart", AsyncMock(return_value=[item1, item2])):
            with patch("app.services.order_service._validate_stock", AsyncMock()):
                with patch("app.services.order_service.cart_service.remove_from_cart", AsyncMock(return_value=True)) as mock_remove:
                    order = await create_order_atomic(
                        db, VALID_UUID, items_snapshot, 10.0,
                        product_ids=["prod-1"],
                    )

        assert order is not None
        assert order.status == "pending_shipping"
        mock_remove.assert_called_once_with(db, VALID_UUID, "prod-1", user_id="")

    @pytest.mark.asyncio
    async def test_order_no_generated(self):
        """订单号在创建时生成"""
        item = MagicMock()
        item.product_id = "prod-1"
        item.title = "T"
        item.price = 5.0
        item.quantity = 1
        db = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        with patch("app.services.order_service.cart_service.get_cart", AsyncMock(return_value=[item])):
            with patch("app.services.order_service._validate_stock", AsyncMock()):
                with patch("app.services.order_service.cart_service.clear_cart", AsyncMock()):
                    order = await create_order_atomic(
                        db, VALID_UUID, [{"product_id": "prod-1", "title": "T", "price": 5.0, "quantity": 1}], 5.0,
                    )

        assert order.order_no.startswith("ORD")

    @pytest.mark.asyncio
    async def test_total_rounded_to_two_decimals(self):
        """总价四舍五入到两位小数"""
        item = MagicMock()
        item.product_id = "prod-1"
        item.title = "T"
        item.price = 3.0
        item.quantity = 1
        db = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        with patch("app.services.order_service.cart_service.get_cart", AsyncMock(return_value=[item])):
            with patch("app.services.order_service._validate_stock", AsyncMock()):
                with patch("app.services.order_service.cart_service.clear_cart", AsyncMock()):
                    order = await create_order_atomic(
                        db, VALID_UUID,
                        [{"product_id": "prod-1", "title": "T", "price": 3.0, "quantity": 1}],
                        10.556,
                    )

        assert order.total == 10.56
