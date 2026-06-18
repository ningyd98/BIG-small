// 控制台 E2E 使用真实 FastAPI 与 fake 运行时服务，验证页面和 API 都不暴露硬件动作。
import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
const artifactRoot = path.resolve(process.cwd(), "../artifacts/dashboard_e2e");
const operatorHeaders = { "x-dashboard-role": "EXPERIMENT_OPERATOR" };

type BatchPayload = Record<string, unknown> & {
  progress: {
    total: number;
    succeeded: number;
    failed: number;
    blocked: number;
    cancelled: number;
    timed_out: number;
  };
};

type TimelinePayload = {
  sequence: number;
  event_type: string;
};

type MetricPayload = {
  name: string;
};

function seedArtifacts() {
  rmSync(artifactRoot, { recursive: true, force: true });
  mkdirSync(path.join(artifactRoot, "phase10"), { recursive: true });
  writeFileSync(
    path.join(artifactRoot, "phase10/dashboard_summary.json"),
    JSON.stringify(
      {
        status: "PHASE10_MOVEIT_DRY_RUN_ACCEPTED",
        planner_backend: "MOVEIT_RUNTIME",
        hardware_motion_observed: false,
        sent_to_hardware: false,
        real_robot_validation: "NOT_STARTED",
        blockers: [],
        provenance: {
          generated_from_commit: "e2e-commit",
          source_tree_hash: "e2e-tree",
          worktree_clean: true,
          generated_at: "2026-06-17T00:00:00Z",
        },
      },
      null,
      2,
    ) + "\n",
    "utf-8",
  );
}

test.beforeAll(seedArtifacts);

test("E2E-01 overview keeps dry-run acceptance without hardware validation", async ({
  page,
}) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "PHASE10_MOVEIT_DRY_RUN_ACCEPTED" }),
  ).toBeVisible();
  await expect(
    page.getByRole("main").getByText("真实机械臂验证：NOT_STARTED"),
  ).toBeVisible();
  await expect(
    page.getByText(/直连 ROS|MoveIt execute|控制器地址/i),
  ).toHaveCount(0);
});

test("E2E-02 loads S01-S15 from real FastAPI simulation API", async ({
  page,
}) => {
  const response = await page.request.get("/api/v1/simulation/scenarios");
  const payload = await response.json();

  expect(response.ok()).toBeTruthy();
  expect(payload.scenarios).toHaveLength(15);
  expect(
    payload.scenarios.map((item: { scenario_id: string }) => item.scenario_id),
  ).toContain("S15_SQLITE_RESTART_DURING_RUN");
});

test("E2E-03 searches network scenario in scenario library", async ({
  page,
}) => {
  await page.goto("/simulation/scenarios");

  await expect(page.getByText("S07_NETWORK_DEGRADED")).toBeVisible();
  await expect(
    page.getByText("NETWORK_DEGRADED", { exact: true }),
  ).toBeVisible();
});

test("E2E-04 shows S14 emergency-stop timeline details", async ({ page }) => {
  const response = await page.request.get(
    "/api/v1/simulation/scenarios/S14_EMERGENCY_STOP",
  );
  const payload = await response.json();

  expect(response.ok()).toBeTruthy();
  expect(payload.category).toBe("SAFETY");
  expect(payload.scheduled_faults[0].trigger_time_ms).toBe(600);
});

test("E2E-05 creates Mock single experiment", async ({ page }) => {
  const created = await page.request.post("/api/v1/simulation/runs", {
    headers: { "x-dashboard-role": "EXPERIMENT_OPERATOR" },
    data: draft(),
  });
  const run = await created.json();

  await page.goto("/simulation");

  expect(created.status()).toBe(202);
  await expect(page.getByText(run.run_id)).toBeVisible({ timeout: 15_000 });
  await expect(
    page
      .getByRole("row")
      .filter({ hasText: run.run_id })
      .getByText("MOCK", { exact: true })
      .first(),
  ).toBeVisible();
  await expect(
    page
      .getByRole("row")
      .filter({ hasText: run.run_id })
      .getByText("SUCCEEDED", { exact: true })
      .first(),
  ).toBeVisible({ timeout: 15_000 });
});

test("E2E-06 creates MuJoCo single experiment through FastAPI", async ({
  page,
}) => {
  test.skip(
    process.env.PLAYWRIGHT_MUJOCO_RUNTIME !== "1",
    "MuJoCo runtime E2E is environment dependent and excluded from ordinary CI.",
  );

  const response = await page.request.post("/api/v1/simulation/runs", {
    headers: operatorHeaders,
    data: draft({ backend: "MUJOCO" }),
  });
  const payload = await response.json();
  const terminal = await waitForRunStatus(page, payload.run_id, [
    "SUCCEEDED",
    "BLOCKED_BY_ENV",
    "FAILED",
  ]);

  expect(response.status()).toBe(202);
  expect(payload.backend).toBe("MUJOCO");
  expect(payload.status).toBe("QUEUED");
  expect(["SUCCEEDED", "BLOCKED_BY_ENV", "FAILED"]).toContain(terminal.status);
  expect(payload.hardware_motion_observed).toBe(false);
});

test("E2E-07 creates mode comparison batch", async ({ page }) => {
  const response = await page.request.post("/api/v1/simulation/batches", {
    headers: operatorHeaders,
    data: draft({
      run_type: "MODE_COMPARISON",
      control_modes: ["PCSC", "ETEAC", "AUTO"],
    }),
  });
  const payload = await response.json();

  expect(response.status()).toBe(202);
  expect(payload.progress.total).toBe(3);
  expect(payload.hardware_write_operations).toEqual([]);
});

test("E2E-08 creates multi-seed batch", async ({ page }) => {
  const response = await page.request.post("/api/v1/simulation/batches", {
    headers: operatorHeaders,
    data: draft({ seeds: [0, 1, 2] }),
  });
  const payload = await response.json();

  expect(response.status()).toBe(202);
  expect(payload.progress.total).toBe(3);
});

test("E2E-09 creates latency sweep validation", async ({ page }) => {
  const response = await page.request.post("/api/v1/simulation/validate", {
    data: draft({
      scenarios: ["S01_NORMAL_STATIC", "S07_NETWORK_DEGRADED"],
      control_modes: ["PCSC", "ETEAC"],
      seeds: [0, 1],
    }),
  });
  const payload = await response.json();

  expect(response.status()).toBe(200);
  expect(payload.run_count).toBe(8);
});

test("E2E-10 rejects oversized sweep", async ({ page }) => {
  const response = await page.request.post("/api/v1/simulation/validate", {
    data: draft({ seeds: Array.from({ length: 121 }, (_, index) => index) }),
  });

  expect(response.status()).toBe(422);
});

test("E2E-11 LiveRun status flow is visible", async ({ page }) => {
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
});

test("E2E-12 LiveRun fault timeline includes emergency stop", async ({
  page,
}) => {
  const created = await page.request.post("/api/v1/simulation/runs", {
    headers: operatorHeaders,
    data: draft({ scenarios: ["S14_EMERGENCY_STOP"] }),
  });
  const run = await created.json();
  await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);
  const events = await page.request.get(
    `/api/v1/simulation/runs/${run.run_id}/events`,
  );
  const payload = await events.json();

  expect(events.ok()).toBeTruthy();
  expect(JSON.stringify(payload.events)).toMatch(
    /fault|task_completed|emergency/i,
  );
});

test("E2E-13 WebSocket stream supports polling fallback", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText(/轮询可用，WebSocket 可兜底/)).toBeVisible();
  const response = await page.request.get("/api/v1/simulation/runs");
  expect(response.ok()).toBeTruthy();
});

test("E2E-14 views metrics and chart route", async ({ page }) => {
  const created = await page.request.post("/api/v1/simulation/runs", {
    headers: operatorHeaders,
    data: draft(),
  });
  const run = await created.json();
  await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);
  const metrics = await page.request.get(
    `/api/v1/simulation/runs/${run.run_id}/metrics`,
  );

  await page.goto("/simulation/analysis");

  expect(metrics.ok()).toBeTruthy();
  expect((await metrics.json()).metrics.length).toBeGreaterThan(0);
  await expect(page.getByText("Result Analysis")).toBeVisible();
});

test("E2E-15 exports CSV and JSON", async ({ page }) => {
  const created = await page.request.post("/api/v1/simulation/runs", {
    headers: operatorHeaders,
    data: draft(),
  });
  const run = await created.json();
  await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);
  const csv = await page.request.post("/api/v1/simulation/exports", {
    data: { export_type: "Metrics CSV", run_ids: [run.run_id] },
  });
  const manifest = await page.request.post("/api/v1/simulation/exports", {
    data: { export_type: "Manifest JSON", run_ids: [run.run_id] },
  });

  expect(csv.ok()).toBeTruthy();
  expect((await csv.json()).format).toBe("Metrics CSV");
  expect(manifest.ok()).toBeTruthy();
  expect((await manifest.json()).redacted).toBe(true);
});

test("E2E-16 reproduces from historical run", async ({ page }) => {
  const created = await page.request.post("/api/v1/simulation/runs", {
    headers: operatorHeaders,
    data: draft(),
  });
  const run = await created.json();
  const response = await page.request.post(
    `/api/v1/simulation/runs/${run.run_id}/reproduce`,
  );
  const payload = await response.json();

  expect(response.ok()).toBeTruthy();
  expect(payload.draft.scenarios).toEqual(["S01_NORMAL_STATIC"]);
  expect(payload.reproducibility_hash).toBeTruthy();
});

test("E2E-17 simulation API exposes no hardware route", async ({ page }) => {
  const capabilities = await page.request.get(
    "/api/v1/simulation/capabilities",
  );
  const payload = await capabilities.json();

  expect(payload.real_controller_contacted).toBe(false);
  expect(payload.hardware_motion_observed).toBe(false);
  expect(payload.hardware_write_operations).toEqual([]);
  expect(
    (await page.request.post("/api/v1/simulation/hardware/enable")).status(),
  ).toBe(404);
});

test("E2E-18 path traversal rejection remains enforced", async ({ page }) => {
  const response = await page.request.get(
    "/api/v1/dashboard/evidence/..%2Fsecret",
  );

  expect([400, 404]).toContain(response.status());
});

test("E2E-19 VIEWER write rejection remains enforced", async ({ page }) => {
  const response = await page.request.post("/api/v1/simulation/runs", {
    headers: { "x-dashboard-role": "VIEWER" },
    data: draft(),
  });

  expect(response.status()).toBe(403);
});

test("E2E-20 no direct ROS MoveIt controller inputs are exposed", async ({
  page,
}) => {
  await page.goto("/");

  await expect(
    page.getByText(/FollowJointTrajectory|MoveIt execute|controller enable/i),
  ).toHaveCount(0);
  expect(
    (await page.request.post("/api/v1/simulation/controller/enable")).status(),
  ).toBe(404);
});

test("E2E-21 Isaac returns BLOCKED_BY_ENV without Mock fallback", async ({
  page,
}) => {
  const response = await page.request.post("/api/v1/simulation/runs", {
    headers: operatorHeaders,
    data: draft({ backend: "ISAAC_SIM" }),
  });
  const payload = await response.json();

  expect(response.status()).toBe(202);
  expect(payload.backend).toBe("ISAAC_SIM");
  expect(payload.status).toBe("BLOCKED_BY_ENV");
  expect(payload.hardware_motion_observed).toBe(false);
});

test("E2E-22 Phase11.1 create run returns QUEUED immediately", async ({
  page,
}) => {
  const created = await createRuntimeRun(page, { runtime_delay_ms: 500 });
  const run = await created.json();

  expect(created.status()).toBe(202);
  expect(run.status).toBe("QUEUED");
  expect(run.job_id).toBeTruthy();
  expect(run.queue_position).toBeGreaterThanOrEqual(1);
});

test("E2E-23 Phase11.1 status advances to running then succeeded", async ({
  page,
}) => {
  const created = await createRuntimeRun(page, { runtime_delay_ms: 900 });
  const run = await created.json();
  const active = await waitForRunStatus(page, run.run_id, [
    "VALIDATING",
    "LEASED",
    "STARTING",
    "RUNNING",
    "SUCCEEDED",
  ]);
  const terminal = await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);

  expect([
    "VALIDATING",
    "LEASED",
    "STARTING",
    "RUNNING",
    "SUCCEEDED",
  ]).toContain(active.status);
  expect(terminal.status).toBe("SUCCEEDED");
});

test("E2E-24 Phase11.1 runtime events persist and grow", async ({ page }) => {
  const created = await createRuntimeRun(page, { runtime_delay_ms: 300 });
  const run = await created.json();
  const early = await runEvents(page, run.run_id);

  await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);
  const final = await runEvents(page, run.run_id);

  expect(early.length).toBeGreaterThanOrEqual(1);
  expect(final.length).toBeGreaterThan(early.length);
  expect(final.map((event) => event.event_type)).toContain("job_completed");
});

test("E2E-25 Phase11.1 metrics appear after worker completion", async ({
  page,
}) => {
  const created = await createRuntimeRun(page, { runtime_delay_ms: 200 });
  const run = await created.json();

  await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);
  const metrics = await runMetrics(page, run.run_id);

  expect(metrics.length).toBeGreaterThan(0);
  expect(metrics.map((metric) => metric.name)).toContain("task_success");
});

test("E2E-26 Phase11.1 cancels a running job cooperatively", async ({
  page,
}) => {
  const created = await createRuntimeRun(page, { runtime_delay_ms: 2000 });
  const run = await created.json();
  await waitForRunStatus(page, run.run_id, ["STARTING", "RUNNING"]);

  const cancel = await page.request.post(
    `/api/v1/simulation/runs/${run.run_id}/cancel`,
    { headers: operatorHeaders },
  );
  const terminal = await waitForRunStatus(page, run.run_id, ["CANCELLED"]);

  expect(cancel.ok()).toBeTruthy();
  expect(terminal.status).toBe("CANCELLED");
});

test("E2E-27 Phase11.1 records cancel progress events", async ({ page }) => {
  const created = await createRuntimeRun(page, { runtime_delay_ms: 2000 });
  const run = await created.json();
  await waitForRunStatus(page, run.run_id, ["STARTING", "RUNNING"]);
  await page.request.post(`/api/v1/simulation/runs/${run.run_id}/cancel`, {
    headers: operatorHeaders,
  });
  await waitForRunStatus(page, run.run_id, ["CANCELLED"]);

  const events = await runEvents(page, run.run_id);
  expect(events.map((event) => event.event_type)).toEqual(
    expect.arrayContaining(["cancel_requested", "job_cancelled"]),
  );
});

test("E2E-28 Phase11.1 marks constrained runs as TIMED_OUT", async ({
  page,
}) => {
  const created = await createRuntimeRun(page, {
    runtime_delay_ms: 1500,
    timeout_seconds: 1,
  });
  const run = await created.json();
  const terminal = await waitForRunStatus(page, run.run_id, ["TIMED_OUT"]);

  expect(terminal.status).toBe("TIMED_OUT");
});

test("E2E-29 Phase11.1 safe recovery keeps run history queryable", async ({
  page,
}) => {
  const created = await createRuntimeRun(page);
  const run = await created.json();
  await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);

  const recovery = await page.request.post(
    "/api/v1/simulation/runtime/recover",
    {
      headers: { "x-dashboard-role": "SAFETY_REVIEWER" },
    },
  );
  const history = await page.request.get(
    `/api/v1/simulation/runs/${run.run_id}`,
  );

  expect(recovery.ok()).toBeTruthy();
  expect(history.ok()).toBeTruthy();
  expect((await history.json()).run_id).toBe(run.run_id);
});

test("E2E-30 Phase11.1 batch progress is persisted", async ({ page }) => {
  const response = await page.request.post("/api/v1/simulation/batches", {
    headers: operatorHeaders,
    data: draft({
      seeds: [0, 1, 2],
      parameter_overrides: { runtime_delay_ms: 200 },
    }),
  });
  const batch = await response.json();
  const terminal = await waitForBatchDone(page, batch.batch_id);

  expect(response.status()).toBe(202);
  expect(terminal.progress.total).toBe(3);
  expect(terminal.progress.succeeded).toBe(3);
});

test("E2E-31 Phase11.1 retry failed run requeues safely", async ({ page }) => {
  const created = await createRuntimeRun(page, {
    runtime_delay_ms: 1500,
    timeout_seconds: 1,
  });
  const run = await created.json();
  await waitForRunStatus(page, run.run_id, ["TIMED_OUT"]);

  const retry = await page.request.post(
    `/api/v1/simulation/runs/${run.run_id}/retry`,
    { headers: operatorHeaders },
  );
  const retried = await retry.json();

  expect(retry.ok()).toBeTruthy();
  expect(retried.status).toBe("QUEUED");
});

test("E2E-32 Phase11.1 worker health and queue panels render", async ({
  page,
}) => {
  await page.goto("/simulation/live");

  await expect(page.getByText("Runtime Health")).toBeVisible();
  await expect(
    page.locator(".ant-card-head-title").filter({ hasText: /^Queue$/ }),
  ).toBeVisible();
  await expect(
    page.locator(".ant-card-head-title").filter({ hasText: /^Workers$/ }),
  ).toBeVisible();
});

test("E2E-33 Phase11.1 WebSocket replay is persisted without duplicates", async ({
  page,
}) => {
  const created = await createRuntimeRun(page);
  const run = await created.json();
  await waitForRunStatus(page, run.run_id, ["SUCCEEDED"]);

  const firstReplay = await readStreamReplay(page, 0, 3);
  const lastSequence = Math.max(...firstReplay.map((event) => event.sequence));
  const secondReplay = await readStreamReplay(page, lastSequence, 1);
  const secondSequences = secondReplay.map((event) => event.sequence);

  expect(new Set(firstReplay.map((event) => event.sequence)).size).toBe(
    firstReplay.length,
  );
  expect(secondSequences.every((sequence) => sequence > lastSequence)).toBe(
    true,
  );
});

test("E2E-M01 opens AI model control center", async ({ page }) => {
  await page.goto("/models");

  await expect(
    page.getByRole("heading", { name: "AI 模型控制中心" }),
  ).toBeVisible();
  await expect(
    page
      .locator(".ant-card-head-title")
      .filter({ hasText: /^Planner Dry-Run$/ }),
  ).toBeVisible();
  await expect(page.getByText(/hardware_execution=false/i)).toBeVisible();
  await expect(page.getByText(/execute hardware/i)).toHaveCount(0);
});

test("E2E-M02 creates and activates RuleBased profile", async ({ page }) => {
  await page.goto("/models");
  const created = await page.request.post("/api/v1/model-control/profiles", {
    data: {
      display_name: "E2E RuleBased",
      provider_kind: "RULE_BASED",
      model_name: "rule-based",
    },
  });
  const profile = await created.json();
  await page.request.post(
    `/api/v1/model-control/profiles/${profile.profile_id}/activate`,
  );
  await page.reload();
  await expect(
    page.getByRole("cell", { name: "E2E RuleBased" }).first(),
  ).toBeVisible();
  await expect(page.getByText("RULE_BASED").first()).toBeVisible();
});

test("E2E-M03 API key is write-only in model profile response", async ({
  page,
}) => {
  const created = await page.request.post("/api/v1/model-control/profiles", {
    data: {
      display_name: "E2E Cloud",
      provider_kind: "OPENAI_COMPATIBLE",
      base_url: "https://api.example.test/v1",
      chat_completions_path: "/chat/completions",
      model_name: "safe-model",
      api_key: "TEST_SECRET_VALUE_E2E",
    },
  });
  const payload = await created.json();
  const listed = await page.request.get("/api/v1/model-control/profiles");
  const listPayload = await listed.json();

  expect(created.status()).toBe(201);
  expect(payload.secret_present).toBe(true);
  expect(JSON.stringify(payload)).not.toContain("TEST_SECRET_VALUE_E2E");
  expect(JSON.stringify(listPayload)).not.toContain("TEST_SECRET_VALUE_E2E");
});

test("E2E-M04 planner dry-run never dispatches hardware", async ({ page }) => {
  const response = await page.request.post(
    "/api/v1/model-control/planner/dry-run",
    {
      data: {
        user_instruction: "pick red cube",
        sample_scene: "S01_NORMAL_STATIC",
        control_mode: "PCSC",
      },
    },
  );
  const payload = await response.json();

  expect(response.ok()).toBeTruthy();
  expect(payload.dispatch).toBe(false);
  expect(payload.hardware_execution).toBe(false);
});

async function createRuntimeRun(
  page: Page,
  parameterOverrides: Record<string, unknown> = {},
) {
  return page.request.post("/api/v1/simulation/runs", {
    headers: operatorHeaders,
    data: draft({ parameter_overrides: parameterOverrides }),
  });
}

async function waitForRunStatus(
  page: Page,
  runId: string,
  statuses: string[],
  timeoutMs = 15_000,
) {
  const deadline = Date.now() + timeoutMs;
  let last: Record<string, unknown> | undefined;
  while (Date.now() < deadline) {
    const response = await page.request.get(`/api/v1/simulation/runs/${runId}`);
    expect(response.ok()).toBeTruthy();
    last = (await response.json()) as Record<string, unknown>;
    if (statuses.includes(String(last.status))) {
      return last;
    }
    await page.waitForTimeout(100);
  }
  throw new Error(
    `Run ${runId} did not reach ${statuses.join(", ")}; last=${JSON.stringify(
      last,
    )}`,
  );
}

async function waitForBatchDone(
  page: Page,
  batchId: string,
  timeoutMs = 20_000,
) {
  const deadline = Date.now() + timeoutMs;
  let last: BatchPayload | undefined;
  while (Date.now() < deadline) {
    const response = await page.request.get(
      `/api/v1/simulation/batches/${batchId}`,
    );
    expect(response.ok()).toBeTruthy();
    last = (await response.json()) as BatchPayload;
    const progress = last.progress;
    if (
      progress.total ===
      progress.succeeded +
        progress.failed +
        progress.blocked +
        progress.cancelled +
        progress.timed_out
    ) {
      return last;
    }
    await page.waitForTimeout(100);
  }
  throw new Error(
    `Batch ${batchId} did not finish; last=${JSON.stringify(last)}`,
  );
}

async function runEvents(page: Page, runId: string) {
  const response = await page.request.get(
    `/api/v1/simulation/runs/${runId}/events`,
  );
  expect(response.ok()).toBeTruthy();
  return ((await response.json()) as { events: TimelinePayload[] }).events;
}

async function runMetrics(page: Page, runId: string) {
  const response = await page.request.get(
    `/api/v1/simulation/runs/${runId}/metrics`,
  );
  expect(response.ok()).toBeTruthy();
  return ((await response.json()) as { metrics: MetricPayload[] }).metrics;
}

async function readStreamReplay(
  page: Page,
  lastSequence: number,
  minEvents: number,
) {
  return page.evaluate(
    ({ lastSequence: replayAfter, minEvents: minimum }) =>
      new Promise<Array<{ sequence: number; event_type: string }>>(
        (resolve, reject) => {
          const events: Array<{ sequence: number; event_type: string }> = [];
          const socket = new WebSocket(
            `ws://127.0.0.1:8000/api/v1/simulation/stream?last_sequence=${replayAfter}`,
          );
          const timer = window.setTimeout(() => {
            socket.close();
            reject(new Error(`Timed out waiting for ${minimum} replay events`));
          }, 5000);
          socket.onerror = () => {
            window.clearTimeout(timer);
            reject(new Error("simulation stream websocket failed"));
          };
          socket.onmessage = (message) => {
            const payload = JSON.parse(String(message.data));
            if (payload.event_type !== "heartbeat") {
              events.push({
                sequence: Number(payload.sequence),
                event_type: String(payload.event_type),
              });
            }
            if (events.length >= minimum) {
              window.clearTimeout(timer);
              socket.close();
              resolve(events);
            }
          };
        },
      ),
    { lastSequence, minEvents },
  );
}

function draft(overrides: Record<string, unknown> = {}) {
  const base = {
    backend: "MOCK",
    run_type: "SINGLE",
    scenarios: ["S01_NORMAL_STATIC"],
    control_modes: ["PCSC"],
    seeds: [0],
    repetitions: 1,
    network_profiles: [
      {
        name: "NORMAL",
        base_latency_ms: 40,
        jitter_ms: 5,
        packet_loss: 0,
        bandwidth_kbps: 10000,
      },
    ],
    fault_profiles: [{ name: "none", parameters: {} }],
    parameter_overrides: {
      cache_policy: "CACHE_ENABLED",
      retry_budget: 2,
      supervision_period_ms: 300,
      timeout_ms: 30000,
    },
    domain_randomization: { enabled: false, level: "NONE" },
    tags: ["e2e"],
    description: "playwright",
  };
  const parameterOverrides =
    overrides.parameter_overrides &&
    typeof overrides.parameter_overrides === "object" &&
    !Array.isArray(overrides.parameter_overrides)
      ? (overrides.parameter_overrides as Record<string, unknown>)
      : {};
  const domainOverrides =
    overrides.domain_randomization &&
    typeof overrides.domain_randomization === "object" &&
    !Array.isArray(overrides.domain_randomization)
      ? (overrides.domain_randomization as Record<string, unknown>)
      : {};
  return {
    ...base,
    ...overrides,
    parameter_overrides: {
      ...base.parameter_overrides,
      ...parameterOverrides,
    },
    domain_randomization: {
      ...base.domain_randomization,
      ...domainOverrides,
    },
  };
}
