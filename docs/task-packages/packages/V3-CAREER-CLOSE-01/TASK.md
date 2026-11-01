# V3-CAREER-CLOSE-01 求职收口

## 目标
关闭已观测的运行配置、Provider预算隔离及质量证据缺口，保持Agent-first产品。

## 状态
in_progress；未完成真实设备/干净启动不能标complete。

## 范围
运行配置、模型预算与Trace身份、真实embedding消融、durable压测、Android真实测试档；外部五包只管理产物。

## 非目标
不实现支付订单、多Agent，不提交推送；报价不升级LIVE。

## 前置依赖
V3-PLATFORM-01；当前用户批准方案与2026-10-08写前快照。

## 路径所有权
本批验收另含 scripts/android_recovery.init.gradle 的独立包名参数、Android ExplorationApiTest/ExplorationTest，以及外部导航的第七批报告与状态摘要。仅隔离安装包可被测试强制停止，不动原应用数据。
探索补齐批次：apps/api/src/ragcommerce_api/{exploration,service,postgres_index,schema_v1,app,commerce,demo}.py、迁移0011及相关API测试；packages/agent-runtime的contracts/runtime；OpenAPI与生成器及三端生成类型；Android的ShoppingModels/ShoppingRepository/ShoppingViewModel/EditorialShoppingApp与对应测试；docs/plans/EXPLORATION-CLOSE.md及本包证据。复用已完成的平台依赖，不改未提交的其他功能；外部导航同步本批结果，不标记整体完成。
第八步模拟器验收：scripts/emulator_recovery_backend.py、scripts/android_recovery.init.gradle、apps/android/app/src/androidTest/java/com/ragcommerce/agent/EmulatorRecoveryApiTest.kt；独立测试applicationId，真实UI/API/数据库状态，不注入ShoppingUiState，不使用真实模型。
第八步第五批：postgres_demo.py、v3_schema.py、erasure.py、迁移20261008_0010及test_postgres_api_integration.py；两种写工具的持久幂等回执与业务写入同事务，故障注入验证不覆盖后续用户修改。
第八步第四批：service.py、postgres_index.py、app.py 与 API 单元/集成测试；协调 Mission 编辑、澄清版本更新和审批，竞争返回409；不扩展支付或自动重试。
第八步第三批：apps/api/src/ragcommerce_api/service.py、postgres_index.py、apps/api/tests/test_postgres_api_integration.py；同一run审批互斥、拒绝后的数据库重建恢复。使用隔离临时数据库，不改银行服务；跨Mission编辑事务及设备验收另行记录。
第八步第二批：apps/android/app/src/main/java/com/ragcommerce/agent/data/ShoppingRepository.kt、ui/ShoppingViewModel.kt 及 apps/android/app/src/test/java/com/ragcommerce/agent/ShoppingProtocolTest.kt；限服务端快照恢复、本地审批与游标同步，不改纵向推荐视觉。
第八步首批增量：apps/api/src/ragcommerce_api/service.py、apps/api/tests/test_turn_api.py；packages/agent-runtime/src/ragcommerce_agent_runtime/runtime.py；packages/contracts/openapi.json、scripts/generate_contracts.py 及其 Python/Kotlin/TypeScript 生成文件。范围为快照游标所属 run 和拒绝审批后的终态保存；Android 消费接线、跨事务并发审批和探索链路另行验收。
本轮C07金额拦截的最小诊断另覆盖 packages/agent-runtime/src/ragcommerce_agent_runtime/runtime.py；仅输出被拦金额的最小数值诊断，不保存完整模型文本，不改变事实门禁。
apps/api/src/ragcommerce_api/provider_config.py、persistent_demo.py；apps/worker/src/ragcommerce_worker/persistent_demo.py；packages/agent-runtime/src/ragcommerce_agent_runtime/model_provider.py；相关tests；scripts/run_real_model_evaluation.py、run_mimo_specialized_acceptance.py、run_local_embedding_acceptance.py、run_v3_durable_load.py；apps/android/app/src/androidTest/；docs/defects/V3-CAREER-CLOSE-20261008.md；docs/evidence/v3/；本任务包与manifest。

## 现状证据
配置回归、顺序预算、并发预算三个测试已失败复现；修复后Provider相关19 passed。写前166文件级dirty记录保存在外部导航。

## 执行步骤
1. 固定180秒/48000单run预算，保证顺序/并发隔离。
2. 校正真实模型Trace身份；执行10黄金/4专项、10Android槽位，失败不重跑。
3. 真实BGE三路消融和持久Worker30并发；全套相关回归。
4. 核对当前证据及未完成门禁，向外部站点交接，不自动发布。

## 数据引用
自有60SKU、黄金10、专项4、自动challenge；DEMO_FIXTURE。

## 验收
Provider隔离回归通过；真实/fixture分档；Android至少8/10，安全项全通过；真实基础设施、消融、当前回归与任务包验证通过。

## 回滚
仅还原本轮具体行级变更，保留用户改动；不用reset/clean。

## 停止条件
缺权限/设备/基础设施保留阻塞；24槽位耗尽后不得重跑。

## 交接格式
命令、时间、退出码、数量、失败摘要、证据等级及剩余门禁。
