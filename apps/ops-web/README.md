# Operations Web

React/Vite 运营台实现连接器、实体冲突、Agent Trace、评测运行与发布门禁五个工作域。

- 默认数据是明确标记的本地 fixture，不代表 live 联盟授权、真实报价或正式发布状态。
- Trace 只展示阶段、版本、工具名、参数摘要哈希与 EvidenceRef，不展示思维链、原始输入或原始工具参数。
- 实体合并和评测启动是 reviewer 受控操作；生产 SSO/RBAC 与持久化审计由外部门禁配置。
- 导出默认关闭，前端不读取或保存连接器 secret、原始授权响应或生产签名材料。
