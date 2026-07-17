# 项目深度缺陷审查报告

> 审查日期: 2026-07-17
> 审查范围: 后端代码 / 前后端契约 / 测试覆盖 / 配置部署 / 文档准确性
> 审查方法: 4 路并行 agent 深度审查，覆盖 42 个源文件 + 20 个测试文件 + 全部配置/部署文件

## 缺陷统计

| 严重度 | 数量 | 说明 |
|--------|------|------|
| **CRITICAL** | 7 | 必须立即修复，影响核心功能或安全 |
| **HIGH** | 18 | 影响功能正确性或存在安全风险 |
| **MEDIUM** | 15 | 代码质量或潜在问题 |
| **LOW** | 8 | 优化建议 |
| **测试缺口** | 12 | 关键未测试模块 |

---

## CRITICAL 缺陷 (7)

### C-1: docker-compose.yml 使用错误的 Postgres 镜像 (无 pgvector)
- **文件**: `infrastructure/docker-compose.yml:28`
- **问题**: 使用 `image: postgres:16`（原生 Postgres），但应用依赖 `vector` 扩展。CI 正确使用了 `pgvector/pgvector:pg16`，但 Docker Compose 没有。
- **影响**: 首次 `docker compose up` 时 `CREATE EXTENSION IF NOT EXISTS vector` 会静默失败，全部向量检索功能不可用，健康检查报 `pgvector: unavailable`。
- **修复**: `image: postgres:16` -> `image: pgvector/pgvector:pg16`

### C-2: 真实 API Key 明文存储在磁盘
- **文件**: `apps/backend/.env:8`, `infrastructure/env/.env.docker:8`
- **问题**: 包含真实 API Key `sk-c06kg3t...`。虽然 `.gitignore` 已排除且未提交到 git，但明文存在于磁盘上，且 `.env.docker` 被 docker-compose 的 `env_file` 加载。
- **影响**: 密钥泄露风险（共享机器、备份、误提交）。
- **修复**: 轮换密钥；使用 secrets manager 或 Docker secrets；`.env.docker` 改用占位符。

### C-3: 所有 API 端点无认证
- **文件**: `app/api/` 全部路由文件
- **问题**: 所有端点接受客户端提供的 `user_id`/`session_id`，无 JWT、API Key 或会话验证。任何人知道 UUID 即可访问他人购物车、订单、收藏。
- **影响**: 完整的跨用户数据访问。
- **修复**: 实现 JWT 或会话认证中间件，验证用户身份后再操作。

### C-4: uv.lock 仍包含 qdrant-client 依赖
- **文件**: `apps/backend/uv.lock:2169, 2197`
- **问题**: pgvector 迁移从 pyproject.toml 移除了 qdrant-client，但 `uv.lock` 从未重新生成，仍包含 `qdrant-client v1.18.0`。
- **影响**: `uv sync` 安装不必要的 qdrant-client 及其传递依赖（grpcio, protobuf 等），与 requirements.txt 不一致。
- **修复**: 运行 `uv lock` 重新生成锁文件。

### C-5: CORS 生产环境通配符
- **文件**: `app/core/config.py:52`, `app/main.py:127`
- **问题**: `CORS_ORIGINS: list[str] = ["*"]` 是默认值，`.env.docker.example` 设置 `APP_ENV=production` 但未设 `CORS_ORIGINS`。
- **影响**: 生产环境允许任意网站跨域请求 API。
- **修复**: 生产环境设具体域名；config.py 添加验证器拒绝 `["*"]` 当 `APP_ENV=production`。

### C-6: Dockerfile 以 root 用户运行
- **文件**: `apps/backend/Dockerfile` (无 USER 指令)
- **问题**: 容器内应用以 root 运行。
- **影响**: 若存在 RCE 漏洞，攻击者获得容器内 root 权限，增大容器逃逸风险。
- **修复**: 添加非 root 用户 `RUN useradd -m -u 1000 appuser && USER appuser`。

### C-7: 弱数据库凭据
- **文件**: `apps/backend/.env:2`, `infrastructure/docker-compose.yml:31-34`
- **问题**: `shopping:shopping123` 硬编码在 docker-compose 和所有 .env 文件中。
- **影响**: 数据库端口暴露时可直接连接。
- **修复**: 使用强随机密码 + 环境变量替换。

---

## HIGH 缺陷 (18)

### 前后端契约不一致 (4)

### H-1: CompareRepository 解析错误的响应格式
- **后端**: `app/api/products.py:48-50` — 返回 `{"code":0,"data":{"items":[...],"total":287}}` 包裹格式
- **前端**: `CompareRepository.kt:42-44` — `JSONArray(json)` 期望裸数组 `[...]`
- **影响**: Compare 页面加载真实商品**始终静默失败**，永远回退到 Mock 数据。
- **修复**: 前端改为 `JSONObject(json).getJSONObject("data").getJSONArray("items")`

### H-2: CompareRepository 使用错误的查询参数名
- **后端**: `products.py:25` — `size: int = Query(20)`
- **前端**: `CompareRepository.kt:36` — 发送 `?limit=100`
- **影响**: 后端忽略 `limit`，默认只返回 20 条（期望 100）。
- **修复**: `limit` -> `size`

### H-3: Compare API 发送 `dimensions: []` 而非 `null`
- **后端**: `comparator.py:317` — `if dimensions is None:` 才自动推断
- **前端**: `CompareRepository.kt:71-73` — 发送 `JSONArray()`（空数组）
- **影响**: 比较结果维度为空，只返回 LLM 摘要，无逐维度对比数据。
- **修复**: 前端不发送 dimensions 字段（让 JSON 中缺省 = Python None），或后端改为 `if not dimensions:`。

### H-4: Product ORM 模型缺少 rating_count 列
- **后端**: `models/product.py` 无 `rating_count` 列 vs `schemas/product.py:28` 声明了该字段
- **前端**: `ProductDetailViewModel.kt:271`, `CompareRepository.kt:53` 解析此字段
- **影响**: API 永远返回 `rating_count: 0`，前端显示"0人付款"。
- **修复**: Product 模型添加 `rating_count = Column(Integer, default=0)` 列。

### 安全与错误处理 (8)

### H-5: 购物车 add_to_cart 竞态条件 (TOCTOU)
- **文件**: `app/services/cart_service.py:72-83`
- **问题**: 先 SELECT 检查是否存在，再 INSERT 或 UPDATE。并发请求会导致数量丢失更新。
- **修复**: 使用 `INSERT ... ON CONFLICT DO UPDATE SET quantity = cart_items.quantity + 1`。

### H-6: 图片服务路径遍历风险
- **文件**: `app/main.py:208-227`
- **问题**: `serve_image` 使用 `{file_path:path}` 参数拼接路径，无显式校验路径不超出 `IMAGES_DIR`。
- **修复**: `.resolve()` 后检查 `startswith(IMAGES_DIR.resolve())`。

### H-7: 健康检查在 engine 为 None 时崩溃
- **文件**: `app/main.py:237`
- **问题**: `DATABASE_URL` 未设时 `engine = None`，`engine.connect()` 抛 `AttributeError`，错误消息泄露内部异常类型。
- **修复**: 顶部添加 `if engine is None: return JSONResponse(503, {"database": "not_configured"})`。

### H-8: 健康检查降级时仍返回 HTTP 200
- **文件**: `app/main.py:246-247`
- **问题**: `healthy = db_status == "connected"` — 数据库连接但 pgvector 不可用时返回 200 "degraded"，负载均衡器无法识别。
- **修复**: `healthy = db_status == "connected" and pgvector_status == "ok"`。

### H-9: 聊天消息无长度限制
- **文件**: `app/schemas/chat.py:6`
- **问题**: `message: str` 无 `max_length`，用户可发送 MB 级文本导致 LLM Token 消耗激增。
- **修复**: `message: str = Field(..., min_length=1, max_length=2000)`。

### H-10: 上传端点跳过 Content-Type 验证
- **文件**: `app/api/upload.py:28-35, 48-55`
- **问题**: `validate_image_upload()` 已在 `core/security.py` 实现但从未被调用，可上传任意文件类型。
- **修复**: 调用 `validate_image_upload(file.content_type, len(contents))`。

### H-11: node_cart 在 AsyncSessionLocal 为 None 时崩溃
- **文件**: `app/services/agent.py:1754-1755`
- **问题**: DATABASE_URL 未设时 `AsyncSessionLocal is None`，`async with AsyncSessionLocal()` 抛 `TypeError`。
- **修复**: 添加 `if AsyncSessionLocal is None:` 检查。

### H-12: LLM 流式响应无错误恢复
- **文件**: `app/services/llm_client.py:181-192`
- **问题**: 流式调用不重试。连接中断时已发送部分 SSE，无法再发送错误事件。
- **影响**: 用户收到截断响应无错误提示。
- **修复**: 流式消费添加 try/except，异常时发送 `ErrorEvent` SSE 事件。

### 配置与部署 (6)

### H-13: Dockerfile 缺少 libgomp1 (torch 依赖)
- **文件**: `apps/backend/Dockerfile:7-9`
- **问题**: `python:3.11-slim` 基础镜像无 `libgomp1`，PyTorch 导入会失败 `ImportError: libgomp.so.1`。
- **修复**: `apt-get install -y libgomp1`。

### H-14: BGE 模型 ~3.5GB 烘入镜像，无多阶段构建
- **文件**: `apps/backend/Dockerfile:26-27`
- **问题**: 模型下载在 `COPY . .` 之后，每次代码变更都重新下载 3.5GB。镜像 ~5-6GB。
- **修复**: 多阶段构建或移除预下载，依赖 volume 挂载。

### H-15: CI 不缓存 pip 依赖且下载 CUDA torch ~2GB
- **文件**: `.github/workflows/ci.yml:29`
- **问题**: 无 pip 缓存；`torch==2.12.0` 默认下载 CUDA 版本。
- **修复**: `cache: 'pip'`；先安装 CPU torch `--index-url https://download.pytorch.org/whl/cpu`。

### H-16: CI 缺少关键环境变量
- **文件**: `.github/workflows/ci.yml:30-33`
- **问题**: 缺少 `AUTO_IMPORT_DATA=false`、`DEMO_MODE=true`、`APP_ENV=testing`、`HF_ENDPOINT`。
- **影响**: 测试触发模型下载、数据导入、LLM 调用，导致缓慢和 flaky。
- **修复**: 添加这些环境变量。

### H-17: .env 示例文件仍有 Qdrant 残留
- **文件**: `infrastructure/env/.env.example:4-6`, `.env.testing:3-4`
- **问题**: 仍包含 `QDRANT_URL`、`QDRANT_COLLECTION`（config.py 已移除）。
- **修复**: 删除这些行。

### H-18: 数据库连接池缺少 recycle/timeout
- **文件**: `app/core/database.py:15-18`
- **问题**: 无 `pool_recycle`（默认 -1 永不回收），长时间运行容器中连接变 stale。
- **修复**: 添加 `pool_recycle=3600, pool_timeout=30`。

---

## MEDIUM 缺陷 (15)

| # | 文件 | 问题 |
|---|------|------|
| M-1 | `cart_service.py:25` | 缓存失效用前缀匹配 `k.startswith(session_id)`，session_id 互为前缀时误删 |
| M-2 | `reranker.py:67-71` | 模型加载失败设 `False` 永不重试，瞬时故障后永久降级 |
| M-3 | `retriever.py:177-207` | `hybrid_search` 无 try/except，DB 故障异常直接上浮 |
| M-4 | `llm_client.py:129,204` | 未检查 `response.choices` 是否为空，可能 IndexError |
| M-5 | `main.py:62` | 启动迁移 `except Exception: pass` 静默吞掉所有错误 |
| M-6 | `config.py:27-77` | 无生产环境必填项验证，缺少 DATABASE_URL/API_KEY 时静默降级 |
| M-7 | `order.py:20-23` | `session_id` 格式未校验，非 UUID 导致 500 而非 400 |
| M-8 | `web_search.py:27-28` | DDGS 同步调用在 async 函数中，阻塞事件循环 |
| M-9 | `config.py` vs `.env.*` | APP_ENV/CORS_ORIGINS/EMBEDDING_MODEL 等跨配置文件不一致 |
| M-10 | `build.gradle.kts:50` | Release 构建未启用 minify，APK 未混淆优化 |
| M-11 | `build.gradle.kts:19-20` | compileSdk=35 但 buildToolsVersion=36.1.0 版本不匹配 |
| M-12 | `docker-compose.yml` | 无资源限制和日志轮转配置 |
| M-13 | `startup.py:31-33` | 残留 `data/qdrant` 路径候选（死代码） |
| M-14 | `.env:15` | 本地 .env 用端口 8082，与所有其他配置的 8080 不一致 |
| M-15 | `uv.lock` vs `requirements.txt` | 版本策略不一致（range vs pin），uv sync 与 pip install 结果不同 |

---

## LOW 缺陷 (8)

| # | 文件 | 问题 |
|---|------|------|
| L-1 | `cart_service.py:13` | 内存缓存非多进程安全，多 worker 时缓存不一致 |
| L-2 | `api/*.py` | API 响应格式不统一（ApiResponse vs 裸 dict vs 裸字段） |
| L-3 | `agent.py:2213` | LangGraph 未显式设置 recursion_limit |
| L-4 | `agent_streaming.py:47` | 流式缓冲区 `buffer.count()` 每次全扫描，O(n^2) |
| L-5 | `llm_client.py:78-79` | AsyncOpenAI 实例未在 shutdown 时关闭 |
| L-6 | `comparator.py:171` | 残留 `_fetch_products_from_qdrant` 向后兼容别名 |
| L-7 | `requirements.txt:28-29` | pytest 在生产依赖中（应在 dev extras） |
| L-8 | `docker-compose.yml:25` | healthcheck start_period=300s 过长 |

---

## 测试覆盖缺口 (关键模块)

### 零测试模块 (12/26 服务)

| 模块 | 函数数 | 严重度 | 缺口 |
|------|--------|--------|------|
| `comparator.py` | 7 | **HIGH** | 整个模块未测试，`_determine_winner` 逻辑未验证 |
| `cache.py` | 6 | **HIGH** | 整个模块未测试，TTL/版本/LRU 未验证 |
| `image_parser.py` | 6 | **HIGH** | `_parse_vlm_output` 未测试，拍照搜索核心解析 |
| `favorite_service.py` | 5 | **HIGH** | 完整 CRUD 未测试 |
| `order_service.py` | 5 | **HIGH** | 完整 CRUD 未测试 |
| `review_service.py` | 4 | **HIGH** | 完整 CRUD 未测试 |
| `product_service.py` | 5 | **HIGH** | 完整 CRUD 未测试 |
| `footprint_service.py` | 4 | **HIGH** | 完整 CRUD 未测试 |
| `user_service.py` | 3 | MEDIUM | 完整 CRUD 未测试 |
| `web_search.py` | 3 | MEDIUM | 搜索+回退链未测试 |
| `feedback_service.py` | 1 | MEDIUM | 服务未测试（仅 schema 测试） |
| `evaluator.py` | 2 | MEDIUM | 仅占位测试 `assert True` |

### agent.py 核心节点未测试

| 函数 | 严重度 | 说明 |
|------|--------|------|
| `route_after_intent` | **CRITICAL** | 路由决策函数，bug 会导致所有查询走错分支 |
| `node_classify_intent` | HIGH | 意图分类+槽位提取+否定语义 |
| `node_retrieve` | HIGH | RAG 检索编排 |
| `node_generate` | HIGH | LLM 生成+反幻觉 |
| `node_compare` | HIGH | 商品比较 |
| `node_cart` | HIGH | 购物车操作 |
| `generate_response` | HIGH | SSE 流式入口（仅 mock 测试） |
| `_validate_ranked_products` | HIGH | 商品校验（零价格/无标题过滤） |

### 测试基础设施问题

| 问题 | 影响 |
|------|------|
| 无 `pytest-cov`，无覆盖率报告 | 无法跟踪覆盖率 |
| 无测试标记（unit/integration/slow） | 无法分离快速/慢速测试 |
| 无 `mock_llm` fixture | 依赖 LLM 的测试 hang |
| `conftest.py` 仅 2 个 fixture | 缺少 mock DB、sample data 等 |
| 28+ API 端点未测试 | HTTP 契约未验证 |
| `test_evaluation.py` 仅 `assert True` | 占位测试 |

### 覆盖率评级

| 模块 | 覆盖率 | 评级 |
|------|--------|------|
| `intent.py` | ~70% | B |
| `product_ranker.py` | ~80% | B+ |
| `retriever.py` | ~60% | C+ |
| `reranker.py` | ~80% | B+ |
| `agent.py` | ~25% | D |
| `cart_service.py` | ~30% | D |
| `comparator.py` | 0% | F |
| `cache.py` | 0% | F |
| `image_parser.py` | ~5% | F |
| CRUD services (7个) | 0% | F |
| API routes | ~15% | D |

---

## 修复优先级建议

### P0 — 立即修复 (阻断核心功能)
1. **C-1**: docker-compose.yml 镜像改 `pgvector/pgvector:pg16`
2. **H-1**: CompareRepository 响应格式解析（Compare 页面始终用 Mock）
3. **H-4**: Product 模型添加 `rating_count` 列
4. **H-13**: Dockerfile 添加 `libgomp1`
5. **C-4**: 重新生成 `uv.lock`

### P1 — 短期修复 (安全+功能正确性)
6. **C-2**: 轮换 API Key，使用 secrets manager
7. **C-3**: 实现认证中间件
8. **C-5/C-6/C-7**: 生产安全配置（CORS/root/DB 密码）
9. **H-5**: 购物车原子操作
10. **H-9/H-10**: 输入验证（消息长度/文件类型）
11. **H-2/H-3**: Compare 查询参数和 dimensions

### P2 — 中期改进 (健壮性+测试)
12. **H-7/H-8**: 健康检查修复
13. **H-12**: LLM 流式错误恢复
14. **H-15/H-16**: CI 缓存和环境变量
15. 补充 `route_after_intent`、`cache.py`、`comparator.py` 单元测试
16. 添加 `mock_llm` fixture 和测试标记

### P3 — 长期优化 (代码质量)
17. 统一 API 响应格式
18. 补充全部 CRUD 服务测试
19. 添加 Alembic 迁移或移除依赖
20. Android 构建优化（minify/签名检查）
