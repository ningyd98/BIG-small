import { describe, expect, it } from "vitest";

import {
  buildSeedSequence,
  buildSim2RealPlan,
  computeSim2RealGap,
  initialSim2RealMeasurements,
  randomizationBounds,
  SIM2REAL_AXES,
} from "./domain/sim2real";

describe("sim2real experiment design helpers", () => {
  it("reproduces the configured moderate randomization envelope", () => {
    const mass = SIM2REAL_AXES.find((axis) => axis.key === "object_mass_kg");
    expect(mass).toBeDefined();
    const [lower, upper] = randomizationBounds(mass!, "MODERATE");
    expect(lower).toBeCloseTo(0.058, 6);
    expect(upper).toBeCloseTo(0.19, 6);
  });

  it("marks nominal calibration values as covered", () => {
    const rows = computeSim2RealGap(initialSim2RealMeasurements(), "MILD");
    expect(rows).toHaveLength(4);
    expect(rows.every((row) => row.covered)).toBe(true);
    expect(rows.every((row) => row.normalizedGap === 0)).toBe(true);
  });

  it("detects a calibration value outside the selected envelope", () => {
    const measurements = initialSim2RealMeasurements();
    measurements.actuator_delay_ms = 90;
    const rows = computeSim2RealGap(measurements, "MILD");
    const actuator = rows.find((row) => row.key === "actuator_delay_ms");
    expect(actuator?.covered).toBe(false);
  });

  it("bounds generated seed count", () => {
    expect(buildSeedSequence(0)).toEqual([0]);
    expect(buildSeedSequence(3)).toEqual([0, 1, 2]);
    expect(buildSeedSequence(99)).toHaveLength(20);
  });

  it("builds a simulation-only plan with explicit hardware boundary", () => {
    const plan = buildSim2RealPlan({
      scenario: "S01_NORMAL_STATIC",
      controlMode: "AUTO",
      level: "SEVERE",
      seedCount: 3,
      repetitions: 2,
      measurements: initialSim2RealMeasurements(),
    });
    expect(plan.planned_run_count).toBe(6);
    expect(plan.safety_boundary.real_controller_contacted).toBe(false);
    expect(plan.safety_boundary.hardware_motion_observed).toBe(false);
    expect(plan.safety_boundary.hardware_write_operations).toEqual([]);
    expect(plan.safety_boundary.real_motion_dispatch_enabled).toBe(false);
  });
});
