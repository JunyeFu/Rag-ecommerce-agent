"""商品足迹（浏览历史）API 端点"""
from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.footprints import FootprintRecordRequest
from app.schemas.common import ApiResponse
from app.services import footprint_service

router = APIRouter()


@router.get("/footprints")
async def get_footprints(
    request: Request,
    start_date: str | None = Query(None, description="筛选起始日期，格式 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="筛选结束日期，格式 YYYY-MM-DD"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取用户足迹列表 - 按浏览日期降序，含日期范围筛选。user_id 从 auth token 解析。"""
    user_id = request.state.user_id

    # 解析日期参数
    sd = None
    ed = None
    if start_date:
        try:
            sd = date.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"start_date 格式错误: {start_date}，应为 YYYY-MM-DD")
    if end_date:
        try:
            ed = date.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"end_date 格式错误: {end_date}，应为 YYYY-MM-DD")

    footprints = await footprint_service.get_footprints(
        db, user_id, start_date=sd, end_date=ed, offset=offset, limit=limit
    )
    count = await footprint_service.get_footprint_count(
        db, user_id, start_date=sd, end_date=ed
    )

    items = []
    for fp in footprints:
        # 查询商品详情以返回前端展示所需字段
        from app.services import product_service
        prod = await product_service.get_product_by_id(db, fp.product_id)
        item = {
            "product_id": fp.product_id,
            "browse_date": fp.browse_date.isoformat() if fp.browse_date else None,
            "created_at": fp.created_at.isoformat() if fp.created_at else None,
        }
        if prod:
            item.update({
                "title": prod.title,
                "price": prod.price,
                "brand": prod.brand,
                "category": prod.category,
                "image_url": prod.image_urls[0] if prod.image_urls else None,
                "rating": prod.rating if hasattr(prod, 'rating') else 0,
            })
        items.append(item)

    return ApiResponse(data={
        "items": items,
        "count": len(items),
        "total": count,
    })


@router.get("/footprints/count")
async def get_footprint_count(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """获取用户足迹总数。user_id 从 auth token 解析。"""
    user_id = request.state.user_id
    count = await footprint_service.get_footprint_count(db, user_id)
    return ApiResponse(data={"count": count})


@router.post("/footprints/record")
async def record_footprint(
    body: FootprintRecordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """记录商品浏览足迹。user_id 从 auth token 解析。"""
    user_id = request.state.user_id
    if not body.product_id:
        raise HTTPException(status_code=400, detail="product_id 不能为空")
    result = await footprint_service.record_footprint(db, user_id, body.product_id)
    return ApiResponse(data=result)
