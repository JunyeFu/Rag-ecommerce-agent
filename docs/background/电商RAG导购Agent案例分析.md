# 电商 RAG 多模态导购 Agent 案例分析

> 文档类型：背景调研 / 竞品分析
> 服务项目：04-rag-ecommerce — 基于 RAG 的多模态电商 AI 导购 Agent
> 最后更新：2026-05-19

---

## 目录

1. [概述：电商 AI 导购 Agent 的三个时代](#1-概述电商-ai-导购-agent-的三个时代)
2. [大厂电商 RAG 导购系统](#2-大厂电商-rag-导购系统)
   - 2.1 [淘宝问问 (淘天集团)](#21-淘宝问问-淘天集团)
   - 2.2 [京东京言 (京东)](#22-京东京言-京东)
   - 2.3 [Amazon Rufus](#23-amazon-rufus)
   - 2.4 [Shopify Sidekick / Shop AI](#24-shopify-sidekick--shop-ai)
3. [RAG + 多模态检索方案](#3-rag--多模态检索方案)
   - 3.1 [图文混合搜索架构](#31-图文混合搜索架构)
   - 3.2 [商品图片理解 pipeline](#32-商品图片理解-pipeline)
   - 3.3 [多模态向量检索技术选型](#33-多模态向量检索技术选型)
4. [前端设计模式：流式对话与渐进推荐](#4-前端设计模式流式对话与渐进推荐)
   - 4.1 [豆包 (字节跳动) 对话 UI 设计](#41-豆包-字节跳动-对话-ui-设计)
   - 4.2 [文心一言 (百度) 商品卡片渲染](#42-文心一言-百度-商品卡片渲染)
   - 4.3 [ChatGPT + 插件生态的导购探索](#43-chatgpt--插件生态的导购探索)
5. [后端架构：Pipeline 设计与 LangGraph 最佳实践](#5-后端架构pipeline-设计与-langgraph-最佳实践)
   - 5.1 [意图识别 → 槽位填充 → 混合检索 → 排序 → 生成 Pipeline](#51-意图识别--槽位填充--混合检索--排序--生成-pipeline)
   - 5.2 [LangGraph 在电商场景的最佳实践](#52-langgraph-在电商场景的最佳实践)
   - 5.3 [LlamaIndex + Qdrant 混合检索工程经验](#53-llamaindex--qdrant-混合检索工程经验)
6. [评测体系：RAGAS 适配与人工评估](#6-评测体系ragas-适配与人工评估)
   - 6.1 [RAGAS 指标在电商导购的适配](#61-ragas-指标在电商导购的适配)
   - 6.2 [电商导购人工评估标准](#62-电商导购人工评估标准)
7. [对我们项目 (04-rag-ecommerce) 的具体设计建议](#7-对我们项目-04-rag-ecommerce-的具体设计建议)
8. [参考链接与延伸阅读](#8-参考链接与延伸阅读)

---

## 1. 概述：电商 AI 导购 Agent 的三个时代

| 时代 | 时间 | 代表方案 | 技术特征 |
|------|------|----------|----------|
| 1.0 关键词搜索 | 2010-2018 | 淘宝搜索框 / 京东搜索 | 倒排索引 + CTR排序，无语义理解 |
| 2.0 对话客服 | 2018-2023 | 阿里小蜜 / JD 智能客服 | 意图分类 + FAQ检索，单轮为主 |
| 3.0 AI 导购 Agent | 2023-至今 | 淘宝问问 / Amazon Rufus / Shop AI | LLM + RAG + 多模态 + 多轮决策 |

**3.0 时代核心能力要求**（也是本项目的目标）：

- **深度意图理解**：能从模糊需求（"想买个送女朋友的礼物"）逐步追问、细化到具体商品
- **RAG 增强回答**：检索商品详情、用户评价、营销文档等非结构化知识，确保回答专业准确
- **多模态融合**：支持以图搜商品、商品图片解读、穿搭推荐等视觉相关场景
- **流式体验**：文本流式输出 + 商品卡片渐进渲染，打造"豆包级"流畅交互
- **评测闭环**：端到端质量评测，覆盖准确率、检索精度、多轮一致性

---

## 2. 大厂电商 RAG 导购系统

### 2.1 淘宝问问 (淘天集团)

**名称**：淘宝问问（Taobao Wenwen）
**来源**：淘天集团 / 淘宝 App 内 AI 助手（2024年Q3上线）
**入口**：淘宝 App 首页搜索框右侧 AI 图标

#### 技术架构
```
┌─────────────────────────────────────────────────┐
│                  前端层 (淘宝 App)                 │
│  ┌─────────────────────────────────────────┐     │
│  │  AI 对话面板                             │     │
│  │  - 流式文本渲染 (Markdown + 自定义卡片)     │     │
│  │  - 商品卡片内嵌 (ProductCard Widget)       │     │
│  │  - 多选题交互 (clarification chips)       │     │
│  │  - 以图搜物入口 (拍照 / 相册)             │     │
│  └─────────────────────────────────────────┘     │
└───────────────────────┬─────────────────────────┘
                        │ SSE / WebSocket
┌───────────────────────▼─────────────────────────┐
│                  网关层                           │
│  ┌─────────────────────────────────────────┐     │
│  │  统一接入网关 (限流 / 鉴权 / 路由)          │     │
│  └─────────────────────────────────────────┘     │
└───────────────────────┬─────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────┐
│                  AI 服务层                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐     │
│  │ 意图识别  │ │ 查询改写  │ │ 多模态理解    │     │
│  │ (Bert/LLM)│ │ (LLM)   │ │ (CLIP/VLM)   │     │
│  └────┬─────┘ └────┬─────┘ └──────┬───────┘     │
│       └──────┬─────┴──────────────┘             │
│  ┌───────────▼───────────────────────────┐      │
│  │        混合检索引擎                     │      │
│  │  - 商品向量检索 (淘宝自研向量库)         │      │
│  │  - 评价/详情 RAG 检索                  │      │
│  │  - 实时价格/库存 API 调用              │      │
│  └───────────┬───────────────────────────┘      │
│  ┌───────────▼───────────────────────────┐      │
│  │        排序与生成层                     │      │
│  │  - 商品排序 (CTR + 相关性 + 个性化)      │      │
│  │  - LLM 回答生成 (千问/Qwen系列)        │      │
│  │  - 安全检查 (敏感词 / 合规过滤)         │      │
│  └───────────────────────────────────────┘      │
└─────────────────────────────────────────────────┘
```

#### 数据流（一次完整对话）
```
用户: "帮我推荐一款3000以内的蓝牙耳机，降噪要好"
  │
  ▼
意图识别 → [commodity_recommend, budget:3000, category:蓝牙耳机, attr:降噪]
  │
  ▼
查询改写 → ["蓝牙耳机 主动降噪 3000以内 推荐", "ANC耳机 高性价比 2024"]
  │
  ▼
混合检索 → 向量检索(Top200) + 关键词召回 + 类目过滤 → Top50
  │
  ▼
精排 → 价格/销量/评分/降噪参数匹配 → Top5
  │
  ▼
LLM 生成 → 流式回复 + 嵌入 Top5 商品卡片
  │
  ▼
用户看到: 文字分析 + 5张商品卡片 (图片/名称/价格/降噪参数/推荐理由)
```

#### 创新点
1. **"追问式导购"** — 不满足条件时主动反问，如"您平时主要在地铁还是办公室用？这对降噪类型有影响"
2. **知识融合** — 将商品详情页 + 用户评价摘要 + 行业测评文章统一检索，回答更全面
3. **多轮状态追踪** — 记录用户已看/已否定的商品，避免重复推荐
4. **场景化推荐** — 不直接搜商品，而是理解场景（"露营需要什么"→帐篷+睡袋+炉具）

#### 可借鉴到我们项目的设计
| 淘宝问问设计 | 我们的落地方式 |
|-------------|---------------|
| 追问式导购 (clarification) | Agent 的 clarify 节点：检测槽位空缺 → 生成追问 |
| 多源知识融合检索 | retriever 同时检索 products 和 knowledge 两个 Qdrant collection |
| 商品卡片嵌入流式 | SSE 事件 `product_cards` → Android Compose 异步渲染 ProductCard |
| 多轮状态追踪 | services/state_manager.py 维护偏好/预算/已看商品 |
| 场景化推荐 | intent.py 识别"场景类意图" → 展开为多品类检索 |

---

### 2.2 京东京言 (京东)

**名称**：京东京言（JD Jingyan）
**来源**：京东 / 京东 App AI 购物助手（2024年Q2内测）
**入口**：京东 App 搜索框 / 首页 AI 助手入口

#### 技术架构（核心差异）
```
┌──────────────────────────────────────────────┐
│              JD 言犀大模型 (ChatRhino)          │
│  - 电商领域微调 + RLHF                         │
│  - 支持商品属性精确提取                         │
│  - 集成京东供应链数据 (实时库存/物流)             │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│              RAG 检索引擎                      │
│  ┌──────────────────────────────────────┐    │
│  │  商品知识图谱 (JD Knowledge Graph)     │    │
│  │  - 品牌 → 系列 → 型号                 │    │
│  │  - 属性对齐 (不同品牌参数名统一)        │    │
│  │  - 同款商品关联                       │    │
│  └──────────────────────────────────────┘    │
│  +                                            │
│  ┌──────────────────────────────────────┐    │
│  │  评价摘要向量库                        │    │
│  │  - 好评/差评分别建库                   │    │
│  │  - 按属性维度聚合 (如"音质"相关评价)     │    │
│  └──────────────────────────────────────┘    │
└──────────────────────────────────────────────┘
```

#### 创新点
1. **商品知识图谱** — 将不同品牌的同类参数对齐（如"降噪深度"统一为 dB 值），实现精准对比
2. **评价维度化检索** — 不只搜"好评"，而是按"音质/佩戴舒适度/续航"等维度检索相关评价
3. **供应链实时联动** — 回答中嵌入实时库存状态和预计送达时间
4. **价格敏感度感知** — 根据用户历史行为判断价格敏感度，调整推荐策略

#### 可借鉴到我们项目的设计
| 京东京言设计 | 我们的落地方式 |
|-------------|---------------|
| 商品知识图谱 | MVP用JSON结构化属性字段替代；全量可引入 Neo4j 或 JSON Schema |
| 评价维度化检索 | 商品数据中添加 `review_summary` 字段，按维度分段检索 |
| 供应链联动 | MVP 不涉及，但预留 `stock_status` / `delivery_estimate` 字段 |
| 价格敏感度感知 | state_manager 记录用户价格偏好，product_ranker 加权时使用 |

---

### 2.3 Amazon Rufus

**名称**：Amazon Rufus
**来源**：Amazon / Amazon App AI 购物助手（2024年2月全球上线）
**入口**：Amazon App 底部搜索栏 AI 标签

#### 技术架构
```
Rufus 架构关键词:
- 底层模型: Amazon Bedrock (Claude + Amazon Titan)
- 检索系统: Amazon Kendra + OpenSearch 向量检索
- 产品目录: Amazon Product Knowledge Graph (数十亿商品)
- 个性化: 用户购物历史 + 浏览记录 + Wish List
```

#### 核心特性
1. **上下文感知** — 在当前浏览的商品详情页唤起 Rufus，自动理解上下文（"这件衣服有类似的吗？"）
2. **比较式对话** — "A 和 B 哪个更适合我？" → 自动提取两款商品属性对比
3. **售后集成** — 可查询订单状态、退货政策、保修信息
4. **Review Q&A** — 从海量用户评价中提取具体问题的答案（"这个行李箱能带上飞机吗？"）

#### 创新点：ReviewRAG — Amazon 特有的评价增强检索
```
用户: "这款耳机戴久了耳朵疼吗？"
  ↓
1. 语义检索 → 找到该商品下与"佩戴舒适度"相关的评价片段
2. 聚合分析 → "70%用户表示佩戴舒适，15%提到超过2小时有压迫感"
3. LLM 合成 → 流式回答 + 引用具体评价来源
```

#### 可借鉴到我们项目的设计
| Amazon Rufus 设计 | 我们的落地方式 |
|-------------------|---------------|
| 上下文感知对话 | state_manager 维护 `current_product_id` |
| 商品对比 Agent | services/comparator.py — 全量 M7 |
| Review Q&A | 知识库中包含评价摘要，retriever 按商品ID过滤 |
| 个性化推荐 | 用户画像（MVP用 session 内行为替代） |

---

### 2.4 Shopify Sidekick / Shop AI

**名称**：Shopify Sidekick (更名为 Shop AI)
**来源**：Shopify / 2023年发布
**定位**：为 Shopify 商家的顾客提供 AI 导购

#### 架构特点
```
特点: 轻量级、可嵌入、面向中小商家

┌─────────────────────────────┐
│  Shop AI 前端 SDK (Web/Mobile)│
│  - 可嵌入任意 Shopify 店铺    │
│  - 流式聊天 UI                │
└──────────┬──────────────────┘
           │
┌──────────▼──────────────────┐
│  Shopify 商家后台            │
│  - 商品目录同步 (自动)        │
│  - 店铺政策配置              │
│  - FAQ 自定义               │
└──────────┬──────────────────┘
           │
┌──────────▼──────────────────┐
│  Shopify AI 引擎            │
│  - 商品目录 RAG              │
│  - 库存/价格实时 API         │
│  - 自然语言 → 搜索过滤条件    │
└─────────────────────────────┘
```

#### 可借鉴点
- **"自然语言 → 搜索过滤条件"转换**：用户"200以内的高分手机"→ `price<=200 & rating>=4.5 & category=手机`，这个范式可直接复用到我们的 intent → slot filling
- **嵌入式 SDK**：我们的 Android App 可以考虑将核心对话组件打包为可复用的 Composable 模块

---

## 3. RAG + 多模态检索方案

### 3.1 图文混合搜索架构

```
           ┌──────────────────┐
           │  用户输入 Query   │
           └────────┬─────────┘
                    │
       ┌────────────┴────────────┐
       │                         │
   ┌───▼───┐                ┌───▼───┐
   │ 文本   │                │ 图片   │
   │ Encoder│                │ Encoder│
   │ BGE/   │                │ CLIP/  │
   │ BERT   │                │ ViT    │
   └───┬───┘                └───┬───┘
       │ 1024d                  │ 512d
       │                        │
       └────────┬───────────────┘
                │
    ┌───────────▼───────────┐
    │  向量融合 / 加权拼接    │
    │  fused = α·v_text     │
    │        + (1-α)·v_img  │
    └───────────┬───────────┘
                │
    ┌───────────▼───────────┐
    │    Qdrant 混合检索     │
    │  - 向量相似度 (cosine) │
    │  - 关键词过滤          │
    │  - 元数据过滤          │
    └───────────┬───────────┘
                │
    ┌───────────▼───────────┐
    │  重排序 (Cross-Encoder)│
    │  BGE-Reranker /       │
    │  Cohere Rerank API    │
    └───────────┬───────────┘
                │
    ┌───────────▼───────────┐
    │   返回 Top-K 商品      │
    └───────────────────────┘
```

#### 关键技术决策

| 决策点 | 选项 A | 选项 B | 本项目建议 |
|--------|--------|--------|-----------|
| 文本 Embedding | BGE-large-zh-v1.5 (1024d) | text2vec-large-chinese (1024d) | BGE-large-zh-v1.5（已采用） |
| 图片 Embedding | Chinese-CLIP (512d) | InternVL2 (768d) | MVP用 CLIP，全量升级 InternVL2 |
| 向量融合方式 | 加权拼接后统一检索 | 分别检索后结果融合 | MVP 分别检索后结果融合（更灵活） |
| 向量数据库 | Qdrant | Milvus | Qdrant（已采用，Docker 部署简单） |

### 3.2 商品图片理解 pipeline

```
用户上传图片 (拍照 / 相册)
      │
      ▼
┌──────────────┐
│  图片预处理    │
│  - 压缩到 512 │
│  - 格式归一化 │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  多模态理解    │
│  (VLM/OCR)   │
├──────────────┤
│ 路径1: OCR   │
│  - PaddleOCR  │  → 提取文字: "品牌X 型号Y"
│  - 商品标签识别│
│              │
│ 路径2: VLM   │
│  - Qwen-VL   │  → 结构化描述:
│  - GPT-4V    │    {category, color,
│  (DeepSeek?) │     style, brand_hint}
│              │
│ 路径3: CLIP  │
│  - Chinese-  │  → 512d 向量 → 以图搜图
│     CLIP     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  结构化提取    │
│  LLM 总结:   │
│  "用户可能在  │
│   找一件[类别]│
│   为[品类]的  │
│   [颜色][风格]│
│   商品..."    │
└──────┬───────┘
       │
       ▼
  进入意图识别 + 检索 pipeline
```

#### 多模态 VLM 选型对比

| 模型 | 参数量 | 中文能力 | 部署方式 | 适用场景 |
|------|--------|----------|----------|----------|
| Qwen-VL-Chat | 7B | ★★★★★ | 本地/API | 商品描述、属性提取 |
| InternVL2 | 1-76B | ★★★★ | 本地 | 细粒度商品理解 |
| GPT-4V | - | ★★★★ | API | 复杂场景理解 (贵) |
| DeepSeek-VL2 | - | ★★★★★ | API | 与 DeepSeek 生态统一（推荐） |
| Chinese-CLIP | 200M-2B | ★★★★ | 本地 | 以图搜图（轻量） |

**本项目建议**：MVP 阶段使用 Chinese-CLIP 做以图搜图（轻量本地部署），全量 M6 阶段接 DeepSeek-VL2 API 做商品图片结构化理解。

### 3.3 多模态向量检索技术选型

#### Qdrant 多模态 Collection 设计

```python
# 单 Collection 多向量方案 (Qdrant 1.9+ 支持)
collections_config = {
    "products_multimodal": {
        "vectors": {
            "text_embedding": {     # 文本描述向量 (BGE, 1024d)
                "size": 1024,
                "distance": "Cosine"
            },
            "image_embedding": {    # 商品图片向量 (CLIP, 512d)
                "size": 512,
                "distance": "Cosine"
            }
        },
        # 混合检索时指定使用哪个向量
        "search": {
            "query_text": "text_embedding",
            "query_image": "image_embedding",
            "fusion": "RRF"  # Reciprocal Rank Fusion
        }
    }
}
```

#### 混合检索流程（伪代码）
```python
async def hybrid_multimodal_search(
    query_text: str,
    query_image_base64: str | None = None,
    filters: dict | None = None,
    top_k: int = 20,
) -> list[Product]:
    
    # 1. 文本向量检索
    text_vec = await embed_text(query_text)
    text_results = await qdrant.search(
        collection="products",
        vector_name="text_embedding",
        vector=text_vec,
        query_filter=filters,
        limit=top_k * 2
    )
    
    # 2. 图片向量检索（如果有图片）
    image_results = []
    if query_image_base64:
        image_vec = await clip_embed_image(query_image_base64)
        image_results = await qdrant.search(
            collection="products",
            vector_name="image_embedding",
            vector=image_vec,
            limit=top_k
        )
    
    # 3. RRF 融合
    merged = reciprocal_rank_fusion(
        text_results, image_results, k=60
    )
    
    # 4. 重排序
    reranked = await reranker.rerank(
        query=query_text,
        documents=merged,
        top_n=top_k
    )
    
    return reranked
```

---

## 4. 前端设计模式：流式对话与渐进推荐

### 4.1 豆包 (字节跳动) 对话 UI 设计

**产品**：豆包 (Doubao)
**来源**：字节跳动
**核心设计理念**：流式优先、渐进展示、多模态入口

#### UI 设计模式
```
┌──────────────────────────────────┐
│  ← 返回    对话标题    ⋮ 更多     │  Header
├──────────────────────────────────┤
│                                  │
│  [用户气泡]                       │
│  ┌─────────────────────┐        │
│  │ 推荐一款3000以内的    │        │  User Message
│  │ 蓝牙耳机             │        │  (右对齐, 圆角)
│  └─────────────────────┘        │
│                                  │
│  [AI 气泡]                       │
│  ┌─────────────────────┐        │
│  │ 好的，为您推荐以下    │        │  AI Text (流式逐字出现)
│  │ 几款...              │        │  Markdown 渲染
│  │                      │        │
│  │ ┌───────┐ ┌───────┐ │        │  商品卡片 (文本之后延迟渲染)
│  │ │ 图 片  │ │ 图 片  │ │        │  - 图片异步加载
│  │ │ 商品A  │ │ 商品B  │ │        │  - 价格高亮
│  │ │ ¥299  │ │ ¥349  │ │        │  - 徽标 (热卖/新品)
│  │ │ 4.8★  │ │ 4.6★  │ │        │
│  │ └───────┘ └───────┘ │        │
│  │                      │        │
│  │ 需要我详细对比这两款吗?│        │  追问按钮 (Chip)
│  │ [详细对比] [再看看]   │        │
│  └─────────────────────┘        │
│                                  │
├──────────────────────────────────┤
│  🎤语音  [输入框...]  📎+  📷    │  Input Bar
└──────────────────────────────────┘
```

#### 流式输出技术栈
```
后端 SSE (Server-Sent Events):
  event: text_delta
  data: {"content": "为您", "seq": 1}

  event: text_delta
  data: {"content": "推荐", "seq": 2}

  event: text_delta
  data: {"content": "以下", "seq": 3}
  ...

  event: product_cards
  data: {"products": [{id, name, price, image_url, rating, reason}]}

  event: done
  data: {"session_id": "xxx"}
```

#### Android Compose 流式渲染实现要点

```kotlin
// 关键设计: StateFlow + 增量拼接
class ChatViewModel : ViewModel() {
    // 流式文本 - 用户看到逐字动画
    private val _streamingText = MutableStateFlow("")
    val streamingText: StateFlow<String> = _streamingText.asStateFlow()
    
    // 商品卡片 - 延迟渲染
    private val _productCards = MutableStateFlow<List<ProductCard>>(emptyList())
    val productCards: StateFlow<List<ProductCard>> = _productCards.asStateFlow()
    
    // SSE 事件处理
    fun onSseEvent(event: SseEvent) {
        when (event) {
            is SseEvent.TextDelta -> {
                _streamingText.value += event.content  // 增量拼接
            }
            is SseEvent.ProductCards -> {
                _productCards.value = event.products   // 替换整个列表
            }
            is SseEvent.Done -> {
                _isStreaming.value = false
                // 将流式文本归档到消息列表
                _messages.value += ChatMessage(...)
            }
        }
    }
}
```

#### 可借鉴到我们项目的设计
| 豆包设计 | 我们的 Android 实现 |
|----------|-------------------|
| 流式逐字渲染 | ChatViewModel._streamingText + AnnotatedString 动画 |
| 商品卡片延迟渲染 | 等 text_delta 流结束后再发送 product_cards 事件 |
| 追问 Chip 按钮 | SSE 事件中添加 `suggestions: ["详细对比", "再看看"]` |
| 多模态输入栏 | ImagePicker.kt (已规划) |
| 消息气泡样式 | MessageBubble.kt — 左对齐 AI + 右对齐用户 |

### 4.2 文心一言 (百度) 商品卡片渲染

**产品**：文心一言 App (百度)
**特色**：卡片式推荐 + "插件"生态

#### 卡片模板设计
```
┌─────────────────────────────┐
│  🏷 为您精选: 降噪耳机       │  Header
├─────────────────────────────┤
│ ┌─────────┐ ┌─────────┐    │
│ │  [图片]  │ │  [图片]  │    │  横向滚动卡片
│ │  WH-1000 │ │ AirPods │    │
│ │  ¥2499   │ │  ¥1899  │    │
│ │  ★4.8   │ │  ★4.7  │    │
│ │  [详情]  │ │  [详情]  │    │
│ └─────────┘ └─────────┘    │
├─────────────────────────────┤
│  📊 对比分析                 │  Expandable section
│  WH-1000XM5 vs AirPods Pro │
│  降噪: XM5 更优             │
│  音质: 各有千秋             │
│  ...展开...                 │
├─────────────────────────────┤
│  💬 用户口碑                │  Review snippet
│  "降噪效果真的绝了" — 99%   │
│  的用户提到降噪效果好       │
└─────────────────────────────┘
```

#### 可借鉴设计
- **横向滚动卡片**：我们的 ProductCard 可支持横向 Row + LazyRow
- **可展开的对比分析**：CompareScreen + 可折叠区域
- **评价摘要模块**：商品数据中附带评价摘要，检索后渲染

### 4.3 ChatGPT + 插件生态的导购探索

OpenAI 的 ChatGPT Plugins 虽然已转向 GPTs，但其插件生态中的购物模式值得参考：

#### 关键设计模式
1. **Function Calling → 商品搜索 API**：当用户意图被识别为购物，LLM 自动调用 `search_products` 函数
2. **Citation/References**：每个推荐附带数据来源，增强可信度
3. **Multi-turn refinement**：用户可以说"太贵了，有没有便宜的"来迭代推荐

#### 可借鉴到我们项目
- Function Calling 模式在 LangGraph 中对应 **Tool Node**
- 我们可以在 LangGraph 工作流中添加 `search_products_tool` / `compare_products_tool` 等

---

## 5. 后端架构：Pipeline 设计与 LangGraph 最佳实践

### 5.1 意图识别 → 槽位填充 → 混合检索 → 排序 → 生成 Pipeline

这是本项目核心的 backend pipeline，以下是业界成熟的设计模式和各模块的详细设计。

#### 完整 Pipeline 架构图
```
┌──────────────────────────────────────────────────────────────────┐
│                    用户输入 Query                                 │
│           "推荐一款3000以内降噪好的蓝牙耳机"                        │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  模块1: INTENT CLASSIFICATION (意图识别)                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  输入: raw_query                                           │  │
│  │  方法: LLM (prompt-based) 或 小模型 (bert-classifier)      │  │
│  │  输出: {                                                   │  │
│  │    "intent": "commodity_recommend",                        │  │
│  │    "sub_intent": "bluetooth_earphone",                     │  │
│  │    "confidence": 0.95                                      │  │
│  │  }                                                         │  │
│  │  intent 枚举:                                               │  │
│  │    commodity_recommend  — 商品推荐                          │  │
│  │    commodity_compare    — 商品对比                          │  │
│  │    commodity_detail     — 商品详情查询                      │  │
│  │    scenario_shopping    — 场景导购                          │  │
│  │    after_sales          — 售后咨询                          │  │
│  │    chitchat             — 闲聊/拒绝                         │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  模块2: SLOT FILLING (槽位填充)                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  输入: raw_query + intent                                  │  │
│  │  方法: LLM (structured output / function calling)          │  │
│  │  输出: {                                                   │  │
│  │    "category": "蓝牙耳机",                                  │  │
│  │    "price_min": 0,                                         │  │
│  │    "price_max": 3000,                                      │  │
│  │    "attributes": {"降噪": "好", "连接方式": null},          │  │
│  │    "brand_preference": null,                               │  │
│  │    "scenario": null,                                       │  │
│  │    "missing_slots": ["品牌偏好", "佩戴方式"]                 │  │
│  │  }                                                         │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │ 槽位是否完整?        │
                    └────┬──────────┬────┘
                    完整  │          │ 缺失
                         │          ▼
                         │   ┌────────────────┐
                         │   │ CLARIFICATION  │  ← 生成追问
                         │   │ "您偏好入耳式  │
                         │   │  还是头戴式?"   │
                         │   └────────────────┘
                         │          │
                         │     (等待用户回复后重新进入 pipeline)
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  模块3: HYBRID RETRIEVAL (混合检索)                               │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                                                            │  │
│  │  路径A: 向量检索 (Qdrant)                                   │  │
│  │    query_vec = embed(rewritten_query)                      │  │
│  │    results_a = qdrant.search(vector=query_vec, top_k=50)   │  │
│  │                                                            │  │
│  │  路径B: 关键词检索 (PostgreSQL full-text search)            │  │
│  │    results_b = db.execute(                                  │  │
│  │      "SELECT * FROM products WHERE to_tsvector('chinese',  │  │
│  │       name || description) @@ plainto_tsquery($1)"          │  │
│  │    )                                                        │  │
│  │                                                            │  │
│  │  路径C: 元数据过滤 (PostgreSQL WHERE)                        │  │
│  │    results_c = db.query(Product)                            │  │
│  │      .filter(Product.category == slots.category)            │  │
│  │      .filter(Product.price.between(slots.price_range))      │  │
│  │                                                            │  │
│  │  融合: Reciprocal Rank Fusion (RRF)                        │  │
│  │    score_rrf = Σ 1/(k + rank_i)  for each path i           │  │
│  │    → merged_results (top 100)                              │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  模块4: RERANKING (重排序)                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  阶段1: Cross-Encoder 重排序                                │  │
│  │    对 Top100 → BGE-Reranker-v2-m3 → Top20                  │  │
│  │                                                            │  │
│  │  阶段2: 业务规则排序                                        │  │
│  │    score = 0.4 × semantic_match                            │  │
│  │          + 0.2 × price_score (越贴近预算越高)               │  │
│  │          + 0.15 × rating_score                              │  │
│  │          + 0.15 × sales_volume_score                        │  │
│  │          + 0.10 × diversity_bonus (避免同品牌扎堆)          │  │
│  │    → Top5                                                │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  模块5: GENERATION (生成回答)                                    │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Prompt 模板:                                               │  │
│  │  ┌─────────────────────────────────────────────────────┐   │  │
│  │  │ System: 你是专业电商导购，基于商品数据回答。          │   │  │
│  │  │         - 推荐理由必须基于检索到的商品描述           │   │  │
│  │  │         - 禁止虚构不存在的商品属性                   │   │  │
│  │  │         - 每个推荐附带简要理由                       │   │  │
│  │  │         - 如果信息不足，诚实告知并建议追问           │   │  │
│  │  │                                                     │   │  │
│  │  │ Context: {retrieved_chunks}                          │   │  │
│  │  │                                                     │   │  │
│  │  │ 用户需求: {query}                                    │   │  │
│  │  │ 槽位信息: {slots}                                    │   │  │
│  │  │ 候选商品 Top5: {ranked_products}                     │   │  │
│  │  └─────────────────────────────────────────────────────┘   │  │
│  │                                                            │  │
│  │  生成方式: 流式 (SSE) → 逐token推送给前端                    │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

#### 模块间通信格式（统一 Schema）
```python
# services/intent.py
class IntentResult:
    intent: str            # commodity_recommend | commodity_compare | ...
    sub_intent: str | None
    confidence: float
    rewrites: list[str]    # 查询改写候选

# services/intent.py (Slot Filling)
class SlotResult:
    category: str | None
    price_min: float | None
    price_max: float | None
    attributes: dict[str, str]  # {"降噪": "好", "颜色": "黑色"}
    brand_preference: str | None
    missing_slots: list[str]     # 缺失的关键槽位

# services/retriever.py
class RetrievalResult:
    product_id: str
    score: float
    source: str            # "vector" | "keyword" | "metadata"
    chunk_text: str

# services/product_ranker.py
class RankedProduct:
    product: Product
    final_score: float
    match_reason: str      # "价格在预算范围内，降噪评分4.8"
```

### 5.2 LangGraph 在电商场景的最佳实践

#### StateGraph 工作流设计

```
                ┌─────────┐
                │  START  │
                └────┬────┘
                     │
                     ▼
              ┌──────────────┐
              │ class_intent │  意图分类
              │   (Intent)   │
              └──────┬───────┘
                     │
          ┌──────────┼──────────┐
          │          │          │
   commodity    scenario   chitchat/
   _recommend   _shopping  after_sales
          │          │          │
          ▼          ▼          ▼
    ┌──────────┐ ┌───────┐ ┌────────┐
    │ extract  │ │expand │ │ simple │
    │ _slots   │ │scene  │ │ answer │
    └────┬─────┘ └───┬───┘ └───┬────┘
         │            │         │
         ▼            │         │
   ┌───────────┐     │         │
   │ check_slots│     │         │
   │ _complete  │     │         │
   └──┬─────┬──┘     │         │
      │     │        │         │
  完整 │     │ 缺失   │         │
      │     ▼        │         │
      │  ┌────────┐  │         │
      │  │clarify │  │         │
      │  │_slots  │──┼─────────┤  ← 返回用户追问
      │  └────────┘  │         │
      │              │         │
      ▼              │         │
   ┌──────────┐     │         │
   │ retrieve │     │         │
   └────┬─────┘     │         │
        │           │         │
        ▼           │         │
   ┌──────────┐     │         │
   │  rank    │     │         │
   └────┬─────┘     │         │
        │           │         │
        ▼           │         │
   ┌──────────┐     │         │
   │ generate │◄────┼─────────┘
   └────┬─────┘
        │
        ▼
   ┌──────────┐
   │  END     │
   └──────────┘
```

#### LangGraph 代码实现要点（对本项目 agent.py 的建议）

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver  # 持久化多轮

class AgentState(TypedDict):
    # 输入
    query: str
    session_id: str
    conversation_history: list[dict]
    
    # 中间状态
    intent: str
    slots: SlotResult
    need_clarify: bool
    clarify_question: str
    
    # 检索结果
    retrieved_chunks: list[RetrievalResult]
    ranked_products: list[RankedProduct]
    knowledge_context: list[str]
    
    # 输出
    response: str
    product_cards: list[ProductCard]

def build_agent_graph():
    workflow = StateGraph(AgentState)
    
    # 添加节点
    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("extract_slots", extract_slots_node)
    workflow.add_node("check_slots", check_slots_node)
    workflow.add_node("clarify", clarify_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("rank", rank_node)
    workflow.add_node("generate", generate_node)
    
    # 条件路由（核心）
    workflow.set_entry_point("classify_intent")
    workflow.add_edge("classify_intent", "extract_slots")
    workflow.add_edge("extract_slots", "check_slots")
    
    workflow.add_conditional_edges(
        "check_slots",
        lambda state: "clarify" if state["need_clarify"] else "retrieve",
        {"clarify": "clarify", "retrieve": "retrieve"}
    )
    
    workflow.add_edge("clarify", END)  # 追问后结束，等用户回复
    workflow.add_edge("retrieve", "rank")
    workflow.add_edge("rank", "generate")
    workflow.add_edge("generate", END)
    
    # 启用多轮记忆（SQLite checkpoint）
    memory = SqliteSaver.from_conn_string(":memory:")  # 或 PostgreSQL
    return workflow.compile(checkpointer=memory)
```

#### LangGraph 最佳实践总结

| 实践 | 说明 |
|------|------|
| **条件路由 > 固定流程** | 用 conditional_edges 根据 intent 分流，避免一大坨 if/else |
| **Checkpointer 做多轮记忆** | SqliteSaver（开发）/ PostgresSaver（生产），自动管理对话状态 |
| **节点粒度为单步骤** | 每个节点只做一件事（分类/提取/检索/排序/生成），易于测试和 debug |
| **流式输出用 `.astream()`** | 支持 token-level streaming，每个 token 触发一次 yield |
| **Human-in-the-loop** | `interrupt_before=["clarify"]` 支持在追问前人工审核 |
| **工具节点 (ToolNode)** | 将商品搜索/对比/下单包装为 Tool，LLM 可自主决策调用 |

### 5.3 LlamaIndex + Qdrant 混合检索工程经验

#### LlamaIndex 在电商 RAG 中的最佳实践

```python
from llama_index.core import VectorStoreIndex, Settings
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.postprocessor import SentenceTransformerRerank

# 1. Embedding 模型设置
Settings.embed_model = HuggingFaceEmbedding(
    model_name="BAAI/bge-large-zh-v1.5",
    device="cpu",  # 或 "cuda"
)

# 2. Qdrant 连接
vector_store = QdrantVectorStore(
    collection_name="products",
    url="http://localhost:6333",
)

# 3. 创建索引
index = VectorStoreIndex.from_vector_store(vector_store)

# 4. 混合检索：向量 + BM25 融合
vector_retriever = index.as_retriever(similarity_top_k=20)
bm25_retriever = BM25Retriever.from_defaults(
    nodes=nodes, similarity_top_k=20
)

fusion_retriever = QueryFusionRetriever(
    retrievers=[vector_retriever, bm25_retriever],
    num_queries=3,           # 生成3个查询变体
    similarity_top_k=50,
    mode="reciprocal_rerank", # RRF 融合
)

# 5. 重排序
reranker = SentenceTransformerRerank(
    model="BAAI/bge-reranker-v2-m3",
    top_n=10,
)

# 6. 完整检索 pipeline
query_engine = index.as_query_engine(
    retriever=fusion_retriever,
    node_postprocessors=[reranker],
    response_mode="compact",  # 或 "tree_summarize" 用于长上下文
)
```

#### 产线化注意事项
1. **Embedding 缓存**：对高频query做embedding cache，减少重复计算
2. **异步批量检索**：`asyncio.gather` 并行执行向量检索 + 关键词检索
3. **Qdrant 的 collection 别名**：用 `products_v1`→`products` 别名实现零停机更新
4. **监控检索质量**：记录每次检索的 `score` 分布，检测 drift

---

## 6. 评测体系：RAGAS 适配与人工评估

### 6.1 RAGAS 指标在电商导购的适配

> RAGAS (Retrieval Augmented Generation Assessment)
> 论文: https://arxiv.org/abs/2309.15217

#### RAGAS 核心指标在电商场景的适配

| 指标 | RAGAS 原始定义 | 电商导购适配 | 计算方法 |
|------|---------------|-------------|---------|
| **Context Precision** | 检索到的上下文中有多少与问题相关 | 检索商品中，有多少真正满足用户需求 | TP / (TP + FP)，需人工标注 ground truth |
| **Context Recall** | 回答是否覆盖了所有必要上下文 | 推荐是否覆盖了用户需求的全部维度（价格/功能/品牌） | 按维度打分后平均 |
| **Faithfulness** | 回答是否忠实于检索上下文（不幻觉） | 推荐理由是否基于商品实际描述（不编造功能） | 逐句检查是否可追溯到商品数据 |
| **Answer Relevancy** | 回答是否直接回应问题 | 推荐是否切题（不求全，但求准） | LLM-as-Judge 打分 |
| **Answer Correctness** | 回答中事实的正确性 | 商品价格/参数是否与数据库一致 | 精确匹配 / 近似匹配 |
| **Aspect Critique** | 按维度分析回答质量 | 按"价格匹配度""质量匹配度""品牌匹配度"评分 | 人工 + LLM 联合 |

#### 新增电商专属评测指标

| 指标 | 定义 | 评估方式 |
|------|------|---------|
| **Recommendation Diversity** | Top5 推荐的商品品牌/价格段是否多样化 | 计算推荐列表的品牌/价格熵 |
| **Price Sensitivity** | 推荐商品价格是否尊重用户预算约束 | 超出预算的商品数/比例 |
| **Justification Quality** | 每条推荐的推荐理由是否具体、有说服力 | LLM-as-Judge 1-5分 |
| **Multi-turn Consistency** | 多轮对话中是否记住用户偏好、不前后矛盾 | 跨轮对比用户的偏好记录 |
| **Clarification Effectiveness** | 追问是否精准命中缺失的槽位 | 是否在1-2轮追问后完整填充所有槽位 |

#### 评测数据集设计
```json
{
  "test_case_id": "shop_001",
  "query": "想买个500以内的运动耳机",
  "expected_intent": "commodity_recommend",
  "expected_slots": {
    "category": "运动耳机",
    "price_max": 500
  },
  "expected_products": ["prod_01", "prod_03"],  // 标注者认为的最佳推荐
  "min_acceptable_products": 3,                 // 最少推荐数
  "forbidden_products": ["prod_05"],            // 不应推荐（如超预算）
  "quality_rubric": {
    "price_compliance": 5,                       // 价格合规 1-5
    "category_match": 5,                         // 品类匹配
    "justification_quality": 4                   // 推荐理由质量
  }
}
```

### 6.2 电商导购人工评估标准

#### 人工评估维度（1-5 分）

| 维度 | 1分 | 3分 | 5分 |
|------|-----|-----|-----|
| **意图理解** | 完全误解用户需求 | 基本理解，但有偏差 | 精确理解隐含需求（如"送女朋友"→推荐精致外观） |
| **推荐准确性** | 推荐商品与需求无关 | 部分相关但不精准 | 推荐精准，符合所有约束条件 |
| **推荐理由** | 无理由或模板化 | 有理由但泛泛 | 理由具体，引用了商品真实参数/评价 |
| **信息真实性** | 有幻觉/编造 | 基本真实但含糊 | 完全基于数据，可追溯 |
| **交互流畅性** | 多轮不连贯 | 基本连贯但生硬 | 自然流畅，追问恰到好处 |
| **多样性** | 单一品牌/风格 | 有变化但不明显 | 品牌/价格/风格层次丰富 |

#### 评估流程
```
1. 评测数据集准备 (20+ cases, 覆盖5大意图类型)
2. 自动评测 (RAGAS 指标 + 程序化检查)
3. 抽样人工评测 (每类抽3-5条, 3人交叉评分, 取 ICC)
4. 问题归因:
   - 检索问题 → 调整 retriever 参数
   - 排序问题 → 调整 ranker 权重
   - 生成问题 → 优化 prompt / 幻觉控制
   - 意图问题 → 补充 few-shot examples
5. 回归测试 → 确保修复不改坏已有case
```

---

## 7. 对我们项目 (04-rag-ecommerce) 的具体设计建议

### 7.1 当前架构与业界对齐情况

| 模块 | 当前状态 | 业界参考 | 差距与建议 |
|------|---------|---------|-----------|
| **agent.py** | 全功能实现（LangGraph 7 个显式主节点 + 条件路由，3000+ 行） | 淘宝问问 pipeline / LangGraph 最佳实践 | ✅ 9/9 场景完成 |
| **intent.py** | 规划中 | 京东意图分类体系 | 建议定义6类 intent + slot schema |
| **retriever.py** | 规划中 | Qdrant 混合检索 + RRF 融合 | 建议 MVP 先做向量检索，后续加 BM25 |
| **reranker.py** | 全量 M9 | BGE-Reranker-v2-m3 | MVP 可先跳过，直接取 Top-N |
| **product_ranker.py** | 规划中 | 多维加权排序公式 | 建议权重可配置 |
| **state_manager.py** | 规划中 | LangGraph Checkpointer | MVP 用内存储存，生产切 PostgreSQL |
| **image_parser.py** | 全量 M6 | Chinese-CLIP + VLM | MVP 可先支持以图搜图 |
| **evaluator.py** | 全量 M8 | RAGAS + 自定义指标 | 建议先积累评测用例 |

### 7.2 推荐实施路径（MVP 优先）

```
M2-M3 (当前→45%): 核心 Pipeline 打通
  ├── 实现 intent + slot_filling (LLM prompt-based)
  ├── 实现 retriever (Qdrant 向量检索)
  ├── 实现 agent 完整工作流 (classify→extract→retrieve→rank→generate)
  └── SSE 流式输出完整链路

M4-M5 (45%→90%): 对话闭环
  ├── state_manager 多轮状态
  ├── product_ranker 多维排序
  ├── clarification 追问机制
  └── Android ProductCard 渲染

M6-M10 (90%→100%): 全量增强
  ├── 多模态（以图搜图 + VLM）
  ├── 商品对比（comparator）
  ├── 评测闭环（evaluator + RAGAS）
  └── 知识迭代（knowledge ingestion）
```

### 7.3 关键技术选型确认

| 技术选型 | 推荐方案 | 理由 |
|---------|---------|------|
| Embedding 模型 | BAAI/bge-large-zh-v1.5 (1024d) | 已采用，中文 SOTA |
| Reranker | BAAI/bge-reranker-v2-m3 | 中文最优，支持 cross-encoder |
| VLM | DeepSeek-VL2 (API) / Chinese-CLIP (本地) | 与 LLM 生态统一 / 轻量 |
| Agent 框架 | LangGraph (StateGraph) | 已采用，状态图模式最适合多步骤决策 |
| RAG 框架 | Qdrant (native Python client) | 直接调用 Qdrant API，无中间层 |
| 多轮记忆 | LangGraph Checkpointer (PostgreSQL) | 与现有 PG 统一，无需额外组件 |
| 评测框架 | RAGAS + 自定义指标 | 业界标准 + 电商专属扩展 |

### 7.4 给 agent.py 的具体实现建议

当前 agent.py 是 stub，建议按以下结构演进：

```python
# services/agent.py 演进计划

# Phase 1 (M2-M3): 线性 Pipeline
async def generate_response(query, session_id):
    intent = await classify_intent(query)
    slots = await extract_slots(query, intent)
    if slots.missing:
        return await generate_clarification(slots.missing)
    chunks = await hybrid_retrieve(slots)
    ranked = await rank_products(chunks)
    async for token in stream_generate(ranked):
        yield token

# Phase 2 (M4-M5): LangGraph StateGraph
# 使用 StateGraph + conditional_edges 替代线性 if/else
# 启用 Checkpointer 实现多轮

# Phase 3 (M6-M10): Tool-augmented Agent
# 添加 ToolNode: search_products, compare, check_inventory
# LLM 自主决策调用工具
```

---

## 8. 参考链接与延伸阅读

### 8.1 产品参考
- 淘宝问问: 淘宝 App → 搜索 → AI 助手
- 京东京言: 京东 App → 搜索 → AI 购物助手
- Amazon Rufus: Amazon App → 搜索栏 AI 图标
- Shopify Sidekick: https://www.shopify.com/magic
- 豆包: https://www.doubao.com
- 文心一言: https://yiyan.baidu.com

### 8.2 技术参考
- RAGAS: https://docs.ragas.io/ / 论文 arXiv:2309.15217
- LangGraph: https://langchain-ai.github.io/langgraph/
- LlamaIndex + Qdrant: https://docs.llamaindex.ai/en/stable/examples/vector_stores/QdrantIndexDemo/
- Qdrant Multimodal: https://qdrant.tech/documentation/concepts/vectors/#multivectors
- BGE Embedding: https://huggingface.co/BAAI/bge-large-zh-v1.5
- BGE Reranker: https://huggingface.co/BAAI/bge-reranker-v2-m3
- Chinese-CLIP: https://github.com/OFA-Sys/Chinese-CLIP

### 8.3 论文参考
- "RAGAS: Automated Evaluation of Retrieval Augmented Generation" (2023)
- "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection" (2023)
- "CRAG: Corrective Retrieval Augmented Generation" (2024)
- "Shopping MMLU: A Benchmark for Evaluating LLMs as Shopping Assistants" (eBay, 2024)

---

> **文档维护**：本文档应随着竞品更新和技术迭代持续补充。每次阅读行业新动态后，在此文档中追加对应章节。
