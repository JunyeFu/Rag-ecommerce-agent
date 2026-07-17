# 答辩 PPT 大纲 — 拾物 · 智能导购 AI Agent

> 更新：2026-06-07 | 建议 15-18 页，讲解 5 分钟 + QA 2 分钟
> 每页 1 核心观点，少文字多图

---

## P1: 封面
- 标题：拾物 — 基于 RAG 的多模态电商智能导购 AI Agent
- 副标题：AI 全栈挑战赛 第3届 · 华南理工大学
- 技术栈标签：FastAPI / LangGraph / Qdrant / Doubao / Android Compose

## P2: 痛点与场景
- 传统电商搜索：关键词匹配 → 多次筛选 → 人工对比 → 决策疲劳
- 核心洞察：「对话式导购」替代「搜索式购物」
- 一句话价值：用 AI 把"逛商场找导购"的体验搬到线上

## P3: 产品 Demo（截图/动图）
- 左侧：对话流 + 商品卡片嵌入
- 右侧：商品详情页 + 购物车 + 下单

## P4: 9 场景全覆盖
- 表格展示 9 场景 × 难度的完成状态
- 标注加分项最高难度：场景 8 (购物车⭐⭐⭐)、场景 9 (拍照找货⭐⭐⭐)

## P5: 系统架构总览
- 三层架构图：Android Client ↔ FastAPI Gateway ↔ Data Layer
- 标注每层核心技术

## P6: RAG 检索链路（核心）
- 用户查询 → 意图分类 → Embedding → Qdrant 向量检索 → Reranker 重排序 → LLM 生成
- 标注延迟：~80ms + 15ms + 900ms + 1.5s = ~2.5s 纯管道

## P7: Agent 编排（LangGraph）
- 7 个显式主节点 + 条件路由图：classify_intent→clarify/retrieve/compare/cart/web_search/generate
- 多轮状态管理：PostgreSQL sessions 表持久化

## P8: 防幻觉机制
- 三层防护：
  1. RAG — 商品信息来自真实数据库
  2. Prompt 结构标记 — `[PRODUCT_N]` 强制格式
  3. 缓存版本校验 — CACHE_VERSION 防过期数据

## P9: SSE 流式输出
- 6 事件类型：progress / text_delta / product_cards / clarify / done / error
- 交错格式：摘要 → (商品文本 + 卡片) × N → 结语
- 首 Token < 1.5s

## P10: 多模态 — 拍照找货
- 端侧拍照 → VLM (Qwen3-VL-2B / Doubao Vision) → 属性提取 → RAG 检索
- 四层打通：Android Camera → HTTP upload → VLM → Qdrant → SSE cards

## P11: 否定语义处理
- Qdrant must_not 过滤器（品牌/品类/属性）
- 文本级兜底过滤（title/highlights 含排除词 → 丢弃）
- curl 验证：5 组反选查询 100% 排除率

## P12: 购物车闭环
- 对话式加购 → CRUD → 下单确认
- Agent checkout 节点 → Order Service → PostgreSQL
- Android CartScreen 实时状态反馈

## P13: 性能优化
- LRU 查询缓存：12s → 16ms（750x 加速）
- Reranker lifespan 预热
- Doubao thinking disabled fast path
- TTFT 1.5s，端到端 ~11s

## P14: 工程质量
- 全栈数据契约 DATA-CONTRACT v1.0
- E2E 自动化测试（9 场景 curl 脚本）
- Docker Compose 一键部署
- 33,000+ 行代码，177 源文件（102 .py + 73 .kt）

## P15: 创新点总结
- SSE 交错流式（文本+卡片交替推送）
- VLM + RAG 拍照找货全链路
- 否定语义双层排除（向量 + 文本）
- TTS 语音导购（Android TextToSpeech 增量播报）

## P16: 自我评价与展望
- 评分自估：~90/100（基础 33/35 + 工程 23/25 + 效果 17/20 + 加分 17/20）
- 后续方向：首 Token < 1s、更多商品数据、语音全双工

## P17: 致谢
- 指导老师 + 队友 + 开源社区

## P18: QA
- 备用页：技术细节补充（Prompt 模板 / 评测数据 / 架构图）

---

## 每页建议视觉元素

| 页码 | 视觉 |
|------|------|
| P3 | App 截图 × 3 |
| P5 | 架构图（draw.io / Excalidraw） |
| P6 | 时序图 / 泳道图 |
| P7 | LangGraph 状态图 |
| P10 | 拍照流程四格图 |
| P12 | 购物车截图 × 2 |
| P14 | 代码行数 / 文件数统计 |
