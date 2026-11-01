# C7 真实使用验收证据

日期：2026-09-23  
设备：Android Emulator `emulator-5554`，1080 × 2424  
服务：本地 fixture API，真实 HTTP/SSE/持久状态链；不代表 LIVE 商业报价

## 验收结果

- Playwright Agent 业务测试：3/3 通过。
  - 简单：单次有证据推荐与严格/预算/替代三路线。
  - 中度：澄清、继续执行、幂等重放、`Last-Event-ID` 恢复。
  - 重度：10 个黄金任务、五类商业事实、保存、待购、观察草稿、商家链接和用户隔离。
- Android `GoldenScenarioApiFlowTest`：1/1 通过，测试体内连续完成 8 个独立黄金购物 Mission。
- Android `FixtureApiFlowTest`：1/1 通过，覆盖 Android → API → Agent → SSE → 有证据候选 → 进程恢复。
- Android `ShoppingFlowTest`：28/28 通过。
- Python Runtime/API/Domain/RAG/Evaluation：120 passed，12 个 integration 用例按标记排除。
- Ops Web：TypeScript check、2 个单元测试及 production build 通过。
- OpenAPI 27 paths、三端契约生成确定性、38 个任务包校验和 `git diff --check` 通过。
- ADB 坐标点击：先点击恢复页“继续任务”，再点击“新建任务”；旧 Mission 消失，输入页显示 `ONLINE / 已新建购物任务`。
- Logcat 未出现应用 `FATAL EXCEPTION`（最终门禁复核见本轮验证记录）。

## 验收驱动修复

1. 独立需求原先会继续写入旧线程，第二个商品仍受第一个目标影响。现增加显式“新建任务”，只清除当前 Mission/thread 指针，不删除已保存方案、待购和观察数据。
2. 五类事实卡会把“保存候选/加入待购”挤出真实屏幕可点击区。现将两个核心操作并排放在报价后，商业事实仍完整保留在候选卡中。
3. Android 真实 API 验收在当前 Windows 防火墙环境通过 `adb reverse tcp:8080 tcp:8080` 连接本机；同时已验证 `-PapiUrl=http://10.0.2.2:8080/` 构建成功。该连接差异不改变 API/SSE 业务路径。

## ADB 证据

运行时文件位于忽略目录 `output/c7-real-use/`：

- `c7-before.*`：应用恢复前的 UI hierarchy 与截图。
- `c7-after.*`：恢复页及“继续任务”入口。
- `c7-continued.xml`：继续任务后的“新建任务”入口。
- `c7-new-mission.*`：新 Mission 输入页；层级断言 `当前 Mission=false`、需求输入提示存在。

## 边界

通过的是演示范围内的 Agent 购物决策闭环。`DEMO_FIXTURE` 不升级为 LIVE；联盟实时报价、支付、订单、物流和后台通知仍是外部门禁。
