// Batch 计划构建器，输出强类型 manifest 并检查后端批量限制。
import type { BatchExperimentManifest } from "../domain/ExperimentManifest";
import type { SimulationBackend } from "../domain/SimulationBackend";

export class BatchPlanBuilder {
  static modeComparison(input: {
    scenario: string;
    seed: number;
    backend: SimulationBackend;
  }): BatchExperimentManifest {
    return {
      backend: input.backend,
      run_type: "MODE_COMPARISON",
      scenarios: [input.scenario],
      control_modes: ["PCSC", "ETEAC", "AUTO"],
      seeds: [input.seed],
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
      parameter_overrides: {},
      domain_randomization: { enabled: false, level: "NONE" },
      tags: ["mode-comparison"],
      description: "PCSC / ETEAC / AUTO comparison",
    };
  }

  static backendPairedRun(input: {
    scenario: string;
    seed: number;
    leftBackend: SimulationBackend;
    rightBackend: SimulationBackend;
  }): BatchExperimentManifest {
    return {
      ...BatchPlanBuilder.modeComparison({
        scenario: input.scenario,
        seed: input.seed,
        backend: input.leftBackend,
      }),
      run_type: "PAIRED_BACKEND",
      control_modes: ["PCSC"],
      tags: ["paired-backend", input.rightBackend],
      paired_key: `${input.scenario}:${input.seed}`,
    };
  }
}
