# V2-ANDROID-01 四标签Android商业导购主流程

## 目标

实现导购、清单、购物车、我的四标签及证据化推荐、报价重验和安全商家跳转。

## 状态

`complete`

## 范围

- 按 UDF 和分层架构实现四标签、ShoppingMission、对话流和多模态输入。
- 实现证据商品卡、报价列表、规格差异、比较工作台和清单。
- 将购物车定义为按商家分组的跨站待购集合，跳转前 requote。
- 实现价格变化确认、失效、离线、重连、进程恢复和深链失败状态。
- 建立 design tokens、截图、instrumentation、可访问性和 performance 测试。

## 非目标

- 不恢复 Explore、Compare 一级标签、支付设置、订单中心、假客服或客户端商业事实推导。
- 不保存支付密码、联盟 secret 或原始媒体。
- 不在客户端计算或补全价格、运费、库存和保障。

## 前置依赖

- `V2-API-01` 的生成 Kotlin 客户端和稳定事件契约完成。

## 路径所有权

- `apps/android/`。
- Android screenshot、unit、instrumentation 和 macrobenchmark 测试。
- Android 设计 token 与可访问性规范。
- `scripts/capture_android_runtime.py`、`scripts/summarize_android_benchmark.py`、`scripts/summarize_android_recovery.py`、`scripts/check_android_accessibility_tokens.py`、`scripts/generate_android_media_fixtures.py`、`scripts/summarize_android_multimodal.py`、`scripts/run_android_instrumentation_case.py` 与 `scripts/android_fixture_api.py`。

## 现状证据

- 旧导航含五个一级标签，release DemoData 为空，商品详情包含伪造商业字段。
- V2 已在 Android 15 模拟器完成 UI-tree、instrumentation、进程恢复、多模态 fixture API 和 macrobenchmark 验证；这些证据不替代物理真机、真实联盟深链、真实模型或人工 TalkBack 验收。

## 执行步骤

1. 用真实契约夹具完成四标签线框、状态表和无障碍语义。
2. 建立生成客户端、repository、Room 缓存、ViewModel 和 UiState。
3. 实现导购、比较、清单、购物车 requote、深链和我的设置。
4. 覆盖 loading/empty/stale/changed/unavailable/offline/error/recovered 状态。
5. 运行 unit、截图、instrumentation、可访问性和 macrobenchmark。

## 数据引用

- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`

## 验收

- [x] 四个一级页面和 12 个核心场景完成 instrumentation；离线套件 14 个测试中 13 通过、fixture 场景按预期跳过，独立 fixture API 场景 1 个通过。
- [x] 所有价格模型强制来源、时间和有效性，客户端不补全价格、运费、库存或保障；fixture 展示保留明确证据引用。
- [x] 价格变化阻断跳转并要求再次确认，HTTPS/host 校验失败时 fail-closed。
- [x] 触控目标 >= 48dp，7 组小字 token 对比度均 >= 4.5:1，并提供语义标签。
- [ ] 物理真机 TalkBack 焦点顺序需人工验收，属于外部门禁。
- [x] 模拟器已验证旋转、进程重建、离线与 SSE 重连状态；物理设备恢复仍属外部门禁。
- [x] 模拟器 10 次冷启动 p95 为 1510.9146 ms，StrictMode 与 fatal 计数为 0；物理参考设备性能仍属外部门禁。

## 回滚

- 按 feature flag 隐藏未完成入口；Room migration 必须有旧版本 fixture，禁止卸载数据作为回滚。

## 停止条件

- API 契约仍漂移、需要本地伪造商业字段、无可用测试设备却要求真机结论或需要生产签名时停止对应结论。

## 交接格式

- 结果：APK 构建、场景矩阵和视觉/可访问性证据。
- 变更路径：apps/android。
- 验证命令与结果：unit、lint、screenshot、instrumentation、benchmark。
- 剩余外部门禁：物理真机 HTTPS/性能、真实联盟深链、人工 TalkBack，以及真实模型/联盟提供方的结构化商品投影。
- 风险与下一包：交给 V2-SECURITY-01 与 V2-LIVE-01。
