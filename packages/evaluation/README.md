# Evaluation

提供冻结的 EvalCase/EvalResult、商业事实与工具策略 grader、95% bootstrap 区间、Cohen's kappa 和确定性 reference runner。

Reference runner 只用于证明评测契约、失败分母、负控和重放有效，不调用真实模型，也不生成 held-out 或 LIVE 质量声明。真实模型适配器必须输出相同 EvalResult，并把失败、超时和无结果全部保留在分母中。
