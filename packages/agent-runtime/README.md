# Agent runtime

`ShoppingAgent` 是文本、媒体、API 和评测共用的唯一运行时。模型只能输出
冻结的类型化工具调用；注册表负责参数 Schema、风险、授权和执行边界，
PostgreSQL store 负责 checkpoint、公开事件重放和领域审计记录。

本地确定性验证：

```powershell
uv run pytest packages/agent-runtime/tests -m "not integration" -q
uv run python scripts/generate_agent_artifacts.py --check
```

真实模型提供方、生产凭据和 live 商业质量不属于本地完成声明。
