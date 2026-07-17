# 拾物 App - 全链路机制设计文档

> **⚠️ 辅助文档** - 开发权威入口为 [`DEV-CONTROL.md`](../DEV-CONTROL.md)，如有冲突以权威文档为准。
>
> 本文档描述拾物 App 所有已实现功能的端到端数据流、控制流与渲染机制。

---

## 目录

1. [对话推荐机制](#1-对话推荐机制)
2. [拍照找货机制](#2-拍照找货机制)
3. [语音搜索机制](#3-语音搜索机制)
4. [商品对比机制](#4-商品对比机制)
5. [购物车机制](#5-购物车机制)
6. [后端 RAG 管道](#6-后端-rag-管道)
7. [全局 UI 系统](#7-全局-ui-系统)
8. [导航与路由机制](#8-导航与路由机制)

---

## 1. 对话推荐机制

### 1.1 用户输入 -> 推荐展示全流程

```
用户输入"我想要一双运动鞋"
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ ChatInputBar (Compose)                               │
│ - 文本输入: OutlinedTextField                        │
│ - 拍照图标: 触发图片选择器                            │
│ - 语音图标: 启动录音                                  │
│ - 发送按钮: FilledIconButton                        │
│   条件: inputText.isNotBlank() && !isStreaming       │
│   触发: sendMessage()                               │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ ChatViewModel.sendMessage()                          │
│                                                      │
│ 1. 读取 uiState.inputText                           │
│ 2. 创建 ChatMessage(role=User, content=text)        │
│ 3. 更新 uiState:                                    │
│    - messages += userMessage                        │
│    - inputText = ""                                 │
│    - isStreaming = true                             │
│    - searchStatus = "AI 正在思考…"                   │
│ 4. 持久化: userRepo.saveMessage()                   │
│ 5. 调用 streamWithRetry(text)                       │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ streamWithRetry(text) -> performStream(text)         │
│                                                      │
│ 重试策略: 最多3次, 指数退避 (1s/2s/4s/8s)            │
│ IOException 重试, 其他异常直接失败                    │
│                                                      │
│ performStream:                                       │
│   chatRepository.sendMessage(text, convId, sessionId)│
│       .collect { event ->                            │
│           when (event) {                             │
│             Progress -> 更新 searchStatus            │
│             TextDelta -> 累积文本, TTS 播报           │
│             ProductCard -> 交错提交文本+卡片           │
│             Clarify -> 显示追问+选项                  │
│             WebSearchResult -> 累积联网结果           │
│             Compare -> 累积对比维度                   │
│             Done -> 提交剩余文本, 结束流               │
│             Error -> 显示错误                         │
│           }                                          │
│       }                                              │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ 后端: POST /api/chat (SSE)                           │
│                                                      │
│ 1. 解析请求 (text, conversation_id, session_id)      │
│ 2. agent.generate_response() 进入 LangGraph          │
│ 3. SSE 事件流 (text/event-stream):                   │
│    data: {"type":"progress","message":"正在搜索..."}  │
│    data: {"type":"text_delta","content":"为您..."}    │
│    data: {"type":"product_cards",...}                │
│    data: {"type":"done","total_cards":3}             │
└─────────────────────────────────────────────────────┘
```

### 1.2 交错式卡片输出

后端在 LLM 流式生成过程中，遇到商品卡片标记时**立即发射 ProductCard 事件**，而非等全部文本生成完毕。前端收到 ProductCard 时：

1. 将已累积的文本提交为独立 Assistant 消息
2. 将商品卡片作为独立消息插入
3. 清空累积器，继续接收后续文本

```
SSE 流: [Progress] [TextDelta×N] [ProductCard#1] [TextDelta×N] [ProductCard#2] ... [Done]

前端渲染:
  Message(role=Assistant, content="为您推荐以下商品：")
  Message(role=Assistant, content="", productCards=[Product#1])
  Message(role=Assistant, content="这款鞋子轻盈透气...", productCards=[Product#2])
  ...
```

### 1.3 每日推荐问候

```
App 启动 -> NavGraph 创建 ChatViewModel
    -> sendDailyGreeting()
    -> 检查 last_greeting_date (当日首次才触发)
    -> 检查 messages.isEmpty() (有历史不覆盖)
    -> 插入: "fujunye，早上好 ☀️\n\n以下是今日为你精选的推荐："
    -> 商品卡片: mockProducts.take(3) (本地数据, 非后端请求)
    -> 持久化到 SQLite
```

### 1.4 ChatViewModel 状态管理

```
ChatViewModel : AndroidViewModel()
    ├── _uiState: MutableStateFlow<GuideUiState>
    │       ├── messages: List<ChatMessage>       // 历史消息 (SQLite 持久化)
    │       ├── conversations: List<ConversationMeta> // 多对话列表
    │       ├── currentConversationId: String     // 当前对话 ID
    │       ├── inputText: String                  // 输入框文本
    │       ├── isStreaming: Boolean               // 流式输出中
    │       ├── streamingText: String             // 当前流式文本
    │       ├── streamingCards: List<Product>     // 当前流式商品卡片
    │       ├── searchStatus: String              // 搜索状态提示
    │       ├── clarifyChips: List<String>        // 追问/排除选项
    │       ├── clarifyQuestion: String            // 追问问题文本
    │       ├── ttsEnabled: Boolean                // TTS 开关
    │       └── screenState: ScreenState          // Idle/Loading/Streaming/Content/Error
    │
    ├── sendMessage()          // 文本消息
    ├── sendVoice(audioFile)    // 语音消息
    ├── sendImage(imageFile)    // 拍照找货
    ├── onClarifyChipClick()    // 追问/排除选项点击
    ├── createNewConversation() // 新建对话
    ├── loadConversation()      // 切换对话
    └── deleteConversation()    // 删除对话
```

### 1.5 DEMO_MODE

当 DEMO_MODE 开启时（前端 SettingsScreen 开关），`ChatRepository.sendMessage()` 使用 `DemoStreamProvider` 生成模拟 SSE 流，跳过后端请求。用于离线演示和 CI 测试。

---

## 2. 拍照找货机制

### 2.1 完整流程

```
用户选择/拍摄商品图片
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ ChatViewModel.sendImage(imageFile)                   │
│                                                      │
│ 1. 创建 ChatMessage(role=User, content="📷 拍照找货") │
│ 2. 更新 uiState: isStreaming=true,                   │
│    searchStatus="📷 正在识别图片，请稍候…"             │
│ 3. 持久化用户消息                                    │
│ 4. 调用 visionClient.connectVision(imageFile)        │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ 后端: POST /api/v1/upload/vision-search             │
│ Content-Type: multipart/form-data                    │
│ Body: file=@image.jpg                               │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ upload.py -> vision_search(file)                      │
│                                                      │
│ 1. 读取文件: contents = await file.read()            │
│ 2. 大小限制: 10MB                                    │
│ 3. 保存图片: save_upload_image() -> uploads/UUID.jpg  │
│                                                      │
│ 4. 视觉 API 识别: parse_product_image(contents)       │
│    └─ Doubao OpenAI-compatible vision API            │
│    └─ 失败 -> SSE ErrorEvent + DoneEvent             │
│                                                      │
│ 5. 构造搜索查询: _build_search_query(product_info)   │
│    例: "运动鞋 NIKE 跑步鞋 红色 轻量"                │
│                                                      │
│ 6. pgvector 检索: search_similar_products(           │
│        query_text=search_query, top_k=8)             │
│                                                      │
│ 7. SSE 流式返回                                      │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ 视觉解析: image_parser.py                             │
│                                                      │
│ Provider: Doubao OpenAI-compatible vision API         │
│ 配置: DOUBAO_API_KEY + LLM_MODEL                     │
│                                                      │
│ parse_product_image(image_bytes):                    │
│   1. base64 编码图片 -> data URL                      │
│   2. 构造 messages: [{role:"user", content:[         │
│        {type:"image_url", image_url:{url:data_url}}, │
│        {type:"text", text: prompt}                  │
│      ]}]                                             │
│   3. 调用 Doubao 视觉模型                             │
│   4. 解析 JSON 输出                                   │
│                                                      │
│ 输出: {category, brand, color, material,              │
│        style, keywords[], description, confidence}    │
│                                                      │
│ _needs_thinking_disabled() 自动适配 Doubao/Mimo/ep-*  │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ pgvector 相似检索: retriever.py                      │
│                                                      │
│ search_similar_products(query_text, top_k=8):        │
│   1. query_vector = await embed_text(query_text)     │
│      └─ BGE-large-zh-v1.5, 1024维                   │
│   2. SQL: SELECT *, embedding <=> :query_vec AS dist │
│           FROM products                              │
│           ORDER BY embedding <=> :query_vec          │
│           LIMIT :top_k                               │
│   3. 结构化: {product_id, title, price, rating,       │
│               brand, category, match_score,           │
│               highlights[], image_url}               │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ SSE 事件流 (text/event-stream)                       │
│                                                      │
│ data: {"type":"progress","message":"识别中..."}       │
│ data: {"type":"product_cards","product_id":"...",    │
│        "title":"Nike Air Max 270...","price":899,    │
│        "rating":4.7,"match_score":0.6,               │
│        "highlights":[...],"index":1,"total":8}       │
│ ... (共8张商品卡片)                                   │
│ data: {"type":"done","total_cards":8}                 │
└─────────────────────────────────────────────────────┘
```

### 2.2 视觉 API 错误处理

```
parse_product_image() 失败
    -> SSE ErrorEvent(code="VISION_API_UNAVAILABLE", message="...")
    -> SSE DoneEvent(total_cards=0)
    -> 前端显示错误状态
```

---

## 3. 语音搜索机制

```
用户长按语音按钮 -> 录音
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ ChatViewModel.sendVoice(audioFile, durationSec)     │
│                                                      │
│ 1. AudioCompressor.prepareForUpload(audioFile)      │
│ 2. 创建 ChatMessage(role=User, content="语音输入",    │
│    audioUri=path, audioDurationSec=duration)         │
│ 3. 更新 uiState: searchStatus="正在理解语音..."       │
│ 4. chatRepository.sendVoice(audioFile, convId, ...)   │
│    .collect { event ->                               │
│        VoiceRecognized -> 更新用户消息为识别文本       │
│        Progress/TextDelta/ProductCard/... -> 同对话   │
│    }                                                 │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ 后端: POST /api/v1/voice/recognize                   │
│ Body: multipart/form-data (audio file)               │
│                                                      │
│ voice_recognition.py:                                │
│   1. 音频文件 -> Doubao multimodal API (ASR)         │
│   2. 返回识别文本                                     │
│   3. 将识别文本作为 query 进入正常 RAG 管道            │
│   4. SSE 流式返回 (VoiceRecognized + 后续事件)        │
└─────────────────────────────────────────────────────┘
```

---

## 4. 商品对比机制

### 4.1 对比流程

```
用户: "对比 Nike Air Max 270 和 Adidas Ultraboost"
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ 后端: LangGraph route_after_intent                   │
│                                                      │
│ 1. classify_intent -> intent="compare"               │
│ 2. _resolve_compare_targets(query) -> 提取商品名称     │
│ 3. node_compare:                                      │
│    a. _fetch_products_from_db(source_product_ids)     │
│       └─ PostgreSQL SELECT by source_product_id        │
│    b. comparator.compare_products(products)           │
│       └─ 生成对比维度 (价格/评分/品牌/材质/功能)       │
│    c. SSE Compare event (dimensions)                 │
│    d. SSE TextDelta (对比总结)                        │
│    e. SSE Done                                        │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ 前端: CompareScreen 渲染                             │
│                                                      │
│ 收到 Compare event -> accCompareDims                  │
│ Done 时:                                              │
│   - 提交 Assistant 消息 (含 compareDimensions)         │
│   - CompareScreen 渲染对比表格                        │
│     Row { 维度名 | 商品1值 | 商品2值 }                 │
└─────────────────────────────────────────────────────┘
```

### 4.2 独立比价页

CompareScreen 也支持独立搜索（不经过 LangGraph），直接调用 `/api/products?search=xxx` 获取商品列表，前端按分类标签过滤展示。

---

## 5. 购物车机制

### 5.1 聊天内购物车操作

```
用户: "把第一件加入购物车"
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ 后端: LangGraph node_cart                            │
│                                                      │
│ 1. _extract_cart_action(query) -> action="add"       │
│ 2. _extract_cart_item_indices(query) -> [0]          │
│ 3. _find_product_for_cart(index, context_products)   │
│    └─ 从上下文中获取商品信息                          │
│ 4. cart_service.add_to_cart(product, quantity=1)      │
│ 5. SSE TextDelta: "已将 Nike Air Max 270 加入..."    │
│ 6. SSE Done                                          │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│ 前端: syncCartAfterChatIfNeeded(text)                │
│                                                      │
│ 检测购物车相关关键词 -> userRepo.syncCartFromBackend() │
│ -> CartEvents.notifyChanged() -> CartViewModel 刷新   │
└─────────────────────────────────────────────────────┘
```

### 5.2 购物车操作类型

| 操作 | 触发词示例 | 后端处理 |
|------|-----------|----------|
| 查看 | "看看购物车" | `cart_service.get_cart()` |
| 添加 | "加入购物车" | `cart_service.add_to_cart()` |
| 修改数量 | "改成2件" | `cart_service.update_quantity()` |
| 移除 | "删掉第一件" | `cart_service.remove_from_cart()` |
| 清空 | "清空购物车" | `cart_service.clear_cart()` |
| 结算 | "确认下单" | 前端跳转结算页 |

### 5.3 结算流程

```
用户输入"确认下单"
    -> shouldOpenCheckout() 检测确认关键词
    -> 检查购物车是否有商品
    -> 有商品: checkoutNavigationRequest++ -> 前端跳转结算页
    -> 无商品: 走正常 SSE 对话流程
```

---

## 6. 后端 RAG 管道

### 6.1 LangGraph StateGraph 流转

```
用户请求
    │
    ▼
node_classify_intent
    ├── LLM 意图分类 (recommend/compare/cart/clarify/chitchat/web_search)
    ├── Slot 提取 (category, brand, price_range, exclude_*)
    ├── 否定语义提取 ("不要红色" -> exclude_attributes)
    ├── 品类别名映射 (_CATEGORY_ALIASES)
    └── Query rewrite (短查询扩展 ≤6 字符)
    │
    ▼
route_after_intent (条件路由)
    ├── chitchat -> node_generate (直接回复)
    ├── web_search -> node_web_search
    ├── compare -> node_compare
    ├── cart -> node_cart
    ├── clarify (缺少关键信息) -> node_clarify
    └── recommend -> node_retrieve
         │
         ▼
    node_retrieve
         ├── rag_retrieve(query, slots, exclusions)
         │   ├── embed_text (BGE-large-zh -> 1024维向量)
         │   ├── pgvector hybrid_search
         │   │   ├── dense: embedding <=> query_vec (cosine)
         │   │   ├── keyword: search_vector @@ plainto_tsquery
         │   │   └── RRF 融合 (k=60)
         │   ├── 分级回退 (类目+价格 -> 类目 -> 无类目)
         │   ├── 场景分解 + 类目感知 MMR 采样
         │   ├── exclusion 过滤 (NOT attributes->>:key = :val)
         │   └── BGE-Reranker-v2-m3 重排
         ├── product_ranker (intent-aware 5维加权排序)
         │   semantic*0.4 + price*0.2 + rating*0.15
         │   + brand*0.1 + attributes*0.15
         └── Precision@K 监控
         │
         ▼
    node_generate
         ├── 构建生成 Prompt (反幻觉约束)
         ├── LLM 流式生成 (Doubao-Seed-2.0-lite)
         ├── SSE 交错输出 (text_delta + product_cards)
         └── SSE Done
```

### 6.2 数据存储

```
PostgreSQL (单一数据库):
    ├── products 表
    │   ├── 结构化字段 (id, title, price, category, brand, ...)
    │   ├── embedding vector(1024) -- BGE-large-zh 向量
    │   ├── search_vector tsvector  -- 全文搜索 (title A + desc B + cat C)
    │   ├── ivfflat 索引 (lists=100) -- 向量近似搜索
    │   └── GIN 索引 -- 全文搜索
    │
    └── 数据源: data/products/products_expanded_100.jsonl (287条)
        启动时自动导入: ensure_pgvector_data()
        ├── JSONL -> PostgreSQL seed
        ├── CREATE EXTENSION vector
        ├── 生成 tsvector 列 + 索引
        └── 批量生成 embedding + UPDATE
```

### 6.3 DEMO_MODE 快速路径

当 `DEMO_MODE=true` 时，`generate_response()` 跳过 LLM 调用：
1. 仍执行 pgvector 检索 + 重排
2. 使用模板生成回复文本
3. 适用于无 API Key 的离线演示

---

## 7. 全局 UI 系统

### 7.1 渐变条 GradientTopBar

```
GradientTopBar(icons: @Composable RowScope.() -> Unit)

计算逻辑:
    statusBarHeight = WindowInsets.statusBars.topPadding
    gradientHeight = statusBarHeight × 0.14
    总高 = statusBarHeight + gradientHeight

    Box(totalHeight, fillMaxWidth)
    ├── 背景: 水平渐变 (#C5D9F0 -> #EDE7F0 -> #F5D5D8)
    └── Row(padding(horizontal=4dp), SpaceBetween)
        └── icons()  ← 各页面自定义图标
```

### 7.2 ChatInputBar (可复用输入栏)

```
ChatInputBar(chatViewModel, onSendRequested?, placeholder, showIcons)

Surface(shadowElevation=3dp) {
    Row {
        📷 IconButton (拍照入口)
        OutlinedTextField (输入框, RadiusFull, 最大4行)
        🎤 IconButton (语音入口)
        🔵 FilledIconButton (发送, CircleShape)
    }
}
```

### 7.3 颜色系统

```
渐变: #C5D9F0 -> #EDE7F0 -> #F5D5D8
品牌蓝 Primary: #4A90D9
品牌粉 BrandPink: #E8917E
价格红 TextPrice: #FF5C5C
用户气泡: #E3F0FD
页面底 Background: #F8F9FA
卡片 Surface: #FFFFFF
中性色: Neutral50~Neutral900
```

### 7.4 尺寸规范

```
渐变图标: IconButton=34dp / Icon=26dp
搜索图标: IconButton=44dp / SendButton=48dp
圆角: RadiusFull(50%) / RadiusLg(20dp) / RadiusMd(12dp)
间距: Dimens.space1(4dp) ~ space12(48dp)
```

---

## 8. 导航与路由机制

### 8.1 路由表

```
NavGraph (AppNavGraph)
├── "home"              -> HomeScreen(chatViewModel)
├── "compare_tab"       -> CompareTabScreen()
├── "explore"           -> ExploreScreen(chatViewModel, onChatSend, onPostClick)
├── "profile"           -> ProfileScreen(onSettingsClick)
├── "settings"          -> SettingsScreen(onBack)
├── "category_list"     -> CategoryListScreen(navController)
├── "explore_post/{id}" -> ExploreProductPostScreen(postId, onBack)
└── "history"           -> HistoryScreen()
```

### 8.2 ChatViewModel 共享

```
NavGraph (顶层) {
    val chatViewModel: ChatViewModel = viewModel()
        ↓ 注入 (Activity 作用域)
    HomeScreen(chatViewModel)
    ExploreScreen(chatViewModel, onChatSend)
}
```

### 8.3 HistoryDrawer 触发

```
NavGraph {
    val drawerVisible: Boolean
    CompositionLocalProvider(
        LocalOnMenuClick provides { drawerVisible = true }
    )
}

各页面菜单图标:
    onClick = LocalOnMenuClick.current  -> drawerVisible = true
    -> HistoryDrawer(visible, onDismiss, onSessionClick, onNewChat)
```

### 8.4 多对话管理

```
对话持久化: SQLite (UserRepository)
    ├── conversations 表 (id, title, created_at)
    ├── messages 表 (id, conversation_id, role, content, product_cards_json, ...)
    └── settings 表 (key-value: session_id, last_conversation_id, clarify_chips_{convId}, ...)

对话切换:
    loadConversation(convId)
    -> 从 SQLite 恢复 messages
    -> 恢复该对话的 clarify_chips
    -> 更新 uiState
```

---

## 附录: 关键技术栈

| 层 | 技术 |
|----|------|
| 前端框架 | Jetpack Compose (Material3) |
| 状态管理 | AndroidViewModel + StateFlow |
| 导航 | Jetpack Navigation Compose |
| 图片加载 | Coil (AsyncImage) |
| 本地存储 | SQLite (Room-compatible) |
| TTS | Android TextToSpeech |
| 后端 | FastAPI + uvicorn |
| Agent 编排 | LangGraph StateGraph (7 nodes) |
| 向量库 | PostgreSQL + pgvector (1024维, cosine) |
| 全文搜索 | PostgreSQL tsvector (GIN 索引) |
| Embedding | BAAI/bge-large-zh-v1.5 |
| Reranker | BGE-Reranker-v2-m3 |
| 视觉 API | Doubao OpenAI-compatible vision API |
| LLM | Doubao-Seed-2.0-lite |
