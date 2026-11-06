# V3-INTERVIEW-REPAIR-01 十题修复与验证

## 目标
按 Q5 → Q3 → Q10 优先顺序实施十题修复，随后完成其他问题和回归，逐项更新状态。

## 状态
complete（本地实施与验收）；远端 CI、LIVE 与产品外部门禁单独保留。

## 范围
计划列明的代码、类型生成、依赖和必要测试；保留历史审查，修复状态单独记录。

## 非目标
不提交、推送、部署、调用付费模型或启用真实联盟；不替代物理设备、人审和发布验收。

## 前置依赖
V3-INTERVIEW-REPAIR-PLAN-01、两个审查包均 complete；相关路径拥有包已 complete，本包明确接管下列直接依赖路径。

## 路径所有权
本包、本 manifest、docs/evaluation/AGENT-INTERVIEW-REPAIR-STATUS-20261105.md、docs/plans/AGENT-INTERVIEW-REPAIR-PLAN-20261105.md（状态引用）、.gitattributes、package-lock.json、uv.lock、pyproject.toml、docs/security/evidence/（现有安全快照、SBOM、许可证清单）、packages/domain/tests/test_migration_integration.py（新凭据表纳入严格元数据断言）、packages/contracts/（OpenAPI 及对应生成类型）、scripts/generate_contracts.py、evals/agent/fake-trace.json、e2e/agent/、apps/api/src/ 与 tests/ 与 migrations/、apps/android/app/src/、apps/ops-web/src/ 与 e2e/（已观测的 Trace 夹具断言失配）、packages/agent-runtime/src/ 与 tests/、packages/retrieval/src/ 与 tests/、packages/connectors/src/ 与 tests/、scripts/tests/test_agent_interview_repairs.py、output/interview-repairs-20261105/。已有相关包均 complete；本包接管这些有直接修复依赖的路径。

## 现状证据
275项 Python 通过、1项本地嵌入组合跳过；25项原协议探针、55项 Android 单元、2项原生集成和8项 Web E2E 通过。不同层级不相加。

## 执行步骤
按 Q5、Q3、Q10 优先实施；随后完成其余组件、身份与客户端；逐项实测并收敛真实回归失败。

## 数据引用
原审查及修复计划、本轮状态报告和 evidence/verification.json；最终 JUnit 保存在 output/interview-repairs-20261105。

## 验收
代码修复、受影响回归、冷迁移/严格元数据、真实 PostgreSQL/MinIO/Qdrant、子进程、原生 HTTP/SSE及治理校验通过；外部门禁不被本地完成状态覆盖。

## 回滚
未提交；仅按本包明确 diff 撤销，保留旧审查与测试数据库，不 reset/clean/prune，不更动只读来源仓。

## 停止条件
本地实施验收结束；不自行推送、部署、启用 LIVE 或执行付费模型。

## 交接格式
状态报告逐题说明、验证命令/时间/数量及未关闭门禁；验证后停止本任务的测试服务。
