# 拾物 App — 前端设计总纲 v5.5

> Sprint 1 ✅ | Sprint 2 ✅ | Sprint 3 ✅ | Sprint 4 ✅ | Sprint 5 ✅ VLM+商品扩充+探索社交帖+视觉打磨 2026-05-26

---

## 一、架构决策

| # | 决策 |
|:--:|------|
| 1 | Agent 发送问候 — ChatMessage 承载 |
| 2 | 渐变薄条 — statusBar×0.14, edge-to-edge 从 0px |
| 3 | 图标尺寸 — IconButton 34dp / Icon 26dp (×0.8 原尺寸) |
| 4 | 比价/探索/我的 — 渐变条空白 |
| 5 | 无标题设计 — 页面即内容流 |
| 6 | 比价统一 2 列网格 — 点击展开挂画面板 (点击/下滑关闭) |
| 7 | 探索 100 张随机散落卡片 — 双轴滚动, 点击进入分享贴详情 |
| 8 | ChatViewModel 全局共享 — NavGraph 层创建 |
| 9 | 比价页独立搜索 — 本地匹配 10 条, 不跳转主页 |
| 10 | ChatInputBar 组件化 — 主页+探索复用, 比价自建同款 |
| 11 | HistoryDrawer 通过 CompositionLocal 全局触发 |

## 二、页面架构

```
App (4 Tab)
├── Tab1: 主页 — Agent 消息流 + ChatInputBar (拍照/语音/发送) + HistoryDrawer
├── Tab2: 比价 — 搜索栏(1:1复刻) + 分类Tab + 2列网格 + 挂画面板(下滑/点击关闭)
│      └── 搜索→本地匹配Top10→自动切推荐Tab→2列卡片展示
├── Tab3: 探索 — 100张随机散落分享贴卡片 + ChatInputBar(发送→跳主页)
│      └── ExploreProductPostScreen — 作者信息 + 大图轮播 + 正文左对齐
└── Tab4: 我的 — 渐变头部(头像+用户名水平排列,100dp) + 购物车+订单+功能+领券
```

### 搜索交互流

```
┌─────────────────────────────────────────────────────┐
│ 主页搜索   → ChatViewModel.sendMessage()             │
│             → SSE 流式 → 文字 + ProductCard            │
│ 探索搜索   → ChatViewModel.sendMessage()             │
│             → 自动 navigate("home") → 主页展示结果     │
│ 比价搜索   → 本地匹配(商品名/品牌/分类)                │
│             → 评分排序 Top 10 → 比价页内展示           │
│             → 自动切回「推荐」Tab                      │
└─────────────────────────────────────────────────────┘
```

## 三、色彩

```
渐变: #C5D9F0 → #EDE7F0 → #F5D5D8
品牌蓝: #4A90D9 | 品牌粉: #E8917E | 价格红: #FF5C5C
用户气泡: #E3F0FD | Agent胶囊: #FFE0E0
页面底: #F8F9FA | 卡片: #FFFFFF
地图底: #F0F0F3
```

## 四、探索页规格

```
类型: 社交分享贴随机散落地图
卡片数: 100 张 (MockExplorePosts)
布局: 12列 × 9行 网格, 随机放置不重叠 (种子=42)
卡片: 110dp 正方形, 间距 8dp, 步长 118dp
初始: 双轴居中对齐
滚动: 水平+垂直 360° 自由滚动
每卡片: 商品图 + 作者头像 + 作者名 + 标题(8字截断)
点击 → ExploreProductPostScreen (100条Mock数据)
```

### 分享贴详情页

```
ExploreProductPostScreen(postId, onBack)
├── GradientTopBar (返回箭头)
├── 作者信息行 (头像+昵称+更多三点)
├── 大图轮播 (2张, 左右点击切换, 指示点)
└── 正文 (标题+3段左对齐段落, 非卡片, lineHeight×1.6)
```

## 五、组件状态

| 组件 | 状态 | 说明 |
|------|:--:|------|
| GradientTopBar | ✅ | edge-to-edge, 总高=statusBar×1.14, 图标34/26dp |
| ChatInputBar | ✅ | 独立组件, 拍照/语音/发送图标 |
| ChatViewModel | ✅ | NavGraph 层共享 |
| HomeScreen | ✅ | 共享 ChatViewModel + HistoryDrawer |
| CompareScreen | ✅ | 本地搜索+7品类过滤+挂画面板(点击+下滑关闭) |
| CompareSearchBar | ✅ | 1:1复刻主页, 拍照/语音/发送 |
| CompareTrackingSheet | ✅ | 点击上方关闭 + 下滑150px收回 |
| ExploreScreen | ✅ | 100随机卡片 + ChatInputBar + 分享贴详情 |
| ExploreProductPostScreen | ✅ | 新建: 作者+大图轮播+正文 |
| ProfileScreen | ✅ | 头像+姓名水平排列, 渐变100dp |
| PriceTrendChart | ✅ | Canvas曲线图(折线+面积+空心圆点) |
| HistoryDrawer | ✅ | CompositionLocal 全局触发 |

## 六、Sprint 5 变更清单

### 6.1 渐变条打磨

| 迭代 | 参数 | 说明 |
|:--:|------|------|
| 初始 | statusBar×0.75 | 设计稿基准 |
| 1 | statusBar×0.375 | 首次收窄 |
| 2 | statusBar×0.1875 | 收窄为 1/2 |
| 3 | **statusBar×0.14** | 最终版 |
| — | edge-to-edge | 从屏幕0px开始, 覆盖状态栏 |
| — | 图标 42→34dp / 33→26dp | ×0.8 缩小 |

### 6.2 VLM 拍照找货

| 项目 | 详情 |
|------|------|
| 模型 | Doubao Vision API（云端），Qwen3-VL-2B 离线降级 |
| 端点 | POST /api/v1/upload/vision-search (SSE) |
| 事件流 | vision_parsed → product_cards×8 → done |
| 状态 | ✅ Nike鞋照→8双跑步鞋, 匹配度 0.53-0.60 |

### 6.3 商品数据扩充

| 维度 | 变更前 | 变更后 |
|------|:--:|:--:|
| pgvector 向量 | 50 | **287** |
| 品类 | 1 (电子) | **94** |
| MockProducts | 10条3品类 | **30条15品类** |
| MockCategoryProducts | 5Tab | **10Tab 72条** |
| MockCompareData | 2品类 | **7品类+默认推荐** |
| **MockExplorePosts** | — | **100条社交分享帖** |

### 6.4 探索页重构

| 项目 | v5.4 | v5.5 |
|------|------|------|
| 数据源 | MockCategoryProducts (24条) | MockExplorePosts (100条) |
| 布局 | 9×9螺旋 | 12×9随机散落(不重叠) |
| 卡片内容 | 商品名+价格 | 商品图+作者+标题 |
| 点击行为 | 无 | →ExploreProductPostScreen |
| 卡片尺寸 | 124dp | 110dp |
| 图片 | picsum自然风景 | placehold.co产品占位图 |

### 6.5 比价页打磨

| 特性 | 实现 |
|------|------|
| 搜索栏 1:1 复刻 | CompareSearchBar (拍照/语音/发送) |
| 本地搜索 | 评分匹配 Top10, 自动切推荐Tab |
| 挂画面板关闭 | 点击上方区域关闭 + 下滑150px收回 |
| 删除"收起"按钮 | ✅ |
| 分类过滤 | derivedStateOf 按 selectedCategory, 默认推荐 |

### 6.6 ProfileScreen 打磨

| 改动 | 改前 | 改后 |
|------|------|------|
| 布局 | Column (头像上, 名下) | Row (头像左, 名右) |
| 渐变高度 | 160dp | 100dp |
| 头像尺寸 | 64dp | 56dp |
| 对齐 | BottomStart | CenterStart |

### 6.7 编译修复

| 问题 | 修复 |
|------|------|
| Kotlin IC 路径污染 | `./gradlew clean` |
| CompareArrows 包路径 | `Icons.AutoMirrored.Filled.CompareArrows` |
| 缺 dp import | HomeScreen 添加 |
| 缺 collectAsState import | ChatInputBar 添加 |
| Dp * Int 顺序 | `STEP * col` 而非 `col * STEP` |
| 中文引号破坏 Kotlin 字符串 | `\u201c\u201d` → `\\"` |
| Scaffold import | `material3.*` 替代单独 import |

## 七、完整文件清单

```
新增:
  data/model/ExplorePost.kt                   分享贴数据模型
  data/mock/MockExplorePosts.kt              100条社交分享帖
  ui/screens/ExploreProductPostScreen.kt      分享贴详情页
  ui/components/ChatInputBar.kt              可复用输入栏

修改:
  docs/standards/DESIGN.md                    v5.4 → v5.5
  docs/progress/开发进度控制表.md              场景9/M7更新
  apps/backend/data/seed_products.json 50→287条
  data/mock/MockProducts.kt                   10→30条 (picsum→placehold)
  data/mock/MockCategoryProducts.kt           5Tab→10Tab (picsum→placehold)
  data/mock/MockCompareData.kt                默认推荐+7品类
  ui/navigation/NavGraph.kt                   ChatViewModel共享+explore_post路由+CompositionLocal
  ui/screens/HomeScreen.kt                    共享ChatViewModel+LocalOnMenuClick+图标34/26
  ui/screens/CompareScreen.kt                 搜索栏+本地搜索+下滑关闭
  ui/screens/ExploreScreen.kt                 100随机卡片+ChatInputBar+分享贴导航
  ui/screens/ProfileScreen.kt                 Row布局+100dp渐变
  ui/components/GradientScreenBackground.kt   edge-to-edge+0.14倍率
  ui/components/MainBottomNavBar.kt           图标修复
  MainActivity.kt                             enableEdgeToEdge()
```
