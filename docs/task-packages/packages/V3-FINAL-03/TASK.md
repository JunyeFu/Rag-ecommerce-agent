# V3-FINAL-03 真实质量证据

## 目标
执行用户批准的一次长执行实习投递收口方案，AI应用实习为主，全栈证据为辅。

## 状态
in_progress；当前分层质量证据已执行，完整用户路径仍需联合验收。

## 范围
真实质量证据。仅声明路径内实施必要修改。

## 非目标
本轮不提交、推送、合并或发布；不做支付、订单、多Agent、生产身份或自动价格监控。

## 前置依赖
V3-FINAL-02。

## 路径所有权
2026-10-24 F60继续排障：profile_standard_uvicorn.py对比uvicorn.run正常CLI的预加载与Server.run诊断导入，补充逐请求/submit/GC时间线；只观测不改变GC、日志或阈值。修复须有实际因果证据，最终使用无观测补丁的正常CLI与两个独立Worker完整十批×30签收，保留每次失败。范围沿用app.py、observability.py、service.py、postgres_connection.py及相应最小回归测试。
F60实际时间线定位HTTP转发等待后，最小修复增补http_middleware.py、test_http_middleware.py：用直接ASGI消息转发替换两层BaseHTTPMiddleware，保留开发身份响应头、Trace头、结构化日志及未缓冲SSE，不改变认证、数据库、GC和访问日志。
F60真实BGE补验首批300.6ms失败后，实际发现每Worker八通道重复加载相同ONNX模型（约1GB/Worker）。增补retrieval_config.py与test_retrieval_composition_integration.py：仅共享同进程同固定快照的只读BGE提供者，索引/客户端仍通道独立；真实八路并行检索先红后绿，随后新数据库完整十批，不丢弃冷启动批次、不降低阈值。
F60共享模型后第6批仍260.8ms，增补scripts/profile_durable_client.py同步只读记录客户端send/GC/事件循环时间线，核对是否将压测端暂停归因API；不修改run_v3_durable_load.py的负载、计时、分位数或门槛。
F60隔离实验确认启动后约21万长期存活对象在回收0对象时仍耗50–61ms扫描，增补persistent_demo.py启动生命周期与test_startup_gc_integration.py：启动完成先回收启动垃圾，再冻结进程生命周期静态对象；运行期新对象仍正常GC、阈值不变。子进程复验发现解释器启动前已冻结377对象，故不在app退出时全局unfreeze破坏已有策略。不得gc.disable或修改触发阈值；独立子进程生命周期红绿回归后，仅无观测标准CLI＋真实BGE完整十批签收。
F60静态扫描修复后第7批仍225.3ms，正常CLI缺少应用INFO日志（Logger继承WARNING、无自身Handler）使耗时无法复核；在既有http_middleware.py一次配置结构化日志stderr输出，并在test_http_middleware.py新增无Collector/无日志外部配置的子进程检查。用于当前消费者排障，不增加重试或通用监控。
2026-10-24实际Ops画面发现页头将固定旧日期伪装成证据时点：增补apps/ops-web/src/components.tsx、对应样式及既有Ops Playwright用例，仅移除虚假时点并显示数据来源说明，不新增伪实时钟或公共API。
2026-10-24实际冷启动暴露MinIO桶创建竞态：范围增补apps/api/src/ragcommerce_api/media.py、test_minio_media_integration.py与最小异常边界单测。只接受同一账号已创建成功的BucketAlreadyOwnedByYou，其他S3错误原样传播；先真实并发红测、修复后绿测，再从独立新数据库重跑Worker启动／十批容量，保留首次中断和未领取任务。
F64增加scripts/inspect_existing_recommendation_accessibility.py，在已恢复的专用QA真实任务上做100%/200%文字、证据弹窗与三层VerticalPager只读检查，前后GET快照对照；不发送Turn、保存/待购/审批，finally恢复字体，仅私有截图/XML和摘要。
F60两组正常启动/诊断差异仍复现后，增加scripts/profile_standard_uvicorn.py；使用Uvicorn标准Server.run与字符串应用导入，在实际标准生命周期观测submit、GC与日志emit耗时，原日志照常输出，不关闭日志、不改GC或业务实现。仅fake隔离数据库，观测仍不是最终容量签收。
F60正常启动十批出现每第三批接受延迟尖峰后，profile_turn_acceptance.py增加只读GC callback计时；不关闭GC、不改变阈值，诊断归属仍非正式容量签收。
NFR06增加scripts/inspect_android_large_font.py，只在专用QA AVD对真实MainActivity做100%/200%字体、三入口只读导航与交互边界捕获，finally恢复原字体；不提交Turn、不批准/删除/上传。输出仅本轮私有截图/XML与非敏感摘要，不注入ShoppingUiState。
NFR07增加scripts/verify_android_cold_start.py，限定已确认的RagFinalSafety20261012与本项目safetytest包，30次am start -S -W，不清数据/日志、不开录音、不发送Turn；按应用UID和时间窗统计fatal/StrictMode，保留已安装APK范围，不以旧APK签收最终同版。
F60接受延迟失败后增加scripts/profile_turn_acceptance.py，仅在独立fake环境对真实TurnService/PG接受路径做阶段壁钟诊断；cProfile在Python3.12并发下归属不可靠，旧诊断保留但不用于因果归因。不把直连服务/同进程HTTP测量当容量通过，不输出凭据或用户输入。
N11复审发现PRD NFR04要求10批×30并发及从202到首状态计时；增加run_v3_durable_load.py连续批次与计时修正及apps/api/tests/test_durable_load_measurement.py，沿用隔离fake/真实PostgreSQL，不重跑MiMo。
N02实际预检发现F55，范围增加GoldenScenarioApiFlowTest.kt和run_android_instrumentation_case.py及定向回执测试：health斜杠拼接与Assumption不得签为原生PASS。
2026-10-13 N02补齐原生验收入口：run_final_android_acceptance.py/安全执行器与FinalScenarioApiTest.kt；A02仅在本人可即时配合麦克风时领取原始名额，A09先通过普通API读取自然过期报价再领取零模型名额。增量0015对应packages/domain/tests/test_migration_integration.py的表结构断言同步加入独立quote_schema。
实际格式门禁暴露生成Python与formatter漂移，增加scripts/generate_contracts.py和三端生成类型；统一生成前格式化，API版本不变。
独立预检发现SBOM/安全锁文件报告漂移与旧V2元数据，增加scripts/generate_sbom.py、docs/security/evidence与toolchain.versions.json；只刷新实际清单，不把本地扫描当成外部漏洞或法律审查。
evals/v3/retrieval-closeout.json；scripts/run_local_embedding_acceptance.py、scripts/run_v3_durable_load.py及必要的验收脚本；API/Worker/检索/Agent/Android/Ops测试；docs/evidence/v3/final-*与任务包证据。
scripts/run_frozen_retrieval_acceptance.py独立硬约束判定；针对首次并发实测失败，修复API app.py/service.py异步边界与Worker执行调度，不改变权限、事务、租约和幂等约束。
第二次并发仍未达门槛：每个事件/读取建立新PG连接，接入官方psycopg pool，范围为pyproject.toml/uv.lock、agent-runtime的postgres_connection.py/postgres_store.py、API的postgres_index.py/postgres_demo.py。事务异常直接传播，不重试业务操作。
playwright.config.ts支持明确使用已启动真实基础设施服务；Ops回归共五项并验证刷新后数据库Trace/冲突/排队/审计状态，不启动其他项目的8080服务。
Playwright发现Ops Trace仍继承静态fixture：修复ops.py/postgres_ops.py、generate_contracts.py与生成OpenAPI/TS及Ops views.tsx，真实日志投影、检索模式和未知用量/金额如实显示；对应集成与浏览器复验。
扩展到ops_state_schema.py与增量0014、seed_demo_ops.py：数据库声明自有演示来源、合成复核练习与未签收门禁，删除真实模式继承的示例成功/健康数字。Windows gradlew.bat修复已观测的失败码被吞问题。
scripts/verify_worker_process_recovery.py使用独立数据库和真实子进程故障注入；runtime/contracts及public_event记录非终态检查点恢复，使Ops不再查询永远不会产生的run_resumed事件。五分钟租约自然到期，不修改系统时钟或租约时间戳。

## 现状证据
检索表示遗漏目录scenarios/highlights，构建前纳入已有可信用途字段；normalization.py补全自有演示品牌别名。增加scripts/generate_retrieval_closeout.py在首次验收前生成并冻结查询，后续只允许check；不按冻结集结果调参。
FINAL-01/evidence/current-state.json及docs/defects/V3-FINAL-CLOSEOUT.md；历史报告保留原分母。

## 执行步骤
2026-10-24 F60后续完成：四项实测贡献/诊断缺口按声明范围修正；最终无观察器正常CLI、双Worker、本地BGE/真实Qdrant完整10×30通过，接受p95=182.079ms、最慢批190.832ms、首状态111.482ms；实际DB300次local检索记录及300唯一成功终态。237 Python/0skip、契约/11工具生成通过。所有中间失败与诊断记录保留，详见final-F60-review-20261024.json；不关闭整个包或最终同版门禁，0新MiMo。

2026-10-24结果：MinIO实际冷启动竞态及Ops虚假旧时点已修复；231 Python／Ops最终5项、固定基础设施／迁移／检索／自然租约及HTTP进程恢复按声明范围通过。F60十批300任务均完成但接受p95=229.731ms，批1/3/5未过；诊断路径133.038ms不替换验收失败，根因仍未确定。本包不标complete，0新MiMo。见`docs/evidence/v3/final-infrastructure-recheck-20261024.json`，原始失败保留。

2026-10-24 Docker恢复后复验：使用独立Compose项目／卷／数据库与已登记的本地QA端口，执行固定镜像健康、Alembic upgrade/current/check、完整非付费Python分层测试、真实Qdrant/BGE、两独立Worker十批×30并发、自然租约故障恢复及Ops五工作流。模型显式fake，不读取已有凭据；不使用站点启动服务，不操作其他项目容器。保留首次失败；本轮证据为docs/evidence/v3/final-infrastructure-recheck-20261024.json及其子报告。录音暂缓，Chrome首次配置需要本人时再提示；不继承历史发布GO。

2026-10-22当前非付费增量见`docs/evidence/v3/android-figma-accessibility-20261022.json`：192无数据库、36真实基础设施、55 Android单测、Ops五工作流、冻结本地BGE三路及单批30 durable Mission通过；视觉fixture与TalkBack另列。单批观测不替代原十批NFR或最终媒体后同版签收；0新增真实模型调用，不关闭整个FINAL-03。

1. 冻结分层查询与多相关qrels。
2. 执行真实BGE三路消融并报告困难项。
3. 执行真实基础设施、并发与恢复测试。
4. 执行Python、契约、Android、Ops与治理验证。

## 数据引用
自有60SKU、DEMO_FIXTURE、固定BGE revision、当前PRD、24+6场景槽位。

## 验收
- 冻结120查询，40开发/80验收，BM25/BGE/RRF同输入
- 真实PG Worker30并发无丢失或重复写入
- 必要全套回归与Ops五工作流通过

## 回滚
仅撤销本轮具体行级变更，保留用户已有改动与数据；不使用reset或clean。

## 停止条件
真实凭据/额度、必要设备或基础设施阻塞时停止相关路径；其余独立工作继续。不自动增加付费调用。

## 交接格式
命令、时间、退出码、数量、失败摘要、证据等级、当前候选状态及剩余门禁。
