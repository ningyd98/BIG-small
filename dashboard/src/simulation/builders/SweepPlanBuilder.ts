import type { SweepDefinition } from "../domain/SweepDefinition";
import type { SimulationBackend } from "../domain/SimulationBackend";

type SweepOptions = {
  maxRuns: number;
  backend?: SimulationBackend;
  maxConcurrency?: number;
};

export class SweepPlanBuilder {
  private scenarioIds = ["S01_NORMAL_STATIC"];
  private modeValues: Array<"PCSC" | "ETEAC" | "AUTO"> = ["PCSC"];
  private seedValues = [0];
  private latencyValues = [40];
  private backendValue: SimulationBackend;
  private maxRuns: number;
  private maxConcurrency: number;

  private constructor(options: SweepOptions) {
    this.maxRuns = options.maxRuns;
    this.backendValue = options.backend ?? "MOCK";
    this.maxConcurrency = options.maxConcurrency ?? 1;
  }

  static create(options: SweepOptions): SweepPlanBuilder {
    return new SweepPlanBuilder(options);
  }

  scenarios(scenarios: string[]): SweepPlanBuilder {
    this.scenarioIds = [...scenarios];
    return this;
  }

  modes(modes: Array<"PCSC" | "ETEAC" | "AUTO">): SweepPlanBuilder {
    this.modeValues = [...modes];
    return this;
  }

  seeds(seeds: number[]): SweepPlanBuilder {
    this.seedValues = [...seeds];
    return this;
  }

  latencies(latencies: number[]): SweepPlanBuilder {
    this.latencyValues = [...latencies];
    return this;
  }

  build(): SweepDefinition {
    const combinations = this.scenarioIds.flatMap((scenario) =>
      this.modeValues.flatMap((control_mode) =>
        this.seedValues.flatMap((seed) =>
          this.latencyValues.map((latency_ms) => ({
            scenario,
            control_mode,
            seed,
            latency_ms,
            backend: this.backendValue,
          })),
        ),
      ),
    );
    if (combinations.length > this.maxRuns) {
      throw new Error(
        `sweep run count ${combinations.length} exceeds ${this.maxRuns}`,
      );
    }
    const signatures = combinations.map((item) => JSON.stringify(item));
    return {
      totalRuns: combinations.length,
      combinations,
      invalidCombinations: combinations
        .filter((item) => item.seed < 0 || item.latency_ms < 0)
        .map((item) => JSON.stringify(item)),
      duplicateCount: signatures.length - new Set(signatures).size,
      maxConcurrency: this.maxConcurrency,
    };
  }
}
