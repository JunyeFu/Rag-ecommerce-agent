"""认证 API 端点 - Session Token 登录/登出/当前用户"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.common import ApiResponse
from app.services import auth_service
from app.core.exceptions import AuthError

router = APIRouter()


@router.post("/auth/login", response_model=ApiResponse[TokenResponse])
async def login(body: LoginRequest):
    """登录 - 生成 Session Token

    - 传入 user_id: 关联已有用户（不存在则创建非游客用户）
    - 不传 user_id: 创建游客用户
    """
    token, user_id, is_guest, expires_at = await auth_service.create_session_token(
        user_id=body.user_id,
        nickname=body.nickname,
    )
    return ApiResponse(data=TokenResponse(
        token=token,
        user_id=user_id,
        nickname=body.nickname,
        is_guest=is_guest,
        expires_at=expires_at,
    ))


@router.post("/auth/logout")
async def logout(request: Request):
    """登出 - 撤销当前 token"""
    token = request.headers.get("authorization", "").replace("Bearer ", "").strip()
    if token:
        await auth_service.revoke_session_token(token)
    return ApiResponse(data={"logged_out": True})


@router.get("/auth/me")
async def me(request: Request):
    """获取当前认证用户"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise AuthError("未认证")
    return ApiResponse(data={
        "user_id": user_id,
        "is_authenticated": True,
    })
