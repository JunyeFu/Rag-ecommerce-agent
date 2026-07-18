# RAG E-Commerce Agent - Agent 上下文

> **⚠️ 辅助文档** - 开发权威入口为 [`docs/DEV-CONTROL.md`](docs/DEV-CONTROL.md)，如有冲突以权威文档为准。

> 项目根: `04-rag-ecommerce/`  
> GitHub: `git@github.com:fujunye-company/rag-ecommerce-agent.git`

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + LangGraph (7节点, recursion_limit=10) |
| 向量库 | PostgreSQL + pgvector (1024-dim, bge-large-v1.5) |
| 数据库 | PostgreSQL (async SQLAlchemy, pool_recycle=3600) |
| LLM | **Doubao-Seed-2.0-lite** (火山方舟 API) |
| Embedding | BGE-large-zh-v1.5 |
| Reranker | BGE-Reranker-v2-m3 (失败冷却重试 300s) |
| 前端 | Kotlin + Jetpack Compose (Android 原生, 73 .kt, 集中式 ApiClient) |
| Python | 3.11+ (`.venv` in apps/backend/) |

### 架构亮点
- **agent.py 模块化**: 2704->838行, 13个聚焦模块 (agent_nodes/ + slot_management + cart_nlp + scenario + ...)
- **设计模式**: Strategy+Factory (llm/), Template Method (comparison/), Protocol (core/cache/), LazySingleton (core/lazy.py)
- **API 统一**: 所有 JSON 端点使用 ApiResponse 信封, 前端 ApiClient.kt 集中调用
- **测试**: 231 单元测试 (0.27s) + 44 集成测试 (pytest -m unit/integration)

### Doubao API
```
Base: https://ark.cn-beijing.volces.com/api/v3/
Model: ep-20260514111645-lmgt2
Key:  见 apps/backend/.env (DOUBAO_API_KEY)
```

## 关键命令

```bash
cd apps/backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
docker compose -f infrastructure/docker-compose.yml up -d
cd apps/backend && python -c "from app.startup import ensure_pgvector_data; import asyncio; asyncio.run(ensure_pgvector_data())"
cd apps/backend && .venv\Scripts\python.exe -m pytest -m unit -q   # 231 tests, 0.27s
```

## 场景完成度 (9场景 × 全栈)

| 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

> 9/9 场景全栈代码就绪 / 287条商品94品类 / APK 24.1MB

## 严禁项
- 编造不存在的优惠券/功能/价格
- 用纯 Web/H5 客户端
- 泄露 API Key
- 忽略否定语义
