# V2-ANDROID-01 易错点

- 旧新野兽派 token 仅作品牌参考，不能直接复制全部高饱和布局。
- 不使用 hash、rating 或价格比例推导销量、原价、店铺、物流或保障。
- release 中不得依赖 debug DemoData；核心场景必须由 fixture API 驱动。
- deep link 解析失败时不得绕过后端校验直接打开原始 URL。
- `assembleBenchmark` 和截图 PASS 不代表 TalkBack、真机网络或联盟 App 跳转通过。
- `local.properties` 必须继续忽略；在验证命令中使用进程级 `ANDROID_HOME/ANDROID_SDK_ROOT`。
- 冻结的 AGP 8.7/Kotlin 2.0.21 不能盲升到要求 compileSdk 36/37、AGP 9 或 Kotlin 2.2 metadata 的最新版依赖。
- `connectedDebugAndroidTest` 的 Compose fixture 场景、确定性 fixture API 和真实 provider LIVE 必须分层报告。
- 当前进程新建 Run 与进程重启恢复都能观察到 `pending_run_id`；必须用提交态护栏避免误报 `RECOVERED`。
- 系统 picker 的点击坐标只能来自 UIAutomator tree；目标缺失时最多滚动一次再判定。
- AndroidX Macrobenchmark 在模拟器上需显式记录 `EMULATOR` suppression，不能当作物理设备性能。
- ADB `input text` 在非 ASCII/下划线输入上可能转换或截断；恢复测试应用 Compose 语义输入播种，再独立强停验证。
