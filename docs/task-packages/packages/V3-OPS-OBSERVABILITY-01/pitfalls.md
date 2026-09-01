# V3-OPS-OBSERVABILITY-01 易错点

- 前端成功提示不能替代数据库审计写入。
- Token 和成本仅展示实测 provider 数据。
- 发布门禁是状态，不是可绕过的装饰标签。
- Trace 只展示结构化公开阶段、工具摘要、哈希和 EvidenceRef，不展示思维链或原始 prompt。
- `deterministic_fake` 运行的 Token/成本必须显示未计费或 N/A，不能用估算值冒充真实 provider 指标。
- LOCAL、INTEGRATION、REAL_MODEL、HUMAN 和 RELEASE 证据必须保持独立，任一前层通过不得自动推进后层。
