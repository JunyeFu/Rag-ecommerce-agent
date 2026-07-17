# 项目整理报告

> 时间：2026-07-01  
> 范围：项目状态梳理、文档同步、过期资料归档、目录整理。

## 一、已完成事项

1. 新增 `docs/PROJECT_STATUS.md`，统一当前项目状态、竞赛刚性要求、评分口径和严禁口径。
2. 新增 `docs/INDEX.md`，作为当前文档与交付物入口。
3. 更新 `README.md`，修正最高优先级需求链接、技术栈、当前文档入口和最终答辩资料入口。
4. 更新架构/提交/答辩知识库中的过期口径：
   - LangGraph 改为 7 个显式主节点 + 条件路由。
   - RAG 当前主链路改为 Qdrant 原生客户端 + BGE Reranker。
   - 商品规模统一为 287 条商品、约百个细分类。
   - P@3=0.146 明确为直连 Qdrant 裸检指标，不代表最终 Agent 输出质量。
   - 下单明确为模拟订单闭环，不涉及真实支付。
5. 将根目录演示视频移动到 `docs/submission/拾物演示视频.mp4`。
6. 将旧版 PPT 和旧预览移入归档目录。
7. 清理本地 Android Gradle 缓存 `apps/android/app/.gradle/`，并加入 `.gitignore`。

## 二、当前交付物位置

| 交付物 | 当前路径 |
|--------|----------|
| 项目状态 | `docs/PROJECT_STATUS.md` |
| 文档索引 | `docs/INDEX.md` |
| 竞赛核心需求 | `docs/background/REQS-竞赛核心需求.md` |
| 最终 PPT | `docs/defense-ppt/拾物-AI全栈挑战赛答辩-视觉修复版-v9.pptx` |
| 完整讲稿 | `docs/defense-ppt/拾物-AI全栈挑战赛答辩-完整讲稿.md` |
| 演示视频 | `docs/submission/拾物演示视频.mp4` |
| 提交文档 | `docs/submission/项目提交文档.md` |
| 演示手册 | `docs/submission/DEMO_RUNBOOK.md` |
| 答辩知识库 | `docs/defense-kb/README.md` |

## 三、归档内容

| 内容 | 路径 | 数量 |
|------|------|:--:|
| 历史 PPT 与 inspect 文件 | `docs/archive/defense-ppt-old/` | 18 |
| 旧版 PPT 预览和布局 JSON | `docs/archive/defense-ppt-preview/` | 50 |

归档资料只用于追溯，不作为当前答辩口径来源。

## 四、未处理事项

本次没有修改或回滚业务源码。当前工作树仍存在此前已有的后端和 Android 源码修改，应在提交前单独复核源码 diff。
