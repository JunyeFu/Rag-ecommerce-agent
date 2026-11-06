# 第二批：生产 Ops 身份、HTTPS 传输与 Linux 验证

日期：2026-11-05。承接[第一批修复状态](AGENT-INTERVIEW-REPAIR-STATUS-20261105.md)。本批已完成本地实施和验收；未提交、推送、部署或启用真实联盟。产品仍为 **HOLD / NO_GO**。

## 剩余事项的进展

| 事项 | 本批结果 | 仍保留的边界 |
| --- | --- | --- |
| 生产 Ops 管理员认证 | 独立服务端凭据、角色绑定、持久化及撤销已实现；管理命令与运营台登录/退出已验证 | 首个真实运营凭据由部署管理员在受控环境创建，本批未替任何真实运营人员发放凭据 |
| Q9 / F09 HTTPS 传输 | 实现验证 DNS 后直接连接已验证 IP、对端检查、原始主机 SNI/证书校验和逐跳重定向；6 项真实 TLS 受控测试通过 | 实际联盟连接器继续关闭；商家授权、真实重定向链及具体调用者接入仍需各自验收 |
| Q5 Linux 可复现性 | Python 3.12.11/Linux 冷迁移、实际服务回归、生成物与安全检查通过；缺输入的两项嵌入测试已补验 | 这是本地 Linux 容器验证，不能替代 GitHub Actions 的 Ubuntu 工作流 |
| 远端 CI | 只读确认当前 `06039ab` 对应工作流仍失败 | 新代码未提交推送，未重跑旧代码来冒充本次结果；[远端运行记录](https://github.com/JunyeFu/Rag-ecommerce-agent/actions/runs/41984925244) |

## 实施内容

### Ops 凭据与权限

- 新增 `ops_credentials` 表及 `20261105_0018` 迁移，令牌使用 256 bit 随机值，数据库只保存摘要和服务端 actor/role 绑定。
- 运营与安装凭据分离。生产 Ops 忽略客户端自报的 `X-Ops-Role`、`X-Ops-Actor-ID`，改由已验证身份注入；viewer 不能伪装 admin 写入，审计仍记录实际 actor 的既有脱敏引用。
- 凭据撤销后，新请求返回 401。没有公开的运营注册、提权或凭据签发接口。
- 运营台默认要求凭据，凭据只保留在页面内存；退出清空查询缓存，刷新后重新连接。只有明确的开发夹具配置才发送本地演示身份。
- 浏览器测试复现并修复了“取消登录后，迟到的成功响应又恢复登录”的竞态；取消还会清空输入和凭据。

### 管理员操作入口

入口：[manage_ops_identity.py](../../scripts/manage_ops_identity.py)。在已配置 `DATABASE_URL` 的受控部署进程中运行，不读取 `.env` 或打印令牌。

```sh
uv run --frozen python scripts/manage_ops_identity.py provision \
  --actor-id operator-001 --role reviewer \
  --credential-file /run/protected/operator-001.json

uv run --frozen python scripts/manage_ops_identity.py revoke \
  --credential-id <先前签发的凭据ID>
```

签发只写入显式指定的新文件，不覆盖已有文件；POSIX 文件权限为 0600。文件写入失败会撤销新令牌。Windows 部署者需自行选择已有受保护 ACL 的目录，本轮未声称验证 Windows ACL。命令仅在测试中签发临时凭据，不是已完成真实部署。

### Q9 传输实现

实现位于 [https_transport.py](../../packages/connectors/src/ragcommerce_connectors/https_transport.py)。每一跳先校验协议、白名单、端口，再解析并检查全部 IP；socket 直接连接选中的 IP，不重复解析主机名，TLS 仍验证原始主机名。对端 IP 不一致时拒绝。

传输只发送 HEAD，不带 Cookie 或 Authorization，不读取代理环境，不自动跟随跳转；每跳重新验证，最多三次重定向。证书验证不能关闭；错误响应不会降级成 GET、忽略证书或静默重试。现有离线连接器仍走显式 fixture-only 路径，未启用 LIVE。

实现依据 [Python HTTPSConnection](https://docs.python.org/3.12/library/http.client.html#http.client.HTTPSConnection)、[SSL 主机验证](https://docs.python.org/3.12/library/ssl.html#ssl.SSLContext.wrap_socket)和 [OWASP SSRF 建议](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)；受控验收没有访问商家或公共站点。

## 实测结果

| 层级 | 结果 | 证据 |
| --- | --- | --- |
| Windows + PostgreSQL/MinIO/Qdrant | **299 通过、7 跳过、0 失败** | [完整回归 XML](../../output/interview-batch2-20261105/windows-services.xml) |
| Linux + PostgreSQL/MinIO/Qdrant | **298 通过、8 跳过、0 失败** | [完整回归 XML](../../output/interview-batch2-20261105/linux-services.xml) |
| Linux 隔离 TLS 网络 | **6 通过、0 跳过** | [TLS XML](../../output/interview-batch2-20261105/tls-isolated-linux.xml) |
| Linux 固定版本本地 ONNX + 八路读取 | **2 通过、0 跳过** | [补验 XML](../../output/interview-batch2-20261105/linux-bge-composition.xml) |
| Windows 八路共享读取 | **1 通过** | [补验 XML](../../output/interview-batch2-20261105/windows-bge-composition.xml) |
| Web | 类型检查、构建通过；**4 单元、10 E2E 通过** | 本批验证记录 |
| 关闭开发身份的运营台 | **2 E2E 通过**，覆盖无效凭据、登录/退出、刷新、取消竞态 | `OPS_TEST_FIXTURE_IDENTITY=0` |
| Android 生成契约回归 | Kotlin 编译、**55 单元通过** | 本轮未重复第一批的原生设备测试 |
| 生成与治理 | 契约、Agent artifacts、OpenAPI、SBOM、安全门禁、任务包、Ruff、diff 通过 | Linux Ruff 使用临时缓存，源快照只读 |

Linux 完整回归跳过的八项，分别由 **6 项隔离 TLS** 和 **2 项嵌入/共享读取补验**覆盖。它们是同一测试集合在不同网络与输入条件下分组运行，不写成一次 `306 passed`，也不把跨平台的重复回归相加。

TLS 在无外网出口的独立 Linux 网络命名空间运行，只在命名空间内部给 loopback 分配测试 IP。证书由测试临时生成，真实 socket/TLS 同时验证 IP、Host 与 SNI，并验证错误主机名、不可信 CA、私网重绑定、非法跳转和循环跳转。六项测试不是 mock socket。

本地模型复用已缓存的 `Qdrant/bge-small-zh-v1.5@46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59`，模型仓库和其公共 blob 都只读挂载；未复制或重新下载权重。只在任务专用 Qdrant 创建 60 条 QA 索引，未覆盖生产别名，未重跑容量/质量基准。

Linux 基于固定摘要的 Python 3.12.11 Debian 镜像，锁定 uv/依赖；源码快照排除 `.git`、凭据、缓存和构建物。由于快照只读，Hypothesis 使用了本次会话内存数据库；性质测试实际执行，未因此跳过。此环境与 GitHub Ubuntu runner 的系统层不同。

## 运营台 QA

Browser 插件不在本会话技能列表中，使用现有 Playwright。流程：打开工作台 → 错误凭据被拒 → 有效凭据登录 → viewer 提权写入被拒 → 退出 → 缓存/凭据清除 → 刷新仍需登录；另测取消未完成登录。

| 检查 | 结果 |
| --- | --- |
| 页面身份与非空 | `RAG Commerce Ops` 标题及登录/概览真实内容通过 |
| 框架错误覆盖层 | 无 Vite 错误覆盖层 |
| 控制台 | 无页面运行时异常；错误凭据的 401 和 viewer 的 403 为预期负对照 |
| 实际交互 | 登录、退出、刷新及取消竞态通过，非静态截图验收 |
| 桌面与移动 | 默认桌面及 390×844 视口通过；移动截图检查无遮挡，登录按钮已补齐 44px 高度及主题样式 |
| 凭据存储 | localStorage/sessionStorage 不保存运营令牌；截图输入已清空 |

截图保存在本机临时目录：`ragcommerce-batch2-ops-auth-desktop.png`、`ragcommerce-batch2-ops-auth.png`，不作为发布或人工签收证据。

## 收尾与当前门禁

本批修复了取消登录竞态；还修正了 Playwright 将 `output/` 源码快照重复收集为测试的问题。初次 Linux Ruff 因只读缓存路径失败，改用容器临时缓存后通过。首次模型挂载缺少仓库外的公共 blob，只读补挂该 blob 后两项补验通过，没有伪造缓存完整标记。

专用服务验收后停止，测试数据库、QA 源快照和必要失败记录保留；没有删除共享 Docker 网络或缓存。QA 镜像约 814 MB，源码快照约 50 MB。原有用户窗口、其他项目服务与模拟器未操作。

**仍未完成：** 新代码远端 CI、真实联盟授权/调用者接入、正式部署和既有完整产品/物理设备/法律/人审/发布门禁。本地本批完成不代表商业发布。

命令、时间、数量和最终状态见[任务验证记录](../task-packages/packages/V3-INTERVIEW-REPAIR-02/evidence/verification.json)。
