# V3-RECOVERY-EXPERIENCE-01 离线与恢复体验（小层 06）

## 目标
确认断网、SSE 中断、Worker 重启和 Android 进程恢复时，用户能够理解任务保存位置、恢复进度和继续入口，同时不生成任何离线新事实。
## 状态
`complete`
## 范围
- 任务页原位呈现 `offline`、`recovering`、`recovered` 和 `failed`，保留同一 Mission、候选身份和已确认写入。
- 恢复状态展示最近安全进度、快照校验、事件续接和是否出现重复终态。
- 提供重试连接、继续任务和查看恢复详情三个与状态匹配的操作。
## 非目标
- 不在离线时制造新报价、新候选、新证据或新终态；不通过清空任务或新建 Thread 伪装恢复成功。
## 前置依赖
- `V3-PLATFORM-CONTROL-01`、`V3-PLATFORM-01`、`V3-ANDROID-01`。
## 路径所有权
- SSE/ThreadSnapshot 恢复相关 Android 表达及本包预览证据。
## 现状证据
- 小层 05 已确认；API 游标、ThreadSnapshot 和 Android recovered 状态已有实现，当前需要冻结面向用户的连续恢复证据。
## 执行步骤
1. 生图。2. 用户确认。3. 注入断网、SSE 中断和 Worker/进程重启。4. 验证快照、游标、幂等和 UI 连续性。
## 数据引用
- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`
## 验收
- [x] 用户确认预览和页面职责。
- [x] 重连无丢失、乱序或重复终态，心跳不推进业务状态。
- [x] Mission、候选身份、已保存方案和审批状态在恢复前后稳定。
- [x] 离线期间不生成商品、报价或证据事实。
## 回滚
- 回滚恢复提示层，不清理用户任务数据。
## 停止条件
- Docker/数据库不可运行、快照与事件无法对账或恢复要求覆盖历史事件时停止。
## 交接格式
- 预览、故障场景、游标、测试证据、环境门禁。
