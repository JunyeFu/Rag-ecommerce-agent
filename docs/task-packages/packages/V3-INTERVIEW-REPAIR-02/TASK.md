# V3-INTERVIEW-REPAIR-02 Ops身份、HTTPS传输与Linux验收

## 目标
补齐生产 Ops 服务端身份及 Q9 实际传输边界，分别验证 Linux、Web 与真实服务，保留远端 CI 和 LIVE 的独立门禁。

## 状态
complete（本地实施及验收）；未发布、未启用真实联盟。

## 范围
独立运营凭据/角色/撤销/管理员命令、运营台会话、固定地址 HTTPS 重定向传输及受控实测。

## 非目标
不提交推送、不部署、不发放真实运营凭据、不执行付费模型或开启真实联盟。

## 前置依赖
V3-INTERVIEW-REPAIR-01 已 complete；接管下列已完成包的直接依赖路径，保留历史证据。

## 路径所有权
本包及 manifest、README.md（事实边界与本地修复状态链接）、playwright.config.ts（测试明确启用开发夹具）；docs/evaluation/AGENT-INTERVIEW-BATCH2-20261105.md、既有修复状态报告；apps/api/src/、tests/、migrations/；apps/ops-web/src/、e2e/；packages/connectors/src/、tests/；packages/domain/tests/test_migration_integration.py；scripts/generate_contracts.py、scripts/manage_ops_identity.py（根目录管理入口）与 Ops 客户端生成器；packages/contracts/、apps/android/app/src/main/java/com/ragcommerce/agent/generated/ApiContracts.kt（契约生成）；docs/security/evidence/；scripts/tests/test_agent_interview_repairs.py（Ops 状态变更的必要断言）；output/interview-batch2-20261105/。上一实施包 complete，本包接管这些直接依赖路径。

## 现状证据
Windows 299通过；Linux 298通过，8项跳过分别由6项TLS和2项缓存ONNX补验覆盖；Windows共享读取补验1项通过；Web4单元/10E2E/关闭开发身份2E2E通过；Android55单元通过。分组数量不当作一次全量运行。

## 执行步骤
实现与测试 Ops 权限及会话；复现并修复取消登录竞态；实现并在隔离命名空间验证真实TLS；完成两平台冷迁移、服务回归和缓存模型补验；更新状态并停止专用服务。

## 数据引用
第二批报告、原修复状态及本包 evidence/verification.json；output/interview-batch2-20261105 中的原生JUnit结果。

## 验收
服务端角色不能由请求头提升；安装与运营凭据隔离；撤销有效；退出及取消不恢复身份；真实socket绑定已验证IP且TLS/SNI正确；跨平台及治理检查通过。

## 回滚
保留未提交diff、数据库、QA镜像/快照与正负证据，不 reset/clean/prune 或永久删除共享资源。

## 停止条件
本地批次完成；实际部署、远端 CI 与 LIVE 需要各自输入和既有授权。

## 交接格式
第二批报告、操作命令、QA证据及未关闭门禁；专用服务停止，数据保留。
