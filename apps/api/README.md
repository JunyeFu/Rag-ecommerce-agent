# API application

FastAPI 薄组合根，公开统一的媒体、线程、Turn、Agent 事件/决策、报价、
安全外跳、清单和购物车契约。路由只做认证主体、所有权、大小、幂等和
协议映射；Agent 编排与商业事实分别通过 `TurnService` 和 `CommercePort`
注入。

默认导出的 `app` 只开放健康检查，业务端口未配置时明确返回 `503`，不会
以 fixture 冒充生产能力。开发环境可注入内存适配器；跨进程幂等和 SSE
重放使用 `PostgresTurnIndex` 与 Agent PostgreSQL checkpointer。

```powershell
uv run python scripts/export_openapi.py --check
uv run python scripts/generate_contracts.py --check
uv run pytest apps/api/tests -q
```

`X-User-ID` 仅为开发身份适配器。生产认证、共享限流、对象存储生命周期和
受信代理配置仍是外部门禁。
