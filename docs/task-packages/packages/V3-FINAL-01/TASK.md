# V3-FINAL-01 基线与可复现环境

## 目标
执行用户批准的一次长执行实习投递收口方案，AI应用实习为主，全栈证据为辅。

## 状态
complete；仅签收本包环境与配置层，不签收真实多模态或作品集总体验收。

## 范围
基线与可复现环境。仅声明路径内实施必要修改。

## 非目标
本轮不提交、推送、合并或发布；不做支付、订单、多Agent、生产身份或自动价格监控。

## 前置依赖
V3-PLATFORM-01及本轮用户授权。

## 路径所有权
scripts/demo_processes.ps1：修复实测停止启动器后遗留Python子进程的问题，仅操作已核对PID及启动时间的本轮进程树。
scripts/ensure_demo_database.py与start_v3_demo.ps1的DatabaseName：按显式名称创建候选/测试隔离库，保留所有原有数据库，不清空或迁移用户数据。
scripts/capture_portfolio_baseline.py、scripts/start_v3_demo.ps1、scripts/stop_v3_demo.ps1、scripts/build_retrieval_index.py；infra/compose.yaml；apps/api/src/ragcommerce_api/{provider_config,retrieval_config,persistent_demo}.py；apps/worker/src/ragcommerce_worker/persistent_demo.py；packages/retrieval/src/ragcommerce_retrieval/semantic.py及相关测试；Ops代理与Android API默认地址；本轮缺陷、证据、任务包。

## 现状证据
Ops代理读取进程环境需要Node类型，apps/ops-web/package.json与根package-lock.json纳入最小依赖修复范围。
Docker认证EOF的本机实测要求增加scripts/pull_official_images.py：仅从官方Docker Hub按固定tag获取并验证OCI内容，不改全局代理。外部导航同步本轮五包进度。
MinIO固定tag的官方DockerHub/Quay均返回401，官方二进制归档410；允许infra/minio-source.Dockerfile从相同官方Git tag构建，不改服务版本，单独记录来源与许可证。官方Go构建镜像按固定版本下载。
FINAL-01/evidence/current-state.json及docs/defects/V3-FINAL-CLOSEOUT.md；历史报告保留原分母。

## 执行步骤
1. 保存文件级写前基线。
2. 修复统一端口、显式Provider及Worker共享存储。
3. 显式构建Qdrant索引，验证多进程启动。
4. 验证启动、健康、迁移及资源归属。

## 数据引用
自有60SKU、DEMO_FIXTURE、固定BGE revision、当前PRD、24+6场景槽位。

## 验收
- 固定版本基础设施、迁移与完整运行链通过
- 查询不重建索引，重建失败保留旧索引
- 模型与检索身份对应真实配置

## 回滚
仅撤销本轮具体行级变更，保留用户已有改动与数据；不使用reset或clean。

## 停止条件
真实凭据/额度、必要设备或基础设施阻塞时停止相关路径；其余独立工作继续。不自动增加付费调用。

## 交接格式
命令、时间、退出码、数量、失败摘要、证据等级、当前候选状态及剩余门禁。
