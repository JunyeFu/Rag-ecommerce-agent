# V3 二十分钟系统设计与面试提纲

## 讲解顺序

1. 问题定义：Android 是 Agent 交互载体，不是淘宝首页复刻。
2. 领域：Mission、候选、EvidenceRef、Offer、Comparison、Approval、List、Cart。
3. RAG：规范化、BM25、Embedding、结构化过滤、RRF、可选 rerank 与消融。
4. Agent：模型负责结构化意图，执行器负责确定性安全边界。
5. 平台：202 durable job、SKIP LOCKED、checkpoint、事件表、SSE 游标恢复。
6. 数据：PostgreSQL 事实、Qdrant 投影、MinIO TTL、Redis 非事实缓存。
7. 客户端：三入口、类型化事件、原生确认与恢复。
8. Ops：运行概览、检索命中、EvidenceRef、Token/成本、事件游标、生成客户端、Query 缓存、持久审计和证据分层。
9. 质量：单元/属性/集成/instrumentation/Playwright/负载/安全。
10. 门禁：fixture、真实模型、人工、LIVE、RELEASE 不能互相替代。

## 高频追问

- 为什么不用 Kafka？单机本地目标下 PostgreSQL job 足够，减少运维面；用 SKIP LOCKED 保证并发领取。
- 为什么单 Agent？任务依赖强且状态共享，多 Agent 会增加协调与评测变量，当前没有收益证据。
- 如何防幻觉？商业事实只来自工具结果并带 EvidenceRef；缺失字段显式为空。
- 如何恢复？事件游标、checkpoint、幂等键和线程快照共同恢复，Worker 回收过期租约，terminal event 只能出现一次。
- 如何替换模型？ModelProvider/EmbeddingProvider 是外部边界，fake 只用于 CI，真实失败不静默降级。
- 最大剩余风险？真实 provider 质量、联盟授权、物理设备体验、双人盲评与正式发布治理。
