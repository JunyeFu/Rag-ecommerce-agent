"""
商品对比接口 - POST /api/products/compare
从 PostgreSQL 检索商品 -> 多维度对比 -> LLM 生成总结
"""
import logging

from fastapi import APIRouter
from app.schemas.common import ApiResponse
from app.schemas.compare import CompareRequest, CompareResult, CompareDimension
from app.services.comparator import compare_products

logger = logging.getLogger("compare_api")

router = APIRouter()


@router.post("/products/compare")
async def compare_products_endpoint(body: CompareRequest):
    """多商品横向对比 - 支持自定义维度或自动推断"""
    result = await compare_products(
        product_ids=body.product_ids,
        dimensions=body.dimensions,
    )

    return ApiResponse(data=CompareResult(
        product_ids=body.product_ids,
        dimensions=[
            CompareDimension(
                name=d["name"],
                values=d["values"],
                winner=d.get("winner"),
            )
            for d in result["dimensions"]
        ],
        summary=result["summary"],
    ))
