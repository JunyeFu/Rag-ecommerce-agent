# 当前候选收口缺陷表

## 2026-10-24 F60后续：原容量门禁通过

F60 / P1 / CLOSED_LOCAL_ACCEPTANCE：正常`python -m uvicorn`、保留access-log和结构化日志、真实PostgreSQL／两个8通道Worker／固定本地BGE＋Qdrant，完整十批×30全部通过。300/300完成，每Run恰一个成功终态；总接受p95=182.079ms，最慢批p95=190.832ms，202后首状态p95=111.482ms。验收器、分位算法、200ms／1s阈值均未修改，不拼接通过批次。

实测贡献项及最小修复：两层BaseHTTPMiddleware的任务/流转发使提交前p95=89.632ms、响应尾部88.237ms，直接ASGI后降至4.476ms／1.841ms；每Worker八份相同BGE模型改为共享同快照只读提供者，真实八路并行结果相同、各自客户端/索引独立，常驻约1GB降至342MB；启动期约21万长期存活对象0回收仍扫描49.8–61.1ms，启动回收后冻结静态图，保留运行期GC和原阈值，新循环对象回收测试通过。另修复默认INFO无输出这一诊断缺口，实际300条Turn耗时可与客户端报告对照。

全部失败均保留：初始正常CLI诊断批10失败；ASGI中间诊断批6/7失败；真实BGE原版批1、共享模型版批6、静态图版批7失败。后者说明单个优化不等于通过，不将每个历史离群值唯一归因某个因素。最后完整正常CLI组独立签收，全部237 Python／0跳过、三端契约及11工具生成检查通过。最慢批距200ms约9.17ms，仅声明本轮本地门禁，不宣称生产SLA。

[逐批、逐轮、根因与源码身份](../evidence/v3/final-F60-review-20261024.json)。下方同日OPEN为本次修复前历史，原报告不覆写。0新增MiMo，录音继续暂缓；最终同版封版仍未完成，整体HOLD。

## 2026-10-24 基础设施复验增量

- INFRA-01 / P1 / FIXED_LOCAL：API与两个8通道Worker从空MinIO启动时，`bucket_exists`与`make_bucket`之间存在TOCTOU。另一个通道已成功创建桶后，`BucketAlreadyOwnedByYou`未处理导致两个Worker退出，首批30个Turn保持PENDING、0个AgentRun开始。只在当前创建请求接受同账号已创建这一S3结果，AccessDenied与BucketAlreadyExists继续原样失败，不新增重试。`media.py`与真实MinIO强制并发回归先红后绿，另2项错误边界单测；修复后全套231/231、0跳过。重新从确认无对象的本轮测试桶启动API/双Worker通过；旧30个待领取任务保存在首次数据库，未清空后重算。
- INFRA-02 / P2 / FIXED_LOCAL：Ops共享页头把固定`2026-08-26 17:00 CST`显示为“证据时点”，与真实数据库运营状态不符。改为“按当前API返回状态展示”，不编造当前时间或另加接口。浏览器先因新说明缺失而红，修复后五工作流通过。中间一次重跑误用了已真实解决的冲突夹具（2通过／1失败／2未执行）；保留旧决策，使用既有seed入口准备新的PENDING冲突ID再验，未把旧记录改回PENDING。
- F60 / P1 / OPEN：本轮十批×30全部完成、数据库终态均唯一，但批1/3/5接受p95越过200ms；全体p95=229.731ms，202后首状态p95=218.210ms。此控制CLI使用fixture检索并关闭access-log，不冒充最终标准启动签收；已有失败不覆盖。现有标准Server.run观测路径300任务通过（接受p95=133.038ms、首状态192.968ms），但这是带观察器的诊断，不能替代失败验收，也不能据此把GC/连接池/日志猜作根因。性能项仍未签收。
- 当前功能层级通过：固定四服务健康；Alembic head0016／check无漂移；真实本地BGE/Qdrant冻结120查询；两个独立检索进程不重建60点共享索引；自然300秒Worker租约接管保持原购物数量、唯一收据／终态；真实HTTP跨API和双Worker重启快照及SSE游标一致，错误用户404／越界游标409。详见`docs/evidence/v3/final-infrastructure-recheck-20261024.json`。
- Android的F64大字号操作及后续TalkBack修复按`docs/evidence/v3/android-talkback-20261024.json`所声明的8条原生／41项fixture范围验收；本轮未重跑Android。下方10月13日OPEN是历史快照，不覆盖后续对应范围证据。

旧缺陷与旧报告保持原始日期及分母。录音按用户要求暂缓，Chrome首次设置未代办；未执行当前最终同版封版，整体仍HOLD，0新增真实模型调用。

## 2026-10-13 N11独立复审增量

F64 / P1（OPEN，200%字体推荐卡关键操作越界）：真实已完成任务的推荐页在font_scale=2.0时只显示匹配/风险文本，证据、价格、比较、保存/待购落在可见区之外。当前RecommendationPage为固定高度Column，没有候选内的阅读适配；可滚动节点是顶部控制区与切换候选的VerticalPager，不能把翻下一候选当成当前候选关键动作可达。需要按保留主/次/再次纵向设计的前提提供大字体下的可达阅读和动作布局，验证真实长文本、来源与比较按钮，不仅测试短fixture。截图：output/f63-qa-20261013/real-recommendation-font-2.0.png；NFR06仍未签收。

F63 / P1（FIXED_LOCAL，返回对话后无法重开已有推荐）：showConversation由ReturnToMissionConversation置true，而没有对应UI入口或本地动作置回false，旧测试靠新的TurnProducts事件回推荐，漏测用户不再请求模型的往返。增加“查看当前推荐”及ShowCurrentRecommendations，仅切换本地视图并保留候选/比较/输入。新增视觉用例先因找不到入口失败，修复后通过；41单测、35视觉fixture、lint 0error/18warning及构建通过。专用QA安装更新后从原真实任务恢复，原生点击返回对话/查看当前推荐，显示原01/03候选，不新增模型调用。对应报告：docs/evidence/v3/final-F63-navigation-review-20261013.json。不是完整A06/多模态重验或最终封版；F64新发现仍OPEN。

F62 / P1（后续操作覆盖购物目标，源码及实际只读复核通过）：NFR06真实页面发现已完成推荐仍待确认品类/预算。API外层goal为“预算2000元的通勤手机”，内部mission.goal却是数量2加入待购操作，预算null。运行时把Turn操作当Mission目标，快照只按版本采纳错误事件。修复为私有command.mission_goal在事务预留中绑定Thread目标、持久Worker恢复；原Turn文本/模型输入/冻结参数不变。快照以Thread为权威，当前版本历史事件公开投影校正、原日志不重写；坏mission载荷明确失败。218项全套Python/0skip、PG重建、代码生成通过。重载实际API/两Worker后，原真实任务预算200000分/手机1/unknowns空，原生页面显示“总预算¥2000”，待购数量2未变，265339Token/94调用未变。证据：docs/evidence/v3/final-F62-mission-goal-review-20261013.json。可访问性全项尚未签收。

F61 / P1（安装环境生成的dex验证产物缺失，已安装QA包缓解、最终同版待复验）：原debug APK为run-from-apk/location error；30次冷启动p95=3179ms。Perfetto首traversal约1953ms，直接845次VerifyClass约558ms，主线程draw仅30ms。只对同一包编译准备后实际status=verify（不是speed），class verification直接切片降至0；同一APK另30次p95=1785ms通过，仍保留一次2630ms离群、原失败及采集器失败。未清数据、未改UI、未关闭StrictMode；907条本窗应用日志无fatal/StrictMode。准备命令写入docs/demo/V3-ANDROID-PREPARE.md；最终源码APK要重新核对，不宣称debug结果是生产release性能。证据：docs/evidence/v3/final-NFR07-verified-dex-review-20261013.json。

- F59 / P1（验收计时，局部修复通过）：run_v3_durable_load.py将首状态从POST发送开始计时，PRD NFR04要求从202接受后开始。时钟/HTTP边界红测原得400ms、期望250ms，修复为accepted_at起算后通过。Worker开始仍从POST发送计时，报告明确区分。旧报告保留，不追改历史数字。
- F60 / P1（连续负载性能，OPEN）：原单批30Mission通过不足以关闭十批要求。首次连续10批×30全部完成且每Run数据库终态恰一次；总接受p95=265.8906ms超过200ms，批3/5/6/7/8失败；202后首状态p95=322.9994ms通过。独立PostgreSQL/Qdrant/双Worker、显式fake、本地BGE，0MiMo调用。性能根因尚未确定，不能将连接池、线程池或本机争用猜测写成根因；不重跑取最好值。详细报告：docs/evidence/v3/final-N07-durable-load-10-batches-20261013.json。
- 证据缺口而非已证实代码bug：NFR06完整48dp/200%字体/TalkBack遍历、NFR07固定设备30次冷启动p95与fatal/StrictMode尚无本轮全量报告。七组设计Token对比检查通过仅证明这些颜色对；少数fixture高度断言不代表全控件可访问性。需补测，不能将剩余项仅列为语音和Chrome就签收。

## 2026-10-13 N02新增实际缺陷

F58 / P1（Ops实际UI）：Trace列表使用工具名+参数哈希作React key；审批暂停/恢复会保留相同参数的两条实际执行尝试，导致重复key控制台错误，并存在丢行/错复用风险。以run_id+追加顺序标识每条尝试，保留完整日志；Playwright按API工具数组长度核对刷新前后实际行数，五工作流复验。

F57 / P1（N07故障注入工具）：旧脚本直接写approved_tools，未绑定F51要求的具体invocation；真实执行器以TOOL_FAILURE拒绝“approved invocation changed; start a new Turn”，45秒内没有业务收据而超时。修复为先由真实Worker产生提案、调用TurnService.decide冻结具体调用，再启动会被中断的子进程。保留first失败，另写02报告；不放宽生产审批规则。

F56 / P1（验收工具）：A08-R4面对保留的FAILED提案后，测试仍强制等待仅COMPLETED快照才有的connection_RECOVERED，20秒超时，零新Run/零模型调用。实际APP正确恢复为已连接、失败提示与对话输入。测试改为显式传入真实priorRunStatus；仅A08的FAILED来源允许直接检查对话输入，并只在实际存在时返回对话。继续要求同Mission/version存在真正完成的MiMo商品推荐、目标待购为空；不改后端失败状态或注入成功UI。原A08-R4失败保留。

F55 / P1（验收工具）：GoldenScenarioApiFlowTest拼接health时假设配置末尾带斜杠，HTTP 20882health导致Assumption跳过；run_android_instrumentation_case仅依据OK字符串把跳过写成PASS。原始回执final-N02-fake-native-preflight-20261013.json保留但已作废，不代表业务完成；独立数据库零Turn证实未执行业务。修复URL分隔符并拒绝-3/-4或Assumption回执，按测试先失败后通过验证，再重跑原生。

F54进度：源码修复、31项非付费定向回归、20项真实PostgreSQL测试通过；独立数据库迁移0015及漂移检查通过。Android过期报价验收仍待完成，尚未关闭总门禁。证据：`docs/evidence/v3/final-quote-lifecycle-20261013.json`。

F54 / P1：DemoCommerce.get_offers忽略fresh，每次读取重新生成采集时间与15分钟有效期；resolve_offer亦重新生成有效期，工具offer.find/requote直接绕过公共报价读取。结果是读取即可使报价续期，真实过期状态无法稳定呈现。修复要求：owner报价快照持久化、普通读取不续期、显式fresh才重新询价、过期解析不返回链接、API/Worker工具共享状态，用户删除包含报价快照。先复现再修复，原A09失败仍保留。

2026-10-12 更新，当前main脏工作树；历史GO不用于签收。下方旧执行记录保留原日期和失败分母，最新结果以末尾收尾记录为准。

| ID | 优先级 | 代码根因/触发 | 修复与回归条件 | 状态 |
|---|---|---|---|---|
| F01 | P0 | start_v3_demo及Ops代理硬编码8080，与其他项目冲突 | 单一API端口20881、Android/Ops/验收一致；完整启动与拥有进程停止已实测 | fixed_local |
| F02 | P0 | QdrantHybridSemanticIndex._ensure_index每进程首次查询删除collection | 显式构建新collection后原子切换；查询只读；索引测试和两个真实Worker并发通过 | fixed_local |
| F03 | P0 | 旧Worker创建InMemoryMediaStore且vision.identify固定文本 | 当前共享MinIO及实际媒体理解已实现；M01-R2/A03-R1真实图片通过；实际有效语音仍待人声 | implemented_image_verified_audio_pending |
| F04 | P1 | 旧Android语音只有GetContent，没有原生录音与识别确认 | 原生PCM录音、预览、取消及后台清理已实现/验证；M03/A02完整有效人声闭环未签收 | blocked_real_audio |
| F05 | P0 | Provider仅响应后核算run用量，无跨进程总预算 | 调用前预留额度、输出上限、共享预算与24/6场景槽位；未知usage保留预留并停止；当前集成测试通过 | fixed_local |
| F06 | P1 | G03被UnsupportedAmount拦截，原文未保存，根因仍未确证 | 定位预算/报价/生成金额混淆，保留事实约束，使用授权复测 | open |
| F07 | P1 | BGE报告只有10公开已知SKU；1000例为参考构造器 | 120查询40/80冻结，BM25/BGE/RRF真实分层消融通过；融合无收益、自动标注及小目录局限保留 | fixed_local |
| F08 | P1 | 固定Compose、真实durable30并发/恢复及当前Android/Ops未完整验收 | 完整固定环境及UI/API/DB状态验收 | open |
| F09 | P1 | 当前源码与媒体/README/面试资料证据版本不一致 | 独立候选导出启动、刷新APK/视频/24题四稿八类材料 | open |
| F10 | P1 | FINAL首次真实durable压测30/30完成，但API异步路由同步访问PG，Worker串行执行；接受p95=769.7ms/首状态p95=12378.1ms | 两Worker与连接池/增量事务；公开排队状态来自DB且不推进游标；最新接受172.12ms/首公开756.50ms，Worker开始延迟另报 | fixed_local |
| F11 | P1 | PowerShell JSON反序列化日期类型与字符串比较不匹配，停止脚本未停止本轮进程；Python还有启动器子进程 | 按DateTime比较PID启动时间，停止已验证拥有的完整进程树；实测停止/重新启动 | fixed_local |
| F12 | P1 | ADB真实长按后没有录音文件；Button内部clickable消费事件，与外层pointerInput冲突 | 改为Surface单一手势所有者，保留无障碍语义；真实3.328秒mono16k PCM16 WAV、预览、取消/后台删除通过，媒体表0记录；有效语音和MiMo另验 | fixed_local |
| F13 | P1 | PostgresOpsStore继承静态Trace、连接器健康、示例评测成功和门禁；UI还有固定P50/P95 | 真实事件投影；数据库声明自有目录/未授权联盟/合成复核练习/待验门禁；未知数值保持null；Ops五工作流12.5秒全通过 | fixed_local |
| F14 | P1 | 集成测试与演示复用DB，测试构造器写入非产品payload，Ops冲突状态也已被先前测试消耗 | 独立集成/候选/进程故障数据库；旧数据保留；Trace只投影当前产品Agent命名空间；真实Ops五工作流通过 | fixed_local |
| F15 | P1 | Ops评测run_id只由请求内容hash生成，12次不同幂等键请求在数据库审计中存在，但恢复列表被同一ID折叠 | 独立run_id、同键回放原结果；12次提交、重建store、刷新与第二会话通过；写事务锁定幂等键 | fixed_local |
| F16 | P1 | observeLocal每次mission/偏好变化都覆盖当前导航，恢复时DECISIONS与锁定冲突；恢复页另把固定运行文案当结论 | 本地导航只首次恢复且遵循锁定规则；删除伪结论；Pixel_9实际API八黄金16.504秒通过，28视觉fixture45.316秒通过 | fixed_local |
| F17 | P1 | Windows gradlew.bat在Java执行后无错误码判断，编译失败仍exit /b 0，旧测试APK因此被再次安装 | 不存在任务返回1；当前测试APK编译54tasks/6executed/48UP-TO-DATE后，设备八黄金与28视觉通过 | fixed_local |
| F18 | P1 | Ops读取run_resumed判定恢复，但运行时从不产生该事件，恢复Trace恒为false | 非终态检查点接管产生公开progress与内部恢复事件；真实子进程终止、自然300秒租约回收和单写入通过 | fixed_local |
| F19 | P1 | 新验收脚本原先空推荐也能取得证据覆盖1，预期商品和用户操作未参与最终通过判定 | 付费前修正非空推荐/预期商品/完整流程检查；用户API按钮操作与模型工具调用分列，HTTP恢复不冒充Android断网 | fixed_local |
| F20 | P1 | M01真实HTTP200/508Token，但媒体工具返回ValidationError；json_object只保证JSON语法，原提示无字面结构且user消息只有图片；异常只存类型，首测具体错误字段不可还原 | 保留首次失败；提供五字段字面JSON模板及同条user文本指令，保持严格契约、不补默认/不丢额外字段；输出只含字段位置/错误类型的诊断；非付费测试后最多一次已登记根因复测 | fixed_local |
| F21 | P1 | G07已有真实推荐，下一轮明确报价UUID+数量2加入待购，却再次WAITING_CLARIFICATION；_explicit_write_target只认同一run的offers，忽略用户已提供的明确目标 | 明确报价UUID且明确加入待购可强制模型生成cart.update参数；仍由工具核验报价存在并请求审批，不预授权、不解析假价格；单测后根因复测 | fixed_local |
| F22 | P1 | M01-R1识别/确认通过，但阶段总结再次生成1299/1799/1899元且被事实守卫阻断；respond只有阶段计数却再次传入购买goal，诱导无事实的推荐回答 | 成功阶段只发送真实阶段计数，不再次发送购买goal；澄清保留goal；明确不声称未完成阶段、关闭该短摘要思考并限制512输出；原金额守卫保持不变 | fixed_local |
| F23 | P1 | G07-R2已提出审批、批准后实际写入成功，但明确报价意图仍强制再次规划cart.update；模型遵循不重复成功工具而省略调用，最终FAILED/重复审批409 | 检查内部真实cart工具结果，完成该明确写入阶段后停止重复规划并进入摘要；不把失败改成成功、不回退、不自动重试；新增单测与根因复测 | fixed_local |
| F24 | P1 | A01界面复审：商品只有“来源已保存”，报价声称“可展开查看”却是无点击行为的Text；用户无法实际查看证据 | 原生依据弹窗读取真实商品/报价EvidenceRef及事实，保留纵向推荐布局；视觉fixture和真实A01点击/后端状态复验 | fixed_local |
| F25 | P1 | G07-R3初始推荐通过，待购提案再次缺少工具调用；Provider依赖MiMo不支持的指定tool_choice，官方说明非auto值被忽略 | 明确写意图一次生成符合注册Schema的JSON参数，随后仍请求审批；非法输出直接失败，不重试、不备用、不直接写入 | fixed_local |
| F26 | P0 | 原生A01后端35.5秒完成，但手机永久分析中；AgentEventStream沿用REST callTimeout=35s，body.string读取异常没有resume等待协程，且整流缓冲隐藏公开进度 | SSE逐帧Flow与明确读失败；36单测、非付费真实恢复、获单独授权的A01-R1原生输入/证据/数据库验收通过 | fixed_local |
| F27 | P1 | 普通页面显示ONLINE/RECOVERED、DEMO_FIXTURE风险及原始Provider异常，加载页展示开发者思维链提示 | 连接和已知失败使用用户文案，保留技术诊断；演示商品/报价边界仍明确显示，不改变美术和纵向浏览 | verifying |
| F28 | P1 | A06真实次推荐比较按钮裁剪为0高；选中后顶部比较提示继续占用候选区域，固定内容无高度限制 | 控制区限高并滚动，保留候选VerticalPager；29项视觉fixture全过，单独授权A06-R1原生/API/数据库复测通过，0新增模型调用 | verified_local |
| F29 | P1 | A07待购只有加入入口，没有数量/移除；恢复忽略API quantity且Room旧CART ID并入状态，可能让已移除商品重新出现 | 原生数量/移除确认、API唯一状态已实现；单独授权A07-R1两阶段UI/API/数据库及实际进程重启通过，0模型调用 | verified_local |
| F30 | P2 | A07脚本只滚动LazyColumn商家分组，已启用的移除按钮仍被裁剪为零面积，点击未命中 | 只读bounds定位，精确滚动子按钮；四报价fixture及授权A07-R1两阶段通过，首测失败保留 | verified_local |
| F31 | P1 | A04验收把products到达当成完成，页面尚未稳定便断言失败；随后关闭场景付费许可，已有Worker后续调用被预算守卫拒绝 | UI等待实际完成；原600秒内等待已接受Run结束再关闭许可；A04-R1原生/API/数据库完整通过，首测保留 | verified_local |
| F32 | P1 | 已观测FAILED快照恢复只处理COMPLETED/WAITING_APPROVAL，失败任务会丢失失败文案并默认展示中间候选 | FAILED恢复到对话并显示明确未完成，不显示成功；只读原生恢复1/1通过，不新增模型调用 | verified_local |
| F33 | P2 | 只读诊断在CHECKING阶段点击禁用任务标签，无实际点击却等任务页文案超时 | 核对初始Disabled并等待实际启用后点击，原生1/1通过；撤回未经证实的导航保护改动，不改产品导航安全锁 | verified_local |
| F34 | P2 | A03图库选择器未定位唯一图片而提前失败，后续诊断暴露系统窗口root暂空及附件在懒加载列表中未组合，不能按节点瞬时缺失宣称没有返回 | 等系统图片节点、按bounds点击并滚动附件；A03-R1原生图库/实际识别/确认/推荐完整通过，首测保留 | verified_local |
| F35 | P1 | resolveApproval批准后未读取API待购状态；随后同步版本在decide之后读取，异步Worker接续后又会过早读取 | 当前消费真实终态后再读取API数量，保留generation隔离；41单测/PG回归通过，新的原生审批尚未复测 | verified_local_pending_real |
| F36 | P2 | A08脚本拼接API地址时假定末尾有/，实际BuildConfig无/，生成20881v1并抛MalformedURLException；未发送业务请求 | 与实际配置统一地址路径分隔；原生只读API检查1/1通过，完整审批复测等待授权，首测0Token失败保留 | verified_local |
| F37 | P1 | 待购报价的重新询价按钮只返回对话；外部来源直接调用跳转，缺少原生确认；报价解析忽略expires_at | 复用fresh=true报价API更新单商品；原生外跳确认；实际过期报价阻断；错误不吞成成功 | fixing |
| F38 | P1 | ThreadSnapshot只投影最近Run；推荐后发起只含cart.update的审批Run，candidates变为空，进程恢复丢失同一Mission候选 | 定向API先复现1失败；按owner/thread/version投影最近products，状态/游标仍取最新Run；独立PG及全191回归通过，原生安全恢复待验收 | fixed_local |
| F39 | P2 | A10脚本使用不存在的mission_submit/rank_0标签，发送前即失败 | 统一生产send_turn/recommendation_rank_0；原生只读发送控件1/1通过，完整恢复复测等待授权 | verified_local |
| F40 | P2 / external | A09外部来源跳转被Chrome首次使用页面阻断，未到真实地址栏；原生报价过期分支也未执行 | 不代替用户接受浏览器条款；首测保留，等待用户完成初始配置及独立复测授权 | blocked |
| F41 | P2 | A08-R1第二次输入节点缺失，最初只归因懒加载；A08-R2证实整个mission_conversation不存在，原诊断不足 | 父列表滚动不是完整根因修复；实际审批监听接管竞态见F43；旧失败保留 | superseded_by_F43 |
| F42 | P2 | A10-R1只用logcat判断原生完成，丢弃instrumentation stdout；真实推荐已完成但原生回执无法核对，600秒后失败 | 同时保留Android原生stdout，明确解析成功/失败及缺回执；无完整回执不通过，6项定向测试通过，不重跑模型 | fixed_local |
| F43 | P1 | A08-R2证实取消审批后整个mission_conversation不存在；监听抢占Run且还能应用旧审批快照改写状态 | 当前在本地Run/审批状态写入前阻止监听接管，显式决定正常消费；实际ViewModel边界时序单测通过，新真实复测未执行 | verified_local_pending_real |
| F44 | provider failure | A08-R3的真实模型cart.update提案未满足严格Schema，执行器拒绝，0业务写入 | 保留315 Token/1调用失败和前台错误，不扩大Schema、不静默修正、不自动重试；原始响应未保存，不能编造具体非法字段 | failed_preserved |
| F45 | P2 | A10-R2分阶段instrumentation结束会关闭App，紧接pidof抛CalledProcessError；异常未被原错误记录捕获，报告未输出 | 同步启动真实App再获取PID并force-stop；记录已观测设备命令失败；先失败后修复，7项定向测试通过，R2部分证据单独保留 | fixed_local |
| F46 | P1 | A10-R3批准后数据库COMPLETED且已有待购，但前台IOException提示“确认结果未核实”却仍显示已连接、停留推荐页，缺少明确恢复入口 | 已知网络错误切到离线对话并暴露只读恢复；39单测/34视觉及真实只读恢复通过；A10-R4隔离/删除收尾通过，不覆盖整程失败 | verified_local_remaining_steps |
| F47 | P1 | A08-R3只留下invalid proposal，JSON/字段/类型错误被统一抹去，真实非法字段不可还原 | 严格JSON类型校验；仅记录Schema字段/错误类型，未知字段名脱敏；显式结构提示，不记录原始响应、不重试 | verified_local_pending_real |
| F48 | P0 | 合法Schema提案可以把用户数量2默认成1，或替换为另一个合法报价UUID | 明确报价与数量必须与请求一致；不自动修改参数；4项红测复现后通过 | verified_local |
| F49 | P1 | resolvingApproval只阻止领取Run，未阻止DataStore旧审批快照把isLoading改回false | 决定期间不应用本地Run/审批快照；可控接口时序测试核对忙碌、重复点击与完成后真实待购读取 | verified_local |
| F50 | P1 | 审批HttpException分支仍保留ONLINE/推荐页，拒绝后缺少状态核对入口 | 锁定操作并回到对话，暴露只读重连；不自动再次批准 | verified_local |
| F51 | P1 | TurnService._decide在API内执行Agent和模型，202要等全部操作完成；已批准命令也未写回任务索引 | 批准参数与具体调用归属写回api_turns后返回；Worker领取，重复批准幂等，拒绝/编辑与已批准任务互斥，终态后刷新待购 | verified_local_process_review |
| F52 | P0 | RunCheckpoint只保存已完成结果，不保存待审批参数；批准后重新规划能将数量2换成99；只授权工具名会放行不同调用 | 持久化pending_calls、恢复冻结提案、API按invocation_id授权；不同参数的同名新调用失败，不继承批准；旧未保存提案不得猜测重建 | verified_local_process_review |
| F53 | P1 | 规划器仅重复已完成调用时不增加tool_attempts，循环直到GraphRecursionError，未形成业务失败终态 | 无进展重复规划直接生成REPLAN_LIMIT失败；无额外调用、无提高递归/工具预算 | verified_local |

固定Compose全部健康、迁移与显式BGE构建成功；MinIO固定官方源码版本构建（原镜像仓401），未改全局代理。
当前Python全套185项通过（22.05秒，无跳过），额外A01授权账本边界5项定向测试通过。复验首次MinIO失败是命令用了错误的本地演示口令，改为启动脚本同一显式值后通过；没有增加重试或降级。
最新Android unit/lint/debug通过（60 tasks: 25 executed/4 FROM-CACHE/31 UP-TO-DATE）；Benchmark通过（54 tasks: 19 executed/35 UP-TO-DATE）。lint第三方Navigation自定义检查过期警告保留，不写成零警告。
真实独立Worker故障注入303.469秒通过，实际终止写入后进程、自然五分钟租约到期，业务updated_at未改变、收据/终态各1；持久事件游标回放通过，不代替HTTP SSE重连或原生审批验收。

## F20 媒体结构化边界

首次证据：docs/evidence/v3/final-real-M01-first-20261009.json。失败是应用类型契约拒绝，不是HTTP失败，不记作识别成功。首次只记录ValidationError，因此不能声称已还原具体非法字段。
MiMo官方仅承诺json_object产生合法JSON，字段结构由提示词约束：[Structured Outputs](https://mimo.mi.com/docs/en-US/quick-start/usage-guide/text-generation/structured-output)。不采用未在官方材料确认支持的json_schema参数；不重试、不fallback、不放宽验收。
修复针对已证实的结构约束与诊断缺口：明确五字段JSON模板、未知值表示、额外字段禁止，user图片后附同一文本指令；已知契约失败记录脱敏字段路径/类型，普通UI仍显示识别失败。复测若失败必须保留，不允许自动追加。

## F21 明确待购后续操作

首次证据：docs/evidence/v3/final-real-G07-first-20261009.json；后续run 64d52b79-6b62-5ea9-a055-bc5b308de9d1没有工具事件，仅message/clarification_required。第二轮没有前一run的offers，因此显式写入工具选择未生效。
修复只覆盖已明确给出的报价UUID及用户加入待购意图。UUID不是价格/库存证明；真实commerce继续检查报价存在，审批、收据和幂等仍由执行器控制。未明确目标不自行选商品；没有实现泛化的对话记忆或直接执行写入。
G07-R1仍失败：fc636fe9-cee1-58fd-a90f-17f32610a84b在规划阶段ProviderInvalidResponse。代码复审发现工具描述“未经审批不得调用”与“调用参数以提出审批请求”相互矛盾；修正为规划只提出待审批参数，实际写入仍需执行器审批。新增脱敏provider_detail，后续非法输出不再只剩类型名。

## F22 阶段摘要不能再次回答购买请求

证据：docs/evidence/v3/final-real-M01-R1-20261009.json；确认run 94a259e5-7243-5373-86f4-c2f89ad69937完成真实检索/事实/报价/比较后被ProviderUnsupportedAmount终止，blocked_amounts_minor为129900/179900/189900。本次守卫有效，未把伪造金额展示成报价。
respond提示要求阶段总结，但user消息又提供购买goal和预算，没有实际报价，模型再次给出购买建议。修复删除成功摘要不需要的goal数据，输入仅实际工具阶段与数量；空结果澄清仍有goal。没有扩大金额白名单、擦除数字、返回假成功或添加重试。M01-R2必须复核整个确认链；先保留R1失败分母。
M01-R2已通过完整图片识别、等待确认、版本递增、幂等和带证据推荐；首次与R1仍计失败。

## F23 已完成写入不再强制重复规划

G07-R2的审批run 60c67eeb-09dc-5377-8592-80f510894f73事件为cart.update/approval_required → 批准后的cart.update/tool_completed → ProviderInvalidResponse("provider omitted required cart.update tool call")。这是完成阶段识别错误，不是审批被绕过。
修复在已观察到真实cart工具结果且仍是同一明确待购意图时返回无新工具，进入正常摘要；收据仍保证业务写入一次。新run复测独立拥有测试数据，原FAILED和已批准写入保留，不覆盖原记录。

## F25 MiMo不支持指定tool_choice

证据：docs/evidence/v3/final-real-G07-R3-20261009.json，后续run 3c900f56-241a-591e-a683-f4894f4dd0cf在写入前失败，数据库待购为空。原报告failure_type=null但approval=false，不记为流程成功。
官方[Chat API](https://mimo.mi.com/docs/en-US/api/chat)明确只支持auto，非auto字段会被移除。不是调整提示词后随机重跑的问题。
修复将已明确的写意图直接走一次json_object参数提案，参数按原注册Schema校验，再生成同一ToolCall交给执行器；未明确意图仍走原自动工具规划。失败不增加第二次请求。此路径没有模型回退，也不自动授权操作。
G07-R4若执行将占用最后一个已授权复测槽位；仍失败则停止该路径并请求必要方向，不能无限重跑。
G07-R4已通过：真实待购提案、批准后的写入和重复审批幂等全部成立；收据一次。首次和R1/R2/R3仍保留失败，已用完6个复测槽位。

## F26 Android长SSE读取不能沿用REST整次时限

首次原生A01 run 3e3447bd-caa8-52f6-9276-6833c2bf7948，12:00:43接受、12:01:18完成，手机继续显示分析中。源码AppModule为REST设callTimeout35秒；AgentEventStream onResponse的body.string抛IOException不调用callback，因此suspendCancellableCoroutine没有完成。此前快速fixture隐藏了真实模型延迟。
修复只针对SSE连接：继承30秒idle readTimeout检测心跳失联，但移除REST整次时限；公开事件逐帧Flow送达并保存游标；读失败关闭Flow使UI明确离线，取消关闭Call，契约错误显式失败并记录无载荷的类型诊断。不增加模型等待窗口、不自动重跑A01、不放宽业务门槛。
单测分别覆盖超过REST时限、正文读断线、游标/身份头；原生修复可恢复已有真实任务用于非付费回归，但不能把首次A01改成通过。新真实复测需另行授权，因为6个复测槽位已耗尽。
用户明确追加仅一次A01-R1，授权记录位于V3-FINAL-04/evidence/A01-EXTRA-AUTHORIZATION.json。该复测已通过：原生新输入、推荐和证据弹窗，后台run完成且终态一次、证据覆盖完整、无未授权写入。用了7809 Token/2次HTTP；首次A01仍为失败，不覆盖报告。证据：docs/evidence/v3/final-real-A01-R1-20261009.json。
120查询冻结消融通过，RRF的验收NDCG=0.99348，低于BM25=1.0；不宣称融合收益。冻结集未调参，硬约束由独立原始目录判定器复核。
本次全量unit暴露4项旧嵌入stub文本缺少新增可信用途字段，更新精确stub输入后复验；真实检索数据和冻结qrels不变。

## F28 候选操作区域被顶部控件挤占

A06首测复用A01-R1真实候选，没有新增模型调用。主推荐选中成功，但次推荐Checkbox边界为(l=116,t=2313,r=179,b=2313)px，高度为0；数据库也只有主推荐一项。不是测试等待过短或模型没有推荐。失败报告：docs/evidence/v3/final-real-A06-first-20261009.json。

RecommendationResult的顶部列没有高度边界，动态比较提示和约束挤压下方VerticalPager。修复控制区最大240dp并允许其自身滚动，不给候选内容增加独立竖向滚动，以保留主/次/再次整页浏览。原首测保留为失败，不能用fixture通过替换正式结果。

2026-10-09：用户明确授权唯一A06-R1无新增模型复测。通过实际MainActivity恢复A01-R1候选，先用原生控件取消首测残留选择，再完成三层纵向浏览、选中两项、决策比较、返回对话与再查看。原生1/1通过（54.625秒），PostgreSQL保存两项，无新Turn，无新付费调用，0Token；报告docs/evidence/v3/final-real-A06-R1-20261009.json。额度场景不激活付费许可，不能以UI复测授权新增模型调用。29项fixture由TestRunner PID13493实测0失败，单列为布局回归，不计入十条真实业务。

## F29 待购数量和移除未接入用户闭环

代码证据：EditorialOfferCard只有报价与跳转；NetworkShoppingRepository.addOffer固定quantity=1，restoreThread读取cart时只取offer_id；ShoppingViewModel.observeLocal将旧Room CART记录并入waitingOfferIds。API已有CartMutation set/remove及PostgreSQL持久化，无需公共契约升级。修复范围仅Android现有决策页、Repository、State/ViewModel及对应测试。回归要求：数量和移除均先原生确认；取消不写；API返回数量严格解析，缺字段不返回空成功；重启从API恢复数量和移除结果，不能依赖注入ShoppingUiState完成A07。

数量/移除确认与严格Cart解析已实现。38项单测、lint/debug通过；冷启动后局部原生fixture 1/1通过（PID2957，8.957秒），不是真实业务签收。A07首次真实验收已保存方案、将第一条数量设为2，但第二条移除与进程恢复未完成，报告docs/evidence/v3/final-real-A07-first-20261009.json。该场景0新模型调用/0Token，失败保留，不能签收F29。

## F30 A07验收滚动分组不等于子按钮可见

首次Runner PID3924在FinalScenarioApiTest.kt:62失败：confirm_user_action节点不存在。只读原生定位PID3676、1/1通过，证据docs/evidence/v3/final-A07-readonly-diagnostic-20261009.json。分组滚动后目标bounds=[0,0,0,0]、disabled=false；对子按钮performScrollTo后bounds=[531,2025,683,2151]、disabled=false。实际根因是大商家分组已经组合但子控件仍被裁剪，不是此前推测的禁用状态。诊断没有点击或写入，不是A07复测。
脚本在点击前精确滚动子控件、核对可见/启用，已保存项也实际滚动；新增四报价同商家fixture覆盖，不增加业务重试或延长10分钟窗口。首次仍失败，无额外授权前不运行A07-R1。

用户随后明确授权唯一A07-R1零模型调用复测，记录于V3-FINAL-04/evidence/A07-EXTRA-AUTHORIZATION.json。实际两阶段Runner PID4117/4221均1/1通过，总23.015秒；阶段间force-stop拥有的applicationId，不清数据。PostgreSQL保留第一条quantity=2、第二条已移除、已保存variant恰一条；其他已有待购物品不删除。无新Turn/模型调用/Token，首次失败不改写。证据docs/evidence/v3/final-real-A07-R1-20261009.json。
F29/F30当前完整视觉fixture31/31通过（PID4296，42.087秒），仍不代替真实业务签收。原30项运行的期望文案失败、随后System UI ANR未完成运行均保留为历史诊断。

## F31 A04验收过早结束已接受的模型运行

首次原生PID4804完成7次目录探索状态变化，转购买后已检索出真实候选；脚本只等recommendation_pager节点存在，随即在尚未稳定的页面上断言rank_0可见而失败。首次报告保存时run仍RUNNING，第一调用1727Token已返回，第二调用未结算，预留46273Token。脚本finally关闭该场景许可后，第二调用返回7488Token，执行器后续阶段被额度守卫拒绝，数据库终态FAILED/ProviderBudgetExceeded。不是原2M预算耗尽，也不是模型超时。首次报告不改写，迟到结算另记docs/evidence/v3/final-real-A04-first-closure-20261009.json。

修正UI判定为实际Agent完成后检查可见；无论原生Runner成败，都仅在原600秒窗口内读取已有Run，等待其离开QUEUED/RUNNING再关闭许可，不新建Turn、不增加重试。三项定向脚本测试覆盖等待、已完成无需等待、窗口不延长；当前Python全188项通过（29.64秒）。A04仍是首测失败，无追加授权前不得重跑。

## F32 已失败的任务恢复不能显示中间推荐为完成

实际ThreadSnapshot a7018ca1-a2c6-55f1-b6e3-2eb68763ef7f返回FAILED，仍包含早期products事件中的候选；原ShoppingViewModel.restoreThreadState没有FAILED分支，默认showConversation=false，存在把中间候选当作正常结果的缺陷。修正FAILED恢复到对话并显示“本次导购未完成，请调整需求或新建任务”，不显示“已完成”。38单测与构建通过；最终只读原生PID6539、1/1通过（6.06秒），核对真实失败快照、明确失败文案、新任务入口及无推荐Pager，不创建Turn或模型调用。截图output/final-failed-restoration-20261009.png，报告docs/evidence/v3/final-A04-readonly-restoration-20261009.json；不是A04业务复测。

## F33 启动诊断不能点击禁用标签

只读原生诊断PID5329/5616/6257等待失败文案超时；Semantics树显示仍在决策页。进一步代码核对发现CHECKING时原生标签disabled，脚本却立即performClick。不能据此声称产品覆盖了用户已生效的选择；此前导航竞态假设撤回，临时navigationChangedByUser改动已移除。
最小修正在诊断点击前记录Disabled，等待标签真正启用再assertIsEnabled/performClick，保留产品已有导航安全锁。最终PID6539实测初始Disabled=true，等待实际启用后点击通过；同一真实FAILED快照只读复验，不创建新Turn或模型调用，不记为A04业务复测。

## F27 对话页不展示内部证据标识

F32原生截图实际显示两块demo:v3:UUID:offer原始引用。MissionConversation将evidenceRefs直接作为正文展示，与用户说明不符；移除该重复调试面板，商品/报价卡原生EvidenceDisclosure仍保留。增加窄范围视觉fixture验证正文不出现原始标识，不修改证据事实、后端事件或纵向候选布局。

## F34 图库验收不能以瞬时节点缺失认定上传失败

首次报告docs/evidence/v3/final-real-A03-first-20261009.json，PID7556、原生1失败，失败发生在selectOwnGalleryImage检查唯一系统图片节点。没有accepted Run、媒体上传或付费调用，0Token；原首测保留。首次没有保存窗口即时树，因此不能断言该瞬间一定是哪一种竞态。

后续非付费定位：MediaStore中自有RagFinalPhone.png恰一项，内容与phone.png一致；系统树中的同一照片日期与bounds已核对。PID7906/8040的系统节点初始匹配均为1，点击后直接等待attachment_image超时；不能据此宣称系统未返回，因为附件是LazyColumn下方尚未组合的item。PID8379另实测窗口root暂空。另一项诊断的新任务入口缺失是当前页面已经空任务，不是产品没有新建功能。修正验收脚本：允许已有空任务、等待真实新任务清空、等待系统窗口中的真实图片节点，依据节点bounds发原生触摸，并对子附件精确滚动；无Intent结果注入、无ShoppingUiState注入、无上传成功伪造。

修正后的带文字输入/图库选择/移除局部诊断PID8528、1/1通过（8.421秒），没有发送、API上传或模型调用；不是完整A03验收。该首次失败需要另行追加A03-R1授权，当前未签收图片原生业务。

## F35 Agent审批写入后刷新待购状态

代码依据：ShoppingViewModel.resolveApproval调用repository.decide后直接consumeRun；applyEvent把tool_completed处理为进度，TurnCompleted只停止加载，没有读取待购API。WaitingCartUpdated此前仅在restoreThreadState或updateWaitingOffer使用，所以Agent审批完成不等于待购界面已更新。属于本轮明确UI与真实API状态一致的验收边界，不增加定时轮询。

最小修复在用户批准cart.update且决策响应成功后读取cartQuantities，按原有Reducer替换数量，保留identityGeneration隔离；不把未确认写入预造为成功。A08必须检查拒绝前/后及批准前真实API未写入，批准后原生决策页显示数量2，PostgreSQL收据一次、终态一次、重复相同已批准决策不重复写入或模型调用。普通确认面板与连接文案不再展示cart.update内部符号；审批所对应的真实API和工具名仍在技术证据中保存。

## F36 A08验收辅助读取使用正确的实际API地址

首次证据docs/evidence/v3/final-real-A08-first-20261009.json：PID9409，MalformedURLException("20881v1")发生在actualOfferQuantity，未创建Run或提案、0Token/0HTTP模型调用。实际生成BuildConfig.API_BASE_URL为http://10.0.2.2:20881，不包含末尾/。辅助GET与应用OkHttp/Retrofit配置不同，直接字符串拼接缺少路径分隔。修正为trimEnd('/')后追加/v1/cart，没有改变生产API地址、运行配置或公共契约。真实审批拒绝/批准尚未执行，不用F35代码/fixture通过替代A08签收；下一次完整场景需要单独追加授权。

原生只读API诊断PID9538、1/1通过（4.789秒），核对实际用户及尚未加入的真实offer数量0；没有Turn、写入或模型调用。证据docs/evidence/v3/final-A08-readonly-diagnostic-20261009.json。

## F37 手动询价与确认外跳

FINAL-02/04明确要求手动重新询价与原生确认外跳。代码原requote按钮派发ReturnToMissionConversation，没有fresh=true请求；onOpenMerchant直接调用ViewModel，缺确认；parseOfferCollection只依据availability标记CURRENT。最小修复复用现有OfferCollection/resolve接口与原确认面板，不改契约。fresh结果只替换对应product；链接操作前再核对实际期限、HTTPS与服务器验证；已知网络错误明确提示，未知契约错误不宽泛catch吞掉。视觉fixture、单测与A09实际API/浏览器验收分层记录；不把演示源视为真实可购买商家。

## F38 同一Mission跨Run候选恢复

定向回归test_snapshot_keeps_mission_candidates_during_followup_approval先实际失败：首次推荐有1个候选，下一次cart.update等待审批时ThreadSnapshot.candidates=[]。这是API/确定性Agent回归复现，不是真实MiMo或Android签收。根因是snapshot只遍历latest_for_thread对应Run事件。修复增加仅用于Mission投影的owner/thread/version限定Run查询，取最近products事件；最新Run的状态、审批、active_run_id和游标不被旧事件替换。新版本和其他用户不得继承旧候选，显式空products不得被旧结果填回。公共0.2.0契约无需变化。

独立数据库ragcommerce_final_regression_20261010迁移后191项全通过、无skip（17.61秒），包括真实PG进程适配器重建后的候选/待审批/游标、跨用户拒绝、新版本清空及显式空结果不回填。此前误用演示Worker数据库的全量运行保留为185通过、2失败、4skip；Worker抢走测试任务，不作为产品回归通过证据。当前演示链已加载修复源码，但完整Android恢复仍待签收。

## F39 A10原生测试标签与生产控件一致

## 2026-10-12 追加验收记录

A03-R1原生1/1通过（95.219秒），实际图库媒体进入MinIO/Worker/MiMo；确认前只识别，确认后版本2推荐、证据覆盖完整、无业务写入，9,963 Token/4请求。A04-R1原生1/1通过（54.77秒），兴趣/排除/换批/结束/转购买/预算/推荐完整核对，9,271 Token/3请求。F31/F34完整业务复测已通过，首测失败仍保留。

A08-R1失败（16.969秒，305 Token/1请求）：真实拒绝Run为COMPLETED、reason=approval_rejected、cart.update未执行、receipt=0，待购数量未变化；PID6330在第二次输入的mission_input查找失败，不是批准成功。只读诊断PID6777也失败：诊断假定底部tab_TASK存在，实际恢复后的推荐页没有该底栏；不能把该诊断当作修复通过。父列表滚动修正已编译，用户随后单独授权A08-R2一次。

A10-R1原生回执超时失败保留，实际第一条推荐Run已COMPLETED，3请求/9,932 Token；待审批、断网、恢复与删除均未签收。原native_phase丢弃stdout，只轮询logcat；查不到完成回执时不能猜测成功，也不能延长600秒或重跑。新增stdout明确结果解析先1项失败、修复后6项通过（包含旧许可关闭边界、成功、失败、缺回执），不改变Agent行为。

Pixel_9缓存回收经用户明确授权，未清空应用、身份、照片或业务数据；回收后仍无法安装。独立RagFinalSafety20261012模拟器采用同一现有API35系统镜像和相同Pixel9画面尺寸，8G空数据分区，仅本轮QA使用。A08-R2复用该隔离安装A10-R1产生的真实MiMo推荐与真实身份，未注入界面或伪造API状态。累计额度继续使用原PostgreSQL会话，不重置预算。

首次报告docs/evidence/v3/final-real-A10-first-20261010.json：PID11063在发送前失败，No node found that matches TestTag=mission_submit；生产按钮实际是send_turn，推荐标记是recommendation_rank_0。新隔离身份没有创建Turn、0模型调用/Token，没有执行断网、审批或删除。测试修正必须先只读核对真实发送控件，不能自动复跑已使用的A10首测槽位。

## F46 审批网络异常后必须提供只读恢复入口

实际A10-R3后端已完成但前台停留错误页。修复对已知IOException显式离线并返回对话，用户重连只读取真实快照，不重新批准。39单测、34视觉fixture通过；只读原生PID9574恢复实际待购数量2通过，未创建Turn/Run，未删除数据。没有保存旧异常类型，因此不猜测其为EOF或超时。

## 2026-10-12 A10-R4零调用收尾

用户单独授权唯一A10-R4，只复用A10-R3已完成的隔离身份，不创建Turn/Run、不重复批准；额度场景active=false。原生PID9929只读恢复1/1、PID10034取消/确认删除1/1通过。真实快照5个候选、两个COMPLETED Run、cart.update收据和终态各一次、待购数量2；跨用户GET=404。取消删除保持数量2，确认后该测试身份七张归属表均0行、本地身份更新，其他身份待购行未变。删除只涉及本轮独立QA身份，不可通过产品界面恢复该身份的业务记录；旧失败报告保留。报告：docs/evidence/v3/final-real-A10-R4-20261012.json。

本次0模型调用、0Token，累计253,785/2,000,000 Token、86HTTP、预留0。A10首次与R1/R2/R3依旧为失败；R3断网检查和后端批准的部分证据与R4剩余步骤分列，不写成原整程通过。完整Android签收仍6/10。A08-R3非法提案失败、有效人声A02/M03、A09浏览器配置/过期分支与最终同版封版门槛未关闭。

R4身份边界测试先KeyError失败、实现后8项定向通过；独立回归DB全196项通过、无skip（11.71秒）。仅测试APK增量构建3秒，54tasks/6executed/48UP-TO-DATE，不声称无缓存全编译。F46只读诊断PID9574、9.641秒另存，不冒充正式复测。

## 2026-10-12 源码分析与修复（F47–F53）

本轮覆盖Provider、Agent执行/检查点/权限、API审批与持久化索引、Android审批状态；未把环境/人声缺口冒充代码缺陷。所有改动沿用FINAL-02范围；未提交、推送或发布。旧真实失败和报告不覆盖。

### F47 / F48 提案边界

model_provider.py原先model_validate允许类型转换和quantity=1默认值，并未核对用户明确指定的报价/数量。四个失败测试复现：省略数量、改数量、改报价、缺字段诊断；修复后Provider28项全通过。输出用严格JSON验证，明确数量不可省略或改变、明确报价不可替换；不把非法输出修成成功。安全诊断仅有已知字段与Pydantic错误类型，额外字段名脱敏，无原始输入值。提示词仅补充字面结构与操作枚举，不生成商品事实。

A08-R3旧响应未保存，因此其具体非法字段仍未知；本轮不能宣称旧真实场景已经修复通过。后续实测需新的直接授权，不能自动重跑到碰巧成功。

### F49 / F50 Android审批状态

ShoppingApprovalStateTest通过Repository系统边界替身驱动真实ViewModel：旧本地审批快照曾把忙碌改回false，HTTP409曾保持ONLINE；两项红测实际失败。修复把审批快照接管挡在状态修改前，HTTP拒绝进入明确核对状态；原生对话已有只读重连入口。测试不注入ShoppingUiState作为业务通过证据。替身最初漏掉终态时清除本地pendingRun的真实语义，造成额外RECOVERED断言失败，已修正替身，不据此增加生产兼容逻辑。单测2/2通过。

### F51 / F52 durable审批与冻结授权

service._decide原先重新调用agent.handle并等待模型；索引仍是旧未批准命令。现在批准命令（包含具体invocation_id）与PENDING状态在PostgreSQL事务中写入现有api_turns，现有Worker领取。拒绝仍只产生已有拒绝终态；相同批准返回既有任务，不创建第二个任务；已接受操作不能再拒绝或编辑Mission。快照在接续期间为RUNNING而非旧WAITING_APPROVAL。Android先消费真实终态，再读取待购，不把202当写入完成。

RunCheckpoint新增私有pending_calls JSON，不新增表或公共契约；每次执行前持久化准确参数，重建后不再向模型重新索要提案。API构造的命令总是使用明确的invocation授权集合；可信嵌入式预授权命令与用户API边界分开。不同参数的同名调用不能继承上次批准，必须失败停止并让用户另起Turn，防止旧相同POST批准另一个提案。旧检查点没有冻结提案时明确失败，不猜测重建或静默兼容。

数量2→99红测实际写入99；修复后写入2。真实PostgreSQL适配器重建测试、待购/清单写入后中断收据测试、同键重复批准、相反决定/编辑并发、不同调用拒绝均通过。独立新Python子进程持有数量99规划器，仍从PG恢复并执行原批准数量2，收据/终态各1；这是实际跨进程、脚本化Provider的工程证据，不是真实MiMo。

不能断言旧A10-R3的IOException一定由同步API导致：旧记录没有保存异常类型。F51依据的是已确认的源码执行链和独立复现，不替旧日志补故事。

### F53 无进展规划

规划器不断返回同一已完成调用时，原实现循环到GraphRecursionError（递归限10007）；缓存命中未增加工具次数，原预算检查不能终止。新增测试先复现异常，修复后产生唯一REPLAN_LIMIT失败，不提高预算、不追加重试、不当作成功。

### 本轮验证与剩余门槛

当前全套Python204通过/0skip（11.72秒，独立ragcommerce_sourcefix_20261012数据库）；Android41单测、lint/debug/test构建通过，18警告/0错误，19秒90tasks/24executed/66UP-TO-DATE。模拟器ShoppingFlowTest34/34通过（45.169秒），为注入视觉fixture，不计真实业务。契约3文件与Agent生成2文件/11工具无漂移，minimality与Ruff通过。

首次切换异步职责时旧同步测试有8失败/193通过；测试改为真实领取/执行已批准任务，保留写入、收据、终态和用户隔离断言。中断集成测试只加速该测试Run的租约，不将其报告为物理进程自然等待；独立子进程复审另列。

真实Token预算仍253,785/2,000,000、86HTTP、预留0。本轮0真实调用。原六条完整Android实测记录保留，但不表示当前审批增量再度完成真实验收；A08、A02/M03、A09及最终同版封版仍待签收，LOCAL_PORTFOLIO_READY=HOLD。

详细证据：docs/evidence/v3/final-source-analysis-repair-20261012.json。


