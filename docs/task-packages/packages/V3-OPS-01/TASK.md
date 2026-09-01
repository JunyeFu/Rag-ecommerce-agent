# V3-OPS-01 真实运营 API 控制台

## 目标
运营台不再读取静态 ops-data，并持久化受控操作。
## 状态
`complete`
## 范围
- 生成类型、TanStack Query、冲突、Trace、评测、门禁与审计。
## 非目标
- 不实现生产 SSO/RBAC。
## 前置依赖
- `V3-ANDROID-01`。
## 路径所有权
- `apps/ops-web`、Ops API 与持久化适配器。
## 现状证据
- 2026-08-31：隔离 fixture API（`127.0.0.1:8080`）与 Ops Vite（`127.0.0.1:24174`）已验证。冲突 `conflict-001` 合并及评测 `eval-queued-002` 入队在页面重新加载后仍由 API 返回。
## 执行步骤
1. 移除静态读取。2. 查询 API。3. 写操作幂等。4. 浏览器恢复测试。
## 数据引用
- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`
## 验收
- [x] 无 `ops-data` 运行时导入。
- [x] 五个真实浏览器工作流和刷新恢复通过。
## 回滚
- 回滚 Query Client 与 API 接入，不伪造本地成功状态。
## 停止条件
- 页面以本地 setState 冒充持久化时停止。
## 交接格式
- 结果、路径、验证、外部门禁、下一包。
