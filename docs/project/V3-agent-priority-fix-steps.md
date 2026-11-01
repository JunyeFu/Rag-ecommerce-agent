# V3 Agent 高优先级分步修复

基线：2026-09-21，`main` / `d670e291d263a6e4f0f041f9c74c6e0246cb854c`。本文件是[总排期](V3-agent-gap-fix-plan.md)中 P0/P1 的执行顺序；没有把既有 `complete` 任务包或历史 MiMo 报告当作本轮修复结果。P2 第三方查价单独排在高优先级验收后。

## 2026-09-21 实施状态

| 项目 | 状态 | 当前证据 |
|---|---|---|
| P0 Agent 清单/待购写入 | 已实现并本地验证 | 工具 Schema 已区分清单与待购；审批后写入真实内存/PostgreSQL 状态；重放与双用户隔离测试通过 |
| P0 报价证据 | 已实现并本地验证 | 报价字段使用匹配 `source_ref` 的独立证据；缺字段、来源不匹配和过期报价不会发布 `offers` |
| P1 Agent 行为 | 已完成真实 Provider 专项验收 | MiMo run-010 公开黄金集通过；专项 run-001 保留模糊需求失败，修复根因后的 run-002 达到 4/4：澄清、重新询价、清单审批写入、待购审批写入全部通过，写入前阻断、批准后变更和幂等重放均成立 |
| P1 真实检索 | 已完成本地真实 Embedding 与 durable Worker 验收 | `RETRIEVAL_MODE=local` 使用固定 revision 的 `Qdrant/bge-small-zh-v1.5` ONNX 模型与 Qdrant；60 SKU / 10 场景 Recall@10 与 NDCG@10 均为 `1.00`。[指标报告](../evidence/v3/local-bge-small-zh-evaluation.json)与[端到端证据](../evidence/v3/local-bge-durable-e2e.json)分开保存；`real` 仍保留给显式外部 OpenAI-compatible Embedding |
| P1 文档 | 已更新 | Android 三入口、Java 21、fixture/real 检索边界与历史证据时点已同步 |

本轮实测：Python 完整套件 `109 passed`（无数据库层 97、集成层 12），Ops `2 passed` 且构建成功，Android Java 21 unit/lint/debug/benchmark 构建成功，Alembic upgrade/current/check 与 OpenAPI、Agent 契约检查通过。MiMo run-010 公开黄金集和专项 run-002 均通过；本地 BGE ONNX + Qdrant 已通过全新缓存首次下载、公开黄金集与 durable Worker 端到端验收，外部 Embedding API 不再是本地作品集门禁。

## 先确认的事实

- `list.update`、`cart.update` 在 [DemoCommerce](../../apps/api/src/ragcommerce_api/demo.py) 中仅返回成功标记；[PostgresDemoCommerce](../../apps/api/src/ragcommerce_api/postgres_demo.py) 继承该处理器，因此 Agent 工具未真正调用已存在的领域写入。
- 工具参数目前共用 `operation/item_id/quantity`，而清单写入需要目标 `list_id` 和 `variant_id`，待购写入需要 `offer_id`；目标解析规则必须先定，否则不能安全接线。
- [运行时](../../packages/agent-runtime/src/ragcommerce_agent_runtime/runtime.py) 在工具调用前检查审批，成功工具写入 checkpoint；PostgreSQL 清单和待购已有主键及 `ON CONFLICT`。修复先使用集合式 `add/remove/set` 语义证明重放后状态不变，不预设新通用重试或操作账本。[PostgreSQL 文档](https://www.postgresql.org/docs/current/sql-insert.html)说明 `ON CONFLICT DO UPDATE` 的原子结果。
- 报价 `OfferView` 包含价格、运费、库存、商家、来源与时效；当前工具证据字段只有商品标题/品牌/品类/属性，不能证明报价字段。
- [MiMo run-009](../evidence/v3/mimo-v2.5-real-evaluation-run-009.json) 的 10 场景已通过其原定门槛，但工具清单没有 `list.update`、`cart.update` 或 `offer.requote`。这份历史报告不能证明新增行为。
- [QdrantProjection](../../packages/retrieval/src/ragcommerce_retrieval/qdrant_projection.py) 与 [真实 EmbeddingProvider](../../packages/retrieval/src/ragcommerce_retrieval/semantic.py) 已存在，但持久化演示仍继承同步的确定性向量检索；真实查询需要处理异步工具边界。

## 第 1 步：固定失败样例（F01，1 人日）

先补会失败的窄范围测试：获批 Agent 清单/待购写入后，公开 GET API 能读到变更；拒绝审批、跨用户调用和同一 run 重放不改变其他用户状态；报价缺少金额来源字段时，Agent 必须失败或显示待核验。测试直接经过 Agent 工具与公开 API，不以直接调用 REST 写入作为 Agent 通过证据。

验收：上述失败在修复前可复现，测试分别指向 D01 与 D02；不运行真实模型或外部查价。

## 第 2 步：让 Agent 写入真实状态（F02–F04，6 人日，P0）

1. 收紧两类工具参数，维持十个工具名称不变：清单使用 `list_id`、`variant_id`、`add/remove`；待购使用 `offer_id`、`add/set/remove`、`quantity`。目标清单不明确时请求用户选择，不猜第一张清单；无目标清单时由现有 API/UI 显式创建。
2. 由 `ToolExecutionContext.user_id` 绑定所有权，处理器调用已有 `patch_list()` 与 `mutate_cart()`；返回实际持久化后的清单/待购结果，不返回布尔成功占位。商家跳转仍保持独立审批。
3. 固定幂等语义：清单 add/remove 是集合操作；待购 add/set 写入明确数量，不做隐式数量累加。利用现有主键及 `ON CONFLICT` 处理并发；只有重放测试显示额外副作用时才增加专门的调用记录。
4. 用 PostgreSQL Worker 测获批、拒绝、进程重启、重复领取、双用户隔离；检验最终状态与 terminal event，避免仅凭 checkpoint 单元测试判定通过。

验收：Agent 发起的获批操作可刷新读取；未授权写入为 0；同一调用重复执行的最终状态一致；用户 A 无法改动用户 B 的清单或待购。

## 第 3 步：补齐报价证据（F05–F06，3 人日，P0）

1. 将商品事实证据与报价证据分开。报价证据明确指向 `price_minor`、`shipping_minor`、`availability`、`merchant_name`、`source_ref` 和验证级别；采集/失效时间是本次报价元数据，不能假装是原始商品资料中的字段。
2. 按结果类型设置 `commercial_fact_fields`。当报价中的任一商业字段缺少对应证据时，现有运行时校验应阻止输出已验证 `offers` 事件；`DEMO_FIXTURE` 始终保留演示级别。
3. 增加缺失价格证据、过期报价、来源不一致的负例，以及商品证据完整但报价证据缺失的回归例。

P0 门禁：上述状态写入和报价证据测试通过，公开事件与 API 报价一致；随后再运行 PostgreSQL 集成测试。

## 第 4 步：补真实 Agent 行为（F07–F08，4 人日，P1）

保持必需商品事实和报价读取规则，只扩大模型可决定的部分：何时追问、是否比较、何时重新询价、何时请求清单/待购审批。新增独立场景覆盖“缺预算追问”“约束变更后重新检索”“报价过期重新询价”“未批准写入停住”“批准后恢复并写入”；先用确定性传输测试工具 Schema 和状态，再以真实 Provider 对这些新增场景单独评测。失败原样记录，不自动切换 fake。

验收：新增场景全部有期望工具序列与状态断言；真实 Provider 报告单列结果、Token、延迟和失败类型，不能复用 run-009 的 9/10 作为新增行为通过证据。

## 第 5 步：接通真实检索（F09–F10，4 人日，P1）

先用半天核实可用 Embedding 端点、向量维度和 Qdrant 集合配置，再决定实现细节。由于 `EmbeddingProvider.embed()` 为异步而工具处理器同步，优先把检索工具调用边界改为可等待的异步执行，避免在事件循环中嵌套 `asyncio.run()`。仅在显式真实模式构建向量和查询 Qdrant；fixture 模式保留确定性向量。对同一冻结查询分别记录 BM25、真实向量和融合排名，来源字段完整；端点缺失或失败时真实模式明确失败。

验收：持久化演示的 `local` 模式确实调用本地 ONNX Embedding 并使用 Qdrant 结果；重建后结果可复现；真实与 fixture 指标分开报告。外部 `real` 模式缺少端点时明确失败，不用 deterministic 结果顶替。

## 第 6 步：文档与高优先级总验收（F13–F14，3 人日）

更新 Android 三入口、Java 21、默认 fake 与显式真实模式的当前说明；旧验证 JSON 保留原始时点并加历史标记。运行 Agent/API 定向测试、PostgreSQL/Qdrant 集成、契约漂移、Android unit/lint/build 与必要的真实 Provider 场景。交付中列出每项通过的证据级别和未通过项。

**P0/P1 目标验收日：2026-10-27。** P2 第三方查价 F11–F12 排在其后；缺沙箱凭据不会阻塞上述高优先级结论。计划日期是估算，实施时以实际失败和完成证据更新 Project。
