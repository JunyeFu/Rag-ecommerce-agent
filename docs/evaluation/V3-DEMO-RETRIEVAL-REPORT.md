# V3 演示检索与质量报告

## 检索门禁

- 数据：60 个项目自有虚构 SKU；10 个项目自有黄金查询。
- 检索：BM25 + 确定性开发向量 + 结构化品类/预算过滤 + RRF。
- 实测：10/10 黄金查询的目标商品排名第 1，因此该固定 demo 集的 Recall@10 与 NDCG@10 均为 `1.00`；每个候选均带 EvidenceRef。
- 验证：`uv run pytest apps/api/tests/test_demo_flow.py packages/retrieval/tests/test_demo_catalog.py packages/retrieval/tests/test_hybrid_semantic.py -q`。

## 负载门禁

- 环境：同一进程内的 FastAPI ASGI fixture，`deterministic_demo` provider，30 个隔离 development identity。
- 实测：30 个 Mission 全部完成；丢失 Mission `0`；重复 terminal event `0`；Turn 接受 p95 `155.365 ms`；首个 SSE 响应 p95 `38.053 ms`。
- 阈值：Turn 接受 p95 `<200 ms`、首个 SSE 响应 p95 `<1000 ms`，本次均通过。
- 原始结果：[v3-fixture-load-20260831.json](evidence/v3-fixture-load-20260831.json)。
- 复现：`uv run python scripts/run_v3_fixture_load.py --output docs/evaluation/evidence/v3-fixture-load-20260831.json`。

## 证据边界

以上均为 `project_authored_demo_fixture` / `fixture_load_only` 本地工程回归，不等于公开测试集真实 embedding 得分，也不替代真实 provider 消融、100 条 held-out 双人盲评、LIVE 报价或竞赛最终质量。
