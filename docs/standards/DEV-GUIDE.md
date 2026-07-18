# 电商AI导购Agent — 开发总纲 DEV-GUIDE v3.2

> **⚠️ 辅助文档** - 开发权威入口为 [`DEV-CONTROL.md`](../DEV-CONTROL.md)，如有冲突以权威文档为准。
>
> 本文档 = PRD + 竞品分析 + 架构分析 + 创新调研 + UI设计 的压缩版  
> 每次编码前必读。  
> **新手入门**：先看 `docs/standards/SETUP.md` 从零搭建环境。

---

## 一、系统目标

```
"意图理解 → 智能咨询 → 决策辅助 → 交易执行" 全链路闭环

Android(Kotlin/Compose) ← SSE → FastAPI ← LangGraph → pgvector/PostgreSQL → Doubao
```

**9 级场景覆盖**：单轮推荐 → 条件筛选 → 多轮追问 → 对比决策 → 主动反问 → 反选排除 → 场景化组合 → 购物车下单 → 拍照找货

---

## 二、技术栈

| 层 | 技术 | 备注 |
|----|------|------|
| 客户端 | Android Kotlin + Jetpack Compose | 原生，不接受 Web |
| 后端 | FastAPI + Uvicorn | |
| Agent | LangGraph StateGraph | |
| RAG | pgvector + SQLAlchemy | LlamaIndex 未实际使用 |
| 数据库 | PostgreSQL + pgvector | |
| LLM | **Doubao-Seed-2.0-lite** ✅ 已验证 | DeepSeek 保留降级 |
| Embedding | BGE-large-zh-v1.5 | 中文电商领域 SOTA |

### Doubao API

```
Base: https://ark.cn-beijing.volces.com/api/v3/
Model: ep-20260514111645-lmgt2
Key:  见 apps/backend/.env (DOUBAO_API_KEY)
Limit: TPM 800K, RPM 700
```

---

## 三、架构设计

```
LangGraph StateGraph (7 节点 — 全部已实现):

  START
    ↓
  classify_intent   → 9类意图 + 否定条件检测
    ↓
  [missing_slots? → clarify] → 主动追问 (已实现)
    ↓
  retrieve          → pgvector向量检索 + 否定排除 + 场景多类目并行
    ↓
  [rank + validate] → ProductRanker 5维加权 + _validate_ranked_products
    ↓
  generate          → SSE stream: progress → text_delta → product_cards → done
    ↓
  [cart 分支]       → 购物车CRUD + 2步下单确认 (已实现)
    ↓
  [vision 分支]     → VLM图像理解 → 相似商品检索 (已实现)
    ↓
  END
```

---

## 四、代码级创新约束

### 4.1 否定语义处理（场景6 — 核心功能）
```
必须: intent 检测否定关键词: "不要"、"除了"、"非"、"不含"、"拒绝"
必须: extract_slots 输出 exclude_attributes: ["含酒精", "日系品牌"]
必须: retriever 排除命中 exclude_attributes 的商品
```

### 4.2 Agent 主动反问（场景5 — 进阶功能）
```
必须: 信息不足时 (missing_slots非空) 主动追问
必须: clarify 节点输出引导性问题 (如"拍照、续航还是性价比？")
禁止: 信息不足时强行推荐
```

### 4.3 条件筛选（场景2 — 基础功能）
```
必须: 结构化参数提取 (price_range, brand, category)
必须: retriever metadata 范围过滤
必须: 整合同类商品按条件排序
```

### 4.4 购物车 CRUD（场景8 — 扩展功能，非阻塞）

> ⚠️ 扩展功能目标，不影响场景 1-5 交付。

```
扩展功能: 识别 cart_add/cart_remove/cart_modify/cart_checkout 意图
扩展功能: 维护 session 级购物车状态
扩展功能: 客户端实时展示购物车数量/状态
```

### 4.5 agent.py → generate_node (v0.3.1 交错输出)
```
输出格式: [SUMMARY] → [PRODUCT_1] 商品名/匹配度/三段理由 → [PRODUCT_2] → [PRODUCT_3] → [CLOSING]
SSE 推送: progress → (text_delta + product_cards) × N → closing_text → done
每商品: 第1行=商品全名, 第2行=综合匹配度, ①②③ 三段理由
禁止: "为您推荐以下几款：1. xxx 2. xxx 3. xxx"
禁止: 编造不存在的优惠券/功能/价格（项目红线）
缓存: 内存 LRU + CACHE_VERSION 版本校验自动过期 + 启动清空 + API 清空端点
```

### 4.6 intent.py → classify_intent
```
必须: LLM prompt-based 分类 (9类: recommend/filter/multiturn/compare/clarify/anti_select/scenario/cart/image)
必须: 否定条件检测 ("不要"/"除了"/"非")
必须: 信息不足时主动追问 (missing_slots → clarify)
```

### 4.7 性能要求
```
首 Token < 1s (Prompt压缩 + 流水线并行)
SSE 流式速率 ≥ 20 tokens/s
检索延迟 < 2s
```

---

## 五、评测指标

| 维度 | 权重 | 指标 |
|------|:---:|------|
| 基础功能完整性 | 35% | 9场景中至少场景1-5跑通 |
| 工程质量 | 25% | 代码结构清晰、错误处理完善、文档齐全 |
| 效果与可靠性 | 20% | 无幻觉、检索准确、流畅美观 |
| 扩展功能深度 | 20% | 购物车/多模态/性能优化/否定语义 |

---

## 六、绝对禁止

```
❌ 编造不存在的优惠券/功能/价格（项目红线）
❌ 用纯 Web/H5 客户端
❌ 泄露 API Key（GitHub 提交前检查 .gitignore）
❌ 忽略否定语义（"不要""除了""非"）
❌ Demo 无法正常运行或需要大量手动配置
❌ 代码完全依赖 AI 生成而无法解释原理（质量红线）
❌ generate_node 输出纯列表
❌ intent 只用品类规则
❌ slots 不全时强行推荐
❌ 一次性生成 >3 个文件的代码
```

---

## 七、模型下载指南

项目依赖 2 个 HuggingFace 模型，**不在 Git 仓库中**（~3.5GB），需要每位开发者自行下载一次。

### 7.1 模型清单

| 模型 | 用途 | 大小 | 加载代码 | 无模型时行为 |
|------|------|:--:|------|------|
| `BAAI/bge-large-zh-v1.5` | Embedding 向量化 | ~1.3GB | `embedding.py` | **报错退出**（`local_files_only=True`） |
| `BAAI/bge-reranker-v2-m3` | Cross-Encoder 精排 | ~2.2GB | `reranker.py` | 降级为原始分数排序 |

### 7.2 缓存位置

```
~/.cache/huggingface/hub/
├── models--BAAI--bge-large-zh-v1.5/
│   └── snapshots/<hash>/    ← Embedding 模型文件
└── models--BAAI--bge-reranker-v2-m3/
    └── snapshots/<hash>/    ← Reranker 模型文件
```

### 7.3 下载命令

```bash
# 激活项目虚拟环境
source ~/.hermes-venv/bin/activate

# 下载 Embedding 模型（必须先下载，否则后端启动报错）
python -c "
from sentence_transformers import SentenceTransformer
m = SentenceTransformer('BAAI/bge-large-zh-v1.5')
print('Embedding model downloaded, dim =', m.get_sentence_embedding_dimension())
"

# 下载 Reranker 模型（可选，无模型时自动降级）
python -c "
from sentence_transformers import CrossEncoder
m = CrossEncoder('BAAI/bge-reranker-v2-m3')
print('Reranker model downloaded')
"
```

### 7.4 验证下载成功

```bash
python -c "
from sentence_transformers import SentenceTransformer, CrossEncoder
# Embedding: 必须成功
m1 = SentenceTransformer('BAAI/bge-large-zh-v1.5', local_files_only=True)
print('Embedding OK, dim =', m1.get_sentence_embedding_dimension())
# Reranker: 必须成功
m2 = CrossEncoder('BAAI/bge-reranker-v2-m3')
print('Reranker OK')
"
```

> 如果 `local_files_only=True` 报 `LocalEntryNotFoundError`，说明模型未正确下载，重新执行 7.3 的下载命令。

### 7.5 离线环境迁移

如果另一台机器无法访问 HuggingFace，可从已下载的机器复制缓存目录：

```bash
# 源机器：打包缓存
tar -czf huggingface-models.tar.gz \
  ~/.cache/huggingface/hub/models--BAAI--bge-large-zh-v1.5 \
  ~/.cache/huggingface/hub/models--BAAI--bge-reranker-v2-m3

# 目标机器：解压到相同位置
tar -xzf huggingface-models.tar.gz -C ~/
```

---

## 八、模块完成度现状

> 更新：2026-07-18（模块化重构后）

| 模块 | 完成度 | 备注 |
|------|:---:|------|
| agent.py (facade) | 95% | 838行 facade + generate_response + node_cart + route_after_intent |
| agent_nodes/ (7节点) | 95% | classify/clarify/retrieve/generate/compare/web_search 已模块化 |
| slot_management.py | 90% | 品类推断 + 槽位合并 + 否定过滤（453行，最高 fan-in） |
| cart_nlp.py | 95% | 购物车 NLP 解析（425行纯正则，14函数） |
| llm/ (Strategy+Factory) | 95% | LLMProvider 接口 + Doubao/DeepSeek/Mimo 自动检测 |
| comparison/ (Template Method) | 95% | ComparisonPipeline + WinnerStrategy 4实现 |
| core/cache/ (Protocol) | 95% | CacheBackend + InMemoryCache(LRU+TTL) + NoOpCache + QueryCache |
| intent.py | 90% | 9类意图 + 否定检测 + 槽位提取 |
| retriever.py | 95% | pgvector hybrid + 否定排除 + DB 错误兜底 |
| reranker.py | 90% | BGE-Reranker-v2-m3 + 冷却重试（300s） |
| product_ranker.py | 90% | 5维加权排序 |
| image_parser.py | 85% | VLM 图像理解 + 结构化输出 |
| cart_service.py | 90% | PostgreSQL 持久化 + FOR UPDATE 竞态修复 |
| state_manager.py | 90% | Session 状态 + 上下文递进 |
| chat.py | 100% | SSE 流式 + 全事件类型 |
| upload.py | 95% | 图片上传 + vision-search + content-type 校验 |
| schemas/ (15文件) | 95% | 内联 BaseModel 已全部提取 + 字段约束 |
| LLM | 100% | Doubao 主路 + DeepSeek/Mimo 快路 + 统一 _execute_completion |
| Android 前端 | 90% | 4页面 + SSE + ApiClient.kt 集中调用 + DemoMode |

---

> 详细展开: 参见 `docs/standards/DEV-CONTROL.md`
> 进度跟踪: `docs/progress/开发进度控制表.md`
