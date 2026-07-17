# 项目当前状态

> **⚠️ 辅助文档** - 开发权威入口为 [`DEV-CONTROL.md`](DEV-CONTROL.md)，如有冲突以权威文档为准。
>
> 更新时间：2026-07-01  
> 项目：拾物 — 基于 RAG 的多模态电商智能导购 AI Agent  
> 最高优先级需求：`docs/background/REQS-竞赛核心需求.md`

## 一、结论

项目已进入答辩交付状态：后端、Android、9 个竞赛场景、评测文档、答辩知识库、PPT 与完整讲稿均已形成。当前工作重点不是继续扩功能，而是保持口径一致、清理历史生成物、确保演示链路稳定。

## 二、当前可信口径

| 项 | 当前口径 |
|----|----------|
| 客户端 | Android Kotlin + Jetpack Compose 原生客户端，非 H5/WebView |
| 后端 | FastAPI + SSE 流式接口 |
| Agent | LangGraph StateGraph，7 个显式主节点 + 条件路由 |
| RAG | Qdrant 原生客户端召回 + BGE Reranker + 业务排序 |
| 数据库 | PostgreSQL + pgvector，用于结构化商品、会话、购物车、订单等状态 |
| LLM | Doubao-Seed-2.0-lite 为主模型，其他模型只作为降级或历史方案口径 |
| 商品数据 | 287 条商品，约百个细分类 |
| 场景状态 | 9/9 场景全栈代码就绪 |
| 答辩资料 | 25 页 PPT、完整逐页讲稿、答辩知识库已整理 |

## 三、竞赛刚性要求对齐

| 要求 | 状态 | 说明 |
|------|:--:|------|
| 原生 App | ✅ | Android Kotlin + Compose |
| 后端服务 | ✅ | FastAPI，含 chat/upload/cart/order/compare/voice 等接口 |
| RAG 链路 | ✅ | Qdrant 召回、BGE embedding、reranker、业务排序 |
| LLM 接入 | ✅ | Doubao-Seed-2.0-lite |
| 流式交互 | ✅ | SSE progress/text_delta/product_cards/clarify/compare/scenario/done |
| 商品卡片 | ✅ | Android 原生卡片增量渲染 |
| 购物车/下单 | ✅ | 对话式 CRUD + 模拟订单闭环 |
| 多模态 | ✅ | 拍照找货、语音输入、TTS 播报 |
| 反幻觉边界 | ✅ | 商品、价格、优惠、参数均以检索和数据库为准 |

## 四、评分口径

| 维度 | 权重 | 当前答辩重点 |
|------|:--:|--------------|
| 基础功能完整性 | 35% | 1-5 场景闭环、原生 App、商品卡片、主动反问 |
| 工程质量 | 25% | 前后端分层、SSE 协议、数据契约、Docker/配置、测试 |
| 效果与可靠性 | 20% | 首事件、端到端延迟、缓存、降级、反幻觉、P@3 诚实口径 |
| 加分项深度 | 20% | 否定语义、场景化组合、购物车下单、拍照找货、TTS |

## 五、严禁口径

- 不说纯 Web/H5 客户端。
- 不泄露任何 API Key。
- 不编造不存在的优惠券、价格、库存、促销、支付能力。
- 不把 LlamaIndex 说成当前主检索链路。
- 不把 LangGraph 节点数夸大成 10 个显式节点。
- 不把 P@3=0.146 说成最终 Agent 质量，只能说是直接 Qdrant 裸检指标。
- 不把模拟下单说成真实支付。

## 六、当前工作树提示

当前仓库存在多处未提交源码修改和未跟踪答辩资料。整理文档时应只处理文档和生成物，不回滚业务代码，不批量 stage 未确认的源码变更。
