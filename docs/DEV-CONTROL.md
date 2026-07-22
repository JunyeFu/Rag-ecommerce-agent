# DEV-CONTROL - 开发控制文档（唯一权威）

> **本文档是项目开发的唯一权威入口。** 所有技术选型、数据口径、命令参考以本文档为准。
> 其他开发文档均为辅助参考，如与本文档冲突，以本文档为准。
>
> 最后更新：2026-07-21（P3 模块化完成 + 448 单元测试 + God File/Function 消除）

---

## 1. 项目概述

| 项目 | 拾物 - RAG 多模态电商导购 AI Agent |
|------|------|
| 仓库 | `git@github.com:fujunye-company/rag-ecommerce-agent.git` |
| 当前状态 | 全栈交付 + P0-P3 质量提升完成，9/9 场景代码就绪 |
| 商品数据 | 287 条商品，94 个细分类目 |
| 客户端 | Android 原生（Kotlin/Compose，82 个 .kt 文件） |

### 功能覆盖

| # | 场景 | 状态 |
|---|------|:---:|
| 1 | 首页对话推荐 | ✅ |
| 2 | 拍照搜物 | ✅ |
| 3 | 商品对比 | ✅ |
| 4 | 购物车管理 | ✅ |
| 5 | 否定语义处理 | ✅ |
| 6 | 多轮追问澄清 | ✅ |
| 7 | 场景化推荐 | ✅ |
| 8 | 语音搜索 | ✅ |
| 9 | 浏览足迹 | ✅ |

---

## 2. 技术栈（唯一权威版本）

| 层 | 技术 | 说明 |
|----|------|------|
| 后端框架 | **FastAPI** | 异步 ASGI，端口 8080，统一 ApiResponse 信封 |
| Agent 编排 | **LangGraph** StateGraph | 7 节点 + 条件路由（recursion_limit=10 安全守卫） |
| 向量库 | **PostgreSQL + pgvector** | 1024-dim，cosine distance，ivfflat 索引 |
| 全文搜索 | **PostgreSQL tsvector** | title(A) + description(B) + category(C) 权重，GIN 索引 |
| Embedding | **BGE-large-zh-v1.5** | 中文语义，CPU 推理，~1.3GB |
| Reranker | **BGE-Reranker-v2-m3** | CrossEncoder，sigmoid 归一化，~2.2GB，失败冷却重试 |
| 数据库 | **PostgreSQL** | 结构化存储 + 向量列 + 全文搜索一体化 |
| LLM | **DeepSeek-V4-Flash** | DeepSeek API（reasoning 已禁用，TTFT ~0.6s） |
| 前端 | **Kotlin + Jetpack Compose** | Android 原生，82 个 .kt 文件，集中式 ApiClient |
| Python | 3.11+ | 虚拟环境 `.venv`（项目目录内） |

### 设计模式落地

| 模式 | 应用位置 |
|------|----------|
| **Strategy + Factory** | `services/llm/` - LLMProvider 接口 + Doubao/DeepSeek/Mimo 多 Provider 自动检测 |
| **Template Method** | `services/comparison/pipeline.py` - ComparisonPipeline 定义对比骨架 |
| **Strategy** | `services/comparison/strategies.py` - WinnerStrategy（Price/Rating/NumericAttribute/NoWinner） |
| **Pipeline + Handler** | `services/pipeline.py` (432行) + `intent_router.py` - generate_response 退化为 40 行调度器 + 9 个 handler |
| **Protocol 接口** | `core/cache/backend.py` - CacheBackend + InMemoryCache(LRU+TTL)/NoOpCache/SlidingWindowRateLimiter |
| **LazySingleton** | `core/lazy.py` - 通用线程安全延迟加载（替代 5 处重复单例模式） |
| **Facade** | `agent.py`（354行）+ `comparator.py` + `llm_client.py` - 向后兼容重导出 |

> **注意**：项目**未使用 LlamaIndex**。检索管线为自研实现（pgvector 原生 SQL + BGE CrossEncoder + 意图感知多维排序）。

### 核心依赖版本

```
langgraph==1.2.2          langchain==1.3.2         langchain-openai==1.2.2
sentence-transformers==3.4.1    torch==2.12.0
pgvector>=0.3.0,<0.4.0    sqlalchemy[asyncio]==2.0.36
```

### LLM API 配置

```
# 当前激活：DeepSeek
Base:  https://api.deepseek.com/v1
Model: deepseek-v4-flash (reasoning disabled, TTFT ~0.6s)
Key:   见 apps/backend/.env (DEEPSEEK_API_KEY)

# 备选：Doubao（DOUBAO_API_KEY 为空时自动 fallback 到 DeepSeek）
Base:  https://ark.cn-beijing.volces.com/api/v3/
Model: ep-20260514111645-lmgt2
```

---

## 3. 环境搭建

> 详细步骤见 [SETUP.md](standards/SETUP.md)（辅助文档）

### 前置条件

- Python 3.11+、Docker 24+、Git 2.40+
- Android Studio + JDK 17（编译前端）
- HuggingFace 模型：BGE-large-zh-v1.5 + BGE-Reranker-v2-m3（共 ~3.5GB）

### 快速启动

```bash
# 1. 启动基础设施（PostgreSQL）
docker compose -f infrastructure/docker-compose.yml up -d

# 2. 配置后端环境
cd apps/backend
cp .env.example .env   # 填入 DOUBAO_API_KEY 等

# 3. 安装依赖
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 4. 启动后端（含自动数据导入 pgvector）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

# 5. 编译 Android
cd apps/android && ./gradlew assembleDebug
```

---

## 4. 关键命令速查

| 操作 | 命令 |
|------|------|
| 启动后端 | `cd apps/backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8080` |
| 启动基础设施 | `docker compose -f infrastructure/docker-compose.yml up -d` |
| 停止基础设施 | `docker compose -f infrastructure/docker-compose.yml down` |
| 手动导入数据 | `cd apps/backend && python -c "from app.startup import ensure_pgvector_data; import asyncio; asyncio.run(ensure_pgvector_data())"` |
| 编译 Android | `cd apps/android && ./gradlew assembleDebug` |
| 健康检查 | `curl http://localhost:8080/health` |
| 就绪检查 | `curl http://localhost:8080/ready` |
| 版本信息 | `curl http://localhost:8080/version` |

### Make 快捷方式

```bash
make install    # 安装 Python 依赖
make dev        # 启动后端开发服务器
make docker-up  # 启动 Docker 基础设施
make test       # 运行测试
make seed       # 数据导入
make clean      # 清理缓存
```

---

## 5. 架构概览

> 详细架构见 [ARCHITECTURE.md](ARCHITECTURE.md)（辅助文档）

### 系统分层

```
Android (Kotlin/Compose)
    ↕ SSE + REST
FastAPI (16 routes)
    ↕
LangGraph StateGraph (7 nodes)
    ↕
RAG Pipeline (embed -> hybrid_search -> rerank -> rank)
    ↕
PostgreSQL + pgvector (向量+结构化+全文搜索) + Doubao LLM
```

### LangGraph 7 节点（已模块化）

| 节点 | 模块 | 职责 |
|------|------|------|
| `classify_intent` | `agent_nodes/classify.py` | LLM 意图分类 + slot 提取 + 否定语义 + query rewrite |
| `clarify` | `agent_nodes/clarify.py` | 追问缺失关键信息 |
| `retrieve` | `agent_nodes/retrieve.py` | RAG 检索（pgvector hybrid + 分级回退 + MMR 采样 + exclusion 过滤 + BGE rerank） |
| `generate` | `agent_nodes/generate.py` | LLM 三段式生成 + 反幻觉约束 + SSE 流式输出 |
| `cart` | `agent.py`（保留，兼容测试 monkeypatch） | 购物车操作 |
| `compare` | `agent_nodes/compare.py` | 商品对比（Template Method 管线） |
| `web_search` | `agent_nodes/web_search.py` | 联网搜索 + 视觉搜索（图片上传 -> LLM vision -> 相似商品检索） |

### 后端模块结构

```
app/services/
├── agent.py (354行 facade)          # route_after_intent + node_cart + build_agent_graph + re-export
├── pipeline.py (432行)              # generate_response 调度器 + 9 个 handler（P3 D1 提取）
├── intent_router.py (81行)          # 4 个意图修正函数（P3 D1 提取）
├── agent_streaming.py               # SSE 交错输出辅助
├── agent_state.py                   # AgentState TypedDict
├── slot_management.py (453行)       # 品类推断 + 槽位合并 + 否定过滤（最高 fan-in）
├── cart_nlp.py (425行)             # 购物车 NLP 解析（纯正则）
├── scenario.py                      # 场景化品类映射
├── product_assembly.py              # 商品校验 + 卡片组装
├── prompts.py                       # LLM 生成 prompt 构建
├── agent_nodes/                     # LangGraph 节点包
│   ├── classify.py / clarify.py / retrieve.py
│   ├── generate.py / compare.py / web_search.py / safety_check.py
├── llm/                             # LLM Strategy + Factory
│   ├── providers.py (Doubao/DeepSeek/Mimo)
│   ├── factory.py / service.py
├── comparison/                      # 对比 Template Method + Strategy
│   ├── pipeline.py / strategies.py / utils.py
├── retriever.py / reranker.py / embedding.py / rag.py
├── product_ranker.py / cart_service.py / comparator.py (facade)
├── image_parser.py / voice_recognition.py / web_search.py
├── exclusion_rules.py / state_manager.py / cache.py (facade)
├── intent.py / ingestion.py / evaluator.py

app/core/
├── cache/ (backend.py + query_cache.py + rate_limiter.py)  # CacheBackend Protocol + InMemoryCache(LRU+TTL) + SlidingWindowRateLimiter
├── config.py                        # model_validator 生产环境守卫（CORS/DB/API Key）+ DeprecatedField 检测
├── database.py                      # DatabaseContext + pool_recycle=3600
├── exceptions.py                    # ValidationError/AuthError/RateLimitError 等
├── lazy.py                          # LazySingleton[T] 通用延迟加载
├── middleware.py                   # AuthMiddleware（强制 401）+ RateLimitMiddleware
├── security.py                     # validate_image_upload（已接入 upload 路由）

app/schemas/ (15 文件)               # cart/favorites/footprints/order 已从路由提取
```

### SSE 事件协议

```
progress -> text_delta (×N) -> product_cards -> done
         ↘ clarify (追问) / error (异常)
```

### RAG 检索管线

```
query -> embed_text (BGE-large-zh)
      -> pgvector hybrid_search (dense vector <=> + tsvector @@  RRF 融合)
      -> 分级回退 (类目+价格 -> 类目 -> 无类目)
      -> 场景分解 + 类目感知 MMR 采样
      -> exclusion 过滤 + 类目守卫
      -> BGE-Reranker-v2-m3 重排
      -> intent-aware 5维加权排序 (semantic*0.4 + price*0.2 + rating*0.15 + brand*0.1 + attributes*0.15)
```

---

## 6. 开发规范

> 详细规范见 [开发规约-v2.md](standards/开发规约-v2.md)（辅助文档）

### 核心红线

1. **禁止编造**不存在的优惠券/功能/价格
2. **禁止使用**纯 Web/H5 客户端
3. **禁止泄露** API Key
4. **禁止忽略**否定语义（"不要红色"-> 必须排除红色商品）
5. **禁止调用** mock 结算做真实支付

### 命名约定

| 语言 | 规范 | 示例 |
|------|------|------|
| Python | snake_case | `product_ranker.py` |
| Kotlin | PascalCase | `ChatViewModel.kt` |
| API | `/api/resource` | `/api/products` |
| 数据库 | 复数表名 | `products`, `categories` |
| Git | `feature/xxx` -> PR -> squash merge | `feature/repo-cleanup` |

### 代码标准

- **注释**：仅在复杂逻辑处添加，禁止冗余注释
- **依赖**：新增依赖必须在 requirements.txt 中声明
- **错误处理**：所有外部调用必须有 try/except + 日志
- **日志**：使用 Python logging，不使用 print
- **提交**：原子提交，一个功能一个 commit

### 性能基准

| 指标 | 目标 | 实际 |
|------|------|------|
| TTFT（首字延迟） | < 1s | ~0.6s（DeepSeek reasoning disabled） |
| SSE 吞吐 | ≥ 20 tok/s | 达标 |
| 检索延迟 | < 2s | ~1s |
| 冷启动 E2E | < 15s | ~11s |
| 热缓存命中 | - | ~16ms |

### 测试

- **单元测试：448 个**（`pytest -m unit`，~23s，零外部依赖）
- 集成/契约/E2E 测试：68 个（`pytest -m integration`，需 DB/LLM）
- pytest 标记：`unit` / `integration` / `contract` / `e2e`，CI 分层运行
- 覆盖核心：route_after_intent(26) / comparator(51) / image_parser(20) / cache(40) / retriever_pgvector(29) / intent(20) / product_ranker(11) / cart_nlp(12) / state_slots(14) / cart_service(19) / order_service(17) / auth_middleware(12) / rate_limiter(7) / product_service(20) / favorite_service(14) / footprint_service(14) / review_service(15)
- service 测试覆盖：13/30 service 模块有专属测试文件（P2 新增 4 个）
- E2E 测试：6 类关键路径（AuthFlow / ProductBrowse / CartFlow / FavoriteFlow / FootprintFlow / OrderFlow）

---

## 7. 数据契约概览

> 详细契约见 [DATA-CONTRACT.md](standards/DATA-CONTRACT.md)（辅助文档）

### Product 实体

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| title | str | 商品标题 |
| description | str | 商品描述 |
| price | numeric | 价格 |
| category | str | 细分类目（94 个） |
| brand | str | 品牌 |
| rating | numeric(3,1) | 评分 |
| image_urls | list[str] | 图片 URL 列表 |
| highlights | list[str] | 亮点 |
| scenarios | list[str] | 适用场景 |
| attributes | JSONB | 扩展属性 |
| stock | int | 库存 |
| tags | list[str] | 标签 |
| embedding | vector(1024) | BGE-large-zh 向量（pgvector） |
| search_vector | tsvector | 全文搜索向量（title A + description B + category C） |

> Python snake_case ↔ Kotlin camelCase 自动映射

### pgvector 存储

- 表名：`products`
- 向量维度：1024（BGE-large-zh-v1.5）
- 距离度量：cosine（`<=>` 操作符）
- 索引：ivfflat（`lists=100`）+ GIN（tsvector）
- 全文搜索：`setweight(title,'A') || setweight(description,'B') || setweight(category,'C')`

### SSE 事件类型

| 事件 | 说明 |
|------|------|
| `progress` | 检索/生成进度 |
| `text_delta` | LLM 流式文本片段 |
| `product_cards` | 推荐商品卡片 |
| `clarify` | 追问用户 |
| `done` | 流结束 |
| `error` | 异常 |

---

## 8. API 概览

> 详细 API 文档见 [API.md](API.md)（辅助文档）
>
> **所有 JSON 端点统一使用 `ApiResponse` 信封**：`{"code":0, "data":..., "message":"ok"}`
> SSE 端点（chat / voice / vision-search）不受信封约束。

| 模块 | 端点 | 说明 |
|------|------|------|
| 对话 | `POST /api/chat` | SSE 流式对话 |
| 商品 | `GET/POST/PUT/DELETE /api/products` | CRUD + 筛选/排序/分页 |
| 购物车 | `GET/POST/DELETE /api/cart` | CRUD（含 Android 兼容别名） |
| 订单 | `POST/GET /api/orders` | 创建/查询订单 |
| 视觉搜索 | `POST /api/upload/vision-search` | 图片上传 -> SSE 商品卡片 |
| 语音 | `POST /api/voice/recognize` `/api/voice/chat` | 语音识别 / SSE 对话 |
| 对比 | `POST /api/products/compare` | 商品对比（Template Method 管线） |
| 反馈 | `POST /api/feedback` | 用户反馈（rating: -1/0/1） |
| 收藏 | `GET/POST /api/favorites` | 收藏管理 |
| 足迹 | `GET/POST /api/footprints` | 浏览足迹 |
| 评价 | `POST/GET /api/reviews` | 商品评价（含图片压缩） |
| 评测 | `POST/GET /api/evaluation` | 系统评测 |
| 健康 | `GET /health /ready /version` | 健康检查（pgvector + DB 双检） |

---

## 9. RAG 调研结论

> 详细报告见 [docs/research/rag-framework-research-report.md](research/rag-framework-research-report.md)

| 决策 | 结论 |
|------|------|
| RAG 框架 | **维持自研，不迁移框架**（LlamaIndex/LangChain/Haystack/RAGFlow 均不适合） |
| 向量库 | **已迁移至 pgvector**（原 Qdrant 已移除，简化架构） |
| 数据存储 | **商品数据存储于 PostgreSQL 结构化表 + pgvector 向量列** |
| 检索策略 | **混合检索（向量 + 结构化过滤 + 全文搜索）是最佳实践** |

---

## 10. 辅助文档索引

> 以下文档为辅助参考，角色已标注。内容如有与本文档冲突，以本文档为准。

### 规范类

| 文档 | 路径 | 角色 |
|------|------|------|
| **开发规约-v2** | `docs/standards/开发规约-v2.md` | 命名/代码/测试/提交详细规范 |
| **DEV-GUIDE** | `docs/standards/DEV-GUIDE.md` | 系统目标与创新约束 |
| **SETUP** | `docs/standards/SETUP.md` | 从零搭建详细指南 |
| **DATA-CONTRACT** | `docs/standards/DATA-CONTRACT.md` | 数据实体与协议规范 |
| **MECHANISM** | `docs/standards/MECHANISM.md` | 全链路机制设计 |
| **DESIGN** | `docs/standards/DESIGN.md` | UI 设计规范 |

### 架构类

| 文档 | 路径 | 角色 |
|------|------|------|
| **ARCHITECTURE** | `docs/ARCHITECTURE.md` | 系统架构详细设计 |
| **API** | `docs/API.md` | 完整 API 接口文档 |
| **项目结构说明** | `docs/architecture/项目结构说明.md` | 历史文档（M1 规划快照） |

### 性能类

| 文档 | 路径 | 角色 |
|------|------|------|
| **PERFORMANCE** | `docs/notes/PERFORMANCE.md` | 性能基准 |
| **TTFT_BENCHMARK** | `docs/optimization/TTFT_BENCHMARK.md` | 延迟与 TTFT 基准 |

### 研究类

| 文档 | 路径 | 角色 |
|------|------|------|
| **RAG 调研报告** | `docs/research/rag-framework-research-report.md` | RAG 框架选型分析 |
| **创新研究** | `docs/optimization/INNOVATION-RESEARCH.md` | 技术创新点研究 |
| **改进设计** | `docs/optimization/IMPROVEMENT-DESIGN-V1.md` | 架构改进设计方案 |

### 背景资料

| 文档 | 路径 | 角色 |
|------|------|------|
| **PRD** | `docs/background/PRD-电商AI导购Agent-V1.0.md` | 产品需求文档 |
| **Agent 框架分析** | `docs/background/Agent框架架构分析.md` | 框架选型分析 |
| **案例分析** | `docs/background/电商RAG导购Agent案例分析.md` | 竞品与案例分析 |
| **学术文献** | `docs/background/PRD-背景资料-学术文献补充.md` | 学术与行业背景 |

### 根目录

| 文档 | 路径 | 角色 |
|------|------|------|
| **README** | `README.md` | 项目 README（对外） |
| **AGENTS / CLAUDE** | `AGENTS.md` / `CLAUDE.md` | AI Agent 上下文（与本文档同步） |

---

## 11. 已知技术债（分级）

> 2026-07-20 基于 Vibe Coding 质量审计刷新。P0 止血已完成（A1-A5），T2/T3/T4/T5/T6/T10/T11 已修复。详细审计依据见 §12。

### CRITICAL（阻塞生产）

| # | 问题 | 位置 | 影响 | 修复方案 |
|---|------|------|------|---------|
| ~~T1~~ | ~~`generate_response` 442 行 God Function~~ | ~~`agent.py:409-851`~~ | ~~7+ early return、深嵌套~~ | ✅ 已拆为 pipeline.py + 9 个 handler，调度器 40 行 |
| T2 | ~~22/30 service 模块零测试~~ ✅ 部分 | `cart_service`/`order_service`/`product_service`/`favorite_service` 等 | 涉及钱、库存、鉴权的核心业务无回归保护 | ✅ `cart_service` +19 测试 / `create_order_atomic` +7 测试（§12.4 A4）。其余 service 待补 |
| T3 | ~~`create_order_atomic` 零测试~~ ✅ | `order_service.py:61-117` | ~~唯一下单事务路径无覆盖~~ | ✅ 7 个测试覆盖空购物车/库存校验/正常下单/product_ids过滤/订单号/精度 |

### HIGH（生产前必修）

| # | 问题 | 位置 | 影响 | 修复方案 |
|---|------|------|------|---------|
| T4 | ~~AuthMiddleware 放行所有业务端点~~ ✅ | ~~`middleware.py:124-159`~~ | ~~无 token 也可调 `/orders`/`/cart`/`/favorites`~~ | ✅ 移除 `AUTH_OPTIONAL_PREFIXES`，强制 401（§12.4 A1） |
| T5 | ~~订单状态无鉴权可突变~~ ✅ | ~~`order.py:118-127`~~ | ~~`?status=completed` 查询参数改状态~~ | ✅ 改 `OrderStatusUpdateRequest` Body + 要求已登录（§12.4 A2） |
| T6 | ~~`.env` 残留死配置~~ ✅ | ~~`.env:3-4`~~ | ~~`QDRANT_URL`/`QDRANT_COLLECTION` 代码 0 引用~~ | ✅ 已删除（§12.4 A3）。Key 轮换待用户操作 |
| T7 | 启动时 12 条裸 SQL 迁移 | `main.py:52-95` | 无 Alembic、无版本号、失败仅 log 后继续 | 引入 Alembic（§12.4 B1） |
| ~~T8~~ | ~~`UserRepository.kt` 1643 行 God File~~ | ~~`data/local/UserRepository.kt`~~ | ~~cart/favorites/footprints/profile/address/order 全塞一文件~~ | ✅ 拆为 6 个 Ext 文件，主文件 596 行 |
| ~~T9~~ | ~~4 处模块级可变 dict 当缓存~~ | ~~`cart_service.py:18`/`auth_service.py:20`/`middleware.py:60`/`state_manager.py:16`~~ | ~~无 TTL/无大小上限/多 worker 不一致~~ | ✅ 统一走 InMemoryCache + SlidingWindowRateLimiter |
| T10 | ~~Cart API 别名复制粘贴~~ ✅ | ~~`cart.py:75-130`~~ | ~~3 个 alias 复制实现而非委托~~ | ✅ 3 个 alias 改为 `return await canonical(...)`（§12.4 A5） |
| T11 | ~~前端 ApiClient 不发 Auth 头~~ ✅ | ~~`ApiClient.kt:18-48`~~ | ~~契约已破，仅因 middleware 放行才"能用"~~ | ✅ `AuthInterceptor` 统一注入 `Authorization` 头（§12.4 A1） |
| T12 | 订单状态跳过 `pending_payment` | `order_service.py:103` | `create_order_atomic` 直接写 `pending_shipping`，状态机初始态不可达 | 修正为 `pending_payment` |
| T13 | 真实 API Key 明文落盘 | `.env:8` | `DEEPSEEK_API_KEY=sk-c11c...` 备份/录屏可泄漏 | 轮换 + 改 `${VAR}` 引用 |

### MEDIUM（后续迭代修复）

| # | 问题 | 位置 | 修复方向 |
|---|------|------|---------|
| T14 | 7 端点绕过 ApiResponse 信封 | `main.py:316/329/347/357`、`upload.py:25` | 统一返 `ApiResponse` 对象 |
| T15 | `products.py` 用 `.model_dump()` 与其他端点不一致 | `products.py:48-97` | 统一返 `ApiResponse` 对象，禁 `.model_dump()` |
| T16 | `_HAS_DB` import 时捕获 | `state_manager.py:19` | 改用 `DatabaseContext` |
| T17 | `cart.py:51` `round(total, 12)` 货币精度无意义 | `cart.py:51` | 改 `round(total, 2)` |
| T18 | 3 处 N+1 查询 | `cart.py:36`、`favorites.py:36`、`footprints.py:59` | 批量 `get_products_by_ids` |
| T19 | `/auth/login` 无速率限制 | `middleware.py:50-57` | 加入 `RATE_LIMIT_CONFIG` |
| T20 | `startup.py:143` 硬编码模型名 | `startup.py:143` | 改用 `settings.EMBEDDING_MODEL` |
| T21 | CORS `["*"]` + 关闭鉴权 | `config.py:52` | 开发环境显式白名单 |
| T22 | `agent.py` re-export 40 个 `_` 前缀私有函数 | `agent.py:35-128` | 调用方直接 import 真实位置 |
| T23 | 12 处函数内 lazy import | `cart.py:36` 等 | 提升到模块级 |
| T24 | `review.py:52-53` 吞异常 | `review.py:52-53` | 改 log + 降级处理 |

### LOW（不阻塞，记录跟踪）

| # | 问题 | 位置 | 修复方向 |
|---|------|------|---------|
| T25 | 品类别名硬编码 | `retriever.py` `_CATEGORY_ALIASES` | 抽到配置 |
| T26 | `web_search.py` DDGS 同步调用在 async 内 | `web_search.py` | 改 `asyncio.to_thread` |
| T27 | 部分 API 集成测试需运行中的 DB/LLM | 68 个 integration/contract/e2e 标记 | docker-compose test 环境 |

---

## 12. Vibe Coding 质量审计与提升路线图

> 2026-07-20 固化。本节基于行业 vibe coding 通病研究 + 全量代码审计，定义从"作品集 demo"到"可维护产品"的质量提升路径。
>
> 审计依据：Wikipedia "Vibe coding" 词条、Veracode 2025 GenAI Code Security Report、CodeRabbit 470 PR 分析、GitClear 2.11 亿行代码纵向研究、METR 随机对照试验 + 本项目全量代码扫描（`apps/backend` ~90 Python 文件 + `apps/android` ~73 Kotlin 文件）。

### 12.1 行业 Vibe Coding 通病映射

| # | 行业通病 | 行业数据 | 本项目是否命中 |
|---|---------|---------|:---:|
| V1 | 安全漏洞 | Veracode: LLM 安全性未改善；Lovable 170/1645 应用泄漏；CodeRabbit: 安全漏洞 2.74x | ✅ 命中（T4/T5/T13） |
| V2 | 代码重复激增 | GitClear: 2021->2024 重复量增 4 倍 | ✅ 命中（T10/cart alias + CartViewModel selectedTotal ~10 处重复） |
| V3 | 重构萎缩 | GitClear: 重构占变更 25%-><10% | ✅ 命中（T1 God Function 未拆） |
| V4 | 重大缺陷率高 | CodeRabbit: AI 协作代码重大问题 1.7x，配置错误多 75% | ✅ 命中（T12 状态机 + T4 鉴权配置） |
| V5 | 可维护性崩塌 | Fast Company "vibe coding hangover"；WSJ "vibe slop 危机" | ✅ 命中（T1/T8 God File/Function） |
| V6 | 复杂任务反降效 | METR RCT: 有经验开发者用 AI +19% 完成时间 | ⚠️ 部分（TTFT 优化已对抗，但 T1 复杂度高） |
| V7 | 技术债复利 | GitClear: code churn 近乎翻倍 | ✅ 命中（T22 re-export 破坏封装） |
| V8 | 测试覆盖断层 | CodeRabbit: AI 代码可读性问题高 | ✅ 命中（T2/T3 核心业务零测试） |

**行业修复共识**（Simon Willison / Ars Technica / IBM Think）：
- **"审查、测试、理解"三件套** -- Willison: "如果 LLM 写了每一行但你审查测试理解了，那不是 vibe coding，是把 LLM 当打字助手"
- **AI 生成代码必须经过等价 Code Review**（CodeRabbit 报告建议）
- **迁移到 ADLC（Agent Development Lifecycle）**（IBM）：结构化、可治理、可追溯
- **护栏优先于自由度**：lint + 类型检查 + 安全扫描 + 契约测试作为硬门禁

### 12.2 项目缺陷分级（审计依据）

> 详细 file:line 可溯源，按严重度分级。完整审计报告见 git 历史 commit。

#### CRITICAL（3 项）

| # | 缺陷 | 位置 |
|---|------|------|
| C1 | `generate_response` 442 行 God Function | `agent.py:409-851` |
| C2 | 22/30 service 模块零测试 | `cart_service`/`order_service`/`product_service` 等 |
| C3 | `create_order_atomic` 零测试 | `order_service.py:61-117` |

#### HIGH（11 项）

| # | 缺陷 | 位置 |
|---|------|------|
| H1 | AuthMiddleware 放行所有业务端点 | `middleware.py:124-159` |
| H2 | 订单状态无鉴权可突变 | `order.py:118-127` |
| H3 | `.env` 残留死配置 `QDRANT_*` | `.env:3-4` |
| H4 | 启动时 12 条裸 SQL 迁移 | `main.py:52-95` |
| H5 | `UserRepository.kt` 1643 行 God File | `data/local/UserRepository.kt` |
| H6 | 4 处模块级可变 dict 当缓存 | `cart_service.py:18`/`auth_service.py:20`/`middleware.py:60`/`state_manager.py:16` |
| H7 | Cart API 别名复制粘贴 | `cart.py:75-130` |
| H8 | `CartViewModel.kt` selectedTotal 计算 ~10 处重复 | `CartViewModel.kt` 多函数 |
| H9 | 前端 ApiClient 不发 Auth 头 | `ApiClient.kt:18-48` |
| H10 | 订单状态跳过 `pending_payment` | `order_service.py:103` |
| H11 | 真实 API Key 明文落盘 | `.env:8` |

### 12.3 AI 协作纪律（反 Vibe Slop）

> 对抗 GitClear 发现的重构萎缩 + Willison 警告的 "vibe slop" 危机。

#### 审查清单（每次 AI 生成代码合入前必过）

- [ ] 我理解这段代码的每一行（Willison 标准）
- [ ] 有对应测试且通过
- [ ] 无安全漏洞（bandit + 人工 review 鉴权/SQL/注入）
- [ ] 无重复实现（grep 同名函数/相似逻辑）
- [ ] 符合 §6 开发规范（行数/参数数/import 规范）
- [ ] 不引入模块级可变状态（T9 对抗）
- [ ] 不绕过 ApiResponse 信封（T14 对抗）

#### AI 协作红线

1. **"Accept All" 禁用** -- AI 生成的 diff 必须逐块审查
2. **重构优先于新增** -- 每个 sprint 至少 20% 时间用于重构（对抗 V3 重构萎缩）
3. **不理解的代码宁可重写也不合入** -- 对抗 V5 可维护性崩塌
4. **安全敏感操作必须双人 review** -- 鉴权/迁移/删库变更（rsync 3.4.1 事件教训）
5. **AI 生成的迁移/脚本必须人工验证** -- 不盲信 LLM 输出

### 12.4 质量提升路线图（P0-P3）

#### P0 止血（✅ 已完成 2026-07-20）

| 步骤 | 动作 | 状态 |
|------|------|------|
| A1 | **启用真实鉴权**：移除 `AUTH_OPTIONAL_PREFIXES`，middleware 强制 401；前端新增 `AuthInterceptor` + `AuthManager` 自动获取/注入 token | ✅ |
| A2 | **订单状态突变改 POST body**：`order.py` `Query(...)` -> `OrderStatusUpdateRequest` Body + 要求已登录 | ✅ |
| A3 | **清理 `.env`**：删 `QDRANT_URL`/`QDRANT_COLLECTION`（key 轮换需用户操作） | ✅ |
| A4 | **补 `cart_service` + `create_order_atomic` 测试**：+26 单元测试（359->385），覆盖缓存/CRUD/原子事务/状态机 | ✅ |
| A5 | **cart API alias 委托**：3 个 alias 改为 `return await canonical(...)` | ✅ |

#### P1 标准化（✅ 2026-07-20，硬门禁已建立）

**B1. 引入 Alembic 迁移框架** ✅
- `alembic init alembic` + async env.py（使用 app.core.database.Base + async_engine）
- 初始迁移 `0001_initial_schema.py`：pgvector 扩展 + Base.metadata.create_all + ivfflat/GIN 索引
- main.py lifespan 12 条裸 SQL 替换为 `alembic upgrade head`，失败则 raise 拒绝启动
- 对现有 DB 执行 `alembic stamp head` 标记 baseline

**B2. 统一 API 契约（5 条硬规则）** ✅（规则 2 后续完善）
1. ✅ 所有业务端点必须返回 `ApiResponse` 对象（13 处 `.model_dump()` 已移除：products/evaluation/voice/upload）
2. ⏳ 所有业务端点必须声明 `response_model=ApiResponse[T]`（需定义泛型类型，后续 P2 完善）
3. ✅ 所有突变操作必须 POST/PATCH/DELETE，禁用 Query 传业务参数（order.py 已在 P0 修复）
4. ✅ 所有端点必须从 `request.state.user_id` 读用户（favorites/footprints/cart 已改，移除 user_id Query）
5. ✅ CI 跑契约测试 `pytest -m contract`（test_api_contract.py：5 端点 401 + ApiResponse 信封验证）

**B3. 环境配置治理** ✅
- `config.py` 增加 `_warn_deprecated_fields` model_validator（QDRANT_URL/COLLECTION 废弃告警）
- `.env.example` 与 `config.py` 字段一一对齐（补齐 RERANKER_MODEL/HF_ENDPOINT/检索配置/DEMO_MODE）
- `.env` 中 key 轮换需用户手动操作（已在 P0 A3 标注）

**B4. CI 硬门禁** ✅（`.github/workflows/ci.yml` 6 job）
```yaml
- lint: ruff check + mypy
- unit-tests: pytest -m unit --cov-fail-under=70
- contract-tests: pytest -m contract (需要 DB)
- integration-tests: pytest -m integration (需要 DB + LLM)
- security: bandit + pip-audit
- migration-check: alembic upgrade head on fresh DB
```
- pyproject.toml 添加 ruff/mypy 配置 + dev 依赖（ruff/mypy/bandit/pip-audit）

#### P2 规范化（✅ 2026-07-20，建立编码规范）

**C1. Python 后端规范** ✅
- ✅ ruff 规则强化: PLR0913(max-args=5) + C901(max-complexity=15) + PLR0912(max-branches=12) + PLR0915(max-statements=50) + PLR0911(max-returns=5)
- ✅ 禁用模块级可变 dict 当缓存 -- 规则已写入 `docs/CODING_STANDARDS.md`，实际迁移在 P3
- ✅ 清理 lazy import: 15 处提升到模块级（cart/favorites/footprints/order_service/intent/reranker/evaluation/review/main/scenario/retriever）
- ✅ 禁用 `_` 前缀函数 re-export -- 规则已写入 CODING_STANDARDS.md，实际迁移在 P3
- ✅ 所有核心 service 有 test: +63 tests (product/favorite/footprint/review_service), 385->448 单元测试
- ✅ CI 覆盖率门禁 ≥ 70% (P1 B4 已配置 --cov-fail-under=70)
- ✅ 编码规范文档: `docs/CODING_STANDARDS.md` (Python + Kotlin + 测试金字塔 + Git + CI)

**C2. Kotlin 前端规范** ✅
- ✅ `CartViewModel.kt`: selectedTotal 计算抽 `calcTotals()` helper, 715->655 行 (-60 行)
- ✅ `ApiClient` 统一注入 Authorization 头 (P0 AuthInterceptor 已实现)
- ✅ UserRepository.kt 拆分 -> P3 模块化阶段执行

**C3. 测试金字塔** ✅
```
        /\
       /e2e\         6 类关键路径 20+ 测试 (pytest -m e2e, 需 DB)
      /------\
     /contract\      API 契约测试 (pytest -m contract)
    /----------\
    / integration\   68 个 (含 contract + e2e, 6 类关键路径)
  /--------------\
  /     unit       \ 448 个 (含 service 层测试)
/------------------\
```

#### P3 模块化（✅ 2026-07-21，消除 God File/Function）

**D1. 拆分 `generate_response`（C1/T1）✅**

443 行 God Function 拆为意图分发 Pipeline 模式：
- `intent_router.py` (96行) - 4 个意图修正函数（cart_keyword/negation/commerce/cart_confirm）
- `pipeline.py` (509行) - PipelineContext + 9 个 handler 异步生成器 + generate_response 调度器
- Handler: demo/cache_hit/chitchat/web_search/cart/compare/clarify/safety_block/retrieve
- `agent.py` 从 851 行降至 411 行，`generate_response` 退化为 40 行调度器
- node_cart 保留在 agent.py（monkeypatch 兼容），pipeline.py 通过 lazy import 调用

**D2. 拆分 `UserRepository.kt`（H5/T8）✅**

1772 行 God File 用 Kotlin 扩展函数拆分，零调用方变更：
- `UserRepository.kt` 596 行（用户画像 + 对话消息 + 设置 + 搜索历史 + 客服 + 嵌套数据类）
- `CartRepositoryExt.kt` 274 行（购物车 CRUD + 后端同步）
- `FavoriteRepositoryExt.kt` 244 行（收藏 CRUD + 后端同步）
- `FootprintRepositoryExt.kt` 182 行（足迹 CRUD + 后端同步）
- `AddressRepositoryExt.kt` 202 行（收货地址 + 支付设置 + 国家地区）
- `OrderRepositoryExt.kt` 209 行（订单记录 + 后端状态同步 + 评价提交）
- `AuthRepositoryExt.kt` 121 行（凭证管理 + 登录状态）
- `db`/`gson` 改为 `internal` 可见性，扩展函数通过 same-module 访问

**D3. 缓存统一（H6/T9）✅**

删除 4 处模块级 dict，全部走 `core/cache/backend.py`：
- `CacheBackend` Protocol 新增 `delete_prefix` 方法
- 新建 `core/cache/rate_limiter.py` - `SlidingWindowRateLimiter` 替代模块级 defaultdict(deque)
- cart_service `_cart_cache` -> `InMemoryCache(max_size=200, default_ttl=300)`
- auth_service `_TOKEN_CACHE` -> `InMemoryCache(max_size=500, default_ttl=1800)`
- middleware `_rate_buckets` -> `SlidingWindowRateLimiter()`
- state_manager `_cache` -> `InMemoryCache(max_size=200, default_ttl=3600)`
- 所有缓存调用从 sync 改为 async（get/set/delete/delete_prefix）

### 12.5 路线图总览

| 阶段 | 周期 | 内容 | 验收指标 |
|------|------|------|---------|
| **P0 止血** | ✅ 2026-07-20 | A1-A5 | 鉴权强制生效、死配置清理、+26 单元测试（359->385）、alias 委托 |
| **P1 标准化** | ✅ 2026-07-20 | B1-B4 | Alembic 迁移可回滚、API 契约信封统一、CI 6-job 硬门禁 |
| **P2 规范化** | ✅ 2026-07-20 | C1-C3 | ruff 规则强化 + 编码规范文档 + +63 service 测试 + CartViewModel helper + e2e 框架 |
| **P3 模块化** | ✅ 2026-07-21 | D1-D3 | generate_response 443->40行、UserRepository.kt 1772->596行、4处模块级dict缓存统一 |
| **持续** | 日常 | §12.3 AI 协作纪律 | 每次合入过审查清单 |

### 12.6 核心结论

1. **本项目是典型 vibe coding 产物**：功能完整（9/9 场景），但存在行业报告的所有通病（V1-V8 全部命中）-- 安全漏洞、代码重复、God File/Function、测试覆盖断层、技术债复利。

2. **行业数据印证风险**：CodeRabbit 报告 AI 协作代码重大问题 1.7x、安全漏洞 2.74x。本项目 T4（鉴权失效）+ T5（无鉴权改订单状态）正是此类高风险缺陷典型。

3. **修复顺序不可颠倒**：**先止血（鉴权 + 死配置 + 关键测试）**，**再标准化（Alembic + CI 门禁）**，**后模块化（拆 God File/Function）**。没有测试和 CI 门禁就重构 God Function，等于在 vibe coding 的地基上盖楼。

4. **长期对抗靠纪律**：Willison 的标准--"审查、测试、理解"--是唯一被行业验证的反 vibe slop 方法。工具（lint/CI/bandit）是硬门禁，纪律（§12.3 清单）是软门禁，两者缺一不可。

---

*本文档由项目维护者创建，是开发的唯一权威入口。如需修改，请提交 PR 并在 commit message 中注明 `docs: update DEV-CONTROL`。*
