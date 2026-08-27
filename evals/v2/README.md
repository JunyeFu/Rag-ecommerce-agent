# Competition evaluation V1

本目录冻结 600 条项目自生成评测用例：300 购物、100 多轮、80 多模态、60 报价故障和 60 安全/隐私。`dev/test/heldout` 固定为 360/140/100。

- `public-cases.v1.jsonl` 是可由本地 runner 消费的 500 条 dev/test。
- `heldout/review-queue.v1.jsonl` 只有盲态任务与 rubric 引用，不含 expected gold；本地 runner 明确拒绝该 split。
- `manifest.json` 固定 generator、seed、文件哈希、split 消费范围和事实声明。
- `results/deterministic-reference-*` 只验证 grader、分母、重放和负控，不是模型质量得分。
- `results/ablation-report.json` 只使用许可/gold 待审的旧开发种子，不是 held-out、LIVE 或生产 embedding 结论。

评测队列在仓库内可见，因此属于流程隔离的 blinded split，不是由外部系统加密封存的秘密测试集；外部封存和双人盲评仍是硬门禁。
