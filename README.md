# RAG Commerce Shopping Agent V2

这是 `D:\Agent\04-rag-ecommerce` 的独立重开发仓库。当前 13 个任务包中，11 个本地可自主包已完成，`V2-LIVE-01` 与 `V2-RELEASE-01` 因真实权限/人工/签名/发布门禁处于 `blocked`；正式发布结论为 `NO-GO`。

## 冻结决策

- 产品：多商家 B2C RAG 电商导购 Agent。
- 客户端：原生 Android + Web 运营台。
- 导航：导购 / 清单 / 购物车 / 我的。
- 交易：聚合授权商品源的报价与深链，跳转商家成交；平台不托管支付、订单、退款或履约。
- 数据：官方/联盟 API、授权 Feed、搜索发现三级分流，禁止绕过验证码、访问控制或站点条款采集。
- 迁移：不继承旧仓 Git 历史，不迁移用户、会话、支付或订单数据；旧商品与评测数据只能通过带来源和哈希的导出包进入 V2。

## 权威入口

- 重开发基线：`docs/baseline/V2-REDEVELOPMENT-BASELINE.md`
- 任务包清单：`docs/task-packages/manifest.json`
- 任务执行规范：`docs/task-packages/README.md`
- 基线验证证据：`docs/task-packages/evidence/baseline-verification.json`
- 共享业务数据：`docs/task-packages/shared/business-data.json`
- 共享开发数据：`docs/task-packages/shared/development-data.json`
- 通用易错点：`docs/task-packages/shared/pitfalls.md`

## 工程入口

- Python：3.12.11 + uv，配置与锁位于 `pyproject.toml`、`uv.lock`。
- Web：Node 24.15.0 + npm 12.0.1，依赖锁位于 `package-lock.json`。
- Android：JDK 17、Gradle 8.9、AGP 8.7.0、Kotlin 2.0.21。
- 本地服务：`infra/compose.yaml`，仅绑定回环地址并使用开发态身份。
- 公共契约：`packages/contracts/openapi.json` 与 `packages/contracts/schemas/`。

模块边界见 `docs/adr/0001-monorepo-module-boundaries.md`。`complete` 只能表示任务包声明范围内的本地实现与验证已完成，不能替代联盟接口授权、法律审查、真实提供方评测、物理真机或商业发布验收。

当前本地已实现数据导出、领域模型、授权连接器边界、可溯源 RAG、类型化 Agent、统一 REST/SSE API、Android、运营台、600 条评测体系和本地安全闭环。fixture、参考构造器、模拟器和本地集成均不构成 LIVE_E2E；当前门禁矩阵见 `docs/live/readiness.json` 与 `docs/release/release-gate-matrix.json`。

## Bootstrap 与验证

Windows：

```powershell
.\scripts\bootstrap.ps1
```

Linux/macOS：

```bash
./scripts/bootstrap.sh
```

快速迭代（跳过 Web、Android 与 Compose）：

```powershell
uv run python scripts/verify_local.py --quick
```

完整本地验证：

```powershell
uv run python scripts/verify_local.py
```

任务包结构验证仍可独立执行：

```powershell
python scripts/validate_task_packages.py
```

重新采集旧仓只读基线：

```powershell
python scripts/capture_source_baseline.py `
  --source D:\Agent\04-rag-ecommerce `
  --output docs\baseline\source-snapshot.json
```

禁止自动暂存、提交、推送或修改旧仓。
