# V2-OPS-01 连接器数据Trace与评测运营台

## 目标

实现连接器、报价新鲜度、实体冲突、Agent Trace、评测和发布门禁的受控运营台。

## 状态

`complete`

## 范围

- 实现连接器授权状态、健康度、限流、错误率和报价新鲜度页面。
- 实现商品实体合并冲突、来源差异和人工复核队列。
- 实现 AgentRun/ToolInvocation/EvidenceRef、提示/模型版本、耗时和成本查询。
- 实现评测运行、回归差异、实验 Manifest 和发布门禁视图。
- 实现角色权限、审计日志、字段脱敏和导出限制。

## 非目标

- 不在 Web 前端保存连接器 secret 或直接调用商家 API。
- 不展示思维链、完整用户敏感输入、原始授权响应或生产签名材料。
- 不用运营台按钮绕过 manifest、审批或发布门禁。

## 前置依赖

- `V2-API-01` 提供生成 TypeScript 客户端和运营 API。

## 路径所有权

- `apps/ops-web/`。
- `apps/api/ops/` 的只读/受控运营接口。
- `tests/ops/` 和 Web E2E。
- `apps/api/src/ragcommerce_api/ops.py`、`ops_schema_v1.py`、迁移 `20260826_0005` 与对应 API 测试。
- `docs/task-packages/packages/V2-OPS-01/evidence/` 的概念、浏览器和验证证据。

## 现状证据

- 旧仓没有 Agent Trace、连接器授权、实体复核或评测运营界面。
- 商业化需要把报价来源、Agent 决策和门禁变化变成可操作证据。

## 执行步骤

1. 定义运营角色、数据字段、脱敏、审计和导出策略。
2. 用 fixture API 完成连接器、数据、Trace、评测和发布五类页面。
3. 实现实体合并审批和评测运行的受控写操作。
4. 实现空数据、权限不足、数据延迟、连接器降级和审计查询状态。
5. 运行 typecheck、unit、build、E2E、权限和敏感字段测试。

## 数据引用

- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`

## 验收

- [x] 连接器健康、报价新鲜度和错误可追溯到来源、证据引用与固定时间窗口，fixture 不标记为 live 授权。
- [x] 实体合并需要 reviewer 权限、至少 12 字理由、幂等键并生成只含 payload 哈希的追加式审计。
- [x] Trace 仅含版本、状态、工具名、参数 SHA-256、耗时、成本估算和 EvidenceRef，无思维链、密钥、原始授权响应和非必要 PII。
- [x] 评测和发布状态按 LOCAL/INTEGRATION/LIVE/HUMAN/RELEASE 分层显示本地证据与外部门禁。
- [x] TypeScript 生成客户端无漂移；6 个 Ops API 权限/脱敏测试、2 个 Web 单测、构建与五域 Playwright 浏览器流程通过。

## 回滚

- 以前端 feature flag 和运营 API 权限撤回功能；不删除审计和历史评测记录。

## 停止条件

- 生产 SSO/RBAC 责任人不明、运营字段需要敏感原文或写操作没有审计主体时停止。

## 交接格式

- 结果：运营页面、角色矩阵和审计覆盖。
- 变更路径：ops-web、api/ops、tests/ops。
- 验证命令与结果：typecheck、unit、build、E2E、RBAC。
- 剩余外部门禁：生产 SSO/RBAC、持久化生产审计适配器和运营人员工作流验收。
- 风险与下一包：交给 V2-SECURITY-01 与 V2-LIVE-01。
