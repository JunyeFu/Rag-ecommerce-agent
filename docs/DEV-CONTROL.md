# DEV-CONTROL - 开发控制文档（唯一权威）

> **本文档是项目开发的唯一权威入口。** 所有技术选型、数据口径、命令参考以本文档为准。
> 其他开发文档均为辅助参考，如与本文档冲突，以本文档为准。
>
> 最后更新：2026-07-18（重构后同步：agent.py 模块化 + 设计模式落地 + 231 单元测试）

---

## 1. 项目概述

| 项目 | 拾物 - RAG 多模态电商导购 AI Agent |
|------|------|
| 仓库 | `git@github.com:fujunye-company/rag-ecommerce-agent.git` |
| 当前状态 | 全栈交付完成，9/9 场景代码就绪 |
| 商品数据 | 287 条商品，94 个细分类目 |
| 客户端 | Android 原生 APK（24.1MB，编译通过） |

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
| LLM | **Doubao-Seed-2.0-lite** | 火山方舟 API（Key 已验证） |
| 前端 | **Kotlin + Jetpack Compose** | Android 原生，73 个 .kt 文件，集中式 ApiClient |
| Python | 3.11+ | 虚拟环境 `.venv`（项目目录内） |

### 设计模式落地

| 模式 | 应用位置 |
|------|----------|
| **Strategy + Factory** | `services/llm/` - LLMProvider 接口 + Doubao/DeepSeek/Mimo 多 Provider 自动检测 |
| **Template Method** | `services/comparison/pipeline.py` - ComparisonPipeline 定义对比骨架 |
| **Strategy** | `services/comparison/strategies.py` - WinnerStrategy（Price/Rating/NumericAttribute/NoWinner） |
| **Protocol 接口** | `core/cache/backend.py` - CacheBackend + InMemoryCache/NoOpCache 可替换 |
| **LazySingleton** | `core/lazy.py` - 通用线程安全延迟加载（替代 5 处重复单例模式） |
| **Facade** | `agent.py`（838行）+ `comparator.py` + `llm_client.py` - 向后兼容重导出 |

> **注意**：项目**未使用 LlamaIndex**。检索管线为自研实现（pgvector 原生 SQL + BGE CrossEncoder + 意图感知多维排序）。

### 核心依赖版本

```
langgraph==1.2.2          langchain==1.3.2         langchain-openai==1.2.2
sentence-transformers==3.4.1    torch==2.12.0
pgvector>=0.3.0,<0.4.0    sqlalchemy[asyncio]==2.0.36
```

### Doubao API 配置

```
Base:  https://ark.cn-beijing.volces.com/api/v3/
Model: ep-20260514111645-lmgt2
Key:   见 apps/backend/.env (DOUBAO_API_KEY)
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
| `web_search` | `agent_nodes/web_search.py` | 视觉搜索（图片上传 -> Doubao vision -> 相似商品检索） |

### 后端模块结构

```
app/services/
├── agent.py (838行 facade)          # route_after_intent + node_cart + generate_response + build_agent_graph
├── agent_streaming.py               # SSE 交错输出辅助
├── agent_state.py                   # AgentState TypedDict
├── slot_management.py (453行)       # 品类推断 + 槽位合并 + 否定过滤（最高 fan-in）
├── cart_nlp.py (425行)             # 购物车 NLP 解析（纯正则）
├── scenario.py                      # 场景化品类映射
├── product_assembly.py              # 商品校验 + 卡片组装
├── prompts.py                       # LLM 生成 prompt 构建
├── agent_nodes/                     # LangGraph 节点包
│   ├── classify.py / clarify.py / retrieve.py
│   ├── generate.py / compare.py / web_search.py
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
├── cache/ (backend.py + query_cache.py)  # CacheBackend Protocol + InMemoryCache
├── config.py                        # model_validator 生产环境守卫（CORS/DB/API Key）
├── database.py                      # DatabaseContext + pool_recycle=3600
├── exceptions.py                    # ValidationError/AuthError/RateLimitError 等
├── lazy.py                          # LazySingleton[T] 通用延迟加载
├── middleware.py                   # RequestIDMiddleware（已激活）
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
| TTFT（首字延迟） | < 1s | ~1.5s |
| SSE 吞吐 | ≥ 20 tok/s | 达标 |
| 检索延迟 | < 2s | ~1s |
| 冷启动 E2E | < 15s | ~11s |
| 热缓存命中 | - | ~16ms |

### 测试

- **单元测试：231 个**（`pytest -m unit`，0.27s，零外部依赖）
- 集成测试：44 个（`pytest -m integration`，需 DB/LLM）
- pytest 标记：`unit` / `integration` / `slow`，CI 分层运行
- 覆盖核心：route_after_intent(26) / comparator(51) / image_parser(20) / cache(40) / retriever_pgvector(29) / intent(20) / product_ranker(11) / cart_nlp(12) / state_slots(14)
- E2E 测试：9 场景全覆盖

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

## 11. 已知技术债

| # | 问题 | 影响 | 优先级 |
|---|------|------|:---:|
| 1 | 品类别名硬编码在 retriever.py `_CATEGORY_ALIASES` | 可维护性 | 低 |
| 2 | `generate_response` 仍 432 行（SSE 编排逻辑密集） | 代码组织 | 低 |
| 3 | 无端点认证体系（所有 API 依赖 session_id 参数，不校验身份） | 安全 | 高（生产前必须补充） |
| 4 | `.env` 中存有明文 API Key（需轮换 + 密钥管理器） | 安全 | 高（用户操作） |
| 5 | DB 密码为弱口令 `shopping123`（需生成强随机密码） | 安全 | 高（用户操作） |
| 6 | 部分 API 集成测试需运行中的 DB/LLM（44 个 integration 标记） | 测试完整性 | 中 |
| 7 | `web_search.py` 中 DDGS 同步调用在 async 函数内（阻塞事件循环） | 性能 | 中 |

---

*本文档由项目维护者创建，是开发的唯一权威入口。如需修改，请提交 PR 并在 commit message 中注明 `docs: update DEV-CONTROL`。*
