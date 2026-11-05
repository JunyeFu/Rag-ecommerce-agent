# V3-SHOWCASE-01 技术选型比较与 Agent 实测披露

## 目标
按 2026-11-05 用户授权，核对实际技术栈、比较备选方案、复算已有 Agent 实测指标，更新 GitHub 首页，呈现商业价值、工程取舍与正式的能力披露。

## 状态
complete；本次文档、离线统计与 GitHub 内容读取核验完成，证据见 verification.json；不改变产品 HOLD 或商业 NO_GO。

## 范围
源码与依赖核对、官方资料比较、已有脱敏报告的离线统计、README 与指标文档发布。

## 非目标
不运行付费模型、不扩展实验、不启用联盟连接器、不部署、不创建 Release；不把历史报告升级为当前版本验收。

## 前置依赖
V3-BASE-00 与 V3-PORTFOLIO-CLOSE-01 均 complete，依赖证据已读取；原始报告与官方资料可用。

## 路径所有权
README.md、docs/README.md、docs/architecture/TECH-STACK-DECISIONS.md、docs/evaluation/AGENT-PERFORMANCE.md、docs/evaluation/agent-metrics-20261105.json、scripts/summarize_agent_metrics.py、本任务包与 manifest。
README 文档增量由 V3-PORTFOLIO-CLOSE-01 转交本包；不转移 V3-FINAL-05 的最终同版交付签收责任。原始证据只读。

## 现状证据
工作树起始干净；main 与 GitHub main 均为 0ed3910c79d21c5418d1111e4c92fd85b06533d1。已有真实模型、检索、容量、恢复与 Android 报告；Redis 配置与应用调用分开核对。

## 执行步骤
1. 核对实现、版本、选型与替代方案。
2. 从逐场景、逐批记录复算指标并保留失败分母。
3. 更新首页与详细文档，校验后发布 GitHub main。

## 数据引用
现有 docs/evidence/v3、evals/v3、evals/v2/results；项目自有 60 SKU。

## 验收
统计脚本离线重跑与 --check 一致；文档链接有效；任务包、脚本 lint/format 与 diff 检查通过；GitHub 默认分支可读到新首页与指标。

## 回滚
仅以新提交撤销本包显式路径改动，保留其他工作与历史证据。

## 停止条件
缺失实测数据以未测说明；远端有并发更新先读取新 head，不覆盖他人提交。

## 交接格式
GitHub 提交、关键选型与指标、验证结果及仍未完成的商业门禁。
