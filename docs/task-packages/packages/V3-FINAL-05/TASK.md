# V3-FINAL-05 独立复审与求职封版

## 目标
执行用户批准的一次长执行实习投递收口方案，AI应用实习为主，全栈证据为辅。

## 状态
in_progress；810文件初步独立启动和24题/4稿/8类材料导出已验证，最终同版APK/媒体/独立复审未签收，不能继承历史Release GO。

## 范围
独立复审与求职封版。仅声明路径内实施必要修改。

## 非目标
2026-11-01 用户已授权按本地最新进展整理并提交推送 GitHub main；不创建 Release 或部署；不做支付、订单、多Agent、生产身份或自动价格监控。

## 前置依赖
V3-FINAL-04。

## 路径所有权
2026-11-01 仓库同步增量：汇总现有各包源码、测试和证据改动；新增整理仅涉及 README.md、docs/README.md、docs/release/local-portfolio.json、本包证据及 .gitignore。原包实现归属保持不变。本次检查发现既有 Ruff 导入/格式错误与安全报告漂移，允许在对应 apps/、scripts/、pyproject.toml 及 docs/security/evidence/ 中做最小规范修复。
2026-10-13求职资料同步包含现有docs/architecture/V3-C4.md与V3-AGENT-SEQUENCE.md，准确反映11工具、媒体确认、冻结审批、JSONL商品源、报价持久化和Redis未接入主链；保持Mermaid格式。
README.md；docs/demo/、docs/media/、docs/project/、docs/release/local-portfolio.json；scripts/export_portfolio_candidate.py、scripts/verify_clean_candidate.py；本包证据。外部导航records/rag-commerce/closeout与sites/rag-commerce/public/closeout及现有页面，保留.local。

## 现状证据
FINAL-01/evidence/current-state.json及docs/defects/V3-FINAL-CLOSEOUT.md；历史报告保留原分母。

## 执行步骤
1. 独立对照PRD、源码、测试和缺陷表复审。
2. 导出显式源码清单，独立环境复验。
3. 产出APK、约90秒视频、精选截图与证据摘要。
4. 更新README与外部导航，发布保持NOT_PERFORMED。

## 数据引用
自有60SKU、DEMO_FIXTURE、固定BGE revision、当前PRD、24+6场景槽位。

## 验收
- 独立目录与数据库从头启动并演示
- APK/视频/截图/指标对应同一候选源码
- 24问答、四稿及八类材料有实际项目依据

## 回滚
仅撤销本轮具体行级变更，保留用户已有改动与数据；不使用reset或clean。

## 停止条件
真实凭据/额度、必要设备或基础设施阻塞时停止相关路径；其余独立工作继续。不自动增加付费调用。

## 交接格式
命令、时间、退出码、数量、失败摘要、证据等级、当前候选状态及剩余门禁。
