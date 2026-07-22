"""异步数据库连接 + ORM Base + DatabaseContext"""
from contextlib import asynccontextmanager
from typing import AsyncIterator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


class Base(DeclarativeBase):
    pass


# 必须在 engine 创建前导入所有模型，确保 Base.metadata 包含全部表
import app.models  # noqa: E402, F401 - 触发所有 ORM 模型注册

if settings.DATABASE_URL:
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False, pool_size=20, max_overflow=10,
        pool_pre_ping=True, pool_recycle=3600, pool_timeout=30,
    )
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
else:
    engine = None
    AsyncSessionLocal = None  # 内存模式


class DatabaseContext:
    """统一 DB 可用性检查，消除 3+ 处重复 `AsyncSessionLocal is None`"""

    @property
    def available(self) -> bool:
        return AsyncSessionLocal is not None

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession | None]:
        """返回真实 session 或 None (内存模式)"""
        if AsyncSessionLocal is None:
            yield None
            return
        async with AsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise


db_context = DatabaseContext()


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
