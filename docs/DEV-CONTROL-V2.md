# DEV-CONTROL-V2 — Phase 2 路线图

> **权威开发控制文档（Phase 2）**。本文档承接 `DEV-CONTROL.md`（Phase 1 基线），定义从"作品集 demo"升级为"可体验产品原型"的完整执行计划。
>
> Phase 1 基线：agent.py 模块化（13 模块）+ pgvector 迁移 + 231 单元测试 + ApiResponse 统一 + CacheBackend/LazySingleton 基础设施。

## Phase 2 完成状态

- [x] **Tier 1**: 认证 + 后端P0 (commit c2b136b)
- [x] **Tier 2**: F6知识库 + F10安全 + F7引用 (commit 70bd24f)
- [x] **Tier 3**: 前端15项缺陷修复 (commit 70bd24f)
- [x] **Tier 4**: Self-Corrective RAG (commit 70bd24f)
- [x] **Tier 5**: 检索质量提升 (commit 70bd24f)
- [x] **Tier 6**: 测试补充 231->403 (359 unit + 44 integration)

### 各 Workstream 落地摘要

| Workstream | 落地内容 |
|-----------|---------|
| A 前端交互修复 (15) | A1-A15 全部修复：首页错误重试、空购物车引导、订单占位清理、订单状态同步、商品详情重试、设置页切换账号、历史抽屉退出、结算确认弹窗、空实现隐藏/标注、DemoMode banner、探索页发布按钮、客服空按钮、收藏/足迹错误提示 |
| B 后端能力补齐 (10) | B1 Session Token 认证 + AuthMiddleware；B2 下单库存校验；B3 订单状态机；B4 下单+清空购物车原子事务；B5 购物车数量上限；B6 速率限制；B7-B10 评价校验/N+1优化/对话式下单/upload端点清理 |
| C 概念落差补齐 (10) | C1-C4 F6 知识库（PDF/MD/TXT 解析 + chunk + pgvector + hybrid_search RRF 融合）；C5-C7 F10 安全过滤（Doubao moderation 输入端+输出端）；C8-C10 F7 引用标注（citation prompt + ProductCardEvent.citation + 前端 CitationSection 渲染） |
| D 检索质量提升 (5) | D1 GT 语义标注；D2 真正 Hybrid Search（dense+tsvector+RRF）；D3 评测默认启用 Reranker；D4 短词扩展 4->8 字符；D5 评测集扩充 |
| E 创新点 (4) | E1 retrieval_score 输出；E2 score<3.0 触发 query rewrite + 二次检索（Self-Corrective RAG）；E3 综合匹配度前端展示；E4 低分商品标注 |
| F 测试覆盖 (6) | F1 认证中间件测试；F2 知识库管道测试；F3 安全过滤测试；F4 订单状态机测试；F5 前端契约回归测试；F6 检索精度评测脚本 |

## 1. 愿景与目标

### 1.1 定位转变
| 维度 | Phase 1 状态 | Phase 2 目标 |
|------|-------------|-------------|
| 项目定位 | 作品集 demo | 可体验产品原型 |
| PRD P0 兑现 | 6/11 完整 | 10/11 完整 |
| P0 交互缺陷 | 13 项 | 0 项 |
| P@3 检索精度 | 0.146 | ≥ 0.35 |
| 单元测试 | 231 | ≥ 350 |
| 认证 | 无 | Session Token 基础认证 |
| 安全过滤 | 无 | Doubao 内容审核（输入+输出） |
| 知识库上传 | stub | PDF/MD/TXT 解析+检索 |

### 1.2 七项核心指标
1. P0 交互缺陷清零（前端 8 + 后端 5 = 13 项）
2. PRD P0 兑现 10/11（补齐 F6 知识库 + F10 安全过滤，F7 引用标注部分实现）
3. P@3 ≥ 0.35（修复 GT + 启用 reranker + 真正 hybrid search）
4. 单元测试 ≥ 350（补充认证/安全/状态机/契约测试）
5. 认证可用（Session Token + AuthMiddleware）
6. 安全过滤可用（输入端+输出端双重审核）
7. 知识库可用（PDF/MD/TXT -> 分块 -> 向量 -> 检索融合）

## 2. 范围定义

### 2.1 In Scope（6 Workstream）
| Workstream | 名称 | 任务数 | 工期 |
|-----------|------|--------|------|
| A | 前端交互修复 | 15 | 6.8d |
| B | 后端能力补齐 | 10 | 5.1d |
| C | 概念落差补齐 | 10 | 7.5d |
| D | 检索质量提升 | 5 | 2.8d |
| E | 创新点落地 | 4 | 3d |
| F | 测试覆盖扩展 | 6 | 2.8d |

### 2.2 Out of Scope
- 完整 JWT/OAuth 认证体系（仅 Session Token）
- 真实支付网关接入（保留 Toast 占位）
- 物流跟踪系统
- GraphRAG 知识图谱
- 双 Agent 协作架构
- 多模态 CLIP image embedding（保留 VLM->文本->检索）

## 3. 优先级矩阵

| Tier | 内容 | Workstream | 工期 | 依赖 |
|------|------|-----------|------|------|
| 1 | 认证 + 后端 P0 | B1-B6 | 3.5d | 无 |
| 2 | 概念补齐：F6 + F10 | C1-C7 | 4.5d | Tier 1 |
| 3 | 前端缺陷修复 | A1-A15 | 6.8d | Tier 1（认证） |
| 4 | 创新点 | E1-E4 | 3d | Tier 2（引用标注） |
| 5 | 检索质量 | D1-D5 | 2.8d | 无 |
| 6 | 测试 | F1-F6 | 2.8d | 所有 Tier |

**总工期**：20-25 天（并行可压缩至 15-18 天）

## 4. Workstream A — 前端交互修复

### A. P0 缺陷（8 项，必须修复）

| # | 任务 | 文件 | 工期 |
|---|------|------|------|
| A1 | 首页错误状态 UI + 重试按钮 | HomeScreen.kt, ChatViewModel.kt | 0.5d |
| A2 | 空购物车"去首页逛逛"clickable | CartScreen.kt | 0.2d |
| A3 | 订单页占位功能清理（去付款/查看物流） | OrdersScreen.kt | 0.3d |
| A4 | 订单状态同步后端（催发货/确认收货/取消） | OrdersScreen.kt, UserRepository.kt | 0.5d |
| A5 | 商品详情加载失败重试按钮 | ProductDetailScreen.kt | 0.3d |
| A6 | 设置页"切换账号"修正为跳转登录页 | SettingsScreen.kt | 0.2d |
| A7 | 历史抽屉"退出登录"修正为真实退出 | HistoryDrawer.kt | 0.2d |
| A8 | 结算页提交订单确认弹窗 | CheckoutScreen.kt | 0.3d |

### B. P1 缺陷（7 项，优先修复）

| # | 任务 | 文件 | 工期 |
|---|------|------|------|
| A9 | 设置页 9 个空实现隐藏或标注"即将开放" | SettingsScreen.kt | 0.5d |
| A10 | 个人页 4 个占位功能隐藏 | ProfileScreen.kt | 0.3d |
| A11 | 比价页价格趋势标注"示例数据" | CompareTrackingSheet.kt | 0.2d |
| A12 | DemoMode 全局视觉标识（顶部 banner） | MainActivity.kt | 0.5d |
| A13 | 探索页"发布"按钮隐藏或标注"即将开放" | ExploreScreen.kt | 0.2d |
| A14 | 客服页空实现按钮隐藏 | CustomerServiceScreen.kt | 0.2d |
| A15 | 收藏/足迹页加载失败错误提示 | FavoritesScreen.kt, FootprintsScreen.kt | 0.5d |

## 5. Workstream B — 后端能力补齐

### B1: Session Token 认证（1.5d）

**方案**：UUID token + DB sessions 表 + 内存缓存

```
POST /api/v1/auth/login
  入参: {user_id: str (可选), nickname: str (可选)}
  出参: {token: UUID, user_id: str, expires_at: ISO8601}
  存储: sessions 表 (token, user_id, expires_at) + 内存缓存 (TTL 30min)

后续请求: Authorization: Bearer <token>
  AuthMiddleware:
    1. 查内存缓存 -> 命中则 request.state.user_id = resolved
    2. 未命中 -> 查 DB sessions 表 -> 命中则写缓存 + request.state.user_id
    3. 未命中 -> 返回 401 AuthError
  豁免路径: /api/v1/auth/login, /health, /ready, /version, /docs, /redoc, /metrics
```

**新增文件**：
- `app/api/auth.py` — login/logout/me 端点
- `app/schemas/auth.py` — LoginRequest/TokenResponse
- `app/services/auth_service.py` — token 生成/验证/缓存
- `app/core/middleware.py` — AuthMiddleware（扩展）

**修改文件**：
- `app/models/session.py` — 增加 auth_token + auth_expires_at + auth_user_id 字段
- `app/main.py` — 注册 AuthMiddleware + auth router
- 所有 API 端点 — user_id 参数改为从 `request.state.user_id` 读取

### B2-B6: 后端 P0 缺陷修复

| # | 任务 | 文件 | 工期 |
|---|------|------|------|
| B2 | 下单库存校验 | order_service.py, product_service.py | 0.5d |
| B3 | 订单状态机（cancel 校验状态） | order_service.py | 0.3d |
| B4 | 下单+清空购物车原子事务 | order.py, cart_service.py | 0.5d |
| B5 | 购物车数量上限（单品≥99/总数≥50） | cart_service.py | 0.3d |
| B6 | 速率限制（/chat /voice /upload 10req/min） | main.py, middleware.py | 0.5d |

### B7-B10: 后端 P1 缺陷修复

| # | 任务 | 文件 | 工期 |
|---|------|------|------|
| B7 | 评价购买资格校验 | review_service.py | 0.3d |
| B8 | 收藏/足迹/购物车 N+1 优化（批量查询） | favorites.py, footprints.py, cart.py | 0.5d |
| B9 | 对话式下单创建真实订单 | agent.py node_cart | 0.5d |
| B10 | /documents/upload 空壳端点移除或标注 | upload.py | 0.2d |

## 6. Workstream C — 概念落差补齐

### C1-C4: F6 知识库上传（3.5d）

**存储方案**：独立 `knowledge_chunks` 表

```sql
CREATE TABLE knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id TEXT NOT NULL,           -- 文档批次 ID
    chunk_index INT NOT NULL,      -- 块序号
    chunk_text TEXT NOT NULL,      -- 原文
    embedding vector(1024),        -- BGE 向量
    metadata JSONB DEFAULT '{}',   -- 来源/标题/页码
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX ON knowledge_chunks (doc_id);
```

| # | 任务 | 工期 |
|---|------|------|
| C1 | 文档解析（PDF=pypdf, MD=markdown, TXT=纯文本） | 1d |
| C2 | chunk_text + embed_batch + pgvector 写入 | 0.5d |
| C3 | `POST /knowledge/ingest` 接收文件上传 | 0.5d |
| C4 | `hybrid_search` 增加 knowledge_chunks 表查询，RRF 融合 | 1.5d |

### C5-C7: F10 安全过滤（2d）

**方案**：Doubao 内容审核 API

```
输入端: classify_intent 节点后 -> safety_check 节点
  -> POST Doubao /api/v3/moderation {input: user_query}
  -> if flagged: 返回 ErrorEvent "抱歉，您的请求包含敏感内容"
  -> 异步执行，不阻塞 SSE 首字节

输出端: generate 节点后 -> output_safety_check
  -> POST Doubao /api/v3/moderation {input: generated_text}
  -> if flagged: 替换为安全提示
  -> LangGraph 新增 safety_check 节点（PRD §9.3 要求）
```

| # | 任务 | 工期 |
|---|------|------|
| C5 | Doubao moderation API 客户端 | 0.5d |
| C6 | 输入端 safety_check 节点 + SSE 集成 | 0.75d |
| C7 | 输出端 safety_check 节点 + 替换逻辑 | 0.75d |

### C8-C10: F7 引用标注（1.5d）

| # | 任务 | 工期 |
|---|------|------|
| C8 | `_build_generation_prompt` 增加 citation 要求 | 0.3d |
| C9 | `ProductCardEvent` 增加 `citation: list[dict] = []` 字段 | 0.3d |
| C10 | 前端 `ProductCard` 组件底部渲染引用来源列表 | 0.9d |

## 7. Workstream D — 检索质量提升

| # | 任务 | 工期 |
|---|------|------|
| D1 | 修复评测 Ground Truth（语义标注替代 rating 排序） | 0.5d |
| D2 | 启用真正 Hybrid Search（dense + tsvector keyword + RRF） | 0.5d |
| D3 | 评测默认启用 Reranker | 0.3d |
| D4 | 短词扩展阈值 4->8 字符 | 0.2d |
| D5 | 评测集 226->300+ 条 | 1.3d |

## 8. Workstream E — 创新点落地

| # | 任务 | 工期 |
|---|------|------|
| E1 | retrieve 节点输出 `retrieval_score` | 0.5d |
| E2 | score < 3.0 触发 query rewrite + 二次检索 | 1d |
| E3 | 商品卡片前端显示"综合匹配度 85%" | 0.75d |
| E4 | 低分商品标注"可能不完全匹配" | 0.75d |

## 9. Workstream F — 测试覆盖扩展

| # | 任务 | 工期 |
|---|------|------|
| F1 | 认证中间件测试（valid/invalid/expired token） | 0.5d |
| F2 | 知识库管道测试（chunk + ingest + 检索融合） | 0.5d |
| F3 | 安全过滤测试（敏感词 + prompt injection） | 0.5d |
| F4 | 订单状态机测试（状态转换 + 非法转换） | 0.3d |
| F5 | 前端契约回归测试（ApiResponse 信封） | 0.5d |
| F6 | 检索精度评测脚本（P@3/P@5/NDCG 自动化） | 0.5d |

## 10. 执行计划

### 10.1 依赖关系图

```
Phase 2.1 (Tier 1): B1 认证 + B2-B6 后端P0     [3.5d] ──┐
                                                            ├──> Phase 2.2 (Tier 2): C1-C7 F6+F10 [4.5d]
                                                            │
Phase 2.2 (Tier 3a): A1-A8 前端P0              [2.5d] ────┤
                                                            ├──> Phase 2.3 (Tier 2): C8-C10 F7 [1.5d]
Phase 2.3 (Tier 3b): A9-A15 前端P1             [4.3d] ────┤
                                                            │
Phase 2.4 (Tier 5): D1-D5 检索质量             [2.8d] ────┤
                                                            ├──> Phase 2.5 (Tier 4): E1-E4 创新 [3d]
Phase 2.6 (Tier 6): F1-F6 测试                 [2.8d] ─────┘
```

### 10.2 提交节奏
- 每个 Tier 完成后提交一次（可随时暂停）
- 提交信息格式：`feat(phase2): Tier N - <描述>`
- 每个 Tier 提交前必须通过 `pytest -m unit`

## 11. 风险与权衡

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| F6 知识库融合复杂度 | hybrid_search 需查双表 | 先做 products-only 基线，再加 knowledge 融合 |
| F10 安全过滤延迟 200-500ms | 影响 TTFT | 异步执行，不阻塞 SSE 首字节 |
| 认证对前端影响 | 所有 API 调用需带 token | ApiClient.kt 统一注入 token |
| P@3 目标 0.35 仍低于 PRD 0.75 | 评测不达标 | 标注"287 条商品结构性限制" |
| 对话式下单与 REST 下单并存 | 两套逻辑混乱 | B9 统一为对话触发 REST 下单 |

## 12. 验收标准

Phase 2 完成标准（全部满足）：
- [x] 8 项 P0 前端缺陷全部修复
- [x] 5 项 P0 后端缺陷全部修复
- [x] F6 知识库可用（PDF/MD/TXT -> 检索）
- [x] F10 安全过滤可用（输入+输出双重）
- [x] F7 引用标注可见（[1][2] + citation 字段 + 前端 CitationSection 渲染）
- [x] 基础认证可用（Session Token）
- [~] P@3 ≥ 0.35 (代码改进已落地 D1-D5，需运行 `python -m app.services.evaluator` 在 LLM 可用时验证)
- [x] 单元测试 ≥ 350（实测 359 unit + 44 integration = 403）
- [x] DEV-CONTROL-V2.md 更新为完成状态

---

> **辅助文档**：本文档承接 `DEV-CONTROL.md`（Phase 1 基线）。技术栈、架构、命令参考等通用信息见基线文档。
