"""认证服务 - Session Token 生成/验证/缓存

方案：UUID token + DB sessions 表 + 内存缓存（TTL 30min）
"""
import uuid
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, db_context
from app.models.user import User

logger = logging.getLogger("auth_service")

# ── 内存缓存：token -> (user_id, expires_ts) ──
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_TOKEN_TTL = 1800  # 30 分钟


def _cache_get(token: str) -> Optional[str]:
    """从缓存读取 user_id，过期则清除"""
    entry = _TOKEN_CACHE.get(token)
    if entry is None:
        return None
    user_id, expires_ts = entry
    if time.time() > expires_ts:
        _TOKEN_CACHE.pop(token, None)
        return None
    return user_id


def _cache_set(token: str, user_id: str, ttl: int = _TOKEN_TTL) -> None:
    _TOKEN_CACHE[token] = (user_id, time.time() + ttl)


def _cache_del(token: str) -> None:
    _TOKEN_CACHE.pop(token, None)


def _cache_clear() -> None:
    _TOKEN_CACHE.clear()


async def create_session_token(user_id: str = "", nickname: str = "") -> tuple[str, str, bool, datetime]:
    """生成 Session Token，关联或创建用户。

    Returns: (token, user_id, is_guest, expires_at)
    """
    token = str(uuid.uuid4())
    is_guest = not user_id
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=_TOKEN_TTL)

    async with db_context.session() as db:
        if db is None:
            # 内存模式 - 仍可生成 token，只是不持久化
            if not user_id:
                user_id = f"guest-{uuid.uuid4().hex[:12]}"
            _cache_set(token, user_id)
            logger.info("Auth token (memory mode): user=%s guest=%s", user_id[:16], is_guest)
            return token, user_id, is_guest, expires_at

        if user_id:
            # 已有用户 - 确认存在
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is None:
                # user_id 不存在 - 创建非游客用户
                user = User(
                    id=user_id,
                    nickname=nickname or f"用户{user_id[:6]}",
                    is_guest=0,
                )
                db.add(user)
                await db.flush()
                logger.info("Auth: created new user %s", user_id[:16])
        else:
            # 创建游客
            user_id = f"guest-{uuid.uuid4().hex[:12]}"
            user = User(
                id=user_id,
                nickname=nickname or "游客",
                is_guest=1,
            )
            db.add(user)
            await db.flush()
            logger.info("Auth: created guest %s", user_id[:16])

        # 持久化 token 到 sessions 表（进程重启后仍可验证）
        from app.models.session import Session as SessionModel
        session = SessionModel(
            auth_token=token,
            auth_user_id=user_id,
            auth_expires_at=expires_at,
        )
        db.add(session)
        await db.flush()

        # 写入内存缓存
        _cache_set(token, user_id)
        logger.info("Auth token: user=%s guest=%s expires=%s", user_id[:16], is_guest, expires_at.isoformat())

    return token, user_id, is_guest, expires_at


async def validate_session_token(token: str) -> Optional[str]:
    """验证 token，返回 user_id 或 None。

    优先查内存缓存，未命中则查 DB。
    """
    # 1. 内存缓存
    user_id = _cache_get(token)
    if user_id is not None:
        return user_id

    # 2. DB 查询 sessions 表
    if AsyncSessionLocal is None:
        return None

    try:
        async with AsyncSessionLocal() as db:
            from app.models.session import Session
            result = await db.execute(
                select(Session)
                .where(Session.auth_token == token)
                .where(Session.auth_expires_at > datetime.now(timezone.utc))
            )
            session = result.scalar_one_or_none()
            if session is None:
                return None
            user_id = session.auth_user_id or ""
            if user_id:
                _cache_set(token, user_id)
            return user_id or None
    except Exception as exc:
        logger.warning("Token validation DB error: %s", exc)
        return None


async def revoke_session_token(token: str) -> bool:
    """撤销 token（登出）"""
    _cache_del(token)
    if AsyncSessionLocal is None:
        return True
    try:
        async with AsyncSessionLocal() as db:
            from app.models.session import Session
            await db.execute(
                update(Session)
                .where(Session.auth_token == token)
                .values(auth_expires_at=datetime.now(timezone.utc))
            )
            await db.commit()
            logger.info("Auth token revoked")
            return True
    except Exception as exc:
        logger.warning("Token revoke DB error: %s", exc)
        return False


async def bind_token_to_session(token: str, session_id: str, user_id: str) -> None:
    """将 token 绑定到 DB session 记录（持久化认证信息）"""
    if AsyncSessionLocal is None:
        return
    try:
        async with AsyncSessionLocal() as db:
            from app.models.session import Session
            sid = uuid.UUID(session_id)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=_TOKEN_TTL)
            await db.execute(
                update(Session)
                .where(Session.id == sid)
                .values(
                    auth_token=token,
                    auth_user_id=user_id,
                    auth_expires_at=expires_at,
                )
            )
            await db.commit()
            _cache_set(token, user_id)
    except Exception as exc:
        logger.warning("Token bind error: %s", exc)
