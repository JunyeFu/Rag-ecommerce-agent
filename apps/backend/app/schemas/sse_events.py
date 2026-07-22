"""
SSE 事件类型统一维护
遵循开发规约 v2.0 §7.3
"""
import json
from pydantic import BaseModel


class SSEMixin:
    """SSE 序列化混入 — 提供 to_sse() 方法"""

    def to_sse(self) -> str:
        """序列化为 SSE 格式: data: {json}\\n\\n"""
        payload = self.model_dump() if hasattr(self, "model_dump") else self.dict()
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ── MVP 事件 ──
class TextDeltaEvent(BaseModel, SSEMixin):
    type: str = "text_delta"
    content: str


class ProductCardEvent(BaseModel, SSEMixin):
    """单张商品卡片 - 对齐 DATA-CONTRACT.md v1.0 §2.2"""
    type: str = "product_cards"
    product_id: str
    title: str
    price: float = 0
    rating: float = 0
    match_score: float = 0.5
    highlights: list[str] = []
    image_url: str | None = None
    image_urls: list[str] = []
    brand: str | None = None
    category: str = ""
    index: int = 0
    total: int = 0
    citation: list[dict] = []


class DoneEvent(BaseModel, SSEMixin):
    type: str = "done"
    total_cards: int = 0
    latency_ms: int = 0
    message: str = ""
    slots: dict = {}  # 当前会话状态，含 exclude_by_category 等


class ProgressEvent(BaseModel, SSEMixin):
    """流水线进度推送 — 在意图分类/检索/排序各阶段完成后立即推送，提升感知速度"""
    type: str = "progress"
    message: str


class ErrorEvent(BaseModel, SSEMixin):
    type: str = "error"
    message: str
    code: str


# ── 全量扩展 (预留) ──
class IntentEvent(BaseModel, SSEMixin):
    type: str = "intent"
    intent: str
    slots: dict = {}


class RetrievalEvent(BaseModel, SSEMixin):
    type: str = "retrieval"
    chunks: list[dict] = []


class CompareEvent(BaseModel, SSEMixin):
    type: str = "compare"
    dimensions: list[dict] = []


class ScenarioEvent(BaseModel, SSEMixin):
    """场景推荐元数据 — 告知前端场景名、子查询、品类分组"""
    type: str = "scenario"
    scenario: str = ""
    sub_queries: list[str] = []
    category_groups: list[str] = []
    total_products: int = 0


class ClarifyEvent(BaseModel, SSEMixin):
    """Agent 主动反问 — 信息不足时引导细化需求"""
    type: str = "clarify"
    question: str
    missing_slots: list[str] = []
    options: list[str] = []  # 可选引导选项，如 ["拍照", "续航", "性价比"]


class WebSearchResultEvent(BaseModel, SSEMixin):
    """联网搜索结果 — 单条搜索结果的标题+链接+摘要"""
    type: str = "web_search_result"
    title: str
    url: str
    snippet: str
    index: int = 0
    total: int = 0


# ── 联合类型 ──
SSEEvent = TextDeltaEvent | ProductCardEvent | DoneEvent | ErrorEvent | ProgressEvent | ClarifyEvent | WebSearchResultEvent | CompareEvent | ScenarioEvent
