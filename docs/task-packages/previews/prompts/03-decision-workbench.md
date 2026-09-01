# 03 决策比较工作台预览提示词

## 图像生成提示词

Create one production-quality 390×844 Android app-content-only UI screen. Continue the exact kinetic editorial-tech visual language of the attached confirmed art direction, recommendation result screen and conversation-analysis screen: warm bone paper, near-black oversized Chinese typography, acid-lime emphasis, deep emerald structure, engineering grids, halftone fields, registration marks and precise technical lines. This is the “决策” main destination after the user has added candidates from the three-level recommendation stack.

Design a focused constraint-led decision workbench, not a traditional e-commerce product comparison table. Use fictional unbranded in-ear products only: “AeroDot N7”, “QuietLoop S4”, “MetroBud C2”. At the top show “决策” and the Mission capsule “¥1,000内 / 通勤降噪 / 接受入耳式”. Make the dominant editorial conclusion “01 胜出” with the explanation “更适合通勤降噪”. Keep the three candidates identifiable with 01/02/03 markers, but do not use large shopping product cards.

In the middle, show “核心取舍” as three readable decision lanes rather than a dense grid: “降噪稳定”, “长时舒适”, “续航余量”. Visually communicate that candidate 01 leads in noise cancellation, candidate 03 leads in comfort, and candidate 02 leads in battery. Add small evidence-reference marks associated with the relevant claims. Keep a directly visible “风险 / 未满足项” block with “DEMO 报价，购买前需重新询价” and “耳型适配需试戴”. Do not hide risks behind expansion.

At the bottom, provide one primary action “保存方案” and one secondary action “加入待购”. Include the compact native navigation “任务”, “决策”, “我的”, with “决策” active. The hierarchy should feel dramatic and artistic while remaining feasible in Jetpack Compose and readable on a phone.

Do not show checkout, cart totals, payment, order, coupon, promotion, merchant logo, sponsored insertion, fake live price, generic star ratings, internal chain-of-thought, phone bezel, status bar, watermark or external brand. Do not turn the page into a spreadsheet or a stack of nested cards.

## 交互与状态约定

- 候选仅来自用户在小层 01 主、次、再次推荐中主动选择的“加入对比”。
- Agent 结论绑定同一 Mission 约束和类型化 `comparison` payload；每个结论可定位到候选和证据。
- 保存方案与加入待购在 API 成功后才反馈完成，刷新或进程恢复后状态不丢失。
- 报价为 `DEMO_FIXTURE` 时始终显示风险；执行购买相关动作前进入小层 04 审批与重新询价。
