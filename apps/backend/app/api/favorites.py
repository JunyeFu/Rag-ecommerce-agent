"""商品收藏 API 端点"""
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.favorites import FavoriteToggleRequest, FavoriteBatchRemoveRequest
from app.schemas.common import ApiResponse
from app.services import favorite_service

router = APIRouter()


@router.get("/favorites")
async def get_favorites(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取用户收藏列表 - 按收藏时间倒序，含分页。user_id 从 auth token 解析。"""
    user_id = request.state.user_id

    favorites = await favorite_service.get_favorites(db, user_id, offset=offset, limit=limit)
    count = await favorite_service.get_favorite_count(db, user_id)

    items = []
    for fav in favorites:
        # 查询商品详情以返回前端展示所需字段
        from app.services import product_service
        prod = await product_service.get_product_by_id(db, fav.product_id)
        item = {
            "product_id": fav.product_id,
            "created_at": fav.created_at.isoformat() if fav.created_at else None,
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


@router.get("/favorites/check")
async def check_favorite(
    request: Request,
    product_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """检查用户是否已收藏指定商品。user_id 从 auth token 解析。"""
    user_id = request.state.user_id
    if not product_id:
        raise HTTPException(status_code=400, detail="product_id 不能为空")
    is_fav = await favorite_service.is_favorited(db, user_id, product_id)
    return ApiResponse(data={"favorited": is_fav})


@router.get("/favorites/count")
async def get_favorite_count(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """获取用户收藏商品总数。user_id 从 auth token 解析。"""
    user_id = request.state.user_id
    count = await favorite_service.get_favorite_count(db, user_id)
    return ApiResponse(data={"count": count})


@router.post("/favorites/toggle")
async def toggle_favorite(
    body: FavoriteToggleRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """切换收藏状态：已收藏则取消，未收藏则添加。user_id 从 auth token 解析。"""
    user_id = request.state.user_id
    if not body.product_id:
        raise HTTPException(status_code=400, detail="product_id 不能为空")
    result = await favorite_service.toggle_favorite(db, user_id, body.product_id)
    return ApiResponse(data=result)


@router.post("/favorites/remove")
async def batch_remove_favorites(
    body: FavoriteBatchRemoveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """批量移除收藏商品。user_id 从 auth token 解析。"""
    user_id = request.state.user_id
    removed = await favorite_service.remove_favorites(
        db, user_id, body.product_ids
    )
    return ApiResponse(data={"removed": removed})
