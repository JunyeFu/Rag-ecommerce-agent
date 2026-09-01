# 06 离线与恢复体验预览提示词

## 图像生成提示词

Create one production-quality 390×844 Android app-content-only UI screen. Continue the exact confirmed kinetic editorial-tech system: warm bone paper, oversized near-black Chinese typography, acid-lime recovered accents, deep emerald technical lines, engineering grids, halftone fields and registration symbols. This is an in-place recovery state inside the “任务” main destination, after a short network interruption and Android process restart. Do not create three device mockups or a storyboard; show one focused recovered screen.

At the top use the oversized heading “已恢复” and the line “已从上次进度继续”. Show the unchanged Mission capsule “¥1,000内 / 通勤降噪 / 接受入耳式”. Create a dominant “安全恢复点” module that states “上次进度：核验证据” and “任务已安全保存”. Inside the same module, show a concise three-step recovery rail: “离线”, “重新连接”, “恢复完成”, with the first two completed and the last highlighted in acid lime.

Below, show a transparent recovery receipt with exactly three checks: “快照已校验”, “事件已续接”, “重复终态 0”. Add the guarantee “离线期间未生成新报价或新证据”. Make one primary action “继续任务” and one lightweight secondary action “查看恢复详情”. Include the compact native navigation “任务”, “决策”, “我的”, with “任务” active.

The screen should communicate continuity and evidence, not an empty success celebration. Do not show new product cards, new recommendations, changed product identity, a new price, live quote, fabricated progress, internal event payloads, stack traces, reset-task action, new-thread action, phone bezel, status bar, watermark or external brand. Do not use a loading spinner as the only recovery evidence.

## 交互与状态约定

- `offline` 只显示最后一次已确认的本地渲染快照和“任务已安全保存”，可执行“重试连接”，不得推进 Mission。
- `recovering` 先读取 ThreadSnapshot，再以 `Last-Event-ID` 续接事件；心跳不计入业务进度。
- `recovered` 只有在快照、事件游标和终态幂等校验通过后出现，并恢复原页面和当前推荐索引。
- 快照与游标冲突、超时或用户隔离失败时进入显式 `failed`，保留本地内容并提供安全重试，不新建 Thread。
