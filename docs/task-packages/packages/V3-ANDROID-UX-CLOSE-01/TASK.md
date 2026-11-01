# V3-ANDROID-UX-CLOSE-01 Android Agent 接口与视觉收口

## 目标

把当前 Android Agent 从“视觉完成、业务语义不完整”收口为可演示、可验收的购物 Agent：写操作有明确确认，报价事实可理解，Agent 过程可见，推荐与比较能支持真实决策。

## 状态

`planned`

## 范围

- 接口与状态：待购/保存/重新询价/安全外跳的请求、审批、幂等、错误和恢复语义。
- Agent 体验：澄清、阶段进度、约束摘要、推荐依据、失败恢复。
- 推荐视觉：主推荐 → 次推荐 → 再次推荐纵向结构、价格真实性、风险、关键差异和动作反馈。
- 决策视觉：移动端差异比较、保存方案、待购计划管理、重新询价和撤销。
- 文案收口：隐藏内部枚举、原始 source ref、API/运行态术语；保留用户能理解的证据说明。
- Android UI/API 联动测试、ADB 真点击证据、截图和验收记录。

## 非目标

- 不实现真实支付、订单、退款、物流或联盟 LIVE 报价。
- 不改变已确认的三入口信息架构和编辑化视觉方向。
- 不新增备用模型、静默 fallback、宽泛重试或旧版本兼容层。
- 不把 `DEMO_FIXTURE` 升级为真实商业事实。

## 前置依赖

- `V3-AGENT-PROGRESS-01`
- `V3-DECISION-WORKBENCH-01`
- `V3-ACTION-APPROVAL-01`
- `V3-ANDROID-01`
- 当前审计：`docs/defects/V3-ANDROID-AGENT-UX-BUSINESS-AUDIT-20260922.md`

## 路径所有权

- 2026-10-02 真实验收：`scripts/run_mimo_specialized_acceptance.py`（修正已观测的测试入口签名漂移）、`docs/defects/V3-REAL-ACCEPTANCE-20261002.md`、`output/real-acceptance-20261002/`（临时脱敏报告）。
- 本轮状态一致性缺陷及验收：`docs/defects/V3-STATE-CONSISTENCY-AUDIT-20261002.md`。
- `apps/api/tests/`、`apps/android/app/src/test/`（本包状态语义回归测试）。
- `apps/android/app/src/main/java/com/ragcommerce/agent/`
- `apps/android/app/src/androidTest/`
- `apps/api/src/ragcommerce_api/`（仅本包接口契约和状态语义）
- `packages/contracts/`（生成契约及漂移测试）
- `docs/task-packages/packages/V3-ANDROID-UX-CLOSE-01/`
- `output/adb-real-click-*/`（临时证据，不进入发布资产）

## 现状证据

- `output/adb-real-click-20260922/ui-07-after-send.xml`：推荐完成后直接展示商品卡和写操作按钮。
- `output/adb-real-click-20260922/ui-08-approval.xml`：点击待购后出现“已加入 API 驱动的待购集合”，未出现用户可理解的确认面板。
- `output/adb-real-click-20260922/screen-09-secondary.png`、`screen-10-again.png`：三张推荐卡重复相同动作和通用理由。
- `output/adb-real-click-20260922/screen-13-decisions.png`：决策页有候选数量和待购卡，但缺少移动端差异表和管理动作。
- `apps/android/app/src/main/java/com/ragcommerce/agent/ui/ShoppingViewModel.kt:188-206`：保存和待购写入成功后仅更新状态文案。
- `apps/android/app/src/main/java/com/ragcommerce/agent/data/ShoppingRepository.kt:389-405`：待购写入直接调用购物车 API。
- `apps/android/app/src/main/java/com/ragcommerce/agent/EditorialShoppingApp.kt:511-651`：纵向推荐与卡片动作实现；`624/716/774/983` 暴露原始来源或内部枚举。

## 执行步骤

### 步骤 1：冻结接口状态机

定义并生成 `SaveCandidate`、`AddToPlan`、`RefreshQuote`、`OpenMerchant` 的请求/响应和事件语义。每个写操作必须经历 `idle → confirmation_required → executing → succeeded|failed|cancelled`；重复请求使用同一幂等键收敛。

### 步骤 2：先补接口与领域测试

覆盖未确认不写入、确认只写一次、取消无副作用、过期报价禁止加入、重复点击不重复、断线恢复不重复执行、错误契约不转换为空对象。

### 步骤 3：接入 Agent 澄清与公开进度

前端渲染 `clarification_required`；公开显示理解需求、混合检索、核验证据、比较候选四阶段。保留硬约束、软偏好和未确定字段；失败时提供补充信息、重试和返回 Mission。

### 步骤 4：重构推荐卡信息层级

保留纵向分页，但把预算匹配、硬约束覆盖、关键差异、风险、价格验证级别和采集时间置于首屏。默认只选主推荐；比较数量必须由真实选择状态驱动。

### 步骤 5：重构决策工作台

增加移动端纵向差异清单/抽屉、只看差异、保存成功态、待购数量、移除、重新询价、报价过期和安全外跳确认。移除用户首屏的原始 source ref、`DEMO_FIXTURE` 枚举和 `API 驱动` 文案。

### 步骤 6：真点击与契约联验

使用 fixture API 和 Pixel_9 模拟器执行黄金路径，保存 UI 树、截图、请求计数、事件序列和失败摘要；再运行 Python、API、契约和 Android 测试。

### 步骤 7：写入证据并收口

将接口测试、视觉截图、可访问性结果和剩余外部门禁写入 `evidence/verification.json`；仅全部验收通过后将 manifest 状态改为 `complete`。

## 数据引用

- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`
- `../../../defects/V3-ANDROID-AGENT-UX-BUSINESS-AUDIT-20260922.md`

## 验收

### A. 接口与业务状态条款

- [ ] 未确认时 `AddToPlan`、`SaveCandidate`、`OpenMerchant` 不产生远端副作用。
- [ ] 确认后服务端恰好执行一次；重复点击、重连和进程恢复不会重复写入。
- [ ] 确认面板展示商品、商家、金额、运费、数量、报价采集时间、验证级别和不会发生的动作。
- [ ] `DEMO_FIXTURE` 明确标为演示报价/不可购买；不能被客户端转换为 LIVE。
- [ ] `CURRENT` 以外报价不能直接加入待购，只能进入重新询价流程。
- [ ] `clarification_required` 能在 Android 显示问题、提交回答并恢复同一 Mission。
- [ ] 公开阶段事件顺序与 ThreadSnapshot/SSE 一致；禁止把结构化结果塞进无语义的消息增量。
- [ ] 失败、取消、过期、断线恢复都有明确状态；未知契约错误直接失败并保留诊断信息。
- [ ] API 契约、Python/Kotlin/TypeScript 生成代码和漂移检查全部通过。

### B. 视觉与交互条款

- [ ] 任务页首屏只保留任务输入、约束摘要、连接状态和发送；图片/语音按钮可用性与实际能力一致。
- [ ] 推荐页保留主推荐 → 次推荐 → 再次推荐；每张卡有独立理由、满足/未满足项、风险和价格事实。
- [ ] 推荐卡不在首屏展示 `API 驱动`、原始 `source_ref`、`demo:v3:*` 或内部枚举；证据可通过详情入口查看。
- [ ] 价格旁固定显示“演示/实时”、商家、采集时间和有效期/未知状态。
- [ ] `保存候选`、`加入待购计划`、`重新询价`、`打开商家` 均有 idle/loading/success/failure/cancelled 可见状态。
- [ ] 比较选择状态和决策页候选数量一致；至少显示 3–5 个关键规格差异和缺失字段。
- [ ] 待购计划可显示数量、商家、价格、运费、更新时间，并支持移除、撤销或重新询价。
- [ ] 大标题、装饰英文和滑动提示不得挤压关键决策信息；动态字体和小屏仍可完成主流程。
- [ ] TalkBack 能读出商品、价格真实性、风险、动作和状态；关键点击区域达到 Android 最小触控尺寸。
- [ ] ADB 真点击证据覆盖：提交、澄清、推荐翻页、保存、取消待购确认、确认待购、重新询价、比较和恢复。

### C. 证据条款

- [ ] 保存每个关键步骤的 UIAutomator XML、截图、请求计数和结果状态。
- [ ] `verification.json` 不保存 API key、完整日志、机器绝对路径或个人数据。
- [ ] `git diff --check` 和 `python scripts/validate_task_packages.py` 通过。
- [ ] 未暂存、未提交、未推送；本包只改变声明的路径。

## 回滚

只回滚本包声明的 Android/API/契约和测试路径；不得撤销既有 Agent runtime 审批、SSE 恢复、数据事实约束或其他任务包证据。

## 停止条件

- 依赖包或当前 API 契约无法确认时停止。
- 需要真实联盟凭据、生产 OAuth、支付或公网服务时停止并记录外部门禁。
- 任何实现试图绕过用户确认、静默把演示价格当真实报价或吞掉未知契约错误时停止。
- 视觉变更导致主/次/再次推荐层级、恢复入口或可访问性下降时停止。

## 交接格式

- 结果：接口状态机、Android 视觉状态、测试和证据是否通过。
- 变更路径：仅列实际修改路径。
- 验证命令与结果：命令、退出码、测试数、失败摘要。
- 接口证据：请求/事件序列、幂等键、写入次数和恢复结果。
- 视觉证据：截图、UI 树、真点击步骤和可访问性结果。
- 剩余外部门禁：真实联盟、LIVE 报价、物理设备和正式发布批准。
