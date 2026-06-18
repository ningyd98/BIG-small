// 运行指标类型，要求每个指标带单位、来源、后端、场景和 seed。
import type { components } from "../../api/generated/schema";

export type SimulationMetric = components["schemas"]["SimulationMetric"];

export type MetricSummary = {
  units: Record<string, string>;
  sampleCounts: Record<string, number>;
  blockedByEnv: boolean;
};
