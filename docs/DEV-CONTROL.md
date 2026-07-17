# DEV-CONTROL — 开发控制文档（唯一权威）

> **本文档是项目开发的唯一权威入口。** 所有技术选型、数据口径、命令参考以本文档为准。
> 其他开发文档均为辅助参考，如与本文档冲突，以本文档为准。
>
> 最后更新：2026-07-17 | 对应里程碑：M10（全栈交付完成）

---

## 1. 项目概述

| 项目 | 拾物 — RAG 多模态电商导购 AI Agent |
|------|------|
| 赛事 | AI 全栈挑战赛（第3届） |
| 仓库 | `git@github.com:fujunye-company/rag-ecommerce-agent.git` |
| 当前状态 | M0–M10 全部完成，9/9 场景全栈代码就绪 |
| 商品数据 | 287 条商品，94 个细分类目 |
| 客户端 | Android 原生 APK（24.1MB，编译通过） |

### 评分维度（自评）

| 维度 | 权重 | 估计 |
|------|:---:|:--:|
| 基础功能完整性 | 35% | ~33% |
| 工程质量 | 25% | ~23% |
| 效果与可靠性 | 20% | ~17% |
| 加分项深度 | 20% | ~17% |
| **合计** | **100%** | **~90%** |

---

## 2. 技术栈（唯一权威版本）

| 层 | 技术 | 说明 |
|----|------|------|
| 后端框架 | **FastAPI** | 异步 ASGI，端口 8080 |
| Agent 编排 | **LangGraph** StateGraph | 7 节点 + 条件路由（非 LangChain AgentExecutor） |
| 向量库 | **Qdrant** | 1024-dim，collection=products，HNSW 索引 |
| Embedding | **BGE-large-zh-v1.5** | 中文语义，CPU 推理，~1.3GB |
| Reranker | **BGE-Reranker-v2-m3** | CrossEncoder，sigmoid 归一化，~2.2GB |
| 数据库 | **PostgreSQL + pgvector** | pgvector 已在依赖中但暂未作为主向量库 |
| LLM | **Doubao-Seed-2.0-lite** | 火山方舟 API（Key 已验证） |
| 前端 | **Kotlin + Jetpack Compose** | Android 原生，73 个 .kt 文件 |
| Python | 3.11 | 虚拟环境 `~/.hermes-venv` |

> **注意**：项目**未使用 LlamaIndex**。检索管线为自研实现（Qdrant 原生 API + BGE CrossEncoder + 意图感知多维排序）。

### 核心依赖版本

```
langgraph==1.2.2          langchain==1.3.2         langchain-openai==1.2.2
qdrant-client==1.18.0     sentence-transformers==3.4.1    torch==2.12.0
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
# 1. 启动基础设施
docker compose -f infrastructure/docker-compose.yml up -d

# 2. 配置后端环境
cd apps/backend
cp .env.example .env   # 填入 DOUBAO_API_KEY 等

# 3. 安装依赖
python -m venv ~/.hermes-venv && source ~/.hermes-venv/bin/activate  # Windows: ~/.hermes-venv\Scripts\activate
pip install -r requirements.txt

# 4. 启动后端（含自动数据导入 Qdrant）
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
| 手动导入 Qdrant | `cd apps/backend && python -c "from app.startup import ensure_qdrant_data; import asyncio; asyncio.run(ensure_qdrant_data())"` |
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
RAG Pipeline (embed → hybrid_search → rerank → rank)
    ↕
Qdrant (向量) + PostgreSQL (结构化) + Doubao LLM
```

### LangGraph 7 节点

| 节点 | 职责 |
|------|------|
| `classify_intent` | LLM 意图分类 + slot 提取 + 否定语义 + query rewrite |
| `clarify` | 追问缺失关键信息 |
| `retrieve` | RAG 检索（Qdrant hybrid + 分级回退 + MMR 采样 + exclusion 过滤 + BGE rerank） |
| `generate` | LLM 三段式生成 + 反幻觉约束 + SSE 流式输出 |
| `cart` | 购物车操作 |
| `compare` | 商品对比 |
| `web_search` | 视觉搜索（图片上传 → Doubao vision → 相似商品检索） |

### SSE 事件协议

```
progress → text_delta (×N) → product_cards → done
         ↘ clarify (追问) / error (异常)
```

### RAG 检索管线

```
query → embed_text (BGE-large-zh)
      → Qdrant hybrid_search (dense + keyword RRF 融合)
      → 分级回退 (类目+价格 → 类目 → 无类目)
      → 场景分解 + 类目感知 MMR 采样
      → exclusion 过滤 + 类目守卫
      → BGE-Reranker-v2-m3 重排
      → intent-aware 5维加权排序 (semantic*0.4 + price*0.2 + rating*0.15 + brand*0.1 + attributes*0.15)
```

---

## 6. 开发规范

> 详细规范见 [开发规约-v2.md](standards/开发规约-v2.md)（辅助文档）

### 核心红线

1. **禁止编造**不存在的优惠券/功能/价格
2. **禁止使用**纯 Web/H5 客户端
3. **禁止泄露** API Key
4. **禁止忽略**否定语义（"不要红色"→ 必须排除红色商品）
5. **禁止调用** mock 结算做真实支付

### 命名约定

| 语言 | 规范 | 示例 |
|------|------|------|
| Python | snake_case | `product_ranker.py` |
| Kotlin | PascalCase | `ChatViewModel.kt` |
| API | `/api/resource` | `/api/products` |
| 数据库 | 复数表名 | `products`, `categories` |
| Git | `feature/xxx` → PR → squash merge | `feature/repo-cleanup` |

### 代码标准

- **注释**：仅在复杂逻辑处添加，禁止冗余注释
- **依赖**：新增依赖必须在 requirements.txt 中声明
- **错误处理**：所有外部调用必须有 try/except + 日志
- **日志**：使用 Python logging，不使用 print
- **提交**：原子提交，一个功能一个 commit

### 性能要求

| 指标 | 目标 | 实际 |
|------|------|------|
| TTFT（首字延迟） | < 1s | ~1.5s |
| SSE 吞吐 | ≥ 20 tok/s | 达标 |
| 检索延迟 | < 2s | ~1s |
| 冷启动 E2E | < 15s | ~11s |
| 热缓存命中 | - | ~16ms |

### 测试要求

- 单元测试：≥ 5 个 pytest 用例
- 集成测试：curl 命令覆盖核心 API
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

> Python snake_case ↔ Kotlin camelCase 自动映射

### Qdrant 存储

- 集合名：`products`
- 向量维度：1024
- Point ID：UUID5（基于 product_id）
- Payload：product 全字段

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

| 模块 | 端点 | 说明 |
|------|------|------|
| 对话 | `POST /api/chat` | SSE 流式对话 |
| 商品 | `GET/POST/PUT/DELETE /api/products` | CRUD + 筛选/排序/分页 |
| 购物车 | `GET/POST/DELETE /api/cart` | CRUD（含 Android 兼容别名） |
| 订单 | `POST /api/orders` | 创建订单 |
| 视觉搜索 | `POST /api/upload` | 图片上传 → 相似商品 |
| 语音 | `POST /api/voice/recognize` | 语音识别 |
| 对比 | `GET /api/compare` | 商品对比 |
| 反馈 | `POST /api/feedback` | 用户反馈 |
| 收藏 | `GET/POST/DELETE /api/favorites` | 收藏管理 |
| 足迹 | `GET /api/footprints` | 浏览足迹 |
| 评测 | `GET /api/evaluation` | 系统评测 |
| 知识 | `POST /api/knowledge/ingest` | 知识导入 |
| 缓存 | `POST /api/cache/clear` | 清除缓存 |
| 健康 | `GET /health /ready /version` | 健康检查 |

---

## 9. 9 场景覆盖

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

## 10. RAG 调研结论

> 详细报告见 [docs/research/rag-framework-research-report.md](research/rag-framework-research-report.md)

| 决策 | 结论 |
|------|------|
| RAG 框架 | **维持自研，不迁移框架**（LlamaIndex/LangChain/Haystack/RAGFlow 均不适合） |
| 向量库 | **短期维持 Qdrant，赛后迁移 pgvector** |
| 数据存储 | **商品数据应迁移到 PostgreSQL 结构化表 + pgvector 向量列** |
| 检索策略 | **混合检索（向量 + 结构化过滤）是最佳实践** |

---

## 11. 辅助文档索引

> 以下文档为辅助参考，角色已标注。内容如有与本文档冲突，以本文档为准。

### 规范类

| 文档 | 路径 | 角色 |
|------|------|------|
| **开发规约-v2** | `docs/standards/开发规约-v2.md` | 命名/代码/测试/提交详细规范 |
| **DEV-GUIDE** | `docs/standards/DEV-GUIDE.md` | 系统目标与创新约束（部分数据需以本文档为准） |
| **SETUP** | `docs/standards/SETUP.md` | 从零搭建详细指南 |
| **DATA-CONTRACT** | `docs/standards/DATA-CONTRACT.md` | 数据实体与协议规范 |
| **MECHANISM** | `docs/standards/MECHANISM.md` | 全链路机制设计（⚠️ 部分描述 Mock 数据流，仅供参考） |

### 架构类

| 文档 | 路径 | 角色 |
|------|------|------|
| **ARCHITECTURE** | `docs/ARCHITECTURE.md` | 系统架构详细设计 |
| **API** | `docs/API.md` | 完整 API 接口文档 |
| **项目结构说明** | `docs/architecture/项目结构说明.md` | ⚠️ 历史文档（M1 规划快照） |

### 进度类

| 文档 | 路径 | 角色 |
|------|------|------|
| **PROJECT_STATUS** | `docs/PROJECT_STATUS.md` | 答辩交付状态 |
| **PERFORMANCE** | `docs/notes/PERFORMANCE.md` | 性能基准（⚠️ 商品数需更新为 287） |

### 研究类

| 文档 | 路径 | 角色 |
|------|------|------|
| **RAG 调研报告** | `docs/research/rag-framework-research-report.md` | RAG 框架选型分析 |

### 根目录

| 文档 | 路径 | 角色 |
|------|------|------|
| **README** | `README.md` | 项目 README（对外） |
| **AGENTS / CLAUDE** | `AGENTS.md` / `CLAUDE.md` | AI Agent 上下文（与本文档同步） |

---

## 12. 已知技术债

| # | 问题 | 影响 | 优先级 |
|---|------|------|:---:|
| 1 | 商品数据 JSONL → Qdrant 双写不够健壮 | 数据一致性风险 | 中 |
| 2 | 品类别名硬编码在 retriever.py | 可维护性 | 低 |
| 3 | pgvector 已在依赖中但未启用 | 架构简化机会 | 低（赛后） |
| 4 | 部分 .py 文件 > 50 行（agent.py 1180+行） | 代码组织 | 低 |
| 5 | MECHANISM.md 描述 Mock 数据流 | 文档准确性 | 中 |

---

*本文档由项目维护者创建，是开发的唯一权威入口。如需修改，请提交 PR 并在 commit message 中注明 `docs: update DEV-CONTROL`。*
