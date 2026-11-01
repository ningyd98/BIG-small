# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: console.spec.ts >> E2E-08 creates multi-seed batch
- Location: tests/e2e/console.spec.ts:175:1

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: 3
Received: 0
```

# Test source

```ts
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
  102 |   ).toBeVisible({ timeout: 15_000 });
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
> 185 |   expect(terminal.progress.succeeded).toBe(3);
      |                                       ^ Error: expect(received).toBe(expected) // Object.is equality
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
  203 |   const response = await page.request.post("/api/v1/simulation/validate", {
  204 |     data: draft({ seeds: Array.from({ length: 121 }, (_, index) => index) }),
  205 |   });
  206 | 
  207 |   expect(response.status()).toBe(422);
  208 | });
  209 | 
  210 | test("E2E-11 LiveRun status flow is visible", async ({ page }) => {
  211 |   const created = await page.request.post("/api/v1/simulation/runs", {
  212 |     headers: operatorHeaders,
  213 |     data: draft(),
  214 |   });
  215 |   const run = await created.json();
  216 |   const terminal = await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);
  217 | 
  218 |   expect(created.status()).toBe(202);
  219 |   expect(run.status).toBe("QUEUED");
  220 |   await page.goto("/simulation/live");
  221 |   const row = page.getByRole("row").filter({ hasText: run.run_id });
  222 |   await expect(row).toBeVisible({ timeout: 15_000 });
  223 |   await expect(
  224 |     row.getByText(terminal.status, { exact: true }).first(),
  225 |   ).toBeVisible({ timeout: 15_000 });
  226 | });
  227 | 
  228 | test("E2E-12 LiveRun fault timeline includes emergency stop", async ({
  229 |   page,
  230 | }) => {
  231 |   const created = await page.request.post("/api/v1/simulation/runs", {
  232 |     headers: operatorHeaders,
  233 |     data: draft({ scenarios: ["S14_EMERGENCY_STOP"] }),
  234 |   });
  235 |   const run = await created.json();
  236 |   await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);
  237 |   const events = await page.request.get(
  238 |     `/api/v1/simulation/runs/${run.run_id}/events`,
  239 |   );
  240 |   const payload = await events.json();
  241 | 
  242 |   expect(events.ok()).toBeTruthy();
  243 |   expect(JSON.stringify(payload.events)).toMatch(
  244 |     /fault|task_completed|emergency/i,
  245 |   );
  246 | });
  247 | 
  248 | test("E2E-13 WebSocket stream supports polling fallback", async ({ page }) => {
  249 |   await page.goto("/");
  250 | 
  251 |   await expect(page.getByText(/轮询可用，WebSocket 可兜底/)).toBeVisible();
  252 |   const response = await page.request.get("/api/v1/simulation/runs");
  253 |   expect(response.ok()).toBeTruthy();
  254 | });
  255 | 
  256 | test("E2E-14 views metrics and chart route", async ({ page }) => {
  257 |   const created = await page.request.post("/api/v1/simulation/runs", {
  258 |     headers: operatorHeaders,
  259 |     data: draft(),
  260 |   });
  261 |   const run = await created.json();
  262 |   await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);
  263 |   const metrics = await page.request.get(
  264 |     `/api/v1/simulation/runs/${run.run_id}/metrics`,
  265 |   );
  266 | 
  267 |   await page.goto("/simulation/analysis");
  268 | 
  269 |   expect(metrics.ok()).toBeTruthy();
  270 |   expect((await metrics.json()).metrics.length).toBeGreaterThan(0);
  271 |   await expect(page.getByText("Result Analysis")).toBeVisible();
  272 | });
  273 | 
  274 | test("E2E-15 exports CSV and JSON", async ({ page }) => {
  275 |   const created = await page.request.post("/api/v1/simulation/runs", {
  276 |     headers: operatorHeaders,
  277 |     data: draft(),
  278 |   });
  279 |   const run = await created.json();
  280 |   await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);
  281 |   const csv = await page.request.post("/api/v1/simulation/exports", {
  282 |     data: { export_type: "Metrics CSV", run_ids: [run.run_id] },
  283 |   });
  284 |   const manifest = await page.request.post("/api/v1/simulation/exports", {
  285 |     data: { export_type: "Manifest JSON", run_ids: [run.run_id] },
```