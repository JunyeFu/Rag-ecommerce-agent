# V3-CONTRACT-01 公共契约 0.2.0

## 目标
交付无 0.1 兼容层的类型化 Agent 公共契约。
## 状态
`complete`
## 范围
- ThreadSnapshot、ProductView、类型化 SSE、DEMO_FIXTURE、三端生成类型。
## 非目标
- 不保留未发布 0.1 客户端兼容。
## 前置依赖
- `V3-BASE-00`。
## 路径所有权
- `packages/contracts`、API 契约路由、生成脚本。
## 现状证据
- OpenAPI 共 23 个路径且生成检查通过。
## 执行步骤
1. 写契约红测。2. 扩展模型与事件。3. 重生成。4. 漂移校验。
## 数据引用
- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`
## 验收
- [x] Python/Kotlin/TypeScript 生成确定。
- [x] 结构化结果不进入 message_delta。
## 回滚
- 回滚 0.2 生成物与对应路由，不添加兼容层。
## 停止条件
- 三端生成结果漂移时停止。
## 交接格式
- 结果、路径、验证、外部门禁、下一包。
