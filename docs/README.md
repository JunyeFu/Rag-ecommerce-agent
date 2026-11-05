# 文档导航

main 是持续开发候选，历史 v0.3.0 Release 与当前源码验收分开。当前整体 HOLD，商业发布 NO_GO。

| 你要了解什么 | 入口 |
|---|---|
| 产品画面与本地启动 | [仓库首页](../README.md) |
| 最新进展、未完成项 | [缺陷收口](defects/V3-FINAL-CLOSEOUT.md)、[交付状态](release/local-portfolio.json) |
| 系统架构与 Agent 链路 | [C4](architecture/V3-C4.md)、[时序](architecture/V3-AGENT-SEQUENCE.md) |
| 演示准备 | [Android 准备](demo/V3-ANDROID-PREPARE.md)、[五分钟讲解](demo/V3-FIVE-MINUTE-DEMO.md) |
| 检索与评测口径 | [方法](evaluation/methodology.md) |
| 技术栈、备选方案与选型理由 | [技术选型复盘](architecture/TECH-STACK-DECISIONS.md) |
| Agent 实测、分母与历史负结果 | [性能报告](evaluation/AGENT-PERFORMANCE.md)、[机器可读统计](evaluation/agent-metrics-20261105.json) |
| 任务范围与证据 | [任务清单](task-packages/manifest.json)、[运行证据](evidence/v3) |

## 仓库目录

- `apps/`：Android、API、Worker 和 Ops Web。
- `packages/`：领域、Agent 运行时、连接器、检索、评测与接口契约。
- `data/`、`evals/`：自有演示输入、评测用例与必要结果。
- `infra/`、`scripts/`、`e2e/`：本地基础设施、运行/验证脚本与端到端测试。
- `docs/media/`：标有版本或日期的展示素材；`docs/evidence/`：分层运行证据，包含失败记录。
- `output/`、`_archive/`、本地环境与构建缓存不作为公开源码交付。

## 阅读证据

以报告日期、运行配置和 evidence level 为准。单测、集成、fake 模型、真实模型、原生设备、人工验收与发布结论不能互相替代。历史报告中的本机 output 路径是原始运行定位信息，不表示附件已公开或可直接下载。新证据不覆盖旧失败。
