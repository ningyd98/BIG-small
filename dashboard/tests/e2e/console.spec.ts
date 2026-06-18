import { expect, test } from "@playwright/test";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

const artifactRoot = path.resolve(process.cwd(), "../artifacts/dashboard_e2e");

function seedArtifacts() {
  rmSync(artifactRoot, { recursive: true, force: true });
  mkdirSync(path.join(artifactRoot, "phase10"), { recursive: true });
  mkdirSync(path.join(artifactRoot, "baselines/phase8_2/full"), {
    recursive: true,
  });
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
  writeFileSync(
    path.join(artifactRoot, "phase10/mujoco_smoke.json"),
    JSON.stringify(
      {
        status: "SUCCEEDED",
        hardware_claim: "SIMULATION_ONLY",
        planner_backend: "MUJOCO",
        sent_to_hardware: false,
        hardware_motion_observed: false,
        provenance: {
          generated_from_commit: "mujoco-commit",
          source_tree_hash: "mujoco-tree",
          worktree_clean: true,
          generated_at: "2026-06-17T00:00:00Z",
        },
      },
      null,
      2,
    ) + "\n",
    "utf-8",
  );
  writeFileSync(
    path.join(artifactRoot, "phase10/synthetic_dry_run.json"),
    JSON.stringify(
      {
        status: "SUCCEEDED",
        hardware_claim: "PLANNING_ONLY",
        planner_backend: "SYNTHETIC",
        sent_to_hardware: false,
        hardware_motion_observed: false,
        provenance: {
          generated_from_commit: "synthetic-commit",
          source_tree_hash: "synthetic-tree",
          worktree_clean: true,
          generated_at: "2026-06-17T00:00:00Z",
        },
      },
      null,
      2,
    ) + "\n",
    "utf-8",
  );
  writeFileSync(
    path.join(artifactRoot, "phase10/moveit_blocked.json"),
    JSON.stringify(
      {
        status: "BLOCKED_BY_ENV",
        hardware_claim: "PLANNING_ONLY",
        planner_backend: "MOVEIT_RUNTIME",
        sent_to_hardware: false,
        hardware_motion_observed: false,
        blockers: ["MoveIt runtime unavailable"],
        provenance: {
          generated_from_commit: "blocked-commit",
          source_tree_hash: "blocked-tree",
          worktree_clean: true,
          generated_at: "2026-06-17T00:00:00Z",
        },
      },
      null,
      2,
    ) + "\n",
    "utf-8",
  );
  writeFileSync(
    path.join(artifactRoot, "baselines/phase8_2/full/summary.json"),
    JSON.stringify(
      {
        by_mode: {
          PCSC: { success_rate: 0.81, cloud_invocation_count: 7 },
          ETEAC: { success_rate: 0.86, retry_count: 2 },
          AUTO: { success_rate: 0.91, mode_switch_count: 1 },
        },
      },
      null,
      2,
    ) + "\n",
    "utf-8",
  );
}

test.beforeAll(seedArtifacts);

test("E2E-01 overview shows dry-run acceptance without hardware validation", async ({
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
    page.getByRole("main").getByText("最高硬件级别：NONE"),
  ).toBeVisible();
  await expect(
    page.getByText(/直连 ROS|MoveIt execute|控制器地址/i),
  ).toHaveCount(0);
});

test("E2E-02 capabilities API exposes no hardware write operations", async ({
  page,
}) => {
  const response = await page.request.get("/api/v1/dashboard/capabilities");
  const payload = await response.json();

  expect(response.ok()).toBeTruthy();
  expect(payload.hardware_write_operations).toEqual([]);
  expect(payload.allowed_write_operations).toContain(
    "start_software_experiment",
  );
});

test("E2E-03 Mock experiment state flow reaches a terminal status", async ({
  page,
}) => {
  await page.goto("/simulation");
  await page.getByRole("button", { name: "启动安全软件实验" }).click();

  await expect(page.getByText(/exp-/)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/MOCK_SOFTWARE/)).toBeVisible();
  await expect(page.getByText(/SUCCEEDED|FAILED/)).toBeVisible({
    timeout: 15_000,
  });
});

test("E2E-04 Synthetic dry-run evidence stays planning-only", async ({
  page,
}) => {
  const response = await page.request.get("/api/v1/dashboard/evidence");
  const payload = await response.json();
  const synthetic = payload.records.find((record: { backend: string }) => {
    return record.backend === "SYNTHETIC";
  });
  const mujoco = payload.records.find((record: { backend: string }) => {
    return record.backend === "MUJOCO";
  });

  expect(synthetic?.hardware_claim).toBe("PLANNING_ONLY");
  expect(mujoco?.hardware_claim).toBe("SIMULATION_ONLY");
  if (!synthetic?.evidence_id || !mujoco?.evidence_id) {
    throw new Error("missing synthetic or MuJoCo evidence");
  }
  const syntheticDetail = await page.request.get(
    `/api/v1/dashboard/evidence/${synthetic.evidence_id}`,
  );
  const mujocoDetail = await page.request.get(
    `/api/v1/dashboard/evidence/${mujoco.evidence_id}`,
  );
  const syntheticPayload = await syntheticDetail.json();
  const mujocoPayload = await mujocoDetail.json();

  expect(syntheticPayload.content.sent_to_hardware).toBe(false);
  expect(syntheticPayload.content.hardware_motion_observed).toBe(false);
  expect(mujocoPayload.content.sent_to_hardware).toBe(false);
  expect(mujocoPayload.content.hardware_motion_observed).toBe(false);
});

test("E2E-05 BLOCKED_BY_ENV evidence remains non-hardware", async ({
  page,
}) => {
  const response = await page.request.get(
    "/api/v1/dashboard/evidence?status=BLOCKED_BY_ENV",
  );
  const payload = await response.json();
  const blocked = payload.records.find((record: { status: string }) => {
    return record.status === "BLOCKED_BY_ENV";
  });

  expect(blocked?.hardware_claim).toBe("PLANNING_ONLY");
  if (!blocked?.evidence_id) throw new Error("missing blocked evidence");
  const detailResponse = await page.request.get(
    `/api/v1/dashboard/evidence/${blocked.evidence_id}`,
  );
  const detail = await detailResponse.json();
  expect(detail.content.sent_to_hardware).toBe(false);
  expect(detail.content.hardware_motion_observed).toBe(false);
});

test("E2E-06 path traversal rejection stays blocked", async ({ page }) => {
  const response = await page.request.get(
    "/api/v1/dashboard/evidence/..%2Fsecret",
  );
  expect(response.status()).toBeGreaterThanOrEqual(400);
});

test("E2E-07 real hardware action locked", async ({ page }) => {
  await page.goto("/safety-acceptance");

  await expect(page.getByText("硬件运动：禁止")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "提交复核备注" }),
  ).toBeVisible();
});

test("E2E-08 WebSocket fallback polling keeps the console live", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByText(/轮询可用，WebSocket 可兜底/)).toBeVisible();
});

test("E2E-09 VIEWER write rejection", async ({ page }) => {
  const response = await page.request.post("/api/v1/dashboard/experiments", {
    headers: { "x-dashboard-role": "VIEWER" },
    data: {
      kind: "MOCK_SOFTWARE",
      scenario_id: "S01_NORMAL_STATIC",
      seed: 0,
      control_mode: "PCSC",
      repetitions: 1,
    },
  });

  expect(response.status()).toBe(403);
});

test("E2E-10 no direct ROS MoveIt controller inputs are exposed", async ({
  page,
}) => {
  await page.goto("/task-execution");

  for (const label of [
    /ROS topic/i,
    /MoveIt execute/i,
    /controller address/i,
  ]) {
    await expect(page.getByLabel(label)).toHaveCount(0);
  }
});
