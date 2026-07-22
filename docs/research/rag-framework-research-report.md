# RAG 框架与文档存储方案调研报告

> 针对「中文电商智能导购 Agent」项目（287 条商品 / 94 品类 / FastAPI + LangGraph + Qdrant）
> 调研日期：2026-07-17 | 资料来源：GitHub 官方仓库、技术文档、社区评测

---

## 目录

1. [当前项目架构分析](#1-当前项目架构分析)
2. [RAG 框架对比](#2-rag-框架对比)
3. [向量库对比](#3-向量库对比)
4. [文档/知识存储格式](#4-文档知识存储格式)
5. [小数据量电商场景策略](#5-小数据量电商场景策略)
6. [最终建议与行动方案](#6-最终建议与行动方案)

---

## 1. 当前项目架构分析

### 1.1 RAG Pipeline 完整数据流

```
用户查询
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│ node_classify_intent (agent.py)                              │
│   ├── 短查询扩展 (≤6字 -> LLM 展开关键词)                      │
│   ├── classify_intent (LLM 意图分类)                          │
│   ├── extract_slots (LLM 槽位提取: category/price/brand...)  │
│   ├── extract_negation_slots (否定语义: 不要/除了/非...)      │
│   ├── 品类别名映射 (_CATEGORY_ALIASES, retriever.py:15-31)  │
│   └── rewrite_query (查询改写)                                │
├─────────────────────────────────────────────────────────────┤
│ node_clarify (条件触发)                                      │
│   └── 缺失关键信息时生成追问                                  │
├─────────────────────────────────────────────────────────────┤
│ node_retrieve (agent.py:438-550)                             │
│   ├── rag_retrieve (rag.py)                                  │
│   │   ├── embed_text (embedding.py)                          │
│   │   │   └── BGE-large-zh-v1.5 (1024-dim, CPU, 本地)        │
│   │   ├── hybrid_search (retriever.py:56-167)               │
│   │   │   ├── Qdrant query_points (dense + keyword RRF)     │
│   │   │   ├── Filter: must (category, price)                │
│   │   │   └── Filter: must_not (exclude_brands, cats, attrs)│
│   │   └── 分级回退: cat+price -> cat only -> no cat          │
│   ├── 场景化: map_scenario -> 多品类检索 -> 品类感知预采样    │
│   ├── _filter_chunks_by_requested_category (品类守卫)        │
│   ├── _filter_chunks_by_exclusions (硬排除过滤)              │
│   ├── 文本级兜底过滤 (exclude_text_terms)                    │
│   └── rerank_async (reranker.py)                             │
│       └── BGE-Reranker-v2-m3 CrossEncoder (sigmoid归一化)    │
├─────────────────────────────────────────────────────────────┤
│ rank_products (product_ranker.py)                            │
│   └── 多维加权: semantic(0.4) + price(0.2) + rating(0.15)  │
│                + brand(0.1) + attributes(0.15)              │
│   └── 意图感知权重矩阵 (6种意图, 不同权重)                   │
├─────────────────────────────────────────────────────────────┤
│ node_generate (LLM 生成推荐回复, SSE stream)                  │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 当前实现质量评估

| 维度 | 评分 | 说明 |
|------|:----:|------|
| **检索架构** | ★★★★☆ | Hybrid search (dense+keyword RRF) + CrossEncoder rerank + 多维加权，架构完整 |
| **中文适配** | ★★★★★ | BGE-large-zh + 品类别名映射 + 否定语义 + 场景化映射，中文电商适配优秀 |
| **工程化** | ★★★★☆ | 懒加载/单例/异步/降级回退/日志完善，生产级质量 |
| **可维护性** | ★★★☆☆ | 自研 pipeline 高度定制化，与业务逻辑耦合较深 |
| **可扩展性** | ★★★☆☆ | 增加新检索策略需修改核心代码，缺少抽象层 |

### 1.3 关键文件清单

| 文件 | 行数 | 职责 |
|------|------|------|
| `app/services/agent.py` | 1180+ | LangGraph StateGraph 编排，意图分类/槽位/检索/生成 |
| `app/services/retriever.py` | 218 | Qdrant hybrid search + 元数据过滤 + 否定排除 |
| `app/services/reranker.py` | 151 | BGE-Reranker CrossEncoder 精排 |
| `app/services/product_ranker.py` | 270 | 多维加权商品排序（意图感知权重矩阵） |
| `app/services/embedding.py` | 60 | BGE-large-zh 向量化 |
| `app/services/rag.py` | 84 | RAG 编排入口 + 分级回退 |
| `app/services/ingestion.py` | 126 | 文档/商品入库 Qdrant |
| `app/core/config.py` | 83 | 全局配置 |

### 1.4 当前依赖（requirements.txt 关键项）

```python
# 已使用的框架
langgraph==1.2.2           # Agent 编排（StateGraph）
langchain==1.3.2           # LangChain 基础库（未深度使用 RAG 模块）
langchain-openai==1.2.2    # OpenAI 兼容 LLM 接口

# RAG 核心组件（直接调用原生客户端，未使用 llama-index）
qdrant-client==1.18.0      # Qdrant 向量库
sentence-transformers==3.4.1  # BGE embedding + reranker
torch==2.12.0              # PyTorch 推理后端

# 数据库
pgvector>=0.3.0,<0.4.0    # 已安装但未作为主向量库
sqlalchemy[asyncio]==2.0.36
```

> **关键发现**：项目注释明确写着「直接调用 Qdrant 原生客户端，未使用 llama-index」。`pgvector` 已在依赖中但未作为主向量库使用。

---

## 2. RAG 框架对比

### 2.1 框架总览（2026年7月数据）

| 框架 | GitHub Stars | 最新版本 | 语言 | 定位 | 架构 |
|------|:----------:|:--------:|------|------|------|
| **LlamaIndex** | 50.9k | v0.14.23 | Python | 数据框架 + RAG | 文档为中心，索引/查询引擎 |
| **LangChain** | 142k | core 1.4.9 | Python | LLM 应用框架 | 链式组合，组件生态 |
| **Haystack** | 25.9k | v2.31.0 | Python | RAG 专用框架 | Pipeline 管道设计 |
| **RAGFlow** | 85.2k | v0.26.4 | Go+Python | 完整 RAG 引擎 | 全栈方案（Docker 部署） |
| **自研** | - | - | - | 高度定制 | 直接调用原生客户端 |

### 2.2 详细对比

#### LlamaIndex

```
定位：以数据为中心的 RAG 框架，擅长文档索引与查询
仓库：github.com/run-llama/llama_index (50.9k stars, 7.8k forks)
最新：v0.14.23 (2026-06-24)，7,857 commits，活跃维护
```

| 维度 | 评估 |
|------|------|
| **中文支持** | ★★★☆☆ 内置支持 HuggingFace embedding（包括 BGE），但中文分块/解析需自定义 |
| **Qdrant 集成** | ★★★★★ 官方 `llama-index-vector-stores-qdrant` 包，一等公民支持 |
| **LangGraph 兼容** | ★★★☆☆ 可共存但架构理念不同，LlamaIndex 有自己的 Workflows/Agent 体系 |
| **Hybrid Search** | ★★★★☆ 支持 `QueryFusionRetriever` 合并 dense+sparse，但不如 Qdrant 原生 RRF 灵活 |
| **自定义 Reranker** | ★★★★★ `BaseNodePostprocessor` 接口，可包装 CrossEncoder |
| **小数据量适配** | ★★★★☆ `VectorStoreIndex` 内存模式无需独立服务，适合小规模 |
| **学习成本** | ★★★☆☆ 模块化设计但有概念门槛（Document/Node/Index/Retriever/QueryEngine） |
| **迁移代价** | ★★☆☆☆ 需要将现有 retriever/reranker/ranker 包装为 LlamaIndex 组件 |

**LlamaIndex 核心优势**：
- 300+ 集成包（LlamaHub），覆盖主流向量库/LLM/embedding
- LlamaParse：130+ 格式的文档解析/OCR
- 成熟的查询引擎抽象：`SubQuestionQueryEngine`、`RouterQueryEngine`
- 内置评估工具

**对本项目的适配性**：
- ✅ 与 BGE embedding + Qdrant 天然兼容
- ✅ 可包装现有 CrossEncoder 为 NodePostprocessor
- ⚠️ 与 LangGraph 存在架构理念冲突（LlamaIndex 有自己的 Agent/Workflow）
- ⚠️ 自定义品类别名映射/否定语义过滤需要 hack 检索管道
- ❌ 迁移后丧失对检索细节的精细控制（分级回退、品类守卫、场景化预采样）

#### LangChain

```
定位：LLM 应用工程平台，组件化组合
仓库：github.com/langchain-ai/langchain (142k stars, 23.6k forks)
最新：langchain-core 1.4.9 (2026-07-08)，16,428 commits
```

| 维度 | 评估 |
|------|------|
| **中文支持** | ★★★☆☆ 依赖外部 embedding/分词器，框架本身不提供中文能力 |
| **Qdrant 集成** | ★★★★★ `langchain-qdrant` 包，成熟的 VectorStore 抽象 |
| **LangGraph 兼容** | ★★★★★ 同一生态体系，天然集成（项目已在使用 LangGraph） |
| **Hybrid Search** | ★★★☆☆ `EnsembleRetriever` 合并多个 retriever 结果，但 RRF 需自己实现 |
| **自定义 Reranker** | ★★★★☆ `ContextualCompressionRetriever` + 自定义 `BaseDocumentCompressor` |
| **小数据量适配** | ★★★★☆ `InMemoryVectorStore` 可用于小规模 |
| **学习成本** | ★★★☆☆ API 变动频繁，版本兼容性问题常见 |
| **迁移代价** | ★★★☆☆ 项目已使用 LangChain 基础库，可渐进式引入 RAG 模块 |

**LangChain 核心优势**：
- 最大的 LLM 生态（142k stars），社区资源丰富
- 与 LangGraph 同生态，Agent 编排无缝衔接
- 组件化设计，可按需引入

**对本项目的适配性**：
- ✅ 项目已使用 LangChain + LangGraph，增量成本低
- ✅ 可用 `langchain-qdrant` 替换直接客户端调用，获得统一抽象
- ⚠️ `EnsembleRetriever` 不如 Qdrant 原生 `query_points` RRF 高效
- ⚠️ 自定义业务逻辑（品类别名/否定排除/分级回退）仍需在 LangGraph 节点中处理

#### Haystack

```
定位：生产级 RAG 编排框架，强调可观测性
仓库：github.com/deepset-ai/haystack (25.9k stars, 2.9k forks)
最新：v2.31.0 (2026-07-08)，5,785 commits
```

| 维度 | 评估 |
|------|------|
| **中文支持** | ★★★☆☆ 依赖外部 embedding，无内置中文能力 |
| **Qdrant 集成** | ★★★★☆ `haystack-core-integrations` 提供 Qdrant 组件 |
| **LangGraph 兼容** | ★★☆☆☆ Haystack 有自己的 Pipeline/Agent 体系，与 LangGraph 并行存在 |
| **Hybrid Search** | ★★★★☆ Pipeline 管道设计天然支持多路召回 + 融合 |
| **自定义 Reranker** | ★★★★★ `SentenceTransformersRanker` 内置支持 |
| **生产可观测性** | ★★★★★ Pipeline 可视化、结构化日志、评估工具链完善 |
| **学习成本** | ★★★☆☆ Pipeline 理念清晰但有概念门槛 |
| **迁移代价** | ★★☆☆☆ 需要用 Haystack Pipeline 重写整个检索流程 |

**Haystack 核心优势**：
- 生产级设计：Pipeline YAML 序列化、版本化、可视化
- deepset 企业级支持（Apple、Meta、Airbus 等在用）
- 内置 `SentenceTransformersRanker`，无需包装 CrossEncoder

**对本项目的适配性**：
- ✅ BGE-Reranker 可直接用 `SentenceTransformersRanker`
- ⚠️ 与 LangGraph 架构冲突（Haystack 有自己的 Agent 体系）
- ❌ 迁移成本最高：需要完全重写检索管道

#### RAGFlow

```
定位：开箱即用的完整 RAG 引擎
仓库：github.com/infiniflow/ragflow (85.2k stars, 10k forks)
最新：v0.26.4 (2026-07-07)，7,428 commits
```

| 维度 | 评估 |
|------|------|
| **中文支持** | ★★★★★ 原生中文文档解析（DeepDoc），中文分词/OCR |
| **Qdrant 集成** | ★★☆☆☆ 默认用 Elasticsearch/Infinity，不直接支持 Qdrant |
| **LangGraph 兼容** | ★☆☆☆☆ 独立全栈系统，有自己的 Agent 工作流 |
| **部署复杂度** | ★☆☆☆☆ Docker Compose 全家桶，需要 16GB RAM + 50GB 磁盘 |
| **学习成本** | ★★★★☆ 低代码界面，上手快 |
| **迁移代价** | ★☆☆☆☆ 等于推翻整个项目重做 |

**RAGFlow 核心优势**：
- 开箱即用的文档解析（DeepDoc），尤其擅长复杂格式（PDF/扫描件/表格）
- 模板化分块策略，可视化人工干预
- 内置多路召回 + 融合重排

**对本项目的适配性**：
- ❌ **完全不适合**。RAGFlow 是全栈独立系统，需要推翻现有 FastAPI + LangGraph 架构
- ❌ 16GB RAM 最低要求对于演示环境过重
- ❌ 不支持 Qdrant，与现有基础设施冲突

### 2.3 框架对比总结表

| 维度 | LlamaIndex | LangChain | Haystack | RAGFlow | **自研（当前）** |
|------|:----------:|:---------:|:--------:|:-------:|:-----------:|
| Stars | 50.9k | 142k | 25.9k | 85.2k | - |
| 中文电商适配 | ★★★☆☆ | ★★★☆☆ | ★★★☆☆ | ★★★★★ | **★★★★★** |
| Qdrant 集成 | ★★★★★ | ★★★★★ | ★★★★☆ | ★★☆☆☆ | **★★★★★** |
| LangGraph 兼容 | ★★★☆☆ | **★★★★★** | ★★☆☆☆ | ★☆☆☆☆ | **★★★★★** |
| Hybrid Search | ★★★★☆ | ★★★☆☆ | ★★★★☆ | ★★★★☆ | **★★★★★** |
| 自定义 Reranker | ★★★★★ | ★★★★☆ | ★★★★★ | ★★☆☆☆ | **★★★★★** |
| 小数据量适配 | ★★★★☆ | ★★★★☆ | ★★★☆☆ | ★☆☆☆☆ | **★★★★★** |
| 迁移代价 | 高 | 中 | 高 | 极高 | - |
| 维护成本 | 中 | 中 | 中 | 高 | **低** |
| 生产可观测性 | ★★★☆☆ | ★★★☆☆ | ★★★★★ | ★★★★☆ | **★★★☆☆** |

### 2.4 是否值得从自研 pipeline 迁移？

**结论：不值得迁移，但可以选择性引入组件。**

理由：

1. **自研 pipeline 已经覆盖了框架能做的一切**：
   - Hybrid search：Qdrant 原生 `query_points` + RRF（比任何框架包装都高效）
   - Reranker：直接调用 CrossEncoder（比框架包装少一层抽象）
   - 多维排序：意图感知权重矩阵（框架不提供此能力）
   - 否定语义/品类别名/分级回退（纯业务定制，框架不支持）

2. **迁移的代价远大于收益**：
   - 需要重写 1180+ 行 agent.py 中的检索编排逻辑
   - 自定义业务逻辑（品类守卫、场景化预采样、排除规则）难以映射到框架抽象
   - 框架的抽象层会增加不必要的间接调用开销

3. **唯一值得引入的场景**：
   - 如果需要处理大量非结构化文档（PDF/Word/扫描件）→ 可考虑 **LlamaParse**（LlamaIndex 的文档解析服务，可独立使用）
   - 如果需要标准化检索评估 → 可考虑引入 **ranx** 库做 NDCG/precision@k 评测

---

## 3. 向量库对比

### 3.1 向量库总览（2026年7月数据）

| 向量库 | Stars | 最新版本 | 语言 | 部署方式 | Hybrid Search | 资源占用 |
|--------|:-----:|:--------:|------|----------|:------------:|---------|
| **Qdrant** | 33.3k | v1.18.2 | Rust | Docker / 嵌入式 / 云 | ✅ 原生 RRF + DBSF | 中（~200MB RAM 空载） |
| **Milvus** | 31k+ | v2.x | Go/C++ | Docker Compose 全家桶 | ✅ | 高（多组件，2GB+ RAM） |
| **Weaviate** | 12k+ | v1.x | Go | Docker / 云 | ✅ | 中 |
| **Chroma** | 18k+ | v0.5+ | Python | 嵌入式 / Docker | ❌ 仅 dense | 低 |
| **pgvector** | 22.2k | v0.8.5 | C (PG扩展) | PostgreSQL 扩展 | ✅ 全文搜索 + RRF | 极低（复用 PG） |

### 3.2 小数据量场景关键对比

#### Qdrant vs pgvector（287 条记录场景）

| 维度 | Qdrant（当前） | pgvector（已有 PG） |
|------|:--------------:|:------------------:|
| **部署复杂度** | 需独立 Docker 容器 | 零（PostgreSQL 扩展） |
| **内存占用** | ~200-300MB | ~0（复用 PG shared_buffers） |
| **287条检索延迟** | <1ms | <1ms（全表扫描也极快） |
| **Hybrid Search** | ✅ 原生 `query_points` + RRF | ✅ tsvector + RRF/cross-encoder |
| **Payload 过滤** | ✅ must/must_not/should | ✅ WHERE 子句（SQL 原生） |
| **否定排除** | ✅ must_not Filter | ✅ NOT IN / NOT EXISTS |
| **数据一致性** | 需同步 JSONL → Qdrant | 单数据库 ACID 保证 |
| **运维成本** | 额外服务需监控 | 复用现有 PG 运维 |
| **向量索引** | HNSW（自动） | HNSW 或精确搜索（可选） |

#### 287 条记录是否需要 ANN 索引？

**不需要。** pgvector 文档明确指出：

> *By default, pgvector performs exact nearest neighbor search, which provides perfect recall.*
> *For 287 records, a sequential scan with ORDER BY embedding <=> query LIMIT 10 is sub-millisecond.*

精确搜索在 287 条记录上的性能：
- 1024 维 × 287 条 × 4 字节 = ~1.2MB 数据
- 全表 cosine distance 计算：<0.5ms
- 无需 HNSW 索引，零召回损失

### 3.3 Qdrant 是否过重？

**对于 287 条商品：是的，Qdrant 在架构上偏重。**

- Qdrant Docker 容器空载占用 ~200-300MB RAM
- 需要独立维护 Qdrant 服务健康、数据备份、collection 管理
- 287 条记录完全可以在 PostgreSQL 内存中做精确搜索

**但当前项目已经稳定运行**，迁移的收益主要是：
- 减少一个 Docker 容器
- 统一数据存储（商品数据在 PG，向量也在 PG）
- 简化数据同步（不再需要 JSONL → Qdrant 的 ingestion 步骤）

### 3.4 迁移到 pgvector 的成本与风险

| 维度 | 评估 |
|------|------|
| **迁移工作量** | 中（需重写 retriever.py 约 167 行） |
| **代码改动范围** | retriever.py（核心）、ingestion.py（入库）、config.py（配置） |
| **Hybrid Search 等价性** | 需用 PG 全文搜索 (tsvector) + pgvector + RRF Python 脚本实现 |
| **Payload 过滤** | 直接映射为 SQL WHERE 子句，更自然 |
| **风险** | 低（pgvector 已在依赖中，PG 已在运行） |
| **回退方案** | 保留 Qdrant 代码路径，配置开关切换 |

---

## 4. 文档/知识存储格式

### 4.1 当前数据存储现状

| 数据类型 | 格式 | 位置 | 大小 |
|----------|------|------|------|
| 商品数据 | JSONL | `data/qdrant/products_expanded_100.jsonl` | 272KB, 287条 |
| 商品数据(子集) | JSON | `data/products.json` | 35KB |
| 商品评价 | JSON | `data/qdrant/seed_reviews.json` | 468KB |
| 知识文档 | .md / .docx | 项目各处散落 | 不定 |
| 测试用例 | JSON | `data/test_cases/` | ~100KB |
| 提示词模板 | JSON | `data/prompts/` | ~12KB |
| 图片资源 | .jpg | `data/images/products/` | ~200张 |

### 4.2 商品数据结构示例（JSONL）

```json
{
  "product_id": "p_clothes_021",
  "title": "Nike Dri-FIT Miler 男子速干短袖跑步上衣轻薄透气公路训练T恤",
  "brand": "耐克",
  "category": "T恤",
  "price": 249.0,
  "rating": 2.4,
  "rating_count": 0,
  "highlights": ["吸湿速干"],
  "attributes": {
    "尺码": "L码~XL码/XXL码",
    "版本": "男款",
    "颜色": "深麻灰~藏青色/藏青色"
  },
  "scenarios": ["通勤", "运动", "日常"],
  "image_url": "/images/products/tshirts/p_clothes_021.jpg",
  "description": "这款Nike Dri-FIT Miler男子速干短袖T恤...(长文本)"
}
```

### 4.3 存储格式对比

| 格式 | 向量化友好度 | 结构化查询 | 维护性 | 推荐场景 |
|------|:----------:|:---------:|:------:|---------|
| **JSONL（当前）** | ★★★★☆ | ★★☆☆☆ | ★★★☆☆ | 原型/小数据量导入 |
| **PostgreSQL 表** | ★★★★★ | ★★★★★ | ★★★★★ | **生产首选** |
| **Markdown** | ★★☆☆☆ | ★☆☆☆☆ | ★★★★☆ | 知识文档/导购规则 |
| **YAML** | ★★☆☆☆ | ★☆☆☆☆ | ★★★★☆ | 配置文件/品类映射表 |
| **JSON** | ★★★☆☆ | ★★☆☆☆ | ★★★☆☆ | 中间格式/测试数据 |

### 4.4 商品数据存储建议

**推荐方案：PostgreSQL 结构化表 + pgvector 向量列**

```sql
CREATE TABLE products (
    id          TEXT PRIMARY KEY,          -- product_id
    title       TEXT NOT NULL,
    description TEXT,
    brand       TEXT,
    category    TEXT NOT NULL,
    price       NUMERIC(10, 2),
    rating      NUMERIC(3, 1) DEFAULT 0,
    rating_count INTEGER DEFAULT 0,
    highlights  TEXT[],                    -- PostgreSQL 数组类型
    attributes  JSONB,                    -- 灵活的属性键值对
    scenarios   TEXT[],                    -- 适用场景
    image_url   TEXT,
    image_urls  TEXT[],
    embedding   vector(1024),             -- pgvector 向量列
    textsearch  tsvector,                 -- 全文搜索列
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_products_brand ON products(brand);
CREATE INDEX idx_products_price ON products(price);
CREATE INDEX idx_products_textsearch ON products USING gin(textsearch);
-- 287条不需要 HNSW 索引，精确搜索即可
-- CREATE INDEX idx_products_embedding ON products USING hnsw (embedding vector_cosine_ops);
```

**优势**：
- 结构化属性可直接 SQL 过滤（品类/价格/品牌），无需 Qdrant payload filter
- 向量检索 + 结构化过滤在同一查询中完成，无需跨服务
- 数据更新时自动 ACID 保证，无需手动同步 Qdrant
- JSONB 支持 attributes 灵活键值对

### 4.5 知识文档管理建议

当前知识文档（导购规则、品类说明）散落在 .md / .docx 文件中：

**推荐方案**：

1. **导购规则/品类说明** → 迁移到 PostgreSQL `knowledge_docs` 表
   ```sql
   CREATE TABLE knowledge_docs (
       id          SERIAL PRIMARY KEY,
       doc_type    TEXT,        -- 'guide_rule' | 'category_info' | 'faq'
       category    TEXT,        -- 关联品类
       title       TEXT,
       content     TEXT,        -- Markdown 内容
       metadata    JSONB,
       embedding   vector(1024),
       created_at  TIMESTAMPTZ DEFAULT NOW()
   );
   ```

2. **.docx 文件** → 使用 `python-docx` 或 `unstructured` 库解析后入库
   - 对于复杂格式（表格/图片），可考虑 LlamaParse（LlamaIndex 的文档解析服务，可独立使用）

3. **品类别名映射**（当前硬编码在 retriever.py 中）→ 迁移到 `category_aliases` 表
   ```sql
   CREATE TABLE category_aliases (
       alias       TEXT PRIMARY KEY,
       category    TEXT NOT NULL,
       sub_categories TEXT[]   -- 子品类列表
   );
   ```
   这样添加新品类别名无需修改代码。

### 4.6 分块策略评估

当前 `ingestion.py:38-53` 的分块策略：

```python
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    # 按段落（\n\n）切分，滑窗 overlap
```

| 场景 | 是否需要分块 | 原因 |
|------|:----------:|------|
| 商品数据 | ❌ 不需要 | 每条商品是一个完整语义单元，整体向量化即可 |
| 商品描述（description） | ⚠️ 可选 | 当前 description 最长约 300 字，在 BGE 512 token 限制内 |
| 知识文档（导购规则） | ✅ 需要 | 规则文档可能较长，需按段落/标题分块 |
| 评价数据 | ❌ 不需要 | 单条评价通常 <100 字，整体向量化 |

**结论**：当前商品数据不分块是正确的。知识文档需要引入分块策略时，建议按 Markdown 标题（##/###）分块，而非固定字符数。

---

## 5. 小数据量电商场景策略

### 5.1 287 条商品用 RAG 是否合理？

**部分合理，但当前架构偏重。**

| 方案 | 适用场景 | 287条表现 | 推荐度 |
|------|---------|:---------:|:------:|
| **纯 SQL + 模糊查询** | 精确品类/价格/品牌筛选 | <1ms | ★★★★☆ |
| **纯向量检索** | 语义匹配（"适合跑步的鞋"） | <1ms | ★★★★☆ |
| **全量 LLM context** | 287条×200字≈57K tokens | 可行但浪费 | ★★☆☆☆ |
| **Hybrid（向量+结构化）** | 语义+精确筛选组合 | <2ms | **★★★★★** |

**关键判断**：
- 287 条商品的全量信息（title + highlights + attributes）≈ 50-60K tokens，理论上可全塞入 LLM context
- 但每次请求 50K+ tokens 的 API 成本和延迟不合理
- 向量检索的价值在于：从 287 条中快速召回 top-20 相关商品，再交给 LLM 精排和生成

### 5.2 纯 SQL 方案的可行性

```sql
-- PostgreSQL 全文搜索（需中文分词插件 zhparser/pg_jieba）
SELECT * FROM products
WHERE textsearch @@ plainto_tsquery('chinese', '跑步 鞋')
  AND category = '鞋'
  AND price BETWEEN 100 AND 500
ORDER BY ts_rank_cd(textsearch, query) DESC
LIMIT 10;

-- pg_trgm 模糊匹配（无需中文分词）
SELECT * FROM products
WHERE title % '跑步鞋'
ORDER BY similarity(title, '跑步鞋') DESC
LIMIT 10;
```

| 方案 | 中文支持 | 语义理解 | 性能(287条) |
|------|:-------:|:-------:|:---------:|
| tsvector 全文搜索 | 需 zhparser/pg_jieba | ❌ 仅关键词 | <1ms |
| pg_trgm 模糊匹配 | ✅ 无需分词 | ❌ 仅字符串相似 | <1ms |
| LIKE 查询 | ✅ | ❌ | <1ms |
| pgvector 语义检索 | ✅ | ✅ | <1ms |

**纯 SQL 方案的局限**：
- 无法理解"适合跑步的鞋" → 应匹配"运动鞋/跑鞋"（需要语义）
- 无法处理"不要 Sony"（需要否定排除逻辑）
- 无法处理"100-300 块的蓝牙耳机"（需要槽位提取 + 多条件组合）

### 5.3 混合方案最佳实践

**推荐架构：pgvector 向量检索 + SQL 结构化过滤（单查询）**

```sql
-- 一次查询完成：语义检索 + 结构化过滤 + 否定排除
SELECT *, 1 - (embedding <=> $1) AS semantic_score
FROM products
WHERE
    -- 结构化过滤
    ($2::text IS NULL OR category = ANY($3::text[]))      -- 品类（含别名）
    AND ($4::numeric IS NULL OR price >= $4)               -- 价格下限
    AND ($5::numeric IS NULL OR price <= $5)               -- 价格上限
    -- 否定排除
    AND ($6::text[] IS NULL OR NOT (brand = ANY($6)))      -- 排除品牌
    AND ($7::text[] IS NULL OR NOT (category = ANY($7)))  -- 排除品类
ORDER BY embedding <=> $1    -- 向量距离排序
LIMIT 20;
```

**优势**：
- 结构化过滤在向量检索前执行（Pre-filtering），零召回损失
- 287 条记录无需 HNSW 索引，精确搜索亚毫秒级
- 否定排除直接用 SQL `NOT IN`，无需 Qdrant 的 `must_not` Filter
- 单数据库查询，无跨服务通信开销

### 5.4 与当前 Qdrant 方案的对比

| 维度 | Qdrant（当前） | pgvector（推荐） | 差异 |
|------|:--------------:|:----------------:|:----:|
| 查询延迟 | 1-3ms | <1ms | pgvector 更快（287条全表扫描） |
| 过滤模式 | Post-filtering（HNSW 后过滤） | Pre-filtering（WHERE 先过滤） | pgvector 无召回损失 |
| 否定排除 | must_not Filter | SQL NOT IN | 等价 |
| 分级回退 | 需多次 Qdrant 查询 | 可用 UNION ALL 单查询 | pgvector 更高效 |
| 数据同步 | JSONL → Qdrant ingestion | 直接 INSERT/UPDATE | pgvector 无需同步 |
| 事务一致性 | 最终一致 | ACID | pgvector 更可靠 |
| 运维 | 额外容器 | 复用 PG | pgvector 更简单 |

### 5.5 LangGraph 中的检索架构建议

在 LangGraph StateGraph 中，检索节点可以更简洁：

```python
# 当前：Qdrant 跨服务调用
async def node_retrieve(state: AgentState) -> AgentState:
    result = await rag_retrieve(query, category=..., exclude_brands=...)
    # rag_retrieve -> embed_text -> qdrant query_points -> filter -> rerank
    ...

# 推荐：PostgreSQL 单查询
async def node_retrieve(state: AgentState) -> AgentState:
    query_vector = await embed_text(query)
    chunks = await pg_hybrid_search(
        query_vector=query_vector,
        query_text=query,
        category=slots.get("category"),
        category_aliases=_category_match_values(slots.get("category")),
        price_min=slots.get("price_min"),
        price_max=slots.get("price_max"),
        exclude_brands=_scoped_exclude_brands(slots),
    )
    # 后续 reranker + product_ranker 逻辑不变
    ...
```

条件路由建议（减少不必要的向量检索）：

```python
def should_retrieve(state: AgentState) -> str:
    if state["intent"] == "chitchat":
        return "generate"
    if state["intent"] == "commodity_detail" and state.get("slots", {}).get("product_id"):
        return "generate"  # 直接查 DB 获取商品详情
    return "retrieve"
```

---

## 6. 最终建议与行动方案

### 6.1 框架选择建议

| 决策 | 推荐方案 | 理由 |
|------|---------|------|
| **RAG 框架** | **维持自研 pipeline** | 当前实现已覆盖所有需求，迁移代价 > 收益 |
| **Agent 编排** | **维持 LangGraph** | 已在使用，与 LangChain 生态兼容 |
| **文档解析** | 可选引入 **LlamaParse** | 如需处理复杂 .docx/PDF 格式，可独立使用 |
| **检索评估** | 可选引入 **ranx** | 标准化 NDCG/precision@k 评测，不改架构 |

### 6.2 向量库选择建议

| 决策 | 推荐方案 | 理由 |
|------|---------|------|
| **短期（比赛阶段）** | **维持 Qdrant** | 已稳定运行，迁移有风险 |
| **中期（赛后优化）** | **迁移到 pgvector** | 统一存储、简化运维、287条无需 ANN |
| **长期（数据增长）** | 如超过 10万条商品 → 回到 Qdrant | pgvector 在大数据量下性能不如专用向量库 |

### 6.3 文档/数据存储建议

| 数据类型 | 当前 | 推荐方案 | 优先级 |
|----------|------|---------|:------:|
| 商品数据 | JSONL 文件 | PostgreSQL `products` 表 + pgvector | **高** |
| 商品评价 | JSON 文件 | PostgreSQL `reviews` 表 | 中 |
| 知识文档 | 散落 .md/.docx | PostgreSQL `knowledge_docs` 表 + Markdown 内容 | 中 |
| 品类别名 | 硬编码 Python dict | PostgreSQL `category_aliases` 表 | 低 |
| 提示词模板 | JSON 文件 | 维持文件（变更频率低） | - |
| 图片资源 | 本地文件 | 维持文件 + CDN URL | - |

### 6.4 架构演进路线图

```
当前状态                    短期优化                    中期演进
───────                   ────────                   ────────
JSONL → Qdrant            JSONL → Qdrant            PostgreSQL + pgvector
     ↓                        ↓                          ↓
  Qdrant 检索              Qdrant 检索               SQL 向量检索
     ↓                        ↓                          ↓
  CrossEncoder             CrossEncoder              CrossEncoder
     ↓                        ↓                          ↓
  ProductRanker            ProductRanker             ProductRanker
     ↓                        ↓                          ↓
  LangGraph 生成            LangGraph 生成            LangGraph 生成

[✅ 已完成]               [🔧 可选优化]              [📋 推荐目标]
                          - 引入 ranx 评估           - 统一 PostgreSQL
                          - LlamaParse 解析          - 移除 Qdrant 依赖
                          - category_aliases 表      - 简化 ingestion 流程
```

### 6.5 如果迁移到 pgvector 的代码改动评估

| 文件 | 改动量 | 说明 |
|------|--------|------|
| `retriever.py` | **重写**（~167行） | Qdrant `query_points` → SQL 查询 |
| `ingestion.py` | **重写**（~126行） | Qdrant upsert → PG INSERT |
| `rag.py` | **小改**（~20行） | 分级回退逻辑用 UNION ALL 简化 |
| `config.py` | **小改**（~5行） | 移除 QDRANT_URL/COLLECTION 配置 |
| `agent.py` | **无需改动** | 检索接口不变，内部实现替换 |
| `reranker.py` | **无需改动** | 输入格式不变 |
| `product_ranker.py` | **无需改动** | 输入格式不变 |
| `embedding.py` | **无需改动** | 向量化逻辑不变 |
| `models/product.py` | **新增** | SQLAlchemy 模型 + pgvector 列 |

**总改动量**：约 300-400 行代码重写，核心业务逻辑（agent.py 1180+ 行）无需改动。

### 6.6 核心结论

1. **不要迁移到 RAG 框架**。自研 pipeline 在中文电商场景下的定制化程度远超框架能提供的抽象，迁移得不偿失。

2. **Qdrant 对 287 条数据偏重，但短期不建议迁移**。比赛阶段已稳定运行，迁移有风险。赛后可考虑迁移到 pgvector 统一存储。

3. **商品数据应迁移到 PostgreSQL 结构化表**。当前 JSONL → Qdrant 的双写模式不够健壮，结构化表 + pgvector 是更合理的方案。

4. **287 条商品用向量检索是合理的**。虽然数据量小可以全塞入 LLM context，但向量检索 + reranker 的组合提供了更好的精准度和成本效率。

5. **混合检索（向量 + 结构化过滤）是最佳实践**。当前已通过 Qdrant payload filter 实现，迁移到 pgvector 后可更自然地用 SQL WHERE 实现。

---

> **参考来源**：
> - LlamaIndex: https://github.com/run-llama/llama_index (v0.14.23, 50.9k stars)
> - LangChain: https://github.com/langchain-ai/langchain (core 1.4.9, 142k stars)
> - Haystack: https://github.com/deepset-ai/haystack (v2.31.0, 25.9k stars)
> - RAGFlow: https://github.com/infiniflow/ragflow (v0.26.4, 85.2k stars)
> - Qdrant: https://github.com/qdrant/qdrant (v1.18.2, 33.3k stars)
> - pgvector: https://github.com/pgvector/pgvector (v0.8.5, 22.2k stars)
> - Qdrant Hybrid Search: https://qdrant.tech/articles/hybrid-search/
> - pgvector README: https://github.com/pgvector/pgvector (filtering, hybrid search, HNSW)
