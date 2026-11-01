# V2-EVAL-01 易错点

- dev 可调试，test 用于回归，challenge 不得参与提示或策略调参。
- Reference runner 只证明 grader 自洽，不证明真实模型质量。
- 检索命中不能证明报价真实；商业事实仍必须有来源和有效期。
- 超时、无结果、拒绝、非法 Schema 和恢复失败必须进入分母。
- 不重新引入人工 review queue、人工 gold 或 LLM-as-judge 隐式门禁。
