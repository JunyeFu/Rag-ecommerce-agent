import { expect, test, type Page } from "@playwright/test";

function collectRuntimeErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

test.describe.configure({ mode: "serial" });

test("renders every governed view without browser runtime errors", async ({ page }) => {
  const errors = collectRuntimeErrors(page);
  await page.goto("/");

  await expect(page).toHaveTitle("RAG Commerce Ops");
  await expect(page.getByRole("heading", { name: "运行概览" })).toBeVisible();
  await expect(page.getByText("按当前 API 返回状态展示", { exact: true })).toBeVisible();
  await expect(page.locator("body")).not.toContainText("证据时点 2026-08-26");
  const connectors = await page.request.get("/v1/ops/connectors", {
    headers: { "X-Ops-Actor-ID": "local-ops-reviewer", "X-Ops-Role": "reviewer" },
  });
  expect(connectors.ok()).toBeTruthy();
  await expect(page.locator("tbody tr").first().locator("td").first()).toHaveText(String((await connectors.json()).length));

  for (const heading of ["Agent Trace", "检索观测", "连接器", "数据冲突", "评测运行", "发布门禁"]) {
    await page.getByRole("button", { name: heading, exact: true }).click();
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
  }

  await expect(page.locator("body")).toContainText("competition-v2 自动挑战集");
  await expect(page.locator("body")).not.toContainText(/held-out|HUMAN|人工盲评/i);
  if (process.env.PLAYWRIGHT_EVIDENCE_PATH) {
    await page.screenshot({ path: process.env.PLAYWRIGHT_EVIDENCE_PATH });
  }
  expect(errors).toEqual([]);
});

test("ops connector regression: inspects health and evidence boundaries", async ({ page }) => {
  const errors = collectRuntimeErrors(page);
  await page.goto("/");
  await page.getByRole("button", { name: "连接器", exact: true }).click();

  const jdSource = page.locator("button.source-button").filter({ hasText: "京东" });
  await jdSource.click();
  const detail = page.getByLabel("京东详情");
  await expect(detail).toBeVisible();
  await expect(detail).toContainText(process.env.PLAYWRIGHT_EXTERNAL_SERVERS === "1" ? "BLOCKED" : "HEALTHY");
  await expect(detail).toContainText("联盟主体授权与 live 凭据未提供");
  await expect(page.locator("tbody tr").filter({ hasText: "拼多多" })).toContainText("BLOCKED");
  expect(errors).toEqual([]);
});

test("ops mutation regression: validates, audits, and persists governed writes", async ({ page }) => {
  const errors = collectRuntimeErrors(page);
  await page.goto("/");
  await page.getByRole("button", { name: "数据冲突", exact: true }).click();

  const conflictId = process.env.OPS_TEST_CONFLICT_ID ?? "conflict-001";
  const conflict = page.locator("tbody tr").filter({ hasText: conflictId });
  await expect(conflict).toContainText("PENDING");
  const reason = page.getByRole("textbox", { name: /本次复核理由/ });
  await reason.fill("理由太短");
  await expect(conflict.getByRole("button", { name: "保持分离" })).toBeDisabled();
  await reason.fill("来源型号字段存在可复核冲突，保持实体分离");
  const resolutionResponse = page.waitForResponse(
    (response) => response.url().includes("/resolution") && response.request().method() === "POST",
  );
  await conflict.getByRole("button", { name: "保持分离" }).click();
  await expect((await resolutionResponse).status()).toBe(200);
  await expect(conflict).toContainText("KEPT_SEPARATE");

  await page.reload();
  await page.getByRole("button", { name: "数据冲突", exact: true }).click();
  await expect(page.locator("tbody tr").filter({ hasText: conflictId })).toContainText(
    "KEPT_SEPARATE",
  );
  await page.getByRole("button", { name: "评测运行", exact: true }).click();
  const evaluationResponse = page.waitForResponse(
    (response) => response.url().endsWith("/v1/ops/evaluation-runs") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "排队本地确定性运行" }).click();
  await expect((await evaluationResponse).status()).toBe(202);

  const queued = page.locator("tbody tr").filter({ hasText: "automated-challenge-v2" });
  await expect(queued.last()).toContainText("QUEUED");
  await expect(queued.last()).toContainText("automated-challenge-v2");

  await page.reload();
  await page.getByRole("button", { name: "评测运行", exact: true }).click();
  await expect(page.locator("tbody tr").filter({ hasText: "automated-challenge-v2" }).last()).toContainText(
    "QUEUED",
  );

  const auditResponse = await page.request.get("/v1/ops/audit", {
    headers: {
      "X-Ops-Actor-ID": "local-ops-reviewer",
      "X-Ops-Role": "reviewer",
    },
  });
  expect(auditResponse.ok()).toBeTruthy();
  const audit = (await auditResponse.json()) as Array<{ action: string }>;
  expect(audit.map((event) => event.action)).toEqual(
    expect.arrayContaining(["entity_conflict.resolve", "evaluation.start"]),
  );
  expect(errors).toEqual([]);
});

test("ops trace review: renders persisted Agent tools after reload", async ({ page }) => {
  const errors = collectRuntimeErrors(page);
  const headers = { "X-Ops-Actor-ID": "local-ops-reviewer", "X-Ops-Role": "reviewer" };
  const response = await page.request.get("/v1/ops/traces", { headers });
  expect(response.ok()).toBeTruthy();
  const traces = await response.json() as Array<{ run_id: string; tools: Array<{ tool: string }> }>;
  const trace = traces.find((item) => item.tools.some((tool) => tool.tool === "catalog.search"));
  expect(trace).toBeDefined();
  await page.goto("/");
  await page.getByRole("button", { name: "Agent Trace", exact: true }).click();
  await page.locator("button.source-button").filter({ hasText: trace!.run_id }).click();
  await expect(page.locator("aside.trace-detail")).toContainText("catalog.search");
  await expect(page.locator("aside.trace-detail .tool-step")).toHaveCount(trace!.tools.length);
  await page.reload();
  await page.getByRole("button", { name: "Agent Trace", exact: true }).click();
  await page.locator("button.source-button").filter({ hasText: trace!.run_id }).click();
  await expect(page.locator("aside.trace-detail")).toContainText(trace!.run_id);
  await expect(page.locator("aside.trace-detail")).toContainText("EvidenceRef");
  await expect(page.locator("aside.trace-detail .tool-step")).toHaveCount(trace!.tools.length);
  expect(errors).toEqual([]);
});

test("ops repeated-write regression: survives a second session, reload, and mobile review", async ({ page }) => {
  const errors = collectRuntimeErrors(page);
  await page.goto("/");
  await page.getByRole("button", { name: "评测运行", exact: true }).click();

  const queuedRows = page.locator("tbody tr").filter({ hasText: "automated-challenge-v2" });
  const initialCount = await queuedRows.count();
  for (let index = 0; index < 12; index += 1) {
    const responsePromise = page.waitForResponse(
      (response) => response.url().endsWith("/v1/ops/evaluation-runs") && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "排队本地确定性运行" }).click();
    await expect((await responsePromise).status()).toBe(202);
  }
  await expect(queuedRows).toHaveCount(initialCount + 12);

  const secondSession = await page.context().newPage();
  const secondSessionErrors = collectRuntimeErrors(secondSession);
  await secondSession.goto("/");
  await secondSession.getByRole("button", { name: "评测运行", exact: true }).click();
  await expect(secondSession.locator("tbody tr").filter({ hasText: "automated-challenge-v2" })).toHaveCount(
    initialCount + 12,
  );
  await secondSession.close();

  await page.reload();
  await page.getByRole("button", { name: "评测运行", exact: true }).click();
  await expect(page.locator("tbody tr").filter({ hasText: "automated-challenge-v2" })).toHaveCount(
    initialCount + 12,
  );

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "发布门禁", exact: true }).click();
  await expect(page.getByRole("heading", { name: "发布门禁", exact: true })).toBeVisible();
  await expect(page.locator("body")).toContainText("competition-v2 自动挑战集");

  if (process.env.PLAYWRIGHT_MOBILE_EVIDENCE_PATH) {
    await page.screenshot({ path: process.env.PLAYWRIGHT_MOBILE_EVIDENCE_PATH });
  }
  expect(errors).toEqual([]);
  expect(secondSessionErrors).toEqual([]);
});
