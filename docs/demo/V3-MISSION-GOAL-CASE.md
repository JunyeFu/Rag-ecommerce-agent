# 工程案例：操作文本不等于购物目标（F62）

## 用户看到什么

用户已完成“预算2000元的通勤手机”推荐，再请求把某个报价以数量2加入待购。操作完成后，任务页却显示预算和品类待确认。真实持久Thread仍保存原购买目标，Mission却变成了待购操作文本。

## 根因

`runtime.py`用Turn请求文本生成`mission_updated`；`service.py`快照又信任同版本的该事件。购物目标与后续操作属于两个不同语义，却共用一个字符串，版本没有变化也不能证明语义一致。

## 最小修复

私有RunCommand增加`mission_goal`，API在事务预留任务时绑定权威Thread目标；模型仍接收原操作请求，冻结工具参数和审批不变。快照从Thread构建Mission，SSE投影使用同一权威目标。旧私有命令按真实Thread当前版本读取目标，不重写旧事件，也不引入公共0.1兼容层。

## 验证与边界

- 回归先观察到目标被待购文本覆盖，再修复；当前全套Python218项/0skip通过，真实PG进程重建测试3项通过。
- 重载API/Worker后，只读核对原真实任务：COMPLETED、预算200000分、手机1、未知字段为空；原待购数量仍为2。
- 原生恢复页面显示总预算¥2000；没有新模型调用、重复批准或补造成功状态。
- Python/Kotlin/TypeScript公共契约仍为0.2.0，生成类型检查通过；完整最终同版封版尚未签收。

代码：`packages/agent-runtime/src/ragcommerce_agent_runtime/runtime.py`、`contracts.py`；`apps/api/src/ragcommerce_api/service.py`、`postgres_index.py`、`app.py`。

测试：`apps/api/tests/test_mission_goal_context.py`及真实PostgreSQL快照/审批恢复集成测试。

实际报告：[F62验证](../evidence/v3/final-F62-mission-goal-review-20261013.json)。个人贡献与AI辅助实施范围由本人确认，本案例不代签“独立完成”。
