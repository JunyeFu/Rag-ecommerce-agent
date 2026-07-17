# RAG E-Commerce Agent - Codex 上下文 v4.0

> **⚠️ 辅助文档** - 开发权威入口为 [`docs/DEV-CONTROL.md`](docs/DEV-CONTROL.md)，如有冲突以权威文档为准。

> 项目根: `04-rag-ecommerce/`  
> GitHub: `git@github.com:fujunye-company/rag-ecommerce-agent.git`  
> 比赛: AI 全栈挑战赛 (第3届) - **最高优先级：`docs/background/REQS-竞赛核心需求.md`**

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + LangGraph |
| 向量库 | Qdrant (1024-dim, bge-large-v1.5) |
| 数据库 | PostgreSQL + pgvector (async SQLAlchemy) |
| LLM | **Doubao-Seed-2.0-lite** ✅ (Key 已验证通过，DeepSeek 保留降级) |
| Embedding | BGE-large-zh-v1.5 |
| 前端 | Kotlin + Jetpack Compose (Android 原生, 73 .kt) |
| Python | 3.11 @ ~/.hermes-venv |

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
cd apps/backend && python -c "from app.startup import ensure_qdrant_data; import asyncio; asyncio.run(ensure_qdrant_data())"
```

## 当前里程碑

```
M0 ✅  M1 ✅  M2 ✅  M3 ✅  M4 ✅  M5 ✅  M6 ✅  M7 ✅  M8 ✅  M9 ✅  M10 ✅
```

**M10 完成项**：
- ✅ P0: 豆包Key验证 ✅ + Qdrant UUID5修复 + fast path修复
- ✅ P1: clarify追问节点 ✅ + 商品详情页 ✅ + CompareScreen联调 ✅
- ✅ P2: 答辩PPT大纲 ✅ + 演示脚本 ✅ + 性能文档 ✅ + E2E测试 ✅ + 交付打包 ✅

## 场景完成度 (9场景 × 全栈)

| 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

> 9/9 场景全栈代码就绪。场景7已通过动态品类映射+品类感知MMR采样+场景感知Prompt+ScenarioEvent SSE完整实现。

## 比赛评分权重

| 维度 | 权重 | 当前估计 |
|------|:---:|:--:|
| 基础功能完整性 | 35% | ~33% |
| 工程质量 | 25% | ~23% |
| 效果与可靠性 | 20% | ~17% |
| 加分项深度 | 20% | ~17% |
| **合计** | **100%** | **~90%** |

> APK 编译成功(24.1MB) / 全部 P0 清零 / 9/9 场景全栈代码就绪 / 287条商品94品类
> 演示脚本+PPT大纲+评测报告 / 交付包就绪 / 剩余: 真机联调 -> 演示视频录制

## 严禁项
- 编造不存在的优惠券/功能/价格
- 用纯 Web/H5 客户端
- 泄露 API Key
- 忽略否定语义
