"""
First-run auto-import: ensures Qdrant has product vectors before the app serves traffic.
Also seeds PostgreSQL products table for REST API queries.

Idempotent — skips if collection/table already contains data. Designed for one-click deploy.
"""
import json
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
from huggingface_hub import scan_cache_dir, snapshot_download
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from sentence_transformers import SentenceTransformer
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import engine, AsyncSessionLocal
from app.models.product import Product

logger = logging.getLogger("startup")

QDRANT_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR_CANDIDATES = [
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
MAX_RETRIES = 20
RETRY_INTERVAL_S = 6


@dataclass
class StartupState:
    phase: str = "initializing"  # initializing | downloading_model | seeding | warming_reranker | ready
    db_done: bool = False
    collection_exists: bool = False
    item_count: int = 0
    reranker_warm: bool = False
    message: str = ""
    model_source: str = ""  # "local" | "cache" | "download"
    model_download_pct: int = 0  # 0-100 progress during download


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
    return str(uuid.uuid5(QDRANT_NAMESPACE, product_id))


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


def _build_payload(prod: dict) -> dict:
    return {
        "product_id": prod["product_id"],
        "title": prod["title"],
        "category": prod["category"],
        "brand": prod.get("brand", ""),
        "price": prod.get("price", 0),
        "rating": prod.get("rating", 3.0),
        "rating_count": prod.get("rating_count", 0),
        "attributes": prod.get("attributes", {}),
        "highlights": prod.get("highlights", []),
        "scenarios": prod.get("scenarios", []),
        "image_url": prod.get("image_url") or (prod.get("image_urls", [None]) or [None])[0],
        "image_urls": prod.get("image_urls", []),
        "source": prod.get("source", ""),
    }


async def _wait_for_qdrant() -> bool:
    """Wait until Qdrant health check passes or retries exhausted."""
    import asyncio
    for i in range(MAX_RETRIES):
        try:
            r = httpx.get(f"{settings.QDRANT_URL}/healthz", timeout=5.0)
            if r.status_code == 200:
                logger.info("Qdrant reachable after %d retry(s)", i)
                return True
        except Exception:
            pass
        logger.debug("Waiting for Qdrant... (%d/%d)", i + 1, MAX_RETRIES)
        await asyncio.sleep(RETRY_INTERVAL_S)
    return False


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
    """Check if a local directory contains a valid SentenceTransformer model.

    A valid model must have config.json AND at least one model weight file.
    """
    if not os.path.isdir(model_path):
        return False
    config = os.path.isfile(os.path.join(model_path, "config.json"))
    if not config:
        return False
    # Check for model weights: pytorch_model.bin or model.safetensors or 1_Pooling/
    weight_files = [
        f for f in os.listdir(model_path)
        if os.path.isfile(os.path.join(model_path, f))
        and (f.startswith("pytorch_model") or f.startswith("model"))
        and (f.endswith(".bin") or f.endswith(".safetensors"))
    ]
    if weight_files:
        return True
    # SentenceTransformer models may store weights in subdirectories (e.g. 1_Pooling/)
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
                # Check the repo has at least the model weight files (>1MB total)
                # This distinguishes complete from partially downloaded
                return repo.size_on_disk > 1_000_000
        return False
    except Exception:
        return False


def _ensure_model_available():
    """Resolve embedding model: local > cached > download with resume.

    Uses settings.EMBEDDING_MODEL (resolved by config.py) to determine
    the model path/repo. Returns the path/name to pass to SentenceTransformer.
    """
    model_ref = settings.EMBEDDING_MODEL  # Already resolved by resolve_model_path()
    repo_id = "BAAI/bge-large-zh-v1.5"

    # 1. Local path with valid model files — use directly, zero download
    if os.path.isdir(model_ref) and _check_local_model(model_ref):
        logger.info("Model found locally: %s", model_ref)
        _state.model_source = "local"
        _state.message = f"Model found locally"
        return model_ref

    # 2. Check if already complete in HF cache
    if _check_complete_cache(repo_id):
        logger.info("Model found in HF cache: %s", repo_id)
        _state.model_source = "cache"
        _state.message = f"Model found in HF cache"
        return repo_id

    # 3. Download with resume — snapshot_download handles:
    #    - Fresh download, partial resume, or no-op if complete
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
    """将商品数据同时写入 PostgreSQL products 表（幂等：已存在则跳过）。"""
    if engine is None or AsyncSessionLocal is None:
        logger.warning("Database not configured, skipping PostgreSQL seed")
        return 0

    # 确保表已创建
    async with engine.begin() as conn:
        await conn.run_sync(Product.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # 查询已有的 products 数量
        stmt = select(func.count(Product.id))
        result = await db.execute(stmt)
        existing_count = result.scalar()
        if existing_count >= len(products):
            logger.info("PostgreSQL already has %d products, skipping seed", existing_count)
            _state.db_done = True
            return 0

        # 查询已有 ID 集合，避免重复插入
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


async def ensure_qdrant_data() -> None:
    """Ensure Qdrant collection exists and contains product vectors.

    Idempotent: if collection already has data, skips immediately.
    """
    # Apply HuggingFace endpoint override for model downloads (mirror for China)
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

    # Wait for Qdrant
    if not await _wait_for_qdrant():
        logger.error("Qdrant unavailable after %d retries, skipping data import", MAX_RETRIES)
        _state.phase = "ready"
        _state.message = "Qdrant unreachable — data import skipped"
        return

    client = QdrantClient(url=settings.QDRANT_URL, timeout=60)
    try:
        # 先加载数据（Qdrant 和 PostgreSQL 共用）
        products = _load_products()
        if not products:
            logger.warning("No products to import")
            _state.phase = "ready"
            return

        _state.message = f"Loading {len(products)} products..."
        logger.info("Auto-import: loading %d products from %s", len(products), JSONL_PATH)

        # PostgreSQL 入库（独立于 Qdrant，始终尝试）
        _state.phase = "seeding"
        try:
            pg_count = await _seed_pg_products(products)
            if pg_count > 0:
                logger.info("PostgreSQL seeded %d products", pg_count)
        except Exception as e:
            logger.warning("PostgreSQL seed failed (non-fatal): %s", e)

        # Qdrant 入库
        collection_exists = client.collection_exists(settings.QDRANT_COLLECTION)
        if collection_exists:
            count = client.count(collection_name=settings.QDRANT_COLLECTION, exact=True).count
            _state.collection_exists = True
            _state.item_count = count
            if count > 0:
                logger.info("Qdrant collection '%s' already has %d vectors, skipping import",
                            settings.QDRANT_COLLECTION, count)
                _state.phase = "ready"
                _state.message += " (Qdrant already populated)"
                return

        # Need to create and/or populate Qdrant

        # Resolve embedding model — local > HF cache > download with resume
        model_source = _ensure_model_available()

        # Load embedding model
        import asyncio
        loop = asyncio.get_running_loop()
        model = await loop.run_in_executor(
            None,
            lambda: SentenceTransformer(model_source)
        )
        dim = model.get_sentence_embedding_dimension()
        logger.info("Embedding model ready, dim=%d", dim)

        # 注入共享模型实例 — API 端点复用，避免重复加载（省 ~1.3GB RAM + 10-30s）
        from app.services.embedding import set_shared_model
        set_shared_model(model)

        # Create collection if needed
        if not collection_exists:
            client.create_collection(
                collection_name=settings.QDRANT_COLLECTION,
                vectors_config=qdrant_models.VectorParams(
                    size=dim,
                    distance=qdrant_models.Distance.COSINE,
                ),
            )
            logger.info("Collection '%s' created (%d-dim)", settings.QDRANT_COLLECTION, dim)

        # Vectorize + upsert in batches
        batch_size = 32
        for i in range(0, len(products), batch_size):
            batch = products[i:i + batch_size]
            texts = [_build_doc_text(p) for p in batch]
            payloads = [_build_payload(p) for p in batch]

            embeddings = await loop.run_in_executor(
                None,
                lambda t=texts: model.encode(
                    t, batch_size=batch_size, normalize_embeddings=True
                ),
            )

            points = [
                qdrant_models.PointStruct(
                    id=_product_id_to_uuid(p["product_id"]),
                    vector=emb.tolist(),
                    payload=pl,
                )
                for emb, p, pl in zip(embeddings, batch, payloads)
            ]
            client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points)
            _state.item_count = min(i + batch_size, len(products))
            _state.message = f"Vectorized {_state.item_count}/{len(products)} products"
            logger.info("Auto-import: %s", _state.message)

        _state.collection_exists = True
        _state.item_count = client.count(
            collection_name=settings.QDRANT_COLLECTION, exact=True
        ).count
        _state.message = f"Import complete: {_state.item_count} vectors in Qdrant"
        logger.info("Auto-import: %s", _state.message)
    finally:
        client.close()
