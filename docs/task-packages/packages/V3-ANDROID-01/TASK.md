# V3-ANDROID-01 Agent-first Android

## 目标
交付任务、决策、我的三入口原生 Agent 产品。
## 状态
`complete`
## 范围
- 类型化商品/报价/比较、清单/待购 API 写入、审批、恢复、安全外跳。
## 非目标
- 删除商城首页、分类、订单、支付、客服和营销。
## 前置依赖
- `V3-PLATFORM-01`。
## 路径所有权
- `apps/android`。
## 现状证据
- Pixel_9 API 35：19 项 UI instrumentation 与 3 项真实 API/SSE/恢复 instrumentation 均通过。
- 8 个黄金场景由 Android 发起真实 fixture API Turn，并经 SSE 渲染类型化推荐结果。
- 当前源码的 unit、lint、debug APK 与 Benchmark APK 通过；视觉对照见仓库根目录 `design-qa.md`。
## 执行步骤
1. 三入口红测。2. reducer。3. API 状态。4. 模拟器闭环。
## 数据引用
- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`
## 验收
- [x] 10 个场景至少 8 个在模拟器独立通过（G01–G06、G09、G10）。
- [x] 三入口与类型化事件单测通过。
## 回滚
- 仅回滚 Android V3 UI，不恢复已删除商城承诺。
## 停止条件
- instrumentation 使用直接 ShoppingUiState 注入冒充 E2E 时停止。
## 交接格式
- 结果、路径、验证、外部门禁、下一包。
