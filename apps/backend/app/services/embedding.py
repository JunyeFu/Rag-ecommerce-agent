"""
Embedding 封装 — 本地 BGE 模型，异步非阻塞
sentence-transformers 为延迟导入，避免阻塞无 RAG 的启动路径
"""
import asyncio
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger("embedding")

_embedding_model: Any = None  # SentenceTransformer | None


def get_embedding_model():
    """懒加载 embedding 模型 (单例, CPU)，warmup 首次调用"""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer  # lazy import
        logger.info("Loading embedding model: %s (CPU, local)", settings.EMBEDDING_MODEL)
        _embedding_model = SentenceTransformer(
            settings.EMBEDDING_MODEL, device="cpu",
            local_files_only=True,
        )
        # warmup: encode a short text to avoid first-request latency
        _embedding_model.encode("warmup", normalize_embeddings=True)
        logger.info("Embedding model ready, dim=%d", _embedding_model.get_sentence_embedding_dimension())
    return _embedding_model


def set_shared_model(model):
    """注入预加载的模型实例，避免 startup 播种后 API 端点重复加载。

    由 startup.py 在 Qdrant 播种完成后调用，复用已加载的 SentenceTransformer，
    节省 ~1.3GB RAM 和 10-30s 重复加载时间。
    """
    global _embedding_model
    _embedding_model = model
    logger.info("Embedding model injected from startup (shared instance)")


async def embed_text(text: str) -> list[float]:
    """单文本 → 向量 (异步非阻塞)"""
    model = get_embedding_model()
    embedding = await asyncio.to_thread(
        model.encode, text, normalize_embeddings=True
    )
    return embedding.tolist()


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """批量文本 → 向量列表 (异步非阻塞)"""
    if not texts:
        return []
    model = get_embedding_model()
    embeddings = await asyncio.to_thread(
        model.encode, texts, normalize_embeddings=True
    )
    return embeddings.tolist()
