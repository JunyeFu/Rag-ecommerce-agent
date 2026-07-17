# 拾物 App — 全链路机制设计文档 v1.0

> **⚠️ 辅助文档** - 开发权威入口为 [`DEV-CONTROL.md`](../DEV-CONTROL.md)，如有冲突以权威文档为准。
>
> 本文档详尽描述拾物 App 所有已实现功能的端到端数据流、控制流与渲染机制。
> 用于项目审核、交接与后续开发参考。

---

## 目录

1. [主页对话推荐机制](#1-主页对话推荐机制)
2. [Doubao 视觉 API 拍照找货机制](#2-doubao-视觉-api-拍照找货机制)
3. [比价页搜索与分类机制](#3-比价页搜索与分类机制)
4. [探索页社交帖机制](#4-探索页社交帖机制)
5. [设置页机制](#5-设置页机制)
6. [我的页面机制](#6-我的页面机制)
7. [全局 UI 系统](#7-全局-ui-系统)
8. [导航与路由机制](#8-导航与路由机制)
9. [后端数据管道](#9-后端数据管道)
10. [数据存储结构](#10-数据存储结构)

---

## 1. 主页对话推荐机制

### 1.1 用户输入 → 推荐展示全流程

```
用户输入"我想要一双运动鞋"
        │
        ▼
┌─────────────────────────────────────────────────────┐
│ ChatInputBar (Compose)                               │
│ - 文本输入: OutlinedTextField                        │
│ - 拍照/语音图标: 预留 未实现                         │
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
│    - streamingText = ""                             │
│    - streamingCards = emptyList()                   │
│    - searchStatus = "正在搜索中…"                    │
│ 4. 调用 simulateStreamingResponse(userQuery)       │
└─────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│ simulateStreamingResponse(userQuery)                 │
│                                                      │
│ 1. delay(800ms) — 模拟网络延迟                       │
│                                                      │
│ 2. generateMockResponse(query) → 生成文字回复:       │
│    ┌──────────────────────────────────────────┐     │
│    │ 运动鞋 → "为您找到几款热门运动鞋。轻盈透气  │     │
│    │          运动鞋采用网面设计，¥319起..."     │     │
│    │ 耳机   → "推荐两款蓝牙耳机：小米真无线..."   │     │
│    │ 水杯   → "苏泊尔316不锈钢保温杯¥129..."     │     │
│    │ 其他   → "为您找到以下相关商品..."          │     │
│    └──────────────────────────────────────────┘     │
│                                                      │
│ 3. getRecommendedProducts(query) → 获取3个商品:       │
│    ┌──────────────────────────────────────────┐     │
│    │ 运动鞋 → p001, p002, p003                 │     │
│    │ 耳机   → p003, p004, p011                 │     │
│    │ 水杯   → p005, p018, p019                 │     │
│    │ 手机   → emptyList() (触发追问)           │     │
│    │ 其他   → mockProducts.take(3)             │     │
│    └──────────────────────────────────────────┘     │
│                                                      │
│ 4. 逐字流式输出 (30ms/字):                           │
│    for (char in responseText) {                      │
│        delay(30)                                     │
│        uiState.update { streamingText += char }      │
│    }                                                  │
│                                                      │
│ 5. delay(400ms) → 输出商品卡片:                       │
│    uiState.update { streamingCards = products }      │
│                                                      │
│ 6. delay(600ms) → 完成:                              │
│    messages += ChatMessage(role=Assistant,            │
│        content=responseText, productCards=products)   │
│    isStreaming = false                               │
│    streamingText = ""                                │
│    streamingCards = emptyList()                      │
└─────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│ HomeScreen (Compose) 响应式渲染                       │
│                                                      │
│ 观察: val uiState by chatViewModel.uiState           │
│           .collectAsState()                          │
│                                                      │
│ 渲染逻辑:                                            │
│ if (messages.isEmpty() && !isStreaming)              │
│     → 显示空态: "输入商品需求，AI为你精准推荐"       │
│ else                                                 │
│     → ChatMessageList:                               │
│       LazyColumn {                                   │
│         messages.forEach { MessageBubble(it) }       │
│         if (isStreaming) {                           │
│           StreamingBubble(                           │
│             text=streamingText,                      │
│             isActive=true,                           │
│             searchStatus=searchStatus,               │
│             productCards=streamingCards              │
│           )                                          │
│         }                                            │
│         if (clarifyChips.isNotEmpty()) {             │
│           chips.forEach { AssistChip }               │
│         }                                            │
│       }                                              │
│                                                      │
│ MessageBubble:                                       │
│   User消息: 蓝色气泡 (E3F0FD), 右对齐                │
│   Agent消息: 白色气泡 + ProductCard列表              │
│                                                      │
│ ProductCard:                                         │
│   AsyncImage(商品图) + 商品名 + 价格(红色)           │
│   + 品牌 + 得分 + 亮点标签                           │
└─────────────────────────────────────────────────────┘
```

### 1.2 每日推荐问候

```
App 启动 → NavGraph 创建 ChatViewModel → HomeScreen LaunchedEffect(Unit)
    → chatViewModel.sendDailyGreeting()
    → 消息: "fujunye，早上好\n\n以下是今日推荐："
    → 商品卡片: mockProducts.take(3)
```

### 1.3 ChatViewModel 架构

```
ChatViewModel : ViewModel()
    ├── _uiState: MutableStateFlow<GuideUiState>
    │       ├── messages: List<ChatMessage>       // 历史消息列表
    │       ├── inputText: String                  // 输入框文本
    │       ├── isStreaming: Boolean               // 是否正在流式输出
    │       ├── streamingText: String             // 当前流式文本
    │       ├── streamingCards: List<Product>     // 当前流式商品卡片
    │       ├── searchStatus: String              // 搜索状态提示
    │       ├── clarifyChips: List<String>        // 追问选项
    │       └── screenState: ScreenState          // Idle/Content/Error
    │
    ├── sendDailyGreeting()    // 每日问候
    ├── sendMessage()          // 发送消息
    ├── onInputChange()        // 输入变化
    ├── onClarifyChipClick()   // 追问选项点击
    └── simulateStreamingResponse()  // Mock SSE 模拟
```

---

## 2. Doubao 视觉 API 拍照找货机制

### 2.1 完整流程

```
用户上传鞋子照片
        │
        ▼
┌─────────────────────────────────────────────────────┐
│ POST /api/v1/upload/vision-search                   │
│ Content-Type: multipart/form-data                    │
│ Body: file=@shoe.jpg                                │
└─────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│ upload.py → vision_search(file)                      │
│                                                      │
│ 1. 读取文件: contents = await file.read()            │
│ 2. 大小限制: 10MB                                    │
│ 3. 保存图片: save_upload_image() → uploads/UUID.jpg  │
│                                                      │
│ 4. Doubao 视觉 API 识别:                              │
│    product_info = await parse_product_image(contents) │
│    └─ 失败 → SSE ErrorEvent + DoneEvent             │
│                                                      │
│ 5. 构造搜索查询:                                      │
│    search_query = _build_search_query(product_info)   │
│    ┌──────────────────────────────────────────┐     │
│    │ 品类+品牌优先, keywords去重追加            │     │
│    │ 例: "运动鞋 NIKE 跑步鞋 红色 轻量"        │     │
│    └──────────────────────────────────────────┘     │
│                                                      │
│ 6. Qdrant 检索:                                      │
│    candidates = await search_similar_products(       │
│        query_text=search_query, top_k=8)             │
│                                                      │
│ 7. SSE 流式返回:                                      │
│    yield vision_parsed event                        │
│    for product in candidates:                       │
│        yield ProductCardEvent.to_sse()               │
│    yield DoneEvent.to_sse()                          │
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
│   1. 检查 DOUBAO_API_KEY                              │
│   2. base64 编码图片并构造 image_url data URL         │
│   3. 调用 client.chat.completions.create(...)         │
│                                                      │
│ _parse_with_doubao():                                │
│   1. base64编码: img_b64 = b64encode(image_bytes)    │
│   2. data_url = "data:image/jpeg;base64,{img_b64}"   │
│   3. 构造 OpenAI-compatible messages:                 │
│      [{role: "user", content: [                      │
│        {type: "image_url", image_url: {url:data_url}},│
│        {type: "text", text: prompt}                  │
│      ]}]                                             │
│   4. 调用 Doubao 视觉模型                             │
│   5. 读取 message.content → _parse_vlm_output(text)  │
│                                                      │
│ Prompt: "分析商品图片提取品类/品牌/颜色/材质/         │
│          风格/关键词/描述, 只输出JSON"                │
│                                                      │
│ 输出格式: {category, brand, color, material,          │
│            style, keywords[], description, confidence}│
│                                                      │
│ JSON解析: 去markdown代码块 → json.loads              │
│          失败 → regex提取{} → 兜底空字典              │
│                                                      │
│ 耗时取决于云端 API 网络与模型响应，不再加载本地视觉模型 │
└─────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│ Qdrant 相似检索: retriever.py                        │
│                                                      │
│ search_similar_products(query_text, top_k=8):        │
│   1. query_vector = await embed_text(query_text)     │
│      └─ BGE-large-zh-v1.5, 1024维                   │
│   2. qdrant.query_points(                            │
│        collection="products",                        │
│        query=query_vector, limit=top_k)              │
│   3. 结构化: {product_id, title, price, rating,       │
│               brand, category, match_score,           │
│               highlights[], image_url}               │
└─────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│ SSE 事件流 (text/event-stream)                       │
│                                                      │
│ data: {"type":"vision_parsed","product_info":{...}}  │
│ data: {"type":"product_cards","product_id":"...",    │
│        "title":"Nike Air Max 270...","price":899,    │
│        "rating":4.7,"match_score":0.6,               │
│        "highlights":[...],"index":1,"total":8}       │
│ ... (共8张商品卡片)                                   │
│ data: {"type":"done","total_cards":8,"message":"..."} │
└─────────────────────────────────────────────────────┘
```

### 2.2 视觉 API 错误处理

```
parse_product_image() 失败
    → RuntimeError("Doubao vision API failed...")
    → upload.py catch RuntimeError
    → SSE ErrorEvent(code="VISION_API_UNAVAILABLE", message="...")
    → SSE DoneEvent(total_cards=0, message="...")
    → StreamingResponse (非500错误)
```

---

## 3. 比价页搜索与分类机制

### 3.1 本地搜索流程

```
用户在比价页输入"运动鞋"并发送
        │
        ▼
┌─────────────────────────────────────────────────────┐
│ CompareSearchBar (独立组件, 不依赖ChatViewModel)      │
│                                                      │
│ 1:1 复刻主页 ChatInputBar:                           │
│ 📷 IconButton (拍照) + 输入框 + 🎤 IconButton (语音)  │
│ + 🔵 FilledIconButton (发送)                         │
│                                                      │
│ 状态: query: String (本地), onQueryChange, onSend    │
└─────────────────────────────────────────────────────┘
        │ onSend → doSearch(query)
        ▼
┌─────────────────────────────────────────────────────┐
│ doSearch(query) — 本地匹配算法                        │
│                                                      │
│ 输入: query (用户输入的搜索词)                         │
│ 数据源: allProducts (MockCompareData.products)        │
│                                                      │
│ 评分规则:                                             │
│   商品名.contains(query)       → +10                │
│   品牌.contains(query)         → +5                 │
│   分类.contains(query)         → +3                 │
│   空格分词.商品名.contains(token) → +3  (每个token)   │
│   空格分词.品牌.contains(token)   → +2  (每个token)   │
│                                                      │
│ 筛选: score > 0 的产品 → 按分降序 → take(10)         │
│                                                      │
│ 副作用:                                               │
│   searchResults = top10 (List<Product>)              │
│   hasSearched = true                                 │
│   selectedCategory = "推荐" (自动切换)               │
└─────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│ CompareProductGrid — 2列网格渲染                      │
│                                                      │
│ LazyVerticalGrid(columns=Fixed(2)) {                 │
│   items(products) { product ->                       │
│     Card {                                           │
│       AsyncImage(product.imageUrl)  // 1:1比例       │
│       Text(product.name, maxLines=2)                 │
│       Row {                                          │
│         Text("¥{price}")  // 红色加粗                │
│         Text("{salesCount}人付款")  // 灰色小字       │
│       }                                              │
│     }                                                │
│   }                                                  │
│ }                                                    │
│                                                      │
│ 点击卡片 → selectedProduct = product.id              │
│           → CompareTrackingSheet 展开                │
└─────────────────────────────────────────────────────┘
```

### 3.2 分类标签过滤

```
CompareTabScreen
    ├── 分类标签 (ScrollableTabRow): 推荐/运动鞋/数码/箱包/家居/美妆/食品/宠物/全部
    │   默认: selectedCategory = "推荐"
    │
    ├── product过滤 (derivedStateOf):
    │   "推荐"/"全部" → allProducts (全部)
    │   其他         → allProducts.filter { it.category == selectedCategory }
    │
    └── 点击分类标签 → hasSearched = false (退出搜索模式)
```

### 3.3 挂画式价格对比面板

```
点击商品卡片 → CompareTrackingSheet
    │
    ├── 关闭方式1: 点击拖拽把手区域 (整行Box clickable)
    ├── 关闭方式2: 向下拖动超过150px (detectVerticalDragGestures)
    │
    └── 内容: LazyColumn {
            platformTrends.forEach { platform →
                PriceTrendCard {
                    Canvas曲线图 (红色折线+浅粉面积+空心终点圆点+横轴标注)
                    最低价来源 + 最低价格
                }
            }
        }
```

---

## 4. 探索页社交帖机制

### 4.1 随机卡片地图

```
ExploreScreen 启动
        │
        ▼
┌─────────────────────────────────────────────────────┐
│ 布局生成 (remember + Random(42)固定种子)             │
│                                                      │
│ 1. 12×9 网格(步长118dp), 100张卡片                   │
│ 2. 将100个帖子索引随机shuffle                         │
│ 3. 逐个尝试放入空闲格子(碰撞检测)                     │
│ 4. 最多500次尝试/卡片                                 │
│ 5. 初始滚动到网格中心 (LaunchedEffect)                │
│                                                      │
│ 卡片样式: 110dp正方形                                 │
│   ├── AsyncImage(帖子第一张商品图, 1:1 Crop)         │
│   ├── Row: 圆形头像(16dp) + 作者名                   │
│   └── Text(帖子标题, 截断8字)                        │
└─────────────────────────────────────────────────────┘
        │ 点击卡片
        ▼
┌─────────────────────────────────────────────────────┐
│ onPostClick(postId)                                  │
│ → navController.navigate("explore_post/$postId")     │
└─────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│ ExploreProductPostScreen(postId, onBack)             │
│                                                      │
│ 数据: MockExplorePosts.posts.find { postId }        │
│                                                      │
│ 页面结构:                                             │
│ 1. GradientTopBar (返回箭头)                         │
│ 2. 作者信息行: 圆形头像(40dp) + 昵称 + 更多三点      │
│ 3. 大图轮播:                                         │
│    AsyncImage(4:3比例, Crop)                        │
│    左右60dp区域点击切换                               │
│    分页指示点 (8dp当前/6dp其他, Primary/Neutral300)   │
│ 4. 正文区域 (左对齐, 非卡片):                         │
│    标题 (titleLarge, Bold)                          │
│    段落×3 (bodyLarge, lineHeight×1.6, 12dp间距)      │
│ 5. 整页可纵向滚动 (verticalScroll)                   │
└─────────────────────────────────────────────────────┘
```

### 4.2 帖子数据结构

```kotlin
ExplorePost
├── postId: String          // "post_001" ~ "post_100"
├── author:
│   ├── id: String          // "auth_001"
│   ├── name: String        // "跑鞋控小王"
│   └── avatar: String      // 头像标识
├── product:
│   ├── id: String          // 关联商品ID
│   ├── category: String    // "运动鞋"
│   ├── title: String       // "Nike Air Max 270 日常穿搭分享"
│   └── images: List<String> // 2张picsum图片
└── content:
    ├── title: String       // "这双鞋已经陪我走了三个月了"
    └── body: List<String>  // 3段日常体验段落
```

---

## 5. 设置页机制

### 5.1 进入路径

```
我的页面 → 点击设置图标(ProfileHeader右上角)
    → navController.navigate("settings")
    → SettingsScreen(onBack = { popBackStack() })
```

### 5.2 页面结构

```
SettingsScreen
├── GradientTopBar (返回箭头 + "设置"标题 + 通知角标 + 更多)
├── 分组1: 账号与安全
│   ├── 个人信息 → (无操作)
│   ├── 账号与安全 → (无操作)
│   ├── 收货地址 → (无操作)
│   ├── 支付设置 → (无操作)
│   └── 国家与地区 → "中国" (无操作)
├── 分组2: 功能
│   ├── 通用设置 → (无操作)
│   ├── 消息通知 → (无操作)
│   ├── 隐私设置 → (无操作)
│   ├── 深色模式 → Switch(可切换, 本地状态)
│   └── 个性皮肤 → "默认" (无操作)
├── 分组3: 关于
│   ├── 商家入驻 → (无操作)
│   ├── 帮助与反馈 → (无操作)
│   └── 关于拾物 → "v1.0.0 有新版本" (橙色提示)
├── 法律链接行: 个人信息共享清单 / 个人信息收集清单 / 证照信息
└── 底部按钮: 切换账号(粉色边框) + 退出登录(灰色边框)
```

---

## 6. 我的页面机制

### 6.1 页面结构

```
ProfileScreen
├── ProfileHeader (100dp渐变)
│   ├── Row(CenterStart对齐)
│   │   ├── 圆形头像 (56dp, "海" 文字)
│   │   └── 用户名 "fujunye" (titleLarge, Bold)
│   └── 右上角: 客服图标 + 设置图标(→Settings)
├── 购物车预览区 (CartPreviewSection)
├── 订单功能区 (OrderSection)
├── 功能入口区 (FeatureSection)
└── 领券中心 (CouponSection)
```

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
    ├── 背景: 水平渐变 (#C5D9F0 → #EDE7F0 → #F5D5D8)
    ├── contentAlignment = Center
    └── Row(padding(horizontal=4dp), SpaceBetween)
        └── icons()  ← 各页面自定义图标

前置条件: Activity.enableEdgeToEdge()
效果: 渐变从屏幕0px开始, 覆盖状态栏区域
```

### 7.2 ChatInputBar (可复用输入栏)

```
ChatInputBar(chatViewModel, onSendRequested?, placeholder, showIcons)

Surface(shadowElevation=3dp) {
    Row {
        📷 IconButton (showIcons时显示)
        OutlinedTextField (输入框, RadiusFull, 最大4行)
        🎤 IconButton (showIcons时显示)
        🔵 FilledIconButton (发送, CircleShape)
    }
}

绑定: chatViewModel.uiState.collectAsState()
发送: chatViewModel.sendMessage() + onSendRequested?.invoke()
```

### 7.3 颜色系统

```
渐变: #C5D9F0 → #EDE7F0 → #F5D5D8
品牌蓝 Primary: #4A90D9
品牌粉 BrandPink: #E8917E
价格红 TextPrice: #FF5C5C
用户气泡: #E3F0FD
Agent胶囊: PrimaryLight (#FFE0E0)
页面底 Background: #F8F9FA
卡片 Surface: #FFFFFF
地图底: #F0F0F3
中性色: Neutral50~Neutral900
```

### 7.4 尺寸规范

```
渐变图标: IconButton=34dp / Icon=26dp
搜索图标: IconButton=44dp / SendButton=48dp
圆角: RadiusFull(50%) / RadiusLg(20dp) / RadiusMd(12dp)
间距: Dimens.space1(4dp) ~ space12(48dp)
卡片: 产品列表110dp, 比价2列自适配
```

---

## 8. 导航与路由机制

### 8.1 路由表

```
NavGraph (AppNavGraph)
├── "home"              → HomeScreen(chatViewModel)
├── "compare_tab"       → CompareTabScreen()
├── "explore"           → ExploreScreen(chatViewModel, onChatSend, onPostClick)
├── "profile"           → ProfileScreen(onSettingsClick)
├── "settings"          → SettingsScreen(onBack)
├── "category_list"     → CategoryListScreen(navController)
├── "explore_post/{id}" → ExploreProductPostScreen(postId, onBack)
└── "history"           → HistoryScreen()
```

### 8.2 ChatViewModel 共享

```
NavGraph (顶层) {
    val chatViewModel: ChatViewModel = viewModel()
        ↓ 注入
    HomeScreen(chatViewModel)
    ExploreScreen(chatViewModel, onChatSend)
}

why viewModel(): Activity作用域, 页面切换不丢失会话状态
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
    onClick = LocalOnMenuClick.current  → drawerVisible = true
    → HistoryDrawer(visible, onDismiss, onSessionClick, onNewChat)
```

---

## 9. 后端数据管道

### 9.1 Qdrant 向量检索

```
数据模型 (seed_products.json, 190条):
{
  product_id, title, category, brand, price, rating,
  rating_count, attributes{}, highlights[], scenarios[], image_urls[]
}

向量化文本构造 (build_document_text):
  "商品名称: {title}"
  + "品牌: {brand} 分类: {category} 价格: {price}元 评分: {rating}分"
  + "属性: {attr_key:val} 亮点: {highlights} 场景: {scenarios}"
  + "用户评价: {review_texts}"

Embedding: BAAI/bge-large-zh-v1.5 (1024维, sentence-transformers)
入库: app.startup.ensure_qdrant_data() → 删除旧collection → 重建 → 向量化 → upsert
环境: HF_HUB_OFFLINE=1 HF_OFFLINE=1 (离线模式)
```

### 9.2 商品种子数据

```
品类分布 (190 Qdrant vectors, 94 细分类):
  3C数码(15) 鞋靴(12) 运动户外(11) 服饰(10) 箱包(8)
  美妆(10) 食品饮料(9) 家居(8) 图书(5) 宠物(4) 办公(5)
  玩具(4) 汽车用品(6) 母婴(5) 健康(4) ...
```

---

## 10. 数据存储结构

### 10.1 Mock 数据文件

```
MockProducts.kt         — 30条商品, 15品类 (HomeScreen搜索源)
MockCategoryProducts.kt — 10Tab 72条商品 (ExploreScreen旧数据)
MockCompareData.kt      — 7品类筛选 (CompareScreen)
MockExplorePosts.kt     — 100条社交分享帖 (ExploreScreen)
MockProfile.kt          — 购物车/订单/功能/优惠券数据
```

### 10.2 Product 数据模型

```kotlin
Product(
    id: String,          // "p001"
    name: String,        // "Nike Air Max 270 缓震透气跑鞋"
    price: Double,       // 899.0
    originalPrice: Double?, // 1099.0 (null表示无折扣)
    imageUrl: String,    // "https://placehold.co/..."
    category: String,    // "运动鞋"
    brand: String?,      // "Nike"
    source: String,      // "天猫旗舰店"
    salesCount: Int?,    // 21000
    rating: Float?,      // 4.7
    matchReason: String?, // 推荐理由
    colorVariants: List<ColorVariant>,
    attributes: Map<String, String> // {"材质":"网布","功能":"缓震/透气"}
)
```

### 10.3 ChatMessage 数据模型

```kotlin
ChatMessage(
    id: String,          // UUID
    role: MessageRole,   // User / Assistant
    content: String,     // 文本内容
    productCards: List<Product>?, // 关联商品卡片
    status: MessageStatus // Sending / Sent / Error
)
```

---

## 附录: 关键技术栈

| 层 | 技术 |
|----|------|
| 前端框架 | Jetpack Compose (Material3) |
| 状态管理 | ViewModel + StateFlow |
| 导航 | Jetpack Navigation Compose |
| 图片加载 | Coil (AsyncImage) |
| 后端 | FastAPI + uvicorn |
| 向量库 | Qdrant (1024维, Cosine距离) |
| Embedding | BAAI/bge-large-zh-v1.5 |
| 视觉 API | Doubao OpenAI-compatible vision API |
| LLM | Doubao-Seed-2.0-lite |
| 数据库 | PostgreSQL + pgvector |
| 代理 | Clash Verge → http://172.24.48.1:7897 |
