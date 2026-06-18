import type { SimulationBackend } from "./SimulationBackend";
import type { SimulationMetric } from "./RunMetric";

export type ComparisonDataset = {
  metrics: SimulationMetric[];
};

export type ComparisonStats = {
  mean: number;
  median: number;
  min: number;
  max: number;
  standard_deviation: number;
  success_rate: number;
  failure_rate: number;
  percentile: { p95: number };
  paired_delta: number;
  relative_delta: number;
};

export type PairedBackendRun = {
  backend: SimulationBackend;
  scenario: string;
  seed: number;
  paired_key: string;
};
