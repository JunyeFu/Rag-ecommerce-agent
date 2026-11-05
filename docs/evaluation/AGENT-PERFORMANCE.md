# Agent 实测性能与质量报告

统计日期：**2026-11-05**。本次从仓库已有脱敏报告离线复算，没有新增模型、设备或压测运行。源码核对基线为 `0ed3910c79d21c5418d1111e4c92fd85b06533d1`；原始报告对应各自日期的实现，其中部分为 dirty candidate，不能作为当前源码的同版验收。

[机器可读统计](agent-metrics-20261105.json) · [统计脚本](../../scripts/summarize_agent_metrics.py) · [选型复盘](../architecture/TECH-STACK-DECISIONS.md) · [当前交付状态](../release/local-portfolio.json)

## 怎样读取这些指标

项目实现是 **单购物决策 Agent**，真实规划模型只有 **MiMo `mimo-v2.5`**。BGE 是 Embedding 模型，fake 是显式测试 Provider；没有多 Agent 或多个真实规划模型的对照结果。

| 指标 | 起止与分母 | 能说明什么 |
|---|---|---|
| 黄金集场景通过 | 完整场景的 `passed`；所有首轮失败保留在 10 条分母内 | 已知任务链路的完成情况，不能外推真实用户成功率 |
| 场景耗时 | runner 开始至场景结束，含 API、模型、工具和保存/恢复等后置检查 | 场景总等待；不是纯模型延迟，也不是首 token 或首张推荐时间 |
| 接单耗时 | 提交 Turn 至收到 HTTP 202 | API 持久化接单响应 |
| 首状态耗时 | 收到 202 至首个公开 SSE 状态；可能只是 queued | 排队反馈，不能解释成 Agent 已完成推荐 |
| Worker 开始耗时 | 提交 Turn 至 Worker 开始执行 | 调度等待，包含提交阶段 |
| 工具 Schema | 每场景未观察到 `tool_failed` 的布尔检查 | 场景级检查；没有足够逐调用 gold 来计算真实工具 precision / recall |
| EvidenceRef 覆盖 | 推荐运行中所有推荐是否带证据引用 | 引用完整性；不等于外部事实真实性或人工判断正确性 |

延迟的 p95 使用 **nearest rank：排序后第 `ceil(n × 0.95)` 条**；中位数在偶数样本中取中间两项平均。只有 10 个样本时 p95 等于最大值，不能当作稳定的生产尾延迟估计。这里报告描述性计数与耗时，不拟合真实用户总体成功率；复测与历史版本分别列示，不合并总成功率。

## 真实 MiMo：持久化黄金集首轮

2026-10-09，G01–G10 各执行一次。真实 MiMo + API / PostgreSQL / Worker，商品与报价仍为演示数据。场景定义见 [黄金集](../../evals/v3/golden-scenarios.json)。

| 指标 | 复算结果 |
|---|---|
| 完整场景 / 预期流程 | **9/10**；G07 审批首轮失败 |
| 可解析 / 场景级工具 Schema | **10/10 / 10/10** |
| 带完整 EvidenceRef 的推荐运行 | **10/10**；共 50 张推荐 |
| 该检查观察到的未授权写入或导航 | **0/10**；正式批准后的操作单独验收 |
| 场景耗时：均值 / 中位数 / p95 | **78.475 / 38.827 / 191.270 秒** |
| 已报告 Token / HTTP 付费调用记录 | **86,158 / 22**；包含这些场景中的附加操作 |
| 实际金额 | **供应商未返回，`NOT_AVAILABLE_FROM_PROVIDER`** |

| 场景 | 主要验证路径 | 首轮 | 场景耗时 s | Token | 付费调用记录 | 原始证据 |
|---|---|---|---:|---:|---:|---|
| G01 | 搜索、事实、报价、比较 | 通过 | 38.762 | 7,342 | 2 | [报告](../evidence/v3/final-real-G01-first-20261009.json) |
| G02 | 保存、待购 | 通过 | 33.811 | 7,663 | 2 | [报告](../evidence/v3/final-real-G02-first-20261009.json) |
| G03 | 商品事实、比较 | 通过 | 26.412 | 7,197 | 2 | [报告](../evidence/v3/final-real-G03-first-20261009.json) |
| G04 | 搜索、保存 | 通过 | 35.677 | 7,881 | 2 | [报告](../evidence/v3/final-real-G04-first-20261009.json) |
| G05 | 搜索、恢复 | 通过 | 191.270 | 7,966 | 2 | [报告](../evidence/v3/final-real-G05-first-20261009.json) |
| G06 | 报价、待购 | 通过 | 168.722 | 15,367 | 2 | [报告](../evidence/v3/final-real-G06-first-20261009.json) |
| G07 | 审批 | **失败** | 55.331 | 10,140 | 4 | [报告](../evidence/v3/final-real-G07-first-20261009.json) |
| G08 | 重新询价、外跳解析 | 通过 | 169.532 | 6,979 | 2 | [报告](../evidence/v3/final-real-G08-first-20261009.json) |
| G09 | 商品事实、比较 | 通过 | 26.344 | 7,452 | 2 | [报告](../evidence/v3/final-real-G09-first-20261009.json) |
| G10 | 断网、恢复 | 通过 | 38.893 | 8,171 | 2 | [报告](../evidence/v3/final-real-G10-first-20261009.json) |

G07 的后续结果单列，**不将首轮改成 10/10**：

| 尝试 | 结果 | 耗时 s | Token / 付费调用记录 | 证据 |
|---|---|---:|---|---|
| R1 | 审批流程未通过 | 68.403 | 10,387 / 3 | [报告](../evidence/v3/final-real-G07-R1-20261009.json) |
| R2 | HTTPStatusError | 50.785 | 原报告未提供 | [报告](../evidence/v3/final-real-G07-R2-20261009.json) |
| R3 | 审批流程未通过 | 33.737 | 9,617 / 3 | [报告](../evidence/v3/final-real-G07-R3-20261009.json) |
| R4 | 审批与幂等通过 | 40.437 | 8,180 / 5 | [报告](../evidence/v3/final-real-G07-R4-20261009.json) |

## 真实模型的历史完整批次

下表列出仓库保存的 **13 组 run + 2026-10-08 一组黄金集**，每组 10 条；不同版本、提示词与测试路径不能作为横向性能提升曲线。`流程标志`单项为真也可能同时报错，因此另外复算“联合条件通过”：可解析、Schema、预期流程、预期商品、证据覆盖为 1、无未授权行为、无商业事实检测、无失败类型同时成立。它不是新增实验，也不改写原报告的 `passed`。

| 批次 / 原始报告 | 可解析 | 流程标志 | 联合条件通过 | 中位数 s | p95 s | 已报告 Token | 原批次结论 |
|---|---:|---:|---:|---:|---:|---:|---|
| [run-001](../evidence/v3/mimo-v2.5-real-evaluation-run-001-failed.json) | 0/10 | 5/10 | 0/10 | 50.941 | 65.276 | 136,484 | 失败 |
| [run-002](../evidence/v3/mimo-v2.5-real-evaluation-run-002.json) | 3/10 | 6/10 | 3/10 | 120.283 | 168.756 | 392,976 | 失败 |
| [run-003](../evidence/v3/mimo-v2.5-real-evaluation-run-003.json) | 10/10 | 6/10 | 5/10 | 63.940 | 112.301 | 152,766 | 失败；商业事实检测 2 条 |
| [run-004](../evidence/v3/mimo-v2.5-real-evaluation-run-004.json) | 10/10 | 7/10 | 5/10 | 73.965 | 232.257 | 167,536 | 失败；商业事实检测 2 条 |
| [run-005](../evidence/v3/mimo-v2.5-real-evaluation-run-005.json) | 10/10 | 7/10 | 7/10 | 109.247 | 125.476 | 152,024 | 失败 |
| [run-006](../evidence/v3/mimo-v2.5-real-evaluation-run-006.json) | 9/10 | 9/10 | 8/10 | 80.390 | 107.855 | 109,469 | 失败 |
| [run-007](../evidence/v3/mimo-v2.5-real-evaluation-run-007.json) | 9/10 | 9/10 | 8/10 | 84.785 | 184.930 | 121,355 | 失败 |
| [run-008](../evidence/v3/mimo-v2.5-real-evaluation-run-008.json) | 9/10 | 9/10 | 8/10 | 78.004 | 180.442 | 101,953 | 失败 |
| [run-009](../evidence/v3/mimo-v2.5-real-evaluation-run-009.json) | 10/10 | 9/10 | 9/10 | 64.432 | 79.994 | 109,525 | 通过历史批次门槛 |
| [run-010](../evidence/v3/mimo-v2.5-real-evaluation-run-010.json) | 10/10 | 9/10 | 9/10 | 62.695 | 90.423 | 115,221 | 通过历史批次门槛 |
| [run-011](../evidence/v3/mimo-v2.5-real-evaluation-run-011.json) | 10/10 | 8/10 | 8/10 | 73.189 | 127.588 | 101,944 | 失败；有场景缺少推荐证据 |
| [run-012](../evidence/v3/mimo-v2.5-real-evaluation-run-012.json) | 9/10 | 10/10 | 9/10 | 63.540 | 102.062 | 131,607 | 失败；预算超限 |
| [run-013](../evidence/v3/mimo-v2.5-real-evaluation-run-013.json) | 9/10 | 10/10 | 9/10 | 68.978 | 95.025 | 88,538 | 失败；无来源金额被阻断 |
| [2026-10-08](../evidence/v3/career-close-golden-20261008.json) | 9/10 | 10/10 | 9/10 | 29.117 | 37.605 | 58,672 | 失败；G03 无来源金额被阻断 |

历史 Schema 通过数 run-001 为 8/10、run-002 为 5/10，其他批次为 10/10。历史汇总的 `evidence_coverage` 取场景最小值，不能当成平均覆盖率；完整字段保存在机器可读统计的 `reported_summary`。run-012 的“流程 10/10”和解析失败共存，也说明不能把单项流程标志当任务成功率。

另存的 [G08 单场景复测](../evidence/v3/mimo-v2.5-real-evaluation-g08-retest-001.json)为 42.212 s / 8,374 Token，[G09 单场景复测](../evidence/v3/mimo-v2.5-real-evaluation-g09-retest-001.json)为 66.162 s / 9,001 Token；不回填历史整组统计。

## 专项、图片与 Android

### 2026-10-08 专项测试

| 项目 | 结果 | 耗时 s | Token |
|---|---|---:|---:|
| 澄清 | 通过 | 4.381 | 1,691 |
| 重新询价 | 通过 | 2.069 | 3,135 |
| 清单写入 / 审批 / 幂等重放 | 通过 | 12.509 | 3,339 |
| 待购写入 / 审批 / 幂等重放 | 通过 | 69.669 | 8,365 |

[原始专项报告](../evidence/v3/career-close-specialized-20261008.json)为 4/4；`cart_write` 记录 `forced_write=true`，是受约束专项，不能充当自然语言自主选择工具的成功率。Token / 耗时沿用专项 runner 的记录范围，不与黄金集总场景直接比较。

### 真实图片理解尝试

| 场景 / 尝试 | 结果 | 耗时 s | Token | 付费调用记录 | 原始证据 |
|---|---|---:|---:|---:|---|
| M01 首轮 | 失败：未等待确认 | 5.279 | 508 | 1 | [报告](../evidence/v3/final-real-M01-first-20261009.json) |
| M01 R1 | 失败：确认后推荐未完成 | 35.155 | 10,635 | 4 | [报告](../evidence/v3/final-real-M01-R1-20261009.json) |
| M01 R2 | 图片→用户确认→证据推荐通过 | 31.793 | 10,093 | 4 | [报告](../evidence/v3/final-real-M01-R2-20261009.json) |
| M02 首轮 | 非 3C 输入解释 / 追问通过 | 9.115 | 750 | 1 | [报告](../evidence/v3/final-real-M02-first-20261009.json) |
| M04 首轮 | 文字 / 图片冲突确认通过 | 136.198 | 10,470 | 4 | [报告](../evidence/v3/final-real-M04-first-20261009.json) |

输入是自有示意图，验证 API 媒体确认链，不是商品照片识别泛化测试。M03 有效原生人声仍未验收，没有语音准确率。

### 原生 Android 场景覆盖

以下是各自具名尝试的覆盖情况，包含修复后复测，不是一次运行 8/10 的首轮成功率。运行终端为 Android 模拟器；真实 API / MiMo 场景与零新增模型调用的 UI 收尾分别读取原报告。

| 场景 | 当前具名证据 | 覆盖结果 | 该尝试新增付费调用记录 / Token |
|---|---|---|---:|
| A01 文字推荐 | [R1](../evidence/v3/final-real-A01-R1-20261009.json) | 通过 | 2 / 7,809 |
| A02 原生人声、澄清 | 尚无有效人声闭环 | 待完成 | 未统计 |
| A03 图库、确认、推荐 | [R1](../evidence/v3/final-real-A03-R1-20261012.json) | 通过 | 4 / 9,963 |
| A04 探索、转购买 | [R1](../evidence/v3/final-real-A04-R1-20261012.json) | 通过 | 3 / 9,271 |
| A05 修改约束、任务隔离 | [首轮](../evidence/v3/final-real-A05-first-20261009.json) | 通过 | 9 / 27,976 |
| A06 比较与返回 | [R1](../evidence/v3/final-real-A06-R1-20261009.json) | 通过；复用已有推荐 | 0 / 0 |
| A07 保存、待购、重启 | [R1](../evidence/v3/final-real-A07-R1-20261009.json) | 通过；复用已有推荐 | 0 / 0 |
| A08 拒绝 / 批准 / 幂等 | [R5](../evidence/v3/final-real-A08-R5-20261013.json) | 通过；拒绝零写入、批准数量 2 | 3 / 921 |
| A09 询价、过期、完整外跳 | [首轮](../evidence/v3/final-real-A09-first-20261010.json) | 局部完成；完整链待浏览器首次设置 | 0 / 0 |
| A10 断网 / 进程恢复 / 隔离 / 删除 | [R5](../evidence/v3/final-real-A10-R5-20261013.json) | 整程通过 | 5 / 10,633 |

覆盖为 **8 项已通过 / 10 项计划场景**；不加总这些挑选尝试的 Token 作为整个项目费用。A08-R5 / A10-R5 后共享账本读数为 **265,339 Token、94 次 HTTP、预留 0**，属于当时整个会话累计值，不能再与本节的子集合相加。

## 检索组件

2026-10-13 冻结查询共 120 条，development 40、acceptance 80；60 个自有 SKU。下表复算 **acceptance 的 64 个有匹配查询**；无匹配的 16 条单独计数。

| 方案 | Recall@10 | NDCG@10 | 无匹配准确数 | 硬约束违规 |
|---|---:|---:|---:|---:|
| BM25 | 1.00000 | **1.00000** | 16/16 | 0/80 |
| 本地 BGE 向量 | 1.00000 | 0.98102 | 16/16 | 0/80 |
| RRF 混合 | 1.00000 | 0.99348 | 16/16 | 0/80 |

RRF 的 NDCG@10 比 BM25 **低 0.00652**，没有检索质量提升证据。每查询计时包含三个方案，120 条合计测量的均值 / 中位数 / p95 为 **66.177 / 61.670 / 92.410 ms**；没有各方案独立耗时，不能用这个数比较三者速度。

[原始冻结报告](../evidence/v3/final-N07-retrieval-20261013.json)的限制必须与成绩一起读：标签由项目自动构造，60 SKU 只有四种不同规格模板，过滤条件由任务直接提供；acceptance 是开发留出集，未用于调参，但不是独立用户盲测。CI 的 [10 条确定性向量消融](../../evals/v3/ablation-report.json)是另一种 fixture，不能替代真实 BGE 结果。

## 平台容量与资源

### 原容量失败与最终本地验收

两次各十批、每批 30 并发，真实 PostgreSQL、双 Worker、本地 BGE，**模型为 explicit fake**。延迟从各批明细的全部 300 个样本重算；没有移除失败批次。

| 指标 | 2026-10-13 失败批次组 | 2026-10-24 最终本地验收 |
|---|---:|---:|
| 任务完成 / 单次 completed 终态 | 300/300 / 300/300 | 300/300 / 300/300 |
| 通过批次 | **5/10，失败** | **10/10，通过** |
| 接单耗时：均值 / 中位数 / p95 ms | 147.405 / 140.297 / 265.891 | 66.971 / 56.415 / **182.079** |
| 202 后首状态 p95 ms | 322.999 | **111.482** |
| 提交至 Worker 开始 p95 ms | 1,052.538 | **828.236** |
| 最差单批接单 p95 ms | 275.354 | 190.832 |

[旧失败明细](../evidence/v3/final-N07-durable-load-10-batches-20261013.json) · [最终 300 样本](../evidence/v3/f60-20261024/final-bge-r3-durable-10-batches.json) · [配置、根因与回读](../evidence/v3/final-F60-review-20261024.json)

最终配置为 Windows、16 逻辑处理器、Python 3.12.11、Uvicorn 0.52.4、两个 Worker 各八通道；固定 BGE revision `46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59`。最差批次距 200 ms 门槛仅约 9.17 ms。此结果不提供真实 MiMo 并发容量、持续吞吐或线上 SLA；未报告任务完成时间分布，也不能由完成数反推 QPS。

### F60 中间尝试保留

以下为 F60 原报告已登记的十次运行汇总，均为 300/300 完成；本表按原汇总列示，不将诊断模式的较好成绩替代正常 CLI 验收。

| 运行 | 检索 | 性质 | 接单 p95 ms | 首状态 p95 ms | 通过批次 |
|---|---|---|---:|---:|---:|
| previous-infrastructure | fixture | 失败对照 | 229.731 | 218.210 | 7/10 |
| cli-baseline | fixture | 诊断，失败 | 184.050 | 241.929 | 9/10 |
| direct-asgi | fixture | 诊断，失败 | 421.545 | 634.002 | 8/10 |
| io-timeline | fixture | 诊断 | 96.031 | 82.659 | 10/10 |
| normal-fixture | fixture | 中间对照 | 186.266 | 205.627 | 10/10 |
| normal-bge | local BGE | 验收失败 | 272.762 | 126.232 | 9/10 |
| normal-bge-shared | local BGE | 验收失败 | 222.648 | 150.844 | 9/10 |
| both-timelines | local BGE | 诊断 | 93.682 | 134.251 | 10/10 |
| normal-bge-static | local BGE | 验收失败 | 218.636 | 134.615 | 9/10 |
| normal-bge-final | local BGE | **正常 CLI 最终本地通过** | **182.079** | **111.482** | **10/10** |

所有运行的源报告路径在 [机器统计的 `capacity.all_closeout_runs`](agent-metrics-20261105.json)中。接单总体 p95 低于 200 ms 仍可能因单批超标失败，不能只挑总体数值。

BGE 同进程共享后，每 Worker 的模型份数从 **8 → 1**；两 Worker 的常驻内存观测从 **1,038,172,160 / 1,036,873,728 bytes** 降至 **342,417,408 / 342,528,000 bytes**（约 989–990 → 327 MiB）。[F60 根因报告](../evidence/v3/final-F60-review-20261024.json)同时记录 ASGI 转发、GC 和日志的影响；不把全部改善归因于一个补丁。

## 恢复、启动与无障碍

| 测量 | 结果 | 条件与证据 |
|---|---|---|
| Worker 进程故障恢复 | **304.438 s**；写入不重复、一个回执、一个终态、游标重放正确 | 自然等待 **300 s 租约**，真实 PostgreSQL + 子进程故障注入 + fake；一次场景，不是恢复时延分布。[报告](../evidence/v3/final-N07-worker-process-recovery-02-20261013.json) |
| Android 未准备 dex，30 次冷启动 | 中位数 **2,320.5 ms**，p95 **3,179 ms**，失败记录保留 | 已安装 QA debug APK / API 35 模拟器。[逐次数据](../evidence/v3/final-NFR07-installed-cold-start-20261013.json) |
| 同 APK 显式 prepare 后，另 30 次 | 中位数 **972 ms**，p95 **1,785 ms**；最大 2,630 ms；fatal / StrictMode 违规均 0 | 实际 dexopt 模式 `verify`，不换包、不清数据；初始界面显示，不是完整 Agent ready，不是 release / 真机性能。[逐次数据](../evidence/v3/final-NFR07-installed-verified-dex-cold-start-20261013.json)、[复审范围](../evidence/v3/final-NFR07-verified-dex-review-20261013.json) |
| TalkBack 原生路径 | **8/8**，字号 1.0 / 2.0 | 2026-10-24 模拟器、explicit fake、真实 HTTP 的内存 API；不是 PostgreSQL / MiMo / 全产品无障碍签收。[报告](../evidence/v3/android-talkback-20261024.json) |

历史质量检查也独立计数：F60 当批 Python **237/237**（198 unit + 39 integration）；10 月 24 日 Android **55 单测**、TalkBack 关闭对照下 **41 视觉 fixture** 通过，lint **0 错误 / 19 警告**。这些是对应日期的工程回归，不计入 Agent 任务完成率，也不是本次重新运行。

## 未测指标与商业解释

- **不能从现有记录得到：** 首 token、首张可用推荐、真实 MiMo 30 并发容量、持续 QPS、用户满意度、转化率、推荐收益、真实商品事实准确率、真机电量/内存/流畅度，以及实际每任务金额。
- **不计入性能：** [1,000 条 deterministic reference](../../evals/v2/results/deterministic-reference-summary.json)来自期望构造器，真实 Provider 调用为 0；其中 100% 和预设 31.2 ms 只验证 grader / 分母契约。真实模型自动 challenge 结果仍缺失。
- **当前可证明的价值：** 演示任务能形成检索、证据、决策与受授权操作的链路；API 接单和恢复有本地测量。**仍需解决的短板：** 实际等待时间长、小目录评测外部效度有限、LIVE 供给与生产条件未建立。

完整语音、浏览器首次设置后的 A09、最终同版 APK / 媒体 / 独立复审和生产门禁仍未完成；当前 **HOLD / 商业 NO_GO**。数据范围与失败留存比一个漂亮的“总分”更能支撑技术评估。

## 本次 GitHub CI 复核

2026-11-05 对提交 `784e3f1e5ffd9f8ff00242293e041450f8637733` 的 [CI 运行](https://github.com/JunyeFu/Rag-ecommerce-agent/actions/runs/41983929044)读取到以下最终结果。这是本次远端检查，区别于上文历史验收。

| Job | 结果 | 实际执行与失败原因 |
|---|---|---|
| android | 通过 | 当前 CI 的 Kotlin 编译、单测、lint 与 benchmark 包构建步骤通过；不是设备性能验收 |
| compose-contract | 通过 | Compose 配置检查通过 |
| web | **失败** | TypeScript 与 2 条 Ops 单测通过；Agent API E2E 为 **2 通过 / 1 失败**。重场景第 251 行仍以精确对象断言待购项只有 `offer_id / quantity`；当前 `CartItemView` 还要求 `product / quote`，响应因此不相等。Ops 浏览器回归与后续 Web build 未执行 |
| python-and-governance | **失败** | 基础设施 / 迁移、本地 Embedding、契约与前序生成检查通过；在 `security_gate.py --check` 报 `DRIFT docs/security/evidence/security-gate.json`，其后的 pytest 未执行，不能声称本次 Python 全量通过 |

源码核对确认：当前 [CartItemView](../../packages/contracts/openapi.json)要求四个字段，[E2E 断言](../../e2e/agent/agent-business.spec.ts)尚未同步；冻结安全报告中的 `npm_lock_sha256` 匹配本机 CRLF 的 `package-lock.json`，不匹配 Git 中 LF 字节，二者换行归一化后相同。本次文档发布没有修改应用、契约、E2E、CI 或依赖文件；这两处保留为已观测的测试 / 门禁问题，没有为展示改写业务行为或测试结果。

本次离线统计、143 个初版文档引用检查、脚本 lint/format、任务包检查与 GitHub 内容读取均通过；**文档校验通过和全量 CI 通过分别报告**。安全报告漂移本身不是发现漏洞或密钥泄漏的结论。

## 复算

在仓库根目录运行，仅使用 Python 标准库和现有 JSON，不启动服务或读取凭据：

```powershell
python scripts/summarize_agent_metrics.py
python scripts/summarize_agent_metrics.py --check
python scripts/validate_task_packages.py
```

脚本重新聚合逐场景耗时与 Token、黄金集联合条件、检索逐查询分数、两组容量的逐批样本及两组启动样本；其他专项与诊断汇总按原记录保留。缺失字段保持缺失，不将未知费用或调用数填为零。
