# V2 Engineering Agreements

## Authority

1. 当前用户指令。
2. 本仓源码、Git、运行态、测试和命名验证器。
3. `docs/baseline/V2-REDEVELOPMENT-BASELINE.md` 与当前任务包。
4. 旧仓源码与历史任务包，仅作为输入证据。
5. 历史文档、截图和固定测试数字。

## Repository Boundaries

- `D:\Agent\04-rag-ecommerce` 是只读来源仓。不得 reset、clean、暂存、提交、覆盖或移动其文件。
- V2 不复制旧仓业务实现形成第二个单体；只迁移经审查的契约、数据、测试思想和领域规则。
- 不读取、复制或输出 `.env`、`.env.docker`、`local.properties`、签名文件或凭据内容。
- 未经明确授权，不提交、不推送、不部署、不启用真实联盟连接器。

## Commercial Truth

- LLM 不生成价格、原价、库存、销量、物流、保障、店铺身份或评分事实。
- 展示价格必须来自 `OfferQuote`，并带来源、采集时间、失效时间和验证级别。
- `DISCOVERY_ONLY` 不参与最低价排序，价格为空或显示“待商家确认”。
- 支付、订单、退款和履约不属于首版工具注册表。

## Evidence Levels

- unit、contract、integration、provider sandbox、LIVE、physical-device、legal、human acceptance 和 release 必须分别报告。
- 任务包 `complete` 只覆盖其本地范围；`external_gates` 未关闭时不得宣称商业可用或正式发布。
- 运行证据必须记录命令、时间、退出码、数量和失败摘要，不保存密钥或完整敏感日志。

## Task Package Workflow

- 开工前确认依赖包已完成、路径所有权无冲突、外部输入可用。
- 只修改当前包声明的路径；跨包变更先更新任务包边界。
- 验收后更新 `evidence/verification.json`，再将 manifest 状态改为 `complete`。
- 每次变更后运行 `python scripts/validate_task_packages.py`。
