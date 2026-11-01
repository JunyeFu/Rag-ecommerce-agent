import { defineConfig, devices } from "@playwright/test";
import os from "node:os";
import path from "node:path";

const repositoryRoot = process.cwd();
const externalServers = process.env.PLAYWRIGHT_EXTERNAL_SERVERS === "1";
const apiUrl = process.env.RAG_API_URL ?? "http://127.0.0.1:8080";
const pythonPath = [
  "apps/api/src",
  "packages/domain/src",
  "packages/agent-runtime/src",
  "packages/connectors/src",
  "packages/retrieval/src",
  "packages/evaluation/src",
  "packages/contracts/generated/python",
]
  .map((entry) => path.resolve(repositoryRoot, entry))
  .join(path.delimiter);

export default defineConfig({
  testDir: ".",
  testMatch: ["apps/ops-web/e2e/**/*.spec.ts", "e2e/agent/**/*.spec.ts"],
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  outputDir: path.join(os.tmpdir(), "rag-commerce-playwright-results"),
  use: {
    baseURL: "http://127.0.0.1:24174",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: externalServers ? [] : [
    {
      command:
        `uv run --frozen python -m uvicorn ragcommerce_api.demo_fixture_server:app --app-dir apps/api/src --host 127.0.0.1 --port ${new URL(apiUrl).port}`,
      url: `${apiUrl}/health`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: { PYTHONPATH: pythonPath },
    },
    {
      command:
        "npm run dev --workspace @rag-commerce/ops-web -- --host 127.0.0.1 --port 24174",
      url: "http://127.0.0.1:24174",
      timeout: 120_000,
      reuseExistingServer: false,
      env: { RAG_API_URL: apiUrl },
    },
  ],
});
