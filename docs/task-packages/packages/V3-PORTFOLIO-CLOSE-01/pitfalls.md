# 易错点

- 不得读取、记录或提交 MiMo 密钥；运行前只做进程级 `MIMO_API_KEY` 到 `OPENAI_COMPATIBLE_API_KEY` 显式映射。
- 每个真实黄金场景只运行一次；429、超时、非法 Schema 和预算耗尽均计失败，不重试、不切换 fixture。
- `complete` 不能仅由本地测试决定；还需要真实 MiMo、远端 CI、main 合入和 Release 匿名复核。
- `output/` 保留为本机临时资产并整体忽略；公开媒体只从显式精选路径进入版本控制。
- 不使用宽泛暂存、reset、clean、自动覆盖用户资产或改写公开历史。
