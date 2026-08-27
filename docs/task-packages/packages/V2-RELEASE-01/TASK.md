# V2-RELEASE-01 商业候选版本与发布门禁收口

## 目标

冻结唯一商业候选身份，聚合全部本地与外部门禁证据并形成明确发布 Go/No-Go。

## 状态

`blocked / NO-GO`

## 范围

- 冻结源码 commit、依赖锁、容器 digest、Schema、模型/提示、索引和 Android 签名候选身份。
- 汇总 unit、contract、integration、eval、security、LIVE、device、legal 和 human approval。
- 生成 SBOM、许可证、隐私/推广披露、回滚、监控、值班和事故响应包。
- 执行清洁 checkout 构建、迁移、部署 smoke 和候选包哈希验证。
- 明确记录未关闭门禁并 fail-closed 输出 No-Go。

## 非目标

- 不自动提交、推送、部署、发布商店、开放流量或代表商业主体批准。
- 不把本地任务包 complete、签名文件存在或 sender-side PASS 当作正式发布。
- 不在本包修复业务缺陷；缺陷退回责任包并重新冻结候选。

## 前置依赖

- `V2-LIVE-01` 完成且没有开放 P0/P1 或不满足阈值。

## 路径所有权

- `docs/release/`、发布 manifest、候选哈希、部署 smoke 和回滚证据。
- 发布工作流配置；不修改业务实现。

## 现状证据

- 当前 V2 本地可自主包已实现，但独立仓仍无候选 commit、正式签名或 live 证据。
- 外部门禁必须由对应权威关闭，不能由任务包自行推断。
- 当前发布矩阵明确为 `NO_GO`，见 `../../../release/release-gate-matrix.json`。

## 执行步骤

1. 冻结 ReleaseIdentity 和全部输入 digest。
2. 在清洁 checkout 重跑构建、迁移、静态、集成、安全和候选 smoke。
3. 核验法律、联盟、隐私、签名、LIVE、设备和商业批准原件。
4. 生成发布、回滚、监控、告警、数据删除和事故响应包。
5. 输出 Go/No-Go；任何硬门禁缺失均为 No-Go。

## 数据引用

- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`

## 验收

- [ ] 唯一候选 commit、artifact digest、Schema、模型/提示和索引版本均冻结。
- [ ] 清洁 checkout 全部本地门禁通过且没有未解释漂移。
- [ ] 联盟、法律、隐私、推广披露、独立渗透、签名、LIVE 和商业批准均有权威证据。
- [ ] 回滚、监控、值班、数据删除和连接器撤销演练通过。
- [ ] 发布结论明确为 Go 或 No-Go，不使用“基本完成”等模糊状态。

## 回滚

- 按 ReleaseIdentity 回退应用、模型/提示、连接器和索引；数据库只使用向前兼容或经验证迁移策略。

## 停止条件

- 任一身份漂移、候选被修改、硬门禁缺证据、出现 P0/P1 或回滚未验证时输出 No-Go 并停止。

## 交接格式

- 结果：ReleaseIdentity 和 Go/No-Go。
- 变更路径：docs/release、release workflows。
- 验证命令与结果：clean build、migration、smoke、artifact hash。
- 剩余外部门禁：逐项列出或明确为 0。
- 风险与下一包：Go 后交商业主体执行发布；No-Go 退回责任包。
