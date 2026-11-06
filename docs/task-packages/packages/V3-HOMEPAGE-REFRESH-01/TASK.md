# V3-HOMEPAGE-REFRESH-01 商业审美 GitHub 主页

## 目标
合并已验收修复，并把 README 改为产品价值、实际体验和可核验实测驱动的正式展示首页。

## 状态
complete（首页内容及GitHub分支渲染的本地验收）；最终合并与远端检查以PR记录为准。

## 范围
README 视觉层级、产品与证据文案、导航、历史与当前结果分区；GitHub 桌面/移动实际渲染检查及授权合并。

## 非目标
不改应用功能、不新增模型/设备/容量实验、不部署、不恢复外部验收、不创建 Release。

## 前置依赖
V3-REMEDIATION-CLOSE-01 complete；PR28 已五项 CI 通过并依用户明确授权合并到 main（43220a7）。

## 路径所有权
README.md、本包全部文件、docs/task-packages/manifest.json；复用既有 docs/media 素材，不修改截图或素材。临时验证脚本与截图放在 D:/C-drive-temp-20261028/new-temp/rag-homepage-20261106/，不提交。

## 现状证据
现有 README 含完整技术取舍及历史实测，顶部到下部混有审查流水；11月6日修复 CI300通过/7跳过、TLS另跑6通过，商业发布仍NO_GO。

## 执行步骤
重排产品、截图、指标和技术选择；验证链接及统计；推送分支/PR；实际 GitHub 桌面/手机检查与修正；CI通过后合并并回读main。

## 数据引用
现有 github-cover.svg 和 Android/Ops 截图、AGENT-PERFORMANCE.md、agent-metrics-20261105.json、TECH-STACK-DECISIONS.md、PR28最终CI。

## 验收
已验收修复PR28进入main；新版首页首屏层级清楚，桌面/手机图片及导航/展开可用，链接有效，实测口径与技术取舍保留，达到授权合并的准备状态。本包complete仅覆盖内容与分支页面验收；首页最终合并及远端CI在GitHub PR记录核验。

## 回滚
保留Git历史和独立分支，不覆盖用户无关改动，不reset/clean/prune。

## 停止条件
首页合并及GitHub回读完成；外部验收继续暂停。

## 交接格式
合并链接、CI、渲染验证范围、实际截图和剩余发布门禁。
