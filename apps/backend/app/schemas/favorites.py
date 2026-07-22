"""收藏 Schema - 请求校验"""
from pydantic import BaseModel, Field


class FavoriteToggleRequest(BaseModel):
    """收藏/取消收藏请求"""
    user_id: str = Field(..., min_length=1)
    product_id: str = Field(..., min_length=1, max_length=64)


class FavoriteBatchRemoveRequest(BaseModel):
    """批量移除收藏请求"""
    user_id: str = Field(..., min_length=1)
    product_ids: list[str] = Field(..., min_length=1)
