# Android shopping application

原生 Kotlin/Compose 客户端，固定四个一级入口：导购、清单、购物车、我的。

## 商业真实性边界

- 初始连接状态为 `CHECKING`，只有真实 `/health` 探测成功后才显示 `ONLINE`。
- 价格、库存、物流、保障和商家身份只能来自服务端证据与报价；客户端不补全。
- 商家跳转前调用 `/v1/offers/{offerId}/resolve` 重新询价，只允许带 host 的 HTTPS URL。
- 图片和音频通过系统 picker 选择，先上传为 24 小时媒体引用，再与文本进入同一 Turn。
- 原始媒体不写入 Room/DataStore；安装级开发 UUID、thread、幂等键、run 与 SSE 游标写入 DataStore。
- debug 构建启用 StrictMode，并只为本机 fixture API 允许 cleartext；Benchmark/Release 不继承该设置。

## 分层

- `ui/ShoppingModels.kt`：UDF 状态、动作、报价确认与四标签模型。
- `ui/ShoppingViewModel.kt`：Turn、审批、SSE 游标恢复、安全商家跳转。
- `data/ShoppingRepository.kt`：Room/DataStore、媒体限制、幂等 Turn 与 SSE 协议。
- `data/remote/CommerceApi.kt`：薄 Retrofit/OkHttp 边界。
- `benchmark/`：独立 AndroidX Macrobenchmark 冷启动测试。

## 本地验证

不创建 `local.properties`；为每条命令提供进程级 SDK 路径：

```powershell
$env:ANDROID_HOME = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
./gradlew.bat :app:testDebugUnitTest :app:lintDebug :app:assembleBenchmark -PapiUrl=https://ci.invalid/
./gradlew.bat :app:connectedDebugAndroidTest
./gradlew.bat :benchmark:connectedBenchmarkAndroidTest
```

确定性 Android→API→Agent→SSE 集成需先从仓库根目录启动 fixture API，再使用模拟器 host 映射：

```powershell
$env:PYTHONPATH = 'apps/api/src;packages/agent-runtime/src;packages/contracts/generated/python;packages/domain/src;packages/connectors/src;packages/retrieval/src'
uv run uvicorn scripts.android_fixture_api:app --host 127.0.0.1 --port 8080
./gradlew.bat :app:connectedDebugAndroidTest -PapiUrl=http://10.0.2.2:8080/
```

fixture、模拟器和本地 debug 签名仅形成 integration/emulator 证据，不代表真实模型、联盟连接器、物理真机、人工 TalkBack、生产 HTTPS 或正式发布通过。
