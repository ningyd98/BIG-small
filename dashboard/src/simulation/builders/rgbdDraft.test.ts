import { describe, expect, it } from "vitest";

import { BatchPlanBuilder } from "./BatchPlanBuilder";
import { ExperimentConfigBuilder } from "./ExperimentConfigBuilder";

describe("execution scopes", () => {
  it("defaults to a visual planning simulation and permits explicit closed loop", () => {
    const planning = ExperimentConfigBuilder.create().build();
    expect(planning.job_type).toBe("SIMULATION");
    expect(planning.execution_scope).toBe("VISUAL_PLANNING");
    expect(ExperimentConfigBuilder.create().executionScope("VISION_CLOSED_LOOP").build()
      .execution_scope).toBe("VISION_CLOSED_LOOP");
  });

  it("keeps Mock mode comparison explicitly on the legacy path", () => {
    const batch = BatchPlanBuilder.modeComparison({ backend: "MOCK", scenario: "S01_NORMAL_STATIC",
      seed: 0 });
    expect(batch.input_mode).toBe("LEGACY_PIPELINE");
    expect(batch.job_type).toBe("SIMULATION");
  });
});
