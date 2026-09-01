# 07 Ops 可观测运营台预览提示词

## 图像生成提示词

Create one production-quality 1440×1024 desktop operations dashboard for a RAG commerce Agent. Extend the confirmed kinetic editorial-tech brand into a serious engineering console: warm bone canvas, near-black navigation and typography, acid-lime active/healthy accents, deep emerald data marks, coral failures, amber pending gates, engineering grid, halftone details and precise registration lines. Retain the existing product's Inter/Noto Sans SC readability, left navigation model, status semantics and Contract 0.2.0 structure, but make it visually distinctive and competition-grade.

Design one focused “Agent Trace” screen, not a collage. Use a black left navigation with “RAG Commerce Ops / 0.2.0” and these entries: “运行概览”, “Agent Trace” active, “检索观测”, “连接器”, “数据冲突”, “评测运行”, “发布门禁”. At the top show environment boundaries “本地演示 / 非生产”, “Provider：deterministic_fake”, “报价：DEMO_FIXTURE”. Do not imply LIVE.

The main canvas should be headed “Mission Trace” and identify one trace “trace_demo_0198” with status “COMPLETED” and “数据库审计：已写入”. Make a clear horizontal summary strip with “总耗时 2.84s”, “检索命中 8/10”, “工具成功 10/10”, and “Token / 成本 N/A · FAKE 未计费”. The dominant center area is a structured public execution timeline, not chain-of-thought: “mission_updated”, “hybrid_search 380ms”, “get_product_facts 122ms”, “compare_products 87ms”, “terminal completed”. Associate concise EvidenceRef counts and tool-duration bars with relevant steps.

Use a compact retrieval panel below or beside the timeline showing “BM25”, “VECTOR”, “RRF”, “RERANK” with measured hit bars and no decorative fake chart. Add a right operations rail with “评测队列” and “发布门禁”. The gate sequence must visibly keep “LOCAL PASS”, “INTEGRATION PASS”, “REAL_MODEL PENDING”, “HUMAN BLOCKED”, “RELEASE BLOCKED” separate. Show one queued evaluation item and a small “刷新后状态保持” audit indicator.

Do not show static-demo disclaimers as if the data were real runtime, fake monetary cost, internal chain-of-thought, raw prompts, secrets, full tool arguments, customer personal data, production SSO, third-party logos, browser chrome, watermark or external brand. Avoid nested-card overload and generic blue SaaS styling; use editorial hierarchy, thin separators, technical typography and a few meaningful panels.

## 交互与状态约定

- 所有 Trace、检索、工具、评测和门禁数据通过生成 TypeScript Client 与 TanStack Query 读取真实运营 API。
- 冲突处置和评测排队先写 PostgreSQL 审计，API 成功后再反馈；刷新后从数据库恢复。
- Trace 只暴露结构化阶段、耗时、哈希和 EvidenceRef，不暴露思维链、原始 prompt 或敏感参数。
- `deterministic_fake` 的 Token/成本显示 N/A；只有真实 Provider 返回的实测数据才能显示数值。
