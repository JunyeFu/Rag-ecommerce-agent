"""
First-run auto-import: ensures PostgreSQL products table has embeddings before serving traffic.
Also seeds PostgreSQL products table for REST API queries.

Idempotent - skips if table already contains embeddings. Designed for one-click deploy.
"""
import json
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from huggingface_hub import scan_cache_dir, snapshot_download
from sentence_transformers import SentenceTransformer
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import engine, AsyncSessionLocal
from app.models.product import Product

logger = logging.getLogger("startup")

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR_CANDIDATES = [
    APP_ROOT / "data" / "products",
    REPO_ROOT / "data" / "products",
    REPO_ROOT / "apps" / "data" / "products",
    APP_ROOT / "data" / "qdrant",
    REPO_ROOT / "data" / "qdrant",
    REPO_ROOT / "apps" / "data" / "qdrant",
]
JSONL_PATH = next(
    (
        path / "products_expanded_100.jsonl"
        for path in DATA_DIR_CANDIDATES
        if (path / "products_expanded_100.jsonl").exists()
    ),
    DATA_DIR_CANDIDATES[0] / "products_expanded_100.jsonl",
)


@dataclass
class StartupState:
    phase: str = "initializing"
    db_done: bool = False
    collection_exists: bool = False
    item_count: int = 0
    reranker_warm: bool = False
    message: str = ""
    model_source: str = ""
    model_download_pct: int = 0


_state = StartupState()


def get_startup_state() -> dict:
    return {
        "phase": _state.phase,
        "db_done": _state.db_done,
        "collection_exists": _state.collection_exists,
        "item_count": _state.item_count,
        "reranker_warm": _state.reranker_warm,
        "message": _state.message,
        "model_source": _state.model_source,
        "model_download_pct": _state.model_download_pct,
    }


def _product_id_to_uuid(product_id: str) -> str:
    return str(uuid.uuid5(uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), product_id))


def _build_doc_text(prod: dict) -> str:
    attrs = " ".join(f"{k}:{v}" for k, v in prod.get("attributes", {}).items())
    highlights = " ".join(prod.get("highlights", []))
    scenarios = " ".join(prod.get("scenarios", []))
    description = prod.get("description", "")
    review_texts = prod.get("review_summary", "")
    return (
        f"商品名称: {prod['title']} "
        f"品牌: {prod.get('brand', '')} "
        f"分类: {prod['category']} "
        f"价格: {prod['price']}元 "
        f"评分: {prod['rating']}分 "
        f"属性: {attrs} "
        f"亮点: {highlights} "
        f"场景: {scenarios} "
        f"描述: {description} "
        f"用户评价: {review_texts}"
    )


def _load_products() -> list[dict]:
    """Load product records from the JSONL data file."""
    products = []
    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                products.append(json.loads(line))
    return products


def _check_local_model(model_path: str) -> bool:
    """Check if a local directory contains a valid SentenceTransformer model."""
    if not os.path.isdir(model_path):
        return False
    config = os.path.isfile(os.path.join(model_path, "config.json"))
    if not config:
        return False
    weight_files = [
        f for f in os.listdir(model_path)
        if os.path.isfile(os.path.join(model_path, f))
        and (f.startswith("pytorch_model") or f.startswith("model"))
        and (f.endswith(".bin") or f.endswith(".safetensors"))
    ]
    if weight_files:
        return True
    for entry in os.listdir(model_path):
        subdir = os.path.join(model_path, entry)
        if os.path.isdir(subdir) and os.path.isfile(os.path.join(subdir, "config.json")):
            return True
    return False


def _check_complete_cache(repo_id: str) -> bool:
    """Check if model is fully cached (not just a partial download)."""
    try:
        hf_cache = scan_cache_dir()
        for repo in hf_cache.repos:
            if repo.repo_id == repo_id and repo.size_on_disk > 0:
                return repo.size_on_disk > 1_000_000
        return False
    except Exception:
        return False


def _ensure_model_available():
    """Resolve embedding model: local > cached > download with resume."""
    model_ref = settings.EMBEDDING_MODEL
    repo_id = "BAAI/bge-large-zh-v1.5"

    if os.path.isdir(model_ref) and _check_local_model(model_ref):
        logger.info("Model found locally: %s", model_ref)
        _state.model_source = "local"
        _state.message = f"Model found locally"
        return model_ref

    if _check_complete_cache(repo_id):
        logger.info("Model found in HF cache: %s", repo_id)
        _state.model_source = "cache"
        _state.message = f"Model found in HF cache"
        return repo_id

    _state.phase = "downloading_model"
    _state.model_source = "download"
    _state.model_download_pct = 0
    _state.message = f"Downloading model {repo_id} (resumable)..."
    logger.info("Downloading model %s (resumable, mirror=%s)...", repo_id, settings.HF_ENDPOINT)

    try:
        snapshot_download(
            repo_id=repo_id,
            resume_download=True,
            max_workers=2,
            local_files_only=False,
        )
    except Exception:
        logger.warning("snapshot_download failed, letting SentenceTransformer handle it")
        _state.message = f"snapshot_download failed, falling back to SentenceTransformer"

    _state.model_download_pct = 100
    _state.message = f"Model download complete: {repo_id}"
    _state.phase = "seeding"
    return repo_id


async def _seed_pg_products(products: list[dict]) -> int:
    """将商品数据写入 PostgreSQL products 表（幂等：已存在则跳过）。"""
    if engine is None or AsyncSessionLocal is None:
        logger.warning("Database not configured, skipping PostgreSQL seed")
        return 0

    async with engine.begin() as conn:
        await conn.run_sync(Product.metadata.create_all)
        # 启用 pgvector 扩展
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # 创建全文搜索 tsvector 生成列
        await conn.execute(text("""
            ALTER TABLE products
            ADD COLUMN IF NOT EXISTS search_vector tsvector
            GENERATED ALWAYS AS (
                setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
                setweight(to_tsvector('simple', coalesce(description, '')), 'B') ||
                setweight(to_tsvector('simple', coalesce(category, '')), 'C')
            ) STORED
        """))
        # 创建向量索引 (ivfflat for cosine distance)
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS products_embedding_idx
            ON products USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """))
        # 创建全文搜索索引
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS products_search_vector_idx
            ON products USING gin (search_vector)
        """))

    async with AsyncSessionLocal() as db:
        stmt = select(func.count(Product.id))
        result = await db.execute(stmt)
        existing_count = result.scalar()
        if existing_count >= len(products):
            logger.info("PostgreSQL already has %d products, skipping seed", existing_count)
            _state.db_done = True
            return 0

        existing_result = await db.execute(select(Product.id))
        existing_ids = {str(uid) for uid in existing_result.scalars().all()}

        new_count = 0
        for p in products:
            uid = _product_id_to_uuid(p["product_id"])
            if str(uid) in existing_ids:
                continue
            image_urls = p.get("image_urls") or []
            if not image_urls and p.get("image_url"):
                image_urls = [p["image_url"]]
            db.add(Product(
                id=uuid.UUID(uid),
                title=p["title"][:256],
                description=p.get("description", ""),
                price=float(p.get("price", 0)),
                category=p.get("category", ""),
                brand=p.get("brand", ""),
                rating=float(p.get("rating", 3.0)),
                image_urls=image_urls,
                stock=100,
                sales=0,
                tags=[],
                attributes=p.get("attributes", {}),
                highlights=p.get("highlights", []),
                scenarios=p.get("scenarios", []),
                source_product_id=p["product_id"],
            ))
            new_count += 1

        await db.commit()
        logger.info("PostgreSQL: seeded %d new products (total: %d)", new_count, existing_count + new_count)
        _state.db_done = True
        return new_count


async def _ensure_embeddings(products: list[dict], model) -> int:
    """为缺少 embedding 的商品生成向量并写入 PostgreSQL。"""
    if engine is None or AsyncSessionLocal is None:
        logger.warning("Database not configured, skipping embedding generation")
        return 0

    import asyncio
    loop = asyncio.get_running_loop()

    async with AsyncSessionLocal() as db:
        # 查找缺少 embedding 的商品
        result = await db.execute(
            text("SELECT source_product_id, title, category, brand, highlights, scenarios, attributes FROM products WHERE embedding IS NULL")
        )
        rows = result.fetchall()

    if not rows:
        logger.info("All products already have embeddings, skipping")
        _state.item_count = len(products)
        _state.collection_exists = True
        return 0

    logger.info("Generating embeddings for %d products...", len(rows))

    batch_size = 32
    total_done = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        texts = []
        for row in batch:
            parts = [row.title or "", row.category or "", row.brand or ""]
            parts.extend(list(row.highlights or [])[:5])
            parts.extend(list(row.scenarios or []))
            if row.attributes:
                parts.extend(str(v) for v in row.attributes.values())
            texts.append(" ".join(str(x) for x in parts if x))

        embeddings = await loop.run_in_executor(
            None,
            lambda t=texts: model.encode(t, batch_size=batch_size, normalize_embeddings=True),
        )

        async with AsyncSessionLocal() as db:
            for row, emb in zip(batch, embeddings):
                await db.execute(
                    text("UPDATE products SET embedding = :vec WHERE source_product_id = :pid"),
                    {"vec": str(emb.tolist()), "pid": row.source_product_id},
                )
            await db.commit()

        total_done += len(batch)
        _state.item_count = total_done
        _state.message = f"Vectorized {total_done}/{len(rows)} products"
        logger.info("Auto-import: %s", _state.message)

    _state.collection_exists = True
    return total_done


async def ensure_pgvector_data() -> None:
    """Ensure PostgreSQL products table has embeddings.

    Idempotent: if all products already have embeddings, skips immediately.
    """
    if settings.HF_ENDPOINT:
        os.environ.setdefault("HF_ENDPOINT", settings.HF_ENDPOINT)
        logger.info("HF_ENDPOINT=%s", settings.HF_ENDPOINT)

    if not settings.AUTO_IMPORT_DATA:
        logger.info("AUTO_IMPORT_DATA=false, skipping data seed")
        _state.phase = "ready"
        return

    if not JSONL_PATH.exists():
        logger.warning("Data file not found: %s, skipping auto-import", JSONL_PATH)
        _state.phase = "ready"
        _state.message = f"Data file missing: {JSONL_PATH}"
        return

    products = _load_products()
    if not products:
        logger.warning("No products to import")
        _state.phase = "ready"
        return

    _state.message = f"Loading {len(products)} products..."
    logger.info("Auto-import: loading %d products from %s", len(products), JSONL_PATH)

    # PostgreSQL 入库
    _state.phase = "seeding"
    try:
        pg_count = await _seed_pg_products(products)
        if pg_count > 0:
            logger.info("PostgreSQL seeded %d products", pg_count)
    except Exception as e:
        logger.warning("PostgreSQL seed failed (non-fatal): %s", e)

    # 检查是否需要生成 embeddings
    if engine is None or AsyncSessionLocal is None:
        logger.warning("Database not configured, skipping embedding generation")
        _state.phase = "ready"
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT COUNT(*) FROM products WHERE embedding IS NULL"))
        missing_count = result.scalar()
        total_result = await db.execute(text("SELECT COUNT(*) FROM products"))
        total_count = total_result.scalar()

    if missing_count == 0 and total_count > 0:
        logger.info("All %d products already have embeddings, skipping", total_count)
        _state.item_count = total_count
        _state.collection_exists = True
        _state.phase = "ready"
        _state.message = f"Import complete: {total_count} products with embeddings"
        return

    # 加载 embedding 模型
    model_source = _ensure_model_available()
    import asyncio
    loop = asyncio.get_running_loop()
    model = await loop.run_in_executor(None, lambda: SentenceTransformer(model_source))
    dim = model.get_sentence_embedding_dimension()
    logger.info("Embedding model ready, dim=%d", dim)

    # 注入共享模型实例
    from app.services.embedding import set_shared_model
    set_shared_model(model)

    # 生成并写入 embeddings
    _state.phase = "embedding"
    embedded_count = await _ensure_embeddings(products, model)

    async with AsyncSessionLocal() as db:
        total_result = await db.execute(text("SELECT COUNT(*) FROM products WHERE embedding IS NOT NULL"))
        final_count = total_result.scalar()

    _state.item_count = final_count
    _state.message = f"Import complete: {final_count} products with embeddings"
    logger.info("Auto-import: %s", _state.message)
    _state.phase = "ready"
