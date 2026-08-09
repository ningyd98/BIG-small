// Sim2Real 实验域模型：只描述实验设计、标定值和覆盖度，不产生低层机器人控制命令。
export type Sim2RealRandomizationLevel =
  | "NONE"
  | "MILD"
  | "MODERATE"
  | "SEVERE";

export type Sim2RealAxisKey =
  | "object_mass_kg"
  | "friction_coefficient"
  | "actuator_delay_ms"
  | "camera_depth_noise_m";

export type Sim2RealAxis = {
  key: Sim2RealAxisKey;
  label: string;
  unit: string;
  nominal: number;
  min: number;
  max: number;
};

export type Sim2RealMeasurementMap = Record<Sim2RealAxisKey, number>;

export type Sim2RealGapRow = Sim2RealAxis & {
  measured: number;
  selectedMin: number;
  selectedMax: number;
  normalizedGap: number;
  covered: boolean;
};

export const SIM2REAL_RANDOMIZATION_SCALE: Record<
  Sim2RealRandomizationLevel,
  number
> = {
  NONE: 0,
  MILD: 0.25,
  MODERATE: 0.55,
  SEVERE: 1,
};

// 与 configs/phase9/domain_randomization.yaml 保持同源语义；页面明确展示配置来源，避免当成实测结果。
export const SIM2REAL_AXES: Sim2RealAxis[] = [
  {
    key: "object_mass_kg",
    label: "物体质量",
    unit: "kg",
    nominal: 0.08,
    min: 0.04,
    max: 0.28,
  },
  {
    key: "friction_coefficient",
    label: "摩擦系数",
    unit: "coefficient",
    nominal: 0.8,
    min: 0.08,
    max: 1.2,
  },
  {
    key: "actuator_delay_ms",
    label: "执行器延迟",
    unit: "ms",
    nominal: 0,
    min: 0,
    max: 120,
  },
  {
    key: "camera_depth_noise_m",
    label: "深度噪声",
    unit: "m",
    nominal: 0.002,
    min: 0,
    max: 0.035,
  },
];

export function initialSim2RealMeasurements(): Sim2RealMeasurementMap {
  return Object.fromEntries(
    SIM2REAL_AXES.map((axis) => [axis.key, axis.nominal]),
  ) as Sim2RealMeasurementMap;
}

export function randomizationBounds(
  axis: Sim2RealAxis,
  level: Sim2RealRandomizationLevel,
): [number, number] {
  const scale = SIM2REAL_RANDOMIZATION_SCALE[level];
  return [
    axis.nominal + (axis.min - axis.nominal) * scale,
    axis.nominal + (axis.max - axis.nominal) * scale,
  ];
}

export function computeSim2RealGap(
  measurements: Sim2RealMeasurementMap,
  level: Sim2RealRandomizationLevel,
): Sim2RealGapRow[] {
  return SIM2REAL_AXES.map((axis) => {
    const measured = measurements[axis.key];
    const [selectedMin, selectedMax] = randomizationBounds(axis, level);
    const scale = Math.max(
      Math.abs(axis.min - axis.nominal),
      Math.abs(axis.max - axis.nominal),
      Number.EPSILON,
    );
    return {
      ...axis,
      measured,
      selectedMin,
      selectedMax,
      normalizedGap: Math.abs(measured - axis.nominal) / scale,
      covered: measured >= selectedMin && measured <= selectedMax,
    };
  });
}

export function buildSeedSequence(count: number): number[] {
  const safeCount = Math.max(1, Math.min(20, Math.floor(count)));
  return Array.from({ length: safeCount }, (_, index) => index);
}

export function buildSim2RealPlan(input: {
  scenario: string;
  controlMode: "PCSC" | "ETEAC" | "AUTO";
  level: Sim2RealRandomizationLevel;
  seedCount: number;
  repetitions: number;
  measurements: Sim2RealMeasurementMap;
}) {
  const gaps = computeSim2RealGap(input.measurements, input.level);
  const seeds = buildSeedSequence(input.seedCount);
  return {
    schema_version: "sim2real.workbench.v1",
    source_randomization_config: "configs/phase9/domain_randomization.yaml",
    stage: "SIMULATION_ROBUSTNESS_BEFORE_REAL_PROMOTION",
    scenario: input.scenario,
    control_mode: input.controlMode,
    randomization_level: input.level,
    seeds,
    repetitions: input.repetitions,
    planned_run_count: seeds.length * input.repetitions,
    real_measurements: input.measurements,
    coverage: gaps.map((gap) => ({
      parameter: gap.key,
      measured: gap.measured,
      selected_min: gap.selectedMin,
      selected_max: gap.selectedMax,
      covered: gap.covered,
      normalized_gap: gap.normalizedGap,
    })),
    safety_boundary: {
      real_controller_contacted: false,
      hardware_motion_observed: false,
      hardware_write_operations: [],
      real_motion_dispatch_enabled: false,
    },
  };
}
