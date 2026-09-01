# 04 审批、重新询价与安全外跳预览提示词

## 图像生成提示词

Create one production-quality 390×844 Android app-content-only UI screen. Continue the exact kinetic editorial-tech language of the attached confirmed art direction and decision workbench: warm bone paper, oversized near-black Chinese typography, acid-lime authorization accents, deep emerald technical structure, engineering grids, halftone fields and precise registration marks. Show the confirmed decision screen dimmed in the background and a native bottom confirmation sheet in the foreground. The sheet must feel native and actionable, while retaining the established editorial art direction.

This is the state after the user taps an action to recheck the offer for fictional unbranded “AeroDot N7” and then open a demo merchant. Use the large heading “确认执行操作” and a compact target line “AeroDot N7”. Show exactly two numbered authorized steps: “01 重新核验当前报价” with status text “当前证据：DEMO_FIXTURE”; “02 打开演示商家” with text “安全域名：demo-merchant.local”. Add a concise impact statement “将生成新的报价证据，并离开当前应用”. Add a visible safety statement “不会支付或下单”. The evidence grade must be visually explicit and must never look like LIVE.

At the bottom of the sheet, show two balanced native actions: secondary “取消” and primary “确认并继续”. Do not use urgency, countdowns, deceptive color, preselected consent or a disabled-looking cancel action. Make the approval scope immediately scannable. The dimmed background may retain enough of “决策 / 01 胜出” to establish context, but its controls must appear inactive while the sheet is open.

Do not show real merchant branding, affiliate claims, checkout, cart total, order, payment, coupon, fake live price, hidden additional actions, chain-of-thought, phone bezel, status bar, watermark or external brand. Do not add more than the two explicitly authorized steps.

## 交互与状态约定

- 打开面板本身不执行工具、不创建外跳 Intent，也不写入业务集合。
- “确认并继续”创建带幂等键的审批记录，依次执行重新询价和安全链接解析；每步结果写入事件日志。
- 新报价证据保留旧证据，不得把 `DEMO_FIXTURE` 静默升级为 `LIVE`。
- 只有 HTTPS 允许域名解析成功后才创建外跳 Intent；取消、过期或失败均停留在应用内并显示明确状态。
- 保存方案、加入/移出待购复用同一审批框架，但只展示各自实际授权的单一步骤。
