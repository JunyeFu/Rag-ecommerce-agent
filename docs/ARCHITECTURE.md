# 系统架构 (v5.0)

> **⚠️ 辅助文档** - 开发权威入口为 [`DEV-CONTROL.md`](DEV-CONTROL.md)，如有冲突以权威文档为准。
>
> 课题：基于 RAG 的多模态电商智能导购 AI Agent

---

## 整体架构

```
┌─────────────────────────────────────────────────────────┐
│  Android (Kotlin + Jetpack Compose)                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ │
│  │HomeScreen│ │CompareScreen│ │CartScreen│ │ExploreScreen│
│  └────┬─────┘ └─────┬────┘ └────┬─────┘ └────┬──────┘ │
│       │              │           │            │         │
│  ┌────┴──────────────┴───────────┴────────────┴────┐    │
│  │         ChatViewModel + SseClient (OkHttp)        │    │
│  └────────────────────────┬─────────────────────────┘    │
└───────────────────────────┼──────────────────────────────┘
                            │ SSE (text/event-stream)
                   ┌────────┴────────┐
                   │  FastAPI :8080  │
                   │  /api/v1/chat   │
                   │  /api/v1/upload │
                   │  /api/v1/products│
                   └────────┬────────┘
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                  │
    ┌─────┴─────┐   ┌──────┴──────┐   ┌──────┴──────┐
     │  LangGraph │   │  pgvector   │   │ PostgreSQL  │
     │  编排引擎  │   │  向量存储    │   │  结构化数据  │
    └─────┬─────┘   └──────┬──────┘   └──────┬──────┘
          │                │                  │
    ┌─────┴──────┐   ┌─────┴──────┐           │
    │ Doubao LLM │   │ BGE Embed  │           │
    │Seed-2.0-lite│  │+ Reranker  │           │
    └────────────┘   └────────────┘           │
                                    ┌─────────┴────────┐
                                    │ CartService CRUD │
                                    │ 购物车/下单持久化  │
                                    └──────────────────┘
```

---

## 技术选型

| 层 | 选型 | 理由 |
|----|------|------|
| 客户端 | Android Kotlin + Compose | 原生客户端 |
| 后端框架 | FastAPI | 异步 + SSE EventSourceResponse |
| Agent 编排 | LangGraph | StateGraph + conditional edges |
| 向量库 | pgvector (1024-dim) | PostgreSQL 扩展，统一数据层 |
| 数据库 | PostgreSQL + asyncpg | 会话/商品/购物车持久化 |
| LLM | Doubao-Seed-2.0-lite | TPM 80万，RPM 700 |
| Embedding | BGE-large-zh-v1.5 | 中文电商领域 SOTA |
| Reranker | BGE-Reranker-large | 中文精排提升 |
| 视觉 API | Doubao-Seed-2.0-lite | 拍照找货图像理解 |

---

## Agent 编排 (LangGraph)

```
classify_intent → route_after_intent
    ├→ retrieve → generate (推荐/对比/详情/场景/反选)
    ├→ clarify → generate  (缺失关键信息追问)
    ├→ cart → generate      (购物车 CRUD + 下单)
    └→ generate             (闲聊引导)
```

### 节点说明

| 节点 | 职责 | 关键逻辑 |
|------|------|----------|
| `node_classify_intent` | 意图分类 + 槽位提取 | 9类意图 + 38对品类关键词推理 + 对话历史品类继承 + 品类切换自动重置偏好 + 否定语义解析 |
| `node_clarify` | 缺失信息追问 | LLM 生成自然追问（品类/预算/场景），含 LLM 失败时的模板降级 |
| `node_retrieve` | RAG 检索 + 精排 | pgvector → Reranker → 文本级否定过滤（场景化购物自动分解多类目检索） |
| `product_ranker` | 多维排序 | 语义(40%) × 价格(20%) × 评分(15%) × 品牌(10%) × 属性(15%)，由检索链路调用 |
| `node_generate` | 生成推荐回复 | LLM 三段式推荐 + 反幻觉约束 + 匹配度标注 |
| `node_cart` | 购物车 CRUD | 对话式加购/删除/清空/查看/下单确认（2步流程） |
| `node_compare` | 多商品对比 | 候选商品解析、品牌/品类过滤、维度对比、LLM 对比总结 |
| `node_web_search` | 联网兜底 | 非商品库问题或外部信息查询的降级路径 |

---

## SSE 流式协议

事件序列（v0.3.1 交错格式）：`progress → text_delta → product_cards → text_delta → product_cards → ... → done`

LLM 输出使用结构化标记 `[SUMMARY]` / `[PRODUCT_N]` / `[CLOSING]`，`_emit_interleaved()` 解析后按 摘要 → (商品文本 + 卡片) × N → 结语 交替推送。

| 事件类型 | 方向 | 说明 |
|----------|------|------|
| `progress` | 后端→前端 | 流水线进度：需求分析/检索/排序/生成 |
| `text_delta` | 后端→前端 | 按商品分段发送（非逐 token），每段对应一款商品描述 |
| `product_cards` | 后端→前端 | 单张商品卡片，紧随其对应文本段之后（Top-3） |
| `done` | 后端→前端 | 流结束，含 total_cards + latency_ms |

> 旧格式（全部文本→全部卡片）降级：当缓存返回无 `[PRODUCT_N]` 标记的旧响应时自动触发。

---

## 反幻觉机制

1. **Prompt 禁止清单**：
   - 不得编造商品名称/型号/价格（只能引用 `[1][2]...` 标记的商品）
   - 不得编造优惠券/满减/折扣/赠品/限时活动
   - 不得编造功能参数/认证标识
   - 不得编造用户评价/销量排名/市场占有率

2. **检索结果校验层** (`_validate_ranked_products`)：
   - 过滤缺失 title/product_id 的记录
   - 过滤价格为 0 或负数的无效数据
   - 匹配度低于 25% 强制告知用户"当前没有很匹配的商品"

3. **编号引用**：LLM 回复必须标注 `[1]` `[2]` 编号，未标注的推荐视为无效

---

## 场景覆盖

| # | 场景 | 难度 | 状态 |
|---|------|:--:|:--:|
| 1 | 单轮模糊推荐 | 基础 | ✅ |
| 2 | 条件筛选 | 基础 | ✅ |
| 3 | 多轮追问与细化 | 进阶 | ✅ |
| 4 | 对比决策 | 进阶 | ✅ |
| 5 | Agent 主动反问 | 进阶 | ✅ |
| 6 | 反选/排除约束 | 高级 | ✅ |
| 7 | 场景化组合推荐 | 高级 | ✅ (LLM场景分解+多类目检索) |
| 8 | 购物车与下单 | 高级 | ✅ (对话CRUD+2步下单确认) |
| 9 | 拍照找货（多模态） | 高级 | ✅ (Doubao 视觉 API + 相似检索) |

---

## 加分项实现

| 加分项 | 难度 | 说明 |
|--------|:--:|------|
| 拍照找货 | ⭐⭐⭐ | Doubao 视觉 API 图像理解 → 结构化属性 → pgvector 相似检索 → SSE 流式返回 |
| 多商品对比 | ⭐⭐⭐ | 多维属性提取 + LLM 对比总结 + 维度可视化面板 |
| 反选与排除 | ⭐⭐ | Clarify Chips 反选 + 文本级兜底过滤 + 否定语义解析 |
| 购物车管理 | ⭐⭐ | 对话式 CRUD + 自然语言序号/名称匹配 + 多商品批量操作（索引提取） |
| 下单确认流程 | ⭐⭐⭐ | 订单汇总展示 → "确认下单"确认 → 清空购物车 + 订单号 |
| 多轮上下文记忆 | ⭐ | Session 持久化（SQLite + PostgreSQL）+ 品类上下文继承 + 切换品类自动重置偏好 |
| 场景化组合推荐 | ⭐⭐⭐ | LLM 场景分解 → 多类目并行检索 → 去重合并 → 品类分组推荐 |

---

## 数据流

### 文本聊天
```
用户输入 → ChatInputBar → ChatViewModel.sendMessage()
  → POST /api/v1/chat (JSON {message, conversation_id})
  → LangGraph: intent → retrieve → rerank → rank → generate
  → SSE stream: progress → (text_delta + product_cards) × N → closing_text → done
  → ChatViewModel 逐卡片提交 ChatMessage → UI 实时更新
  → Done 后持久化到 SQLite (用户消息 + 各 AI 回复片段)
```

### 拍照找货
```
相机拍照 → ChatInputBar (Uri → tempFile) → ChatViewModel.sendImage()
  → POST /api/v1/upload/vision-search (multipart/form-data)
  → Doubao 视觉 API 图像理解 → product_info (description/category/attributes)
  → pgvector 相似商品检索 (top_k=3)
  → SSE stream: vision_parsed | product_cards | done
```

### 购物车下单
```
"加入购物车" → intent=cart_operation → node_cart (add)
  → cart_service.add_to_cart(PostgreSQL) → 确认回复

"下单" → cart_action=checkout (is_confirm=false)
  → 展示订单汇总: 商品列表 + 合计金额 + "确认下单"引导

"确认下单" → cart_action=checkout (is_confirm=true)
  → 生成订单号 → 清空购物车 → 下单成功回复
```

---

## 目录映射

```
apps/backend/app/            # 后端服务
├── api/                     # 路由层 (chat/products/upload)
├── core/                    # 基础设施 (config/database/security)
├── models/                  # SQLAlchemy ORM (Product/Session/Cart)
├── schemas/                 # Pydantic (ProductCard/ChatRequest/SSEEvents)
├── services/                # 业务逻辑
│   ├── agent.py             # LangGraph Agent 编排
│   ├── intent.py            # 意图分类
│   ├── retriever.py         # pgvector 检索
│   ├── reranker.py          # BGE 精排
│   ├── product_ranker.py    # 多维排序
│   ├── comparator.py        # 商品对比
│   ├── cart_service.py      # 购物车持久化
│   └── image_parser.py      # Doubao 视觉 API 图像理解
└── data/                    # 数据导入脚本

apps/android/app/src/main/java/com/shopping/agent/
├── ui/                      # Compose 页面
│   ├── screens/             # HomeScreen/CompareScreen/CartScreen/ExploreScreen
│   ├── components/          # StreamingBubble/ProductCard/ChatInputBar
│   └── theme/               # Design tokens
├── data/
│   ├── remote/              # ApiClient + SseClient
│   ├── repository/          # ChatRepository/CompareRepository
│   └── local/               # UserRepository/LocalDatabase (SQLite)
├── viewmodel/               # ChatViewModel/CartViewModel (StateFlow)
└── core/                    # 工具类/常量

docs/                        # 技术文档
├── ARCHITECTURE.md          # 本文档
├── API.md                   # API 接口文档
└── standards/DATA-CONTRACT.md # 数据协议
```

---

## 部署

```bash
# 1. 基础设施
docker compose -f infrastructure/docker-compose.yml up -d postgres

# 2. 数据导入
cd apps/backend && python -c "from app.startup import ensure_pgvector_data; import asyncio; asyncio.run(ensure_pgvector_data())"

# 3. 后端服务
cd apps/backend && uvicorn app.main:app --host 0.0.0.0 --port 8080

# 4. Android 编译
cd apps/android && ./gradlew assembleDebug
```
