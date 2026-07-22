"""
商品评价服务 — CRUD 操作
"""
import uuid
import logging
from typing import Optional
from datetime import date
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.review import Review

logger = logging.getLogger("review_service")


async def create_review(
    db: AsyncSession,
    product_id: str,
    user_id: str,
    nickname: str = "",
    rating: int = 5,
    content: str = "",
    media: bytes | None = None,
    is_anonymous: bool = False,
) -> Review:
    """创建商品评价"""
    display_nickname = "匿名用户" if is_anonymous else nickname
    review = Review(
        product_id=product_id,
        user_id=user_id,
        nickname=display_nickname,
        rating=rating,
        content=content,
        media=media,
        review_date=date.today(),
        is_anonymous=is_anonymous,
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)
    logger.info("Review created: %s, product=%s, rating=%d", review.id, product_id, rating)
    return review


async def get_reviews_by_product(
    db: AsyncSession,
    product_id: str,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Review], int, float]:
    """获取商品评价列表，返回 (评价列表, 总数, 平均评分)"""
    # 总数
    count_result = await db.execute(
        select(func.count()).select_from(Review).where(Review.product_id == product_id)
    )
    total = count_result.scalar() or 0

    # 平均评分
    avg_result = await db.execute(
        select(func.avg(Review.rating)).where(Review.product_id == product_id)
    )
    avg_rating = avg_result.scalar()
    average = round(float(avg_rating), 1) if avg_rating else 0.0

    # 评价列表（按时间倒序）
    result = await db.execute(
        select(Review)
        .where(Review.product_id == product_id)
        .order_by(Review.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    reviews = list(result.scalars().all())

    return reviews, total, average


async def get_reviews_by_user(
    db: AsyncSession,
    user_id: str,
    limit: int = 20,
    offset: int = 0,
) -> list[Review]:
    """获取用户的所有评价"""
    result = await db.execute(
        select(Review)
        .where(Review.user_id == user_id)
        .order_by(Review.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_review(db: AsyncSession, review_id: str) -> Optional[Review]:
    """按 ID 查询评价"""
    try:
        uid = uuid.UUID(review_id)
    except (ValueError, AttributeError, TypeError):
        return None
    result = await db.execute(select(Review).where(Review.id == uid))
    return result.scalar_one_or_none()
