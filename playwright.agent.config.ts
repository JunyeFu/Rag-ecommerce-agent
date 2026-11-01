import { defineConfig } from "@playwright/test";
import os from "node:os";
import path from "node:path";

const repositoryRoot = process.cwd();
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
  testDir: "./e2e/agent",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  outputDir: path.join(os.tmpdir(), "rag-commerce-agent-playwright-results"),
  webServer: {
    command:
      "uv run --frozen python -m uvicorn ragcommerce_api.demo_fixture_server:app --app-dir apps/api/src --host 127.0.0.1 --port 8080",
    url: "http://127.0.0.1:8080/health",
    timeout: 120_000,
    reuseExistingServer: false,
    env: { PYTHONPATH: pythonPath },
  },
});
