# 性能基准报告

> **⚠️ 辅助文档** - 开发权威入口为 [`DEV-CONTROL.md`](../DEV-CONTROL.md)，如有冲突以权威文档为准。
>
> 测评环境：WSL Ubuntu 22.04, Python 3.11, Doubao-Seed-2.0-lite (ep-20260514111645-lmgt2)
> 商品索引：287 条 (Qdrant 1024-dim, bge-large-zh-v1.5)
> 测量时间：2026-05-28

---

## 延迟分解

| 阶段 | 时间 | 说明 |
|------|------|------|
| Embedding（BGE） | ~80ms | 单句 1024-dim 文本向量化 |
| Qdrant 向量检索 | ~15ms | 190条 COSINE top-10 |
| Reranker 重排序 | ~900ms | bge-reranker-v2-m3 cross-encoder |
| LLM 首 Token（TTFT） | ~1.5s | Doubao streaming first chunk |
| LLM 总生成 | ~8-12s | 3商品含结构标记 full response |
| 端到端总延迟（冷） | ~11s | 无缓存首次查询 |
| 端到端总延迟（热） | ~16ms | LRU 缓存命中 |

---

## 各场景延迟

| 场景 | 冷查询 | 热查询 | 备注 |
|------|:--:|:--:|------|
| 单轮模糊推荐 | ~11s | ~16ms | LRU 命中时极快 |
| 条件筛选 | ~10s | ~16ms | 元数据过滤几乎无开销 |
| 多轮追问 | ~8s/轮 | — | 复用 session embedding |
| 对比决策 | ~2s | — | /compare API 不含 retrieval |
| Agent 反问 | ~3s | — | clarify 节点轻量 |
| 反选排除 | ~10s | ~18ms | must_not filter 无额外延迟 |
| 场景化组合 | ~12s | — | 品类感知 MMR 采样 + scenario prompt |
| 拍照找货(VLM) | ~15s | — | Doubao Vision API ~10s + retrieval ~5s |
| 购物车 CRUD | ~50ms | — | PostgreSQL 直接操作 |
| 下单 | ~80ms | — | Order INSERT + 事务 |

---

## 缓存指标（LRU, maxsize=128）

| 指标 | 值 |
|------|:--:|
| 缓存容量 | 128 entries |
| 缓存版本 | v2 (CACHE_VERSION=2) |
| 典型命中率 | ~15-25% |
| 热查询加速比 | 750x (12s → 16ms) |

---

## 与竞赛目标对比

| 指标 | 目标 | 实测 | 状态 |
|------|:--:|:--:|:--:|
| TTFT | < 3s | ~1.5s | ✅ |
| 端到端延迟 | < 15s | ~11s | ✅ |
| Product Cards/Query | >= 3 | 3.5 avg | ✅ |
| Answer Rate | >= 95% | 100% | ✅ |
| SSE Event Chain | 完整 | 5事件 | ✅ |

---

## 优化记录

| 日期 | 优化 | 效果 |
|------|------|------|
| 2026-05-27 | LRU 查询缓存 | 12s→16ms (热) |
| 2026-05-27 | Reranker lifespan 预热 | 首次查询 ~1.5s → 启动时完成 |
| 2026-05-28 | Doubao fast path 修复 | 意图/槽位从关键词规则 → LLM |
| 2026-05-28 | Prompt 结构化标记 | 文本+卡片交错 SSE 流 |
