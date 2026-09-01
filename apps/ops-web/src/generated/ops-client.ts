import type {
  AgentTraceSummary,
  ConnectorStatus,
  EntityConflict,
  EvaluationRun,
  ReleaseGate,
} from "./api-contracts";

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const headers = {
  "Content-Type": "application/json",
  "X-Ops-Actor-ID": "local-ops-reviewer",
  "X-Ops-Role": "reviewer",
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers: { ...headers, ...init?.headers } });
  if (!response.ok) throw new Error(`Ops API ${response.status}`);
  return response.json() as Promise<T>;
}

export const opsClient = {
  connectors: () => request<ConnectorStatus[]>("/v1/ops/connectors"),
  conflicts: () => request<EntityConflict[]>("/v1/ops/entity-conflicts"),
  traces: () => request<AgentTraceSummary[]>("/v1/ops/traces"),
  evaluations: () => request<EvaluationRun[]>("/v1/ops/evaluation-runs"),
  releaseGates: () => request<ReleaseGate[]>("/v1/ops/release-gates"),
  resolveConflict: (conflictId: string, decision: "MERGE" | "KEEP_SEPARATE", reason: string) =>
    request<EntityConflict>(`/v1/ops/entity-conflicts/${conflictId}/resolution`, {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ decision, reason }),
    }),
  startEvaluation: () => request<EvaluationRun>("/v1/ops/evaluation-runs", {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ dataset_version: "v3-golden-1", runner_version: "deterministic-2" }),
  }),
};
