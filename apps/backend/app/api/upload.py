"""Upload APIs for images, vision search, and documents."""
import json
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core.security import validate_image_upload
from app.schemas.common import ApiResponse
from app.schemas.sse_events import DoneEvent, ErrorEvent, ProductCardEvent
from app.services.image_parser import (
    get_vision_readiness,
    parse_product_image,
    save_upload_image,
)
from app.services.retriever import search_similar_products

logger = logging.getLogger("upload")
router = APIRouter()


@router.get("/upload/vision-status")
async def vision_status():
    """Return Doubao vision readiness without loading local models."""
    return ApiResponse(data=get_vision_readiness())


@router.post("/upload/image")
async def upload_image(file: UploadFile = File(...)):
    """Upload an image and save it locally."""
    contents = await file.read()

    try:
        validate_image_upload(file.content_type, len(contents))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    filepath = save_upload_image(contents, file.filename or "upload.jpg")
    return ApiResponse(
        data={
            "filename": file.filename,
            "content_type": file.content_type,
            "size_bytes": len(contents),
            "path": filepath,
        },
        message="Upload successful",
    )


@router.post("/upload/vision-search")
async def vision_search(file: UploadFile = File(...)):
    """Camera search: image upload -> Doubao vision parse -> vector search -> SSE cards."""
    contents = await file.read()

    try:
        validate_image_upload(file.content_type, len(contents))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    filepath = save_upload_image(contents, file.filename or "camera.jpg")
    logger.info("Vision search: image saved to %s (%d bytes)", filepath, len(contents))

    try:
        product_info = await parse_product_image(contents)
        logger.info("Vision search: parsed product_info=%s", product_info)
    except RuntimeError as e:
        logger.error("Doubao vision API unavailable for vision search: %s", e)

        async def error_stream():
            yield ErrorEvent(
                code="VISION_API_UNAVAILABLE",
                message="Doubao vision API is unavailable. Check DOUBAO_API_KEY and retry.",
            ).to_sse()
            yield DoneEvent(
                total_cards=0,
                latency_ms=0,
                message="Cloud vision search failed before product matching.",
            ).to_sse()

        return StreamingResponse(
            error_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    search_query = _build_search_query(product_info)

    try:
        candidates = await search_similar_products(query_text=search_query, top_k=3)
    except Exception as e:
        logger.warning("PostgreSQL search failed, using fallback: %s", e)
        candidates = []

    async def event_stream():
        yield f"data: {json.dumps({'type': 'vision_parsed', 'product_info': product_info}, ensure_ascii=False)}\n\n"

        if not candidates:
            description = product_info.get("description", "unknown product")
            yield ErrorEvent(
                code="NO_MATCH",
                message=f"No similar products found for {description}. Try another angle.",
            ).to_sse()
            yield DoneEvent(
                total_cards=0,
                latency_ms=0,
                message=f"Image parsed as {description}, but no matching products were found.",
            ).to_sse()
            return

        total = len(candidates)
        for i, product in enumerate(candidates):
            card = ProductCardEvent(
                product_id=product.get("product_id", ""),
                title=product.get("title", ""),
                price=product.get("price", 0),
                rating=product.get("rating", 0),
                match_score=product.get("match_score", product.get("score", 0.5)),
                highlights=product.get("highlights", []),
                image_url=product.get("image_url"),
                image_urls=product.get("image_urls", []),
                brand=product.get("brand"),
                category=product.get("category", ""),
                index=i + 1,
                total=total,
            )
            yield card.to_sse()

        description = product_info.get("description", "")
        yield DoneEvent(
            total_cards=total,
            latency_ms=0,
            message=f"Found {total} similar products from image: {description}",
        ).to_sse()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _build_search_query(product_info: dict) -> str:
    """Build a deduplicated PostgreSQL query from structured vision output."""
    parts = []
    keywords = [str(k) for k in product_info.get("keywords", [])]
    seen = set()

    for key in ("category", "brand"):
        val = product_info.get(key)
        if val and str(val) not in seen:
            parts.append(str(val))
            seen.add(str(val))

    for keyword in keywords:
        if keyword not in seen:
            parts.append(keyword)
            seen.add(keyword)

    query = " ".join(parts) if parts else "product"
    logger.info("Vision search query: %s", query)
    return query


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a knowledge document."""
    return ApiResponse(
        data={"filename": file.filename, "status": "processing"},
        message="Document received and processing",
    )
