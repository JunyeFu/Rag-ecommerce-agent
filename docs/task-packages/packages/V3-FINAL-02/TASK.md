# V3-FINAL-02 Agent闭环与真实多模态

## 目标
执行用户批准的一次长执行实习投递收口方案，AI应用实习为主，全栈证据为辅。

## 状态
in_progress；原生媒体与真实闭环尚未全部签收，不继承历史Release GO。

## 范围
Agent闭环与真实多模态。仅声明路径内实施必要修改。

## 非目标
本轮不提交、推送、合并或发布；不做支付、订单、多Agent、生产身份或自动价格监控。

## 前置依赖
V3-FINAL-01。

## 路径所有权
F64已观察真实200%字体长候选把关键动作挤出固定卡片，范围为EditorialShoppingApp.kt与ShoppingFlowTest.kt；大字体下摘要卡保留身份/报价/证据与操作，完整约束/风险/商业事实放入原滚动证据弹窗，保留VerticalPager主/次/再次手势，不用候选内嵌套滚动替代翻页。不改API或模型调用。
F63独立NFR06检查发现推荐返回对话后无入口重开已有推荐，增加EditorialShoppingApp.kt、ShoppingModels.kt与ShoppingReducerTest/ShoppingFlowTest的最小往返行为修复；只切换现有结果视图并保留比较选择，不发Turn、不改纵向浏览美术。
F62原生NFR06观察及真实快照已证实：后续操作覆盖Mission目标。范围增加runtime/contracts.py、runtime.py、API service.py/postgres_index.py/app.py及对应测试；仅区分私有命令的购物目标与本轮操作、修正快照/事件投影，保持公开0.2.0、模型输入和审批参数不变。旧历史事件保留，不重写业务数据。
2026-10-13补齐验收入口时观察到共用确认页把音频也称作图片线索；EditorialShoppingApp.kt仅将说明改为识别内容，适用于两种实际媒体，行为不变。
2026-10-13 N02实际发现F54：报价读取忽略fresh并自动延长有效期。最小修复范围增加demo.py/postgres_demo.py、报价独立schema与增量0015、migrations/env.py、erasure.py及对应测试；所有报价工具复用同一owner报价状态，删除用户数据覆盖新增归属表。公共0.2.0类型不变。
apps/api/src/ragcommerce_api/{media,service,schema_v1,v3_schema,postgres_index,demo,persistent_demo}.py与增量迁移；packages/agent-runtime/src/ragcommerce_agent_runtime/；媒体、Provider、API测试；Android主源码与对应测试；契约注册表、生成器及三端生成文件；相关证据。

## 现状证据
2026-10-12源码修复范围：Provider写提案的字段诊断与明确报价/数量一致性；Android审批监听与HTTP错误恢复；当前报价链接安全边界。只执行本地确定性与独立基础设施回归，不新增付费验收槽位，不覆盖此前失败。
审批批准必须沿用现有api_turns durable任务：修改service/postgres_index/app和现有API/PG测试，持久化批准命令后立即202，Worker接管；不新增队列、配置项或迁移，不为旧同步行为建兼容层。Android在真实终态到达后读取待购状态。
scripts/start_v3_demo.ps1沿用既有运行源码哈希，加入本轮安全边界contracts/tools/store/postgres_store；仅重启记录中本项目拥有的API/Worker/Ops及Compose资源，数据库和媒体卷保留，不新增付费场景。
真实A01准备时发现证据入口只是文字，修复EditorialShoppingApp.kt的商品/报价来源弹窗；ShoppingFlowTest视觉复验和FinalScenarioApiTest原生真实点击共同验收，不注入业务状态。
audio.transcribe固定为native PCM WAV输入；允许scripts/generate_agent_artifacts.py同步现有生成工件，不改历史证据结论。
scripts/generate_agent_artifacts.py复用现有工具契约生成流程，同步audio.transcribe注册表和生成事件工件。
FINAL-01/evidence/current-state.json及docs/defects/V3-FINAL-CLOSEOUT.md；历史报告保留原分母。

## 执行步骤
1. 实现共享媒体读取和MiMo多模态理解。
2. 增加media_interpreted、待确认快照与确认动作。
3. 实现原生WAV录音、预览和取消。
4. 回归探索、推荐、比较、清单、待购、审批与金额事实。

## 数据引用
自有60SKU、DEMO_FIXTURE、固定BGE revision、当前PRD、24+6场景槽位。

## 验收
- 原生录音、选图、实际理解、用户确认接入同一Agent链
- 媒体归属、过期、审批与恢复通过
- G03按实际根因修复，商业事实约束保留

## 回滚
仅撤销本轮具体行级变更，保留用户已有改动与数据；不使用reset或clean。

## 停止条件
真实凭据/额度、必要设备或基础设施阻塞时停止相关路径；其余独立工作继续。不自动增加付费调用。

## 交接格式
命令、时间、退出码、数量、失败摘要、证据等级、当前候选状态及剩余门禁。
