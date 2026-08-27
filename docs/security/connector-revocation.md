# 连接器撤销与恢复演练

## 撤销

1. 将连接器授权状态设为 `UNAUTHORIZED` 或健康状态设为 `BLOCKED`，并停用 live adapter。
2. 禁止新 requote 和 link resolution；缓存报价降级为 `DISCOVERY_ONLY` 或不可用，绝不延用推广链接。
3. 记录操作者、原因、策略版本、时间和 payload SHA-256，不记录 token。
4. 由凭据所有者在平台侧撤销/轮换，核对平台审计；项目仓不得保存回传值。
5. 检查受影响报价、跳转、佣金披露和用户通知范围。

## 恢复

只有新凭据通过受控注入、allowlist/DNS/redirect 测试、报价新鲜度抽样、最小权限复核和小流量 canary 后才恢复。恢复必须生成新的授权证据，不能复用撤销前的截图或健康数字。

## 本地演练结果边界

本仓可验证 fixture 连接器保持 `live_enabled=false`、恶意链 fail-closed、报价变化阻断深链以及运营状态/审计契约。平台侧撤销与 live 恢复需要真实主体权限，属于 V2-LIVE-01 门禁。
