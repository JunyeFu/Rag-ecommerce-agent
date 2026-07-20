"""initial schema baseline

Revision ID: 0001
Revises:
Create Date: 2026-07-20

包含所有 ORM 表 + pgvector 扩展 + 向量/全文搜索索引。
现有 DB 用 `alembic stamp head` 标记；新 DB 用 `alembic upgrade head` 建表。
"""
from alembic import op

from app.core.database import Base
import app.models  # noqa: F401 - 注册所有 ORM model

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # 1. pgvector 扩展（products.embedding / knowledge_chunks.embedding 依赖）
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. 创建所有 ORM 定义的表（幂等，已存在的表跳过）
    Base.metadata.create_all(op.get_bind())

    # 3. 向量检索索引（ivfflat, cosine）
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_products_embedding "
        "ON products USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_knowledge_embedding "
        "ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # 4. 全文搜索索引（GIN）
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_products_search_vector "
        "ON products USING GIN (search_vector)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_products_search_vector")
    op.execute("DROP INDEX IF EXISTS idx_knowledge_embedding")
    op.execute("DROP INDEX IF EXISTS idx_products_embedding")
    Base.metadata.drop_all(op.get_bind())
