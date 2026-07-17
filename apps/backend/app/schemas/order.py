"""订单 Schema - 请求校验"""
from pydantic import BaseModel, Field


class PlaceOrderRequest(BaseModel):
    """下单请求"""
    session_id: str = Field(..., min_length=1)
    address: str = "默认地址"
    remark: str = ""
    user_id: str = ""
    product_ids: list[str] | None = None
