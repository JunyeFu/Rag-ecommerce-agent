# V3-HOMEPAGE-REFRESH-02 新前端商业主页

## 目标
按新版前端更新GitHub商业宣传主页，采用真实浅暗截图、简洁价值文案和分层证据。

## 状态
in_progress

## 范围
README、品牌SVG、2026-11-06实测展示素材、素材清单、独立预览说明与本包验证；更新GitHub主页。

## 非目标
不提交应用源码、不部署、不创建Release、不重跑模型或硬件验收。

## 前置依赖
V3-HOMEPAGE-REFRESH-01 complete；新版Android/Ops本地证据可用。应用源码仍为开发分支预览，公开素材据此标注。

## 路径所有权
README.md、docs/media/github-cover.svg、docs/media/manifest.json、docs/media/frontend-20261106/、docs/evaluation/FRONTEND-PREVIEW-20261106.md、docs/evidence/v3/frontend-preview-20261106.json、本包与manifest；承接前主页包在此范围的历史所有权。QA复用output/playwright/homepage-refresh-20261106。

## 现状证据
主页仍使用旧霓虹配色和10月截图；本地已有11月6日浅暗原生与Ops实测素材，商业发布仍HOLD。

## 执行步骤
替换主视觉和实测截图；更新体验及验证说明；检查链接/指标；GitHub分支桌面手机渲染；授权合并及回读。

## 数据引用
Android A01-A09本地修复68单元/76原生、浅暗两次本地HTTP/SSE；Ops既有设计规范验收。历史模型性能保留原日期。

## 验收
截图均来自实际运行，手机与桌面可读，锚点/展开有效，历史性能不被当前UI验证覆盖，发布边界明确。

## 回滚
保留分支与PR历史；不覆盖既有未提交应用改动，不reset/clean。

## 停止条件
主页更新与渲染检查完成，记录GitHub交付结果；整体外部HOLD保持。

## 交接格式
主页/PR链接、截图与验证范围、剩余外部门槛。
