# 技术栈与选型复盘

核对日期：2026-11-05；源码基线：`0ed3910c79d21c5418d1111e4c92fd85b06533d1`。本文件按当前产品需求补做选型复盘，说明继续采用这些技术的理由。备选方案未执行等条件跑分，下面的比较是工程判断；实测数值见 [Agent 性能报告](../evaluation/AGENT-PERFORMANCE.md)。

## 先明确要解决的问题

产品面向有预算、用途和约束的 3C 购买决策：澄清需求，检索商品，读取有来源的报价，解释取舍，再由用户比较、保存或确认操作。首版的优先级是 **事实可核验、操作受授权、任务可恢复、Android 体验可连续**。当前输入只有 60 个自有演示 SKU，尚未验证真实商业流量。

据此，保留原生 Android + Python Agent + PostgreSQL 持久化链路；不因为依赖列表里出现某项技术，就将它描述成产品能力。跨语言维护、基础设施数量和模型等待时间，都是这个选择已经付出的成本。

## 实际采用什么

版本来自本仓声明与锁定配置，表示项目选择，不表示上游最新版本。

| 层次 | 实际技术与版本 | 当前职责 | 源码入口 |
|---|---|---|---|
| Android | Kotlin 2.0.21、Jetpack Compose、Room 2.7.2、Coroutines、Hilt、Retrofit / OkHttp；Java 21、SDK 35、minSdk 26 | 三入口 UI、任务本地状态、图库/录音、审批、SSE 与快照恢复 | [构建与依赖](../../apps/android/app/build.gradle.kts)、[工具链](../../toolchain.versions.json) |
| API / 领域 | Python 3.12.11、FastAPI 0.141.1、Pydantic 2.13.4、SQLAlchemy 2.0.52、psycopg 3.3.4、Alembic 1.19.1 | 类型契约、业务状态、授权、事务与迁移 | [Python 依赖](../../pyproject.toml)、[API](../../apps/api/src/ragcommerce_api) |
| Agent | LangGraph 1.2.11、项目自有确定性执行器、11 个注册工具、OpenAI-compatible 协议的 ModelProvider | `guard → plan → tools → respond`；真实规划模型证据只有 MiMo `mimo-v2.5` | [状态图](../../packages/agent-runtime/src/ragcommerce_agent_runtime/runtime.py)、[工具与权限](../../packages/agent-runtime/src/ragcommerce_agent_runtime/tools.py)、[模型接口](../../packages/agent-runtime/src/ragcommerce_agent_runtime/model_provider.py) |
| 持久化 / 异步执行 | PostgreSQL 16、独立 Python Worker、`FOR UPDATE SKIP LOCKED`、租约、持久化事件 | Turn / Job 事务落库、任务领取、写入回执与恢复 | [任务领取](../../apps/api/src/ragcommerce_api/postgres_index.py)、[Worker](../../apps/worker/src/ragcommerce_worker/persistent_demo.py)、[Checkpoint](../../packages/agent-runtime/src/ragcommerce_agent_runtime/postgres_store.py) |
| 检索 | 项目 BM25、结构化过滤、本地 BGE-small-zh-v1.5、ONNX Runtime 1.23.2、Qdrant 1.18.2、RRF | 关键词与语义检索、排序融合、EvidenceRef | [BM25](../../packages/retrieval/src/ragcommerce_retrieval/search.py)、[BGE / Qdrant](../../packages/retrieval/src/ragcommerce_retrieval/semantic.py) |
| 媒体 | MinIO Python SDK 与固定源码构建的 MinIO `RELEASE.2025-04-22T22-12-26Z` | 图像、音频对象存储；第三方许可为 AGPL-3.0-only | [基础设施](../../infra/compose.yaml)、[构建来源](../../infra/minio-source.Dockerfile)、[固定版本与许可](../../toolchain.versions.json) |
| Ops Web | TypeScript 7.0.2、React 19.2.8、Vite 8.2.2、TanStack Query 5 | 通过实际 API 查看 Agent Trace、检索与门禁 | [依赖](../../apps/ops-web/package.json)、[前端](../../apps/ops-web/src) |
| 接口与观测 | OpenAPI 0.2.0、生成的 Python / Kotlin / TypeScript 类型、类型化 SSE、OpenTelemetry | 三端契约同步、公开状态流、请求与执行观测 | [契约](../../packages/contracts/openapi.json)、[生成器](../../scripts/generate_contracts.py)、[观测](../../apps/api/src/ragcommerce_api/observability.py) |
| 工程工具 | uv 0.11.13、Node 24.15.0、npm 12.0.1、Gradle 8.9、Docker Compose、GitHub Actions、pytest / Hypothesis、Ruff、Vitest、Playwright、Android instrumentation | 锁定依赖、本地运行、分层质量检查 | [工具链](../../toolchain.versions.json)、[CI](../../.github/workflows/ci.yml)、[工作区脚本](../../package.json) |

两项容易误读的地方：

- **Redis 8.2.2 在 Compose 和启动脚本中配置，但当前 API / Worker / Agent / 检索源码没有 Redis 调用。** 不能将现有压测归功于 Redis 缓存或消息队列。
- PostgreSQL 镜像包含 **pgvector**；当前本地 BGE 向量检索实现使用 **Qdrant**。两者同时出现在配置中，不等于已经实现双向量数据库方案。

LangGraph 在本项目负责控制流。代码调用 `graph.compile()`，持久化由项目自己的 `CheckpointStore`、PostgreSQL Job 与事件实现；没有使用 LangGraph 官方 checkpointer，因此不把框架提供的持久化能力直接记成已接入能力。官方能力边界见 [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)。

## 对比备选方案：收益、代价与改选条件

### 客户端与服务端

| 决策 | 当前方案的收益 | 当前方案的代价 | 备选方案的优势与适用条件 |
|---|---|---|---|
| Kotlin / Compose，而非 Flutter / React Native | 与 Android 生命周期、AudioRecord、图库、Room 和 TalkBack 在同一原生工程中处理，便于定位恢复与无障碍问题 | 业务 UI 不能直接复用到 iOS；要维护 Kotlin、Python、TypeScript 三套工程 | Flutter 的跨平台代码复用适合首日同时交付 Android / iOS；React Native 适合以 React 为核心的移动团队。若多端覆盖成为首要约束，应重新评估，当前没有跨框架启动或流畅度对照实测。[Compose 官方](https://developer.android.com/compose)、[Flutter 架构](https://docs.flutter.dev/resources/architectural-overview) |
| Python / FastAPI，而非 TypeScript / NestJS、Go 或 Java / Spring | Agent、模型调用、本地 ONNX 与评测共用 Python，类型模型连接 OpenAPI，减少跨服务封装 | 同步 CPU 工作、GC、模型重复加载都会拖累延迟；需要区分 I/O 并发与 CPU 并行 | TypeScript 可以统一 Web/API 语言；Go 适合以网络服务和部署体积为主要约束的团队；Java 适合既有 Spring 领域系统。当前不为未测的语言吞吐优势迁移 AI 主链。[FastAPI 并发与并行](https://fastapi.tiangolo.com/async/) |
| React / Vite SPA，而非引入 Next.js 服务端渲染 | Ops 是连接既有 API 的运营界面，静态构建即可交付；Python 保持业务入口 | 路由、数据边界等由项目明确组织；不具备现成的公开内容 SEO 方案 | Next.js 等框架提供更完整的路由与渲染选择，也支持静态导出；若增加公开可索引的商品内容，应按内容需求选型，不能将 Next.js 简化为“必须多养一台 Node 服务”。[React 建站建议](https://react.dev/learn/creating-a-react-app) |

### Agent、队列与事实存储

| 决策 | 当前方案的收益 | 当前方案的代价 | 备选方案的优势与适用条件 |
|---|---|---|---|
| 单 Agent + 显式状态图 + 确定性工具执行器，而非自由循环 / 多 Agent | 规划、授权、事实守卫与写入职责清楚，失败可对应具体状态与工具；当前购物任务可由一个管理 Agent 完成 | 单模型等待仍长，注册工具与状态边界需要维护；图本身不会自动解决副作用与幂等 | 简单固定问答可用普通函数流程，代码更少；只有任务能明确分工、并行收益超过协调成本时才有理由采用多 Agent。当前未做多 Agent 对照，不宣称单 Agent 的质量或成本领先。[LangGraph workflows / agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents) |
| PostgreSQL durable Job / 事件，而非进程内 BackgroundTask 或 Celery + Broker | Turn 与 Job 同事务提交；已有数据库即可支持多 Worker 领取、恢复、幂等回执，减少应用与独立 Broker 的双写问题 | 要自行实现租约和领取逻辑；Job 与业务共享数据库资源；故障恢复受 300 秒租约影响 | 进程内任务适合可丢失短工作；Celery 的成熟任务队列、路由和独立 Broker 更适合复杂分发。若出现可测的数据库争用或多队列需求，再考虑引入。PostgreSQL 官方明确 `SKIP LOCKED` 适用于 queue-like table；Celery 官方也明确不支持 Windows，当前开发宿主的迁移成本需要计入。[PostgreSQL](https://www.postgresql.org/docs/16/sql-select.html#SQL-FOR-UPDATE-SHARE)、[Celery](https://docs.celeryq.dev/en/stable/getting-started/introduction.html) |
| POST / 审批请求 + SSE 状态下发，而非 WebSocket | 操作走明确 HTTP 接口，事件单向增量下发；持久游标与快照支持重连 | 长连接池、断点与逐帧转发仍需处理；不是全双工实时媒体通道 | WebSocket 更适合持续双向交互；当前状态流无需增加这层连接协议。FastAPI 官方 [SSE 文档](https://fastapi.tiangolo.com/tutorial/server-sent-events/)说明其单向事件流特征；本仓实际实现以 [API](../../apps/api/src/ragcommerce_api/app.py)为准 |

### 检索与基础设施

| 决策 | 当前方案的收益 | 当前方案的代价 | 备选方案的优势与适用条件 |
|---|---|---|---|
| BM25 + 本地 BGE + RRF，而非只靠向量或外部 Embedding API | 保留关键词与语义两路结果；固定本地模型可复跑，查询不消耗外部 Embedding API 额度 | 需要模型与索引；本项目实测融合排序 **低于 BM25**，没有质量增益证据；CPU 与常驻内存成本真实存在 | 当前窄目录的 BM25-only 是更轻的基线。外部 Embedding 服务可减少本地模型运维，但增加网络、数据传输与调用费用。只有真实查询集证明语义收益，才有理由为复杂度付费。[本项目消融](../evaluation/AGENT-PERFORMANCE.md#检索组件) |
| Qdrant，而非统一到 PostgreSQL / pgvector | 当前实现已连接向量查询、payload 过滤、独立投影与 collection 别名切换 | 多一个服务、索引同步和恢复面；60 SKU 的数据量本身不足以证明需要专用向量库 | pgvector 把向量与关系数据放在同一数据库，能减少组件；两者都支持过滤，不能以“pgvector 无法过滤”为理由。当前保留已验证链路，不宣称 Qdrant 性能胜出；若服务精简成为首要目标，pgvector 值得以同一查询集验证。[Qdrant 过滤](https://qdrant.tech/documentation/search/filtering/)、[pgvector 过滤](https://github.com/pgvector/pgvector#filtering) |
| MinIO + 本地 Docker Compose，而非直接接入云托管对象存储 | 本地可测试对象上传、读取与删除；基础设施与演示数据由项目控制 | 自行运维、备份与更新；MinIO 为第三方 AGPL 组件；Compose 本地启动不等于生产高可用 | 托管 S3 类服务更适合已有云环境和托管运维需求的团队，但带来服务与流量支出。商业交付前要明确部署模式和第三方许可，项目 MIT 不覆盖 MinIO。[固定来源与许可记录](../../toolchain.versions.json) |

## 实测反馈怎样影响判断

1. **保留简单基线。** 验收集 64 个有匹配查询上，BM25 / BGE / RRF 的 NDCG@10 分别为 `1.00000 / 0.98102 / 0.99348`。RRF 比 BM25 低 `0.00652`；当前数据不支持“混合检索更准确”。这次只披露结果，不改变运行时检索策略。
2. **先修已知开销。** F60 中每 Worker 的相同 BGE 实例从 8 份改为共享 1 份，两个进程的常驻内存观测从约 989–990 MiB 降至约 327 MiB；ASGI 转发与启动对象 GC 扫描也有对应测量。最终本地十批 × 30 的接单 p95 为 `182.079 ms`。这些结果支持优化现有实现，不支持从一次压测推断语言之间的胜负。[F60 根因与对照](../evidence/v3/final-F60-review-20261024.json)
3. **模型等待仍是产品瓶颈。** 真实 MiMo 黄金集首轮场景耗时中位数 `38.827 s`、p95 `191.270 s`；含 API、工具与场景后置检查，尚无独立首 token / 首张推荐时延指标。异步接单解决请求占用，不能缩短模型推理本身。
4. **组件数量有成本。** 当前是 PostgreSQL、Qdrant、MinIO 加配置中的 Redis；不存在已经验证的 Redis 加速收益。商业方案应按事实供给、交付终端、容量和运维责任确定所需组件，而不是按技术名词数量计价。

## 商业适用性

当前架构适合演示和继续验证“有证据的 3C 选购与购买前决策”，可以评估为消费端助手或商家 / 平台的导购组件。它尚不能支撑“全网最低价”“实时库存”“交易闭环”或生产 SLA 的承诺。联盟授权、LIVE 报价与深链、生产身份与安全/法务门禁、物理设备和最终同版交付仍是上线条件，状态以 [当前候选记录](../release/local-portfolio.json)为准。

本次保留当前架构：继续利用已有可验证链路，同时承认原生多语言维护、专用向量服务和本地模型的成本。没有跨栈实测和真实查询收益前，不将替换框架或增加 Agent 当成性能结论。
