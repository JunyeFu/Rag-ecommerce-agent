# RAG 电商导购 Agent V2 重开发基线

基线 ID：`RAG-COMMERCE-V2-BASELINE-20260826`

状态：`frozen_for_task_planning`

## 1. 当前实现判定

旧实现属于“意图路由式 RAG 对话工作流 + 有限购物车指令”，不是可商业化 Agent。主要证据：

- `apps/backend/app/services/agent.py` 使用固定 LangGraph 条件边，没有类型化工具调用、工具授权或持久化 checkpointer。
- 内部评测走 LangGraph，生产 SSE 又由 `generate_response()` 手工复制分类、检索、排序和生成流程。
- 文本、图片和语音不是统一 Turn；`ChatRequest.image_url/context` 未进入生产 Agent 执行。
- 商品模型没有 Merchant、Variant、Offer、报价来源、有效期、深链或商业事实 Provenance。
- Android 商品详情推导或伪造原价、销量、发货地、保障、旗舰店和评分，构成商业 P0 阻断项。
- Explore、Compare、Profile 多处依赖 DemoData，release 数据为空；支付设置和订单动作与跳转成交边界冲突。

旧仓当前来源状态由 `source-snapshot.json` 冻结。旧仓历史任务包的本地完成不能替代其仍开放的外部门禁。

## 2. 冻结的产品边界

- 市场：中国大陆；语言：简体中文；币种：CNY；时区：Asia/Shanghai。
- 商业模式：多商家 B2C 导购和联盟/推广深链。
- 客户端：Kotlin/Compose Android 与 React/TypeScript 运营台。
- 一级导航：导购、清单、购物车、我的；比较是导购内的决策工作台。
- 平台完成需求理解、商品检索、多站点报价、比较、待购集合和跳转。
- 平台不托管支付、商家订单、发货、退款和售后资金。
- 首批连接器契约覆盖淘宝/天猫、京东、拼多多；live 能力以实际主体授权为硬门禁。
- 搜索发现只返回链接和待确认状态，禁止用非授权网页采集结果冒充实时价格。

## 3. 必须删除或放弃的旧布局

- 删除随机贴纸地图式 Explore 和无动作“发布”。
- 删除 Compare 一级标签、静态平台趋势和 DemoData 商品池；保留为会话内比较工作台。
- 删除本地支付设置、支付密码、免密额度和客户端自定义加密方案。
- 删除分类 Sprint 占位页、本地假客服、模拟订单动作、演示优惠券和未接通 Profile 宫格。
- 删除所有客户端推导的商业事实和占位网络图片。
- 全局放弃高饱和新野兽派作为交易信息语法，只保留小面积品牌色和竞赛展示性元素。
- 未完成端到端能力前隐藏忘记密码、重置密码和其他死路由。

## 4. 目标 Agent

对外只暴露深接口：

```text
ShoppingAgent.handle(TurnCommand) -> AsyncIterator<AgentEvent>
```

内部使用单一管理 Agent，不以多 Agent 数量作为目标。运行链为：

```text
输入护栏 -> 任务记忆 -> 规划 -> 类型化工具循环 -> 证据验证 -> 响应 -> 持久化
```

固定工具：

- `catalog.search`
- `catalog.get_product_facts`
- `offer.find`
- `offer.requote`
- `comparison.build`
- `list.update`
- `cart.update`
- `link.resolve`
- `vision.identify`
- `merchant.get_policy`

模型只建议工具和参数；执行器负责鉴权、Schema、白名单、超时、幂等、审计与风险策略。默认每轮最多 8 次工具调用和 2 次重规划。

## 5. 商业领域与报价真相

核心实体：

- `Product`：跨站点可识别的规范化商品。
- `ProductVariant`：型号、规格、颜色和容量等可成交 SKU 身份。
- `Marketplace` 与 `Merchant`：平台和卖家身份。
- `Offer`：某卖家对某 Variant 的销售入口。
- `OfferQuote`：金额、运费、优惠、库存状态、采集时间、失效时间、验证级别和来源。
- `DeepLink`：允许域名、联盟披露、过期时间和目标商品位置。
- `ShoppingMission`：预算、用途、硬约束、排除项和用户同意的偏好。
- `AgentRun/AgentStep/ToolInvocation/EvidenceRef`：可复现运行证据。

报价级别：

- `LIVE_AUTHORIZED`：本次请求调用官方/联盟 API；无来源 TTL 时最多有效 5 分钟。
- `FEED_VERIFIED`：授权 Feed，必须展示采集时间和 Feed 有效期，不标实时。
- `DISCOVERY_ONLY`：只提供链接；价格为空或待商家确认，不参与最低价排序。

点击商家链接前必须重新询价。价格变化时先阻断跳转、展示差异并要求用户再次确认。

## 6. 架构基线

- `apps/api`：Python 3.12、FastAPI、Pydantic、SQLAlchemy、Alembic。
- `apps/worker`：导入、报价同步、实体解析、索引投影和评测任务。
- `apps/android`：Kotlin、Compose、Hilt、Room、DataStore、Retrofit/OkHttp SSE。
- `apps/ops-web`：React、TypeScript、Vite、TanStack Query。
- `packages/domain`：纯领域模型和策略。
- `packages/agent-runtime`：唯一 Agent 运行时和 PostgreSQL checkpointer。
- `packages/connectors`：授权连接器和确定性夹具。
- `packages/retrieval`：结构化过滤、BM25、Qdrant、重排和证据。
- `packages/contracts`：OpenAPI/JSON Schema 及 Kotlin/TypeScript 生成客户端。

PostgreSQL 是业务事实源；Qdrant 是可重建检索投影；Redis 仅用于限流、短缓存和后台任务；对象存储保存有生命周期的媒体引用。数据库到索引使用事务 Outbox，禁止双写。

## 7. 公共接口基线

- `POST /v1/media`
- `POST /v1/threads/{thread_id}/turns`
- `GET /v1/agent-runs/{run_id}/events`
- `POST /v1/agent-runs/{run_id}/decisions`
- `GET /v1/products/{id}/offers?fresh=true`
- `POST /v1/offers/{id}/resolve`
- `GET/POST/PATCH /v1/lists`
- `GET/POST/PATCH /v1/cart`

Turn 创建必须使用 `Idempotency-Key`。SSE 支持 `Last-Event-ID`。公开事件仅包含脱敏的 status、message_delta、evidence、products、offers、comparison、approval_required、completed 和 failed，不输出思维链、密钥或原始授权响应。

## 8. 质量门禁

- 黄金用例中伪造价格、库存、销量、物流、保障、店铺身份或评分数量为 0。
- 100% 可见价格带来源、时间、有效期和验证级别；100% 外跳 URL 为允许域 HTTPS。
- 价格和商业承诺 grounded precision >= 0.98，整体事实依据精度 >= 0.95。
- Recall@10 >= 0.90，NDCG@10 >= 0.80，硬约束满足率 >= 0.90。
- 端到端任务完成率 >= 0.85，并报告 95% 置信区间。
- 工具参数 Schema 合法率 100%，未授权写操作和高风险越权执行为 0。
- 评测集不少于 600 条：300 购物、100 多轮、80 多模态、60 报价故障、60 安全/隐私。
- Android 至少覆盖 12 个 instrumentation 核心场景、四个一级页面截图回归和 TalkBack/可访问性验证。
- 清洁机器 30 分钟内可完成 bootstrap、夹具导入和本地验证。

## 9. 发布硬门禁

- 联盟/API 主体合同和真实凭据。
- 隐私、推广披露、消费者陈述和数据许可法律审核。
- 凭据轮换、生产限流、依赖与渗透测试。
- 真实提供方评测、报价抽样和小流量试运行。
- Android 正式签名、物理真机 HTTPS、可访问性和商店合规。

任一门禁未关闭时，不得宣称商业可用或正式发布。
