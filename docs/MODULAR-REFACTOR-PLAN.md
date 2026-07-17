# 高质量模块化修复方案

> 制定日期: 2026-07-17
> 基于缺陷审查报告 + 三路深度架构分析
> 原则: 模块化拆分、设计模式引入、向后兼容、渐进式迁移、测试先行

---

## 架构现状诊断

### 核心问题
1. **agent.py 2704 行上帝文件** — 11 个职责混杂，`generate_response` 单函数 432 行
2. **服务层零抽象** — 全项目无 ABC/Protocol/interface，27 个服务文件全为模块级函数
3. **5 处重复懒加载单例** — llm_client/reranker/embedding/image_parser/product_ranker 各自实现
4. **3 处重复内存缓存** — cart_service/state_manager/cache 各自维护 dict，无 TTL/无大小限制
5. **3 种 DB 访问风格** — ORM (cart_service) vs 原生 SQL (retriever/comparator) vs 混合 (state_manager)
6. **API 层不统一** — 5/13 端点用 ApiResponse 包裹，8 个返回裸 dict；安全代码全是死代码
7. **前端无统一 API 客户端** — 8+ 个文件各自构造 OkHttp 请求

### 设计模式映射

| 模式 | 应用目标 | 优先级 |
|------|----------|--------|
| **Repository** | cart_service/state_manager/retriever — 分离 DB 访问与业务逻辑 | P1 |
| **Strategy** | 意图路由/检索策略/LLM Provider/图片解析/维度评分 | P1-P2 |
| **Factory** | LLM 客户端创建/商品卡片构建 | P1 |
| **Chain of Responsibility** | 检索回退链/生成回退链 | P2 |
| **Command** | 购物车操作 (view/add/quantity/remove/clear/checkout) | P2 |
| **Template Method** | 商品比较流水线 (fetch→infer→extract→winner→summary) | P2 |
| **Singleton (形式化)** | 5 处懒加载统一为 `LazySingleton[T]` | P1 |
| **Observer/Event** | SSE 事件发射器，解耦编排与输出 | P3 |
| **Cache Backend (接口隔离)** | 统一缓存抽象，支持 Redis 迁移 | P1 |

---

## 分阶段实施计划 (测试先行策略)

> 用户确认: 测试先行 -> 先建 mock fixtures + 测试标记，再做模块化拆分
> 调整: Phase 5 (测试基础设施) 提前到 Phase 1 之后、Phase 2 之前

### Phase 0: 基础设施修复 (P0 阻断性缺陷)

> 目标: 修复阻断核心功能的配置/部署问题，不涉及架构变更
> 预计: 1-2 天
> 风险: 低 — 纯配置修复

| # | 修复项 | 文件 | 工作量 |
|---|--------|------|--------|
| 0.1 | docker-compose 镜像 `postgres:16` → `pgvector/pgvector:pg16` | `infrastructure/docker-compose.yml:28` | 5min |
| 0.2 | Dockerfile 添加 `libgomp1` + 非 root 用户 | `apps/backend/Dockerfile` | 30min |
| 0.3 | 重新生成 `uv.lock` (移除 qdrant-client) | `apps/backend/uv.lock` | 5min |
| 0.4 | Product 模型添加 `rating_count` 列 | `models/product.py` | 15min |
| 0.5 | 清理 .env 示例文件 Qdrant 残留 | `infrastructure/env/.env.*` | 10min |
| 0.6 | startup.py 清理 `data/qdrant` 死路径 | `app/startup.py:31-33` | 5min |
| 0.7 | comparator.py 移除 `_fetch_products_from_qdrant` 别名 | `comparator.py:171` | 5min |
| 0.8 | 健康检查 engine None 防护 + 降级时返回 503 | `main.py:237,246` | 15min |

### Phase 1: 共享基础设施层 (设计模式落地)

> 目标: 建立设计模式基础，后续模块化依赖这些抽象
> 预计: 3-4 天
> 原则: 先建抽象，再迁移实现，保持向后兼容

#### 1.1 Cache Backend 抽象 (Strategy + 接口隔离)

```
app/core/cache/
├── __init__.py          # 公开接口
├── backend.py            # CacheBackend Protocol + InMemoryCache
├── query_cache.py        # QueryCache 域专用包装 (现有 cache.py 迁入)
└── no_cache.py           # NoOpCache (禁用缓存时的空实现)
```

**接口定义**:
```python
class CacheBackend(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def clear(self) -> None: ...
    async def stats(self) -> dict: ...
```

**迁移**: 现有 `cache.py` 的 OrderedDict + TTL 逻辑 → `InMemoryCache`；`_is_dynamic()` + `CACHE_VERSION` → `QueryCache` 包装层。

**受益方**: cart_service、state_manager 后续迁移到此接口。

#### 1.2 LazySingleton 泛型工具 (Singleton 形式化)

```python
# app/core/lazy.py
class LazySingleton[T]:
    """线程安全懒加载单例，支持失败重试和依赖注入"""
    def __init__(self, factory: Callable[[], T], retry_on_fail: bool = False, cooldown: int = 300):
        ...
    def get(self) -> T | None: ...
    def is_loaded(self) -> bool: ...
    def reset(self) -> None: ...
    def set_instance(self, instance: T) -> None:  # 依赖注入 (startup.py 用)
        ...
```

**迁移**: 5 处重复模式统一:
- `llm_client.py`: `_client`, `_fast_client` → `LazySingleton[AsyncOpenAI]`
- `reranker.py`: `_reranker_model` → `LazySingleton[CrossEncoder]` (含 retry_on_fail=True)
- `embedding.py`: `_embedding_model` → `LazySingleton[SentenceTransformer]`
- `image_parser.py`: `_llm_client` → `LazySingleton`
- `product_ranker.py`: `_ranker` → `LazySingleton[ProductRanker]`

#### 1.3 DB Session 依赖注入 (消除全局 None 检查)

```python
# app/core/database.py 新增
class DatabaseContext:
    """统一 DB 可用性检查，消除 3+ 处重复 `AsyncSessionLocal is None`"""
    @property
    def available(self) -> bool: ...
    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession | None]:
        """返回真实 session 或 None (内存模式)"""
        ...

db_context = DatabaseContext()  # 全局单例
```

**受益方**: retriever、state_manager、comparator、agent.py node_cart 全部改用 `db_context.session()`。

#### 1.4 异常体系重构

```
app/core/exceptions.py  (扩展)
├── AppException (现有基类)
├── NotFoundError (现有)
├── ValidationError (新)
├── AuthError (新)
├── RateLimitError (新)
├── DatabaseUnavailableError (新)
├── LLMProviderError (新)
└── RetrieverError (新)
```

**HTTPException 处理器**: 在 main.py 注册 `HTTPException` → `ApiResponse` 转换器，统一错误响应格式。

#### 1.5 中间件层激活

```python
# app/core/middleware.py (扩展)
# 1. 激活已存在的 RequestIDMiddleware (当前是死代码)
# 2. 新增 RateLimitMiddleware (slowapi 或自实现)
# 3. 新增 AuthMiddleware (Phase 3 详细实现，先留接口)
```

---

### Phase 1.5: 测试基础设施 (测试先行 - Phase 2 前置条件)

> 目标: 建 mock fixtures + 测试标记 + 覆盖率报告，使现有 hang 测试可跳过
> 预计: 2-3 天
> 原则: 先让测试体系健壮，再做模块化拆分时才能安全验证回归

#### 1.5.1 pytest 配置

```toml
# pyproject.toml 新增
[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "unit: 纯函数测试, 无外部依赖 (<1s)",
    "integration: 需要 DB 或 LLM (>1s)",
    "slow: 耗时测试 (>5s)",
]
testpaths = ["tests"]
addopts = "--strict-markers --cov=app --cov-report=term-missing --cov-fail-under=30"
```

#### 1.5.2 核心 Fixtures

```python
# conftest.py 扩展
@pytest.fixture
def mock_llm(monkeypatch):
    """Mock LLMService, 返回预设响应, 防止 test_agent/test_sse hang"""
    # mock chat_completion / fast_chat_completion
    ...

@pytest.fixture
def mock_db_session():
    """内存 AsyncSession (aiosqlite), 不需要真实 PostgreSQL"""
    ...

@pytest.fixture
def mock_cache():
    """NoOpCache, 测试中不产生缓存副作用"""
    ...

@pytest.fixture
def sample_product():
    """标准 Product dict, 287 条中第 1 条的精简版"""
    ...

@pytest.fixture
def sample_cart_item():
    """标准 CartItem dict"""
    ...
```

#### 1.5.3 标记现有测试

```python
# 为所有测试添加标记
# 纯函数测试 -> @pytest.mark.unit
# 需要 DB/LLM 的测试 -> @pytest.mark.integration
# test_agent.py/test_sse.py/test_chat.py 中 hang 的测试 -> @pytest.mark.integration
```

#### 1.5.4 CI 分层运行

```yaml
# .github/workflows/ci.yml
- name: Run unit tests (fast, no deps)
  run: cd apps/backend && python -m pytest tests/ -m unit -v --cov

- name: Run integration tests (needs DB)
  env:
    DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/test
    DEMO_MODE: "true"
    AUTO_IMPORT_DATA: "false"
  run: cd apps/backend && python -m pytest tests/ -m integration -v
```

**交付标准**: `pytest -m unit` 在 30 秒内完成，零 hang。

---

### Phase 2: agent.py 模块化拆分

> 目标: 2704 行 → ~150 行 facade + 13 个聚焦模块
> 预计: 5-7 天
> 策略: 按依赖顺序从底向上拆分，每步保持测试通过
> 向后兼容: agent.py 变为 re-export facade，现有 import 不破坏

#### 2.1 拆分依赖图与顺序

```
拆分顺序 (从底向上):

Step 1: agent_state.py (AgentState TypedDict + _SLOT_KEYS)
  ↓ 零依赖

Step 2: slot_management.py (Concern G, ~400 行)
  ↓ 依赖 exclusion_rules.py
  ↓ 被几乎所有其他模块依赖 (最高 fan-in)

Step 3: cart_nlp.py (购物车 NLP 解析, ~200 行)
  ↓ 纯正则函数，零 I/O

Step 4: scenario.py (Concern C, ~120 行)
  ↓ 依赖 llm_client.py
  ↓ 仅被 node_retrieve 调用

Step 5: product_assembly.py (Concern E, ~80 行)
  ↓ 依赖 slot_management.py
  ↓ 纯数据转换

Step 6: prompts.py (Concern F, ~180 行)
  ↓ 依赖 slot_management.py
  ↓ 纯字符串构建

Step 7: agent_nodes/ 包 (逐个提取)
  7a: agent_nodes/web_search.py (~40 行) — 最简单
  7b: agent_nodes/clarify.py (~80 行)
  7c: agent_nodes/generate.py (~60 行)
  7d: agent_nodes/retrieve.py (~120 行)
  7e: agent_nodes/compare.py (~220 行)
  7f: agent_nodes/classify.py (~110 行)
  7g: agent_nodes/cart.py (~140 行) — 应用 Command 模式

Step 8: agent.py facade (~150 行)
  - re-export 所有被测试和外部模块引用的符号
  - 保留 route_after_intent, build_agent_graph, agent_graph, run_agent
  - 保留 generate_response (后续 Phase 3 重构)
```

#### 2.2 agent_nodes/cart.py — Command 模式应用

```python
# app/services/agent_nodes/cart.py
from abc import ABC, abstractmethod

class CartCommand(ABC):
    @abstractmethod
    async def execute(self, state: AgentState, db: AsyncSession) -> dict: ...

class ViewCartCommand(CartCommand): ...
class AddToCartCommand(CartCommand): ...
class UpdateQuantityCommand(CartCommand): ...
class RemoveFromCartCommand(CartCommand): ...
class ClearCartCommand(CartCommand): ...
class CheckoutCommand(CartCommand): ...

CART_COMMANDS: dict[str, CartCommand] = {
    "view": ViewCartCommand(),
    "add": AddToCartCommand(),
    "quantity": UpdateQuantityCommand(),
    "remove": RemoveFromCartCommand(),
    "clear": ClearCartCommand(),
    "checkout": CheckoutCommand(),
}

async def node_cart(state: AgentState) -> dict:
    action = _extract_cart_action(state["messages"][-1])
    command = CART_COMMANDS.get(action)
    if command:
        return await command.execute(state, db)
```

**优势**: 130 行 node_cart → 6 个独立可测试命令，每个 <30 行。

#### 2.3 每步验证清单

每个 Step 完成后:
1. `python -m py_compile` 验证语法
2. 运行现有测试套件 (101 passing tests)
3. `grep -r "from app.services.agent import"` 确认 re-export 覆盖
4. agent.py 行数持续下降

---

### Phase 3: 服务层设计模式重构

> 目标: 27 个服务文件引入 Repository/Strategy/Factory 模式
> 预计: 8-10 天
> 依赖: Phase 1 共享基础设施完成

#### 3.1 cart_service.py → Repository + Service (优先: HIGH)

```
app/services/
├── cart_service.py          # 保持公开 API (向后兼容 facade)
├── repositories/
│   ├── __init__.py
│   ├── cart_repository.py   # CartRepository Protocol + SQLAlchemy impl
│   └── base.py              # BaseRepository[T] (通用 CRUD 基类)
```

**修复同时解决**:
- H-5: 购物车竞态条件 → `INSERT ... ON CONFLICT DO UPDATE`
- M-1: 缓存前缀误删 → 精确 key 匹配
- L-1: 多进程缓存不一致 → CacheBackend 接口 (可插 Redis)

#### 3.2 retriever.py → Strategy + Repository (优先: MEDIUM, 最后做)

```
app/services/
├── retriever.py              # 保持公开 API
├── retrieval/
│   ├── __init__.py
│   ├── strategies.py         # SearchStrategy Protocol + DenseVectorSearch + KeywordSearch
│   ├── fuser.py              # ResultFuser (RRF 融合, 独立可测)
│   ├── repository.py         # RetrievalRepository (DB 访问抽象)
│   └── mapper.py             # ProductMapper (统一 Row → dict 转换)
```

**修复同时解决**:
- M-3: DB 故障无处理 → repository 层 try/except + 降级返回
- M-4: LLM 空响应 → 验证层
- SQL 注入 → repository 层参数化查询集中管理

#### 3.3 llm_client.py → Strategy + Factory (优先: HIGH)

```
app/services/
├── llm_client.py             # 保持公开 API
├── llm/
│   ├── __init__.py
│   ├── providers.py          # LLMProvider Protocol + DoubaoProvider + DeepSeekProvider + MimoProvider
│   ├── factory.py            # LLMClientFactory
│   ├── retry.py              # _retry_with_backoff (已有, 提取)
│   └── service.py            # LLMService 统一 chat_completion (消除 fast/普通 重复)
```

**修复同时解决**:
- H-12: 流式无错误恢复 → LLMService 封装错误处理
- M-4: 空 choices 验证 → LLMService 统一验证
- `_needs_thinking_disabled` 重复 → Provider 内聚

#### 3.4 comparator.py → Template Method + Strategy (优先: MEDIUM)

```
app/services/
├── comparator.py             # 保持公开 API
├── comparison/
│   ├── __init__.py
│   ├── pipeline.py           # ComparisonPipeline (Template Method)
│   ├── dimensions.py        # DimensionExtractor + WinnerStrategy
│   ├── summary.py           # SummaryGenerator (LLM + Template 两个策略)
│   └── repository.py         # ProductRepository (复用, 替代直接 SQL)
```

#### 3.5 product_ranker.py → Strategy (优先: MEDIUM)

```
app/services/
├── product_ranker.py         # 保持公开 API
├── ranking/
│   ├── __init__.py
│   ├── scorers.py            # DimensionScorer Protocol + PriceScorer + RatingScorer + ...
│   ├── strategy.py           # RankingStrategy (WeightedSum 等)
│   └── exclusion_filter.py  # 统一 3 种排除机制
```

#### 3.6 image_parser.py → Strategy (优先: MEDIUM)

```
app/services/
├── image_parser.py           # 保持公开 API
├── vision/
│   ├── __init__.py
│   ├── strategies.py         # ImageParseStrategy + VisionLLMStrategy
│   ├── parser.py             # ImageParser (context, 支持回退链)
│   └── storage.py            # FileStorageService (分离文件存储)
```

---

### Phase 4: API 层统一 + 前后端契约修复

> 目标: 统一响应格式、激活安全中间件、修复前端契约
> 预计: 4-5 天
> 依赖: Phase 1 异常体系完成

#### 4.1 统一 API 响应格式

**规则**: 所有 JSON 端点返回 `ApiResponse(data=...)`，SSE 端点不变。

```python
# 需要修改的 8 个端点:
# cart.py, favorites.py, footprints.py, order.py, review.py, user.py, compare.py, feedback.py
# 全部改为: return ApiResponse(data=...)
```

**HTTPException 处理器**: 注册全局 handler 将 HTTPException → ApiResponse 格式。

#### 4.2 前端统一 ApiClient + 契约修复

**用户确认**: 建统一 ApiClient.kt + 修 4 个 bug

```kotlin
// data/remote/ApiClient.kt (新建 - 统一 HTTP 客户端)
class ApiClient private constructor() {
    companion object {
        val instance: ApiClient by lazy { ApiClient() }
    }

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .build()

    // 统一 GET/POST/PUT/DELETE + ApiResponse 解析
    suspend fun <T> get(path: String, params: Map<String, String> = emptyMap()): ApiResponse<T>
    suspend fun <T> post(path: String, body: RequestBody): ApiResponse<T>
    suspend fun <T> put(path: String, body: RequestBody): ApiResponse<T>
    suspend fun <T> delete(path: String, params: Map<String, String> = emptyMap()): ApiResponse<T>

    // 类型化封装 (消除 8+ 文件重复)
    suspend fun getProducts(page: Int, size: Int): PaginatedResponse<Product>
    suspend fun getProduct(id: String): Product
    suspend fun getCart(sessionId: String, userId: String): CartResponse
    suspend fun addToCart(request: CartAddRequest): CartItemResponse
    suspend fun compareProducts(productIds: List<String>): CompareResult
    // ... 其余端点
}

// data/remote/ApiResponse.kt (统一响应解析)
data class ApiResponse<T>(
    val code: Int,
    val data: T?,
    val message: String
) {
    val isSuccess get() = code == 0 || code == 200
}
```

**迁移**: 所有 Repository/ViewModel/Screen 中的 OkHttp 调用 -> `ApiClient.instance.xxx()`

**4 个契约 bug 修复**:

| # | 修复 | 文件 | 方式 |
|---|------|------|------|
| H-1 | 解析 `data.items` 而非裸数组 | CompareRepository.kt -> ApiClient.getProducts() | 统一在 ApiClient 解析 |
| H-2 | `limit` -> `size` | CompareRepository.kt -> ApiClient.getProducts() | 参数名修正 |
| H-3 | dimensions 发送 null | CompareRepository.kt -> ApiClient.compareProducts() | 不传 dimensions 字段 |
| H-4 | rating_count | Phase 0 已修 (后端添加列) | - |

#### 4.3 Schema 整理

```
schemas/
├── cart.py                  # 新建: 从 cart.py 路由内联提取
├── favorites.py             # 新建: 从 favorites.py 内联提取
├── footprints.py            # 新建: 从 footprints.py 内联提取
├── order.py                 # 新建: 从 order.py 内联提取
├── common.py                # 修复: code 默认值 0→200, 添加 error codes
├── product.py               # 修复: ProductUpdate 添加约束
├── review.py                # 激活: 路由改为使用已定义的 schema
├── feedback.py              # 修复: rating 添加 Literal[1, -1]
└── chat.py                  # 修复: message 添加 max_length=2000
```

#### 4.4 安全中间件激活

```python
# main.py 新增
from app.core.middleware import RequestIDMiddleware, RateLimitMiddleware

app.add_middleware(RequestIDMiddleware)     # 激活死代码
app.add_middleware(RateLimitMiddleware,     # LLM 端点限流
    limits={
        "/api/v1/chat": "10/min",
        "/api/v1/voice/chat": "10/min",
        "/api/v1/upload/vision-search": "5/min",
    }
)

# security.py 激活
# upload.py 路由调用 validate_image_upload()
# review.py 路由调用 validate_image_upload()
```

#### 4.5 配置与部署修复

| # | 修复 | 优先级 |
|---|------|--------|
| CORS 生产环境限制 | `.env.docker.example` 设具体域名 + config.py 验证器 | HIGH |
| DB 连接池 recycle | `pool_recycle=3600, pool_timeout=30` | HIGH |
| CI pip 缓存 + CPU torch | `.github/workflows/ci.yml` | HIGH |
| CI 环境变量补全 | AUTO_IMPORT_DATA/DEMO_MODE/APP_ENV | HIGH |
| Dockerfile 多阶段构建 | 模型下载分离到 builder stage | MEDIUM |
| 环境变量一致性 | 统一 .env.example / config.py / docker-compose | MEDIUM |

---

### Phase 5: 测试体系重建

> 目标: 从"能跑的测试" → "有覆盖率保障的测试体系"
> 预计: 5-7 天
> 依赖: Phase 2-3 模块化完成 (可 mock 的接口存在)

#### 5.1 测试基础设施

```python
# pyproject.toml 新增
[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "unit: 纯函数测试, 无外部依赖",
    "integration: 需要 DB 或 LLM",
    "slow: 耗时测试 (>5s)",
]
testpaths = ["tests"]
addopts = "--strict-markers --cov=app --cov-report=term-missing --cov-fail-under=40"
```

```python
# conftest.py 新增 fixtures
@pytest.fixture
def mock_llm(): ...           # Mock LLMService, 防止 hang

@pytest.fixture
def mock_db_session(): ...    # 内存 AsyncSession (sqlite)

@pytest.fixture
def mock_cache(): ...         # NoOpCache 或 InMemoryCache

@pytest.fixture
def sample_product(): ...     # 标准 Product dict

@pytest.fixture
def sample_cart_item(): ...  # 标准 CartItem dict
```

#### 5.2 测试补充优先级

| 优先级 | 模块 | 目标 | 测试数 |
|--------|------|------|--------|
| P0 | `route_after_intent` | 6 条路由分支全覆盖 | 6 |
| P0 | `cache.py` (CacheBackend) | get/set/TTL/version/LRU/dynamic | 8 |
| P0 | `comparator._determine_winner` | price/rating/numeric 各策略 | 5 |
| P0 | `image_parser._parse_vlm_output` | markdown/partial/empty/keywords | 6 |
| P1 | `exclusion_rules.product_violates_exclusions` | brand/category/attr/text | 5 |
| P1 | `cart_service` (Repository) | CRUD + 竞态 + 缓存失效 | 8 |
| P1 | `llm_client` (LLMService) | retry/empty_choices/provider | 5 |
| P1 | `generate_response` (mock LLM) | cache/fallback/override | 5 |
| P2 | 全部 CRUD services | favorite/order/review/product/user | 25 |
| P2 | API 端点 (ASGI client) | 400/404/413/认证 | 20 |

#### 5.3 CI 流水线

```yaml
# .github/workflows/ci.yml 改进
- name: Install CPU torch
  run: pip install torch --index-url https://download.pytorch.org/whl/cpu

- name: Install deps (cached)
  uses: actions/setup-python@v5
  with:
    cache: pip
    cache-dependency-path: apps/backend/requirements.txt

- name: Run unit tests
  run: cd apps/backend && python -m pytest tests/ -m unit -v --cov

- name: Run integration tests
  env:
    DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/test
    DEMO_MODE: "true"
    AUTO_IMPORT_DATA: "false"
  run: cd apps/backend && python -m pytest tests/ -m integration -v
```

---

### Phase 6: generate_response 重构 (SSE Event Pattern)

> 目标: 432 行 god function → 编排器 + 事件发射器
> 预计: 3-4 天
> 依赖: Phase 2 模块化完成

#### 6.1 SSEEventEmitter (Observer 模式)

```python
# app/services/sse_emitter.py
class SSEEventEmitter:
    """解耦 SSE 事件发射与业务编排"""
    def __init__(self):
        self._events: AsyncGenerator[dict, None] = ...

    async def emit_progress(self, message: str): ...
    async def emit_text_delta(self, text: str): ...
    async def emit_product_cards(self, cards: list[dict]): ...
    async def emit_clarify(self, options: list[str]): ...
    async def emit_compare(self, result: dict): ...
    async def emit_done(self): ...
    async def emit_error(self, message: str): ...

    async def stream(self) -> AsyncGenerator[dict, None]:
        """供 EventSourceResponse 消费"""
```

#### 6.2 Pipeline Orchestrator

```python
# app/services/pipeline.py
class ChatPipeline:
    """替代 generate_response 的编排器"""
    def __init__(self, emitter: SSEEventEmitter, ...):
        ...

    async def execute(self, query: str, session_id: str, ...):
        # 1. Cache check
        # 2. Intent classification
        # 3. Route to handler (Strategy)
        # 4. Retrieval (Chain of Responsibility fallback)
        # 5. Generation + interleaved card emission
        # 6. Cache + state persistence
```

---

## 模块化目标架构

```
app/
├── core/
│   ├── cache/               # Phase 1.1: CacheBackend 抽象
│   ├── database.py          # Phase 1.3: DatabaseContext
│   ├── exceptions.py        # Phase 1.4: 异常体系
│   ├── lazy.py              # Phase 1.2: LazySingleton[T]
│   ├── middleware.py        # Phase 1.5: 中间件激活
│   └── security.py          # Phase 4.4: 安全工具激活
│
├── services/
│   ├── agent.py              # Phase 2: facade (~150 行)
│   ├── agent_streaming.py   # 已有
│   ├── agent_state.py        # Phase 2.1
│   ├── slot_management.py    # Phase 2.2
│   ├── cart_nlp.py           # Phase 2.3
│   ├── scenario.py           # Phase 2.4
│   ├── product_assembly.py   # Phase 2.5
│   ├── prompts.py            # Phase 2.6
│   ├── sse_emitter.py        # Phase 6.1
│   ├── pipeline.py           # Phase 6.2
│   │
│   ├── agent_nodes/          # Phase 2.7
│   │   ├── cart.py           # Command 模式
│   │   ├── classify.py
│   │   ├── clarify.py
│   │   ├── retrieve.py       # Strategy: 标准/场景检索
│   │   ├── generate.py       # Strategy: 标准生成
│   │   ├── web_search.py
│   │   └── compare.py
│   │
│   ├── repositories/         # Phase 3.1
│   │   ├── base.py           # BaseRepository[T]
│   │   ├── cart_repository.py
│   │   ├── product_repository.py
│   │   └── session_repository.py
│   │
│   ├── retrieval/            # Phase 3.2
│   │   ├── strategies.py     # DenseVectorSearch + KeywordSearch
│   │   ├── fuser.py          # RRF 融合
│   │   └── mapper.py         # ProductMapper
│   │
│   ├── llm/                  # Phase 3.3
│   │   ├── providers.py      # Doubao/DeepSeek/Mimo Provider
│   │   ├── factory.py        # LLMClientFactory
│   │   └── service.py       # LLMService 统一接口
│   │
│   ├── comparison/           # Phase 3.4
│   │   ├── pipeline.py      # Template Method
│   │   ├── dimensions.py    # WinnerStrategy
│   │   └── summary.py       # LLM/Template 生成
│   │
│   ├── ranking/              # Phase 3.5
│   │   ├── scorers.py       # DimensionScorer
│   │   └── exclusion_filter.py
│   │
│   └── vision/               # Phase 3.6
│       ├── strategies.py    # VisionLLMStrategy
│       └── storage.py        # FileStorageService
│
├── api/
│   ├── deps.py              # Phase 4: get_current_user, rate_limiter
│   └── v1/                  # 统一 ApiResponse + thin controllers
│
└── schemas/                 # Phase 4.3: 全部内联 schema 提取到此
    ├── cart.py              # 新建
    ├── favorites.py        # 新建
    ├── footprints.py       # 新建
    └── order.py            # 新建
```

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 拆分破坏现有 import | 中 | 高 | agent.py 保持 re-export facade，每步 grep 验证 |
| 测试 hang 无法发现回归 | 高 | 中 | Phase 5.1 先建 mock_llm fixture |
| 前端契约修复引入新 bug | 中 | 高 | 契约修复与后端统一同步，集成测试验证 |
| 重构周期过长 | 高 | 中 | 严格按 Phase 顺序，每 Phase 可独立交付 |
| 设计模式过度设计 | 低 | 中 | 仅在重复 ≥3 次时引入抽象；Strategy 仅用于实际有多实现的场景 |

---

## 交付里程碑 (测试先行策略)

| 里程碑 | 内容 | 预计天数 | 可交付状态 |
|--------|------|----------|-----------|
| M1 | Phase 0: 阻断性修复 | 1-2 天 | 核心功能可用 |
| M2 | Phase 1: 共享基础设施 | +3-4 天 | 抽象层就绪 |
| M3 | Phase 1.5: 测试基础设施 | +2-3 天 | mock fixtures + CI 分层 |
| M4 | Phase 2: agent.py 模块化 | +5-7 天 | 2704->150 行 facade |
| M5 | Phase 3: 服务层设计模式 | +8-10 天 | Repository/Strategy/Factory |
| M6 | Phase 4: API统一+前端ApiClient | +4-5 天 | 契约一致 + 统一客户端 |
| M7 | Phase 5: 测试补充 | +3-4 天 | 覆盖率 ≥40% |
| M8 | Phase 6: generate_response | +3-4 天 | SSE 编排解耦 |

**总计**: 29-39 天 (M1-M4 优先交付核心架构改善，M5-M8 后续迭代)

---

## 已确认决策 (用户选择)

1. **API 统一策略**: **全部包裹 ApiResponse** - 所有 JSON 端点统一返回 `{code, data, message}`，前端同步适配
2. **前端改造**: **建统一 ApiClient.kt + 修 4 个 bug** - 集中式 HTTP 客户端，消除 8+ 文件重复
3. **拆分粒度**: **13 模块 (精细)** - 每个职责独立模块，最大可测试性
4. **执行顺序**: **测试先行** - 先建 mock fixtures + 测试标记，再做模块化拆分
5. **缓存迁移**: Phase 1 先用 InMemoryCache，Redis 后续引入
6. **认证方案**: 待定 - JWT 为推荐方案，在 Phase 4 时细化
