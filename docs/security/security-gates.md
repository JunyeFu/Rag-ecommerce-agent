# 安全门禁与证据等级

## 本地自动门禁

- `python scripts/generate_sbom.py --check`：验证 Python、Node、Gradle 和容器锁定清单未漂移。
- `python scripts/security_gate.py --check`：验证疑似 secret、危险代码模式、敏感文件忽略、事务工具排除和必需安全文档。
- `pytest -m "not integration"`：覆盖工具授权、跨用户访问、媒体、SSRF/redirect、运营 RBAC、日志投影和用户删除。
- OpenAPI/生成客户端、Android lint/unit/instrumentation 和 Ops Web 浏览器证据保持各自等级，不互相冒充。

`security-gate.json` 的 `commercial_release_eligible=false` 是有意的 fail-closed 结果：本地模式扫描不能替代带冻结漏洞库的依赖扫描、已构建镜像扫描、凭据轮换、法律审核或独立渗透。

## 外部门禁

进入 live 前至少需要：获批 advisory 数据库的 Python/Node/Gradle 高危依赖报告；每个候选镜像的 digest 和漏洞报告；对象存储恶意文件扫描；生产 SSO/RBAC、共享限流、KMS/凭据轮换；独立渗透；隐私、许可与推广披露审核。

正式发布还需要签名产物身份、SBOM 与产物 digest 绑定、审批人和回滚演练。任何“未运行”或“无法访问”都保持阻断，不写成零发现。
