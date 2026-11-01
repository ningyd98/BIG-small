# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: console.spec.ts >> E2E-05 creates Mock single experiment
- Location: tests/e2e/console.spec.ts:78:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByRole('row').filter({ hasText: 'sim-e3b8a7ddb6b6' }).getByText('SUCCEEDED', { exact: true }).first()
Expected: visible
Timeout: 15000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 15000ms
  - waiting for getByRole('row').filter({ hasText: 'sim-e3b8a7ddb6b6' }).getByText('SUCCEEDED', { exact: true }).first()

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
  - img "check-circle"
  - text: PHASE10_MOVEIT_DRY_RUN_ACCEPTED 真实机械臂验证：NOT_STARTED 最高硬件级别：NONE
- banner:
  - strong: 连接状态
  - text: "connected 轮询可用，WebSocket 可兜底 last: heartbeat"
- main:
  - heading "BIG-small Simulation Workbench" [level=3]
  - alert:
    - img "info-circle"
    - text: 默认使用 RGB-D 视觉规划。可选择仅采集、视觉规划或 MuJoCo 物理闭环；规划结果与物理任务结果分别记录。
  - text: 实验设计 * 输入方式 视觉 + 深度（默认）
  - combobox "* 输入方式"
  - img "down"
  - text: "* 任务指令"
  - textbox "* 任务指令": 将红色方块放到绿色区域
  - text: "* 视觉能力 视觉规划（默认）"
  - combobox "* 视觉能力"
  - img "down"
  - text: "* Backend MUJOCO (READY)"
  - combobox "* Backend"
  - img "down"
  - text: "* Scenario S01_NORMAL_STATIC NORMAL"
  - combobox "* Scenario"
  - img "down"
  - text: "* Mode PCSC"
  - combobox "* Mode"
  - img "down"
  - text: "* Seed"
  - spinbutton "* Seed": "0"
  - button "Increase Value":
    - img "up"
  - button "Decrease Value" [disabled]:
    - img "down"
  - text: Description
  - textbox "Description"
  - text: 参数与网络 Latency ms
  - spinbutton "Latency ms": "40"
  - button "Increase Value":
    - img "up"
  - button "Decrease Value":
    - img "down"
  - text: Jitter ms
  - spinbutton "Jitter ms": "5"
  - button "Increase Value":
    - img "up"
  - button "Decrease Value":
    - img "down"
  - text: Packet loss
  - spinbutton "Packet loss": "0.00"
  - button "Increase Value":
    - img "up"
  - button "Decrease Value" [disabled]:
    - img "down"
  - text: Repetitions
  - spinbutton "Repetitions": "1"
  - button "Increase Value":
    - img "up"
  - button "Decrease Value" [disabled]:
    - img "down"
  - text: 提交与阻塞
  - table:
    - rowgroup:
      - 'row "Readiness : status READY"':
        - 'cell "Readiness : status READY"':
          - text: "Readiness :"
          - img "check-circle"
          - text: READY
      - 'row "Queued : 0"':
        - 'cell "Queued : 0"'
      - 'row "Hardware writes : none"':
        - 'cell "Hardware writes : none"'
  - img "No data"
  - text: 无 backend blocker
  - button "Submit simulation run"
  - text: Runtime Health
  - table:
    - rowgroup:
      - 'row "Status : status READY"':
        - 'cell "Status : status READY"':
          - text: "Status :"
          - img "check-circle"
          - text: READY
      - 'row "Database : sqlite"':
        - 'cell "Database : sqlite"'
      - 'row "Controller contacted : false"':
        - 'cell "Controller contacted : false"'
      - 'row "Hardware motion : false"':
        - 'cell "Hardware motion : false"'
  - text: Queue
  - table:
    - rowgroup:
      - 'row "Queued : 0"':
        - 'cell "Queued : 0"'
      - 'row "Running : 0"':
        - 'cell "Running : 0"'
      - 'row "Blocked : 1"':
        - 'cell "Blocked : 1"'
      - 'row "Batch limit : 120"':
        - 'cell "Batch limit : 120"'
  - progressbar: 0%
  - text: Planner Configuration
  - table:
    - rowgroup:
      - 'row "Provider : MOCK"':
        - 'cell "Provider : MOCK"'
      - 'row "Model : mock"':
        - 'cell "Model : mock"'
      - 'row "Health : status READY"':
        - 'cell "Health : status READY"':
          - text: "Health :"
          - img "check-circle"
          - text: READY
      - 'row "Profile version : 0"':
        - 'cell "Profile version : 0"'
  - text: Active and recent runs
  - table:
    - rowgroup:
      - row "Run Backend Scenario Mode Seed Worker Attempt Status":
        - columnheader "Run"
        - columnheader "Backend"
        - columnheader "Scenario"
        - columnheader "Mode"
        - columnheader "Seed"
        - columnheader "Worker"
        - columnheader "Attempt"
        - columnheader "Status"
    - rowgroup:
      - row "sim-e3b8a7ddb6b6 MOCK S01_NORMAL_STATIC PCSC 0 0 status BLOCKED_BY_ENV":
        - cell "sim-e3b8a7ddb6b6"
        - cell "MOCK"
        - cell "S01_NORMAL_STATIC"
        - cell "PCSC"
        - cell "0"
        - cell
        - cell "0"
        - cell "status BLOCKED_BY_ENV":
          - img "warning"
          - text: BLOCKED_BY_ENV
  - list:
    - listitem "Previous Page":
      - button "left" [disabled]:
        - img "left"
    - listitem "1"
    - listitem "Next Page":
      - button "right" [disabled]:
        - img "right"
```

# Test source

```ts
  2   | import { expect, test, type Page } from "@playwright/test";
  3   | import { readFileSync } from "node:fs";
  4   | import path from "node:path";
  5   | const operatorHeaders = { "x-dashboard-role": "EXPERIMENT_OPERATOR" };
  6   | 
  7   | type BatchPayload = Record<string, unknown> & {
  8   |   progress: {
  9   |     total: number;
  10  |     succeeded: number;
  11  |     failed: number;
  12  |     blocked: number;
  13  |     cancelled: number;
  14  |     timed_out: number;
  15  |   };
  16  | };
  17  | 
  18  | type TimelinePayload = {
  19  |   sequence: number;
  20  |   event_type: string;
  21  | };
  22  | 
  23  | type MetricPayload = {
  24  |   name: string;
  25  | };
  26  | 
  27  | test("E2E-01 overview keeps dry-run acceptance without hardware validation", async ({
  28  |   page,
  29  | }) => {
  30  |   await page.goto("/");
  31  | 
  32  |   await expect(
  33  |     page.getByRole("heading", { name: "PHASE10_MOVEIT_DRY_RUN_ACCEPTED" }),
  34  |   ).toBeVisible();
  35  |   await expect(
  36  |     page.getByRole("main").getByText("真实机械臂验证：NOT_STARTED"),
  37  |   ).toBeVisible();
  38  |   await expect(
  39  |     page.getByText(/直连 ROS|MoveIt execute|控制器地址/i),
  40  |   ).toHaveCount(0);
  41  | });
  42  | 
  43  | test("E2E-02 loads S01-S15 from real FastAPI simulation API", async ({
  44  |   page,
  45  | }) => {
  46  |   const response = await page.request.get("/api/v1/simulation/scenarios");
  47  |   const payload = await response.json();
  48  | 
  49  |   expect(response.ok()).toBeTruthy();
  50  |   expect(payload.scenarios).toHaveLength(15);
  51  |   expect(
  52  |     payload.scenarios.map((item: { scenario_id: string }) => item.scenario_id),
  53  |   ).toContain("S15_SQLITE_RESTART_DURING_RUN");
  54  | });
  55  | 
  56  | test("E2E-03 searches network scenario in scenario library", async ({
  57  |   page,
  58  | }) => {
  59  |   await page.goto("/simulation/scenarios");
  60  | 
  61  |   await expect(page.getByText("S07_NETWORK_DEGRADED")).toBeVisible();
  62  |   await expect(
  63  |     page.getByText("NETWORK_DEGRADED", { exact: true }),
  64  |   ).toBeVisible();
  65  | });
  66  | 
  67  | test("E2E-04 shows S14 emergency-stop timeline details", async ({ page }) => {
  68  |   const response = await page.request.get(
  69  |     "/api/v1/simulation/scenarios/S14_EMERGENCY_STOP",
  70  |   );
  71  |   const payload = await response.json();
  72  | 
  73  |   expect(response.ok()).toBeTruthy();
  74  |   expect(payload.category).toBe("SAFETY");
  75  |   expect(payload.scheduled_faults[0].trigger_time_ms).toBe(600);
  76  | });
  77  | 
  78  | test("E2E-05 creates Mock single experiment", async ({ page }) => {
  79  |   const created = await page.request.post("/api/v1/simulation/runs", {
  80  |     headers: { "x-dashboard-role": "EXPERIMENT_OPERATOR" },
  81  |     data: draft(),
  82  |   });
  83  |   const run = await created.json();
  84  | 
  85  |   await page.goto("/simulation");
  86  | 
  87  |   expect(created.status()).toBe(202);
  88  |   await expect(page.getByText(run.run_id)).toBeVisible({ timeout: 15_000 });
  89  |   await expect(
  90  |     page
  91  |       .getByRole("row")
  92  |       .filter({ hasText: run.run_id })
  93  |       .getByText("MOCK", { exact: true })
  94  |       .first(),
  95  |   ).toBeVisible();
  96  |   await expect(
  97  |     page
  98  |       .getByRole("row")
  99  |       .filter({ hasText: run.run_id })
  100 |       .getByText("SUCCEEDED", { exact: true })
  101 |       .first(),
> 102 |   ).toBeVisible({ timeout: 15_000 });
      |     ^ Error: expect(locator).toBeVisible() failed
  103 | });
  104 | 
  105 | test("E2E-06 creates MuJoCo single experiment through FastAPI", async ({
  106 |   page,
  107 | }) => {
  108 |   test.skip(
  109 |     process.env.PLAYWRIGHT_MUJOCO_RUNTIME !== "1",
  110 |     "MuJoCo runtime E2E is environment dependent and excluded from ordinary CI.",
  111 |   );
  112 | 
  113 |   const response = await page.request.post("/api/v1/simulation/runs", {
  114 |     headers: operatorHeaders,
  115 |     data: draft({ backend: "MUJOCO" }),
  116 |   });
  117 |   const payload = await response.json();
  118 |   const terminal = await waitForRunStatus(page, payload.run_id, [
  119 |     "SUCCEEDED",
  120 |     "BLOCKED_BY_ENV",
  121 |     "FAILED",
  122 |   ]);
  123 | 
  124 |   expect(response.status()).toBe(202);
  125 |   expect(payload.backend).toBe("MUJOCO");
  126 |   expect(payload.status).toBe("QUEUED");
  127 |   expect(terminal.status).toBe("SUCCEEDED");
  128 |   expect(terminal.backend).toBe("MUJOCO");
  129 |   const artifactPaths = terminal.artifact_paths as Record<string, string>;
  130 |   const resultPath = path.join(
  131 |     process.env.BIGSMALL_E2E_ARTIFACT_ROOT!,
  132 |     artifactPaths.result,
  133 |   );
  134 |   // SUCCEEDED 状态可先于原子 artifact 落盘；等待证据，仍要求真实运行字段。
  135 |   await expect
  136 |     .poll(
  137 |       () => {
  138 |         try {
  139 |           const evidence = JSON.parse(readFileSync(resultPath, "utf-8"));
  140 |           return {
  141 |             runtime_executed: evidence.runtime_executed,
  142 |             mock_fallback_used: evidence.mock_fallback_used,
  143 |           };
  144 |         } catch {
  145 |           return null;
  146 |         }
  147 |       },
  148 |       { timeout: 15_000 },
  149 |     )
  150 |     .toEqual({ runtime_executed: true, mock_fallback_used: false });
  151 |   const result = JSON.parse(readFileSync(resultPath, "utf-8"));
  152 |   expect(result.runtime_executed).toBe(true);
  153 |   expect(result.mock_fallback_used).toBe(false);
  154 |   expect(result.trial.metrics.physics_steps).toBeGreaterThan(0);
  155 |   expect(payload.hardware_motion_observed).toBe(false);
  156 | });
  157 | 
  158 | test("E2E-07 creates mode comparison batch", async ({ page }) => {
  159 |   const response = await page.request.post("/api/v1/simulation/batches", {
  160 |     headers: operatorHeaders,
  161 |     data: draft({
  162 |       run_type: "MODE_COMPARISON",
  163 |       control_modes: ["PCSC", "ETEAC", "AUTO"],
  164 |     }),
  165 |   });
  166 |   const payload = await response.json();
  167 | 
  168 |   expect(response.status()).toBe(202);
  169 |   expect(payload.progress.total).toBe(3);
  170 |   const terminal = await waitForBatchDone(page, payload.batch_id);
  171 |   expect(terminal.progress.succeeded).toBe(3);
  172 |   expect(payload.hardware_write_operations).toEqual([]);
  173 | });
  174 | 
  175 | test("E2E-08 creates multi-seed batch", async ({ page }) => {
  176 |   const response = await page.request.post("/api/v1/simulation/batches", {
  177 |     headers: operatorHeaders,
  178 |     data: draft({ seeds: [0, 1, 2] }),
  179 |   });
  180 |   const payload = await response.json();
  181 | 
  182 |   expect(response.status()).toBe(202);
  183 |   expect(payload.progress.total).toBe(3);
  184 |   const terminal = await waitForBatchDone(page, payload.batch_id);
  185 |   expect(terminal.progress.succeeded).toBe(3);
  186 | });
  187 | 
  188 | test("E2E-09 creates latency sweep validation", async ({ page }) => {
  189 |   const response = await page.request.post("/api/v1/simulation/validate", {
  190 |     data: draft({
  191 |       scenarios: ["S01_NORMAL_STATIC", "S07_NETWORK_DEGRADED"],
  192 |       control_modes: ["PCSC", "ETEAC"],
  193 |       seeds: [0, 1],
  194 |     }),
  195 |   });
  196 |   const payload = await response.json();
  197 | 
  198 |   expect(response.status()).toBe(200);
  199 |   expect(payload.run_count).toBe(8);
  200 | });
  201 | 
  202 | test("E2E-10 rejects oversized sweep", async ({ page }) => {
```