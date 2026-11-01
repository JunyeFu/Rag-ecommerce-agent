# 2026-10-02 真实验收记录

用户授权：在状态一致性修复后进行真实模型与 Android 验收。测试对象为当前脏工作树，不是仅 HEAD `d670e291d263a6e4f0f041f9c74c6e0246cb854c`。

## 运行边界

- MiMo：官方端点、mimo-v2.5；凭据只在进程内从 MIMO_API_KEY 映射到 OPENAI_COMPATIBLE_API_KEY。未读取凭据文件，未在报告中保存凭据。
- 商品/报价：自有 60 SKU 演示目录，仍是 DEMO_FIXTURE。不能把真实模型验收解释为 LIVE 报价验收。
- 黄金集：现有 10 场景，单次执行、不自动重试。
- 专项：真实规划器加构造的既有工具结果，检查澄清、重新询价、清单/待购审批。不等于 Android E2E。

## 过程与结果

| 项目 | 结果 |
|---|---|
| Android debug + androidTest APK | 构建成功，17 executed / 56 UP-TO-DATE；指向设备 127.0.0.1:8080，尚未安装 |
| 独立 Pixel_9 启动 | 本机策略拒绝命令，未绕过；已请用户手工启动。原 emulator-5556 属于其他项目，未操作 |
| MiMo 黄金集 | 退出码 0，10/10 可解析、Schema 合法、预期流程完成、预期商品命中；报告 `output/real-acceptance-20261002/mimo-golden.json` |
| 专项 run-1 | 退出码 1；发出模型请求前 TypeError：_candidate_payload 缺少 6 个 keyword-only 参数。测试入口签名漂移，不算 provider 失败 |
| 专项 run-2 | 退出码 0，4/4 通过；报告 `output/real-acceptance-20261002/mimo-specialized-run2.json`，不覆盖 run-1 失败记录 |
| 静态与任务包校验 | ruff check 通过；38 个任务包，0 errors / 0 warnings；本轮 diff --check 通过 |

专项实际模型延迟：澄清 3607.552 ms、重新询价 5325.021 ms、清单 9894.476 ms、待购 4596.068 ms。合计 11749 tokens。两种写操作均在未批准时阻断，批准后执行，重放结果相同。金额由 provider 未提供，记为 `NOT_AVAILABLE_FROM_PROVIDER`。

## 最终判定

- `REAL_PROVIDER_GOLDEN=PASS`：10/10；证据覆盖率 100%；脚本未检出越权写入/外跳和不受支持的价格金额。商业事实检测器检查的是金额与现有工具事实的匹配，不是对任意物流、库存等自然语言陈述的完备证明。
- `REAL_PROVIDER_SPECIALIZED=PASS`：4/4。专项给定已有工具结果，不是完整自主从零流程。
- `ANDROID_LIVE_E2E=BLOCKED`：自动启动模拟器被策略拒绝；已告知用户从 Android Studio Device Manager 手工启动 Pixel_9。最后 ADB 查询没有已连接设备。没有安装、清数据、注入界面状态或报告设备通过。
- `OVERALL_ACCEPTANCE=HOLD`：真实模型功能门禁通过，不等于设备业务、性能或商业发布通过。

黄金集共 132020 tokens，单场景耗时 19.685–160.229 秒；G06 为 160.229 秒、G09 为 63.577 秒。成本未由 provider 提供，不自行估价。

### 发现的验收差距

1. 真实评测配置为每次模型请求 timeout=180 秒、单场景预算 48000 tokens；应用 `configured_provider` 使用 Provider 默认 timeout=30 秒、预算 12000 tokens。因此不能用本报告替代应用默认配置下的验收。整场景时长不等于单个请求超时，尚不能仅凭时长断定应用一定超时。
2. 现有 Android 黄金测试完成等待为 15 秒，低于本次全部真实黄金场景耗时；该测试原本面向 fixture API，不能不作区分地当作真实模型端到端门禁。
3. UI 上真实提问、澄清、返回对话保留比较、审批、重启恢复仍须在可连接设备上执行，本轮没有将编译成功冒充点击通过。

下一步：用户从标准图形入口启动 Pixel_9 后，先验证应用默认 Provider 配置，再做真实交互；不得为获得绿灯静默替换 fake、重试失败场景或删除旧失败证据。报价继续为演示目录，尚无 LIVE 商业验收结论。未提交或推送。
