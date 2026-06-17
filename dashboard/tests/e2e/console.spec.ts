import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/dashboard/**", async (route) => {
    const url = route.request().url();
    if (url.endsWith("/summary")) {
      await route.fulfill({
        json: {
          current_project_status: "PHASE10_MOVEIT_DRY_RUN_ACCEPTED",
          real_robot_validation: "NOT_STARTED",
          highest_acceptance_level: "NONE",
          hardware_claim: "PLANNING_ONLY",
          worktree_clean: true,
          software_commit: "abc123",
          source_tree_hash: "tree123",
          services: [],
          blockers: [],
          latest_evidence: [],
          active_experiments: [],
          safety_summary: {
            hardware_motion_authorized: false,
            reason_codes: ["CONTROLLER_NOT_CONFIGURED"],
          },
        },
      });
      return;
    }
    if (url.endsWith("/capabilities")) {
      await route.fulfill({
        json: { hardware_write_operations: [], allowed_write_operations: [] },
      });
      return;
    }
    if (url.endsWith("/evidence")) {
      await route.fulfill({ json: { records: [] } });
      return;
    }
    await route.fulfill({ json: {} });
  });
});

test("E2E-01 概览展示 dry-run 已验收且不声明硬件能力", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });

  await page.goto("/");
  const main = page.getByRole("main");
  await expect(
    page.getByRole("heading", { name: "PHASE10_MOVEIT_DRY_RUN_ACCEPTED" }),
  ).toBeVisible();
  await expect(main.getByText("真实机械臂验证：NOT_STARTED")).toBeVisible();
  await expect(main.getByText("最高硬件级别：NONE")).toBeVisible();
  await expect(
    page.getByText(/直连 ROS|MoveIt execute|控制器地址/i),
  ).toHaveCount(0);
  expect(
    consoleErrors.filter((message) => /deprecated/i.test(message)),
  ).toEqual([]);
});
