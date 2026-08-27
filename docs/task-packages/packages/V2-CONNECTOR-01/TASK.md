# V2-CONNECTOR-01 授权报价连接器与深链安全

## 目标

建立统一报价连接器 SPI、确定性夹具、报价新鲜度和安全深链解析闭环。

## 状态

`complete`

## 范围

- 定义淘宝/天猫、京东、拼多多和授权 Feed 的连接器契约。
- 实现录制/合成夹具，不依赖 live 凭据即可运行 contract tests。
- 规范化 Offer、OfferQuote、DeepLink、错误、限流、重试和熔断。
- 实现 host/scheme/redirect 白名单、报价点击前 requote 和佣金披露。
- Discovery adapter 只输出链接和待确认状态。

## 非目标

- 不抓取需要绕过验证码、登录、风控、访问控制或条款的网页。
- 不实现 RAG、Agent、Android UI 或商家结算。
- 不在无主体授权时启用 live 连接器。

## 前置依赖

- `V2-DATA-01` 提供合法开发种子和许可状态。
- `V2-DOMAIN-01` 提供 Offer/Quote/DeepLink 契约。

## 路径所有权

- `packages/connectors/`。
- `apps/worker/jobs/connectors/`。
- `tests/contracts/connectors/` 和脱敏夹具。

## 现状证据

- 旧 Web search 没有商家商品身份、报价 TTL 或推广深链契约。
- 官方/联盟接口是否可用取决于主体、应用、权限和真实凭据。

## 执行步骤

1. 定义 connector capability、错误分类、速率和数据保留契约。
2. 为三个目标平台建立脱敏夹具和 contract tests。
3. 实现授权 API/Feed 适配器和 discovery-only 适配器边界。
4. 实现 requote、价格变化、不可用、超时和熔断行为。
5. 验证 SSRF、开放重定向、域名伪装和外部提示注入防护。

## 数据引用

- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`

## 验收

- [x] 三个平台 contract fixture 全部通过，文件哈希和字段映射可追溯。
- [x] LIVE_AUTHORIZED、FEED_VERIFIED、DISCOVERY_ONLY 不能互相升级，live 静态启用会失败。
- [x] 100% 夹具 URL 通过 HTTPS、精确 host 和每跳 redirect 校验。
- [x] 点击前 requote 可表达 unchanged、changed、unavailable、unverified。
- [x] 未知 Offer、策略拒绝和连接器失败只返回类型化错误，不合成价格、库存或最低价。

## 回滚

- 按连接器 feature flag 禁用并退回 discovery-only 或无结果；保留历史审计，不删除其他连接器数据。

## 停止条件

- 需要未经授权的 live 凭据、绕过站点控制、复制敏感响应或违反平台条款时停止。

## 交接格式

- 结果：连接器能力矩阵、fixture 和 contract 结果。
- 变更路径：connectors、worker connector jobs、contract tests。
- 验证命令与结果：contract、安全和临时服务 integration。
- 剩余外部门禁：各平台主体授权与 live 凭据。
- 风险与下一包：交给 V2-AGENT-01 与 V2-LIVE-01。
