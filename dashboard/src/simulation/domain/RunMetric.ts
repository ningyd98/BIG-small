import type { components } from "../../api/generated/schema";

export type SimulationMetric = components["schemas"]["SimulationMetric"];

export type MetricSummary = {
  units: Record<string, string>;
  sampleCounts: Record<string, number>;
  blockedByEnv: boolean;
};
