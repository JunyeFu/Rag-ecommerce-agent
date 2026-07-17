"""
FastAPI应用入口 — 电商AI导购系统
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import logging
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import chat, products, upload, evaluation, feedback, compare, knowledge, cart, order, favorites, footprints, user, review, voice
from app.core.config import settings
from app.core.database import engine, Base

# ── 日志配置 ──────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


# ── Lifespan ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表+预热模型，关闭时断开数据库"""
    from app import startup as _startup

    # startup
    # 尽早设置 HF_ENDPOINT — 后续 reranker/embedding 模型加载都依赖此环境变量
    if settings.HF_ENDPOINT:
        import os as _os
        _os.environ.setdefault("HF_ENDPOINT", settings.HF_ENDPOINT)
        logger.info("HF_ENDPOINT=%s", settings.HF_ENDPOINT)

    if settings.DATABASE_URL:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                # 迁移：为已有 cart_items 表添加 user_id 列（v1→v2）
                try:
                    await conn.execute(text(
                        "ALTER TABLE cart_items ADD COLUMN IF NOT EXISTS user_id VARCHAR(64)"
                    ))
                    await conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_cart_items_user_id ON cart_items(user_id)"
                    ))
                    await conn.execute(text(
                        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS audio_data BYTEA"
                    ))
                    await conn.execute(text(
                        "ALTER TABLE products ADD COLUMN IF NOT EXISTS rating_count INTEGER DEFAULT 0"
                    ))
                except Exception as e:
                    logger.debug("Schema migration skipped: %s", e)
            logger.info("数据库表创建/验证完成")
            _startup._state.db_done = True
        except Exception as exc:
            logger.warning("数据库初始化失败（降级运行，购物车/多轮历史暂不可用）: %s", exc)
            # 不 raise — 允许应用在无数据库模式下运行
    else:
        logger.info("DATABASE_URL 未配置，跳过数据库初始化（内存模式）")

    # 并行预热 Reranker + Embedding 模型
    _startup._state.phase = "warming_models"
    try:
        from app.services.reranker import _get_model as _load_reranker
        from app.services.embedding import get_embedding_model as _load_embedding
        await asyncio.gather(
            asyncio.to_thread(_load_reranker),
            asyncio.to_thread(_load_embedding),
        )
        logger.info("Reranker + Embedding models warmed up in parallel")
        _startup._state.reranker_warm = True
    except Exception as e:
        logger.warning("Model warmup skipped: %s", e)

    # 自动数据入库 — 确保 PostgreSQL 有商品向量（幂等）
    await _startup.ensure_pgvector_data()

    # 清空旧缓存 — 确保 top_k 等参数变更后不返回过期数据
    from app.services import cache
    await cache.clear()
    logger.info("Query cache cleared on startup")
    _startup._state.phase = "ready"

    yield
    # shutdown
    try:
        await engine.dispose()
        logger.info("数据库连接已关闭")
    except Exception as exc:
        logger.error("数据库关闭异常: %s", exc)
    try:
        from app.services.llm_client import _client, _fast_client
        if _client:
            await _client.close()
        if _fast_client:
            await _fast_client.close()
        logger.info("LLM HTTP clients closed")
    except Exception as exc:
        logger.error("LLM client cleanup error: %s", exc)


# ── FastAPI app ───────────────────────────────────────────
app = FastAPI(
    title="Hermes 电商AI导购系统",
    description="""基于 RAG 的多模态电商智能导购 AI Agent。

## 核心能力
- **智能导购**: 9 种意图识别（推荐/对比/详情/场景/反选/购物车/拍照找货/售后/闲聊）
- **多轮对话**: 上下文继承、澄清反问、槽位填充
- **拍照找货**: Doubao 视觉 API 图片解析 → 向量检索 → 商品匹配
- **语音输入**: Doubao Chat API input_audio → RAG 导购
- **流式响应**: SSE (Server-Sent Events) 实时推送

## 技术栈
FastAPI + LangGraph + pgvector + Doubao-Seed-2.0 + BGE-large-v1.5""",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — MVP 阶段不传 credentials（避免与 wildcard origin 冲突）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,  # MVP: 移动端 SSE 无需 cookie
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求追踪中间件
from app.core.middleware import RequestIDMiddleware
app.add_middleware(RequestIDMiddleware)

# Prometheus metrics — 所有 HTTP 请求的延迟/计数/错误率
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
except ImportError:
    pass


# ── 异常处理器 ──────────────────────────────────────────────
from app.core.exceptions import AppException
from app.schemas.common import ApiResponse
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """统一应用异常 → {code, message, data}"""
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse(
            code=exc.detail["code"] if isinstance(exc.detail, dict) else 5000,
            message=exc.detail["message"] if isinstance(exc.detail, dict) else str(exc.detail),
            data=None,
        ).model_dump(),
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """将 HTTPException 统一转换为 ApiResponse 格式"""
    return JSONResponse(
        status_code=exc.status_code,
        content=ApiResponse(
            code=exc.status_code * 10,
            message=str(exc.detail) if not isinstance(exc.detail, dict) else exc.detail.get("message", str(exc.detail)),
            data=None,
        ).model_dump(),
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """兜底异常处理器 — 不暴露堆栈，记录请求上下文"""
    import logging
    logger = logging.getLogger("main")
    logger.error(
        "Unhandled exception: %s %s [client=%s] — %s",
        request.method, request.url.path, request.client.host if request.client else "?",
        exc, exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content=ApiResponse(code=5000, message="服务器内部错误", data=None).model_dump(),
    )


# ── 请求耗时中间件 ──────────────────────────────────────────
@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    """记录每个请求的耗时，慢查询警告"""
    import time as _time
    t0 = _time.monotonic()
    response = await call_next(request)
    elapsed_ms = (_time.monotonic() - t0) * 1000
    if elapsed_ms > 3000:
        logger.warning("Slow request: %s %s — %.0fms", request.method, request.url.path, elapsed_ms)
    return response

for prefix in ["/api/v1"]:
    app.include_router(chat.router, prefix=prefix, tags=["chat"])
    app.include_router(products.router, prefix=prefix, tags=["products"])
    app.include_router(upload.router, prefix=prefix, tags=["upload"])
    app.include_router(evaluation.router, prefix=prefix, tags=["evaluation"])
    app.include_router(feedback.router, prefix=prefix, tags=["feedback"])
    app.include_router(compare.router, prefix=prefix, tags=["compare"])
    app.include_router(knowledge.router, prefix=prefix, tags=["knowledge"])
    app.include_router(cart.router, prefix=prefix, tags=["cart"])
    app.include_router(order.router, prefix=prefix, tags=["order"])
    app.include_router(favorites.router, prefix=prefix, tags=["favorites"])
    app.include_router(footprints.router, prefix=prefix, tags=["footprints"])
    app.include_router(user.router, prefix=prefix, tags=["user"])
    app.include_router(review.router, prefix=prefix, tags=["review"])
    app.include_router(voice.router, prefix=prefix, tags=["voice"])

# 商品图片服务 — FastAPI 路由替代 StaticFiles mount
# 解决中文路径 URL 编码兼容性问题（StaticFiles mount 对中文字符处理不一致）
IMAGES_DIR = Path(__file__).resolve().parent.parent / "data" / "images"

if IMAGES_DIR.exists():
    @app.get("/images/{file_path:path}")
    async def serve_image(file_path: str):
        """通过 FastAPI 路由参数（自动 URL 解码）提供商品图片。

        路径格式: /images/<category>/<filename.jpg>
        示例: /images/T恤/p_clothes_021_live.jpg
        FastAPI 自动将 %E6%81%A4 解码为 恤，并传递给 file_path 参数。
        避免 StaticFiles mount 对非 ASCII 路径的处理差异。
        """
        from fastapi.responses import FileResponse

        image_file = (IMAGES_DIR / file_path).resolve()
        if not str(image_file).startswith(str(IMAGES_DIR.resolve())):
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Forbidden")
        if not image_file.exists() or not image_file.is_file():
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Image not found")

        return FileResponse(
            path=str(image_file),
            media_type="image/jpeg" if image_file.suffix.lower() in (".jpg", ".jpeg") else "image/png",
        )

# ── 健康检查 ──────────────────────────────────────────────
@app.get("/health")
async def health():
    """健康检查：验证应用 + 数据库 + pgvector 连通性"""
    db_status = "connected"
    pgvector_status = "unknown"
    embedding_count = 0
    try:
        if engine is None:
            db_status = "not_configured"
            pgvector_status = "not_configured"
        else:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                result = await conn.execute(text("SELECT COUNT(*) FROM products WHERE embedding IS NOT NULL"))
                embedding_count = result.scalar()
                pgvector_status = "ok"
    except Exception as e:
        db_status = "unavailable"
        pgvector_status = f"unavailable: {str(e)[:50]}"

    healthy = db_status == "connected" and pgvector_status == "ok"
    return JSONResponse(status_code=200 if healthy else 503, content={
        "status": "ok" if healthy else "degraded",
        "version": "1.0.0",
        "database": db_status,
        "pgvector": pgvector_status,
        "embedding_count": embedding_count,
    })


# ── 版本信息 ──────────────────────────────────────────────
@app.get("/version")
async def version():
    """返回系统版本及技术栈信息"""
    return {
        "name": "电商AI导购系统",
        "version": "1.0.0",
        "tech_stack": {
            "backend": "FastAPI",
            "llm": "Doubao-Seed-2.0-lite",
        },
    }


# ── 缓存管理 ──────────────────────────────────────────────
@app.post("/api/cache/clear")
async def clear_cache():
    """清空查询缓存 — 参数变更后使用"""
    from app.services import cache
    st = await cache.stats()
    await cache.clear()
    logger.info("Cache cleared via API (was %d entries)", st["size"])
    return {"status": "ok", "cleared": st["size"]}


# ── 就绪检查 ──────────────────────────────────────────────
@app.get("/ready")
async def ready():
    """部署脚本轮询端点 — 返回初始化进度，直到所有组件就绪"""
    from app.startup import get_startup_state
    state = get_startup_state()
    status_code = 200 if state["phase"] == "ready" else 503
    return JSONResponse(status_code=status_code, content={
        "status": state["phase"],
        "progress": {
            "database": state["db_done"],
            "pgvector_ready": state["collection_exists"],
            "embedding_count": state["item_count"],
            "reranker_warm": state["reranker_warm"],
            "model_source": state.get("model_source", ""),
            "model_download_pct": state.get("model_download_pct", 0),
        },
        "message": state["message"],
    })


# ── 根路径 ────────────────────────────────────────────────
@app.get("/")
async def root():
    """根路径：重定向到 /docs 便于开发调试"""
    return RedirectResponse(url="/docs")
 
