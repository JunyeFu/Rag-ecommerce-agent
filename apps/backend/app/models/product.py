"""
商品表 ORM 模型 (PostgreSQL + pgvector)
"""
import uuid
from sqlalchemy import String, Float, Integer, Text, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from app.core.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    rating: Mapped[float] = mapped_column(Float, default=0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, comment="评分人数")
    image_urls: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=list)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    sales: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=list)
    attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="结构化属性 (e.g. {颜色:黑, 续航:30h})")
    highlights: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True, comment="核心卖点")
    scenarios: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True, comment="适用场景")
    source_product_id: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="原始商品ID (seed/expanded)")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True, comment="BGE-large-zh-v1.5 向量")
    search_vector: Mapped[object | None] = mapped_column(TSVECTOR, nullable=True, comment="全文搜索向量 (title+description+category)")
