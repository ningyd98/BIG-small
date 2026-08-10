// Sim2Real experiment model. It never contains low-level robot control commands.
export type Sim2RealRandomizationLevel =
  | "NONE"
  | "MILD"
  | "MODERATE"
  | "SEVERE";

export type Sim2RealDistribution = "UNIFORM" | "NORMAL" | "FIXED";
export type Sim2RealRangeMode = "LEVEL_SCALED" | "ABSOLUTE";

export type Sim2RealAxisKey =
  | "object_mass_kg"
  | "friction_coefficient"
  | "actuator_delay_ms"
  | "camera_depth_noise_m"
  | "joint_damping_scale"
  | "actuator_gain_scale"
  | "gravity_z_m_s2";

export type Sim2RealAxis = {
  key: Sim2RealAxisKey;
  label: string;
  unit: string;
  nominal: number;
  min: number;
  max: number;
  mujocoAdapter: string;
  isaacLabAdapter: string;
};

export type Sim2RealParameterConfig = {
  enabled: boolean;
  distribution: Sim2RealDistribution;
  range_mode: Sim2RealRangeMode;
  nominal: number;
  min: number;
  max: number;
  mean?: number | null;
  std?: number | null;
};

export type Sim2RealParameterMap = Record<
  Sim2RealAxisKey,
  Sim2RealParameterConfig
>;
export type Sim2RealMeasurementMap = Record<Sim2RealAxisKey, number>;

export type Sim2RealGapRow = Sim2RealAxis & {
  measured: number;
  selectedMin: number;
  selectedMax: number;
  normalizedGap: number;
  covered: boolean;
  enabled: boolean;
  distribution: Sim2RealDistribution;
  rangeMode: Sim2RealRangeMode;
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

export const SIM2REAL_AXES: Sim2RealAxis[] = [
  {
    key: "object_mass_kg",
    label: "物体质量",
    unit: "kg",
    nominal: 0.08,
    min: 0.04,
    max: 0.28,
    mujocoAdapter: "MjSpec geom.mass",
    isaacLabAdapter: "randomize_rigid_body_mass",
  },
  {
    key: "friction_coefficient",
    label: "摩擦系数",
    unit: "coefficient",
    nominal: 0.8,
    min: 0.08,
    max: 1.2,
    mujocoAdapter: "MjSpec geom.friction[0]",
    isaacLabAdapter: "randomize_rigid_body_material",
  },
  {
    key: "actuator_delay_ms",
    label: "执行器延迟",
    unit: "ms",
    nominal: 0,
    min: 0,
    max: 120,
    mujocoAdapter: "deterministic control queue",
    isaacLabAdapter: "DelayedPDActuator",
  },
  {
    key: "camera_depth_noise_m",
    label: "深度噪声",
    unit: "m",
    nominal: 0.002,
    min: 0,
    max: 0.035,
    mujocoAdapter: "sensor noise std",
    isaacLabAdapter: "observation noise model",
  },
  {
    key: "joint_damping_scale",
    label: "关节阻尼比例",
    unit: "scale",
    nominal: 1,
    min: 0.6,
    max: 1.6,
    mujocoAdapter: "MjSpec joint.damping",
    isaacLabAdapter: "randomize_actuator_gains",
  },
  {
    key: "actuator_gain_scale",
    label: "执行器增益比例",
    unit: "scale",
    nominal: 1,
    min: 0.7,
    max: 1.4,
    mujocoAdapter: "MjSpec gainprm/biasprm",
    isaacLabAdapter: "randomize_actuator_gains",
  },
  {
    key: "gravity_z_m_s2",
    label: "重力 Z 分量",
    unit: "m/s²",
    nominal: -9.81,
    min: -10.1,
    max: -9.5,
    mujocoAdapter: "MjSpec option.gravity[2]",
    isaacLabAdapter: "randomize_physics_scene_gravity",
  },
];

export function initialSim2RealMeasurements(): Sim2RealMeasurementMap {
  return Object.fromEntries(
    SIM2REAL_AXES.map((axis) => [axis.key, axis.nominal]),
  ) as Sim2RealMeasurementMap;
}

export function initialSim2RealParameters(): Sim2RealParameterMap {
  return Object.fromEntries(
    SIM2REAL_AXES.map((axis) => [
      axis.key,
      {
        enabled: true,
        distribution: "UNIFORM",
        range_mode: "LEVEL_SCALED",
        nominal: axis.nominal,
        min: axis.min,
        max: axis.max,
      },
    ]),
  ) as Sim2RealParameterMap;
}

export function randomizationBounds(
  axis: Sim2RealAxis,
  level: Sim2RealRandomizationLevel,
  config?: Sim2RealParameterConfig,
): [number, number] {
  const source = config ?? {
    enabled: true,
    distribution: "UNIFORM" as const,
    range_mode: "LEVEL_SCALED" as const,
    nominal: axis.nominal,
    min: axis.min,
    max: axis.max,
  };
  if (!source.enabled || source.distribution === "FIXED") {
    return [source.nominal, source.nominal];
  }
  if (source.range_mode === "ABSOLUTE") return [source.min, source.max];
  const scale = SIM2REAL_RANDOMIZATION_SCALE[level];
  return [
    source.nominal + (source.min - source.nominal) * scale,
    source.nominal + (source.max - source.nominal) * scale,
  ];
}

export function computeSim2RealGap(
  measurements: Sim2RealMeasurementMap,
  level: Sim2RealRandomizationLevel,
  parameters: Sim2RealParameterMap = initialSim2RealParameters(),
): Sim2RealGapRow[] {
  return SIM2REAL_AXES.map((axis) => {
    const config = parameters[axis.key];
    const measured = measurements[axis.key];
    const [selectedMin, selectedMax] = randomizationBounds(axis, level, config);
    const scale = Math.max(
      Math.abs(config.min - config.nominal),
      Math.abs(config.max - config.nominal),
      Number.EPSILON,
    );
    return {
      ...axis,
      measured,
      selectedMin,
      selectedMax,
      normalizedGap: Math.abs(measured - config.nominal) / scale,
      covered:
        !config.enabled || (measured >= selectedMin && measured <= selectedMax),
      enabled: config.enabled,
      distribution: config.distribution,
      rangeMode: config.range_mode,
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
  parameters?: Sim2RealParameterMap;
}) {
  const parameters = input.parameters ?? initialSim2RealParameters();
  const gaps = computeSim2RealGap(input.measurements, input.level, parameters);
  const seeds = buildSeedSequence(input.seedCount);
  return {
    schema_version: "sim2real.workbench.v2",
    source_randomization_config: "configs/phase9/domain_randomization.yaml",
    stage: "SIMULATION_ROBUSTNESS_BEFORE_REAL_PROMOTION",
    scenario: input.scenario,
    control_mode: input.controlMode,
    randomization_level: input.level,
    parameter_randomization: parameters,
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
    paired_backend_contract: {
      shared_sample: true,
      mujoco_adapter: "MjSpec",
      isaac_adapter: "Isaac Lab EventManager",
    },
    observability: {
      timeline: "elapsed_s",
      viewer: "Rerun",
      gap_report_schema: "sim2real.gap-report.v1",
    },
    safety_boundary: {
      real_controller_contacted: false,
      hardware_motion_observed: false,
      hardware_write_operations: [],
      real_motion_dispatch_enabled: false,
    },
  };
}
