# V3 五分钟演示脚本

## 演示前置

```powershell
.\scripts\bootstrap.ps1 -Quick
.\scripts\start_v3_demo.ps1
```

Android debug 使用 `http://10.0.2.2:8080/`；Ops 使用 `http://127.0.0.1:24174/`。本演示身份、商品、报价和商家链接均为本地 fixture，不需要联盟凭据。

## 八镜头现场路线

| 时间 | 镜头 | 现场操作 | 预期观察 | 证据与状态 |
|---|---|---|---|---|
| 00:00–00:25 | 启动与边界 | 展示启动命令和健康结果 | PostgreSQL、Qdrant、Redis、MinIO、API、Worker、Ops 可用；迁移到 `20260831_0007` | LOCAL/INTEGRATION；不是 LIVE |
| 00:25–00:55 | 购买任务 | Android 输入“通勤降噪耳机” | Agent 只追问一个必要条件，不出现商品卡 | `clarification_required`、`WAITING_CLARIFICATION` |
| 00:55–01:25 | 澄清与 RAG | 回答“预算上限 1500 元” | 回答合并进原 Mission；公开显示理解、检索、核验和比较阶段 | BM25 + 向量 + 过滤 + RRF；不展示思维链 |
| 01:25–02:05 | 证据推荐 | 查看主推荐并纵向滑到次推荐、再次推荐 | 每屏一个候选，显示匹配、不满足项、风险、EvidenceRef 和 `DEMO_FIXTURE` 报价 | Android/API/Worker/SSE 真实状态 |
| 02:05–02:35 | 比较决策 | 保存候选、加入待购并打开“决策” | Agent 结论、取舍、风险、清单和待购由 API 状态驱动 | 不含支付、订单或自动购买 |
| 02:35–03:10 | 审批与外跳 | 发起重新询价，检查目标域名，确认动作 | 原生审批面板先出现；确认后只打开未来有效的 HTTPS 演示链接 | 可逆、幂等；真实联盟深链 BLOCKED |
| 03:10–03:45 | 故障恢复 | 断开连接或强停应用后重新打开 | 从 ThreadSnapshot、checkpoint 与最后事件游标恢复，无重复 terminal event | RECOVERED/RECONNECTING；Worker 过期租约可回收 |
| 03:45–04:35 | Ops 与门禁 | 打开运行概览、检索观测、Trace、评测、发布门禁 | 检索命中、EvidenceRef、Token、成本、游标可见；刷新后评测排队保持；LIVE/HUMAN 明确阻塞 | fixture/local/REAL_MODEL/HUMAN/LIVE/RELEASE 分层 |

04:35–05:00 用于总结：本地黄金场景、契约和恢复已经实测；真实模型公开集评测、100 条 held-out 双人盲评、联盟 LIVE 报价、物理设备验收和 RELEASE 未由 fixture 代替。

## 异常备用路线

- Android 暂时离线：展示已恢复快照和“重新连接”，随后恢复 API。
- 模拟器不可用：使用 `apps/api/tests/test_demo_flow.py` 展示澄清、Mission 合并、RAG、EvidenceRef、待购与安全链接的公共 API 证据。
- Ops 页面不可用：展示 PostgreSQL Ops 重启回归和 `output/playwright/` 浏览器证据；不得将截图称为 LIVE_E2E。

## 二十分钟讲解映射

八个镜头依次映射到 `V3-SYSTEM-DESIGN-INTERVIEW.md` 的问题定义、领域、RAG、Agent、平台、客户端、Ops 和质量门禁章节。
