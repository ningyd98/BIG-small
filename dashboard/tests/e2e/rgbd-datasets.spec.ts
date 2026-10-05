import { expect, test } from "@playwright/test";
import { writeFileSync } from "node:fs";
import path from "node:path";

const operator = { "x-dashboard-role": "EXPERIMENT_OPERATOR" };
const artifactRoot = process.env.BIGSMALL_E2E_ARTIFACT_ROOT!;

test("real dataset capture stays available without a model", async ({ page }) => {
  await page.goto("/simulation/datasets");
  await expect(page.getByRole("heading", { name: "RGB-D 数据工作台" })).toBeVisible();
  await page.getByLabel("独立场景组").fill("1");
  await page.getByRole("button", { name: "启动采集" }).click();
  await expect(page.getByText("SUCCEEDED", { exact: true })).toBeVisible({ timeout: 60000 });
  await expect(page.getByText("1 / 1", { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: "真实 RGB 帧" })).toBeVisible();
  await expect(page.getByRole("img", { name: "深度可视化" })).toBeVisible();
  await expect(page.getByText(/物理任务未执行/)).toBeVisible();
  await page.screenshot({ path: path.join(artifactRoot, "real-dataset.png"), fullPage: true });
});

test("real capture and unavailable visual planning retain distinct evidence", async ({ page }) => {
  const draft = { backend: "MUJOCO", input_mode: "RGBD", user_instruction: "将红色方块放到绿色区域",
    scenarios: ["S01_NORMAL_STATIC"], control_modes: ["PCSC"], seeds: [17001],
    execution_scope: "CAPTURE_ONLY", parameter_overrides: { timeout_ms: 20000 } };
  const createdCapture = await page.request.post("/api/v1/simulation/runs", {
    headers: operator, data: draft,
  });
  expect(createdCapture.status()).toBe(202);
  const capture = await createdCapture.json();
  await expect.poll(async () => (await (await page.request.get(
    `/api/v1/simulation/runs/${capture.run_id}`)).json()).status, { timeout: 60000 }).toBe("SUCCEEDED");
  const createdPlanning = await page.request.post("/api/v1/simulation/runs", {
    headers: operator, data: { ...draft, execution_scope: "VISUAL_PLANNING", seeds: [17002] },
  });
  expect(createdPlanning.status()).toBe(202);
  const planning = await createdPlanning.json();
  let last: Record<string, unknown> = {};
  await expect.poll(async () => {
    last = await (await page.request.get(`/api/v1/simulation/runs/${planning.run_id}`)).json();
    return ["FAILED", "BLOCKED_BY_ENV"].includes(String(last.status));
  }, { timeout: 60000 }).toBe(true);
  writeFileSync(path.join(artifactRoot, "capture-and-missing-model.json"),
    JSON.stringify({ capture, planning: last }, null, 2));
  await page.goto("/simulation/live");
  await expect(page.getByText("独立物理成功：UNKNOWN")).toBeVisible();
  await expect(page.getByText("NOT_EXECUTED", { exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(artifactRoot, "model-unavailable.png"), fullPage: true });
});

test("cancelling real capture preserves already committed frames", async ({ page }) => {
  const response = await page.request.post("/api/v1/rgbd-datasets/jobs", {
    headers: operator, data: { config_id: "SMOKE", groups: 100, seed: 17003,
      width: 320, height: 240 },
  });
  expect(response.status()).toBe(202);
  const created = await response.json();
  let before: Record<string, unknown> = {};
  await expect.poll(async () => {
    before = await (await page.request.get(`/api/v1/rgbd-datasets/jobs/${created.job_id}`)).json();
    return Number(before.published_groups);
  }, { timeout: 60000 }).toBeGreaterThan(0);
  const cancelled = await page.request.post(`/api/v1/rgbd-datasets/jobs/${created.job_id}/cancel`, {
    headers: operator, data: {},
  });
  expect(cancelled.ok()).toBe(true);
  let final: Record<string, unknown> = {};
  await expect.poll(async () => {
    final = await (await page.request.get(`/api/v1/rgbd-datasets/jobs/${created.job_id}`)).json();
    return final.status;
  }, { timeout: 60000 }).toBe("CANCELLED");
  expect(Number(final.published_groups)).toBeGreaterThanOrEqual(Number(before.published_groups));
  expect(Number(final.published_groups)).toBeLessThan(100);
  expect(final.model_calls).toBe(0);
  const sample = (final.sample_ids as string[])[0];
  expect((await page.request.get(
    `/api/v1/rgbd-datasets/${created.dataset_id}/samples/${sample}`)).ok()).toBe(true);
  writeFileSync(path.join(artifactRoot, "cancel-preserved-data.json"),
    JSON.stringify({ before, final }, null, 2));
});
