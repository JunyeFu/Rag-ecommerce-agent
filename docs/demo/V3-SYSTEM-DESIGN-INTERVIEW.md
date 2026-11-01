# V3 二十分钟系统设计与面试提纲

## 讲解顺序

1. 问题定义：Android 是 Agent 交互载体，不是淘宝首页复刻。
2. 领域：Mission、候选、EvidenceRef、Offer、Comparison、Approval、List、Cart。
3. RAG：规范化、BM25、Embedding、结构化过滤、RRF、可选 rerank 与消融。
4. Agent：模型负责结构化意图，执行器负责确定性安全边界。
5. 平台：202 durable job、SKIP LOCKED、checkpoint、事件表、SSE 游标恢复。
6. 数据：PostgreSQL 事实、Qdrant 投影、MinIO TTL；Redis容器存在，但尚未接入运行链。
7. 客户端：三入口、类型化事件、原生确认与恢复。
8. Ops：运行概览、检索命中、EvidenceRef、Token/成本、事件游标、生成客户端、Query 缓存、持久审计和证据分层。
9. 质量：单元/属性/集成/instrumentation/Playwright/负载/安全。
10. 门禁：参考构造器、实际检索、Agent/API、真实模型、原生界面、LIVE、RELEASE分别说明；人类测试集已取消，个人贡献仍由本人确认。

当前讲解依据（2026-10-13）：F62修复后全套218项Python/0skip。正常启动十批×30全部完成，但最近隔离对照接受p95=477.54ms、202后首状态p95=648.16ms，未通过200ms接受门槛；旧单批134.94ms不得用作当前容量结论，旧十批249.74ms失败也保留。带观测的标准生命周期119.78ms通过只是诊断，不替代正常启动。自然300秒租约在304.438秒回收；当前A08/A10完整原生通过，累计完整8/10；A02/M03人声和A09浏览器设置等待配合。成本为NOT_AVAILABLE_FROM_PROVIDER。工程案例包括F54普通报价读取自动续期、F51批准参数被重规划、F58真实Trace重复React键，以及[F62操作覆盖购物目标](./V3-MISSION-GOAL-CASE.md)。本地候选仍HOLD，最终同版APK/媒体未签收。

## 高频追问

- 为什么不用 Kafka？单机本地目标下 PostgreSQL job 足够，减少运维面；用 SKIP LOCKED 保证并发领取。
- 为什么单 Agent？任务依赖强且状态共享，多 Agent 会增加协调与评测变量，当前没有收益证据。
- 如何防幻觉？商业事实只来自工具结果并带 EvidenceRef；缺失字段显式为空。
- 如何恢复？事件游标、checkpoint、幂等键和线程快照共同恢复，Worker 回收过期租约，terminal event 只能出现一次。
- 如何替换模型？ModelProvider/EmbeddingProvider 是外部边界，fake明确用于CI与免费本地演示，真实失败不静默降级。
- 最大剩余风险？真实 Provider 的 challenge 成绩、联盟授权、物理设备体验与正式发布治理。
