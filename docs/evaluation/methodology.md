# RAG Commerce V2 评测方法

## 证据层级

1. `deterministic_contract_reference_only`：验证用例 schema、grader、失败分母、哈希与重放。
2. `development_seed_ablation_only`：在旧 226 条开发种子上比较检索算法；种子许可和 gold 仍待审。
3. `provider_sandbox`：需要获批模型预算与固定 provider/model/prompt 版本，本地尚未执行。
4. `heldout_human`：100 条盲态队列由两位独立评审完成并仲裁，本地尚未执行。
5. `LIVE`：真实授权报价、真实流量和物理终端证据，不属于本任务包。

不同层级不得合并成一个“总分”。确定性 reference 的 100% 只说明期望构造器和 grader 相容，不说明 Agent、RAG、真实报价或人工体验达到质量目标。

## 数据冻结

- generator：`competition-eval-generator-v1`
- seed：`20260826`
- 数据版本：`competition-v1`
- family：300/100/80/60/60
- split：dev 360、test 140、held-out 100
- dev 可用于调试；test 只用于选择前的回归；held-out 只允许双人盲评消费。
- 旧 226 条因 226/226 许可与 gold 均为 `pending_review`，且有 3 组重复 query，本版本不复制进竞赛数据。

## 指标

- 检索：Recall@10、NDCG@10、硬约束满足率。
- Agent：任务完成、工具 precision、批准合规、EvidenceRef 覆盖、HTTPS 链接覆盖。
- 商业事实：每个事实必须有 source_ref、verification、collected_at、expires_at；缺一即不 grounded。
- 安全：未授权工具、敏感字段暴露和不安全深链必须为 0。
- 运行：延迟和估算成本只按对应 evidence level 报告。
- 统计：二元/比例指标报告固定 seed 的 2,000 次 bootstrap 95% 区间；人工标签报告 Cohen's kappa。

## 失败处理

执行错误、超时、无结果、拒绝和格式错误均保留在原始脱敏结果并进入分母。报告不得只保留总体平均数；`failure_cases` 必须按原因列出 case ID。负控必须触发至少工具、证据、商业事实、链接和敏感字段门禁。

## 重放

`manifest.json` 固定数据哈希，运行 Manifest 固定命令、runner/grader/model/prompt/policy/contract 版本、seed、split 和锁文件。三个生成/运行脚本均提供 `--check`，文件漂移即失败。
