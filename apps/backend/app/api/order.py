"""订单 API 端点 — 下单/查单/取消"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.core.database import get_db
from app.schemas.common import ApiResponse
from app.services import order_service, cart_service

router = APIRouter()


class PlaceOrderRequest(BaseModel):
    session_id: str
    address: str = "默认地址"
    remark: str = ""
    user_id: str = ""
    product_ids: list[str] | None = None


@router.post("/orders")
async def place_order(body: PlaceOrderRequest, db: AsyncSession = Depends(get_db)):
    """下单 — 读取购物车，创建订单，清空购物车"""
    # 读取当前购物车
    items = await cart_service.get_cart(db, body.session_id, body.user_id)
    if body.product_ids:
        selected = set(body.product_ids)
        items = [item for item in items if str(item.product_id) in selected]
    if not items:
        raise HTTPException(status_code=400, detail="购物车为空，无法下单")

    total = sum(float(item.price) * int(item.quantity) for item in items)
    items_snapshot = [
        {
            "product_id": it.product_id,
            "title": it.title,
            "price": it.price,
            "quantity": it.quantity,
        }
        for it in items
    ]

    # 创建订单
    order = await order_service.create_order(
        db, body.session_id, items_snapshot, total, body.address, body.remark
    )

    # 清空购物车
    if body.product_ids:
        for item in items:
            await cart_service.remove_from_cart(db, body.session_id, str(item.product_id), user_id=body.user_id)
    else:
        await cart_service.clear_cart(db, body.session_id, user_id=body.user_id)

    return ApiResponse(data={
        "order_id": str(order.id),
        "order_no": order.order_no,
        "total": order.total,
        "items_count": len(items_snapshot),
        "status": order.status,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    })


@router.get("/orders")
async def list_orders(
    session_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """查询当前会话的所有订单"""
    orders = await order_service.get_orders_by_session(db, session_id)
    return ApiResponse(data={
        "orders": [
            {
                "order_id": str(o.id),
                "order_no": o.order_no,
                "total": o.total,
                "status": o.status,
                "items_count": len(o.items_snapshot) if o.items_snapshot else 0,
                "items_snapshot": o.items_snapshot if o.items_snapshot else [],
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "updated_at": o.updated_at.isoformat() if o.updated_at else None,
            }
            for o in orders
        ]
    })


@router.get("/orders/{order_id}")
async def get_order(order_id: str, db: AsyncSession = Depends(get_db)):
    """查询单个订单详情"""
    order = await order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return ApiResponse(data={
        "order_id": str(order.id),
        "order_no": order.order_no,
        "total": order.total,
        "status": order.status,
        "address": order.address,
        "remark": order.remark,
        "items": order.items_snapshot,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    })


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, db: AsyncSession = Depends(get_db)):
    """取消订单"""
    ok = await order_service.cancel_order(db, order_id)
    if not ok:
        raise HTTPException(status_code=404, detail="订单不存在")
    return ApiResponse(data={"cancelled": True})
