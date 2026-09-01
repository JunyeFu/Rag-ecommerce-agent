# 02 对话、必要澄清与公开分析预览提示词

## 图像生成提示词

Create one polished 390×844 Android app-content-only UI screen using the selected kinetic editorial-tech reference image as the strict visual language. This is the upstream main Task conversation page before any recommendation result appears. The user has submitted a shopping need, the Agent asked one necessary clarification, the user answered, and the Agent is now analyzing.

Use a warm bone paper texture, oversized near-black Chinese typography, acid-lime progress accents, deep emerald structural marks, engineering grids, halftone fields, registration marks and a flowing technical scan line. Keep the composition editorial and dramatic but fully usable as a native Android screen. Use coral only for an actual error; there is no error in this preview.

Show a compact header with “购物对话” and a small live-state mark. Keep message history sparse and intentional: user message “预算 ¥1,000，通勤降噪，排除头戴式”; Agent clarification “是否接受入耳式？”; user answer “接受”. Below it, make a dominant artistic module titled “Agent 分析中”. Show exactly four public, verifiable stages: “理解需求”, “混合检索”, “核验证据”, “比较候选”. Mark the first two complete, “核验证据” as the active stage, and “比较候选” as pending. Add the concise transition note “分析完成后进入推荐结果”. Provide a bottom composer labeled “继续补充要求” and a compact three-item native navigation: “任务”, “决策”, “我的”, with “任务” active.

Do not show any product, product image, recommendation card, ranking, price, offer, evidence result, category grid, cart, order, payment, marketing banner, internal chain-of-thought, hidden score, raw tool call, phone bezel, status bar, watermark or external brand. The Agent analysis module must communicate observable execution state, not simulated inner reasoning.

## 交互与状态约定

- 澄清只在必要字段缺失时出现；用户回答后写回同一 Mission 并进入分析。
- 四个阶段由类型化 `progress` 事件驱动，已完成、当前、待执行状态可恢复。
- 用户在分析过程中可继续补充要求；新增硬约束会创建可审计的新 Turn，而不是静默篡改当前结果。
- 分析完成前不显示任何商品；完成后使用同一 ThreadSnapshot 和事件游标进入小层 01 推荐结果栈。
- 超时、限流、取消或输出无效使用显式失败状态，不静默切换 fake，也不伪装仍在运行。
