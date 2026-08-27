# V2-API-01 统一多模态Turn与可恢复SSE接口

## 目标

实现 Android、运营台和评测共用的版本化 REST/SSE 契约与安全媒体生命周期。

## 状态

`complete`

## 范围

- 实现媒体上传、线程 Turn、运行事件、决策、商品报价、requote、清单和购物车接口。
- Turn 使用 `Idempotency-Key`；SSE 使用事件 ID 和 `Last-Event-ID` 恢复。
- 文本、图片和语音通过 MediaRef 进入同一 TurnCommand。
- 实现认证、对象所有权、限流、输入大小、内容签名、保留和删除。
- 从 OpenAPI 生成 Kotlin/TypeScript 客户端并检查漂移。

## 非目标

- 不复制 Agent 业务编排到路由层。
- 不提供支付、订单、退款、任意 URL 抓取或文档自由上传。
- 不在事件中输出思维链、密钥或原始提供方响应。

## 前置依赖

- `V2-AGENT-01` 的唯一运行时和事件契约完成。

## 路径所有权

- `apps/api/` 的路由、auth、media 和 SSE 层。
- `packages/contracts/api/`、生成客户端配置。
- `tests/api/`。

## 现状证据

- 旧 ChatRequest 的图片/context 没有进入生产 Agent；语音和图片分别复制会话流程。
- V2 要求所有输入最终转换为同一 TurnCommand。

## 执行步骤

1. 冻结 OpenAPI、错误码、事件顺序、幂等和媒体保留契约。
2. 先写 API contract、所有权、断线重连和恶意媒体测试。
3. 实现薄路由并只调用 ShoppingAgent、domain service 和 connector service。
4. 实现 SSE 事件存储、游标恢复、背压和取消。
5. 生成客户端并在 CI 验证无漂移。

## 数据引用

- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`

## 验收

- [x] 文本、语音、图片共享线程、Mission、AgentRun 和工具策略。
- [x] 同一 Idempotency-Key 不重复创建 Turn 或可逆写入。
- [x] SSE 断线后从 Last-Event-ID 恢复，无重复或丢失完成事件。
- [x] 跨用户对象访问、超限媒体、伪造 MIME 和路径穿越均被拒绝。
- [x] 生成客户端与 OpenAPI 一致，路由层无 Agent 业务分支。

## 回滚

- 保持 v1 URL 版本稳定，以 feature flag 禁用新接口；迁移只回滚本包新增表和对象生命周期配置。

## 停止条件

- 生产对象存储保留策略、受信代理、认证主体或共享限流边界无法确定时停止生产配置。

## 交接格式

- 结果：OpenAPI 版本、端点和 SSE 恢复结果。
- 变更路径：api、contracts/api、generated clients、tests/api。
- 验证命令与结果：contract、integration、auth、media、SSE。
- 剩余外部门禁：生产限流、对象存储与受信代理。
- 风险与下一包：交给 V2-ANDROID-01 和 V2-OPS-01。
