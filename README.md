<p align="center">
  <img src="docs/media/github-cover.svg" alt="RAG Commerce — 从想买什么，到知道怎么选" width="100%">
</p>

<h1 align="center">RAG Commerce · 购物决策 Agent</h1>
<p align="center"><strong>说出需求，看懂取舍，由你决定。</strong><br>Android 原生体验，把需求澄清、证据推荐与购买前决策连成一条线。</p>
<p align="center">
  <a href="#产品画廊">查看产品画面</a> ·
  <a href="docs/media/rag-commerce-v3-demo.mp4">观看 87 秒历史演示</a> ·
  <a href="#三条本地启动命令">本地体验</a> ·
  <a href="docs/architecture/V3-C4.md">架构设计</a>
</p>

> **研发展示版 · 非商业上线服务。** 当前候选仍为 **HOLD**，未公开发布；商品与报价为演示数据。下方历史运行截图用于展示交互与视觉设计，不代表当前源码已完成验收。

## 最新进展 · 2026-11-01 同步

- **容量门禁本地通过（10 月 24 日）**：真实 PostgreSQL、双 Worker、本地 BGE，fake 模型，十批 × 30 共 300/300 完成；接受 p95 **182.079 ms**，首状态 p95 **111.482 ms**。[F60 完整结果与历史失败](docs/evidence/v3/final-F60-review-20261024.json)。
- **Android 决策与无障碍增量**：比较、保存、待购连续性，以及两档字号下的 TalkBack 路径；8/8 原生场景为 explicit fake + 内存 API 的限定验收。[验收范围](docs/evidence/v3/android-talkback-20261024.json)。
- **待完成**：有效人声闭环、浏览器首次设置后的完整外跳、最终同版 APK／视频／独立复审；整体 **HOLD**，商业发布 **NO_GO**。

[文档导航与目录说明](docs/README.md) · [最新缺陷记录](docs/defects/V3-FINAL-CLOSEOUT.md) · [交付状态](docs/release/local-portfolio.json)

### 本轮 Android 决策画面

<img src="docs/media/android-ux-native-20261021/default-comparison.png" width="340" alt="2026-10-21 Android 比较工作台：按预算、硬约束和偏好比较候选">

2026-10-21 运行截图，演示商品与报价；与下方历史推荐画面分开标注，不代表最终同版媒体签收。

## 不止给你一张商品列表

| 从需求开始 | 把推荐讲清楚 | 把决定交给你 |
| :--- | :--- | :--- |
| 描述预算、用途与偏好，逐步澄清购买约束。 | 查看推荐理由、约束匹配与报价来源，再比较候选。 | 保存方案或确认加入待购，让下一步建立在明确授权上。 |

## 产品画廊

### 01 / Android · 从推荐到决策

<table>
<tr>
<td width="50%" align="center"><img src="docs/media/android-agent-recommendation.png" width="340" alt="Android 历史运行截图：带理由、来源、演示报价与保存入口的推荐卡片"></td>
<td width="50%" align="center"><img src="docs/media/android-recovery.png" width="340" alt="Android 历史运行截图：任务恢复界面"></td>
</tr>
<tr>
<td><strong>推荐有依据</strong><br>商品、场景匹配、来源与操作集中在同一张卡片中，帮助用户理解推荐。</td>
<td><strong>任务有连续性</strong><br>恢复界面呈现任务状态；恢复能力的具体通过范围见下方分层验收记录。</td>
</tr>
</table>

### 02 / Ops · 看得见的执行过程

![历史 Ops 界面：Agent Trace 工具执行与证据引用，fixture 演示数据](docs/media/ops-agent-trace.png)

**运行轨迹** — 用工具状态、检索命中和证据引用解释执行过程，方便开发与运营定位问题。

<details>
<summary><strong>展开查看发布门禁界面</strong></summary>

![历史 Ops 界面：分层发布门禁，不代表当前门禁通过](docs/media/ops-release-gates.png)

</details>

以上四张画面来自仓库已有的[历史运行素材](docs/media/manifest.json)，包含 fixture 数据；[历史视频](docs/media/rag-commerce-v3-demo.mp4)可下载播放。当前候选视频与最终原生验收尚未签收。

## 为可信决策而设计

- **事实来自证据。** 报价来自 `OfferQuote`，携带来源、采集时间、失效时间与验证级别；发现型候选不参与最低价排序。
- **行动需要授权。** 模型负责规划与解释，执行器负责权限、审批与持久化；首版不包含支付、订单、退款和履约。
- **体验连接工程。** Android 原生前端、持久化任务与增量事件衔接；Ops 提供运行与检索观测入口。

> A native Android shopping agent for evidence-backed recommendations and explicit user decisions. Built with Kotlin / Compose, FastAPI, PostgreSQL and hybrid retrieval.

## Agent 闭环

文字购买与无目标探索共用 Mission；图库图片和原生录音用于理解需求，识别结果要经用户修改确认，不能充当价格、库存或商家政策证据。

```text
Android → API 事务写入 Turn/Job → 独立 Worker
        → 模型生成计划/参数 + 确定性执行器 + 11 个受控工具
        → PostgreSQL 事件 → 逐帧 SSE / ThreadSnapshot → Android、Ops

60 个自有 3C SKU → 结构化过滤 + BM25 / 本地 BGE → RRF → EvidenceRef
```

用户保留最终决定权：主／次／再次推荐纵向浏览，比较、保存、待购和跳转均有实际 API 状态。模型提出参数不等于授权；工具仍核验归属、审批、幂等及报价有效期。图片确认链已有真实模型证据；原生有效语音闭环仍未验收。

技术栈：Kotlin / Jetpack Compose / Room、FastAPI / Python、PostgreSQL、Qdrant、MinIO、Redis、React / TypeScript、OpenAPI、OpenTelemetry。没有支付、订单、生产身份或多 Agent。

## 当前证据与限制

以下为 2026-10-13 的历史验收快照，保留负结果。F60 与无障碍后续进展以上方 10 月 24 日报告为准，本次仓库同步不重跑付费模型或完整设备验收。

<details>
<summary><strong>展开验收记录、负结果与待完成项</strong></summary>


| 层级 | 已核验结果 | 边界与报告 |
|---|---|---|
| 黄金 Agent：真实 MiMo | 首次 10/10 可解析，9/10 预期流程；推荐证据 100% | G07 首次失败保留；[修复后审批与幂等](docs/evidence/v3/final-real-G07-R4-20261009.json) |
| 原生 Android：真实 API / MiMo | 完整场景 8/10；当前审批与安全恢复增量已真实复验 | [A08-R5](docs/evidence/v3/final-real-A08-R5-20261013.json)：拒绝零写入、批准数量2、重复决定幂等；[A10-R5](docs/evidence/v3/final-real-A10-R5-20261013.json)：断网/进程恢复、审批、隔离和原生删除整程通过。先前六条记录保留；A02有效人声和A09浏览器首次设置仍待完成 |
| 真实图片理解 | 图片→确认→带证据推荐；非 3C 澄清、文字/图片冲突处理 | [M01-R2](docs/evidence/v3/final-real-M01-R2-20261009.json)、[M02](docs/evidence/v3/final-real-M02-first-20261009.json)、[M04](docs/evidence/v3/final-real-M04-first-20261009.json)；原生语音未完成 |
| 冻结检索验收 | RRF Recall@10=1.00、NDCG@10=0.99348；BM25=1.00、BGE=0.98102 | [当前120查询、40/80划分复验](docs/evidence/v3/final-N07-retrieval-20261013.json)；融合没有收益，自动构造标注和小目录限制保留 |
| 平台容量 | 连续10批×30全部完成、终态一次；接受p95=265.89ms，未过200ms门槛；202后首状态p95=323.00ms | [完整失败报告](docs/evidence/v3/final-N07-durable-load-10-batches-20261013.json)；显式fake/真实BGE/双Worker。旧单批通过保留，不能替代连续负载；性能根因待定位 |
| 进程恢复 | 终止真实 Worker 后自然300秒租约回收，写入/收据/终态不重复 | [304.438秒故障注入](docs/evidence/v3/final-N07-worker-process-recovery-02-20261013.json)；通过正式审批服务冻结调用，首次工具失败保留 |
| 回归 | Python215项/0跳过；Android41单测、34视觉fixture、Ops五个真实工作流通过 | [当前分层质量证据](docs/evidence/v3/final-N07-quality-20261013.json)；单测UP-TO-DATE、18个lint警告保留。1000条构造用例不等于真实Agent成功率 |
| Android启动（已安装QA debug） | 未准备验证产物时30次p95=3179ms失败；同APK准备verify后另30次p95=1785ms、fatal/StrictMode为0 | [同APK复审](docs/evidence/v3/final-NFR07-verified-dex-review-20261013.json)；原失败及2630ms离群保留。不是release性能，也不替代最终源码APK复验；[安装准备](docs/demo/V3-ANDROID-PREPARE.md) |

截至 2026-10-13 A08-R5/A10-R5 完整验收，原共享账本使用 265,339 / 2,000,000 Token、94 次 HTTP、预留 0。API 没有返回金额，费用标记 `NOT_AVAILABLE_FROM_PROVIDER`。每个追加名额按直接授权执行一次；历史失败全部保留。

[A10-R4](docs/evidence/v3/final-real-A10-R4-20261012.json)是历史局部收尾，[A08-R3](docs/evidence/v3/final-real-A08-R3-20261012.json)和[A08-R4](docs/evidence/v3/final-real-A08-R4-20261013.json)的失败记录继续保留；当前整程结果以R5报告为准。A02/M03仍等待实际人声；报价自动续期已修复，A09自然过期原生分支已补，完整外跳验收等待本人完成Chrome首次设置。最终同版启动、APK/视频和封版复审仍未签收。

所有商品和报价均为自有演示数据，`DEMO_FIXTURE` 不能变成 LIVE 证据。当前覆盖中未观察到越权写入；虚构金额曾被事实守卫阻断并记为失败，不把安全拦截包装成整个流程通过。

本轮源码修复提案数量/目标偏移、审批参数重规划、未绑定具体调用、同步批准占用API、前台审批状态竞态与无进展循环。批准参数持久化后由Worker执行冻结提案；Android终态读取真实待购。独立子进程换用数量99规划器仍只写原批准数量2，当前A08-R5/A10-R5又验证了真实模型与原生审批/恢复。报价按用户持久化，普通读取不续期，显式重新询价才更新有效期。

</details>

## 三条本地启动命令

在当前候选源码目录执行，要求 Python 3.12.11、uv 0.11.13、Node 24.15、npm 12、Java 21、Docker Desktop 与 Android SDK。先确认 `uv --version` 与冻结版本一致；同机存在多个uv时，在本次终端选择正确版本：

```powershell
./scripts/bootstrap.ps1 -Quick
./scripts/start_v3_demo.ps1 -ProviderMode fake -RetrievalMode local -DatabaseName ragcommerce_candidate
./apps/android/gradlew.bat -p apps/android :app:assembleDebug -PapiUrl=http://10.0.2.2:20881
```

API 为 `127.0.0.1:20881`，Ops 为 `127.0.0.1:24174`；模拟器使用 `10.0.2.2:20881`。第三条命令构建当前源码 APK，不下载历史 APK。端口必须空闲；停止运行 `./scripts/stop_v3_demo.ps1`，只清理启动记录拥有的资源，数据卷保留。

默认明确使用 fake 模型和真实本地 BGE，启动不会意外花费模型额度。BGE 固定 revision `46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59`，查询进程只读既有索引；构建新 collection 成功后才切换别名。真实 MiMo 使用独立、已授权的场景账本与现有进程凭据入口；无备用模型或自动重试。

本次 main 同步包含截至 2026-10-24 的本地开发进展；历史 Release 不包含这些新增能力。独立候选导出脚本使用显式文件清单，不复制凭据、环境、编译缓存或导航站；导出本身不表示交付已通过。

## 工程取舍与面试入口

- 单 Agent＋确定性执行器：模型负责规划和解释，权限、事务、预算与恢复是固定安全流程，不宣称完全自主。
- PostgreSQL durable job＋租约：不用 Kafka；SSE 使用独立长连接配置，逐帧传递公开进度，不展示思维链。
- RAG 消融不反向包装：在当前小目录上 BM25 优于融合，报告保留这一结果。
- 错误直出：非法 Schema、429、超时、预算不足都保留失败；不静默切换 Provider。
- [当前缺陷与根因](docs/defects/V3-FINAL-CLOSEOUT.md)、[五包收口计划](docs/plans/INTERNSHIP-FINAL-CLOSEOUT.md)、[任务包与证据](docs/task-packages/manifest.json)。
- [C4 架构](docs/architecture/V3-C4.md)、[Agent 时序](docs/architecture/V3-AGENT-SEQUENCE.md)为已有设计资料，当前媒体和参数提案增量仍需同步复审。
- [五分钟讲解](docs/demo/V3-FIVE-MINUTE-DEMO.md)、[系统设计讲解](docs/demo/V3-SYSTEM-DESIGN-INTERVIEW.md)为历史入口；当前 24 问答、四稿、八类材料由外部导航站维护，个人掌握和贡献不代签。

## 发布与许可

历史 [v0.3.0](https://github.com/JunyeFu/Rag-ecommerce-agent/releases/tag/v0.3.0) 的发布结论仅属于历史版本。本次源码与文档同步由用户授权；未创建新 Release，最终同版验收仍待签收。

MIT 覆盖项目自有源码、60 SKU 和项目生成美术资产。第三方依赖遵循各自许可，包括 MinIO 的 AGPL；不把第三方许可改成 MIT。商业发布仍缺联盟授权、LIVE 报价及生产门禁。
