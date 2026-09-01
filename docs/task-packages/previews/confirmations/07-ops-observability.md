# 小层 07 Ops 可观测运营台确认记录

- 任务包：`V3-OPS-OBSERVABILITY-01`
- 状态：`confirmed`
- 确认时间：`2026-08-30T22:53:43+08:00`
- 用户决策：`确认`
- 已确认美术：编辑实验室 / Kinetic Editorial Tech
- 当前待确认版本：`../generated/07-ops-observability-editorial-v1.png`
- SHA-256：`71ae06a679bd93a77b6ac7ddce1580523997ee809d85dfecde90d94bf52973e1`
- 最终提示词：`../prompts/07-ops-observability.md`

## 页面职责

- 本页是桌面 Ops 中以单个 Mission 为核心的 Agent Trace 工作台。
- 左侧导航覆盖运行、检索、连接器、冲突、评测和发布门禁；当前聚焦 Trace，而不是把所有功能堆进同一页。
- 所有运行态来自生成 TypeScript Client、TanStack Query、运营 API 和 PostgreSQL 审计。

## 当前版本功能

- 顶部明确本地演示、非生产、`deterministic_fake` 和 `DEMO_FIXTURE` 边界。
- Trace 时间线只显示结构化阶段、工具、耗时和 EvidenceRef，不展示思维链或原始参数。
- 检索详情展示 BM25、VECTOR、RRF、RERANK 的真实命中与耗时。
- Fake Provider 的 Token/成本显示 N/A，不用估算值冒充实测。
- 评测队列、数据库审计和五层发布门禁保持独立，刷新后从数据库恢复。

## 用户确认结论

- 用户已确认桌面品牌、Trace 主视图、检索观测和门禁轨道。
- 视觉方案冻结为 `07-ops-observability-editorial-v1.png`。
- 小层 08 已解锁，进入五分钟演示故事板确认。
