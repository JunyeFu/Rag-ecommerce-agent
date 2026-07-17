"""Application settings for the Hermes backend.

Configuration priority:
1. Environment variables
2. apps/backend/.env
3. Code defaults
"""
import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings

CONFIG_DIR = Path(__file__).resolve().parents[2]  # apps/backend/

_HF_EMBEDDING = "BAAI/bge-large-zh-v1.5"
_HF_RERANKER = "BAAI/bge-reranker-v2-m3"


def resolve_model_path(local_path: str, hf_name: str) -> str:
    """Use a local model directory when present; otherwise fall back to HF."""
    if os.path.isdir(local_path):
        return local_path
    return hf_name


class Settings(BaseSettings):
    """Runtime configuration loaded by pydantic-settings."""

    APP_ENV: str = "development"

    DATABASE_URL: str = ""

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "products"

    DOUBAO_API_KEY: str = ""
    DOUBAO_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3/"
    LLM_MODEL: str = ""

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    EMBEDDING_MODEL: str = str(CONFIG_DIR / "data" / "models" / "bge-large-zh-v1.5")
    RERANKER_MODEL: str = str(CONFIG_DIR / "data" / "models" / "bge-reranker-v2-m3")

    HF_ENDPOINT: str = "https://hf-mirror.com"

    AUTO_IMPORT_DATA: bool = True

    LOG_LEVEL: str = "INFO"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8080
    CORS_ORIGINS: list[str] = ["*"]
    MAX_UPLOAD_SIZE_MB: int = 10

    # 检索配置
    RETRIEVAL_TOP_K: int = 20
    RERANKER_TOP_K: int = 10
    HYBRID_SEARCH_ENABLED: bool = True

    # Demo 模式 — 跳过 LLM 调用，仅 Qdrant 检索 + 模板化回复
    DEMO_MODE: bool = False

    @field_validator("EMBEDDING_MODEL", mode="after")
    @classmethod
    def _resolve_embedding(cls, v: str) -> str:
        return resolve_model_path(v, _HF_EMBEDDING)

    @field_validator("RERANKER_MODEL", mode="after")
    @classmethod
    def _resolve_reranker(cls, v: str) -> str:
        return resolve_model_path(v, _HF_RERANKER)

    model_config = {
        "env_file": str(CONFIG_DIR / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
