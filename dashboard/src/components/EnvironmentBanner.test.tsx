// 环境横幅测试：验证硬件边界和 dry-run 状态通过文本明确展示。
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EnvironmentBanner } from "./EnvironmentBanner";

// 测试确保安全横幅用可读文本表达硬件边界，而不是只依赖颜色或图标。
describe("EnvironmentBanner", () => {
  it("不用只靠颜色表达 dry-run 和硬件边界", () => {
    render(
      <EnvironmentBanner
        projectStatus="PHASE10_MOVEIT_DRY_RUN_ACCEPTED"
        realRobotValidation="NOT_STARTED"
        highestAcceptanceLevel="NONE"
      />,
    );

    expect(screen.getByText(/MoveIt dry-run/i)).toBeInTheDocument();
    expect(screen.getByText(/不执行硬件动作/i)).toBeInTheDocument();
    expect(
      screen.getByLabelText(/real robot validation not started/i),
    ).toBeInTheDocument();
  });
});
