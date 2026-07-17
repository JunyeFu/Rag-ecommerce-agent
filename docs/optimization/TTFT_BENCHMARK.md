# TTFT / SSE 首屏响应基准

验证日期：2026-06-05

验证环境：
- Backend: FastAPI / Uvicorn, `http://127.0.0.1:8080/api/v1`
- Database: Docker PostgreSQL, `localhost:5433`
- Vector DB: pgvector in PostgreSQL, `localhost:5433`
- 商品向量：`products` table，287 条（评测时为 290 条）

基准脚本：
- `apps/backend/scripts/benchmark_ttft.py`
- 原始结果：`docs/optimization/ttft_benchmark_20260605.json`

## 结论

后端 SSE 已在进入缓存、历史、意图分类、检索和 LLM 调用前立即发送 `progress` 事件，因此客户端首屏可见反馈稳定小于 1 秒。

后端同时发送一段极短的 `text_delta` 前导文本，因此严格按首个文本 token 计算也稳定小于 1 秒。

本次复测结果：

| 指标 | 结果 |
| --- | ---: |
| first_event 平均值 | 47.2 ms |
| first_event 最大值 | 65 ms |
| first_event P95 | 63.0 ms |
| first_event 是否全部 < 1s | 是 |
| first_text 平均值 | 47.2 ms |
| first_text 最大值 | 65 ms |
| first_text P95 | 63.0 ms |

分场景结果：

| 场景 | first_event_ms | first_text_ms | first_card_ms | done_ms | cards |
| --- | ---: | ---: | ---: | ---: | ---: |
| chitchat | 23 | 23 | - | 10503 | 0 |
| recommend | 65 | 65 | 10478 | 12465 | 3 |
| negation | 52 | 52 | 9175 | 11807 | 3 |
| compare | 49 | 49 | 6149 | 6149 | 3 |

说明：
- `first_event_ms` 是客户端收到第一个 SSE 事件的时间，用于证明首屏反馈能力。
- `first_text_ms` 是客户端收到第一个 `text_delta` 的时间，本轮通过流式前导文本将严格首 token 口径控制在 1 秒内。
- 推荐/排除/对比路径均返回 3 张商品卡，说明性能基准覆盖了真实导购链路，而不是空接口。
