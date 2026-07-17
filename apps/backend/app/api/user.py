"""用户 API 端点 — 同步前端 user_profile 表"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.user import UserSyncRequest, UserRead
from app.services import user_service

router = APIRouter()


# 暂不使用前后端用户同步，注释保留以便后续启用
# @router.post("/users/sync")
# async def sync_user(body: UserSyncRequest, db: AsyncSession = Depends(get_db)):
#     """同步前端用户画像到后端（upsert 模式）。
#
#     前端在用户画像变更时调用此接口，保证前后端 user_profile 数据一致。
#     """
#     user = await user_service.create_or_update_user(
#         db,
#         user_id=body.id,
#         nickname=body.nickname,
#         gender=body.gender,
#         age_range=body.age_range,
#         budget_min=body.budget_min,
#         budget_max=body.budget_max,
#         preferred_categories=body.preferred_categories,
#         is_guest=body.is_guest,
#     )
#     return {
#         "user_id": user.id,
#         "nickname": user.nickname,
#         "is_guest": user.is_guest,
#         "updated_at": user.updated_at.isoformat() if user.updated_at else None,
#     }


@router.get("/users/{user_id}")
async def get_user(user_id: str, db: AsyncSession = Depends(get_db)):
    """查询用户画像"""
    user = await user_service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return ApiResponse(data={
        "id": user.id,
        "nickname": user.nickname,
        "gender": user.gender,
        "age_range": user.age_range,
        "budget_min": user.budget_min,
        "budget_max": user.budget_max,
        "preferred_categories": user.preferred_categories,
        "is_guest": user.is_guest,
        "has_avatar": user.avatar is not None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    })
