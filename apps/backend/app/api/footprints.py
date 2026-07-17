"""商品足迹（浏览历史）API 端点"""
from datetime import date
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.footprints import FootprintRecordRequest
from app.schemas.common import ApiResponse
from app.services import footprint_service

router = APIRouter()


@router.get("/footprints")
async def get_footprints(
    user_id: str = Query(...),
    start_date: str | None = Query(None, description="筛选起始日期，格式 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="筛选结束日期，格式 YYYY-MM-DD"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取用户足迹列表 — 按浏览日期降序，含日期范围筛选。

    Args:
        user_id: 用户 ID（必填）
        start_date: 筛选起始日期（含），格式 YYYY-MM-DD，可选
        end_date: 筛选结束日期（含），格式 YYYY-MM-DD，可选
        offset: 分页偏移量，默认 0
        limit: 每页数量，默认 50，最大 100
    """
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id 不能为空")

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
    user_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """获取用户足迹总数。

    Args:
        user_id: 用户 ID（必填）
    """
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id 不能为空")
    count = await footprint_service.get_footprint_count(db, user_id)
    return ApiResponse(data={"count": count})


@router.post("/footprints/record")
async def record_footprint(
    body: FootprintRecordRequest,
    db: AsyncSession = Depends(get_db),
):
    """记录商品浏览足迹。

    - 库中不存在该商品足迹 → 新增记录
    - 库中已存在该商品足迹 → 更新浏览日期

    Args:
        body.user_id: 用户 ID
        body.product_id: 商品 ID
    """
    if not body.user_id or not body.product_id:
        raise HTTPException(status_code=400, detail="user_id 和 product_id 不能为空")
    result = await footprint_service.record_footprint(db, body.user_id, body.product_id)
    return ApiResponse(data=result)
