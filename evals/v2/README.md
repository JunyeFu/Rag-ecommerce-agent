# Competition evaluation V2

本目录冻结 1,000 条项目自生成、可全自动判分的评测用例。不存在人工盲评 split、review queue 或人工 gold。

- `cases.v2.jsonl`：全部 dev/test/challenge 用例及机器规则 gold。
- split 固定为 dev 600、test 250、challenge 150；只有 dev 可用于调试，challenge 只用于最终自动门禁。
- 十个家族覆盖精确检索、语义检索、冲突澄清、无结果、多轮约束、审批写入、报价证据、多模态、恢复并发和安全攻击。
- `manifest.json` 固定生成器、seed、文件哈希、家族与 split 数量。
- `results/deterministic-reference-*` 只验证 grader、分母、重放和负控，不代表真实模型质量。

所有用例由项目生成并携带 `expected`，可由同一 grader 重放。真实 Provider 报告必须另外保存，不能使用 reference fixture 指标代替。
