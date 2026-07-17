"""足迹 Schema - 请求校验"""
from pydantic import BaseModel, Field


class FootprintRecordRequest(BaseModel):
    """记录足迹请求"""
    user_id: str = Field(..., min_length=1)
    product_id: str = Field(..., min_length=1, max_length=64)
