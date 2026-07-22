"""
会话表 ORM 模型
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(256), default="新对话")
    state_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="会话状态 (预算/偏好/已比较商品)")
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 认证字段（Phase 2 - Session Token）
    auth_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, comment="Session Token (UUID)")
    auth_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, comment="认证用户 ID")
    auth_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="Token 过期时间")
