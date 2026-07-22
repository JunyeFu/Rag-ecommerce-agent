"""
多轮状态管理 — 数据库持久化 + 内存缓存 (无数据库时纯内存模式)
"""
import logging
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.core.cache import InMemoryCache
from app.models.session import Session
from app.models.message import Message

logger = logging.getLogger("state_manager")

# 内存缓存 (减少 DB 查询, TTL 1h)
_cache = InMemoryCache(max_size=200, default_ttl=3600)

# 检测数据库是否可用
_HAS_DB = AsyncSessionLocal is not None
if not _HAS_DB:
    logger.info("state_manager: 数据库不可用，使用纯内存模式")


async def _get_db():
    """获取数据库会话上下文管理器 (无DB时返回空上下文)"""
    if _HAS_DB:
        return AsyncSessionLocal()
    else:
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def _null():
            yield None
        return _null()


async def get_or_create_session(session_id: str | None = None) -> tuple[str, dict]:
    """获取或创建会话，返回 (session_id, state)"""
    # 验证 session_id 是否为有效 UUID
    valid_uuid = None
    if session_id:
        try:
            valid_uuid = uuid.UUID(session_id)
        except (ValueError, AttributeError):
            valid_uuid = None

    if valid_uuid:
        session_str = str(valid_uuid)
        # 尝试从缓存获取
        cached = await _cache.get(session_str)
        if cached is not None:
            return session_str, cached

        # 从数据库获取 (仅当有DB时)
        if _HAS_DB:
            try:
                async with AsyncSessionLocal() as db:
                    result = await db.execute(select(Session).where(Session.id == valid_uuid))
                    session = result.scalar_one_or_none()
                    if session:
                        state = session.state_json or {}
                        await _cache.set(str(session.id), state)
                        return str(session.id), state
            except Exception as e:
                logger.warning("Session DB lookup failed, using memory fallback: %s", e)

    # 创建新会话（优先使用传入的有效 UUID）
    new_id = valid_uuid if valid_uuid else uuid.uuid4()
    new_id_str = str(new_id)

    if _HAS_DB:
        try:
            async with AsyncSessionLocal() as db:
                session = Session(id=new_id, state_json={}, message_count=0)
                db.add(session)
                await db.commit()
        except Exception as e:
            logger.warning("Session DB create failed, using memory fallback: %s", e)

    await _cache.set(new_id_str, {})
    logger.info("Created session: %s (db=%s)", new_id_str[:8], _HAS_DB)
    return new_id_str, {}


async def update_state(session_id: str, **kwargs) -> dict:
    """更新会话状态 (合并写入，自动持久化)"""
    state = await _cache.get(session_id) or {}
    state.update(kwargs)

    # 缓存更新
    await _cache.set(session_id, state)

    # 异步持久化 (仅当有DB时)
    if _HAS_DB:
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(Session)
                    .where(Session.id == session_id)
                    .values(
                        state_json=state,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await db.commit()
        except Exception as e:
            logger.warning("Failed to persist state for %s: %s", session_id[:8], e)

    logger.debug("Session %s state: %s", session_id[:8], list(kwargs.keys()))
    return state


async def increment_message_count(session_id: str):
    """增加消息计数"""
    if not _HAS_DB:
        return
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Session)
                .where(Session.id == session_id)
                .values(message_count=Session.message_count + 1)
            )
            await db.commit()
    except Exception as e:
        logger.warning("Failed to increment msg count: %s", e)


async def get_state(session_id: str) -> dict:
    """获取会话状态（优先缓存）"""
    cached = await _cache.get(session_id)
    if cached is not None:
        return cached
    _, state = await get_or_create_session(session_id)
    return state


async def clear_state(session_id: str) -> None:
    """清除会话状态"""
    await _cache.delete(session_id)
    if not _HAS_DB:
        return
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(update(Session).where(Session.id == session_id).values(is_active=False))
            await db.commit()
    except Exception as e:
        logger.warning("Failed to deactivate session: %s", e)


async def save_message(
    session_id: str,
    role: str,
    content: str,
    product_ids: list = None,
    audio_data: bytes | None = None,
) -> None:
    """持久化单条消息到 messages 表"""
    if not content.strip():
        return
    if not _HAS_DB:
        return
    try:
        sid = uuid.UUID(session_id)
        async with AsyncSessionLocal() as db:
            msg = Message(
                session_id=sid,
                role=role,
                content=content[:2000],  # 截断过长内容
                product_ids=product_ids or [],
                audio_data=audio_data,
            )
            db.add(msg)
            await db.commit()
    except Exception as e:
        logger.warning("Failed to save message for %s: %s", session_id[:8], e)


async def get_recent_messages(session_id: str, limit: int = 6) -> list[dict]:
    """获取最近 N 条消息，返回 [{role, content}, ...]（时间正序）"""
    if not _HAS_DB:
        return []
    try:
        sid = uuid.UUID(session_id)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Message.content, Message.role)
                .where(Message.session_id == sid)
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            rows = result.all()
            # 逆转为时间正序
            return [{"role": r.role, "content": r.content} for r in reversed(rows)]
    except Exception as e:
        logger.warning("Failed to get recent messages for %s: %s", session_id[:8], e)
        return []
