# Android本地演示准备与启动测量

先按README启动后端，演示APK访问`http://10.0.2.2:20881/`。以下步骤仅针对本项目包，不清除应用数据、账号、媒体、系统日志或其他应用的缓存。不以预生成UI状态代替业务。

在Android SDK的platform-tools目录使用adb，明确选择你的演示模拟器；专用验收设备使用20884 ADB server，普通本机ADB默认5037。

```powershell
adb -s <演示设备serial> install -r <候选app-debug.apk>
adb -s <演示设备serial> shell cmd package compile -m speed -f com.ragcommerce.agent
adb -s <演示设备serial> shell dumpsys package com.ragcommerce.agent
adb -s <演示设备serial> shell am start -W -n com.ragcommerce.agent/com.ragcommerce.agent.MainActivity
```

`compile`准备的是这个已安装包的生成代码/验证缓存，不是清数据；重新安装不同APK后应重新准备并记录实际编译状态。命令返回Success不代表状态一定是speed：本轮debug QA包实际得到verify，必须以dumpsys Dexopt state为准。

## 已观察到的问题与证据边界

2026-10-13，RagFinalSafety20261012/API35上已安装的debug QA APK处于run-from-apk，Dexopt location缺失。30次进程冷启动p95=3179ms，未过2000ms；应用UID时间窗内1034条日志未发现fatal/StrictMode violation。

定向trace：首帧traversal约1953ms；其直接子级845次VerifyClass累计约558ms，measure约581ms；主线程draw约30ms。绘制美术不是该trace的主要耗时，未删除设计元素。原始trace保留在运行输出目录，公开摘要不包含设备路径和完整日志。

随后仅对同一包执行上述编译准备，实际变为verify，APK与应用数据未更换。完整另30次复验p95=1785ms通过；仍保留一次2630ms样本，907条本窗应用UID日志无fatal/StrictMode。后trace首次traversal约952ms，直接VerifyClass为0。原失败报告不覆盖，详见[同APK复审](../evidence/v3/final-NFR07-verified-dex-review-20261013.json)。

- 未准备的原始安装状态：[30次失败记录](../evidence/v3/final-NFR07-installed-cold-start-20261013.json)。
- 受控verify状态：[另一次30次记录](../evidence/v3/final-NFR07-installed-verified-dex-cold-start-20261013.json)。
- TotalTime对应初始显示，不等于任务恢复、推荐或所有网络请求已完成；进程冷启动保留系统/磁盘缓存，不声称设备完全冷启动。
- 这是已安装QA二进制的证据，不代替最终源码/APK同版验收。debug数据不得包装成生产release性能。

方法依据：[Android性能测量指南](https://developer.android.com/topic/performance/measuring-performance)、[手动测量Baseline Profile](https://developer.android.com/topic/performance/baselineprofiles/manually-create-measure)。官方建议使用代表发布行为的构建及已知编译状态。本项目保留debug实际结果、实际状态及其限制，不用未运行的benchmark结果替代。
