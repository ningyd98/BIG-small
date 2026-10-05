# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: research-evidence.spec.ts >> unknown run identity is rejected without a result or experiment submission
- Location: tests/e2e/research-evidence.spec.ts:19:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText(/证据不可用.*404/)
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for getByText(/证据不可用.*404/)

```

```yaml
- complementary:
  - heading "BIG-small 控制台" [level=4]
  - text: 实验与安全验收控制台
  - menu:
    - menuitem "dashboard 概览":
      - img "dashboard"
      - link "概览":
        - /url: /
    - menuitem "experiment 仿真工作台":
      - img "experiment"
      - link "仿真工作台":
        - /url: /simulation
    - menuitem "场景库":
      - link "场景库":
        - /url: /simulation/scenarios
    - menuitem "RGB-D 数据":
      - link "RGB-D 数据":
        - /url: /simulation/datasets
    - menuitem "Batch/Sweep":
      - link "Batch/Sweep":
        - /url: /simulation/batch
    - menuitem "Live Run":
      - link "Live Run":
        - /url: /simulation/live
    - menuitem "结果分析":
      - link "结果分析":
        - /url: /simulation/analysis
    - menuitem "研究证据":
      - link "研究证据":
        - /url: /simulation/research
    - menuitem "robot Sim2Real":
      - img "robot"
      - link "Sim2Real":
        - /url: /simulation/sim2real
    - menuitem "robot AI 模型":
      - img "robot"
      - link "AI 模型":
        - /url: /models
    - menuitem "本地模型":
      - link "本地模型":
        - /url: /models/local
    - menuitem "Planner 测试":
      - link "Planner 测试":
        - /url: /models/test
    - menuitem "任务执行":
      - link "任务执行":
        - /url: /task-execution
    - menuitem "safety 安全验收":
      - img "safety"
      - link "安全验收":
        - /url: /safety-acceptance
    - menuitem "file-search 证据浏览":
      - img "file-search"
      - link "证据浏览":
        - /url: /evidence
    - menuitem "指标对比":
      - link "指标对比":
        - /url: /comparison
    - menuitem "审计事件":
      - link "审计事件":
        - /url: /audit
- alert:
  - strong: MoveIt dry-run，仅规划，不执行硬件动作
  - img "stop"
  - text: UNKNOWN 真实机械臂验证：UNKNOWN 最高硬件级别：NONE
- banner:
  - strong: 连接状态
  - text: stale 轮询可用，WebSocket 可兜底
- main:
  - text: 研究结果与证据 实际研究：NOT_RUN。读取已登记的产物，不启动实验。 unregistered
  - combobox "已登记研究记录"
  - img "down"
  - searchbox "研究运行 ID"
  - button "读取证据"
  - alert: "证据未载入：研究证据请求失败 (404)：{\"detail\":\"research_run_not_found\"}"
```

# Test source

```ts
  1  | import { expect, test } from "@playwright/test";
  2  | import { readFileSync, writeFileSync } from "node:fs";
  3  | import path from "node:path";
  4  | 
  5  | const evidenceRoot = path.resolve(
  6  |   process.cwd(),
  7  |   "../artifacts/research/process/20261004-ced-development/t17b-ui-module/browser",
  8  | );
  9  | 
  10 | test("a registered missing source stays NOT_RUN with unavailable denominators", async ({ page }) => {
  11 |   await page.goto("/simulation/research?run_id=missing-source");
  12 |   await expect(page.getByText("N/A 组配对 / N/A 条全部分配")).toBeVisible();
  13 |   await expect(page.getByText(/缺失来源.*protocol/)).toBeVisible();
  14 |   await expect(page.getByText(/正式验收.*false/)).toBeVisible();
  15 |   await expect(page.getByText("研究验收通过", { exact: true })).toHaveCount(0);
  16 |   await page.screenshot({ path: path.join(evidenceRoot, "missing-source.png") });
  17 | });
  18 | 
  19 | test("unknown run identity is rejected without a result or experiment submission", async ({ page }) => {
  20 |   const writes: string[] = [];
  21 |   page.on("request", (request) => {
  22 |     if (request.method() !== "GET") writes.push(request.url());
  23 |   });
  24 |   await page.goto("/simulation/research?run_id=unregistered");
> 25 |   await expect(page.getByText(/证据不可用.*404/)).toBeVisible();
     |                                              ^ Error: expect(locator).toBeVisible() failed
  26 |   await expect(page.getByTestId("research-view-json")).toHaveCount(0);
  27 |   expect(writes).toEqual([]);
  28 | });
  29 | 
  30 | test("software fixture preserves every blocked original in the page and real export", async ({ page }) => {
  31 |   await page.goto("/simulation/research?run_id=software-smoke-600");
  32 |   await expect(page.getByText("600 组配对 / 4200 条全部分配")).toBeVisible();
  33 |   await expect(page.getByText(/正式验收.*false/)).toBeVisible();
  34 |   await expect(page.getByText("候选：N/A", { exact: true })).toBeVisible();
  35 |   const view = JSON.parse(await page.getByTestId("research-view-json").innerText());
  36 |   expect(view.scope).toBe("SOFTWARE_ONLY");
  37 |   expect(view.actual_research_status).toBe("NOT_RUN");
  38 |   expect(view.formal_accepted).toBe(false);
  39 |   expect(view.failures).toHaveLength(4200);
  40 |   expect(view.terminal_status_counts.BLOCKED).toBe(4200);
  41 |   const [download] = await Promise.all([
  42 |     page.waitForEvent("download"),
  43 |     page.getByRole("link", { name: "导出同分母 JSON" }).click(),
  44 |   ]);
  45 |   const destination = path.join(evidenceRoot, "software-smoke-600.export.json");
  46 |   await download.saveAs(destination);
  47 |   expect(JSON.parse(readFileSync(destination, "utf-8"))).toEqual(view);
  48 |   writeFileSync(path.join(evidenceRoot, "observed-summary.json"), JSON.stringify({
  49 |     scope: view.scope,
  50 |     groups: view.paired_group_denominator,
  51 |     assigned: view.assigned_denominator,
  52 |     blocked: view.failures.length,
  53 |     formal_accepted: view.formal_accepted,
  54 |     actual_research_status: view.actual_research_status,
  55 |     export_matches_page: true,
  56 |     model_requests: 0,
  57 |     physical_actions: 0,
  58 |   }, null, 2) + "\n");
  59 |   await page.screenshot({ path: path.join(evidenceRoot, "software-only.png") });
  60 | });
  61 | 
```