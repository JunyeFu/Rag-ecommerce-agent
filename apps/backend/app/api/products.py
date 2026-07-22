"""商品API端点 — 纯路由层，委托给 services/product_service"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate, ProductCard
from app.schemas.common import ApiResponse, PaginatedResponse
from app.services.product_service import (
    get_products, get_product_by_id,
    create_product, update_product, delete_product,
)

router = APIRouter()


@router.get("/products")
async def list_products(
    category: str | None = Query(None),
    brand: str | None = Query(None),
    price_min: float | None = Query(None),
    price_max: float | None = Query(None),
    keyword: str | None = Query(None),
    sort_by: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """商品列表 — 支持按品类/品牌/价格/关键词筛选 + 排序 + 分页"""
    products, total = await get_products(
        db=db, category=category, brand=brand,
        price_min=price_min, price_max=price_max,
        keyword=keyword, sort_by=sort_by,
        page=page, size=size,
    )
    items = [
        ProductCard(
            product_id=str(p.id),
            title=p.title,
            price=p.price,
            category=p.category,
            brand=p.brand,
            rating=p.rating or 0,
            image_url=p.image_urls[0] if p.image_urls else None,
            highlights=p.highlights or [],
        ).model_dump(mode="json")
        for p in products
    ]
    return ApiResponse(
        data=PaginatedResponse(items=items, total=total, page=page, size=size)
    )


@router.get("/products/{product_id}")
async def get_product_detail(
    product_id: str,
    db: AsyncSession = Depends(get_db),
):
    """商品详情"""
    product = await get_product_by_id(db, product_id)
    if not product:
        raise NotFoundError(message=f"商品不存在: {product_id}")
    return ApiResponse(data=ProductRead.model_validate(product).model_dump(mode="json"))


@router.post("/products", status_code=201)
async def create_product_endpoint(
    body: ProductCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建商品"""
    product = await create_product(db, body.model_dump())
    return ApiResponse(data=ProductRead.model_validate(product).model_dump(mode="json"))


@router.put("/products/{product_id}")
async def update_product_endpoint(
    product_id: str,
    body: ProductUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新商品（仅更新传入字段）"""
    product = await update_product(db, product_id, body.model_dump(exclude_none=True))
    if not product:
        raise NotFoundError(message=f"商品不存在: {product_id}")
    return ApiResponse(data=ProductRead.model_validate(product).model_dump(mode="json"))


@router.delete("/products/{product_id}")
async def delete_product_endpoint(
    product_id: str,
    db: AsyncSession = Depends(get_db),
):
    """删除商品"""
    success = await delete_product(db, product_id)
    if not success:
        raise NotFoundError(message=f"商品不存在: {product_id}")
    return ApiResponse(data={"deleted": str(product_id)})
