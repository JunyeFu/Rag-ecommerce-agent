# V2 Development Task Packages

本目录把重开发方案转为可排期、可验证、可交接的任务 DAG。

## 状态

- `planned`：边界已定义，尚未开工。
- `in_progress`：依赖已满足且正在执行。
- `blocked`：同一外部阻断已被证实，不能在本地继续推进。
- `complete`：任务包声明范围内的实现与验证均有证据；外部门禁仍单独保留。

## 固定结构

每个包必须包含：

- `TASK.md`：目标、范围、非目标、依赖、所有权、步骤、验收和停止条件。
- `data.json`：输入、输出、测试配置、业务数据与风险引用。
- `pitfalls.md`：该包特有易错点。
- `evidence/verification.json`：实际命令、退出码、结果数量、失败摘要和外部门禁。

## 执行流程

1. 验证 manifest、依赖 DAG、路径和共享数据。
2. 读取当前包及其全部依赖证据。
3. 确认路径所有权和外部输入。
4. 仅实现当前包范围。
5. 运行包内验证以及全局任务包验证。
6. 更新 evidence；只有成功后才将 manifest 状态改为 `complete`。
7. 不自动暂存、提交、推送或部署。

## 验证命令

```powershell
python scripts/validate_task_packages.py
```
