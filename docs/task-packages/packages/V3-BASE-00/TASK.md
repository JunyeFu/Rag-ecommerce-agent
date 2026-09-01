# V3-BASE-00 Agent-first 基线

## 目标
冻结 V3 产品、证据和版本边界。
## 状态
`complete`
## 范围
- V3 基线、任务 DAG、旧仓只读边界。
## 非目标
- 不声明 LIVE 或 RELEASE。
## 前置依赖
- V2 工程基线。
## 路径所有权
- `docs/baseline`、`docs/task-packages`。
## 现状证据
- `docs/baseline/V3-AGENT-FIRST-BASELINE.md`。
## 执行步骤
1. 冻结范围。2. 登记任务。3. 校验 DAG。
## 数据引用
- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`
## 验收
- [x] V3 边界与非目标可机器校验。
## 回滚
- 仅移除 V3 基线与 V3 任务条目。
## 停止条件
- 旧仓发生写入时立即停止。
## 交接格式
- 结果、路径、验证、外部门禁、下一包。
