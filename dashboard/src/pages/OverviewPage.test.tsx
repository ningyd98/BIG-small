import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OverviewPageView } from "./OverviewPage";

describe("OverviewPageView", () => {
  it("展示权威状态和硬件边界", () => {
    render(
      <OverviewPageView
        summary={{
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
        }}
      />,
    );

    expect(
      screen.getByText("PHASE10_MOVEIT_DRY_RUN_ACCEPTED"),
    ).toBeInTheDocument();
    expect(screen.getByText("真实机械臂验证：NOT_STARTED")).toBeInTheDocument();
    expect(screen.getByText("最高硬件级别：NONE")).toBeInTheDocument();
  });
});
