# V3 Agent-first 权威基线

## 当前阶段

`codex/v3-agent-first` 在 V2 独立仓上原位升级；旧仓 `D:/Agent/04-rag-ecommerce` 不属于写入范围。

## 产品边界

Android 只保留任务、决策、我的三个一级入口。系统是单一管理 Agent：模型生成结构化计划与解释，执行器掌握工具 Schema、权限、幂等、预算和审计。演示数据、真实模型、人工评测、LIVE 联盟事实和 RELEASE 证据分层记录。

## 当前可验证实现

- OpenAPI `0.2.0`、ThreadSnapshot、ProductView 与类型化 SSE。
- OpenAI-compatible ModelProvider 与 EmbeddingProvider；无静默 fake 回退。
- 60 个项目自有虚构 3C SKU、BM25 + 向量 + 过滤 + RRF。
- 十个冻结工具的本地黄金闭环、202 job、PostgreSQL SKIP LOCKED Worker。
- Android 三入口、类型化商品/报价/比较事件、API 驱动清单与待购写入。
- Ops TanStack Query 真实 API、PostgreSQL Ops 适配器、MinIO 媒体适配器。

## 尚不能声称

- 未提供真实模型或联盟凭据，不能声称真实模型质量、LIVE 报价或深链授权。
- 100 条 held-out 双人盲评、物理设备性能与无障碍人工验收未完成。
- 未形成候选提交、签名 APK、远端 CI 与发布批准，因此 RELEASE 为 NO_GO。
