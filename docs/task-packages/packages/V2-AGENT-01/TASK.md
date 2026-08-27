# V2-AGENT-01 类型化工具与持久化购物Agent

## 目标

实现生产 API、评测、文本、语音和图片共用的单一购物 Agent 运行时。

## 状态

`complete`

## 范围

- 实现 `ShoppingAgent.handle(TurnCommand) -> AsyncIterator<AgentEvent>`。
- 使用内部 LangGraph 和 PostgreSQL checkpointer 实现规划、工具循环、验证、恢复和有限重规划。
- 注册十个冻结工具，并实现 read/reversible/consent/external-navigation 风险策略。
- 实现 ShoppingMission、短期线程状态和用户同意的长期偏好记忆。
- 记录脱敏 AgentRun、步骤、工具参数摘要、证据、版本、耗时与成本。

## 非目标

- 不建设多 Agent 网络、自主支付、退款、下单、发消息或无限自循环。
- 不让模型直接访问数据库、连接器凭据、任意 URL 或原始用户媒体。
- 不在本包实现 HTTP/SSE 路由和客户端。

## 前置依赖

- `V2-CONNECTOR-01` 的报价工具与夹具。
- `V2-RAG-01` 的检索、实体和证据工具。

## 路径所有权

- `packages/agent-runtime/`。
- `tests/agent/`、`evals/agent/`。
- Agent 专用 migrations 和 contracts。
- `apps/api/migrations/` 中 Agent checkpoint、事件与偏好迁移。

## 现状证据

- 旧仓固定路由没有 tool call、checkpointer、审批、恢复或统一生产入口。
- 旧生产 SSE 和内部图是两套执行器，V2 必须消除该分叉。

## 执行步骤

1. 固定 TurnCommand、AgentEvent、ToolResult、ToolPolicy 和停止语义。
2. 用确定性 fake model 编写工具选择、参数、循环预算和恢复测试。
3. 实现输入护栏、任务记忆、规划、工具节点、证据验证和响应节点。
4. 实现 checkpoint、SSE 重放所需事件日志和幂等恢复。
5. 验证提示注入、工具错误、报价变化、超限、拒绝与隐私删除。

## 数据引用

- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`

## 验收

- [x] 所有入口只调用一个 ShoppingAgent 运行时。
- [x] 工具参数 Schema 合法率 100%，未授权写和高风险越权为 0。
- [x] 节点故障可从最后 checkpoint 恢复且不重复已成功幂等动作。
- [x] 每轮最多 8 次工具和 2 次重规划，超限可解释终止。
- [x] 商业事实全部来自 ToolResult/EvidenceRef，模型生成字段数量为 0。
- [x] 未经同意的长期偏好不持久化，删除请求可验证完成。

## 回滚

- 通过 Agent 版本开关回退到上一已验证图和提示版本；保留运行审计，不重放外部动作。

## 停止条件

- 需要新增支付/订单工具、模型提供方不支持类型化工具、checkpointer 语义不可靠或隐私策略未确认时停止。

## 交接格式

- 结果：Agent 版本、工具清单、Trace 和回归结果。
- 变更路径：agent-runtime、agent tests/evals、专用迁移。
- 验证命令与结果：fake-model trace、integration、恢复和安全测试。
- 剩余外部门禁：真实模型提供方工具调用和质量评测。
- 风险与下一包：交给 V2-API-01 与 V2-EVAL-01。
