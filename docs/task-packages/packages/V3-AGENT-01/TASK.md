# V3-AGENT-01 单管理 Agent 与十工具闭环

## 目标
交付显式 provider、结构化规划和冻结工具闭环。
## 状态
`complete`
## 范围
- 异步 ModelProvider、真实兼容 API、确定性 fake、迭代工具执行、错误分类。
## 非目标
- 不实现多 Agent，不静默降级 fake。
## 前置依赖
- `V3-DATA-RAG-01`。
## 路径所有权
- `packages/agent-runtime`、本地演示工具实现。
## 现状证据
- provider、runtime、demo golden API 测试通过。
## 执行步骤
1. provider 红测。2. 错误策略。3. 十工具迭代。4. 黄金闭环。
## 数据引用
- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`
## 验收
- [x] Schema、审批、预算、超时与 429 有确定失败语义。
- [x] 无静默 fake 回退。
## 回滚
- 回滚 provider 与 runtime 新增节点，保留工具审计数据。
## 停止条件
- provider 输出绕过执行器权限时停止。
## 交接格式
- 结果、路径、验证、外部门禁、下一包。
