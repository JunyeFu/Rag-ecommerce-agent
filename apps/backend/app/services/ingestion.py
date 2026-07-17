"""
知识入库 — 文档→切分→向量化→Qdrant 全流程
"""
import logging
import hashlib
import asyncio
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from app.services.embedding import embed_batch
from app.core.config import settings

logger = logging.getLogger("ingestion")

_qdrant: AsyncQdrantClient | None = None


def _get_qdrant() -> AsyncQdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = AsyncQdrantClient(url=settings.QDRANT_URL)
    return _qdrant


async def ensure_collection(collection_name: str = "", vector_size: int = 1024):
    """确保 Qdrant collection 存在，不存在则创建"""
    name = collection_name or settings.QDRANT_COLLECTION
    client = _get_qdrant()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    if name not in names:
        await client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection: %s (dim=%d)", name, vector_size)


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """语义切分: 按段落/句子边界切分，overlap 滑窗"""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) < chunk_size:
            current += para + "\n"
        else:
            if current:
                chunks.append(current.strip())
            # overlap: 保留当前段落作为下一个 chunk 的起始
            current = para + "\n"
    if current:
        chunks.append(current.strip())
    return chunks


async def ingest_document(
    doc_id: str,
    text: str,
    metadata: dict | None = None,
) -> int:
    """
    单文档入库: 切分→向量化→Qdrant upsert
    返回 chunk 数量
    """
    chunks = chunk_text(text)
    if not chunks:
        logger.warning("No chunks generated for doc_id=%s", doc_id)
        return 0

    vectors = await embed_batch(chunks)
    client = _get_qdrant()
    collection = settings.QDRANT_COLLECTION

    points = []
    for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
        point_id = int(hashlib.md5(f"{doc_id}:{i}".encode()).hexdigest()[:12], 16) % (10**12)
        payload = {"doc_id": doc_id, "chunk_index": i, "text": chunk}
        if metadata:
            payload.update(metadata)
        points.append(PointStruct(id=point_id, vector=vec, payload=payload))

    await client.upsert(collection_name=collection, points=points)
    logger.info("Ingested doc_id=%s: %d chunks → Qdrant", doc_id, len(chunks))
    return len(chunks)


async def ingest_products_from_db(products: list[dict]) -> int:
    """
    从 PostgreSQL 商品数据批量入库 Qdrant。
    每件商品构造检索文本: title + category + brand + highlights + scenarios + attributes
    """
    await ensure_collection()
    client = _get_qdrant()

    texts = []
    for p in products:
        parts = [p.get("title", ""), p.get("category", ""), p.get("brand", "")]
        parts.extend(p.get("highlights") or [])
        parts.extend(p.get("scenarios") or [])
        if p.get("attributes"):
            parts.extend(str(v) for v in p["attributes"].values())
        texts.append(" ".join(str(x) for x in parts if x))

    vectors = await embed_batch(texts)
    collection = settings.QDRANT_COLLECTION

    points = []
    for prod, vec in zip(products, vectors):
        point_id = int(hashlib.md5(str(prod["id"]).encode()).hexdigest()[:12], 16) % (10**12)
        payload = {
            "product_id": str(prod["id"]),
            "title": prod.get("title"),
            "category": prod.get("category"),
            "brand": prod.get("brand"),
            "price": float(prod.get("price", 0)),
            "rating": float(prod.get("rating", 0)),
            "highlights": prod.get("highlights", []),
            "scenarios": prod.get("scenarios", []),
            "attributes": prod.get("attributes", {}),
            "text": texts[i],
        }
        points.append(PointStruct(id=point_id, vector=vec, payload=payload))

    await client.upsert(collection_name=collection, points=points)
    logger.info("Ingested %d products into Qdrant", len(products))
    return len(products)
