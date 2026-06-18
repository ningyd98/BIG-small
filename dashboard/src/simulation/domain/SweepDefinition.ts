// Sweep 定义类型，描述多 seed、多场景和网络参数扫描。
import type { SimulationBackend } from "./SimulationBackend";

export type SweepCombination = {
  scenario: string;
  control_mode: "PCSC" | "ETEAC" | "AUTO";
  seed: number;
  latency_ms: number;
  backend: SimulationBackend;
};

export type SweepDefinition = {
  totalRuns: number;
  combinations: SweepCombination[];
  invalidCombinations: string[];
  duplicateCount: number;
  maxConcurrency: number;
};
