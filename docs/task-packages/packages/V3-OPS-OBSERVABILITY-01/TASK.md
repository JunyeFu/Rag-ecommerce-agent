# V3-OPS-OBSERVABILITY-01 Ops 可观测运营台（小层 07）

## 目标
确认以真实运营 API 和 PostgreSQL 审计为数据源的桌面运营台信息架构，使单个 Mission 的 Agent、RAG、工具、事件和发布门禁可以端到端追踪。
## 状态
`complete`
## 范围
- 左侧固定导航覆盖运行概览、Agent Trace、检索观测、连接器、数据冲突、评测运行和发布门禁。
- Agent Trace 首屏展示任务身份、Provider/证据边界、阶段时间线、检索命中、工具耗时、Token/成本和事件恢复信息。
- 右侧运营轨道展示数据库审计状态、评测队列和 LOCAL/INTEGRATION/REAL_MODEL/HUMAN/RELEASE 门禁。
- 冲突处理与评测排队必须持久化，页面刷新后恢复真实状态。
## 非目标
- 不使用静态 `ops-data.ts` 冒充运行态，不展示思维链、原始 prompt、密钥或完整敏感工具参数；不实现生产 SSO/RBAC。
## 前置依赖
- `V3-PLATFORM-CONTROL-01`、`V3-OPS-01`。
## 路径所有权
- `apps/ops-web` 信息架构及本包预览证据。
## 现状证据
- 小层 06 已确认；现有 Ops 已具备五个导航视图、生成 TypeScript Client 和基础企业风格，当前需要升级为与 Android 一致的编辑实验室品牌并冻结 Mission Trace 首屏。
## 执行步骤
1. 生图。2. 用户确认。3. 移除静态运行态并对齐生成 Client/TanStack Query。4. Playwright 验证五个工作流和刷新持久化。
## 数据引用
- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`
## 验收
- [x] 用户确认预览和信息架构。
- [x] Trace、检索、耗时、成本、冲突、评测和门禁均来自真实运营 API。
- [x] 页面刷新后审计与排队状态不丢失，DEMO/REAL_MODEL/LIVE/HUMAN/RELEASE 清晰区分。
## 回滚
- 回滚视图布局，不回滚持久化审计。
## 停止条件
- API/数据库不可用、生成 Client 与契约漂移或要求静态数据冒充运行态时停止。
## 交接格式
- 预览、API 字段、Playwright 证据、用户决策、外部门禁。
