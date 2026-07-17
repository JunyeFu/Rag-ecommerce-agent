# 改进方案初版设计 v1.0

> 来源：评委模拟中识别的 3 个改进方向
> 状态：初版设计，待评审后进入迭代

---

## 改进方向 A：首屏冷启动优化（15min → 30s）

### 现状

| 启动阶段 | 耗时（无缓存） | 耗时（有缓存） |
|----------|:---:|:---:|
| DB 建表 | 1-3s | ~0.5s |
| Reranker 预热（CrossEncoder 加载） | 30-120s | 3-10s |
| Qdrant 等待就绪 | 0-120s | ~0s |
| Embedding 模型下载 | 2-5min | ~0s |
| SentenceTransformer 加载 | 10-30s | 10-30s |
| 向量编码 + 入库 | 20-40s | ~1s（已存在则跳过） |
| **合计** | **~8-15min** | **~15-45s** |

### A.1 快速见效（v1.0，不改 Docker）

#### A.1.1 并行化启动（~30s 节省）

`main.py` lifespan 中 reranker 预热和 Qdrant 数据播种是顺序执行但互不依赖：

```python
# 现状（顺序）
await _warmup_reranker()          # 3-10s
await _startup.ensure_qdrant_data()  # 1-40s

# 改为并行
await asyncio.gather(
    _warmup_reranker(),
    _startup.ensure_qdrant_data(),
)
```

#### A.1.2 共享 Embedding 模型实例（节省 ~1.3GB RAM + 10-30s 重复加载）

`startup.py` 和 `embedding.py` 各自创建独立的 `SentenceTransformer` 实例，加载同一个模型两次。改为共享：

```python
# embedding.py 新增
def set_shared_model(model: SentenceTransformer):
    """由 startup.py 在播种完成后注入已加载的模型"""
    global _embedding_model
    _embedding_model = model

# startup.py 播种完成后
from app.services.embedding import set_shared_model
set_shared_model(local_model)  # 复用，不再重复加载
```

#### A.1.3 Reranker 改为首次请求懒加载（~3-10s 节省）

当前 lifespan 中强制预热 reranker，将其移到首次 `/chat` 请求中按需加载。`reranker.py` 已经支持懒加载（`_get_model()` 有 double-checked locking），只需删除 `main.py:73-81` 的预热调用。

### A.2 深度优化（v2.0，改 Dockerfile）

#### A.2.1 Docker 镜像预烘焙模型

```dockerfile
# Dockerfile 中 pip install 之后、COPY 之前
RUN python -c "
from sentence_transformers import SentenceTransformer, CrossEncoder
SentenceTransformer('BAAI/bge-large-zh-v1.5')
CrossEncoder('BAAI/bge-reranker-v2-m3')
"
```

模型在 `docker build` 时下载到镜像层，容器启动时直接加载本地缓存，**跳过 2-5min 下载**。

代价：镜像增大 ~3.5GB。可接受，比赛评审用 Docker 环境通常不关心镜像大小。

#### A.2.2 预计算向量快照

在 Docker build 阶段运行一次完整编码，将 Qdrant 快照打入镜像或 volume。容器启动时直接挂载，**跳过 20-40s 编码**。

### A.3 推荐实施路径

| 阶段 | 改动 | 效果 | 风险 |
|:--:|------|------|------|
| v1.0 | A.1.1 并行化 + A.1.3 懒加载 | 节省 6-40s | 首次请求多等 3-10s |
| v1.0 | A.1.2 共享模型 | 节省 1.3GB RAM | 需确保线程安全 |
| v1.1 | A.2.1 Docker 预烘焙 | 跳过模型下载 | 镜像+3.5GB |
| v1.1 | A.2.2 预计算向量 | 跳过编码阶段 | 种子数据变更需重建 |

---

## 改进方向 B：P@3 检索精度提升（0.146 → 目标 0.35+）

### 根因分析

| # | 根因 | 严重度 |
|:--:|------|:--:|
| B1 | Ground Truth 生成方式错误——按 rating 排序选 top-3，而非语义相关性标注 | **致命** |
| B2 | "Hybrid Search" 实为纯向量检索，无 BM25/关键词组件 | 高 |
| B3 | P@3 测试未启用 reranker（`--with-reranker` 关闭） | 高 |
| B4 | 所有字段等权拼接为一个 embedding，title 与 description 权重相同 | 中 |
| B5 | 查询扩展仅对 ≤4 字符的查询生效，遗漏大量可扩展查询 | 中 |
| B6 | 意图分类 keyword fallback 准确率仅 61.89%，错误分类导致检索方向偏离 | 中 |
| B7 | 商品语料仅 100-290 条，嵌入空间稀疏 | 低 |

### B.1 快速见效（v1.0）

#### B.1.1 修复 Ground Truth 生成

当前 `run_p3_test.py:find_ground_truth()` 用 category+rating 排序作为正确答案，与语义检索目标不一致。改为：

- **方案 1**：人工标注 50 条查询的正确商品 ID（最准确，耗时 2-3h）
- **方案 2**：多路检索投票——BM25 + 向量 + LLM 三路结果取交集/并集作为 ground truth

#### B.1.2 启用 Reranker 参与 P@3 评测

`run_p3_test.py` 默认不启用 reranker。增加 `--with-reranker` 为默认行为，预期 P@3 从 0.146 → 0.25-0.35。

#### B.1.3 查询扩展覆盖所有查询

`agent.py:68` 当前仅对 `len(query) <= 4` 触发扩展。改为：

```python
# 始终使用 LLM 生成 2-3 个变体查询，多路检索后合并去重
expanded_queries = await _expand_query_llm(query)
all_results = []
for q in expanded_queries:
    all_results.extend(await retriever.search(q))
results = mmr_deduplicate(all_results)
```

### B.2 深度优化（v2.0）

#### B.2.1 真正的 Hybrid Search（BM25 + Dense）

Qdrant 原生支持多路检索 + RRF 融合：

```python
# Prefetch: 同时发两条检索
prefetch = [
    models.Prefetch(query=dense_vector, using="dense", limit=20),
    models.Prefetch(query=sparse_vector, using="sparse", limit=20),
]
results = client.query_points(
    collection_name="products",
    prefetch=prefetch,
    query=models.FusionQuery(fusion=models.Fusion.RRF),
)
```

需要：创建 sparse vector 索引（BGE 的 SPLADE 或 BM25 tokenizer）。

#### B.2.2 Per-Field 加权 Embedding

将 title（权重 0.4）、highlights（0.3）、description（0.2）、attributes（0.1）分别嵌入，检索时加权聚合：

```
final_score = 0.4 * sim(q, title_vec) + 0.3 * sim(q, highlights_vec) 
            + 0.2 * sim(q, desc_vec) + 0.1 * sim(q, attrs_vec)
```

#### B.2.3 Reranker 输入扩展

`reranker.py:_get_content()` 当前仅用 `title + highlights[:3]`。扩展为：

```python
parts = [title, description[:200]]  # 加入描述前 200 字
parts.extend(highlights[:5])        # 从 3 条扩到 5 条
if attributes:                      # 加入属性
    parts.append(" ".join(attributes))
```

### B.3 推荐实施路径

| 阶段 | 改动 | 预期 P@3 | 工作量 |
|:--:|------|:--:|:--:|
| v1.0 | B.1.1 修复 GT + B.1.2 启用 reranker | 0.25-0.35 | 2-3h |
| v1.0 | B.1.3 查询扩展全覆盖 | 0.30-0.40 | 1h |
| v2.0 | B.2.1 BM25 混合检索 | 0.35-0.45 | 4-6h |
| v2.0 | B.2.3 Reranker 输入扩展 | 0.40-0.50 | 0.5h |

---

## 改进方向 C：离线/Demo 模式

### 现状

- Android 端 Mock 数据齐全（MockProducts 100条、MockChats 3轮对话、MockCompareData、MockExplorePosts 100条）
- `CartViewModel.loadCart()` 已有本地 DB 降级
- `ProductDetailViewModel.loadProduct()` 已有 `buildMockDetail()` 降级
- **唯独 Chat/SES 路径没有降级**——网络失败时只显示 toast 报错

### 设计方案：Android 端 Demo 模式

不修改后端。在 Android 端新增 `DemoModeConfig` + 修改 `ChatRepository` 返回 mock SSE 流。

### C.1 新增 DemoModeConfig

```kotlin
// core/network/DemoModeConfig.kt
object DemoModeConfig {
    private val prefs by lazy {
        ShoppingApp.instance.getSharedPreferences("demo_mode", Context.MODE_PRIVATE)
    }
    
    var isEnabled: Boolean
        get() = prefs.getBoolean("enabled", false)
        set(value) { prefs.edit().putBoolean("enabled", value).apply() }
}
```

### C.2 修改 ChatRepository

```kotlin
// data/repository/ChatRepository.kt
fun sendMessage(request: ChatRequest): Flow<SSEEvent> = flow {
    if (DemoModeConfig.isEnabled) {
        emitAll(mockResponse(request.message))  // 从 MockChats 匹配回复
    } else {
        emitAll(sseClient.connect(request))      // 正常网络路径
    }
}

private fun mockResponse(message: String): Flow<SSEEvent> = flow {
    emit(SSEEvent.Progress(SSEEvent.ProgressData("classifying")))
    delay(200)
    emit(SSEEvent.Progress(SSEEvent.ProgressData("retrieving")))
    delay(300)
    // 从 MockProducts 中关键词匹配，生成 product_cards 事件
    val matched = MockProducts.match(message)
    emit(SSEEvent.ProductCards(matched))
    emit(SSEEvent.TextDelta("为您找到 ${matched.size} 款商品"))
    delay(100)
    emit(SSEEvent.Done(SSEEvent.DoneData(conversationId = "demo")))
}
```

### C.3 SettingsScreen 添加开关

在已有的 `SettingsScreen.kt` 中新增一行 `Switch` 组件，绑定 `DemoModeConfig.isEnabled`。

### C.4 额外收益

同一个 `DemoModeConfig` 开关可复用到：
- `CartViewModel`：跳过网络同步，纯本地 DB 操作
- `CompareViewModel`：使用 `MockCompareData` 替代 LLM 对比
- `ProductDetailViewModel`：已有降级逻辑，无需改动

### C.5 工作量估算

| 文件 | 改动 | 行数 |
|------|------|:--:|
| 新增 `DemoModeConfig.kt` | SharedPreferences 包装 | ~20 |
| 修改 `ChatRepository.kt` | 分流 mock/real | ~30 |
| 修改 `SettingsScreen.kt` | 添加 Switch 组件 | ~15 |
| 新增 `MockSseResponder.kt` | 关键词匹配 + SSE 事件生成 | ~40 |
| **合计** | | **~105 行** |

---

## 实施优先级汇总

| 优先级 | 改进项 | 预期效果 | 工作量 | 风险 |
|:--:|--------|----------|:--:|:--:|
| **P0** | C: Demo 模式 | 断网也能完整演示 | 2h | 低 |
| **P0** | A.1.1 + A.1.3: 启动并行化+懒加载 | 启动快 6-40s | 1h | 低 |
| **P1** | B.1.1 + B.1.2: 修复 GT + 启用 reranker | P@3 → 0.25-0.35 | 2-3h | 低 |
| **P1** | B.1.3: 查询扩展全覆盖 | P@3 → 0.30-0.40 | 1h | 低 |
| **P2** | A.2.1: Docker 预烘焙模型 | 跳过 2-5min 下载 | 0.5h | 镜像变大 |
| **P2** | B.2.1: BM25 混合检索 | P@3 → 0.35-0.45 | 4-6h | 中 |
