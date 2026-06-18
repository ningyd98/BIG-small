import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OverviewPageView } from "./OverviewPage";

// 概览页测试固定 dry-run 权威状态，防止回归时误展示真实硬件验收通过。
describe("OverviewPageView", () => {
  it("展示权威状态和硬件边界", () => {
    render(
      <OverviewPageView
        summary={{
          current_environment: "MOVEIT_DRY_RUN",
          current_project_status: "PHASE10_MOVEIT_DRY_RUN_ACCEPTED",
          current_project_status_source: "authoritative",
          generated_at: "2026-06-17T00:00:00Z",
          real_robot_validation: "NOT_STARTED",
          highest_acceptance_level: "NONE",
          hardware_claim: "PLANNING_ONLY",
          runtime_profile: "local",
          worktree_clean: true,
          software_commit: "abc123",
          source_tree_hash: "tree123",
          services: [],
          blockers: [],
          latest_evidence: [],
          active_experiments: [],
          safety_summary: {
            allowed: false,
            controller_connected: false,
            current_acceptance_level: "NONE",
            decided_at: "2026-06-17T00:00:00Z",
            emergency_stop_state: "UNKNOWN",
            execution_mode: "DRY_RUN",
            hardware_motion_authorized: false,
            operator_confirmation_state: "NOT_REQUIRED_FOR_READINESS_VIEW",
            requested_acceleration_scale: 0,
            requested_velocity_scale: 0,
            required_acceptance_level: "LEVEL_0",
            reason_codes: ["CONTROLLER_NOT_CONFIGURED"],
            safety_shield_state: "UNKNOWN",
            telemetry_freshness: "MISSING",
          },
        }}
      />,
    );

    expect(
      screen.getByText("PHASE10_MOVEIT_DRY_RUN_ACCEPTED"),
    ).toBeInTheDocument();
    expect(screen.getByText("真实机械臂验证：NOT_STARTED")).toBeInTheDocument();
    expect(screen.getByText("最高硬件级别：NONE")).toBeInTheDocument();
    expect(screen.getByText("状态来源：authoritative")).toBeInTheDocument();
  });
});
