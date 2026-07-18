"""
知识库分块表 ORM 模型 - RAG 知识库文档向量化存储
"""
import uuid
from datetime import datetime
from sqlalchemy import Text, Integer, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from app.core.database import Base


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    doc_id: Mapped[str] = mapped_column(Text, nullable=False, comment="文档批次ID")
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, comment="分块序号")
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True, comment="BGE-large-zh-v1.5 向量")
    chunk_meta: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict, server_default="{}", comment="文档元数据 (filename/doc_name 等)")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
