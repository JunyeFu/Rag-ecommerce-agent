# 01 对话后推荐结果栈提示词

- 全局美术基线：`00-selected-art-direction.md`
- 已选风格参考：`../art-direction/selected-editorial-tech.png`
- 当前确认图：`../generated/01-recommendation-stack-editorial-v3.png`

## 页面职责

用户已经在对话页面提交购买需求，Agent 分析已经完成。本页不再展示对话、约束编辑或分析进度，只展示 Agent 排序后的主推荐、次推荐、再次推荐。

## 生成提示词

Create a `390 × 844` production-quality Android result screen using the confirmed kinetic editorial-tech language: bone paper texture, near-black oversized typography, acid-lime highlights, emerald evidence accents, coral risks, engineering grids, annotation lines, halftone grain and a dramatic fictional product cutout.

The initial viewport shows one full-screen `01 / 03` primary recommendation frame. A small clipped edge of `02 / 03` is visible below with “下滑查看次推荐”. Scrolling downward snaps to the secondary recommendation. The secondary recommendation can scroll upward to primary or downward to tertiary. The tertiary recommendation can only scroll upward to secondary. Use a slim vertical position rail; do not use tabs or a horizontal carousel.

The current recommendation frame contains only the product name, match score, concise match reason, three verified facts, evidence state, one risk, DEMO price state, “查看依据” and “加入对比”. Remove the giant task overview, budget and constraint strip, Agent execution timeline, multiple-product list, evidence dashboard, bottom navigation, marketplace categories, cart, order and payment.

## 功能确认点

- 是否认可一个 viewport 只展示一个完整推荐框。
- 是否认可 `主推荐 ↕ 次推荐 ↕ 再次推荐` 的纵向整页吸附关系。
- 是否认可证据、风险、演示报价和两个动作继续属于推荐框。
