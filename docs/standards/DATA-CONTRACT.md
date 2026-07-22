# 拾物 RAG-Commerce 统一数据契约 v1.0

> **⚠️ 辅助文档** - 开发权威入口为 [`DEV-CONTROL.md`](../DEV-CONTROL.md)，如有冲突以权威文档为准。
>
> 本文档定义全栈唯一权威数据格式。所有后端 API、SSE 事件、pgvector 存储、
> 前端模型、Mock 数据必须遵守此契约。任何偏离均为 Bug。

---

## 1. 核心实体：Product（商品）

### 1.1 后端 Python / JSON API (snake_case)

```python
# 全栈统一字段 — 所有层使用完全相同的语义
ProductRecord = {
    # ── 标识 ──
    "product_id": str,          # 唯一商品ID（必填，非空）

    # ── 基本信息 ──
    "title": str,               # 商品标题（必填）
    "brand": str | None,        # 品牌名
    "category": str,            # 品类（必填，如 "耳机"/"跑鞋"）

    # ── 价格 ──
    "price": float,             # 现价（必填，≥0）

    # ── 评价 ──
    "rating": float,            # 评分 1.0-5.0（必填，默认 3.0）
    "rating_count": int,        # 评价数量（默认 0）

    # ── 描述 ──
    "highlights": list[str],    # 卖点标签 ≤5个（必填，默认 []）
    "attributes": dict[str, str], # 属性键值对（默认 {}，如 {"颜色":"黑","重量":"250g"}）
    "scenarios": list[str],     # 使用场景 ≤5个（默认 []）

    # ── 多媒体 ──
    "image_url": str | None,    # 主图 URL（单张，SSE/卡片用）
    "image_urls": list[str],    # 全部图片 URL（列表，详情页用）

    # ── 来源 ──
    "source": str,              # 数据来源（默认 ""，如 "jd"/"taobao"）

    # ── 检索元数据（后端生成，不出现在种子数据中） ──
    "semantic_score": float,    # 向量检索语义匹配分 0.0-1.0
    "match_score": float,       # 综合匹配度 0.0-1.0（排序后）
    "rank_reason": str,         # 排序理由（≤30字）
}
```

### 1.2 前端 Kotlin (camelCase)

```kotlin
// 与 ProductRecord 一一映射
data class Product(
    val productId: String,          // → product_id
    val title: String,              // → title
    val brand: String?,             // → brand
    val category: String,           // → category
    val price: Double,              // → price
    val rating: Float,              // → rating
    val ratingCount: Int,           // → rating_count
    val highlights: List<String>,   // → highlights
    val attributes: Map<String, String>, // → attributes
    val scenarios: List<String>,    // → scenarios
    val imageUrl: String?,          // → image_url
    val imageUrls: List<String>,    // → image_urls
    val source: String,             // → source
    val matchScore: Double,         // → match_score
    val rankReason: String,         // → rank_reason
)
```

### 1.3 关键改名（对照旧格式）

| 旧字段名 (废弃) | 新字段名 | 说明 |
|----------------|---------|------|
| `id` | `product_id` / `productId` | 统一用 product_id |
| `name` | `title` / `title` | 前后端统一用 title |
| `originalPrice` | 移除 | 不再使用 |
| `salesCount` | `rating_count` / `ratingCount` | 统一命名 |
| `matchReason`(String) | `match_score`(Double) | 数值而非字符串 |
| `colorVariants` | 移除 | 简化为 attributes |
| `image_url` (SSE) | 保留 | SSE 单张用 `image_url` |
| `image_urls` (列表) | 保留 | 详图列表用 `image_urls` |

---

## 2. SSE 事件协议

### 2.1 事件类型

| event 字段 | 含义 | data 载荷 |
|-----------|------|----------|
| `progress` | 流水线进度 | `{"message": "..."}` |
| `text_delta` | LLM 流式增量 | `{"content": "..."}` |
| `product_cards` | 单张商品卡片 | 见 2.2 |
| `clarify` | Agent 主动反问 | `{"question": "...", "missing_slots": [...], "options": [...]}` |
| `done` | 流结束 | `{"total_cards": N, "latency_ms": M}` |
| `error` | 错误 | `{"message": "...", "code": "..."}` |

### 2.2 product_cards 载荷

```json
{
    "product_id": "JD100038798465",
    "title": "Sony WH-1000XM5 无线降噪头戴式耳机",
    "price": 2499.0,
    "rating": 4.7,
    "match_score": 0.92,
    "highlights": ["降噪深度35dB", "30小时续航", "轻量250g"],
    "image_url": "https://...",
    "image_urls": ["https://...", "https://..."],
    "brand": "Sony",
    "category": "耳机",
    "index": 1,
    "total": 5
}
```

### 2.3 前端 SSEEvent 映射

| 后端 event | 前端 SSEEvent 子类 | 映射 |
|-----------|-------------------|------|
| `progress` | `SSEEvent.Progress` | `message` → `message` |
| `text_delta` | `SSEEvent.TextDelta` | `content` → `content` |
| `product_cards` | `SSEEvent.ProductCard` | 见 2.2 → ProductCard |
| `clarify` | `SSEEvent.Clarify` | `question`→`question`, `missing_slots`→`missingSlots`, `options`→`options` |
| `done` | `SSEEvent.Done` | `total_cards`→`totalCards`, `latency_ms`→`latencyMs` |
| `error` | `SSEEvent.Error` | `message` → `message` |

---

## 3. pgvector 存储格式

### 3.1 Table: products

```
维度: 1024 (BAAI/bge-large-zh-v1.5)
向量字段: vector
Row fields: ProductRecord 的全部字段（1.1）
```

### 3.2 索引

```
column index: category, brand, price
```

### 3.3 摄入流程

```
seed_products.json → ProductRecord → embed(title) → pgvector upsert
```

主键使用 `uuid.uuid5(namespace, product_id)` 确定性生成，避免 md5 hash 碰撞。

种子数据文件 (`data/seed_products.json`) 必须使用 ProductRecord 格式。

---

## 4. API 响应格式

### 4.1 /api/v1/products 列表

```json
{
    "code": 200,
    "items": [ /* ProductRecord[] */ ],
    "total": 287,
    "page": 1,
    "size": 20
}
```

### 4.2 /api/v1/products/{id} 详情

```json
{
    "code": 200,
    "data": { /* ProductRecord */ }
}
```

### 4.3 /api/v1/compare 对比

```json
{
    "products": [ /* ProductRecord[] */ ],
    "dimensions": ["价格", "评分", "品牌", "续航", ...],
    "winner": "product_id",
    "summary": "对比总结文本"
}
```

---

## 5. Agent 内部数据流

```
seed_products.json (ProductRecord)
  ↓ embed → pgvector
  ↓ retriever.hybrid_search()
retriever result: {"id": str, "score": float, "row": ProductRecord}
  ↓ agent.py node_retrieve → raw_products
raw_products: ProductRecord + {"semantic_score": float}
  ↓ product_ranker.rank()
ranked: ProductRecord + {"match_score": float, "dimension_scores": dict, "rank_reason": str}
  ↓ agent.py node_generate → cards
cards: ProductRecord + {"match_score": float, "rank_reason": str}
  ↓ SSE product_cards
SSE: ProductRecord 子集 + {"index": int, "total": int}
  ↓ SseClient.parse
SSEEvent.ProductCard
  ↓ ChatViewModel
Product (Kotlin)
```

每一层都是 ProductRecord 的超集/子集，字段语义不变化。

---

## 6. 品类规范

### 6.1 品类规范（94 个细分类，不再分大类）

> 实际种子数据包含 94 个 distinct category 值（如 T恤、手机、耳机、跑鞋、精华液等），
> 通过 `category_mapping.json` 映射到展示大类。详见 `apps/backend/data/seed_products.json`。

旧 `"Electronics/Headphones"` 格式废弃，全改为 `"耳机"`。

---

## 7. 迁移检查清单

- [x] seed_products.json → 改为 ProductRecord 格式 + 新品类名
- [x] pgvector 重建 table + 重新摄入
- [x] ProductSchema (Pydantic) → 对齐 ProductRecord 字段
- [x] ProductCardEvent (SSE) → 补全 image_urls, brand, category
- [x] agent.py raw_products/cards → 统一用 ProductRecord 字段
- [x] retriever.py row fields 读取 → 字段名对齐
- [x] product_ranker.py → 输入输出字段对齐 ProductRecord
- [x] product_service.py → 返回 ProductRecord
- [x] Product.kt → 重写对齐 ProductRecord
- [x] SSEEvent.ProductCard → 字段对齐（已有 imageUrls, brand, category）
- [x] ChatViewModel → Product 构造适配
- [x] MockProducts.kt → 全量重写
- [x] ChatMessage.kt → productCards 字段不变（List<Product>）
- [x] MockChats/MockExplorePosts → 适配新 Product
- [x] 全量编译 + curl SSE 验证
