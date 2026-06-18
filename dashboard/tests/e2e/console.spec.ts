import { expect, test } from "@playwright/test";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

const artifactRoot = path.resolve(process.cwd(), "../artifacts/dashboard_e2e");

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
    page.getByRole("row").filter({ hasText: run.run_id }).getByText("MOCK"),
  ).toBeVisible();
  await expect(
    page
      .getByRole("row")
      .filter({ hasText: run.run_id })
      .getByText("SUCCEEDED"),
  ).toBeVisible({ timeout: 15_000 });
});

test("E2E-06 creates MuJoCo single experiment through FastAPI", async ({
  page,
}) => {
  const response = await page.request.post("/api/v1/simulation/runs", {
    headers: { "x-dashboard-role": "EXPERIMENT_OPERATOR" },
    data: draft({ backend: "MUJOCO" }),
  });
  const payload = await response.json();

  expect(response.status()).toBe(202);
  expect(payload.backend).toBe("MUJOCO");
  expect(["SUCCEEDED", "BLOCKED_BY_ENV", "FAILED"]).toContain(payload.status);
  expect(payload.hardware_motion_observed).toBe(false);
});

test("E2E-07 creates mode comparison batch", async ({ page }) => {
  const response = await page.request.post("/api/v1/simulation/batches", {
    headers: { "x-dashboard-role": "EXPERIMENT_OPERATOR" },
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
    headers: { "x-dashboard-role": "EXPERIMENT_OPERATOR" },
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
    headers: { "x-dashboard-role": "EXPERIMENT_OPERATOR" },
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
    headers: { "x-dashboard-role": "EXPERIMENT_OPERATOR" },
    data: draft({ scenarios: ["S14_EMERGENCY_STOP"] }),
  });
  const run = await created.json();
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
    headers: { "x-dashboard-role": "EXPERIMENT_OPERATOR" },
    data: draft(),
  });
  const run = await created.json();
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
    headers: { "x-dashboard-role": "EXPERIMENT_OPERATOR" },
    data: draft(),
  });
  const run = await created.json();
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
    headers: { "x-dashboard-role": "EXPERIMENT_OPERATOR" },
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
    headers: { "x-dashboard-role": "EXPERIMENT_OPERATOR" },
    data: draft({ backend: "ISAAC_SIM" }),
  });
  const payload = await response.json();

  expect(response.status()).toBe(202);
  expect(payload.backend).toBe("ISAAC_SIM");
  expect(payload.status).toBe("BLOCKED_BY_ENV");
  expect(payload.hardware_motion_observed).toBe(false);
});

function draft(overrides: Record<string, unknown> = {}) {
  return {
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
    ...overrides,
  };
}
