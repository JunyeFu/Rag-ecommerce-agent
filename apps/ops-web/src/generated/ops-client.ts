import type {
  AgentTraceSummary,
  ConnectorStatus,
  EntityConflict,
  EvaluationRun,
  ReleaseGate,
} from "./api-contracts";

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
export const fixtureOpsIdentity = import.meta.env.VITE_OPS_DEVELOPMENT_IDENTITY === "1";
let credential = "";
export function setOpsCredential(value: string) { credential = value; }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  if (credential) headers.set("Authorization", `Bearer ${credential}`);
  else if (fixtureOpsIdentity) {
    headers.set("X-Ops-Actor-ID", "local-ops-reviewer");
    headers.set("X-Ops-Role", "reviewer");
  }
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers });
  if (!response.ok) throw new Error(`Ops API ${response.status}`);
  return response.json() as Promise<T>;
}

export const opsClient = {
  policy: () => request<{auth_mode: string}>("/v1/ops/policy"),
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
    body: JSON.stringify({ dataset_version: "competition-v2", runner_version: "automated-challenge-v2" }),
  }),
};
