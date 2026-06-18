import type { ExperimentDraft, NetworkDraft } from "../domain/ExperimentDraft";
import type { SimulationBackend } from "../domain/SimulationBackend";

const forbiddenKeys = new Set([
  "shell",
  "command",
  "cmd",
  "script",
  "path",
  "module",
  "environment",
  "env",
  "executable",
  "runner",
  "runner_name",
  "pythonpath",
]);

const defaultDraft: ExperimentDraft = {
  backend: "MOCK",
  run_type: "SINGLE",
  scenarios: ["S01_NORMAL_STATIC"],
  control_modes: ["PCSC"],
  seeds: [0],
  repetitions: 1,
  network_profiles: [
    {
      name: "NORMAL",
      base_latency_ms: 40,
      jitter_ms: 5,
      packet_loss: 0,
      bandwidth_kbps: 10000,
    },
  ],
  fault_profiles: [{ name: "none", parameters: {} }],
  parameter_overrides: {
    cache_policy: "CACHE_ENABLED",
    retry_budget: 2,
    supervision_period_ms: 300,
    timeout_ms: 30000,
  },
  domain_randomization: { enabled: false, level: "NONE" },
  tags: [],
  description: "",
};

const defaultNetworkProfile: NetworkDraft = {
  name: "NORMAL",
  base_latency_ms: 40,
  jitter_ms: 5,
  packet_loss: 0,
  bandwidth_kbps: 10000,
};

export class ExperimentConfigBuilder {
  private constructor(private readonly draft: ExperimentDraft) {}

  static create(): ExperimentConfigBuilder {
    return new ExperimentConfigBuilder(structuredClone(defaultDraft));
  }

  backend(backend: SimulationBackend): ExperimentConfigBuilder {
    return this.next({ backend });
  }

  scenario(scenario: string): ExperimentConfigBuilder {
    return this.next({ scenarios: [scenario] });
  }

  scenarios(scenarios: string[]): ExperimentConfigBuilder {
    return this.next({ scenarios: [...scenarios] });
  }

  controlMode(mode: "PCSC" | "ETEAC" | "AUTO"): ExperimentConfigBuilder {
    return this.next({ control_modes: [mode] });
  }

  controlModes(
    modes: Array<"PCSC" | "ETEAC" | "AUTO">,
  ): ExperimentConfigBuilder {
    return this.next({ control_modes: [...modes] });
  }

  seed(seed: number): ExperimentConfigBuilder {
    return this.next({ seeds: [seed] });
  }

  seeds(seeds: number[]): ExperimentConfigBuilder {
    return this.next({ seeds: [...seeds] });
  }

  repetitions(repetitions: number): ExperimentConfigBuilder {
    return this.next({ repetitions });
  }

  network(profile: Partial<NetworkDraft>): ExperimentConfigBuilder {
    const [current = defaultNetworkProfile] = this.draft.network_profiles ?? [];
    return this.next({
      network_profiles: [{ ...current, ...profile }],
    });
  }

  parameterOverride(
    key: string,
    value: string | number | boolean,
  ): ExperimentConfigBuilder {
    return this.next({
      parameter_overrides: { ...this.draft.parameter_overrides, [key]: value },
    });
  }

  domainRandomization(
    enabled: boolean,
    level = "NONE",
  ): ExperimentConfigBuilder {
    return this.next({ domain_randomization: { enabled, level } });
  }

  runType(runType: ExperimentDraft["run_type"]): ExperimentConfigBuilder {
    return this.next({ run_type: runType });
  }

  build(): ExperimentDraft {
    this.validate();
    return structuredClone(this.draft);
  }

  private next(update: Partial<ExperimentDraft>): ExperimentConfigBuilder {
    return new ExperimentConfigBuilder({
      ...structuredClone(this.draft),
      ...structuredClone(update),
    });
  }

  private validate(): void {
    if (this.draft.scenarios.length === 0) {
      throw new Error("at least one scenario is required");
    }
    if (this.draft.control_modes.length === 0) {
      throw new Error("at least one control mode is required");
    }
    if (this.draft.seeds.some((seed) => !Number.isInteger(seed) || seed < 0)) {
      throw new Error("seeds must be non-negative integers");
    }
    for (const key of Object.keys(this.draft.parameter_overrides ?? {})) {
      if (forbiddenKeys.has(key.toLowerCase())) {
        throw new Error(`forbidden parameter: ${key}`);
      }
    }
  }
}
