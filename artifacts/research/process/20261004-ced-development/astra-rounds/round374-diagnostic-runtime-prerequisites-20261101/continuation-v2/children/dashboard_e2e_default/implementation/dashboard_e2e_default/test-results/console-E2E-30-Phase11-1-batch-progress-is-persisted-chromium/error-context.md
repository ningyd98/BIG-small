# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: console.spec.ts >> E2E-30 Phase11.1 batch progress is persisted
- Location: tests/e2e/console.spec.ts:498:1

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: 3
Received: 0
```

# Test source

```ts
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
  477 |   page,
  478 | }) => {
  479 |   const created = await createRuntimeRun(page);
  480 |   const run = await created.json();
  481 |   await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);
  482 | 
  483 |   const recovery = await page.request.post(
  484 |     "/api/v1/simulation/runtime/recover",
  485 |     {
  486 |       headers: { "x-dashboard-role": "SAFETY_REVIEWER" },
  487 |     },
  488 |   );
  489 |   const history = await page.request.get(
  490 |     `/api/v1/simulation/runs/${run.run_id}`,
  491 |   );
  492 | 
  493 |   expect(recovery.ok()).toBeTruthy();
  494 |   expect(history.ok()).toBeTruthy();
  495 |   expect((await history.json()).run_id).toBe(run.run_id);
  496 | });
  497 | 
  498 | test("E2E-30 Phase11.1 batch progress is persisted", async ({ page }) => {
  499 |   const response = await page.request.post("/api/v1/simulation/batches", {
  500 |     headers: operatorHeaders,
  501 |     data: draft({
  502 |       seeds: [0, 1, 2],
  503 |       parameter_overrides: { runtime_delay_ms: 200 },
  504 |     }),
  505 |   });
  506 |   const batch = await response.json();
  507 |   const terminal = await waitForBatchDone(page, batch.batch_id);
  508 | 
  509 |   expect(response.status()).toBe(202);
  510 |   expect(terminal.progress.total).toBe(3);
> 511 |   expect(terminal.progress.succeeded).toBe(3);
      |                                       ^ Error: expect(received).toBe(expected) // Object.is equality
  512 | });
  513 | 
  514 | test("E2E-31 Phase11.1 retry failed run requeues safely", async ({ page }) => {
  515 |   const created = await createRuntimeRun(page, {
  516 |     runtime_delay_ms: 1500,
  517 |     timeout_seconds: 1,
  518 |   });
  519 |   const run = await created.json();
  520 |   await waitForRunStatus(page, run.run_id, ["TIMED_OUT"]);
  521 | 
  522 |   const retry = await page.request.post(
  523 |     `/api/v1/simulation/runs/${run.run_id}/retry`,
  524 |     { headers: operatorHeaders },
  525 |   );
  526 |   const retried = await retry.json();
  527 | 
  528 |   expect(retry.ok()).toBeTruthy();
  529 |   expect(retried.status).toBe("QUEUED");
  530 | });
  531 | 
  532 | test("E2E-32 Phase11.1 worker health and queue panels render", async ({
  533 |   page,
  534 | }) => {
  535 |   await page.goto("/simulation/live");
  536 | 
  537 |   await expect(page.getByText("Runtime Health")).toBeVisible();
  538 |   await expect(
  539 |     page.locator(".ant-card-head-title").filter({ hasText: /^Queue$/ }),
  540 |   ).toBeVisible();
  541 |   await expect(
  542 |     page.locator(".ant-card-head-title").filter({ hasText: /^Workers$/ }),
  543 |   ).toBeVisible();
  544 | });
  545 | 
  546 | test("E2E-33 Phase11.1 WebSocket replay is persisted without duplicates", async ({
  547 |   page,
  548 | }) => {
  549 |   const created = await createRuntimeRun(page);
  550 |   const run = await created.json();
  551 |   await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);
  552 | 
  553 |   const firstReplay = await readStreamReplay(page, 0, 3);
  554 |   const lastSequence = Math.max(...firstReplay.map((event) => event.sequence));
  555 |   const secondReplay = await readStreamReplay(page, lastSequence, 1);
  556 |   const secondSequences = secondReplay.map((event) => event.sequence);
  557 | 
  558 |   expect(new Set(firstReplay.map((event) => event.sequence)).size).toBe(
  559 |     firstReplay.length,
  560 |   );
  561 |   expect(secondSequences.every((sequence) => sequence > lastSequence)).toBe(
  562 |     true,
  563 |   );
  564 | });
  565 | 
  566 | test("E2E-M01 opens AI model control center", async ({ page }) => {
  567 |   await page.goto("/models");
  568 | 
  569 |   await expect(
  570 |     page.getByRole("heading", { name: "AI 模型控制中心" }),
  571 |   ).toBeVisible();
  572 |   await expect(
  573 |     page
  574 |       .locator(".ant-card-head-title")
  575 |       .filter({ hasText: /^Planner Dry-Run$/ }),
  576 |   ).toBeVisible();
  577 |   await expect(page.getByText(/hardware_execution=false/i)).toBeVisible();
  578 |   await expect(page.getByText(/execute hardware/i)).toHaveCount(0);
  579 | });
  580 | 
  581 | test("E2E-M02 creates and activates RuleBased profile", async ({ page }) => {
  582 |   await page.goto("/models");
  583 |   const created = await page.request.post("/api/v1/model-control/profiles", {
  584 |     data: {
  585 |       display_name: "E2E RuleBased",
  586 |       provider_kind: "RULE_BASED",
  587 |       model_name: "rule-based",
  588 |     },
  589 |   });
  590 |   const profile = await created.json();
  591 |   await page.request.post(
  592 |     `/api/v1/model-control/profiles/${profile.profile_id}/activate`,
  593 |   );
  594 |   await page.reload();
  595 |   await expect(
  596 |     page.getByRole("cell", { name: "E2E RuleBased" }).first(),
  597 |   ).toBeVisible();
  598 |   await expect(page.getByText("RULE_BASED").first()).toBeVisible();
  599 | });
  600 | 
  601 | test("E2E-M03 API key is write-only in model profile response", async ({
  602 |   page,
  603 | }) => {
  604 |   const created = await page.request.post("/api/v1/model-control/profiles", {
  605 |     data: {
  606 |       display_name: "E2E Cloud",
  607 |       provider_kind: "OPENAI_COMPATIBLE",
  608 |       base_url: "https://api.example.test/v1",
  609 |       chat_completions_path: "/chat/completions",
  610 |       model_name: "safe-model",
  611 |       api_key: "TEST_SECRET_VALUE_E2E",
```