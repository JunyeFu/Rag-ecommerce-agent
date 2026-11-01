# 易错点

- 单请求超时不等于场景总耗时；Token预算必须按run隔离。
- Provider实例复用不能串用量与规划诊断，Trace不能固定fake身份。
- 本地Qdrant内存验收不等于远端投影验收；ASGI压测不等于durable Worker。
- 不读凭据文件；只从进程环境显式映射，不输出密钥。
