import { expect, test } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const evidenceRoot = path.resolve(
  process.cwd(),
  "../artifacts/research/process/20261004-ced-development/t17b-ui-module/browser",
);

test("a registered missing source stays NOT_RUN with unavailable denominators", async ({
  page,
}) => {
  await page.goto("/simulation/research?run_id=missing-source");
  await expect(page.getByText("N/A 组配对 / N/A 条全部分配")).toBeVisible();
  await expect(page.getByText(/缺失来源.*protocol/)).toBeVisible();
  await expect(page.getByText(/正式验收.*false/)).toBeVisible();
  await expect(page.getByText("研究验收通过", { exact: true })).toHaveCount(0);
  await page.screenshot({
    path: path.join(evidenceRoot, "missing-source.png"),
  });
});

test("unknown run identity is rejected without a result or experiment submission", async ({
  page,
}) => {
  const writes: string[] = [];
  page.on("request", (request) => {
    if (request.method() !== "GET") writes.push(request.url());
  });
  await page.goto("/simulation/research?run_id=unregistered");
  await expect(page.getByText(/证据未载入.*404/)).toBeVisible();
  await expect(page.getByTestId("research-view-json")).toHaveCount(0);
  expect(writes).toEqual([]);
});

test("software fixture preserves every blocked original in the page and real export", async ({
  page,
}) => {
  await page.goto("/simulation/research?run_id=software-smoke-600");
  await expect(page.getByText("600 组配对 / 4200 条全部分配")).toBeVisible({
    timeout: 30000,
  });
  await expect(page.getByText(/正式验收.*false/)).toBeVisible();
  await expect(page.getByText("候选：N/A", { exact: true })).toBeVisible();
  const view = JSON.parse(
    await page.getByTestId("research-view-json").innerText(),
  );
  expect(view.scope).toBe("SOFTWARE_ONLY");
  expect(view.actual_research_status).toBe("NOT_RUN");
  expect(view.formal_accepted).toBe(false);
  expect(view.failures).toHaveLength(4200);
  expect(view.terminal_status_counts.BLOCKED).toBe(4200);
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "导出同分母 JSON" }).click(),
  ]);
  const destination = path.join(evidenceRoot, "software-smoke-600.export.json");
  await download.saveAs(destination);
  expect(JSON.parse(readFileSync(destination, "utf-8"))).toEqual(view);
  writeFileSync(
    path.join(evidenceRoot, "observed-summary.json"),
    JSON.stringify(
      {
        scope: view.scope,
        groups: view.paired_group_denominator,
        assigned: view.assigned_denominator,
        blocked: view.failures.length,
        formal_accepted: view.formal_accepted,
        actual_research_status: view.actual_research_status,
        export_matches_page: true,
        model_requests: 0,
        physical_actions: 0,
      },
      null,
      2,
    ) + "\n",
  );
  await page.screenshot({ path: path.join(evidenceRoot, "software-only.png") });
});
