# V3-EXPERIENCE-CONTROL-01 Android 体验控制（中层）

## 目标
把 Agent-first Android 体验分解为任务、决策、信任三个可独立确认的界面切片。
## 状态
`complete`
## 范围
- 控制三入口信息架构、Mission 连续性、证据呈现和原生交互一致性。
## 非目标
- 不恢复商城首页、分类、订单、支付、客服或营销入口。
## 前置依赖
- `V3-PRODUCT-CONTROL-01`、`V3-ANDROID-01`。
## 路径所有权
- 本包及三个体验小层包；业务实现仍由 `apps/android` 所属包控制。
## 现状证据
- Android 已有三入口骨架和 API 状态流，视觉与功能组合尚需逐项确认。
## 执行步骤
1. 确认任务页。2. 确认决策页。3. 确认信任中心。4. 汇总体验门禁。
## 数据引用
- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`
## 验收
- [x] 三个体验子包均有冻结提示词、功能确认点和顺序。
## 回滚
- 只回滚未确认的体验方案和对应小层文档。
## 停止条件
- 视觉方案要求恢复非 Agent 商城主线时停止并升级大层决策。
## 交接格式
- 子包、确认结论、Android 路径、测试证据、剩余门禁。
