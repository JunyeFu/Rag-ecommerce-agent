# V2-RAG-01 可溯源商品RAG与实体解析

## 目标

建立以 PostgreSQL 为事实源、Qdrant 为派生投影的商品检索、实体解析、重排和证据闭环。

## 状态

`complete`

## 范围

- 导入规范化 Product/Variant/Merchant/Offer 数据并通过 Outbox 投影索引。
- 实现结构化约束、BM25、向量检索、融合、重排和证据组装。
- 实现 GTIN/MPN/型号/规格优先的实体匹配与人工复核队列。
- 为价格、规格、政策和商品描述区分独立来源与新鲜度。
- 建立 Recall@10、NDCG@10、硬约束和 grounded claim 评测。

## 非目标

- 不生成报价、运费、库存或保障事实。
- 不实现 Agent 工具循环、客户端或 live 联盟授权。
- 不让 Qdrant 成为业务写入或商品事实源。

## 前置依赖

- `V2-DATA-01` 的合法种子包。
- `V2-DOMAIN-01` 的 Product/Variant/Offer/Evidence 模型。

## 路径所有权

- `packages/retrieval/`。
- `apps/worker/jobs/indexing/` 和实体解析任务。
- `apps/api/migrations/` 中本包 Outbox 与投影检查点迁移。
- `tests/retrieval/`、`evals/retrieval/`。

## 现状证据

- 旧仓有可继承的 Qdrant、过滤、排序和索引一致性测试经验。
- 旧商品只有单一商品 ID 和价格，不能直接支撑跨站同规格比价。

## 执行步骤

1. 固定检索文档、过滤字段、EvidenceRef 和索引版本契约。
2. 实现事务 Outbox、幂等投影和全量重建。
3. 实现混合检索、融合、重排和硬约束后置验证。
4. 实现实体匹配置信度、冲突记录和人工复核队列。
5. 运行检索基准、消融和索引漂移恢复测试。

## 数据引用

- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`

## 验收

- [x] PostgreSQL Outbox 到 Qdrant 的删除、更新、重放和全量重建通过真实服务验证。
- [x] 144 条可独立检索开发用例 Recall@10=0.9444、NDCG@10=0.9168、硬约束=1.0；82 条非检索/缺上下文用例单列。
- [x] 低置信度、GTIN/MPN 或规格冲突商品不会合并为同一比价对象。
- [x] 每个返回事实映射到来源路径、哈希、seed ID 和允许字段。
- [x] 外部描述只进入 `untrusted_content`，不会成为系统或工具指令，且不写入 Qdrant payload。

## 回滚

- 删除当前索引版本并由 PostgreSQL/Outbox 重建；不回滚权威业务记录。

## 停止条件

- 生产 embedding 不可用、数据许可未确认、权威字段所有权不清或评测集泄漏时停止。

## 交接格式

- 结果：索引版本、指标和实体冲突数量。
- 变更路径：retrieval、indexing jobs、retrieval evals。
- 验证命令与结果：unit、integration、benchmark 和 rebuild。
- 剩余外部门禁：生产 embedding 与生产数据启动。
- 风险与下一包：交给 V2-AGENT-01 与 V2-OPS-01。
