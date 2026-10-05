import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VisualRunEvidence } from "./VisualRunEvidence";

describe("visual evidence layers", () => {
  it("shows NOT_EXECUTED stages without a physical success badge", () => {
    render(<VisualRunEvidence result={{ evaluation_scope: "VISUAL_PLANNING",
      task_execution: "NOT_EXECUTED", task_success: false, model_calls: 1 }} />);
    expect(screen.getByText("VISUAL_PLANNING")).toBeInTheDocument();
    expect(screen.getByText("NOT_EXECUTED")).toBeInTheDocument();
    expect(screen.queryByText("物理成功")).not.toBeInTheDocument();
  });

  it("shows separate online and independent physical evidence", () => {
    render(<VisualRunEvidence result={{ evaluation_scope: "VISION_CLOSED_LOOP",
      task_execution: "EXECUTED", task_success: false,
      online_reported_complete: true, physical_success: false }} />);
    expect(screen.getByText("在线完成声明：是")).toBeInTheDocument();
    expect(screen.getByText("独立物理成功：否")).toBeInTheDocument();
    expect(screen.queryByText("物理成功")).not.toBeInTheDocument();
  });
});
