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

test("E2E-03 simulation lab starts an allowlisted software experiment", async ({
  page,
}) => {
  await page.goto("/simulation");
  await page.getByRole("button", { name: "启动安全软件实验" }).click();

  await expect(page.getByText(/exp-/)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/MOCK_SOFTWARE/)).toBeVisible();
  await expect(page.getByText(/SIMULATION_ONLY/)).toBeVisible({
    timeout: 15_000,
  });
});

test("E2E-04 task execution remains read-only", async ({ page }) => {
  await page.goto("/task-execution");

  await expect(page.getByRole("main").getByText("任务执行")).toBeVisible();
  await expect(page.getByText(/HardwareExecutionGate/)).toBeVisible();
  await expect(
    page.getByText(/MoveIt execute|ros2_control|真实控制器写入/i),
  ).toHaveCount(0);
});

test("E2E-05 safety acceptance blocks hardware motion and records reviewer note", async ({
  page,
}) => {
  await page.goto("/safety-acceptance");

  await expect(page.getByText("当前级别：NONE")).toBeVisible();
  await expect(page.getByText("硬件运动：禁止")).toBeVisible();
  await page.getByLabel("安全复核备注").fill("E2E reviewer note");
  await page.getByRole("button", { name: "提交复核备注" }).click();
  await expect(page.getByText("硬件运动授权：false")).toBeVisible();
});

test("E2E-06 evidence explorer opens seeded evidence detail", async ({
  page,
}) => {
  await page.goto("/evidence");

  await expect(page.getByText("phase10/dashboard_summary.json")).toBeVisible();
  await page.getByRole("button", { name: "详情" }).first().click();
  await expect(
    page.getByText("e2e-commit", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("PHASE10_MOVEIT_DRY_RUN_ACCEPTED").first(),
  ).toBeVisible();
});

test("E2E-07 evidence download is scoped to the dashboard API", async ({
  page,
}) => {
  await page.goto("/evidence");

  const downloadLink = page.getByRole("link", { name: "下载" }).first();
  const href = await downloadLink.getAttribute("href");

  expect(href).toMatch(/^\/api\/v1\/dashboard\/evidence\/[^/]+\/download$/);
});

test("E2E-08 comparison page reads Phase 8 baseline metrics from artifacts", async ({
  page,
}) => {
  await page.goto("/comparison");

  await expect(page.getByText("success_rate")).toBeVisible();
  await expect(page.getByText("0.8100")).toBeVisible();
  await expect(page.getByText("0.9100")).toBeVisible();
});

test("E2E-09 audit page shows safety review audit events", async ({ page }) => {
  await page.request.post("/api/v1/dashboard/safety/review-notes", {
    headers: { "x-dashboard-role": "SAFETY_REVIEWER" },
    data: { note: "Audit e2e note", related_evidence_id: "" },
  });

  await page.goto("/audit");
  await expect(
    page.getByRole("cell", { name: "safety_review_note" }).first(),
  ).toBeVisible();
});

test("E2E-10 websocket stream connects through the dashboard API path without token query", async ({
  page,
}) => {
  await page.goto("/");

  const event = await page.evaluate(() => {
    return new Promise<{ eventType: string; url: string }>(
      (resolve, reject) => {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const ws = new WebSocket(
          `${protocol}//${window.location.host}/api/v1/dashboard/stream`,
        );
        const timer = window.setTimeout(() => {
          ws.close();
          reject(new Error("websocket timeout"));
        }, 5000);
        ws.onmessage = (message) => {
          window.clearTimeout(timer);
          const payload = JSON.parse(String(message.data)) as {
            event_type: string;
          };
          resolve({ eventType: payload.event_type, url: ws.url });
          ws.close();
        };
        ws.onerror = () => {
          window.clearTimeout(timer);
          reject(new Error("websocket error"));
        };
      },
    );
  });

  expect(event.eventType).toMatch(/heartbeat|summary|experiment|audit/);
  expect(event.url).toContain("/api/v1/dashboard/stream");
  expect(event.url).not.toContain("token=");
});
