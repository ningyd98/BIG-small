import { describe, expect, it } from "vitest";

import {
  buildSeedSequence,
  buildSim2RealPlan,
  computeSim2RealGap,
  initialSim2RealMeasurements,
  initialSim2RealParameters,
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
    expect(rows).toHaveLength(SIM2REAL_AXES.length);
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

  it("supports an independent absolute range per parameter", () => {
    const parameters = initialSim2RealParameters();
    parameters.object_mass_kg = {
      ...parameters.object_mass_kg,
      range_mode: "ABSOLUTE",
      min: 0.15,
      nominal: 0.2,
      max: 0.25,
    };
    const measurements = initialSim2RealMeasurements();
    measurements.object_mass_kg = 0.16;

    const rows = computeSim2RealGap(measurements, "MILD", parameters);
    const mass = rows.find((row) => row.key === "object_mass_kg");
    expect(mass?.selectedMin).toBe(0.15);
    expect(mass?.selectedMax).toBe(0.25);
    expect(mass?.covered).toBe(true);
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
    expect(plan.schema_version).toBe("sim2real.workbench.v2");
    expect(plan.paired_backend_contract.mujoco_adapter).toBe("MjSpec");
    expect(plan.safety_boundary.real_controller_contacted).toBe(false);
    expect(plan.safety_boundary.hardware_motion_observed).toBe(false);
    expect(plan.safety_boundary.hardware_write_operations).toEqual([]);
    expect(plan.safety_boundary.real_motion_dispatch_enabled).toBe(false);
  });
});
