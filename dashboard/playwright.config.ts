// Playwright E2E 配置，固定本地 Dashboard 服务和报告输出。
import { defineConfig, devices } from "@playwright/test";

import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import path from "node:path";

// 每次 Playwright 运行使用独立目录；worker 继承同一运行目录，不移动活跃证据。
const artifactRoot = path.resolve(
  process.env.BIGSMALL_E2E_ARTIFACT_ROOT ||
    path.resolve(
      process.cwd(),
      "../artifacts/deployment/e2e-runs",
      randomUUID(),
    ),
);
process.env.BIGSMALL_E2E_ARTIFACT_ROOT = artifactRoot;
const summaryPath = path.join(artifactRoot, "phase10/dashboard_summary.json");
if (!existsSync(summaryPath)) {
  mkdirSync(path.dirname(summaryPath), { recursive: true });
  writeFileSync(
    summaryPath,
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

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 45_000,
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command:
        "cd .. && PYTHONPATH=src DASHBOARD_EXPERIMENT_WRITES_ENABLED=true DASHBOARD_AUTH_MODE=LOCAL_ONLY python -m uvicorn cloud_edge_robot_arm.cloud.api.dev_dashboard_app:app --host 127.0.0.1 --port 8000 --log-level warning",
      env: {
        ...process.env,
        ISAAC_SIM_ROOT: "",
        ISAAC_RUNTIME_MODE: "disabled",
        ISAAC_SIM_BACKEND_CMD: "",
        SIMULATION_RUNTIME_DB: "",
        DASHBOARD_ARTIFACT_ROOT: artifactRoot,
        MODEL_CONTROL_DB: path.join(artifactRoot, "model_control.db"),
      },
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "npm run dev -- --host 127.0.0.1",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
