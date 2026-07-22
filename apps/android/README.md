# 拾物 — Android 客户端

> **AI 全栈挑战赛 第3届 · 华南理工大学 2026**
> Jetpack Compose 原生 Android 导购客户端

## 快速开始

### 环境要求

| 工具 | 版本 |
|------|------|
| Android SDK | 35 (compileSdk) / 26+ (minSdk) |
| Build Tools | 36.1.0 |
| Gradle | 8.9 |
| Kotlin | 2.0+ |
| JDK | 17 |

### 编译

```bash
# Windows (推荐 Android Studio)
./gradlew assembleDebug

# WSL (需配置 SDK 路径和代理)
export ANDROID_HOME=/mnt/c/Users/<user>/AppData/Local/Android/Sdk
export GRADLE_OPTS="-Dhttp.proxyHost=172.24.48.1 -Dhttp.proxyPort=7897 -Dhttps.proxyHost=172.24.48.1 -Dhttps.proxyPort=7897"
./gradlew assembleDebug
```

APK 输出: `app/build/outputs/apk/debug/app-debug.apk`

### 运行

1. 确保后端服务运行在 `http://10.0.2.2:8080`（模拟器）或 `http://<host-ip>:8080`（真机）
2. 安装 APK 到模拟器: `adb install app/build/outputs/apk/debug/app-debug.apk`
3. 启动应用即可

---

## 项目结构

```
apps/android/
├── app/
│   ├── build.gradle.kts          # 依赖配置
│   └── src/main/java/com/shopping/agent/
│       ├── MainActivity.kt       # 入口 (edge-to-edge)
│       │
│       ├── data/
│       │   ├── mock/             # Mock 数据 (9 files)
│       │   │   ├── MockProducts.kt      30 件商品
│       │   │   ├── MockChats.kt         对话历史
│       │   │   ├── MockExplorePosts.kt  100 条探索动态
│       │   │   ├── MockCompareData.kt   对比数据
│       │   │   └── MockCategoryProducts.kt 品类商品
│       │   │
│       │   ├── model/            # 数据模型 (7 files)
│       │   │   ├── Product.kt          统一商品模型 (对齐 DATA-CONTRACT.md)
│       │   │   ├── ChatMessage.kt      聊天消息
│       │   │   ├── SSEEvent.kt         SSE 事件类型
│       │   │   ├── ExplorePost.kt      探索动态
│       │   │   └── Feedback.kt         用户反馈
│       │   │
│       │   ├── remote/           # 网络层 (3 files)
│       │   │   ├── SseClient.kt        SSE 客户端 (chat + vision-search)
│       │   │   └── ApiService.kt       REST API
│       │   │
│       │   └── repository/       # 仓库层 (3 files)
│       │       ├── ChatRepository.kt   聊天仓库
│       │       └── ProductRepository.kt 商品仓库
│       │
│       ├── viewmodel/            # ViewModel (3 files)
│       │   ├── ChatViewModel.kt       聊天 (文本 + 拍照找货)
│       │   ├── CompareViewModel.kt    比价
│       │   └── ProductViewModel.kt    商品
│       │
│       └── ui/
│           ├── theme/            # 设计系统 (5 files)
│           │   ├── Color.kt
│           │   ├── Type.kt
│           │   └── Theme.kt
│           │
│           ├── components/       # 通用组件 (17 files)
│           │   ├── ChatInputBar.kt    输入栏 (文本+拍照+语音)
│           │   ├── ProductCard.kt     商品卡片
│           │   ├── StreamingBubble.kt 流式气泡
│           │   ├── MessageBubble.kt   消息气泡
│           │   ├── GradientTopBar.kt  渐变顶栏
│           │   └── LoadingStates.kt   加载态
│           │
│           ├── screens/          # 页面 (9 files)
│           │   ├── HomeScreen.kt      首页 (AI 导购)
│           │   ├── CompareScreen.kt   比价
│           │   ├── ExploreScreen.kt   探索
│           │   ├── ProfileScreen.kt   我的
│           │   ├── SettingsScreen.kt  设置
│           │   └── ProductDetailScreen.kt 商品详情
│           │
│           ├── chat/             # 聊天 (2 files)
│           │   └── ChatGuideScreen.kt 导购对话
│           │
│           └── navigation/       # 导航 (2 files)
│               └── NavGraph.kt        路由图
```

---

## 架构

```
UI (Compose)
    ↓ StateFlow
ViewModel (ChatViewModel / CompareViewModel)
    ↓ suspend fun
Repository (ChatRepository)
    ↓ Flow<SSEEvent>
SseClient (OkHttp SSE)
    ↓ HTTP POST (JSON / Multipart)
Backend (FastAPI :8000)
    ↓ SSE (text/event-stream)
    → text_delta → 逐字流式输出
    → product_cards → 商品卡片逐张推送
    → progress → 流水线状态
    → done / error
```

### 数据流

| 功能 | 前端入口 | 后端端点 | 事件流 |
|------|---------|---------|--------|
| AI 导购 | ChatInputBar 文本 | POST /api/v1/chat | progress→text_delta→product_cards→done |
| 拍照找货 | ChatInputBar 相机 | POST /api/v1/upload/vision-search | vision_parsed→product_cards→done |
| 多轮对话 | conversation_id 复用 | 同上 + state_manager | 上下文自动继承 |

### SSE 事件处理

```
SSEEvent.TextDelta   → 追加到 streamingText（逐字渲染）
SSEEvent.ProductCard → 追加到 streamingCards（逐张推送）
SSEEvent.Progress    → 更新 searchStatus（流水线提示）
SSEEvent.Done        → 结束流，生成 ChatMessage
SSEEvent.Error       → 显示错误
```

---

## 关键技术细节

### 拍照找货

1. `ChatInputBar` 相机按钮 → `ActivityResultContracts.GetContent("image/*")`
2. Uri → tempFile (ContentResolver copy)
3. `SseClient.connectVision(file)` → multipart POST
4. 后端 Doubao 视觉 API 解析 → pgvector 检索
5. SSE 流返回识别结果 + 8 件相似商品

### 多轮上下文

- `ChatViewModel.sessionId` (UUID) 在应用生命周期内保持不变
- 每次 `sendMessage()` 附带相同 `conversation_id`
- 后端 `state_manager` 存储对话槽位 (category/price/brand/attributes)
- 新消息的 LLM extract_slots 与历史 merge（None 不覆盖有效值）

### 统一数据契约

所有商品数据遵循 `DATA-CONTRACT.md v1.0` (docs/standards/)。
前端 `Product` 与后端 `ProductRecord` 字段一一映射 (camelCase ↔ snake_case)。

---

## 依赖

| 库 | 版本 | 用途 |
|---|------|------|
| Compose BOM | 2024.12.01 | UI 框架 |
| Material3 | — | 设计系统 |
| OkHttp | 4.12.0 | HTTP + SSE 客户端 |
| Gson | 2.11.0 | JSON 解析 |
| Coil | 2.7.0 | 图片加载 |
| Navigation Compose | 2.8.5 | 页面路由 |
| Lifecycle ViewModel | 2.8.7 | MVVM |

---

## 常见问题

### Gradle 增量编译缓存污染

**现象**: 修改代码后编译报错 `Unresolved reference` 但代码正确。

**原因**: Gradle IC (Incremental Compilation) 缓存了旧的类结构，
       字段重命名/类型变更后缓存未失效。

**解决**:
```bash
./gradlew clean assembleDebug      # 清理缓存 + 重新编译
```

**预防**: 在 `gradle.properties` 中添加:
```properties
kotlin.incremental.useClasspathSnapshot=false
```

### WSL 编译报 SDK 找不到

```bash
export ANDROID_HOME=/mnt/c/Users/fujunye/AppData/Local/Android/Sdk
```

## 开发注意事项

- **API 地址**: 模拟器使用 `10.0.2.2:8080`，真机使用宿主机 IP
- **WSL 代理**: Gradle 必须配置 `-Dhttp.proxyHost=172.24.48.1 -Dhttp.proxyPort=7897`
- **SSE 超时**: OkHttp readTimeout 设为 120s（云端视觉识别与检索需要）
- **语音输入**: 真机不依赖系统语音引擎，App 录音后上传 `/api/v1/voice/recognize` 或 `/api/v1/voice/chat`，由后端 Doubao Chat API `input_audio` 识别并进入 RAG 链路
- **数据格式**: 严格遵循 `docs/standards/DATA-CONTRACT.md`
- **编译前**: 确认 `ANDROID_HOME` 指向 Windows SDK 目录
