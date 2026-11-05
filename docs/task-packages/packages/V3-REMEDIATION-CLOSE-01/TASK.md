# V3-REMEDIATION-CLOSE-01 修复分支与远端验收收口

## 目标
将十题修复及第二批补验发布到授权分支和草稿 PR，完成当前候选的远端 CI，列清整个项目仍需外部输入的待办。

## 状态
in_progress

## 范围
授权分支提交、推送、草稿 PR；现有 CI 的隔离 TLS 测试覆盖；远端失败的必要修复；当前状态和待办证据。

## 非目标
不合并 main、不部署、不启用 LIVE、不增加付费模型重测、不替代真机、法律或人审签收。

## 前置依赖
V3-INTERVIEW-REPAIR-02 已 complete。用户明确授权 codex/complete-agent-remediation 分支提交、推送和草稿 PR。

## 路径所有权
本包、docs/task-packages/manifest.json、.github/workflows/ci.yml、README.md、docs/evaluation/AGENT-REMEDIATION-CLOSE-20261106.md、docs/evaluation/AGENT-INTERVIEW-REPAIR-STATUS-20261105.md（追加当前状态链接）、output/remediation-close-20261106/。上一批源码只在本包记录具体远端失败与必要路径扩展后修改；既有报告与失败证据保留。

## 现状证据
本地分平台回归已通过，最新已提交版本的远端 CI 失败；修复尚未提交。六项真实 TLS 测试需要无外网的 Linux 网络命名空间，普通测试会跳过，需要独立 CI job 实际执行。

## 执行步骤
补齐隔离 TLS job；确认生成产物及任务校验；发布授权分支和草稿 PR；跟进并修复远端失败；记录同版 CI 结果和剩余输入。

## 数据引用
V3-INTERVIEW-REPAIR-01/02 验证记录、本包 evidence/verification.json、当前 PR 与 Actions run。

## 验收
授权分支与草稿 PR 可审阅；同一源码候选的全部 CI job 通过，隔离 TLS 六项实际执行；状态文档区分当前证据、历史证据与外部门禁。

## 回滚
保留独立分支和草稿状态，不改 main；不 reset/clean/prune，不删除原始失败记录和测试数据。

## 停止条件
本包远端验收完成；全部项目目标仍受真实联盟、真机、人声和发布批准等独立输入约束。

## 交接格式
PR、Actions、验证命令/时间/退出码/数量/失败摘要、尚需输入的逐项待办。
