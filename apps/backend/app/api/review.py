"""商品评价 API 端点 — 评价增删查"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.common import ApiResponse
from app.services import review_service

router = APIRouter()


@router.post("/reviews")
async def create_review(
    product_id: str = Form(..., description="商品 ID"),
    user_id: str = Form(..., description="用户 ID"),
    nickname: str = Form(default="", description="用户昵称"),
    rating: int = Form(default=5, ge=1, le=5, description="评分（1-5 分）"),
    content: str = Form(default="", description="评价内容"),
    is_anonymous: bool = Form(default=False, description="是否匿名评价"),
    media_files: list[UploadFile] | None = File(default=None, description="图片/视频文件（最多 9 个）"),
    db: AsyncSession = Depends(get_db),
):
    """创建商品评价。

    支持 multipart/form-data 上传图片/视频。
    图片和视频会在服务端进行压缩处理后以二进制大对象存储。
    """
    # 处理上传的媒体文件
    media_bytes: bytes | None = None
    if media_files:
        import io
        from PIL import Image

        all_media = []
        for upload_file in media_files[:9]:  # 最多 9 个文件
            file_bytes = await upload_file.read()
            content_type = upload_file.content_type or ""

            # 对图片进行压缩处理（最大 1024px 宽，JPEG 质量 80%）
            if content_type.startswith("image/"):
                try:
                    img = Image.open(io.BytesIO(file_bytes))
                    # 限制最大尺寸
                    max_size = 1024
                    if img.width > max_size or img.height > max_size:
                        img.thumbnail((max_size, max_size), Image.LANCZOS)
                    # 转为 JPEG 压缩
                    output = io.BytesIO()
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    img.save(output, format="JPEG", quality=80)
                    file_bytes = output.getvalue()
                except Exception:
                    pass  # 非图片文件或处理失败则保持原样

            all_media.append(file_bytes)

        # 多个文件合并为一个 BLOB（用分隔符标识）
        if len(all_media) == 1:
            media_bytes = all_media[0]
        elif len(all_media) > 1:
            # 多个文件：依次拼接，每个文件前 4 字节记录长度
            merged = io.BytesIO()
            for data in all_media:
                merged.write(len(data).to_bytes(4, "big"))
                merged.write(data)
            media_bytes = merged.getvalue()

    # 若用户未编写评价文本，使用默认文本
    final_content = content if content.strip() else "用户未编写评价信息"

    review = await review_service.create_review(
        db,
        product_id=product_id,
        user_id=user_id,
        nickname=nickname,
        rating=rating,
        content=final_content,
        media=media_bytes,
        is_anonymous=is_anonymous,
    )
    return ApiResponse(data={
        "review_id": str(review.id),
        "product_id": review.product_id,
        "rating": review.rating,
        "nickname": review.nickname,
        "review_date": review.review_date.isoformat() if review.review_date else None,
        "message": "评价成功",
    })


@router.get("/reviews/product/{product_id}")
async def list_product_reviews(
    product_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """获取商品评价列表"""
    reviews, total, avg_rating = await review_service.get_reviews_by_product(
        db, product_id, limit=limit, offset=offset
    )
    return ApiResponse(data={
        "reviews": [
            {
                "id": str(r.id),
                "product_id": r.product_id,
                "user_id": r.user_id,
                "nickname": r.nickname,
                "rating": r.rating,
                "content": r.content,
                "has_media": r.media is not None,
                "review_date": r.review_date.isoformat() if r.review_date else None,
                "is_anonymous": r.is_anonymous,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reviews
        ],
        "total": total,
        "average_rating": avg_rating,
    })


@router.get("/reviews/user/{user_id}")
async def list_user_reviews(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """获取用户的所有评价"""
    reviews = await review_service.get_reviews_by_user(db, user_id, limit=limit, offset=offset)
    return ApiResponse(data={
        "reviews": [
            {
                "id": str(r.id),
                "product_id": r.product_id,
                "nickname": r.nickname,
                "rating": r.rating,
                "content": r.content,
                "review_date": r.review_date.isoformat() if r.review_date else None,
                "is_anonymous": r.is_anonymous,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reviews
        ]
    })


@router.get("/reviews/{review_id}")
async def get_review(review_id: str, db: AsyncSession = Depends(get_db)):
    """查询单个评价详情"""
    review = await review_service.get_review(db, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="评价不存在")
    return ApiResponse(data={
        "id": str(review.id),
        "product_id": review.product_id,
        "user_id": review.user_id,
        "nickname": review.nickname,
        "rating": review.rating,
        "content": review.content,
        "has_media": review.media is not None,
        "review_date": review.review_date.isoformat() if review.review_date else None,
        "is_anonymous": review.is_anonymous,
        "created_at": review.created_at.isoformat() if review.created_at else None,
    })
