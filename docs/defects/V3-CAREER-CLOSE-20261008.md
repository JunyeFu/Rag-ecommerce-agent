# 求职收口实际缺陷与验证

2026-10-08，当前脏工作树，不代表已合入main。

| ID | 根因 | 最小修复 | 验收状态 |
|---|---|---|---|
| C01 | configured_provider沿用30秒/12000默认，真实评测180秒/48000 | 应用与两评测入口共享显式参数 | 新测试先失败，修复后通过 |
| C02 | Provider实例_usage累计跨run，Worker复用导致后续任务消耗旧额度；并发诊断亦串线 | 按run_id和异步ContextVar隔离用量及规划诊断，同run仍累计 | 顺序/并发测试先失败；Provider相关19通过 |
| C03 | API/Worker RuntimeIdentity固定deterministic-demo，即使真实模型开启 | 由实际provider model标识记录，fake明确保留 | 静态修正，持久数据库Trace待验 |
| C04 | 旧消融deterministic_vector是词集合重合，不是BGE；现有BGE只报融合 | 扩展现有入口，同输入测BM25/BGE向量/RRF | 本轮已运行，报告分三路；公开十例不等于challenge |
| C05 | 现有并发是ASGI内存fixture，不证明durable Worker | 增加访问真实API及数据库readback的入口 | Docker引擎不可连接，尚未运行 |
| C06 | Android黄金测试15秒fixture等待，不能用于MiMo实测 | 单独真实10分钟观察档，不更改fixture语义 | unit/lint/debug/androidTest编译通过；真实业务未运行 |
| C07 | G03最终解释被ProviderUnsupportedAmount拦截；原报告没有保存违规金额，无法进一步确定模型生成/金额识别根因 | 仅增加违规金额数值诊断，不记录模型原文；未改安全约束、未重跑 | 单元回归通过；黄金集仍失败，模型行为修复待定位 |

过程：三个新回归失败复现；修复后19 Provider测试通过；加入金额诊断回归后的Python非集成130 passed，15 deselected。没有追加fallback、自动重试或备用Provider。

设备：独立Pixel_9 emulator-5554已从标准emulator入口启动，未清数据；未操作其他项目设备。Docker Desktop进程启动后Linux引擎仍不可连接，基础设施不签收。

Android第一次编译使用旧JAVA_HOME，javac拒绝source21；仅在进程内显式设置现有JDK21后重跑，这是环境失败，不降低项目Java版本。

后续：用户启动Docker后，引擎29.8.0已连接。固定Compose镜像下载遇DockerHub认证EOF；官方Qdrant GHCR固定tag不存在，MinIO Quay固定tag返回401。采用本机缓存PostgreSQL18.3独立临时数据库完成迁移head/current/check及12项PostgreSQL集成，全部通过，不冒充原定16版本或MinIO/Qdrant完整链。测试后仅清理本轮自建临时容器，银行容器未操作。详见career-close-docker-followup-20261008.json；没有新增真实模型调用。

真实MiMo本轮黄金10与专项4各执行一次，报告保留原始失败分母；Android另有10槽位。当前候选与商业发布均不继承历史GO；未提交推送。

本轮实际黄金可解析9/10，G03失败；工具参数合法10/10，读取工具链10/10完成不等于最终业务成功。专项4/4通过。推荐证据覆盖100%，未授权写入0；输出结果的商业事实检测为0，但有1次未支持金额被拦截，不能宣称模型从未尝试生成商业错误。原报告不覆盖后来新增的数值诊断代码。

真实BGE公开十例：BM25、向量、RRF的Recall@10和NDCG@10均1.0。这是小规模已知SKU回归，不能证明融合收益或困难集达标。挑战集1000例参考构造器检查通过，不冒充真实检索/AgentRuntime挑战结果。

Android最新构建90任务：9执行、81UP-TO-DATE，如实保留缓存状态。Ops check/test(2)/build通过但五工作流未复验。基础设施、30并发、真实Android与干净启动阻塞于Docker引擎；当前结论HOLD。
