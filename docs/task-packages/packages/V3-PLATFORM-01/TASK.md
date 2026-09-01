# V3-PLATFORM-01 Durable 平台运行链

## 目标
交付 202、可领取 Worker、持久事件、恢复和媒体生命周期。
## 状态
`complete`
## 范围
- PostgreSQL job/事件、SKIP LOCKED、SSE 游标、MinIO、Ops 持久化适配器。
## 非目标
- 不增加 Kafka、Kubernetes 或微服务拆分。
## 前置依赖
- `V3-AGENT-01`。
## 路径所有权
- `apps/api`、`apps/worker`、`infra`、平台集成 CI `.github/workflows/ci.yml`，以及迁移全表契约测试 `packages/domain/tests/test_migration_integration.py`。
## 现状证据
- 隔离 PostgreSQL/Qdrant/Redis/MinIO 服务健康，迁移一致、媒体生命周期、并发领取、事件恢复和全量 Python 测试均已通过。
## 执行步骤
1. 任务领取。2. 事件恢复。3. MinIO TTL。4. PostgreSQL 集成与故障恢复。
## 数据引用
- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`
## 验收
- [x] PostgreSQL/Qdrant/MinIO 临时服务全链通过。
- [x] 领取与幂等单测通过。
## 回滚
- 回滚新增适配器和 V3 迁移，不删除用户数据卷。
## 停止条件
- 迁移检查或重复领取失败时停止。
## 交接格式
- 结果、路径、验证、外部门禁、下一包。
