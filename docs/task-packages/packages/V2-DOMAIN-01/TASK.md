# V2-DOMAIN-01 商品报价与Agent运行领域模型

## 目标

建立商品身份、商家报价、购物任务和 Agent 运行证据的权威领域模型与迁移。

## 状态

`complete`

## 范围

- 实现 Product、Variant、Marketplace、Merchant、Offer、OfferQuote 和 DeepLink。
- 实现 ShoppingMission、List、Cart、Conversation、AgentRun、AgentStep、ToolInvocation 和 EvidenceRef。
- 使用整数最小货币单位或 Decimal/Numeric，定义报价 TTL、状态机和不可变快照。
- 定义外键、唯一性、幂等、审计、保留和删除策略。

## 非目标

- 不实现连接器、检索、LLM 编排、UI、支付、商家订单、退款或履约。
- 不把 PostgreSQL 模型直接暴露为公共 API。

## 前置依赖

- `V2-BASE-00` 的模块、迁移和测试入口完成。

## 路径所有权

- `packages/domain/`。
- `apps/api/migrations/` 中本包迁移。
- `packages/contracts/domain/` 中领域 Schema。

## 现状证据

- 旧 Product 同时承载商品和单一价格，缺少商家、SKU、报价时间与来源。
- V2 产品边界要求跳转商家成交，因此不建立平台支付和订单账本。

## 执行步骤

1. 以 ADR 固定实体身份、状态机、金额和时间语义。
2. 先编写领域不变量和属性测试。
3. 实现纯领域类型、持久化映射和 Alembic 迁移。
4. 验证 upgrade、downgrade、并发唯一性、幂等和删除策略。
5. 生成公共 Schema，但不泄露内部表结构。

## 数据引用

- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`

## 验收

- [x] Product、Variant、Offer、OfferQuote 使用独立 UUID 与外键边界。
- [x] 金额只接受 CNY 整数分，拒绝二进制浮点并有属性测试。
- [x] 过期、变化、不可用和 discovery-only 报价状态可确定性表达。
- [x] AgentRun 和工具调用可关联证据、模型/提示/策略/契约版本与幂等键。
- [x] Alembic upgrade/current/check、PostgreSQL integration 和 downgrade fixture 通过。

## 回滚

- 使用本包 Alembic downgrade 回滚空库或测试数据；有生产数据时禁止无审计降级。

## 停止条件

- 交易边界被扩大到平台收银、字段所有权不清或需要未审查 PII 时停止。

## 交接格式

- 结果：领域 ADR、Schema 和迁移 head。
- 变更路径：domain、contracts/domain、migrations。
- 验证命令与结果：unit、property、migration integration。
- 剩余外部门禁：无。
- 风险与下一包：交给 V2-CONNECTOR-01 与 V2-RAG-01。
