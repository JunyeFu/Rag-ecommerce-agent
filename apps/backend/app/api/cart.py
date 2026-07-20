"""购物车 API 端点"""
import uuid
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.cart import CartAddRequest, CartRemoveRequest, CartQuantityRequest, CartClearRequest
from app.schemas.common import ApiResponse
from app.services import cart_service

router = APIRouter()


def _validate_uuid(value: str, name: str = "session_id") -> uuid.UUID:
    """校验 UUID 格式，无效时返回 400"""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail=f"无效的 {name} 格式: {value}")


@router.get("/cart")
async def get_cart(
    session_id: str = Query(...),
    user_id: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """获取购物车 — 返回商品详情含 image_url/brand/category。
    可选 user_id 用于匹配特定用户的购物车数据。
    """
    _validate_uuid(session_id)
    items = await cart_service.get_cart(db, session_id, user_id)
    total = await cart_service.get_cart_total(db, session_id, user_id)

    cart_items = []
    for i in items:
        from app.services import product_service
        # 直接传原始 product_id，get_product_by_id 内部已支持 UUID / source_product_id 双重查找
        prod = await product_service.get_product_by_id(db, i.product_id)
        cart_items.append({
            "product_id": i.product_id,
            "title": i.title,
            "price": i.price,
            "quantity": i.quantity,
            "image_url": prod.image_urls[0] if (prod and prod.image_urls) else None,
            "brand": prod.brand if prod else None,
            "category": prod.category if prod else "",
        })

    return ApiResponse(data={
        "items": cart_items,
        "total": round(total, 12),
        "count": len(items),
    })


@router.post("/cart/items")
async def add_item(body: CartAddRequest, db: AsyncSession = Depends(get_db)):
    """添加商品到购物车 — 服务端查商品表取真实价格"""
    _validate_uuid(body.session_id)

    # 服务端查商品表，不信任客户端传入的 price/title
    from app.services import product_service
    # 直接传原始 product_id，get_product_by_id 内部已支持 UUID / source_product_id 双重查找
    product = await product_service.get_product_by_id(db, body.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品不存在")

    item = await cart_service.add_to_cart(
        db, body.session_id, body.product_id, product.title, product.price,
        user_id=body.user_id,
    )
    return ApiResponse(data={"id": str(item.id), "quantity": item.quantity})


@router.post("/cart/add")
async def add_item_alias(body: CartAddRequest, db: AsyncSession = Depends(get_db)):
    """[Android 兼容] 添加商品到购物车"""
    return await add_item(body, db)


@router.delete("/cart/items")
async def remove_item(body: CartRemoveRequest, db: AsyncSession = Depends(get_db)):
    """删除购物车商品"""
    _validate_uuid(body.session_id)
    ok = await cart_service.remove_from_cart(db, body.session_id, body.product_id, user_id=body.user_id)
    return ApiResponse(data={"deleted": ok})


@router.post("/cart/remove")
async def remove_item_alias(body: CartRemoveRequest, db: AsyncSession = Depends(get_db)):
    """[Android 兼容] 删除购物车商品"""
    return await remove_item(body, db)


@router.put("/cart/items")
async def update_quantity(body: CartQuantityRequest, db: AsyncSession = Depends(get_db)):
    """修改商品数量"""
    _validate_uuid(body.session_id)
    ok = await cart_service.update_quantity(db, body.session_id, body.product_id, body.quantity, user_id=body.user_id)
    return ApiResponse(data={"updated": ok})


@router.put("/cart/quantity")
async def update_quantity_alias(body: CartQuantityRequest, db: AsyncSession = Depends(get_db)):
    """[Android 兼容] 修改商品数量"""
    return await update_quantity(body, db)


@router.delete("/cart")
async def clear_cart(
    session_id: str = Query(...),
    user_id: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """清空购物车，可选 user_id 仅清空特定用户的商品"""
    _validate_uuid(session_id)
    await cart_service.clear_cart(db, session_id, user_id=user_id)
    return ApiResponse(data={"cleared": True})


@router.post("/cart/clear")
async def clear_cart_alias(body: CartClearRequest, db: AsyncSession = Depends(get_db)):
    """[Android 兼容] 清空购物车"""
    return await clear_cart(session_id=body.session_id, user_id=body.user_id, db=db)
