"""
知识入库 - 商品向量化 -> PostgreSQL pgvector 写入
"""
import json
import logging
from io import BytesIO
from sqlalchemy import text
from app.services.embedding import embed_batch
from app.core.database import AsyncSessionLocal

logger = logging.getLogger("ingestion")


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
            current = para + "\n"
    if current:
        chunks.append(current.strip())
    return chunks


def parse_document_file(file_bytes: bytes, filename: str) -> str:
    """解析上传文档为纯文本: .txt/.md (UTF-8) / .pdf (pypdf)"""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(file_bytes))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n\n".join(parts)
    if name.endswith(".txt") or name.endswith(".md"):
        return file_bytes.decode("utf-8", errors="replace")
    raise ValueError(f"Unsupported file type: {filename}")


async def ingest_document(
    doc_id: str,
    text_content: str,
    metadata: dict | None = None,
) -> int:
    """
    单文档入库: 切分->向量化->写入 knowledge_chunks 表
    返回 chunk 数量
    """
    chunks = chunk_text(text_content)
    if not chunks:
        logger.warning("No chunks generated for doc_id=%s", doc_id)
        return 0

    if AsyncSessionLocal is None:
        logger.warning("Database not configured, skipping knowledge ingestion for doc_id=%s", doc_id)
        return 0

    vectors = await embed_batch(chunks)
    meta_json = json.dumps(metadata or {}, ensure_ascii=False)

    async with AsyncSessionLocal() as db:
        for idx, (chunk, vec) in enumerate(zip(chunks, vectors)):
            await db.execute(
                text("""
                    INSERT INTO knowledge_chunks (doc_id, chunk_index, chunk_text, embedding, metadata)
                    VALUES (:doc_id, :chunk_index, :chunk_text, :embedding::vector, :metadata::jsonb)
                """),
                {
                    "doc_id": doc_id,
                    "chunk_index": idx,
                    "chunk_text": chunk,
                    "embedding": str(vec),
                    "metadata": meta_json,
                },
            )
        await db.commit()

    logger.info("Ingested doc_id=%s: %d chunks (knowledge_chunks)", doc_id, len(chunks))
    return len(chunks)


async def ingest_knowledge_document(
    doc_id: str,
    text_content: str,
    filename: str,
    metadata: dict | None = None,
) -> int:
    """知识库文档入库: 包装 ingest_document，自动注入 filename 到 metadata"""
    meta = dict(metadata or {})
    meta.setdefault("filename", filename)
    return await ingest_document(doc_id, text_content, meta)


async def ingest_products_from_db(products: list[dict]) -> int:
    """
    批量更新 PostgreSQL products 表的 embedding 列。
    每件商品构造检索文本: title + category + brand + highlights + scenarios + attributes
    """
    if AsyncSessionLocal is None:
        logger.warning("Database not configured, skipping ingestion")
        return 0

    texts = []
    for p in products:
        parts = [p.get("title", ""), p.get("category", ""), p.get("brand", "")]
        parts.extend(p.get("highlights") or [])
        parts.extend(p.get("scenarios") or [])
        if p.get("attributes"):
            parts.extend(str(v) for v in p["attributes"].values())
        texts.append(" ".join(str(x) for x in parts if x))

    vectors = await embed_batch(texts)

    async with AsyncSessionLocal() as db:
        for prod, vec in zip(products, vectors):
            product_uid = prod.get("id") or prod.get("product_id")
            await db.execute(
                text("UPDATE products SET embedding = :vec WHERE source_product_id = :pid"),
                {"vec": str(vec.tolist()), "pid": str(product_uid)},
            )
        await db.commit()

    logger.info("Updated embeddings for %d products in PostgreSQL", len(products))
    return len(products)
