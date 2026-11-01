# V3 Agent 时序：媒体确认、冻结审批与恢复

2026-10-13当前源码；此图说明已实现流程，A02/M03真实人声仍待验收。

```mermaid
sequenceDiagram
  participant A as Android
  participant API as API
  participant DB as PostgreSQL
  participant W as Worker
  participant M as ModelProvider
  participant T as Tools/RAG
  participant S as MinIO
  opt 图片或原生录音
    A->>API: 上传实际附件
    API->>S: 写入私有对象
    API->>DB: 保存归属／有效期；失败补偿对象
    API-->>A: media_id
  end
  A->>API: POST Turn + Idempotency-Key
  API->>DB: 写 Turn/PENDING Job
  API-->>A: 202 run_id
  W->>DB: FOR UPDATE SKIP LOCKED
  opt 媒体待确认
    W->>S: 读取当前用户、未过期媒体
    W->>M: Base64实际媒体字节
    M-->>W: 转写或线索／不确定项
    W->>DB: media_interpreted／WAITING_CLARIFICATION
    API-->>A: SSE识别结果／ThreadSnapshot
    A->>API: 修改确认文本与media_confirmation
    API->>DB: 更新Mission版本；幂等创建确认Turn
  end
  W->>M: 结构化规划与工具参数
  M-->>W: 已知工具Schema内的计划
  W->>T: 检索／事实／报价／比较
  T-->>W: 类型化结果 + EvidenceRef
  W->>DB: 追加事件与 checkpoint
  A->>API: SSE + Last-Event-ID
  API-->>A: progress/products/offers/comparison/completed
  opt Agent提出受控写入
    W->>DB: checkpoint冻结具体ToolCall与invocation_id
    API-->>A: approval_required
    alt 用户拒绝
      A->>API: 拒绝当前提案
      API->>DB: 记录拒绝并完成；零业务写入
    else 用户批准
      A->>API: 批准当前提案
      API->>DB: 同一Run持久化批准并重新排队
      API-->>A: 202
      W->>DB: 领取批准后的任务
      W->>T: 执行冻结参数与具体invocation
      T->>DB: 同事务写业务状态与唯一收据
      W->>DB: 完成终态
      API-->>A: SSE完成；客户端读取真实待购
    end
  end
  opt 断线或进程恢复
    A->>API: ThreadSnapshot与Last-Event-ID
    API-->>A: Mission／候选／待审批动作／后续事件
    Note over W,DB: Worker中断后自然300秒租约回收；收据避免重复写入
  end
  A->>API: 普通读取报价／fresh重新询价
  API->>DB: 读取原有效期／显式刷新报价快照
  A->>API: 用户确认后解析演示链接
  API-->>A: 过期无链接；有效HTTPS链接
```

仅公开阶段与结构化结果。模型失败进入明确错误，不回退fake；普通报价读取不续期。原生保存/待购确认与Agent写入审批使用真实API状态，外跳仅演示安全边界。

当前真实批准和恢复分别见`final-real-A08-R5-20261013.json`、`final-real-A10-R5-20261013.json`；租约故障注入见`final-N07-worker-process-recovery-02-20261013.json`。媒体转写的人声效果不能由这张图代签。
