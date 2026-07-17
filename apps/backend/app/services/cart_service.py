"""
购物车 CRUD 服务 — 带内存缓存加速，支持 user_id 匹配
"""
import uuid
import logging
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.cart import CartItem

logger = logging.getLogger("cart_service")

# ── 内存缓存：key=(session_id, user_id), value=(items_list, total) ──
_cart_cache: dict[str, tuple[list[CartItem], float]] = {}


def _cache_key(session_id: str, user_id: str = "") -> str:
    """生成缓存键，user_id 为空时仅使用 session_id"""
    return f"{session_id}:{user_id}" if user_id else session_id


def _invalidate_cache(session_id: str, user_id: str = ""):
    """清除指定 session（及所有 user_id 变体）的缓存。

    使用 ":" 分隔符精确匹配，避免 session_id 前缀重合导致误删
    （例如 "abc123" 不应匹配 "abc123def" 的缓存键）。
    """
    keys_to_remove = [
        k for k in _cart_cache
        if k == session_id or k.startswith(f"{session_id}:")
    ]
    for k in keys_to_remove:
        _cart_cache.pop(k, None)


def _to_uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)


async def get_cart(db: AsyncSession, session_id: str, user_id: str = "") -> list[CartItem]:
    """获取购物车商品列表（优先缓存）。

    Args:
        session_id: 会话 ID
        user_id: 可选的用户 ID，传入时按 user_id + session_id 联合过滤
    """
    cache_key = _cache_key(session_id, user_id)
    cached = _cart_cache.get(cache_key)
    if cached is not None:
        return cached[0]

    sid = _to_uuid(session_id)
    stmt = select(CartItem).where(CartItem.session_id == sid)
    if user_id:
        stmt = stmt.where(CartItem.user_id == user_id)
    stmt = stmt.order_by(CartItem.created_at)

    result = await db.execute(stmt)
    items = list(result.scalars().all())
    total = sum(it.price * it.quantity for it in items)
    _cart_cache[cache_key] = (items, total)
    return items


async def add_to_cart(
    db: AsyncSession, session_id: str,
    product_id: str, title: str, price: float,
    user_id: str = "",
) -> CartItem:
    """添加商品到购物车（已存在则数量+1）。

    Args:
        user_id: 可选的用户 ID，传入时写入 cart_items.user_id 列
    """
    sid = _to_uuid(session_id)
    _invalidate_cache(session_id)

    result = await db.execute(
        select(CartItem)
        .where(
            CartItem.session_id == sid,
            CartItem.product_id == product_id,
            CartItem.user_id == user_id if user_id else CartItem.user_id.is_(None),
        )
        .with_for_update()
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.quantity += 1
        await db.flush()
        logger.info("Cart: %s quantity=%d (user=%s)", product_id[:16], existing.quantity, user_id[:12] if user_id else "anon")
        return existing

    item = CartItem(
        session_id=sid,
        product_id=product_id,
        title=title,
        price=price,
        quantity=1,
        user_id=user_id if user_id else None,
    )
    db.add(item)
    await db.flush()
    logger.info("Cart: added %s (user=%s)", title[:30], user_id[:12] if user_id else "anon")
    return item


async def remove_from_cart(
    db: AsyncSession, session_id: str, product_id: str,
    user_id: str = "",
) -> bool:
    """从购物车删除商品。

    Args:
        user_id: 可选，传入时仅删除匹配 user_id 的商品
    """
    sid = _to_uuid(session_id)
    _invalidate_cache(session_id)
    stmt = delete(CartItem).where(
        CartItem.session_id == sid,
        CartItem.product_id == product_id,
    )
    if user_id:
        stmt = stmt.where(CartItem.user_id == user_id)
    result = await db.execute(stmt)
    await db.flush()
    return result.rowcount > 0


async def update_quantity(
    db: AsyncSession, session_id: str, product_id: str, quantity: int,
    user_id: str = "",
) -> bool:
    """修改购物车商品数量。

    Args:
        user_id: 可选，传入时仅更新匹配 user_id 的商品
    """
    sid = _to_uuid(session_id)
    _invalidate_cache(session_id)
    stmt = select(CartItem).where(
        CartItem.session_id == sid,
        CartItem.product_id == product_id,
    )
    if user_id:
        stmt = stmt.where(CartItem.user_id == user_id)
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()
    if not item:
        return False
    item.quantity = max(0, quantity)
    await db.flush()
    return True


async def clear_cart(db: AsyncSession, session_id: str, user_id: str = ""):
    """清空购物车。

    Args:
        user_id: 可选，传入时仅清空匹配 user_id 的商品
    """
    sid = _to_uuid(session_id)
    _invalidate_cache(session_id)
    stmt = delete(CartItem).where(CartItem.session_id == sid)
    if user_id:
        stmt = stmt.where(CartItem.user_id == user_id)
    await db.execute(stmt)
    await db.flush()


async def get_cart_total(db: AsyncSession, session_id: str, user_id: str = "") -> float:
    """购物车总金额（优先缓存）。

    Args:
        user_id: 可选，传入时仅统计匹配 user_id 的商品
    """
    cache_key = _cache_key(session_id, user_id)
    cached = _cart_cache.get(cache_key)
    if cached is not None:
        return cached[1]

    sid = _to_uuid(session_id)
    stmt = select(func.sum(CartItem.price * CartItem.quantity)).where(CartItem.session_id == sid)
    if user_id:
        stmt = stmt.where(CartItem.user_id == user_id)
    result = await db.execute(stmt)
    total = result.scalar() or 0.0
    return total
