# V3-PLATFORM-CONTROL-01 运行与恢复控制（中层）

## 目标
控制 durable job、事件恢复、离线体验和 Ops 可观测性的端到端一致性。
## 状态
`complete`
## 范围
- 覆盖恢复体验和运营台两项可见结果，并引用真实持久化证据。
## 非目标
- 不增加 Kafka、Kubernetes、微服务拆分或生产 SSO。
## 前置依赖
- `V3-PRODUCT-CONTROL-01`、`V3-PLATFORM-01`、`V3-OPS-01`。
## 路径所有权
- 本包及恢复、Ops 两个小层包。
## 现状证据
- durable 运行链代码已存在；Docker 集成与最终信息架构仍有门禁。
## 执行步骤
1. 确认离线恢复。2. 确认 Ops 视图。3. 运行 PostgreSQL/Qdrant/MinIO 集成。
## 数据引用
- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`
## 验收
- [x] 恢复与 Ops 两个小层控制边界和验收已冻结。
- [x] 集成运行与静态配置证据边界已写入停止条件。
## 回滚
- 只回滚本层控制文档和未确认视图，不删除持久化数据。
## 停止条件
- Docker 运行环境不可用或方案要求静态数据冒充运营状态时停止。
## 交接格式
- 服务状态、恢复证据、Ops 证据、环境阻断、下一包。
