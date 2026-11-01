# V3-UX-FIGMA-01 Figma可编辑Android设计与原生落地

## 目标

Figma可编辑Android设计与原生落地；仅完成有证据的本地范围，不继承历史发布结论。

## 状态

`in_progress`（31状态设计目录保留；10月24日同版TalkBack两字号8条指定路径通过，当前持久化复验与最终封版仍未关闭）

2026-10-24：按用户选择先完成不依赖Docker的范围。两个产品缺陷（探索双焦点、滚动后返回不可达）已修复；三入口触摸／键盘、默认／200%字号、弹窗及纵向候选主流程8/8通过。实际MainActivity＋HTTP内存fixture，不注入界面状态，不冒充PostgreSQL或真实模型验收；原始失败和一次0测试未知异常保留。当前回归与剩余项见 `docs/evidence/v3/android-talkback-20261024.json`，整体仍HOLD，0新增MiMo调用。

2026-10-22当前证据：`docs/evidence/v3/android-figma-accessibility-20261022.json`。已修复复选框语境、48dp触达、浅底小字对比度及验收用户归属；非付费回归分层记录。TalkBack服务绑定但遍历/激活没有完整通过回执，不能签收整包。下方10月21日为历史状态，原始失败保留。

2026-10-21：100%/200%字号的关联原生路径、UI与真实PostgreSQL终态见 `docs/evidence/v3/android-ux-native-20261021.json`。0新增MiMo调用。保留三入口/纵向推荐及既定美术；完整14状态、全部加载/失败/媒体/外跳和TalkBack未签收。

## 范围

- 读取现有DesignTokens和已实现交互，建立可编辑Figma原生Design稿。
- 覆盖任务/探索、候选反馈、差异比较、无匹配、保存/历史、审批、我的及错误恢复。
- 通过Figma设计上下文对照实现Compose；保持三入口/纵向推荐/骨白祖母绿荧光绿珊瑚色硬边美术。
- 运行契约漂移、Python定向、Android unit/lint/build与可执行设备验收，保存实际证据。

## 非目标

不增加订单/支付/营销/自动监控/多Agent，不提交推送发布，不调用额外付费模型。

## 前置依赖

V3-UX-EXPLORATION-01；前包验收记录明确后进入下一包。

## 路径所有权

- `apps/android/app/src/`
- `docs/design/`
- `docs/media/android-figma-a11y-20261022/`（本轮精选设计／原生验收截图）
- `docs/evidence/v3/`
- `docs/task-packages/`
- `scripts/`
- 本包 TASK/data/pitfalls/evidence、manifest登记及总收口计划。

## 现状证据

2026-10-21读取现有源码和PRD：三入口与纵向推荐存在；保存区域只显示标题；对话只显示最近三条Agent消息；比较以摘要和数量为主。以当前代码而非旧报告为准。

## 执行步骤

2026-10-23补验：修正TalkBack输入链路与观察器，先在系统页面对照shell注入与模拟器硬件事件，再在隔离安装上验证顺序遍历、自然激活、回退与两档字号。允许必要的真实模型调用，沿用原共享预算；默认fake用于无障碍排障。新增原生观察器及主机执行脚本属于现有Android/scripts路径。保留旧失败、三入口、纵向推荐及现有美术；通过新回执后只关闭对应无障碍门禁。

2026-10-22本轮：对齐既有14个Figma画面及当前已实现的保存批量比较/全局待购，补运行状态矩阵；在Pixel_9a隔离身份上执行默认/200%字号与原生无障碍（含实际TalkBack焦点/手势）验收。假Provider与真实API/PostgreSQL，禁止新增真实模型调用；语音人声及Chrome首次条款仍不代办。证据与测试脚本位于本包已有路径所有权，不以静态语义或视觉fixture代替实际TalkBack证据。

1. 读取现有DesignTokens和已实现交互，建立可编辑Figma原生Design稿。
2. 覆盖任务/探索、候选反馈、差异比较、无匹配、保存/历史、审批、我的及错误恢复。
3. 通过Figma设计上下文对照实现Compose；保持三入口/纵向推荐/骨白祖母绿荧光绿珊瑚色硬边美术。
4. 运行契约漂移、Python定向、Android unit/lint/build与可执行设备验收，保存实际证据。

## 数据引用

- docs/plans/ANDROID-DECISION-UX-UPGRADE.md
- docs/task-packages/shared/business-data.json
- docs/task-packages/shared/development-data.json
- 自有60 SKU、DEMO_FIXTURE报价；不读取环境凭据。

## 验收

- [x] 10月24日限定TalkBack原生矩阵8/8；不据此签收当前持久化或完整发布门禁。
- [ ] 不是网页套壳，不嵌入整张截图当成页面。
- [ ] 所有公开控件连接真实Repository/API，测试不注入成功作为E2E通过。
- [ ] 默认/大字号、加载/空态/失败/恢复、纵向候选动作均可达。
- [ ] 必要测试通过，实际未运行项单列；任务包校验通过。

## 回滚

只撤销本包新变更；不reset/clean、不覆盖既有脏文件。迁移不清空业务数据，恢复前先确认目标与可回滚范围。

## 停止条件

新增付费调用、删除用户资产、远端发布需另行授权；外部阻塞只暂停相关验收，不伪造通过。

## 交接格式

结果／变更路径／命令与实际结果／未验收事项／下一包。

