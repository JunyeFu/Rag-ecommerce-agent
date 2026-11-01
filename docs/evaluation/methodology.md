# RAG Commerce 自动化评测方法

## 证据层级

1. `deterministic_contract_reference_only`：验证用例 schema、grader、失败分母、哈希与重放。
2. `local_runtime`：使用本地 BGE、Qdrant、真实工具和持久化链执行冻结场景。
3. `provider_sandbox`：固定 provider/model/prompt 版本执行自动化 dev/test/challenge。
4. `LIVE`：真实授权报价、真实流量和物理终端证据，不属于本测试集。

不同层级不得合并成一个“总分”。确定性 reference 的 100% 只说明期望构造器和 grader 相容，不说明 Agent、RAG 或真实报价达到质量目标。

## 数据冻结

- generator：`competition-eval-generator-v2`
- seed：`20260921`
- 数据版本：`competition-v2`
- family：120/120/100/80/120/100/100/80/80/100，共 1,000 条。
- split：dev 600、test 250、challenge 150。
- dev 可用于调试；test 用于选择前回归；challenge 只用于最终自动门禁，三者都具备机器 gold。
- 旧 600 条含人工盲评队列的 competition-v1 已退役，不再作为运行或发布门禁。

## 指标

- 检索：Recall@10、NDCG@10、硬约束满足率。
- Agent：任务完成、工具 precision、批准合规、EvidenceRef 覆盖、HTTPS 链接覆盖。
- 商业事实：每个事实必须有 source_ref、verification、collected_at、expires_at；缺一即不 grounded。
- 安全：未授权工具、敏感字段暴露和不安全深链必须为 0。
- 运行：延迟和估算成本只按对应 evidence level 报告。
- 统计：二元/比例指标报告固定 seed 的 2,000 次 bootstrap 95% 区间。

## 失败处理

执行错误、超时、无结果、拒绝和格式错误均保留在原始脱敏结果并进入分母。报告不得只保留总体平均数；`failure_cases` 必须按原因列出 case ID。负控必须触发至少工具、证据、商业事实、链接和敏感字段门禁。

## 重放

`manifest.json` 固定数据哈希，运行 Manifest 固定命令、runner/grader/model/prompt/policy/contract 版本、seed、split 和锁文件。三个生成/运行脚本均提供 `--check`，文件漂移即失败。

## 前台运行时

`npm run test:agent:e2e` 使用 Playwright APIRequestContext 启动真实 Agent fixture API，不启动 Ops 前台也不使用网络 Mock：

- 简单：单轮 Mission 完成 RAG 检索、事实读取、报价、比较和带 EvidenceRef 的推荐。
- 中度：模糊需求触发澄清，补充预算后恢复；同时验证 Mission 合并、幂等重放和 Last-Event-ID 恢复。
- 重度：并发执行 10 个黄金购物任务，再完成商品事实、报价、清单、待购、HTTPS 链接解析和用户隔离闭环。

`npm run test:ops:e2e` 只作为运营台独立回归，不计入 Agent 三档结论。Agent 三档使用项目自有商品与 `DEMO_FIXTURE` 报价，验证真实 AgentRuntime/RAG/工具/API 链，不替代真实模型 challenge 指标或性能压测。
