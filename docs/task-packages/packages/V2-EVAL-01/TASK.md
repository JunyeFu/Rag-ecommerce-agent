# V2-EVAL-01 全自动竞赛评测集

## 目标

建立 1,000 条覆盖 Agent、RAG、状态、安全与故障边界的全自动测试集，取消人工盲评数据与人工 gold 门禁。

## 状态

`complete`（数据生成、机器判分与本地重放完成；真实 Provider challenge 执行独立报告）

## 范围

- 十个测试家族，固定 dev/test/challenge 为 600/250/150。
- 所有用例携带机器规则 gold、许可状态、风险标签与唯一 query 指纹。
- 判分覆盖 outcome、工具 precision/recall、证据、商业事实、审批、链接和敏感信息。

## 非目标

- 不使用人工盲评、LLM-as-judge 或 LIVE 报价替代确定性 gold。
- 不把 reference 构造器的 100% 当作模型质量。

## 前置依赖

- `V2-AGENT-01` 的 Trace 与工具契约。
- `V2-API-01` 的统一 Turn 契约。

## 路径所有权

- `evals/v2/`、`packages/evaluation/`、`docs/evaluation/` 与对应脚本。

## 现状证据

- competition-v1 的 500 公开 + 100 人工 held-out 已退役。
- competition-v2 的全部 split 均可由相同 runner 和 grader 自动执行。

## 执行步骤

1. 冻结 schema、seed、家族与 split。
2. 生成 1,000 条唯一用例并校验规则一致性。
3. 重放 reference、负控、指标与置信区间。
4. 在 CI 检查数据漂移、grader 和完整 Python 回归。

## 数据引用

- `evals/v2/cases.v2.jsonl`
- `evals/v2/manifest.json`
- `docs/evaluation/methodology.md`

## 验收

- [x] cases = 1,000，十个家族与三个 split 数量准确。
- [x] query fingerprint 无重复，全部 gold 可机器判分。
- [x] 人工 review queue、rubric、状态脚本和 CI 门禁已移除。
- [x] reference 和负控可确定性重放。

## 回滚

- 保留 Git 历史；新版本只通过生成器和 manifest 切换，不混用旧数据。

## 停止条件

- Schema 漂移、重复 query、规则冲突或失败样本未进入分母时停止发布评测结果。

## 交接格式

- 提供数据版本、split 指标、失败 case ID、Provider/模型版本和运行命令。
