"""订单服务 - 下单/查单/取消 + 库存校验 + 状态机"""
import uuid
import hashlib
import logging
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.order import Order
from app.models.product import Product
from app.core.exceptions import BadRequestError, NotFoundError, ValidationError
from app.services import cart_service

logger = logging.getLogger("order_service")

# 订单状态机
ORDER_TRANSITIONS: dict[str, set[str]] = {
    "pending_payment": {"pending_shipping", "cancelled"},
    "pending_shipping": {"pending_receipt", "cancelled"},
    "pending_receipt": {"pending_review", "completed"},
    "pending_review": {"completed", "cancelled"},
    "completed": set(),  # 终态
    "cancelled": set(),  # 终态
}

# 可取消的状态
CANCELLABLE_STATES = {"pending_payment", "pending_shipping"}


def _generate_order_no(session_id: str) -> str:
    """生成唯一订单号：ORD + 时间戳 + hash 后8位"""
    import time
    ts = str(int(time.time()))
    digest = hashlib.md5((session_id + ts).encode()).hexdigest()[:8].upper()
    return f"ORD{ts[-6:]}{digest}"


async def _validate_stock(db: AsyncSession, items: list) -> None:
    """校验商品库存 - 查 products 表 stock 字段

    Args:
        items: CartItem 列表
    Raises:
        BadRequestError: 库存不足
        NotFoundError: 商品不存在
    """
    for item in items:
        result = await db.execute(
            select(Product).where(
                (Product.id == item.product_id) | (Product.source_product_id == item.product_id)
            )
        )
        product = result.scalar_one_or_none()
        if product is None:
            raise NotFoundError(f"商品不存在: {item.product_id}")
        if product.stock < item.quantity:
            raise BadRequestError(
                f"商品库存不足: {item.title}（剩余 {product.stock}，需要 {item.quantity}）"
            )


async def create_order_atomic(
    db: AsyncSession,
    session_id: str,
    items: list[dict],
    total: float,
    address: str = "默认地址",
    remark: str = "",
    product_ids: list[str] | None = None,
    user_id: str = "",
) -> Order:
    """原子下单：创建订单 + 清空购物车（同一事务）

    在同一 DB 事务中完成：
    1. 库存校验
    2. 创建订单
    3. 清空/移除购物车商品
    4. 提交事务

    若任何步骤失败，整体回滚。
    """
    # 1. 库存校验（查 products 表）
    # 先获取购物车 CartItem 对象用于库存校验
    cart_items = await cart_service.get_cart(db, session_id, user_id)
    if product_ids:
        selected = set(product_ids)
        cart_items = [item for item in cart_items if str(item.product_id) in selected]
    
    if not cart_items:
        raise BadRequestError("购物车为空，无法下单")

    # 库存校验
    await _validate_stock(db, cart_items)

    # 2. 创建订单
    order_no = _generate_order_no(session_id)
    order = Order(
        session_id=uuid.UUID(session_id),
        order_no=order_no,
        total=round(total, 2),
        address=address,
        remark=remark,
        items_snapshot=items,
        status="pending_shipping",
    )
    db.add(order)
    await db.flush()
    await db.refresh(order)

    # 3. 清空购物车（移除已下单商品）
    if product_ids:
        for item in cart_items:
            await cart_service.remove_from_cart(db, session_id, str(item.product_id), user_id=user_id)
    else:
        await cart_service.clear_cart(db, session_id, user_id=user_id)

    logger.info("Order created atomically: %s, total=%.2f, items=%d", order_no, total, len(items))
    return order


async def get_order(db: AsyncSession, order_id: str) -> Optional[Order]:
    """按 ID 查询订单"""
    try:
        uid = uuid.UUID(order_id)
    except (ValueError, AttributeError):
        return None
    result = await db.execute(select(Order).where(Order.id == uid))
    return result.scalar_one_or_none()


async def get_orders_by_session(db: AsyncSession, session_id: str) -> list[Order]:
    """按 session 查询所有订单"""
    try:
        sid = uuid.UUID(session_id)
    except (ValueError, AttributeError):
        return []
    result = await db.execute(
        select(Order).where(Order.session_id == sid).order_by(Order.created_at.desc())
    )
    return list(result.scalars().all())


def _validate_state_transition(current: str, target: str) -> None:
    """校验订单状态转换是否合法

    Raises:
        ValidationError: 非法状态转换
    """
    allowed = ORDER_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValidationError(
            f"订单状态不允许从 '{current}' 转换到 '{target}'"
        )


async def cancel_order(db: AsyncSession, order_id: str) -> bool:
    """取消订单 - 校验状态机

    只有 pending_payment 和 pending_shipping 状态可取消。
    """
    order = await get_order(db, order_id)
    if order is None:
        return False

    if order.status not in CANCELLABLE_STATES:
        raise ValidationError(
            f"订单当前状态为 '{order.status}'，无法取消（仅待付款/待发货可取消）"
        )

    order.status = "cancelled"
    await db.flush()
    logger.info("Order cancelled: %s", order.order_no)
    return True


async def update_order_status(
    db: AsyncSession, order_id: str, new_status: str
) -> Order | None:
    """更新订单状态 - 带状态机校验

    Args:
        new_status: 目标状态
    Raises:
        NotFoundError: 订单不存在
        ValidationError: 非法状态转换
    """
    order = await get_order(db, order_id)
    if order is None:
        raise NotFoundError("订单不存在")

    _validate_state_transition(order.status, new_status)
    order.status = new_status
    await db.flush()
    logger.info("Order status: %s -> %s", order.order_no, new_status)
    return order
