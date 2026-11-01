# V3 Engineering Agreements

## Authority

1. 当前用户指令。
2. 本仓源码、Git、运行态、测试和命名验证器。
3. `docs/baseline/V3-AGENT-FIRST-BASELINE.md` 与当前任务包。
4. 旧仓源码与历史任务包，仅作为输入证据。
5. 历史文档、截图和固定测试数字。

## Repository Boundaries

- `D:\Agent\04-rag-ecommerce` 是只读来源仓。不得 reset、clean、暂存、提交、覆盖或移动其文件。
- V3 不复制旧仓业务实现形成第二个单体；只迁移经审查的契约、数据、测试思想和领域规则。
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

## Local Storage

- 复用 `output/`；仅在批次/里程碑结束检查新增产物，不按每次调用巡检或重复生成全量日志、截图、ZIP及克隆。
- 当前源码/人工修改、lock、APK/正式网页材料与必要恢复状态原地保留；F60等关键正负证据保留可恢复集合，冷日志/trace及时无损归档至 `_archive/`，相同截图可合并去重，不机械重压图片/视频/模型。
- 不移动 `.git`、凭据、共享缓存、在用依赖或未结束的模拟器恢复点。已确认失效的项目独占构建物及归档验证可读后的原件，仅同盘移至 `D:\_Codex待人工删除\电商Agent\<批次>\<原相对路径>`，不覆盖，保留一份短清单。
- 不永久删除或 clean/prune/purge；同盘隔离实际释放为0。空间收尾不启动模型、录音、验收、下载或服务，不改变整体HOLD。
