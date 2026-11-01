# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: console.spec.ts >> E2E-22 Phase11.1 create run returns QUEUED immediately
- Location: tests/e2e/console.spec.ts:369:1

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: "QUEUED"
Received: "BLOCKED_BY_ENV"
```

# Test source

```ts
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
  286 |   });
  287 | 
  288 |   expect(csv.ok()).toBeTruthy();
  289 |   expect((await csv.json()).format).toBe("Metrics CSV");
  290 |   expect(manifest.ok()).toBeTruthy();
  291 |   expect((await manifest.json()).redacted).toBe(true);
  292 | });
  293 | 
  294 | test("E2E-16 reproduces from historical run", async ({ page }) => {
  295 |   const created = await page.request.post("/api/v1/simulation/runs", {
  296 |     headers: operatorHeaders,
  297 |     data: draft(),
  298 |   });
  299 |   const run = await created.json();
  300 |   const response = await page.request.post(
  301 |     `/api/v1/simulation/runs/${run.run_id}/reproduce`,
  302 |   );
  303 |   const payload = await response.json();
  304 | 
  305 |   expect(response.ok()).toBeTruthy();
  306 |   expect(payload.draft.scenarios).toEqual(["S01_NORMAL_STATIC"]);
  307 |   expect(payload.reproducibility_hash).toBeTruthy();
  308 | });
  309 | 
  310 | test("E2E-17 simulation API exposes no hardware route", async ({ page }) => {
  311 |   const capabilities = await page.request.get(
  312 |     "/api/v1/simulation/capabilities",
  313 |   );
  314 |   const payload = await capabilities.json();
  315 | 
  316 |   expect(payload.real_controller_contacted).toBe(false);
  317 |   expect(payload.hardware_motion_observed).toBe(false);
  318 |   expect(payload.hardware_write_operations).toEqual([]);
  319 |   expect(
  320 |     (await page.request.post("/api/v1/simulation/hardware/enable")).status(),
  321 |   ).toBe(404);
  322 | });
  323 | 
  324 | test("E2E-18 path traversal rejection remains enforced", async ({ page }) => {
  325 |   const response = await page.request.get(
  326 |     "/api/v1/dashboard/evidence/..%2Fsecret",
  327 |   );
  328 | 
  329 |   expect([400, 404]).toContain(response.status());
  330 | });
  331 | 
  332 | test("E2E-19 VIEWER write rejection remains enforced", async ({ page }) => {
  333 |   const response = await page.request.post("/api/v1/simulation/runs", {
  334 |     headers: { "x-dashboard-role": "VIEWER" },
  335 |     data: draft(),
  336 |   });
  337 | 
  338 |   expect(response.status()).toBe(403);
  339 | });
  340 | 
  341 | test("E2E-20 no direct ROS MoveIt controller inputs are exposed", async ({
  342 |   page,
  343 | }) => {
  344 |   await page.goto("/");
  345 | 
  346 |   await expect(
  347 |     page.getByText(/FollowJointTrajectory|MoveIt execute|controller enable/i),
  348 |   ).toHaveCount(0);
  349 |   expect(
  350 |     (await page.request.post("/api/v1/simulation/controller/enable")).status(),
  351 |   ).toBe(404);
  352 | });
  353 | 
  354 | test("E2E-21 Isaac returns BLOCKED_BY_ENV without Mock fallback", async ({
  355 |   page,
  356 | }) => {
  357 |   const response = await page.request.post("/api/v1/simulation/runs", {
  358 |     headers: operatorHeaders,
  359 |     data: draft({ backend: "ISAAC_SIM" }),
  360 |   });
  361 |   const payload = await response.json();
  362 | 
  363 |   expect(response.status()).toBe(202);
  364 |   expect(payload.backend).toBe("ISAAC_SIM");
  365 |   expect(payload.status).toBe("BLOCKED_BY_ENV");
  366 |   expect(payload.hardware_motion_observed).toBe(false);
  367 | });
  368 | 
  369 | test("E2E-22 Phase11.1 create run returns QUEUED immediately", async ({
  370 |   page,
  371 | }) => {
  372 |   const created = await createRuntimeRun(page, { runtime_delay_ms: 500 });
  373 |   const run = await created.json();
  374 | 
  375 |   expect(created.status()).toBe(202);
> 376 |   expect(run.status).toBe("QUEUED");
      |                      ^ Error: expect(received).toBe(expected) // Object.is equality
  377 |   expect(run.job_id).toBeTruthy();
  378 |   expect(run.queue_position).toBeGreaterThanOrEqual(1);
  379 | });
  380 | 
  381 | test("E2E-23 Phase11.1 status advances to running then succeeded", async ({
  382 |   page,
  383 | }) => {
  384 |   const created = await createRuntimeRun(page, { runtime_delay_ms: 900 });
  385 |   const run = await created.json();
  386 |   const active = await waitForRunStatus(page, run.run_id, [
  387 |     "VALIDATING",
  388 |     "LEASED",
  389 |     "STARTING",
  390 |     "RUNNING",
  391 |     "SUCCEEDED",
  392 |   ]);
  393 |   const terminal = await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);
  394 | 
  395 |   expect([
  396 |     "VALIDATING",
  397 |     "LEASED",
  398 |     "STARTING",
  399 |     "RUNNING",
  400 |     "SUCCEEDED",
  401 |   ]).toContain(active.status);
  402 |   expect(terminal.status).toBe("SUCCEEDED");
  403 | });
  404 | 
  405 | test("E2E-24 Phase11.1 runtime events persist and grow", async ({ page }) => {
  406 |   const created = await createRuntimeRun(page, { runtime_delay_ms: 300 });
  407 |   const run = await created.json();
  408 |   const early = await runEvents(page, run.run_id);
  409 | 
  410 |   await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);
  411 |   const final = await runEvents(page, run.run_id);
  412 | 
  413 |   expect(early.length).toBeGreaterThanOrEqual(1);
  414 |   expect(final.length).toBeGreaterThan(early.length);
  415 |   expect(final.map((event) => event.event_type)).toContain("job_completed");
  416 | });
  417 | 
  418 | test("E2E-25 Phase11.1 metrics appear after worker completion", async ({
  419 |   page,
  420 | }) => {
  421 |   const created = await createRuntimeRun(page, { runtime_delay_ms: 200 });
  422 |   const run = await created.json();
  423 | 
  424 |   await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);
  425 |   const metrics = await runMetrics(page, run.run_id);
  426 | 
  427 |   expect(metrics.length).toBeGreaterThan(0);
  428 |   expect(metrics.map((metric) => metric.name)).toContain("task_success");
  429 | });
  430 | 
  431 | test("E2E-26 Phase11.1 cancels a running job cooperatively", async ({
  432 |   page,
  433 | }) => {
  434 |   const created = await createRuntimeRun(page, { runtime_delay_ms: 2000 });
  435 |   const run = await created.json();
  436 |   await waitForRunStatus(page, run.run_id, ["STARTING", "RUNNING"]);
  437 | 
  438 |   const cancel = await page.request.post(
  439 |     `/api/v1/simulation/runs/${run.run_id}/cancel`,
  440 |     { headers: operatorHeaders },
  441 |   );
  442 |   const terminal = await waitForRunStatus(page, run.run_id, ["CANCELLED"]);
  443 | 
  444 |   expect(cancel.ok()).toBeTruthy();
  445 |   expect(terminal.status).toBe("CANCELLED");
  446 | });
  447 | 
  448 | test("E2E-27 Phase11.1 records cancel progress events", async ({ page }) => {
  449 |   const created = await createRuntimeRun(page, { runtime_delay_ms: 2000 });
  450 |   const run = await created.json();
  451 |   await waitForRunStatus(page, run.run_id, ["STARTING", "RUNNING"]);
  452 |   await page.request.post(`/api/v1/simulation/runs/${run.run_id}/cancel`, {
  453 |     headers: operatorHeaders,
  454 |   });
  455 |   await waitForRunStatus(page, run.run_id, ["CANCELLED"]);
  456 | 
  457 |   const events = await runEvents(page, run.run_id);
  458 |   expect(events.map((event) => event.event_type)).toEqual(
  459 |     expect.arrayContaining(["cancel_requested", "job_cancelled"]),
  460 |   );
  461 | });
  462 | 
  463 | test("E2E-28 Phase11.1 marks constrained runs as TIMED_OUT", async ({
  464 |   page,
  465 | }) => {
  466 |   const created = await createRuntimeRun(page, {
  467 |     runtime_delay_ms: 1500,
  468 |     timeout_seconds: 1,
  469 |   });
  470 |   const run = await created.json();
  471 |   const terminal = await waitForRunStatus(page, run.run_id, ["TIMED_OUT"]);
  472 | 
  473 |   expect(terminal.status).toBe("TIMED_OUT");
  474 | });
  475 | 
  476 | test("E2E-29 Phase11.1 safe recovery keeps run history queryable", async ({
```