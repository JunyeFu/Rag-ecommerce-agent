"""购物车 Schema - 请求校验"""
from pydantic import BaseModel, Field


class CartAddRequest(BaseModel):
    """添加商品到购物车"""
    session_id: str = Field(..., min_length=1)
    product_id: str = Field(..., min_length=1, max_length=64)
    title: str = ""
    price: float = Field(default=0, ge=0)
    user_id: str = ""


class CartRemoveRequest(BaseModel):
    """删除购物车商品"""
    session_id: str = Field(..., min_length=1)
    product_id: str = Field(..., min_length=1, max_length=64)
    user_id: str = ""


class CartQuantityRequest(BaseModel):
    """修改商品数量"""
    session_id: str = Field(..., min_length=1)
    product_id: str = Field(..., min_length=1, max_length=64)
    quantity: int = Field(default=1, ge=1)
    user_id: str = ""


class CartClearRequest(BaseModel):
    """清空购物车"""
    session_id: str = Field(..., min_length=1)
    user_id: str = ""
