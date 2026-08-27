# V2-BASE-00 独立仓与工程治理基线

## 目标

建立可在清洁机器复现的 V2 单仓工程骨架、契约入口、CI 基线和任务包门禁。

## 状态

`complete`

## 范围

- 初始化 apps/packages/infra/docs/evals/data 的所有权边界。
- 固定 Python、JDK、Node、容器和生成客户端的版本来源。
- 建立 OpenAPI/JSON Schema 入口、ADR、CI、依赖锁和一键本地验证命令。
- 将任务包验证接入清洁 checkout CI。

## 非目标

- 不实现商品、连接器、RAG、Agent、Android 业务页面或运营台业务。
- 不导入旧仓业务代码和用户数据。
- 不配置生产凭据、签名、域名或部署环境。

## 前置依赖

- 无。

## 路径所有权

- `README.md`、`AGENTS.md`、根级构建配置。
- `.github/workflows/`、`infra/`、`docs/adr/`、`docs/task-packages/`、`scripts/`。
- apps/packages 的空模块和契约骨架，不含业务实现。

## 现状证据

- V2 已是独立空 Git 仓，旧仓当前状态保存在 `docs/baseline/source-snapshot.json`。
- 重开发决策冻结于 `docs/baseline/V2-REDEVELOPMENT-BASELINE.md`。

## 执行步骤

1. 创建单仓模块、版本清单和依赖锁。
2. 创建开发容器或等价 bootstrap，并固定本地服务端口。
3. 建立契约生成、lint、unit、integration、Android 与 Web CI 占位工作流。
4. 建立 ADR、贡献指南、问题/PR 模板和证据输出规范。
5. 在清洁 checkout 执行 bootstrap 与任务包验证。

## 数据引用

- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`

## 验收

- [x] 清洁源副本 18.1 秒完成 bootstrap 和无 live 凭据的基础验证。
- [x] Python、JDK、Node、Gradle 和容器依赖均有锁与明确版本源。
- [x] OpenAPI 与 Python/Kotlin/TypeScript 生成客户端存在确定性漂移检查。
- [x] `python scripts/validate_task_packages.py` 通过（13 包，0 错误，0 警告）。
- [x] CI 策略守卫验证不读取本机忽略文件或输出环境值。

## 回滚

- 仅删除本包新建的空模块、工作流和根配置；保留任务包基线和旧仓快照。

## 停止条件

- 需要修改旧仓、安装未审查的全局工具、引入未锁定来源或覆盖机器配置时停止。

## 交接格式

- 结果：工程骨架和清洁 CI 状态。
- 变更路径：根配置、infra、workflow、ADR 和空模块。
- 验证命令与结果：bootstrap、契约生成和任务包验证。
- 剩余外部门禁：无。
- 风险与下一包：交给 V2-DATA-01 与 V2-DOMAIN-01。
