import { afterEach, expect, test, vi } from "vitest";

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.resetModules(); });

test("production client sends no caller-chosen roles and keeps credentials in memory", async () => {
  vi.stubEnv("VITE_OPS_DEVELOPMENT_IDENTITY", "0");
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
  vi.stubGlobal("fetch", fetch);
  const { opsClient, setOpsCredential } = await import("./generated/ops-client");
  setOpsCredential("test-only-operator");
  await opsClient.connectors();
  const headers = fetch.mock.calls[0][1].headers as Headers;
  expect(headers.get("Authorization")).toBe("Bearer test-only-operator");
  expect(headers.has("X-Ops-Role")).toBe(false);
  expect(headers.has("X-Ops-Actor-ID")).toBe(false);
  setOpsCredential("");
  await opsClient.connectors();
  expect((fetch.mock.calls[1][1].headers as Headers).has("Authorization")).toBe(false);
});

test("only explicit development fixture mode supplies fixture headers", async () => {
  vi.stubEnv("VITE_OPS_DEVELOPMENT_IDENTITY", "1");
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
  vi.stubGlobal("fetch", fetch);
  const { opsClient } = await import("./generated/ops-client");
  await opsClient.connectors();
  expect((fetch.mock.calls[0][1].headers as Headers).get("X-Ops-Role")).toBe("reviewer");
});
