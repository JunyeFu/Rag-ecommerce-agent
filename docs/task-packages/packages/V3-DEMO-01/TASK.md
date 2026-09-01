# V3-DEMO-01 一键演示与面试资产

## 目标
交付干净机器一键演示、APK、证据与讲解材料。
## 状态
`complete`
## 范围
- Compose、导入、索引、健康检查、五分钟演示和系统设计材料。
## 非目标
- 不发布应用商店或公网生产环境。
## 前置依赖
- `V3-QUALITY-01`。
## 路径所有权
- `scripts`、`infra`、`docs/demo`、`docs/architecture`。
## 现状证据
- 2026-08-31：从空 Docker 数据卷启动后，API、Worker、Ops 与四项基础设施均健康；Pixel_9 通过 adb reverse 连接本机回环 API，8 个黄金任务真实完成。全新 checkout 的依赖引导仍待验收。
## 执行步骤
1. 一键启动。2. 10 场景。3. 证据包。4. 演示与面试材料。
## 数据引用
- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`
## 验收
- [x] clean machine 一条命令完成依赖引导和快速验证；空数据卷演示栈一条命令启动全部服务。
- [x] APK 与演示材料可复核。
## 回滚
- 回滚演示编排和文档，不删除数据卷或证据。
## 停止条件
- 依赖真实联盟凭据或宣称 RELEASE 时停止。
## 交接格式
- 结果、路径、验证、外部门禁、下一包。
