"""异步数据库连接 + ORM Base"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


class Base(DeclarativeBase):
    pass


# 必须在 engine 创建前导入所有模型，确保 Base.metadata 包含全部表
import app.models  # noqa: E402, F401 — 触发所有 ORM 模型注册

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


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
