<p align="center">
  <img src="docs/media/github-cover.svg" alt="RAG Commerce：从想买什么，到知道怎么选" width="100%">
</p>

<h1 align="center">RAG Commerce</h1>
<p align="center"><strong>把预算、用途与取舍，变成有依据的购买决定。</strong><br>面向 3C 选购的 Android 原生购物决策 Agent。</p>

<p align="center">
  <a href="https://github.com/JunyeFu/Rag-ecommerce-agent/actions/workflows/ci.yml"><img src="https://github.com/JunyeFu/Rag-ecommerce-agent/actions/workflows/ci.yml/badge.svg?branch=main" alt="main 分支 CI 状态"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-161912?style=flat-square" alt="自有源码 MIT 许可"></a>
  <a href="#技术选型"><img src="https://img.shields.io/badge/Android-Kotlin%20%2B%20Compose-caff42?style=flat-square&labelColor=161912" alt="Android 原生 Kotlin 与 Compose"></a>
  <a href="#交付状态"><img src="https://img.shields.io/badge/Stage-Development%20Preview-f3efdf?style=flat-square&labelColor=161912" alt="研发展示版"></a>
</p>

<p align="center">
  <a href="docs/media/rag-commerce-v3-demo.mp4"><strong>观看 87 秒演示</strong></a>
</p>

<p align="center">
  <a href="#产品体验">产品体验</a> ·
  <a href="#实测证据">实测证据</a> ·
  <a href="#技术选型">技术选型</a> ·
  <a href="#本地体验">本地体验</a>
</p>

> **产品预览。** 基于 60 个自有演示 SKU 与 DEMO_FIXTURE 报价，可审阅源码、运行证据和本地体验。当前候选 **HOLD / 商业发布 NO_GO**；外部验收保持暂停。

## 产品体验

选购从“什么适合我”开始。RAG Commerce 将预算、用途和偏好组织成购买任务，让用户看清候选之间的差异，保存选择，并在确认后执行待购操作。

<table>
<tr>
<td width="50%" align="center"><img src="docs/media/android-agent-recommendation.png" width="260" alt="Android 历史推荐界面：候选理由、证据来源和演示报价"></td>
<td width="50%" align="center"><img src="docs/media/android-ux-native-20261021/default-comparison.png" width="260" alt="2026-10-21 原生比较界面：预算、约束和偏好取舍"></td>
</tr>
<tr>
<td align="center"><strong>推荐有依据</strong><br>候选、理由、报价来源与有效期一起呈现。</td>
<td align="center"><strong>选择看得懂</strong><br>比较差异，保留选择，继续购买任务。</td>
</tr>
</table>

<sub>仓库已有运行截图与历史演示视频，包含演示商品及报价。比较页为 2026-10-21；素材日期见<a href="docs/media/manifest.json">素材清单</a>，当前候选同版 APK / 视频签收仍待完成。</sub>

### 从表达需求到继续决策

| 用户要完成的事 | 产品如何承接 |
| --- | --- |
| **说清需求** | 输入用途、预算与硬约束；支持图片理解后的确认、澄清和条件修改 |
| **理解取舍** | 查看候选依据、规格差异和报价时效；缺失信息保留为未知 |
| **保留选择** | 比较、保存候选、组织购买任务，通过快照与游标继续处理 |
| **确认行动** | 审批绑定具体操作和参数；拒绝不写入，确认后按幂等回执执行 |

适合评估 **有预算和用途约束的 3C 导购**，以及商家或平台的购买前决策组件。商业价值定位于需求组织与证据推荐；消费者留存、转化率、收入和客户采用情况尚未测量。

<details>
<summary><strong>查看 Ops 运营台与任务恢复界面</strong></summary>

![历史 Ops 界面：Agent Trace、工具执行与证据引用，fixture 演示数据](docs/media/ops-agent-trace.png)

执行状态、工具回执与证据引用帮助定位问题；运营身份和消费者安装凭据分别管理。

<img src="docs/media/android-recovery.png" width="260" alt="Android 历史任务恢复界面">

![历史 Ops 发布门禁界面](docs/media/ops-release-gates.png)

</details>

## 实测证据

按报告日期呈现历史实测，真实模型、检索组件与平台容量分别统计。本次首页更新没有重跑付费模型、设备或容量实验。

<table width="100%">
<tr>
<td width="33%" align="center"><h3>9 / 10</h3><strong>真实模型场景完成</strong><br><sub>MiMo 黄金集首轮 · 10 场景<br>2026-10-09</sub></td>
<td width="33%" align="center"><h3>182 ms</h3><strong>平台接单 p95</strong><br><sub>fake 模型 / 双 Worker / 本地 BGE<br>2026-10-24</sub></td>
<td width="33%" align="center"><h3>1,785 ms</h3><strong>Android 冷启动 p95</strong><br><sub>QA debug APK / API 35 模拟器<br>2026-10-13</sub></td>
</tr>
</table>

**接单耗时不等于推荐完成耗时。** 真实模型首轮场景耗时中位数为 **38.827 s**，p95 为 **191.270 s**，含工具与场景后置检查。G07 首轮失败，后续复测单独列示；10 条样本不能外推真实用户成功率。

<details>
<summary><strong>查看完整指标、样本条件与原始证据</strong></summary>

| 测量层级 / 日期 | 样本与条件 | 结果 | 证据 |
|---|---|---|---|
| **真实 MiMo 黄金集首轮 · 10-09** | G01–G10；真实 API / PostgreSQL / Worker；演示数据 | **9/10** 完整通过；解析与场景级 Schema 各 **10/10**；推荐证据完整的运行 **10/10** | [逐场景与复测](docs/evaluation/AGENT-PERFORMANCE.md#真实-mimo持久化黄金集首轮) |
| **真实模型场景耗时与用量 · 10-09** | 同一首轮 10 场景，含工具与场景后置检查，失败保留 | 中位数 **38.827 s**；p95 **191.270 s**；**86,158 Token / 22 次付费调用记录**；供应商未返回金额 | [统计与口径](docs/evaluation/AGENT-PERFORMANCE.md) |
| **检索消融 · 10-13** | 60 SKU；120 查询按 40 / 80 划分，验收含 64 个有匹配查询 | Recall@10 三路均 **1.000**；NDCG@10：BM25 **1.00000**、BGE **0.98102**、RRF **0.99348**；融合无增益 | [冻结报告](docs/evidence/v3/final-N07-retrieval-20261013.json) |
| **本地平台容量 · 10-24** | 十批 × 30，共 300；真实 PostgreSQL、双 Worker、本地 BGE、**fake 模型** | **300/300** 完成，**10/10** 批次通过；接单 p95 **182.079 ms**；202 后首状态 p95 **111.482 ms**；提交至 Worker 开始 p95 **828.236 ms** | [完整验收与负结果](docs/evidence/v3/final-F60-review-20261024.json) |
| **Worker 进程恢复 · 10-13** | 真实 PostgreSQL + 子进程故障注入 + fake | 自然 300 s 租约下 **304.438 s** 恢复；写入、回执与终态不重复 | [故障注入](docs/evidence/v3/final-N07-worker-process-recovery-02-20261013.json) |
| **Android 场景覆盖 · 截至 10-13** | 具名尝试与修复复测；模拟器，实际 API / MiMo 或零新增调用的 UI 收尾 | **8/10 项已覆盖**；A02 有效人声、A09 完整外跳待完成；不作为首轮通过率 | [场景矩阵](docs/evaluation/AGENT-PERFORMANCE.md#原生-android-场景覆盖) |
| **Android 冷启动 · 10-13** | 同一已安装 QA debug APK；准备前后各 30 次，API 35 模拟器 | p95 **3,179 → 1,785 ms**；后组最大 2,630 ms；非 release / 真机性能 | [同 APK 复审](docs/evidence/v3/final-NFR07-verified-dex-review-20261013.json) |
| **TalkBack 限定验收 · 10-24** | 字号 1.0 / 2.0；原生模拟器 + fake + 内存 API | **8/8** 路径通过；不替代全产品无障碍与真机验收 | [范围与历史失败](docs/evidence/v3/android-talkback-20261024.json) |

检索负结果同样保留：该冻结小目录上 **BM25 的 NDCG@10 优于 RRF**，混合检索没有质量增益证据。历史容量也保留未通过批次，未回填为成功；详见[完整性能报告](docs/evaluation/AGENT-PERFORMANCE.md)。

统计覆盖 14 组历史黄金集报告、持久化首轮场景、复测、图片、原生端、检索、容量与启动数据。[机器可读结果](docs/evaluation/agent-metrics-20261105.json)可离线复算：

```powershell
python scripts/summarize_agent_metrics.py --check
```

构造 reference 的 1,000 条确定性结果不计入真实 Agent 性能。多模型对照、真实模型并发容量、首张推荐时延、实际每任务金额和消费者转化率暂无测量结果。

</details>

**工程验证 · 2026-11-06：** [已合并修复 #28](https://github.com/JunyeFu/Rag-ecommerce-agent/pull/28)的[完整 CI 五项通过](https://github.com/JunyeFu/Rag-ecommerce-agent/actions/runs/42065228011)：Python **300 通过 / 7 跳过**，隔离真实 TLS **另跑 6 通过**；Web、Android 与 Compose 通过。[修复与验证记录](docs/evaluation/AGENT-REMEDIATION-CLOSE-20261106.md)保留分组口径、历史失败和剩余门禁。

## 技术选型

架构围绕三个判断展开：**原生任务连续性、商品事实可核验、工具操作受授权。** 采用单 Agent 规划与确定性执行器，避免把事实和写入权限交给模型文本。

| 组成 | 采用它的理由与代价 |
| --- | --- |
| **Kotlin / Compose / Room** | 原生生命周期承接图库、录音、无障碍与恢复；承担 Android 专用 UI 的维护成本 |
| **Python / FastAPI / LangGraph** | 规划、工具、ONNX 与评测共享生态；承担 CPU 阻塞、状态契约和跨语言维护成本 |
| **PostgreSQL / Worker / SSE** | 任务与 Job 同事务落库，事件可回放；队列、租约及故障恢复由项目维护 |
| **BM25 / 本地 BGE / Qdrant / RRF** | 关键词与语义检索接到商品证据；增加模型和向量服务，当前小目录实测 BM25 排序更好 |
| **React / TypeScript / Vite** | Ops 类型契约与静态交付直接；需要公开内容与 SEO 时再评估服务端渲染 |

<details>
<summary><strong>查看备选技术栈、选择条件与系统实现</strong></summary>

| 层次 / 实际采用 | 选择理由 | 已承担的代价 | 其他技术栈更合适的条件 |
|---|---|---|---|
| **Kotlin 2.0 / Compose / Room** | 在原生生命周期内处理图库、AudioRecord、TalkBack 与任务恢复 | Android 专用 UI，另做 iOS 需要投入 | Flutter / React Native：多端复用优先，且具备相应团队能力 |
| **Python 3.12 / FastAPI / Pydantic** | Agent、ONNX 推理和评测共用语言，OpenAPI 连接三端类型 | 需管理 CPU 阻塞、GC 与内存；与客户端跨语言维护 | TypeScript：统一 Web/API；Go / Java：以既有服务体系与团队积累为主 |
| **LangGraph + 单 Agent + 确定性执行器** | 控制流清楚，规划与事实、授权、写入分工明确 | 模型等待仍长，状态与工具契约需要维护 | 普通函数流适合固定短流程；任务确有可分工收益时再评估多 Agent |
| **PostgreSQL 16 + 独立 Worker + SSE** | Turn / Job 同事务落库，减少 Broker 双写；事件支持重放 | 租约与队列逻辑自行维护，300 s 租约影响故障恢复 | Celery + Broker：复杂路由 / 多队列；WebSocket：持续双向实时交互 |
| **BM25 + 本地 BGE / ONNX + Qdrant + RRF** | 关键词、语义、过滤与证据形成可复跑链路 | 多一个向量服务和本地模型；**当前实测 BM25 排序更好** | BM25-only：窄目录精确检索；pgvector：希望合并关系与向量存储 |
| **React 19 / TypeScript / Vite / TanStack Query** | Ops 连接既有 API，静态构建可交付 | 不提供完整的公开内容与 SEO 方案 | Next.js 等框架：出现公开内容、路由与渲染需求时按需选择 |

以上是基于当前实现的工程比较，备选技术栈未做等条件跑分；完整版本、源码入口和官方参考见[技术选型复盘](docs/architecture/TECH-STACK-DECISIONS.md)。

```text
Android：需求 → 澄清 / 图片确认 → 推荐 → 比较 / 保存 / 审批
    │ POST Turn / 用户决定                  ▲ SSE / ThreadSnapshot
    ▼                                     │
FastAPI → PostgreSQL：Turn + Job → 独立 Worker
    → LangGraph 单 Agent：guard → plan → tools → respond
    → 确定性执行器：11 个注册工具、授权、事实守卫、幂等与持久化

60 个自有 3C SKU → 结构化过滤 + BM25 / 本地 BGE → RRF → EvidenceRef
MinIO：图片 / 音频对象                    Ops Web：Trace / 检索 / 门禁
```

- **事实边界：** 价格来自带来源、采集/失效时间和验证级别的 `OfferQuote`；`DISCOVERY_ONLY` 不参加最低价排序。模型负责规划和多模态理解，公开阶段文本由运行时生成。
- **执行边界：** 11 个注册工具；审批绑定调用及参数，执行器核验归属和授权。支付、订单、退款与履约不在首版范围。
- **基础设施：** Docker Compose、MinIO；OpenAPI 生成类型，OpenTelemetry 观测。Redis 在配置中，当前主链未调用；PostgreSQL 镜像含 pgvector，实际向量检索使用 Qdrant。

[C4 设计](docs/architecture/V3-C4.md) · [Agent 时序](docs/architecture/V3-AGENT-SEQUENCE.md)

</details>

## 交付状态

| 评估方向 | 当前可审阅内容 | 下一阶段条件 |
| --- | --- | --- |
| **工程与产品评估** | 公开源码、原生体验素材、历史实测、身份/审批/恢复及 CI 证据 | 当前候选同版 APK / 视频、完整人声与浏览器外跳、独立复审 |
| **授权导购接入** | 类型化报价、来源/时效、用户确认和受控 HTTPS 传输 | 联盟授权、LIVE 报价/深链、更新条件与正式部署 |
| **消费者或商家服务** | 可运行的购买前决策机制与演示 | 真实用户、物理设备、安全/法务和业务人审、容量与运维验收 |

外部验收按用户指令暂停，商业发布维持 **NO_GO**。不承诺全网最低价、实时库存或生产 SLA；[交付记录](docs/release/local-portfolio.json)及[缺陷记录](docs/defects/V3-FINAL-CLOSEOUT.md)保留未完成项，历史 [v0.3.0](https://github.com/JunyeFu/Rag-ecommerce-agent/releases/tag/v0.3.0) 不代表当前候选发布资格。

## 本地体验

固定工具链：Python **3.12.11** · uv **0.11.13** · Node **24.15.0** · npm **12.0.1** · Java **21**；需要 Docker Desktop 与 Android SDK。见[完整配置](toolchain.versions.json)。

```powershell
./scripts/bootstrap.ps1 -Quick
./scripts/start_v3_demo.ps1 -ProviderMode fake -RetrievalMode local -DatabaseName ragcommerce_candidate
./apps/android/gradlew.bat -p apps/android :app:assembleDebug -PapiUrl=http://10.0.2.2:20881
```

API `127.0.0.1:20881` · Ops `127.0.0.1:24174` · Android 模拟器 `10.0.2.2:20881`。端口需空闲；停止使用 `./scripts/stop_v3_demo.ps1`，仅处理启动记录拥有的资源，保留数据卷。

启动明确选择 fake 模型与本地 BGE，首次准备可能下载固定依赖和模型；运营凭据由[管理员命令](scripts/manage_ops_identity.py)签发。真实模型使用独立授权与预算，不静默回退或自动重试。

---

[文档中心](docs/README.md) · [技术决策](docs/architecture/TECH-STACK-DECISIONS.md) · [评测方法](docs/evaluation/methodology.md) · [任务与证据](docs/task-packages/manifest.json) · [贡献说明](CONTRIBUTING.md) · [MIT 许可](LICENSE)

<sub>MIT 覆盖项目自有源码、60 SKU 与项目生成美术资产；第三方依赖按各自许可使用。MinIO 固定版本为 AGPL-3.0-only，商业交付需结合实际部署确定第三方许可范围。</sub>

<p align="center"><sub>Native Android · Evidence-backed recommendations · Explicit approval · Durable recovery</sub></p>
