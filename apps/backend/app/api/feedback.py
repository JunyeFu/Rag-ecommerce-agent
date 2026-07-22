"""
反馈接口 - POST /api/feedback
遵循开发规约 v2.0 §3.2: api/ 只处理请求/响应
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.feedback import FeedbackCreate, FeedbackRead
from app.services.feedback_service import record_feedback

router = APIRouter()


@router.post("/feedback")
async def create_feedback(
    body: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
):
    """提交用户反馈 (点赞/点踩)"""
    fb = await record_feedback(
        db=db,
        session_id=body.session_id,
        rating=body.rating,
        product_id=body.product_id,
        reason=body.reason,
    )
    return ApiResponse(data=FeedbackRead.model_validate(fb))
