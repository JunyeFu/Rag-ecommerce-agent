import type {
  AgentTraceSummary,
  AuditEvent,
  ConnectorStatus,
  EntityConflict,
  EvaluationRun,
  ReleaseGate,
} from "./generated/api-contracts";

const observedAt = "2026-08-26T09:00:00Z";

export const connectors: ConnectorStatus[] = [
  {
    source_id: "src_taobao_tmall",
    display_name: "淘宝/天猫",
    authorization: "FIXTURE_ONLY",
    health: "DEGRADED",
    error_rate_5m: 0.0312,
    requests_used: 620,
    requests_limit: 1000,
    freshness_p50_seconds: 500,
    last_observed_at: observedAt,
    evidence: {
      local_evidence: "fixture:connector-taobao-v1",
      external_gate: "联盟主体授权与 live 凭据未提供",
    },
  },
  {
    source_id: "src_jd",
    display_name: "京东",
    authorization: "FIXTURE_ONLY",
    health: "HEALTHY",
    error_rate_5m: 0.0041,
    requests_used: 1420,
    requests_limit: 2000,
    freshness_p50_seconds: 135,
    last_observed_at: observedAt,
    evidence: {
      local_evidence: "fixture:connector-jd-v1",
      external_gate: "联盟主体授权与 live 凭据未提供",
    },
  },
  {
    source_id: "src_pdd",
    display_name: "拼多多",
    authorization: "UNAUTHORIZED",
    health: "BLOCKED",
    error_rate_5m: null,
    requests_used: 0,
    requests_limit: 500,
    freshness_p50_seconds: null,
    last_observed_at: observedAt,
    evidence: {
      local_evidence: "fixture:connector-pdd-v1",
      external_gate: "联盟主体授权与 live 凭据未提供",
    },
  },
];

export const entityConflicts: EntityConflict[] = [
  {
    conflict_id: "conflict-001",
    left_entity_ref: "entity:seed-0021",
    right_entity_ref: "entity:seed-0198",
    conflict_fields: ["brand", "model_number"],
    confidence: 0.82,
    status: "PENDING",
    source_refs: ["seed:product-0021", "seed:product-0198"],
    observed_at: observedAt,
  },
  {
    conflict_id: "conflict-002",
    left_entity_ref: "entity:seed-0104",
    right_entity_ref: "entity:seed-0147",
    conflict_fields: ["capacity"],
    confidence: 0.74,
    status: "PENDING",
    source_refs: ["seed:product-0104", "seed:product-0147"],
    observed_at: observedAt,
  },
];

export const traces: AgentTraceSummary[] = [
  {
    run_id: "run-fixture-001",
    status: "COMPLETED",
    prompt_version: "shopping-agent-v1",
    model_version: "deterministic-planner-v1",
    duration_ms: 284,
    estimated_cost_microunits: 0,
    tools: [
      {
        tool: "search_catalog",
        status: "COMPLETED",
        arguments_sha256: "5286c7bda40f…",
        evidence_refs: ["fixture:catalog-product-1"],
        duration_ms: 31,
      },
    ],
    redaction_policy: "public_trace_v1:no_input_no_cot_no_raw_tool_arguments",
    created_at: observedAt,
  },
  {
    run_id: "run-fixture-002",
    status: "WAITING_APPROVAL",
    prompt_version: "shopping-agent-v1",
    model_version: "deterministic-planner-v1",
    duration_ms: 192,
    estimated_cost_microunits: 0,
    tools: [
      {
        tool: "cart.update",
        status: "APPROVAL_REQUIRED",
        arguments_sha256: "bf909a06b6e8…",
        evidence_refs: ["fixture:quote-4"],
        duration_ms: 14,
      },
    ],
    redaction_policy: "public_trace_v1:no_input_no_cot_no_raw_tool_arguments",
    created_at: observedAt,
  },
];

export const evaluationRuns: EvaluationRun[] = [
  {
    run_id: "eval-local-smoke-001",
    dataset_version: "v2-smoke-1",
    runner_version: "deterministic-1",
    status: "PASSED",
    case_count: 12,
    metrics: { schema_valid: 1, unsafe_tool_execution_rate: 0 },
    evidence: {
      local_evidence: "docs:evaluation/local-smoke",
      external_gate: "600-case frozen evaluation and held-out human review not complete",
    },
    created_at: observedAt,
  },
];

export const releaseGates: ReleaseGate[] = [
  {
    gate_id: "local-contract",
    title: "本地契约与回归",
    evidence_level: "LOCAL",
    status: "PASSED",
    evidence_ref: "docs/task-packages/manifest.json",
  },
  {
    gate_id: "integration",
    title: "受控集成环境",
    evidence_level: "INTEGRATION",
    status: "PASSED",
    evidence_ref: "docs/task-packages/packages/V2-API-01/evidence/verification.json",
  },
  {
    gate_id: "live-commerce",
    title: "真实联盟报价",
    evidence_level: "LIVE",
    status: "BLOCKED",
    blocker: "缺少 live 联盟授权与凭据",
  },
  {
    gate_id: "human-acceptance",
    title: "运营与无障碍人工验收",
    evidence_level: "HUMAN",
    status: "NOT_RUN",
    blocker: "需指定人员在物理设备与生产预演环境执行",
  },
  {
    gate_id: "formal-release",
    title: "正式发布批准",
    evidence_level: "RELEASE",
    status: "BLOCKED",
    blocker: "签名、隐私、法律与发布批准未完成",
  },
];

export const initialAudit: AuditEvent[] = [];
