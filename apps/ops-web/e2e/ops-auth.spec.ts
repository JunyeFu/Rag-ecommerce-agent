import { expect, test } from "@playwright/test";
import os from "node:os";
import path from "node:path";

test("ops credential login rejects invalid input, clears on logout and on reload", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page).toHaveTitle(/RAG Commerce/);
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  if (await page.getByRole("button", { name: "退出运营身份" }).isVisible()) {
    await page.getByRole("button", { name: "退出运营身份" }).click();
  }
  await expect(page.getByRole("heading", { name: "连接运营工作台" })).toBeVisible();
  await page.getByLabel("运营凭据", { exact: true }).fill("invalid-fixture");
  await page.getByRole("button", { name: "连接", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("凭据无效");
  await page.getByLabel("运营凭据", { exact: true }).fill("test-only-ops-reviewer");
  await page.getByRole("button", { name: "连接", exact: true }).click();
  await expect(page.getByRole("button", { name: "退出运营身份" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "运行概览", exact: true })).toBeVisible();
  const denied = await page.request.post("/v1/ops/evaluation-runs", {headers: {"Authorization":"Bearer test-only-ops-viewer", "X-Ops-Role":"admin", "X-Ops-Actor-ID":"spoofed-admin", "Idempotency-Key":"viewer-denied"}, data:{dataset_version:"fixture-v2",runner_version:"fixture-v2"}});
  expect(denied.status()).toBe(403);
  await page.getByRole("button", { name: "退出运营身份" }).click();
  await expect(page.getByRole("heading", { name: "连接运营工作台" })).toBeVisible();
  expect(await page.evaluate(() => JSON.stringify([localStorage,sessionStorage]))).not.toContain("test-only-ops-reviewer");
  if (process.env.OPS_TEST_FIXTURE_IDENTITY === "0") {
    await page.reload();
    await expect(page.getByRole("heading", { name: "连接运营工作台" })).toBeVisible();
  }
  expect(errors).toEqual([]);
  await page.screenshot({ path: path.join(os.tmpdir(), "ragcommerce-batch2-ops-auth-desktop.png") });
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({ path: path.join(os.tmpdir(), "ragcommerce-batch2-ops-auth.png") });
});

test("cancelling a pending login cannot reconnect after its response arrives", async ({ page }) => {
  let release: (() => void) | undefined;
  await page.route("**/v1/ops/policy", async (route) => {
    const response = await route.fetch();
    await new Promise<void>((resolve) => { release = resolve; });
    await route.fulfill({ response });
  });
  await page.goto("/");
  if (await page.getByRole("button", { name: "退出运营身份" }).isVisible()) {
    await page.getByRole("button", { name: "退出运营身份" }).click();
  }
  await page.getByLabel("运营凭据", { exact: true }).fill("test-only-ops-reviewer");
  await page.getByRole("button", { name: "连接", exact: true }).click();
  await expect.poll(() => Boolean(release)).toBeTruthy();
  await page.getByRole("button", { name: /尚未连接|取消连接/ }).click();
  const response = page.waitForResponse("**/v1/ops/policy");
  release!();
  await response;
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.getByRole("heading", { name: "连接运营工作台" })).toBeVisible();
  await expect(page.getByRole("button", { name: "退出运营身份" })).toHaveCount(0);
});
