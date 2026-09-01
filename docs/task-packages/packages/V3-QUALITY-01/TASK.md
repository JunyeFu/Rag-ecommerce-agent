# V3-QUALITY-01 量化质量与可观测性

## 目标
建立 CI、评测、故障、负载、安全和可观测门禁。
## 状态
`complete`
## 范围
- 自动化矩阵、消融、并发 Mission、结构化日志与 OTLP 可选导出。
## 非目标
- fake 指标不替代真实模型或人工证据。
## 前置依赖
- `V3-OPS-01`。
## 路径所有权
- `.github`、`packages/evaluation`、`docs/evaluation`、观测代码。
## 现状证据
- 2026-08-31：本地 22 项回归门禁、30 Mission fixture 负载、Alembic upgrade/current/check 与 PostgreSQL/Qdrant/Redis/MinIO 集成测试均已实测。真实模型和 held-out 人工质量仍为明确外部门禁。
## 执行步骤
1. CI 矩阵。2. 消融。3. 故障与并发。4. 指标报告。
## 数据引用
- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`
## 验收
- [x] RAG、grounding、30 并发和性能阈值有实测报告。
- [x] 真实模型评测与 fake 分栏。
## 回滚
- 回滚观测导出配置，不删除历史评测证据。
## 停止条件
- 测试输出凭据或用 fixture 冒充真实质量时停止。
## 交接格式
- 结果、路径、验证、外部门禁、下一包。
