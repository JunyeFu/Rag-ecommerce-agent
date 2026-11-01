# Competition V2 自动化测试集报告

## 数据设计

- 共 1,000 条项目自生成、机器可判分且 query fingerprint 唯一的用例。
- dev/test/challenge 固定为 600/250/150；challenge 不参与调参。
- 十类覆盖：精确检索 120、语义检索 120、冲突澄清 100、无结果 80、多轮约束 120、审批状态 100、报价证据 100、多模态 80、恢复并发 80、安全 100。
- 所有 split 均包含冻结 `expected`；旧人工 held-out 队列、rubric 和一致性门禁已取消。

## 自动判分范围

- 任务 outcome、工具 precision、必需工具 recall、证据覆盖率。
- 商业事实 grounded precision、审批合规、HTTPS 链接与敏感字段暴露。
- 错误、超时、无结果和拒绝全部进入分母。
- reference 构造器只证明 Schema、grader、分母、负控和重放自洽，不作为模型质量分数。

## 仍需独立报告

- 真实 Provider 的 1,000 条执行结果、Token、费用、延迟和失败类型。
- LIVE 联盟报价、真实流量、物理终端和生产安全/法律批准。

因此当前可以声明“全自动竞赛测试集与确定性判分框架已建立”，不能用 reference fixture 结果替代真实 Agent 或商业质量。
