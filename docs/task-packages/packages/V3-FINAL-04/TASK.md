# V3-FINAL-04 MiMo与Android联合验收

## 目标
执行用户批准的一次长执行实习投递收口方案，AI应用实习为主，全栈证据为辅。

## 状态
in_progress；真实场景首次执行中，失败保留，不继承历史Release GO。

## 范围
MiMo与Android联合验收。仅声明路径内实施必要修改。

## 非目标
本轮不提交、推送、合并或发布；不做支付、订单、多Agent、生产身份或自动价格监控。

## 前置依赖
V3-FINAL-03。

## 路径所有权
evals/v3/final-scenarios.json、scripts/final_scenario_slots.py、scripts/run_final_acceptance.py：冻结24首次/6复测，按真实API/Worker/同一目录验收，付费调用须有已登记的场景归属；复测必须已有根因文档。
scripts/run_final_media_acceptance.py、render_media_acceptance.mjs与evals/v3/media：自有无文字示意图在Chromium渲染后经过真实MinIO/Worker/MiMo；媒体专项结果不冒充原生图库或照片鲁棒性，原生录音来源必须另行观察。
packages/agent-runtime的额度控制及相关迁移/测试；apps/api的Provider配置、budget_schema、迁移env及相关测试；scripts/start_v3_demo.ps1的显式预算会话；scripts/run_real_model_evaluation.py、scripts/run_mimo_specialized_acceptance.py、scripts/run_final_acceptance.py；Android真实验收测试；evals/v3/final-scenarios.json；docs/evidence/v3/final-*；本包。

## 2026-10-12 追加授权
用户直接授权A03-R1、A04-R1、A08-R1、A10-R1各一次，按此顺序执行。共同授权记录为evidence/A03-A04-A08-A10-EXTRA-AUTHORIZATION-20261012.json；原预算会话与2,000,000 Token累计上限不变，不重置账本，不覆盖首测，不授权A09复测或自动重试。

## 现状证据
2026-10-12另行直接授权A10-R4一次零模型调用收尾：scripts/run_final_android_safety_acceptance.py只复用A10-R3已完成的隔离身份，核对恢复/隔离后原生取消和确认删除；额度active=false，不创建Turn/Run、不重新批准。之前各次失败保留。
scripts/run_final_android_acceptance.py由本包维护，原生Runner完成回执与真实PostgreSQL状态同时判断；额外A01-R1、A06-R1、A07-R1分别由evidence/*-EXTRA-AUTHORIZATION.json中的直接人类授权启用，其他复测仍阻断。A06-R1与A07-R1只复用既有真实候选；额度记录active=false，不能获得付费调用预留，结果由完成后的实际回执写入。A07两阶段之间实际force-stop本包拥有的applicationId，不清数据；第二阶段重新从真实API恢复。
额度表迁移需要同步packages/domain/tests/test_migration_integration.py的当前schema集合，旧迁移不引用新预算元数据。
FINAL-01/evidence/current-state.json及docs/defects/V3-FINAL-CLOSEOUT.md；历史报告保留原分母。

## 执行步骤
1. 先实现跨进程用量、调用前额度与输出上限。
2. 各执行10黄金、4多模态、10Android一次。
3. 修复真实失败，仅在6复测槽位内复测。
4. 保存首测、复测及实际数据库/UI/Trace证据。

## 数据引用
自有60SKU、DEMO_FIXTURE、固定BGE revision、当前PRD、24+6场景槽位。

## 验收
- 24首次场景与最多6根因修复复测，总预算2000000Token
- 黄金10/10可解析、流程>=8/10；多模态4项正确
- Android>=8/10且媒体、审批、隔离、恢复通过

## 回滚
仅撤销本轮具体行级变更，保留用户已有改动与数据；不使用reset或clean。

## 停止条件
真实凭据/额度、必要设备或基础设施阻塞时停止相关路径；其余独立工作继续。不自动增加付费调用。

## 交接格式
命令、时间、退出码、数量、失败摘要、证据等级、当前候选状态及剩余门禁。
