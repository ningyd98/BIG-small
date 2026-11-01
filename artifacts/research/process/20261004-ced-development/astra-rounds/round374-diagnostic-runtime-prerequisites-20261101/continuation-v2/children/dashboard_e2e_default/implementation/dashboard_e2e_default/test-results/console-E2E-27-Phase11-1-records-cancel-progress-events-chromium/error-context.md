# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: console.spec.ts >> E2E-27 Phase11.1 records cancel progress events
- Location: tests/e2e/console.spec.ts:448:1

# Error details

```
Error: Run sim-57dcc0f79e05 did not reach STARTING, RUNNING; last={"run_id":"sim-57dcc0f79e05","job_id":"job-979024da499c482a","queue_position":0,"backend":"MOCK","run_type":"SINGLE","status":"BLOCKED_BY_ENV","scenario_id":"S01_NORMAL_STATIC","control_mode":"PCSC","seed":0,"manifest":{"manifest_id":"manifest-44a239bef2ab","schema_version":"phase11.simulation.v1","normalized_config":{"backend":"MOCK","control_modes":["PCSC"],"dataset_config":null,"description":"playwright","domain_randomization":{"enabled":false,"level":"NONE","parameters":{}},"execution_scope":"VISUAL_PLANNING","fault_profiles":[{"name":"none","parameters":{}}],"input_mode":"RGBD","job_type":"SIMULATION","network_profiles":[{"bandwidth_kbps":10000,"base_latency_ms":40,"jitter_ms":5,"name":"NORMAL","packet_loss":0}],"parameter_overrides":{"cache_policy":"CACHE_ENABLED","retry_budget":2,"runtime_delay_ms":2000,"supervision_period_ms":300,"timeout_ms":30000},"repetitions":1,"run_type":"SINGLE","scenarios":["S01_NORMAL_STATIC"],"seeds":[0],"tags":["e2e"],"user_instruction":"将红色方块放到绿色区域"},"source_commit":"8089743604be33ab107853f86894de211f7bf259","source_tree_hash":"f800f1c99163cbcd0f4203d8569ac1d348150db2a34df402afb22c087d23f66c","created_at":"2026-11-01T07:03:02.184798Z","run_count":1,"reproducibility_hash":"44a239bef2abf6dcaa642917cb64cfa512c4d9393129453daafa956603c1f11a"},"created_at":"2026-11-01T07:03:02.306481Z","accepted_at":null,"updated_at":"2026-11-01T07:03:02.329695Z","started_at":null,"completed_at":"2026-11-01T07:03:02.329695Z","attempt":0,"max_attempts":2,"timeout_seconds":30,"cancel_requested":false,"worker_id":"","lease_id":"","runtime_reason":"RGBD requires a real simulator camera; Mock is LEGACY_PIPELINE only","blockers":["RGBD requires a real simulator camera; Mock is LEGACY_PIPELINE only"],"artifact_paths":{},"hardware_claim":"SIMULATION_ONLY","real_controller_contacted":false,"hardware_motion_observed":false,"hardware_write_operations":[],"provenance":{"config_hash":"e84337981d7c401694d900986fc94eb698fec9d148a208fdaf2144e6d26b7c0e","generated_at":"2026-11-01T07:03:02.303179+00:00","hardware_motion_observed":false,"hardware_write_operations":[],"real_controller_contacted":false,"source_commit":"8089743604be33ab107853f86894de211f7bf259","source_tree_hash":"f800f1c99163cbcd0f4203d8569ac1d348150db2a34df402afb22c087d23f66c"},"publication":{"schema_version":"simulation.publication-status.v1","recorded_sql_status":"BLOCKED_BY_ENV","confirmation_state":"NOT_APPLICABLE","accepted":false,"operation_id":null,"attempt":0,"epoch":null,"generation":null,"job_receipt_hash":null,"event_receipt_hash":null,"artifact_manifest_sha256":null,"confirmed_artifact_paths":{},"historical_artifact_paths":{},"reasons":[]}}
```

# Test source

```ts
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
  612 |     },
  613 |   });
  614 |   const payload = await created.json();
  615 |   const listed = await page.request.get("/api/v1/model-control/profiles");
  616 |   const listPayload = await listed.json();
  617 | 
  618 |   expect(created.status()).toBe(201);
  619 |   expect(payload.secret_present).toBe(true);
  620 |   expect(JSON.stringify(payload)).not.toContain("TEST_SECRET_VALUE_E2E");
  621 |   expect(JSON.stringify(listPayload)).not.toContain("TEST_SECRET_VALUE_E2E");
  622 | });
  623 | 
  624 | test("E2E-M04 planner dry-run never dispatches hardware", async ({ page }) => {
  625 |   const response = await page.request.post(
  626 |     "/api/v1/model-control/planner/dry-run",
  627 |     {
  628 |       data: {
  629 |         user_instruction: "pick red cube",
  630 |         sample_scene: "S01_NORMAL_STATIC",
  631 |         control_mode: "PCSC",
  632 |       },
  633 |     },
  634 |   );
  635 |   const payload = await response.json();
  636 | 
  637 |   expect(response.ok()).toBeTruthy();
  638 |   expect(payload.dispatch).toBe(false);
  639 |   expect(payload.hardware_execution).toBe(false);
  640 | });
  641 | 
  642 | async function createRuntimeRun(
  643 |   page: Page,
  644 |   parameterOverrides: Record<string, unknown> = {},
  645 | ) {
  646 |   return page.request.post("/api/v1/simulation/runs", {
  647 |     headers: operatorHeaders,
  648 |     data: draft({ parameter_overrides: parameterOverrides }),
  649 |   });
  650 | }
  651 | 
  652 | async function waitForRunStatus(
  653 |   page: Page,
  654 |   runId: string,
  655 |   statuses: string[],
  656 |   timeoutMs = 15_000,
  657 | ) {
  658 |   const deadline = Date.now() + timeoutMs;
  659 |   let last: Record<string, unknown> | undefined;
  660 |   while (Date.now() < deadline) {
  661 |     const response = await page.request.get(`/api/v1/simulation/runs/${runId}`);
  662 |     expect(response.ok()).toBeTruthy();
  663 |     last = (await response.json()) as Record<string, unknown>;
  664 |     if (statuses.includes(String(last.status))) {
  665 |       return last;
  666 |     }
  667 |     await page.waitForTimeout(100);
  668 |   }
> 669 |   throw new Error(
      |         ^ Error: Run sim-57dcc0f79e05 did not reach STARTING, RUNNING; last={"run_id":"sim-57dcc0f79e05","job_id":"job-979024da499c482a","queue_position":0,"backend":"MOCK","run_type":"SINGLE","status":"BLOCKED_BY_ENV","scenario_id":"S01_NORMAL_STATIC","control_mode":"PCSC","seed":0,"manifest":{"manifest_id":"manifest-44a239bef2ab","schema_version":"phase11.simulation.v1","normalized_config":{"backend":"MOCK","control_modes":["PCSC"],"dataset_config":null,"description":"playwright","domain_randomization":{"enabled":false,"level":"NONE","parameters":{}},"execution_scope":"VISUAL_PLANNING","fault_profiles":[{"name":"none","parameters":{}}],"input_mode":"RGBD","job_type":"SIMULATION","network_profiles":[{"bandwidth_kbps":10000,"base_latency_ms":40,"jitter_ms":5,"name":"NORMAL","packet_loss":0}],"parameter_overrides":{"cache_policy":"CACHE_ENABLED","retry_budget":2,"runtime_delay_ms":2000,"supervision_period_ms":300,"timeout_ms":30000},"repetitions":1,"run_type":"SINGLE","scenarios":["S01_NORMAL_STATIC"],"seeds":[0],"tags":["e2e"],"user_instruction":"将红色方块放到绿色区域"},"source_commit":"8089743604be33ab107853f86894de211f7bf259","source_tree_hash":"f800f1c99163cbcd0f4203d8569ac1d348150db2a34df402afb22c087d23f66c","created_at":"2026-11-01T07:03:02.184798Z","run_count":1,"reproducibility_hash":"44a239bef2abf6dcaa642917cb64cfa512c4d9393129453daafa956603c1f11a"},"created_at":"2026-11-01T07:03:02.306481Z","accepted_at":null,"updated_at":"2026-11-01T07:03:02.329695Z","started_at":null,"completed_at":"2026-11-01T07:03:02.329695Z","attempt":0,"max_attempts":2,"timeout_seconds":30,"cancel_requested":false,"worker_id":"","lease_id":"","runtime_reason":"RGBD requires a real simulator camera; Mock is LEGACY_PIPELINE only","blockers":["RGBD requires a real simulator camera; Mock is LEGACY_PIPELINE only"],"artifact_paths":{},"hardware_claim":"SIMULATION_ONLY","real_controller_contacted":false,"hardware_motion_observed":false,"hardware_write_operations":[],"provenance":{"config_hash":"e84337981d7c401694d900986fc94eb698fec9d148a208fdaf2144e6d26b7c0e","generated_at":"2026-11-01T07:03:02.303179+00:00","hardware_motion_observed":false,"hardware_write_operations":[],"real_controller_contacted":false,"source_commit":"8089743604be33ab107853f86894de211f7bf259","source_tree_hash":"f800f1c99163cbcd0f4203d8569ac1d348150db2a34df402afb22c087d23f66c"},"publication":{"schema_version":"simulation.publication-status.v1","recorded_sql_status":"BLOCKED_BY_ENV","confirmation_state":"NOT_APPLICABLE","accepted":false,"operation_id":null,"attempt":0,"epoch":null,"generation":null,"job_receipt_hash":null,"event_receipt_hash":null,"artifact_manifest_sha256":null,"confirmed_artifact_paths":{},"historical_artifact_paths":{},"reasons":[]}}
  670 |     `Run ${runId} did not reach ${statuses.join(", ")}; last=${JSON.stringify(
  671 |       last,
  672 |     )}`,
  673 |   );
  674 | }
  675 | 
  676 | async function waitForBatchDone(
  677 |   page: Page,
  678 |   batchId: string,
  679 |   timeoutMs = 20_000,
  680 | ) {
  681 |   const deadline = Date.now() + timeoutMs;
  682 |   let last: BatchPayload | undefined;
  683 |   while (Date.now() < deadline) {
  684 |     const response = await page.request.get(
  685 |       `/api/v1/simulation/batches/${batchId}`,
  686 |     );
  687 |     expect(response.ok()).toBeTruthy();
  688 |     last = (await response.json()) as BatchPayload;
  689 |     const progress = last.progress;
  690 |     if (
  691 |       progress.total ===
  692 |       progress.succeeded +
  693 |         progress.failed +
  694 |         progress.blocked +
  695 |         progress.cancelled +
  696 |         progress.timed_out
  697 |     ) {
  698 |       return last;
  699 |     }
  700 |     await page.waitForTimeout(100);
  701 |   }
  702 |   throw new Error(
  703 |     `Batch ${batchId} did not finish; last=${JSON.stringify(last)}`,
  704 |   );
  705 | }
  706 | 
  707 | async function runEvents(page: Page, runId: string) {
  708 |   const response = await page.request.get(
  709 |     `/api/v1/simulation/runs/${runId}/events`,
  710 |   );
  711 |   expect(response.ok()).toBeTruthy();
  712 |   return ((await response.json()) as { events: TimelinePayload[] }).events;
  713 | }
  714 | 
  715 | async function runMetrics(page: Page, runId: string) {
  716 |   const response = await page.request.get(
  717 |     `/api/v1/simulation/runs/${runId}/metrics`,
  718 |   );
  719 |   expect(response.ok()).toBeTruthy();
  720 |   return ((await response.json()) as { metrics: MetricPayload[] }).metrics;
  721 | }
  722 | 
  723 | async function readStreamReplay(
  724 |   page: Page,
  725 |   lastSequence: number,
  726 |   minEvents: number,
  727 | ) {
  728 |   return page.evaluate(
  729 |     ({ lastSequence: replayAfter, minEvents: minimum }) =>
  730 |       new Promise<Array<{ sequence: number; event_type: string }>>(
  731 |         (resolve, reject) => {
  732 |           const events: Array<{ sequence: number; event_type: string }> = [];
  733 |           const socket = new WebSocket(
  734 |             `ws://127.0.0.1:8000/api/v1/simulation/stream?last_sequence=${replayAfter}`,
  735 |           );
  736 |           const timer = window.setTimeout(() => {
  737 |             socket.close();
  738 |             reject(new Error(`Timed out waiting for ${minimum} replay events`));
  739 |           }, 5000);
  740 |           socket.onerror = () => {
  741 |             window.clearTimeout(timer);
  742 |             reject(new Error("simulation stream websocket failed"));
  743 |           };
  744 |           socket.onmessage = (message) => {
  745 |             const payload = JSON.parse(String(message.data));
  746 |             if (payload.event_type !== "heartbeat") {
  747 |               events.push({
  748 |                 sequence: Number(payload.sequence),
  749 |                 event_type: String(payload.event_type),
  750 |               });
  751 |             }
  752 |             if (events.length >= minimum) {
  753 |               window.clearTimeout(timer);
  754 |               socket.close();
  755 |               resolve(events);
  756 |             }
  757 |           };
  758 |         },
  759 |       ),
  760 |     { lastSequence, minEvents },
  761 |   );
  762 | }
  763 | 
  764 | function draft(overrides: Record<string, unknown> = {}) {
  765 |   const base = {
  766 |     backend: "MOCK",
  767 |     run_type: "SINGLE",
  768 |     scenarios: ["S01_NORMAL_STATIC"],
  769 |     control_modes: ["PCSC"],
```