"""认证 Schema - 登录请求/响应"""
from datetime import datetime
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求 - 支持 guest 和 user 两种模式"""
    user_id: str = Field("", description="用户 ID（已有用户可传入，空则创建游客）")
    nickname: str = Field("", description="昵称")


class TokenResponse(BaseModel):
    """登录响应 - 返回 Session Token"""
    token: str = Field(..., description="Session Token (UUID)")
    user_id: str = Field(..., description="用户 ID")
    nickname: str = Field("", description="昵称")
    is_guest: bool = Field(True, description="是否游客")
    expires_at: datetime = Field(..., description="Token 过期时间")
