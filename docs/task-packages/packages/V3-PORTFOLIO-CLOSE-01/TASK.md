# V3-PORTFOLIO-CLOSE-01 求职作品集收口

## 目标
把 `RAG Commerce Shopping Agent V3` 收口为唯一可公开复核的 GitHub 求职入口，并在全部作品集门禁通过后标记 `PORTFOLIO_READY=GO`。

## 状态
`blocked`：MiMo `run-009` 已通过；等待远端 CI、main 合入、Release 与匿名访问验证。

## 范围
- 删除无生产调用者的旧 UI、静态 Ops 数据、连接器通用韧性占位和旧 seed 运行输入。
- 固定 MiMo `mimo-v2.5` 十场景单次真实评测入口，分离真实与 fixture 证据。
- 建立 MIT 许可、公开 README、精选媒体、演示 APK、发布矩阵和 GitHub Release。

## 非目标
- 不实现联盟 LIVE、生产部署、支付订单、物理设备门禁或 100 条双人盲评。
- 不增加模型回退、通用重试、供应商注册中心或公共 API 0.1.0 兼容层。

## 前置依赖
- `V3-DEMO-STORY-01`。

## 路径所有权
- 根 README/LICENSE、`docs/media`、`docs/release`、真实评测脚本及本任务包。

## 现状证据
- 当前工作树冻结信息见 `data.json`；删除面由 `scripts/check_minimality.py` 精确约束。
- 真实 MiMo 状态与本地/远端验证结果见 `evidence/verification.json`。

## 执行步骤
1. 冻结并分类脏工作树。2. 完成最小化清理与单一 V3 数据链。3. 运行全套本地和干净检出验证。4. 执行 MiMo 十场景评测。5. 形成四个可审阅提交。6. 推送 PR、等待 CI、合入 main。7. 从合入 SHA 发布固定资产并匿名复核。

## 数据引用
- `../../shared/business-data.json`
- `../../shared/development-data.json`
- `../../shared/pitfalls.md`

## 验收
- [x] MiMo 10/10 可解析、工具 Schema 100%、预期流程至少 8/10、推荐证据 100%、未授权写入与商业事实伪造均为 0。
- [x] Python、集成、契约、Ops、Android、任务包、安全和 diff 门禁通过。
- [ ] PR CI 全绿并以 merge commit 合入 main。
- [ ] `v0.3.0` Release 的 APK、MP4、截图包、证据摘要和校验和均可匿名下载。
- [ ] 仅在以上条件全部满足后写入 `PORTFOLIO_READY=GO`。

## 回滚
- 发布前撤销本包的显式路径提交；发布后通过新提交与新 Release 修正，不重写公开历史。

## 停止条件
- 真实凭据不可用、真实评测未达门槛、远端 CI 未全绿或发布资产不可匿名访问时停止 GO 声明。

## 交接格式
- main 合入 SHA、PR、Release、真实/fixture 指标、资产 SHA-256、商业发布边界和未完成门禁。
