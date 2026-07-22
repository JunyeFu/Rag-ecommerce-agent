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
| LLM | **DeepSeek-V4-Flash** (reasoning disabled, TTFT ~0.6s) |
| Embedding | BGE-large-zh-v1.5 |
| Reranker | BGE-Reranker-v2-m3 (失败冷却重试 300s) |
| 前端 | Kotlin + Jetpack Compose (Android 原生, 82 .kt, 集中式 ApiClient + AuthInterceptor) |
| Python | 3.11+ (`.venv` in apps/backend/) |

### 架构亮点
- **Pipeline 模块化**: agent.py 851->354行, pipeline.py(432行)+intent_router.py(81行) 提取 9 个 handler
- **设计模式**: Strategy+Factory (llm/), Template Method (comparison/), Pipeline+Handler (pipeline.py), Protocol (core/cache/), LazySingleton (core/lazy.py)
- **缓存统一**: 4 处模块级 dict -> InMemoryCache(LRU+TTL) + SlidingWindowRateLimiter (core/cache/)
- **API 统一**: 所有 JSON 端点使用 ApiResponse 信封, 前端 ApiClient.kt + AuthInterceptor 集中调用
- **鉴权强制**: AuthMiddleware 强制 401（P0），前端 AuthManager 自动获取 token
- **测试**: 448 单元测试 (~23s) + 68 集成/契约/E2E 测试 (pytest -m unit/integration)
- **UserRepository.kt 拆分**: 1772->596行 + 6 个 Ext 文件（Cart/Favorite/Footprint/Address/Order/Auth）

### LLM API
```
# 当前激活：DeepSeek
Base: https://api.deepseek.com/v1
Model: deepseek-v4-flash (reasoning disabled)
Key:  见 apps/backend/.env (DEEPSEEK_API_KEY)

# 备选：Doubao（DOUBAO_API_KEY 为空时自动 fallback）
Base: https://ark.cn-beijing.volces.com/api/v3/
Model: ep-20260514111645-lmgt2
```

## 关键命令

```bash
cd apps/backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
docker compose -f infrastructure/docker-compose.yml up -d
cd apps/backend && python -c "from app.startup import ensure_pgvector_data; import asyncio; asyncio.run(ensure_pgvector_data())"
cd apps/backend && .venv\Scripts\python.exe -m pytest -m unit -q   # 448 tests, ~23s
```

## 场景完成度 (9场景 × 全栈)

| 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

> 9/9 场景全栈代码就绪 / 287条商品94品类 / 448单元测试+68集成测试 / P0-P3质量提升完成

## 严禁项
- 编造不存在的优惠券/功能/价格
- 用纯 Web/H5 客户端
- 泄露 API Key
- 忽略否定语义
