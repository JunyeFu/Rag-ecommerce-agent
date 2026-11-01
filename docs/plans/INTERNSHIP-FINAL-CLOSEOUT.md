# 实习投递版长执行收口

批准日期：2026-10-09；目标：2026-10-20。本轮交付本地候选，不提交推送或发布。

按V3-FINAL-01到05依次执行：基线环境→Agent与原生多模态→真实质量→24场景MiMo/Android联合验收→独立复审与求职封版。

固定自有60SKU、API0.2.0、mimo-v2.5、单请求180秒、单AgentRun48000Token、总2000000Token、24首测+最多6根因修复复测。选图与原生16kHz单声道PCM WAV录音(最多60秒)，确认识别后导购，保留纵向推荐。

LOCAL_PORTFOLIO_READY只有全部必要门槛通过才GO；PUBLIC_RELEASE=NOT_PERFORMED；COMMERCIAL_RELEASE=NO_GO。历史Release不继承。

总清单及根因：docs/defects/V3-FINAL-CLOSEOUT.md。证据写入各包evidence与docs/evidence/v3/final-*，外部导航手工同步，保留个人草稿。

门槛：黄金10/10可解析、流程>=8/10；4多模态正确；Android>=8/10且录音/图片/审批/隔离/恢复必须通过；证据100%；未授权写入0；RAG Recall@10>=0.90、NDCG@10>=0.80；真实Worker30并发无丢失/重复，API接受p95<200ms、fake首状态p95<1秒；必要回归及独立目录启动通过。

## 2026-10-13 剩余执行计划

### 最新实施进展（下面规划快照保留为历史）

N01—N04各自声明范围完成；A08-R5与A10-R5当前源码完整实测通过，累计完整原生8/10。当前215项Python、真实BGE消融、双Worker 30并发、自然300秒租约恢复和Ops五工作流通过。810文件独立目录初步启动已完成，但后续10个文件改变，不能作为最终同版封版；实际源码debug APK构建及41项Java21单测通过。24题/4稿/8类材料在外部导航完成引用及导出验证，个人掌握不代签。

A02/M03真实人声、A09 Chrome首次设置按用户选择稍后处理；不代接受条款，不导入音频。N07最终回归、N08同版最终导出、N09成片和N11独立签收未关闭。[本地交付矩阵](../release/local-portfolio.json)明确HOLD，PUBLIC_RELEASE=NOT_PERFORMED，COMMERCIAL_RELEASE=NO_GO。原共享预算最近结算265,339/2MToken、94HTTP；余额不产生复测授权。

仅核对与规划，不执行新实测、不追加许可、不提交发布。当前main HEAD d670e291d263a6e4f0f041f9c74c6e0246cb854c，写计划前344状态项；最新源码修复报告的11文件与当前一致。204 Python/41 Android单测/34视觉fixture是10.12报告，未在本轮重跑；完整先前原生记录6/10不能替当前审批增量签收。

详细执行卡与可导出清单维护在外部导航：[NEXT-STEPS.md](D:/Agent/project-navigation/records/rag-commerce/closeout/NEXT-STEPS.md)、[NEXT-STEPS.json](D:/Agent/project-navigation/records/rag-commerce/closeout/NEXT-STEPS.json)。沿用现有五包，不另建任务管理体系；预计33h＋6h缓冲，10.20目标不变，外部等待不计净工时。

| 顺序 | 原包 | 任务与退出条件 |
|---|---|---|
| N01–N02 | FINAL-01/03 | 核对Git/运行/设备/原预算；补A02原生执行入口和A09过期分支，非付费预检通过 |
| N03–N06 | FINAL-02/04 | 新授权后一次A08完整审批、一次A10整程恢复、一次A09零模型复测；A02/M03有效原生人声首测。UI/API/DB联合签收 |
| N07 | FINAL-03 | 最终变更回归、真实Worker容量/审批恢复、Ops五工作流、检索版本范围及挑战分层报告 |
| N08–N10 | FINAL-05 | 当前候选独立导出启动、同版APK/90秒视频/精选截图、24题/四稿/八类材料 |
| N11 | FINAL-05 | 独立复审全部必要门槛，达标才本地GO；公开NOT_PERFORMED、商业NO_GO |

A08-R4/A09-R1/A10-R5是待授权提议编号，不是已获许可；A10-R5尚不在安全执行器choices中。原6复测与12追加许可均已消耗，Token余额不代表新许可。A02/M03仍有原未消耗首测许可但需要本人麦克风配合。A09模拟器Chrome首次配置由本人完成；Codex Browser工具缺失不替代该步骤，也不阻塞已有Playwright。

原账本最近报告253,785/2,000,000 Token、86 HTTP、预留0；执行前只读复核原会话。旧报告、失败分母和用户资产全部保留；本次计划不更新manifest或包的验收状态。
