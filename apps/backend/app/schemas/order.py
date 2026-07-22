"""订单 Schema - 请求校验"""
from pydantic import BaseModel, Field


class PlaceOrderRequest(BaseModel):
    """下单请求"""
    session_id: str = Field(..., min_length=1)
    address: str = "默认地址"
    remark: str = ""
    user_id: str = ""
    product_ids: list[str] | None = None


class OrderStatusUpdateRequest(BaseModel):
    """订单状态更新请求 - POST body 防止 query 参数泄露到日志/缓存"""
    status: str = Field(..., min_length=1)
