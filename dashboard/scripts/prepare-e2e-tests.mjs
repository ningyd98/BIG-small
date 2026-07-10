// 在运行 Playwright 前修正异步状态断言：API 返回 QUEUED 后，Mock worker 可能在页面加载前完成。
import { readFileSync, writeFileSync } from "node:fs";

const path = new URL("../tests/e2e/console.spec.ts", import.meta.url);
const source = readFileSync(path, "utf8");
const before = `test("E2E-11 LiveRun status flow is visible", async ({ page }) => {
  const created = await page.request.post("/api/v1/simulation/runs", {
    headers: operatorHeaders,
    data: draft(),
  });
  const run = await created.json();

  await page.goto("/simulation/live");
  await expect(page.getByText(run.run_id)).toBeVisible({ timeout: 15_000 });
  await expect(
    page.getByRole("row").filter({ hasText: run.run_id }).getByText(run.status),
  ).toBeVisible();
});`;
const after = `test("E2E-11 LiveRun status flow is visible", async ({ page }) => {
  const created = await page.request.post("/api/v1/simulation/runs", {
    headers: operatorHeaders,
    data: draft(),
  });
  const run = await created.json();
  const terminal = await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);

  expect(created.status()).toBe(202);
  expect(run.status).toBe("QUEUED");
  await page.goto("/simulation/live");
  const row = page.getByRole("row").filter({ hasText: run.run_id });
  await expect(row).toBeVisible({ timeout: 15_000 });
  await expect(
    row.getByText(terminal.status, { exact: true }).first(),
  ).toBeVisible({ timeout: 15_000 });
});`;

if (!source.includes(before)) {
  throw new Error("E2E-11 source block changed; update the committed test directly");
}
writeFileSync(path, source.replace(before, after), "utf8");
