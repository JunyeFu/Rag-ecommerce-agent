# V3 Agent-first 权威基线

## 当前阶段

当前开发基线位于 `main`。旧仓 `D:/Agent/04-rag-ecommerce` 只作为历史来源，不属于写入范围。

## 产品边界

Android 只保留任务、决策、我的三个一级入口。系统是单一管理 Agent：模型生成结构化计划与解释，执行器掌握工具 Schema、权限、幂等、预算和审计。演示数据、自动化 challenge、真实模型、LIVE 联盟事实和 RELEASE 证据分层记录。

## 当前可验证实现

- OpenAPI `0.2.0`、ThreadSnapshot、ProductView 与类型化 SSE。
- OpenAI-compatible ModelProvider 与 EmbeddingProvider；无静默 fake 回退。
- 60 个项目自有虚构 3C SKU；默认 `fixture` 使用确定性 BM25 + 向量 + 过滤 + RRF，显式 `real` 模式使用真实 Embedding API 与 Qdrant，并在配置或调用失败时明确失败。
- 十个冻结工具的本地黄金闭环、202 job、PostgreSQL SKIP LOCKED Worker。
- Agent 的清单与待购工具经过审批后调用真实领域状态，类型化报价事件具备逐字段来源证据；Android 三入口通过 API 读取写入结果。
- Ops TanStack Query 真实 API、PostgreSQL Ops 适配器、MinIO 媒体适配器。

Android 构建使用 Java 21。旧任务包中的 Java 17、分支名和当时门禁结论属于历史时点，不回写成当前证据。

## 尚不能声称

- 已有 MiMo 公开黄金集报告只证明报告所列只读场景；本轮新增写操作、重新询价与真实 Embedding 尚无新的真实 Provider 报告，不能由旧报告替代。
- 未提供联盟凭据，不能声称 LIVE 报价或深链授权。
- competition-v2 challenge 的真实 Provider 执行、物理设备性能与无障碍验收未完成。
- 作品集发布状态以 `docs/release/release-gate-matrix.json` 为准；商业发布继续为 `NO_GO`。
