# 新增五类 Agent 面试问题：Q6–Q10 实测审查

2026-11-05；业务源码基线 `06039aba1cf4798704f26549b7a3633c42fceb96`。[前五题及其证据](AGENT-INTERVIEW-AUDIT-20261105.md)保持原样，本轮继续编号到 Q10，未修改业务实现或公开发布审查结果。

**新增 29 项探针：22 通过、7 失败、0 error、0 skip；另有 41 项相关既有回归全部通过。** 七个失败断言归并为四类缺口，组件适配器、调用方条件与当前运行链路分别说明，不能解读为七个线上漏洞。

[测试代码](../../scripts/tests/test_agent_interview_audit_extra.py) · [命令、时间与结构化结果](../task-packages/packages/V3-INTERVIEW-AUDIT-02/evidence/verification.json)

## 联网选题依据

| 公开来源 | 本轮使用的主题 |
|---|---|
| [近期开发 AI 面经](https://www.nowcoder.com/feed/main/detail/e3425d60dec24ee1bcf1dc44420b0101) | SSE 局限性、RAG 动态知识更新、复杂任务执行 |
| [大模型应用开发日常实习面经](https://www.nowcoder.com/feed/main/detail/e380512a58d046798664f694fbc4d49a) | 语音、多模态、图像预处理、长期存储 |
| [安软 AI 应用开发实习面经](https://www.nowcoder.com/feed/main/detail/40920533fad14136bff01c3928c7e953) | 工具权限与作用范围；哪些信息长期保留、摘要或淘汰 |
| [工具调用与 MCP 公开题单](https://www.nowcoder.com/discuss/916877388720373760?sourceSSR=dynamic) | URL 白名单、参数业务校验、异常结果处理；作为题单补充，不作为一次真实面试复盘 |

这些是公开帖子中的常见工程主题，未统计全网频次。Q9 的外链和 Q10 的删除竞态是结合购物产品作的具体延伸追问，不冒充原帖逐字真题。原帖参考答案不作为技术正确性的依据。

## 五题结果总览

| 问题 | 新增用例 | 实测结论 |
|---|---:|---|
| **Q6：为什么选 SSE？断线续传会不会漏事件或重复执行？** | **5/5 通过** | 重放精确后缀；负数/非法游标拒绝，超前游标 409；终态游标不重发，缓存与缓冲关闭 |
| **Q7：知识库更新和重建失败时，怎样保留可用版本？** | **4 通过 / 2 失败** | 重复/乱序/删除事件控制有效；当前别名发布器失败不切换。两个 fixture 投影重建会先清空旧数据 |
| **Q8：图片、音频上传成功，是否意味着内容有效？** | **5 通过 / 3 失败** | 错签名、超大文件、过期媒体和非法 WAV 的模型入口受控；仅文件头的 PNG/JPEG/WAV 仍返回 201 |
| **Q9：工具给出的外链在白名单内，就足够安全吗？** | **4 通过 / 1 失败** | 公网解析、空 DNS、混合私网地址检查有效；省略整个 DNS 参数则跳过解析地址校验 |
| **Q10：用户删除数据后，运行中的 Agent 会不会写回来？** | **4 通过 / 1 失败** | 确认、用户范围、重复删除和失败状态有效；内存 API 删除成功后发生 checkpoint 回写 |

### Q6：SSE 断线续传与游标

**面试可说：** 事件保存在任务运行中，客户端按 run 保存游标，重连使用 `Last-Event-ID`，服务端只发送更大的序号。终态和排队进度有不同语义，不能把无 ID 的 queued 状态当作已持久化事件。协议语义参考 [WHATWG SSE](https://html.spec.whatwg.org/multipage/server-sent-events.html#the-last-event-id-header)。

本轮创建完整的 fake 购物任务，再重新请求实际 SSE 接口：

- 在中间游标后重放，结果与首轮事件序列的后缀精确一致，ID 无重复，completed 只有一次。
- `-1` 和非法字符串返回 400，超前游标返回 409。
- 使用最后一个事件 ID 时不再返回旧事件，响应带 `Cache-Control: no-store`、`X-Accel-Buffering: no`。

[API 实现](../../apps/api/src/ragcommerce_api/app.py)通过这五项检查。本轮是 HTTP TestClient 下的新请求重放，**没有模拟真实 TCP 中断、反向代理、Android 网络切换或长连接耗尽**；也不据此报告真实网络首帧延迟。

### Q7：索引更新失败与版本切换

**面试可说：** 查询质量和更新一致性要分开。默认索引构建器把新数据写到新 collection，成功后才切换读取别名；不能先销毁正在服务的版本。现有事件投影还会检查重复 ID 和序号回退。

本轮已通过：重复事件不重复应用、旧更新不能覆盖新版本、旧事件不能复活已删除商品，以及在当前 `QdrantHybridSemanticIndex.build_index()` 注入 upsert 失败后，读取别名仍指向原 collection，原 collection 仍存在。[当前构建器](../../packages/retrieval/src/ragcommerce_retrieval/semantic.py)

**F07 / P2，fixture 适配器重建缺口：**

1. [`OutboxProjector.rebuild`](../../packages/retrieval/src/ragcommerce_retrieval/outbox.py)先清空旧 projection，再处理新事件。注入缺失 document 的 UPSERT 后抛错，旧商品消失。
2. [`QdrantProjection.rebuild`](../../packages/retrieval/src/ragcommerce_retrieval/qdrant_projection.py)先删除旧 collection，再重放新事件；同样的异常留下空 collection。

第二个适配器源码明确使用非生产 fixture 向量，本轮也只用 `QdrantClient(":memory:")`。**这两个失败不能写成当前本地 BGE 发布器会清空服务索引；后者的失败保留检查通过。** 本轮不验证真实 Qdrant 服务故障、别名切换中的并发读或完整热更新 SLA。

### Q8：多模态输入的格式、容量与有效性

**面试可说：** MIME、文件签名、文件能否解析、内容是否有用是不同层次。当前上传层有类型、签名、大小和 TTL 检查；WAV 在模型入口还有 PCM 格式校验。但上传成功不能解释为图像有效或语音识别成功。[OWASP 文件上传指南](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html#file-signature-validation)也将签名检查和内容检查区分开。

通过项：有效 1×1 PNG 可上传；不匹配签名返回 415；超出 8 MiB 的图片返回 413 且未写入 store；过期媒体不可读并可清理；截断 WAV 在模型入口被拒绝，fake transport 调用数为零。

**F08 / P2，上传接收层缺少完整可解析性保证：** 仅包含 8 字节 PNG 头、3 字节 JPEG 头或 12 字节 RIFF/WAVE 头的内容，上传接口都返回 201 并建立记录。[上传存储实现](../../apps/api/src/ragcommerce_api/media.py)只对这些输入核对前缀，未验证完整文件结构。

这里确认的是无效输入能进入上传存储，不是任意代码执行、解压炸弹或真实模型调用成功。WAV 的后续入口检查在本次用例中有效；图片的实际 Provider 接收行为和真实音频识别准确率均未测。

正向 PNG 的初版常量存在 IDAT CRC 错误，审查中已替换为有效 PNG 并重跑整组新增用例。结果保持 22 通过 / 7 失败，初版记录保留，没有把这处夹具错误算成产品漏洞。

### Q9：外链白名单与 DNS 校验

**面试可说：** HTTPS 和域名白名单只覆盖 URL 表面；重定向中的每一步及实际解析地址也必须符合使用场景。该项目有此类检查，但调用方是否提供 DNS 证据影响最终保证。[OWASP SSRF 防护资料](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)说明了域名与解析地址校验的区别。

新用例验证：允许域名加公网地址通过；传入空映射、空地址列表、同域名同时包含公网和私网地址时，全部拒绝。相关既有回归还通过了 HTTP、用户信息伪装、非默认端口、恶意重定向、私网解析及同形域名等检查。

**F09 / 条件性调用缺口：** [`SafeLinkPolicy.validate_chain`](../../packages/connectors/src/ragcommerce_connectors/security.py)的 `resolved_addresses` 默认是 `None`。调用方省略这个参数时，允许域名链接会通过，实际解析地址检查不执行。

这符合当前方法对离线 fixture 的可选参数行为，**不是本轮证实的 LIVE SSRF 或 DNS 重绑定攻击**。全部测试使用静态地址字符串，没有执行 DNS 查询、HTTP 请求或访问内网。若将来对 LIVE 连接器宣称地址级防护，必须保证调用方提供真实解析/重定向证据，并约束实际连接目标；这部分仍未验收。

### Q10：删除与正在运行的任务竞态

**面试可说：** 删除已完成的数据和禁止在途任务继续写回，是两个不同保证。当前内存组合删除器能按用户删除记录，但 API 的成功响应还缺少与执行中任务协调的证明。

通过四项：未提供明确删除确认返回 400；已完成数据按用户删除且重复调用成功，另一用户的数据保留；未配置删除器返回 503；注入删除器异常返回 500，不返回 `deleted=true`。

**F10 / P1，内存 API 生命周期竞态已复现：**

1. 启动本轮临时用户的 Turn，在 planner 处用事件屏障暂停。
2. 通过实际删除接口提交确认，响应 200；组合删除器删除媒体、TurnIndex 和 checkpoint store 中该用户的记录。
3. 解除屏障，原任务继续执行。
4. 检查同一个 run 的 checkpoint，发现它被重新写回，失败断言保留。

源码原因对应 [API 删除处理](../../apps/api/src/ragcommerce_api/app.py)与 [内存 checkpoint 保存/删除](../../packages/agent-runtime/src/ragcommerce_agent_runtime/store.py)：删除没有阻止在途 Agent 继续 `save`；后者可以重新加入已经移除的 run。这是确定顺序的本地并发复现，不依赖随机 sleep 碰撞。

测试创建了自己的内存存储和用户，未删除真实数据。**PostgreSQL / MinIO 的持久化竞态没有验证，不能由内存结果直接宣称其同样失效或已经安全。** 修复优先应明确删除与任务取消/写入隔离的协调语义，再对真实持久化链复验；本轮没有实施修复。

## 复跑与证据边界

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest -q scripts/tests/test_agent_interview_audit_extra.py --tb=short

.venv/Scripts/python.exe -X utf8 -m pytest -q apps/api/tests/test_turn_api.py apps/api/tests/test_media_flow.py apps/api/tests/test_security_regression.py packages/connectors/tests/test_connector_contract.py packages/retrieval/tests/test_entity_and_outbox.py
```

第一条当前应返回退出码 1，显示七个保留的失败断言。当前批次见 `output/interview-audit-extra-20261105/audit-current.xml`；初版为 `audit.xml`；41 项既有回归见 `regression.xml`。结构化回执记录实际时间、退出码、逐题数量和失败摘要。

所有测试使用内存 HTTP、内存 Qdrant、静态 DNS 字符串和注入 transport；无外部目标、真实模型调用、真实数据库变更或设备窗口。任务完成只表示新增五题审查完成，缺口未修复；当前产品仍为 **HOLD / 商业 NO_GO**。
